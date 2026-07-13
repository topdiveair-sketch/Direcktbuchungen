
from __future__ import annotations

from datetime import date, datetime, timedelta
from flask import flash, jsonify, redirect, render_template, request, url_for


def init_smart_host(app, db, require_admin, ROOMS):
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS laundry_stock(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL UNIQUE,
            clean_quantity INTEGER NOT NULL DEFAULT 0,
            dirty_quantity INTEGER NOT NULL DEFAULT 0,
            minimum_clean INTEGER NOT NULL DEFAULT 0,
            last_update TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS maintenance_schedule(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            interval_days INTEGER NOT NULL DEFAULT 30,
            last_done TEXT NOT NULL DEFAULT '',
            next_due TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offen',
            note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS route_content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assistant TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            link TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS autopilot_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time TEXT NOT NULL,
            sync_status TEXT NOT NULL DEFAULT '',
            backup_status TEXT NOT NULL DEFAULT '',
            daily_status TEXT NOT NULL DEFAULT '',
            recommendations INTEGER NOT NULL DEFAULT 0,
            details TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS smart_recommendations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rec_date TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'offen',
            created_at TEXT NOT NULL
        );
        """)

        if conn.execute("SELECT COUNT(*) c FROM laundry_stock").fetchone()["c"] == 0:
            defaults = [
                ("Bettwäsche-Sets", 8, 0, 4),
                ("Handtuch-Sets", 16, 0, 8),
                ("Badvorleger", 8, 0, 4),
                ("Geschirrtücher", 12, 0, 6),
            ]
            now = datetime.now().isoformat(timespec="seconds")
            for item, clean, dirty, minimum in defaults:
                conn.execute(
                    """INSERT INTO laundry_stock(item,clean_quantity,dirty_quantity,minimum_clean,last_update)
                       VALUES(?,?,?,?,?)""",
                    (item, clean, dirty, minimum, now),
                )

        if conn.execute("SELECT COUNT(*) c FROM maintenance_schedule").fetchone()["c"] == 0:
            today = date.today()
            defaults = [
                ("", "Rauchmelder prüfen", 180),
                ("", "Feuerlöscher kontrollieren", 365),
                ("", "Kaffeemaschine entkalken", 30),
                ("", "Fahrradwerkzeug prüfen", 60),
            ]
            for room in ROOMS:
                defaults.append((room, "Zimmer-Grundkontrolle", 90))
            for room, title, interval in defaults:
                conn.execute(
                    """INSERT INTO maintenance_schedule
                       (room,title,interval_days,last_done,next_due,status)
                       VALUES(?,?,?,?,?,'offen')""",
                    ("", title, interval, "", (today + timedelta(days=interval)).isoformat())
                    if room == "" else
                    (room, title, interval, "", (today + timedelta(days=interval)).isoformat())
                )

        if conn.execute("SELECT COUNT(*) c FROM route_content").fetchone()["c"] == 0:
            rows = [
                ("Fidel","Wandern","Welterbesteig Wachau","Etappen, Orientierung und Hinweise für Wanderer.",""),
                ("Fidel","Rad","Donauradweg","Informationen zu Radweg, E-Bike-Laden und Gepäcktransport.",""),
                ("Fidel","Ausflug","Aggstein","Ausflugsidee zur Burgruine Aggstein.",""),
                ("Gloria","Haus","Frühstück","Frühstück, Hausregeln und Zimmerablauf.",""),
                ("Pia","Kinder","Windis-Rätsel","Rätsel und kleine Aufgaben für Kinder.",""),
                ("Pia","Kinder","Wachau-Schatzsuche","Vorbereitete Schatzsuche rund um die Unterkunft.",""),
            ]
            for a,c,t,d,l in rows:
                conn.execute(
                    "INSERT INTO route_content(assistant,category,title,description,link) VALUES(?,?,?,?,?)",
                    (a,c,t,d,l),
                )

    def occupancy_for_period(start, end):
        total_room_nights = max(1, (end-start).days * len(ROOMS))
        occupied = 0
        with db() as conn:
            rows = conn.execute(
                """SELECT arrival,departure FROM bookings
                   WHERE status!='cancelled' AND arrival<? AND departure>?""",
                (end.isoformat(), start.isoformat()),
            ).fetchall()
        for row in rows:
            a = max(start, date.fromisoformat(row["arrival"]))
            b = min(end, date.fromisoformat(row["departure"]))
            if b > a:
                occupied += (b-a).days
        return round(occupied / total_room_nights * 100, 1)

    def build_recommendations():
        today = date.today()
        today_iso = today.isoformat()
        two_weeks = today + timedelta(days=14)
        occupancy = occupancy_for_period(today, two_weeks)
        with db() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) c FROM smart_recommendations WHERE rec_date=?",
                (today_iso,),
            ).fetchone()["c"]
            if existing:
                return

            recs = []
            if occupancy < 40:
                recs.append(("Marketing","Auslastung niedrig",
                             f"Die Auslastung der nächsten 14 Tage liegt bei {occupancy} %. Ein Google-Post oder Direktbuchungsangebot ist sinnvoll.","hoch"))
            elif occupancy < 65:
                recs.append(("Marketing","Auslastung ausbaufähig",
                             f"Die Auslastung der nächsten 14 Tage liegt bei {occupancy} %. Freie Wochenenden gezielt bewerben.","normal"))

            laundry = conn.execute(
                "SELECT * FROM laundry_stock WHERE clean_quantity<minimum_clean"
            ).fetchall()
            for row in laundry:
                recs.append(("Gloria","Wäschebestand niedrig",
                             f"{row['item']}: nur {row['clean_quantity']} sauber, Minimum {row['minimum_clean']}.","hoch"))

            maint = conn.execute(
                "SELECT * FROM maintenance_schedule WHERE next_due<=? AND status!='erledigt'",
                (today_iso,),
            ).fetchall()
            for row in maint:
                room = f" ({row['room']})" if row["room"] else ""
                recs.append(("Wartung",row["title"]+room,
                             f"Fällig seit {row['next_due']}.","hoch"))

            open_reviews = conn.execute(
                "SELECT value FROM site_settings WHERE key='google_review_count'"
            ).fetchone()
            if open_reviews and int(float(open_reviews["value"] or 0)) == 0:
                recs.append(("Marketing","Google-Bewertungen aktivieren",
                             "Noch keine Google-Bewertungen eingetragen. Bewertungslink und Anzahl im Adminbereich ergänzen.","normal"))

            for cat,title,msg,prio in recs:
                conn.execute(
                    """INSERT INTO smart_recommendations
                       (rec_date,category,title,message,priority,status,created_at)
                       VALUES(?,?,?,?,?,'offen',?)""",
                    (today_iso,cat,title,msg,prio,datetime.now().isoformat(timespec="seconds")),
                )

    def run_autopilot():
        details = []
        sync_status = "nicht ausgeführt"
        backup_status = "nicht ausgeführt"
        daily_status = "bereit"

        sync_func = app.extensions.get("zab_sync_room")
        if sync_func:
            counts = []
            for room in ROOMS:
                try:
                    count, msg = sync_func(room)
                    counts.append(f"{room}:{count}")
                except Exception as exc:
                    counts.append(f"{room}:Fehler")
            sync_status = ", ".join(counts)

        backup_func = app.extensions.get("zab_create_backup")
        if backup_func:
            try:
                path = backup_func("autopilot")
                backup_status = str(path) if path else "kein Backup"
            except Exception as exc:
                backup_status = f"Fehler: {exc}"

        build_recommendations()

        with db() as conn:
            rec_count = conn.execute(
                "SELECT COUNT(*) c FROM smart_recommendations WHERE rec_date=? AND status='offen'",
                (date.today().isoformat(),),
            ).fetchone()["c"]
            conn.execute(
                """INSERT INTO autopilot_runs
                   (run_time,sync_status,backup_status,daily_status,recommendations,details)
                   VALUES(?,?,?,?,?,?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    sync_status, backup_status, daily_status, rec_count,
                    "Autopilot abgeschlossen",
                ),
            )
        return rec_count

    @app.get("/smart")
    def smart_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        build_recommendations()
        today = date.today()
        next_arrival = None
        with db() as conn:
            row = conn.execute(
                """SELECT * FROM bookings
                   WHERE arrival>=? AND status!='cancelled'
                   ORDER BY arrival LIMIT 1""",
                (today.isoformat(),),
            ).fetchone()
            if row:
                next_arrival = row
            recommendations = conn.execute(
                """SELECT * FROM smart_recommendations
                   WHERE status='offen' ORDER BY CASE priority WHEN 'hoch' THEN 1 ELSE 2 END,id"""
            ).fetchall()
            laundry = conn.execute("SELECT * FROM laundry_stock ORDER BY item").fetchall()
            maintenance = conn.execute(
                "SELECT * FROM maintenance_schedule ORDER BY next_due,title"
            ).fetchall()
            last_run = conn.execute(
                "SELECT * FROM autopilot_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        countdown_days = None
        if next_arrival:
            countdown_days = (date.fromisoformat(next_arrival["arrival"]) - today).days

        return render_template(
            "smart_dashboard.html",
            next_arrival=next_arrival,
            countdown_days=countdown_days,
            occupancy_14=occupancy_for_period(today, today+timedelta(days=14)),
            occupancy_30=occupancy_for_period(today, today+timedelta(days=30)),
            recommendations=recommendations,
            laundry=laundry,
            maintenance=maintenance,
            last_run=last_run,
        )

    @app.post("/autopilot/run")
    def autopilot_run():
        if not require_admin():
            return redirect(url_for("admin_login"))
        count = run_autopilot()
        flash(f"Autopilot abgeschlossen. {count} Hinweise offen.", "success")
        return redirect(url_for("smart_dashboard"))

    @app.post("/smart/recommendation/<int:rec_id>/done")
    def recommendation_done(rec_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE smart_recommendations SET status='erledigt' WHERE id=?", (rec_id,))
        return redirect(url_for("smart_dashboard"))

    @app.route("/smart/laundry", methods=["GET","POST"])
    def laundry_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            item_id = int(request.form["item_id"])
            with db() as conn:
                conn.execute(
                    """UPDATE laundry_stock SET clean_quantity=?,dirty_quantity=?,
                       minimum_clean=?,last_update=? WHERE id=?""",
                    (
                        int(request.form.get("clean_quantity","0")),
                        int(request.form.get("dirty_quantity","0")),
                        int(request.form.get("minimum_clean","0")),
                        datetime.now().isoformat(timespec="seconds"),
                        item_id,
                    ),
                )
            return redirect(url_for("laundry_center"))
        with db() as conn:
            rows = conn.execute("SELECT * FROM laundry_stock ORDER BY item").fetchall()
        return render_template("laundry_center.html", rows=rows)

    @app.route("/smart/maintenance", methods=["GET","POST"])
    def maintenance_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute(
                    """INSERT INTO maintenance_schedule
                       (room,title,interval_days,last_done,next_due,status,note)
                       VALUES(?,?,?,'',?,'offen',?)""",
                    (
                        request.form.get("room",""),
                        request.form["title"],
                        int(request.form.get("interval_days","30")),
                        request.form["next_due"],
                        request.form.get("note",""),
                    ),
                )
            return redirect(url_for("maintenance_center"))
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM maintenance_schedule ORDER BY next_due,title"
            ).fetchall()
        return render_template("maintenance_center.html", rows=rows)

    @app.post("/smart/maintenance/<int:item_id>/done")
    def maintenance_done(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        today = date.today()
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM maintenance_schedule WHERE id=?", (item_id,)
            ).fetchone()
            next_due = (today + timedelta(days=int(row["interval_days"]))).isoformat()
            conn.execute(
                """UPDATE maintenance_schedule
                   SET last_done=?,next_due=?,status='offen' WHERE id=?""",
                (today.isoformat(), next_due, item_id),
            )
        return redirect(url_for("maintenance_center"))

    @app.get("/fidel")
    def fidel_center():
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM route_content WHERE assistant='Fidel' AND enabled=1 ORDER BY category,title"
            ).fetchall()
        return render_template("assistant_public.html", assistant="Fidel", rows=rows)

    @app.get("/pia")
    def pia_center():
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM route_content WHERE assistant='Pia' AND enabled=1 ORDER BY category,title"
            ).fetchall()
        return render_template("assistant_public.html", assistant="Pia", rows=rows)

    @app.get("/smart/status.json")
    def smart_status():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        today = date.today()
        with db() as conn:
            recs = conn.execute(
                "SELECT COUNT(*) c FROM smart_recommendations WHERE status='offen'"
            ).fetchone()["c"]
        return jsonify(
            occupancy_14=occupancy_for_period(today,today+timedelta(days=14)),
            occupancy_30=occupancy_for_period(today,today+timedelta(days=30)),
            recommendations=recs,
        )

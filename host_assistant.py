
from __future__ import annotations
from datetime import date, datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for


def init_host_assistant(app, db, require_admin, ROOMS):
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cleaning_templates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            item TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 100,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS cleaning_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            run_date TEXT NOT NULL,
            booking_id INTEGER,
            status TEXT NOT NULL DEFAULT 'offen',
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS cleaning_run_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            done_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS breakfast_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            booking_id INTEGER NOT NULL,
            room TEXT NOT NULL,
            adults INTEGER NOT NULL DEFAULT 1,
            preference TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offen',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_closings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            closing_date TEXT NOT NULL UNIQUE,
            revenue REAL NOT NULL DEFAULT 0,
            costs REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL DEFAULT 0,
            open_items INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            closed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS host_preferences(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        defaults = {
            "welcome_name": "Hans",
            "weather_location": "Aggsbach Markt",
            "default_checkin_time": "15:00",
            "default_checkout_time": "10:00",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO host_preferences(key,value) VALUES(?,?)",
                (key, value),
            )

        existing = conn.execute("SELECT COUNT(*) c FROM cleaning_templates").fetchone()["c"]
        if existing == 0:
            checklist = [
                "Fenster öffnen und lüften",
                "Bettwäsche abziehen",
                "Bett frisch beziehen",
                "Bad und Dusche reinigen",
                "WC reinigen",
                "Spiegel und Armaturen reinigen",
                "Handtücher austauschen",
                "Müll leeren",
                "Staubsaugen",
                "Boden wischen",
                "Kaffee und Verbrauchsmaterial auffüllen",
                "Zimmerschlüssel kontrollieren",
                "Endkontrolle durchführen",
            ]
            for room in ROOMS:
                for order, item in enumerate(checklist, start=10):
                    conn.execute(
                        "INSERT INTO cleaning_templates(room,item,sort_order) VALUES(?,?,?)",
                        (room, item, order),
                    )

    def prefs():
        with db() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM host_preferences")}

    def ensure_cleaning_run(room, booking_id=None, run_date=None):
        run_date = run_date or date.today().isoformat()
        with db() as conn:
            run = conn.execute(
                """SELECT * FROM cleaning_runs
                   WHERE room=? AND run_date=? AND status!='erledigt'
                   ORDER BY id DESC LIMIT 1""",
                (room, run_date),
            ).fetchone()
            if run:
                return run["id"]
            cur = conn.execute(
                """INSERT INTO cleaning_runs(room,run_date,booking_id,status)
                   VALUES(?,?,?,'offen')""",
                (room, run_date, booking_id),
            )
            run_id = cur.lastrowid
            items = conn.execute(
                """SELECT item FROM cleaning_templates
                   WHERE room=? AND enabled=1 ORDER BY sort_order,id""",
                (room,),
            ).fetchall()
            for item in items:
                conn.execute(
                    "INSERT INTO cleaning_run_items(run_id,item) VALUES(?,?)",
                    (run_id, item["item"]),
                )
            return run_id

    def ensure_breakfast_runs(run_date=None):
        run_date = run_date or date.today().isoformat()
        with db() as conn:
            rows = conn.execute(
                """SELECT * FROM bookings
                   WHERE arrival<=? AND departure>? AND breakfast=1
                   AND status!='cancelled' ORDER BY room""",
                (run_date, run_date),
            ).fetchall()
            for b in rows:
                found = conn.execute(
                    "SELECT 1 FROM breakfast_runs WHERE run_date=? AND booking_id=?",
                    (run_date, b["id"]),
                ).fetchone()
                if not found:
                    pref = ""
                    gp = conn.execute(
                        "SELECT breakfast_preference FROM guest_profiles WHERE email=?",
                        (b["email"],),
                    ).fetchone()
                    if gp:
                        pref = gp["breakfast_preference"] or ""
                    conn.execute(
                        """INSERT INTO breakfast_runs
                           (run_date,booking_id,room,adults,preference,status,created_at)
                           VALUES(?,?,?,?,?,'offen',?)""",
                        (
                            run_date, b["id"], b["room"], b["adults"], pref,
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )

    @app.get("/assistent")
    def host_assistant():
        if not require_admin():
            return redirect(url_for("admin_login"))

        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        ensure_breakfast_runs(today)

        with db() as conn:
            arrivals = conn.execute(
                "SELECT * FROM bookings WHERE arrival=? AND status!='cancelled' ORDER BY room",
                (today,),
            ).fetchall()
            departures = conn.execute(
                "SELECT * FROM bookings WHERE departure=? AND status!='cancelled' ORDER BY room",
                (today,),
            ).fetchall()
            breakfast = conn.execute(
                "SELECT * FROM breakfast_runs WHERE run_date=? ORDER BY room",
                (today,),
            ).fetchall()
            open_cleaning = conn.execute(
                "SELECT * FROM cleaning_runs WHERE run_date=? AND status!='erledigt' ORDER BY room",
                (today,),
            ).fetchall()
            open_payments = conn.execute(
                """SELECT * FROM bookings WHERE status='confirmed' AND paid=0
                   AND arrival<=? ORDER BY arrival,room""",
                (today,),
            ).fetchall()
            tomorrow_arrivals = conn.execute(
                "SELECT * FROM bookings WHERE arrival=? AND status!='cancelled' ORDER BY room",
                (tomorrow,),
            ).fetchall()
            open_tasks = conn.execute(
                """SELECT * FROM tasks WHERE status!='erledigt'
                   AND (due_date='' OR due_date<=?)
                   ORDER BY CASE priority WHEN 'hoch' THEN 1
                                          WHEN 'normal' THEN 2 ELSE 3 END,id""",
                (today,),
            ).fetchall()
            open_orders = conn.execute(
                """SELECT o.*,b.room,b.first_name,b.last_name FROM guest_orders o
                   JOIN bookings b ON b.id=o.booking_id
                   WHERE o.status='offen' ORDER BY o.created_at"""
            ).fetchall()
            shopping = conn.execute(
                "SELECT * FROM shopping_items WHERE status!='erledigt' ORDER BY category,item"
            ).fetchall()
            inventory_alerts = conn.execute(
                """SELECT * FROM room_inventory
                   WHERE quantity<minimum_quantity OR condition!='gut'
                   ORDER BY room,item"""
            ).fetchall()
            revenue = conn.execute(
                """SELECT COALESCE(SUM(total),0) value FROM bookings
                   WHERE arrival=? AND status!='cancelled'""",
                (today,),
            ).fetchone()["value"]
            costs = conn.execute(
                """SELECT COALESCE(SUM(amount),0) value FROM operating_costs
                   WHERE cost_date=?""",
                (today,),
            ).fetchone()["value"]

        total_people = sum(int(b["adults"]) for b in breakfast)
        high_priority = len([t for t in open_tasks if t["priority"] == "hoch"])
        recommendation = "Alles ruhig – heute den Betrieb sauber abarbeiten."
        if inventory_alerts:
            recommendation = "Gloria empfiehlt: Inventarwarnungen heute prüfen."
        elif tomorrow_arrivals and not open_cleaning:
            recommendation = "Zimmer für die morgigen Anreisen vorbereiten."
        elif open_payments:
            recommendation = "Offene Zahlungen vor dem Tagesabschluss prüfen."
        elif not arrivals and not departures:
            recommendation = "Ruhiger Tag – gute Gelegenheit für Marketing oder Wartung."

        return render_template(
            "host_assistant.html",
            settings=prefs(),
            today=today,
            arrivals=arrivals,
            departures=departures,
            breakfast=breakfast,
            breakfast_people=total_people,
            open_cleaning=open_cleaning,
            open_payments=open_payments,
            tomorrow_arrivals=tomorrow_arrivals,
            open_tasks=open_tasks,
            open_orders=open_orders,
            shopping=shopping,
            inventory_alerts=inventory_alerts,
            revenue=float(revenue or 0),
            costs=float(costs or 0),
            profit=float(revenue or 0)-float(costs or 0),
            high_priority=high_priority,
            recommendation=recommendation,
        )

    @app.get("/reinigung/<int:run_id>")
    def cleaning_mode(run_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            run = conn.execute("SELECT * FROM cleaning_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return "Reinigung nicht gefunden", 404
            items = conn.execute(
                "SELECT * FROM cleaning_run_items WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return render_template("cleaning_mode.html", run=run, items=items)

    @app.post("/reinigung/start/<room>")
    def cleaning_start(room):
        if not require_admin():
            return redirect(url_for("admin_login"))
        booking_id = request.form.get("booking_id")
        run_id = ensure_cleaning_run(room, int(booking_id) if booking_id else None)
        with db() as conn:
            conn.execute(
                "UPDATE cleaning_runs SET status='in Arbeit',started_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), run_id),
            )
            conn.execute(
                """UPDATE housekeeping SET status='Reinigung',updated_at=?
                   WHERE room=?""",
                (datetime.now().isoformat(timespec="seconds"), room),
            )
        return redirect(url_for("cleaning_mode", run_id=run_id))

    @app.post("/reinigung/item/<int:item_id>/toggle")
    def cleaning_item_toggle(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            item = conn.execute(
                """SELECT i.*,r.id run_id FROM cleaning_run_items i
                   JOIN cleaning_runs r ON r.id=i.run_id WHERE i.id=?""",
                (item_id,),
            ).fetchone()
            if not item:
                return "Nicht gefunden", 404
            new_value = 0 if item["done"] else 1
            conn.execute(
                "UPDATE cleaning_run_items SET done=?,done_at=? WHERE id=?",
                (
                    new_value,
                    datetime.now().isoformat(timespec="seconds") if new_value else "",
                    item_id,
                ),
            )
        return redirect(url_for("cleaning_mode", run_id=item["run_id"]))

    @app.post("/reinigung/<int:run_id>/finish")
    def cleaning_finish(run_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            run = conn.execute("SELECT * FROM cleaning_runs WHERE id=?", (run_id,)).fetchone()
            remaining = conn.execute(
                "SELECT COUNT(*) c FROM cleaning_run_items WHERE run_id=? AND done=0",
                (run_id,),
            ).fetchone()["c"]
            if remaining:
                flash(f"Noch {remaining} Punkte offen.", "error")
                return redirect(url_for("cleaning_mode", run_id=run_id))
            conn.execute(
                "UPDATE cleaning_runs SET status='erledigt',finished_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), run_id),
            )
            conn.execute(
                """UPDATE housekeeping SET status='fertig',note='Endkontrolle erledigt',
                   updated_at=? WHERE room=?""",
                (datetime.now().isoformat(timespec="seconds"), run["room"]),
            )
        flash("Zimmer ist fertig und freigegeben.", "success")
        return redirect(url_for("host_assistant"))

    @app.get("/fruehstueck")
    def breakfast_mode():
        if not require_admin():
            return redirect(url_for("admin_login"))
        today = date.today().isoformat()
        ensure_breakfast_runs(today)
        with db() as conn:
            runs = conn.execute(
                "SELECT * FROM breakfast_runs WHERE run_date=? ORDER BY room",
                (today,),
            ).fetchall()
        total_people = sum(int(r["adults"]) for r in runs)
        return render_template(
            "breakfast_mode.html",
            runs=runs,
            total_people=total_people,
            today=today,
        )

    @app.post("/fruehstueck/<int:run_id>/done")
    def breakfast_done(run_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE breakfast_runs SET status='erledigt' WHERE id=?", (run_id,))
        return redirect(url_for("breakfast_mode"))

    @app.post("/tagesabschluss")
    def daily_closing():
        if not require_admin():
            return redirect(url_for("admin_login"))
        today = date.today().isoformat()
        with db() as conn:
            revenue = conn.execute(
                """SELECT COALESCE(SUM(total),0) value FROM bookings
                   WHERE arrival=? AND status!='cancelled'""",
                (today,),
            ).fetchone()["value"]
            costs = conn.execute(
                "SELECT COALESCE(SUM(amount),0) value FROM operating_costs WHERE cost_date=?",
                (today,),
            ).fetchone()["value"]
            open_items = 0
            for table, condition in [
                ("tasks", "status!='erledigt'"),
                ("guest_orders", "status='offen'"),
                ("shopping_items", "status!='erledigt'"),
                ("cleaning_runs", "run_date=? AND status!='erledigt'"),
                ("breakfast_runs", "run_date=? AND status!='erledigt'"),
            ]:
                if "?" in condition:
                    open_items += conn.execute(
                        f"SELECT COUNT(*) c FROM {table} WHERE {condition}",
                        (today,),
                    ).fetchone()["c"]
                else:
                    open_items += conn.execute(
                        f"SELECT COUNT(*) c FROM {table} WHERE {condition}"
                    ).fetchone()["c"]

            conn.execute(
                """INSERT INTO daily_closings
                   (closing_date,revenue,costs,profit,open_items,notes,closed_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(closing_date) DO UPDATE SET
                       revenue=excluded.revenue,
                       costs=excluded.costs,
                       profit=excluded.profit,
                       open_items=excluded.open_items,
                       notes=excluded.notes,
                       closed_at=excluded.closed_at""",
                (
                    today, float(revenue or 0), float(costs or 0),
                    float(revenue or 0)-float(costs or 0), int(open_items),
                    request.form.get("notes","").strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        flash("Tagesabschluss wurde gespeichert.", "success")
        return redirect(url_for("host_assistant"))

    @app.get("/assistent/status.json")
    def assistant_status():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        today = date.today().isoformat()
        ensure_breakfast_runs(today)
        with db() as conn:
            data = {
                "arrivals": conn.execute(
                    "SELECT COUNT(*) c FROM bookings WHERE arrival=? AND status!='cancelled'",
                    (today,),
                ).fetchone()["c"],
                "departures": conn.execute(
                    "SELECT COUNT(*) c FROM bookings WHERE departure=? AND status!='cancelled'",
                    (today,),
                ).fetchone()["c"],
                "breakfast_open": conn.execute(
                    "SELECT COUNT(*) c FROM breakfast_runs WHERE run_date=? AND status!='erledigt'",
                    (today,),
                ).fetchone()["c"],
                "cleaning_open": conn.execute(
                    "SELECT COUNT(*) c FROM cleaning_runs WHERE run_date=? AND status!='erledigt'",
                    (today,),
                ).fetchone()["c"],
            }
        return jsonify(data)

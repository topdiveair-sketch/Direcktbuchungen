
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Response, flash, jsonify, redirect, render_template,
    request, session, url_for
)


def init_zab_os(app, DB_PATH, db, require_admin, ROOMS):
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS guest_profiles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            country TEXT NOT NULL DEFAULT '',
            preferred_room TEXT NOT NULL DEFAULT '',
            breakfast_preference TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            stays INTEGER NOT NULL DEFAULT 0,
            total_revenue REAL NOT NULL DEFAULT 0,
            last_stay TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Allgemein',
            priority TEXT NOT NULL DEFAULT 'normal',
            due_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offen',
            assigned_to TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS room_inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            minimum_quantity INTEGER NOT NULL DEFAULT 1,
            condition TEXT NOT NULL DEFAULT 'gut',
            last_check TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS operating_costs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL DEFAULT 0,
            cost_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS windis_content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS marketing_ideas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Idee',
            planned_date TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monteur_channel_windows(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'zimmmer.at',
            status TEXT NOT NULL DEFAULT 'not_published',
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(start_date, end_date, channel)
        );
        """)

        # Grundinventar nur einmal anlegen
        existing = conn.execute("SELECT COUNT(*) c FROM room_inventory").fetchone()["c"]
        if existing == 0:
            base_items = [
                ("Bettwäsche", 2, 2),
                ("Handtuchsets", 4, 4),
                ("Föhn", 1, 1),
                ("Fernbedienung", 1, 1),
                ("Rauchmelder", 1, 1),
                ("Zimmerschlüssel", 2, 2),
                ("Trinkgläser", 2, 2),
            ]
            for room in ROOMS:
                for item, qty, minimum in base_items:
                    conn.execute(
                        """INSERT INTO room_inventory
                           (room,item,quantity,minimum_quantity,condition,last_check)
                           VALUES(?,?,?,?, 'gut', ?)""",
                        (room, item, qty, minimum, date.today().isoformat())
                    )

        windis_existing = conn.execute("SELECT COUNT(*) c FROM windis_content").fetchone()["c"]
        if windis_existing == 0:
            defaults = [
                ("Fidel", "Aktiv", "Welterbesteig", "Fidel hilft bei Etappen, Wanderrouten, Wetter und Orientierung."),
                ("Fidel", "Aktiv", "Donauradweg", "Fidel kennt Radwege, Abstellmöglichkeiten und E-Bike-Laden."),
                ("Gloria", "Haus", "Frühstück", "Gloria erklärt Frühstück, Hausregeln, Ordnung und Zimmerabläufe."),
                ("Gloria", "Haus", "Anreise", "Gloria hilft beim Check-in, bei Schlüsseln und Ankunftszeiten."),
                ("Pia", "Familie", "Abenteuer", "Pia begleitet Kinder mit Rätseln, Geschichten und Wachau-Abenteuern."),
                ("Pia", "Familie", "Bücher", "Pia stellt die Wilden Wachauer Windis und ihre Geschichten vor."),
            ]
            now = datetime.now().isoformat(timespec="seconds")
            for char, cat, title, content in defaults:
                conn.execute(
                    """INSERT INTO windis_content(character,category,title,content,created_at)
                       VALUES(?,?,?,?,?)""",
                    (char, cat, title, content, now)
                )

    def refresh_guest_profiles():
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            rows = conn.execute("""
                SELECT email,
                       MAX(first_name) first_name,
                       MAX(last_name) last_name,
                       MAX(phone) phone,
                       COUNT(*) stays,
                       COALESCE(SUM(CASE WHEN status!='cancelled' THEN total ELSE 0 END),0) total_revenue,
                       MAX(departure) last_stay,
                       MAX(room) preferred_room
                FROM bookings
                WHERE email IS NOT NULL AND email!=''
                GROUP BY email
            """).fetchall()
            for row in rows:
                conn.execute("""
                    INSERT INTO guest_profiles
                    (email,first_name,last_name,phone,preferred_room,stays,total_revenue,last_stay,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(email) DO UPDATE SET
                        first_name=excluded.first_name,
                        last_name=excluded.last_name,
                        phone=excluded.phone,
                        preferred_room=excluded.preferred_room,
                        stays=excluded.stays,
                        total_revenue=excluded.total_revenue,
                        last_stay=excluded.last_stay,
                        updated_at=excluded.updated_at
                """, (
                    row["email"], row["first_name"] or "", row["last_name"] or "",
                    row["phone"] or "", row["preferred_room"] or "", int(row["stays"] or 0),
                    float(row["total_revenue"] or 0), row["last_stay"] or "", now, now
                ))

    def month_profit(month_prefix):
        with db() as conn:
            revenue = conn.execute("""
                SELECT COALESCE(SUM(total),0) value
                FROM bookings
                WHERE arrival LIKE ? AND status!='cancelled'
            """, (month_prefix + "%",)).fetchone()["value"]
            costs = conn.execute("""
                SELECT COALESCE(SUM(amount),0) value
                FROM operating_costs
                WHERE cost_date LIKE ?
            """, (month_prefix + "%",)).fetchone()["value"]
        return float(revenue or 0), float(costs or 0), float(revenue or 0) - float(costs or 0)

    MONTEUR_ROOM = "Bachblick"
    MONTEUR_CHANNEL = "zimmmer.at"
    MONTEUR_CHANNEL_URL = "https://www.zimmmer.at/de/einstellungen"
    MONTEUR_WINTER_MONTHS = {11, 12, 1, 2, 3}
    MONTEUR_NIGHTS = 5
    MONTEUR_MAX_GUESTS = 2
    MONTEUR_TWO_PERSON_PRICE_PER_PERSON = 55.0
    MONTEUR_SINGLE_ROOM_PRICE = 80.0

    def _monteur_blocker(conn, start_day, end_day):
        booking = conn.execute(
            """SELECT 1 FROM bookings
               WHERE room=?
                 AND status IN ('pending','confirmed')
                 AND arrival < ?
                 AND departure > ?
               LIMIT 1""",
            (MONTEUR_ROOM, end_day.isoformat(), start_day.isoformat()),
        ).fetchone()
        if booking:
            return "Direktbuchung"

        external = conn.execute(
            """SELECT 1 FROM external_blocks
               WHERE room=?
                 AND start_date < ?
                 AND end_date > ?
               LIMIT 1""",
            (MONTEUR_ROOM, end_day.isoformat(), start_day.isoformat()),
        ).fetchone()
        if external:
            return "Externer Buchungskanal"

        closed = conn.execute(
            """SELECT 1 FROM central_overrides
               WHERE room=?
                 AND availability=0
                 AND day>=?
                 AND day<?
               LIMIT 1""",
            (MONTEUR_ROOM, start_day.isoformat(), end_day.isoformat()),
        ).fetchone()
        if closed:
            return "Im Master-Kalender gesperrt"
        return ""

    def monteur_gap_windows(limit=18, horizon_weeks=64):
        today_day = date.today()
        days_to_sunday = (6 - today_day.weekday()) % 7
        first_sunday = today_day + timedelta(days=days_to_sunday)
        windows = []

        with db() as conn:
            states = {
                (row["start_date"], row["end_date"]): row
                for row in conn.execute(
                    """SELECT start_date,end_date,status,note,updated_at
                       FROM monteur_channel_windows
                       WHERE channel=?""",
                    (MONTEUR_CHANNEL,),
                ).fetchall()
            }

            for week in range(horizon_weeks + 1):
                start_day = first_sunday + timedelta(days=7 * week)
                end_day = start_day + timedelta(days=MONTEUR_NIGHTS)
                nights = [start_day + timedelta(days=i) for i in range(MONTEUR_NIGHTS)]
                if not all(day.month in MONTEUR_WINTER_MONTHS for day in nights):
                    continue

                blocker = _monteur_blocker(conn, start_day, end_day)
                state = states.get((start_day.isoformat(), end_day.isoformat()))
                status = str(state["status"]) if state else "not_published"
                note = str(state["note"] or "") if state else ""
                updated_at = str(state["updated_at"] or "") if state else ""

                windows.append({
                    "start_date": start_day.isoformat(),
                    "end_date": end_day.isoformat(),
                    "start_label": start_day.strftime("%d.%m.%Y"),
                    "end_label": end_day.strftime("%d.%m.%Y"),
                    "available": not blocker,
                    "blocker": blocker,
                    "channel_status": status,
                    "channel_note": note,
                    "updated_at": updated_at,
                    "nights": MONTEUR_NIGHTS,
                    "single_total": round(MONTEUR_SINGLE_ROOM_PRICE * MONTEUR_NIGHTS, 2),
                    "double_total": round(
                        MONTEUR_TWO_PERSON_PRICE_PER_PERSON * MONTEUR_MAX_GUESTS * MONTEUR_NIGHTS,
                        2,
                    ),
                    "double_pppn": MONTEUR_TWO_PERSON_PRICE_PER_PERSON,
                    "single_room_rate": MONTEUR_SINGLE_ROOM_PRICE,
                })
                if len(windows) >= limit:
                    break

        return windows

    def monteur_gap_summary():
        windows = monteur_gap_windows(limit=18)
        free = [window for window in windows if window["available"]]
        published = [
            window for window in windows
            if window["available"] and window["channel_status"] == "published"
        ]
        next_free = free[0] if free else None
        return {
            "free_windows": len(free),
            "published_windows": len(published),
            "next_free": next_free,
            "weekly_single": round(MONTEUR_SINGLE_ROOM_PRICE * MONTEUR_NIGHTS, 2),
            "weekly_double": round(
                MONTEUR_TWO_PERSON_PRICE_PER_PERSON * MONTEUR_MAX_GUESTS * MONTEUR_NIGHTS,
                2,
            ),
        }

    @app.get("/os")
    def os_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))

        refresh_guest_profiles()
        today = date.today().isoformat()
        month_prefix = date.today().strftime("%Y-%m")

        with db() as conn:
            arrivals = conn.execute(
                "SELECT * FROM bookings WHERE arrival=? AND status!='cancelled' ORDER BY room",
                (today,)
            ).fetchall()
            departures = conn.execute(
                "SELECT * FROM bookings WHERE departure=? AND status!='cancelled' ORDER BY room",
                (today,)
            ).fetchall()
            open_tasks = conn.execute(
                """SELECT * FROM tasks WHERE status!='erledigt'
                   ORDER BY CASE priority WHEN 'hoch' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                            due_date, id"""
            ).fetchall()
            room_status = conn.execute("SELECT * FROM housekeeping ORDER BY room").fetchall()
            guests = conn.execute("SELECT COUNT(*) c FROM guest_profiles").fetchone()["c"]
            low_stock = conn.execute(
                "SELECT COUNT(*) c FROM room_inventory WHERE quantity<minimum_quantity OR condition!='gut'"
            ).fetchone()["c"]
            pending_bookings = conn.execute(
                "SELECT COUNT(*) c FROM bookings WHERE status='pending'"
            ).fetchone()["c"]
            unread_orders = conn.execute(
                "SELECT COUNT(*) c FROM guest_orders WHERE status='offen'"
            ).fetchone()["c"]

        revenue, costs, profit = month_profit(month_prefix)
        monteur_summary = monteur_gap_summary()

        guardian_state = app.extensions.get("projectos_system_guardian_state") or {}
        guardian_result = guardian_state.get("last_result") if isinstance(guardian_state, dict) else None

        revenue_status = {"available": False}
        revenue_provider = app.extensions.get("zab_revenue_management_status")
        if callable(revenue_provider):
            try:
                revenue_status = revenue_provider()
            except Exception as exc:
                revenue_status = {"available": False, "error": str(exc)}

        return render_template(
            "os_dashboard.html",
            guardian_result=guardian_result,
            revenue_status=revenue_status,
            arrivals=arrivals,
            departures=departures,
            open_tasks=open_tasks,
            room_status=room_status,
            guest_count=guests,
            low_stock=low_stock,
            pending_bookings=pending_bookings,
            unread_orders=unread_orders,
            revenue=revenue,
            costs=costs,
            profit=profit,
            monteur_summary=monteur_summary,
            today=today,
        )

    @app.get("/os/system-guardian/status")
    def system_guardian_status():
        if not require_admin():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        state = app.extensions.get("projectos_system_guardian_state") or {}
        result = state.get("last_result") if isinstance(state, dict) else None
        return jsonify({
            "ok": True,
            "scheduler_active": bool(app.extensions.get("projectos_system_guardian_scheduler")),
            "guardian": result,
        }), 200


    @app.route("/os/system-guardian", methods=["GET", "POST"])
    def system_guardian_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))

        runner = app.extensions.get("projectos_system_guardian_run")
        state = app.extensions.get("projectos_system_guardian_state") or {}
        action = request.form.get("action", "").strip().lower() if request.method == "POST" else ""

        if request.method == "POST":
            if not callable(runner):
                flash("System Guardian ist auf diesem Dienst nicht verfügbar.", "error")
            else:
                try:
                    result = runner(auto_repair=action == "repair")
                    if action == "repair":
                        flash(
                            f"Guardian-Prüfung abgeschlossen: {result.get('summary', {}).get('repairs_applied', 0)} sichere Reparatur(en) ausgeführt.",
                            "success",
                        )
                    else:
                        flash("Guardian-Prüfung abgeschlossen.", "success")
                except Exception as exc:
                    flash(f"Guardian-Prüfung fehlgeschlagen: {exc}", "error")
            return redirect(url_for("system_guardian_dashboard"))

        result = state.get("last_result") if isinstance(state, dict) else None
        if result is None and callable(runner):
            try:
                result = runner(auto_repair=False)
            except Exception as exc:
                result = {
                    "ok": False,
                    "status": "error",
                    "generated_at": "",
                    "summary": {"checks": 0, "errors": 1, "warnings": 0, "repairs_applied": 0, "manual_actions": 1},
                    "findings": [{
                        "component": "System Guardian",
                        "severity": "error",
                        "code": "guardian_run_failed",
                        "message": f"Prüfung konnte nicht ausgeführt werden: {exc}",
                        "repaired": False,
                        "manual_action_required": True,
                        "details": {},
                    }],
                }

        return render_template(
            "system_guardian.html",
            guardian=result,
            scheduler_active=bool(app.extensions.get("projectos_system_guardian_scheduler")),
        )


    @app.get("/os/guests")
    def guest_database():
        if not require_admin():
            return redirect(url_for("admin_login"))
        refresh_guest_profiles()
        query = request.args.get("q", "").strip()
        with db() as conn:
            if query:
                guests = conn.execute("""
                    SELECT * FROM guest_profiles
                    WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ?
                    ORDER BY last_name,first_name
                """, tuple(["%" + query + "%"] * 4)).fetchall()
            else:
                guests = conn.execute(
                    "SELECT * FROM guest_profiles ORDER BY last_stay DESC,last_name"
                ).fetchall()
        return render_template("guest_database.html", guests=guests, query=query)

    @app.route("/os/guest/<int:guest_id>", methods=["GET", "POST"])
    def guest_profile(guest_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    UPDATE guest_profiles
                    SET country=?,preferred_room=?,breakfast_preference=?,notes=?,updated_at=?
                    WHERE id=?
                """, (
                    request.form.get("country",""),
                    request.form.get("preferred_room",""),
                    request.form.get("breakfast_preference",""),
                    request.form.get("notes",""),
                    datetime.now().isoformat(timespec="seconds"),
                    guest_id
                ))
            flash("Gästeprofil gespeichert.", "success")
            return redirect(url_for("guest_profile", guest_id=guest_id))

        with db() as conn:
            guest = conn.execute("SELECT * FROM guest_profiles WHERE id=?", (guest_id,)).fetchone()
            if not guest:
                return "Gast nicht gefunden", 404
            bookings = conn.execute(
                "SELECT * FROM bookings WHERE email=? ORDER BY arrival DESC",
                (guest["email"],)
            ).fetchall()
        return render_template("guest_profile.html", guest=guest, bookings=bookings)

    @app.route("/os/tasks", methods=["GET", "POST"])
    def task_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO tasks(title,description,category,priority,due_date,assigned_to,created_at)
                    VALUES(?,?,?,?,?,?,?)
                """, (
                    request.form["title"].strip(),
                    request.form.get("description","").strip(),
                    request.form.get("category","Allgemein"),
                    request.form.get("priority","normal"),
                    request.form.get("due_date",""),
                    request.form.get("assigned_to",""),
                    datetime.now().isoformat(timespec="seconds")
                ))
            flash("Aufgabe angelegt.", "success")
            return redirect(url_for("task_center"))

        with db() as conn:
            tasks = conn.execute("""
                SELECT * FROM tasks
                ORDER BY CASE status WHEN 'offen' THEN 1 WHEN 'in Arbeit' THEN 2 ELSE 3 END,
                         CASE priority WHEN 'hoch' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                         due_date,id
            """).fetchall()
        return render_template("task_center.html", tasks=tasks)

    @app.post("/os/task/<int:task_id>/<action>")
    def task_action(task_id, action):
        if not require_admin():
            return redirect(url_for("admin_login"))
        status_map = {"start":"in Arbeit","done":"erledigt","open":"offen"}
        if action not in status_map:
            return "Ungültige Aktion", 400
        completed = datetime.now().isoformat(timespec="seconds") if action == "done" else ""
        with db() as conn:
            conn.execute(
                "UPDATE tasks SET status=?,completed_at=? WHERE id=?",
                (status_map[action], completed, task_id)
            )
        return redirect(url_for("task_center"))

    @app.route("/os/inventory", methods=["GET", "POST"])
    def inventory_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO room_inventory(room,item,quantity,minimum_quantity,condition,last_check,note)
                    VALUES(?,?,?,?,?,?,?)
                """, (
                    request.form["room"], request.form["item"].strip(),
                    int(request.form.get("quantity","1")),
                    int(request.form.get("minimum_quantity","1")),
                    request.form.get("condition","gut"),
                    date.today().isoformat(),
                    request.form.get("note","")
                ))
            flash("Inventar ergänzt.", "success")
            return redirect(url_for("inventory_center"))

        with db() as conn:
            inventory = conn.execute(
                "SELECT * FROM room_inventory ORDER BY room,item"
            ).fetchall()
        return render_template("inventory_center.html", inventory=inventory)

    @app.post("/os/inventory/<int:item_id>/update")
    def inventory_update(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("""
                UPDATE room_inventory
                SET quantity=?,minimum_quantity=?,condition=?,last_check=?,note=?
                WHERE id=?
            """, (
                int(request.form.get("quantity","0")),
                int(request.form.get("minimum_quantity","0")),
                request.form.get("condition","gut"),
                date.today().isoformat(),
                request.form.get("note",""),
                item_id
            ))
        return redirect(url_for("inventory_center"))

    @app.route("/os/finance", methods=["GET", "POST"])
    def finance_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO operating_costs(booking_id,category,description,amount,cost_date,created_at)
                    VALUES(NULL,?,?,?,?,?)
                """, (
                    request.form["category"],
                    request.form.get("description",""),
                    float(request.form.get("amount","0")),
                    request.form.get("cost_date", date.today().isoformat()),
                    datetime.now().isoformat(timespec="seconds")
                ))
            flash("Kosten erfasst.", "success")
            return redirect(url_for("finance_center"))

        month_prefix = request.args.get("month", date.today().strftime("%Y-%m"))
        revenue, costs, profit = month_profit(month_prefix)
        with db() as conn:
            cost_rows = conn.execute(
                "SELECT * FROM operating_costs WHERE cost_date LIKE ? ORDER BY cost_date DESC,id DESC",
                (month_prefix + "%",)
            ).fetchall()
            room_revenue = conn.execute("""
                SELECT room,COUNT(*) bookings,ROUND(SUM(total),2) revenue
                FROM bookings
                WHERE arrival LIKE ? AND status!='cancelled'
                GROUP BY room ORDER BY revenue DESC
            """, (month_prefix + "%",)).fetchall()
        return render_template(
            "finance_center.html",
            month=month_prefix,
            revenue=revenue,
            costs=costs,
            profit=profit,
            cost_rows=cost_rows,
            room_revenue=room_revenue,
        )

    @app.get("/os/finance/export.csv")
    def finance_export():
        if not require_admin():
            return redirect(url_for("admin_login"))
        month_prefix = request.args.get("month", date.today().strftime("%Y-%m"))
        with db() as conn:
            bookings = conn.execute("""
                SELECT id,room,arrival,departure,first_name,last_name,total,status
                FROM bookings WHERE arrival LIKE ? ORDER BY arrival
            """, (month_prefix + "%",)).fetchall()
            costs = conn.execute("""
                SELECT category,description,amount,cost_date
                FROM operating_costs WHERE cost_date LIKE ? ORDER BY cost_date
            """, (month_prefix + "%",)).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["EINNAHMEN"])
        writer.writerow(["ID","Zimmer","Anreise","Abreise","Gast","Betrag","Status"])
        for row in bookings:
            writer.writerow([
                row["id"],row["room"],row["arrival"],row["departure"],
                f"{row['first_name']} {row['last_name']}",row["total"],row["status"]
            ])
        writer.writerow([])
        writer.writerow(["KOSTEN"])
        writer.writerow(["Datum","Kategorie","Beschreibung","Betrag"])
        for row in costs:
            writer.writerow([row["cost_date"],row["category"],row["description"],row["amount"]])

        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=finanzen-{month_prefix}.csv"}
        )

    @app.route("/os/windis", methods=["GET", "POST"])
    def windis_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO windis_content(character,category,title,content,created_at)
                    VALUES(?,?,?,?,?)
                """, (
                    request.form["character"],
                    request.form.get("category","Allgemein"),
                    request.form["title"].strip(),
                    request.form["content"].strip(),
                    datetime.now().isoformat(timespec="seconds")
                ))
            flash("Windis-Inhalt gespeichert.", "success")
            return redirect(url_for("windis_center"))

        with db() as conn:
            content = conn.execute(
                "SELECT * FROM windis_content ORDER BY character,category,title"
            ).fetchall()
        return render_template("windis_center.html", content=content)

    @app.route("/os/marketing", methods=["GET", "POST"])
    def marketing_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            with db() as conn:
                conn.execute("""
                    INSERT INTO marketing_ideas(channel,title,text,status,planned_date,created_at)
                    VALUES(?,?,?,?,?,?)
                """, (
                    request.form["channel"],
                    request.form["title"].strip(),
                    request.form["text"].strip(),
                    request.form.get("status","Idee"),
                    request.form.get("planned_date",""),
                    datetime.now().isoformat(timespec="seconds")
                ))
            flash("Marketing-Idee gespeichert.", "success")
            return redirect(url_for("marketing_center"))

        with db() as conn:
            ideas = conn.execute(
                "SELECT * FROM marketing_ideas ORDER BY planned_date,id DESC"
            ).fetchall()
        return render_template("marketing_center.html", ideas=ideas)

    @app.route("/os/monteur", methods=["GET", "POST"])
    def monteur_gap_optimizer():
        if not require_admin():
            return redirect(url_for("admin_login"))

        if request.method == "POST":
            action = request.form.get("action", "").strip().lower()
            start_raw = request.form.get("start_date", "").strip()
            end_raw = request.form.get("end_date", "").strip()
            try:
                start_day = date.fromisoformat(start_raw)
                end_day = date.fromisoformat(end_raw)
            except ValueError:
                flash("Ungültiger Zeitraum.", "error")
                return redirect(url_for("monteur_gap_optimizer"))

            nights = [start_day + timedelta(days=i) for i in range(MONTEUR_NIGHTS)]
            valid_window = (
                start_day.weekday() == 6
                and end_day == start_day + timedelta(days=MONTEUR_NIGHTS)
                and all(day.month in MONTEUR_WINTER_MONTHS for day in nights)
            )
            if not valid_window:
                flash("Nur Winter-Monteurfenster Sonntag bis Freitag können verwaltet werden.", "error")
                return redirect(url_for("monteur_gap_optimizer"))

            with db() as conn:
                blocker = _monteur_blocker(conn, start_day, end_day)
                if action == "publish":
                    if blocker:
                        flash(f"Nicht freigeschaltet: Zeitraum ist belegt oder gesperrt ({blocker}).", "error")
                        return redirect(url_for("monteur_gap_optimizer"))
                    status = "published"
                    message = "Zeitraum als auf zimmmer.at veröffentlicht markiert."
                elif action == "unpublish":
                    status = "not_published"
                    message = "Zeitraum als nicht veröffentlicht markiert."
                else:
                    flash("Unbekannte Aktion.", "error")
                    return redirect(url_for("monteur_gap_optimizer"))

                conn.execute(
                    """INSERT INTO monteur_channel_windows
                       (start_date,end_date,channel,status,note,updated_at)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(start_date,end_date,channel) DO UPDATE SET
                           status=excluded.status,
                           note=excluded.note,
                           updated_at=excluded.updated_at""",
                    (
                        start_day.isoformat(),
                        end_day.isoformat(),
                        MONTEUR_CHANNEL,
                        status,
                        "",
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
            flash(message, "success")
            return redirect(url_for("monteur_gap_optimizer"))

        windows = monteur_gap_windows()
        free_windows = [window for window in windows if window["available"]]
        published_windows = [
            window for window in windows
            if window["available"] and window["channel_status"] == "published"
        ]
        return render_template(
            "monteur_optimizer.html",
            windows=windows,
            free_windows=len(free_windows),
            published_windows=len(published_windows),
            channel_url=MONTEUR_CHANNEL_URL,
            single_room_rate=MONTEUR_SINGLE_ROOM_PRICE,
            double_pppn=MONTEUR_TWO_PERSON_PRICE_PER_PERSON,
            weekly_single=round(MONTEUR_SINGLE_ROOM_PRICE * MONTEUR_NIGHTS, 2),
            weekly_double=round(
                MONTEUR_TWO_PERSON_PRICE_PER_PERSON * MONTEUR_MAX_GUESTS * MONTEUR_NIGHTS,
                2,
            ),
            today=date.today().isoformat(),
        )


    @app.get("/os/status.json")
    def os_status():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        refresh_guest_profiles()
        with db() as conn:
            data = {
                "guests": conn.execute("SELECT COUNT(*) c FROM guest_profiles").fetchone()["c"],
                "open_tasks": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status!='erledigt'").fetchone()["c"],
                "inventory_alerts": conn.execute(
                    "SELECT COUNT(*) c FROM room_inventory WHERE quantity<minimum_quantity OR condition!='gut'"
                ).fetchone()["c"],
                "marketing_ideas": conn.execute("SELECT COUNT(*) c FROM marketing_ideas").fetchone()["c"],
            }
        return jsonify(data)

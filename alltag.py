
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for


def init_alltag(app, db, require_admin, ROOMS):
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_date TEXT NOT NULL,
            item_type TEXT NOT NULL,
            reference_id INTEGER,
            room TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'offen',
            sort_order INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS shopping_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            quantity TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Allgemein',
            needed_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offen',
            created_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS daily_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        defaults = {
            "day_start_hour": "7",
            "show_tomorrow": "1",
            "auto_generate": "1",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO daily_settings(key,value) VALUES(?,?)",
                (key, value),
            )

    def today_iso():
        return date.today().isoformat()

    def task_exists(conn, item_date, item_type, reference_id, title):
        if reference_id is None:
            return conn.execute(
                """SELECT 1 FROM daily_items
                   WHERE item_date=? AND item_type=? AND reference_id IS NULL AND title=?""",
                (item_date, item_type, title),
            ).fetchone()
        return conn.execute(
            """SELECT 1 FROM daily_items
               WHERE item_date=? AND item_type=? AND reference_id=?""",
            (item_date, item_type, reference_id),
        ).fetchone()

    def add_daily_item(conn, *, item_date, item_type, title, details="",
                       room="", reference_id=None, priority="normal", sort_order=100):
        if task_exists(conn, item_date, item_type, reference_id, title):
            return
        conn.execute(
            """INSERT INTO daily_items
               (item_date,item_type,reference_id,room,title,details,priority,status,
                sort_order,created_at)
               VALUES(?,?,?,?,?,?,?,'offen',?,?)""",
            (
                item_date, item_type, reference_id, room, title, details,
                priority, sort_order, datetime.now().isoformat(timespec="seconds"),
            ),
        )

    def sync_today_items(target_date=None):
        day = target_date or date.today()
        day_iso = day.isoformat()
        tomorrow_iso = (day + timedelta(days=1)).isoformat()

        with db() as conn:
            arrivals = conn.execute(
                """SELECT * FROM bookings
                   WHERE arrival=? AND status!='cancelled' ORDER BY room""",
                (day_iso,),
            ).fetchall()
            departures = conn.execute(
                """SELECT * FROM bookings
                   WHERE departure=? AND status!='cancelled' ORDER BY room""",
                (day_iso,),
            ).fetchall()
            occupied_breakfast = conn.execute(
                """SELECT * FROM bookings
                   WHERE arrival<=? AND departure>? AND breakfast=1
                   AND status!='cancelled' ORDER BY room""",
                (day_iso, day_iso),
            ).fetchall()
            open_orders = conn.execute(
                """SELECT o.*,b.room,b.first_name,b.last_name
                   FROM guest_orders o JOIN bookings b ON b.id=o.booking_id
                   WHERE o.status='offen' ORDER BY o.created_at"""
            ).fetchall()
            open_tasks = conn.execute(
                """SELECT * FROM tasks
                   WHERE status!='erledigt' AND (due_date='' OR due_date<=?)
                   ORDER BY CASE priority WHEN 'hoch' THEN 1
                                          WHEN 'normal' THEN 2 ELSE 3 END,id""",
                (day_iso,),
            ).fetchall()
            pending_payments = conn.execute(
                """SELECT * FROM bookings
                   WHERE status='confirmed' AND paid=0 AND arrival<=?
                   ORDER BY arrival,room""",
                (day_iso,),
            ).fetchall()
            tomorrow_arrivals = conn.execute(
                """SELECT * FROM bookings
                   WHERE arrival=? AND status!='cancelled' ORDER BY room""",
                (tomorrow_iso,),
            ).fetchall()

            for b in arrivals:
                time_text = b["arrival_time"] if "arrival_time" in b.keys() and b["arrival_time"] else "Zeit noch offen"
                add_daily_item(
                    conn, item_date=day_iso, item_type="arrival",
                    reference_id=b["id"], room=b["room"],
                    title=f"{b['room']}: {b['first_name']} {b['last_name']} einchecken",
                    details=f"Anreise: {time_text} · {b['adults']} Person(en) · {b['phone']}",
                    priority="hoch", sort_order=20,
                )

            for b in departures:
                add_daily_item(
                    conn, item_date=day_iso, item_type="departure",
                    reference_id=b["id"], room=b["room"],
                    title=f"{b['room']}: Check-out {b['first_name']} {b['last_name']}",
                    details=f"Abreise heute · Zahlung: {'bezahlt' if b['paid'] else 'offen'}",
                    priority="hoch", sort_order=10,
                )
                add_daily_item(
                    conn, item_date=day_iso, item_type="cleaning",
                    reference_id=b["id"], room=b["room"],
                    title=f"{b['room']} reinigen und kontrollieren",
                    details="Bettwäsche, Bad, Handtücher, Müll, Boden und Zimmerkontrolle.",
                    priority="hoch", sort_order=30,
                )

            for b in occupied_breakfast:
                add_daily_item(
                    conn, item_date=day_iso, item_type="breakfast",
                    reference_id=b["id"], room=b["room"],
                    title=f"Frühstück für {b['room']} vorbereiten",
                    details=f"{b['adults']} Person(en) · {b['first_name']} {b['last_name']}",
                    priority="hoch", sort_order=5,
                )

            for order in open_orders:
                add_daily_item(
                    conn, item_date=day_iso, item_type="guest_order",
                    reference_id=order["id"], room=order["room"],
                    title=f"{order['order_type']} – {order['room']}",
                    details=f"{order['first_name']} {order['last_name']}: {order['details']}",
                    priority="normal", sort_order=40,
                )

            for task in open_tasks:
                add_daily_item(
                    conn, item_date=day_iso, item_type="task",
                    reference_id=task["id"], room="",
                    title=task["title"],
                    details=f"{task['category']}: {task['description']}",
                    priority=task["priority"], sort_order=50,
                )

            for b in pending_payments:
                add_daily_item(
                    conn, item_date=day_iso, item_type="payment",
                    reference_id=b["id"], room=b["room"],
                    title=f"Zahlung prüfen: {b['first_name']} {b['last_name']}",
                    details=f"{b['room']} · {b['total']:.2f} € · {b['payment_method']}",
                    priority="normal", sort_order=60,
                )

            for b in tomorrow_arrivals:
                add_daily_item(
                    conn, item_date=day_iso, item_type="tomorrow",
                    reference_id=b["id"], room=b["room"],
                    title=f"Für morgen vorbereiten: {b['room']}",
                    details=f"{b['first_name']} {b['last_name']} · {b['adults']} Person(en)",
                    priority="niedrig", sort_order=90,
                )

            # Zimmerstatus-Warnungen
            housekeeping = conn.execute(
                "SELECT * FROM housekeeping WHERE status IN ('Reinigung','gesperrt') ORDER BY room"
            ).fetchall()
            for room in housekeeping:
                add_daily_item(
                    conn, item_date=day_iso, item_type="room_status",
                    reference_id=None, room=room["room"],
                    title=f"Zimmerstatus prüfen: {room['room']}",
                    details=f"Status: {room['status']} · {room['note']}",
                    priority="normal", sort_order=35,
                )

    def complete_linked_item(conn, item):
        item_type = item["item_type"]
        ref = item["reference_id"]
        if ref is None:
            return
        if item_type == "task":
            conn.execute(
                "UPDATE tasks SET status='erledigt',completed_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), ref),
            )
        elif item_type == "guest_order":
            conn.execute("UPDATE guest_orders SET status='erledigt' WHERE id=?", (ref,))
        elif item_type == "payment":
            conn.execute(
                "UPDATE bookings SET paid=1,status='confirmed' WHERE id=?", (ref,)
            )
        elif item_type == "cleaning":
            room = item["room"]
            conn.execute(
                """UPDATE housekeeping SET status='fertig',note='',
                   updated_at=? WHERE room=?""",
                (datetime.now().isoformat(timespec="seconds"), room),
            )
        elif item_type == "arrival":
            room = item["room"]
            conn.execute(
                """UPDATE housekeeping SET status='belegt',note='Gast eingecheckt',
                   updated_at=? WHERE room=?""",
                (datetime.now().isoformat(timespec="seconds"), room),
            )
        elif item_type == "departure":
            room = item["room"]
            conn.execute(
                """UPDATE housekeeping SET status='Reinigung',note='Check-out erledigt',
                   updated_at=? WHERE room=?""",
                (datetime.now().isoformat(timespec="seconds"), room),
            )

    @app.get("/heute")
    def today_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))

        sync_today_items()
        day_iso = today_iso()

        with db() as conn:
            items = conn.execute(
                """SELECT * FROM daily_items
                   WHERE item_date=? AND status!='erledigt'
                   ORDER BY sort_order,
                            CASE priority WHEN 'hoch' THEN 1
                                          WHEN 'normal' THEN 2 ELSE 3 END,
                            id""",
                (day_iso,),
            ).fetchall()
            completed_count = conn.execute(
                """SELECT COUNT(*) c FROM daily_items
                   WHERE item_date=? AND status='erledigt'""",
                (day_iso,),
            ).fetchone()["c"]
            shopping = conn.execute(
                """SELECT * FROM shopping_items
                   WHERE status!='erledigt'
                   ORDER BY CASE WHEN needed_date='' THEN 1 ELSE 0 END,
                            needed_date,category,item"""
            ).fetchall()
            arrivals_count = conn.execute(
                "SELECT COUNT(*) c FROM bookings WHERE arrival=? AND status!='cancelled'",
                (day_iso,),
            ).fetchone()["c"]
            departures_count = conn.execute(
                "SELECT COUNT(*) c FROM bookings WHERE departure=? AND status!='cancelled'",
                (day_iso,),
            ).fetchone()["c"]
            breakfast_people = conn.execute(
                """SELECT COALESCE(SUM(adults),0) c FROM bookings
                   WHERE arrival<=? AND departure>? AND breakfast=1
                   AND status!='cancelled'""",
                (day_iso, day_iso),
            ).fetchone()["c"]
            open_payments = conn.execute(
                """SELECT COUNT(*) c FROM bookings
                   WHERE status='confirmed' AND paid=0 AND arrival<=?""",
                (day_iso,),
            ).fetchone()["c"]

        groups = {}
        for item in items:
            groups.setdefault(item["item_type"], []).append(item)

        return render_template(
            "today_dashboard.html",
            items=items,
            groups=groups,
            shopping=shopping,
            completed_count=completed_count,
            arrivals_count=arrivals_count,
            departures_count=departures_count,
            breakfast_people=breakfast_people,
            open_payments=open_payments,
            today=day_iso,
        )

    @app.post("/heute/item/<int:item_id>/done")
    def today_item_done(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            item = conn.execute(
                "SELECT * FROM daily_items WHERE id=?", (item_id,)
            ).fetchone()
            if not item:
                return "Nicht gefunden", 404
            complete_linked_item(conn, item)
            conn.execute(
                """UPDATE daily_items SET status='erledigt',completed_at=?
                   WHERE id=?""",
                (datetime.now().isoformat(timespec="seconds"), item_id),
            )
        return redirect(url_for("today_dashboard"))

    @app.post("/heute/item/add")
    def today_item_add():
        if not require_admin():
            return redirect(url_for("admin_login"))
        title = request.form.get("title", "").strip()
        if title:
            with db() as conn:
                add_daily_item(
                    conn,
                    item_date=today_iso(),
                    item_type="manual",
                    title=title,
                    details=request.form.get("details", "").strip(),
                    priority=request.form.get("priority", "normal"),
                    sort_order=45,
                )
        return redirect(url_for("today_dashboard"))

    @app.post("/heute/shopping/add")
    def shopping_add():
        if not require_admin():
            return redirect(url_for("admin_login"))
        item = request.form.get("item", "").strip()
        if item:
            with db() as conn:
                conn.execute(
                    """INSERT INTO shopping_items
                       (item,quantity,category,needed_date,status,created_at)
                       VALUES(?,?,?,?, 'offen', ?)""",
                    (
                        item,
                        request.form.get("quantity", "").strip(),
                        request.form.get("category", "Allgemein"),
                        request.form.get("needed_date", ""),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        return redirect(url_for("today_dashboard"))

    @app.post("/heute/shopping/<int:item_id>/done")
    def shopping_done(item_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute(
                """UPDATE shopping_items SET status='erledigt',completed_at=?
                   WHERE id=?""",
                (datetime.now().isoformat(timespec="seconds"), item_id),
            )
        return redirect(url_for("today_dashboard"))

    @app.post("/heute/refresh")
    def today_refresh():
        if not require_admin():
            return redirect(url_for("admin_login"))
        sync_today_items()
        flash("Tagesliste wurde aktualisiert.", "success")
        return redirect(url_for("today_dashboard"))

    @app.get("/heute/status.json")
    def today_status():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        sync_today_items()
        day_iso = today_iso()
        with db() as conn:
            open_count = conn.execute(
                """SELECT COUNT(*) c FROM daily_items
                   WHERE item_date=? AND status!='erledigt'""",
                (day_iso,),
            ).fetchone()["c"]
            high_count = conn.execute(
                """SELECT COUNT(*) c FROM daily_items
                   WHERE item_date=? AND status!='erledigt' AND priority='hoch'""",
                (day_iso,),
            ).fetchone()["c"]
            shopping_count = conn.execute(
                "SELECT COUNT(*) c FROM shopping_items WHERE status!='erledigt'"
            ).fetchone()["c"]
        return jsonify(
            date=day_iso,
            open_items=open_count,
            high_priority=high_count,
            shopping=shopping_count,
        )

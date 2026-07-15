from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (
    Response, flash, jsonify, redirect, render_template, request,
    send_file, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


def init_quality_v12(app, DB_PATH, db, require_admin, ROOMS):
    import_dir = Path(DB_PATH).parent / "imports"
    restore_dir = Path(DB_PATH).parent / "restore_points"
    import_dir.mkdir(parents=True, exist_ok=True)
    restore_dir.mkdir(parents=True, exist_ok=True)

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'staff',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS setup_state(
                key TEXT PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS import_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                rows_total INTEGER NOT NULL DEFAULT 0,
                rows_success INTEGER NOT NULL DEFAULT 0,
                rows_failed INTEGER NOT NULL DEFAULT 0,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quality_checks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                check_time TEXT NOT NULL,
                check_name TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ''
            );
            """
        )
        setup = {
            "business_data": "Unternehmensdaten und Kontakt",
            "rooms": "Zimmerbilder und Ausstattungen",
            "prices": "Preise, Saisonen und Extras",
            "booking_ical": "Booking.com-iCal-Links",
            "email": "SMTP/E-Mail-Versand",
            "paypal": "PayPal-Link oder Zugang",
            "legal": "Impressum, Datenschutz und Bedingungen",
            "security": "Sicheres Adminpasswort und Benutzer",
            "backup": "Backup geprüft",
            "knowledge": "Wissensdaten gepflegt",
        }
        now = datetime.now().isoformat(timespec="seconds")
        for key, note in setup.items():
            conn.execute(
                "INSERT OR IGNORE INTO setup_state(key,completed,note,updated_at) VALUES(?,0,?,?)",
                (key, note, now),
            )

    @app.after_request
    def v12_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Cache-Control", "no-store" if request.path.startswith(("/admin", "/os", "/smart", "/wissen", "/assistent", "/heute")) else "private, max-age=60")
        return response

    def current_role():
        return session.get("role", "admin" if session.get("admin") else "")

    def role_required(*allowed):
        return current_role() in allowed or session.get("admin")

    def create_restore_point(label="manual"):
        if not Path(DB_PATH).exists():
            return None
        filename = f"restore-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        target = restore_dir / filename
        shutil.copy2(DB_PATH, target)
        return target

    def run_checks():
        checks = []
        def add(name, ok, details=""):
            checks.append({"name": name, "status": "OK" if ok else "FEHLER", "details": details})

        try:
            with db() as conn:
                conn.execute("PRAGMA integrity_check").fetchone()
            add("Datenbank erreichbar", True)
        except Exception as exc:
            add("Datenbank erreichbar", False, str(exc))

        required_templates = [
            "index.html", "admin.html", "smart_dashboard.html", "host_assistant.html",
            "knowledge_dashboard.html", "setup_wizard.html", "quality_center.html",
        ]
        for name in required_templates:
            add(f"Vorlage {name}", (Path(app.template_folder) / name).exists())

        add("Titelbild", (Path(app.static_folder) / "images" / "aggsbach-markt-luftbild.png").exists())
        add("CSS", (Path(app.static_folder) / "css" / "style.css").exists())
        add("JavaScript", (Path(app.static_folder) / "js" / "app.js").exists())

        with db() as conn:
            rooms = conn.execute("SELECT COUNT(*) c FROM room_prices").fetchone()["c"]
            settings = conn.execute("SELECT COUNT(*) c FROM site_settings").fetchone()["c"]
            knowledge = conn.execute("SELECT COUNT(*) c FROM knowledge_entries").fetchone()["c"]
        add("Vier Zimmerpreise", rooms == len(ROOMS), f"gefunden: {rooms}")
        add("Seiteneinstellungen", settings > 0, f"gefunden: {settings}")
        add("Wissensdaten", knowledge > 0, f"gefunden: {knowledge}")

        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute("DELETE FROM quality_checks")
            for item in checks:
                conn.execute(
                    "INSERT INTO quality_checks(check_time,check_name,status,details) VALUES(?,?,?,?)",
                    (now, item["name"], item["status"], item["details"]),
                )
        return checks

    @app.route("/setup", methods=["GET", "POST"])
    def setup_wizard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        if request.method == "POST":
            key = request.form.get("key", "")
            completed = 1 if request.form.get("completed") == "on" else 0
            note = request.form.get("note", "").strip()
            with db() as conn:
                conn.execute(
                    "UPDATE setup_state SET completed=?,note=?,updated_at=? WHERE key=?",
                    (completed, note, datetime.now().isoformat(timespec="seconds"), key),
                )
            flash("Einrichtungspunkt gespeichert.", "success")
            return redirect(url_for("setup_wizard"))
        with db() as conn:
            rows = conn.execute("SELECT * FROM setup_state ORDER BY key").fetchall()
        completed = sum(1 for r in rows if r["completed"])
        return render_template("setup_wizard.html", rows=rows, completed=completed, total=len(rows))

    @app.get("/quality")
    def quality_center():
        if not require_admin():
            return redirect(url_for("admin_login"))
        checks = run_checks()
        with db() as conn:
            imports = conn.execute("SELECT * FROM import_log ORDER BY id DESC LIMIT 20").fetchall()
            users = conn.execute("SELECT id,username,display_name,role,active,last_login FROM app_users ORDER BY username").fetchall()
        return render_template(
            "quality_center.html",
            checks=checks,
            imports=imports,
            users=users,
            passed=sum(1 for c in checks if c["status"] == "OK"),
            total=len(checks),
        )

    @app.get("/quality/report.json")
    def quality_report():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        checks = run_checks()
        return jsonify(
            status="ok" if all(c["status"] == "OK" for c in checks) else "degraded",
            checks=checks,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

    @app.post("/quality/restore-point")
    def make_restore_point():
        if not require_admin():
            return redirect(url_for("admin_login"))
        target = create_restore_point("manual")
        flash(f"Wiederherstellungspunkt erstellt: {target.name if target else 'nicht möglich'}", "success")
        return redirect(url_for("quality_center"))

    @app.get("/quality/restore-points")
    def restore_points():
        if not require_admin():
            return jsonify(error="unauthorized"), 401
        files = sorted(restore_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        return jsonify([
            {"name": p.name, "size": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in files
        ])

    @app.post("/quality/user")
    def create_user():
        if not require_admin():
            return redirect(url_for("admin_login"))
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff")
        allowed_roles = {"staff", "housekeeping", "accounting", "manager"}
        if role not in allowed_roles:
            role = "staff"
        if not username or len(password) < 8:
            flash("Benutzername und Passwort mit mindestens 8 Zeichen erforderlich.", "error")
            return redirect(url_for("quality_center"))
        with db() as conn:
            try:
                conn.execute(
                    "INSERT INTO app_users(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)",
                    (username, generate_password_hash(password), request.form.get("display_name", ""), role, datetime.now().isoformat(timespec="seconds")),
                )
                flash("Benutzer angelegt.", "success")
            except sqlite3.IntegrityError:
                flash("Benutzername existiert bereits.", "error")
        return redirect(url_for("quality_center"))

    @app.route("/staff/login", methods=["GET", "POST"])
    def staff_login():
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            with db() as conn:
                user = conn.execute("SELECT * FROM app_users WHERE username=? AND active=1", (username,)).fetchone()
                if user and check_password_hash(user["password_hash"], password):
                    session.clear()
                    session["staff_user_id"] = user["id"]
                    session["role"] = user["role"]
                    session["display_name"] = user["display_name"] or user["username"]
                    conn.execute("UPDATE app_users SET last_login=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), user["id"]))
                    target_by_role = {
                        "housekeeping": "host_mobile",
                        "accounting": "finance_center",
                        "manager": "smart_dashboard",
                    }
                    return redirect(url_for(target_by_role.get(user["role"], "smart_dashboard")))
            flash("Anmeldung fehlgeschlagen.", "error")
        return render_template("staff_login.html")

    @app.post("/quality/import/bookings")
    def import_bookings_csv():
        if not require_admin():
            return redirect(url_for("admin_login"))
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("CSV-Datei auswählen.", "error")
            return redirect(url_for("quality_center"))
        filename = secure_filename(upload.filename)
        raw = upload.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(raw), delimiter=";" if ";" in raw.splitlines()[0] else ",")
        required = {"room", "arrival", "departure", "first_name", "last_name", "email", "phone", "adults", "total"}
        rows_total = rows_success = rows_failed = 0
        errors = []
        create_restore_point("before-import")
        with db() as conn:
            for row in reader:
                rows_total += 1
                try:
                    missing = required - set(row.keys())
                    if missing:
                        raise ValueError("Fehlende Spalten: " + ", ".join(sorted(missing)))
                    uid = f"IMPORT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{rows_total}@zab"
                    conn.execute(
                        """INSERT INTO bookings(uid,room,arrival,departure,adults,breakfast,first_name,last_name,email,phone,message,payment_method,total,status,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,'Import',?,'confirmed',?)""",
                        (uid,row["room"],row["arrival"],row["departure"],int(row["adults"]),int(row.get("breakfast") or 0),row["first_name"],row["last_name"],row["email"],row["phone"],row.get("message", ""),float(str(row["total"]).replace(",", ".")),datetime.now().isoformat(timespec="seconds")),
                    )
                    rows_success += 1
                except Exception as exc:
                    rows_failed += 1
                    errors.append(f"Zeile {rows_total}: {exc}")
            conn.execute(
                "INSERT INTO import_log(import_type,filename,rows_total,rows_success,rows_failed,details,created_at) VALUES('bookings',?,?,?,?,?,?)",
                (filename, rows_total, rows_success, rows_failed, "\n".join(errors[:30]), datetime.now().isoformat(timespec="seconds")),
            )
        flash(f"Import abgeschlossen: {rows_success} erfolgreich, {rows_failed} fehlerhaft.", "success" if rows_failed == 0 else "error")
        return redirect(url_for("quality_center"))

    @app.get("/quality/import/sample.csv")
    def import_sample_csv():
        content = "room;arrival;departure;first_name;last_name;email;phone;adults;breakfast;total;message\nBachblick;2026-09-01;2026-09-03;Max;Muster;max@example.com;+431234567;2;1;190.00;Beispielimport\n"
        return Response("\ufeff" + content, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=buchungsimport-vorlage.csv"})

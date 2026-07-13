
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import smtplib
import sqlite3
import urllib.request
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from secrets import token_urlsafe

from flask import (
    Response, flash, jsonify, redirect, render_template, request,
    send_file, session, url_for
)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def init_addons(app, DB_PATH, db, require_admin, ROOMS, PAYPAL_EMAIL):
    backup_dir = Path(DB_PATH).parent / "backups"
    invoice_dir = Path(DB_PATH).parent / "invoices"
    backup_dir.mkdir(parents=True, exist_ok=True)
    invoice_dir.mkdir(parents=True, exist_ok=True)

    def ensure_column(conn, table, column, definition):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    with db() as conn:
        ensure_column(conn, "bookings", "public_token", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "cancel_token", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "extras_json", "TEXT DEFAULT '{}'")
        ensure_column(conn, "bookings", "paid", "INTEGER DEFAULT 0")
        ensure_column(conn, "bookings", "invoice_number", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "arrival_time", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "guest_note", "TEXT DEFAULT ''")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS housekeeping(
            room TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'frei',
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS guest_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            order_type TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offen',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coupons(
            code TEXT PRIMARY KEY,
            percent REAL NOT NULL,
            valid_from TEXT DEFAULT '',
            valid_to TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS email_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            recipient TEXT,
            subject TEXT,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS faq(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        """)
        for room in ROOMS:
            conn.execute("INSERT OR IGNORE INTO housekeeping(room,status,updated_at) VALUES(?, 'frei', ?)", (room, datetime.now().isoformat(timespec="seconds")))
        defaults = [
            ("WLAN", "Die WLAN-Zugangsdaten finden Gäste in der Gäste-App und im Zimmer."),
            ("Frühstück", "Frühstück kostet 12 € pro Person und Nacht und ist vegetarisch oder vegan möglich."),
            ("Fahrrad", "Fahrräder können sicher im Innenbereich abgestellt und E-Bikes geladen werden."),
            ("Welterbesteig", "Zuhause am Bach ist als Basislager für den Welterbesteig positioniert."),
            ("Donauradweg", "Der Donauradweg ist gut erreichbar. Werkzeug, Luft und Lademöglichkeit stehen bereit."),
        ]
        for q, a in defaults:
            found = conn.execute("SELECT 1 FROM faq WHERE question=?", (q,)).fetchone()
            if not found:
                conn.execute("INSERT INTO faq(question,answer) VALUES(?,?)", (q,a))

    def settings():
        with db() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM site_settings")}

    def booking_by_token(token):
        with db() as conn:
            return conn.execute("SELECT * FROM bookings WHERE public_token=? OR cancel_token=?", (token, token)).fetchone()

    def smtp_send(to, subject, body):
        cfg = settings()
        host = cfg.get("smtp_host", "")
        user = cfg.get("smtp_user", "")
        password = cfg.get("smtp_password", "")
        port = int(cfg.get("smtp_port", "587") or 587)
        sender = cfg.get("smtp_sender", user or cfg.get("email", PAYPAL_EMAIL))
        if not host or not user or not password:
            return False, "SMTP ist noch nicht vollständig eingerichtet."
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            return True, "gesendet"
        except Exception as exc:
            return False, str(exc)

    def ensure_booking_tokens(booking_id):
        with db() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            public_token = row["public_token"] or token_urlsafe(20)
            cancel_token = row["cancel_token"] or token_urlsafe(20)
            invoice_number = row["invoice_number"] or f"ZAB-{datetime.now().year}-{booking_id:05d}"
            conn.execute(
                "UPDATE bookings SET public_token=?,cancel_token=?,invoice_number=? WHERE id=?",
                (public_token, cancel_token, invoice_number, booking_id),
            )
            return public_token, cancel_token, invoice_number

    def generate_invoice_pdf(booking):
        invoice_number = booking["invoice_number"] or f"ZAB-{datetime.now().year}-{booking['id']:05d}"
        path = invoice_dir / f"{invoice_number}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        y = height - 60
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, y, "Zuhause am Bach")
        y -= 24
        c.setFont("Helvetica", 10)
        c.drawString(50, y, "Das Basislager für Welterbesteig und Donauradweg")
        y -= 34
        c.setFont("Helvetica-Bold", 15)
        c.drawString(50, y, f"Rechnung {invoice_number}")
        y -= 28
        c.setFont("Helvetica", 11)
        lines = [
            f"Gast: {booking['first_name']} {booking['last_name']}",
            f"Zimmer: {booking['room']}",
            f"Aufenthalt: {booking['arrival']} bis {booking['departure']}",
            f"Personen: {booking['adults']}",
            f"Zahlungsart: {booking['payment_method']}",
            f"Status: {'bezahlt' if booking['paid'] else 'offen'}",
        ]
        for line in lines:
            c.drawString(50, y, line); y -= 20
        y -= 16
        c.setFont("Helvetica-Bold", 13)
        c.drawString(50, y, f"Gesamtbetrag: {booking['total']:.2f} EUR")
        y -= 40
        c.setFont("Helvetica", 9)
        c.drawString(50, y, "Jeder Gast bringt seine Geschichte mit. Bei Zuhause am Bach nimmt jeder eine neue mit nach Hause.")
        c.save()
        return path

    def send_booking_confirmation(booking_id):
        public_token, cancel_token, invoice_number = ensure_booking_tokens(booking_id)
        with db() as conn:
            b = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        base_url = settings().get("public_base_url", request.url_root.rstrip("/"))
        body = (
            f"Hallo {b['first_name']},\n\n"
            f"deine Buchungsanfrage für {b['room']} von {b['arrival']} bis {b['departure']} "
            f"wurde gespeichert.\nGesamtbetrag: {b['total']:.2f} EUR\n"
            f"Zahlungsart: {b['payment_method']}\n\n"
            f"Gästeportal: {base_url}/guest/{public_token}\n"
            f"Stornierung: {base_url}/cancel/{cancel_token}\n"
            f"Rechnung: {base_url}/invoice/{public_token}.pdf\n\n"
            "Bitte PayPal erst nach persönlicher Bestätigung verwenden.\n"
            "Zuhause am Bach"
        )
        ok_guest, msg_guest = smtp_send(b["email"], "Buchungsanfrage – Zuhause am Bach", body)
        owner = settings().get("email", PAYPAL_EMAIL)
        ok_owner, msg_owner = smtp_send(
            owner,
            f"Neue Direktbuchung: {b['room']}",
            f"{b['first_name']} {b['last_name']}\n{b['arrival']} bis {b['departure']}\n{b['total']:.2f} EUR\nTelefon: {b['phone']}",
        )
        with db() as conn:
            conn.execute("INSERT INTO email_log(booking_id,recipient,subject,status,created_at) VALUES(?,?,?,?,?)",
                         (booking_id,b["email"],"Buchungsanfrage",msg_guest,datetime.now().isoformat(timespec="seconds")))
        return ok_guest or ok_owner

    app.extensions["zab_send_confirmation"] = send_booking_confirmation
    app.extensions["zab_ensure_tokens"] = ensure_booking_tokens

    @app.get("/guest/<token>")
    def guest_portal(token):
        b = booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden", 404
        with db() as conn:
            orders = conn.execute("SELECT * FROM guest_orders WHERE booking_id=? ORDER BY created_at DESC", (b["id"],)).fetchall()
        return render_template("guest_portal.html", booking=b, orders=orders, settings=settings())

    @app.post("/guest/<token>/message")
    def guest_message(token):
        b = booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden", 404
        details = request.form.get("details","").strip()
        order_type = request.form.get("order_type","Nachricht")
        with db() as conn:
            conn.execute("INSERT INTO guest_orders(booking_id,order_type,details,status,created_at) VALUES(?,?,?,?,?)",
                         (b["id"],order_type,details,"offen",datetime.now().isoformat(timespec="seconds")))
            if order_type == "Spätere Anreise":
                conn.execute("UPDATE bookings SET arrival_time=? WHERE id=?", (details,b["id"]))
        flash("Deine Nachricht wurde gespeichert.", "success")
        return redirect(url_for("guest_portal", token=token))

    @app.route("/cancel/<token>", methods=["GET","POST"])
    def cancel_booking(token):
        b = booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden", 404
        if request.method == "POST":
            with db() as conn:
                conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (b["id"],))
            return render_template("cancelled.html", booking=b)
        return render_template("cancel_confirm.html", booking=b)

    @app.get("/invoice/<token>.pdf")
    def invoice_pdf(token):
        b = booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden", 404
        ensure_booking_tokens(b["id"])
        with db() as conn:
            b = conn.execute("SELECT * FROM bookings WHERE id=?", (b["id"],)).fetchone()
        path = generate_invoice_pdf(b)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/admin/dashboard")
    def dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        today = date.today().isoformat()
        month_prefix = date.today().strftime("%Y-%m")
        with db() as conn:
            arrivals = conn.execute("SELECT * FROM bookings WHERE arrival=? AND status!='cancelled'",(today,)).fetchall()
            departures = conn.execute("SELECT * FROM bookings WHERE departure=? AND status!='cancelled'",(today,)).fetchall()
            upcoming = conn.execute("SELECT * FROM bookings WHERE arrival>=? AND status!='cancelled' ORDER BY arrival LIMIT 20",(today,)).fetchall()
            revenue = conn.execute("SELECT COALESCE(SUM(total),0) total FROM bookings WHERE arrival LIKE ? AND status='confirmed'",(month_prefix+"%",)).fetchone()["total"]
            open_payments = conn.execute("SELECT COUNT(*) c FROM bookings WHERE status='confirmed' AND paid=0").fetchone()["c"]
            breakfast = conn.execute("SELECT * FROM bookings WHERE arrival<=? AND departure>? AND breakfast=1 AND status!='cancelled'",(today,today)).fetchall()
            housekeeping = conn.execute("SELECT * FROM housekeeping ORDER BY room").fetchall()
            orders = conn.execute("""SELECT o.*, b.first_name,b.last_name,b.room FROM guest_orders o
                                   JOIN bookings b ON b.id=o.booking_id WHERE o.status='offen' ORDER BY o.created_at""").fetchall()
        return render_template("dashboard.html", arrivals=arrivals,departures=departures,upcoming=upcoming,
                               revenue=revenue,open_payments=open_payments,breakfast=breakfast,
                               housekeeping=housekeeping,orders=orders,today=today)

    @app.post("/admin/housekeeping/<room>")
    def housekeeping_update(room):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE housekeeping SET status=?,note=?,updated_at=? WHERE room=?",
                         (request.form.get("status","frei"),request.form.get("note",""),datetime.now().isoformat(timespec="seconds"),room))
        return redirect(url_for("dashboard"))

    @app.post("/admin/order/<int:order_id>/done")
    def order_done(order_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE guest_orders SET status='erledigt' WHERE id=?",(order_id,))
        return redirect(url_for("dashboard"))

    @app.post("/admin/booking/<int:booking_id>/paid")
    def mark_paid(booking_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            conn.execute("UPDATE bookings SET paid=1,status='confirmed' WHERE id=?",(booking_id,))
        return redirect(url_for("dashboard"))

    @app.post("/admin/booking/<int:booking_id>/email")
    def resend_email(booking_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        ok = send_booking_confirmation(booking_id)
        flash("E-Mail wurde versendet." if ok else "E-Mail konnte nicht versendet werden. SMTP-Einstellungen prüfen.",
              "success" if ok else "error")
        return redirect(url_for("admin"))

    @app.get("/admin/export/bookings.csv")
    def export_bookings():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            rows = conn.execute("SELECT * FROM bookings ORDER BY arrival").fetchall()
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["ID","Status","Zimmer","Anreise","Abreise","Gast","E-Mail","Telefon","Personen","Frühstück","Zahlung","Bezahlt","Gesamt"])
        for b in rows:
            w.writerow([b["id"],b["status"],b["room"],b["arrival"],b["departure"],f"{b['first_name']} {b['last_name']}",
                        b["email"],b["phone"],b["adults"],b["breakfast"],b["payment_method"],b["paid"],b["total"]])
        return Response("\ufeff"+out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition":"attachment; filename=buchungen.csv"})

    @app.get("/admin/export/kurtaxe.csv")
    def export_kurtaxe():
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            rows = conn.execute("SELECT * FROM bookings WHERE status='confirmed' ORDER BY arrival").fetchall()
        out = io.StringIO(); w=csv.writer(out,delimiter=";")
        w.writerow(["Gast","Anreise","Abreise","Nächte","Personen","Personennächte"])
        for b in rows:
            nights=(date.fromisoformat(b["departure"])-date.fromisoformat(b["arrival"])).days
            w.writerow([f"{b['first_name']} {b['last_name']}",b["arrival"],b["departure"],nights,b["adults"],nights*b["adults"]])
        return Response("\ufeff"+out.getvalue(),mimetype="text/csv",
                        headers={"Content-Disposition":"attachment; filename=kurtaxe.csv"})

    @app.get("/admin/backup")
    def backup_database():
        if not require_admin():
            return redirect(url_for("admin_login"))
        name=f"zab-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        target=backup_dir/name
        shutil.copy2(DB_PATH,target)
        return send_file(target,as_attachment=True,download_name=name)

    @app.post("/admin/coupon")
    def coupon_save():
        if not require_admin():
            return redirect(url_for("admin_login"))
        code=request.form.get("code","").strip().upper()
        if code:
            with db() as conn:
                conn.execute("""INSERT INTO coupons(code,percent,valid_from,valid_to,enabled)
                             VALUES(?,?,?,?,1) ON CONFLICT(code) DO UPDATE SET percent=excluded.percent,
                             valid_from=excluded.valid_from,valid_to=excluded.valid_to,enabled=1""",
                             (code,float(request.form.get("percent","0")),request.form.get("valid_from",""),request.form.get("valid_to","")))
        return redirect(url_for("admin"))

    @app.get("/api/coupon/<code>")
    def coupon_check(code):
        today=date.today().isoformat()
        with db() as conn:
            row=conn.execute("SELECT * FROM coupons WHERE code=? AND enabled=1",(code.upper(),)).fetchone()
        if not row:
            return jsonify(valid=False,message="Gutscheincode nicht gültig.")
        if row["valid_from"] and today<row["valid_from"] or row["valid_to"] and today>row["valid_to"]:
            return jsonify(valid=False,message="Gutscheincode ist außerhalb des Gültigkeitszeitraums.")
        return jsonify(valid=True,percent=row["percent"])

    @app.route("/concierge", methods=["GET","POST"])
    def concierge():
        answer=""
        question=""
        if request.method=="POST":
            question=request.form.get("question","").strip()
            with db() as conn:
                faqs=conn.execute("SELECT * FROM faq WHERE enabled=1").fetchall()
            low=question.lower()
            best=None
            for faq in faqs:
                if faq["question"].lower() in low or any(word in low for word in faq["question"].lower().split()):
                    best=faq; break
            answer=best["answer"] if best else (
                "Dazu habe ich noch keine sichere hinterlegte Antwort. Bitte kontaktiere Zuhause am Bach direkt "
                "oder nutze die Gäste-App."
            )
        return render_template("concierge.html",question=question,answer=answer)

    @app.post("/admin/email-settings")
    def email_settings():
        if not require_admin():
            return redirect(url_for("admin_login"))
        keys=["smtp_host","smtp_port","smtp_user","smtp_password","smtp_sender","public_base_url","paypal_me_url"]
        with db() as conn:
            for key in keys:
                val=request.form.get(key,"").strip()
                conn.execute("""INSERT INTO site_settings(key,value) VALUES(?,?)
                             ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(key,val))
        flash("E-Mail- und Zahlungsdaten gespeichert.","success")
        return redirect(url_for("admin"))

from __future__ import annotations

import time
import threading
import hmac
import csv
import io
import json
import os
import logging
import shutil
import smtplib
import sqlite3
import urllib.request
import requests
import urllib.error
from datetime import date, datetime, timedelta
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
        ensure_column(conn, "bookings", "onsite_verified_at", "TEXT DEFAULT ''")
        conn.execute(
            """UPDATE bookings
               SET status='inquiry'
               WHERE payment_method='Vor Ort'
                 AND status='pending'
                 AND onsite_verified_at=''"""
        )
        ensure_column(conn, "bookings", "onsite_verify_expires_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "onsite_verify_token", "TEXT DEFAULT ''")
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
        CREATE TABLE IF NOT EXISTS email_outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT NOT NULL UNIQUE,
            booking_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT DEFAULT '',
            provider_message_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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

    _brevo_sender_cache = {"email": None, "name": None}

    def brevo_sender_email(brevo_key, configured_email, configured_name):
        if _brevo_sender_cache["email"]:
            return _brevo_sender_cache["email"], _brevo_sender_cache["name"] or configured_name
        try:
            response = requests.get(
                "https://api.brevo.com/v3/senders",
                headers={"accept": "application/json", "api-key": brevo_key},
                timeout=(4, 8),
            )
            if response.ok:
                data = response.json() or {}
                senders = data.get("senders") or []
                active = [s for s in senders if s.get("active") is True and s.get("email")]
                chosen = None
                for s in active:
                    if configured_email and s.get("email", "").lower() == configured_email.lower():
                        chosen = s
                        break
                if chosen is None and active:
                    chosen = active[0]
                if chosen:
                    _brevo_sender_cache["email"] = chosen["email"]
                    _brevo_sender_cache["name"] = chosen.get("name") or configured_name
                    return _brevo_sender_cache["email"], _brevo_sender_cache["name"]
        except requests.RequestException:
            pass
        return configured_email, configured_name

    def smtp_send(to, subject, body):
        """Reliable HTTPS mail transport with explicit provider control."""
        sender_name = os.environ.get("MAIL_SENDER_NAME", "Zuhause am Bach – Wachau").strip()
        reply_to = (
            os.environ.get("MAIL_REPLY_TO", "").strip()
            or os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
            or "zuhause.am.bach@outlook.com"
        )
        last_reason = "no_provider"

        brevo_key = os.environ.get("BREVO_API_KEY", "").strip()
        if brevo_key:
            configured_sender = (
                os.environ.get("BREVO_SENDER_EMAIL", "").strip()
                or os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
                or "zuhause.am.bach@outlook.com"
            )
            brevo_sender, brevo_name = brevo_sender_email(
                brevo_key, configured_sender, sender_name
            )
            payload = {
                "sender": {"name": brevo_name, "email": brevo_sender},
                "to": [{"email": to}],
                "replyTo": {"name": sender_name, "email": reply_to},
                "subject": subject,
                "textContent": body,
                "tags": ["zuhause-am-bach", "booking"],
            }
            try:
                response = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "accept": "application/json",
                        "api-key": brevo_key,
                        "content-type": "application/json",
                    },
                    json=payload,
                    timeout=(4, 8),
                )
                if 200 <= int(response.status_code) < 300:
                    data = response.json() if response.content else {}
                    message_id = str(data.get("messageId", "")).strip()
                    app.logger.warning(
                        "mail_send_ok transport=brevo recipient=%s sender=%s subject=%s message_id=%s",
                        to, brevo_sender, subject, message_id or "-",
                    )
                    return True, f"gesendet_brevo:{message_id}" if message_id else "gesendet_brevo"
                last_reason = f"brevo_failed_{response.status_code}"
                app.logger.error(
                    "mail_send_failed transport=brevo recipient=%s status=%s body=%s",
                    to, response.status_code, response.text[:500],
                )
            except requests.Timeout:
                last_reason = "brevo_timeout"
                app.logger.error("mail_send_failed transport=brevo reason=timeout recipient=%s", to)
            except requests.RequestException as exc:
                last_reason = "brevo_unreachable"
                app.logger.error(
                    "mail_send_failed transport=brevo reason=unreachable recipient=%s error=%s",
                    to, str(exc)[:200],
                )

        if os.environ.get("MAIL_PROVIDER_ALLOW_RESEND", "0").strip() == "1":
            resend_key = os.environ.get("RESEND_API_KEY", "").strip()
            sender_email = (
                os.environ.get("MAIL_SENDER_EMAIL", "").strip()
                or "buchung@zuhauseambach-wachau.at"
            )
            if resend_key:
                payload = {
                    "from": f"{sender_name} <{sender_email}>",
                    "to": [to],
                    "subject": subject,
                    "text": body,
                    "reply_to": [reply_to],
                    "tags": [
                        {"name": "app", "value": "zuhause-am-bach"},
                        {"name": "type", "value": "booking"},
                    ],
                }
                try:
                    response = requests.post(
                        "https://api.resend.com/emails",
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=(4, 8),
                    )
                    if 200 <= int(response.status_code) < 300:
                        data = response.json() if response.content else {}
                        message_id = str(data.get("id", "")).strip()
                        app.logger.warning(
                            "mail_send_ok transport=resend recipient=%s sender=%s subject=%s message_id=%s",
                            to, sender_email, subject, message_id or "-",
                        )
                        return True, f"gesendet_resend:{message_id}" if message_id else "gesendet_resend"
                    last_reason = f"resend_failed_{response.status_code}"
                    app.logger.error(
                        "mail_send_failed transport=resend recipient=%s status=%s body=%s",
                        to, response.status_code, response.text[:500],
                    )
                except requests.Timeout:
                    last_reason = "resend_timeout"
                except requests.RequestException:
                    last_reason = "resend_unreachable"

        return False, last_reason

    def _queue_mail(booking_id, role, recipient, subject, body):
        dedupe_key = f"{booking_id}:{role}:{subject}"
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """INSERT INTO email_outbox
                   (dedupe_key,booking_id,role,recipient,subject,body,status,attempts,last_error,
                    provider_message_id,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'pending',0,'','',?,?)
                   ON CONFLICT(dedupe_key) DO UPDATE SET
                     recipient=excluded.recipient,
                     body=excluded.body,
                     updated_at=excluded.updated_at,
                     status=CASE WHEN email_outbox.status='sent' THEN 'sent' ELSE 'pending' END""",
                (dedupe_key, booking_id, role, recipient, subject, body, now, now),
            )
        return dedupe_key

    def _deliver_outbox_row(row):
        ok, reason = smtp_send(row["recipient"], row["subject"], row["body"])
        now = datetime.now().isoformat(timespec="seconds")
        provider_message_id = ""
        if ok and ":" in reason:
            provider_message_id = reason.split(":", 1)[1]
        with db() as conn:
            conn.execute(
                """UPDATE email_outbox
                   SET status=?, attempts=attempts+1, last_error=?,
                       provider_message_id=?, updated_at=?
                   WHERE id=?""",
                ("sent" if ok else "pending", "" if ok else reason,
                 provider_message_id, now, row["id"]),
            )
            conn.execute(
                "INSERT INTO email_log(booking_id,recipient,subject,status,created_at) VALUES(?,?,?,?,?)",
                (row["booking_id"], row["recipient"], row["subject"], reason, now),
            )
        return ok, reason

    def process_mail_outbox(limit=20):
        with db() as conn:
            rows = conn.execute(
                """SELECT * FROM email_outbox
                   WHERE status='pending' AND attempts < 12
                   ORDER BY id LIMIT ?""",
                (int(limit),),
            ).fetchall()
        sent = 0
        for row in rows:
            ok, _ = _deliver_outbox_row(row)
            if ok:
                sent += 1
            else:
                time.sleep(1)
        return sent, len(rows)

    def _mail_retry_worker():
        while True:
            try:
                expire_unverified_onsite()
                now_iso = datetime.now().isoformat(timespec="seconds")
                with db() as conn:
                    conn.execute(
                        """UPDATE bookings
                           SET status='inquiry'
                           WHERE payment_method='Vor Ort'
                             AND status='pending'
                             AND payment_status NOT IN ('paid_partial','paid_full')
                             AND payment_hold_expires_at<>''
                             AND payment_hold_expires_at < ?""",
                        (now_iso,),
                    )
                process_mail_outbox(limit=10)
            except Exception:
                app.logger.exception("mail_retry_worker_failed")
            time.sleep(60)

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
            f"Zimmer: {'Gartenzimmer' if booking['room'] == 'Bachblick' else booking['room']}",
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

    def expire_unverified_onsite():
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET status='expired'
                   WHERE payment_method='Vor Ort'
                     AND status='inquiry'
                     AND onsite_verified_at=''
                     AND onsite_verify_expires_at<>''
                     AND onsite_verify_expires_at < ?""",
                (now,),
            )

    def send_onsite_verification(booking_id):
        with db() as conn:
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not booking or booking["payment_method"] != "Vor Ort":
                return False

            token = booking["onsite_verify_token"] or token_urlsafe(32)
            expires = booking["onsite_verify_expires_at"]
            if not expires or booking["status"] == "expired":
                expires = (datetime.now() + timedelta(hours=2)).isoformat(timespec="seconds")
                conn.execute(
                    """UPDATE bookings
                       SET onsite_verify_token=?, onsite_verify_expires_at=?,
                           onsite_verified_at='', status='inquiry'
                       WHERE id=?""",
                    (token, expires, booking_id),
                )

        site_url = os.environ.get("PUBLIC_SITE_URL", "https://www.zuhauseambach-wachau.at").rstrip("/")
        room_name = "Gartenzimmer" if booking["room"] == "Bachblick" else booking["room"]
        subject = "Bitte Buchungsanfrage bestätigen – Zuhause am Bach"
        body = (
            f"Hallo {booking['first_name']},\n\n"
            "du hast Zahlung bei Anreise gewählt. Damit der Termin nicht durch unbeabsichtigte "
            "oder nicht ernst gemeinte Anfragen blockiert wird, bestätige bitte deine E-Mail-Adresse.\n\n"
            f"Zimmer: {room_name}\n"
            f"Anreise: {booking['arrival']}\n"
            f"Abreise: {booking['departure']}\n"
            f"Personen: {booking['adults']}\n"
            f"Gesamtbetrag: {booking['total']:.2f} EUR\n\n"
            f"Bestätigen: {site_url}/verify-onsite/{token}\n\n"
            "Der Link ist 2 Stunden gültig. Erst nach der Bestätigung wird der Zeitraum vorläufig reserviert.\n\n"
            "Zuhause am Bach"
        )
        key = _queue_mail(booking_id, "onsite_verify", booking["email"], subject, body)
        with db() as conn:
            row = conn.execute("SELECT * FROM email_outbox WHERE dedupe_key=?", (key,)).fetchone()
        if not row:
            return False
        if row["status"] == "sent":
            return True
        ok, _ = _deliver_outbox_row(row)
        return ok

    @app.get("/verify-onsite/<token>")
    def verify_onsite(token):
        expire_unverified_onsite()
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            booking = conn.execute(
                "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
                (token,),
            ).fetchone()
            if not booking:
                return Response("<h1>Bestätigungslink ungültig.</h1>", status=404, mimetype="text/html")

            if booking["onsite_verified_at"]:
                return Response("<h1>Bereits bestätigt.</h1><p>Der Zeitraum ist bereits vorläufig reserviert.</p>", mimetype="text/html")

            if booking["onsite_verify_expires_at"] and booking["onsite_verify_expires_at"] < now:
                conn.execute("UPDATE bookings SET status='expired' WHERE id=?", (booking["id"],))
                return Response("<h1>Bestätigungslink abgelaufen.</h1><p>Bitte stelle eine neue Anfrage.</p>", status=410, mimetype="text/html")

            local_conflict = conn.execute(
                """SELECT id FROM bookings
                   WHERE id<>? AND room=? AND status IN ('pending','confirmed')
                     AND arrival < ? AND departure > ?
                   LIMIT 1""",
                (booking["id"], booking["room"], booking["departure"], booking["arrival"]),
            ).fetchone()
            external_conflict = conn.execute(
                """SELECT id FROM external_blocks
                   WHERE room=? AND start_date < ? AND end_date > ?
                   LIMIT 1""",
                (booking["room"], booking["departure"], booking["arrival"]),
            ).fetchone()
            if local_conflict or external_conflict:
                conn.execute("UPDATE bookings SET status='expired' WHERE id=?", (booking["id"],))
                return Response("<h1>Termin nicht mehr verfügbar.</h1><p>Bitte wähle einen anderen Zeitraum.</p>", status=409, mimetype="text/html")

            conn.execute(
                "UPDATE bookings SET status='inquiry', onsite_verified_at=? WHERE id=?",
                (now, booking["id"]),
            )

        owner = (
            os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
            or os.environ.get("SITE_EMAIL", "").strip()
            or "zuhause.am.bach@outlook.com"
        )
        subject = f"Vor-Ort-Anfrage bestätigt: {booking['first_name']} {booking['last_name']}"
        body = (
            f"Buchung #{booking['id']}\n"
            f"Gast: {booking['first_name']} {booking['last_name']}\n"
            f"E-Mail: {booking['email']}\n"
            f"Telefon: {booking['phone']}\n"
            f"Anreise: {booking['arrival']}\n"
            f"Abreise: {booking['departure']}\n"
            f"Personen: {booking['adults']}\n"
            f"Gesamtpreis: {booking['total']:.2f} EUR\n"
            "Zahlung: Vor Ort\n"
            "E-Mail-Verifizierung: erfolgreich\n"
            "Status: E-Mail bestätigt – SMS und Zahlung noch ausständig"
        )
        owner_key = _queue_mail(booking["id"], "onsite_verified_owner", owner, subject, body)
        with db() as conn:
            owner_row = conn.execute("SELECT * FROM email_outbox WHERE dedupe_key=?", (owner_key,)).fetchone()
        if owner_row and owner_row["status"] != "sent":
            _deliver_outbox_row(owner_row)

        return redirect(url_for("onsite_security", token=token))

    def send_booking_confirmation(booking_id):
        public_token, cancel_token, invoice_number = ensure_booking_tokens(booking_id)
        with db() as conn:
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        cfg = settings()
        site_url = os.environ.get("PUBLIC_SITE_URL", "https://www.zuhauseambach-wachau.at").rstrip("/")
        room_name = "Gartenzimmer" if booking["room"] == "Bachblick" else booking["room"]
        is_confirmed = booking["status"] == "confirmed"
        is_paid = bool(booking["paid"])
        payment_method = booking["payment_method"]

        guest_subject = (
            "Buchungsbestätigung – Zuhause am Bach"
            if is_confirmed else
            "Buchungsanfrage eingegangen – Zuhause am Bach"
        )

        if is_confirmed:
            intro = (
                f"deine Buchung für {room_name} von {booking['arrival']} bis {booking['departure']} "
                "ist bestätigt."
            )
        else:
            intro = (
                f"deine Buchungsanfrage für {room_name} von {booking['arrival']} bis {booking['departure']} "
                "ist eingegangen. Der Termin wird erst nach unserer persönlichen Bestätigung verbindlich reserviert."
            )

        payment_info = ""
        if payment_method == "Banküberweisung":
            holder = os.environ.get("BANK_ACCOUNT_HOLDER", "").strip()
            iban = os.environ.get("BANK_IBAN", "").strip()
            iban_display = " ".join(iban[i:i+4] for i in range(0, len(iban), 4)) if iban else ""
            payment_info = (
                "\nBanküberweisung:\n"
                f"Kontoinhaber: {holder}\n"
                f"IBAN: {iban_display}\n"
                f"Betrag: {booking['total']:.2f} EUR\n"
                f"Verwendungszweck: ZAB-{booking_id:06d} · {booking['first_name']}\n"
                "Bitte erst nach unserer persönlichen Buchungsbestätigung überweisen.\n"
            )
        elif payment_method == "PayPal":
            payment_info = (
                "\nPayPal-Zahlung: erfolgreich bestätigt.\n"
                if is_paid else
                "\nPayPal-Zahlung: noch nicht abgeschlossen.\n"
            )
        elif payment_method == "Vor Ort":
            payment_info = "\nZahlung: bei Anreise vor Ort.\n"

        guest_body = (
            f"Hallo {booking['first_name']},\n\n"
            f"{intro}\n"
            f"Gesamtbetrag: {booking['total']:.2f} EUR\n"
            f"Zahlungsart: {payment_method}\n"
            f"{payment_info}\n"
            f"Gästeportal: {site_url}/guest/{public_token}\n"
            f"Stornierung: {site_url}/cancel/{cancel_token}\n"
            f"Rechnung: {site_url}/invoice/{public_token}.pdf\n\n"
            "Wir freuen uns auf deinen Aufenthalt.\n"
            "Zuhause am Bach"
        )
        owner = (
            os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
            or os.environ.get("SITE_EMAIL", "").strip()
            or cfg.get("email", "").strip()
            or PAYPAL_EMAIL
        )
        owner_subject = (
            f"Neue bestätigte Buchung: {room_name}"
            if is_confirmed else
            f"Neue Buchungsanfrage: {room_name}"
        )
        owner_body = (
            f"Buchung #{booking_id}\n"
            f"Gast: {booking['first_name']} {booking['last_name']}\n"
            f"E-Mail: {booking['email']}\n"
            f"Telefon: {booking['phone']}\n"
            f"Zimmer: {room_name}\n"
            f"Anreise: {booking['arrival']}\n"
            f"Abreise: {booking['departure']}\n"
            f"Personen: {booking['adults']}\n"
            f"Gesamtpreis: {booking['total']:.2f} EUR\n"
            f"Zahlungsart: {payment_method}\n"
            f"Status: {booking['status']}\n"
            f"Nachricht: {booking['message'] or '-'}"
        )
        forced_recipient = os.environ.get("FORCE_BOOKING_MAIL_TO", "").strip()
        owner_recipient = forced_recipient or owner
        guest_recipient = booking["email"]

        app.logger.warning("booking_mail_queue booking_id=%s owner=%s", booking_id, owner_recipient)
        owner_key = _queue_mail(booking_id, "owner", owner_recipient, owner_subject, owner_body)

        with db() as conn:
            row = conn.execute(
                "SELECT * FROM email_outbox WHERE dedupe_key=?",
                (owner_key,),
            ).fetchone()

        if row and row["status"] == "sent":
            ok_owner, msg_owner = True, "already_sent"
        elif row:
            ok_owner, msg_owner = _deliver_outbox_row(row)
        else:
            ok_owner, msg_owner = False, "owner_missing"

        app.logger.warning(
            "booking_mail_results booking_id=%s owner_ok=%s owner_status=%s",
            booking_id, ok_owner, msg_owner,
        )
        return ok_owner

    app.extensions["zab_send_confirmation"] = send_booking_confirmation
    app.extensions["zab_ensure_tokens"] = ensure_booking_tokens
    app.extensions["zab_smtp_send"] = smtp_send
    app.extensions["zab_send_onsite_verification"] = send_onsite_verification
    app.extensions["zab_expire_unverified_onsite"] = expire_unverified_onsite
    app.extensions["zab_process_mail_outbox"] = process_mail_outbox
    if not app.extensions.get("zab_mail_retry_worker_started"):
        app.extensions["zab_mail_retry_worker_started"] = True
        threading.Thread(target=_mail_retry_worker, name="zab-mail-retry", daemon=True).start()

    def _os_sync_authorized():
        expected = os.environ.get("OS_SYNC_TOKEN", "").strip()
        if not expected:
            return False
        provided = (
            request.headers.get("X-OS-Sync-Token", "").strip()
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        return bool(provided) and hmac.compare_digest(provided, expected)

    @app.get("/api/os/sync")
    def os_sync_feed():
        """Read-only bridge for Zuhause am Bach OS / Rainsoft Central."""
        if not _os_sync_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        # Refresh configured Booking/iCal feeds before returning calendar blocks.
        # A failed feed refresh must not break booking/mail synchronization; the
        # last successfully imported blocks remain available as a safe fallback.
        ical_results = []
        sync_room_fn = app.extensions.get("zab_sync_room")
        if sync_room_fn:
            with db() as conn:
                rooms_to_sync = [
                    row["room"]
                    for row in conn.execute(
                        "SELECT room FROM ical_settings WHERE TRIM(import_url) <> '' ORDER BY room"
                    )
                ]
            for room_name in rooms_to_sync:
                try:
                    count, message = sync_room_fn(room_name)
                    ical_results.append({"room": room_name, "ok": True, "count": count, "message": message})
                except Exception as exc:
                    app.logger.exception("os_sync_ical_refresh_failed room=%s", room_name)
                    ical_results.append({"room": room_name, "ok": False, "count": 0, "message": str(exc)})

        with db() as conn:
            bookings = [
                dict(row)
                for row in conn.execute(
                    """SELECT id,room,arrival,departure,adults,breakfast,first_name,last_name,
                              email,phone,message,payment_method,total,status,created_at,
                              paid,arrival_time,guest_note,invoice_number,
                              onsite_verified_at,onsite_verify_expires_at,
                              deposit_percent,amount_paid,payment_status,payment_reference,
                              price_breakdown_json
                       FROM bookings
                       ORDER BY id"""
                )
            ]
            mail_rows = [
                dict(row)
                for row in conn.execute(
                    """SELECT id,booking_id,recipient,subject,status,created_at
                       FROM email_log
                       ORDER BY id"""
                )
            ]
            external_blocks = [
                dict(row)
                for row in conn.execute(
                    """SELECT id,room,start_date,end_date,source,uid,summary,imported_at
                       FROM external_blocks
                       ORDER BY room,start_date,id"""
                )
            ]

        return jsonify({
            "ok": True,
            "schema": "zab-os-sync-v3",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "bookings": bookings,
            "mail": mail_rows,
            "external_blocks": external_blocks,
            "ical_refresh": ical_results,
        })

    @app.get("/internal/resend-booking/<token>/<int:booking_id>")
    def internal_resend_booking(token, booking_id):
        expected = os.environ.get("MAIL_DIAGNOSTIC_TOKEN", "")
        if not expected or not hmac.compare_digest(token, expected):
            return {"ok": False}, 404
        ok = bool(send_booking_confirmation(booking_id))
        app.logger.warning("booking_resend_result booking_id=%s ok=%s", booking_id, ok)
        return {"ok": ok, "booking_id": booking_id}, (200 if ok else 502)

    @app.get("/internal/mail-status/<token>/<int:booking_id>")
    def internal_mail_status(token, booking_id):
        expected = os.environ.get("MAIL_DIAGNOSTIC_TOKEN", "")
        if not expected or not hmac.compare_digest(token, expected):
            return {"ok": False}, 404
        with db() as conn:
            booking = conn.execute("SELECT id,email,first_name,last_name,status FROM bookings WHERE id=?", (booking_id,)).fetchone()
            rows = conn.execute("SELECT recipient,subject,status,created_at FROM email_log WHERE booking_id=? ORDER BY id", (booking_id,)).fetchall()
        return {
            "ok": True,
            "booking": dict(booking) if booking else None,
            "email_log": [dict(r) for r in rows],
        }

    @app.get("/internal/mail-diagnostic/<token>")
    def internal_mail_diagnostic(token):
        expected = os.environ.get("MAIL_DIAGNOSTIC_TOKEN", "")
        if not expected or not hmac.compare_digest(token, expected):
            return {"ok": False}, 404
        recipient = os.environ.get("BOOKING_OWNER_EMAIL", "").strip() or os.environ.get("SITE_EMAIL", "").strip()
        ok, reason = smtp_send(
            recipient,
            "Zuhause am Bach – Mail-Diagnose",
            "Technischer Test des automatischen Buchungs-Mailversands.",
        )
        app.logger.warning("mail_diagnostic_result ok=%s reason=%s recipient=%s", ok, reason, recipient)
        return {"ok": bool(ok), "reason": reason, "recipient": recipient}, (200 if ok else 502)

    @app.get("/guest/<token>")
    def guest_portal(token):
        b = booking_by_token(token)
        if not b:
            return "Buchung nicht gefunden", 404
        with db() as conn:
            orders = conn.execute("SELECT * FROM guest_orders WHERE booking_id=? ORDER BY created_at DESC", (b["id"],)).fetchall()
        cfg = settings()
        return render_template(
            "guest_portal.html",
            booking=b,
            orders=orders,
            settings=cfg,
            guest_app_url=cfg.get("public_base_url", "https://topdiveair-sketch.github.io/Gaeste/"),
        )

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

    @app.post("/admin/booking/<int:booking_id>/confirm")
    def confirm_booking(booking_id):
        if not require_admin():
            return redirect(url_for("admin_login"))

        sync_room = app.extensions.get("zab_sync_room")
        if sync_room:
            try:
                with db() as conn:
                    current = conn.execute("SELECT room FROM bookings WHERE id=?", (booking_id,)).fetchone()
                if current:
                    sync_room(current["room"])
            except Exception:
                pass

        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not booking:
                conn.rollback()
                flash("Buchungsanfrage wurde nicht gefunden.", "error")
                return redirect(url_for("dashboard"))
            if booking["status"] == "confirmed":
                conn.rollback()
                flash("Buchung ist bereits bestätigt.", "success")
                return redirect(url_for("dashboard"))
            if booking["status"] != "inquiry":
                conn.rollback()
                flash("Diese Buchung kann in diesem Status nicht bestätigt werden.", "error")
                return redirect(url_for("dashboard"))

            local_conflict = conn.execute(
                """SELECT id FROM bookings
                   WHERE id<>? AND room=? AND status IN ('pending','confirmed')
                     AND arrival < ? AND departure > ?
                   LIMIT 1""",
                (booking_id, booking["room"], booking["departure"], booking["arrival"]),
            ).fetchone()
            external_conflict = conn.execute(
                """SELECT id FROM external_blocks
                   WHERE room=? AND start_date < ? AND end_date > ?
                   LIMIT 1""",
                (booking["room"], booking["departure"], booking["arrival"]),
            ).fetchone()

            if local_conflict or external_conflict:
                conn.rollback()
                flash("Nicht bestätigt: Der Zeitraum ist inzwischen belegt.", "error")
                return redirect(url_for("dashboard"))

            conn.execute("UPDATE bookings SET status='confirmed' WHERE id=?", (booking_id,))

        try:
            send_booking_confirmation(booking_id)
        except Exception:
            pass
        flash("Buchungsanfrage wurde bestätigt und der Zeitraum ist jetzt reserviert.", "success")
        return redirect(url_for("dashboard"))


    @app.post("/admin/booking/<int:booking_id>/paid")
    def mark_paid(booking_id):
        if not require_admin():
            return redirect(url_for("admin_login"))
        with db() as conn:
            booking = conn.execute("SELECT status FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not booking:
                flash("Buchung wurde nicht gefunden.", "error")
                return redirect(url_for("dashboard"))
            if booking["status"] == "inquiry":
                flash("Bitte die Anfrage zuerst bestätigen. Erst danach kann sie als bezahlt markiert werden.", "error")
                return redirect(url_for("dashboard"))
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

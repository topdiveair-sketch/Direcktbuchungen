from __future__ import annotations

import os
import re
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import jsonify, request


PAID_GUEST_SUBJECT = "Buchung bestätigt – Zuhause am Bach"


def init_booking_notifications(app, db):
    """Send booking emails and expose a safe, non-binding direct-inquiry endpoint."""

    def settings():
        with db() as conn:
            return {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM site_settings")}

    def smtp_send(to: str, subject: str, body: str):
        cfg = settings()
        host = cfg.get("smtp_host", "")
        user = cfg.get("smtp_user", "")
        password = cfg.get("smtp_password", "")
        port = int(cfg.get("smtp_port", "587") or 587)
        sender = cfg.get("smtp_sender", user or cfg.get("email", ""))
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

    def already_sent(booking_id: int, recipient: str) -> bool:
        with db() as conn:
            row = conn.execute(
                """SELECT 1 FROM email_log
                   WHERE booking_id=? AND lower(recipient)=lower(?)
                     AND subject=? AND status='gesendet'
                   LIMIT 1""",
                (booking_id, recipient, PAID_GUEST_SUBJECT),
            ).fetchone()
        return bool(row)

    def send_paid_confirmation(booking_id: int):
        with db() as conn:
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not booking:
            return False
        if booking["status"] != "confirmed" or not int(booking["paid"] or 0):
            return False
        if already_sent(booking_id, booking["email"]):
            return True

        keys = set(booking.keys())
        arrival = datetime.fromisoformat(booking["arrival"])
        departure = datetime.fromisoformat(booking["departure"])
        nights = max(0, (departure - arrival).days)
        capture = booking["paypal_capture_id"] if "paypal_capture_id" in keys else ""

        body = (
            f"Hallo {booking['first_name']} {booking['last_name']},\n\n"
            "Ihre PayPal-Zahlung ist bestätigt. Ihre Buchung bei Zuhause am Bach ist damit verbindlich.\n\n"
            "Ihre Buchungsdaten:\n"
            f"Buchungsnummer: {booking['uid']}\n"
            f"Zimmer: {booking['room']}\n"
            f"Anreise: {booking['arrival']}\n"
            f"Abreise: {booking['departure']}\n"
            f"Nächte: {nights}\n"
            f"Personen: {booking['adults']}\n"
            f"Gesamtpreis bezahlt: {booking['total']:.2f} EUR\n"
        )
        if capture:
            body += f"PayPal-Transaktion: {capture}\n"
        body += (
            "\nDer gebuchte Zeitraum ist verbindlich für Sie reserviert.\n\n"
            "Wir freuen uns auf Ihren Aufenthalt.\n\n"
            "Herzliche Grüße\nZuhause am Bach"
        )

        ok, status = smtp_send(booking["email"], PAID_GUEST_SUBJECT, body)
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO email_log(booking_id,recipient,subject,status,created_at) VALUES(?,?,?,?,?)",
                    (
                        booking_id,
                        booking["email"],
                        PAID_GUEST_SUBJECT,
                        status,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
        except Exception:
            pass
        return ok

    # A direct inquiry is intentionally not written into the bookings table:
    # it must never block dates before the host has personally confirmed it.
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                room TEXT NOT NULL,
                arrival TEXT NOT NULL,
                departure TEXT NOT NULL,
                adults INTEGER NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                message TEXT DEFAULT '',
                breakfast INTEGER NOT NULL DEFAULT 0,
                jause INTEGER NOT NULL DEFAULT 0,
                luggage INTEGER NOT NULL DEFAULT 0,
                source TEXT DEFAULT '',
                utm_medium TEXT DEFAULT '',
                utm_campaign TEXT DEFAULT '',
                page TEXT DEFAULT '',
                referrer TEXT DEFAULT ''
            )
            """
        )

    default_origin = "https://topdiveair-sketch.github.io"
    configured_origins = {
        value.strip().rstrip("/")
        for value in os.environ.get("PUBLIC_SITE_ORIGINS", "").split(",")
        if value.strip()
    }
    allowed_origins = {default_origin, *configured_origins}

    def with_cors(response):
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Cache-Control"] = "no-store"
        return response

    def clean(value, limit=500):
        return str(value or "").strip()[:limit]

    @app.route("/api/inquiry", methods=["POST", "OPTIONS"])
    def api_direct_inquiry():
        origin = request.headers.get("Origin", "").rstrip("/")
        if request.method == "OPTIONS":
            response = app.response_class(status=204)
            return with_cors(response)
        if origin not in allowed_origins:
            return with_cors(jsonify(ok=False, message="Origin nicht freigegeben.")), 403
        if (request.content_length or 0) > 20000:
            return with_cors(jsonify(ok=False, message="Anfrage ist zu groß.")), 413

        data = request.get_json(silent=True) or {}
        # Honeypot: normal visitors never fill this field.
        if clean(data.get("website"), 200):
            return with_cors(jsonify(ok=True, message="Anfrage erhalten.")), 200

        room = clean(data.get("room"), 60)
        arrival_text = clean(data.get("arrival"), 20)
        departure_text = clean(data.get("departure"), 20)
        first_name = clean(data.get("first_name"), 80)
        last_name = clean(data.get("last_name"), 80)
        email = clean(data.get("email"), 160)
        phone = clean(data.get("phone"), 80)
        message = clean(data.get("message"), 2000)
        source = clean(data.get("source"), 120)
        utm_medium = clean(data.get("utm_medium"), 120)
        utm_campaign = clean(data.get("utm_campaign"), 160)
        page = clean(data.get("page"), 300)
        referrer = clean(data.get("referrer"), 300)
        extras = data.get("extras") if isinstance(data.get("extras"), dict) else {}

        try:
            adults = int(data.get("adults") or 0)
        except (TypeError, ValueError):
            adults = 0

        if room != "Bachblick":
            return with_cors(jsonify(ok=False, message="Dieses Zimmer ist derzeit nicht für Direktanfragen freigegeben.")), 400
        if not first_name or not last_name or not email or not phone:
            return with_cors(jsonify(ok=False, message="Bitte Kontaktdaten vollständig ausfüllen.")), 400
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return with_cors(jsonify(ok=False, message="Bitte eine gültige E-Mail-Adresse eingeben.")), 400
        if adults not in (1, 2):
            return with_cors(jsonify(ok=False, message="Bitte 1 oder 2 Personen wählen.")), 400

        try:
            arrival = datetime.fromisoformat(arrival_text).date()
            departure = datetime.fromisoformat(departure_text).date()
        except ValueError:
            return with_cors(jsonify(ok=False, message="Bitte gültige Reisedaten wählen.")), 400
        nights = (departure - arrival).days
        if arrival < datetime.now().date() or nights < 1 or nights > 30:
            return with_cors(jsonify(ok=False, message="Bitte einen gültigen zukünftigen Reisezeitraum wählen.")), 400

        created_at = datetime.now().isoformat(timespec="seconds")
        duplicate_cutoff = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
        with db() as conn:
            duplicate = conn.execute(
                """SELECT id FROM inquiries
                   WHERE lower(email)=lower(?) AND arrival=? AND departure=? AND room=?
                     AND created_at>=?
                   ORDER BY id DESC LIMIT 1""",
                (email, arrival_text, departure_text, room, duplicate_cutoff),
            ).fetchone()
            if duplicate:
                inquiry_id = int(duplicate["id"])
            else:
                cur = conn.execute(
                    """INSERT INTO inquiries(
                           created_at,room,arrival,departure,adults,first_name,last_name,email,phone,message,
                           breakfast,jause,luggage,source,utm_medium,utm_campaign,page,referrer
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        created_at,
                        room,
                        arrival_text,
                        departure_text,
                        adults,
                        first_name,
                        last_name,
                        email,
                        phone,
                        message,
                        1 if extras.get("breakfast") else 0,
                        1 if extras.get("jause") else 0,
                        1 if extras.get("luggage") else 0,
                        source,
                        utm_medium,
                        utm_campaign,
                        page,
                        referrer,
                    ),
                )
                inquiry_id = int(cur.lastrowid)

        extras_names = []
        if extras.get("breakfast"):
            extras_names.append("Frühstück")
        if extras.get("jause"):
            extras_names.append("Wachauer Jause")
        if extras.get("luggage"):
            extras_names.append("Gepäcktransport (Preis nach Strecke)")
        extras_text = ", ".join(extras_names) if extras_names else "keine"
        attribution = source or "direkt / unbekannt"
        if utm_medium:
            attribution += f" | Medium: {utm_medium}"
        if utm_campaign:
            attribution += f" | Kampagne: {utm_campaign}"

        owner_body = (
            "NEUE DIREKTANFRAGE VON DER WEBSITE\n\n"
            f"Anfrage-ID: {inquiry_id}\n"
            f"Gast: {first_name} {last_name}\n"
            f"Zimmer: {room}\n"
            f"Anreise: {arrival_text}\n"
            f"Abreise: {departure_text}\n"
            f"Nächte: {nights}\n"
            f"Personen: {adults}\n"
            f"Zusatzleistungen: {extras_text}\n"
            f"Telefon: {phone}\n"
            f"E-Mail: {email}\n"
            f"Nachricht: {message or 'keine'}\n\n"
            f"Quelle: {attribution}\n"
            f"Seite: {page or 'unbekannt'}\n"
            f"Referrer: {referrer or 'keiner'}\n\n"
            "Dies ist eine unverbindliche Anfrage und blockiert das Zimmer noch nicht."
        )
        cfg = settings()
        owner_email = cfg.get("inquiry_email", "").strip() or cfg.get("email", "").strip() or "topdiveair@gmail.com"
        ok_owner, owner_status = smtp_send(
            owner_email,
            f"[WICHTIG] Neue Direktanfrage: {arrival_text} – {departure_text}",
            owner_body,
        )

        guest_body = (
            f"Hallo {first_name} {last_name},\n\n"
            "vielen Dank für Ihre Anfrage bei Zuhause am Bach – Wachau.\n"
            "Ihre Reisedaten sind bei uns angekommen.\n\n"
            f"Zimmer: {room}\n"
            f"Anreise: {arrival_text}\n"
            f"Abreise: {departure_text}\n"
            f"Personen: {adults}\n"
            f"Zusatzleistungen: {extras_text}\n\n"
            "Wichtig: Dies ist noch keine verbindliche Buchungsbestätigung. "
            "Wir prüfen die Anfrage persönlich und melden uns anschließend bei Ihnen.\n\n"
            "Herzliche Grüße\nZuhause am Bach – Wachau"
        )
        ok_guest, _ = smtp_send(email, "Ihre Anfrage ist angekommen – Zuhause am Bach", guest_body)

        if not ok_owner:
            return with_cors(
                jsonify(
                    ok=False,
                    message="Direktversand konnte nicht bestätigt werden. Bitte E-Mail oder WhatsApp verwenden.",
                    detail=owner_status,
                )
            ), 503

        return with_cors(
            jsonify(
                ok=True,
                inquiry_id=inquiry_id,
                guest_acknowledgement=bool(ok_guest),
                message="Anfrage wurde direkt übermittelt.",
            )
        ), 200

    @app.after_request
    def send_missing_paid_confirmations(response):
        try:
            with db() as conn:
                rows = conn.execute(
                    """SELECT b.id
                       FROM bookings b
                       WHERE b.status='confirmed' AND COALESCE(b.paid,0)=1
                         AND NOT EXISTS (
                             SELECT 1 FROM email_log e
                             WHERE e.booking_id=b.id
                               AND lower(e.recipient)=lower(b.email)
                               AND e.subject=? AND e.status='gesendet'
                         )
                       ORDER BY b.id
                       LIMIT 5""",
                    (PAID_GUEST_SUBJECT,),
                ).fetchall()
            for row in rows:
                send_paid_confirmation(row["id"])
        except Exception:
            pass
        return response

    app.extensions["zab_send_paid_guest_confirmation"] = send_paid_confirmation
    app.extensions["zab_direct_inquiry_enabled"] = True

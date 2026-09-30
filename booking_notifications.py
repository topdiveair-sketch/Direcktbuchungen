from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
import re
from datetime import datetime, timedelta

from flask import jsonify, request

from transactional_email import send_transactional_email


PAID_GUEST_SUBJECT = "Buchung bestätigt / Booking confirmed – Zuhause am Bach"
PUBLIC_CONTACT_EMAIL = "Zuhause.am.Bach@outlook.com"


def init_booking_notifications(app, db):
    """Send booking emails and expose a safe, non-binding direct-inquiry endpoint."""

    def settings():
        with db() as conn:
            return {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM site_settings")}

    def smtp_send(to: str, subject: str, body: str, *, reply_to: str | None = None, important: bool = False):
        return send_transactional_email(
            to,
            subject,
            body,
            settings=settings(),
            reply_to=reply_to,
            important=important,
        )

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
        payment_method = str(booking["payment_method"] or "").strip()
        booking_number = (
            str(booking["booking_number"]).strip()
            if "booking_number" in keys and booking["booking_number"]
            else str(booking["uid"] or f"ZAB-{booking_id:06d}")
        )

        extras_text = "Keine"
        if "price_breakdown_json" in keys and booking["price_breakdown_json"]:
            try:
                breakdown = json.loads(booking["price_breakdown_json"])
                lines = breakdown.get("extras") if isinstance(breakdown, dict) else []
                labels = [
                    str(line.get("label") or "").strip()
                    for line in (lines or [])
                    if isinstance(line, dict) and str(line.get("label") or "").strip()
                ]
                if labels:
                    extras_text = ", ".join(labels)
            except Exception:
                pass
        elif "breakfast" in keys and int(booking["breakfast"] or 0):
            extras_text = "Frühstück"

        cfg = settings()
        cancellation_text = (
            cfg.get("cancellation_text", "").strip()
            or "Kostenfreie Stornierung bis 7 Tage vor Anreise."
        )

        if payment_method == "PayPal":
            payment_status = "PayPal-Zahlung bestätigt"
        elif payment_method == "Banküberweisung":
            payment_status = "Banküberweisung eingegangen"
        else:
            payment_status = "Zahlung bestätigt"

        body = (
            f"Hallo {booking['first_name']} {booking['last_name']},\n\n"
            "deine Buchung bei Zuhause am Bach – Wachau ist verbindlich bestätigt.\n\n"
            "DEINE BUCHUNG AUF EINEN BLICK\n"
            f"Buchungsnummer: {booking_number}\n"
            f"Zimmer: Gartenzimmer\n"
            f"Anreise: {booking['arrival']}\n"
            f"Abreise: {booking['departure']}\n"
            f"Nächte: {nights}\n"
            f"Gäste: {booking['adults']}\n"
            f"Extras: {extras_text}\n"
            f"Gesamtpreis: {float(booking['total']):.2f} EUR\n\n"
            "ZAHLUNG\n"
            f"Zahlungsart: {payment_method or 'bezahlt'}\n"
            f"Status: {payment_status}\n"
        )
        if capture and payment_method == "PayPal":
            body += f"PayPal-Transaktion: {capture}\n"

        body += (
            "\nSTORNIERUNG\n"
            f"{cancellation_text}\n\n"
            "ANREISE\n"
            "Check-in: ab 14:00 Uhr\n"
            "Check-out: bis 10:00 Uhr\n"
            "Adresse: Aggsbach Markt 82, 3641 Aggsbach Markt, Österreich\n"
            "Google Maps / Navigation:\n"
            "https://www.google.com/maps/search/?api=1&query=Aggsbach+Markt+82%2C+3641+Aggsbach+Markt%2C+Austria\n\n"
            "Der gebuchte Zeitraum ist jetzt fest für dich reserviert. "
            "Bei Fragen oder Änderungswünschen antworte einfach auf diese E-Mail.\n\n"
            "Wir freuen uns auf deinen Aufenthalt in der Wachau.\n\n"
            "Herzliche Grüße\n"
            "Zuhause am Bach – Wachau\n"
            "https://www.zuhauseambach-wachau.at/"
        )

        ok, status = smtp_send(
            booking["email"],
            PAID_GUEST_SUBJECT,
            body,
            reply_to=PUBLIC_CONTACT_EMAIL,
            important=True,
        )
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
        owner_email = cfg.get("inquiry_email", "").strip() or PUBLIC_CONTACT_EMAIL
        ok_owner, owner_status = smtp_send(
            owner_email,
            f"[WICHTIG] Neue Direktanfrage: {arrival_text} – {departure_text}",
            owner_body,
            reply_to=email,
            important=True,
        )

        guest_body = (
            f"Hallo / Hello {first_name} {last_name},\n\n"
            "vielen Dank für Ihre Anfrage bei Zuhause am Bach – Wachau. Ihre Reisedaten sind bei uns angekommen.\n"
            "Thank you for your request to Zuhause am Bach – Wachau. We have received your travel dates.\n\n"
            f"Zimmer / Room: {room}\n"
            f"Anreise / Arrival: {arrival_text}\n"
            f"Abreise / Departure: {departure_text}\n"
            f"Personen / Guests: {adults}\n"
            f"Zusatzleistungen / Extras: {extras_text}\n\n"
            "Adresse / Address: Aggsbach Markt 82, 3641 Aggsbach Markt, Österreich\n"
            "Google Maps / Navigation: https://www.google.com/maps/search/?api=1&query=Aggsbach+Markt+82%2C+3641+Aggsbach+Markt%2C+Austria\n\n"
            "Wichtig: Dies ist noch keine verbindliche Buchungsbestätigung. Wir prüfen die Anfrage persönlich und melden uns anschließend.\n"
            "Important: This is not yet a binding booking confirmation. We will review your request personally and contact you afterwards.\n\n"
            "Herzliche Grüße / Kind regards\nZuhause am Bach – Wachau"
        )
        ok_guest, _ = smtp_send(email, "Anfrage erhalten / Request received – Zuhause am Bach", guest_body)

        if not ok_owner:
            return with_cors(
                jsonify(
                    ok=False,
                    message="Direktversand konnte nicht bestätigt werden. Bitte E-Mail oder WhatsApp verwenden.",
                    detail="smtp_unavailable",
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

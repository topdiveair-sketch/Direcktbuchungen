from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage


PAID_GUEST_SUBJECT = "Buchung bestätigt – Zuhause am Bach"


def init_booking_notifications(app, db):
    """Send a final guest email once a PayPal booking is paid and confirmed."""

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

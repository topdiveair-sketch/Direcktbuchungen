from __future__ import annotations

import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage


HOLD_MINUTES = 10


def init_payment_hold(app, db):
    """Add a 10-minute payment hold and booking-specific payment reply."""

    def ensure_column(conn, table, column, definition):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    with db() as conn:
        ensure_column(conn, "bookings", "hold_expires_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "released_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "release_reason", "TEXT DEFAULT ''")

    def settings():
        with db() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key,value FROM site_settings")}

    def start_hold(booking_id: int) -> str:
        expires = datetime.now() + timedelta(minutes=HOLD_MINUTES)
        expires_iso = expires.isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET hold_expires_at=?, released_at='', release_reason=''
                   WHERE id=? AND status='pending' AND COALESCE(paid,0)=0""",
                (expires_iso, booking_id),
            )
        return expires_iso

    def release_expired() -> int:
        now_iso = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            cur = conn.execute(
                """UPDATE bookings
                   SET status='cancelled', released_at=?,
                       release_reason='Zahlungsfrist von 10 Minuten abgelaufen'
                   WHERE status='pending'
                     AND COALESCE(paid,0)=0
                     AND COALESCE(hold_expires_at,'')!=''
                     AND hold_expires_at<=?""",
                (now_iso, now_iso),
            )
            return cur.rowcount

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

    original_confirmation = app.extensions.get("zab_send_confirmation")
    ensure_tokens = app.extensions.get("zab_ensure_tokens")

    def send_payment_hold_reply(booking_id: int):
        if ensure_tokens:
            ensure_tokens(booking_id)
        expires_iso = start_hold(booking_id)
        with db() as conn:
            b = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not b:
            return False

        cfg = settings()
        paypal_email = cfg.get("paypal_email", "topdiveair@gmail.com").strip()
        paypal_url = cfg.get("paypal_me_url", "").strip()
        payment_line = (
            f"PayPal-Zahlungslink: {paypal_url}"
            if paypal_url
            else f"PayPal-Zahlung an: {paypal_email}"
        )
        extras = []
        if b["breakfast"]:
            extras.append("Frühstück")
        extras_text = ", ".join(extras) if extras else "keine"
        nights = (datetime.fromisoformat(b["departure"]) - datetime.fromisoformat(b["arrival"])).days
        expires = datetime.fromisoformat(expires_iso).strftime("%H:%M Uhr")

        body = (
            f"Hallo {b['first_name']} {b['last_name']},\n\n"
            "vielen Dank für Ihre Buchungsanfrage bei Zuhause am Bach.\n\n"
            f"Wir haben das Zimmer {b['room']} für Sie für 10 Minuten reserviert.\n\n"
            "Ihre Buchungsdaten:\n"
            f"Anreise: {b['arrival']}\n"
            f"Abreise: {b['departure']}\n"
            f"Nächte: {nights}\n"
            f"Personen: {b['adults']}\n"
            f"Zimmer: {b['room']}\n"
            f"Zusatzleistungen: {extras_text}\n"
            f"Gesamtpreis: {b['total']:.2f} EUR\n\n"
            f"Bitte bezahlen Sie den Betrag innerhalb von 10 Minuten, spätestens bis {expires}.\n"
            f"{payment_line}\n\n"
            "Nach Eingang der Zahlung wird Ihre Buchung verbindlich bestätigt.\n\n"
            "Erfolgt innerhalb von 10 Minuten keine Zahlung, wird die Reservierung automatisch aufgehoben und das Zimmer wieder zur Buchung freigegeben.\n\n"
            "Herzliche Grüße\nZuhause am Bach"
        )
        ok_guest, guest_status = smtp_send(
            b["email"], "Ihre Zimmerreservierung – Zuhause am Bach", body
        )

        owner = cfg.get("email", paypal_email)
        owner_body = (
            f"Neue Direktanfrage mit 10-Minuten-Zahlungsfrist\n\n"
            f"Gast: {b['first_name']} {b['last_name']}\n"
            f"Zimmer: {b['room']}\n"
            f"Anreise: {b['arrival']}\nAbreise: {b['departure']}\n"
            f"Personen: {b['adults']}\nGesamt: {b['total']:.2f} EUR\n"
            f"Telefon: {b['phone']}\nE-Mail: {b['email']}\n"
            f"Reserviert bis: {expires}\n"
        )
        ok_owner, owner_status = smtp_send(owner, f"Neue Direktanfrage: {b['room']}", owner_body)

        with db() as conn:
            conn.execute(
                "INSERT INTO email_log(booking_id,recipient,subject,status,created_at) VALUES(?,?,?,?,?)",
                (booking_id, b["email"], "Zimmerreservierung 10 Minuten", guest_status, datetime.now().isoformat(timespec="seconds")),
            )
        return ok_guest or ok_owner

    @app.before_request
    def cleanup_expired_payment_holds():
        release_expired()

    app.extensions["zab_original_send_confirmation"] = original_confirmation
    app.extensions["zab_send_confirmation"] = send_payment_hold_reply
    app.extensions["zab_start_payment_hold"] = start_hold
    app.extensions["zab_release_expired_holds"] = release_expired

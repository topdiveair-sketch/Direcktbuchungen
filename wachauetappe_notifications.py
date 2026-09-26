"""Transactional email and reminder workflow for WachauEtappe."""
from __future__ import annotations

import os
import smtplib
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage


def init_wachauetappe_notifications(app, db):
    if app.extensions.get("wachauetappe_notifications_initialized"):
        return
    app.extensions["wachauetappe_notifications_initialized"] = True

    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS wachauetappe_notification_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          booking_reference TEXT NOT NULL,
          event TEXT NOT NULL,
          recipient TEXT NOT NULL,
          status TEXT NOT NULL,
          detail TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          UNIQUE(booking_reference,event,recipient)
        )""")

    def now():
        return datetime.now().isoformat(timespec="seconds")

    def settings():
        cfg={}
        try:
            with db() as conn:
                cfg={r["key"]:r["value"] for r in conn.execute("SELECT key,value FROM site_settings")}
        except Exception:
            pass
        return cfg

    def smtp_send(to, subject, body):
        cfg=settings()
        host=(cfg.get("smtp_host") or os.environ.get("SMTP_HOST") or "").strip()
        user=(cfg.get("smtp_user") or os.environ.get("SMTP_USER") or "").strip()
        password=(cfg.get("smtp_password") or os.environ.get("SMTP_PASSWORD") or "").strip()
        sender=(cfg.get("smtp_sender") or os.environ.get("SMTP_SENDER") or user).strip()
        try:
            port=int(cfg.get("smtp_port") or os.environ.get("SMTP_PORT") or 587)
        except Exception:
            port=587
        if not host or not user or not password or not sender or not to:
            return False,"smtp_not_configured"
        msg=EmailMessage()
        msg["From"]=sender;msg["To"]=to;msg["Subject"]=subject;msg.set_content(body)
        try:
            with smtplib.SMTP(host,port,timeout=20) as server:
                server.starttls();server.login(user,password);server.send_message(msg)
            return True,"sent"
        except Exception as exc:
            return False,str(exc)[:300]

    def logged(reference,event,recipient):
        with db() as conn:
            return bool(conn.execute("SELECT 1 FROM wachauetappe_notification_log WHERE booking_reference=? AND event=? AND lower(recipient)=lower(?) AND status='sent'",(reference,event,recipient)).fetchone())

    def record(reference,event,recipient,ok,detail):
        try:
            with db() as conn:
                conn.execute("""INSERT INTO wachauetappe_notification_log(booking_reference,event,recipient,status,detail,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(booking_reference,event,recipient) DO UPDATE SET status=excluded.status,detail=excluded.detail,created_at=excluded.created_at""",
                (reference,event,recipient,"sent" if ok else "error",detail,now()))
        except Exception:
            pass

    def booking(reference):
        with db() as conn:
            return conn.execute("""SELECT b.*,p.name AS host_name,p.location AS host_location,p.email AS host_email
            FROM wachauetappe_guest_bookings b
            LEFT JOIN wachauetappe_partner_accounts p ON p.host_id=b.host_id
            WHERE b.reference=?""",(reference,)).fetchone()

    def deliver(reference,event,recipient,subject,body):
        if not recipient or logged(reference,event,recipient):
            return False
        ok,detail=smtp_send(recipient,subject,body)
        record(reference,event,recipient,ok,detail)
        return ok

    def notify_new(reference):
        b=booking(reference)
        if not b:return False
        host=b["host_name"] or b["host_id"]
        host_body=(
            f"Neue WachauEtappe-Anfrage\n\n"
            f"Referenz: {b['reference']}\nGast: {b['guest_name']}\n"
            f"Datum: {b['stay_date']}\nPersonen: {b['guests']}\n"
            f"Preis laut Anfrage: {('%.2f EUR' % b['price']) if b['price'] is not None else 'noch offen'}\n"
            f"Telefon: {b['guest_phone'] or '–'}\nE-Mail: {b['guest_email']}\n"
            f"Nachricht: {b['note'] or 'keine'}\n\n"
            "Bitte im WachauEtappe-Partnerportal bestätigen oder ablehnen. "
            "Offene Anfragen werden nach 12 Stunden als fällig markiert."
        )
        guest_body=(
            f"Hallo {b['guest_name']},\n\n"
            f"deine Anfrage an {host} für {b['stay_date']} ist eingegangen.\n"
            f"Referenz: {b['reference']}\n\n"
            "Dies ist noch keine Buchungsbestätigung. Der Gastgeber prüft die Anfrage persönlich. "
            "Unterkunftsvertrag und Zahlung erfolgen direkt mit dem Gastgeber.\n\n"
            "Herzliche Grüße\nWachauEtappe"
        )
        a=deliver(reference,"new_host",b["host_email"],f"Neue Gästeanfrage {b['reference']} – {b['stay_date']}",host_body)
        g=deliver(reference,"guest_received",b["guest_email"],f"Deine WachauEtappe-Anfrage {b['reference']} ist eingegangen",guest_body)
        return a or g

    def alternative_count(b):
        if not b["host_location"]:return 0
        try:
            with db() as conn:
                row=conn.execute("""SELECT COUNT(DISTINCT a.host_id) AS n
                FROM wachauetappe_partner_availability a
                JOIN wachauetappe_partner_accounts p ON p.host_id=a.host_id AND p.active=1
                WHERE lower(p.location)=lower(?) AND a.stay_date=? AND a.status='free' AND a.rooms_free>0
                  AND a.host_id<>?
                  AND NOT EXISTS(SELECT 1 FROM wachauetappe_partner_calendar_blocks x WHERE x.host_id=a.host_id AND x.stay_date=a.stay_date AND x.provider='booking')""",
                (b["host_location"],b["stay_date"],b["host_id"])).fetchone()
            return int(row["n"] or 0)
        except Exception:
            return 0

    def notify_status(reference,status):
        b=booking(reference)
        if not b:return False
        host=b["host_name"] or b["host_id"]
        if status=="confirmed":
            subject=f"Bestätigt: {host} · {b['stay_date']}"
            body=(
                f"Hallo {b['guest_name']},\n\n"
                f"{host} hat deine Anfrage für {b['stay_date']} bestätigt.\n"
                f"Referenz: {b['reference']}\n"
                f"Personen: {b['guests']}\n"
                f"Preis: {('%.2f EUR' % b['price']) if b['price'] is not None else 'wird direkt vom Gastgeber bestätigt'}\n\n"
                "Die weitere Vertrags- und Zahlungsabwicklung erfolgt direkt mit dem Gastgeber.\n\n"
                "Herzliche Grüße\nWachauEtappe"
            )
            return deliver(reference,"guest_confirmed",b["guest_email"],subject,body)
        if status=="declined":
            n=alternative_count(b)
            alt=(f"Aktuell sind für Ort und Datum {n} weitere Partneroption(en) mit freiem Kontingent gemeldet. Öffne deinen Reiseplaner und wähle eine Alternative." if n else "Aktuell ist keine weitere Partnerunterkunft mit freiem Kontingent für genau diese Nacht gemeldet. Du kannst eine persönliche Alternativanfrage senden.")
            subject=f"Unterkunft nicht verfügbar: {host} · {b['stay_date']}"
            body=(
                f"Hallo {b['guest_name']},\n\n"
                f"{host} kann deine Anfrage für {b['stay_date']} leider nicht bestätigen.\n"
                f"Referenz: {b['reference']}\n\n{alt}\n\n"
                "Herzliche Grüße\nWachauEtappe"
            )
            return deliver(reference,"guest_declined",b["guest_email"],subject,body)
        return False

    def send_due_reminders():
        cutoff=(datetime.now()-timedelta(hours=12)).isoformat(timespec="seconds")
        with db() as conn:
            rows=conn.execute("""SELECT b.reference,p.email AS host_email,p.name AS host_name,b.stay_date,b.guest_name
            FROM wachauetappe_guest_bookings b
            JOIN wachauetappe_partner_accounts p ON p.host_id=b.host_id AND p.active=1
            WHERE b.status='requested' AND b.created_at<=?
            ORDER BY b.created_at LIMIT 50""",(cutoff,)).fetchall()
        sent=0
        for r in rows:
            recipient=r["host_email"]
            if not recipient or logged(r["reference"],"host_reminder_12h",recipient):continue
            body=(
                f"Offene WachauEtappe-Anfrage\n\nReferenz: {r['reference']}\n"
                f"Datum: {r['stay_date']}\nGast: {r['guest_name']}\n\n"
                "Diese Anfrage wartet seit mindestens 12 Stunden auf eine Antwort. "
                "Bitte im Partnerportal bestätigen oder ablehnen."
            )
            if deliver(r["reference"],"host_reminder_12h",recipient,f"Erinnerung: offene Anfrage {r['reference']}",body):sent+=1
        return sent

    app.extensions["wachauetappe_notify_new_booking"]=notify_new
    app.extensions["wachauetappe_notify_booking_status"]=notify_status
    app.extensions["wachauetappe_send_due_reminders"]=send_due_reminders

    def loop():
        time.sleep(75)
        while True:
            try:send_due_reminders()
            except Exception:pass
            time.sleep(3600)

    if os.environ.get("WERKZEUG_RUN_MAIN")=="true" or not app.debug:
        threading.Thread(target=loop,daemon=True,name="wachauetappe-reminders").start()

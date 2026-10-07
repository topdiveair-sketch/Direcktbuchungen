"""Direct bank bookings: confirmed immediately, unpaid room holds expire in 48h."""
from datetime import datetime, timedelta, timezone
import threading
from transactional_email import send_transactional_email

PAYMENT_HOURS = 48


def bank_payment_deadline():
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=PAYMENT_HOURS)).isoformat(timespec='seconds')


def init_bank_booking(app, db, *, start_worker=True):
    def release_unpaid():
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
        with db() as conn:
            rows = conn.execute("""SELECT * FROM bookings WHERE status='confirmed'
                AND payment_method='Banküberweisung' AND COALESCE(paid,0)=0
                AND bank_payment_due_at!='' AND bank_payment_due_at<=?""", (now,)).fetchall()
            if not rows:
                return 0
            released = []
            for row in rows:
                cur = conn.execute("""UPDATE bookings SET status='cancelled', cancelled_at=?
                    WHERE id=? AND status='confirmed' AND COALESCE(paid,0)=0
                    AND bank_payment_due_at!='' AND bank_payment_due_at<=?""", (now,row['id'],now))
                if cur.rowcount:
                    released.append(dict(row))
        # Notifications run only after the release transaction has committed.
        for row in released:
            cfg = app.extensions.get('zab_bank_settings', lambda: {})()
            body = (f"Buchung ZAB-{row['id']:06d}, {row['arrival']} bis {row['departure']}: "
                    "Die Zahlungsfrist ist abgelaufen und es ist kein Zahlungseingang im System vermerkt. "
                    "Die Reservierung wurde aufgehoben und das Zimmer wieder freigegeben. "
                    "Falls bereits überwiesen wurde, kontaktiere bitte umgehend Zuhause am Bach.")
            recipients = {row['email'], cfg.get('email','')}
            for recipient in recipients - {''}:
                try:
                    queue = app.extensions.get('zab_queue_transactional_mail')
                    if queue:
                        role = 'bank_expired_guest' if recipient == row['email'] else 'bank_expired_owner'
                        queue(row['id'], role, recipient, 'Zahlungsfrist abgelaufen – Zuhause am Bach', body)
                    else:
                        ok, _ = send_transactional_email(recipient, 'Zahlungsfrist abgelaufen – Zuhause am Bach', body, settings=cfg, important=True)
                        if not ok:
                            app.logger.error('bank_expiry_mail_failed booking_id=%s', row['id'])
                except Exception:
                    app.logger.exception('bank_expiry_mail_failed booking_id=%s',row['id'])
        return len(released)

    @app.before_request
    def cleanup_bank_bookings():
        release_unpaid()

    app.extensions['zab_release_unpaid_bank_bookings'] = release_unpaid

    if start_worker:
        def worker():
            while True:
                threading.Event().wait(60)
                try:
                    release_unpaid()
                except Exception:
                    app.logger.exception('bank_expiry_cleanup_failed')
        threading.Thread(target=worker, name='bank-payment-expiry', daemon=True).start()

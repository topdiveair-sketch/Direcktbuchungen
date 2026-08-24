from __future__ import annotations

from datetime import datetime, timedelta


HOLD_MINUTES = 30


def init_payment_hold(app, db):
    """Add a 30-minute payment hold to pending direct bookings.

    Pending, unpaid bookings block availability only until their hold expires.
    The cleanup is intentionally request-driven, so it works with the existing
    single-process Railway deployment without an additional scheduler.
    """

    def ensure_column(conn, table, column, definition):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    with db() as conn:
        ensure_column(conn, "bookings", "hold_expires_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "released_at", "TEXT DEFAULT ''")
        ensure_column(conn, "bookings", "release_reason", "TEXT DEFAULT ''")

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
                       release_reason='Zahlungsfrist von 30 Minuten abgelaufen'
                   WHERE status='pending'
                     AND COALESCE(paid,0)=0
                     AND COALESCE(hold_expires_at,'')!=''
                     AND hold_expires_at<=?""",
                (now_iso, now_iso),
            )
            return cur.rowcount

    @app.before_request
    def cleanup_expired_payment_holds():
        release_expired()

    app.extensions["zab_start_payment_hold"] = start_hold
    app.extensions["zab_release_expired_holds"] = release_expired

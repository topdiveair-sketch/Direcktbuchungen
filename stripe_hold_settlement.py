"""Transactional release of Stripe holds after verified unpaid session expiry."""
from datetime import datetime
from stripe_hold_release import may_release_stripe_hold


def release_verified_stripe_hold(conn, session: dict, *, now: datetime) -> str:
    """Return released, retained, missing or duplicate; caller supplies SQLite conn."""
    session_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(session_id, str) or not session_id.startswith("cs_test_"):
        return "retained"
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM bookings WHERE stripe_session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            conn.rollback()
            return "missing"
        booking = dict(row)
        if booking["status"] == "cancelled":
            conn.rollback()
            return "duplicate"
        if not may_release_stripe_hold(session, booking, now=now):
            conn.rollback()
            return "retained"
        result = conn.execute(
            """UPDATE bookings SET status='cancelled', released_at=?,
                      release_reason='Stripe-Sitzung abgelaufen und unbezahlt',
                      hold_expires_at=''
               WHERE id=? AND status='pending' AND COALESCE(paid,0)=0
                 AND payment_method='stripe_checkout' AND stripe_session_id=?""",
            (now.replace(tzinfo=None).isoformat(timespec="seconds"),
             booking["id"], session_id),
        )
        if result.rowcount != 1:
            conn.rollback()
            return "retained"
        conn.commit()
        return "released"
    except Exception:
        conn.rollback()
        raise

"""Atomically settle a verified Stripe Checkout session in the booking database.

Caller MUST first verify Stripe's raw webhook signature. No browser redirect
may invoke this function. Transactions serialize payment-state transitions.
"""
from datetime import datetime

from stripe_booking_verification import verify_paid_checkout_session


def settle_verified_stripe_session(conn, session: dict) -> str:
    """Return confirmed, duplicate or rejected; transaction is caller-managed."""
    booking_ref = session.get("client_reference_id")
    try:
        booking_id = int(booking_ref)
    except (TypeError, ValueError):
        return "rejected"
    if booking_id <= 0:
        return "rejected"
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if row is None:
            conn.rollback()
            return "rejected"
        booking = dict(row)
        if (session.get("livemode") is False
                and booking.get("payment_method") == "stripe_checkout"
                and booking.get("status") == "confirmed" and int(booking.get("paid") or 0) == 1
                and booking.get("stripe_session_id") == session.get("id")
                and booking.get("stripe_payment_intent") == session.get("payment_intent")):
            conn.commit()
            return "duplicate"
        try:
            payment_intent = verify_paid_checkout_session(session, booking)
        except (ValueError, TypeError):
            conn.rollback()
            return "rejected"
        paid_at = datetime.now().isoformat(timespec="seconds")
        cursor = conn.execute(
            """UPDATE bookings
               SET status='confirmed', paid=1, paid_at=?,
                   stripe_payment_intent=?, hold_expires_at='',
                   payment_error='', released_at='', release_reason=''
               WHERE id=? AND status='pending' AND COALESCE(paid,0)=0
                 AND payment_method='stripe_checkout' AND stripe_session_id=?""",
            (paid_at, payment_intent, booking_id, session["id"]),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "rejected"
        conn.commit()
        return "confirmed"
    except Exception:
        conn.rollback()
        raise

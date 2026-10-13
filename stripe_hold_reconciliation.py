"""Reconcile Stripe test holds against Stripe's authoritative Checkout API.

Do not infer expiry from local clocks alone. Paid sessions can also be
recovered if the webhook was delayed. A Stripe API error must never
release inventory. Designed for explicit admin/worker invocation.
"""
from datetime import datetime, timezone

from stripe_session_lookup import retrieve_test_checkout_session
from stripe_hold_settlement import release_verified_stripe_hold
from stripe_booking_settlement import settle_verified_stripe_session


def reconcile_expired_stripe_holds(db, *, secret_key: str,
                                   now: datetime | None = None,
                                   limit: int = 20, lookup=None) -> dict:
    if not secret_key.startswith("sk_test_"):
        raise ValueError("Stripe sandbox secret required")
    if not 1 <= limit <= 100:
        raise ValueError("Invalid reconciliation batch size")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    # Read candidates without holding a write transaction over network calls.
    with db() as conn:
        rows = conn.execute(
            """SELECT id,stripe_session_id FROM bookings
               WHERE payment_method='stripe_checkout' AND status='pending'
                 AND COALESCE(paid,0)=0
                 AND COALESCE(stripe_session_id,'')!=''
               ORDER BY id LIMIT ?""",
            (limit,),
        ).fetchall()
    results = {"checked": 0, "released": 0, "confirmed": 0, "retained": 0,
               "failed": 0, "missing": 0}
    for row in rows:
        session_id = row["stripe_session_id"]
        try:
            session = (lookup or retrieve_test_checkout_session)(
                secret_key=secret_key, session_id=session_id
            )
            results["checked"] += 1
            if session.get("livemode") is False and session.get("status") == "complete" and session.get("payment_status") == "paid":
                with db() as conn:
                    outcome = settle_verified_stripe_session(conn, session)
                if outcome == "confirmed":
                    results["confirmed"] += 1
                elif outcome != "duplicate":
                    results["failed"] += 1
                continue
            with db() as conn:
                outcome = release_verified_stripe_hold(conn, session, now=now)
            if outcome == "released":
                results["released"] += 1
            elif outcome == "missing":
                results["missing"] += 1
            else:
                results["retained"] += 1
        except Exception:
            # Failed lookups are never treated as unpaid sessions.
            results["failed"] += 1
    return results

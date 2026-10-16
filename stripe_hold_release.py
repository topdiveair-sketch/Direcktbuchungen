"""Fail-closed policy for releasing a Stripe-backed room reservation.

Never release a pending booking based solely on a browser cancel redirect,
a local timer or an unverified Checkout response.
"""
from datetime import datetime, timedelta, timezone


class StripeReleaseUnsafe(ValueError):
    pass


def may_release_stripe_hold(session: dict, booking: dict, *, now: datetime,
                            grace_minutes: int = 15) -> bool:
    """Only an expired, unpaid, matching sandbox session may free a room."""
    if now.tzinfo is None:
        raise StripeReleaseUnsafe("Timezone-aware clock required")
    if grace_minutes < 5:
        raise StripeReleaseUnsafe("Insufficient webhook grace period")
    if booking.get("payment_method") != "stripe_checkout":
        return False
    if booking.get("status") != "pending" or int(booking.get("paid") or 0):
        return False
    if not booking.get("stripe_session_id"):
        return False
    if session.get("livemode") is not False:
        return False
    if session.get("id") != booking["stripe_session_id"]:
        return False
    if session.get("status") != "expired" or session.get("payment_status") != "unpaid":
        return False
    if session.get("payment_intent"):
        return False
    if str(session.get("client_reference_id")) != str(booking.get("id")):
        return False
    try:
        expires_at = datetime.fromtimestamp(int(session["expires_at"]), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return now.astimezone(timezone.utc) >= expires_at + timedelta(minutes=grace_minutes)

"""Guard against unsafe Stripe Checkout retries.

A Checkout creation with an uncertain response must be reviewed manually
until the exact original request payload (including expires_at) is persisted.
Changing expires_at on retry violates Stripe idempotency semantics.
"""


def recovery_requires_manual_review(booking: dict) -> bool:
    """Fail closed for a pending booking without an attached session."""
    return (
        booking.get("payment_method") == "stripe_checkout"
        and booking.get("status") == "pending"
        and not bool(booking.get("paid"))
        and not str(booking.get("stripe_session_id") or "").strip()
    )

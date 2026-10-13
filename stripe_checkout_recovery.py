"""Look up an ambiguous Stripe Checkout creation using its idempotency key.

Only sandbox keys. Stripe may return the original session when a POST with
identical parameters and idempotency key is repeated; do not blindly create
another booking or another session.
"""
from stripe_checkout_client import create_hosted_checkout_session


def recover_test_checkout_session(*, secret_key, booking_id, total_eur,
                                  guest_email, success_url, cancel_url,
                                  opener=None):
    """Replay exactly the original Stripe request with the same booking ID."""
    if not str(secret_key).startswith("sk_test_"):
        raise ValueError("Stripe sandbox key required")
    if not isinstance(booking_id, int) or booking_id <= 0:
        raise ValueError("Valid booking ID required")
    return create_hosted_checkout_session(
        secret_key=secret_key, booking_id=booking_id, total_eur=total_eur,
        guest_email=guest_email, success_url=success_url,
        cancel_url=cancel_url, opener=opener)

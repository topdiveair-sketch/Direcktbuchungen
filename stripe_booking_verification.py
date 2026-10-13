"""Validate a paid Stripe Checkout session against an immutable local booking.

Only a verified webhook may supply the Stripe session data. This validator
does not itself mark bookings as paid or release inventory.
"""
from decimal import Decimal, InvalidOperation


class StripeBookingMismatch(ValueError):
    pass


def verify_paid_checkout_session(session: dict, booking: dict) -> str:
    """Return the PaymentIntent ID only when the exact booking was paid in EUR."""
    try:
        expected_cents = int((Decimal(str(booking["total"])) * 100).to_integral_exact())
        actual_cents = int(session["amount_total"])
        booking_id = str(booking["id"])
    except (KeyError, ValueError, TypeError, InvalidOperation, ArithmeticError) as exc:
        raise StripeBookingMismatch("Invalid amount or booking reference") from exc
    payment_intent = str(session.get("payment_intent") or "")
    if (
        booking.get("payment_method") != "stripe_checkout"
        or booking.get("status") != "pending"
        or int(booking.get("paid") or 0) != 0
        or session.get("mode") != "payment"
        or session.get("status") != "complete"
        or session.get("payment_status") != "paid"
        or session.get("currency") != "eur"
        or str(session.get("client_reference_id")) != booking_id
        or str((session.get("metadata") or {}).get("booking_id")) != booking_id
        or actual_cents != expected_cents
        or expected_cents <= 0
        or not payment_intent.startswith("pi_")
        or not str(session.get("id") or "").startswith("cs_test_")
        or str(booking.get("stripe_session_id") or "") != str(session.get("id"))
    ):
        raise StripeBookingMismatch("Stripe payment does not match the pending booking")
    return payment_intent

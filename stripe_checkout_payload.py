"""Server-side Stripe Checkout session payload construction.

This module does not activate payments or reserve rooms. Call only after
calendar synchronization, transactional availability check and local hold.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode


class CheckoutValidationError(ValueError):
    pass


def checkout_session_fields(*, booking_id: int, total_eur, guest_email: str,
                            success_url: str, cancel_url: str) -> dict:
    """Create form fields for Stripe's hosted Checkout API."""
    try:
        amount = Decimal(str(total_eur))
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CheckoutValidationError("Invalid booking total") from exc
    if cents < 50 or cents > 99999999:
        raise CheckoutValidationError("Booking amount outside allowed range")
    if not isinstance(booking_id, int) or booking_id < 1:
        raise CheckoutValidationError("Invalid booking ID")
    if not guest_email or "@" not in guest_email:
        raise CheckoutValidationError("Guest email required")
    if not success_url.startswith("https://") or not cancel_url.startswith("https://"):
        raise CheckoutValidationError("HTTPS redirect URLs required")
    return {
        "mode": "payment",
        "payment_method_types[0]": "card",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(cents),
        "line_items[0][price_data][product_data][name]": "Zuhause am Bach - Zimmerbuchung",
        "line_items[0][quantity]": "1",
        "client_reference_id": str(booking_id),
        "metadata[booking_id]": str(booking_id),
        "customer_email": guest_email,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }


def encoded_checkout_fields(**kwargs) -> bytes:
    return urlencode(checkout_session_fields(**kwargs)).encode("ascii")

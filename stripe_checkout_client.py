"""Stripe hosted Checkout API transport.

Never log the secret key, raw guest payment details or Authorization header.
This module deliberately does not mutate reservations or activate a payment route.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from stripe_checkout_payload import checkout_session_fields


class StripeCheckoutError(RuntimeError):
    pass


def create_hosted_checkout_session(*, secret_key: str, booking_id: int,
                                   total_eur, guest_email: str,
                                   success_url: str, cancel_url: str,
                                   timeout: int = 20, opener=None) -> dict:
    """Request a hosted card-payment session with a server-calculated amount."""
    if not secret_key or not secret_key.startswith("sk_test_"):
        raise StripeCheckoutError("Only Stripe sandbox credentials are allowed")
    fields = checkout_session_fields(
        booking_id=booking_id, total_eur=total_eur, guest_email=guest_email,
        success_url=success_url, cancel_url=cancel_url,
    )
    request = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=urlencode(fields).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + secret_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": "zab-checkout-" + str(booking_id),
        },
        method="POST",
    )
    transport = opener or urllib.request.urlopen
    try:
        with transport(request, timeout=timeout) as response:
            session = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
        raise StripeCheckoutError("Stripe checkout session creation failed") from exc
    if (not isinstance(session, dict)
            or session.get("mode") != "payment"
            or session.get("client_reference_id") != str(booking_id)
            or not str(session.get("id", "")).startswith("cs_test_")
            or not str(session.get("url", "")).startswith("https://checkout.stripe.com/")):
        raise StripeCheckoutError("Stripe returned an invalid sandbox checkout session")
    return {"id": session["id"], "url": session["url"]}

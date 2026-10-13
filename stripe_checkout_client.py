"""Stripe hosted Checkout API transport.

Never log the secret key, raw guest payment details or Authorization header.
This module deliberately does not mutate reservations or activate a payment route.
"""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

from stripe_checkout_payload import checkout_session_fields


class StripeCheckoutError(RuntimeError):
    pass


def create_hosted_checkout_session(*, secret_key: str, booking_id: int,
                                   total_eur, guest_email: str,
                                   success_url: str, cancel_url: str,
                                   timeout: int = 20, opener=None, expires_at: int | None = None) -> dict:
    """Request a hosted card-payment session with a server-calculated amount."""
    if not secret_key or not secret_key.startswith("sk_test_"):
        raise StripeCheckoutError("Only Stripe sandbox credentials are allowed")
    fields = checkout_session_fields(
        booking_id=booking_id, total_eur=total_eur, guest_email=guest_email,
        success_url=success_url, cancel_url=cancel_url,
    )
    # Give Stripe a full 30-minute minimum even after request transit and rounding.
    # Local inventory release still requires authoritative session reconciliation.
    expiry = int(time.time()) + 31 * 60 if expires_at is None else expires_at
    if not isinstance(expiry, int) or isinstance(expiry, bool):
        raise StripeCheckoutError("Invalid Stripe checkout expiry")
    fields["expires_at"] = str(expiry)
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
    except urllib.error.HTTPError as exc:
        # Retain only allowlisted Stripe diagnostics; do not log payment data.
        stripe_code = "unknown"
        stripe_param = "unknown"
        try:
            payload = json.loads(exc.read(8192).decode("utf-8"))
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(error, dict):
                code = error.get("code") or error.get("type")
                param = error.get("param")
                if isinstance(code, str) and code.replace("_", "").isalnum() and len(code) <= 64:
                    stripe_code = code
                if isinstance(param, str) and len(param) <= 120 and all(ch.isalnum() or ch in "_[]" for ch in param):
                    stripe_param = param
        except (ValueError, UnicodeError, OSError):
            pass
        raise StripeCheckoutError(
            f"Stripe checkout rejected: HTTP {exc.code}, code={stripe_code}, param={stripe_param}"
        ) from None
    except (urllib.error.URLError, ValueError) as exc:
        raise StripeCheckoutError("Stripe checkout transport or response error") from exc
    if (not isinstance(session, dict)
            or session.get("mode") != "payment"
            or session.get("client_reference_id") != str(booking_id)
            or not str(session.get("id", "")).startswith("cs_test_")
            or not str(session.get("url", "")).startswith("https://checkout.stripe.com/")):
        raise StripeCheckoutError("Stripe returned an invalid sandbox checkout session")
    return {"id": session["id"], "url": session["url"]}

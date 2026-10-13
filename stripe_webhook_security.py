"""Stripe webhook signature verification, independent of payment activation.

Do not accept browser redirects as payment proof. The signed raw webhook body
must be verified before any future booking-status mutation.
"""
import hashlib
import hmac
import time


class StripeSignatureError(ValueError):
    """Missing, invalid or stale Stripe webhook signature."""


def verify_stripe_signature(payload: bytes, signature_header: str, secret: str, *,
                            now: int | None = None, tolerance: int = 300) -> None:
    """Verify Stripe-Signature (t=...,v1=...) against the unmodified raw body."""
    if not isinstance(payload, bytes) or not secret:
        raise StripeSignatureError("Raw payload or webhook secret missing")
    fields = {}
    for field in (signature_header or "").split(","):
        key, sep, value = field.strip().partition("=")
        if sep and key in ("t", "v1"):
            fields.setdefault(key, []).append(value)
    try:
        timestamp = int(fields["t"][0])
    except (KeyError, ValueError, IndexError) as exc:
        raise StripeSignatureError("Missing or invalid timestamp") from exc
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > tolerance:
        raise StripeSignatureError("Webhook timestamp outside tolerance")
    signed = str(timestamp).encode("ascii") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in fields.get("v1", [])):
        raise StripeSignatureError("Invalid webhook signature")

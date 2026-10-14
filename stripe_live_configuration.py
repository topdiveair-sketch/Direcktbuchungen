"""Fail-closed configuration gate for a future dedicated Stripe live webhook.

This module DOES NOT register a Flask route, accept events, or enable payments.
The live endpoint must use a different signing secret and must never run in the
Stripe sandbox service. Payment settlement still requires a signed webhook,
a matching persisted booking, and authoritative availability protections.
"""
import os


class StripeLiveConfigurationError(ValueError):
    pass


def validate_live_webhook_configuration(env=None):
    cfg = os.environ if env is None else env
    if cfg.get("ZAB_STRIPE_ISOLATED_TEST") == "1":
        raise StripeLiveConfigurationError("Sandbox service cannot enable live webhook")
    if cfg.get("STRIPE_LIVE_WEBHOOK_ENABLED") != "1":
        raise StripeLiveConfigurationError("Live webhook disabled")
    if cfg.get("STRIPE_LIVE_BOOKING_INTEGRATION_VERIFIED") != "1":
        raise StripeLiveConfigurationError("Production booking integration not verified")
    live_key = (cfg.get("STRIPE_LIVE_SECRET_KEY") or "").strip()
    signing_secret = (cfg.get("STRIPE_LIVE_WEBHOOK_SECRET") or "").strip()
    test_signing_secret = (cfg.get("STRIPE_TEST_WEBHOOK_SECRET") or "").strip()
    if not live_key.startswith("sk_live_"):
        raise StripeLiveConfigurationError("Stripe live API key not configured")
    if not signing_secret.startswith("whsec_") or signing_secret == test_signing_secret:
        raise StripeLiveConfigurationError("Dedicated Stripe live signing secret required")
    return signing_secret

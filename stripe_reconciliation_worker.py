"""Opt-in background Stripe sandbox reconciliation.

Disabled by default. Intended for one dedicated worker process, not each web
worker. Errors never trigger release without authoritative Stripe verification.
"""
import logging
import os
import threading

from stripe_hold_reconciliation import reconcile_expired_stripe_holds

_LOG = logging.getLogger(__name__)
_started = False
_guard = threading.Lock()


def start_stripe_reconciliation_worker(db, *, interval_seconds=300):
    """Start only when explicitly configured in a dedicated sandbox worker."""
    global _started
    if os.environ.get("STRIPE_SANDBOX_RECONCILE_WORKER") != "1":
        return False
    if os.environ.get("STRIPE_SANDBOX_CHECKOUT_ENABLED") != "1":
        return False
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith("sk_test_"):
        return False
    if interval_seconds < 60:
        raise ValueError("Reconciliation interval must be at least 60 seconds")
    with _guard:
        if _started:
            return False
        _started = True

    def loop():
        while True:
            # Delay initial run so database startup and schema migration finish.
            if threading.Event().wait(interval_seconds):
                return
            try:
                result = reconcile_expired_stripe_holds(
                    db, secret_key=key, limit=20)
                _LOG.info("Stripe sandbox reconciliation: %s", result)
            except Exception:
                _LOG.exception("Stripe sandbox reconciliation failed; holds retained")

    threading.Thread(target=loop, daemon=True, name="stripe-sandbox-reconcile").start()
    return True

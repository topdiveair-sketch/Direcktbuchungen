"""Dedicated Stripe sandbox reconciliation worker entrypoint.

Run as a single separate Railway worker service after the same app database
migrations have completed. Never start this inside a web worker.
"""
import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stripe-reconcile")


def main():
    if os.environ.get("STRIPE_SANDBOX_RECONCILE_WORKER") != "1":
        raise SystemExit("Stripe sandbox reconciliation worker is disabled")
    if os.environ.get("STRIPE_SANDBOX_CHECKOUT_ENABLED") != "1":
        raise SystemExit("Stripe sandbox checkout is disabled")
    secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret.startswith("sk_test_"):
        raise SystemExit("Only Stripe test keys are permitted")

    from app import db, init_db
    from stripe_hold_reconciliation import reconcile_expired_stripe_holds

    init_db()
    interval = int(os.environ.get("STRIPE_RECONCILE_INTERVAL_SECONDS", "300"))
    if interval < 60:
        raise SystemExit("Interval must be at least 60 seconds")
    log.info("Stripe sandbox reconciliation worker started")
    while True:
        time.sleep(interval)
        try:
            report = reconcile_expired_stripe_holds(db, secret_key=secret, limit=20)
            log.info("Stripe sandbox reconciliation: %s", report)
        except Exception:
            log.exception("Stripe reconciliation failed; inventory retained")


if __name__ == "__main__":
    main()

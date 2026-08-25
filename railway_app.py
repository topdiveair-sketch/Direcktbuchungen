"""Railway entrypoint with booking hold cleanup, PayPal checkout and health check."""

import base64
import json
import os
import urllib.error
import urllib.request

from app import (
    app,
    db,
    ROOMS,
    parse_date,
    price_breakdown,
    room_available_in_conn,
    sync_room,
)
from payment_hold import init_payment_hold
from paypal_checkout import init_paypal_checkout


# Bump this marker when Railway must rebuild after PayPal checkout module changes.
PAYPAL_CHECKOUT_DEPLOY_REV = "2026-08-25-minimal-orders-v2"

PUBLIC_BACHBLICK_NIGHTLY_PRICE = float(
    os.environ.get("PUBLIC_BACHBLICK_NIGHTLY_PRICE", "101.00")
)


def direct_checkout_price_breakdown(room, arrival, departure, adults, chosen, coupon_code=""):
    """Return the price that is actually published on the direct-booking page.

    Bachblick is currently the only released room on GitHub Pages. The public
    page advertises 101 EUR/night and calculates extras separately. PayPal must
    therefore use exactly the same room price and must not silently apply the
    backend's legacy direct-booking/last-minute discounts.
    """
    breakdown = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)
    if room != "Bachblick":
        return breakdown

    nights = max(0, (departure - arrival).days)
    room_total = round(PUBLIC_BACHBLICK_NIGHTLY_PRICE * nights, 2)
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )
    return {
        **breakdown,
        "room_total": room_total,
        "discounts": [],
        "total": round(room_total + extras_total, 2),
    }


init_payment_hold(app, db)
init_paypal_checkout(
    app,
    db,
    ROOMS,
    parse_date,
    direct_checkout_price_breakdown,
    room_available_in_conn,
    sync_room,
)


@app.get("/health/deploy")
def railway_deploy_health():
    """Return the exact Railway/PayPal checkout revision currently running."""
    return {
        "status": "ok",
        "paypal_checkout": bool(app.extensions.get("zab_paypal_checkout_enabled")),
        "paypal_checkout_rev": PAYPAL_CHECKOUT_DEPLOY_REV,
    }, 200


@app.get("/health/paypal")
def paypal_health():
    """Verify PayPal credentials without creating an order or exposing secrets."""
    environment = os.environ.get("PAYPAL_ENV", "live").strip().lower()
    client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
    secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return {
            "ok": False,
            "environment": environment,
            "reason": "credentials_missing",
        }, 503

    api_base = (
        "https://api-m.sandbox.paypal.com"
        if environment == "sandbox"
        else "https://api-m.paypal.com"
    )
    auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        api_base + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Accept-Language": "de_AT",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("access_token"):
            return {
                "ok": False,
                "environment": environment,
                "reason": "token_missing",
            }, 502
        return {
            "ok": True,
            "environment": environment,
            "credentials": "accepted",
        }, 200
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "environment": environment,
            "reason": "paypal_rejected_credentials" if exc.code == 401 else "paypal_http_error",
            "paypal_status": exc.code,
        }, 503
    except Exception:
        return {
            "ok": False,
            "environment": environment,
            "reason": "paypal_unreachable",
        }, 503

"""Railway entrypoint with booking hold cleanup, PayPal checkout and health check."""

import os

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


@app.get("/health")
def railway_health():
    """Return 200 when the Flask process is ready to accept requests."""
    return {
        "status": "ok",
        "paypal_checkout": bool(app.extensions.get("zab_paypal_checkout_enabled")),
    }, 200

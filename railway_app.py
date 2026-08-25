"""Railway entrypoint with booking hold cleanup, PayPal checkout and health check."""

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


init_payment_hold(app, db)
init_paypal_checkout(
    app,
    db,
    ROOMS,
    parse_date,
    price_breakdown,
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

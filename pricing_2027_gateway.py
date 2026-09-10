"""Direct-booking pricing bridge from 14 September 2026 through 2027.

This module activates the configured nightly rate calendar before Railway imports
the checkout stack. It keeps public price quotes, booking storage and PayPal
checkout on the same price source while preserving legacy pricing outside the
configured active window.
"""

from __future__ import annotations

from datetime import timedelta

import app as legacy_app
import paypal_checkout as paypal_checkout_module
from pricing_2027 import nightly_direct_rate

_original_price_breakdown = legacy_app.price_breakdown
_original_init_paypal_checkout = paypal_checkout_module.init_paypal_checkout


def price_breakdown_2027(room, arrival, departure, adults, chosen, coupon_code=""):
    breakdown = _original_price_breakdown(
        room, arrival, departure, adults, chosen, coupon_code
    )

    if room != "Bachblick" or departure <= arrival:
        return breakdown

    current = arrival
    room_total = 0.0
    while current < departure:
        nightly = nightly_direct_rate(current)
        if nightly is None:
            return breakdown
        room_total += float(nightly)
        current += timedelta(days=1)

    # Configured rates are FINAL DIRECT RATES. Legacy percentage discounts are
    # not stacked on top, so the 99 EUR floor remains a real guest price floor.
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )

    return {
        **breakdown,
        "room_total": round(room_total, 2),
        "discounts": [],
        "total": round(room_total + extras_total, 2),
        "pricing_model": "direct-event-calendar-2026-2027",
    }


def _init_paypal_checkout_2027(
    app,
    db,
    rooms,
    parse_date,
    _legacy_direct_checkout_price_breakdown,
    room_available_in_conn,
    sync_room,
):
    """Ensure PayPal uses the same dynamic direct price as the booking API."""
    return _original_init_paypal_checkout(
        app,
        db,
        rooms,
        parse_date,
        price_breakdown_2027,
        room_available_in_conn,
        sync_room,
    )


legacy_app.price_breakdown = price_breakdown_2027
legacy_app.calculate_total = lambda room, arrival, departure, adults, breakfast: price_breakdown_2027(
    room,
    arrival,
    departure,
    adults,
    {"breakfast": breakfast},
)["total"]
paypal_checkout_module.init_paypal_checkout = _init_paypal_checkout_2027

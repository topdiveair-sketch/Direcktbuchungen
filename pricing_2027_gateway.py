"""2027 direct-booking pricing bridge.

This module activates the 2027 nightly rate calendar before Railway imports the
checkout stack. It keeps public price quotes, booking storage and PayPal checkout
on the same price source while preserving the legacy pricing model outside 2027.
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

    # The 2027 calendar governs the directly marketed Bachblick room. Other
    # rooms and dates outside 2027 retain the application's existing pricing.
    if room != "Bachblick" or arrival.year != 2027 or departure <= arrival:
        return breakdown

    current = arrival
    room_total = 0.0
    while current < departure:
        nightly = nightly_direct_rate(current)
        if nightly is None:
            return breakdown
        room_total += float(nightly)
        current += timedelta(days=1)

    # Rates in pricing-2027.json are FINAL DIRECT RATES. Legacy percentage
    # discounts are not stacked on top, otherwise the 99 EUR floor could fall
    # below 99 EUR (for example through the old 3% direct-booking discount).
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )

    return {
        **breakdown,
        "room_total": round(room_total, 2),
        "discounts": [],
        "total": round(room_total + extras_total, 2),
        "pricing_model": "direct-2027-event-calendar",
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
    """Ensure PayPal uses the same dynamic 2027 price as the booking API.

    railway_app historically replaces Bachblick with one fixed nightly price.
    Supplying price_breakdown_2027 here removes that divergence for checkout.
    """
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

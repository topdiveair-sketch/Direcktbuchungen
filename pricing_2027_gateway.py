"""2027 direct-booking pricing bridge.

This module patches app.price_breakdown before Railway imports the checkout
stack. That keeps the public availability/price API, booking storage and PayPal
checkout on the same nightly-rate source without rewriting the legacy app.
"""

from __future__ import annotations

from datetime import timedelta

import app as legacy_app
from pricing_2027 import nightly_direct_rate

_original_price_breakdown = legacy_app.price_breakdown


def price_breakdown_2027(room, arrival, departure, adults, chosen, coupon_code=""):
    breakdown = _original_price_breakdown(
        room, arrival, departure, adults, chosen, coupon_code
    )

    # The 2027 calendar currently governs the directly marketed Bachblick room.
    # Other rooms and all dates outside 2027 retain the existing pricing system.
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

    # 2027 JSON rates are FINAL DIRECT RATES. Existing percentage discounts are
    # intentionally not stacked on top, otherwise a 99 EUR floor could become
    # 96.03 EUR through the legacy 3% direct-booking discount.
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


legacy_app.price_breakdown = price_breakdown_2027
legacy_app.calculate_total = lambda room, arrival, departure, adults, breakfast: price_breakdown_2027(
    room,
    arrival,
    departure,
    adults,
    {"breakfast": breakfast},
)["total"]

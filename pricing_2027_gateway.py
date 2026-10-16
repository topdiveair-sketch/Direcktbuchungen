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
from pricing_2027 import nightly_direct_rate, quiet_night_rate

_original_price_breakdown = legacy_app.price_breakdown
_original_init_paypal_checkout = paypal_checkout_module.init_paypal_checkout


def effective_direct_rate(room, day, fallback):
    """Resolve the final direct rate, preserving explicit OS calendar prices."""
    try:
        central = legacy_app.central_override_for_day(room, day)
        if central.get("price") not in (None, ""):
            return round(float(central["price"]), 2), True
    except Exception:
        pass

    getter = legacy_app.app.extensions.get("zab_channel_price_for_day")
    if not callable(getter):
        return float(fallback), False
    try:
        value = getter(room, "direct", day, fallback)
    except Exception:
        return float(fallback), False
    if value is None:
        return float(fallback), False
    if isinstance(value, tuple) and len(value) == 2:
        amount, is_manual = value
        return round(float(amount), 2), bool(is_manual)
    amount = round(float(value), 2)
    return amount, amount != round(float(fallback), 2)


def price_breakdown_2027(room, arrival, departure, adults, chosen, coupon_code=""):
    breakdown = _original_price_breakdown(
        room, arrival, departure, adults, chosen, coupon_code
    )

    if room != "Bachblick" or departure <= arrival:
        return breakdown

    current = arrival
    room_total = 0.0
    override_used = False
    while current < departure:
        nightly = nightly_direct_rate(current)
        if nightly is None:
            return breakdown
        # Match the public quote and OS feed: central calendar prices win,
        # then explicit channel overrides, then the configured revenue rate.
        fallback = float(legacy_app.direct_nightly_price_for_day(room, current))
        effective, manual_override = effective_direct_rate(room, current, fallback)
        quiet = quiet_night_rate(current)
        if quiet is not None and not manual_override:
            effective = quiet
        override_used = override_used or manual_override
        room_total += effective
        current += timedelta(days=1)

    # Configured rates and explicit OS calendar prices are FINAL DIRECT RATES.
    # Legacy percentage discounts are not stacked on top.
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )

    return {
        **breakdown,
        "room_total": round(room_total, 2),
        "discounts": [],
        "total": round(room_total + extras_total, 2),
        "pricing_model": (
            "zab-os-calendar-override"
            if override_used
            else "direct-event-calendar-2026-2027"
        ),
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

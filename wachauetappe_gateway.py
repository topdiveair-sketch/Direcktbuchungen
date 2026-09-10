"""Unified Railway entrypoint for WachauEtappe production.

All operational APIs share the same Flask app and Railway database:
- direct booking / existing site backend
- guest booking gateway
- partner portal / availability
- central live state for Windows
- existing growth/winter/ProjectOS endpoints
"""

from datetime import date

# Load the dynamic direct-pricing bridge before the Railway/app stack. This
# patches the shared pricing and PayPal checkout hooks for the configured
# 14.09.2026-31.12.2027 pricing window while preserving legacy pricing outside it.
import pricing_2027_gateway  # noqa: F401,E402
from pricing_2027 import nightly_direct_rate

# projectos_winter_gateway initializes the central live-state gateway on the
# shared Flask app. Import it once and do not register those routes twice.
from projectos_winter_gateway import app  # noqa: F401,E402

# Importing these modules registers their routes on that same app instance.
import guest_booking_gateway  # noqa: F401,E402
import partner_portal_gateway  # noqa: F401,E402


def _has_live_state_route() -> bool:
    return any(rule.rule == "/api/central/live-state" for rule in app.url_map.iter_rules())


def _pricing_self_check() -> tuple[bool, dict[str, float | None]]:
    rates = {
        "2026-09-14": nightly_direct_rate(date(2026, 9, 14)),
        "2026-09-18": nightly_direct_rate(date(2026, 9, 18)),
        "2027-01-04": nightly_direct_rate(date(2027, 1, 4)),
    }
    expected = {
        "2026-09-14": 119.0,
        "2026-09-18": 149.0,
        "2027-01-04": 99.0,
    }
    return rates == expected, rates


@app.get("/health/wachauetappe_production")
def wachauetappe_production_health():
    live_ok = _has_live_state_route()
    pricing_ok, pricing_rates = _pricing_self_check()
    ok = live_ok and pricing_ok
    return {
        "ok": ok,
        "gateway": "wachauetappe_gateway",
        "guest_bookings": True,
        "partner_portal": True,
        "live_central_state": live_ok,
        "dynamic_direct_pricing": pricing_ok,
        "pricing_rates": pricing_rates,
    }, 200 if ok else 503


# Keep the older human-readable health URL too.
@app.get("/health/wachauetappe-production")
def wachauetappe_production_health_legacy():
    return wachauetappe_production_health()

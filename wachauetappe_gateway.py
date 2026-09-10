"""Unified Railway entrypoint for WachauEtappe production.

All operational APIs share the same Flask app and Railway database:
- direct booking / existing site backend
- guest booking gateway
- partner portal / availability
- central live state for Windows
- existing growth/winter/ProjectOS endpoints
"""

# projectos_winter_gateway already initializes the central live-state gateway on
# the shared Flask app. Import it once and do not register those routes twice.
from projectos_winter_gateway import app  # noqa: F401

# Importing these modules registers their routes on that same app instance.
import guest_booking_gateway  # noqa: F401,E402
import partner_portal_gateway  # noqa: F401,E402


def _has_live_state_route() -> bool:
    return any(rule.rule == "/api/central/live-state" for rule in app.url_map.iter_rules())


@app.get("/health/wachauetappe_production")
def wachauetappe_production_health():
    live_ok = _has_live_state_route()
    return {
        "ok": live_ok,
        "gateway": "wachauetappe_gateway",
        "guest_bookings": True,
        "partner_portal": True,
        "live_central_state": live_ok,
    }, 200 if live_ok else 503

# Keep the older human-readable health URL too.
@app.get("/health/wachauetappe-production")
def wachauetappe_production_health_legacy():
    return wachauetappe_production_health()

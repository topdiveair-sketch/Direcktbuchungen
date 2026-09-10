"""Unified Railway entrypoint for WachauEtappe production.

All operational APIs share the same Flask app and Railway database:
- direct booking / existing site backend
- guest booking gateway
- partner portal / availability
- central live state for Windows
- existing growth/winter/ProjectOS endpoints
"""

# Import the broad existing gateway chain first. It resolves to the single Flask
# app instance created in railway_app/app.py.
from projectos_winter_gateway import app  # noqa: F401

# Importing these modules registers their routes on that same app instance.
import guest_booking_gateway  # noqa: F401,E402
import partner_portal_gateway  # noqa: F401,E402


@app.get("/health/wachauetappe-production")
def wachauetappe_production_health():
    return {
        "ok": True,
        "gateway": "wachauetappe_gateway",
        "guest_bookings": True,
        "partner_portal": True,
        "live_central_state": True,
    }, 200

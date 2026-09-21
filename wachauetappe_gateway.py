"""Unified Railway entrypoint for WachauEtappe production.

All operational APIs share the same Flask app and Railway database:
- direct booking / existing site backend
- guest booking gateway
- partner portal / availability
- central live state for Windows
- existing growth/winter/ProjectOS endpoints
- privacy-light demand and conversion analytics for ZAB OS
"""

import hmac
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from flask import request

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
import app as legacy_app  # noqa: E402
from demand_analytics import init_demand_analytics  # noqa: E402
from master_calendar_desktop_api import init_master_calendar_desktop_api  # noqa: E402
from booking_connectivity import init_booking_connectivity  # noqa: E402
from booking_guest_sync import init_booking_guest_sync  # noqa: E402
from zab_control_center_v3 import init_zab_control_center_v3  # noqa: E402

init_demand_analytics(app, legacy_app.db, legacy_app.require_admin)

PUBLIC_SITE_ORIGIN = "https://topdiveair-sketch.github.io"
PUBLIC_CALENDAR_SNAPSHOT_URL = os.environ.get(
    "ZAB_PUBLIC_CALENDAR_JSON_URL",
    "https://raw.githubusercontent.com/topdiveair-sketch/Direcktbuchungen/main/booking-calendar.json",
).strip()
LIVE_SAFETY_ICAL_URL = os.environ.get(
    "ZAB_LIVE_SAFETY_ICAL_URL",
    "https://web-production-907d68.up.railway.app/calendar/public/Bachblick.ics",
).strip()
PUBLIC_CALENDAR_MAX_AGE_SECONDS = max(
    60,
    min(int(os.environ.get("ZAB_PUBLIC_CALENDAR_MAX_AGE_SECONDS", "900")), 3600),
)


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": PUBLIC_SITE_ORIGIN,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Cache-Control",
        "Cache-Control": "no-store",
    }


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


def _desktop_admin_ok() -> bool:
    expected = os.environ.get("ADMIN_PASSWORD", "")
    supplied = request.headers.get("X-Admin-Password", "")
    if not expected or not supplied:
        return False
    return hmac.compare_digest(str(expected), str(supplied))


# RAINsoft CENTRAL uses the same DPAPI-protected Railway admin credential as
# the existing demand dashboard. Only non-sensitive calendar data is returned.
init_master_calendar_desktop_api(
    app,
    legacy_app.db,
    legacy_app.ROOMS,
    _desktop_admin_ok,
    nightly_direct_rate,
)

# V3 is the Windows-first Zuhause-am-Bach control center. It keeps the old
# desktop endpoint for compatibility while adding guest operations, additional
# channels and Booking.com rate push support.
init_booking_connectivity(app)
init_zab_control_center_v3(
    app,
    legacy_app.db,
    legacy_app.ROOMS,
    _desktop_admin_ok,
    nightly_direct_rate,
)
# Booking reservation details are private enrichment data only. They are
# matched to Booking iCal blocks and never exported through public ICS feeds.
init_booking_guest_sync(app, legacy_app.db, _desktop_admin_ok)


def _effective_direct_rate(room: str, day: date, fallback: float) -> tuple[float, bool]:
    getter = app.extensions.get("zab_channel_price_for_day")
    if not callable(getter):
        return fallback, False
    try:
        value = getter(room, "direct", day, fallback)
    except Exception:
        return fallback, False
    if value is None:
        return fallback, False
    value = float(value)
    return value, value != fallback


def _dates_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start < b_end and b_start < a_end


def _parse_snapshot_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_ical_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if len(raw) < 8:
        return None
    raw = raw[:8]
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except (TypeError, ValueError):
        return None


def _live_calendar_safety_check(room: str, arrival: date, departure: date):
    """Check the authoritative live ZAB calendar before using a static snapshot.

    The public ICS feed is served directly by the production ZAB OS with
    Cache-Control: no-store. This removes GitHub Actions freshness from the
    critical direct-booking path while preserving fail-closed behaviour.
    """
    if room != "Bachblick" or not LIVE_SAFETY_ICAL_URL:
        return None, "Der Live-Sicherheitskalender ist nicht konfiguriert."

    separator = "&" if "?" in LIVE_SAFETY_ICAL_URL else "?"
    url = f"{LIVE_SAFETY_ICAL_URL}{separator}_zab={int(datetime.now(timezone.utc).timestamp())}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Zuhause-am-Bach-Direct-Booking-Safety/1.0",
            "Accept": "text/calendar,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, f"Der Live-Sicherheitskalender konnte nicht geprüft werden: {exc}"

    if "BEGIN:VCALENDAR" not in text:
        return None, "Der Live-Sicherheitskalender hat ungültige Daten geliefert."

    unfolded = text.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")
    for block in unfolded.split("BEGIN:VEVENT")[1:]:
        start = None
        end = None
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if line.startswith("DTSTART"):
                start = _parse_ical_date(line.split(":", 1)[-1])
            elif line.startswith("DTEND"):
                end = _parse_ical_date(line.split(":", 1)[-1])
        if start and end and end > start and _dates_overlap(arrival, departure, start, end):
            return False, "Das Gartenblick Zimmer ist im Live-Sicherheitskalender bereits belegt oder geschlossen."

    return True, "Der Live-Sicherheitskalender ist aktuell und ohne Konflikt."


def _public_calendar_safety_check(room: str, arrival: date, departure: date):
    """Preserve known Booking conflicts, while using live ZAB state for stale positives.

    A Booking conflict from the public hybrid snapshot remains authoritative
    even after the snapshot freshness window expires. If the snapshot is fresh
    and conflict-free, it can positively confirm availability. If it is stale,
    the live ZAB ICS feed must also confirm the period before pricing proceeds.
    """
    if room != "Bachblick" or not PUBLIC_CALENDAR_SNAPSHOT_URL:
        return _live_calendar_safety_check(room, arrival, departure)

    separator = "&" if "?" in PUBLIC_CALENDAR_SNAPSHOT_URL else "?"
    url = f"{PUBLIC_CALENDAR_SNAPSHOT_URL}{separator}_zab={int(datetime.now(timezone.utc).timestamp())}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Zuhause-am-Bach-Direct-Booking-Safety/1.1",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )

    payload = None
    snapshot_error = ""
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        snapshot_error = str(exc)

    if isinstance(payload, dict):
        events = payload.get("events")
        updated = _parse_snapshot_timestamp(payload.get("updatedAtIso", ""))
        if isinstance(events, list):
            # Known Booking/master conflicts must never disappear merely because
            # the snapshot became old.
            for event in events:
                if not isinstance(event, dict):
                    continue
                try:
                    start = date.fromisoformat(str(event.get("start", "")))
                    end = date.fromisoformat(str(event.get("end", "")))
                except ValueError:
                    continue
                if end > start and _dates_overlap(arrival, departure, start, end):
                    return False, "Das Gartenblick Zimmer ist in diesem Zeitraum bereits belegt oder geschlossen."

            if updated is not None:
                age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
                if -300 <= age_seconds <= PUBLIC_CALENDAR_MAX_AGE_SECONDS:
                    return True, "ZAB- und Booking-Sicherheitskalender sind aktuell und ohne Konflikt."

    live_available, live_message = _live_calendar_safety_check(room, arrival, departure)
    if live_available is not None:
        return live_available, live_message

    if snapshot_error:
        return None, f"Booking-Snapshot nicht erreichbar ({snapshot_error}); {live_message}"
    return None, f"Booking-Snapshot nicht aktuell genug; {live_message}"


def _master_direct_availability(room: str, arrival: date, departure: date):
    checker = app.extensions.get("zab_master_room_available")
    if not callable(checker):
        return None, "Der ZAB-Masterkalender ist nicht verfügbar."
    release_expired = app.extensions.get("zab_release_expired_holds")
    if callable(release_expired):
        try:
            release_expired()
        except Exception:
            pass
    try:
        with legacy_app.db() as conn:
            available, message = checker(conn, room, arrival, departure, "direct")
        return bool(available), str(message or "")
    except Exception as exc:
        return None, f"Der ZAB-Masterkalender konnte nicht geprüft werden: {exc}"


@app.route("/api/direct-booking-calendar", methods=["GET", "OPTIONS"])
def public_direct_booking_calendar():
    """Fresh public calendar for the static direct-booking frontend."""
    if request.method == "OPTIONS":
        return "", 204, _cors_headers()

    separator = "&" if "?" in LIVE_SAFETY_ICAL_URL else "?"
    url = f"{LIVE_SAFETY_ICAL_URL}{separator}_zab={int(datetime.now(timezone.utc).timestamp())}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Zuhause-am-Bach-Direct-Booking-Calendar/1.0",
            "Accept": "text/calendar,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {
            "ok": False,
            "error": "live_calendar_unavailable",
            "message": f"Der Live-Sicherheitskalender konnte nicht geladen werden: {exc}",
        }, 503, _cors_headers()

    if "BEGIN:VCALENDAR" not in text:
        return {
            "ok": False,
            "error": "invalid_live_calendar",
            "message": "Der Live-Sicherheitskalender hat ungültige Daten geliefert.",
        }, 503, _cors_headers()

    unfolded = text.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")
    events = []
    for block in unfolded.split("BEGIN:VEVENT")[1:]:
        start = None
        end = None
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if line.startswith("DTSTART"):
                start = _parse_ical_date(line.split(":", 1)[-1])
            elif line.startswith("DTEND"):
                end = _parse_ical_date(line.split(":", 1)[-1])
        if start and end and end > start:
            events.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": "CLOSED - Not available",
                "source": "ZAB OS Master-Kalender live",
            })

    now = datetime.now(timezone.utc)
    return {
        "ok": True,
        "room": "Bachblick",
        "roomDisplayName": "Gartenblick Zimmer",
        "source": "ZAB OS Master-Kalender live",
        "events": events,
        "updatedAt": now.astimezone().strftime("%d.%m.%Y %H:%M:%S"),
        "updatedAtIso": now.isoformat().replace("+00:00", "Z"),
    }, 200, _cors_headers()


@app.route("/api/direct-price", methods=["GET", "OPTIONS"])
def public_direct_price():
    """Public, date-aware room quote used by the static GitHub Pages frontend."""
    if request.method == "OPTIONS":
        return "", 204, _cors_headers()

    room = (request.args.get("room") or "Bachblick").strip()
    if room != "Bachblick":
        return {"ok": False, "available": False, "error": "unsupported_room"}, 400, _cors_headers()

    try:
        arrival = date.fromisoformat(request.args.get("arrival", ""))
        departure = date.fromisoformat(request.args.get("departure", ""))
    except ValueError:
        return {"ok": False, "available": False, "error": "invalid_dates"}, 400, _cors_headers()

    if departure <= arrival:
        return {"ok": False, "available": False, "error": "departure_must_be_after_arrival"}, 400, _cors_headers()
    if (departure - arrival).days > 30:
        return {"ok": False, "available": False, "error": "stay_too_long"}, 400, _cors_headers()

    master_available, master_message = _master_direct_availability(room, arrival, departure)
    if master_available is None:
        return {
            "ok": False,
            "available": False,
            "error": "master_availability_unavailable",
            "message": master_message,
        }, 503, _cors_headers()
    if not master_available:
        return {
            "ok": False,
            "available": False,
            "error": "unavailable",
            "message": master_message,
        }, 409, _cors_headers()

    safety_available, safety_message = _public_calendar_safety_check(room, arrival, departure)
    if safety_available is None:
        return {
            "ok": False,
            "available": False,
            "error": "booking_safety_check_unavailable",
            "message": safety_message,
        }, 503, _cors_headers()
    if not safety_available:
        return {
            "ok": False,
            "available": False,
            "error": "unavailable",
            "message": safety_message,
        }, 409, _cors_headers()

    nights = []
    current = arrival
    total = 0.0
    override_used = False
    while current < departure:
        rate = nightly_direct_rate(current)
        if rate is None:
            return {"ok": False, "available": False, "error": "date_outside_pricing_calendar"}, 400, _cors_headers()
        fallback = float(rate)
        rate, overridden = _effective_direct_rate(room, current, fallback)
        override_used = override_used or overridden
        nights.append({"date": current.isoformat(), "price_eur": rate, "os_override": overridden})
        total += rate
        current += timedelta(days=1)

    return {
        "ok": True,
        "available": True,
        "room": room,
        "room_display_name": "Gartenblick Zimmer",
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "night_count": len(nights),
        "room_total_eur": round(total, 2),
        "average_nightly_eur": round(total / len(nights), 2),
        "nights": nights,
        "currency": "EUR",
        "availability_source": "zab-master+booking-safety-snapshot",
        "pricing_model": (
            "zab-os-calendar-override"
            if override_used
            else "direct-event-calendar-2026-2027"
        ),
    }, 200, _cors_headers()


@app.get("/api/central/demand-summary")
def central_demand_summary():
    """Authenticated JSON funnel summary for RAINsoft CENTRAL desktop clients."""
    if not _desktop_admin_ok():
        return {"ok": False, "error": "unauthorized"}, 401
    summary = app.extensions.get("zab_demand_analytics_summary")
    if not callable(summary):
        return {"ok": False, "error": "analytics_unavailable"}, 503
    try:
        days = max(1, min(int(request.args.get("days", "30")), 3650))
    except (TypeError, ValueError):
        days = 30
    payload = dict(summary(days))
    payload["ok"] = True
    payload["source"] = "zab-demand-analytics"
    return payload, 200, {"Cache-Control": "no-store"}


@app.get("/health/wachauetappe_production")
def wachauetappe_production_health():
    live_ok = _has_live_state_route()
    pricing_ok, pricing_rates = _pricing_self_check()
    price_api_ok = any(rule.rule == "/api/direct-price" for rule in app.url_map.iter_rules())
    analytics_ok = any(rule.rule == "/api/demand-event" for rule in app.url_map.iter_rules())
    os_analytics_ok = any(rule.rule == "/os/nachfrage" for rule in app.url_map.iter_rules())
    central_demand_ok = any(rule.rule == "/api/central/demand-summary" for rule in app.url_map.iter_rules())
    master_calendar_ok = bool(app.extensions.get("zab_master_calendar_initialized"))
    desktop_calendar_api_ok = bool(app.extensions.get("zab_master_calendar_desktop_api"))
    control_center_v3_ok = bool(app.extensions.get("zab_control_center_v3"))
    booking_connectivity_ok = bool(app.extensions.get("zab_booking_connectivity_initialized"))
    booking_guest_sync_ok = bool(app.extensions.get("zab_booking_guest_sync_initialized"))
    ok = (
        live_ok and pricing_ok and price_api_ok and analytics_ok and os_analytics_ok
        and central_demand_ok and master_calendar_ok and desktop_calendar_api_ok
        and control_center_v3_ok and booking_connectivity_ok and booking_guest_sync_ok
    )
    return {
        "ok": ok,
        "gateway": "wachauetappe_gateway",
        "guest_bookings": True,
        "partner_portal": True,
        "live_central_state": live_ok,
        "dynamic_direct_pricing": pricing_ok,
        "public_direct_price_api": price_api_ok,
        "public_direct_price_fail_closed": True,
        "demand_analytics_api": analytics_ok,
        "zab_os_demand_dashboard": os_analytics_ok,
        "rainsoft_central_demand_api": central_demand_ok,
        "master_calendar": master_calendar_ok,
        "rainsoft_central_master_calendar_api": desktop_calendar_api_ok,
        "zab_control_center_v3": control_center_v3_ok,
        "booking_connectivity_adapter": booking_connectivity_ok,
        "booking_guest_sync": booking_guest_sync_ok,
        "pricing_rates": pricing_rates,
    }, 200 if ok else 503


# Keep the older human-readable health URL too.
@app.get("/health/wachauetappe-production")
def wachauetappe_production_health_legacy():
    return wachauetappe_production_health()


# SEO, browser metadata and baseline security hardening for the public site.
from flask import Response

_CANONICAL_ORIGIN = "https://www.zuhauseambach-wachau.at"

@app.get("/robots.txt")
def public_robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        f"Sitemap: {_CANONICAL_ORIGIN}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain"), 200, {"Cache-Control": "public, max-age=3600"}

@app.get("/sitemap.xml")
def public_sitemap():
    urls = ["/", "/legal/impressum", "/legal/datenschutz", "/legal/agb"]
    entries = "".join(
        f"<url><loc>{_CANONICAL_ORIGIN}{path}</loc></url>" for path in urls
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries +
        "</urlset>"
    )
    return Response(body, mimetype="application/xml"), 200, {"Cache-Control": "public, max-age=3600"}

@app.get("/favicon.ico")
def public_favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#f2eadc"/>
<path d="M12 31 32 14l20 17v21H39V38H25v14H12z" fill="#4d5b45"/>
<path d="M25 52V38h14v14" fill="#fffaf2"/>
</svg>"""
    return Response(svg, mimetype="image/svg+xml"), 200, {"Cache-Control": "public, max-age=86400"}

@app.after_request
def public_security_and_seo_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.path.startswith("/admin"):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
        response.headers.setdefault("Cache-Control", "no-store")
    elif request.path in {"/", "/legal/impressum", "/legal/datenschutz", "/legal/agb"}:
        canonical = _CANONICAL_ORIGIN + request.path
        response.headers.setdefault("Link", f'<{canonical}>; rel="canonical"')
    return response

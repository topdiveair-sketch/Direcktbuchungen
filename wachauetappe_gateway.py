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
# These routes intentionally live on the production gateway so they are served
# by the same canonical www host as the booking application.
from flask import Response, redirect, render_template

PUBLIC_HOME_TRANSLATIONS = json.loads((legacy_app.BASE / "translations" / "public_home.json").read_text(encoding="utf-8"))

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
    urls = [
        ("/", "daily", "1.0"),
        ("/unterkunft-wachau", "weekly", "1.0"),
        ("/unterkunft-welterbesteig-wachau", "weekly", "0.9"),
        ("/unterkunft-donauradweg-wachau", "weekly", "0.9"),
        ("/uebernachten-aggsbach-markt", "weekly", "0.9"),
        ("/radfahrer-unterkunft-wachau", "weekly", "0.9"),
        ("/unterkunft-jauerling-wachau", "weekly", "0.95"),
        ("/skifahren-jauerling-unterkunft-wachau", "weekly", "0.9"),
        ("/en/", "weekly", "0.8"),
        ("/cs/", "weekly", "0.8"),
        ("/sk/", "weekly", "0.8"),
        ("/hu/", "weekly", "0.8"),
        ("/es/", "weekly", "0.8"),
        ("/fr/", "weekly", "0.8"),
        ("/legal/impressum", "monthly", "0.3"),
        ("/legal/datenschutz", "monthly", "0.3"),
        ("/legal/agb", "monthly", "0.3"),
    ]
    today = date.today().isoformat()
    entries = "".join(
        f"<url><loc>{_CANONICAL_ORIGIN}{path}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>{freq}</changefreq><priority>{priority}</priority></url>"
        for path, freq, priority in urls
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries +
        "</urlset>"
    )
    return Response(body, mimetype="application/xml"), 200, {"Cache-Control": "public, max-age=3600"}

def _seo_landing(**kwargs):
    kwargs.setdefault("faq", [])
    return render_template("seo_landing.html", **kwargs)



@app.get("/unterkunft-wachau")
def seo_unterkunft_wachau():
    return _seo_landing(
        title="Unterkunft Wachau direkt buchen | Zuhause am Bach Aggsbach",
        description="Unterkunft in der Wachau direkt beim Gastgeber buchen: ruhiges Privatzimmer in Aggsbach Markt für Donauradweg, Welterbesteig und E-Bike. Verfügbarkeit und Preis direkt prüfen.",
        canonical=_CANONICAL_ORIGIN + "/unterkunft-wachau",
        h1="Unterkunft in der Wachau direkt beim Gastgeber",
        lead="Ruhiges Privatzimmer in Aggsbach Markt für Donauradweg, Welterbesteig und entspannte Wachau-Tage.",
        eyebrow="Unterkunft Wachau · Direktbuchung",
        subheading="Persönlich übernachten statt über ein Buchungsportal",
        paragraphs=[
            "Zuhause am Bach ist eine kleine persönlich geführte Unterkunft in Aggsbach Markt in der Wachau. Das Gartenzimmer ist für maximal zwei Personen ausgelegt und kann direkt über die offizielle Website angefragt beziehungsweise gebucht werden.",
            "Besonders passend ist die Unterkunft für Radfahrer am Donauradweg, Wanderer am Welterbesteig und Gäste, die eine ruhige Übernachtung mit direktem Kontakt zu den Gastgebern suchen.",
            "Freie Termine, aktuelle Preise und Zusatzleistungen wie Frühstück, Wachauer Jause oder Gepäcktransport werden direkt auf der offiziellen Website angezeigt.",
        ],
        features=[
            ("🏡","Persönliche Unterkunft","Kleines Gästehaus mit direktem Kontakt zu den Gastgebern."),
            ("🚲","Donauradweg","Fahrradunterbringung und E-Bike-Lademöglichkeit für Radreisende."),
            ("🥾","Welterbesteig","Geeignet als ruhiger Etappenstopp in der Wachau."),
            ("💶","Direkt buchen","Verfügbarkeit und Preis ohne Umweg über ein Buchungsportal prüfen."),
        ],
        faq=[
            {"@type":"Question","name":"Kann ich Zuhause am Bach direkt buchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Verfügbarkeit und Preis können direkt auf der offiziellen Website von Zuhause am Bach geprüft werden."}},
            {"@type":"Question","name":"Ist die Unterkunft für Radfahrer am Donauradweg geeignet?","acceptedAnswer":{"@type":"Answer","text":"Ja. Die Unterkunft nennt Fahrradunterbringung und E-Bike-Lademöglichkeit als Leistungen für Gäste."}},
            {"@type":"Question","name":"Ist Frühstück verfügbar?","acceptedAnswer":{"@type":"Answer","text":"Frühstück kann auf Wunsch als Zusatzleistung gewählt werden."}},
            {"@type":"Question","name":"Wo liegt Zuhause am Bach?","acceptedAnswer":{"@type":"Answer","text":"Zuhause am Bach liegt in Aggsbach Markt 82, 3641 Aggsbach Markt, in der Wachau in Niederösterreich."}},
        ],
    )


@app.get("/unterkunft-welterbesteig-wachau")
def seo_welterbesteig():
    return _seo_landing(
        title="Unterkunft am Welterbesteig Wachau | Zuhause am Bach",
        description="Unterkunft in Aggsbach Markt für Wanderer am Welterbesteig Wachau. Ruhiges Gartenzimmer, Frühstück auf Wunsch und Direktbuchung bei Zuhause am Bach.",
        canonical=_CANONICAL_ORIGIN + "/unterkunft-welterbesteig-wachau",
        h1="Unterkunft am Welterbesteig Wachau",
        lead="Ruhig übernachten in Aggsbach Markt und die nächste Wachau-Etappe entspannt beginnen.",
        eyebrow="Welterbesteig Wachau",
        subheading="Ein persönlicher Ausgangspunkt für Wanderer",
        paragraphs=[
            "Zuhause am Bach liegt in Aggsbach Markt und richtet sich an Gäste, die die Wachau zu Fuß erleben möchten.",
            "Das Gartenzimmer ist direkt über die offizielle Website anfragbar. Frühstück ist auf Wunsch möglich; aktuelle freie Termine zeigt der Live-Kalender.",
        ],
        faq=[
            {"@type":"Question","name":"Ist Zuhause am Bach für den Welterbesteig geeignet?","acceptedAnswer":{"@type":"Answer","text":"Die Unterkunft in Aggsbach Markt richtet sich ausdrücklich auch an Wanderer am Welterbesteig Wachau."}},
            {"@type":"Question","name":"Kann ich Frühstück dazubuchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Frühstück ist auf Wunsch als Zusatzleistung verfügbar."}},
            {"@type":"Question","name":"Wo prüfe ich freie Termine?","acceptedAnswer":{"@type":"Answer","text":"Freie Termine und Preise werden im Live-Buchungsbereich der offiziellen Website angezeigt."}},
        ],
        features=[
            ("🥾","Für Wanderer","Passend für die Planung von Etappen am Welterbesteig."),
            ("🍳","Frühstück auf Wunsch","Für einen unkomplizierten Start in den Wandertag."),
            ("📱","Gäste-App","Informationen und persönliche Tipps auf dem Smartphone."),
            ("⌖","Aggsbach Markt","Standort in der Wachau mit direktem Bezug zur Wanderregion."),
        ],
    )


@app.get("/unterkunft-donauradweg-wachau")
def seo_donauradweg():
    return _seo_landing(
        title="Unterkunft am Donauradweg Wachau | Zuhause am Bach",
        description="Unterkunft für Radfahrer am Donauradweg in Aggsbach Markt. Fahrradunterbringung, E-Bike-Lademöglichkeit und Direktbuchung bei Zuhause am Bach.",
        canonical=_CANONICAL_ORIGIN + "/unterkunft-donauradweg-wachau",
        h1="Unterkunft am Donauradweg in der Wachau",
        lead="Übernachten in Aggsbach Markt mit praktischen Leistungen für Radreisende.",
        eyebrow="Donauradweg Wachau",
        subheading="Für Radfahrer auf der Wachau-Etappe",
        paragraphs=[
            "Zuhause am Bach ist auf Gäste vorbereitet, die mit dem Fahrrad durch die Wachau reisen.",
            "Fahrradunterbringung und E-Bike-Lademöglichkeit gehören zu den auf der offiziellen Website ausgewiesenen Leistungen. Freie Termine und Preise werden direkt geprüft.",
        ],
        faq=[
            {"@type":"Question","name":"Kann ich mein Fahrrad sicher unterbringen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Die offizielle Website weist eine Fahrradunterbringung für Gäste aus."}},
            {"@type":"Question","name":"Kann ich ein E-Bike laden?","acceptedAnswer":{"@type":"Answer","text":"Ja. Eine E-Bike-Lademöglichkeit wird als Leistung der Unterkunft ausgewiesen."}},
            {"@type":"Question","name":"Kann ich direkt beim Gastgeber buchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Verfügbarkeit und Preis können direkt auf der offiziellen Website geprüft werden."}},
        ],
        features=[
            ("🚲","Fahrradunterbringung","Praktisch für Radreisende und Touren durch die Wachau."),
            ("⚡","E-Bike laden","Lademöglichkeit für E-Bikes vor Ort."),
            ("🍳","Frühstück auf Wunsch","Stärkung vor der nächsten Etappe."),
            ("📅","Live-Verfügbarkeit","Freie Termine direkt auf der offiziellen Website prüfen."),
        ],
    )


@app.get("/uebernachten-aggsbach-markt")
def seo_aggsbach():
    return _seo_landing(
        title="Übernachten in Aggsbach Markt | Unterkunft Wachau",
        description="Ruhig übernachten in Aggsbach Markt in der Wachau. Gartenzimmer bei Zuhause am Bach mit Direktbuchung, Frühstück auf Wunsch und persönlicher Betreuung.",
        canonical=_CANONICAL_ORIGIN + "/uebernachten-aggsbach-markt",
        h1="Übernachten in Aggsbach Markt",
        lead="Eine persönliche Unterkunft in der Wachau für Natur, Donau, Wandern und Radfahren.",
        eyebrow="Aggsbach Markt · Wachau",
        subheading="Ruhige Unterkunft mit persönlicher Atmosphäre",
        paragraphs=[
            "Zuhause am Bach befindet sich in Aggsbach Markt in Niederösterreich und bietet Gästen einen ruhigen Ausgangspunkt für Aufenthalte in der Wachau.",
            "Das Gartenzimmer kann direkt auf der offiziellen Website angefragt werden. Aktuelle Preise und freie Termine werden im Buchungsbereich angezeigt.",
        ],
        faq=[
            {"@type":"Question","name":"Wo liegt die Unterkunft in Aggsbach Markt?","acceptedAnswer":{"@type":"Answer","text":"Zuhause am Bach liegt in Aggsbach Markt 82, 3641 Aggsbach Markt."}},
            {"@type":"Question","name":"Wie viele Personen können im Gartenzimmer übernachten?","acceptedAnswer":{"@type":"Answer","text":"Das direkt angebotene Gartenzimmer ist für maximal zwei Personen vorgesehen."}},
            {"@type":"Question","name":"Kann ich online die Verfügbarkeit prüfen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Die offizielle Website zeigt einen Live-Kalender sowie den Direktbuchungsbereich."}},
        ],
        features=[
            ("🏡","Persönlich wohnen","Kleine Unterkunft statt anonymer Großbetrieb."),
            ("🥾","Wachau erwandern","Guter Ausgangspunkt für Wanderpläne in der Region."),
            ("🚲","Wachau erradeln","Geeignet für Radfahrer und E-Bikes."),
            ("💬","Direkter Kontakt","Buchungsanfrage ohne Umweg über ein Portal."),
        ],
    )


@app.get("/radfahrer-unterkunft-wachau")
def seo_radfahrer():
    return _seo_landing(
        title="Radfahrer-Unterkunft Wachau | Zuhause am Bach",
        description="Radfahrer-Unterkunft in der Wachau: Gartenzimmer in Aggsbach Markt mit Fahrradunterbringung, E-Bike-Lademöglichkeit und Direktbuchung.",
        canonical=_CANONICAL_ORIGIN + "/radfahrer-unterkunft-wachau",
        h1="Radfahrer-Unterkunft in der Wachau",
        lead="Für Radurlaub, Donauradweg und E-Bike-Touren rund um Aggsbach Markt.",
        eyebrow="Radurlaub Wachau",
        subheading="Praktisch für Radfahrer und E-Bikes",
        paragraphs=[
            "Bei Zuhause am Bach stehen die Bedürfnisse von Radreisenden sichtbar im Mittelpunkt.",
            "Die offizielle Website nennt Fahrradunterbringung und E-Bike-Lademöglichkeit. Das Gartenzimmer wird direkt angeboten; Verfügbarkeit und Preis sind online prüfbar.",
        ],
        faq=[
            {"@type":"Question","name":"Ist die Unterkunft für Radfahrer geeignet?","acceptedAnswer":{"@type":"Answer","text":"Ja. Fahrradunterbringung und E-Bike-Lademöglichkeit werden auf der offiziellen Website ausdrücklich genannt."}},
            {"@type":"Question","name":"Gibt es Frühstück für Radreisende?","acceptedAnswer":{"@type":"Answer","text":"Frühstück kann auf Wunsch zur Übernachtung gewählt werden."}},
            {"@type":"Question","name":"Wo kann ich direkt buchen?","acceptedAnswer":{"@type":"Answer","text":"Direkt auf www.zuhauseambach-wachau.at über den Bereich Verfügbarkeit und Preis."}},
        ],
        features=[
            ("🚲","Radfreundlich","Fahrradunterbringung für Gäste."),
            ("⚡","E-Bike","Lademöglichkeit während des Aufenthalts."),
            ("📍","Aggsbach Markt","Standort in der Wachau für weitere Radtouren."),
            ("💶","Direkt anfragen","Preis und Verfügbarkeit auf der offiziellen Website."),
        ],
    )




def _public_home_language(lang: str):
    if lang not in PUBLIC_HOME_TRANSLATIONS:
        return redirect(_CANONICAL_ORIGIN + "/", code=302)
    tr = PUBLIC_HOME_TRANSLATIONS[lang]
    canonical = _CANONICAL_ORIGIN + ("/" if lang == "de" else f"/{lang}/")
    return render_template(
        "public_home_i18n.html",
        tr=tr,
        lang=lang,
        languages=PUBLIC_HOME_TRANSLATIONS,
        canonical=canonical,
        origin=_CANONICAL_ORIGIN,
    )


@app.get("/en/")
def public_home_en():
    return _public_home_language("en")


@app.get("/cs/")
def public_home_cs():
    return _public_home_language("cs")


@app.get("/sk/")
def public_home_sk():
    return _public_home_language("sk")


@app.get("/hu/")
def public_home_hu():
    return _public_home_language("hu")


@app.get("/es/")
def public_home_es():
    return _public_home_language("es")


@app.get("/fr/")
def public_home_fr():
    return _public_home_language("fr")


@app.get("/unterkunft-jauerling-wachau")
def seo_jauerling():
    return _seo_landing(
        title="Unterkunft Jauerling Wachau | Zuhause am Bach",
        description="Unterkunft für Jauerling-Gäste in der Wachau: ruhig in Aggsbach Markt übernachten, Parkplatz, WLAN und Frühstück auf Wunsch. Direktpreis und Verfügbarkeit prüfen.",
        canonical=_CANONICAL_ORIGIN + "/unterkunft-jauerling-wachau",
        h1="Unterkunft am Jauerling in der Wachau",
        lead="Ruhig in Aggsbach Markt übernachten und den Jauerling mit Natur, Wandern oder Winteraktivitäten verbinden.",
        eyebrow="Jauerling · Wachau · Aggsbach Markt",
        subheading="Persönliche Unterkunft als Ausgangspunkt für den Jauerling",
        paragraphs=[
            "Zuhause am Bach in Aggsbach Markt ist eine kleine persönliche Unterkunft für Gäste, die einen Aufenthalt in der Wachau mit einem Ausflug zum Jauerling verbinden möchten.",
            "Das direkt angebotene Gartenzimmer ist für maximal zwei Personen vorgesehen. WLAN und Parkplatz gehören zur Unterkunft; Frühstück kann auf Wunsch ergänzt werden.",
            "Aktuelle Verfügbarkeit und Preise werden direkt auf der offiziellen Website geprüft. Für wetter- oder saisonabhängige Angebote am Jauerling sollten Gäste den jeweiligen Betreiber vor der Anreise prüfen.",
            "Die Unterkunft eignet sich damit sowohl für Wander- und Naturtage als auch für winterliche Aufenthalte in der Region.",
        ],
        features=[
            ("🏔️","Jauerling","Ausgangspunkt für Natur, Wandern und saisonale Aktivitäten rund um den Jauerling."),
            ("🛏️","Für zwei Gäste","Ruhiges Gartenzimmer für maximal zwei Personen."),
            ("🍳","Frühstück auf Wunsch","Optional zur Übernachtung buchbar."),
            ("💶","Direktpreis","Preis und freie Termine direkt bei Zuhause am Bach prüfen."),
        ],
        faq=[
            {"@type":"Question","name":"Welche Unterkunft eignet sich für einen Besuch am Jauerling?","acceptedAnswer":{"@type":"Answer","text":"Zuhause am Bach in Aggsbach Markt bietet ein ruhiges Gartenzimmer für maximal zwei Gäste und kann als Ausgangspunkt für Ausflüge zum Jauerling genutzt werden."}},
            {"@type":"Question","name":"Kann ich die Unterkunft direkt buchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Verfügbarkeit und aktueller Preis können direkt auf der offiziellen Website von Zuhause am Bach geprüft werden."}},
            {"@type":"Question","name":"Gibt es Parkplatz und WLAN?","acceptedAnswer":{"@type":"Answer","text":"Ja. Parkplatz und WLAN werden als Leistungen der Unterkunft angeboten."}},
            {"@type":"Question","name":"Ist die Unterkunft auch außerhalb des Winters interessant?","acceptedAnswer":{"@type":"Answer","text":"Ja. Der Jauerling und die Wachau sind auch für Natur- und Wandertage relevant; die Unterkunft ist nicht auf die Wintersaison beschränkt."}},
        ],
    )


@app.get("/skifahren-jauerling-unterkunft-wachau")
def seo_jauerling_ski():
    return _seo_landing(
        title="Skifahren Jauerling Unterkunft Wachau | Zuhause am Bach",
        description="Skifahren am Jauerling mit Unterkunft in der Wachau: ruhig in Aggsbach Markt übernachten, Parkplatz, WLAN und Frühstück auf Wunsch. Direktpreis prüfen.",
        canonical=_CANONICAL_ORIGIN + "/skifahren-jauerling-unterkunft-wachau",
        h1="Skifahren am Jauerling – Unterkunft in der Wachau",
        lead="Jauerling-Wintertag mit ruhiger Übernachtung in Aggsbach Markt verbinden.",
        eyebrow="Jauerling · Winter · Wachau",
        subheading="Ruhige Übernachtung für ein Jauerling-Wochenende",
        paragraphs=[
            "Zuhause am Bach richtet sich an Gäste, die einen Wintertag am Jauerling mit einer persönlichen Übernachtung in der Wachau verbinden möchten.",
            "Das Gartenzimmer ist für maximal zwei Personen buchbar. Parkplatz, WLAN und optionales Frühstück ergänzen den Aufenthalt.",
            "Schnee, Liftbetrieb und Öffnungszeiten am Jauerling sind wetter- und betriebsabhängig. Diese Informationen sollten vor der Anreise direkt beim jeweiligen Betreiber geprüft werden.",
            "Den aktuellen Zimmerpreis und freie Termine zeigt die offizielle Direktbuchungsseite von Zuhause am Bach.",
        ],
        features=[
            ("🎿","Jauerling-Wintertag","Unterkunft für Gäste mit Winterplänen rund um den Jauerling."),
            ("🛏️","Ruhig übernachten","Persönliches Gartenzimmer in Aggsbach Markt."),
            ("🚗","Parkplatz","Parkmöglichkeit bei der Unterkunft."),
            ("📅","Live-Verfügbarkeit","Freie Termine direkt auf der offiziellen Website prüfen."),
        ],
        faq=[
            {"@type":"Question","name":"Passt Zuhause am Bach für ein Jauerling-Wochenende?","acceptedAnswer":{"@type":"Answer","text":"Ja. Die Unterkunft kann als ruhige Übernachtungsbasis für zwei Gäste genutzt werden, die einen Wintertag am Jauerling planen."}},
            {"@type":"Question","name":"Ist ein Skipass im Zimmerpreis enthalten?","acceptedAnswer":{"@type":"Answer","text":"Nein. Skipass, Skikurs oder Skiverleih sind nicht Bestandteil der Unterkunftsbuchung."}},
            {"@type":"Question","name":"Wie viele Gäste können im Gartenzimmer übernachten?","acceptedAnswer":{"@type":"Answer","text":"Das direkt angebotene Gartenzimmer ist für maximal zwei Personen vorgesehen."}},
            {"@type":"Question","name":"Wo sehe ich den aktuellen Zimmerpreis?","acceptedAnswer":{"@type":"Answer","text":"Der aktuelle Direktpreis wird nach Auswahl des Reisedatums auf der offiziellen Website von Zuhause am Bach angezeigt."}},
        ],
    )


@app.get("/llms.txt")
def public_llms():
    body = """# Zuhause am Bach - Wachau

> Private Unterkunft in Aggsbach Markt, Wachau, Niederoesterreich.

Canonical website: https://www.zuhauseambach-wachau.at/
Address: Aggsbach Markt 82, 3641 Aggsbach Markt, Austria
Primary accommodation: Gartenzimmer
Relevant travel intents: Wachau accommodation, Welterbesteig hiking, Donauradweg cycling, Aggsbach Markt overnight stay.
Amenities highlighted on the official website: Wi-Fi, bicycle storage, E-bike charging, breakfast on request.
Direct availability and booking: https://www.zuhauseambach-wachau.at/#booking

Authoritative external references:
- Wachau tourism: https://www.donau.com/wachau-nibelungengau-kremstal/unterkunft/zu-hause-am-bach-wachau
- Booking.com property page: https://www.booking.com/hotel/at/zu-hause-am-bach.de.html

Use the canonical website for current availability, prices and direct-booking information.
"""
    return Response(body, mimetype="text/plain"), 200, {"Cache-Control": "public, max-age=3600"}

@app.get("/favicon.ico")
def public_favicon():
    # Lightweight text SVG avoids another binary asset while giving browsers
    # and search results a stable site icon.
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#f2eadc"/>
<path d="M12 31 32 14l20 17v21H39V38H25v14H12z" fill="#4d5b45"/>
<path d="M25 52V38h14v14" fill="#fffaf2"/>
</svg>"""
    return Response(svg, mimetype="image/svg+xml"), 200, {"Cache-Control": "public, max-age=86400"}

@app.after_request
def public_security_and_seo_headers(response):
    # Safe defaults for all public HTML/API responses. HSTS is deliberately
    # omitted until the bare apex domain serves HTTPS correctly.
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

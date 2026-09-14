"""Railway entrypoint with booking hold cleanup, PayPal checkout and health checks."""

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.utils import parseaddr
from zoneinfo import ZoneInfo

from flask import jsonify, request

import app as core_app
from app import (
    app,
    db,
    ROOMS,
    parse_date,
    price_breakdown,
    room_available_in_conn,
    sync_room,
    require_admin,
)
from payment_hold import ALERT_EMAIL, init_payment_hold
from paypal_checkout import init_paypal_checkout
from booking_notifications import init_booking_notifications
from provider_monitor import init_provider_monitor
from provider_radar import init_provider_radar
from pricing_2027 import nightly_direct_rate
from master_calendar import init_master_calendar


# Bump this marker when Railway must rebuild after checkout/notification changes.
PAYPAL_CHECKOUT_DEPLOY_REV = "2026-09-14-zab-master-calendar-v1"
EXPECTED_PAYPAL_MERCHANT_EMAIL = "topdiveair@gmail.com"

# Checkout callbacks must use the currently active Railway public domain. Railway's
# own RAILWAY_PUBLIC_DOMAIN wins over a stale manually configured callback URL.
FALLBACK_RAILWAY_CHECKOUT_BASE = "https://web-production-f05a4.up.railway.app"
_raw_checkout_base = os.environ.get("PUBLIC_CHECKOUT_BASE_URL", "").strip().strip("'\"").strip().rstrip("/")
_railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
if _railway_public_domain:
    _clean_checkout_base = f"https://{_railway_public_domain}"
elif _raw_checkout_base.startswith("https://"):
    _clean_checkout_base = _raw_checkout_base
else:
    _clean_checkout_base = FALLBACK_RAILWAY_CHECKOUT_BASE
os.environ["PUBLIC_CHECKOUT_BASE_URL"] = _clean_checkout_base

PUBLIC_BACHBLICK_NIGHTLY_PRICE = float(
    os.environ.get("PUBLIC_BACHBLICK_NIGHTLY_PRICE", "99.00")
)


def direct_checkout_price_breakdown(room, arrival, departure, adults, chosen, coupon_code=""):
    """Return the price that is actually published on the direct-booking page."""
    breakdown = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)
    if room != "Bachblick":
        return breakdown

    nights = max(0, (departure - arrival).days)
    dynamic_rates = []
    current = arrival
    while current < departure:
        nightly = nightly_direct_rate(current)
        if nightly is None:
            dynamic_rates = []
            break
        dynamic_rates.append(float(nightly))
        current += timedelta(days=1)
    room_total = round(
        sum(dynamic_rates) if dynamic_rates else PUBLIC_BACHBLICK_NIGHTLY_PRICE * nights,
        2,
    )
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )
    return {
        **breakdown,
        "room_total": room_total,
        "discounts": [],
        "total": round(room_total + extras_total, 2),
    }


# Install the OS-owned availability layer after app.py has initialized its base
# schema and routes. The wrapper is then injected back into the app module, so
# /book, /api/availability and the PayPal checkout all consult the same source.
init_master_calendar(app, db, require_admin, ROOMS)
_legacy_room_available_in_conn = core_app.room_available_in_conn


def master_room_available_in_conn(conn, room, arrival, departure):
    checker = app.extensions.get("zab_master_room_available")
    if checker:
        return checker(conn, room, arrival, departure, "direct")
    return _legacy_room_available_in_conn(conn, room, arrival, departure)


core_app.room_available_in_conn = master_room_available_in_conn
room_available_in_conn = master_room_available_in_conn


init_payment_hold(app, db)
init_paypal_checkout(
    app,
    db,
    ROOMS,
    parse_date,
    direct_checkout_price_breakdown,
    room_available_in_conn,
    sync_room,
)
init_booking_notifications(app, db)
init_provider_monitor(app, db, require_admin)
init_provider_radar(app, db, require_admin)


@app.before_request
def validate_public_paypal_payload():
    """Enforce critical checkout rules on the server, independent of browser JS."""
    if request.method != "POST" or request.path not in {"/api/paypal/quote", "/api/paypal/create-order"}:
        return None

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "message": "Ungültige Buchungsdaten."}), 400

    try:
        arrival = parse_date(str(payload.get("arrival", "")))
        departure = parse_date(str(payload.get("departure", "")))
    except Exception:
        return jsonify({"ok": False, "message": "Bitte gültige Reisedaten eingeben."}), 400

    if arrival < datetime.now(ZoneInfo("Europe/Vienna")).date():
        return jsonify({"ok": False, "message": "Die Anreise darf nicht in der Vergangenheit liegen."}), 400
    if departure <= arrival:
        return jsonify({"ok": False, "message": "Die Abreise muss nach der Anreise liegen."}), 400

    extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
    if extras.get("etappenjause"):
        return jsonify({
            "ok": False,
            "message": "Die Etappenjause wird separat bestätigt und kann nicht automatisch über PayPal abgeschlossen werden.",
        }), 400

    if request.path == "/api/paypal/create-order":
        configured_merchant_email = os.environ.get("PAYPAL_EMAIL", "").strip().lower()
        if configured_merchant_email != EXPECTED_PAYPAL_MERCHANT_EMAIL:
            return jsonify({
                "ok": False,
                "message": "PayPal-Zahlung aus Sicherheitsgründen gestoppt: Händlerkonto ist nicht eindeutig als Zuhause am Bach konfiguriert.",
            }), 503

        email = str(payload.get("email", "")).strip()
        _, parsed_email = parseaddr(email)
        if not parsed_email or parsed_email != email or "@" not in parsed_email:
            return jsonify({"ok": False, "message": "Bitte eine gültige E-Mail-Adresse eingeben."}), 400
        phone_digits = "".join(ch for ch in str(payload.get("phone", "")) if ch.isdigit())
        if len(phone_digits) < 6:
            return jsonify({"ok": False, "message": "Bitte eine gültige Telefonnummer eingeben."}), 400

    return None


# The notification modules historically retried email delivery in global
# after_request handlers. That can make Railway's health request wait on SMTP.
# Remove those global handlers and notify only after a successful paid return.
_BLOCKING_NOTIFICATION_HANDLERS = {
    "notify_new_confirmed_bookings",
    "send_missing_paid_confirmations",
}
app.after_request_funcs[None] = [
    func
    for func in app.after_request_funcs.get(None, [])
    if getattr(func, "__name__", "") not in _BLOCKING_NOTIFICATION_HANDLERS
]


# Railway liveness must not depend on Flask hooks, SQLite, SMTP or iCal.
_flask_wsgi_app = app.wsgi_app


def railway_liveness_wsgi(environ, start_response):
    if environ.get("PATH_INFO") == "/health/live":
        body = b"ok\n"
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]
    return _flask_wsgi_app(environ, start_response)


app.wsgi_app = railway_liveness_wsgi


def _notify_paid_booking(booking_id):
    if not booking_id:
        return
    try:
        with db() as conn:
            booking = conn.execute(
                "SELECT id,email,status,paid FROM bookings WHERE id=?", (booking_id,)
            ).fetchone()
            owner_sent = conn.execute(
                """SELECT 1 FROM email_log
                   WHERE booking_id=? AND lower(recipient)=lower(?)
                     AND subject LIKE '%Neue bezahlte Buchung:%' AND status='gesendet'
                   LIMIT 1""",
                (booking_id, ALERT_EMAIL),
            ).fetchone()
    except Exception:
        return
    if not booking or booking["status"] != "confirmed" or not int(booking["paid"] or 0):
        return
    if not owner_sent:
        sender = app.extensions.get("zab_send_priority_alert")
        if sender:
            try:
                sender(booking_id, "confirmed")
            except Exception:
                pass
    guest_sender = app.extensions.get("zab_send_paid_guest_confirmation")
    if guest_sender:
        try:
            guest_sender(booking_id)
        except Exception:
            pass


@app.after_request
def notify_successful_paid_booking(response):
    """Send owner/guest alerts after a genuinely paid PayPal return."""
    if response.status_code != 200:
        return response
    if request.path != "/paypal/return":
        return response
    _notify_paid_booking(request.args.get("booking", type=int))
    return response


@app.get("/health/deploy")
def railway_deploy_health():
    """Return the checkout revision currently running."""
    configured_merchant_email = os.environ.get("PAYPAL_EMAIL", "").strip().lower()
    return {
        "status": "ok",
        "paypal_checkout": bool(app.extensions.get("zab_paypal_checkout_enabled")),
        "paypal_merchant_email_match": configured_merchant_email == EXPECTED_PAYPAL_MERCHANT_EMAIL,
        "paid_guest_email": bool(app.extensions.get("zab_send_paid_guest_confirmation")),
        "provider_monitor": bool(app.extensions.get("zab_provider_monitor_initialized")),
        "provider_radar": bool(app.extensions.get("zab_provider_radar_initialized")),
        "master_calendar": bool(app.extensions.get("zab_master_calendar_initialized")),
        "master_calendar_mode": app.extensions.get("zab_master_calendar_mode", "off"),
        "checkout_rev": PAYPAL_CHECKOUT_DEPLOY_REV,
        "checkout_base": os.environ.get("PUBLIC_CHECKOUT_BASE_URL", ""),
    }, 200


@app.get("/health/paypal")
def paypal_health():
    """Verify PayPal credentials without creating an order or exposing secrets."""
    environment = os.environ.get("PAYPAL_ENV", "live").strip().lower()
    client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
    secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
    configured_merchant_email = os.environ.get("PAYPAL_EMAIL", "").strip().lower()
    if configured_merchant_email != EXPECTED_PAYPAL_MERCHANT_EMAIL:
        return {
            "ok": False,
            "environment": environment,
            "reason": "merchant_email_mismatch",
        }, 503
    if not client_id or not secret:
        return {"ok": False, "environment": environment, "reason": "credentials_missing"}, 503

    api_base = (
        "https://api-m.sandbox.paypal.com"
        if environment == "sandbox"
        else "https://api-m.paypal.com"
    )
    auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        api_base + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Accept-Language": "de_AT",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("access_token"):
            return {"ok": False, "environment": environment, "reason": "token_missing"}, 502
        return {"ok": True, "environment": environment, "credentials": "accepted"}, 200
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "environment": environment,
            "reason": "paypal_rejected_credentials" if exc.code == 401 else "paypal_http_error",
            "paypal_status": exc.code,
        }, 503
    except Exception:
        return {"ok": False, "environment": environment, "reason": "paypal_unreachable"}, 503

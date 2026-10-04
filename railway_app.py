"""Railway entrypoint with booking hold cleanup, PayPal checkout and health checks."""

import base64
import json
import os
import smtplib
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
from pricing_2027 import nightly_direct_rate, pricing_config, cap_room_rate
from master_calendar import init_master_calendar
from zab_control_center_v3 import make_master_checkout_sync
from host_automation import init_host_automation


# Bump this marker when Railway must rebuild after checkout/notification changes.
PAYPAL_CHECKOUT_DEPLOY_REV = "2026-09-26-market-ready-ar-v1"
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


def _booked_nights_next_30_days(today=None):
    """Return unique occupied Bachblick nights in the rolling 30-day window."""
    today = today or datetime.now(ZoneInfo("Europe/Vienna")).date()
    window_end = today + timedelta(days=30)
    occupied = set()
    with db() as conn:
        booking_rows = conn.execute(
            """SELECT arrival, departure
               FROM bookings
               WHERE room='Bachblick'
                 AND status='confirmed'
                 AND departure > ?
                 AND arrival < ?""",
            (today.isoformat(), window_end.isoformat()),
        ).fetchall()
        block_rows = conn.execute(
            """SELECT start_date, end_date
               FROM external_blocks
               WHERE room='Bachblick'
                 AND end_date > ?
                 AND start_date < ?""",
            (today.isoformat(), window_end.isoformat()),
        ).fetchall()

    for row in list(booking_rows) + list(block_rows):
        try:
            start = max(today, parse_date(str(row[0])))
            end = min(window_end, parse_date(str(row[1])))
        except Exception:
            continue
        cur = start
        while cur < end:
            occupied.add(cur)
            cur += timedelta(days=1)
    return occupied


def revenue_management_status(today=None):
    """Return the shared live revenue state used by checkout and Zuhause am Bach OS."""
    today = today or datetime.now(ZoneInfo("Europe/Vienna")).date()
    occupied = _booked_nights_next_30_days(today)
    occupancy = round((len(occupied) / 30.0) * 100.0, 1)
    cfg = pricing_config()
    add_eur = 0.0
    for rule in sorted(
        cfg.get("revenue_rules", {}).get("raise_if_occupancy_next_30_days_percent_gte", []),
        key=lambda row: float(row.get("occupancy", 0)),
    ):
        if occupancy >= float(rule.get("occupancy", 0)):
            add_eur = max(add_eur, float(rule.get("add_eur", 0)))
    level = (
        "PEAK" if occupancy >= 85
        else "STRONG" if occupancy >= 70
        else "ACTIVE" if occupancy >= 50
        else "BASE"
    )
    rules_cfg = cfg.get("revenue_rules", {})
    late_hour = int(rules_cfg.get("same_day_after_hour_local", 20))
    late_add_eur = float(rules_cfg.get("same_day_after_hour_add_eur", 100))
    now_local = datetime.now(ZoneInfo(str(rules_cfg.get("same_day_after_hour_timezone", "Europe/Vienna"))))
    return {
        "available": True,
        "occupancy": occupancy,
        "occupied_nights": len(occupied),
        "available_nights": 30 - len(occupied),
        "add_eur": round(add_eur, 2),
        "level": level,
        "window_start": today.isoformat(),
        "window_end": (today + timedelta(days=30)).isoformat(),
        "same_day_after_hour_local": late_hour,
        "same_day_after_hour_add_eur": round(late_add_eur, 2),
        "same_day_late_surcharge_active_now": now_local.date() == today and now_local.hour >= late_hour,
    }


app.extensions["zab_revenue_management_status"] = revenue_management_status


@app.get("/api/public/revenue-status")
def public_revenue_status():
    """Public aggregate yield status for the local Zuhause am Bach OS.

    Contains no guest names, booking references, emails or other personal data.
    """
    try:
        payload = dict(revenue_management_status())
        return jsonify({"ok": True, **payload}), 200, {"Cache-Control": "no-store"}
    except Exception as exc:
        return jsonify({"ok": False, "error": "revenue_status_unavailable", "message": str(exc)[:300]}), 503


def _revenue_adjustment_for_day(day, occupied=None, today=None):
    """Apply the configured rolling-occupancy yield rule to near-term nights only."""
    today = today or datetime.now(ZoneInfo("Europe/Vienna")).date()
    lead_days = (day - today).days
    if lead_days < 0 or lead_days >= 30:
        return 0.0, 0.0

    if occupied is None:
        occupied = _booked_nights_next_30_days(today)
    occupancy = (len(occupied) / 30.0) * 100.0

    cfg = pricing_config()
    add_eur = 0.0
    rules = cfg.get("revenue_rules", {}).get(
        "raise_if_occupancy_next_30_days_percent_gte", []
    )
    for rule in sorted(rules, key=lambda row: float(row.get("occupancy", 0))):
        if occupancy >= float(rule.get("occupancy", 0)):
            add_eur = max(add_eur, float(rule.get("add_eur", 0)))
    return add_eur, round(occupancy, 1)


def direct_checkout_price_breakdown(room, arrival, departure, adults, chosen, coupon_code=""):
    """Return the published direct rate with rolling occupancy-based yield management."""
    breakdown = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)
    if room != "Bachblick":
        return breakdown

    nights = max(0, (departure - arrival).days)
    dynamic_rates = []
    yield_details = []
    pricing_cfg = pricing_config()
    revenue_rules_cfg = pricing_cfg.get("revenue_rules", {})
    late_tz = ZoneInfo(str(revenue_rules_cfg.get("same_day_after_hour_timezone", "Europe/Vienna")))
    now_local = datetime.now(late_tz)
    today = now_local.date()
    late_hour = int(revenue_rules_cfg.get("same_day_after_hour_local", 20))
    late_add_eur = float(revenue_rules_cfg.get("same_day_after_hour_add_eur", 100))
    try:
        occupied = _booked_nights_next_30_days(today)
    except Exception:
        occupied = set()

    current = arrival
    while current < departure:
        nightly = core_app.direct_nightly_price_for_day(room, current)
        if nightly is None:
            dynamic_rates = []
            yield_details = []
            break

        base_rate = float(nightly)
        add_eur, occupancy = _revenue_adjustment_for_day(
            current, occupied=occupied, today=today
        )
        nightly = base_rate + add_eur
        same_day_late_add_eur = 0.0
        if current == today and now_local.hour >= late_hour:
            same_day_late_add_eur = late_add_eur
            nightly += same_day_late_add_eur

        nightly = cap_room_rate(nightly)
        dynamic_rates.append(float(nightly))
        yield_details.append(
            {
                "date": current.isoformat(),
                "base_rate": round(base_rate, 2),
                "occupancy_30d_percent": occupancy,
                "yield_add_eur": round(add_eur, 2),
                "same_day_late_add_eur": round(same_day_late_add_eur, 2),
                "same_day_late_after_hour": late_hour,
                "final_rate": round(float(nightly), 2),
            }
        )
        current += timedelta(days=1)

    room_total = round(
        sum(dynamic_rates) if dynamic_rates else cap_room_rate(PUBLIC_BACHBLICK_NIGHTLY_PRICE) * nights,
        2,
    )
    extras_total = round(
        sum(float(line.get("amount", 0) or 0) for line in breakdown.get("extras", [])),
        2,
    )
    nightly_rates = [
        {"date": row["date"], "rate": row["final_rate"]}
        for row in yield_details
    ]
    if not nightly_rates:
        nightly_rates = [
            {"date": (arrival + timedelta(days=index)).isoformat(),
             "rate": round(cap_room_rate(PUBLIC_BACHBLICK_NIGHTLY_PRICE), 2)}
            for index in range(nights)
        ]
    return {
        **breakdown,
        "nightly_rates": nightly_rates,
        "room_total": room_total,
        "discounts": [],
        "revenue_management": yield_details,
        "total": round(room_total + extras_total, 2),
    }


# Public availability, booking requests and payment use the same final direct
# rates. The imported price_breakdown above remains the legacy extras calculator,
# so this assignment does not recurse into direct_checkout_price_breakdown.
core_app.price_breakdown = direct_checkout_price_breakdown

from channel_pricing import init_channel_pricing


def final_direct_rate(room, day):
    return direct_checkout_price_breakdown(room, day, day + timedelta(days=1), 2, {})["room_total"]





# Install the OS-owned availability layer after app.py has initialized its base
# schema and routes. The wrapper is then injected back into the app module, so
# /book, /api/availability and the PayPal checkout all consult the same source.
init_master_calendar(app, db, require_admin, ROOMS)
init_channel_pricing(app, db, final_direct_rate, require_admin)
_legacy_room_available_in_conn = core_app.room_available_in_conn


def master_room_available_in_conn(conn, room, arrival, departure):
    checker = app.extensions.get("zab_master_room_available")
    if checker:
        return checker(conn, room, arrival, departure, "direct")
    return _legacy_room_available_in_conn(conn, room, arrival, departure)


core_app.room_available_in_conn = master_room_available_in_conn
room_available_in_conn = master_room_available_in_conn

# HYBRID keeps the existing Booking/iCal safety barrier. In MASTER mode the
# operator can explicitly let PayPal trust the OS calendar, or it happens
# automatically while the Booking channel is globally closed.
checkout_sync_room = make_master_checkout_sync(app, db, sync_room)

init_payment_hold(app, db)
init_paypal_checkout(
    app,
    db,
    ROOMS,
    parse_date,
    direct_checkout_price_breakdown,
    room_available_in_conn,
    checkout_sync_room,
)
init_booking_notifications(app, db)
init_provider_monitor(app, db, require_admin)
init_provider_radar(app, db, require_admin)
init_host_automation(app, db, require_admin, core_app.DB_PATH)


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
    """Return a secret-safe production readiness snapshot."""
    configured_merchant_email = os.environ.get("PAYPAL_EMAIL", "").strip().lower()
    try:
        with db() as conn:
            settings = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM site_settings")}
            ical = conn.execute("SELECT import_url FROM ical_settings WHERE room='Bachblick'").fetchone()
        smtp_configured = all(str(settings.get(k, "")).strip() for k in ("smtp_host","smtp_user","smtp_password"))
        ical_configured = bool(ical and str(ical["import_url"] or "").strip())
    except Exception:
        settings = {}
        smtp_configured = False
        ical_configured = False
    bank_transfer_configured = bool(
        os.environ.get("BANK_ACCOUNT_HOLDER", "").strip()
        and os.environ.get("BANK_IBAN", "").strip()
    )
    public_site = os.environ.get("PUBLIC_SITE_URL", "").strip().rstrip("/")
    return {
        "status": "ok",
        "paypal_checkout": bool(app.extensions.get("zab_paypal_checkout_enabled")),
        "paypal_merchant_email_match": configured_merchant_email == EXPECTED_PAYPAL_MERCHANT_EMAIL,
        "paid_guest_email": bool(app.extensions.get("zab_send_paid_guest_confirmation")),
        "smtp_configured": smtp_configured,
        "https_mail_configured": bool(os.environ.get("RESEND_API_KEY", "").strip() and os.environ.get("MAIL_SENDER_EMAIL", "").strip()),
        "bank_transfer_configured": bank_transfer_configured,
        "ical_configured": ical_configured,
        "official_public_site": public_site in {"https://zuhauseambach-wachau.at","https://www.zuhauseambach-wachau.at"},
        "provider_monitor": bool(app.extensions.get("zab_provider_monitor_initialized")),
        "provider_radar": bool(app.extensions.get("zab_provider_radar_initialized")),
        "master_calendar": bool(app.extensions.get("zab_master_calendar_initialized")),
        "master_calendar_mode": app.extensions.get("zab_master_calendar_mode", "off"),
        "paypal_master_independent": bool(app.extensions.get("zab_paypal_master_independent")),
        "checkout_rev": PAYPAL_CHECKOUT_DEPLOY_REV,
        "checkout_base": os.environ.get("PUBLIC_CHECKOUT_BASE_URL", ""),
    }, 200


@app.get("/health/mail")
def mail_health():
    """Verify the active HTTPS mail provider without sending a message."""
    brevo_key = os.environ.get("BREVO_API_KEY", "").strip()
    brevo_sender = (
        os.environ.get("BREVO_SENDER_EMAIL", "").strip()
        or os.environ.get("BOOKING_OWNER_EMAIL", "").strip()
    )
    if brevo_key:
        req = urllib.request.Request(
            "https://api.brevo.com/v3/account",
            headers={
                "accept": "application/json",
                "api-key": brevo_key,
                "User-Agent": "ZAB-Booking/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                if int(response.status) == 200:
                    return {
                        "ok": True,
                        "provider": "brevo",
                        "authentication": "accepted",
                        "sender_configured": bool(brevo_sender),
                    }, 200
        except urllib.error.HTTPError as exc:
            brevo_reason = "brevo_auth_rejected" if exc.code in (401, 403) else "brevo_http_error"
        except Exception:
            brevo_reason = "brevo_unreachable"
    else:
        brevo_reason = "brevo_api_key_missing"

    if os.environ.get("MAIL_PROVIDER_ALLOW_RESEND", "0").strip() == "1":
        resend_key = os.environ.get("RESEND_API_KEY", "").strip()
        sender_email = os.environ.get("MAIL_SENDER_EMAIL", "").strip()
        if resend_key:
            req = urllib.request.Request(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {resend_key}", "User-Agent": "ZAB-Booking/1.0"},
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    if int(response.status) == 200:
                        return {
                            "ok": True,
                            "provider": "resend",
                            "authentication": "accepted",
                            "sender_configured": bool(sender_email),
                        }, 200
            except urllib.error.HTTPError as exc:
                resend_reason = "resend_auth_rejected" if exc.code in (401, 403) else "resend_http_error"
            except Exception:
                resend_reason = "resend_unreachable"
        else:
            resend_reason = "resend_api_key_missing"
    else:
        resend_reason = "resend_disabled"

    return {
        "ok": False,
        "provider": "none",
        "reason": "mail_provider_unhealthy",
        "brevo": brevo_reason,
        "resend": resend_reason,
    }, 503


@app.get("/health/smtp")
def smtp_health():
    """Verify SMTP configuration and authentication without sending mail."""
    try:
        with db() as conn:
            settings = {
                row["key"]: row["value"]
                for row in conn.execute("SELECT key,value FROM site_settings")
            }
        host = str(settings.get("smtp_host", "")).strip()
        user = str(settings.get("smtp_user", "")).strip()
        password = str(settings.get("smtp_password", "")).strip()
        port = int(str(settings.get("smtp_port", "587") or "587").strip())
    except Exception:
        return {"ok": False, "reason": "settings_unavailable"}, 503

    if not host or not user or not password:
        return {
            "ok": False,
            "reason": "smtp_credentials_missing",
            "host_configured": bool(host),
            "user_configured": bool(user),
            "password_configured": bool(password),
        }, 503

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
        return {
            "ok": True,
            "tls": True,
            "authentication": "accepted",
        }, 200
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "reason": "smtp_auth_rejected"}, 503
    except (smtplib.SMTPException, OSError, TimeoutError):
        return {"ok": False, "reason": "smtp_unreachable"}, 503
    except Exception:
        return {"ok": False, "reason": "smtp_check_failed"}, 503


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

"""Railway entrypoint with booking hold cleanup, PayPal checkout and health check."""

import base64
import json
import os
import urllib.error
import urllib.request

from flask import request

from app import (
    app,
    db,
    ROOMS,
    parse_date,
    price_breakdown,
    room_available_in_conn,
    sync_room,
)
from payment_hold import ALERT_EMAIL, init_payment_hold
from paypal_checkout import init_paypal_checkout
from booking_notifications import init_booking_notifications


# Bump this marker when Railway must rebuild after checkout/notification changes.
PAYPAL_CHECKOUT_DEPLOY_REV = "2026-08-26-wsgi-liveness-v4"

# PayPal requires return_url/cancel_url to be valid absolute URIs. Prefer the
# explicitly configured public URL, otherwise Railway's current public domain.
# The historic URL remains only as a last-resort fallback for older setups.
FALLBACK_RAILWAY_CHECKOUT_BASE = "https://web-production-7db62.up.railway.app"
_raw_checkout_base = os.environ.get("PUBLIC_CHECKOUT_BASE_URL", "").strip().strip("'\"").strip().rstrip("/")
_railway_public_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
if _raw_checkout_base.startswith("https://"):
    _clean_checkout_base = _raw_checkout_base
elif _railway_public_domain:
    _clean_checkout_base = f"https://{_railway_public_domain}"
else:
    _clean_checkout_base = FALLBACK_RAILWAY_CHECKOUT_BASE
os.environ["PUBLIC_CHECKOUT_BASE_URL"] = _clean_checkout_base

PUBLIC_BACHBLICK_NIGHTLY_PRICE = float(
    os.environ.get("PUBLIC_BACHBLICK_NIGHTLY_PRICE", "101.00")
)


def direct_checkout_price_breakdown(room, arrival, departure, adults, chosen, coupon_code=""):
    """Return the price that is actually published on the direct-booking page."""
    breakdown = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)
    if room != "Bachblick":
        return breakdown

    nights = max(0, (departure - arrival).days)
    room_total = round(PUBLIC_BACHBLICK_NIGHTLY_PRICE * nights, 2)
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
# This WSGI-level endpoint proves only that Gunicorn imported the app and is
# accepting HTTP requests. If application startup itself crashes, it still fails.
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


@app.after_request
def notify_successful_paypal_booking(response):
    """Send owner/guest mail only for a genuinely paid PayPal return."""
    if request.path != "/paypal/return" or response.status_code != 200:
        return response

    booking_id = request.args.get("booking", type=int)
    if not booking_id:
        return response

    try:
        with db() as conn:
            booking = conn.execute(
                "SELECT id,email,status,paid FROM bookings WHERE id=?",
                (booking_id,),
            ).fetchone()
            owner_sent = conn.execute(
                """SELECT 1 FROM email_log
                   WHERE booking_id=?
                     AND lower(recipient)=lower(?)
                     AND subject LIKE '%Neue bezahlte Buchung:%'
                     AND status='gesendet'
                   LIMIT 1""",
                (booking_id, ALERT_EMAIL),
            ).fetchone()
    except Exception:
        return response

    if not booking or booking["status"] != "confirmed" or not int(booking["paid"] or 0):
        return response

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

    return response


@app.get("/health/deploy")
def railway_deploy_health():
    """Return the exact Railway/PayPal checkout revision currently running."""
    return {
        "status": "ok",
        "paypal_checkout": bool(app.extensions.get("zab_paypal_checkout_enabled")),
        "paid_guest_email": bool(app.extensions.get("zab_send_paid_guest_confirmation")),
        "paypal_checkout_rev": PAYPAL_CHECKOUT_DEPLOY_REV,
        "checkout_base": os.environ.get("PUBLIC_CHECKOUT_BASE_URL", ""),
    }, 200


@app.get("/health/paypal")
def paypal_health():
    """Verify PayPal credentials without creating an order or exposing secrets."""
    environment = os.environ.get("PAYPAL_ENV", "live").strip().lower()
    client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
    secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return {
            "ok": False,
            "environment": environment,
            "reason": "credentials_missing",
        }, 503

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
            return {
                "ok": False,
                "environment": environment,
                "reason": "token_missing",
            }, 502
        return {
            "ok": True,
            "environment": environment,
            "credentials": "accepted",
        }, 200
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "environment": environment,
            "reason": "paypal_rejected_credentials" if exc.code == 401 else "paypal_http_error",
            "paypal_status": exc.code,
        }, 503
    except Exception:
        return {
            "ok": False,
            "environment": environment,
            "reason": "paypal_unreachable",
        }, 503

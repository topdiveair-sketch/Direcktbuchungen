"""Public booking-request API for the WachauEtappe guest website."""
from __future__ import annotations

import re
from datetime import datetime
from flask import jsonify, request
from railway_app import app, db

ALLOWED_ORIGINS = {
    "https://topdiveair-sketch.github.io",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _init_table() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS wachauetappe_guest_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            host_id TEXT NOT NULL,
            stay_date TEXT NOT NULL,
            guests INTEGER NOT NULL DEFAULT 1,
            guest_name TEXT NOT NULL,
            guest_email TEXT NOT NULL,
            guest_phone TEXT DEFAULT '',
            note TEXT DEFAULT '',
            price REAL,
            payment_method TEXT NOT NULL DEFAULT 'host',
            status TEXT NOT NULL DEFAULT 'requested',
            source TEXT NOT NULL DEFAULT 'guest_web',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_wachauetappe_guest_bookings_date
        ON wachauetappe_guest_bookings(stay_date, host_id, status);
        """)


_init_table()


def _origin_allowed() -> bool:
    origin = (request.headers.get("Origin") or "").rstrip("/")
    return not origin or origin in ALLOWED_ORIGINS


def _with_cors(response):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/guest-bookings", methods=["OPTIONS"])
def guest_bookings_options():
    return _with_cors(app.make_response(("", 204)))


@app.post("/api/guest-bookings")
def create_guest_booking():
    if not _origin_allowed():
        return _with_cors(jsonify({"error": "origin_not_allowed"})), 403

    payload = request.get_json(silent=True) or {}
    host_id = str(payload.get("hostId") or "").strip()[:160]
    stay_date = str(payload.get("stayDate") or "").strip()[:10]
    guest_name = str(payload.get("guestName") or "").strip()[:160]
    guest_email = str(payload.get("guestEmail") or "").strip()[:254]
    guest_phone = str(payload.get("guestPhone") or "").strip()[:80]
    note = str(payload.get("note") or "").strip()[:2000]
    payment_method = str(payload.get("paymentMethod") or "host").strip()[:40] or "host"
    try:
        guests = max(1, min(12, int(payload.get("guests") or 1)))
    except (TypeError, ValueError):
        guests = 1
    price = payload.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    if not host_id or not guest_name or not stay_date:
        return _with_cors(jsonify({"error": "missing_required_fields"})), 422
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stay_date):
        return _with_cors(jsonify({"error": "invalid_stay_date"})), 422
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", guest_email):
        return _with_cors(jsonify({"error": "invalid_email"})), 422

    now = _now()
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO wachauetappe_guest_bookings(
                reference,host_id,stay_date,guests,guest_name,guest_email,guest_phone,note,
                price,payment_method,status,source,created_at,updated_at
            ) VALUES('',?,?,?,?,?,?,?,?,?,'requested','guest_web',?,?)""",
            (host_id,stay_date,guests,guest_name,guest_email,guest_phone,note,price,payment_method,now,now),
        )
        booking_id = int(cur.lastrowid)
        reference = f"WE-{datetime.now():%Y%m%d}-{booking_id:05d}"
        conn.execute(
            "UPDATE wachauetappe_guest_bookings SET reference=? WHERE id=?",
            (reference, booking_id),
        )

    return _with_cors(jsonify({
        "ok": True,
        "reference": reference,
        "status": "requested",
        "message": "Buchungsanfrage wurde an WachauEtappe übertragen."
    })), 201


@app.get("/health/wachauetappe-bookings")
def guest_booking_health():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM wachauetappe_guest_bookings").fetchone()["n"]
    return {"ok": True, "guest_booking_api": True, "request_count": int(total or 0)}, 200

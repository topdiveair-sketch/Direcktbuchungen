"""Public booking, guest inquiry and host application API for WachauEtappe."""
from __future__ import annotations

import re
from datetime import date, datetime
import secrets
from flask import jsonify, request
from railway_app import app, db

ALLOWED_ORIGINS = {"https://topdiveair-sketch.github.io"}


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

        CREATE TABLE IF NOT EXISTS wachauetappe_guest_inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            guest_name TEXT NOT NULL,
            guest_email TEXT NOT NULL,
            guest_phone TEXT DEFAULT '',
            route TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            guests INTEGER NOT NULL DEFAULT 1,
            daily_km INTEGER,
            luggage INTEGER NOT NULL DEFAULT 0,
            message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wachauetappe_partner_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            business_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT DEFAULT '',
            location TEXT NOT NULL,
            rooms INTEGER,
            one_night INTEGER NOT NULL DEFAULT 1,
            cash_at_host INTEGER NOT NULL DEFAULT 1,
            luggage INTEGER NOT NULL DEFAULT 0,
            website TEXT DEFAULT '',
            note TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        );
        """)
        cols={r[1] for r in conn.execute("PRAGMA table_info(wachauetappe_guest_bookings)").fetchall()}
        if "trip_key" not in cols: conn.execute("ALTER TABLE wachauetappe_guest_bookings ADD COLUMN trip_key TEXT DEFAULT ''")
        if "trip_reference" not in cols: conn.execute("ALTER TABLE wachauetappe_guest_bookings ADD COLUMN trip_reference TEXT DEFAULT ''")
        if "client_request_id" not in cols: conn.execute("ALTER TABLE wachauetappe_guest_bookings ADD COLUMN client_request_id TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_we_guest_trip_key ON wachauetappe_guest_bookings(trip_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_we_guest_trip_reference ON wachauetappe_guest_bookings(trip_reference)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_we_guest_client_request ON wachauetappe_guest_bookings(client_request_id) WHERE client_request_id<>''")


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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response


def _valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value or ""))


def _options():
    return _with_cors(app.make_response(("", 204)))


@app.route("/api/guest-bookings", methods=["OPTIONS"])
def guest_bookings_options():
    return _options()


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
    trip_key = str(payload.get("tripKey") or "").strip()[:120]
    if not trip_key: trip_key = secrets.token_urlsafe(24)
    client_request_id = str(payload.get("clientRequestId") or "").strip()[:320]
    try: guests = max(1, min(12, int(payload.get("guests") or 1)))
    except (TypeError, ValueError): guests = 1
    try: price = float(payload.get("price")) if payload.get("price") is not None else None
    except (TypeError, ValueError): price = None
    if not host_id or not guest_name or not stay_date: return _with_cors(jsonify({"error":"missing_required_fields"})), 422
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stay_date): return _with_cors(jsonify({"error":"invalid_stay_date"})), 422
    try:
        if date.fromisoformat(stay_date) < date.today(): return _with_cors(jsonify({"error":"stay_date_in_past"})),422
    except ValueError: return _with_cors(jsonify({"error":"invalid_stay_date"})),422
    if not _valid_email(guest_email): return _with_cors(jsonify({"error":"invalid_email"})), 422
    now = _now()
    with db() as conn:
        if client_request_id:
            duplicate=conn.execute("SELECT reference,trip_key,trip_reference,status FROM wachauetappe_guest_bookings WHERE client_request_id=?",(client_request_id,)).fetchone()
            if duplicate:
                return _with_cors(jsonify({"ok":True,"reference":duplicate["reference"],"tripKey":duplicate["trip_key"],"tripReference":duplicate["trip_reference"],"status":duplicate["status"],"idempotentReplay":True})),200

        availability=conn.execute("""SELECT a.price,a.rooms_free,a.status,
            CASE WHEN b.stay_date IS NULL THEN 0 ELSE 1 END AS booking_blocked
            FROM wachauetappe_partner_accounts p
            JOIN wachauetappe_partner_availability a ON a.host_id=p.host_id
            LEFT JOIN wachauetappe_partner_calendar_blocks b ON b.host_id=a.host_id AND b.stay_date=a.stay_date AND b.provider='booking'
            WHERE p.host_id=? AND p.active=1 AND a.stay_date=? LIMIT 1""",(host_id,stay_date)).fetchone()
        if not availability:
            return _with_cors(jsonify({"error":"host_or_availability_not_found"})),409
        if availability["status"]!="free" or int(availability["rooms_free"] or 0)<=0 or int(availability["booking_blocked"] or 0):
            return _with_cors(jsonify({"error":"host_not_available"})),409
        price=float(availability["price"]) if availability["price"] is not None else None

        existing=conn.execute("SELECT trip_reference FROM wachauetappe_guest_bookings WHERE trip_key=? AND trip_reference<>'' ORDER BY id LIMIT 1",(trip_key,)).fetchone()
        trip_reference=str(existing["trip_reference"]) if existing else f"WE-R-{datetime.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
        cur = conn.execute("""INSERT INTO wachauetappe_guest_bookings(reference,host_id,stay_date,guests,guest_name,guest_email,guest_phone,note,price,payment_method,status,source,created_at,updated_at,trip_key,trip_reference,client_request_id) VALUES('',?,?,?,?,?,?,?,?,?,'requested','guest_web',?,?,?,?,?)""",(host_id,stay_date,guests,guest_name,guest_email,guest_phone,note,price,payment_method,now,now,trip_key,trip_reference,client_request_id))
        booking_id = int(cur.lastrowid)
        reference = f"WE-{datetime.now():%Y%m%d}-{booking_id:05d}"
        conn.execute("UPDATE wachauetappe_guest_bookings SET reference=? WHERE id=?",(reference,booking_id))
    notifier=app.extensions.get("wachauetappe_notify_new_booking")
    if callable(notifier):
        try:notifier(reference)
        except Exception:pass
    return _with_cors(jsonify({"ok":True,"reference":reference,"tripKey":trip_key,"tripReference":trip_reference,"status":"requested","message":"Buchungsanfrage wurde an WachauEtappe übertragen."})), 201


@app.route("/api/guest-trips/<trip_key>", methods=["OPTIONS"])
def guest_trip_options(trip_key):
    return _options()


@app.get("/api/guest-trips/<trip_key>")
def guest_trip_status(trip_key):
    if not _origin_allowed():
        return _with_cors(jsonify({"error":"origin_not_allowed"})),403
    key=str(trip_key or "").strip()[:120]
    if len(key)<20:
        return _with_cors(jsonify({"error":"invalid_trip_key"})),404
    with db() as conn:
        rows=conn.execute("""SELECT b.reference,b.trip_reference,b.stay_date,b.guests,b.price,b.status,b.created_at,b.updated_at,
        b.host_id,COALESCE(p.name,b.host_id) AS host_name,COALESCE(p.location,'') AS host_location
        FROM wachauetappe_guest_bookings b
        LEFT JOIN wachauetappe_partner_accounts p ON p.host_id=b.host_id
        WHERE b.trip_key=? ORDER BY b.stay_date,b.id""",(key,)).fetchall()
    if not rows:return _with_cors(jsonify({"error":"trip_not_found"})),404
    items=[{"reference":r["reference"],"date":r["stay_date"],"hostId":r["host_id"],"name":r["host_name"],"location":r["host_location"],"price":r["price"],"status":r["status"],"updatedAt":r["updated_at"]} for r in rows]
    confirmed=sum(1 for x in items if x["status"]=="confirmed")
    declined=sum(1 for x in items if x["status"]=="declined")
    requested=sum(1 for x in items if x["status"]=="requested")
    overall="confirmed" if confirmed==len(items) else "needs_alternative" if declined else "pending"
    known_total=sum(float(x["price"]) for x in items if x["price"] is not None)
    return _with_cors(jsonify({"ok":True,"tripKey":key,"tripReference":rows[0]["trip_reference"],"overallStatus":overall,"confirmed":confirmed,"declined":declined,"requested":requested,"totalNights":len(items),"knownTotal":round(known_total,2),"items":items})),200


@app.route("/api/guest-inquiries", methods=["OPTIONS"])
def guest_inquiries_options():
    return _options()


@app.post("/api/guest-inquiries")
def create_guest_inquiry():
    if not _origin_allowed(): return _with_cors(jsonify({"error":"origin_not_allowed"})), 403
    p = request.get_json(silent=True) or {}
    name = str(p.get("name") or "").strip()[:160]
    email = str(p.get("email") or "").strip()[:254]
    if not name or not _valid_email(email): return _with_cors(jsonify({"error":"name_and_valid_email_required"})), 422
    try: guests = max(1,min(12,int(p.get("guests") or 1)))
    except (TypeError,ValueError): guests=1
    try: daily_km = max(5,min(80,int(p.get("dailyKm")))) if p.get("dailyKm") else None
    except (TypeError,ValueError): daily_km=None
    now=_now()
    with db() as conn:
        cur=conn.execute("""INSERT INTO wachauetappe_guest_inquiries(reference,guest_name,guest_email,guest_phone,route,start_date,guests,daily_km,luggage,message,status,created_at) VALUES('',?,?,?,?,?,?,?,?,?,'new',?)""",(name,email,str(p.get('phone') or '')[:80],str(p.get('route') or '')[:160],str(p.get('startDate') or '')[:10],guests,daily_km,1 if p.get('luggage') else 0,str(p.get('message') or '')[:3000],now))
        iid=int(cur.lastrowid); ref=f"WE-A-{datetime.now():%Y%m%d}-{iid:05d}"; conn.execute("UPDATE wachauetappe_guest_inquiries SET reference=? WHERE id=?",(ref,iid))
    return _with_cors(jsonify({"ok":True,"reference":ref,"status":"new"})),201


@app.route("/api/partner-applications", methods=["OPTIONS"])
def partner_applications_options():
    return _options()


@app.post("/api/partner-applications")
def create_partner_application():
    if not _origin_allowed(): return _with_cors(jsonify({"error":"origin_not_allowed"})), 403
    p=request.get_json(silent=True) or {}
    business=str(p.get('businessName') or '').strip()[:200]
    contact=str(p.get('contactName') or '').strip()[:160]
    email=str(p.get('email') or '').strip()[:254]
    location=str(p.get('location') or '').strip()[:160]
    if not business or not contact or not location or not _valid_email(email): return _with_cors(jsonify({"error":"required_fields_missing"})),422
    try: rooms=max(1,min(100,int(p.get('rooms')))) if p.get('rooms') else None
    except (TypeError,ValueError): rooms=None
    now=_now()
    with db() as conn:
        cur=conn.execute("""INSERT INTO wachauetappe_partner_applications(reference,business_name,contact_name,email,phone,location,rooms,one_night,cash_at_host,luggage,website,note,status,created_at) VALUES('',?,?,?,?,?,?,?,?,?,?,?,'new',?)""",(business,contact,email,str(p.get('phone') or '')[:80],location,rooms,1 if p.get('oneNight',True) else 0,1 if p.get('cashAtHost',True) else 0,1 if p.get('luggage') else 0,str(p.get('website') or '')[:300],str(p.get('note') or '')[:3000],now))
        aid=int(cur.lastrowid); ref=f"WE-P-{datetime.now():%Y%m%d}-{aid:05d}"; conn.execute("UPDATE wachauetappe_partner_applications SET reference=? WHERE id=?",(ref,aid))
    return _with_cors(jsonify({"ok":True,"reference":ref,"status":"new"})),201


@app.get("/health/wachauetappe-bookings")
def guest_booking_health():
    with db() as conn:
        bookings=conn.execute("SELECT COUNT(*) AS n FROM wachauetappe_guest_bookings").fetchone()["n"]
        inquiries=conn.execute("SELECT COUNT(*) AS n FROM wachauetappe_guest_inquiries").fetchone()["n"]
        partners=conn.execute("SELECT COUNT(*) AS n FROM wachauetappe_partner_applications").fetchone()["n"]
    return {"ok":True,"guest_booking_api":True,"request_count":int(bookings or 0),"inquiry_count":int(inquiries or 0),"partner_application_count":int(partners or 0)},200

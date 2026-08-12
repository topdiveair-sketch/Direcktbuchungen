
from __future__ import annotations

import os
import sqlite3
import urllib.request
import urllib.error
import hmac
from datetime import datetime, date, timedelta
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask, Response, jsonify, redirect, render_template, request,
    session, flash, url_for
)
from werkzeug.utils import secure_filename
from addons import init_addons
from v6_features import init_v6
from stability import init_stability
from zab_os import init_zab_os
from host_assistant import init_host_assistant
from smart_host import init_smart_host
from knowledge import init_knowledge
from quality_v12 import init_quality_v12
from alltag import init_alltag

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE / "data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "zab.db"
ROOM_IMAGE_DIR = BASE / "static" / "images" / "rooms"

def env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


PRODUCTION_MODE = (
    env_flag("REQUIRE_PRODUCTION_SECRETS")
    or os.environ.get("APP_ENV", "").lower() == "production"
    or bool(os.environ.get("RAILWAY_ENVIRONMENT"))
)
SECRET_KEY = os.environ.get("SECRET_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if PRODUCTION_MODE:
    if len(SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY muss im Livebetrieb gesetzt sein und mindestens 32 Zeichen haben.")
    if len(ADMIN_PASSWORD) < 12 or ADMIN_PASSWORD == "windis2026":
        raise RuntimeError("ADMIN_PASSWORD muss im Livebetrieb gesetzt und sicher sein.")

app = Flask(__name__, template_folder=str(BASE / "templates"), static_folder=str(BASE / "static"))
app.json.ensure_ascii = False
app.secret_key = SECRET_KEY or "zab-local-dev-secret-change-before-live"
app.config.update(
    JSON_AS_ASCII=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env_flag("SESSION_COOKIE_SECURE", "0"),
    MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
)
ADMIN_PASSWORD = ADMIN_PASSWORD or "windis2026"
PAYPAL_EMAIL = os.environ.get("PAYPAL_EMAIL", "topdiveair@gmail.com")
GUEST_APP_URL = "https://topdiveair-sketch.github.io/Gaeste/"
ROOM_RELEASE_DATE = date(2026, 8, 16)
BREAKFAST_PRICE = 12.0

ROOMS = {
    "Bachblick": {
        "price": 75.0,
        "available_from": date(2020, 1, 1),
        "image": "bachblick.jpg",
        "description": "Doppelzimmer mit Blick auf den Bach. Gemütlich, ruhig und zum Wohlfühlen.",
    },
    "Marillenzimmer": {
        "price": 90.0,
        "available_from": ROOM_RELEASE_DATE,
        "image": "marillenzimmer.jpg",
        "description": "Wachauer Atmosphäre, warme Details und ein ruhiger Rückzugsort.",
    },
    "Weinbergzimmer": {
        "price": 90.0,
        "available_from": ROOM_RELEASE_DATE,
        "image": "weinbergzimmer.jpg",
        "description": "Inspiriert von den Weinbergen der Wachau – ideal für Genießer.",
    },
    "Donauzimmer": {
        "price": 90.0,
        "available_from": ROOM_RELEASE_DATE,
        "image": "donauzimmer.jpg",
        "description": "Ein freundliches Zimmer mit Bezug zur Donau und zur Wachauer Landschaft.",
    },
}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL UNIQUE,
                room TEXT NOT NULL,
                arrival TEXT NOT NULL,
                departure TEXT NOT NULL,
                adults INTEGER NOT NULL,
                breakfast INTEGER NOT NULL DEFAULT 0,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                message TEXT DEFAULT '',
                payment_method TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS external_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                source TEXT NOT NULL,
                uid TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ical_settings (
                room TEXT PRIMARY KEY,
                import_url TEXT DEFAULT '',
                last_sync TEXT DEFAULT '',
                last_result TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS room_images (
                room TEXT PRIMARY KEY,
                filename TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS room_prices (room TEXT PRIMARY KEY, standard REAL NOT NULL, weekend REAL NOT NULL, high REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS seasons (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS discounts (key TEXT PRIMARY KEY, enabled INTEGER NOT NULL, percent REAL NOT NULL, min_nights INTEGER NOT NULL DEFAULT 0, days_before INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS extras (key TEXT PRIMARY KEY, label TEXT NOT NULL, price REAL NOT NULL, unit TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
            """
        )
        for room, data in ROOMS.items():
            conn.execute(
                "INSERT OR IGNORE INTO ical_settings(room, import_url) VALUES (?, '')",
                (room,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO room_images(room, filename) VALUES (?, ?)",
                (room, data["image"]),
            )

        defaults = {
            "business_name": "Zuhause am Bach - Wachau",
            "operator_name": "Laura Prem",
            "google_rating": "4.8",
            "google_review_count": "4",
            "google_review_url": "https://www.google.com/maps/search/?api=1&query=Zuhause%20am%20Bach%20-%20Wachau%20Aggsbach%20Markt%2082",
            "phone": "+43 664 6437526",
            "email": "topdiveair@gmail.com",
            "address": "Aggsbach Markt 82, 3641 Aggsbach Markt, Oesterreich",
            "public_base_url": "https://topdiveair-sketch.github.io/Gaeste/",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "smtp_user": "topdiveair@gmail.com",
            "smtp_sender": "Zuhause am Bach <topdiveair@gmail.com>",
            "paypal_email": "topdiveair@gmail.com",
            "cancellation_text": "Kostenlose Stornierung bis 7 Tage vor Anreise.",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO site_settings(key, value) VALUES (?, ?)",
                (key, value),
            )
        env_settings = {
            "phone": env_value("SITE_PHONE", "ZAB_PHONE"),
            "email": env_value("SITE_EMAIL", "ZAB_EMAIL"),
            "address": env_value("SITE_ADDRESS", "ZAB_ADDRESS"),
            "public_base_url": env_value("PUBLIC_BASE_URL", "ZAB_PUBLIC_BASE_URL"),
            "paypal_me_url": env_value("PAYPAL_ME_URL", "ZAB_PAYPAL_ME_URL"),
            "google_rating": env_value("GOOGLE_RATING", "ZAB_GOOGLE_RATING"),
            "google_review_count": env_value("GOOGLE_REVIEW_COUNT", "ZAB_GOOGLE_REVIEW_COUNT"),
            "google_review_url": env_value("GOOGLE_REVIEW_URL", "ZAB_GOOGLE_REVIEW_URL"),
            "google_places_api_key": env_value("GOOGLE_PLACES_API_KEY", "ZAB_GOOGLE_PLACES_API_KEY"),
            "smtp_host": env_value("SMTP_HOST", "ZAB_SMTP_HOST"),
            "smtp_port": env_value("SMTP_PORT", "ZAB_SMTP_PORT"),
            "smtp_user": env_value("SMTP_USER", "ZAB_SMTP_USER"),
            "smtp_password": env_value("SMTP_PASSWORD", "ZAB_SMTP_PASSWORD"),
            "smtp_sender": env_value("SMTP_SENDER", "ZAB_SMTP_SENDER"),
            "cancellation_text": env_value("CANCELLATION_TEXT", "ZAB_CANCELLATION_TEXT"),
        }
        if PAYPAL_EMAIL:
            env_settings["paypal_email"] = PAYPAL_EMAIL
        for key, value in env_settings.items():
            if value:
                conn.execute(
                    """INSERT INTO site_settings(key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                    (key, value),
                )

        ical_envs = {
            "Bachblick": env_value("ICAL_BACHBLICK_URL", "BOOKING_ICAL_BACHBLICK_URL"),
            "Marillenzimmer": env_value("ICAL_MARILLENZIMMER_URL", "BOOKING_ICAL_MARILLENZIMMER_URL"),
            "Weinbergzimmer": env_value("ICAL_WEINBERGZIMMER_URL", "BOOKING_ICAL_WEINBERGZIMMER_URL"),
            "Donauzimmer": env_value("ICAL_DONAUZIMMER_URL", "BOOKING_ICAL_DONAUZIMMER_URL"),
        }
        for room, import_url in ical_envs.items():
            if import_url:
                conn.execute(
                    "UPDATE ical_settings SET import_url=? WHERE room=?",
                    (import_url, room),
                )
        price_defaults={"Bachblick":(75,85,95),"Marillenzimmer":(90,100,110),"Weinbergzimmer":(90,100,110),"Donauzimmer":(90,100,110)}
        for r,p in price_defaults.items(): conn.execute("INSERT OR IGNORE INTO room_prices VALUES(?,?,?,?)",(r,*p))
        for row in [("last_minute",1,10,0,3),("early_bird",0,5,0,60),("three_nights",1,5,3,0),("five_nights",1,8,5,0),("seven_nights",1,12,7,0),("direct_booking",1,3,0,0)]: conn.execute("INSERT OR IGNORE INTO discounts VALUES(?,?,?,?,?)",row)
        for row in [("breakfast","Frühstück",12,"person_night",1),("jause","Wachauer Jause",29.9,"booking",1),("luggage","Gepäcktransport",15,"booking",1),("dog","Hund",10,"night",1),("baby_bed","Babybett",8,"booking",1)]: conn.execute("INSERT OR IGNORE INTO extras VALUES(?,?,?,?,?)",row)
        conn.execute("UPDATE extras SET price=15 WHERE key='luggage' AND ABS(price - 25) < 0.001")
        conn.execute("INSERT OR IGNORE INTO seasons(id,name,start_date,end_date) VALUES(1,'Hauptsaison Sommer','2026-06-01','2026-09-30')")


def get_settings() -> dict[str, str]:
    with db() as conn:
        return {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM site_settings")
        }


def get_room_images() -> dict[str, str]:
    with db() as conn:
        return {
            row["room"]: row["filename"]
            for row in conn.execute("SELECT room, filename FROM room_images")
        }



def pricing_data():
    with db() as c:
        prices={r["room"]:dict(r) for r in c.execute("SELECT * FROM room_prices")}
        discounts={r["key"]:dict(r) for r in c.execute("SELECT * FROM discounts")}
        extras={r["key"]:dict(r) for r in c.execute("SELECT * FROM extras")}
        seasons=[dict(r) for r in c.execute("SELECT * FROM seasons ORDER BY start_date")]
    return prices,discounts,extras,seasons

def is_high(day):
    with db() as c:
        for r in c.execute("SELECT start_date,end_date FROM seasons"):
            if parse_date(r["start_date"])<=day<=parse_date(r["end_date"]): return True
    return False

def price_breakdown(room,arrival,departure,adults,chosen,coupon_code=""):
    prices,discounts,extras,seasons=pricing_data(); n=(departure-arrival).days; cur=arrival; room_total=0
    while cur<departure:
        p=prices[room]["high"] if is_high(cur) else (prices[room]["weekend"] if cur.weekday() in (4,5) else prices[room]["standard"])
        room_total+=float(p); cur+=timedelta(days=1)
    extra_total=0; lines=[]
    for k,v in chosen.items():
        if v and k in extras and extras[k]["enabled"]:
            e=extras[k]; amount=float(e["price"])*(adults*n if e["unit"]=="person_night" else n if e["unit"]=="night" else 1); extra_total+=amount; lines.append({"label":e["label"],"amount":round(amount,2)})
    subtotal=room_total+extra_total; applied=[]
    opts=[]
    for k in ("three_nights","five_nights","seven_nights"):
        d=discounts[k]
        if d["enabled"] and n>=d["min_nights"]: opts.append((d["percent"],k))
    keys=[max(opts)[1]] if opts else []
    days=(arrival-date.today()).days
    if discounts["last_minute"]["enabled"] and 0<=days<=discounts["last_minute"]["days_before"]: keys.append("last_minute")
    if discounts["early_bird"]["enabled"] and days>=discounts["early_bird"]["days_before"]: keys.append("early_bird")
    if discounts["direct_booking"]["enabled"]: keys.append("direct_booking")
    for k in keys:
        d=discounts[k]; amt=subtotal*float(d["percent"])/100; subtotal-=amt; applied.append({"label":k.replace("_"," ").title(),"percent":d["percent"],"amount":round(amt,2)})
    coupon_code=(coupon_code or "").strip().upper()
    if coupon_code:
        today_iso=date.today().isoformat()
        with db() as c:
            coupon=c.execute("SELECT * FROM coupons WHERE code=? AND enabled=1",(coupon_code,)).fetchone()
        if coupon and (not coupon["valid_from"] or today_iso>=coupon["valid_from"]) and (not coupon["valid_to"] or today_iso<=coupon["valid_to"]):
            amt=subtotal*float(coupon["percent"])/100
            subtotal-=amt
            applied.append({"label":f"Gutschein {coupon_code}","percent":coupon["percent"],"amount":round(amt,2)})
    return {"nights":n,"room_total":round(room_total,2),"extras":lines,"discounts":applied,"total":round(subtotal,2)}

def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start < b_end and b_start < a_end


def room_available_in_conn(conn: sqlite3.Connection, room: str, arrival: date, departure: date) -> tuple[bool, str]:
    local = conn.execute(
        """
        SELECT arrival, departure FROM bookings
        WHERE room = ? AND status IN ('pending', 'confirmed')
        """,
        (room,),
    ).fetchall()
    external = conn.execute(
        "SELECT start_date, end_date FROM external_blocks WHERE room = ?",
        (room,),
    ).fetchall()

    for row in local:
        if overlaps(arrival, departure, parse_date(row["arrival"]), parse_date(row["departure"])):
            return False, "Das Zimmer ist durch eine Direktbuchung belegt."

    for row in external:
        if overlaps(arrival, departure, parse_date(row["start_date"]), parse_date(row["end_date"])):
            return False, "Das Zimmer ist über Booking.com/iCal belegt."

    return True, "Das Zimmer ist verfügbar."


def room_available(room: str, arrival: date, departure: date) -> tuple[bool, str]:
    if room not in ROOMS:
        return False, "Unbekanntes Zimmer."
    if departure <= arrival:
        return False, "Die Abreise muss nach der Anreise liegen."
    if arrival < ROOMS[room]["available_from"]:
        return False, f"{room} ist erst ab {ROOMS[room]['available_from'].strftime('%d.%m.%Y')} buchbar."
    if app.extensions.get("v6_maintenance_conflict"):
        conflict, reason = app.extensions["v6_maintenance_conflict"](room, arrival, departure)
        if conflict:
            return False, f"Das Zimmer ist wegen {reason} gesperrt."

    with db() as conn:
        return room_available_in_conn(conn, room, arrival, departure)

def calculate_total(room: str, arrival: date, departure: date, adults: int, breakfast: bool) -> float:
    return price_breakdown(room,arrival,departure,adults,{"breakfast":breakfast})["total"]



def unfold_ical(text: str) -> list[str]:
    source = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in source:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def parse_ical_date(value: str) -> date | None:
    value = value.strip().split("T", 1)[0][:8]
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def parse_ical(text: str) -> list[dict]:
    events: list[dict] = []
    current: dict | None = None

    for line in unfold_ical(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if current.get("start") and current.get("end"):
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0]
            if key == "DTSTART":
                current["start"] = parse_ical_date(value)
            elif key == "DTEND":
                current["end"] = parse_ical_date(value)
            elif key == "UID":
                current["uid"] = value.strip()
            elif key == "SUMMARY":
                current["summary"] = value.strip()

    return events


def sync_room(room: str) -> tuple[int, str]:
    with db() as conn:
        row = conn.execute(
            "SELECT import_url FROM ical_settings WHERE room = ?", (room,)
        ).fetchone()

    url = (row["import_url"] if row else "").strip()
    now = datetime.now().isoformat(timespec="seconds")

    if not url:
        with db() as conn:
            conn.execute(
                "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
                (now, "Kein Link hinterlegt", room),
            )
        return 0, "Kein Link hinterlegt."

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Zuhause-am-Bach-iCal/3.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
        events = parse_ical(text)

        with db() as conn:
            conn.execute(
                "DELETE FROM external_blocks WHERE room=? AND source='booking_ical'",
                (room,),
            )
            for event in events:
                conn.execute(
                    """
                    INSERT INTO external_blocks
                    (room, start_date, end_date, source, uid, summary, imported_at)
                    VALUES (?, ?, ?, 'booking_ical', ?, ?, ?)
                    """,
                    (
                        room,
                        event["start"].isoformat(),
                        event["end"].isoformat(),
                        event.get("uid", ""),
                        event.get("summary", "Booking.com"),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
                (now, f"{len(events)} Termine importiert", room),
            )
        return len(events), "Synchronisierung erfolgreich."
    except Exception as exc:
        with db() as conn:
            conn.execute(
                "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
                (now, f"Fehler: {exc}", room),
            )
        return 0, f"Fehler: {exc}"


app.extensions["zab_sync_room"] = sync_room


ROLE_ALLOWED_PREFIXES = {
    "staff": (
        "/host", "/heute", "/assistent", "/fruehstueck", "/reinigung",
        "/smart", "/os", "/admin/dashboard", "/system-test",
    ),
    "housekeeping": (
        "/host", "/heute", "/assistent", "/fruehstueck", "/reinigung",
        "/smart/laundry",
    ),
    "accounting": (
        "/os/finance", "/os/status.json", "/admin/dashboard",
        "/admin/export", "/admin/statistics", "/quality/report.json",
    ),
}


def staff_path_allowed(role: str, path: str) -> bool:
    if role == "manager":
        return True
    for prefix in ROLE_ALLOWED_PREFIXES.get(role, ()):
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def require_admin(*roles: str) -> bool:
    if session.get("admin"):
        return True
    role = session.get("role", "")
    if not role or not session.get("staff_user_id"):
        return False
    if roles:
        return role in roles
    return staff_path_allowed(role, request.path)


@app.context_processor
def globals_for_templates():
    return {
        "rooms": ROOMS,
        "paypal_email": PAYPAL_EMAIL,
        "guest_app_url": GUEST_APP_URL,
        "breakfast_price": BREAKFAST_PRICE,
        "room_release_date": ROOM_RELEASE_DATE,
        "extras": pricing_data()[2],
        "price_settings": pricing_data()[0],
    }


@app.get("/")
def index():
    return render_template(
        "index.html",
        today=date.today().isoformat(),
        settings=get_settings(),
        room_images=get_room_images(),
        price_settings=pricing_data()[0], discounts=pricing_data()[1], extras_cfg=pricing_data()[2], seasons=pricing_data()[3],
    )


@app.post("/api/availability")
def api_availability():
    try:
        room = request.form["room"]
        arrival = parse_date(request.form["arrival"])
        departure = parse_date(request.form["departure"])
        adults = max(1, min(2, int(request.form.get("adults", "2"))))
        breakfast = request.form.get("breakfast") == "true"
        chosen={k:request.form.get(k)=="true" for k in ("breakfast","jause","luggage","dog","baby_bed")}
        coupon_code=request.form.get("coupon_code","")
    except (KeyError, ValueError):
        return jsonify(available=False, message="Bitte gültige Reisedaten eingeben."), 400

    ok, message = room_available(room, arrival, departure)
    return jsonify(
        available=ok,
        message=message,
        total=price_breakdown(room,arrival,departure,adults,chosen,coupon_code)["total"] if ok else None,
        breakdown=price_breakdown(room,arrival,departure,adults,chosen,coupon_code) if ok else None,
        nights=(departure-arrival).days if departure>arrival else 0,
    )


@app.get("/api/calendar")
def api_calendar():
    room = request.args.get("room", "Bachblick")
    year = int(request.args.get("year", date.today().year))
    month = int(request.args.get("month", date.today().month))

    if room not in ROOMS:
        return jsonify(error="Unbekanntes Zimmer"), 400

    first = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)

    states = {}
    current = first
    while current < next_month:
        states[current.isoformat()] = "free"
        current += timedelta(days=1)

    if first < ROOMS[room]["available_from"]:
        current = first
        while current < min(next_month, ROOMS[room]["available_from"]):
            states[current.isoformat()] = "unreleased"
            current += timedelta(days=1)

    with db() as conn:
        local = conn.execute(
            """
            SELECT arrival, departure, status FROM bookings
            WHERE room=? AND status IN ('pending','confirmed')
            """,
            (room,),
        ).fetchall()
        external = conn.execute(
            "SELECT start_date, end_date FROM external_blocks WHERE room=?",
            (room,),
        ).fetchall()

    for row in external:
        start, end = parse_date(row["start_date"]), parse_date(row["end_date"])
        current = max(first, start)
        while current < min(next_month, end):
            states[current.isoformat()] = "booking"
            current += timedelta(days=1)

    for row in local:
        start, end = parse_date(row["arrival"]), parse_date(row["departure"])
        current = max(first, start)
        state = "direct" if row["status"] == "confirmed" else "pending"
        while current < min(next_month, end):
            states[current.isoformat()] = state
            current += timedelta(days=1)

    return jsonify(room=room, year=year, month=month, days=states)


@app.post("/book")
def book():
    try:
        room = request.form["room"]
        arrival = parse_date(request.form["arrival"])
        departure = parse_date(request.form["departure"])
        adults = max(1, min(2, int(request.form["adults"])))
        breakfast = request.form.get("breakfast") == "on"
        chosen={k:request.form.get(k)=="on" for k in ("breakfast","jause","luggage","dog","baby_bed")}
        coupon_code=request.form.get("coupon_code","")
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()
        payment_method = request.form["payment_method"]
    except (KeyError, ValueError):
        flash("Bitte alle Pflichtfelder korrekt ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    ok, message = room_available(room, arrival, departure)
    if not ok:
        flash(message, "error")
        return redirect(url_for("index") + "#booking")

    if not all([first_name, last_name, email, phone]):
        flash("Bitte Name, E-Mail und Telefonnummer ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    total = price_breakdown(room,arrival,departure,adults,chosen,coupon_code)["total"]
    uid = f"ZAB-{uuid4()}@zuhause-am-bach"

    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        ok, message = room_available_in_conn(conn, room, arrival, departure)
        if not ok:
            flash(message, "error")
            return redirect(url_for("index") + "#booking")
        cur = conn.execute(
            """
            INSERT INTO bookings
            (uid, room, arrival, departure, adults, breakfast, first_name,
             last_name, email, phone, message, payment_method, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                uid, room, arrival.isoformat(), departure.isoformat(), adults,
                1 if breakfast else 0, first_name, last_name, email, phone,
                request.form.get("message", "").strip(), payment_method, total,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        booking_id = cur.lastrowid
    if app.extensions.get("zab_ensure_tokens"):
        app.extensions["zab_ensure_tokens"](booking_id)
    if app.extensions.get("v6_ensure_checkin_token"):
        app.extensions["v6_ensure_checkin_token"](booking_id)
    if app.extensions.get("zab_send_confirmation"):
        try:
            app.extensions["zab_send_confirmation"](booking_id)
        except Exception:
            pass

    return render_template(
        "success.html",
        booking={
            "room": room,
            "arrival": arrival,
            "departure": departure,
            "adults": adults,
            "breakfast": breakfast,
            "payment_method": payment_method,
            "total": total,
            "first_name": first_name,
        },
        settings=get_settings(),
    )


@app.get("/calendar/<room>.ics")
def export_calendar(room: str):
    if room not in ROOMS:
        return "Zimmer nicht gefunden", 404

    with db() as conn:
        rows = conn.execute(
            """
            SELECT uid, arrival, departure FROM bookings
            WHERE room=? AND status IN ('pending','confirmed')
            ORDER BY arrival
            """,
            (room,),
        ).fetchall()

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Zuhause am Bach//Direktbuchung Pro//DE",
        "CALSCALE:GREGORIAN",
    ]
    for row in rows:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{row['uid']}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{parse_date(row['arrival']).strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{parse_date(row['departure']).strftime('%Y%m%d')}",
                "SUMMARY:Belegt - Direktbuchung",
                "TRANSP:OPAQUE",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")

    return Response(
        "\r\n".join(lines) + "\r\n",
        mimetype="text/calendar",
        headers={"Content-Disposition": f'inline; filename="{room}.ics"'},
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        now = datetime.now()
        lock_until_raw = session.get("admin_lock_until", "")
        if lock_until_raw:
            try:
                lock_until = datetime.fromisoformat(lock_until_raw)
            except ValueError:
                lock_until = now
            if lock_until > now:
                flash("Zu viele Fehlversuche. Bitte kurz warten.", "error")
                return render_template("admin_login.html")

        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session.clear()
            session["admin"] = True
            session["role"] = "admin"
            return redirect(url_for("smart_dashboard"))
        failed = int(session.get("admin_failed_logins", 0)) + 1
        session["admin_failed_logins"] = failed
        if failed >= 5:
            session["admin_lock_until"] = (now + timedelta(minutes=10)).isoformat(timespec="seconds")
            session["admin_failed_logins"] = 0
        flash("Falsches Passwort.", "error")
    return render_template("admin_login.html")


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/admin")
def admin():
    if not require_admin():
        return redirect(url_for("admin_login"))

    with db() as conn:
        bookings = conn.execute(
            "SELECT * FROM bookings ORDER BY arrival, room"
        ).fetchall()
        ical = conn.execute(
            "SELECT * FROM ical_settings ORDER BY room"
        ).fetchall()

    prices, discounts, extras_cfg, seasons = pricing_data()
    return render_template(
        "admin.html",
        bookings=bookings,
        ical=ical,
        settings=get_settings(),
        room_images=get_room_images(),
        price_settings=prices,
        discounts=discounts,
        extras_cfg=extras_cfg,
        seasons=seasons,
    )


@app.post("/admin/ical")
def admin_ical():
    if not require_admin():
        return redirect(url_for("admin_login"))

    with db() as conn:
        for room in ROOMS:
            conn.execute(
                "UPDATE ical_settings SET import_url=? WHERE room=?",
                (request.form.get(f"ical_{room}", "").strip(), room),
            )
    flash("iCal-Links gespeichert.", "success")
    return redirect(url_for("admin"))


@app.post("/admin/sync")
def admin_sync():
    if not require_admin():
        return redirect(url_for("admin_login"))

    results = []
    for room in ROOMS:
        count, message = sync_room(room)
        results.append(f"{room}: {count} Termine")
    flash("Synchronisierung: " + " · ".join(results), "success")
    return redirect(url_for("admin"))


@app.post("/admin/booking/<int:booking_id>/<action>")
def admin_booking_action(booking_id: int, action: str):
    if not require_admin():
        return redirect(url_for("admin_login"))

    mapping = {"confirm": "confirmed", "cancel": "cancelled", "pending": "pending"}
    if action not in mapping:
        return "Ungültige Aktion", 400

    with db() as conn:
        conn.execute(
            "UPDATE bookings SET status=? WHERE id=?",
            (mapping[action], booking_id),
        )
    flash("Buchungsstatus aktualisiert.", "success")
    return redirect(url_for("admin"))


@app.post("/admin/settings")
def admin_settings():
    if not require_admin():
        return redirect(url_for("admin_login"))

    allowed = {
        "google_rating",
        "google_review_count",
        "google_review_url",
        "phone",
        "email",
        "address",
        "cancellation_text",
    }
    with db() as conn:
        for key in allowed:
            if key in request.form:
                conn.execute(
                    "UPDATE site_settings SET value=? WHERE key=?",
                    (request.form[key].strip(), key),
                )
    flash("Seiteneinstellungen gespeichert.", "success")
    return redirect(url_for("admin"))


@app.post("/admin/room-image/<room>")
def admin_room_image(room: str):
    if not require_admin():
        return redirect(url_for("admin_login"))
    if room not in ROOMS:
        return "Unbekanntes Zimmer", 404

    upload = request.files.get("image")
    if not upload or not upload.filename:
        flash("Bitte eine Bilddatei auswählen.", "error")
        return redirect(url_for("admin"))

    ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        flash("Erlaubt sind JPG, PNG und WEBP.", "error")
        return redirect(url_for("admin"))

    filename = secure_filename(f"{room.lower()}.{ext}")
    ROOM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    upload.save(ROOM_IMAGE_DIR / filename)

    with db() as conn:
        conn.execute(
            "UPDATE room_images SET filename=? WHERE room=?",
            (filename, room),
        )
    flash(f"Zimmerbild für {room} aktualisiert.", "success")
    return redirect(url_for("admin"))

@app.post("/admin/prices")
def admin_prices():
    if not require_admin(): return redirect(url_for("admin_login"))
    with db() as c:
        for r in ROOMS: c.execute("UPDATE room_prices SET standard=?,weekend=?,high=? WHERE room=?",(float(request.form[f"{r}_standard"]),float(request.form[f"{r}_weekend"]),float(request.form[f"{r}_high"]),r))
    flash("Preise gespeichert.","success"); return redirect(url_for("admin"))

@app.post("/admin/discounts")
def admin_discounts():
    if not require_admin(): return redirect(url_for("admin_login"))
    _,ds,_,_=pricing_data()
    with db() as c:
        for k,d in ds.items(): c.execute("UPDATE discounts SET enabled=?,percent=?,min_nights=?,days_before=? WHERE key=?",(1 if request.form.get(k+"_enabled") else 0,float(request.form.get(k+"_percent",d["percent"])),int(request.form.get(k+"_min_nights",d["min_nights"])),int(request.form.get(k+"_days_before",d["days_before"])),k))
    flash("Rabatte gespeichert.","success"); return redirect(url_for("admin"))

@app.post("/admin/extras")
def admin_extras():
    if not require_admin(): return redirect(url_for("admin_login"))
    _,_,es,_=pricing_data()
    with db() as c:
        for k,e in es.items(): c.execute("UPDATE extras SET label=?,price=?,unit=?,enabled=? WHERE key=?",(request.form[k+"_label"],float(request.form[k+"_price"]),request.form[k+"_unit"],1 if request.form.get(k+"_enabled") else 0,k))
    flash("Zusatzleistungen gespeichert.","success"); return redirect(url_for("admin"))

@app.post("/admin/seasons/add")
def add_season():
    if not require_admin(): return redirect(url_for("admin_login"))
    with db() as c: c.execute("INSERT INTO seasons(name,start_date,end_date) VALUES(?,?,?)",(request.form["name"],request.form["start_date"],request.form["end_date"]))
    return redirect(url_for("admin"))

@app.post("/admin/seasons/<int:i>/delete")
def del_season(i):
    if not require_admin(): return redirect(url_for("admin_login"))
    with db() as c: c.execute("DELETE FROM seasons WHERE id=?",(i,))
    return redirect(url_for("admin"))


init_db()
init_addons(app, DB_PATH, db, require_admin, ROOMS, PAYPAL_EMAIL)
init_v6(app, DB_PATH, db, require_admin, ROOMS)
init_stability(app, DB_PATH, db, require_admin, ROOMS)
init_zab_os(app, DB_PATH, db, require_admin, ROOMS)
init_host_assistant(app, db, require_admin, ROOMS)
init_smart_host(app, db, require_admin, ROOMS)
init_knowledge(app, DB_PATH, db, require_admin, ROOMS)
init_quality_v12(app, DB_PATH, db, require_admin, ROOMS)
init_alltag(app, db, require_admin, ROOMS)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "0") == "1")

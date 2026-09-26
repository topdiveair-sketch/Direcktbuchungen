
from __future__ import annotations

import os
import base64
import json
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

def format_iban(value: str) -> str:
    clean = "".join(ch for ch in (value or "") if ch.isalnum()).upper()
    return " ".join(clean[i:i+4] for i in range(0, len(clean), 4))


def public_room_name(room: str) -> str:
    return "Gartenzimmer" if room == "Bachblick" else room


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
GUEST_APP_URL = os.environ.get("GUEST_APP_URL", "https://topdiveair-sketch.github.io/Gaeste/")
ROOM_RELEASE_DATE = date(2026, 8, 16)
BREAKFAST_PRICE = 12.0

# Ertragsstrategie: starke, offiziell bestätigte Wachau-Termine werden nicht
# rabattiert, sondern mit einem transparenten Eventfaktor bepreist.
# factor 1.15 = +15 %, 1.25 = +25 %, 1.35 = +35 %.
EVENT_PRICING = (
    (date(2026, 11, 19), date(2026, 12, 24), "Kremser Adventzauber", 1.15, 159.0, 1),
    (date(2027, 3, 26), date(2027, 3, 28), "Kremser Marillenblütenmarkt", 1.15, 169.0, 1),
    (date(2027, 4, 2), date(2027, 4, 4), "Kremser Marillenblütenmarkt", 1.15, 169.0, 1),
    (date(2027, 6, 19), date(2027, 6, 20), "Wachauer Sonnenwende", 1.35, 179.0, 2),
    (date(2027, 7, 8), date(2027, 7, 26), "ALLES MARILLE!", 1.25, 169.0, 1),
    (date(2027, 8, 26), date(2027, 9, 6), "Wachauer Volksfest", 1.15, 169.0, 1),
    (date(2028, 6, 17), date(2028, 6, 18), "Wachauer Sonnenwende", 1.35, 179.0, 2),
)


def event_pricing_for_day(day: date):
    for start, end_exclusive, name, factor, cap, min_nights in EVENT_PRICING:
        if start <= day < end_exclusive:
            # Bei ALLES MARILLE! gilt der 2-Nächte-Mindestaufenthalt nur
            # für Freitag/Samstag-Nächte, nicht pauschal für Werktage.
            if name == "ALLES MARILLE!" and day.weekday() in (4, 5):
                min_nights = 2
            if name == "Kremser Adventzauber":
                # Adventpreis nur an den nachfragestarken Wochenendtagen.
                if day.weekday() not in (4, 5, 6):
                    return None
                min_nights = 2
            return {
                "name": name,
                "factor": factor,
                "cap": cap,
                "min_nights": min_nights,
            }
    return None


def minimum_stay_for_period(arrival: date, departure: date):
    required = 1
    reasons = []
    cur = arrival
    while cur < departure:
        event = event_pricing_for_day(cur)
        if event and int(event["min_nights"]) > required:
            required = int(event["min_nights"])
        if event and int(event["min_nights"]) > 1 and event["name"] not in reasons:
            reasons.append(str(event["name"]))
        cur += timedelta(days=1)
    return required, reasons

ROOMS = {
    "Bachblick": {
        "price": 99.0,
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
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bookings)")}
        if "idempotency_key" not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN idempotency_key TEXT DEFAULT ''")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_idempotency "
            "ON bookings(idempotency_key) WHERE idempotency_key <> ''"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS site_events(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   event TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )

        conn.execute(
            """UPDATE bookings
               SET status='inquiry'
               WHERE status='pending'
                 AND payment_method IN ('Banküberweisung','Vor Ort')"""
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
            "email": "Zuhause.am.Bach@outlook.com",
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
        price_defaults={"Bachblick":(99,109,119),"Marillenzimmer":(90,100,110),"Weinbergzimmer":(90,100,110),"Donauzimmer":(90,100,110)}
        for r,p in price_defaults.items(): conn.execute("INSERT OR IGNORE INTO room_prices VALUES(?,?,?,?)",(r,*p))
        conn.execute("UPDATE room_prices SET standard=99, weekend=109, high=119 WHERE room='Bachblick' AND standard<99")
        for row in [("last_minute",1,10,0,3),("early_bird",0,5,0,60),("three_nights",1,5,3,0),("five_nights",1,8,5,0),("seven_nights",1,12,7,0),("direct_booking",1,3,0,0)]: conn.execute("INSERT OR IGNORE INTO discounts VALUES(?,?,?,?,?)",row)
        # Einmalige Umstellung auf Knappheits-/Ertragsstrategie:
        # keine Last-Minute-, Frühbucher- oder Aufenthaltsrabatte; nur der
        # wirtschaftlich sinnvolle Direktbuchungsvorteil bleibt aktiv.
        scarcity_done = conn.execute(
            "SELECT value FROM site_settings WHERE key='scarcity_revenue_v1_applied'"
        ).fetchone()
        if not scarcity_done:
            conn.execute(
                "UPDATE discounts SET enabled=0 WHERE key IN "
                "('last_minute','early_bird','three_nights','five_nights','seven_nights')"
            )
            conn.execute(
                "UPDATE discounts SET enabled=1, percent=3 WHERE key='direct_booking'"
            )
            conn.execute(
                "INSERT OR REPLACE INTO site_settings(key,value) VALUES "
                "('scarcity_revenue_v1_applied','1')"
            )
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
        event = event_pricing_for_day(cur)
        if event:
            p = min(float(p) * float(event["factor"]), float(event["cap"]))
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


MASTER_CALENDAR_URL = "https://web-production-907d68.up.railway.app/api/direct-booking-calendar"

def live_master_availability(arrival: date, departure: date) -> tuple[bool | None, str]:
    """Return True=free, False=blocked, None=live check unavailable."""
    try:
        req = urllib.request.Request(
            MASTER_CALENDAR_URL,
            headers={"Cache-Control": "no-cache", "User-Agent": "ZAB-Homepage/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        events = payload.get("events")
        if payload.get("ok") is not True or not isinstance(events, list):
            return None, "Live-Kalender konnte nicht bestätigt werden."
        for event in events:
            if not event.get("start") or not event.get("end"):
                continue
            start_d = parse_date(str(event["start"])[:10])
            end_d = parse_date(str(event["end"])[:10])
            if overlaps(arrival, departure, start_d, end_d):
                return False, "Das Gartenzimmer ist in diesem Zeitraum bereits belegt."
        return True, "Das Gartenzimmer ist laut Live-Kalender verfügbar."
    except Exception:
        return None, "Live-Kalender derzeit nicht erreichbar. Bitte Termin später erneut prüfen oder direkt anfragen."


def room_available(room: str, arrival: date, departure: date) -> tuple[bool, str]:
    if room != "Bachblick":
        return False, "Unbekanntes Zimmer."
    if departure <= arrival:
        return False, "Die Abreise muss nach der Anreise liegen."
    min_nights, min_reasons = minimum_stay_for_period(arrival, departure)
    actual_nights = (departure - arrival).days
    if actual_nights < min_nights:
        reason = " / ".join(min_reasons) if min_reasons else "starker Nachfragezeitraum"
        return False, f"Für {reason} gilt ein Mindestaufenthalt von {min_nights} Nächten."
    if arrival < ROOMS[room]["available_from"]:
        return False, "Das Gartenzimmer ist für diesen Zeitraum nicht buchbar."
    if app.extensions.get("v6_maintenance_conflict"):
        conflict, reason = app.extensions["v6_maintenance_conflict"](room, arrival, departure)
        if conflict:
            return False, f"Das Gartenzimmer ist wegen {reason} gesperrt."

    # Booking/iCal ist die unabhängige Sicherheitsquelle. Vor jeder
    # Verfügbarkeitsprüfung frisch synchronisieren, damit eine neue
    # Booking-Sperre nie durch einen leeren/stalen Masterkalender als frei gilt.
    sync_room(room)

    live_ok, live_message = live_master_availability(arrival, departure)
    if live_ok is None:
        return False, live_message
    if live_ok is False:
        return False, live_message

    with db() as conn:
        local_ok, local_message = room_available_in_conn(conn, room, arrival, departure)
    if not local_ok:
        return False, local_message
    return True, live_message

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


@app.get("/media/gartenblick.jpg")
def gartenblick_image():
    # Compatibility endpoint for older links. The room image is now stored
    # as a normal static asset, avoiding runtime reconstruction from removed
    # base64 fragment files.
    response = app.send_static_file("images/rooms/bachblick.jpg")
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.get("/")
def index():
    response = Response(render_template(
        "index.html",
        today=date.today().isoformat(),
        booking_horizon_year=date.today().year + 2,
        settings=get_settings(),
        room_images=get_room_images(),
        rooms={"Bachblick": ROOMS["Bachblick"]},
        price_settings=pricing_data()[0], discounts=pricing_data()[1], extras_cfg=pricing_data()[2], seasons=pricing_data()[3],
        bank_account_holder=env_value("BANK_ACCOUNT_HOLDER"),
        bank_iban=env_value("BANK_IBAN"),
        bank_iban_display=format_iban(env_value("BANK_IBAN")),
        paypal_email=PAYPAL_EMAIL,
    ))
    # Preview/Homepage immer frisch ausliefern, damit alte Zimmertexte nicht aus dem Browser-Cache kommen.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


PUBLIC_HOME_LANGUAGES = ("en", "cs", "sk", "hu", "es", "fr")


def _public_home_translations() -> dict:
    """Load curated public homepage translations shipped with the repository."""
    path = BASE / "translations" / "public_home.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@app.get("/<lang>/")
def localized_public_home(lang: str):
    """Serve real localized landing pages instead of letting language URLs 404."""
    lang = (lang or "").lower()
    if lang not in PUBLIC_HOME_LANGUAGES:
        return Response("Not found", status=404)

    translations = _public_home_translations()
    copy = translations.get(lang)
    if not isinstance(copy, dict):
        return redirect(url_for("index"), code=302)

    response = Response(render_template(
        "localized_home.html",
        lang=lang,
        t=copy,
        supported_languages=("de",) + PUBLIC_HOME_LANGUAGES,
    ))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def activity_landing_context(kind: str) -> dict:
    horizon = date.today().year + 2
    if kind == "bike":
        return {
            "kind": "bike",
            "page_title": "Donauradweg Unterkunft Wachau | Zuhause am Bach Aggsbach",
            "meta_description": "Donauradweg Unterkunft Wachau: auch 1 Nacht möglich. Sichere Fahrradunterbringung, E-Bike laden, Frühstück und Gepäcktransport in Aggsbach Markt.",
            "canonical": "https://www.zuhauseambach-wachau.at/unterkunft-donauradweg-wachau",
            "eyebrow": "Donauradweg Wachau · Aggsbach Markt",
            "headline": "Unterkunft am Donauradweg in der Wachau",
            "intro": "Zuhause am Bach ist ein ruhiger Etappenstopp in Aggsbach Markt für Radreisende in der Wachau. Auch eine einzelne Übernachtung für 1 Nacht ist grundsätzlich möglich – mit sicherer Fahrradunterbringung, E-Bike-Lademöglichkeit und persönlichem Kontakt.",
            "benefits": [
                "Sichere Unterbringung für Fahrräder",
                "E-Bike-Lademöglichkeit",
                "Frühstück auf Wunsch",
                "Trocknungsmöglichkeit für Radbekleidung",
                "Gepäcktransport auf Anfrage",
                "Persönliche Tipps für die nächste Wachau-Etappe",
            ],
            "planning_title": "Radetappe früh sichern – bis %s planbar" % horizon,
            "planning_text": "Beliebte Wochenenden und starke Wachau-Termine werden früh nachgefragt. Deshalb können Radreisende ihre Übernachtung bei uns weit im Voraus anfragen, statt erst wenige Wochen vor der Tour zu suchen.",
            "cta": "Donauradweg-Termin direkt prüfen",
            "audience": "Radfahrer und E-Bike-Reisende",
        }
    return {
        "kind": "hike",
        "page_title": "Welterbesteig Unterkunft Wachau | Zuhause am Bach Aggsbach",
        "meta_description": "Welterbesteig Unterkunft Wachau in Aggsbach Markt: auch 1 Nacht möglich. Frühstück, Gepäcktransport, Etappentipps und ruhige Übernachtung.",
        "canonical": "https://www.zuhauseambach-wachau.at/unterkunft-welterbesteig-wachau",
        "eyebrow": "Welterbesteig Wachau · Aggsbach Markt",
        "headline": "Unterkunft am Welterbesteig Wachau",
        "intro": "Zuhause am Bach ist ein ruhiger Etappenstopp für Wanderer am Welterbesteig Wachau. Auch eine einzelne Übernachtung für 1 Nacht ist grundsätzlich möglich – persönlich, überschaubar und auf die nächste Etappe ausgerichtet.",
        "benefits": [
            "Ruhige Übernachtung in Aggsbach Markt",
            "Frühstück auf Wunsch vor der nächsten Etappe",
            "Trocknungsmöglichkeit für Wanderbekleidung",
            "Gepäcktransport auf Anfrage",
            "Persönliche Etappen- und Wachau-Tipps",
            "Wachau-Etappenstempel als Haussouvenir",
        ],
        "planning_title": "Wanderetappe früh sichern – bis %s planbar" % horizon,
        "planning_text": "Gerade an beliebten Wanderwochenenden ist ein kleiner Betrieb schnell ausgebucht. Deshalb nehmen wir Anfragen für den Welterbesteig bewusst weit im Voraus an.",
        "cta": "Welterbesteig-Termin direkt prüfen",
        "audience": "Wanderer und Etappengäste",
    }


def seo_landing_context(slug: str) -> dict:
    common_features = [
        ("⌂", "Aggsbach Markt", "Ruhige Basis am nördlichen Wachauufer."),
        ("🍳", "Frühstück auf Wunsch", "Vegetarisch oder vegan nach Absprache."),
        ("🧳", "Gepäcktransport", "Für Etappengäste auf Anfrage."),
        ("📅", "Direkt planen", "Verfügbarkeit bis %s prüfen." % (date.today().year + 2)),
    ]
    faq_direct = [
        {"@type":"Question","name":"Kann ich direkt bei Zuhause am Bach buchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Verfügbarkeit, Preis und Zusatzleistungen können auf der offiziellen Website direkt geprüft werden."}},
        {"@type":"Question","name":"Kann ich in der Wachau bei Zuhause am Bach nur 1 Nacht übernachten?","acceptedAnswer":{"@type":"Answer","text":"Ja. Eine Übernachtung für nur eine Nacht ist grundsätzlich möglich, sofern der Termin verfügbar ist. An einzelnen stark nachgefragten Veranstaltungsterminen können abweichende Mindestaufenthalte gelten."}},
        {"@type":"Question","name":"Wie weit im Voraus kann ich planen?","acceptedAnswer":{"@type":"Answer","text":"Zuhause am Bach kommuniziert aktuell einen Planungshorizont bis %s." % (date.today().year + 2)}},
    ]
    pages = {
        "wachau": {
            "title":"Unterkunft Wachau zwischen Melk und Krems | Zuhause am Bach",
            "description":"Persönliche Unterkunft in der Wachau zwischen Melk und Krems: Aggsbach Markt, Donauradweg, Welterbesteig, Frühstück und Direktbuchung bei Zuhause am Bach.",
            "canonical":"https://www.zuhauseambach-wachau.at/unterkunft-wachau",
            "h1":"Unterkunft in der Wachau zwischen Melk und Krems",
            "lead":"Zuhause am Bach ist eine kleine, persönliche Unterkunft in Aggsbach Markt – ruhig zwischen Melk und Krems gelegen und praktisch für Donauradweg, Welterbesteig und Wachau-Ausflüge.",
            "eyebrow":"Wachau direkt erleben",
            "subheading":"Kleine Unterkunft statt anonymer Bettenburg",
            "paragraphs":["Das Gartenzimmer ist für maximal zwei Gäste gedacht und liegt in Aggsbach Markt am nördlichen Wachauufer.","Donauradweg und Welterbesteig lassen sich mit persönlichen Tipps, Frühstück auf Wunsch und direktem Gastgeberkontakt verbinden.","Wer starke Wochenenden oder Veranstaltungen bereits kennt, kann seinen Termin früh direkt prüfen."],
            "features":common_features,
            "hero_image":"images/gartenzimmer-04-web.jpg","hero_image_alt":"Gartenzimmer bei Zuhause am Bach in Aggsbach Markt","hero_image_caption":"Das direkt angebotene Gartenzimmer.",
            "secondary_image":"images/bach-hinterm-haus-v11.webp","secondary_image_alt":"Bach hinter Zuhause am Bach in Aggsbach Markt","secondary_image_caption":"Ruhige Wege beginnen direkt hinter dem Haus.",
            "faq":faq_direct,
        },
        "aggsbach": {
            "title":"Übernachten Aggsbach Markt | Zuhause am Bach Wachau",
            "description":"Übernachten in Aggsbach Markt: auch 1 Nacht möglich. Ruhiges Gartenzimmer für Donauradweg, Welterbesteig, Frühstück und Direktbuchung bei Zuhause am Bach.",
            "canonical":"https://www.zuhauseambach-wachau.at/uebernachten-aggsbach-markt",
            "h1":"Übernachten in Aggsbach Markt",
            "lead":"Zuhause am Bach bietet eine persönliche Übernachtungsmöglichkeit direkt in Aggsbach Markt – auch für nur 1 Nacht, ideal für Wanderer, Radfahrer und Etappengäste.",
            "eyebrow":"Aggsbach Markt · Wachau",
            "subheading":"Direkt im Ort schlafen und die Wachau weiterziehen",
            "paragraphs":["Aggsbach Markt ist ein ruhiger Etappenort am nördlichen Donauufer. Das Gartenzimmer ist aktuell unser direkt angebotenes Zimmer für maximal zwei Personen.","Welterbesteig, Donauradweg und Ausflüge in die Wachau können von hier aus gut kombiniert werden.","Frühstück, Gepäcktransport und persönliche Tipps sind auf Wunsch Teil der Reiseplanung."],
            "features":common_features,
            "hero_image":"images/bach-hinterm-haus-v11.webp","hero_image_alt":"Bach und Weg hinter Zuhause am Bach in Aggsbach Markt","hero_image_caption":"Aggsbach Markt: ruhig ankommen und weiterziehen.",
            "secondary_image":"images/gartenzimmer-04-web.jpg","secondary_image_alt":"Gartenzimmer in Aggsbach Markt","secondary_image_caption":"Das Gartenzimmer für maximal zwei Gäste.",
            "faq":faq_direct,
        },
        "radfahrer": {
            "title":"Radfahrer Unterkunft Wachau | Donauradweg Zuhause am Bach",
            "description":"Radfahrer-Unterkunft in der Wachau: sichere Fahrradunterbringung, E-Bike-Laden, Frühstück, Trocknung und Gepäcktransport in Aggsbach Markt.",
            "canonical":"https://www.zuhauseambach-wachau.at/radfahrer-unterkunft-wachau",
            "h1":"Radfahrer-Unterkunft in der Wachau",
            "lead":"Für Radreisende am Donauradweg bietet Zuhause am Bach einen kleinen, persönlichen Etappenstopp mit sicherer Fahrradunterbringung und E-Bike-Lademöglichkeit.",
            "eyebrow":"Für Radreisende",
            "subheading":"Fahrrad sicher abstellen, laden und am nächsten Morgen weiter",
            "paragraphs":["Fahrräder können geschützt untergebracht werden; für E-Bikes gibt es eine Lademöglichkeit.","Frühstück auf Wunsch, Trocknungsmöglichkeit für Radbekleidung und Gepäcktransport auf Anfrage unterstützen die Etappenreise.","Starke Wachau-Wochenenden können früh knapp werden, weil nur ein Gartenzimmer direkt angeboten wird."],
            "features":[("🚲","Fahrrad sicher","Geschützte Unterbringung."),("⚡","E-Bike laden","Lademöglichkeit am Haus."),("👕","Trocknen","Für nasse Radbekleidung."),("🧳","Gepäcktransport","Auf Anfrage für die nächste Etappe.")],
            "hero_image":"images/donauradweg-web.jpg","hero_image_alt":"Donauradweg bei Zuhause am Bach in der Wachau","hero_image_caption":"Direkt auf Radreisende ausgerichtet.",
            "secondary_image":"images/gartenzimmer-04-web.jpg","secondary_image_alt":"Gartenzimmer für Radfahrer in der Wachau","secondary_image_caption":"Ruhige Nacht zwischen zwei Etappen.",
            "faq":faq_direct,
        },
        "jauerling": {
            "title":"Unterkunft Jauerling Wachau | Zuhause am Bach Aggsbach",
            "description":"Unterkunft nahe Jauerling und Wachau: ruhig in Aggsbach Markt übernachten, wandern, Naturpark erleben und direkt bei Zuhause am Bach buchen.",
            "canonical":"https://www.zuhauseambach-wachau.at/unterkunft-jauerling-wachau",
            "h1":"Unterkunft für Jauerling & Wachau",
            "lead":"Wer Naturpark Jauerling-Wachau, Welterbesteig und Donau verbinden möchte, findet bei Zuhause am Bach eine ruhige Basis in Aggsbach Markt.",
            "eyebrow":"Jauerling · Naturpark · Wachau",
            "subheading":"Natur, Wanderwege und ruhige Übernachtung verbinden",
            "paragraphs":["Zuhause am Bach liegt in Aggsbach Markt und eignet sich als Basis für Ausflüge Richtung Jauerling und für Wanderetappen in der Wachau.","Frühstück auf Wunsch, Trocknungsmöglichkeit und persönliche Tipps sind besonders für aktive Gäste praktisch.","Aktuelle Öffnungs-, Wege- und Saisoninformationen für Ausflugsziele sollten vor der Anreise immer bei den jeweiligen offiziellen Betreibern geprüft werden."],
            "features":common_features,
            "hero_image":"images/welterbesteig-original.jpg","hero_image_alt":"Welterbesteig und Wachau nahe Jauerling","hero_image_caption":"Wandern zwischen Donau und Jauerling.",
            "secondary_image":"images/bach-hinterm-haus-v11.webp","secondary_image_alt":"Ruhiger Bachweg hinter Zuhause am Bach","secondary_image_caption":"Ruhiger Ausgangspunkt in Aggsbach Markt.",
            "faq":faq_direct,
        },
        "winter": {
            "title":"Winterurlaub Wachau | Unterkunft zwischen Melk und Krems",
            "description":"Winterurlaub in der Wachau: ruhig zwischen Melk und Krems in Aggsbach Markt übernachten. Jauerling, Advent, Winterwandern, Frühstück und Direktbuchung.",
            "canonical":"https://www.zuhauseambach-wachau.at/winterurlaub-wachau",
            "h1":"Winterurlaub in der Wachau – ruhig zwischen Melk und Krems",
            "lead":"Zuhause am Bach ist eine kleine Winter-Unterkunft in Aggsbach Markt für Gäste, die Wachau, Jauerling, Advent, Winterwandern und ruhige Tage an der Donau verbinden möchten.",
            "eyebrow":"Winter · Wachau · Jauerling",
            "subheading":"Wintertage in der Wachau mit persönlicher Unterkunft",
            "paragraphs":["Aggsbach Markt liegt ruhig zwischen Melk und Krems und eignet sich als Basis für Winterausflüge in der Wachau und Richtung Jauerling.","Frühstück auf Wunsch und eine Trocknungsmöglichkeit für Outdoorbekleidung machen kurze Winteraufenthalte unkompliziert.","Adventtermine, Winterwanderungen und wetterabhängige Angebote lassen sich über die offiziellen Veranstalter prüfen; die Übernachtung kann direkt bei Zuhause am Bach angefragt werden."],
            "features":[("❄️","Winterbasis","Ruhig zwischen Melk und Krems übernachten."),("🏔️","Jauerling","Winterausflug und Naturpark verbinden."),("🍳","Frühstück","Auf Wunsch vor dem Wintertag."),("📅","Direkt buchen","Preis und freie Termine live prüfen.")],
            "hero_image":"images/bach-hinterm-haus-v11.webp","hero_image_alt":"Winterurlaub Wachau bei Zuhause am Bach in Aggsbach Markt","hero_image_caption":"Ruhige Wachau-Basis zwischen Melk und Krems.",
            "secondary_image":"images/gartenzimmer-04-web.jpg","secondary_image_alt":"Gartenzimmer für Winterurlaub in der Wachau","secondary_image_caption":"Persönlich übernachten und die Wachau im Winter erleben.",
            "faq":faq_direct,
        },
        "ski": {
            "title":"Skifahren Jauerling Unterkunft Wachau | Zuhause am Bach",
            "description":"Winter-Unterkunft für Ausflüge zum Jauerling: in Aggsbach Markt übernachten, aktuelle Liftzeiten offiziell prüfen und direkt bei Zuhause am Bach buchen.",
            "canonical":"https://www.zuhauseambach-wachau.at/skifahren-jauerling-unterkunft-wachau",
            "h1":"Unterkunft für Wintertage am Jauerling",
            "lead":"Zuhause am Bach ist eine ruhige Wachau-Unterkunft für Gäste, die einen Winterausflug Richtung Jauerling mit einer Übernachtung in Aggsbach Markt verbinden möchten.",
            "eyebrow":"Winter in der Wachau",
            "subheading":"Jauerling-Ausflug und ruhige Nacht kombinieren",
            "paragraphs":["Das Gartenzimmer bietet eine kleine, persönliche Basis in Aggsbach Markt.","Winterbetrieb, Liftzeiten, Schnee- und Pistenstatus hängen von Saison und Wetter ab und werden deshalb nicht pauschal versprochen. Bitte vor der Fahrt die offiziellen Jauerling-Informationen prüfen.","Für nasse Outdoorbekleidung gibt es eine Trocknungsmöglichkeit; Frühstück ist auf Wunsch verfügbar."],
            "features":[("❄️","Winterbasis","Ruhig in Aggsbach Markt übernachten."),("👕","Trocknung","Für nasse Outdoorbekleidung."),("🍳","Frühstück","Auf Wunsch vor dem Ausflug."),("📅","Direkt planen","Termin früh prüfen.")],
            "hero_image":"images/welterbesteig-original.jpg","hero_image_alt":"Winter- und Wanderregion Wachau Jauerling","hero_image_caption":"Wachau und Jauerling als Winterausflug verbinden.",
            "secondary_image":"images/gartenzimmer-04-web.jpg","secondary_image_alt":"Gartenzimmer als Winterunterkunft in der Wachau","secondary_image_caption":"Ruhige Übernachtung in Aggsbach Markt.",
            "faq":faq_direct,
        },
    }
    data = pages.get(slug)
    if not data:
        abort(404)
    return data


@app.get("/unterkunft-wachau")
def seo_unterkunft_wachau():
    return render_template("seo_landing.html", **seo_landing_context("wachau"))


@app.get("/uebernachten-aggsbach-markt")
def seo_aggsbach_markt():
    return render_template("seo_landing.html", **seo_landing_context("aggsbach"))


@app.get("/radfahrer-unterkunft-wachau")
def seo_radfahrer_wachau():
    return render_template("seo_landing.html", **seo_landing_context("radfahrer"))


@app.get("/unterkunft-jauerling-wachau")
def seo_jauerling():
    return render_template("seo_landing.html", **seo_landing_context("jauerling"))


@app.get("/skifahren-jauerling-unterkunft-wachau")
def seo_ski_jauerling():
    return render_template("seo_landing.html", **seo_landing_context("ski"))

@app.get("/winterurlaub-wachau")
def seo_winterurlaub_wachau():
    return render_template("seo_landing.html", **seo_landing_context("winter"))


@app.get("/unterkunft-donauradweg-wachau")
def activity_donauradweg():
    return render_template(
        "activity_landing.html",
        **activity_landing_context("bike"),
        booking_horizon_year=date.today().year + 2,
        settings=get_settings(),
    )


@app.get("/unterkunft-welterbesteig-wachau")
def activity_welterbesteig():
    return render_template(
        "activity_landing.html",
        **activity_landing_context("hike"),
        booking_horizon_year=date.today().year + 2,
        settings=get_settings(),
    )


@app.get("/wachau-aktivurlaub-2027-2028")
def future_planning():
    return render_template(
        "future_planning.html",
        booking_horizon_year=date.today().year + 2,
        settings=get_settings(),
    )


@app.get("/bewertung")
def review_page():
    return render_template(
        "review.html",
        settings=get_settings(),
    )


@app.get("/partner")
def partner_page():
    return render_template(
        "partner.html",
        settings=get_settings(),
    )


@app.get("/wachau-events-2027-2028")
def wachau_events():
    return render_template(
        "events_2027_2028.html",
        booking_horizon_year=date.today().year + 2,
        settings=get_settings(),
    )


def event_landing_context(slug: str) -> dict:
    horizon = date.today().year + 2
    events = {
        "kremser-adventzauber-2026": {
            "page_title": "Kremser Adventzauber 2026 Unterkunft Wachau | Zuhause am Bach",
            "meta_description": "Unterkunft für den Kremser Adventzauber 2026: ruhig in Aggsbach Markt übernachten, direkt buchen und Adventwochenenden früh sichern.",
            "canonical": "https://www.zuhauseambach-wachau.at/kremser-adventzauber-2026-unterkunft",
            "event_name": "Kremser Adventzauber 2026",
            "start_date": "2026-11-19", "end_date": "2026-12-23",
            "display_date": "19. Nov.–23. Dez. 2026",
            "event_location": "Kremser Altstadt", "event_city": "Krems an der Donau",
            "official_url": "https://www.krems.info/kremser-adventzauber",
            "event_description": "Adventveranstaltungen, Märkte und Programm in der Kremser Altstadt.",
            "eyebrow": "Advent in der Wachau",
            "headline": "Unterkunft zum Kremser Adventzauber 2026",
            "intro": "Wer Advent in Krems mit einer ruhigen Übernachtung in der Wachau verbinden möchte, kann bei Zuhause am Bach in Aggsbach Markt früh direkt prüfen.",
            "scarcity_text": "An starken Adventwochenenden ist ein einzelnes Zimmer schnell vergeben. Freitag bis Sonntag schützen wir diese Nachfrage mit Eventpreis und zwei Nächten Mindestaufenthalt.",
        },
        "marillenbluetenmarkt-2027": {
            "page_title": "Marillenblütenmarkt Krems 2027 Unterkunft | Zuhause am Bach Wachau",
            "meta_description": "Unterkunft zum Kremser Marillenblütenmarkt 2027: 26.–27. März und 2.–3. April. Ruhig in Aggsbach Markt übernachten und direkt buchen.",
            "canonical": "https://www.zuhauseambach-wachau.at/marillenbluetenmarkt-krems-2027-unterkunft",
            "event_name": "Kremser Marillenblütenmarkt 2027",
            "start_date": "2027-03-26", "end_date": "2027-04-03",
            "display_date": "26.–27. März & 2.–3. April 2027",
            "event_location": "Kremser Altstadt", "event_city": "Krems an der Donau",
            "official_url": "https://www.krems.info/r-marillenbluetenmarkt",
            "event_description": "Kremser Marillenblütenmarkt an zwei Wochenenden in der Altstadt.",
            "eyebrow": "Marillenblüte 2027",
            "headline": "Unterkunft zum Marillenblütenmarkt 2027",
            "intro": "Die Marillenblüte ist ein früher Reiseanlass in der Wachau. Zuhause am Bach bietet eine ruhige Basis in Aggsbach Markt für Gäste, die Krems und die Wachau verbinden möchten.",
            "scarcity_text": "Die bestätigten Markttermine werden als stärkere Nachfragezeiten bepreist. Wer genau an einem dieser Wochenenden kommen möchte, sollte seinen Termin früh prüfen.",
        },
        "sonnenwende-wachau-2027": {
            "page_title": "Wachauer Sonnenwende 2027 Unterkunft | Zuhause am Bach",
            "meta_description": "Unterkunft zur Wachauer Sonnenwende am 19. Juni 2027. Wunschtermin in Aggsbach Markt früh direkt prüfen; nur ein Gartenzimmer.",
            "canonical": "https://www.zuhauseambach-wachau.at/wachauer-sonnenwende-2027-unterkunft",
            "event_name": "Wachauer Sonnenwende 2027",
            "start_date": "2027-06-19", "end_date": "2027-06-19",
            "display_date": "19. Juni 2027",
            "event_location": "Wachau", "event_city": "Wachau",
            "official_url": "https://www.donau.com/sonnenwende",
            "event_description": "Sonnwendfeiern in der Wachau mit Lichtern und Feuerspektakel entlang der Donau.",
            "eyebrow": "Premium-Termin 2027",
            "headline": "Unterkunft zur Wachauer Sonnenwende 2027",
            "intro": "Die Wachauer Sonnenwende gehört zu den stärksten Terminen des Jahres. Für den 19. Juni 2027 kann das Gartenzimmer früh direkt angefragt werden.",
            "scarcity_text": "Für die Sonnenwende gilt ein Premiumpreis und ein Mindestaufenthalt von zwei Nächten. Bei nur einem Gartenzimmer ist dieser Termin besonders knapp.",
        },
        "alles-marille-2027": {
            "page_title": "ALLES MARILLE 2027 Unterkunft Wachau | Zuhause am Bach",
            "meta_description": "Unterkunft für ALLES MARILLE! 2027 in Krems vom 8.–25. Juli. Ruhig in Aggsbach Markt übernachten und starke Juli-Wochenenden früh sichern.",
            "canonical": "https://www.zuhauseambach-wachau.at/alles-marille-2027-unterkunft",
            "event_name": "ALLES MARILLE! 2027",
            "start_date": "2027-07-08", "end_date": "2027-07-25",
            "display_date": "8.–25. Juli 2027",
            "event_location": "Kremser Altstadt", "event_city": "Krems an der Donau",
            "official_url": "https://www.krems.info/alles-marille",
            "event_description": "Marillenfest in der Kremser Altstadt an drei Juli-Wochenenden.",
            "eyebrow": "Marillenzeit 2027",
            "headline": "Unterkunft zu ALLES MARILLE! 2027",
            "intro": "Drei Juli-Wochenenden stehen in Krems im Zeichen der Wachauer Marille. Zuhause am Bach ist die ruhige Wachau-Basis für Gäste, die Genuss und Aktivurlaub verbinden.",
            "scarcity_text": "Freitag- und Samstagnächte während ALLES MARILLE! sind als starke Nachfragezeiten mit zwei Nächten Mindestaufenthalt geschützt.",
        },
        "sonnenwende-wachau-2028": {
            "page_title": "Wachauer Sonnenwende 2028 Unterkunft | Zuhause am Bach",
            "meta_description": "Unterkunft zur Wachauer Sonnenwende am 17. Juni 2028. Termin in Aggsbach Markt weit im Voraus direkt prüfen.",
            "canonical": "https://www.zuhauseambach-wachau.at/wachauer-sonnenwende-2028-unterkunft",
            "event_name": "Wachauer Sonnenwende 2028",
            "start_date": "2028-06-17", "end_date": "2028-06-17",
            "display_date": "17. Juni 2028",
            "event_location": "Wachau", "event_city": "Wachau",
            "official_url": "https://www.donau.com/sonnenwende",
            "event_description": "Sonnwendfeier in der Wachau am 17. Juni 2028.",
            "eyebrow": "Premium-Termin 2028",
            "headline": "Unterkunft zur Wachauer Sonnenwende 2028",
            "intro": "Auch die Wachauer Sonnenwende 2028 ist offiziell terminiert. Wer diesen Abend mit einer Wachau-Reise verbinden möchte, kann den Wunschtermin schon früh prüfen.",
            "scarcity_text": "Für die Sonnenwende gilt ein Premiumpreis und ein Mindestaufenthalt von zwei Nächten. Frühplanung sichert den Termin, nicht einen Rabatt.",
        },
    }
    data = events.get(slug)
    if not data:
        abort(404)
    return {**data, "booking_horizon_year": horizon, "settings": get_settings()}


@app.get("/kremser-adventzauber-2026-unterkunft")
def event_advent_2026():
    return render_template("event_landing.html", **event_landing_context("kremser-adventzauber-2026"))


@app.get("/marillenbluetenmarkt-krems-2027-unterkunft")
def event_marillenbluete_2027():
    return render_template("event_landing.html", **event_landing_context("marillenbluetenmarkt-2027"))


@app.get("/wachauer-sonnenwende-2027-unterkunft")
def event_sonnenwende_2027():
    return render_template("event_landing.html", **event_landing_context("sonnenwende-wachau-2027"))


@app.get("/alles-marille-2027-unterkunft")
def event_marille_2027():
    return render_template("event_landing.html", **event_landing_context("alles-marille-2027"))


@app.get("/wachauer-sonnenwende-2028-unterkunft")
def event_sonnenwende_2028():
    return render_template("event_landing.html", **event_landing_context("sonnenwende-wachau-2028"))


@app.get("/sitemap.xml")
def sitemap():
    today_iso = date.today().isoformat()
    urls = [
        "https://www.zuhauseambach-wachau.at/",
        "https://www.zuhauseambach-wachau.at/unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/uebernachten-aggsbach-markt",
        "https://www.zuhauseambach-wachau.at/radfahrer-unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/unterkunft-jauerling-wachau",
        "https://www.zuhauseambach-wachau.at/skifahren-jauerling-unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/winterurlaub-wachau",
        "https://www.zuhauseambach-wachau.at/unterkunft-donauradweg-wachau",
        "https://www.zuhauseambach-wachau.at/unterkunft-welterbesteig-wachau",
        "https://www.zuhauseambach-wachau.at/wachau-aktivurlaub-2027-2028",
        "https://www.zuhauseambach-wachau.at/wachau-events-2027-2028",
        "https://www.zuhauseambach-wachau.at/kremser-adventzauber-2026-unterkunft",
        "https://www.zuhauseambach-wachau.at/marillenbluetenmarkt-krems-2027-unterkunft",
        "https://www.zuhauseambach-wachau.at/wachauer-sonnenwende-2027-unterkunft",
        "https://www.zuhauseambach-wachau.at/alles-marille-2027-unterkunft",
        "https://www.zuhauseambach-wachau.at/wachauer-sonnenwende-2028-unterkunft",
        "https://www.zuhauseambach-wachau.at/bewertung",
        "https://www.zuhauseambach-wachau.at/partner",
    ]
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        body.append(f"<url><loc>{url}</loc><lastmod>{today_iso}</lastmod><changefreq>weekly</changefreq></url>")
    body.append("</urlset>")
    return Response("\n".join(body), mimetype="application/xml")


@app.get("/robots.txt")
def robots():
    return Response(
        "User-agent: *\nAllow: /\nSitemap: https://www.zuhauseambach-wachau.at/sitemap.xml\n",
        mimetype="text/plain",
    )


@app.post("/api/events")
def api_events():
    payload = request.get_json(silent=True) or {}
    event = str(payload.get("event", "")).strip()[:64]
    allowed_prefixes = (
        "landing_view", "room_selected", "extras_selected",
        "availability_started", "availability_result_",
        "checkout_started", "booking_abandoned",
    )
    if not event or not any(event == prefix or event.startswith(prefix) for prefix in allowed_prefixes):
        return Response(status=204)
    with db() as conn:
        conn.execute(
            "INSERT INTO site_events(event, created_at) VALUES (?, ?)",
            (event, datetime.now().isoformat(timespec="seconds")),
        )
    return Response(status=204)


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

    if room != "Bachblick":
        return jsonify(error="Unbekanntes Zimmer"), 400

    first = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)

    # Grundzustand nur dann "free", wenn der Live-Masterkalender erfolgreich gelesen wurde.
    states = {}
    live_ok = False
    live_updated = ""
    live_source = ""
    try:
        live_url = "https://web-production-907d68.up.railway.app/api/direct-booking-calendar"
        req = urllib.request.Request(live_url, headers={"Cache-Control": "no-cache", "User-Agent": "ZAB-Homepage/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        events = payload.get("events")
        if payload.get("ok") is True and isinstance(events, list):
            live_ok = True
            live_updated = str(payload.get("updatedAt") or "")
            live_source = str(payload.get("source") or "Live-Kalender")
            current = first
            while current < next_month:
                states[current.isoformat()] = "free"
                current += timedelta(days=1)
            for event in events:
                if not event.get("start") or not event.get("end"):
                    continue
                start_d = parse_date(event["start"][:10])
                end_d = parse_date(event["end"][:10])
                current = max(first, start_d)
                while current < min(next_month, end_d):
                    states[current.isoformat()] = "booking"
                    current += timedelta(days=1)
    except Exception:
        current = first
        while current < next_month:
            states[current.isoformat()] = "unknown"
            current += timedelta(days=1)

    # Booking/iCal vor der Anzeige frisch synchronisieren und seine Sperren
    # als Sicherheitsnetz über den Masterkalender legen. Der Master kann leer
    # oder verzögert sein; Booking-Belegungen dürfen dadurch nie "free" werden.
    sync_room(room)

    # Eigene Direktbuchungen und Booking/iCal-Sperren werden immer zusätzlich
    # berücksichtigt.
    with db() as conn:
        local = conn.execute(
            """
            SELECT arrival, departure, status FROM bookings
            WHERE room=? AND status IN ('pending','confirmed')
            """,
            (room,),
        ).fetchall()
        external = conn.execute(
            """
            SELECT start_date, end_date FROM external_blocks
            WHERE room=? AND source='booking_ical'
            """,
            (room,),
        ).fetchall()

    for row in external:
        start_d, end_d = parse_date(row["start_date"]), parse_date(row["end_date"])
        current = max(first, start_d)
        while current < min(next_month, end_d):
            states[current.isoformat()] = "booking"
            current += timedelta(days=1)

    for row in local:
        start_d, end_d = parse_date(row["arrival"]), parse_date(row["departure"])
        current = max(first, start_d)
        state = "direct" if row["status"] == "confirmed" else "pending"
        while current < min(next_month, end_d):
            states[current.isoformat()] = state
            current += timedelta(days=1)

    return jsonify(
        room="Gartenzimmer",
        roomTechnical="Bachblick",
        year=year,
        month=month,
        days=states,
        live=live_ok,
        updatedAt=live_updated,
        source=live_source,
    )

def booking_success_response(booking):
    data = dict(booking)
    booking_id = int(data.get("id") or 0)
    data["booking_number"] = data.get("booking_number") or (f"ZAB-{booking_id:06d}" if booking_id else "ZAB")
    data["room"] = public_room_name(str(data.get("room", "")))
    settings = get_settings()
    return render_template(
        "success.html",
        booking=data,
        settings=settings,
        bank_account_holder=env_value("BANK_ACCOUNT_HOLDER"),
        bank_iban=env_value("BANK_IBAN"),
        bank_iban_display=format_iban(env_value("BANK_IBAN")),
        paypal_email=PAYPAL_EMAIL,
        guest_app_url=settings.get("public_base_url", "https://topdiveair-sketch.github.io/Gaeste/"),
    )


@app.post("/book")
def book():
    try:
        room = request.form["room"]
        arrival = parse_date(request.form["arrival"])
        departure = parse_date(request.form["departure"])
        adults = max(1, min(2, int(request.form["adults"])))
        breakfast = request.form.get("breakfast") == "on"
        chosen = {k: request.form.get(k) == "on" for k in ("breakfast", "jause", "luggage", "dog", "baby_bed")}
        coupon_code = request.form.get("coupon_code", "").strip()
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()
        payment_method = request.form["payment_method"].strip()
        idempotency_key = request.form.get("idempotency_key", "").strip()[:120]
    except (KeyError, ValueError):
        flash("Bitte alle Pflichtfelder korrekt ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    if payment_method == "PayPal":
        flash("PayPal-Zahlungen bitte über den sicheren PayPal-Button starten.", "error")
        return redirect(url_for("index") + "#booking")
    if payment_method not in {"Banküberweisung", "Vor Ort"}:
        flash("Bitte eine gültige Zahlungsart wählen.", "error")
        return redirect(url_for("index") + "#booking")

    if idempotency_key:
        with db() as conn:
            existing = conn.execute(
                "SELECT * FROM bookings WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        if existing:
            return booking_success_response(existing)

    ok, message = room_available(room, arrival, departure)
    if not ok:
        flash(message, "error")
        return redirect(url_for("index") + "#booking")

    if not all([first_name, last_name, email, phone]):
        flash("Bitte Name, E-Mail und Telefonnummer ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    total = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)["total"]
    uid = f"ZAB-{uuid4()}@zuhause-am-bach"

    try:
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM bookings WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    conn.rollback()
                    return booking_success_response(existing)

            ok, message = room_available_in_conn(conn, room, arrival, departure)
            if not ok:
                conn.rollback()
                flash(message, "error")
                return redirect(url_for("index") + "#booking")

            cur = conn.execute(
                """
                INSERT INTO bookings
                (uid, room, arrival, departure, adults, breakfast, first_name,
                 last_name, email, phone, message, payment_method, total, status,
                 created_at, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inquiry', ?, ?)
                """,
                (
                    uid, room, arrival.isoformat(), departure.isoformat(), adults,
                    1 if breakfast else 0, first_name, last_name, email, phone,
                    request.form.get("message", "").strip(), payment_method, total,
                    datetime.now().isoformat(timespec="seconds"), idempotency_key,
                ),
            )
            booking_id = cur.lastrowid
    except sqlite3.IntegrityError:
        if idempotency_key:
            with db() as conn:
                existing = conn.execute(
                    "SELECT * FROM bookings WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
            if existing:
                return booking_success_response(existing)
        flash("Die Buchung wurde bereits verarbeitet. Bitte Seite aktualisieren.", "error")
        return redirect(url_for("index") + "#booking")

    if app.extensions.get("zab_ensure_tokens"):
        app.extensions["zab_ensure_tokens"](booking_id)
    if app.extensions.get("v6_ensure_checkin_token"):
        app.extensions["v6_ensure_checkin_token"](booking_id)
    if app.extensions.get("zab_send_confirmation"):
        try:
            app.extensions["zab_send_confirmation"](booking_id)
        except Exception:
            pass

    with db() as conn:
        booking_row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return booking_success_response(booking_row)


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

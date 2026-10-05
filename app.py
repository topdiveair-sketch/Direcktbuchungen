
from __future__ import annotations

import threading

import os
import base64
import json
import sqlite3
import socket
import ssl
import http.client
from contextlib import contextmanager
import urllib.request
import urllib.error
import urllib.parse
import hmac
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from uuid import uuid4
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

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
from pricing_2027 import nightly_direct_rate, pricing_config, cap_room_rate

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
    if len(ADMIN_PASSWORD) < 10 or ADMIN_PASSWORD == "windis2026":
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
    # Advent 2026: bestätigte regionale Nachfragefenster. Bei Überschneidungen
    # steht das stärkere Ereignis weiter oben, damit Zuschläge nie gestapelt werden.
    (date(2026, 11, 20), date(2026, 11, 23), "Wachauer Advent Dürnstein", 1.20, 169.0, 1),
    (date(2026, 11, 27), date(2026, 11, 30), "Wachauer Advent Dürnstein", 1.20, 169.0, 1),
    (date(2026, 12, 4), date(2026, 12, 9), "Wachauer Advent Dürnstein", 1.20, 169.0, 1),
    (date(2026, 12, 11), date(2026, 12, 14), "Wachauer Advent Dürnstein", 1.20, 169.0, 1),
    (date(2026, 10, 30), date(2026, 11, 2), "Aggsteiner Burgadvent", 1.15, 159.0, 1),
    (date(2026, 11, 6), date(2026, 11, 9), "Aggsteiner Burgadvent", 1.15, 159.0, 1),
    (date(2026, 11, 13), date(2026, 11, 16), "Aggsteiner Burgadvent", 1.15, 159.0, 1),
    (date(2026, 11, 20), date(2026, 11, 23), "Aggsteiner Burgadvent", 1.15, 159.0, 1),
    (date(2026, 11, 27), date(2026, 11, 30), "Melker Advent", 1.15, 159.0, 1),
    (date(2026, 12, 4), date(2026, 12, 7), "Melker Advent", 1.15, 159.0, 1),
    (date(2026, 12, 11), date(2026, 12, 14), "Melker Advent", 1.15, 159.0, 1),
    (date(2026, 12, 18), date(2026, 12, 21), "Melker Advent", 1.15, 159.0, 1),
    # Spitzer Advent (28.-29.11.) sowie Maria Laach Adventkranzbinden (21.11.)
    # liegen bereits innerhalb der stärkeren Dürnstein-/Aggstein-Fenster.
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
            if name in {"Wachauer Advent Dürnstein", "Aggsteiner Burgadvent", "Melker Advent"}:
                # Adventtermine sind explizit hinterlegt. Freitag/Samstag
                # erhalten 2-Nächte-Mindestaufenthalt; Sonntag bleibt 1 Nacht möglich.
                if day.weekday() in (4, 5):
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

def suspended_rooms() -> set[str]:
    raw = env_value("ZAB_SUSPENDED_ROOMS")
    return {item.strip() for item in raw.split(",") if item.strip()}


def room_is_suspended(room: str) -> bool:
    return room in suspended_rooms()

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# The deployed app uses one worker with multiple request/background threads.
# Coordinate short database scopes; feed HTTP requests stay outside this lock.
_DB_LOCK = threading.RLock()


@contextmanager
def db():
    with _DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            # sqlite3's context manager commits/rolls back but does not close.
            with conn:
                yield conn
        finally:
            conn.close()


@app.errorhandler(sqlite3.OperationalError)
def calendar_database_error(exc):
    """Also cover a busy DB in before_request; never confirm availability."""
    code = getattr(exc, "sqlite_errorcode", 0) & 0xff
    if code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or request.path not in {
        "/api/availability", "/api/calendar", "/api/paypal/quote", "/api/paypal/create-order",
    }:
        raise exc
    app.logger.warning("calendar_database_busy path=%s code=%s", request.path, code)
    response = jsonify(
        ok=False, available=False, status="unknown", live=False, days={},
        message="Kalenderprüfung vorübergehend ausgelastet. Bitte kurz warten und erneut prüfen.",
    )
    response.headers["Retry-After"] = "2"
    response.headers["Cache-Control"] = "no-store"
    return response, 503


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

            CREATE TABLE IF NOT EXISTS central_overrides (
                room TEXT NOT NULL,
                day TEXT NOT NULL,
                availability INTEGER,
                price REAL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'os_central',
                PRIMARY KEY (room, day)
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
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bookings)")}
        for column, definition in (
            ("price_breakdown_json", "TEXT DEFAULT '{}'"),
            ("sms_verified_at", "TEXT DEFAULT ''"),
            ("sms_sent_at", "TEXT DEFAULT ''"),
            ("payment_hold_expires_at", "TEXT DEFAULT ''"),
            ("deposit_percent", "INTEGER DEFAULT 0"),
            ("amount_paid", "REAL DEFAULT 0"),
            ("payment_status", "TEXT DEFAULT ''"),
            ("payment_reference", "TEXT DEFAULT ''"),
            ("paypal_order_id", "TEXT DEFAULT ''"),
            ("cancelled_at", "TEXT DEFAULT ''"),
            ("source", "TEXT DEFAULT ''"),
            ("utm_medium", "TEXT DEFAULT ''"),
            ("utm_campaign", "TEXT DEFAULT ''"),
            ("landing_page", "TEXT DEFAULT ''"),
            ("referrer", "TEXT DEFAULT ''")
        ):
            if column not in cols:
                conn.execute(f"ALTER TABLE bookings ADD COLUMN {column} {definition}")
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
        site_event_cols = {row[1] for row in conn.execute("PRAGMA table_info(site_events)")}
        if "visitor_hash" not in site_event_cols:
            conn.execute("ALTER TABLE site_events ADD COLUMN visitor_hash TEXT DEFAULT ''")
        if "country_code" not in site_event_cols:
            conn.execute("ALTER TABLE site_events ADD COLUMN country_code TEXT DEFAULT 'XX'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_events_event_created "
            "ON site_events(event, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_events_visitor_created "
            "ON site_events(visitor_hash, created_at)"
        )

        conn.execute(
            """CREATE TABLE IF NOT EXISTS demand_signals(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   room TEXT NOT NULL,
                   target_day TEXT NOT NULL,
                   visitor_hash TEXT NOT NULL,
                   observed_on TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   UNIQUE(room, target_day, visitor_hash, observed_on)
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_demand_signals_target_created "
            "ON demand_signals(room, target_day, created_at)"
        )

        conn.execute(
            """CREATE TABLE IF NOT EXISTS demand_searches(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   room TEXT NOT NULL,
                   arrival TEXT NOT NULL,
                   departure TEXT NOT NULL,
                   visitor_hash TEXT NOT NULL,
                   country_code TEXT NOT NULL DEFAULT 'XX',
                   local_date TEXT NOT NULL,
                   local_weekday INTEGER NOT NULL,
                   local_hour INTEGER NOT NULL,
                   available INTEGER NOT NULL DEFAULT 0,
                   created_at TEXT NOT NULL
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_demand_searches_created "
            "ON demand_searches(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_demand_searches_country "
            "ON demand_searches(country_code, local_date)"
        )

        conn.execute(
            """UPDATE bookings
               SET status='inquiry'
               WHERE status='pending'
                 AND payment_method='Banküberweisung'"""
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
            "google_rating": "4.9",
            "google_review_count": "9",
            "google_review_url": "https://www.google.com/maps/search/?api=1&query=Zuhause%20am%20Bach%20-%20Wachau%20Aggsbach%20Markt%2082",
            "phone": "+43 664 6437526",
            "email": "Zuhause.am.Bach@outlook.com",
            "address": "Aggsbach Markt 82, 3641 Aggsbach Markt, Oesterreich",
            "public_base_url": "https://www.zuhauseambach-wachau.at/",
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

def central_override_for_day(room: str, day: date) -> dict:
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT availability, price, updated_at FROM central_overrides WHERE room=? AND day=?",
                (room, day.isoformat()),
            ).fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}


def _base_direct_nightly_price_for_day(room: str, day: date) -> float:
    """Return the OS/base rate before demand adjustment."""
    prices, _discounts, _extras, _seasons = pricing_data()
    getter = app.extensions.get("zab_channel_price_for_day")
    if callable(getter):
        value = getter(room, "direct", day, None)
        if value is not None:
            return round(float(value), 2)
    manual_base = app.extensions.get("zab_manual_room_base")
    if callable(manual_base) and manual_base(room):
        row = prices[room]
        return float(row["high"] if is_high(day) else row["weekend"] if day.weekday() in (4, 5) else row["standard"])
    override = central_override_for_day(room, day)
    if override.get("price") is not None:
        return round(float(override["price"]), 2)

    if room == "Bachblick":
        configured = nightly_direct_rate(day)
        if configured is not None:
            return round(float(configured), 2)

    price = prices[room]["high"] if is_high(day) else (
        prices[room]["weekend"] if day.weekday() in (4, 5) else prices[room]["standard"]
    )
    event = event_pricing_for_day(day)
    if event:
        price = min(float(price) * float(event["factor"]), float(event["cap"]))
    return round(float(price), 2)


def _demand_rule_config() -> dict:
    try:
        cfg = pricing_config().get("demand_rules", {})
    except Exception:
        cfg = {}
    return {
        "lookback_hours": int(cfg.get("lookback_hours", 48)),
        "floor_eur": float(cfg.get("floor_eur", 99)),
        "cap_eur": float(cfg.get("cap_eur", 159)),
        "thresholds": cfg.get("unique_checks_thresholds", [
            {"checks": 3, "percent": 5},
            {"checks": 6, "percent": 8},
            {"checks": 10, "percent": 12},
            {"checks": 15, "percent": 15},
        ]),
    }


def _demand_unique_checks(room: str, day: date, now=None) -> int:
    """Unique, privacy-preserving date checks in the configured rolling window."""
    now = now or datetime.now()
    cfg = _demand_rule_config()
    cutoff = (now - timedelta(hours=max(1, cfg["lookback_hours"]))).isoformat(timespec="seconds")
    try:
        with db() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT visitor_hash) AS n
                   FROM demand_signals
                   WHERE room=? AND target_day=? AND created_at>=?""",
                (room, day.isoformat(), cutoff),
            ).fetchone()
        return int(row["n"] or 0) if row else 0
    except Exception:
        return 0


def _demand_percent_for_day(room: str, day: date) -> tuple[float, int]:
    checks = _demand_unique_checks(room, day)
    percent = 0.0
    for rule in sorted(_demand_rule_config()["thresholds"], key=lambda row: int(row.get("checks", 0))):
        if checks >= int(rule.get("checks", 0)):
            percent = max(percent, float(rule.get("percent", 0)))
    return percent, checks


def direct_nightly_price_for_day(room: str, day: date) -> float:
    """OS base price plus aggregate date demand, with hard floor/cap protection."""
    base = _base_direct_nightly_price_for_day(room, day)
    if room != "Bachblick":
        return base

    # Explicit locked direct-price overrides are used when the public direct
    # rate must stay below a known OTA comparison price. Demand uplift must
    # not silently erase that direct-booking advantage.
    try:
        for row in pricing_config().get("date_overrides", []):
            if row.get("lock_price") and date.fromisoformat(row["start"]) <= day <= date.fromisoformat(row["end"]):
                return round(cap_room_rate(float(row["price_eur"])), 2)
    except Exception:
        pass

    percent, _checks = _demand_percent_for_day(room, day)
    cfg = _demand_rule_config()
    adjusted = base * (1.0 + percent / 100.0)
    return round(cap_room_rate(min(cfg["cap_eur"], max(cfg["floor_eur"], adjusted))), 2)


def _request_country_code() -> str:
    """Return a coarse ISO country code from trusted proxy headers when available."""
    for header in (
        "CF-IPCountry",
        "CloudFront-Viewer-Country",
        "X-Country-Code",
        "X-Geo-Country",
        "X-Vercel-IP-Country",
    ):
        value = (request.headers.get(header) or "").strip().upper()
        if len(value) == 2 and value.isalpha():
            return value
    return "XX"


def _visitor_hash() -> str:
    """Privacy-preserving visitor key; raw IP and user-agent are never stored."""
    remote = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    agent = request.headers.get("User-Agent", "")[:200]
    salt = app.secret_key or "zab-demand"
    return hashlib.sha256(f"{salt}|{remote}|{agent}".encode("utf-8")).hexdigest()


def _record_search_analytics(room: str, arrival: date, departure: date, available: bool) -> None:
    """Store one coarse, privacy-safe availability search event for OS statistics."""
    if room != "Bachblick" or departure <= arrival:
        return
    try:
        local_now = datetime.now(ZoneInfo("Europe/Vienna"))
    except Exception:
        local_now = datetime.now()
    try:
        with db() as conn:
            conn.execute(
                """INSERT INTO demand_searches
                   (room,arrival,departure,visitor_hash,country_code,local_date,
                    local_weekday,local_hour,available,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    room,
                    arrival.isoformat(),
                    departure.isoformat(),
                    _visitor_hash(),
                    _request_country_code(),
                    local_now.date().isoformat(),
                    int(local_now.weekday()),
                    int(local_now.hour),
                    1 if available else 0,
                    local_now.isoformat(timespec="seconds"),
                ),
            )
    except Exception:
        pass


def _record_demand_check(room: str, arrival: date, departure: date) -> None:
    """Record one anonymous check per visitor/date/day; never stores an IP or user-agent."""
    if room != "Bachblick" or departure <= arrival:
        return
    visitor_hash = _visitor_hash()
    now = datetime.now()
    observed_on = now.date().isoformat()
    created_at = now.isoformat(timespec="seconds")
    try:
        with db() as conn:
            current = arrival
            while current < departure and (current - arrival).days < 14:
                conn.execute(
                    """INSERT OR IGNORE INTO demand_signals
                       (room,target_day,visitor_hash,observed_on,created_at)
                       VALUES (?,?,?,?,?)""",
                    (room, current.isoformat(), visitor_hash, observed_on, created_at),
                )
                current += timedelta(days=1)
    except Exception:
        pass


def price_breakdown(room,arrival,departure,adults,chosen,coupon_code=""):
    prices,discounts,extras,seasons=pricing_data(); n=(departure-arrival).days; cur=arrival; room_total=0
    nightly_rates=[]
    while cur<departure:
        p=direct_nightly_price_for_day(room, cur)
        percent, checks = _demand_percent_for_day(room, cur) if room == "Bachblick" else (0.0, 0)
        nightly_rates.append({"date":cur.isoformat(),"rate":round(float(p),2),"demand_percent":percent,"unique_checks_48h":checks})
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
    return {"nights":n,"room_total":round(room_total,2),"nightly_rates":nightly_rates,"extras":lines,"discounts":applied,"total":round(subtotal,2)}

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
    central_closed = conn.execute(
        "SELECT day FROM central_overrides WHERE room=? AND availability=0 AND day>=? AND day<?",
        (room, arrival.isoformat(), departure.isoformat()),
    ).fetchall()

    for row in local:
        if overlaps(arrival, departure, parse_date(row["arrival"]), parse_date(row["departure"])):
            return False, "Das Zimmer ist durch eine Direktbuchung belegt."

    for row in external:
        if overlaps(arrival, departure, parse_date(row["start_date"]), parse_date(row["end_date"])):
            return False, "Das Zimmer ist über einen externen Buchungskanal belegt."

    if central_closed:
        return False, "Das Zimmer wurde im Zuhause-am-Bach Zentralkalender gesperrt."

    return True, "Das Zimmer ist verfügbar."


@app.post("/api/os/control")
def os_central_control():
    expected = env_value("OS_SYNC_TOKEN")
    supplied = (request.headers.get("X-OS-Sync-Token") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(ok=False, error="unauthorized"), 401

    payload = request.get_json(silent=True) or {}
    room = str(payload.get("room") or "").strip()
    if room != "Bachblick":
        return jsonify(ok=False, error="unknown_room"), 400
    try:
        start = parse_date(str(payload.get("from") or payload.get("date") or "")[:10])
        end = parse_date(str(payload.get("to") or payload.get("from") or payload.get("date") or "")[:10])
    except Exception:
        return jsonify(ok=False, error="invalid_date"), 400
    if end < start:
        start, end = end, start
    if (end - start).days > 370:
        return jsonify(ok=False, error="range_too_large"), 400

    availability = payload.get("availability", None)
    if availability is not None:
        try:
            availability = int(availability)
        except Exception:
            return jsonify(ok=False, error="invalid_availability"), 400
        if availability not in (0, 1):
            return jsonify(ok=False, error="invalid_availability"), 400

    price = payload.get("price", None)
    clear_price = bool(payload.get("clear_price", False))
    if price not in (None, ""):
        try:
            price = round(float(price), 2)
        except Exception:
            return jsonify(ok=False, error="invalid_price"), 400
        if price < 0 or price > 5000:
            return jsonify(ok=False, error="invalid_price"), 400
    else:
        price = None

    now = datetime.now().isoformat(timespec="seconds")
    changed = 0
    current = start
    with db() as conn:
        while current <= end:
            existing = conn.execute(
                "SELECT availability, price FROM central_overrides WHERE room=? AND day=?",
                (room, current.isoformat()),
            ).fetchone()
            new_availability = availability if availability is not None else (existing["availability"] if existing else None)
            new_price = None if clear_price else (price if price is not None else (existing["price"] if existing else None))
            conn.execute(
                """
                INSERT INTO central_overrides(room,day,availability,price,updated_at,source)
                VALUES(?,?,?,?,?,'os_central')
                ON CONFLICT(room,day) DO UPDATE SET
                    availability=excluded.availability,
                    price=excluded.price,
                    updated_at=excluded.updated_at,
                    source=excluded.source
                """,
                (room, current.isoformat(), new_availability, new_price, now),
            )
            changed += 1
            current += timedelta(days=1)
    return jsonify(ok=True, room=room, changed=changed, from_date=start.isoformat(), to_date=end.isoformat(),
                   availability=availability, price=price, clear_price=clear_price)


@app.get("/api/os/demand-stats")
def os_demand_stats():
    """Aggregated, privacy-safe search analytics for the authenticated desktop OS."""
    expected = env_value("OS_SYNC_TOKEN")
    supplied = (request.headers.get("X-OS-Sync-Token") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(ok=False, error="unauthorized"), 401

    try:
        days = max(1, min(730, int(request.args.get("days", "30"))))
    except Exception:
        days = 30

    persistent_summary = app.extensions.get("zab_demand_analytics_os_summary")
    if callable(persistent_summary):
        try:
            payload = persistent_summary(days)
            if payload is not None:
                return jsonify(payload)
        except Exception:
            app.logger.exception("persistent demand analytics summary failed")

    try:
        cutoff = (datetime.now(ZoneInfo("Europe/Vienna")) - timedelta(days=days)).isoformat(timespec="seconds")
    except Exception:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT country_code,local_date,local_weekday,local_hour,available,visitor_hash,
                          arrival,departure,created_at
                   FROM demand_searches
                   WHERE room='Bachblick' AND created_at>=?
                   ORDER BY created_at""",
                (cutoff,),
            ).fetchall()
            event_rows = conn.execute(
                """SELECT event,visitor_hash,country_code,created_at
                   FROM site_events
                   WHERE created_at>=?
                   ORDER BY created_at""",
                (cutoff,),
            ).fetchall()
    except Exception:
        rows = []
        event_rows = []

    total = len(rows)
    unique_visitors = len({str(r["visitor_hash"] or "") for r in rows if r["visitor_hash"]})
    available_count = sum(1 for r in rows if int(r["available"] or 0) == 1)

    def pct(n):
        return round((100.0 * n / total), 1) if total else 0.0

    country_counts = {}
    weekday_counts = {i: 0 for i in range(7)}
    hour_counts = {i: 0 for i in range(24)}
    date_counts = {}
    for row in rows:
        cc = (row["country_code"] or "XX").upper()
        country_counts[cc] = country_counts.get(cc, 0) + 1
        wd = int(row["local_weekday"] or 0)
        hour = int(row["local_hour"] or 0)
        weekday_counts[wd] = weekday_counts.get(wd, 0) + 1
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
        day = str(row["local_date"] or "")
        if day:
            date_counts[day] = date_counts.get(day, 0) + 1

    weekday_names = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
    by_country = [
        {"country_code": cc, "searches": n, "percent": pct(n)}
        for cc, n in sorted(country_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    by_weekday = [
        {"weekday": weekday_names[i], "weekday_index": i, "searches": weekday_counts.get(i, 0), "percent": pct(weekday_counts.get(i, 0))}
        for i in range(7)
    ]
    by_hour = [
        {"hour": i, "label": f"{i:02d}:00", "searches": hour_counts.get(i, 0), "percent": pct(hour_counts.get(i, 0))}
        for i in range(24)
    ]
    by_date = [
        {"date": day, "searches": n, "percent": pct(n)}
        for day, n in sorted(date_counts.items())
    ]

    landing_rows = [r for r in event_rows if str(r["event"] or "") == "landing_view"]
    visitor_hashes = {str(r["visitor_hash"] or "") for r in landing_rows if r["visitor_hash"]}
    visitor_country_sets = {}
    for row in landing_rows:
        visitor = str(row["visitor_hash"] or "")
        if not visitor:
            continue
        cc = str(row["country_code"] or "XX").upper()
        visitor_country_sets.setdefault(cc, set()).add(visitor)
    visitor_total = len(visitor_hashes)
    by_visitor_country = [
        {
            "country_code": cc,
            "visitors": len(values),
            "percent": round((100.0 * len(values) / visitor_total), 1) if visitor_total else 0.0,
        }
        for cc, values in sorted(visitor_country_sets.items(), key=lambda item: (-len(item[1]), item[0]))
    ]
    booking_attempts = sum(1 for r in event_rows if str(r["event"] or "") == "checkout_started")
    booking_abandoned = sum(1 for r in event_rows if str(r["event"] or "") == "booking_abandoned")
    abandonment_rate = round((100.0 * booking_abandoned / booking_attempts), 1) if booking_attempts else 0.0

    # Monatswerte beziehen sich auf den angefragten Aufenthaltsmonat.
    # Beispiel: Im Oktober-Kalender werden Interessenten fuer Oktober-Aufenthalte
    # gezaehlt, auch wenn die Suche bereits im September stattgefunden hat.
    month_searches = {}
    month_visitors = {}
    month_countries = {}
    month_weekdays = {}
    month_hours = {}
    visitor_search_history = {}
    for row in rows:
        visitor = str(row["visitor_hash"] or "")
        try:
            arr = parse_date(str(row["arrival"] or "")[:10])
            dep = parse_date(str(row["departure"] or "")[:10])
        except Exception:
            continue
        if dep <= arr:
            continue
        cc = str(row["country_code"] or "XX").upper()
        created = str(row["created_at"] or "")
        if visitor:
            visitor_search_history.setdefault(visitor, []).append((created, arr, dep))
        current_month = date(arr.year, arr.month, 1)
        last_day = dep - timedelta(days=1)
        last_month = date(last_day.year, last_day.month, 1)
        while current_month <= last_month:
            month = current_month.strftime("%Y-%m")
            month_searches[month] = month_searches.get(month, 0) + 1
            wd = int(row["local_weekday"] or 0)
            hr = int(row["local_hour"] or 0)
            month_weekdays.setdefault(month, {})[wd] = month_weekdays.setdefault(month, {}).get(wd, 0) + 1
            month_hours.setdefault(month, {})[hr] = month_hours.setdefault(month, {}).get(hr, 0) + 1
            if visitor:
                month_visitors.setdefault(month, set()).add(visitor)
                month_countries.setdefault(month, {}).setdefault(cc, set()).add(visitor)
            if current_month.month == 12:
                current_month = date(current_month.year + 1, 1, 1)
            else:
                current_month = date(current_month.year, current_month.month + 1, 1)

    for history in visitor_search_history.values():
        history.sort(key=lambda item: item[0])

    def _event_stay_month(row):
        visitor = str(row["visitor_hash"] or "")
        created = str(row["created_at"] or "")
        if not visitor or not created:
            return ""
        chosen = None
        for item in visitor_search_history.get(visitor, []):
            if item[0] and item[0] <= created:
                chosen = item
            else:
                break
        return chosen[1].strftime("%Y-%m") if chosen else ""

    month_attempts = {}
    month_abandoned = {}
    for row in event_rows:
        event = str(row["event"] or "")
        month = _event_stay_month(row)
        if not month:
            continue
        if event == "checkout_started":
            month_attempts[month] = month_attempts.get(month, 0) + 1
        elif event == "booking_abandoned":
            month_abandoned[month] = month_abandoned.get(month, 0) + 1

    all_months = sorted(set(month_searches) | set(month_visitors) | set(month_attempts) | set(month_abandoned))
    by_month = []
    for month in all_months:
        visitors = len(month_visitors.get(month, set()))
        attempts = int(month_attempts.get(month, 0))
        abandoned = int(month_abandoned.get(month, 0))
        countries = [
            {"country_code": cc, "visitors": len(values)}
            for cc, values in sorted(
                month_countries.get(month, {}).items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        ]
        total_month_searches = int(month_searches.get(month, 0))
        month_weekday_rows = [
            {
                "weekday": weekday_names[i],
                "weekday_index": i,
                "searches": int(month_weekdays.get(month, {}).get(i, 0)),
                "percent": round((100.0 * int(month_weekdays.get(month, {}).get(i, 0)) / total_month_searches), 1)
                           if total_month_searches else 0.0,
            }
            for i in range(7)
        ]
        month_hour_rows = [
            {
                "hour": i,
                "label": f"{i:02d}:00",
                "searches": int(month_hours.get(month, {}).get(i, 0)),
                "percent": round((100.0 * int(month_hours.get(month, {}).get(i, 0)) / total_month_searches), 1)
                           if total_month_searches else 0.0,
            }
            for i in range(24)
        ]
        by_month.append({
            "month": month,
            "unique_visitors": visitors,
            "total_searches": total_month_searches,
            "booking_attempts": attempts,
            "booking_abandoned": abandoned,
            "abandonment_rate": round((100.0 * abandoned / attempts), 1) if attempts else 0.0,
            "by_visitor_country": countries,
            "by_weekday": month_weekday_rows,
            "by_hour": month_hour_rows,
        })

    return jsonify(
        ok=True,
        period_days=days,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        total_searches=total,
        unique_visitors=visitor_total if visitor_total else unique_visitors,
        search_unique_visitors=unique_visitors,
        available_searches=available_count,
        available_percent=pct(available_count),
        booking_attempts=booking_attempts,
        booking_abandoned=booking_abandoned,
        abandonment_rate=abandonment_rate,
        by_visitor_country=by_visitor_country,
        by_month=by_month,
        by_country=by_country,
        by_weekday=by_weekday,
        by_hour=by_hour,
        by_date=by_date,
        privacy="Aggregated only; no raw IP address or user-agent is exposed.",
    )


@app.get("/api/os/direct-prices")
def os_direct_prices():
    """Return the website's authoritative nightly direct-booking prices for the OS calendar."""
    expected = env_value("OS_SYNC_TOKEN")
    supplied = (request.headers.get("X-OS-Sync-Token") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(ok=False, error="unauthorized"), 401

    room = str(request.args.get("room") or "Bachblick").strip()
    if room != "Bachblick":
        return jsonify(ok=False, error="unknown_room"), 400
    try:
        start = parse_date(str(request.args.get("from") or date.today().isoformat())[:10])
        end = parse_date(str(request.args.get("to") or (start + timedelta(days=62)).isoformat())[:10])
    except Exception:
        return jsonify(ok=False, error="invalid_date"), 400
    if end < start:
        start, end = end, start
    if (end - start).days > 370:
        return jsonify(ok=False, error="range_too_large"), 400

    _prices, discounts, _extras, _seasons = pricing_data()
    direct_discount = 0.0
    direct = discounts.get("direct_booking") or {}
    if direct.get("enabled"):
        try:
            direct_discount = float(direct.get("percent") or 0.0)
        except Exception:
            direct_discount = 0.0

    days = []
    current = start
    while current <= end:
        display_price = direct_nightly_price_for_day(room, current)
        checkout_price = round(display_price * (1.0 - direct_discount / 100.0), 2)
        demand_percent, unique_checks = _demand_percent_for_day(room, current)
        try:
            with db() as conn:
                live_row = conn.execute(
                    """SELECT COUNT(DISTINCT visitor_hash) AS n
                       FROM demand_signals
                       WHERE room=? AND target_day=?""",
                    (room, current.isoformat()),
                ).fetchone()
            unique_checks_live = int(live_row["n"] or 0) if live_row else 0
        except Exception:
            unique_checks_live = unique_checks

        persistent_day_checks = app.extensions.get("zab_demand_analytics_day_checks")
        if callable(persistent_day_checks):
            try:
                unique_checks_live = max(
                    int(unique_checks_live or 0),
                    int(persistent_day_checks(current.isoformat()) or 0),
                )
            except Exception:
                pass
        event = event_pricing_for_day(current)
        override = central_override_for_day(room, current)
        days.append({
            "date": current.isoformat(),
            "display_price": display_price,
            "checkout_price": checkout_price,
            "direct_discount_percent": direct_discount,
            "demand_percent": demand_percent,
            "unique_checks_48h": unique_checks,
            "unique_checks_live": unique_checks_live,
            "source": "os_override" if override.get("price") is not None else ("event" if event else ("high" if is_high(current) else ("weekend" if current.weekday() in (4, 5) else "standard"))),
        })
        current += timedelta(days=1)
    return jsonify(
        ok=True,
        room=room,
        roomDisplayName=public_room_name(room),
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        days=days,
    )


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


def _calendar_sources_for_room(room: str) -> list[tuple[str, str, str]]:
    """Authoritative occupancy feeds. Any successful feed can block availability."""
    with db() as conn:
        row = conn.execute(
            "SELECT import_url FROM ical_settings WHERE room = ?", (room,)
        ).fetchone()

    sources: list[tuple[str, str, str]] = []
    booking_url = (row["import_url"] if row else "").strip()
    if booking_url:
        sources.append(("booking_ical", "Booking.com", booking_url))

    env_suffix = room.upper().replace(" ", "_")
    beds24_url = env_value(f"BEDS24_ICAL_{env_suffix}_URL", "BEDS24_ICAL_URL")
    if beds24_url:
        sources.append(("beds24_ical", "Beds24", beds24_url))

    airbnb_url = env_value(f"AIRBNB_ICAL_{env_suffix}_URL", "AIRBNB_ICAL_URL")
    if airbnb_url:
        sources.append(("airbnb_ical", "Airbnb", airbnb_url))

    # Remove accidental duplicate URLs while preserving the strongest source label.
    seen = set()
    unique = []
    for source, label, url in sources:
        if url in seen:
            continue
        seen.add(url)
        unique.append((source, label, url))
    return unique


def _calendar_failure(exc: Exception) -> tuple[str, bool]:
    """Allowlisted diagnostics only: exception text may contain feed credentials."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}", exc.code in {429, 500, 502, 503, 504}
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, TimeoutError):
        return "Zeitüberschreitung", True
    if isinstance(reason, ssl.SSLError):
        return "TLS-/Zertifikatsfehler", False
    if isinstance(reason, socket.gaierror):
        return "DNS-Auflösung fehlgeschlagen", reason.errno == socket.EAI_AGAIN
    if isinstance(reason, (ConnectionError, http.client.IncompleteRead)):
        return "Verbindung unterbrochen oder abgelehnt", True
    if isinstance(exc, urllib.error.URLError):
        return "Netzwerkfehler", False
    if isinstance(exc, ValueError):
        return "Ungültige Kalenderdaten", False
    if isinstance(exc, sqlite3.Error):
        code = getattr(exc, "sqlite_errorcode", 0) & 0xff
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return "Datenbank gesperrt", False
        return "Datenbankfehler", False
    return "Kalenderverarbeitung fehlgeschlagen", False


def sync_room(room: str) -> tuple[int, str]:
    now = datetime.now().isoformat(timespec="seconds")
    if room_is_suspended(room):
        with db() as conn:
            conn.execute(
                "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
                (now, "Zimmer vorübergehend stillgelegt", room),
            )
        return 0, "Zimmer vorübergehend stillgelegt."
    sources = _calendar_sources_for_room(room)

    if not sources:
        with db() as conn:
            conn.execute(
                "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
                (now, "Kein externer Kalender hinterlegt", room),
            )
        return 0, "Kein externer Kalender hinterlegt."

    total = 0
    results = []
    any_success = False

    for source, label, url in sources:
        attempts = 0
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Zuhause-am-Bach-iCal/4.0",
                    "Cache-Control": "no-cache",
                },
            )
            # One immediate retry only, confined to transient fetch/read errors.
            # Do not repeat parsing or database writes, or retry auth/TLS errors.
            for _ in range(2):
                attempts += 1
                try:
                    with urllib.request.urlopen(req, timeout=8) as response:
                        text = response.read().decode("utf-8", errors="replace")
                    break
                except Exception as exc:
                    if attempts == 2 or not _calendar_failure(exc)[1]:
                        raise
            # An HTML error page or truncated response must not erase old blocks.
            lines = unfold_ical(text.lstrip("\ufeff").strip())
            if not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
                raise ValueError("Invalid iCal envelope")
            events = parse_ical(text)

            # Replace only this provider's previous snapshot. If another provider
            # fails, its last successful snapshot remains as a safety net.
            with db() as conn:
                conn.execute(
                    "DELETE FROM external_blocks WHERE room=? AND source=?",
                    (room, source),
                )
                for event in events:
                    conn.execute(
                        """
                        INSERT INTO external_blocks
                        (room, start_date, end_date, source, uid, summary, imported_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            room,
                            event["start"].isoformat(),
                            event["end"].isoformat(),
                            source,
                            event.get("uid", ""),
                            event.get("summary", label),
                            now,
                        ),
                    )

            total += len(events)
            any_success = True
            results.append(f"{label}: {len(events)}" + (" (nach Retry)" if attempts > 1 else ""))
        except Exception as exc:
            reason, _ = _calendar_failure(exc)
            app.logger.warning(
                "external_calendar_sync_failed room=%s source=%s attempts=%s reason=%s",
                room, source, attempts, reason,
            )
            results.append(
                f"{label}: Fehler ({reason}; Versuche: {attempts}; letzter Stand beibehalten)"
            )

    message = " · ".join(results)
    with db() as conn:
        conn.execute(
            "UPDATE ical_settings SET last_sync=?, last_result=? WHERE room=?",
            (now, message, room),
        )

    if any_success:
        # Keep the sync_room return contract stable for checkout callers:
        # detailed per-provider results stay in ical_settings.last_result, while
        # callers receive the canonical success marker whenever at least one
        # live provider refreshed successfully. Failed providers keep their
        # last successful external_blocks snapshot as a safety net.
        return total, "Synchronisierung erfolgreich."
    return 0, message or "Kalender-Synchronisierung fehlgeschlagen."


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


@app.get("/media/windis-band15.jpg")
def windis_band15_image():
    """Serve the Band 15 cover from repository-safe base64 chunks."""
    parts = []
    for i in range(1, 7):
        path = BASE / "static" / "images" / f"windis-band15-cover.part{i}.b64"
        parts.append(path.read_text(encoding="utf-8").strip())
    data = base64.b64decode("".join(parts), validate=True)
    response = Response(data, mimetype="image/jpeg")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


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


PUBLIC_HOME_LANGUAGES = ("en", "cs", "sk", "hu", "nl", "pl", "it", "es", "fr", "ch", "ar")


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
            "route_facts": [
                "Der Donauradweg ist Teil des EuroVelo 6; in Niederösterreich verlaufen rund 260 km.",
                "Die offizielle Nordufer-Etappe Emmersdorf–Krems führt direkt über Aggsbach Markt.",
                "Fähren ermöglichen in der Wachau je nach Tour einen Wechsel der Uferseite."
            ],
            "official_url": "https://www.donau.com/donauradweg",
            "official_label": "Offizielle Donauradweg-Infos"
        }
    return {
        "kind": "hike",
        "page_title": "Welterbesteig Unterkunft Wachau | Zuhause am Bach Aggsbach",
        "meta_description": "Welterbesteig Unterkunft Wachau in Aggsbach Markt: Gartenzimmer ab 99 €, auch 1 Nacht möglich, Frühstück, Gepäcktransport und direkte Terminprüfung.",
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
        "route_facts": [
            "Der Welterbesteig Wachau umfasst rund 180 km in 14 Etappen.",
            "Etappe 6 führt von Maria Laach nach Aggsbach Markt; Etappe 7 startet in Aggsbach Markt Richtung Emmersdorf.",
            "Gepäcktransport und Etappenplanung lassen sich gut mit einer einzelnen Übernachtung kombinieren."
        ],
        "official_url": "https://www.donau.com/welterbesteig-wachau",
        "official_label": "Offizielle Welterbesteig-Infos"
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
        "1nacht": {
            "title":"1 Nacht Wachau | Etappen-Unterkunft in Aggsbach Markt",
            "description":"Nur 1 Nacht in der Wachau? Bei Zuhause am Bach in Aggsbach Markt grundsätzlich möglich – ideal für Donauradweg und Welterbesteig. Direkt Verfügbarkeit prüfen.",
            "canonical":"https://www.zuhauseambach-wachau.at/1-nacht-wachau",
            "h1":"1 Nacht in der Wachau übernachten",
            "lead":"Für Radfahrer am Donauradweg, Wanderer am Welterbesteig und Durchreisende ist bei Zuhause am Bach auch eine einzelne Übernachtung grundsätzlich möglich – sofern der Termin verfügbar ist.",
            "eyebrow":"1 Nacht · Donauradweg · Welterbesteig",
            "subheading":"Etappenübernachtung direkt beim Gastgeber",
            "paragraphs":["Wer auf einer Rad- oder Wanderetappe unterwegs ist, braucht oft kein Wochenende, sondern genau eine ruhige Nacht. Unser Gartenzimmer in Aggsbach Markt ist für maximal zwei Gäste direkt buchbar.","Frühstück auf Wunsch, sichere Fahrradunterbringung, E-Bike-Lademöglichkeit, Trocknungsmöglichkeit und Gepäcktransport auf Anfrage unterstützen die Weiterreise.","Freie Einzelübernachtungen können direkt im Live-Kalender geprüft werden. An einzelnen stark nachgefragten Veranstaltungsterminen können abweichende Mindestaufenthalte gelten."],
            "features":[("🌙","1 Nacht möglich","Einzelübernachtungen direkt auf Verfügbarkeit prüfen."),("🚲","Für Radreisende","Fahrrad sicher unterbringen und E-Bike laden."),("🥾","Für Wanderer","Praktisch für Etappen am Welterbesteig."),("🍳","Frühstück auf Wunsch","Stärkung vor der nächsten Etappe.")],
            "hero_image":"images/gartenzimmer-04-web.jpg","hero_image_alt":"Gartenzimmer für eine Nacht in der Wachau bei Zuhause am Bach","hero_image_caption":"Eine ruhige Nacht in Aggsbach Markt zwischen zwei Etappen.",
            "secondary_image":"images/bach-hinterm-haus-v11.webp","secondary_image_alt":"Ruhige Umgebung bei Zuhause am Bach in Aggsbach Markt","secondary_image_caption":"Ruhig ankommen, schlafen und am nächsten Tag weiterziehen.",
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
        "wanderer": {
            "title":"Wanderer Unterkunft Wachau | Welterbesteig Zuhause am Bach",
            "description":"Wanderer-Unterkunft am Welterbesteig Wachau in Aggsbach Markt: Frühstück, Trocknung, Gepäcktransport auf Anfrage und Direktbuchung für 1–2 Personen.",
            "canonical":"https://www.zuhauseambach-wachau.at/wanderer-unterkunft-wachau",
            "h1":"Wanderer-Unterkunft am Welterbesteig Wachau",
            "lead":"Für Wanderer am Welterbesteig bietet Zuhause am Bach in Aggsbach Markt einen ruhigen, persönlichen Etappenstopp mit Frühstück auf Wunsch und praktischer Unterstützung für die nächste Etappe.",
            "eyebrow":"Für Wanderer · Welterbesteig",
            "subheading":"Ruhig ankommen, trocknen, stärken und weiterwandern",
            "paragraphs":["Das Gartenzimmer ist für maximal zwei Gäste gedacht und eignet sich besonders für eine einzelne Etappenübernachtung.","Frühstück auf Wunsch, Trocknungsmöglichkeit für Wanderbekleidung und Gepäcktransport auf Anfrage unterstützen die Weiterreise.","Aggsbach Markt liegt auf dem Welterbesteig; freie Termine können direkt über die offizielle Website geprüft werden."],
            "features":[("🥾","Welterbesteig","Etappenstopp direkt in Aggsbach Markt."),("🍳","Frühstück","Auf Wunsch vor der nächsten Etappe."),("👕","Trocknen","Für nasse Wanderbekleidung."),("🧳","Gepäcktransport","Auf Anfrage für die nächste Etappe.")],
            "hero_image":"images/welterbesteig-original.jpg","hero_image_alt":"Welterbesteig Wachau für Wanderer nahe Zuhause am Bach in Aggsbach Markt","hero_image_caption":"Etappenquartier für Wanderer am Welterbesteig Wachau.",
            "secondary_image":"images/gartenzimmer-04-web.jpg","secondary_image_alt":"Gartenzimmer für Wanderer bei Zuhause am Bach in Aggsbach Markt","secondary_image_caption":"Ruhige Nacht zwischen zwei Wanderetappen.",
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
        "business": {
            "title":"Business-Unterkunft Melk–Krems | Geschäftsreisende & Fachkräfte | Zuhause am Bach",
            "description":"Ruhige Business- und Firmenunterkunft zwischen Melk und Krems für Geschäftsreisende, Servicetechniker, Projektleiter und qualifizierte Fachkräfte: WLAN, Parkplatz, eigenes Bad, Frühstück auf Wunsch und direkte Buchung.",
            "canonical":"https://www.zuhauseambach-wachau.at/business-unterkunft-melk-krems",
            "business_mode":True,
            "h1":"Business-Unterkunft zwischen Melk und Krems",
            "lead":"Zuhause am Bach in Aggsbach Markt richtet sich in erster Linie an Geschäftsreisende, Servicetechniker, Projektleiter und qualifizierte Fachkräfte, die zwischen Melk und Krems ruhig, ordentlich und mit direktem Gastgeberkontakt übernachten möchten.",
            "eyebrow":"Business · Servicetechnik · Projekte · Firmen",
            "subheading":"Ruhig schlafen, zuverlässig arbeiten und Arbeitswochen unkompliziert direkt buchen",
            "paragraphs":[
                "Das Gartenzimmer ist für eine oder zwei Personen ausgelegt und eignet sich besonders für Geschäftsreisen, Serviceeinsätze, Inbetriebnahmen, Bau- und Projektleitung sowie qualifizierte Montageeinsätze zwischen Melk, Aggsbach Markt, Spitz und Krems.",
                "WLAN, kostenloser Parkplatz, eigenes Bad und Frühstück auf Wunsch decken die wichtigsten Anforderungen für berufliche Aufenthalte ab. Der kleine, persönlich geführte Rahmen ist bewusst auf ruhige und verlässliche Aufenthalte statt auf günstige Massenunterbringung ausgerichtet.",
                "Besonders interessant sind mehrtägige Aufenthalte von Sonntag bis Freitag, wiederkehrende Firmenbuchungen und mehrere Arbeitswochen. Direkte Abstimmung und Rechnung für Firmenaufenthalte sind möglich.",
                "Suchbegriffe wie Monteurzimmer Wachau oder Firmenunterkunft Melk Krems führen ebenfalls zu dieser Seite. Inhaltlich richtet sich das Angebot jedoch bevorzugt an Geschäftsreisende, Servicetechniker, Projektverantwortliche und spezialisierte Fachkräfte."
            ],
            "features":[
                ("📶","WLAN","Für E-Mail, Planung, Videocalls und Arbeit unterwegs."),
                ("🚗","Parkplatz","Kostenlos direkt bei der Unterkunft."),
                ("🛏️","1–2 Personen","Ruhiges Gartenzimmer mit eigenem Bad."),
                ("🍳","Frühstück","Auf Wunsch vor dem Arbeitstag."),
                ("📅","So–Fr geeignet","Ideal für Geschäftsreisen, Service- und Projektwochen."),
                ("🏢","Firmenbuchungen","Mehrtägige und wiederkehrende Aufenthalte direkt abstimmen.")
            ],
            "hero_image":"images/gartenzimmer-04-web.jpg",
            "hero_image_alt":"Ruhige Business-Unterkunft bei Zuhause am Bach zwischen Melk und Krems",
            "hero_image_caption":"Gartenzimmer für Geschäftsreisende, Servicetechniker, Projektleiter und Fachkräfte.",
            "secondary_image":"images/gaestekueche-zuhause-am-bach-v2.webp",
            "secondary_image_alt":"Gästeküche für Geschäftsreisende und Firmenaufenthalte bei Zuhause am Bach",
            "secondary_image_caption":"Praktische Infrastruktur für mehrtägige berufliche Aufenthalte.",
            "faq":[
                {"@type":"Question","name":"Für wen ist die Business-Unterkunft zwischen Melk und Krems gedacht?","acceptedAnswer":{"@type":"Answer","text":"Vor allem für Geschäftsreisende, Servicetechniker, Projektleiter und qualifizierte Fachkräfte, die eine ruhige Unterkunft für ein oder zwei Personen suchen."}},
                {"@type":"Question","name":"Ist die Unterkunft auch für spezialisierte Monteure geeignet?","acceptedAnswer":{"@type":"Answer","text":"Ja. Qualifizierte Montage-, Service- und Inbetriebnahmeeinsätze sind willkommen, sofern der gewünschte Zeitraum verfügbar ist."}},
                {"@type":"Question","name":"Sind Aufenthalte von Sonntag bis Freitag möglich?","acceptedAnswer":{"@type":"Answer","text":"Ja, sofern die Reisedaten verfügbar sind. Solche Arbeitswochen sind besonders in den Wintermonaten interessant."}},
                {"@type":"Question","name":"Können Firmen mehrere Nächte oder wiederkehrend buchen?","acceptedAnswer":{"@type":"Answer","text":"Ja. Mehrtägige und wiederkehrende Firmenaufenthalte können direkt angefragt und abgestimmt werden."}},
                {"@type":"Question","name":"Wie kann ein Firmenaufenthalt angefragt werden?","acceptedAnswer":{"@type":"Answer","text":"Freie Termine und Preise können auf der offiziellen Website geprüft werden. Zusätzliche Anforderungen können direkt mit den Gastgebern abgestimmt werden."}}
            ],
        },
        "marillenbluete": {
            "title":"Marillenblüte Wachau Unterkunft | Zuhause am Bach Aggsbach",
            "description":"Unterkunft zur Marillenblüte in der Wachau: ruhig in Aggsbach Markt übernachten, Blüte flexibel erleben und direkt bei Zuhause am Bach buchen.",
            "canonical":"https://www.zuhauseambach-wachau.at/marillenbluete-wachau-unterkunft",
            "h1":"Unterkunft zur Marillenblüte in der Wachau",
            "lead":"Wenn die Wachauer Marillenbäume blühen, ist Aggsbach Markt eine ruhige Basis für Ausflüge zwischen Melk, Spitz, Dürnstein und Krems. Den exakten Blühzeitpunkt bestimmt jedes Jahr das Wetter – deshalb lohnt sich flexible Reiseplanung.",
            "eyebrow":"Frühling · Wachau · Marillenblüte",
            "subheading":"Marillenblüte erleben und ruhig in der Wachau übernachten",
            "paragraphs":["Die Marillenblüte gehört zu den bekanntesten Frühlingsmomenten der Wachau. Der tatsächliche Beginn und die Dauer lassen sich nicht seriös Monate im Voraus auf einen festen Tag festlegen.","Zuhause am Bach liegt in Aggsbach Markt und eignet sich als Ausgangspunkt für Fahrten und Spaziergänge durch die Wachau, ohne an einen einzelnen Veranstaltungsort gebunden zu sein.","Wer die Blüte gezielt erleben möchte, sollte kurz vor der Reise die aktuellen Blütenmeldungen der offiziellen Wachau-Information prüfen und den Aufenthalt direkt nach Verfügbarkeit buchen."],
            "features":[("🌸","Marillenblüte","Frühlingszeit in der Wachau flexibel erleben."),("📍","Aggsbach Markt","Ruhige Basis zwischen Melk und Krems."),("🍳","Frühstück","Auf Wunsch vor dem Ausflug."),("📅","Direkt planen","Freie Termine live prüfen.")],
            "hero_image":"images/regionale-genussmomente-final.jpg",
            "hero_image_alt":"Wachauer Genuss und Marillenzeit bei Zuhause am Bach",
            "hero_image_caption":"Wachauer Marille als Teil der regionalen Reisezeit.",
            "secondary_image":"images/bach-hinterm-haus-v11.webp",
            "secondary_image_alt":"Ruhige Wachau-Landschaft bei Zuhause am Bach in Aggsbach Markt",
            "secondary_image_caption":"Ruhige Basis für Frühlingsausflüge durch die Wachau.",
            "faq":faq_direct,
        },
        "marillenernte": {
            "title":"Marillenernte Wachau Unterkunft | Marillenzeit bei Zuhause am Bach",
            "description":"Unterkunft zur Marillenernte in der Wachau: Marillenzeit meist im Juli erleben, ruhig in Aggsbach Markt übernachten und direkt buchen.",
            "canonical":"https://www.zuhauseambach-wachau.at/marillenernte-wachau-unterkunft",
            "h1":"Unterkunft zur Marillenernte und Marillenzeit in der Wachau",
            "lead":"Die Wachauer Marillenernte liegt typischerweise rund um die Sommermitte. Zuhause am Bach in Aggsbach Markt ist eine ruhige Basis für Genuss, Ausflüge und die Marillenzeit zwischen Melk und Krems.",
            "eyebrow":"Sommer · Wachau · Marillenzeit",
            "subheading":"Marillenernte, Genuss und Wachau-Aufenthalt verbinden",
            "paragraphs":["Die offizielle Wachau-Information beschreibt die Marillenernte als saisonales Ereignis rund um Mitte Juli; Witterung und Reifeentwicklung können den genauen Verlauf jedes Jahr verschieben.","Zur Marillenzeit verbinden viele Gäste regionale Produkte, Donauradweg, Wanderungen und Orte wie Spitz, Dürnstein, Melk oder Krems in einem Aufenthalt.","Zuhause am Bach bietet dafür ein ruhiges Gartenzimmer, Frühstück auf Wunsch und direkte Terminprüfung ohne Umweg über große Buchungsplattformen."],
            "features":[("🍑","Marillenzeit","Sommerliche Wachau und regionale Produkte."),("🚲","Donauradweg","Marillenzeit mit einer Radtour verbinden."),("🥾","Wandern","Welterbesteig und Genuss kombinieren."),("📅","Direkt buchen","Verfügbarkeit und Preis live prüfen.")],
            "hero_image":"images/regionale-genussmomente-final.jpg",
            "hero_image_alt":"Regionale Wachauer Genussmomente mit Marillenprodukten",
            "hero_image_caption":"Regionale Genussmomente gehören zur Wachauer Marillenzeit.",
            "secondary_image":"images/gartenzimmer-04-web.jpg",
            "secondary_image_alt":"Gartenzimmer bei Zuhause am Bach für die Wachauer Marillenzeit",
            "secondary_image_caption":"Ruhige Übernachtung während der Wachauer Marillenzeit.",
            "faq":faq_direct,
        },
        "seasonalhub": {
            "title":"Wachau Jahreszeiten Urlaub | Marillenblüte, Rad, Wandern & Winter",
            "description":"Wachau nach Jahreszeit planen: Marillenblüte, Marillenernte, Donauradweg, Welterbesteig, Jauerling, Advent und Winter mit Unterkunft in Aggsbach Markt.",
            "canonical":"https://www.zuhauseambach-wachau.at/wachau-jahreszeiten-urlaub",
            "h1":"Wachau zu jeder Jahreszeit erleben",
            "lead":"Von der Marillenblüte im Frühling über Rad- und Wanderetappen im Sommer bis zu Marillenzeit, Advent und Jauerling im Winter: Zuhause am Bach bündelt die wichtigsten Wachau-Reiseanlässe an einer Stelle.",
            "eyebrow":"Frühling · Sommer · Herbst · Winter",
            "subheading":"Die passende Wachau-Zeit für deine Reise",
            "paragraphs":[
                "Im Frühling stehen Marillenblüte und erste Wander- und Radetappen im Mittelpunkt. Der exakte Blühzeitpunkt bleibt wetterabhängig.",
                "Im Sommer verbinden viele Gäste Donauradweg, Welterbesteig und Marillenzeit. Aggsbach Markt eignet sich dabei als ruhige Basis zwischen Melk und Krems.",
                "Im Herbst und Winter folgen ruhige Wachau-Tage, Adventmärkte und wetterabhängige Ausflüge Richtung Jauerling. Für aktuelle Bedingungen gelten immer die offiziellen Veranstalter- und Betreiberinformationen."
            ],
            "features":[
                ("🌸","Frühling","Marillenblüte und erste Wachau-Ausflüge."),
                ("🚲","Sommer","Donauradweg, Welterbesteig und Marillenzeit."),
                ("🍂","Herbst","Ruhige Wachau-Tage und Genuss."),
                ("❄️","Winter","Advent, Jauerling und Winterausflüge.")
            ],
            "hero_image":"images/bach-hinterm-haus-v11.webp",
            "hero_image_alt":"Wachau zu verschiedenen Jahreszeiten bei Zuhause am Bach",
            "hero_image_caption":"Zuhause am Bach als ganzjährige Basis in Aggsbach Markt.",
            "secondary_image":"images/gartenzimmer-04-web.jpg",
            "secondary_image_alt":"Gartenzimmer bei Zuhause am Bach in der Wachau",
            "secondary_image_caption":"Ruhig übernachten und saisonale Wachau-Reiseanlässe verbinden.",
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
            "title":"Skisaison Jauerling Unterkunft Wachau | Skifahren & Übernachten",
            "description":"Unterkunft für die Skisaison am Jauerling: Flutlicht, Kinderskipark, Skischule und Skiverleih aktuell beim Betreiber prüfen und ruhig in Aggsbach Markt übernachten.",
            "canonical":"https://www.zuhauseambach-wachau.at/skifahren-jauerling-unterkunft-wachau",
            "h1":"Unterkunft für die Skisaison am Jauerling",
            "lead":"Zuhause am Bach ist eine ruhige Wachau-Unterkunft für Gäste, die einen Winterausflug Richtung Jauerling mit einer Übernachtung in Aggsbach Markt verbinden möchten.",
            "eyebrow":"Winter in der Wachau",
            "subheading":"Jauerling-Ausflug und ruhige Nacht kombinieren",
            "paragraphs":["Das Gartenzimmer bietet eine kleine, persönliche Basis in Aggsbach Markt für Wintertage in der Wachau.","Die Skiarena Jauerling bewirbt unter anderem Flutlichtskifahren, einen Kinderskipark sowie Skischule und Skiverleih direkt an der Piste. Winterbetrieb, Liftzeiten, Schnee- und Pistenstatus bleiben wetterabhängig und sollten vor der Fahrt immer auf jauerling.at geprüft werden.","Für nasse Outdoorbekleidung gibt es eine Trocknungsmöglichkeit; Frühstück ist auf Wunsch verfügbar."],
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


@app.get("/cs/ubytovani-wachau")
def seo_cz_wachau():
    return render_template("seo_landing_intl.html",
        lang="cs", locale="cs_CZ",
        title="Ubytování ve Wachau mezi Melkem a Kremží | Zuhause am Bach",
        description="Rodinné ubytování ve Wachau mezi Melkem a Kremží. Dunajská cyklostezka, stezka Welterbesteig Wachau, Jauerling, úschovna kol, snídaně na objednávku a přímá rezervace.",
        canonical="https://www.zuhauseambach-wachau.at/cs/ubytovani-wachau",
        h1="Ubytování ve Wachau mezi Melkem a Kremží",
        lead="Klidné rodinné ubytování v Aggsbach Markt pro cyklisty, turisty i hosty, kteří chtějí poznat Wachau vlastním tempem.",
        booking="Ověřit dostupnost a cenu",
        cards=[
            ("Dunajská cyklostezka","Bezpečné uložení kol, možnost nabíjení elektrokol a praktické zázemí pro cestu podél Dunaje."),
            ("Welterbesteig Wachau","Klidné zázemí pro pěší výlety, jednotlivé etapy stezky Welterbesteig a poznávání krajiny Wachau."),
            ("Melk a Kremže","Aggsbach Markt leží ve Wachau mezi Melkem a Kremží a je vhodným výchozím bodem pro výlety po regionu."),
            ("Jauerling a zima","Ubytování lze spojit s výlety na Jauerling, zimními procházkami i adventními návštěvami Wachau.")
        ],
        direct_title="Přímá rezervace na oficiálních stránkách",
        direct_text="Aktuální volné termíny a cenu si ověříte přímo u Zuhause am Bach. Dotazy a přání můžete řešit přímo s hostiteli.",
        location_title="Wachau jako výchozí bod",
        location_text="Dunaj, Melk, Kremže, Spitz, Dürnstein a další cíle ve Wachau lze pohodlně kombinovat podle vašeho programu.",
        language_title="Mluvíme česky",
        language_text="S českými hosty komunikujeme česky – před příjezdem, během pobytu i při přímé rezervaci."
    )


@app.get("/sk/ubytovanie-wachau")
def seo_sk_wachau():
    return render_template("seo_landing_intl.html",
        lang="sk", locale="sk_SK",
        title="Ubytovanie vo Wachau medzi Melkom a Kremsom | Zuhause am Bach",
        description="Rodinné ubytovanie vo Wachau medzi Melkom a Kremsom. Dunajská cyklotrasa, trasa Welterbesteig Wachau, Jauerling, úschovňa bicyklov, raňajky na objednávku a priama rezervácia.",
        canonical="https://www.zuhauseambach-wachau.at/sk/ubytovanie-wachau",
        h1="Ubytovanie vo Wachau medzi Melkom a Kremsom",
        lead="Pokojné rodinné ubytovanie v Aggsbach Markt pre cyklistov, turistov aj hostí, ktorí chcú spoznávať Wachau vlastným tempom.",
        booking="Overiť dostupnosť a cenu",
        cards=[
            ("Dunajská cyklotrasa","Bezpečné uloženie bicyklov, možnosť nabíjania elektrobicyklov a praktické zázemie na cestu popri Dunaji."),
            ("Welterbesteig Wachau","Pokojné zázemie na pešie výlety, jednotlivé etapy trasy Welterbesteig a spoznávanie krajiny Wachau."),
            ("Melk a Krems","Aggsbach Markt leží vo Wachau medzi Melkom a Kremsom a je vhodným východiskovým bodom na výlety po regióne."),
            ("Jauerling a zima","Pobyt môžete spojiť s výletmi na Jauerling, zimnými prechádzkami aj adventnými návštevami Wachau.")
        ],
        direct_title="Priama rezervácia na oficiálnej stránke",
        direct_text="Aktuálne voľné termíny a cenu si overíte priamo u Zuhause am Bach. Otázky a želania môžete riešiť priamo s hostiteľmi.",
        location_title="Wachau ako východiskový bod",
        location_text="Dunaj, Melk, Krems, Spitz, Dürnstein a ďalšie ciele vo Wachau môžete pohodlne kombinovať podľa svojho programu.",
        language_title="Hovoríme po slovensky",
        language_text="So slovenskými hosťami komunikujeme po slovensky – pred príchodom, počas pobytu aj pri priamej rezervácii."
    )




def _intl_wachau_page(lang: str):
    pages = {
        "en": dict(locale="en_GB", title="Wachau accommodation between Melk and Krems | Zuhause am Bach",
            description="Small personal accommodation in the Wachau between Melk and Krems. Danube Cycle Path, Wachau World Heritage Trail, Jauerling, breakfast and direct booking.",
            canonical="https://www.zuhauseambach-wachau.at/en/wachau-accommodation",
            h1="Accommodation in the Wachau between Melk and Krems",
            lead="A quiet, personal place to stay in Aggsbach Markt for cyclists, hikers and guests exploring the Wachau.",
            booking="Check availability & price",
            cards=[("Danube Cycle Path","Secure bicycle storage, e-bike charging and practical support for your Danube cycling stage."),("Wachau World Heritage Trail","A quiet base for hiking stages and walking days in the Wachau."),("Melk & Krems","Aggsbach Markt lies between Melk and Krems and works well as a base for exploring the region."),("Jauerling & winter","Combine your stay with Jauerling, winter walks and Advent visits in the Wachau.")],
            direct_title="Book direct on the official website",direct_text="Check current availability and the direct price with Zuhause am Bach. Questions and special requests go straight to your hosts.",
            location_title="A base for the Wachau",location_text="The Danube, Melk, Krems, Spitz, Dürnstein and other Wachau destinations can be combined easily from Aggsbach Markt.",
            language_title="International guests welcome",language_text="Direct booking information is available in English, with personal contact before and during your stay."),
        "hu": dict(locale="hu_HU", title="Wachau szállás Melk és Krems között | Zuhause am Bach",
            description="Kis, személyes szállás a Wachauban, Melk és Krems között. Duna menti kerékpárút, Welterbesteig, Jauerling, reggeli és közvetlen foglalás.",
            canonical="https://www.zuhauseambach-wachau.at/hu/wachau-szallas",
            h1="Szállás a Wachauban Melk és Krems között",
            lead="Nyugodt, személyes szállás Aggsbach Marktban kerékpárosoknak, túrázóknak és a Wachaut felfedező vendégeknek.",
            booking="Elérhetőség és ár ellenőrzése",
            cards=[("Duna menti kerékpárút","Biztonságos kerékpártároló, e-bike töltés és praktikus segítség a Duna menti túrához."),("Welterbesteig Wachau","Nyugodt kiindulópont gyalogtúrákhoz és wachaui túranapokhoz."),("Melk és Krems","Aggsbach Markt Melk és Krems között fekszik, jó kiindulópont a régió felfedezéséhez."),("Jauerling és tél","A szállás összeköthető Jauerling-kirándulással, téli sétákkal és adventi programokkal.")],
            direct_title="Közvetlen foglalás a hivatalos oldalon",direct_text="Az aktuális szabad időpontokat és a közvetlen árat a Zuhause am Bach hivatalos oldalán ellenőrizheti.",
            location_title="Kiindulópont a Wachauban",location_text="A Duna, Melk, Krems, Spitz, Dürnstein és más wachaui célpontok könnyen kombinálhatók.",
            language_title="Személyes kapcsolat",language_text="A foglalás közvetlenül a szállásadóval történik, közvetítő nélkül."),
        "nl": dict(locale="nl_NL", title="Accommodatie in de Wachau tussen Melk en Krems | Zuhause am Bach",
            description="Kleinschalige accommodatie in de Wachau tussen Melk en Krems. Donauradweg, Welterbesteig, Jauerling, ontbijt en direct boeken.",
            canonical="https://www.zuhauseambach-wachau.at/nl/accommodatie-wachau",
            h1="Accommodatie in de Wachau tussen Melk en Krems",
            lead="Een rustige, persoonlijk gerunde accommodatie in Aggsbach Markt voor fietsers, wandelaars en gasten die de Wachau willen ontdekken.",
            booking="Beschikbaarheid & prijs bekijken",
            cards=[("Donauradweg","Veilige fietsenstalling, e-bike laden en praktische ondersteuning voor uw fietsroute langs de Donau."),("Welterbesteig Wachau","Een rustige uitvalsbasis voor wandelroutes en etappes door de Wachau."),("Melk & Krems","Aggsbach Markt ligt tussen Melk en Krems en is een goede uitvalsbasis voor de regio."),("Jauerling & winter","Combineer uw verblijf met Jauerling, winterwandelingen en Advent in de Wachau.")],
            direct_title="Direct boeken via de officiële website",direct_text="Controleer actuele beschikbaarheid en de directe prijs bij Zuhause am Bach. Vragen en wensen komen rechtstreeks bij de hosts terecht.",
            location_title="Uitvalsbasis voor de Wachau",location_text="De Donau, Melk, Krems, Spitz, Dürnstein en andere Wachau-bestemmingen zijn goed te combineren.",
            language_title="Nederlandstalige informatie",language_text="Belangrijke informatie over verblijf, beschikbaarheid en direct boeken is in het Nederlands beschikbaar."),
        "pl": dict(locale="pl_PL", title="Nocleg w Wachau między Melk a Krems | Zuhause am Bach",
            description="Kameralny nocleg w Wachau między Melk a Krems. Dunajska Trasa Rowerowa, Welterbesteig, Jauerling, śniadanie i rezerwacja bezpośrednia.",
            canonical="https://www.zuhauseambach-wachau.at/pl/nocleg-wachau",
            h1="Nocleg w Wachau między Melk a Krems",
            lead="Spokojny, kameralny nocleg w Aggsbach Markt dla rowerzystów, turystów pieszych i gości zwiedzających Wachau.",
            booking="Sprawdź dostępność i cenę",
            cards=[("Dunajska Trasa Rowerowa","Bezpieczne miejsce na rowery, ładowanie e-bike'ów i praktyczne wsparcie na trasie wzdłuż Dunaju."),("Welterbesteig Wachau","Spokojna baza na piesze etapy i wycieczki po Wachau."),("Melk i Krems","Aggsbach Markt leży między Melk a Krems i jest dobrym punktem wypadowym do zwiedzania regionu."),("Jauerling i zima","Pobyt można połączyć z Jauerlingiem, zimowymi spacerami i adwentem w Wachau.")],
            direct_title="Rezerwacja bezpośrednia na oficjalnej stronie",direct_text="Sprawdź aktualną dostępność i cenę bezpośrednią w Zuhause am Bach. Pytania i życzenia trafiają bezpośrednio do gospodarzy.",
            location_title="Baza do zwiedzania Wachau",location_text="Dunaj, Melk, Krems, Spitz, Dürnstein i inne miejsca w Wachau można wygodnie połączyć podczas pobytu.",
            language_title="Informacje po polsku",language_text="Najważniejsze informacje o pobycie, dostępności i rezerwacji bezpośredniej są dostępne po polsku."),
        "it": dict(locale="it_IT", title="Alloggio nella Wachau tra Melk e Krems | Zuhause am Bach",
            description="Piccolo alloggio nella Wachau tra Melk e Krems. Ciclabile del Danubio, Welterbesteig, Jauerling, colazione e prenotazione diretta.",
            canonical="https://www.zuhauseambach-wachau.at/it/alloggio-wachau",
            h1="Alloggio nella Wachau tra Melk e Krems",
            lead="Un alloggio tranquillo e personale ad Aggsbach Markt per ciclisti, escursionisti e ospiti che desiderano scoprire la Wachau.",
            booking="Verifica disponibilità e prezzo",
            cards=[("Ciclabile del Danubio","Deposito sicuro per biciclette, ricarica e-bike e supporto pratico lungo il Danubio."),("Welterbesteig Wachau","Una base tranquilla per escursioni a piedi e tappe nella Wachau."),("Melk e Krems","Aggsbach Markt si trova tra Melk e Krems ed è un buon punto di partenza per esplorare la regione."),("Jauerling e inverno","Il soggiorno può essere abbinato a Jauerling, passeggiate invernali e visite d'Avvento nella Wachau.")],
            direct_title="Prenota direttamente sul sito ufficiale",direct_text="Controlla disponibilità aggiornata e prezzo diretto presso Zuhause am Bach. Domande e richieste arrivano direttamente agli host.",
            location_title="Una base per la Wachau",location_text="Danubio, Melk, Krems, Spitz, Dürnstein e altre mete della Wachau possono essere facilmente combinate.",
            language_title="Informazioni in italiano",language_text="Le informazioni principali su soggiorno, disponibilità e prenotazione diretta sono disponibili in italiano."),
        "fr": dict(locale="fr_FR", title="Hébergement dans la Wachau entre Melk et Krems | Zuhause am Bach",
            description="Petit hébergement dans la Wachau entre Melk et Krems. Véloroute du Danube, Welterbesteig, Jauerling, petit-déjeuner et réservation directe.",
            canonical="https://www.zuhauseambach-wachau.at/fr/hebergement-wachau",
            h1="Hébergement dans la Wachau entre Melk et Krems",
            lead="Un hébergement calme et personnalisé à Aggsbach Markt pour cyclistes, randonneurs et visiteurs souhaitant découvrir la Wachau.",
            booking="Voir les disponibilités et le prix",
            cards=[("Véloroute du Danube","Local à vélos sécurisé, recharge des vélos électriques et aide pratique le long du Danube."),("Welterbesteig Wachau","Un point de départ calme pour les randonnées et étapes dans la Wachau."),("Melk et Krems","Aggsbach Markt se situe entre Melk et Krems et constitue une bonne base pour découvrir la région."),("Jauerling et hiver","Combinez votre séjour avec le Jauerling, des promenades hivernales et l'Avent dans la Wachau.")],
            direct_title="Réserver en direct sur le site officiel",direct_text="Consultez les disponibilités et le tarif direct de Zuhause am Bach. Questions et demandes arrivent directement aux hôtes.",
            location_title="Une base pour découvrir la Wachau",location_text="Le Danube, Melk, Krems, Spitz, Dürnstein et d'autres destinations de la Wachau se combinent facilement.",
            language_title="Informations en français",language_text="Les informations essentielles sur le séjour, les disponibilités et la réservation directe sont disponibles en français.")
,
        "ch": dict(locale="de_CH", title="Unterkunft Wachau zwischen Melk und Krems | Zuhause am Bach",
            description="Persönliche Unterkunft in der Wachau zwischen Melk und Krems für Gäste aus der Schweiz. Donauradweg, Welterbesteig, Jauerling, Frühstück und Direktbuchung.",
            canonical="https://www.zuhauseambach-wachau.at/ch/wachau-unterkunft",
            h1="Dini Unterkunft i de Wachau zwüsche Melk und Krems",
            lead="Ruhig übernachte in Aggsbach Markt – persönlich, direkt buchbar und ideal für Velo, Wandere und entspannte Täg i de Wachau.",
            booking="Verfügbarkeit & Priis prüefe",
            cards=[("Donauradweg","Sicheri Velounterbringig, E-Bike-Lade und praktische Unterstützig für dini Etappe a de Donau."),("Welterbesteig Wachau","E ruhigi Basis für Wanderetappe und Usflüg i de Wachau."),("Melk & Krems","Aggsbach Markt liit zwüsche Melk und Krems und isch e guete Ausgangspunkt für d Region."),("Jauerling & Winter","De Ufenthalt laht sich guet mit Jauerling, Winterspaziergäng und Advent i de Wachau verbinde.")],
            direct_title="Direkt uf de offizielle Website bueche",direct_text="Prüef freii Termin und de Direktpriis bi Zuhause am Bach. Frage und Wünsch chömed direkt zu üs.",
            location_title="Dini Basis für d Wachau",location_text="Donau, Melk, Krems, Spitz, Dürnstein und wiiteri Ziel i de Wachau sind vo Aggsbach Markt guet erreichbar.",
            language_title="Für Gäste us de Schwiiz",language_text="D wichtigste Infos sind im Schwiizer Stil formuliert; Buechig und Kontakt laufe direkt mit de Gastgeber.")    }
    return pages.get(lang)


@app.get("/en/wachau-accommodation")
@app.get("/hu/wachau-szallas")
@app.get("/nl/accommodatie-wachau")
@app.get("/pl/nocleg-wachau")
@app.get("/it/alloggio-wachau")
@app.get("/fr/hebergement-wachau")
@app.get("/ch/wachau-unterkunft")
def seo_intl_wachau():
    path_lang = request.path.strip("/").split("/")[0]
    data = _intl_wachau_page(path_lang)
    if not data:
        abort(404)
    return render_template("seo_landing_intl.html", lang=path_lang, **data)


@app.get("/uebernachten-aggsbach-markt")
def seo_aggsbach_markt():
    return render_template("seo_landing.html", **seo_landing_context("aggsbach"))


@app.get("/1-nacht-wachau")
@app.get("/1-nacht-wachau/")
def seo_eine_nacht_wachau():
    return render_template("seo_landing.html", **seo_landing_context("1nacht"))


@app.get("/radfahrer-unterkunft-wachau")
def seo_radfahrer_wachau():
    return render_template("seo_landing.html", **seo_landing_context("radfahrer"))

@app.get("/wanderer-unterkunft-wachau")
def seo_wanderer_wachau():
    return render_template("seo_landing.html", **seo_landing_context("wanderer"))


@app.get("/unterkunft-jauerling-wachau")
def seo_jauerling():
    return render_template("seo_landing.html", **seo_landing_context("jauerling"))


@app.get("/skifahren-jauerling-unterkunft-wachau")
def seo_ski_jauerling():
    return render_template("seo_landing.html", **seo_landing_context("ski"))

@app.get("/marillenbluete-wachau-unterkunft")
def seo_marillenbluete_wachau():
    return render_template("seo_landing.html", **seo_landing_context("marillenbluete"))


@app.get("/marillenernte-wachau-unterkunft")
def seo_marillenernte_wachau():
    return render_template("seo_landing.html", **seo_landing_context("marillenernte"))


@app.get("/wachau-jahreszeiten-urlaub")
def seo_wachau_jahreszeiten():
    return render_template("seo_landing.html", **seo_landing_context("seasonalhub"))


@app.get("/winterurlaub-wachau")
def seo_winterurlaub_wachau():
    return render_template("seo_landing.html", **seo_landing_context("winter"))

@app.get("/business-unterkunft-melk-krems")
def seo_business_unterkunft():
    return render_template("seo_landing.html", **seo_landing_context("business"))

@app.get("/monteurzimmer-wachau")
@app.get("/monteurzimmer-melk-krems")
@app.get("/firmenunterkunft-melk-krems")
@app.get("/arbeiterzimmer-wachau")
def business_search_aliases():
    return redirect(url_for("seo_business_unterkunft"), code=301)


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

@app.get("/donauradweg-unterkunft-wachau")
def legacy_donauradweg_redirect():
    return redirect(url_for("activity_donauradweg"), code=301)


@app.get("/welterbesteig-unterkunft-wachau")
def legacy_welterbesteig_redirect():
    return redirect(url_for("activity_welterbesteig"), code=301)


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
        "wachauer-advent-duernstein-2026": {
            "page_title": "Wachauer Advent Dürnstein 2026 Unterkunft | Zuhause am Bach",
            "meta_description": "Unterkunft zum Wachauer Advent Dürnstein 2026: 20.–22.11., 27.–29.11., 4.–8.12. und 11.–13.12. Ruhig in Aggsbach Markt übernachten und direkt buchen.",
            "canonical": "https://www.zuhauseambach-wachau.at/wachauer-advent-duernstein-2026-unterkunft",
            "event_name": "Wachauer Advent Dürnstein 2026",
            "start_date": "2026-11-20", "end_date": "2026-12-13",
            "display_date": "20.–22.11. · 27.–29.11. · 4.–8.12. · 11.–13.12.2026",
            "event_location": "Dürnstein", "event_city": "Dürnstein",
            "official_url": "https://www.donau.com/veranstaltungen/wachauer-advent-duernstein",
            "event_description": "Wachauer Advent in Dürnstein mit Adventmarkt, Stiftshof, Schloss und Weihnachtsweg an vier Terminblöcken im November und Dezember 2026.",
            "eyebrow": "Wachauer Advent 2026",
            "headline": "Unterkunft zum Wachauer Advent Dürnstein 2026",
            "intro": "Dürnstein verbindet Adventstimmung, historische Altstadt und Donau. Zuhause am Bach in Aggsbach Markt ist eine ruhige Wachau-Basis für ein Adventwochenende mit direkter Buchungsmöglichkeit.",
            "scarcity_text": "Die vier bestätigten Dürnstein-Terminblöcke sind starke Nachfragezeiten. Für Freitag und Samstag schützt ein Mindestaufenthalt von zwei Nächten die knappen Wochenenden.",
        },
        "burgadvent-aggstein-2026": {
            "page_title": "Burgadvent Aggstein 2026 Unterkunft Wachau | Zuhause am Bach",
            "meta_description": "Unterkunft zum Burgadvent Aggstein 2026: 30.10.–1.11., 6.–8.11., 13.–15.11. und 20.–22.11. Ruhig in Aggsbach Markt übernachten.",
            "canonical": "https://www.zuhauseambach-wachau.at/burgadvent-aggstein-2026-unterkunft",
            "event_name": "Burgadvent auf Aggstein 2026",
            "start_date": "2026-10-30", "end_date": "2026-11-22",
            "display_date": "30.10.–1.11. · 6.–8.11. · 13.–15.11. · 20.–22.11.2026",
            "event_location": "Burgruine Aggstein", "event_city": "Aggstein",
            "official_url": "https://ruineaggstein.at/veranstaltungen/burgadvent",
            "event_description": "Burgadvent auf der Burgruine Aggstein an vier Wochenenden mit Kunsthandwerk, Kulinarik und mittelalterlicher Atmosphäre.",
            "eyebrow": "Burgadvent 2026",
            "headline": "Unterkunft zum Burgadvent auf Aggstein 2026",
            "intro": "Der Burgadvent auf Aggstein ist ein besonders früher Advent-Anlass in der Wachau. Zuhause am Bach in Aggsbach Markt eignet sich als ruhige Unterkunft für ein Wochenende zwischen Burg, Donau und Wachau.",
            "scarcity_text": "Die bestätigten Burgadvent-Wochenenden werden als starke Nachfragefenster behandelt. Freitag und Samstag sind deshalb auf zwei Nächte ausgelegt.",
        },
        "melker-advent-2026": {
            "page_title": "Melker Advent 2026 Unterkunft Wachau | Zuhause am Bach",
            "meta_description": "Unterkunft zum Melker Advent 2026: 27.11.–20.12. in der Melker Altstadt. Ruhig in Aggsbach Markt übernachten und direkt buchen.",
            "canonical": "https://www.zuhauseambach-wachau.at/melker-advent-2026-unterkunft",
            "event_name": "Melker Advent 2026",
            "start_date": "2026-11-27", "end_date": "2026-12-20",
            "display_date": "27. Nov.–20. Dez. 2026",
            "event_location": "Melker Altstadt", "event_city": "Melk",
            "official_url": "https://www.melk.gv.at/melkeradvent",
            "event_description": "Melker Advent in der Altstadt mit Musik, Kulinarik, Kunsthandwerk und Programm an den Adventwochenenden.",
            "eyebrow": "Melker Advent 2026",
            "headline": "Unterkunft zum Melker Advent 2026",
            "intro": "Der Melker Advent verbindet Altstadt, Stiftkulisse und vorweihnachtliches Programm. Zuhause am Bach bietet eine ruhige Wachau-Unterkunft für Gäste, die Melk und die Donau miteinander verbinden möchten.",
            "scarcity_text": "Die Adventwochenenden in Melk sind als stärkere Nachfragezeiten hinterlegt. Wer einen bestimmten Freitag oder Samstag möchte, sollte den Termin früh direkt prüfen.",
        },
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


@app.get("/wachauer-advent-duernstein-2026-unterkunft")
def event_duernstein_advent_2026():
    return render_template("event_landing.html", **event_landing_context("wachauer-advent-duernstein-2026"))


@app.get("/burgadvent-aggstein-2026-unterkunft")
def event_aggstein_advent_2026():
    return render_template("event_landing.html", **event_landing_context("burgadvent-aggstein-2026"))


@app.get("/melker-advent-2026-unterkunft")
def event_melk_advent_2026():
    return render_template("event_landing.html", **event_landing_context("melker-advent-2026"))


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
        "https://www.zuhauseambach-wachau.at/cs/ubytovani-wachau",
        "https://www.zuhauseambach-wachau.at/sk/ubytovanie-wachau",
        "https://www.zuhauseambach-wachau.at/en/",
        "https://www.zuhauseambach-wachau.at/cs/",
        "https://www.zuhauseambach-wachau.at/sk/",
        "https://www.zuhauseambach-wachau.at/hu/",
        "https://www.zuhauseambach-wachau.at/nl/",
        "https://www.zuhauseambach-wachau.at/pl/",
        "https://www.zuhauseambach-wachau.at/it/",
        "https://www.zuhauseambach-wachau.at/es/",
        "https://www.zuhauseambach-wachau.at/fr/",
        "https://www.zuhauseambach-wachau.at/ar/",
        "https://www.zuhauseambach-wachau.at/en/wachau-accommodation",
        "https://www.zuhauseambach-wachau.at/hu/wachau-szallas",
        "https://www.zuhauseambach-wachau.at/nl/accommodatie-wachau",
        "https://www.zuhauseambach-wachau.at/pl/nocleg-wachau",
        "https://www.zuhauseambach-wachau.at/it/alloggio-wachau",
        "https://www.zuhauseambach-wachau.at/fr/hebergement-wachau",
        "https://www.zuhauseambach-wachau.at/ch/",
        "https://www.zuhauseambach-wachau.at/ch/wachau-unterkunft",
        "https://www.zuhauseambach-wachau.at/uebernachten-aggsbach-markt",
        "https://www.zuhauseambach-wachau.at/1-nacht-wachau",
        "https://www.zuhauseambach-wachau.at/radfahrer-unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/wanderer-unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/unterkunft-jauerling-wachau",
        "https://www.zuhauseambach-wachau.at/skifahren-jauerling-unterkunft-wachau",
        "https://www.zuhauseambach-wachau.at/marillenbluete-wachau-unterkunft",
        "https://www.zuhauseambach-wachau.at/marillenernte-wachau-unterkunft",
        "https://www.zuhauseambach-wachau.at/winterurlaub-wachau",
        "https://www.zuhauseambach-wachau.at/business-unterkunft-melk-krems",
        "https://www.zuhauseambach-wachau.at/unterkunft-donauradweg-wachau",
        "https://www.zuhauseambach-wachau.at/unterkunft-welterbesteig-wachau",
        "https://www.zuhauseambach-wachau.at/wachau-aktivurlaub-2027-2028",
        "https://www.zuhauseambach-wachau.at/wachau-events-2027-2028",
        "https://www.zuhauseambach-wachau.at/wachauer-advent-duernstein-2026-unterkunft",
        "https://www.zuhauseambach-wachau.at/burgadvent-aggstein-2026-unterkunft",
        "https://www.zuhauseambach-wachau.at/melker-advent-2026-unterkunft",
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


@app.get("/llms.txt")
def llms_txt():
    body = """# Zuhause am Bach – Wachau

Official website: https://www.zuhauseambach-wachau.at/
Location: Aggsbach Markt, Wachau, Lower Austria
Type: Small personal accommodation / guest room with direct booking

## Primary travel topics
- Wachau accommodation: https://www.zuhauseambach-wachau.at/unterkunft-wachau
- Seasonal Wachau travel: https://www.zuhauseambach-wachau.at/wachau-jahreszeiten-urlaub
- Donauradweg accommodation: https://www.zuhauseambach-wachau.at/unterkunft-donauradweg-wachau
- Welterbesteig accommodation: https://www.zuhauseambach-wachau.at/unterkunft-welterbesteig-wachau
- Radfahrer-Unterkunft Wachau: https://www.zuhauseambach-wachau.at/radfahrer-unterkunft-wachau
- Wanderer-Unterkunft Wachau: https://www.zuhauseambach-wachau.at/wanderer-unterkunft-wachau
- Marillenblüte Wachau: https://www.zuhauseambach-wachau.at/marillenbluete-wachau-unterkunft
- Marillenernte / Marillenzeit: https://www.zuhauseambach-wachau.at/marillenernte-wachau-unterkunft
- Jauerling ski season: https://www.zuhauseambach-wachau.at/skifahren-jauerling-unterkunft-wachau
- Winter in the Wachau: https://www.zuhauseambach-wachau.at/winterurlaub-wachau
- Business accommodation / Firmenunterkunft Melk–Krems for business travellers, service technicians, project managers, commissioning specialists and qualified technical staff: https://www.zuhauseambach-wachau.at/business-unterkunft-melk-krems
- Wachau events: https://www.zuhauseambach-wachau.at/wachau-events-2027-2028

## Direct-booking features
One-night stays are generally possible when available. Bicycle storage, e-bike charging, breakfast on request, drying options and luggage transfer on request are available depending on the stay.

## Official profiles and references
- Facebook: https://www.facebook.com/ZuHauseamBach
- Instagram: https://www.instagram.com/altstadthans/
- Booking.com: https://www.booking.com/hotel/at/zu-hause-am-bach.de.html
- Donau Niederösterreich tourism listing: https://www.donau.com/wachau-nibelungengau-kremstal/unterkunft/zu-hause-am-bach-wachau
- Municipality of Aggsbach listing: https://www.aggsbach.gv.at/Zuhause_am_Bach_-_Privatzimmervermietung_3

## Seasonal discovery
- Wachauer Advent Dürnstein 2026: https://www.zuhauseambach-wachau.at/wachauer-advent-duernstein-2026-unterkunft
- Burgadvent Aggstein 2026: https://www.zuhauseambach-wachau.at/burgadvent-aggstein-2026-unterkunft
- Melker Advent 2026: https://www.zuhauseambach-wachau.at/melker-advent-2026-unterkunft

For current availability, prices and booking, use the official website.
"""
    return Response(body, mimetype="text/plain")


@app.post("/api/events")
def api_events():
    payload = request.get_json(silent=True) or {}
    event = str(payload.get("event", "")).strip()[:64]
    allowed_prefixes = (
        "landing_view", "room_selected", "extras_selected",
        "availability_started", "availability_result_",
        "checkout_started", "booking_abandoned",
        "gallery_open", "panorama_open",
        "business_landing_view", "business_booking_cta_click",
    )
    if not event or not any(event == prefix or event.startswith(prefix) for prefix in allowed_prefixes):
        return Response(status=204)
    with db() as conn:
        conn.execute(
            "INSERT INTO site_events(event, created_at, visitor_hash, country_code) VALUES (?, ?, ?, ?)",
            (event, datetime.now().isoformat(timespec="seconds"), _visitor_hash(), _request_country_code()),
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
    _record_search_analytics(room, arrival, departure, ok)
    if ok:
        _record_demand_check(room, arrival, departure)
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
            WHERE room=?
            """,
            (room,),
        ).fetchall()
        central_closed = conn.execute(
            """
            SELECT day FROM central_overrides
            WHERE room=? AND availability=0 AND day>=? AND day<?
            """,
            (room, first.isoformat(), next_month.isoformat()),
        ).fetchall()

    for row in external:
        start_d, end_d = parse_date(row["start_date"]), parse_date(row["end_date"])
        current = max(first, start_d)
        while current < min(next_month, end_d):
            states[current.isoformat()] = "booking"
            current += timedelta(days=1)

    for row in central_closed:
        states[str(row["day"])] = "booking"

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

def resend_existing_booking_mail(booking_id: int) -> None:
    with db() as conn:
        booking = conn.execute("SELECT id,payment_method,status FROM bookings WHERE id=?", (booking_id,)).fetchone()

    sender = app.extensions.get("zab_send_confirmation")
    if sender:
        try:
            ok = bool(sender(booking_id))
            if ok:
                app.logger.info("booking_mail_existing_ok booking_id=%s", booking_id)
            else:
                app.logger.error("booking_mail_existing_failed booking_id=%s", booking_id)
        except Exception:
            app.logger.exception("booking_mail_existing_exception booking_id=%s", booking_id)

    if booking and booking["payment_method"] == "Vor Ort" and booking["status"] in ("inquiry", "expired"):
        verifier = app.extensions.get("zab_send_onsite_verification")
        if verifier:
            try:
                verifier(booking_id)
            except Exception:
                app.logger.exception("onsite_verification_resend_failed booking_id=%s", booking_id)


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
        booking_source = request.form.get("source", "").strip()[:120]
        utm_medium = request.form.get("utm_medium", "").strip()[:120]
        utm_campaign = request.form.get("utm_campaign", "").strip()[:160]
        landing_page = request.form.get("landing_page", "").strip()[:300]
        referrer = request.form.get("referrer", "").strip()[:300]
        company = request.form.get("company", "").strip()[:160]
        invoice_address = request.form.get("invoice_address", "").strip()[:300]
        company_tax_id = request.form.get("company_tax_id", "").strip()[:120]
        company_reference = request.form.get("company_reference", "").strip()[:160]
        company_contact = request.form.get("company_contact", "").strip()[:160]
        company_email = request.form.get("company_email", "").strip()[:200]
        recurring_business = request.form.get("recurring_business") == "on"
        guest_message = request.form.get("message", "").strip()
        business_notes = []
        if company:
            business_notes.append(f"Firma/Auftraggeber: {company}")
        if invoice_address:
            business_notes.append(f"Rechnungsadresse: {invoice_address}")
        if company_tax_id:
            business_notes.append(f"UID/Steuerangabe: {company_tax_id}")
        if company_reference:
            business_notes.append(f"Kostenstelle/Bestellnummer: {company_reference}")
        if company_contact:
            business_notes.append(f"Firmen-Ansprechpartner: {company_contact}")
        if company_email:
            business_notes.append(f"Firmen-E-Mail: {company_email}")
        if recurring_business:
            business_notes.append("Wiederkehrende Arbeits-/Projektaufenthalte: ja")
        if business_notes:
            guest_message = " | ".join(business_notes + ([guest_message] if guest_message else []))
    except (KeyError, ValueError):
        flash("Bitte alle Pflichtfelder korrekt ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    if payment_method == "PayPal":
        flash("PayPal-Zahlungen bitte über den sicheren PayPal-Button starten.", "error")
        return redirect(url_for("index") + "#booking")
    if payment_method not in {"Banküberweisung", "Vor Ort"}:
        flash("Bitte eine gültige Zahlungsart wählen.", "error")
        return redirect(url_for("index") + "#booking")

    if payment_method == "Vor Ort" and (arrival - date.today()).days < 3:
        flash("Zahlung vor Ort ist bei Anreise in weniger als 3 Tagen nicht verfügbar. Bitte Banküberweisung oder PayPal wählen.", "error")
        return redirect(url_for("index") + "#booking")

    if idempotency_key:
        with db() as conn:
            existing = conn.execute(
                "SELECT * FROM bookings WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        if existing:
            resend_existing_booking_mail(int(existing["id"]))
            return booking_success_response(existing)

    ok, message = room_available(room, arrival, departure)
    if not ok:
        flash(message, "error")
        return redirect(url_for("index") + "#booking")

    if not all([first_name, last_name, email, phone]):
        flash("Bitte Name, E-Mail und Telefonnummer ausfüllen.", "error")
        return redirect(url_for("index") + "#booking")

    breakdown = price_breakdown(room, arrival, departure, adults, chosen, coupon_code)
    total = breakdown["total"]
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
                 created_at, idempotency_key, price_breakdown_json,
                 source,utm_medium,utm_campaign,landing_page,referrer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'inquiry', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid, room, arrival.isoformat(), departure.isoformat(), adults,
                    1 if breakfast else 0, first_name, last_name, email, phone,
                    guest_message, payment_method, total,
                    datetime.now().isoformat(timespec="seconds"), idempotency_key,
                    json.dumps(breakdown, ensure_ascii=False),
                    booking_source, utm_medium, utm_campaign, landing_page, referrer,
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
                resend_existing_booking_mail(int(existing["id"]))
                return booking_success_response(existing)
        flash("Die Buchung wurde bereits verarbeitet. Bitte Seite aktualisieren.", "error")
        return redirect(url_for("index") + "#booking")

    if app.extensions.get("zab_ensure_tokens"):
        app.extensions["zab_ensure_tokens"](booking_id)
    if app.extensions.get("v6_ensure_checkin_token"):
        app.extensions["v6_ensure_checkin_token"](booking_id)
    sender = app.extensions.get("zab_send_confirmation")
    if sender:
        try:
            ok = bool(sender(booking_id))
            if ok:
                app.logger.info("booking_mail_sent booking_id=%s", booking_id)
            else:
                app.logger.error("booking_saved_but_mail_failed booking_id=%s", booking_id)
        except Exception:
            app.logger.exception("booking notification failed for booking_id=%s", booking_id)

    if payment_method == "Vor Ort":
        verifier = app.extensions.get("zab_send_onsite_verification")
        if verifier:
            try:
                verified_mail_queued = bool(verifier(booking_id))
                if not verified_mail_queued:
                    app.logger.error("onsite_verification_mail_failed booking_id=%s", booking_id)
            except Exception:
                app.logger.exception("onsite_verification_mail_exception booking_id=%s", booking_id)

    with db() as conn:
        booking_row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return booking_success_response(booking_row)



def _twilio_verify_post(path: str, data: dict) -> dict:
    account_sid = env_value("TWILIO_ACCOUNT_SID")
    auth_token = env_value("TWILIO_AUTH_TOKEN")
    service_sid = env_value("TWILIO_VERIFY_SERVICE_SID")
    if not all((account_sid, auth_token, service_sid)):
        raise RuntimeError("SMS-Verifizierung ist noch nicht konfiguriert.")
    body = urllib.parse.urlencode(data).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        f"https://verify.twilio.com/v2/Services/{service_sid}/{path}",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Zuhause-am-Bach/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _paypal_base_url() -> str:
    return "https://api-m.paypal.com" if env_value("PAYPAL_ENV").lower() == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_access_token() -> str:
    client_id = env_value("PAYPAL_CLIENT_ID")
    client_secret = env_value("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("PayPal ist noch nicht vollständig konfiguriert.")
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        _paypal_base_url() + "/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["access_token"]


def _paypal_json(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    token = _paypal_access_token()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        _paypal_base_url() + path,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _onsite_amounts(total_value, percent: int):
    total = Decimal(str(total_value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    now_amount = (total * Decimal(percent) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    remainder = (total - now_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total, now_amount, remainder


def _booking_breakdown(booking):
    try:
        data = json.loads(booking["price_breakdown_json"] or "{}")
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"room_total": float(booking["total"]), "extras": [], "discounts": [], "total": float(booking["total"])}


@app.get("/onsite-security/<token>")
def onsite_security(token):
    with db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
            (token,),
        ).fetchone()
    if not booking or not booking["onsite_verified_at"]:
        return Response("E-Mail-Verifizierung erforderlich.", status=403)
    return render_template(
        "onsite_security.html",
        booking=booking,
        breakdown=_booking_breakdown(booking),
    )


@app.post("/onsite-sms/send/<token>")
def onsite_sms_send(token):
    with db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
            (token,),
        ).fetchone()
    if not booking or not booking["onsite_verified_at"]:
        return Response("Nicht freigegeben.", status=403)
    try:
        result = _twilio_verify_post("Verifications", {"To": booking["phone"], "Channel": "sms"})
        if result.get("status") not in ("pending", "approved"):
            raise RuntimeError("SMS konnte nicht gestartet werden.")
        with db() as conn:
            conn.execute(
                "UPDATE bookings SET sms_sent_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), booking["id"]),
            )
        flash("SMS-Code wurde gesendet.", "success")
    except Exception as exc:
        app.logger.exception("onsite_sms_send_failed booking_id=%s", booking["id"])
        flash(f"SMS konnte nicht gesendet werden: {exc}", "error")
    return redirect(url_for("onsite_security", token=token))


@app.post("/onsite-sms/check/<token>")
def onsite_sms_check(token):
    code = request.form.get("code", "").strip()
    if not (code.isdigit() and 4 <= len(code) <= 10):
        flash("Bitte den SMS-Code eingeben.", "error")
        return redirect(url_for("onsite_security", token=token))
    with db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
            (token,),
        ).fetchone()
    if not booking or not booking["onsite_verified_at"]:
        return Response("Nicht freigegeben.", status=403)
    try:
        result = _twilio_verify_post("VerificationCheck", {"To": booking["phone"], "Code": code})
        if result.get("status") != "approved":
            flash("SMS-Code ist nicht gültig.", "error")
            return redirect(url_for("onsite_security", token=token))
        now = datetime.now()
        hold_until = (now + timedelta(minutes=30)).isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET sms_verified_at=?, status='pending', payment_hold_expires_at=?
                   WHERE id=?""",
                (now.isoformat(timespec="seconds"), hold_until, booking["id"]),
            )
        flash("Telefonnummer bestätigt. Bitte Zahlungsoption auswählen.", "success")
    except Exception as exc:
        app.logger.exception("onsite_sms_check_failed booking_id=%s", booking["id"])
        flash(f"SMS-Verifizierung fehlgeschlagen: {exc}", "error")
    return redirect(url_for("onsite_security", token=token))


@app.post("/onsite-payment/<token>")
def onsite_payment_start(token):
    try:
        percent = int(request.form.get("percent", "0"))
    except ValueError:
        percent = 0
    if percent not in (50, 100):
        return Response("Ungültige Zahlungsoption.", status=400)
    with db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
            (token,),
        ).fetchone()
    if not booking or not booking["onsite_verified_at"]:
        return Response("E-Mail-Verifizierung erforderlich.", status=403)

    total, amount_now, remainder = _onsite_amounts(booking["total"], percent)
    base_url = env_value("PUBLIC_SITE_URL") or "https://www.zuhauseambach-wachau.at"
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": f"ZAB-{booking['id']:06d}",
            "description": f"Zuhause am Bach – {'50% Anzahlung' if percent == 50 else 'Vollzahlung'}",
            "amount": {"currency_code": "EUR", "value": f"{amount_now:.2f}"},
        }],
        "application_context": {
            "brand_name": "Zuhause am Bach – Wachau",
            "user_action": "PAY_NOW",
            "return_url": f"{base_url.rstrip('/')}/onsite-paypal-return/{token}?percent={percent}",
            "cancel_url": f"{base_url.rstrip('/')}/onsite-paypal-cancel/{token}",
        },
    }
    try:
        order = _paypal_json("/v2/checkout/orders", "POST", payload)
        order_id = order.get("id", "")
        approval_url = next((x.get("href") for x in order.get("links", []) if x.get("rel") == "approve"), "")
        if not order_id or not approval_url:
            raise RuntimeError("PayPal hat keine Zahlungsfreigabe geliefert.")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET deposit_percent=?, payment_status='initiated',
                       paypal_order_id=?, payment_hold_expires_at=?
                   WHERE id=?""",
                (
                    percent, order_id,
                    (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds"),
                    booking["id"],
                ),
            )
        return redirect(approval_url)
    except Exception as exc:
        app.logger.exception("onsite_paypal_create_failed booking_id=%s", booking["id"])
        flash(f"PayPal konnte nicht gestartet werden: {exc}", "error")
        return redirect(url_for("onsite_security", token=token))


@app.get("/onsite-paypal-return/<token>")
def onsite_paypal_return(token):
    order_id = request.args.get("token", "").strip()
    try:
        percent = int(request.args.get("percent", "0"))
    except ValueError:
        percent = 0
    with db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE onsite_verify_token=? AND payment_method='Vor Ort'",
            (token,),
        ).fetchone()
    if not booking or percent not in (50, 100) or not order_id or booking["paypal_order_id"] != order_id:
        return Response("Zahlung konnte nicht zugeordnet werden.", status=400)

    total, expected_now, remainder = _onsite_amounts(booking["total"], percent)
    if booking["payment_status"] in ("paid_partial", "paid_full") and float(booking["amount_paid"] or 0) > 0:
        return render_template(
            "onsite_paid.html", booking=booking, breakdown=_booking_breakdown(booking),
            total=total, amount_paid=Decimal(str(booking["amount_paid"])), remainder=total-Decimal(str(booking["amount_paid"])),
            percent=booking["deposit_percent"],
        )

    try:
        capture = _paypal_json(f"/v2/checkout/orders/{order_id}/capture", "POST", {})
        if capture.get("status") != "COMPLETED":
            raise RuntimeError("PayPal-Zahlung ist noch nicht abgeschlossen.")
        captured = Decimal("0.00")
        for unit in capture.get("purchase_units", []):
            for item in (unit.get("payments", {}) or {}).get("captures", []):
                if item.get("status") == "COMPLETED":
                    captured += Decimal(str((item.get("amount") or {}).get("value", "0")))
        captured = captured.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if captured != expected_now:
            raise RuntimeError("Zahlungsbetrag stimmt nicht mit der Buchung überein.")

        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute(
                """UPDATE bookings
                   SET status='confirmed', amount_paid=?, deposit_percent=?,
                       payment_status=?, payment_reference=?, paid=?
                   WHERE id=?""",
                (
                    float(captured), percent,
                    "paid_full" if percent == 100 else "paid_partial",
                    order_id, 1 if percent == 100 else 0, booking["id"],
                ),
            )
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking["id"],)).fetchone()

        sender = app.extensions.get("zab_send_confirmation")
        if sender:
            try:
                sender(booking["id"])
            except Exception:
                app.logger.exception("onsite_paid_owner_mail_failed booking_id=%s", booking["id"])

        return render_template(
            "onsite_paid.html", booking=booking, breakdown=_booking_breakdown(booking),
            total=total, amount_paid=captured, remainder=remainder, percent=percent,
        )
    except Exception as exc:
        app.logger.exception("onsite_paypal_capture_failed booking_id=%s", booking["id"])
        flash(f"Zahlung konnte nicht bestätigt werden: {exc}", "error")
        return redirect(url_for("onsite_security", token=token))


@app.get("/onsite-paypal-cancel/<token>")
def onsite_paypal_cancel(token):
    flash("PayPal-Zahlung wurde abgebrochen. Die Auswahl kann erneut gestartet werden.", "error")
    return redirect(url_for("onsite_security", token=token))


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
        cancelled_at = datetime.now().isoformat(timespec="seconds") if action == "cancel" else ""
        conn.execute(
            "UPDATE bookings SET status=?, cancelled_at=? WHERE id=?",
            (mapping[action], cancelled_at, booking_id),
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
    manager = app.extensions.get("zab_manage_rate_days")
    if callable(manager):
        manager("Bachblick", date.today(), date.today() + timedelta(days=370), manual_base=True)
    flash("Preise gespeichert; Portalpreise mit 5 % Aufschlag (max. 149 €) sind vorgemerkt; Übertragungsstatus prüfen.","success"); return redirect(url_for("admin"))

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


def cleanup_cancelled_bookings(retention_days: int = 14) -> int:
    """Delete cancelled booking requests after the retention period."""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat(timespec="seconds")
    with db() as conn:
        # Legacy cancelled rows had no cancellation timestamp. Their creation
        # time is the safest available fallback and removes old test clutter.
        conn.execute(
            """UPDATE bookings
               SET cancelled_at=created_at
               WHERE status='cancelled'
                 AND COALESCE(cancelled_at, '')=''"""
        )
        cur = conn.execute(
            """DELETE FROM bookings
               WHERE status='cancelled'
                 AND COALESCE(NULLIF(cancelled_at, ''), created_at) < ?""",
            (cutoff,),
        )
        deleted = int(cur.rowcount or 0)
    if deleted:
        app.logger.info("cancelled_booking_cleanup deleted=%s retention_days=%s", deleted, retention_days)
    return deleted


_cancelled_cleanup_last_run = datetime.min


@app.before_request
def automatic_cancelled_booking_cleanup():
    """Run the cancelled-booking cleanup at most once every 24 hours per worker."""
    global _cancelled_cleanup_last_run
    now = datetime.now()
    if now - _cancelled_cleanup_last_run < timedelta(hours=24):
        return None
    _cancelled_cleanup_last_run = now
    try:
        cleanup_cancelled_bookings(14)
    except Exception:
        app.logger.exception("cancelled_booking_cleanup_failed")
    return None


init_db()
cleanup_cancelled_bookings(14)
init_addons(app, DB_PATH, db, require_admin, ROOMS, PAYPAL_EMAIL)

# Optional one-shot resend used for operational recovery. Keep this synchronous so
# the process cannot exit before the mail attempt completes.
_resend_booking_id = os.environ.get("RESEND_BOOKING_ID_ON_START", "").strip()
if _resend_booking_id.isdigit():
    try:
        _resend_sender = app.extensions.get("zab_send_confirmation")
        if _resend_sender:
            _resend_ok = bool(_resend_sender(int(_resend_booking_id)))
            app.logger.warning(
                "startup_booking_resend booking_id=%s ok=%s",
                _resend_booking_id, _resend_ok,
            )
    except Exception:
        app.logger.exception("startup booking resend failed booking_id=%s", _resend_booking_id)
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

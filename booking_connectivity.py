from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html import escape

from flask import jsonify

AUTH_URL = "https://connectivity-authentication.booking.com/token-based-authentication/exchange"
RATE_URL = "https://supply-xml.booking.com/hotels/ota/OTA_HotelRateAmountNotif"

ROOM_ENV_KEYS = {
    "Bachblick": "BACHBLICK",
    "Marillenzimmer": "MARILLENZIMMER",
    "Weinbergzimmer": "WEINBERGZIMMER",
    "Donauzimmer": "DONAUZIMMER",
}

_token_lock = threading.Lock()
_token_value = ""
_token_expires_at = datetime.min.replace(tzinfo=timezone.utc)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _room_mapping(room: str) -> tuple[str, str]:
    key = ROOM_ENV_KEYS.get(room, room.upper().replace(" ", "_"))
    return (
        _env(f"BOOKING_ROOM_ID_{key}"),
        _env(f"BOOKING_RATE_ID_{key}"),
    )


def connectivity_status(room: str | None = None) -> dict:
    client_id = _env("BOOKING_CONNECTIVITY_CLIENT_ID")
    secret = _env("BOOKING_CONNECTIVITY_CLIENT_SECRET")
    hotel_id = _env("BOOKING_HOTEL_ID", "10657485")
    base = {
        "credentials_configured": bool(client_id and secret),
        "hotel_id_configured": bool(hotel_id),
        "hotel_id": hotel_id,
        "authentication": "token",
        "rate_endpoint": RATE_URL,
    }
    if room:
        room_id, rate_id = _room_mapping(room)
        base.update(
            room=room,
            room_id_configured=bool(room_id),
            rate_id_configured=bool(rate_id),
            configured=bool(client_id and secret and hotel_id and room_id and rate_id),
        )
    else:
        base["configured"] = bool(client_id and secret and hotel_id)
    return base


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    if not raw:
        return f"HTTP {exc.code}"
    try:
        payload = json.loads(raw)
        return str(payload.get("message") or payload.get("error") or raw)[:700]
    except Exception:
        return raw[:700]


def _token() -> str:
    global _token_value, _token_expires_at
    now = datetime.now(timezone.utc)
    if _token_value and now + timedelta(minutes=5) < _token_expires_at:
        return _token_value

    with _token_lock:
        now = datetime.now(timezone.utc)
        if _token_value and now + timedelta(minutes=5) < _token_expires_at:
            return _token_value

        client_id = _env("BOOKING_CONNECTIVITY_CLIENT_ID")
        secret = _env("BOOKING_CONNECTIVITY_CLIENT_SECRET")
        if not client_id or not secret:
            raise RuntimeError("Booking.com Connectivity-Zugang fehlt.")

        body = json.dumps({"client_id": client_id, "client_secret": secret}).encode("utf-8")
        req = urllib.request.Request(
            AUTH_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Zuhause-am-Bach-OS/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Booking.com Anmeldung fehlgeschlagen: {_read_http_error(exc)}") from exc
        token = str(payload.get("jwt") or "").strip()
        if not token:
            raise RuntimeError("Booking.com hat kein JWT geliefert.")
        _token_value = token
        _token_expires_at = now + timedelta(minutes=55)
        return token


def _response_error(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
        errors = []
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in {"Error", "Warning"}:
                text = element.attrib.get("ShortText") or element.attrib.get("Details") or (element.text or "")
                if text:
                    errors.append(text.strip())
        return " | ".join(errors)[:900]
    except Exception:
        return ""


def push_rate(room: str, day: date, price_eur: float) -> dict:
    """Push one nightly Booking.com rate using OTA_HotelRateAmountNotif.

    The call is only possible for properties connected through Booking.com
    Connectivity with a token machine account and mapped Booking room/rate IDs.
    """
    status = connectivity_status(room)
    if not status.get("configured"):
        return {
            "ok": False,
            "status": "not_configured",
            "message": "Booking.com Connectivity oder Zimmer-/Rate-Mapping fehlt.",
            **status,
        }

    price = round(float(price_eur), 2)
    if price < 5 or price > 50000:
        return {
            "ok": False,
            "status": "invalid_price",
            "message": "Booking.com akzeptiert diesen Preisbereich nicht.",
        }

    room_id, rate_id = _room_mapping(room)
    amount = int(round(price * 100))
    amount_mode = _env("BOOKING_RATE_AMOUNT_MODE", "after_tax").lower()
    amount_attr = "AmountBeforeTax" if amount_mode == "before_tax" else "AmountAfterTax"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    d = day.isoformat()

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<OTA_HotelRateAmountNotifRQ xmlns="http://www.opentravel.org/OTA/2003/05" TimeStamp="{escape(timestamp)}" Version="3.000">
  <RateAmountMessages>
    <RateAmountMessage LocatorID="1">
      <StatusApplicationControl Start="{escape(d)}" End="{escape(d)}" RatePlanCode="{escape(rate_id)}" InvTypeCode="{escape(room_id)}" />
      <Rates>
        <Rate>
          <BaseByGuestAmts>
            <BaseByGuestAmt {amount_attr}="{amount}" DecimalPlaces="2" CurrencyCode="EUR" />
          </BaseByGuestAmts>
        </Rate>
      </Rates>
    </RateAmountMessage>
  </RateAmountMessages>
</OTA_HotelRateAmountNotifRQ>'''.encode("utf-8")

    req = urllib.request.Request(
        RATE_URL,
        data=xml,
        method="POST",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept-Version": "1.1",
            "Content-Type": "application/xml",
            "Accept": "application/xml,text/xml",
            "User-Agent": "Zuhause-am-Bach-OS/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": "booking_http_error",
            "message": _read_http_error(exc),
            "http_status": exc.code,
        }
    except Exception as exc:
        return {"ok": False, "status": "unreachable", "message": str(exc)[:700]}

    error_text = _response_error(text)
    try:
        root = ET.fromstring(text)
        success = any(e.tag.rsplit("}", 1)[-1] == "Success" for e in root.iter())
    except Exception:
        success = "<Success" in text
    if not success:
        return {
            "ok": False,
            "status": "booking_rejected",
            "message": error_text or "Booking.com hat die Preisänderung nicht bestätigt.",
        }

    return {
        "ok": True,
        "status": "synced",
        "room": room,
        "date": d,
        "price_eur": price,
        "message": "Booking.com Preis bestätigt.",
        "warning": error_text,
    }


def init_booking_connectivity(app):
    app.extensions["zab_booking_push_rate"] = push_rate
    app.extensions["zab_booking_connectivity_status"] = connectivity_status
    app.extensions["zab_booking_connectivity_initialized"] = True

    @app.get("/health/booking-connectivity")
    def booking_connectivity_health():
        rooms = {}
        configured_rooms = getattr(app, "extensions", {}).get("zab_rooms")
        if isinstance(configured_rooms, dict):
            for room in configured_rooms:
                rooms[room] = connectivity_status(room)
        else:
            rooms["Bachblick"] = connectivity_status("Bachblick")
        configured = any(v.get("configured") for v in rooms.values())
        return jsonify(
            ok=True,
            adapter=True,
            connected=configured,
            property_id=_env("BOOKING_HOTEL_ID", "10657485"),
            rooms=rooms,
        ), 200

    return push_rate

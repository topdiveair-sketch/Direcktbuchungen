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
RESERVATIONS_URL = "https://secure-supply-xml.booking.com/hotels/xml/reservations"
RESERVATIONS_SUMMARY_URL = "https://secure-supply-xml.booking.com/hotels/xml/reservationssummary"

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


def internal_room_for_booking_id(room_type_id: str) -> str:
    wanted = str(room_type_id or "").strip()
    for room in ROOM_ENV_KEYS:
        room_id, _ = _room_mapping(room)
        if room_id and room_id == wanted:
            return room
    return ""


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
        "reservations_endpoint": RESERVATIONS_URL,
        "reservations_summary_endpoint": RESERVATIONS_SUMMARY_URL,
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


def _post_xml(url: str, xml: bytes, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        data=xml,
        method="POST",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/xml",
            "Accept": "application/xml,text/xml",
            "User-Agent": "Zuhause-am-Bach-OS/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_read_http_error(exc)) from exc


def _text(parent, path: str) -> str:
    node = parent.find(path)
    return (node.text or "").strip() if node is not None and node.text else ""


def _guest_count(room_node) -> int:
    total = 0
    for guest in room_node.findall("./guest_counts/guest_count"):
        try:
            total += int(guest.attrib.get("count", "0"))
        except Exception:
            pass
    if total:
        return total
    raw = _text(room_node, "numberofguests")
    try:
        return int(raw)
    except Exception:
        return 0


def _breakfast_value(room_node):
    meal = (_text(room_node, "meal_plan") + " " + _text(room_node, "info")).strip().casefold()
    if not meal:
        return None
    positive = ("breakfast" in meal and "included" in meal) or ("frühstück" in meal and "inbegriffen" in meal)
    negative = ("breakfast" in meal and ("not included" in meal or "excluded" in meal)) or ("frühstück" in meal and "nicht" in meal)
    if positive:
        return True
    if negative:
        return False
    return None


def _parse_bxml_reservations(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        raise RuntimeError(f"Booking.com Reservierungsantwort ist ungültig: {exc}") from exc

    records = []
    for reservation in root.findall(".//reservation"):
        reservation_id = _text(reservation, "id")
        customer = reservation.find("customer")
        first = _text(customer, "first_name") if customer is not None else ""
        last = _text(customer, "last_name") if customer is not None else ""
        country = _text(customer, "countrycode").upper() if customer is not None else ""
        booker_name = " ".join(x for x in (first, last) if x).strip()
        status = _text(reservation, "status") or "future"
        for room_node in reservation.findall("room"):
            room_type_id = _text(room_node, "id")
            guest_name = _text(room_node, "guest_name") or booker_name
            records.append({
                "reservation_id": reservation_id,
                "roomreservation_id": _text(room_node, "roomreservation_id"),
                "room_type_id": room_type_id,
                "room": internal_room_for_booking_id(room_type_id),
                "arrival": _text(room_node, "arrival_date"),
                "departure": _text(room_node, "departure_date"),
                "guest_name": guest_name,
                "country": country,
                "guests": _guest_count(room_node),
                "breakfast": _breakfast_value(room_node),
                "meal_plan": _text(room_node, "meal_plan"),
                "status": status,
            })
    return records


def fetch_future_reservations() -> dict:
    """Retrieve future Booking.com reservations for OS guest enrichment.

    reservationssummary is used first because it returns all future check-outs,
    including reservations from before the property was connected. For each
    parent reservation, the B.XML reservations endpoint is then queried by ID
    to enrich the room with country-of-residence and full current details.
    No payment-card fields are retained by this module.
    """
    base_status = connectivity_status()
    if not base_status.get("configured"):
        return {"ok": False, "status": "not_configured", "message": "Booking.com Connectivity-Zugang fehlt.", "reservations": []}
    hotel_id = _env("BOOKING_HOTEL_ID", "10657485")
    summary_xml = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><request><hotel_id>{escape(hotel_id)}</hotel_id></request>".encode("utf-8")
    try:
        summary_text = _post_xml(RESERVATIONS_SUMMARY_URL, summary_xml, timeout=90)
        summaries = _parse_bxml_reservations(summary_text)
    except Exception as exc:
        return {"ok": False, "status": "summary_failed", "message": str(exc)[:700], "reservations": []}

    # Fetch each parent once. A small property normally has only a handful of
    # future reservations. Limit protects the interactive Windows call.
    ids = []
    for row in summaries:
        rid = row.get("reservation_id")
        if rid and rid not in ids:
            ids.append(rid)
    ids = ids[:50]
    detailed_by_key = {}
    detail_errors = []
    for rid in ids:
        request_xml = (
            f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><request><hotel_id>{escape(hotel_id)}</hotel_id>"
            f"<id>{escape(str(rid))}</id></request>"
        ).encode("utf-8")
        try:
            detail_text = _post_xml(RESERVATIONS_URL, request_xml, timeout=90)
            for detail in _parse_bxml_reservations(detail_text):
                key = (detail.get("reservation_id"), detail.get("roomreservation_id"), detail.get("room_type_id"), detail.get("arrival"), detail.get("departure"))
                detailed_by_key[key] = detail
        except Exception as exc:
            detail_errors.append(f"{rid}: {str(exc)[:180]}")

    merged = []
    for summary in summaries:
        key = (summary.get("reservation_id"), summary.get("roomreservation_id"), summary.get("room_type_id"), summary.get("arrival"), summary.get("departure"))
        detail = detailed_by_key.get(key)
        if detail:
            merged.append({**summary, **detail})
        else:
            merged.append(summary)
    return {
        "ok": True,
        "status": "synced",
        "message": f"{len(merged)} Booking-Zimmeraufenthalte geladen.",
        "reservations": merged,
        "detail_errors": detail_errors,
    }


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
    app.extensions["zab_booking_fetch_future_reservations"] = fetch_future_reservations
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

"""Beds24 V2 portal-only daily prices. No availability or booking mutations."""
import json
import math
import os
import time
import threading
import urllib.error
import urllib.request

BASE = "https://beds24.com/api/v2"
_token_cache = ("", 0.0)
_token_lock = threading.Lock()


def configuration(room):
    key = room.upper()
    room_id = os.environ.get(f"BEDS24_ROOM_ID_{key}", "")
    slot = os.environ.get(f"BEDS24_PORTAL_PRICE_SLOT_{key}", "")
    return {
        "configured": bool(os.environ.get("BEDS24_REFRESH_TOKEN") and room_id.isdigit()
                           and slot.isdigit() and 1 <= int(slot) <= 16),
        "room_id": int(room_id) if room_id.isdigit() else None,
        "slot": int(slot) if slot.isdigit() else None,
    }


def _request(path, headers, payload=None):
    req = urllib.request.Request(BASE + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/json", **headers},
        method="GET" if payload is None else "POST")
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode())


def _token():
    global _token_cache
    with _token_lock:
        if _token_cache[0] and _token_cache[1] > time.monotonic():
            return _token_cache[0]
        data = _request("/authentication/token", {"refreshToken": os.environ["BEDS24_REFRESH_TOKEN"]})
        token = data.get("token")
        if not token:
            raise ValueError("invalid_auth_response")
        _token_cache = (str(token), time.monotonic() + max(0, int(data.get("expiresIn", 0)) - 60))
        return str(token)


def push_rate(room, day, price):
    try:
        price = float(price)
        if not math.isfinite(price) or not 5 <= price <= 149:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "status": "invalid_price", "message": "Ungültiger Portal-Zimmerpreis."}
    cfg = configuration(room)
    if not cfg["configured"]:
        return {"ok": False, "status": "not_configured",
                "message": "Beds24 API-Token, Zimmer-ID oder Portal-Preiszeile fehlt."}
    try:
        payload = [{"roomId": cfg["room_id"], "calendar": [{
            "from": day.isoformat(), "to": day.isoformat(),
            f"price{cfg['slot']}": round(float(price), 2),
        }]}]
        result = _request("/inventory/rooms/calendar", {"token": _token()}, payload)
        # A HTTP 200 can contain a rejected item. Never report that as applied.
        items = result if isinstance(result, list) else result.get("data", [])
        if not isinstance(items, list) or len(items) != 1 or items[0].get("success") is not True:
            return {"ok": False, "status": "rejected", "message": "Beds24 hat die Preisänderung nicht bestätigt."}
        return {"ok": True, "status": "applied", "message": "Preisänderung von Beds24 bestätigt."}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            global _token_cache
            _token_cache = ("", 0.0)
        return {"ok": False, "status": "http_error", "message": f"Beds24 HTTP {exc.code}."}
    except Exception:
        return {"ok": False, "status": "error", "message": "Beds24-Preisübertragung fehlgeschlagen; erneuter Versuch folgt."}

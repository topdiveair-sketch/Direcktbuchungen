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

# Only these fixed descriptions may reach status pages or logs. Never echo an
# API response, exception, URL or credential supplied by the remote service.
ERROR_MESSAGES = {
    "unauthorized": "Beds24 HTTP 401: API-Zugang abgelehnt; Refresh-Token prüfen.",
    "forbidden": "Beds24 HTTP 403: Zugriff verweigert; write:inventory und Zimmerfreigabe prüfen.",
    "rate_limited": "Beds24 HTTP 429: API-Limit erreicht; erneuter Versuch folgt.",
    "server_error": "Beds24 Serverfehler; erneuter Versuch folgt.",
    "http_error": "Beds24 hat die API-Anfrage abgelehnt.",
    "missing_scope": "Beds24: Schreibberechtigung fehlt; write:inventory und Zimmerfreigabe prüfen.",
    "slave_rate": "Beds24: RATE_IS_A_SLAVE_RATE; abgeleitete Preisrate kann nicht direkt geschrieben werden.",
    "room_mapping": "Beds24: Zimmerzuordnung abgelehnt; Zimmer-ID und Freigabe prüfen.",
    "auth_response": "Beds24: Token-Erneuerung lieferte keinen gültigen Zugangstoken.",
    "network_error": "Beds24: Netzwerkfehler oder Zeitüberschreitung; erneuter Versuch folgt.",
    "invalid_response": "Beds24: ungültige API-Antwort; Preisänderung nicht bestätigt.",
    "rejected": "Beds24 hat die Preisänderung nicht bestätigt.",
    "error": "Beds24-Preisübertragung fehlgeschlagen; erneuter Versuch folgt.",
}


def diagnostic_message(result):
    return ERROR_MESSAGES.get(result.get("error_code"), ERROR_MESSAGES["error"])


def _failure(status, code):
    return {"ok": False, "status": status, "error_code": code,
            "message": ERROR_MESSAGES[code]}


def _rejection_code(response):
    # Inspect bounded data for known errors; return a category, never raw text.
    text = json.dumps(response, ensure_ascii=True)[:65536].lower()
    if "rate_is_a_slave_rate" in text:
        return "slave_rate"
    if any(value in text for value in ("scope", "permission", "access denied")):
        return "missing_scope"
    if any(value in text for value in ("room not found", "invalid room", "invalid_room")):
        return "room_mapping"
    return "rejected"


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
        if not isinstance(token, str) or not token.strip():
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
        items = result if isinstance(result, list) else result.get("data", []) if isinstance(result, dict) else []
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict) or items[0].get("success") is not True:
            return _failure("rejected", _rejection_code(result))
        return {"ok": True, "status": "applied", "message": "Preisänderung von Beds24 bestätigt."}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            global _token_cache
            _token_cache = ("", 0.0)
        code = {401: "unauthorized", 403: "forbidden", 429: "rate_limited"}.get(
            exc.code, "server_error" if 500 <= exc.code <= 599 else "http_error")
        return _failure("http_error", code)
    except (urllib.error.URLError, TimeoutError):
        return _failure("error", "network_error")
    except ValueError as exc:
        return _failure("error", "auth_response" if str(exc) == "invalid_auth_response" else "invalid_response")
    except Exception:
        return _failure("error", "error")

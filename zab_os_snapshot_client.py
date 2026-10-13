"""Read-only HTTPS client for Zuhause am Bach OS V113.0.

Never uses the staging database as the source of production occupancy.
"""
import hashlib
import json
import os
import ssl
from datetime import date
import urllib.error
import urllib.parse
import urllib.request

class SnapshotError(RuntimeError):
    pass

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a bearer token to a redirected host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def fetch_snapshot(base_url, token, start, end, timeout=12):
    """Fetch an authenticated snapshot; fail closed on any transport or data error."""
    parsed = urllib.parse.urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or any(ch.isspace() for ch in base_url)
            or not token or any(ch in token for ch in "\r\n")):
        raise SnapshotError("Ungueltige HTTPS-Serveradresse oder Zugangsschluessel")
    query = urllib.parse.urlencode({"start": start, "end": end})
    url = base_url.rstrip("/") + "/internal/os/v1/snapshot?" + query
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Cache-Control": "no-store",
    })
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )
        with opener.open(req, timeout=timeout) as response:
            if response.status != 200:
                raise SnapshotError("HTTP " + str(response.status))
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SnapshotError("HTTP " + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SnapshotError("Verbindung oder Daten ungueltig") from exc
    if not isinstance(payload, dict) or payload.get("room_id") != "Bachblick":
        raise SnapshotError("Unbekanntes Zimmer oder ungueltige Antwort")
    if not isinstance(payload.get("bookings"), list) or not isinstance(payload.get("blocks"), list):
        raise SnapshotError("Unvollstaendige Kalenderdaten")
    if not isinstance(payload.get("sync"), dict) or not isinstance(payload["sync"].get("verified"), bool):
        raise SnapshotError("Synchronisierungsstatus fehlt oder ist ungueltig")
    if not isinstance(payload.get("revision"), str) or len(payload["revision"]) != 64 or any(c not in "0123456789abcdef" for c in payload["revision"]):
        raise SnapshotError("Snapshot-Pruefsumme fehlt oder ist ungueltig")
    signed_fields = {key: value for key, value in payload.items() if key not in ("revision", "generated_at")}
    expected_revision = hashlib.sha256(json.dumps(signed_fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if payload["revision"] != expected_revision:
        raise SnapshotError("Snapshot-Pruefsumme stimmt nicht mit den Kalenderdaten ueberein")
    # The current server deliberately cannot certify OTA sync. Never infer
    # availability from an otherwise valid snapshot.
    if payload["sync"]["verified"] is not False:
        raise SnapshotError("Unzulaessige Synchronisierungsfreigabe")
    if not isinstance(payload["sync"].get("provider_status"), dict):
        raise SnapshotError("Kanalstatus fehlt oder ist ungueltig")
    # Validate the requested range locally as well; never trust a partial response.
    try:
        requested_start = date.fromisoformat(start)
        requested_end = date.fromisoformat(end)
        if requested_start >= requested_end or (requested_end - requested_start).days > 366:
            raise ValueError("range")
    except (TypeError, ValueError):
        raise SnapshotError("Ungueltiger angefragter Kalenderzeitraum") from None
    # Malformed occupancy intervals must never be interpreted as free nights.
    try:
        for booking in payload["bookings"]:
            if not isinstance(booking, dict):
                raise ValueError("booking")
            arrival = date.fromisoformat(booking["arrival"])
            departure = date.fromisoformat(booking["departure"])
            if arrival >= departure or departure <= requested_start or arrival >= requested_end or booking.get("status") not in ("pending", "confirmed"):
                raise ValueError("booking interval/status")
        for block in payload["blocks"]:
            if not isinstance(block, dict):
                raise ValueError("block")
            first = date.fromisoformat(block["start"])
            last = date.fromisoformat(block["end"])
            if first >= last or last <= requested_start or first >= requested_end:
                raise ValueError("block interval")
    except (KeyError, TypeError, ValueError):
        raise SnapshotError("Ungueltige Buchungs- oder Sperrintervalle") from None
    return payload

def get_connection_config():
    """Secrets belong in Windows environment variables, never in code or logs."""
    return os.environ.get("ZAB_OS_SNAPSHOT_URL", ""), os.environ.get("ZAB_BRIDGE_TOKEN", "")

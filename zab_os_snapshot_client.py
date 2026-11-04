"""Read-only HTTPS client for Zuhause am Bach OS V113.0.

Never uses the staging database as the source of production occupancy.
"""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

class SnapshotError(RuntimeError):
    pass

def fetch_snapshot(base_url, token, start, end, timeout=12):
    """Fetch an authenticated snapshot; fail closed on any transport or data error."""
    if not base_url.startswith("https://") or not token:
        raise SnapshotError("HTTPS-Adresse oder Zugangsschluessel fehlt")
    query = urllib.parse.urlencode({"start": start, "end": end})
    url = base_url.rstrip("/") + "/internal/os/v1/snapshot?" + query
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Cache-Control": "no-store",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as response:
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
    return payload

def get_connection_config():
    """Secrets belong in Windows environment variables, never in code or logs."""
    return os.environ.get("ZAB_OS_SNAPSHOT_URL", ""), os.environ.get("ZAB_BRIDGE_TOKEN", "")

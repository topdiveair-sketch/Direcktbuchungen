"""Export a verified-integrity ZAB snapshot to JSON without changing bookings."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from zab_os_snapshot_client import SnapshotError, fetch_snapshot, get_connection_config


def export_snapshot(destination, start, end, *, base_url=None, token=None):
    if base_url is None or token is None:
        configured_url, configured_token = get_connection_config()
        base_url = configured_url if base_url is None else base_url
        token = configured_token if token is None else token
    if not base_url or not token:
        raise SnapshotError("ZAB_OS_SNAPSHOT_URL und ZAB_BRIDGE_TOKEN fehlen")
    payload = fetch_snapshot(base_url, token, start, end)
    payload["source_id"] = "zab-os-snapshot"
    destination = Path(destination)
    # Never overwrite an existing export: preserve evidence for later comparison.
    with destination.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description="ZAB OS Snapshot exportieren (nur lesen)")
    parser.add_argument("destination", help="Neue JSON-Datei, darf noch nicht existieren")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args(argv)
    try:
        destination = export_snapshot(args.destination, args.start, args.end)
    except (SnapshotError, OSError, ValueError) as exc:
        parser.exit(2, "Export fehlgeschlagen: " + str(exc) + "\n")
    print("Snapshot gespeichert: " + str(destination))
    print("ACHTUNG: Synchronisierung nicht verifiziert; keine Naechte freigeben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

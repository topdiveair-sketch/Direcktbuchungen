"""Offline, read-only ZAB calendar comparison. Never contacts booking providers."""
import argparse
import json
from pathlib import Path
from zab_os_snapshot_client import SnapshotError, compare_occupancy_snapshots


def compare_files(first_path, second_path, start, end):
    first = Path(first_path).resolve()
    second = Path(second_path).resolve()
    if first == second:
        raise SnapshotError("Zwei verschiedene Exportdateien erforderlich")
    with first.open(encoding="utf-8") as handle:
        a = json.load(handle)
    with second.open(encoding="utf-8") as handle:
        b = json.load(handle)
    for snapshot in (a, b):
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("bookings"), list) or not isinstance(snapshot.get("blocks"), list):
            raise SnapshotError("Ungueltiger Kalenderexport")
    return compare_occupancy_snapshots(a, b, start, end)


def main(argv=None):
    parser = argparse.ArgumentParser(description="ZAB OS Kalendervergleich (nur lesen; keine Freigaben)")
    parser.add_argument("first", help="Erster JSON-Kalenderexport")
    parser.add_argument("second", help="Zweiter, unabhaengiger JSON-Kalenderexport")
    parser.add_argument("--start", required=True, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Enddatum exklusiv YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        result = compare_files(args.first, args.second, args.start, args.end)
    except (SnapshotError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, "Kalendervergleich fehlgeschlagen: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

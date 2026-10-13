"""Conservative, offline iCalendar import for all-day booking blocks.

Reject unsupported date-time events rather than guessing occupancy.
"""
import argparse
import json
from datetime import date
from pathlib import Path
from zab_os_snapshot_client import SnapshotError


def convert_ics(source, destination, source_id):
    if not source_id or not source_id.strip() or source_id.strip().casefold() == "zab-os-snapshot":
        raise SnapshotError("Eindeutige externe Quellenkennung erforderlich")
    text = Path(source).read_text(encoding="utf-8-sig")
    if len(text) > 5_000_000:
        raise SnapshotError("Kalenderdatei zu gross")
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")):
            if not lines:
                raise SnapshotError("Ungueltige iCalendar-Fortsetzungszeile")
            lines[-1] += line[1:]
        else:
            lines.append(line)
    if "BEGIN:VCALENDAR" not in lines or "END:VCALENDAR" not in lines:
        raise SnapshotError("Kein vollstaendiger iCalendar")
    events = []
    current = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            if current is not None:
                raise SnapshotError("Verschachtelte Ereignisse")
            current = {}
        elif line == "END:VEVENT":
            if current is None:
                raise SnapshotError("Ereignisende ohne Beginn")
            if current.get("STATUS") != "CANCELLED":
                if "RRULE" in current or "RECURRENCE-ID" in current or "RDATE" in current or "EXDATE" in current:
                    raise SnapshotError("Wiederkehrende Ereignisse werden nicht unterstuetzt")
                if "DTSTART" not in current or "DTEND" not in current:
                    raise SnapshotError("Ereignis ohne Beginn oder Ende")
                try:
                    start = date.fromisoformat(current["DTSTART"])
                    end = date.fromisoformat(current["DTEND"])
                except ValueError as exc:
                    raise SnapshotError("Ungueltiges Tagesdatum") from exc
                if start >= end:
                    raise SnapshotError("Ungueltiger Ereigniszeitraum")
                events.append({"start": start.isoformat(), "end": end.isoformat(), "source": source_id.strip()})
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            prop = key.split(";", 1)[0].upper()
            if prop in ("DTSTART", "DTEND"):
                if key.upper() != prop + ";VALUE=DATE" and key.upper() != prop:
                    raise SnapshotError("Nur ganztagige iCalendar-Ereignisse erlaubt")
                if len(value) != 8 or not value.isdigit():
                    raise SnapshotError("Zeitangaben nicht unterstuetzt; nur YYYYMMDD")
                value = value[:4] + "-" + value[4:6] + "-" + value[6:]
            if prop in ("DTSTART", "DTEND", "STATUS", "RRULE", "RECURRENCE-ID", "RDATE", "EXDATE"):
                if prop in current:
                    raise SnapshotError("Doppelte Ereigniseigenschaft")
                current[prop] = value
    if current is not None:
        raise SnapshotError("Unvollstaendiges Ereignis")
    if not events:
        raise SnapshotError("Keine aktiven ganztagigen Ereignisse; leerer Export nicht beweiskraeftig")
    payload = {"source_id": source_id.strip(), "bookings": [], "blocks": events, "sync": {"verified": False}}
    with Path(destination).open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return len(events)


def main(argv=None):
    parser = argparse.ArgumentParser(description="iCalendar in konservativen ZAB-Kalenderexport umwandeln")
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--source-id", required=True, help="z.B. airbnb-export")
    args = parser.parse_args(argv)
    try:
        count = convert_ics(args.source, args.destination, args.source_id)
    except (SnapshotError, ValueError, OSError) as exc:
        parser.exit(2, "Import fehlgeschlagen: " + str(exc) + "\n")
    print(str(count) + " Kalenderereignisse exportiert. Sync NICHT verifiziert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

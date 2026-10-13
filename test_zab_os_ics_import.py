import tempfile
import unittest
from pathlib import Path
from zab_os_ics_import import convert_ics
from zab_os_snapshot_client import SnapshotError
from zab_os_compare_exports import compare_files
import json


class IcsImportTests(unittest.TestCase):
    def test_all_day_import_and_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "airbnb.ics"
            dst = Path(directory) / "airbnb.json"
            other = Path(directory) / "zab.json"
            src.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261015\nDTEND;VALUE=DATE:20261017\nEND:VEVENT\nEND:VCALENDAR\n")
            self.assertEqual(convert_ics(src, dst, "airbnb-export"), 1)
            other.write_text(json.dumps({"source_id":"zab-os-snapshot","bookings":[],"blocks":[]}))
            result = compare_files(other, dst, "2026-10-14", "2026-10-19")
            self.assertEqual(result["only_in_second"], ["2026-10-15", "2026-10-16"])
            self.assertFalse(result["safe_to_release_nights"])

    def test_reject_timed_event(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "source.ics"
            dst = Path(directory) / "target.json"
            src.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261015T120000Z\nDTEND:20261016T120000Z\nEND:VEVENT\nEND:VCALENDAR\n")
            with self.assertRaises(SnapshotError):
                convert_ics(src, dst, "booking-export")
            self.assertFalse(dst.exists())

    def test_reject_recurring(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "source.ics"
            src.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261015\nDTEND;VALUE=DATE:20261016\nRRULE:FREQ=DAILY\nEND:VEVENT\nEND:VCALENDAR\n")
            with self.assertRaises(SnapshotError):
                convert_ics(src, Path(directory)/"target.json", "booking-export")

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "source.ics"
            dst = Path(directory) / "target.json"
            src.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261015\nDTEND;VALUE=DATE:20261016\nEND:VEVENT\nEND:VCALENDAR\n")
            dst.write_text("unchanged")
            with self.assertRaises(FileExistsError):
                convert_ics(src, dst, "booking-export")
            self.assertEqual(dst.read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()

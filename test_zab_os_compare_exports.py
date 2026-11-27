"""Tests for the offline read-only ZAB calendar comparison CLI."""
import json
import tempfile
import unittest
from pathlib import Path
from zab_os_compare_exports import compare_files
from zab_os_snapshot_client import SnapshotError


class OfflineCompareTests(unittest.TestCase):
    def test_independent_files_report_differences(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.json", Path(directory) / "second.json"
            first.write_text(json.dumps({"source_id":"zab-os","bookings":[{"arrival":"2026-10-15","departure":"2026-10-17"}],"blocks":[]}), encoding="utf-8")
            second.write_text(json.dumps({"source_id":"direct-booking","bookings":[],"blocks":[{"start":"2026-10-16","end":"2026-10-18"}]}), encoding="utf-8")
            report = compare_files(first, second, "2026-10-14", "2026-10-19")
            self.assertEqual(report["only_in_first"], ["2026-10-15"])
            self.assertEqual(report["only_in_second"], ["2026-10-17"])
            self.assertFalse(report["safe_to_release_nights"])

    def test_same_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            path.write_text('{"source_id":"zab-os","bookings":[],"blocks":[]}', encoding="utf-8")
            with self.assertRaisesRegex(SnapshotError, "verschiedene"):
                compare_files(path, path, "2026-10-14", "2026-10-19")

    def test_same_source_id_rejected_even_for_distinct_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.json", Path(directory) / "second.json"
            payload = '{"source_id":"zab-os","bookings":[],"blocks":[]}'
            first.write_text(payload, encoding="utf-8")
            second.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(SnapshotError, "Kalenderquellen"):
                compare_files(first, second, "2026-10-14", "2026-10-19")

    def test_invalid_export_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.json", Path(directory) / "second.json"
            first.write_text('{"bookings":[]}', encoding="utf-8")
            second.write_text('{"bookings":[],"blocks":[]}', encoding="utf-8")
            with self.assertRaisesRegex(SnapshotError, "Kalenderexport"):
                compare_files(first, second, "2026-10-14", "2026-10-19")


if __name__ == "__main__":
    unittest.main()

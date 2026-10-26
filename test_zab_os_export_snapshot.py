"""Offline unit tests for ZAB snapshot export."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zab_os_export_snapshot import export_snapshot


class SnapshotExportTests(unittest.TestCase):
    @patch("zab_os_export_snapshot.fetch_snapshot")
    def test_export_adds_source_and_preserves_payload(self, fetch):
        fetch.return_value = {"room_id":"Bachblick","bookings":[],"blocks":[],"revision":"a"*64}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export.json"
            export_snapshot(destination, "2026-10-01", "2026-11-01", base_url="https://example.org", token="secret")
            saved = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(saved["source_id"], "zab-os-snapshot")
            self.assertEqual(saved["revision"], "a"*64)
            fetch.assert_called_once_with("https://example.org", "secret", "2026-10-01", "2026-11-01")

    @patch("zab_os_export_snapshot.fetch_snapshot")
    def test_export_never_overwrites_existing_file(self, fetch):
        fetch.return_value = {"bookings":[],"blocks":[]}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export.json"
            destination.write_text("original", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_snapshot(destination, "2026-10-01", "2026-11-01", base_url="https://example.org", token="secret")
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")

    @patch("zab_os_export_snapshot.fetch_snapshot")
    def test_missing_token_rejected_without_network(self, fetch):
        with self.assertRaisesRegex(Exception, "fehlen"):
            export_snapshot("ignored.json", "2026-10-01", "2026-11-01", base_url="https://example.org", token="")
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

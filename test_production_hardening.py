from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from production_hardening import init_production_hardening


class _FakeLegacy:
    def __init__(self, path: Path):
        self.DB_PATH = path

        def original_db():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        self.db = original_db


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ProductionHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "zab.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE external_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    uid TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    imported_at TEXT NOT NULL
                );
                CREATE TABLE ical_settings (
                    room TEXT PRIMARY KEY,
                    import_url TEXT DEFAULT '',
                    last_sync TEXT DEFAULT '',
                    last_result TEXT DEFAULT ''
                );
                INSERT INTO ical_settings(room, import_url) VALUES('Bachblick', '');
                CREATE TABLE proof(value TEXT NOT NULL);
                INSERT INTO proof(value) VALUES('preserve-me');
                """
            )
        self.app = Flask(__name__)
        self.legacy = _FakeLegacy(self.db_path)
        self.payload = {
            "updatedAtIso": "2026-09-14T19:00:00Z",
            "events": [
                {
                    "start": "2027-05-01",
                    "end": "2027-05-02",
                    "source": "Booking iCal Sicherheitsabgleich",
                },
                {
                    "start": "2027-06-01",
                    "end": "2027-06-02",
                    "source": "ZAB OS Master",
                },
            ],
        }

    def tearDown(self):
        self.tmp.cleanup()

    @patch("production_hardening.urllib.request.urlopen")
    def test_hardening_mirrors_only_booking_and_creates_private_backup(self, urlopen):
        urlopen.return_value = _Response(self.payload)
        with patch.dict(os.environ, {"REQUIRE_PERSISTENT_STORAGE": "0"}, clear=False):
            init_production_hardening(self.app, self.legacy, lambda: True)

        with self.legacy.db() as conn:
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            rows = conn.execute(
                "SELECT start_date,end_date,source,uid FROM external_blocks ORDER BY start_date"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start_date"], "2027-05-01")
        self.assertEqual(rows[0]["source"], "booking_ical")
        self.assertTrue(rows[0]["uid"].startswith("booking-safety-"))

        client = self.app.test_client()
        health = client.get("/health/zab-storage")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json["sqlite_integrity"], "ok")
        self.assertFalse(health.json["persistent_storage"])

        backup = client.get("/api/central/system/db-backup")
        self.assertEqual(backup.status_code, 200)
        self.assertEqual(backup.headers["X-ZAB-SQLite-Integrity"], "ok")
        self.assertEqual(len(backup.headers["X-ZAB-SHA256"]), 64)
        self.assertTrue(backup.data.startswith(b"SQLite format 3"))

        backup_path = Path(self.tmp.name) / "downloaded.db"
        backup_path.write_bytes(backup.data)
        with sqlite3.connect(backup_path) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT value FROM proof").fetchone()[0], "preserve-me")

    @patch("production_hardening.urllib.request.urlopen")
    def test_real_ical_configuration_prevents_public_snapshot_mirror(self, urlopen):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE ical_settings SET import_url='https://example.invalid/booking.ics' WHERE room='Bachblick'"
            )
        init_production_hardening(self.app, self.legacy, lambda: True)
        urlopen.assert_not_called()
        with self.legacy.db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM external_blocks").fetchone()[0]
        self.assertEqual(count, 0)

    @patch("production_hardening.urllib.request.urlopen")
    def test_persistent_storage_requirement_fails_closed_without_volume(self, urlopen):
        urlopen.return_value = _Response(self.payload)
        with patch.dict(
            os.environ,
            {"REQUIRE_PERSISTENT_STORAGE": "1", "RAILWAY_VOLUME_MOUNT_PATH": ""},
            clear=False,
        ):
            init_production_hardening(self.app, self.legacy, lambda: True)
            response = self.app.test_client().get("/health/zab-storage")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["persistent_storage"])
        self.assertTrue(response.json["persistent_storage_required"])


if __name__ == "__main__":
    unittest.main()

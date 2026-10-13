"""Real Flask test-client checks for the isolated OS snapshot route."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask
from zab_os_snapshot_server import init_os_snapshot


class SnapshotFlaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "test.db")
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE bookings(uid TEXT,room TEXT,arrival TEXT,departure TEXT,status TEXT,first_name TEXT,email TEXT);
                CREATE TABLE external_blocks(room TEXT,start_date TEXT,end_date TEXT,source TEXT);
                CREATE TABLE ical_settings(room TEXT,last_sync TEXT,last_result TEXT);
                CREATE TABLE central_overrides(room TEXT,day TEXT,availability INTEGER,price REAL);
                INSERT INTO bookings VALUES('PRIVATE_UID','Bachblick','2026-10-15','2026-10-17','confirmed','PRIVATE_NAME','PRIVATE_EMAIL');
                INSERT INTO bookings VALUES('other','Weinbergzimmer','2026-10-15','2026-10-17','confirmed','OTHER','OTHER');
                INSERT INTO external_blocks VALUES('Bachblick','2026-10-20','2026-10-21','Airbnb');
                INSERT INTO ical_settings VALUES('Bachblick','2026-10-13','OK');
                INSERT INTO central_overrides VALUES('Bachblick','2026-10-22',0,NULL);
                INSERT INTO central_overrides VALUES('Bachblick','2026-10-23',1,125);
                INSERT INTO central_overrides VALUES('Bachblick','2026-10-24',NULL,130);
                INSERT INTO central_overrides VALUES('Weinbergzimmer','2026-10-25',0,NULL);
            """)
        @contextmanager
        def db():
            conn = sqlite3.connect(self.path)
            try:
                yield conn
            finally:
                conn.close()
        app = Flask(__name__)
        app.testing = True
        init_os_snapshot(app, db)
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {"ZAB_BRIDGE_TOKEN": "integration-secret"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def get(self, token="integration-secret", start="2026-10-13", end="2026-11-13"):
        return self.client.get("/internal/os/v1/snapshot", query_string={"start":start,"end":end},
                               headers={"Authorization": "Bearer " + token})

    def test_success_and_privacy(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["room_name"], "Gartenzimmer")
        self.assertEqual(len(payload["bookings"]), 1)
        self.assertEqual(len(payload["blocks"]), 2)
        self.assertIn({"start":"2026-10-22","end":"2026-10-23","source":"Zentrale Sperre"}, payload["blocks"])
        self.assertFalse(any(b["start"] in ("2026-10-23","2026-10-24","2026-10-25") for b in payload["blocks"]))
        self.assertFalse(payload["sync"]["verified"])
        self.assertNotIn("PRIVATE_", response.get_data(as_text=True))
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_central_override_range(self):
        payload = self.get(start='2026-10-23',end='2026-10-25').get_json()
        self.assertEqual(payload['blocks'], [])

    def test_bad_token(self):
        self.assertEqual(self.get(token="wrong").status_code, 401)

    def test_missing_server_token(self):
        os.environ.pop("ZAB_BRIDGE_TOKEN", None)
        self.assertEqual(self.get().status_code, 401)

    def test_invalid_dates(self):
        self.assertEqual(self.get(start="bad").status_code, 400)
        self.assertEqual(self.get(start="2026-10-13",end="2026-10-13").status_code, 400)
        self.assertEqual(self.get(end="2028-10-13").status_code, 400)

    def test_database_failure(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE bookings")
        self.assertEqual(self.get().status_code, 503)

if __name__ == "__main__":
    unittest.main()

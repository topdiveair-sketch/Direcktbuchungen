"""Regression tests for privacy-safe Stripe checkout abandonment alerts."""
import hashlib
import hmac
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from payment_hold import init_payment_hold
from stripe_checkout import init_stripe_checkout


class StripeCancelRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "bookings.db")
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE bookings (
                    id INTEGER PRIMARY KEY, uid TEXT UNIQUE, room TEXT, arrival TEXT, departure TEXT,
                    adults INTEGER DEFAULT 2, breakfast INTEGER DEFAULT 0,
                    first_name TEXT DEFAULT '', last_name TEXT DEFAULT '', email TEXT DEFAULT '',
                    phone TEXT DEFAULT '', message TEXT DEFAULT '', payment_method TEXT, total REAL,
                    status TEXT, created_at TEXT, paid INTEGER DEFAULT 0,
                    stripe_session_id TEXT DEFAULT '', hold_expires_at TEXT DEFAULT ''
                );
                CREATE TABLE external_blocks(room TEXT, start_date TEXT, end_date TEXT);
                CREATE TABLE central_overrides(room TEXT, day TEXT, availability INTEGER);
                CREATE TABLE ical_settings(room TEXT PRIMARY KEY, import_url TEXT, last_sync TEXT);
            """)
        self.app = Flask(__name__)
        init_stripe_checkout(
            self.app, self.db, {"Bachblick": {}}, lambda value: value,
            lambda *args: {"total": 100.0}, lambda *args: (True, ""),
            lambda room: (0, "Synchronisierung erfolgreich."),
        )
        self.alerts = []
        self.app.extensions["zab_send_priority_alert"] = lambda *args: self.alerts.append(args)
        self.client = self.app.test_client()
        self.token = "unpredictable-cancel-token"
        self.token_hash = hashlib.sha256(self.token.encode()).hexdigest()
        with self.db() as conn:
            conn.execute(
                """INSERT INTO bookings
                   (id,uid,room,arrival,departure,adults,breakfast,first_name,last_name,
                    email,phone,message,payment_method,total,status,created_at,paid,
                    hold_expires_at,stripe_cancel_token_hash)
                   VALUES(1,'ZAB-test','Bachblick','2026-12-10','2026-12-12',2,0,
                          'Test','Gast','test@example.test','+430000000','',
                          'stripe_checkout',200,'pending',?,0,?,?)""",
                (datetime.now().isoformat(timespec="seconds"),
                 (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds"),
                 self.token_hash),
            )

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_cancel_requires_unpredictable_token_and_sends_owner_alert(self):
        self.client.get("/stripe/cancel?booking=1&token=wrong")
        with self.db() as conn:
            row = conn.execute("SELECT status FROM bookings WHERE id=1").fetchone()
        self.assertEqual(row["status"], "pending")
        self.assertEqual(self.alerts, [])

        response = self.client.get(f"/stripe/cancel?booking=1&token={self.token}")
        self.assertEqual(response.status_code, 302)
        with self.db() as conn:
            row = conn.execute("SELECT status,release_reason,hold_expires_at FROM bookings WHERE id=1").fetchone()
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["release_reason"], "Kartenzahlung abgebrochen")
        self.assertEqual(row["hold_expires_at"], "")
        self.assertEqual(self.alerts, [(1, "abandoned")])


class ExpiredCheckoutNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "bookings.db")
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE bookings (
                    id INTEGER PRIMARY KEY, uid TEXT, room TEXT, arrival TEXT, departure TEXT,
                    adults INTEGER, breakfast INTEGER, first_name TEXT, last_name TEXT, email TEXT,
                    phone TEXT, message TEXT, payment_method TEXT, total REAL, status TEXT,
                    paid INTEGER DEFAULT 0, hold_expires_at TEXT, released_at TEXT DEFAULT '',
                    release_reason TEXT DEFAULT '', checkout_ip_hash TEXT DEFAULT ''
                );
                CREATE TABLE site_settings(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE email_log(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER, recipient TEXT,
                    subject TEXT, status TEXT, created_at TEXT
                );
                INSERT INTO site_settings VALUES('inquiry_email','owner@example.test');
                INSERT INTO bookings VALUES(
                    1,'ZAB-test','Bachblick','2026-12-10','2026-12-12',2,0,
                    'Test','Gast','test@example.test','+430000000','',
                    'stripe_checkout',200,'pending',0,'2000-01-01','','','ZAB-hash');
            """)
        self.app = Flask(__name__)
        init_payment_hold(self.app, self.db)
        self.client = self.app.test_client()

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_expired_stripe_hold_emails_details_without_raw_ip(self):
        sent = []
        def fake_send(to, subject, body, **kwargs):
            sent.append((to, subject, body))
            return True, "gesendet"

        with patch("payment_hold.send_transactional_email", side_effect=fake_send):
            self.client.get("/test")
        self.assertEqual(len(sent), 1)
        to, subject, body = sent[0]
        self.assertEqual(to, "Zuhause.am.Bach@outlook.com")
        self.assertIn("Karten-Checkout abgebrochen", subject)
        self.assertIn("2026-12-10", body)
        self.assertIn("IP-Kennzeichen (pseudonymisiert", body)
        self.assertNotIn("198.51.100", body)
        with self.db() as conn:
            row = conn.execute("SELECT status FROM bookings WHERE id=1").fetchone()
        self.assertEqual(row["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()

"""Offline tests of signed Stripe live webhook and reservation settlement."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from stripe_checkout import init_stripe_checkout


class StripeLiveWebhookTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "ZAB_STRIPE_LIVE_ENABLED": "1",
            "STRIPE_SECRET_KEY": "rk_live_offline_test_only",
            "STRIPE_WEBHOOK_SECRET": "whsec_offline_test_only",
        })
        self.env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "bookings.db")
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE bookings (
                    id INTEGER PRIMARY KEY, room TEXT, arrival TEXT, departure TEXT,
                    total REAL, payment_method TEXT, status TEXT, paid INTEGER DEFAULT 0,
                    stripe_session_id TEXT, stripe_payment_intent_id TEXT,
                    hold_expires_at TEXT
                );
                CREATE TABLE external_blocks (
                    room TEXT, start_date TEXT, end_date TEXT
                );
                CREATE TABLE central_overrides (
                    room TEXT, day TEXT, availability INTEGER
                );
            """)
        self.app = Flask(__name__)
        init_stripe_checkout(
            self.app, self.db, {"Bachblick": {}}, lambda s: s,
            lambda *args: {}, lambda *args: (True, ""), lambda room: (0, "Synchronisierung erfolgreich."),
        )
        self.client = self.app.test_client()
        self.insert_booking()

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
        self.env.stop()

    def insert_booking(self, expires=None):
        expiry = expires or (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
        with self.db() as conn:
            conn.execute("""INSERT INTO bookings
                (id,room,arrival,departure,total,payment_method,status,paid,stripe_session_id,hold_expires_at)
                VALUES (1,'Bachblick','2026-11-10','2026-11-11',119.0,'stripe_checkout',
                        'pending',0,'cs_live_test_session',?)""", (expiry,))

    def session(self):
        return {
            "id": "cs_live_test_session", "object": "checkout.session",
            "livemode": True, "payment_status": "paid", "currency": "eur",
            "amount_total": 11900, "payment_intent": "pi_test_payment",
            "metadata": {"booking_id": "1"},
        }

    def send_event(self, session=None, tamper=False):
        event = {
            "id": "evt_offline_test", "livemode": True,
            "type": "checkout.session.completed",
            "data": {"object": session or self.session()},
        }
        raw = json.dumps(event, separators=(",", ":")).encode()
        ts = str(int(time.time()))
        signature = hmac.new(
            b"whsec_offline_test_only", ts.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        if tamper:
            signature = "0" * 64
        return self.client.post(
            "/stripe/webhook", data=raw, content_type="application/json",
            headers={"Stripe-Signature": "t=" + ts + ",v1=" + signature},
        )

    def booking(self):
        with self.db() as conn:
            return dict(conn.execute("SELECT * FROM bookings WHERE id=1").fetchone())

    def test_paid_webhook_confirms_once(self):
        self.assertEqual(self.send_event().status_code, 200)
        self.assertEqual(self.booking()["status"], "confirmed")
        self.assertEqual(self.booking()["paid"], 1)
        self.assertEqual(self.send_event().status_code, 200)
        self.assertEqual(self.booking()["stripe_payment_intent_id"], "pi_test_payment")

    def test_bad_signature_rejected(self):
        self.assertEqual(self.send_event(tamper=True).status_code, 400)
        self.assertEqual(self.booking()["paid"], 0)

    def test_expired_hold_rejected(self):
        with self.db() as conn:
            conn.execute("UPDATE bookings SET hold_expires_at=? WHERE id=1", (
                (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds"),))
        self.assertEqual(self.send_event().status_code, 503)
        self.assertEqual(self.booking()["paid"], 0)

    def test_conflicting_direct_booking_rejected(self):
        with self.db() as conn:
            conn.execute("""INSERT INTO bookings
                (id,room,arrival,departure,total,payment_method,status,paid)
                VALUES (2,'Bachblick','2026-11-10','2026-11-11',119,'paypal','confirmed',1)""")
        self.assertEqual(self.send_event().status_code, 503)
        self.assertEqual(self.booking()["paid"], 0)

    def test_external_block_rejected(self):
        with self.db() as conn:
            conn.execute("INSERT INTO external_blocks VALUES ('Bachblick','2026-11-10','2026-11-11')")
        self.assertEqual(self.send_event().status_code, 503)
        self.assertEqual(self.booking()["paid"], 0)

    def test_central_closure_rejected(self):
        with self.db() as conn:
            conn.execute("INSERT INTO central_overrides VALUES ('Bachblick','2026-11-10',0)")
        self.assertEqual(self.send_event().status_code, 503)
        self.assertEqual(self.booking()["paid"], 0)

    def test_wrong_amount_rejected(self):
        session = self.session()
        session["amount_total"] = 12000
        self.assertEqual(self.send_event(session).status_code, 503)
        self.assertEqual(self.booking()["paid"], 0)

    def test_return_and_cancel_cannot_settle_or_release_hold(self):
        self.client.get("/stripe/success?booking=1&session_id=cs_live_test_session")
        self.client.get("/stripe/cancel?booking=1")
        self.assertEqual(self.booking()["status"], "pending")
        self.assertEqual(self.booking()["paid"], 0)


if __name__ == "__main__":
    unittest.main()

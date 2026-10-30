"""Offline PayPal return/cancel regression tests; no provider calls or emails."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from paypal_checkout import init_paypal_checkout


class PayPalSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "bookings.db"
        self.env = patch.dict(os.environ, {
            "PAYPAL_CLIENT_ID": "offline-test", "PAYPAL_CLIENT_SECRET": "offline-test",
            "PAYPAL_ENV": "sandbox",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.arrival = (date.today() + timedelta(days=10)).isoformat()
        self.departure = (date.today() + timedelta(days=11)).isoformat()
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE bookings (
                    id INTEGER PRIMARY KEY, room TEXT, arrival TEXT, departure TEXT,
                    first_name TEXT DEFAULT 'Test', total REAL, payment_method TEXT,
                    status TEXT, paid INTEGER DEFAULT 0, hold_expires_at TEXT
                );
                CREATE TABLE external_blocks(room,start_date,end_date);
                CREATE TABLE central_overrides(room,day,availability);
            """)
        self.app = Flask(__name__)
        init_paypal_checkout(self.app, self.db, {"Bachblick": {}}, date.fromisoformat,
                             lambda *args: {"total": 119}, lambda *args: (True, ""),
                             lambda room: (0, "Synchronisierung erfolgreich."))
        with self.db() as conn:
            conn.execute("""INSERT INTO bookings
                (id,room,arrival,departure,total,payment_method,status,paid,hold_expires_at,paypal_order_id)
                VALUES(1,'Bachblick',?,?,119,'paypal_checkout','pending',0,?,'ORDER-1')""",
                (self.arrival, self.departure,
                 (datetime.now() + timedelta(minutes=10)).isoformat(timespec="seconds")))
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

    def booking(self):
        with self.db() as conn:
            return dict(conn.execute("SELECT * FROM bookings WHERE id=1").fetchone())

    def return_from_provider(self, during_capture=None, amount="119.00", currency="EUR"):
        def request(req, **kwargs):
            if req.full_url.endswith("/v1/oauth2/token"):
                payload = {"access_token": "offline-token"}
            else:
                self.assertTrue(req.full_url.endswith("/ORDER-1/capture"))
                if during_capture:
                    during_capture()
                payload = {"id": "ORDER-1", "status": "COMPLETED", "purchase_units": [{
                    "payments": {"captures": [{"id": "CAPTURE-1", "status": "COMPLETED",
                        "amount": {"value": amount, "currency_code": currency}}]}}]}
            from io import BytesIO
            return BytesIO(json.dumps(payload).encode())
        with patch("urllib.request.urlopen", side_effect=request):
            return self.client.get("/paypal/return?booking=1&token=ORDER-1")

    def test_browser_cancel_does_not_release_or_rewrite_a_reservation(self):
        before = self.booking()
        result = self.client.get("/paypal/cancel?booking=1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.booking(), before)
        self.assertNotIn("wieder freigegeben", result.get_data(as_text=True))

    def test_verified_payment_confirms_once_and_repeated_return_is_read_only(self):
        self.assertEqual(self.return_from_provider().status_code, 200)
        self.assertEqual(self.booking()["status"], "confirmed")
        self.assertEqual(self.booking()["paid"], 1)
        before = self.booking()
        with patch("urllib.request.urlopen", side_effect=AssertionError("No repeated capture")):
            result = self.client.get("/paypal/return?booking=1&token=ORDER-1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.booking(), before)

    def test_manual_cancellation_during_capture_cannot_be_reconfirmed(self):
        def cancel():
            with self.db() as conn:
                conn.execute("UPDATE bookings SET status='cancelled',release_reason='manual' WHERE id=1")
        self.assertNotEqual(self.return_from_provider(cancel).status_code, 200)
        self.assertEqual(self.booking()["status"], "cancelled")
        self.assertTrue(self.booking()["payment_error"])

    def test_competing_booking_during_capture_cannot_double_book(self):
        def competing():
            with self.db() as conn:
                conn.execute("""INSERT INTO bookings(id,room,arrival,departure,total,status,paid)
                    VALUES(2,'Bachblick',?,?,119,'confirmed',1)""", (self.arrival, self.departure))
        self.assertNotEqual(self.return_from_provider(competing).status_code, 200)
        self.assertNotEqual(self.booking()["status"], "confirmed")
        with self.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'").fetchone()[0], 1)

    def test_external_block_during_capture_prevents_confirmation(self):
        def block():
            with self.db() as conn:
                conn.execute("INSERT INTO external_blocks VALUES('Bachblick',?,?)",
                             (self.arrival, self.departure))
        self.assertNotEqual(self.return_from_provider(block).status_code, 200)
        self.assertNotEqual(self.booking()["status"], "confirmed")

    def test_room_closure_during_capture_prevents_confirmation(self):
        def close():
            with self.db() as conn:
                conn.execute("INSERT INTO central_overrides VALUES('Bachblick',?,0)", (self.arrival,))
        self.assertNotEqual(self.return_from_provider(close).status_code, 200)
        self.assertNotEqual(self.booking()["status"], "confirmed")

    def test_wrong_amount_or_currency_never_confirms(self):
        for amount, currency in [("1.00", "EUR"), ("119.00", "USD")]:
            with self.subTest(amount=amount, currency=currency):
                self.assertNotEqual(self.return_from_provider(amount=amount, currency=currency).status_code, 200)
                self.assertEqual(self.booking()["paid"], 0)

    def test_wrong_order_never_contacts_paypal_or_changes_booking(self):
        before = self.booking()
        with patch("urllib.request.urlopen", side_effect=AssertionError("No provider calls")):
            result = self.client.get("/paypal/return?booking=1&token=OTHER-ORDER")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.booking(), before)

    def test_invalid_email_is_rejected_before_calendar_or_payment_calls(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("No provider calls")):
            result = self.client.post("/api/paypal/create-order", json={
                "room": "Bachblick", "arrival": self.arrival, "departure": self.departure,
                "first_name": "Test", "last_name": "Guest", "phone": "test", "email": "invalid",
            })
        self.assertEqual(result.status_code, 400)
        self.assertIn("E-Mail", result.get_json()["message"])


if __name__ == "__main__":
    unittest.main()

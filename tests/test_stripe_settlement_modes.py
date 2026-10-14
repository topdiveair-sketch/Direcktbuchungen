"""SQLite regression tests for Stripe mode isolation and repeat settlement."""
import sqlite3
import unittest

from stripe_booking_settlement import settle_verified_stripe_session


def make_db(live):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, total REAL, payment_method TEXT,
        status TEXT, paid INTEGER, stripe_session_id TEXT,
        stripe_payment_intent TEXT DEFAULT '', paid_at TEXT DEFAULT '',
        hold_expires_at TEXT DEFAULT '', payment_error TEXT DEFAULT '',
        released_at TEXT DEFAULT '', release_reason TEXT DEFAULT ''
    )""")
    sid = ("cs_live_" if live else "cs_test_") + "test"
    conn.execute(
        "INSERT INTO bookings(id,total,payment_method,status,paid,stripe_session_id) "
        "VALUES(42,149,'stripe_checkout','pending',0,?)", (sid,)
    )
    return conn, sid


def paid_session(live, sid):
    return {
        "id": sid, "livemode": live, "object": "checkout.session",
        "mode": "payment", "status": "complete", "payment_status": "paid",
        "currency": "eur", "amount_total": 14900,
        "client_reference_id": "42", "metadata": {"booking_id": "42"},
        "payment_intent": "pi_test_example",
    }


class StripeSettlementModeTests(unittest.TestCase):
    def test_test_payment_confirmed_once(self):
        conn, sid = make_db(False)
        session = paid_session(False, sid)
        self.assertEqual(settle_verified_stripe_session(conn, session), "confirmed")
        self.assertEqual(settle_verified_stripe_session(conn, session), "duplicate")
        self.assertEqual(tuple(conn.execute(
            "SELECT status,paid FROM bookings WHERE id=42").fetchone()), ("confirmed", 1))
        conn.close()

    def test_live_payment_requires_explicit_mode(self):
        conn, sid = make_db(True)
        session = paid_session(True, sid)
        self.assertEqual(settle_verified_stripe_session(conn, session), "rejected")
        self.assertEqual(settle_verified_stripe_session(
            conn, session, expected_livemode=True), "confirmed")
        self.assertEqual(settle_verified_stripe_session(
            conn, session, expected_livemode=True), "duplicate")
        conn.close()

    def test_test_session_rejected_by_live_settlement(self):
        conn, sid = make_db(False)
        self.assertEqual(settle_verified_stripe_session(
            conn, paid_session(False, sid), expected_livemode=True), "rejected")
        self.assertEqual(conn.execute("SELECT paid FROM bookings").fetchone()[0], 0)
        conn.close()

    def test_wrong_amount_retains_pending(self):
        conn, sid = make_db(True)
        session = paid_session(True, sid)
        session["amount_total"] = 100
        self.assertEqual(settle_verified_stripe_session(
            conn, session, expected_livemode=True), "rejected")
        self.assertEqual(conn.execute("SELECT status FROM bookings").fetchone()[0], "pending")
        conn.close()

    def test_wrong_booking_reference_retains_pending(self):
        conn, sid = make_db(True)
        session = paid_session(True, sid)
        session["metadata"]["booking_id"] = "999"
        self.assertEqual(settle_verified_stripe_session(
            conn, session, expected_livemode=True), "rejected")
        conn.close()


if __name__ == "__main__":
    unittest.main()

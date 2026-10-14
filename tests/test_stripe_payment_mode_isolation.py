"""Offline safety tests: Stripe test/live sessions cannot cross-settle bookings."""
import unittest

from stripe_booking_verification import StripeBookingMismatch, verify_paid_checkout_session


def fixtures(live=False):
    sid = ("cs_live_" if live else "cs_test_") + "example"
    booking = {
        "id": 42, "total": 149.0, "payment_method": "stripe_checkout",
        "status": "pending", "paid": 0, "stripe_session_id": sid,
    }
    session = {
        "id": sid, "livemode": live, "mode": "payment",
        "status": "complete", "payment_status": "paid",
        "currency": "eur", "amount_total": 14900,
        "payment_intent": "pi_example", "client_reference_id": "42",
        "metadata": {"booking_id": "42"},
    }
    return session, booking


class StripeModeIsolationTests(unittest.TestCase):
    def test_sandbox_accepts_test_session(self):
        self.assertEqual(verify_paid_checkout_session(*fixtures(False)), "pi_example")

    def test_sandbox_rejects_live_session(self):
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(*fixtures(True))

    def test_live_accepts_live_session_only_with_explicit_flag(self):
        self.assertEqual(verify_paid_checkout_session(*fixtures(True), expected_livemode=True), "pi_example")

    def test_live_rejects_test_session(self):
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(*fixtures(False), expected_livemode=True)

    def test_live_rejects_test_session_id_prefix_even_if_flag_is_live(self):
        session, booking = fixtures(True)
        session["id"] = booking["stripe_session_id"] = "cs_test_example"
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(session, booking, expected_livemode=True)

    def test_rejects_amount_mismatch(self):
        session, booking = fixtures(True)
        session["amount_total"] = 14800
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(session, booking, expected_livemode=True)

    def test_rejects_wrong_booking_reference(self):
        session, booking = fixtures(True)
        session["metadata"]["booking_id"] = "43"
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(session, booking, expected_livemode=True)

    def test_rejects_non_boolean_mode(self):
        with self.assertRaises(StripeBookingMismatch):
            verify_paid_checkout_session(*fixtures(False), expected_livemode="false")


if __name__ == "__main__":
    unittest.main()

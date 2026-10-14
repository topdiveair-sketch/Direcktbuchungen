import unittest
from datetime import datetime, timedelta, timezone
from stripe_live_calendar_gate import card_checkout_calendar_ready

SOURCES = [
    ("booking_ical", "Booking.com", "https://example.test/booking"),
    ("beds24_ical", "Beds24", "https://example.test/beds24"),
    ("airbnb_ical", "Airbnb", "https://example.test/airbnb"),
]
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
GOOD = "Booking.com: 8 · Beds24: 2 · Airbnb: 0"


def check(sources=SOURCES, report=GOOD, success=True, timestamp=NOW):
    return card_checkout_calendar_ready(
        sources, report, success, synced_at=timestamp, now=NOW)[0]


class LiveCalendarGateTests(unittest.TestCase):
    def test_all_providers_success(self):
        self.assertTrue(check())

    def test_one_provider_failed(self):
        self.assertFalse(check(report="Booking.com: 8 · Beds24: Fehler (timeout) · Airbnb: 0"))

    def test_missing_report(self):
        self.assertFalse(check(report="Booking.com: 8 · Beds24: 2"))

    def test_reordered_provider(self):
        self.assertFalse(check(report="Booking.com: 8 · Airbnb: 0 · Beds24: 2"))

    def test_failed_sync(self):
        self.assertFalse(check(success=False))

    def test_empty_configuration(self):
        self.assertFalse(check(sources=[]))

    def test_missing_airbnb_configuration(self):
        self.assertFalse(check(sources=SOURCES[:2], report="Booking.com: 8 · Beds24: 2"))

    def test_stale_result(self):
        self.assertFalse(check(timestamp=NOW - timedelta(minutes=6)))

    def test_future_timestamp(self):
        self.assertFalse(check(timestamp=NOW + timedelta(seconds=2)))

    def test_missing_timestamp(self):
        self.assertFalse(check(timestamp=None))

    def test_retry_success(self):
        self.assertTrue(check(report="Booking.com: 8 (nach Retry) · Beds24: 2 · Airbnb: 0"))

    def test_partial_numeric_report_is_rejected(self):
        self.assertFalse(check(report="Booking.com: 8 Fehler · Beds24: 2 · Airbnb: 0"))


if __name__ == "__main__":
    unittest.main()

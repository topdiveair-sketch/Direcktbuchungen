import unittest
from stripe_live_calendar_gate import card_checkout_calendar_ready


SOURCES = [
    ("booking_ical", "Booking.com", "https://example.test/booking"),
    ("beds24_ical", "Beds24", "https://example.test/beds24"),
    ("airbnb_ical", "Airbnb", "https://example.test/airbnb"),
]


class LiveCalendarGateTests(unittest.TestCase):
    def test_all_providers_success(self):
        self.assertTrue(card_checkout_calendar_ready(
            SOURCES, "Booking.com: 8 · Beds24: 2 · Airbnb: 0", True)[0])

    def test_one_provider_failed(self):
        self.assertFalse(card_checkout_calendar_ready(
            SOURCES, "Booking.com: 8 · Beds24: Fehler (timeout) · Airbnb: 0", True)[0])

    def test_missing_source(self):
        self.assertFalse(card_checkout_calendar_ready(
            SOURCES, "Booking.com: 8 · Beds24: 2", True)[0])

    def test_mismatched_provider(self):
        self.assertFalse(card_checkout_calendar_ready(
            SOURCES, "Booking.com: 8 · Airbnb: 0 · Beds24: 2", True)[0])

    def test_stale_sync_marker(self):
        self.assertFalse(card_checkout_calendar_ready(
            SOURCES, "Booking.com: 8 · Beds24: 2 · Airbnb: 0", False)[0])

    def test_empty_configuration(self):
        self.assertFalse(card_checkout_calendar_ready(
            [], "", True)[0])


if __name__ == "__main__":
    unittest.main()

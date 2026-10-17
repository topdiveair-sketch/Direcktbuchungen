"""Regression tests: manual direct prices also reach the legacy booking checkout."""
import unittest
from datetime import date
from unittest.mock import patch
import app as legacy


class ManualCheckoutRateTests(unittest.TestCase):
    def test_event_friday_manual_price_skips_demand_markup(self):
        with patch.object(legacy, "_base_direct_nightly_price_for_day", return_value=149.0), \
             patch.object(legacy, "_demand_percent_for_day", return_value=(15.0, 10)), \
             patch.dict(legacy.app.extensions, {"zab_channel_price_for_day": lambda room, channel, day, fallback: (99.0, True)}):
            self.assertEqual(legacy.direct_nightly_price_for_day("Bachblick", date(2026, 10, 16)), 99.0)

    def test_other_date_manual_price_skips_demand_markup(self):
        with patch.object(legacy, "_base_direct_nightly_price_for_day", return_value=129.0), \
             patch.object(legacy, "_demand_percent_for_day", return_value=(12.0, 7)), \
             patch.dict(legacy.app.extensions, {"zab_channel_price_for_day": lambda room, channel, day, fallback: (115.0, True)}):
            self.assertEqual(legacy.direct_nightly_price_for_day("Bachblick", date(2026, 11, 7)), 115.0)

    def test_no_manual_override_keeps_automatic_price(self):
        with patch.object(legacy, "_base_direct_nightly_price_for_day", return_value=120.0), \
             patch.object(legacy, "_demand_percent_for_day", return_value=(0.0, 0)), \
             patch.dict(legacy.app.extensions, {"zab_channel_price_for_day": lambda room, channel, day, fallback: (fallback, False)}):
            self.assertEqual(legacy.direct_nightly_price_for_day("Bachblick", date(2026, 11, 7)), 120.0)


if __name__ == "__main__":
    unittest.main()

"""Regression checks for final direct-price parity with Beds24."""
import os
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import app as app_module
from pricing_2027 import pricing_config


class FinalDirectRatePolicyTests(unittest.TestCase):
    def test_checkout_does_not_apply_legacy_direct_discount(self):
        discounts = {
            "last_minute": {"enabled": False, "percent": 10, "days_before": 3},
            "early_bird": {"enabled": False, "percent": 5, "days_before": 60},
            "three_nights": {"enabled": False, "percent": 5, "min_nights": 3},
            "five_nights": {"enabled": False, "percent": 8, "min_nights": 5},
            "seven_nights": {"enabled": False, "percent": 12, "min_nights": 7},
            # Simulate a legacy database that still has the 3% discount enabled.
            "direct_booking": {"enabled": True, "percent": 3},
        }
        with patch.object(app_module, "pricing_data", return_value=({}, discounts, {}, {})), \
             patch.object(app_module, "direct_nightly_price_for_day", return_value=139.0), \
             patch.object(app_module, "_demand_percent_for_day", return_value=(0.0, 0)):
            result = app_module.price_breakdown(
                "Bachblick", date(2026, 10, 16), date(2026, 10, 17),
                2, {"breakfast": False}
            )
        self.assertEqual(result["room_total"], 139.0)
        self.assertEqual(result["total"], 139.0)
        self.assertEqual(result["discounts"], [])

    def test_os_price_feed_checkout_equals_final_display_price(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE demand_signals(visitor_hash, target_day)")
        conn.execute("CREATE TABLE central_overrides(room, day, availability, price)")
        with patch.dict(os.environ, {"OS_SYNC_TOKEN": "test-token"}), \
             patch.object(app_module, "db", return_value=conn), \
             patch.object(app_module, "direct_nightly_price_for_day", return_value=139.0), \
             patch.object(app_module, "_demand_percent_for_day", return_value=(0.0, 0)):
            response = app_module.app.test_client().get(
                "/api/os/direct-prices?room=Bachblick&from=2026-10-16&to=2026-10-16",
                headers={"X-OS-Sync-Token": "test-token"},
            )
        self.assertEqual(response.status_code, 200)
        day = response.get_json()["days"][0]
        self.assertEqual(day["display_price"], 139.0)
        self.assertEqual(day["checkout_price"], 139.0)
        self.assertEqual(day["direct_discount_percent"], 0.0)
        conn.close()

    def test_late_booking_surcharge_matches_user_policy(self):
        rules = pricing_config()["revenue_rules"]
        self.assertEqual(rules["same_day_after_hour_local"], 20)
        self.assertEqual(rules["same_day_after_hour_timezone"], "Europe/Vienna")
        self.assertEqual(rules["same_day_after_hour_add_eur"], 50)


if __name__ == "__main__":
    unittest.main()

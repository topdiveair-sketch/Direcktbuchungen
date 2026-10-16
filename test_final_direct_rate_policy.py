"""Regressions for the final direct price and central calendar precedence."""
import os
import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

import app as app_module
import pricing_2027_gateway as pricing_gateway
from pricing_2027 import pricing_config


class FinalDirectRatePolicyTests(unittest.TestCase):
    def test_checkout_does_not_apply_legacy_direct_discount(self):
        legacy_breakdown = {
            "room_total": 134.83,
            "extras": [],
            "discounts": [{"label": "Direct Booking", "percent": 3, "amount": 4.17}],
            "total": 134.83,
        }
        with patch.object(pricing_gateway, "_original_price_breakdown", return_value=legacy_breakdown), \
             patch.object(pricing_gateway, "nightly_direct_rate", return_value=139.0), \
             patch.object(app_module, "direct_nightly_price_for_day", return_value=139.0), \
             patch.object(app_module, "central_override_for_day", return_value={}), \
             patch.object(pricing_gateway, "effective_direct_rate", return_value=(139.0, False)), \
             patch.object(pricing_gateway, "quiet_night_rate", return_value=None):
            result = pricing_gateway.price_breakdown_2027(
                "Bachblick", date(2026, 10, 16), date(2026, 10, 17),
                2, {"breakfast": False}
            )
        self.assertEqual(result["room_total"], 139.0)
        self.assertEqual(result["total"], 139.0)
        self.assertEqual(result["discounts"], [])

    def test_manual_calendar_price_beats_quiet_night_automation(self):
        legacy_breakdown = {"room_total": 96.03, "extras": [], "discounts": [], "total": 96.03}
        with patch.object(pricing_gateway, "_original_price_breakdown", return_value=legacy_breakdown), \
             patch.object(pricing_gateway, "nightly_direct_rate", return_value=119.0), \
             patch.object(app_module, "direct_nightly_price_for_day", return_value=109.0), \
             patch.object(app_module, "central_override_for_day", return_value={"price": 109.0}), \
             patch.object(pricing_gateway, "effective_direct_rate", return_value=(109.0, True)), \
             patch.object(pricing_gateway, "quiet_night_rate", return_value=99.0):
            result = pricing_gateway.price_breakdown_2027(
                "Bachblick", date(2026, 10, 19), date(2026, 10, 20),
                2, {"breakfast": False}
            )
        self.assertEqual(result["room_total"], 109.0)
        self.assertEqual(result["total"], 109.0)

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

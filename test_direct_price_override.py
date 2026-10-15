"""Regression coverage for direct-price precedence. Run: python -m unittest test_direct_price_override.py"""
import unittest
from datetime import date
from unittest.mock import patch

import wachauetappe_gateway as gateway


class DirectPriceOverrideTests(unittest.TestCase):
    def test_event_night_uses_manual_os_price(self):
        day = date(2026, 10, 16)
        with patch.object(gateway, "_master_direct_availability", return_value=(True, "ok")), \
             patch.object(gateway, "_public_calendar_safety_check", return_value=(True, "ok")), \
             patch.object(gateway, "_effective_direct_rate", return_value=(99.0, True)):
            with gateway.app.test_client() as client:
                response = client.get("/api/direct-price?arrival=2026-10-16&departure=2026-10-17")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["nights"][0]["price_eur"], 99.0)

    def test_quiet_night_does_not_replace_os_override(self):
        with patch.object(gateway, "_master_direct_availability", return_value=(True, "ok")), \
             patch.object(gateway, "_public_calendar_safety_check", return_value=(True, "ok")), \
             patch.object(gateway, "_effective_direct_rate", return_value=(109.0, True)):
            with gateway.app.test_client() as client:
                response = client.get("/api/direct-price?arrival=2026-10-19&departure=2026-10-20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["nights"][0]["price_eur"], 109.0)
        self.assertTrue(response.json["nights"][0]["os_override"])

    def test_quiet_night_uses_fallback_without_os_override(self):
        with patch.object(gateway, "_master_direct_availability", return_value=(True, "ok")), \
             patch.object(gateway, "_public_calendar_safety_check", return_value=(True, "ok")), \
             patch.object(gateway, "_effective_direct_rate", return_value=(129.0, False)):
            with gateway.app.test_client() as client:
                response = client.get("/api/direct-price?arrival=2026-10-19&departure=2026-10-20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["nights"][0]["price_eur"], 99.0)


if __name__ == "__main__":
    unittest.main()

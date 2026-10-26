"""Safe, DB-isolated regression checks for direct booking checkout changes.

Run: python -m unittest discover -s tests -p 'test_booking_reliability_20261026.py' -v
No imports from the production Flask app; no network, payment, bookings or writes.
"""
import ast
import re
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def load_function(filename, name, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / filename), "exec"), namespace)
    return namespace[name]


class ManualRateTests(unittest.TestCase):
    def test_explicit_direct_rate_clamped_and_selected(self):
        price = [115.0]
        class FakeConnection:
            def execute(self, statement, params):
                assert "channel='direct'" in statement
                return SimpleNamespace(fetchone=lambda: {"price": price[0]})
        @contextmanager
        def fake_db():
            yield FakeConnection()
        env = dict(db=fake_db, sqlite3=sqlite3, date=date,
                   cap_room_rate=lambda n: min(149, n),
                   central_override_for_day=lambda room, day: {})
        rate = load_function("app.py", "explicit_manual_direct_price_for_day", env)
        self.assertEqual(rate("Bachblick", date(2026, 11, 7)), 115.0)
        price[0] = 80.0
        self.assertEqual(rate("Bachblick", date(2026, 11, 7)), 99.0)
        price[0] = 190.0
        self.assertEqual(rate("Bachblick", date(2026, 11, 7)), 149.0)

    def test_manual_rate_skips_demand_in_core_price(self):
        def fail_if_called(*args):
            raise AssertionError("Demand pricing must not run for a manual rate")
        env = dict(date=date, explicit_manual_direct_price_for_day=lambda *args: 115.0,
                   _base_direct_nightly_price_for_day=fail_if_called,
                   _demand_percent_for_day=fail_if_called)
        fn = load_function("app.py", "direct_nightly_price_for_day", env)
        self.assertEqual(fn("Bachblick", date(2026, 11, 7)), 115.0)

    def test_manual_rate_skips_checkout_yield_and_sameday_charge(self):
        def fail_if_called(*args, **kwargs):
            raise AssertionError("Yield uplift must not run for a manual rate")
        app = SimpleNamespace(
            direct_nightly_price_for_day=lambda room, day: 115.0,
            explicit_manual_direct_price_for_day=lambda room, day: 115.0)
        env = dict(price_breakdown=lambda *a: {"extras": []},
                   core_app=app, _booked_nights_next_30_days=lambda *a: set(),
                   _revenue_adjustment_for_day=fail_if_called,
                   pricing_config=lambda: {"revenue_rules": {"same_day_after_hour_local": 0}},
                   ZoneInfo=ZoneInfo, datetime=datetime, timedelta=timedelta,
                   cap_room_rate=lambda n: min(n, 149),
                   PUBLIC_BACHBLICK_NIGHTLY_PRICE=99.0)
        fn = load_function("railway_app.py", "direct_checkout_price_breakdown", env)
        start = date(2026, 11, 7)
        result = fn("Bachblick", start, start + timedelta(days=1), 2, {})
        self.assertEqual(result["total"], 115.0)
        self.assertEqual(result["room_total"], 115.0)
        self.assertEqual(result["revenue_management"][0]["yield_add_eur"], 0.0)
        self.assertTrue(result["revenue_management"][0]["manual_direct_price"])


class CheckoutGuardTests(unittest.TestCase):
    def test_stripe_keeps_active_hold_but_removes_six_hour_ip_lock(self):
        code = (ROOT / "stripe_checkout.py").read_text(encoding="utf-8")
        self.assertIn("if active_hold:", code)
        self.assertIn("checkout_ip_hash", code)
        self.assertNotIn("CHECKOUT_WINDOW_HOURS", code)
        self.assertNotIn("attempt_count >=", code)
        self.assertIn("re.fullmatch(", code)
        regex = r"[^\\s@]+@[^\\s@]+\\.[^\\s@]+"
        for email in ("guest@example.com", "first.last+stay@example.at"):
            self.assertIsNotNone(re.fullmatch(regex, email))
        for email in ("invalid", "guest @example.com", "guest@example", "a@@b.com"):
            self.assertIsNone(re.fullmatch(regex, email))

    def test_browser_payment_choices_match_server_rules(self):
        html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
        js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
        self.assertIn('value="Banküberweisung"', html)
        self.assertNotIn('value="Vor Ort"', html)
        self.assertIn("bank.disabled = !allowed", js)
        self.assertIn("paypal.checked = true", js)
        self.assertIn("bankLabel.textContent=T.bank", html)


if __name__ == "__main__":
    unittest.main()

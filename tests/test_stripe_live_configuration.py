"""Regression tests for the fail-closed Stripe live webhook configuration gate."""
import unittest

from stripe_live_configuration import (
    StripeLiveConfigurationError,
    validate_live_webhook_configuration,
)


def config():
    return {
        "STRIPE_LIVE_WEBHOOK_ENABLED": "1",
        "STRIPE_LIVE_BOOKING_INTEGRATION_VERIFIED": "1",
        "STRIPE_LIVE_SECRET_KEY": "sk_live_example",
        "STRIPE_LIVE_WEBHOOK_SECRET": "whsec_live_example",
        "STRIPE_TEST_WEBHOOK_SECRET": "whsec_test_example",
        "ZAB_STRIPE_ISOLATED_TEST": "0",
    }


class LiveConfigurationTests(unittest.TestCase):
    def test_valid_dedicated_configuration(self):
        self.assertEqual(validate_live_webhook_configuration(config()), "whsec_live_example")

    def test_missing_live_enable_flag(self):
        data = config()
        data.pop("STRIPE_LIVE_WEBHOOK_ENABLED")
        with self.assertRaises(StripeLiveConfigurationError):
            validate_live_webhook_configuration(data)

    def test_sandbox_service_blocked(self):
        data = config()
        data["ZAB_STRIPE_ISOLATED_TEST"] = "1"
        with self.assertRaises(StripeLiveConfigurationError):
            validate_live_webhook_configuration(data)

    def test_missing_booking_integration_approval(self):
        data = config()
        data.pop("STRIPE_LIVE_BOOKING_INTEGRATION_VERIFIED")
        with self.assertRaises(StripeLiveConfigurationError):
            validate_live_webhook_configuration(data)

    def test_test_api_key_rejected(self):
        data = config()
        data["STRIPE_LIVE_SECRET_KEY"] = "sk_test_example"
        with self.assertRaises(StripeLiveConfigurationError):
            validate_live_webhook_configuration(data)

    def test_shared_signing_secret_rejected(self):
        data = config()
        data["STRIPE_LIVE_WEBHOOK_SECRET"] = data["STRIPE_TEST_WEBHOOK_SECRET"]
        with self.assertRaises(StripeLiveConfigurationError):
            validate_live_webhook_configuration(data)


if __name__ == "__main__":
    unittest.main()

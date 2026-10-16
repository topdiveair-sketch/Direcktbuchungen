import json
from urllib.parse import parse_qs
import pytest

from stripe_checkout_client import create_hosted_checkout_session, StripeCheckoutError


class FakeResponse:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.data).encode()


def make(opener, secret_key="sk_test_example"):
    return create_hosted_checkout_session(
        secret_key=secret_key, booking_id=14, total_eur="125.50",
        guest_email="guest@example.test",
        success_url="https://example.test/stripe/success",
        cancel_url="https://example.test/stripe/cancel",
        opener=opener,
    )


def test_session_request_is_server_priced_and_idempotent():
    def fake_open(req, timeout):
        assert req.full_url == "https://api.stripe.com/v1/checkout/sessions"
        assert req.get_header("Idempotency-key") == "zab-checkout-14"
        assert req.get_header("Authorization") == "Bearer sk_test_example"
        fields = parse_qs(req.data.decode())
        assert fields["line_items[0][price_data][unit_amount]"] == ["12550"]
        assert fields["client_reference_id"] == ["14"]
        assert 1800 <= int(fields["expires_at"][0]) - __import__("time").time() <= 1860
        return FakeResponse({"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/test",
                             "mode": "payment", "client_reference_id": "14"})
    assert make(fake_open)["id"] == "cs_test_123"


def test_live_secret_is_rejected_before_network_request():
    with pytest.raises(StripeCheckoutError):
        make(lambda *args, **kwargs: pytest.fail("Network must not be called"), secret_key="sk_live_not_allowed")


def test_mismatched_booking_is_rejected():
    with pytest.raises(StripeCheckoutError):
        make(lambda *args, **kwargs: FakeResponse({
            "id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/test",
            "mode": "payment", "client_reference_id": "15",
        }))


def test_explicit_expiry_is_preserved_for_identical_replay():
    seen = []
    def fake_open(req, timeout):
        fields = parse_qs(req.data.decode())
        seen.append(fields["expires_at"][0])
        return FakeResponse({"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/test",
                             "mode": "payment", "client_reference_id": "14"})
    for _ in range(2):
        create_hosted_checkout_session(
            secret_key="sk_test_example", booking_id=14, total_eur="125.50",
            guest_email="guest@example.test",
            success_url="https://example.test/stripe/success",
            cancel_url="https://example.test/stripe/cancel",
            expires_at=1791900000, opener=fake_open)
    assert seen == ["1791900000", "1791900000"]

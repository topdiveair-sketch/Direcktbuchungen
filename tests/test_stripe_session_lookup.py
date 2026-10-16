import json
import pytest

from stripe_session_lookup import retrieve_test_checkout_session, StripeSessionLookupError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode()


def test_read_only_stripe_lookup():
    def fake_open(request, timeout):
        assert request.get_method() == "GET"
        assert request.full_url.endswith("/v1/checkout/sessions/cs_test_123")
        assert request.get_header("Authorization") == "Bearer sk_test_key"
        return FakeResponse({"id": "cs_test_123", "livemode": False, "status": "expired",
                             "payment_status": "unpaid"})
    result = retrieve_test_checkout_session(secret_key="sk_test_key",
                                            session_id="cs_test_123", opener=fake_open)
    assert result["status"] == "expired"


@pytest.mark.parametrize("key,session_id", [
    ("sk_live_key", "cs_test_123"), ("sk_test_key", "cs_live_123"),
    ("sk_test_key", "cs_test_../bad"), ("sk_test_key", "cs_test_123?x=1"),
])
def test_rejects_unsafe_identifiers_and_keys(key, session_id):
    with pytest.raises(StripeSessionLookupError):
        retrieve_test_checkout_session(secret_key=key, session_id=session_id,
                                       opener=lambda *args, **kwargs: pytest.fail("Network forbidden"))


def test_rejects_mismatched_api_session():
    with pytest.raises(StripeSessionLookupError):
        retrieve_test_checkout_session(
            secret_key="sk_test_key", session_id="cs_test_123",
            opener=lambda *args, **kwargs: FakeResponse({"id": "cs_test_999", "livemode": False}),
        )

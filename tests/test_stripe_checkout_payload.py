import pytest
from urllib.parse import parse_qs
from stripe_checkout_payload import checkout_session_fields, encoded_checkout_fields, CheckoutValidationError


def make(**overrides):
    args = dict(booking_id=27, total_eur="119.90", guest_email="guest@example.test",
                success_url="https://example.test/stripe/success",
                cancel_url="https://example.test/stripe/cancel")
    args.update(overrides)
    return args


def test_dynamic_price_and_booking_reference():
    fields = checkout_session_fields(**make())
    assert fields["line_items[0][price_data][unit_amount]"] == "11990"
    assert fields["line_items[0][price_data][currency]"] == "eur"
    assert fields["payment_method_types[0]"] == "card"
    assert fields["client_reference_id"] == "27"
    assert parse_qs(encoded_checkout_fields(**make()).decode())["customer_email"] == ["guest@example.test"]


@pytest.mark.parametrize("overrides", [
    {"total_eur": "0"}, {"total_eur": "nan"}, {"total_eur": "-1"},
    {"booking_id": 0}, {"guest_email": ""}, {"success_url": "http://example.test/ok"},
])
def test_invalid_checkout_rejected(overrides):
    with pytest.raises(CheckoutValidationError):
        checkout_session_fields(**make(**overrides))

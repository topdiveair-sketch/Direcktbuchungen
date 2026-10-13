import pytest
from stripe_booking_verification import verify_paid_checkout_session, StripeBookingMismatch


def booking():
    return dict(id=42, total="119.90", status="pending", paid=0,
                payment_method="stripe_checkout", stripe_session_id="cs_test_abc")


def session():
    return dict(id="cs_test_abc", mode="payment", status="complete",
                payment_status="paid", currency="eur", amount_total=11990,
                client_reference_id="42", metadata={"booking_id": "42"},
                payment_intent="pi_test_abc")


def test_exact_paid_booking_is_accepted():
    assert verify_paid_checkout_session(session(), booking()) == "pi_test_abc"


@pytest.mark.parametrize("key,value", [
    ("amount_total", 11989), ("currency", "usd"), ("payment_status", "unpaid"),
    ("status", "open"), ("client_reference_id", "43"), ("payment_intent", None),
    ("id", "cs_test_other"), ("metadata", {"booking_id": "43"}),
])
def test_mismatched_session_is_rejected(key, value):
    payload = session()
    payload[key] = value
    with pytest.raises(StripeBookingMismatch):
        verify_paid_checkout_session(payload, booking())


@pytest.mark.parametrize("key,value", [
    ("status", "cancelled"), ("paid", 1), ("payment_method", "paypal_checkout"),
    ("stripe_session_id", "cs_test_other"),
])
def test_unavailable_or_other_payment_booking_is_rejected(key, value):
    record = booking()
    record[key] = value
    with pytest.raises(StripeBookingMismatch):
        verify_paid_checkout_session(session(), record)

from datetime import datetime, timedelta, timezone
import pytest

from stripe_hold_release import may_release_stripe_hold, StripeReleaseUnsafe

NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)


def booking():
    return {"id": 12, "payment_method": "stripe_checkout", "status": "pending",
            "paid": 0, "stripe_session_id": "cs_test_12"}


def session():
    return {"id": "cs_test_12", "livemode": False, "status": "expired",
            "payment_status": "unpaid", "payment_intent": None,
            "client_reference_id": "12",
            "expires_at": int((NOW - timedelta(minutes=20)).timestamp())}


def test_expired_unpaid_session_after_grace_can_be_released():
    assert may_release_stripe_hold(session(), booking(), now=NOW)


@pytest.mark.parametrize("field,value", [
    ("status", "complete"), ("status", "open"),
    ("payment_status", "paid"), ("payment_status", "no_payment_required"),
    ("payment_intent", "pi_test_12"), ("livemode", True),
    ("id", "cs_test_other"), ("client_reference_id", "13"),
])
def test_unsafe_session_is_never_released(field, value):
    data = session()
    data[field] = value
    assert not may_release_stripe_hold(data, booking(), now=NOW)


def test_pending_webhook_grace_prevents_early_release():
    data = session()
    data["expires_at"] = int((NOW - timedelta(minutes=10)).timestamp())
    assert not may_release_stripe_hold(data, booking(), now=NOW)


def test_confirmed_or_cancelled_booking_is_not_released():
    for state in ("confirmed", "cancelled"):
        record = booking()
        record["status"] = state
        assert not may_release_stripe_hold(session(), record, now=NOW)


def test_naive_time_is_rejected():
    with pytest.raises(StripeReleaseUnsafe):
        may_release_stripe_hold(session(), booking(), now=NOW.replace(tzinfo=None))

"""End-to-end SQLite state-transition tests without real Stripe charges."""
import sqlite3
from datetime import datetime, timedelta, timezone

from stripe_booking_settlement import settle_verified_stripe_session
from stripe_hold_reconciliation import reconcile_expired_stripe_holds

NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)


def setup_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, total TEXT, status TEXT, paid INTEGER,
        payment_method TEXT, stripe_session_id TEXT, stripe_payment_intent TEXT,
        paid_at TEXT, hold_expires_at TEXT, payment_error TEXT,
        released_at TEXT, release_reason TEXT)""")
    conn.execute("""INSERT INTO bookings
        (id,total,status,paid,payment_method,stripe_session_id,hold_expires_at)
        VALUES (1,'119.90','pending',0,'stripe_checkout','cs_test_one','later')""")
    conn.commit()

    def db():
        class Context:
            def __enter__(self):
                return conn
            def __exit__(self, exc_type, exc, tb):
                if exc_type:
                    conn.rollback()
                else:
                    conn.commit()
        return Context()
    return conn, db


def paid_session():
    return dict(id="cs_test_one", object="checkout.session", livemode=False,
                mode="payment", status="complete", payment_status="paid",
                currency="eur", amount_total=11990, client_reference_id="1",
                metadata={"booking_id": "1"}, payment_intent="pi_test_one")


def expired_session():
    return dict(id="cs_test_one", object="checkout.session", livemode=False,
                mode="payment", status="expired", payment_status="unpaid",
                currency="eur", amount_total=11990, client_reference_id="1",
                metadata={"booking_id": "1"}, payment_intent=None,
                expires_at=int((NOW - timedelta(minutes=20)).timestamp()))


def test_paid_booking_survives_later_expired_reconciliation():
    conn, db = setup_db()
    assert settle_verified_stripe_session(conn, paid_session()) == "confirmed"
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW,
        lookup=lambda **kwargs: expired_session())
    assert report["released"] == 0
    assert conn.execute("SELECT status,paid FROM bookings").fetchone()[:] == ("confirmed", 1)
    assert settle_verified_stripe_session(conn, paid_session()) == "duplicate"


def test_expired_unpaid_booking_rejects_late_paid_webhook():
    conn, db = setup_db()
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW,
        lookup=lambda **kwargs: expired_session())
    assert report["released"] == 1
    assert settle_verified_stripe_session(conn, paid_session()) == "rejected"
    assert conn.execute("SELECT status,paid FROM bookings").fetchone()[:] == ("cancelled", 0)


def test_failed_stripe_lookup_never_releases_or_confirms():
    conn, db = setup_db()
    def fail(**kwargs):
        raise ConnectionError("simulated Stripe outage")
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW, lookup=fail)
    assert report["failed"] == 1
    assert conn.execute("SELECT status,paid FROM bookings").fetchone()[:] == ("pending", 0)


def test_missed_webhook_is_recovered_by_authoritative_stripe_lookup():
    conn, db = setup_db()
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW,
        lookup=lambda **kwargs: paid_session())
    assert report["confirmed"] == 1
    assert tuple(conn.execute("SELECT status,paid,stripe_payment_intent FROM bookings").fetchone()) == (
        "confirmed", 1, "pi_test_one")
    again = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW,
        lookup=lambda **kwargs: expired_session())
    assert again["released"] == 0


def test_mismatched_paid_session_is_not_confirmed():
    conn, db = setup_db()
    invalid = paid_session()
    invalid["amount_total"] = 100
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_dummy", now=NOW,
        lookup=lambda **kwargs: invalid)
    assert report["failed"] == 1
    assert tuple(conn.execute("SELECT status,paid FROM bookings").fetchone()) == ("pending", 0)

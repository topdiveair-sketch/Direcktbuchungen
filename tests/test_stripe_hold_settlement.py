import sqlite3
from datetime import datetime, timedelta, timezone
from stripe_hold_settlement import release_verified_stripe_hold

NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)


def database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings(
        id INTEGER PRIMARY KEY, stripe_session_id TEXT, payment_method TEXT,
        status TEXT, paid INTEGER, released_at TEXT, release_reason TEXT,
        hold_expires_at TEXT)""")
    conn.execute("""INSERT INTO bookings VALUES
        (1,'cs_test_123','stripe_checkout','pending',0,'','','later')""")
    conn.commit()
    return conn


def session():
    return {"id": "cs_test_123", "livemode": False, "status": "expired",
            "payment_status": "unpaid", "payment_intent": None,
            "client_reference_id": "1",
            "expires_at": int((NOW - timedelta(minutes=20)).timestamp())}


def test_releases_verified_expired_unpaid_hold():
    conn = database()
    assert release_verified_stripe_hold(conn, session(), now=NOW) == "released"
    row = conn.execute("SELECT status,hold_expires_at FROM bookings WHERE id=1").fetchone()
    assert tuple(row) == ("cancelled", "")
    assert release_verified_stripe_hold(conn, session(), now=NOW) == "duplicate"


def test_does_not_release_paid_or_open_session():
    for key, value in (("payment_status", "paid"), ("status", "open"),
                       ("livemode", True), ("payment_intent", "pi_test_1")):
        conn = database()
        data = session()
        data[key] = value
        assert release_verified_stripe_hold(conn, data, now=NOW) == "retained"
        assert conn.execute("SELECT status FROM bookings").fetchone()[0] == "pending"


def test_does_not_release_during_grace_period():
    conn = database()
    data = session()
    data["expires_at"] = int((NOW - timedelta(minutes=5)).timestamp())
    assert release_verified_stripe_hold(conn, data, now=NOW) == "retained"


def test_does_not_release_wrong_booking():
    conn = database()
    data = session()
    data["client_reference_id"] = "2"
    assert release_verified_stripe_hold(conn, data, now=NOW) == "retained"

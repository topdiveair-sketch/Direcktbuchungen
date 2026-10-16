import sqlite3
from datetime import datetime, timedelta, timezone

from stripe_hold_reconciliation import reconcile_expired_stripe_holds

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
    class DB:
        def __call__(self):
            class Ctx:
                def __enter__(self):
                    return conn
                def __exit__(self, exc_type, exc, tb):
                    if exc_type:
                        conn.rollback()
                    else:
                        conn.commit()
            return Ctx()
    return conn, DB()


def session():
    return {"id": "cs_test_123", "livemode": False, "status": "expired",
            "payment_status": "unpaid", "payment_intent": None,
            "client_reference_id": "1",
            "expires_at": int((NOW - timedelta(minutes=20)).timestamp())}


def test_reconciliation_releases_only_verified_unpaid_hold():
    conn, db = database()
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_123", now=NOW,
        lookup=lambda **kwargs: session())
    assert report["released"] == 1
    assert conn.execute("SELECT status FROM bookings").fetchone()[0] == "cancelled"


def test_network_failure_keeps_room_reserved():
    conn, db = database()
    def failing(**kwargs):
        raise OSError("Stripe unavailable")
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_123", now=NOW, lookup=failing)
    assert report["failed"] == 1
    assert conn.execute("SELECT status FROM bookings").fetchone()[0] == "pending"


def test_open_session_keeps_room_reserved():
    conn, db = database()
    data = session()
    data["status"] = "open"
    report = reconcile_expired_stripe_holds(
        db, secret_key="sk_test_123", now=NOW, lookup=lambda **kwargs: data)
    assert report["retained"] == 1
    assert conn.execute("SELECT status FROM bookings").fetchone()[0] == "pending"


def test_reconciliation_prioritizes_earliest_expiring_hold():
    conn, db = database()
    conn.execute("UPDATE bookings SET hold_expires_at='2026-10-20T00:00:00' WHERE id=1")
    conn.execute("""INSERT INTO bookings(id,stripe_session_id,payment_method,status,paid,
                 released_at,release_reason,hold_expires_at)
                 VALUES(2,'cs_test_early','stripe_checkout','pending',0,'','','2026-10-12T00:00:00')""")
    conn.commit()
    checked = []
    def lookup(**kwargs):
        checked.append(kwargs["session_id"])
        return {"id": kwargs["session_id"], "livemode": False, "status": "open",
                "payment_status": "unpaid", "payment_intent": None,
                "client_reference_id": "2", "expires_at": int(NOW.timestamp())}
    report = reconcile_expired_stripe_holds(db, secret_key="sk_test_123", now=NOW,
                                             limit=1, lookup=lookup)
    assert report["checked"] == 1
    assert checked == ["cs_test_early"]

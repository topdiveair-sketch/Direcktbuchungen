import sqlite3

from stripe_booking_settlement import settle_verified_stripe_session


def test_settlement_confirms_once_and_preserves_other_bookings():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, total TEXT, status TEXT, paid INTEGER,
        payment_method TEXT, stripe_session_id TEXT, stripe_payment_intent TEXT,
        paid_at TEXT, hold_expires_at TEXT, payment_error TEXT,
        released_at TEXT, release_reason TEXT
    )""")
    conn.executemany(
        """INSERT INTO bookings(id,total,status,paid,payment_method,
           stripe_session_id,stripe_payment_intent,hold_expires_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        [(1,"119.90","pending",0,"stripe_checkout","cs_test_one","","2026-10-13T20:00:00"),
         (2,"119.90","pending",0,"paypal_checkout","","","2026-10-13T20:00:00")],
    )
    conn.commit()
    event = dict(id="cs_test_one", livemode=False, mode="payment", status="complete",
                 payment_status="paid", currency="eur", amount_total=11990,
                 client_reference_id="1", metadata={"booking_id": "1"},
                 payment_intent="pi_test_one")
    assert settle_verified_stripe_session(conn, event) == "confirmed"
    assert settle_verified_stripe_session(conn, event) == "duplicate"
    assert tuple(conn.execute("SELECT status,paid,hold_expires_at FROM bookings WHERE id=1").fetchone()) == (
        "confirmed", 1, ""
    )
    assert tuple(conn.execute("SELECT status,paid FROM bookings WHERE id=2").fetchone()) == ("pending", 0)


def test_wrong_amount_does_not_mark_paid():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, total TEXT, status TEXT, paid INTEGER,
        payment_method TEXT, stripe_session_id TEXT, stripe_payment_intent TEXT,
        paid_at TEXT, hold_expires_at TEXT, payment_error TEXT,
        released_at TEXT, release_reason TEXT
    )""")
    conn.execute("INSERT INTO bookings(id,total,status,paid,payment_method,stripe_session_id) VALUES(1,'125.00','pending',0,'stripe_checkout','cs_test_one')")
    conn.commit()
    event = dict(id="cs_test_one", livemode=False, mode="payment", status="complete",
                 payment_status="paid", currency="eur", amount_total=100,
                 client_reference_id="1", metadata={"booking_id": "1"},
                 payment_intent="pi_test_one")
    assert settle_verified_stripe_session(conn, event) == "rejected"
    assert conn.execute("SELECT paid FROM bookings WHERE id=1").fetchone()[0] == 0

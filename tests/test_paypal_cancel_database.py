"""Exercise the cancellation SQL against a real in-memory SQLite database."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1].joinpath("paypal_checkout.py").read_text(encoding="utf-8")


def _cancel_statement():
    route = SOURCE.split("def paypal_cancel():", 1)[1].split('app.extensions["zab_paypal_checkout_enabled"]', 1)[0]
    match = re.search(r'"""(UPDATE bookings SET status=\'cancelled\'.*?)"""', route, re.S)
    assert match, "PayPal cancel SQL not found"
    return match.group(1)


def test_cancel_releases_only_matching_pending_paypal_booking():
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, status TEXT, payment_method TEXT,
        paid INTEGER, released_at TEXT, release_reason TEXT
    )""")
    db.executemany(
        "INSERT INTO bookings(id,status,payment_method,paid) VALUES(?,?,?,?)",
        [(1,"pending","paypal_checkout",0),
         (2,"pending","bank_transfer",0),
         (3,"confirmed","paypal_checkout",1),
         (4,"confirmed","paypal_checkout",0),
         (5,"cancelled","paypal_checkout",0)],
    )
    statement = _cancel_statement()
    now = datetime.now().isoformat(timespec="seconds")
    for booking_id in (1,2,3,4,5):
        db.execute(statement, (now, booking_id))
    rows = db.execute("SELECT id,status,released_at FROM bookings ORDER BY id").fetchall()
    assert rows[0][1] == "cancelled" and rows[0][2] == now
    assert rows[1][1] == "pending" and rows[1][2] is None
    assert rows[2][1] == "confirmed" and rows[2][2] is None
    assert rows[3][1] == "confirmed" and rows[3][2] is None
    assert rows[4][1] == "cancelled" and rows[4][2] is None

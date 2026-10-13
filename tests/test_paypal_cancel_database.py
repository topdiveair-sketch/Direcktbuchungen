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


def test_ambiguous_capture_keeps_pending_reservation_blocked():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bookings (id INTEGER PRIMARY KEY, status TEXT, paid INTEGER, hold_expires_at TEXT, payment_error TEXT)")
    db.executemany("INSERT INTO bookings VALUES(?,?,?,?,?)", [
        (1, "pending", 0, "2026-10-13T18:00:00", ""),
        (2, "confirmed", 1, "", ""),
    ])
    statement = """UPDATE bookings SET payment_error=?,
        hold_expires_at=CASE WHEN status='pending' THEN '' ELSE hold_expires_at END
        WHERE id=? AND COALESCE(paid,0)=0"""
    db.execute(statement, ("Manual reconciliation required", 1))
    assert db.execute("SELECT status,hold_expires_at,payment_error FROM bookings WHERE id=1").fetchone() == (
        "pending", "", "Manual reconciliation required"
    )
    db.execute(statement, ("Must not overwrite", 2))
    assert db.execute("SELECT payment_error FROM bookings WHERE id=2").fetchone()[0] == ""

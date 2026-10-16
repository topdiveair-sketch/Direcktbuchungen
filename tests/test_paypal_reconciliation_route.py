"""Execute the admin PayPal reconciliation route with Flask and SQLite fixtures."""
import ast
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, jsonify

SOURCE = Path(__file__).resolve().parents[1].joinpath("railway_app.py").read_text(encoding="utf-8")


def _route(allowed, connection):
    tree = ast.parse(SOURCE)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "paypal_reconciliation_queue")
    # Compile the original route function without its app registration decorator.
    fn.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    @contextmanager
    def db():
        yield connection
    scope = {
        "require_admin": lambda: allowed,
        "db": db,
        "jsonify": jsonify,
        "app": SimpleNamespace(logger=SimpleNamespace(exception=lambda *args: None)),
    }
    exec(compile(module, "<reconciliation-route>", "exec"), scope)
    return scope["paypal_reconciliation_queue"]


def test_queue_requires_admin_and_only_lists_unresolved_paypal():
    app = Flask(__name__)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bookings (
        id INTEGER PRIMARY KEY, room TEXT, arrival TEXT, departure TEXT,
        status TEXT, paid INTEGER, paypal_order_id TEXT,
        paypal_capture_id TEXT, payment_error TEXT, created_at TEXT,
        payment_method TEXT
    )""")
    conn.executemany(
        """INSERT INTO bookings
        (id,room,arrival,departure,status,paid,paypal_order_id,
         paypal_capture_id,payment_error,created_at,payment_method)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (1,"Gartenzimmer","2026-11-01","2026-11-02","pending",0,"ORDER-1","","PayPal-Zahlungsstatus unklar: capture","2026-10-13","paypal_checkout"),
            (2,"Gartenzimmer","2026-11-03","2026-11-04","confirmed",1,"ORDER-2","","","2026-10-13","paypal_checkout"),
            (3,"Gartenzimmer","2026-11-05","2026-11-06","pending",0,"","","PayPal-Zahlungsstatus unklar: capture","2026-10-13","bank_transfer"),
            (4,"Gartenzimmer","2026-11-07","2026-11-08","pending",0,"ORDER-4","","","2026-10-13","paypal_checkout"),
        ],
    )
    with app.app_context():
        denied = _route(False, conn)()
        assert denied[1] == 403
        assert denied[0].get_json() == {"error": "Nicht autorisiert"}
        allowed = _route(True, conn)()
        payload = allowed.get_json()
        assert payload["count"] == 1
        assert [item["id"] for item in payload["bookings"]] == [1]
        assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 4

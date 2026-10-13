import ast
import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1].joinpath("paypal_checkout.py").read_text(encoding="utf-8")


def _signer(secret):
    tree = ast.parse(SOURCE)
    initializer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "init_paypal_checkout")
    fn = next(node for node in initializer.body if isinstance(node, ast.FunctionDef) and node.name == "cancel_signature")
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope = {"app": SimpleNamespace(secret_key=secret), "hmac": hmac, "hashlib": hashlib}
    exec(compile(module, "<paypal-cancel-signature>", "exec"), scope)
    return scope["cancel_signature"]


def test_signature_matches_only_correct_booking():
    signer = _signer("test-only-secret")
    good = signer(42)
    assert len(good) == 64
    assert hmac.compare_digest(good, signer(42))
    assert not hmac.compare_digest(good, signer(43))
    assert not hmac.compare_digest(good, _signer("different-secret")(42))


def test_missing_secret_fails_closed():
    try:
        _signer(None)(42)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Missing secret must not permit cancellation")


def test_cancel_route_rejects_unsigned_requests():
    assert 'hmac.compare_digest(supplied_signature, cancel_signature(booking_id))' in SOURCE
    assert 'sig={cancel_signature(booking_id)}' in SOURCE
    assert 'COALESCE(paid,0)=0' in SOURCE


def test_paid_return_rejects_stale_unpaid_reservation():
    assert 'if booking["status"] != "pending" and not booking["paid"]:' in SOURCE
    assert 'current["status"] != "pending" or current["paid"]' in SOURCE
    assert '(current["paypal_order_id"] or "").strip() != order_id' in SOURCE


def test_payment_capture_revalidates_reservation():
    assert 'latest = conn.execute("SELECT status,paid,paypal_order_id FROM bookings WHERE id=?"' in SOURCE
    assert 'latest["status"] != "pending"' in SOURCE
    assert 'latest["paypal_order_id"] or ""' in SOURCE


def test_paid_email_recognizes_paypal_checkout_method():
    notifications = Path(__file__).resolve().parents[1].joinpath("booking_notifications.py").read_text(encoding="utf-8")
    ast.parse(notifications)
    assert 'payment_method in {"PayPal", "paypal_checkout"}' in notifications
    assert 'if capture and payment_method in {"PayPal", "paypal_checkout"}:' in notifications


def test_cancel_only_releases_pending_paypal_checkout_holds():
    cancel_route = SOURCE.split("def paypal_cancel():", 1)[1].split('app.extensions["zab_paypal_checkout_enabled"]', 1)[0]
    assert "WHERE id=? AND status='pending' AND payment_method='paypal_checkout'" in cancel_route

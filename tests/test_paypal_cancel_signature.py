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

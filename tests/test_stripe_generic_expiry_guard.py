"""Regression guard: Stripe inventory must never be released by generic cleanup."""
from pathlib import Path


def test_generic_expiry_query_excludes_stripe_checkout():
    source = (Path(__file__).resolve().parents[1] / "paypal_checkout.py").read_text(encoding="utf-8")
    assert "AND COALESCE(payment_method,'')!='stripe_checkout'" in source
    assert "AND COALESCE(hold_expires_at,'')!='' AND hold_expires_at<=?" in source


def test_shared_payment_hold_extension_excludes_stripe_from_select_and_update():
    source = (Path(__file__).resolve().parents[1] / "payment_hold.py").read_text(encoding="utf-8")
    start = source.index("    def release_expired() -> int:")
    end = source.index("    def smtp_send(", start)
    cleanup = source[start:end]
    assert cleanup.count("AND COALESCE(payment_method,'')!='stripe_checkout'") == 2
    assert "UPDATE bookings" in cleanup
    assert "SELECT 1 FROM bookings" in cleanup


def test_missing_stripe_session_queue_is_admin_only_and_read_only():
    source = (Path(__file__).resolve().parents[1] / "railway_app.py").read_text(encoding="utf-8")
    start = source.index("def stripe_unresolved_holds():")
    end = source.index("@app.post(\"/admin/stripe/reconcile\")", start)
    route = source[start:end]
    assert "if not require_admin():" in route
    assert "COALESCE(stripe_session_id,'')=''" in route
    assert "SELECT id,room,arrival,departure" in route
    assert "UPDATE bookings" not in route
    assert 'Cache-Control' in route

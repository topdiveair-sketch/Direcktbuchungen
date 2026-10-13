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


def test_stripe_recovery_requires_admin_original_expiry_and_pending_booking():
    source = (Path(__file__).resolve().parents[1] / "railway_app.py").read_text(encoding="utf-8")
    start = source.index("def stripe_recover_missing_session(booking_id):")
    end = source.index('@app.post("/admin/stripe/reconcile")', start)
    route = source[start:end]
    assert "if not require_admin():" in route
    assert "recovery_requires_manual_review(dict(row))" in route
    assert 'payload.get("stripe_session_expires_at")' in route
    assert "expires_at=expires_at" in route
    assert "COALESCE(stripe_session_id,'')=''" in route
    assert "BEGIN IMMEDIATE" in route


def test_stripe_recovery_uses_persisted_checkout_base_not_current_environment():
    root = Path(__file__).resolve().parents[1]
    checkout = (root / "paypal_checkout.py").read_text(encoding="utf-8")
    railway = (root / "railway_app.py").read_text(encoding="utf-8")
    start = railway.index("def stripe_recover_missing_session(booking_id):")
    end = railway.index('@app.post("/admin/stripe/reconcile")', start)
    recovery = railway[start:end]
    assert '"stripe_checkout_base_url": base' in checkout
    assert 'base = payload.get("stripe_checkout_base_url")' in recovery
    assert 'os.environ.get("PUBLIC_CHECKOUT_BASE_URL"' not in recovery

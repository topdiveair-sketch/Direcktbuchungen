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

"""Regression guard: Stripe inventory must never be released by generic cleanup."""
from pathlib import Path


def test_generic_expiry_query_excludes_stripe_checkout():
    source = (Path(__file__).resolve().parents[1] / "paypal_checkout.py").read_text(encoding="utf-8")
    assert "AND COALESCE(payment_method,'')!='stripe_checkout'" in source
    assert "AND COALESCE(hold_expires_at,'')!='' AND hold_expires_at<=?" in source

import pytest
import stripe_reconciliation_worker as worker


def test_worker_disabled_by_default(monkeypatch):
    monkeypatch.delenv("STRIPE_SANDBOX_RECONCILE_WORKER", raising=False)
    assert worker.start_stripe_reconciliation_worker(lambda: None) is False


def test_worker_requires_test_key(monkeypatch):
    monkeypatch.setenv("STRIPE_SANDBOX_RECONCILE_WORKER", "1")
    monkeypatch.setenv("STRIPE_SANDBOX_CHECKOUT_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_wrong")
    assert worker.start_stripe_reconciliation_worker(lambda: None) is False


def test_worker_rejects_too_frequent_runs(monkeypatch):
    monkeypatch.setenv("STRIPE_SANDBOX_RECONCILE_WORKER", "1")
    monkeypatch.setenv("STRIPE_SANDBOX_CHECKOUT_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_example")
    with pytest.raises(ValueError):
        worker.start_stripe_reconciliation_worker(lambda: None, interval_seconds=10)

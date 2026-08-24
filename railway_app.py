"""Railway entrypoint with booking hold cleanup and health check."""

from app import app, db
from payment_hold import init_payment_hold


init_payment_hold(app, db)


@app.get("/health")
def railway_health():
    """Return 200 when the Flask process is ready to accept requests."""
    return {"status": "ok"}, 200

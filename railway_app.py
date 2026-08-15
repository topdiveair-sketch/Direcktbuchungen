"""Railway entrypoint with a lightweight health check."""

from app import app


@app.get("/health")
def railway_health():
    """Return 200 when the Flask process is ready to accept requests."""
    return {"status": "ok"}, 200

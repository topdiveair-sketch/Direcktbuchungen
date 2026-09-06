"""ProjectOS bridge for the central Jauerling winter analytics."""

from __future__ import annotations

import hmac
import os

from flask import jsonify, request

from winter_analytics_gateway import app, _summary


def _projectos_token() -> str:
    return os.environ.get("PROJECTOS_ANALYTICS_TOKEN", "").strip()


def _projectos_authorized() -> bool:
    token = _projectos_token()
    if not token:
        return False
    supplied = request.headers.get("Authorization", "").strip()
    expected = f"Bearer {token}"
    return hmac.compare_digest(supplied, expected)


@app.get("/api/projectos/winter-performance")
def projectos_winter_performance():
    if not _projectos_token():
        return jsonify({"ok": False, "error": "projectos_analytics_token_not_configured"}), 503
    if not _projectos_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    days = request.args.get("days", default=120, type=int)
    data = _summary(days)
    return jsonify({"ok": True, **data}), 200


@app.get("/health/projectos-winter")
def projectos_winter_health():
    return {
        "ok": True,
        "configured": bool(_projectos_token()),
        "endpoint": "/api/projectos/winter-performance",
    }, 200

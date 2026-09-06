"""ProjectOS bridge for the central Jauerling winter analytics."""

from __future__ import annotations

import hashlib
import hmac
import os

from flask import jsonify, request

from winter_analytics_gateway import app, _summary

# Public repository stores only the SHA-256 of the packaged ProjectOS token.
# The actual high-entropy token is shipped only in the user's local ProjectOS package.
PACKAGED_TOKEN_SHA256 = "daab1344c9cdb902847b85105ff52e7da5d62d4a6239711e72b2bc184c885e2b"


def _projectos_token() -> str:
    return os.environ.get("PROJECTOS_ANALYTICS_TOKEN", "").strip()


def _token_matches_packaged_hash(supplied_token: str) -> bool:
    if not supplied_token or not PACKAGED_TOKEN_SHA256:
        return False
    digest = hashlib.sha256(supplied_token.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, PACKAGED_TOKEN_SHA256)


def _projectos_authorized() -> bool:
    supplied = request.headers.get("Authorization", "").strip()
    if not supplied.startswith("Bearer "):
        return False
    supplied_token = supplied[7:].strip()
    env_token = _projectos_token()
    if env_token and hmac.compare_digest(supplied_token, env_token):
        return True
    return _token_matches_packaged_hash(supplied_token)


@app.get("/api/projectos/winter-performance")
def projectos_winter_performance():
    if not _projectos_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    days = request.args.get("days", default=120, type=int)
    data = _summary(days)
    return jsonify({"ok": True, **data}), 200


@app.get("/health/projectos-winter")
def projectos_winter_health():
    return {
        "ok": True,
        "configured": bool(_projectos_token() or PACKAGED_TOKEN_SHA256),
        "authorization": "environment_or_packaged_hash",
        "endpoint": "/api/projectos/winter-performance",
    }, 200

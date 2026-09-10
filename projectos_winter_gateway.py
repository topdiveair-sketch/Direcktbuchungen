"""ProjectOS bridge for central winter, direct-booking and market-leader analytics."""

from __future__ import annotations

import hashlib
import hmac
import os

from flask import jsonify, request

from winter_analytics_gateway import app, _summary
from railway_app import db, require_admin
from direct_booking_metrics import init_direct_booking_metrics
from market_leader_metrics import init_market_leader_metrics
from market_leader_scheduler import init_market_leader_scheduler
from wachauetappe_live_gateway import init_wachauetappe_live

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


_direct_booking_summary = init_direct_booking_metrics(app, db, require_admin)
_market_leader_summary = init_market_leader_metrics(app, db, require_admin)
init_market_leader_scheduler(app, db, _market_leader_summary)
init_wachauetappe_live(app, db, require_admin)


@app.get("/api/projectos/winter-performance")
def projectos_winter_performance():
    if not _projectos_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    days = request.args.get("days", default=120, type=int)
    data = _summary(days)
    return jsonify({"ok": True, **data}), 200


@app.get("/api/projectos/direct-booking-performance")
def projectos_direct_booking_performance():
    if not _projectos_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    days = request.args.get("days", default=30, type=int)
    return jsonify({"ok": True, **_direct_booking_summary(days)}), 200


@app.get("/api/projectos/market-leader-performance")
def projectos_market_leader_performance():
    if not _projectos_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    refresh = request.args.get("refresh", "1") != "0"
    return jsonify({"ok": True, **_market_leader_summary(refresh_competitors=refresh)}), 200


@app.get("/health/projectos-winter")
def projectos_winter_health():
    return {
        "ok": True,
        "configured": bool(_projectos_token() or PACKAGED_TOKEN_SHA256),
        "authorization": "environment_or_packaged_hash",
        "endpoint": "/api/projectos/winter-performance",
        "direct_booking_endpoint": "/api/projectos/direct-booking-performance",
        "market_leader_endpoint": "/api/projectos/market-leader-performance",
        "direct_booking_metrics": bool(app.extensions.get("zab_direct_booking_metrics_initialized")),
        "market_leader_metrics": bool(app.extensions.get("zab_market_leader_metrics_initialized")),
        "market_leader_scheduler": bool(app.extensions.get("zab_market_leader_scheduler_initialized")),
        "wachauetappe_live": True,
    }, 200

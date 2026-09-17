"""Windows desktop API bridge for the rank/price monitor.

This route uses the existing Railway ADMIN_PASSWORD via X-Admin-Password.
It deliberately keeps SERP credentials server-side.
"""

from __future__ import annotations

import hmac
import os
from datetime import date, timedelta

from flask import jsonify, request

from rank_price_gateway import app, _public_benchmarks, _serp_rank, _stay_price, DEFAULT_QUERY
import app as legacy_app


def _desktop_admin_ok() -> bool:
    expected = os.environ.get("ADMIN_PASSWORD", "").strip()
    supplied = request.headers.get("X-Admin-Password", "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@app.get("/api/windows/rank-price-check")
def windows_rank_price_check():
    if not _desktop_admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    query = " ".join((request.args.get("q") or DEFAULT_QUERY).split())[:180]
    room = (request.args.get("room") or "Bachblick").strip()
    if room not in legacy_app.ROOMS:
        return jsonify({"ok": False, "error": "unknown_room"}), 400

    try:
        arrival = date.fromisoformat(request.args.get("arrival") or date.today().isoformat())
        departure = date.fromisoformat(
            request.args.get("departure") or (arrival + timedelta(days=1)).isoformat()
        )
        own = _stay_price(room, arrival, departure)
    except Exception as exc:
        return jsonify({"ok": False, "error": "invalid_input", "message": str(exc)}), 400

    return jsonify({
        "ok": True,
        "query": query,
        "rank": _serp_rank(query),
        "own_price": own,
        "public_benchmarks": _public_benchmarks(),
        "serp_live_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
        "price_rank_rule": "Nur identische Aufenthalte duerfen fuer einen exakten Preisrang verglichen werden.",
    }), 200, {"Cache-Control": "no-store"}


@app.get("/health/rank-price-windows")
def rank_price_windows_health():
    return {
        "ok": True,
        "endpoint": "/api/windows/rank-price-check",
        "auth": "X-Admin-Password",
        "serp_live_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
    }, 200

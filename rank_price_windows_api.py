"""Windows desktop API bridge for the rank/price monitor.

This route uses the existing Railway ADMIN_PASSWORD via X-Admin-Password.
It deliberately keeps SERP credentials server-side.
"""

from __future__ import annotations

import calendar
import hmac
import os
from datetime import date, timedelta

from flask import jsonify, request

from rank_price_gateway import app, _public_benchmarks, _stay_price, DEFAULT_QUERY
from competitor_serp import KEYWORDS, serp_snapshot
import app as legacy_app


WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
API_VERSION = "1.4-month-overview"


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

    serp = serp_snapshot(query)
    return jsonify({
        "ok": True,
        "api_version": API_VERSION,
        "query": query,
        "rank": serp.get("rank") or {},
        "competitor_rankings": serp.get("competitor_rankings") or [],
        "ranking_source": serp.get("source") or "",
        "provider_error": serp.get("provider_error") or "",
        "ranking_result_count": serp.get("result_count") or 0,
        "available_keywords": KEYWORDS,
        "own_price": own,
        "public_benchmarks": _public_benchmarks(),
        "serp_live_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
        "price_rank_rule": "Nur identische Aufenthalte duerfen fuer einen exakten Preisrang verglichen werden.",
    }), 200, {"Cache-Control": "no-store"}


@app.get("/api/windows/month-overview")
def windows_month_overview():
    if not _desktop_admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    room = (request.args.get("room") or "Bachblick").strip()
    if room not in legacy_app.ROOMS:
        return jsonify({"ok": False, "error": "unknown_room"}), 400

    raw_month = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    try:
        year_text, month_text = raw_month.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        if year < 2020 or year > 2100 or month < 1 or month > 12:
            raise ValueError
    except Exception:
        return jsonify({"ok": False, "error": "invalid_month", "message": "Monat muss YYYY-MM sein."}), 400

    days_in_month = calendar.monthrange(year, month)[1]
    rows = []
    numeric_prices = []
    for day_number in range(1, days_in_month + 1):
        arrival = date(year, month, day_number)
        departure = arrival + timedelta(days=1)
        try:
            stay = _stay_price(room, arrival, departure)
            total = stay.get("total_eur")
            nightly = stay.get("average_nightly_eur")
            try:
                numeric_prices.append(float(total))
            except (TypeError, ValueError):
                pass
            rows.append({
                "date": arrival.isoformat(),
                "weekday": WEEKDAYS_DE[arrival.weekday()],
                "total_eur": total,
                "average_nightly_eur": nightly,
                "nights": stay.get("nights", 1),
                "status": "ok",
                "message": "",
            })
        except Exception as exc:
            rows.append({
                "date": arrival.isoformat(),
                "weekday": WEEKDAYS_DE[arrival.weekday()],
                "total_eur": None,
                "average_nightly_eur": None,
                "nights": 1,
                "status": "unavailable",
                "message": str(exc),
            })

    summary = {
        "days": len(rows),
        "priced_days": len(numeric_prices),
        "min_eur": min(numeric_prices) if numeric_prices else None,
        "max_eur": max(numeric_prices) if numeric_prices else None,
        "average_eur": (sum(numeric_prices) / len(numeric_prices)) if numeric_prices else None,
    }
    return jsonify({
        "ok": True,
        "api_version": API_VERSION,
        "month": f"{year:04d}-{month:02d}",
        "room": room,
        "rows": rows,
        "summary": summary,
    }), 200, {"Cache-Control": "no-store"}


@app.get("/health/rank-price-windows")
def rank_price_windows_health():
    return {
        "ok": True,
        "version": API_VERSION,
        "endpoint": "/api/windows/rank-price-check",
        "month_endpoint": "/api/windows/month-overview",
        "auth": "X-Admin-Password",
        "serp_live_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
        "competitor_rankings": True,
        "month_overview": True,
    }, 200

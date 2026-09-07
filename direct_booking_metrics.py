"""Server-side KPI measurement for ZAB direct bookings.

Measures the real booking funnel without collecting guest PII:
quote -> PayPal order -> confirmed paid booking. Platform commission savings are
only calculated when an explicit comparison percentage is configured.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from flask import jsonify, redirect, request, url_for


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_host(value: str) -> str:
    try:
        return (urlsplit(value or "").hostname or "")[:160]
    except Exception:
        return ""


def _safe_page(value: str) -> str:
    try:
        parsed = urlsplit(value or "")
        path = parsed.path or "/"
        return path[:300]
    except Exception:
        return ""


def _rate(num: int, den: int):
    return round((num / den) * 100, 1) if den else None


def _commission_pct():
    raw = (
        os.environ.get("DIRECT_BOOKING_PLATFORM_COMMISSION_PCT", "").strip()
        or os.environ.get("OTA_COMMISSION_PCT", "").strip()
    )
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    if value < 0 or value > 100:
        return None
    return value


def init_direct_booking_metrics(app, db, require_admin):
    """Attach privacy-light server-side funnel logging and KPI endpoints."""
    if app.extensions.get("zab_direct_booking_metrics_initialized"):
        return app.extensions["zab_direct_booking_metrics_summary"]

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS direct_booking_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                event_key TEXT UNIQUE,
                booking_id INTEGER,
                room TEXT DEFAULT '',
                total REAL,
                page TEXT DEFAULT '',
                origin_host TEXT DEFAULT '',
                referrer_host TEXT DEFAULT '',
                details_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_direct_booking_event_created
                ON direct_booking_events(event,created_at);
            CREATE INDEX IF NOT EXISTS idx_direct_booking_booking
                ON direct_booking_events(booking_id,event);
            """
        )

    def record(event, *, event_key=None, booking_id=None, room="", total=None, details=None):
        referer = request.headers.get("Referer", "")
        origin = request.headers.get("Origin", "")
        safe_details = details if isinstance(details, dict) else {}
        safe_details = {
            str(key)[:60]: value if isinstance(value, (int, float, bool)) else str(value)[:160]
            for key, value in safe_details.items()
            if key in {"available", "status", "order_id", "currency"}
        }
        try:
            with db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO direct_booking_events
                       (event,event_key,booking_id,room,total,page,origin_host,referrer_host,details_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event,
                        event_key,
                        booking_id,
                        str(room or "")[:80],
                        total,
                        _safe_page(referer),
                        _safe_host(origin),
                        _safe_host(referer),
                        json.dumps(safe_details, ensure_ascii=False),
                        _now(),
                    ),
                )
        except Exception:
            # Measurement must never interrupt a booking or payment response.
            pass

    @app.after_request
    def measure_direct_booking_response(response):
        path = request.path
        try:
            if path == "/api/paypal/quote" and request.method == "POST":
                payload = request.get_json(silent=True) or {}
                result = response.get_json(silent=True) or {}
                record(
                    "quote_available" if response.status_code == 200 and result.get("available") else "quote_unavailable",
                    room=payload.get("room", ""),
                    total=result.get("total"),
                    details={"available": bool(result.get("available")), "status": response.status_code},
                )
            elif path == "/api/paypal/create-order" and request.method == "POST":
                payload = request.get_json(silent=True) or {}
                result = response.get_json(silent=True) or {}
                booking_id = result.get("booking_id")
                if response.status_code == 200 and result.get("ok") and booking_id:
                    record(
                        "checkout_started",
                        event_key=f"checkout:{booking_id}",
                        booking_id=int(booking_id),
                        room=payload.get("room", ""),
                        total=result.get("total"),
                        details={"order_id": result.get("order_id", ""), "status": response.status_code},
                    )
                else:
                    record(
                        "checkout_failed",
                        room=payload.get("room", ""),
                        details={"status": response.status_code},
                    )
            elif path == "/paypal/return" and request.method == "GET" and response.status_code == 200:
                booking_id = request.args.get("booking", type=int)
                if booking_id:
                    with db() as conn:
                        booking = conn.execute(
                            """SELECT id,room,total,status,paid FROM bookings WHERE id=?""",
                            (booking_id,),
                        ).fetchone()
                    if booking and booking["status"] == "confirmed" and int(booking["paid"] or 0):
                        record(
                            "booking_confirmed",
                            event_key=f"confirmed:{booking_id}",
                            booking_id=booking_id,
                            room=booking["room"],
                            total=float(booking["total"] or 0),
                            details={"status": "confirmed", "currency": "EUR"},
                        )
        except Exception:
            pass
        return response

    def summary(days=30):
        days = max(1, min(int(days or 30), 3650))
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with db() as conn:
            counts = {
                row["event"]: int(row["n"])
                for row in conn.execute(
                    """SELECT event,COUNT(*) AS n FROM direct_booking_events
                       WHERE created_at>=? GROUP BY event""",
                    (since,),
                ).fetchall()
            }
            source_rows = conn.execute(
                """SELECT COALESCE(NULLIF(referrer_host,''),'direct') AS source,
                          COUNT(*) AS events
                   FROM direct_booking_events
                   WHERE created_at>=? AND event IN ('quote_available','checkout_started','booking_confirmed')
                   GROUP BY source ORDER BY events DESC LIMIT 20""",
                (since,),
            ).fetchall()
            booking = conn.execute(
                """SELECT COUNT(*) AS bookings, COALESCE(SUM(total),0) AS revenue
                   FROM bookings
                   WHERE status='confirmed' AND COALESCE(paid,0)=1
                     AND payment_method='paypal_checkout'
                     AND COALESCE(paid_at,created_at)>=?""",
                (since,),
            ).fetchone()

        quotes = counts.get("quote_available", 0)
        checkouts = counts.get("checkout_started", 0)
        confirmed = int(booking["bookings"] or 0)
        revenue = round(float(booking["revenue"] or 0), 2)
        pct = _commission_pct()
        saved = round(revenue * pct / 100.0, 2) if pct is not None else None

        return {
            "period_days": days,
            "since": since,
            "funnel": {
                "quotes_available": quotes,
                "quotes_unavailable": counts.get("quote_unavailable", 0),
                "checkout_starts": checkouts,
                "checkout_failures": counts.get("checkout_failed", 0),
                "confirmed_paid_bookings": confirmed,
                "quote_to_checkout_pct": _rate(checkouts, quotes),
                "checkout_to_booking_pct": _rate(confirmed, checkouts),
                "quote_to_booking_pct": _rate(confirmed, quotes),
            },
            "economics": {
                "direct_revenue_eur": revenue,
                "avoided_platform_bookings": confirmed,
                "comparison_commission_pct": pct,
                "estimated_platform_commission_saved_eur": saved,
                "commission_basis": "configured_contract_rate" if pct is not None else "not_configured",
            },
            "sources": [dict(row) for row in source_rows],
        }

    @app.get("/admin/direct-booking-performance.json")
    def direct_booking_performance_json():
        if not require_admin():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(summary(request.args.get("days", default=30, type=int)))

    @app.get("/admin/direct-booking-performance")
    def direct_booking_performance():
        if not require_admin():
            return redirect(url_for("admin_login"))
        data = summary(request.args.get("days", default=30, type=int))
        f = data["funnel"]
        e = data["economics"]
        saved = "nicht konfiguriert" if e["estimated_platform_commission_saved_eur"] is None else f"{e['estimated_platform_commission_saved_eur']:.2f} EUR"
        pct = "–" if e["comparison_commission_pct"] is None else f"{e['comparison_commission_pct']:.2f} %"
        html = f"""<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Direktbuchungs-Cockpit</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f4f7f5;color:#17372f}}main{{max-width:1100px;margin:auto;padding:28px 18px 60px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:22px 0}}.kpi{{background:#fff;border:1px solid #d8e4dc;border-radius:14px;padding:18px}}.kpi strong{{display:block;font-size:28px;margin-top:5px}}.label{{font-size:12px;text-transform:uppercase;font-weight:800;color:#667a72}}.note{{padding:14px 16px;background:#fff7df;border:1px solid #ead9a6;border-radius:12px;color:#6d5717}}</style></head><body><main><h1>📈 ZAB Direktbuchungs-Cockpit</h1><p>Reale Serverstrecke: Verfügbarkeit → PayPal-Checkout → bestätigte Zahlung. Zeitraum: {data['period_days']} Tage.</p><div class='grid'><div class='kpi'><span class='label'>Verfügbare Quotes</span><strong>{f['quotes_available']}</strong></div><div class='kpi'><span class='label'>PayPal-Starts</span><strong>{f['checkout_starts']}</strong></div><div class='kpi'><span class='label'>Bezahlte Direktbuchungen</span><strong>{f['confirmed_paid_bookings']}</strong></div><div class='kpi'><span class='label'>Checkout → Buchung</span><strong>{f['checkout_to_booking_pct'] if f['checkout_to_booking_pct'] is not None else '–'} %</strong></div><div class='kpi'><span class='label'>Direktumsatz</span><strong>{e['direct_revenue_eur']:.2f} EUR</strong></div><div class='kpi'><span class='label'>Vergleichsprovision</span><strong>{pct}</strong></div><div class='kpi'><span class='label'>Geschätzte Provision gespart</span><strong>{saved}</strong></div></div><p class='note'>Der Provisions-Eurobetrag wird nur berechnet, wenn DIRECT_BOOKING_PLATFORM_COMMISSION_PCT (oder OTA_COMMISSION_PCT) mit dem tatsächlichen Vergleichssatz gesetzt ist. Ohne Vertragssatz wird keine Ersparnis behauptet.</p></main></body></html>"""
        return html, 200

    app.extensions["zab_direct_booking_metrics_initialized"] = True
    app.extensions["zab_direct_booking_metrics_summary"] = summary
    return summary

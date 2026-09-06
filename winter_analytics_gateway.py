"""Central, privacy-light analytics for the Jauerling winter campaign."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from flask import Response, jsonify, redirect, request, url_for

from growth_action_gateway import app, db
from railway_app import require_admin

CAMPAIGN = "winter_jauerling_2026_27"
ALLOWED_EVENTS = {
    "winter_promo_impression",
    "winter_landingpage_view",
    "winter_landingpage_click",
    "winter_booking_cta_click",
    "winter_return_to_booking",
    "direct_inquiry_sent",
    "direct_paypal_checkout_started",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _cors_headers() -> dict[str, str]:
    origin = request.headers.get("Origin", "")
    allowed = origin.startswith("https://topdiveair-sketch.github.io") or origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
    return {
        "Access-Control-Allow-Origin": origin if allowed else "https://topdiveair-sketch.github.io",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
        "Cache-Control": "no-store",
    }


def _json(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    for key, value in _cors_headers().items():
        response.headers[key] = value
    return response


def _init_table() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS winter_campaign_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign TEXT NOT NULL,
                event TEXT NOT NULL,
                visitor_id TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                page TEXT DEFAULT '',
                source TEXT DEFAULT '',
                medium TEXT DEFAULT '',
                referrer_host TEXT DEFAULT '',
                details_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_winter_campaign_event_created
                ON winter_campaign_events(campaign,event,created_at);
            CREATE INDEX IF NOT EXISTS idx_winter_campaign_visitor
                ON winter_campaign_events(campaign,visitor_id);
            """
        )


_init_table()


@app.route("/api/analytics/winter-event", methods=["POST", "OPTIONS"])
def winter_event():
    if request.method == "OPTIONS":
        return Response(status=204, headers=_cors_headers())

    payload = request.get_json(silent=True) or {}
    campaign = str(payload.get("campaign") or "").strip()[:80]
    event = str(payload.get("event") or "").strip()[:80]
    if campaign != CAMPAIGN or event not in ALLOWED_EVENTS:
        return _json({"ok": False, "error": "invalid_event"}, 400)

    visitor_id = str(payload.get("visitor_id") or "").strip()[:80]
    session_id = str(payload.get("session_id") or "").strip()[:80]
    page = str(payload.get("page") or "").strip()[:300]
    source = str(payload.get("source") or "").strip()[:80]
    medium = str(payload.get("medium") or "").strip()[:80]
    referrer_host = str(payload.get("referrer_host") or "").strip()[:160]
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

    # Keep the collector intentionally free of names, emails, phone numbers and IPs.
    safe_details = {}
    for key in ("inquiry_id", "booking_id", "order_id", "total", "room", "adults", "nights"):
        if key in details:
            value = details.get(key)
            safe_details[key] = value if isinstance(value, (int, float)) else str(value)[:120]

    with db() as conn:
        conn.execute(
            """INSERT INTO winter_campaign_events
               (campaign,event,visitor_id,session_id,page,source,medium,referrer_host,details_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                campaign,
                event,
                visitor_id,
                session_id,
                page,
                source,
                medium,
                referrer_host,
                json.dumps(safe_details, ensure_ascii=False),
                _now(),
            ),
        )
    return _json({"ok": True}, 201)


def _summary(days: int = 120) -> dict:
    since = (datetime.now() - timedelta(days=max(1, min(days, 365)))).isoformat(timespec="seconds")
    with db() as conn:
        rows = conn.execute(
            """SELECT event, COUNT(*) AS events, COUNT(DISTINCT NULLIF(visitor_id,'')) AS visitors
               FROM winter_campaign_events
               WHERE campaign=? AND created_at>=?
               GROUP BY event""",
            (CAMPAIGN, since),
        ).fetchall()
        sources = conn.execute(
            """SELECT COALESCE(NULLIF(source,''),'direct') AS source,
                      COALESCE(NULLIF(medium,''),'unknown') AS medium,
                      COUNT(*) AS events,
                      COUNT(DISTINCT NULLIF(visitor_id,'')) AS visitors
               FROM winter_campaign_events
               WHERE campaign=? AND created_at>=?
               GROUP BY source,medium
               ORDER BY events DESC LIMIT 20""",
            (CAMPAIGN, since),
        ).fetchall()
        daily = conn.execute(
            """SELECT substr(created_at,1,10) AS day,
                      SUM(CASE WHEN event='winter_promo_impression' THEN 1 ELSE 0 END) AS impressions,
                      SUM(CASE WHEN event='winter_landingpage_click' THEN 1 ELSE 0 END) AS landing_clicks,
                      SUM(CASE WHEN event='winter_booking_cta_click' THEN 1 ELSE 0 END) AS booking_clicks,
                      SUM(CASE WHEN event='direct_inquiry_sent' THEN 1 ELSE 0 END) AS inquiries,
                      SUM(CASE WHEN event='direct_paypal_checkout_started' THEN 1 ELSE 0 END) AS paypal_starts
               FROM winter_campaign_events
               WHERE campaign=? AND created_at>=?
               GROUP BY day ORDER BY day DESC LIMIT 60""",
            (CAMPAIGN, since),
        ).fetchall()

    by_event = {row["event"]: {"events": int(row["events"]), "visitors": int(row["visitors"] or 0)} for row in rows}
    impressions = by_event.get("winter_promo_impression", {}).get("visitors", 0)
    landing = by_event.get("winter_landingpage_click", {}).get("visitors", 0)
    booking = by_event.get("winter_booking_cta_click", {}).get("visitors", 0)
    inquiries = by_event.get("direct_inquiry_sent", {}).get("visitors", 0)
    paypal = by_event.get("direct_paypal_checkout_started", {}).get("visitors", 0)

    def rate(num: int, den: int):
        return round((num / den) * 100, 1) if den else None

    return {
        "campaign": CAMPAIGN,
        "since": since,
        "events": by_event,
        "funnel": {
            "promo_visitors": impressions,
            "landing_click_visitors": landing,
            "booking_cta_visitors": booking,
            "inquiry_visitors": inquiries,
            "paypal_start_visitors": paypal,
            "promo_to_landing_pct": rate(landing, impressions),
            "landing_to_booking_pct": rate(booking, landing),
            "booking_to_inquiry_pct": rate(inquiries, booking),
            "booking_to_paypal_pct": rate(paypal, booking),
        },
        "sources": [dict(row) for row in sources],
        "daily": [dict(row) for row in daily],
    }


@app.get("/admin/winter-performance.json")
def winter_performance_json():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(_summary(request.args.get("days", default=120, type=int)))


@app.get("/admin/winter-performance")
def winter_performance():
    if not require_admin():
        return redirect(url_for("admin_login"))
    data = _summary(request.args.get("days", default=120, type=int))
    f = data["funnel"]

    def value(v):
        return "–" if v is None else str(v)

    source_rows = "".join(
        f"<tr><td>{row['source']}</td><td>{row['medium']}</td><td>{row['visitors']}</td><td>{row['events']}</td></tr>"
        for row in data["sources"]
    ) or "<tr><td colspan='4'>Noch keine Daten.</td></tr>"
    daily_rows = "".join(
        f"<tr><td>{row['day']}</td><td>{row['impressions']}</td><td>{row['landing_clicks']}</td><td>{row['booking_clicks']}</td><td>{row['inquiries']}</td><td>{row['paypal_starts']}</td></tr>"
        for row in data["daily"]
    ) or "<tr><td colspan='6'>Noch keine Daten.</td></tr>"

    html = f"""<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Winter-Umsatz-Cockpit</title><style>
    body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f4f7f8;color:#17313d}}main{{max-width:1180px;margin:auto;padding:28px 18px 60px}}h1{{margin-bottom:4px}}.sub{{color:#61727a;margin-top:0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:22px 0}}.kpi{{background:#fff;border:1px solid #d9e3e7;border-radius:14px;padding:18px}}.kpi strong{{display:block;font-size:29px;margin-top:5px}}.label{{font-size:12px;text-transform:uppercase;font-weight:800;color:#667981}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d9e3e7;border-radius:14px;overflow:hidden;margin:10px 0 26px}}th,td{{padding:11px 12px;border-bottom:1px solid #e7edef;text-align:left}}th{{background:#edf4f6;font-size:12px;text-transform:uppercase}}.note{{padding:14px 16px;background:#fff7df;border:1px solid #ead9a6;border-radius:12px;color:#6d5717}}</style></head><body><main><h1>❄️ Winter-Umsatz-Cockpit</h1><p class='sub'>Jauerling-Kampagne 2026/27 · zentrale Website-Messung ohne personenbezogene Gästedaten.</p>
    <div class='grid'>
      <div class='kpi'><span class='label'>Promo-Besucher</span><strong>{f['promo_visitors']}</strong></div>
      <div class='kpi'><span class='label'>Landingpage-Klicks</span><strong>{f['landing_click_visitors']}</strong></div>
      <div class='kpi'><span class='label'>Buchungs-CTA</span><strong>{f['booking_cta_visitors']}</strong></div>
      <div class='kpi'><span class='label'>Anfragen</span><strong>{f['inquiry_visitors']}</strong></div>
      <div class='kpi'><span class='label'>PayPal-Starts</span><strong>{f['paypal_start_visitors']}</strong></div>
    </div>
    <div class='grid'>
      <div class='kpi'><span class='label'>Promo → Landingpage</span><strong>{value(f['promo_to_landing_pct'])}%</strong></div>
      <div class='kpi'><span class='label'>Landingpage → Buchung</span><strong>{value(f['landing_to_booking_pct'])}%</strong></div>
      <div class='kpi'><span class='label'>Buchung → Anfrage</span><strong>{value(f['booking_to_inquiry_pct'])}%</strong></div>
      <div class='kpi'><span class='label'>Buchung → PayPal</span><strong>{value(f['booking_to_paypal_pct'])}%</strong></div>
    </div>
    <p class='note'><strong>Wirtschaftlich wichtig:</strong> Dieses Cockpit misst den Winter-Funnel. Tatsächlicher Umsatz gilt erst dann als belastbar, wenn eine Anfrage bzw. PayPal-Buchung bestätigt und bezahlt wurde. Klicks werden nicht als Umsatz ausgegeben.</p>
    <h2>Quellen</h2><table><thead><tr><th>Quelle</th><th>Medium</th><th>Besucher</th><th>Ereignisse</th></tr></thead><tbody>{source_rows}</tbody></table>
    <h2>Verlauf</h2><table><thead><tr><th>Tag</th><th>Promo</th><th>Landing</th><th>Buchung</th><th>Anfragen</th><th>PayPal</th></tr></thead><tbody>{daily_rows}</tbody></table>
    </main></body></html>"""
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/health/winter-analytics")
def winter_analytics_health():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM winter_campaign_events WHERE campaign=?", (CAMPAIGN,)).fetchone()["n"]
    return {"ok": True, "campaign": CAMPAIGN, "events": int(total or 0)}, 200

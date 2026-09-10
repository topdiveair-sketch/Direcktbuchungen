"""Privacy-light demand and conversion analytics for Zuhause am Bach OS.

Tracks anonymous funnel events from the public booking page and combines them
with confirmed bookings from the local booking database. No names, email
addresses, phone numbers, message text, IP addresses or user agents are stored.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from flask import jsonify, redirect, request, url_for

PUBLIC_ORIGIN = "https://topdiveair-sketch.github.io"
ALLOWED_EVENTS = {
    "page_view",
    "booking_cta_click",
    "dates_selected",
    "price_quote_loaded",
    "request_prepared",
    "email_click",
    "whatsapp_click",
    "copy_request_click",
}
ALLOWED_DETAIL_KEYS = {
    "arrival", "departure", "nights", "total", "language", "cta", "room"
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_host(value: str) -> str:
    try:
        return (urlsplit(value or "").hostname or "")[:160]
    except Exception:
        return ""


def _safe_path(value: str) -> str:
    try:
        return (urlsplit(value or "").path or "/")[:240]
    except Exception:
        return "/"


def _pct(num: int, den: int):
    return round(num * 100.0 / den, 1) if den else None


def init_demand_analytics(app, db, require_admin):
    if app.extensions.get("zab_demand_analytics_initialized"):
        return

    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS demand_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            page TEXT NOT NULL DEFAULT '/',
            referrer_host TEXT NOT NULL DEFAULT '',
            room TEXT NOT NULL DEFAULT '',
            arrival TEXT NOT NULL DEFAULT '',
            departure TEXT NOT NULL DEFAULT '',
            nights INTEGER,
            total REAL,
            cta TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_demand_events_created
            ON demand_events(created_at,event);
        CREATE INDEX IF NOT EXISTS idx_demand_events_arrival
            ON demand_events(arrival,event);
        """)

    def cors(response):
        response.headers["Access-Control-Allow-Origin"] = PUBLIC_ORIGIN
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/demand-event", methods=["POST", "OPTIONS"])
    def demand_event():
        if request.method == "OPTIONS":
            return cors(app.make_response(("", 204)))
        origin = request.headers.get("Origin", "")
        if origin and origin != PUBLIC_ORIGIN:
            return cors(jsonify({"ok": False, "error": "origin_not_allowed"})), 403
        payload = request.get_json(silent=True) or {}
        event = str(payload.get("event", ""))[:40]
        if event not in ALLOWED_EVENTS:
            return cors(jsonify({"ok": False, "error": "invalid_event"})), 400
        raw = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        details = {k: raw.get(k) for k in ALLOWED_DETAIL_KEYS if k in raw}
        arrival = str(details.get("arrival") or "")[:10]
        departure = str(details.get("departure") or "")[:10]
        try:
            nights = int(details.get("nights")) if details.get("nights") is not None else None
        except (TypeError, ValueError):
            nights = None
        nights = nights if nights is None or 0 <= nights <= 30 else None
        try:
            total = float(details.get("total")) if details.get("total") is not None else None
        except (TypeError, ValueError):
            total = None
        if total is not None and not 0 <= total <= 10000:
            total = None
        try:
            with db() as conn:
                conn.execute(
                    """INSERT INTO demand_events
                       (event,page,referrer_host,room,arrival,departure,nights,total,cta,language,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event,
                        _safe_path(request.headers.get("Referer", "")),
                        _safe_host(request.headers.get("Referer", "")),
                        str(details.get("room") or "")[:60],
                        arrival,
                        departure,
                        nights,
                        total,
                        str(details.get("cta") or "")[:80],
                        str(details.get("language") or "")[:12],
                        _now(),
                    ),
                )
        except Exception:
            return cors(jsonify({"ok": False, "error": "storage_failed"})), 503
        return cors(jsonify({"ok": True}))

    def summary(days: int = 30):
        days = max(1, min(int(days or 30), 3650))
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with db() as conn:
            counts = {
                r["event"]: int(r["n"])
                for r in conn.execute(
                    "SELECT event,COUNT(*) n FROM demand_events WHERE created_at>=? GROUP BY event",
                    (since,),
                ).fetchall()
            }
            demand_dates = [dict(r) for r in conn.execute(
                """SELECT arrival,COUNT(*) interest,
                          ROUND(AVG(COALESCE(nights,0)),1) avg_nights,
                          ROUND(AVG(COALESCE(total,0)),2) avg_quote
                   FROM demand_events
                   WHERE created_at>=? AND event IN ('dates_selected','price_quote_loaded')
                     AND arrival!=''
                   GROUP BY arrival ORDER BY interest DESC,arrival LIMIT 12""",
                (since,),
            ).fetchall()]
            months = [dict(r) for r in conn.execute(
                """SELECT substr(arrival,1,7) month,COUNT(*) interest
                   FROM demand_events
                   WHERE created_at>=? AND event IN ('dates_selected','price_quote_loaded')
                     AND length(arrival)>=7
                   GROUP BY substr(arrival,1,7) ORDER BY interest DESC,month LIMIT 12""",
                (since,),
            ).fetchall()]
            sources = [dict(r) for r in conn.execute(
                """SELECT COALESCE(NULLIF(referrer_host,''),'direkt') source,COUNT(*) events
                   FROM demand_events WHERE created_at>=?
                   GROUP BY source ORDER BY events DESC LIMIT 10""",
                (since,),
            ).fetchall()]
            confirmed = conn.execute(
                """SELECT COUNT(*) bookings,COALESCE(SUM(total),0) revenue
                   FROM bookings WHERE status='confirmed' AND created_at>=?""",
                (since,),
            ).fetchone()
        views = counts.get("page_view", 0)
        ctas = counts.get("booking_cta_click", 0)
        quotes = counts.get("price_quote_loaded", 0)
        requests = counts.get("request_prepared", 0)
        bookings = int(confirmed["bookings"] or 0)
        return {
            "days": days,
            "views": views,
            "cta_clicks": ctas,
            "dates_selected": counts.get("dates_selected", 0),
            "price_quotes": quotes,
            "requests": requests,
            "email_clicks": counts.get("email_click", 0),
            "whatsapp_clicks": counts.get("whatsapp_click", 0),
            "confirmed_bookings": bookings,
            "confirmed_revenue": round(float(confirmed["revenue"] or 0), 2),
            "view_to_cta_pct": _pct(ctas, views),
            "quote_to_request_pct": _pct(requests, quotes),
            "request_to_booking_pct": _pct(bookings, requests),
            "view_to_booking_pct": _pct(bookings, views),
            "top_dates": demand_dates,
            "top_months": months,
            "sources": sources,
        }

    @app.get("/os/nachfrage.json")
    def demand_json():
        if not require_admin():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(summary(request.args.get("days", default=30, type=int)))

    @app.get("/os/nachfrage")
    def demand_dashboard():
        if not require_admin():
            return redirect(url_for("admin_login"))
        d = summary(request.args.get("days", default=30, type=int))
        pct = lambda v: "–" if v is None else f"{v:.1f} %"
        cards = [
            ("Seitenaufrufe", d["views"]), ("Buchungs-CTA-Klicks", d["cta_clicks"]),
            ("Preisabfragen", d["price_quotes"]), ("Vorbereitete Anfragen", d["requests"]),
            ("E-Mail-Klicks", d["email_clicks"]), ("WhatsApp-Klicks", d["whatsapp_clicks"]),
            ("Bestätigte Buchungen", d["confirmed_bookings"]),
            ("Bestätigter Umsatz", f"{d['confirmed_revenue']:.2f} EUR"),
        ]
        card_html = "".join(f"<article><span>{k}</span><strong>{v}</strong></article>" for k,v in cards)
        dates = "".join(f"<tr><td>{r['arrival']}</td><td>{r['interest']}</td><td>{r['avg_nights']}</td><td>{r['avg_quote']:.2f} EUR</td></tr>" for r in d["top_dates"]) or "<tr><td colspan='4'>Noch keine Nachfrage-Daten.</td></tr>"
        months = "".join(f"<tr><td>{r['month']}</td><td>{r['interest']}</td></tr>" for r in d["top_months"]) or "<tr><td colspan='2'>Noch keine Daten.</td></tr>"
        html = f"""<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>ZAB OS – Nachfrage & Buchungen</title><style>body{{font-family:system-ui;margin:0;background:#f4f7f5;color:#17372f}}main{{max-width:1180px;margin:auto;padding:28px 18px 60px}}a{{color:#176b5a}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}article,section{{background:#fff;border:1px solid #d8e4dc;border-radius:14px;padding:16px}}article span{{display:block;font-size:12px;font-weight:800;text-transform:uppercase;color:#647970}}article strong{{font-size:26px}}section{{margin-top:18px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #e5ece8;text-align:left}}.conv{{display:flex;gap:18px;flex-wrap:wrap}}</style></head><body><main><p><a href='/os'>← Zuhause am Bach OS</a></p><h1>📈 Nachfrage & Direktbuchungen</h1><p>Datenschutzarme First-Party-Statistik · letzte {d['days']} Tage. Keine Namen, E-Mails, Telefonnummern oder Nachrichtentexte werden für diese Klickstatistik gespeichert.</p><div class='grid'>{card_html}</div><section><h2>Conversion</h2><div class='conv'><b>Ansicht → CTA: {pct(d['view_to_cta_pct'])}</b><b>Preis → Anfrage: {pct(d['quote_to_request_pct'])}</b><b>Anfrage → bestätigte Buchung: {pct(d['request_to_booking_pct'])}</b><b>Ansicht → Buchung: {pct(d['view_to_booking_pct'])}</b></div></section><section><h2>Stärkste Reisedaten</h2><table><tr><th>Anreise</th><th>Interesse</th><th>Ø Nächte</th><th>Ø Quote</th></tr>{dates}</table></section><section><h2>Nachfrage nach Monat</h2><table><tr><th>Monat</th><th>Interesse</th></tr>{months}</table></section></main></body></html>"""
        return html, 200

    app.extensions["zab_demand_analytics_initialized"] = True
    app.extensions["zab_demand_analytics_summary"] = summary

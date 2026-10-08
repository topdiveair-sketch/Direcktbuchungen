"""Privacy-light demand and conversion analytics for Zuhause am Bach OS.

Tracks anonymous funnel events from the public booking page and combines them
with confirmed bookings from the local booking database. No names, email
addresses, phone numbers, message text, IP addresses or user agents are stored.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from flask import jsonify, redirect, request, url_for

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

PUBLIC_ORIGINS = {
    "https://topdiveair-sketch.github.io",
    "https://www.zuhauseambach-wachau.at",
    "https://zuhauseambach-wachau.at",
    "https://direcktbuchungen-production.up.railway.app",
}
ALLOWED_EVENTS = {
    "page_view",
    "booking_cta_click",
    "dates_selected",
    "price_quote_loaded",
    "request_prepared",
    "email_click",
    "whatsapp_click",
    "copy_request_click",
    "checkout_started",
    "booking_abandoned",
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


def _analytics_database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _pg_connect():
    url = _analytics_database_url()
    if not url:
        return None
    if psycopg is None:
        raise RuntimeError("DATABASE_URL ist gesetzt, aber psycopg ist nicht installiert.")
    return psycopg.connect(url, row_factory=dict_row)


def _init_event_store(db):
    """Use Postgres for persistent demand events when DATABASE_URL is configured."""
    pg = _pg_connect()
    if pg is not None:
        with pg:
            with pg.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS demand_events(
                        id BIGSERIAL PRIMARY KEY,
                        event TEXT NOT NULL,
                        page TEXT NOT NULL DEFAULT '/',
                        referrer_host TEXT NOT NULL DEFAULT '',
                        room TEXT NOT NULL DEFAULT '',
                        arrival TEXT NOT NULL DEFAULT '',
                        departure TEXT NOT NULL DEFAULT '',
                        nights INTEGER,
                        total DOUBLE PRECISION,
                        cta TEXT NOT NULL DEFAULT '',
                        language TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        visitor_hash TEXT NOT NULL DEFAULT '',
                        country_code TEXT NOT NULL DEFAULT 'XX',
                        local_date TEXT NOT NULL DEFAULT '',
                        local_weekday INTEGER NOT NULL DEFAULT 0,
                        local_hour INTEGER NOT NULL DEFAULT 0
                    )
                """)
                for ddl in (
                    "ALTER TABLE demand_events ADD COLUMN IF NOT EXISTS visitor_hash TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE demand_events ADD COLUMN IF NOT EXISTS country_code TEXT NOT NULL DEFAULT 'XX'",
                    "ALTER TABLE demand_events ADD COLUMN IF NOT EXISTS local_date TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE demand_events ADD COLUMN IF NOT EXISTS local_weekday INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE demand_events ADD COLUMN IF NOT EXISTS local_hour INTEGER NOT NULL DEFAULT 0",
                ):
                    cur.execute(ddl)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_demand_events_created "
                    "ON demand_events(created_at,event)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_demand_events_arrival "
                    "ON demand_events(arrival,event)"
                )
        pg.close()
        return "postgres"

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
            created_at TEXT NOT NULL,
            visitor_hash TEXT NOT NULL DEFAULT '',
            country_code TEXT NOT NULL DEFAULT 'XX',
            local_date TEXT NOT NULL DEFAULT '',
            local_weekday INTEGER NOT NULL DEFAULT 0,
            local_hour INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_demand_events_created
            ON demand_events(created_at,event);
        CREATE INDEX IF NOT EXISTS idx_demand_events_arrival
            ON demand_events(arrival,event);
        """)
    return "sqlite"


def _insert_event(db, values):
    pg = _pg_connect()
    if pg is not None:
        with pg:
            with pg.cursor() as cur:
                cur.execute(
                    """INSERT INTO demand_events
                       (event,page,referrer_host,room,arrival,departure,nights,total,cta,language,created_at,
                        visitor_hash,country_code,local_date,local_weekday,local_hour)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    values,
                )
        pg.close()
        return
    with db() as conn:
        conn.execute(
            """INSERT INTO demand_events
               (event,page,referrer_host,room,arrival,departure,nights,total,cta,language,created_at,
                visitor_hash,country_code,local_date,local_weekday,local_hour)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )


def _event_summary(db, since: str):
    pg = _pg_connect()
    if pg is not None:
        with pg:
            with pg.cursor() as cur:
                cur.execute(
                    "SELECT event,COUNT(*) n FROM demand_events WHERE created_at>=%s GROUP BY event",
                    (since,),
                )
                counts = {r["event"]: int(r["n"]) for r in cur.fetchall()}
                cur.execute(
                    """SELECT arrival,COUNT(*) interest,
                              ROUND(AVG(COALESCE(nights,0))::numeric,1) avg_nights,
                              ROUND(AVG(COALESCE(total,0))::numeric,2) avg_quote
                       FROM demand_events
                       WHERE created_at>=%s AND event IN ('dates_selected','price_quote_loaded')
                         AND arrival!=''
                       GROUP BY arrival ORDER BY interest DESC,arrival LIMIT 12""",
                    (since,),
                )
                demand_dates = list(cur.fetchall())
                cur.execute(
                    """SELECT substr(arrival,1,7) month,COUNT(*) interest
                       FROM demand_events
                       WHERE created_at>=%s AND event IN ('dates_selected','price_quote_loaded')
                         AND length(arrival)>=7
                       GROUP BY substr(arrival,1,7) ORDER BY interest DESC,month LIMIT 12""",
                    (since,),
                )
                months = list(cur.fetchall())
                cur.execute(
                    """SELECT COALESCE(NULLIF(referrer_host,''),'direkt') source,COUNT(*) events
                       FROM demand_events WHERE created_at>=%s
                       GROUP BY source ORDER BY events DESC LIMIT 10""",
                    (since,),
                )
                sources = list(cur.fetchall())
        pg.close()
        return counts, demand_dates, months, sources

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
    return counts, demand_dates, months, sources


def _country_code() -> str:
    for header in ("CF-IPCountry","CloudFront-Viewer-Country","X-Country-Code","X-Geo-Country","X-Vercel-IP-Country"):
        value = (request.headers.get(header) or "").strip().upper()
        if len(value) == 2 and value.isalpha():
            return value
    return "XX"


def _visitor_hash(app) -> str:
    remote = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    agent = request.headers.get("User-Agent", "")[:200]
    salt = app.secret_key or "zab-demand"
    return hashlib.sha256(f"{salt}|{remote}|{agent}".encode("utf-8")).hexdigest()


def _local_parts():
    try:
        now = datetime.now(ZoneInfo("Europe/Vienna"))
    except Exception:
        now = datetime.now()
    return now.date().isoformat(), int(now.weekday()), int(now.hour)


def _persistent_day_checks(target_day: str) -> int:
    """Distinct visitors whose selected stay includes target_day."""
    target_day = str(target_day or "")[:10]
    if len(target_day) != 10:
        return 0
    pg = _pg_connect()
    if pg is None:
        return 0
    try:
        with pg:
            with pg.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(DISTINCT visitor_hash) AS n
                       FROM demand_events
                       WHERE event='dates_selected'
                         AND visitor_hash!=''
                         AND arrival<=%s
                         AND departure>%s""",
                    (target_day, target_day),
                )
                row = cur.fetchone()
                return int((row or {}).get("n") or 0)
    finally:
        pg.close()


def init_demand_analytics(app, db, require_admin):
    if app.extensions.get("zab_demand_analytics_initialized"):
        return

    event_store = _init_event_store(db)
    app.extensions["zab_demand_analytics_store"] = event_store

    def cors(response):
        origin = request.headers.get("Origin", "")
        response.headers["Access-Control-Allow-Origin"] = origin if origin in PUBLIC_ORIGINS else "https://www.zuhauseambach-wachau.at"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/demand-event", methods=["POST", "OPTIONS"])
    def demand_event():
        if request.method == "OPTIONS":
            return cors(app.make_response(("", 204)))
        origin = request.headers.get("Origin", "")
        if origin and origin not in PUBLIC_ORIGINS:
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
            _insert_event(
                db,
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
                    _visitor_hash(app),
                    _country_code(),
                    *_local_parts(),
                ),
            )
        except Exception:
            return cors(jsonify({"ok": False, "error": "storage_failed"})), 503
        return cors(jsonify({"ok": True}))

    def summary(days: int = 30):
        days = max(1, min(int(days or 30), 3650))
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        counts, demand_dates, months, sources = _event_summary(db, since)
        with db() as conn:
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

    @app.get("/api/public/demand-stats")
    def public_demand_stats():
        """Privacy-safe aggregated funnel statistics for the local ZAB OS.

        This endpoint intentionally exposes no names, email addresses, phone
        numbers, messages, raw IP addresses or user agents.
        """
        try:
            days = max(1, min(730, int(request.args.get("days", "30"))))
        except Exception:
            days = 30
        payload = os_summary(days)
        if payload is None:
            # Fall back to the local event store summary when Postgres is absent.
            since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
            counts, _dates, _months, _sources = _event_summary(db, since)
            attempts = int(counts.get("checkout_started", 0))
            abandoned = int(counts.get("booking_abandoned", 0))
            payload = {
                "ok": True,
                "period_days": days,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "total_searches": int(counts.get("dates_selected", 0)),
                "unique_visitors": 0,
                "search_unique_visitors": 0,
                "available_searches": int(counts.get("price_quote_loaded", 0)),
                "available_percent": 0.0,
                "booking_attempts": attempts,
                "booking_abandoned": abandoned,
                "abandonment_rate": round(100.0 * abandoned / attempts, 1) if attempts else 0.0,
                "by_visitor_country": [],
                "by_month": [],
                "by_country": [],
                "by_weekday": [],
                "by_hour": [],
                "by_date": [],
                "privacy": "Aggregated only; no personal data is exposed.",
            }
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response

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
    def os_summary(days: int = 30):
        days = max(1, min(int(days or 30), 730))
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        pg = _pg_connect()
        if pg is None:
            return None
        with pg:
            with pg.cursor() as cur:
                cur.execute("""SELECT event,arrival,departure,visitor_hash,country_code,local_date,local_weekday,local_hour,created_at
                               FROM demand_events WHERE created_at >= %s ORDER BY created_at""", (since,))
                rows = list(cur.fetchall())
        pg.close()
        searches = [r for r in rows if r["event"] == "dates_selected" and r["arrival"] and r["departure"]]
        page_views = [r for r in rows if r["event"] == "page_view"]
        checkout_starts = [r for r in rows if r["event"] == "checkout_started"]
        checkout_abandoned = [r for r in rows if r["event"] == "booking_abandoned"]
        total = len(searches)
        visitors = {r["visitor_hash"] for r in searches if r["visitor_hash"]}
        page_visitors = {r["visitor_hash"] for r in page_views if r["visitor_hash"]}
        def pct(n):
            return round(100.0*n/total,1) if total else 0.0
        country_counts={}
        weekday_counts={i:0 for i in range(7)}
        hour_counts={i:0 for i in range(24)}
        date_counts={}
        month_searches={}
        month_visitors={}
        for r in searches:
            cc=(r["country_code"] or "XX").upper()
            country_counts[cc]=country_counts.get(cc,0)+1
            wd=int(r["local_weekday"] or 0); hr=int(r["local_hour"] or 0)
            weekday_counts[wd]=weekday_counts.get(wd,0)+1
            hour_counts[hr]=hour_counts.get(hr,0)+1
            day=str(r["local_date"] or "")
            if day: date_counts[day]=date_counts.get(day,0)+1
            month=str(r["arrival"] or "")[:7]
            if month:
                month_searches[month]=month_searches.get(month,0)+1
                if r["visitor_hash"]: month_visitors.setdefault(month,set()).add(r["visitor_hash"])
        weekday_names=["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
        month_attempts={}
        month_abandoned={}
        for r in checkout_starts:
            m=str(r["arrival"] or "")[:7]
            if m:
                month_attempts[m]=month_attempts.get(m,0)+1
        for r in checkout_abandoned:
            m=str(r["arrival"] or "")[:7]
            if m:
                month_abandoned[m]=month_abandoned.get(m,0)+1
        all_months=sorted(set(month_searches) | set(month_attempts) | set(month_abandoned))
        by_month=[]
        for m in all_months:
            n=month_searches.get(m,0)
            attempts_m=month_attempts.get(m,0)
            abandoned_m=month_abandoned.get(m,0)
            by_month.append({
                "month":m,
                "unique_visitors":len(month_visitors.get(m,set())),
                "total_searches":n,
                "booking_attempts":attempts_m,
                "booking_abandoned":abandoned_m,
                "abandonment_rate":round(100.0*abandoned_m/attempts_m,1) if attempts_m else 0.0,
                "by_visitor_country":[],
                "by_weekday":[],
                "by_hour":[],
            })
        attempts=len(checkout_starts); abandoned=len(checkout_abandoned)
        return {
            "ok":True,
            "period_days":days,
            "generated_at":datetime.now().isoformat(timespec="seconds"),
            "total_searches":total,
            "unique_visitors":len(page_visitors) if page_visitors else len(visitors),
            "search_unique_visitors":len(visitors),
            "available_searches":sum(1 for r in rows if r["event"]=="price_quote_loaded"),
            "available_percent":pct(sum(1 for r in rows if r["event"]=="price_quote_loaded")),
            "booking_attempts":attempts,
            "booking_abandoned":abandoned,
            "abandonment_rate":round(100.0*abandoned/attempts,1) if attempts else 0.0,
            "by_visitor_country":[{"country_code":cc,"visitors":n,"percent":pct(n)} for cc,n in sorted(country_counts.items(),key=lambda x:(-x[1],x[0]))],
            "by_month":by_month,
            "by_country":[{"country_code":cc,"searches":n,"percent":pct(n)} for cc,n in sorted(country_counts.items(),key=lambda x:(-x[1],x[0]))],
            "by_weekday":[{"weekday":weekday_names[i],"weekday_index":i,"searches":weekday_counts[i],"percent":pct(weekday_counts[i])} for i in range(7)],
            "by_hour":[{"hour":i,"label":f"{i:02d}:00","searches":hour_counts[i],"percent":pct(hour_counts[i])} for i in range(24)],
            "by_date":[{"date":d,"searches":n,"percent":pct(n)} for d,n in sorted(date_counts.items())],
            "privacy":"Aggregated only; no raw IP address or user-agent is exposed.",
        }

    app.extensions["zab_demand_analytics_os_summary"] = os_summary
    app.extensions["zab_demand_analytics_day_checks"] = _persistent_day_checks

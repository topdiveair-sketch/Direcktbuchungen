"""Operations and commercial dashboard for WachauEtappe."""
from __future__ import annotations

from datetime import datetime, timedelta
from flask import jsonify, request


def init_wachauetappe_operations(app, db, require_admin):
    if app.extensions.get("wachauetappe_operations_initialized"):
        return
    app.extensions["wachauetappe_operations_initialized"]=True

    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS wachauetappe_funnel_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event TEXT NOT NULL,
          route TEXT DEFAULT '',
          nights INTEGER,
          luggage INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_we_funnel_created ON wachauetappe_funnel_events(created_at,event);
        CREATE TABLE IF NOT EXISTS wachauetappe_partner_leads(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          business_name TEXT NOT NULL,
          contact_name TEXT NOT NULL,
          email TEXT NOT NULL,
          phone TEXT DEFAULT '',
          location TEXT NOT NULL,
          rooms TEXT DEFAULT '',
          website TEXT DEFAULT '',
          source TEXT DEFAULT '',
          message TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new',
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_we_partner_leads_created ON wachauetappe_partner_leads(created_at,status);
        """)

    allowed={"planner_view","trip_planned","host_selected","trip_request_started","trip_request_submitted","my_trip_opened"}

    def cors(resp):
        origin=(request.headers.get("Origin") or "").rstrip("/")
        if origin=="https://topdiveair-sketch.github.io":
            resp.headers["Access-Control-Allow-Origin"]=origin;resp.headers["Vary"]="Origin"
        resp.headers["Access-Control-Allow-Headers"]="Content-Type";resp.headers["Access-Control-Allow-Methods"]="POST, OPTIONS";resp.headers["Cache-Control"]="no-store"
        return resp

    @app.route("/api/wachauetappe/funnel",methods=["POST","OPTIONS"])
    def we_funnel():
        if request.method=="OPTIONS":return cors(app.make_response(("",204)))
        origin=(request.headers.get("Origin") or "").rstrip("/")
        if origin and origin!="https://topdiveair-sketch.github.io":return cors(jsonify({"error":"origin_not_allowed"})),403
        p=request.get_json(silent=True) or {};event=str(p.get("event") or "")[:50]
        if event not in allowed:return cors(jsonify({"error":"invalid_event"})),422
        try:nights=max(0,min(30,int(p.get("nights")))) if p.get("nights") is not None else None
        except Exception:nights=None
        with db() as conn:conn.execute("INSERT INTO wachauetappe_funnel_events(event,route,nights,luggage,created_at) VALUES(?,?,?,?,?)",(event,str(p.get("route") or "")[:120],nights,1 if p.get("luggage") else 0,datetime.now().isoformat(timespec="seconds")))
        return cors(jsonify({"ok":True})),201

    @app.route("/api/wachauetappe/partner-leads",methods=["POST","OPTIONS"])
    def we_partner_leads():
        if request.method=="OPTIONS":return cors(app.make_response(("",204)))
        origin=(request.headers.get("Origin") or "").rstrip("/")
        if origin and origin!="https://topdiveair-sketch.github.io":return cors(jsonify({"error":"origin_not_allowed"})),403
        p=request.get_json(silent=True) or {}
        business=str(p.get("businessName") or "").strip()[:160];contact=str(p.get("contactName") or "").strip()[:120];email=str(p.get("email") or "").strip().lower()[:180];location=str(p.get("location") or "").strip()[:120]
        if not business or not contact or "@" not in email or not location:return cors(jsonify({"error":"missing_fields"})),422
        with db() as conn:
            conn.execute("""INSERT INTO wachauetappe_partner_leads(business_name,contact_name,email,phone,location,rooms,website,source,message,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,'new',?)""",(business,contact,email,str(p.get("phone") or "")[:80],location,str(p.get("rooms") or "")[:40],str(p.get("website") or "")[:240],str(p.get("source") or "")[:100],str(p.get("message") or "")[:1200],datetime.now().isoformat(timespec="seconds")))
        return cors(jsonify({"ok":True,"message":"Partneranfrage wurde übermittelt."})),201

    def commission_rate():
        try:
            with db() as conn:
                row=conn.execute("SELECT value FROM site_settings WHERE key='wachauetappe_commission_pct'").fetchone()
            return max(0.0,min(50.0,float(row["value"]))) if row else 10.0
        except Exception:return 10.0

    def summary(days=30):
        since=(datetime.now()-timedelta(days=max(1,min(int(days),365)))).isoformat(timespec="seconds")
        rate=commission_rate()
        with db() as conn:
            bookings=conn.execute("""SELECT COUNT(*) total,
              SUM(CASE WHEN status='requested' THEN 1 ELSE 0 END) requested,
              SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) confirmed,
              SUM(CASE WHEN status='declined' THEN 1 ELSE 0 END) declined,
              COALESCE(SUM(CASE WHEN status='confirmed' THEN price ELSE 0 END),0) confirmed_value
              FROM wachauetappe_guest_bookings WHERE created_at>=?""",(since,)).fetchone()
            trips=conn.execute("""SELECT trip_reference,
              COUNT(*) nights,
              SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) confirmed,
              SUM(CASE WHEN status='declined' THEN 1 ELSE 0 END) declined,
              SUM(CASE WHEN status='requested' THEN 1 ELSE 0 END) requested,
              COALESCE(SUM(CASE WHEN status='confirmed' THEN price ELSE 0 END),0) value,
              MIN(stay_date) start_date,MAX(stay_date) end_date,MAX(updated_at) updated_at
              FROM wachauetappe_guest_bookings WHERE created_at>=?
              GROUP BY trip_key,trip_reference ORDER BY updated_at DESC LIMIT 100""",(since,)).fetchall()
            funnel={r["event"]:int(r["n"]) for r in conn.execute("SELECT event,COUNT(*) n FROM wachauetappe_funnel_events WHERE created_at>=? GROUP BY event",(since,)).fetchall()}
            lead_row=conn.execute("SELECT COUNT(*) n FROM wachauetappe_partner_leads WHERE created_at>=?",(since,)).fetchone()
            alternatives=[dict(r) for r in conn.execute("""SELECT b.reference,b.trip_reference,b.stay_date,COALESCE(p.location,'') location,COALESCE(p.name,b.host_id) declined_host,
              (SELECT COUNT(*) FROM wachauetappe_partner_availability a JOIN wachauetappe_partner_accounts p2 ON p2.host_id=a.host_id AND p2.active=1
               WHERE lower(p2.location)=lower(p.location) AND a.stay_date=b.stay_date AND a.status='free' AND a.rooms_free>0 AND a.host_id<>b.host_id
               AND NOT EXISTS(SELECT 1 FROM wachauetappe_partner_calendar_blocks x WHERE x.host_id=a.host_id AND x.stay_date=a.stay_date AND x.provider='booking')) alternatives
              FROM wachauetappe_guest_bookings b LEFT JOIN wachauetappe_partner_accounts p ON p.host_id=b.host_id
              WHERE b.status='declined' AND b.created_at>=? ORDER BY b.updated_at DESC LIMIT 30""",(since,)).fetchall()]
        total=int(bookings["total"] or 0);confirmed=int(bookings["confirmed"] or 0);value=float(bookings["confirmed_value"] or 0)
        trip_items=[]
        for r in trips:
            d=dict(r);d["status"]="confirmed" if d["confirmed"]==d["nights"] else "needs_alternative" if d["declined"] else "pending";trip_items.append(d)
        return {"days":days,"partnerLeads":int(lead_row["n"] or 0),"commissionPct":rate,"bookingRequests":total,"requested":int(bookings["requested"] or 0),"confirmed":confirmed,"declined":int(bookings["declined"] or 0),"confirmedValue":round(value,2),"estimatedCommission":round(value*rate/100,2),"requestConfirmationPct":round(confirmed*100/total,1) if total else None,"funnel":funnel,"trips":trip_items,"replacementNeeds":alternatives}

    @app.get("/api/central/wachauetappe-operations")
    def we_ops_json():
        if not require_admin():return jsonify({"error":"unauthorized"}),401
        try:days=int(request.args.get("days") or 30)
        except Exception:days=30
        return jsonify(summary(days)),200

    @app.get("/os/wachauetappe")
    def we_ops_dashboard():
        if not require_admin():return app.redirect("/admin/login")
        d=summary(request.args.get("days",30,type=int));pct=lambda x:"–" if x is None else f"{x:.1f} %"
        cards=[("Partner-Leads",d["partnerLeads"]),("Anfragen",d["bookingRequests"]),("Bestätigte Nächte",d["confirmed"]),("Offen",d["requested"]),("Absagen",d["declined"]),("Bestätigter Buchungswert",f'{d["confirmedValue"]:.2f} EUR'),("Provisionssatz",f'{d["commissionPct"]:.1f} %'),("Erwartete Provision*",f'{d["estimatedCommission"]:.2f} EUR'),("Bestätigungsquote",pct(d["requestConfirmationPct"]))]
        card_html="".join(f"<article><span>{k}</span><strong>{v}</strong></article>" for k,v in cards)
        trip_html="".join(f"<tr><td>{x['trip_reference'] or '–'}</td><td>{x['start_date']} – {x['end_date']}</td><td>{x['confirmed']}/{x['nights']}</td><td>{x['status']}</td><td>{float(x['value'] or 0):.2f} EUR</td></tr>" for x in d["trips"]) or "<tr><td colspan='5'>Noch keine Reisen.</td></tr>"
        alt_html="".join(f"<tr><td>{x['trip_reference']}</td><td>{x['stay_date']}</td><td>{x['location']}</td><td>{x['declined_host']}</td><td>{x['alternatives']}</td></tr>" for x in d["replacementNeeds"]) or "<tr><td colspan='5'>Kein Ersatzbedarf.</td></tr>"
        f=d["funnel"];funnel_html="".join(f"<article><span>{k.replace('_',' ')}</span><strong>{f.get(k,0)}</strong></article>" for k in ["planner_view","trip_planned","host_selected","trip_request_started","trip_request_submitted","my_trip_opened"])
        html=f"""<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>WachauEtappe Operations</title><style>body{{font-family:system-ui;margin:0;background:#f3f6f4;color:#173d32}}main{{max-width:1200px;margin:auto;padding:28px 18px 60px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px}}article,section{{background:#fff;border:1px solid #d9e5df;border-radius:15px;padding:16px}}article span{{display:block;font-size:11px;font-weight:800;text-transform:uppercase;color:#6a7d75}}article strong{{font-size:25px}}section{{margin-top:20px;overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e6ece8;text-align:left;white-space:nowrap}}small{{color:#6a7d75}}a{{color:#176b5a}}</style></head><body><main><p><a href='/admin'>← Verwaltung</a></p><h1>🥾 WachauEtappe Operations</h1><p>Operative Vermittlungsübersicht · letzte {d['days']} Tage.</p><div class='grid'>{card_html}</div><p><small>*Rechnerischer Wert auf Basis bestätigter, im System bekannter Unterkunftspreise und des konfigurierten Provisionssatzes. Keine Zahlungs-/Forderungsbuchung.</small></p><section><h2>Conversion-Funnel</h2><div class='grid'>{funnel_html}</div></section><section><h2>Reisen</h2><table><tr><th>Reise</th><th>Zeitraum</th><th>Bestätigt</th><th>Status</th><th>Wert</th></tr>{trip_html}</table></section><section><h2>Ersatzbedarf</h2><table><tr><th>Reise</th><th>Nacht</th><th>Ort</th><th>Absage</th><th>freie Alternativen</th></tr>{alt_html}</table></section></main></body></html>"""
        return html,200

    app.extensions["wachauetappe_operations_summary"]=summary

from __future__ import annotations

import json, re, urllib.request, urllib.error
from datetime import date, datetime, timedelta
from html import unescape
from flask import jsonify, redirect, request, url_for

CORE=("direct_revenue_eur","direct_booking_conversion_pct","platform_commission_saved_eur","reputation_rating","review_volume","confirmed_visibility","comparable_competitors","guest_text_count","data_confidence_pct")
STATES=("live","snapshot","unavailable","error")
COMPETITORS=(
    ("haus-gerstbauer","Haus Gerstbauer",(
        ("google_hotels","https://www.google.at/travel/hotels/entity/CgoI6JiM5ZqSrLEgEAE"),
        ("municipality","https://www.aggsbach.gv.at/Ferienwohnung_-_Haus_GERSTBAUER_3"),)),
    ("goldene-wachau","Goldene Wachau",(
        ("official","https://www.goldenewachau.at/"),
        ("tripadvisor","https://www.tripadvisor.at/LocalMaps-g2273687-Aggsbach_Dorf-Area.html"),)),
)

def _now(): return datetime.now().isoformat(timespec="seconds")
def _today(): return date.today().isoformat()
def _fresh(value,hours=36):
    try: return datetime.now()-datetime.fromisoformat(value)<=timedelta(hours=hours)
    except Exception: return False

def _num(value):
    if value in (None,""): return None
    s=re.sub(r"[^0-9,.-]","",str(value).replace("\xa0"," "))
    if s.count(",")==1 and "." not in s: s=s.replace(",",".")
    try: return float(s)
    except Exception: return None

def _metric(key,value=None,state="unavailable",source="",measured_at="",note=""):
    return {"key":key,"value":value,"state":state if state in STATES else "error","source":source,"measured_at":measured_at or _now(),"note":note}

def _fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 ZuhauseAmBachMarketLeader/1.0","Accept-Language":"de-AT,de;q=0.9,en;q=0.7"})
    try:
        with urllib.request.urlopen(req,timeout=14) as r:
            return True,r.read(1500000).decode(r.headers.get_content_charset() or "utf-8",errors="replace"),f"HTTP {r.status}"
    except urllib.error.HTTPError as exc: return False,"",f"HTTP {exc.code}"
    except Exception as exc: return False,"",f"{type(exc).__name__}: {exc}"[:300]

def _parse(name,html):
    text=re.sub(r"<script\b[^>]*>.*?</script>"," ",html,flags=re.I|re.S)
    text=re.sub(r"<style\b[^>]*>.*?</style>"," ",text,flags=re.I|re.S)
    text=re.sub(r"<[^>]+>"," ",text); text=re.sub(r"\s+"," ",unescape(text)).strip()
    tokens=[x for x in re.split(r"\W+",name.lower()) if len(x)>=4]
    visible=bool(tokens) and sum(t in text.lower() for t in tokens)>=max(1,len(tokens)-1)
    rating=reviews=price=None
    for pat in (r"\b([1-5][,.][0-9])\s*(?:von\s*5|/\s*5|Hervorragend|Excellent)",r"\b([1-5][,.][0-9])\s*(?:\||-)\s*([0-9]{1,6})\s*(?:Rezensionen|Bewertungen|reviews)"):
        m=re.search(pat,text,flags=re.I)
        if m:
            rating=_num(m.group(1)); reviews=int(m.group(2)) if len(m.groups())>1 and m.group(2) else reviews; break
    if reviews is None:
        m=re.search(r"([0-9]{1,6})\s*(?:Rezensionen|Bewertungen|reviews|ratings)",text,flags=re.I)
        if m: reviews=int(m.group(1))
    vals=[]
    for pat in (r"(?:€|EUR)\s*([0-9]{2,4}(?:[,.][0-9]{1,2})?)",r"([0-9]{2,4}(?:[,.][0-9]{1,2})?)\s*(?:€|EUR)"):
        vals=[n for n in (_num(m.group(1)) for m in re.finditer(pat,text,flags=re.I)) if n is not None and 20<=n<=2000]
        if vals: price=min(vals); break
    return {"visibility":1 if visible else None,"rating":rating,"review_volume":reviews,"price_eur":price}

def init_market_leader_metrics(app,db,require_admin):
    if app.extensions.get("zab_market_leader_metrics_initialized"): return app.extensions["zab_market_leader_summary"]
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS market_kpi_daily(snapshot_date TEXT NOT NULL,entity_key TEXT NOT NULL,entity_name TEXT NOT NULL,entity_type TEXT NOT NULL,kpi_key TEXT NOT NULL,value_json TEXT DEFAULT 'null',state TEXT NOT NULL,source TEXT DEFAULT '',measured_at TEXT NOT NULL,note TEXT DEFAULT '',PRIMARY KEY(snapshot_date,entity_key,kpi_key));
        CREATE TABLE IF NOT EXISTS market_run_quality(snapshot_date TEXT PRIMARY KEY,consistent INTEGER NOT NULL,core_covered INTEGER NOT NULL,core_total INTEGER NOT NULL,live_count INTEGER NOT NULL,snapshot_count INTEGER NOT NULL,unavailable_count INTEGER NOT NULL,error_count INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS market_baseline(baseline_key TEXT PRIMARY KEY,baseline_date TEXT NOT NULL,payload_json TEXT NOT NULL,frozen_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS market_milestones(baseline_key TEXT NOT NULL,milestone_day INTEGER NOT NULL,measured_date TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(baseline_key,milestone_day));
        CREATE TABLE IF NOT EXISTS market_competitor_observations(competitor_key TEXT NOT NULL,competitor_name TEXT NOT NULL,source_key TEXT NOT NULL,source_url TEXT NOT NULL,checked_at TEXT NOT NULL,fetch_ok INTEGER NOT NULL,error TEXT DEFAULT '',metrics_json TEXT DEFAULT '{}',PRIMARY KEY(competitor_key,source_key));
        """)
    def save(entity_key,entity_name,entity_type,m):
        with db() as c:c.execute("INSERT INTO market_kpi_daily VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_date,entity_key,kpi_key) DO UPDATE SET value_json=excluded.value_json,state=excluded.state,source=excluded.source,measured_at=excluded.measured_at,note=excluded.note",(_today(),entity_key,entity_name,entity_type,m["key"],json.dumps(m["value"],ensure_ascii=False),m["state"],m["source"],m["measured_at"],m["note"]))
    def previous(entity,key):
        with db() as c:r=c.execute("SELECT * FROM market_kpi_daily WHERE entity_key=? AND kpi_key=? AND snapshot_date<? ORDER BY snapshot_date DESC LIMIT 1",(entity,key,_today())).fetchone()
        if not r:return None
        try:v=json.loads(r["value_json"])
        except Exception:v=None
        return _metric(key,v,"snapshot",r["source"],r["measured_at"],f"Letzter gültiger Snapshot vom {r['snapshot_date']}")
    def competitors(refresh=True):
        if refresh:
            for key,name,sources in COMPETITORS:
                for source,url in sources:
                    ok,html,err=_fetch(url); metrics=_parse(name,html) if ok else {}
                    with db() as c:c.execute("INSERT INTO market_competitor_observations VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(competitor_key,source_key) DO UPDATE SET checked_at=excluded.checked_at,fetch_ok=excluded.fetch_ok,error=excluded.error,metrics_json=CASE WHEN excluded.fetch_ok=1 THEN excluded.metrics_json ELSE market_competitor_observations.metrics_json END",(key,name,source,url,_now(),1 if ok else 0,"" if ok else err,json.dumps(metrics,ensure_ascii=False)))
        out=[]
        with db() as c:rows=c.execute("SELECT * FROM market_competitor_observations").fetchall()
        for key,name,_ in COMPETITORS:
            item={"key":key,"name":name,"metrics":{},"sources":[]}
            for r in rows:
                if r["competitor_key"]!=key:continue
                item["sources"].append({"source":r["source_key"],"url":r["source_url"],"fetch_ok":bool(r["fetch_ok"]),"checked_at":r["checked_at"],"error":r["error"]})
                try:vals=json.loads(r["metrics_json"] or "{}")
                except Exception:vals={}
                for k,v in vals.items():
                    if v is None:continue
                    state="live" if r["fetch_ok"] and _fresh(r["checked_at"]) else "snapshot"
                    old=item["metrics"].get(k)
                    if not old or (old["state"]!="live" and state=="live"):item["metrics"][k]=_metric(k,v,state,r["source_key"],r["checked_at"])
            for k in ("visibility","rating","review_volume","price_eur"):
                item["metrics"].setdefault(k,_metric(k,None,"unavailable","benchmark"));save(key,name,"competitor",item["metrics"][k])
            item["live_categories"]=sum(1 for m in item["metrics"].values() if m["state"]=="live" and m["value"] is not None);item["comparable"]=item["live_categories"]>=2;out.append(item)
        return out
    def property_metrics(comp):
        m={};direct=app.extensions.get("zab_direct_booking_metrics_summary")
        if direct:
            d=direct(30);e=d.get("economics",{});f=d.get("funnel",{})
            m["direct_revenue_eur"]=_metric("direct_revenue_eur",e.get("direct_revenue_eur"),"live","direct_booking_events")
            conv=f.get("quote_to_booking_pct");m["direct_booking_conversion_pct"]=_metric("direct_booking_conversion_pct",conv,"live" if conv is not None else "unavailable","direct_booking_events")
            saved=e.get("estimated_platform_commission_saved_eur");m["platform_commission_saved_eur"]=_metric("platform_commission_saved_eur",saved,"live" if saved is not None else "unavailable","direct_booking_events",note="Nur mit tatsächlichem Vergleichssatz")
        else:
            for k in CORE[:3]:m[k]=previous("zab",k) or _metric(k,None,"unavailable","direct_booking_metrics")
        with db() as c:
            b=c.execute("SELECT * FROM provider_monitor_listings WHERE lower(url) LIKE '%booking.com/%' AND active=1 ORDER BY CASE WHEN last_status='ok' THEN 0 ELSE 1 END,last_checked DESC LIMIT 1").fetchone(); listings=c.execute("SELECT * FROM provider_monitor_listings WHERE active=1").fetchall()
            try:reviews=c.execute("SELECT COUNT(*) n,MAX(checked_at) checked_at FROM provider_radar_reviews WHERE COALESCE(review_text,'')<>''").fetchone()
            except Exception:reviews=None
        for key,col,cast in (("reputation_rating","current_rating",_num),("review_volume","current_review_count",lambda x:int(_num(x)) if _num(x) is not None else None)):
            value=cast(b[col]) if b else None
            if value is not None:m[key]=_metric(key,value,"live" if b["last_status"]=="ok" and _fresh(b["last_checked"] or "") else "snapshot",b["name"],b["last_checked"] or _now())
            else:m[key]=previous("zab",key) or _metric(key,None,"error" if b and b["last_status"] not in ("","neu","ok") else "unavailable",b["name"] if b else "Booking.com",b["last_checked"] if b else "",b["last_error"] if b else "")
        vis=sum(1 for r in listings if r["last_status"]=="ok" and _fresh(r["last_checked"] or ""));m["confirmed_visibility"]=_metric("confirmed_visibility",vis,"live","provider_monitor") if vis else previous("zab","confirmed_visibility") or _metric("confirmed_visibility",None,"unavailable","provider_monitor")
        comparable=sum(1 for x in comp if x["comparable"]);m["comparable_competitors"]=_metric("comparable_competitors",comparable,"live","local_benchmark")
        if reviews and int(reviews["n"] or 0):m["guest_text_count"]=_metric("guest_text_count",int(reviews["n"]),"live" if _fresh(reviews["checked_at"] or "",72) else "snapshot","provider_radar_reviews",reviews["checked_at"] or _now())
        else:m["guest_text_count"]=previous("zab","guest_text_count") or _metric("guest_text_count",None,"unavailable","provider_radar_reviews")
        weights={"live":1,"snapshot":.65,"unavailable":0,"error":0};inputs=[m[k] for k in CORE[:-1]];conf=round(100*sum(weights[x["state"]] for x in inputs)/len(inputs),1);m["data_confidence_pct"]=_metric("data_confidence_pct",conf,"live","market_leader_metrics")
        for x in m.values():save("zab","Zuhause am Bach","property",x)
        return m
    def quality(m):
        states=[m[k]["state"] for k in CORE];counts={s:states.count(s) for s in STATES};consistent=all(s in STATES for s in states) and not any(m[k]["state"]=="error" and m[k]["value"] is not None for k in CORE);covered=sum(s!="error" for s in states)
        with db() as c:c.execute("INSERT INTO market_run_quality VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_date) DO UPDATE SET consistent=excluded.consistent,core_covered=excluded.core_covered,core_total=excluded.core_total,live_count=excluded.live_count,snapshot_count=excluded.snapshot_count,unavailable_count=excluded.unavailable_count,error_count=excluded.error_count,created_at=excluded.created_at",(_today(),1 if consistent else 0,covered,len(CORE),counts["live"],counts["snapshot"],counts["unavailable"],counts["error"],_now()))
        return {"consistent":consistent,"core_covered":covered,"core_total":len(CORE),**{s+"_count":counts[s] for s in STATES}}
    def proof(m):
        key="market_leader_v1"
        with db() as c:base=c.execute("SELECT * FROM market_baseline WHERE baseline_key=?",(key,)).fetchone();recent=c.execute("SELECT snapshot_date,consistent FROM market_run_quality ORDER BY snapshot_date DESC LIMIT 3").fetchall()
        if not base and len(recent)==3 and all(r["consistent"] for r in recent):
            ds=[date.fromisoformat(r["snapshot_date"]) for r in recent]
            if ds[0]-ds[1]==timedelta(days=1) and ds[1]-ds[2]==timedelta(days=1):
                payload=json.dumps({k:m[k] for k in CORE},ensure_ascii=False)
                with db() as c:c.execute("INSERT INTO market_baseline VALUES(?,?,?,?)",(key,_today(),payload,_now()))
                base={"baseline_date":_today()}
        result={"frozen":bool(base),"baseline_date":base["baseline_date"] if base else None,"milestones":{}}
        if not base:return {**result,"runs_needed":max(0,3-sum(1 for r in recent if r["consistent"]))}
        elapsed=(date.today()-date.fromisoformat(base["baseline_date"])).days
        with db() as c:existing={r["milestone_day"]:r for r in c.execute("SELECT * FROM market_milestones WHERE baseline_key=?",(key,)).fetchall()}
        for day in (30,60,90):
            if elapsed>=day and day not in existing:
                with db() as c:c.execute("INSERT INTO market_milestones VALUES(?,?,?,?,?)",(key,day,_today(),json.dumps({k:m[k] for k in CORE},ensure_ascii=False),_now()))
                existing[day]={"measured_date":_today()}
            row=existing.get(day);result["milestones"][f"d{day}"]={"captured":bool(row),"measured_date":row["measured_date"] if row else None,"due_in_days":0 if row else max(0,day-elapsed)}
        return result
    def run(refresh_competitors=True):
        comp=competitors(refresh_competitors);m=property_metrics(comp);q=quality(m);p=proof(m);count=sum(1 for x in comp if x["comparable"])
        return {"snapshot_date":_today(),"kpi_schema":{"states":list(STATES),"core_kpis":list(CORE)},"property":{"key":"zab","name":"Zuhause am Bach","metrics":m},"quality":q,"proof_30_60_90":p,"benchmark":{"competitors":comp,"comparable_live_competitors":count,"success_criterion_met":count>=2}}
    @app.get("/admin/market-leader-performance.json")
    def market_json():
        if not require_admin():return jsonify({"error":"unauthorized"}),401
        return jsonify(run(request.args.get("refresh","1")!="0"))
    @app.get("/admin/market-leader-performance")
    def market_html():
        if not require_admin():return redirect(url_for("admin_login"))
        d=run(request.args.get("refresh","1")!="0");m=d["property"]["metrics"]
        cards="".join(f"<li><b>{k}</b>: {m[k]['value'] if m[k]['value'] is not None else '–'} <small>({m[k]['state']} · {m[k]['source']})</small></li>" for k in CORE);comps="".join(f"<li>{x['name']}: {x['live_categories']} Live-Kategorien</li>" for x in d["benchmark"]["competitors"])
        return f"<html><head><meta charset='utf-8'><title>Marktführer-Cockpit</title></head><body><main><h1>Marktführer-Cockpit</h1><ul>{cards}</ul><h2>Lokaler Benchmark</h2><ul>{comps}</ul><p>Baseline: {'eingefroren' if d['proof_30_60_90']['frozen'] else 'wartet auf 3 konsistente Tagesläufe'}</p></main></body></html>",200
    app.extensions["zab_market_leader_metrics_initialized"]=True;app.extensions["zab_market_leader_summary"]=run;return run

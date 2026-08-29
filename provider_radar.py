"""Market/distribution radar layered on top of provider_monitor.py."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from html import unescape

from flask import flash, jsonify, redirect, render_template, url_for


DIRECT_URL = "https://topdiveair-sketch.github.io/Direcktbuchungen/index"
PROPERTY_MARKERS = ("zuhause am bach", "zu hause am bach", "aggsbach markt 82")
WRONG_PHRASES = (
    "gemeinschaftsbad", "gemeinschaftliches badezimmer", "gemeinsames badezimmer",
    "shared bathroom", "shared bath", "bathroom shared", "adults only",
    "adult-only", "nur für erwachsene", "nur fuer erwachsene",
)
SEARCH_QUERIES = (
    '\"Zuhause am Bach\" Aggsbach', '\"Zuhause am Bach\" Wachau',
    '\"Zuhause am Bach - Wachau\"', '\"Aggsbach Markt 82\" Unterkunft',
)
AIRBNB_URL = "https://www.airbnb.com/rooms/1747752971503065378"


def _now(): return datetime.now().isoformat(timespec="seconds")
def _host(url):
    try: h=urllib.parse.urlsplit(url).netloc.lower().split("@")[ -1].split(":")[0]
    except Exception: return ""
    return h[4:] if h.startswith("www.") else h

def _canonical(url):
    try: p=urllib.parse.urlsplit(url)
    except Exception: return url[:3000]
    host=_host(url); path=re.sub(r"/+","/",p.path or "/").rstrip("/") or "/"
    keep=[(k,v) for k,v in urllib.parse.parse_qsl(p.query) if k.lower() in {"id","hotelid","hotel_id","room","property"}]
    return urllib.parse.urlunsplit((p.scheme or "https",host,path,urllib.parse.urlencode(keep),""))[:3000]

def _country(url):
    h=_host(url)
    known={"donau.com":"Österreich","aggsbach.gv.at":"Österreich","holidaycheck.at":"Österreich","viamichelin.at":"Österreich","booking.com":"International","airbnb.com":"International","agoda.com":"International","outdooractive.com":"International","bedandbreakfast.eu":"Europa"}
    for d,c in known.items():
        if h==d or h.endswith("."+d): return c
    tlds={"at":"Österreich","de":"Deutschland","ch":"Schweiz","it":"Italien","fr":"Frankreich","nl":"Niederlande","be":"Belgien","cz":"Tschechien","sk":"Slowakei","hu":"Ungarn","si":"Slowenien","hr":"Kroatien","pl":"Polen","es":"Spanien","pt":"Portugal","dk":"Dänemark","se":"Schweden","no":"Norwegen","fi":"Finnland","uk":"Vereinigtes Königreich"}
    return tlds.get(h.rsplit(".",1)[-1],"International") if h else "Unbekannt"

def _name(url):
    h=_host(url); bits=h.split("."); core=bits[-2] if len(bits)>1 else h
    return (core or "Neue Quelle").replace("-"," ").title()

def _float(value):
    m=re.search(r"\d+(?:[.,]\d+)?",str(value or ""))
    if not m: return None
    try: return float(m.group(0).replace(",","."))
    except ValueError: return None

def _pct(cur,old):
    if old is None: return None
    if old==0: return 100.0 if cur else 0.0
    return round((cur-old)*100.0/old,1)

def _fetch(url, timeout=15):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 ZuhauseAmBachRadar/1.0","Accept-Language":"de-AT,de;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def _jsonld(html):
    out=[]
    for raw in re.findall(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",html,re.I|re.S):
        try: node=json.loads(unescape(raw).strip())
        except Exception: continue
        stack=[node]
        while stack:
            x=stack.pop()
            if isinstance(x,dict): out.append(x); stack.extend(x.values())
            elif isinstance(x,list): stack.extend(x)
    return out

def _latest_review(html):
    reviews=[o for o in _jsonld(html) if str(o.get("@type") or "").lower()=="review"]
    if not reviews: return {"fingerprint":"","rating":"","date":"","author":"","text":""}
    reviews.sort(key=lambda x:str(x.get("datePublished") or x.get("dateCreated") or ""),reverse=True); r=reviews[0]
    rr=r.get("reviewRating") or {}; rating=rr.get("ratingValue","") if isinstance(rr,dict) else rr
    a=r.get("author") or {}; author=a.get("name","") if isinstance(a,dict) else a
    text=re.sub(r"\s+"," ",str(r.get("reviewBody") or r.get("description") or "")).strip()[:2500]
    dt=str(r.get("datePublished") or r.get("dateCreated") or "")[:80]
    src="|".join(map(str,(rating,dt,author,text)))
    return {"fingerprint":hashlib.sha256(src.encode()).hexdigest() if src.strip("|") else "","rating":str(rating),"date":dt,"author":str(author)[:200],"text":text}

def _page_text(html): return re.sub(r"\s+"," ",unescape(re.sub(r"<[^>]+>"," ",re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>"," ",html,flags=re.I|re.S)))).strip()
def _alerts(text): return [p for p in WRONG_PHRASES if p in text.lower()]

def _search(query):
    key=os.environ.get("SERPER_API_KEY","").strip()
    if key:
        try:
            data=json.dumps({"q":query,"gl":"at","hl":"de","num":20}).encode()
            req=urllib.request.Request("https://google.serper.dev/search",data=data,headers={"X-API-KEY":key,"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=20) as r: body=json.loads(r.read().decode())
            return [(i,str(x.get("title") or ""),str(x.get("link") or ""),"Google/Serper") for i,x in enumerate(body.get("organic") or [],1) if x.get("link")]
        except Exception: pass
    try:
        html=_fetch("https://html.duckduckgo.com/html/?"+urllib.parse.urlencode({"q":query,"kl":"at-de"}),20)
        pat=re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',re.I|re.S); rows=[]
        for i,m in enumerate(pat.finditer(html),1):
            href=unescape(m.group(1)); title=re.sub(r"<[^>]+>"," ",m.group(2)).strip()
            p=urllib.parse.urlsplit(href)
            if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"): href=urllib.parse.parse_qs(p.query).get("uddg",[href])[0]
            rows.append((i,title,href,"DuckDuckGo"))
            if len(rows)>=20: break
        return rows
    except Exception: return []


def init_provider_radar(app,db,require_admin):
    if app.extensions.get("zab_provider_radar_initialized"): return
    app.extensions["zab_provider_radar_initialized"]=True

    def addcol(conn,table,definition):
        name=definition.split()[0]
        if name not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    with db() as c:
        for d in ("country TEXT DEFAULT 'Unbekannt'","auto_discovered INTEGER NOT NULL DEFAULT 0","first_seen TEXT DEFAULT ''","last_seen TEXT DEFAULT ''","consecutive_failures INTEGER NOT NULL DEFAULT 0","presence_status TEXT DEFAULT 'aktiv'","radar_seen_check TEXT DEFAULT ''","search_rank INTEGER NOT NULL DEFAULT 0"):
            addcol(c,"provider_monitor_listings",d)
        for d in ("severity TEXT DEFAULT 'yellow'","summary TEXT DEFAULT ''"):
            addcol(c,"provider_monitor_changes",d)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS provider_radar_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_radar_snapshots(snapshot_date TEXT PRIMARY KEY,provider_count INTEGER NOT NULL,direct_count INTEGER NOT NULL,booking_count INTEGER NOT NULL,countries_count INTEGER NOT NULL,score INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS provider_radar_discovery(id INTEGER PRIMARY KEY AUTOINCREMENT,query TEXT NOT NULL,engine TEXT NOT NULL,rank INTEGER NOT NULL,title TEXT DEFAULT '',url TEXT NOT NULL,canonical_url TEXT NOT NULL,found_at TEXT NOT NULL,added INTEGER NOT NULL DEFAULT 0,UNIQUE(query,canonical_url));
        CREATE TABLE IF NOT EXISTS provider_radar_reviews(listing_id INTEGER PRIMARY KEY,fingerprint TEXT DEFAULT '',rating TEXT DEFAULT '',review_date TEXT DEFAULT '',author TEXT DEFAULT '',review_text TEXT DEFAULT '',checked_at TEXT DEFAULT '');
        """)
        defaults={"discovery_enabled":"1","discovery_hours":"24","last_discovery":"","last_discovery_result":"noch nie","failure_threshold":"3","direct_price":os.environ.get("PUBLIC_BACHBLICK_NIGHTLY_PRICE","101.00") or "101.00"}
        for k,v in defaults.items(): c.execute("INSERT OR IGNORE INTO provider_radar_settings(key,value) VALUES(?,?)",(k,v))
        if not c.execute("SELECT 1 FROM provider_monitor_listings WHERE url LIKE '%airbnb.com/rooms/1747752971503065378%' LIMIT 1").fetchone():
            c.execute("INSERT INTO provider_monitor_listings(name,category,url,active,created_at,country,first_seen,presence_status) VALUES('Airbnb','OTA',?,1,?,'International',?,'aktiv')",(AIRBNB_URL,_now(),_now()))
        c.execute("UPDATE provider_monitor_listings SET country=CASE WHEN country IN ('','Unbekannt') THEN 'Österreich' ELSE country END WHERE url LIKE '%aggsbach.gv.at%' OR url LIKE '%donau.com/%'")
        c.execute("UPDATE provider_monitor_listings SET country='International' WHERE country IN ('','Unbekannt') AND (url LIKE '%booking.com/%' OR url LIKE '%airbnb.com/%' OR url LIKE '%agoda.com/%' OR url LIKE '%outdooractive.com/%')")

    def cfg():
        with db() as c: return {r["key"]:r["value"] for r in c.execute("SELECT key,value FROM provider_radar_settings")}
    def setcfg(k,v):
        with db() as c: c.execute("INSERT INTO provider_radar_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))
    def direct_price():
        try: return float(cfg().get("direct_price","101").replace(",","."))
        except Exception: return 101.0

    def classify_change(field,old,new):
        o,n=str(old or ""),str(new or "")
        if field=="Direktbuchungs-Link": return ("green","Direktlink hinzugekommen") if n=="1" else ("red","Direktlink verschwunden")
        if field=="Booking-Link": return ("red","Booking-Link hinzugekommen") if n=="1" else ("green","Booking-Link entfernt")
        if field=="Bewertung":
            a,b=_float(o),_float(n)
            if a is not None and b is not None: return ("green",f"Bewertung gestiegen: {o} → {n}") if b>a else (("red",f"Bewertung gefallen: {o} → {n}") if b<a else ("yellow","Bewertung geändert"))
        if field=="Preis":
            b=_float(n)
            return ("red",f"Fremdpreis {n} liegt unter Direktpreis € {direct_price():.0f}") if b is not None and b<direct_price() else ("yellow",f"Preis geändert: {o or '–'} → {n or '–'}")
        if field=="Beschreibung": return "yellow","Beschreibung geändert"
        if field=="Anzahl Bewertungen": return "blue","Bewertungsanzahl geändert"
        if field=="Neuer Anbieter": return "blue","Neue Quelle im Web gefunden"
        if field=="Anbieterstatus": return ("red","Anbieter/Eintrag weggefallen") if n=="weggefallen" else ("green","Anbieter/Eintrag wieder erreichbar")
        if field=="Neue Bewertung": return "blue","Neue öffentliche Bewertung erkannt"
        if field=="Inhaltswarnung": return ("red","Mögliche Falschangabe im Text") if n else ("green","Falschangabe nicht mehr gefunden")
        return "gray","Technische/sonstige Änderung"

    def enrich_changes():
        with db() as c:
            changes=c.execute("SELECT id,field,old_value,new_value,severity,summary FROM provider_monitor_changes ORDER BY id DESC LIMIT 500").fetchall()
            for x in changes:
                sev,s=classify_change(x["field"],x["old_value"],x["new_value"])
                if not x["summary"] or (x["severity"] in ("","yellow") and sev!="yellow"):
                    c.execute("UPDATE provider_monitor_changes SET severity=?,summary=? WHERE id=?",(sev,s,x["id"]))

    def update_presence():
        th=max(2,min(10,int(cfg().get("failure_threshold","3") or 3)))
        with db() as c:
            rows=c.execute("SELECT * FROM provider_monitor_listings WHERE active=1").fetchall()
            for r in rows:
                if not r["last_checked"] or r["last_checked"]==r["radar_seen_check"]: continue
                fails=0 if r["last_status"]=="ok" else int(r["consecutive_failures"] or 0)+1
                presence="aktiv" if r["last_status"]=="ok" else ("weggefallen" if fails>=th else (r["presence_status"] or "aktiv"))
                if presence!=r["presence_status"]:
                    sev,s=classify_change("Anbieterstatus",r["presence_status"],presence)
                    c.execute("INSERT INTO provider_monitor_changes(listing_id,field,old_value,new_value,changed_at,acknowledged,severity,summary) VALUES(?,?,?,?,?,0,?,?)",(r["id"],"Anbieterstatus",r["presence_status"],presence,_now(),sev,s))
                c.execute("UPDATE provider_monitor_listings SET consecutive_failures=?,presence_status=?,radar_seen_check=?,last_seen=CASE WHEN last_status='ok' THEN ? ELSE last_seen END,country=CASE WHEN country IN ('','Unbekannt') THEN ? ELSE country END WHERE id=?",(fails,presence,r["last_checked"],_now(),_country(r["url"]),r["id"]))

    def review_and_text_scan():
        with db() as c: rows=c.execute("SELECT * FROM provider_monitor_listings WHERE active=1 AND presence_status<>'weggefallen'").fetchall()
        for r in rows:
            try:
                url=r["last_rendered_url"] or r["url"]; html=_fetch(url,12); txt=_page_text(html)[:30000]; alerts=_alerts(txt)
                review=_latest_review(html)
                with db() as c:
                    old=c.execute("SELECT * FROM provider_radar_reviews WHERE listing_id=?",(r["id"],)).fetchone()
                    if old and review["fingerprint"] and review["fingerprint"]!=old["fingerprint"]:
                        sev,s=classify_change("Neue Bewertung","",review["fingerprint"])
                        new=" | ".join(x for x in (review["date"],review["rating"],review["author"],review["text"]) if x)
                        c.execute("INSERT INTO provider_monitor_changes(listing_id,field,old_value,new_value,changed_at,acknowledged,severity,summary) VALUES(?,?,?,?,?,0,?,?)",(r["id"],"Neue Bewertung","",new,_now(),sev,s))
                    c.execute("INSERT INTO provider_radar_reviews(listing_id,fingerprint,rating,review_date,author,review_text,checked_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(listing_id) DO UPDATE SET fingerprint=excluded.fingerprint,rating=excluded.rating,review_date=excluded.review_date,author=excluded.author,review_text=excluded.review_text,checked_at=excluded.checked_at",(r["id"],review["fingerprint"],review["rating"],review["date"],review["author"],review["text"],_now()))
                    prior_alerts=_alerts(r["current_description"] or "")
                    if sorted(alerts)!=sorted(prior_alerts):
                        sev,s=classify_change("Inhaltswarnung",json.dumps(prior_alerts,ensure_ascii=False),json.dumps(alerts,ensure_ascii=False))
                        c.execute("INSERT INTO provider_monitor_changes(listing_id,field,old_value,new_value,changed_at,acknowledged,severity,summary) VALUES(?,?,?,?,?,0,?,?)",(r["id"],"Inhaltswarnung",", ".join(prior_alerts),", ".join(alerts),_now(),sev,s))
            except Exception: pass
            time.sleep(.25)

    def discover(force=False):
        s=cfg(); last=s.get("last_discovery",""); hours=max(6,min(168,int(s.get("discovery_hours","24") or 24)))
        if s.get("discovery_enabled","1")!="1" and not force: return 0,0,"Discovery deaktiviert"
        if last and not force:
            try:
                if datetime.now()-datetime.fromisoformat(last)<timedelta(hours=hours): return 0,0,"noch nicht fällig"
            except ValueError: pass
        with db() as c: existing={_canonical(r["url"]):r["id"] for r in c.execute("SELECT id,url FROM provider_monitor_listings")}
        seen=added=0
        for q in SEARCH_QUERIES:
            for rank,title,url,engine in _search(q):
                combined=(title+" "+url).lower()
                if not any(m in combined for m in PROPERTY_MARKERS) or not url.startswith(("http://","https://")): continue
                can=_canonical(url); seen+=1
                with db() as c: c.execute("INSERT OR IGNORE INTO provider_radar_discovery(query,engine,rank,title,url,canonical_url,found_at,added) VALUES(?,?,?,?,?,?,?,0)",(q,engine,rank,title[:500],url[:3000],can,_now()))
                if can in existing:
                    with db() as c: c.execute("UPDATE provider_monitor_listings SET search_rank=CASE WHEN search_rank=0 OR ?>0 AND ?<search_rank THEN ? ELSE search_rank END WHERE id=?",(rank,rank,rank,existing[can]))
                    continue
                with db() as c:
                    cur=c.execute("INSERT INTO provider_monitor_listings(name,category,url,active,created_at,country,auto_discovered,first_seen,presence_status,search_rank) VALUES(?,?,?,?,?,?,?,?,?,?)",(_name(can),"Entdeckt",can,1,_now(),_country(can),1,_now(),"aktiv",rank)); lid=cur.lastrowid
                    sev,su=classify_change("Neuer Anbieter","",can); c.execute("INSERT INTO provider_monitor_changes(listing_id,field,old_value,new_value,changed_at,acknowledged,severity,summary) VALUES(?, 'Neuer Anbieter','',?, ?,0,?,?)",(lid,can,_now(),sev,su)); c.execute("UPDATE provider_radar_discovery SET added=1 WHERE canonical_url=?",(can,))
                existing[can]=lid; added+=1
        text=f"{seen} relevante Suchtreffer, {added} neue Quelle(n)"; setcfg("last_discovery",_now()); setcfg("last_discovery_result",text); return seen,added,text

    def score(rows):
        p=[r for r in rows if r["active"] and r["category"]!="Direkt" and r["presence_status"]!="weggefallen"]
        if not p: return 0
        n=len(p); direct=sum(bool(r["direct_link"]) for r in p); only=sum(bool(r["booking_link"]) and not bool(r["direct_link"]) for r in p); bad=sum(bool(_alerts(r["current_description"] or "")) for r in p); prices=[_float(r["current_price"]) for r in p if _float(r["current_price"]) is not None]; cheap=min(prices) if prices else None
        return max(0,min(100,round(45*direct/n+20*(1-only/n)+15*(1-bad/n)+(10 if cheap is None or cheap>=direct_price() else 0)+10*sum(r["last_status"]=="ok" for r in p)/n)))

    def snapshot():
        with db() as c: rows=c.execute("SELECT * FROM provider_monitor_listings").fetchall()
        p=[r for r in rows if r["active"] and r["category"]!="Direkt" and r["presence_status"]!="weggefallen"]; direct=sum(bool(r["direct_link"]) for r in p); booking=sum(bool(r["booking_link"]) for r in p); countries=len({r["country"] for r in p if r["country"] and r["country"]!="Unbekannt"}); sc=score(rows)
        with db() as c: c.execute("INSERT INTO provider_radar_snapshots(snapshot_date,provider_count,direct_count,booking_count,countries_count,score,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(snapshot_date) DO UPDATE SET provider_count=excluded.provider_count,direct_count=excluded.direct_count,booking_count=excluded.booking_count,countries_count=excluded.countries_count,score=excluded.score,created_at=excluded.created_at",(date.today().isoformat(),len(p),direct,booking,countries,sc,_now()))

    def metrics(rows):
        p=[r for r in rows if r["active"] and r["category"]!="Direkt" and r["presence_status"]!="weggefallen"]; n=len(p); countries={}
        for r in p: countries[r["country"] or "Unbekannt"]=countries.get(r["country"] or "Unbekannt",0)+1
        prices=[(_float(r["current_price"]),r["name"]) for r in p if _float(r["current_price"]) is not None]; prices.sort(key=lambda x:x[0]); cheapest=prices[0] if prices else (None,"")
        def prev(days):
            target=(date.today()-timedelta(days=days)).isoformat()
            with db() as c: return c.execute("SELECT provider_count FROM provider_radar_snapshots WHERE snapshot_date<=? ORDER BY snapshot_date DESC LIMIT 1",(target,)).fetchone()
        d1,d7,d30=prev(1),prev(7),prev(30); direct=sum(bool(r["direct_link"]) for r in p); booking=sum(bool(r["booking_link"]) for r in p)
        return {"provider_count":n,"direct_count":direct,"booking_count":booking,"ota_only_count":sum(bool(r["booking_link"]) and not bool(r["direct_link"]) for r in p),"direct_share":round(100*direct/n,1) if n else 0,"booking_share":round(100*booking/n,1) if n else 0,"countries":sorted(countries.items(),key=lambda x:(-x[1],x[0])),"countries_count":len(countries),"score":score(rows),"direct_price":direct_price(),"cheapest_price":cheapest[0],"cheapest_provider":cheapest[1],"growth_1d":_pct(n,int(d1["provider_count"])) if d1 else None,"growth_7d":_pct(n,int(d7["provider_count"])) if d7 else None,"growth_30d":_pct(n,int(d30["provider_count"])) if d30 else None}

    def maintenance(force_discovery=False):
        update_presence(); enrich_changes(); discover(force_discovery); review_and_text_scan(); snapshot()

    def loop():
        time.sleep(70)
        while True:
            try: maintenance(False)
            except Exception: pass
            time.sleep(3600)
    if os.environ.get("WERKZEUG_RUN_MAIN")=="true" or not app.debug: threading.Thread(target=loop,daemon=True,name="zab-provider-radar").start()

    @app.get("/admin/provider-radar")
    def provider_radar_dashboard():
        if not require_admin(): return redirect(url_for("admin_login"))
        update_presence(); enrich_changes(); snapshot()
        with db() as c:
            rows=c.execute("SELECT l.*,r.rating AS latest_review_rating,r.review_date AS latest_review_date,r.author AS latest_review_author,r.review_text AS latest_review_text FROM provider_monitor_listings l LEFT JOIN provider_radar_reviews r ON r.listing_id=l.id ORDER BY CASE WHEN l.category='Direkt' THEN 1 ELSE 0 END,CASE l.presence_status WHEN 'weggefallen' THEN 1 ELSE 0 END,l.active DESC,l.category,l.name").fetchall()
            changes=c.execute("SELECT c.*,l.name AS listing_name FROM provider_monitor_changes c JOIN provider_monitor_listings l ON l.id=c.listing_id ORDER BY c.id DESC LIMIT 300").fetchall(); open_changes=c.execute("SELECT COUNT(*) n FROM provider_monitor_changes WHERE acknowledged=0").fetchone()["n"]; discoveries=c.execute("SELECT * FROM provider_radar_discovery ORDER BY id DESC LIMIT 50").fetchall()
        view=[]
        for r in rows:
            d=dict(r); d["alerts"]=_alerts(r["current_description"] or ""); d["traffic"]="black" if r["presence_status"]=="weggefallen" else ("green" if r["category"]=="Direkt" or (r["direct_link"] and not r["booking_link"]) else ("yellow" if r["direct_link"] and r["booking_link"] else ("red" if r["booking_link"] else ("blue" if r["auto_discovered"] and not r["last_checked"] else "gray")))); view.append(d)
        return render_template("provider_radar.html",listings=view,changes=changes,open_changes=open_changes,discoveries=discoveries,metrics=metrics(rows),radar_settings=cfg(),direct_url=DIRECT_URL)

    @app.post("/admin/provider-radar/discover")
    def provider_radar_discover():
        if not require_admin(): return redirect(url_for("admin_login"))
        _,_,msg=discover(True); runner=app.extensions.get("zab_provider_monitor_run"); runner and runner("radar-discovery"); maintenance(False); flash(msg,"success"); return redirect(url_for("provider_radar_dashboard"))

    @app.post("/admin/provider-radar/refresh")
    def provider_radar_refresh():
        if not require_admin(): return redirect(url_for("admin_login"))
        runner=app.extensions.get("zab_provider_monitor_run"); ok,msg,_=runner("radar-manual") if runner else (False,"Monitor nicht verfügbar",0); maintenance(False); flash(msg,"success" if ok else "error"); return redirect(url_for("provider_radar_dashboard"))

    @app.post("/admin/provider-radar/settings")
    def provider_radar_settings():
        if not require_admin(): return redirect(url_for("admin_login"))
        from flask import request
        setcfg("discovery_enabled","1" if request.form.get("discovery_enabled")=="on" else "0"); setcfg("discovery_hours",max(6,min(168,int(request.form.get("discovery_hours","24") or 24)))); setcfg("failure_threshold",max(2,min(10,int(request.form.get("failure_threshold","3") or 3))))
        try: dp=max(1,float(str(request.form.get("direct_price","101")).replace(",",".")))
        except ValueError: dp=101
        setcfg("direct_price",f"{dp:.2f}"); flash("Radar-Einstellungen gespeichert.","success"); return redirect(url_for("provider_radar_dashboard"))

    @app.get("/health/provider-radar")
    def provider_radar_health():
        with db() as c: active=c.execute("SELECT COUNT(*) n FROM provider_monitor_listings WHERE active=1 AND category<>'Direkt' AND presence_status<>'weggefallen'").fetchone()["n"]; gone=c.execute("SELECT COUNT(*) n FROM provider_monitor_listings WHERE active=1 AND presence_status='weggefallen'").fetchone()["n"]
        s=cfg(); return jsonify(ok=True,active_providers=active,gone_providers=gone,last_discovery=s.get("last_discovery"),last_discovery_result=s.get("last_discovery_result"))

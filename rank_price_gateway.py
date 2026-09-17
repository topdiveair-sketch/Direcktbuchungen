"""Admin rank + price monitor for Zuhause am Bach.

Adds an authenticated dashboard and JSON endpoint to the existing Railway app.
Live organic Google rank is only reported when SERPAPI_KEY is configured.
Without it, the UI explicitly marks rank as unavailable rather than inventing data.
Price comparison uses the exact ZAB direct-price calendar plus optional user-entered
competitor prices for the same stay. Public benchmark prices are shown separately
and never mixed into an exact date-specific ranking.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta

from flask import Response, jsonify, redirect, request

from railway_app import app
import app as legacy_app
from pricing_2027 import nightly_direct_rate

TARGET_DOMAIN = os.environ.get("RANK_TARGET_DOMAIN", "topdiveair-sketch.github.io").strip().lower()
TARGET_PATH = os.environ.get("RANK_TARGET_PATH", "/Direcktbuchungen/").strip()
SERP_LOCATION = os.environ.get("SERP_LOCATION", "Lower Austria, Austria").strip()
DEFAULT_QUERY = "unterkunft wachau nordufer"


def _admin_ok() -> bool:
    try:
        return bool(legacy_app.require_admin())
    except Exception:
        return False


def _effective_direct_rate(room: str, day: date) -> float | None:
    if room == "Bachblick":
        base = nightly_direct_rate(day)
        if base is None:
            return None
    else:
        with legacy_app.db() as conn:
            row = conn.execute(
                "SELECT standard,weekend,high FROM room_prices WHERE room=?", (room,)
            ).fetchone()
            if not row:
                return None
            high = False
            for season in conn.execute("SELECT start_date,end_date FROM seasons"):
                try:
                    if date.fromisoformat(season["start_date"]) <= day <= date.fromisoformat(season["end_date"]):
                        high = True
                        break
                except Exception:
                    continue
            base = float(row["high"] if high else row["weekend"] if day.weekday() in (4, 5) else row["standard"])
    getter = app.extensions.get("zab_channel_price_for_day")
    if callable(getter):
        try:
            value = getter(room, "direct", day, float(base))
            if value is not None:
                return round(float(value), 2)
        except Exception:
            pass
    return round(float(base), 2)


def _stay_price(room: str, arrival: date, departure: date) -> dict:
    if departure <= arrival:
        raise ValueError("Abreise muss nach Anreise liegen.")
    nights = (departure - arrival).days
    if nights > 30:
        raise ValueError("Maximal 30 Nächte pro Vergleich.")
    rows = []
    total = 0.0
    current = arrival
    while current < departure:
        rate = _effective_direct_rate(room, current)
        if rate is None:
            raise ValueError("Für mindestens eine Nacht ist kein Direktpreis hinterlegt.")
        rows.append({"date": current.isoformat(), "price_eur": rate})
        total += rate
        current += timedelta(days=1)
    return {
        "room": room,
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "nights": nights,
        "total_eur": round(total, 2),
        "average_nightly_eur": round(total / nights, 2),
        "nightly": rows,
        "basis": "final_direct_rate",
    }


def _serp_rank(query: str) -> dict:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return {
            "status": "not_configured",
            "rank": None,
            "query": query,
            "source": "SerpAPI",
            "message": "SERPAPI_KEY fehlt. Live-Rang wird absichtlich nicht geschätzt.",
        }
    params = {
        "engine": "google",
        "q": query,
        "google_domain": "google.at",
        "gl": "at",
        "hl": "de",
        "num": "100",
        "location": SERP_LOCATION,
        "api_key": key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ZuhauseAmBach-RankMonitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {
            "status": "error",
            "rank": None,
            "query": query,
            "source": "SerpAPI",
            "message": f"Live-Abfrage fehlgeschlagen: {type(exc).__name__}",
        }
    organic = payload.get("organic_results") if isinstance(payload, dict) else []
    if not isinstance(organic, list):
        organic = []
    matches = []
    for item in organic:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "")
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        try:
            parsed = urllib.parse.urlparse(link)
            host = parsed.netloc.lower()
            path = parsed.path
        except Exception:
            host = ""
            path = ""
        domain_match = TARGET_DOMAIN and (host == TARGET_DOMAIN or host.endswith("." + TARGET_DOMAIN))
        path_match = not TARGET_PATH or path.startswith(TARGET_PATH)
        brand_match = "zuhause am bach" in (title + " " + snippet).lower()
        if (domain_match and path_match) or brand_match:
            pos = item.get("position")
            try:
                pos = int(pos)
            except Exception:
                continue
            matches.append({"position": pos, "title": title, "link": link})
    matches.sort(key=lambda x: x["position"])
    if not matches:
        return {
            "status": "live",
            "rank": None,
            "query": query,
            "source": "SerpAPI / Google.at",
            "message": "In den abgefragten organischen Ergebnissen nicht gefunden.",
            "matches": [],
        }
    return {
        "status": "live",
        "rank": matches[0]["position"],
        "query": query,
        "source": "SerpAPI / Google.at",
        "message": "Live organische Position für diese Abfrage.",
        "matches": matches[:5],
    }


def _public_benchmarks() -> list[dict]:
    """Return latest stored benchmark prices; these are indicative, not stay-specific."""
    out = []
    try:
        with legacy_app.db() as conn:
            rows = conn.execute(
                "SELECT competitor_name,source_key,checked_at,fetch_ok,metrics_json "
                "FROM market_competitor_observations ORDER BY competitor_name,checked_at DESC"
            ).fetchall()
        seen = set()
        for row in rows:
            name = str(row["competitor_name"] or "").strip()
            if not name or name in seen:
                continue
            try:
                metrics = json.loads(row["metrics_json"] or "{}")
            except Exception:
                metrics = {}
            value = metrics.get("price_eur")
            if value is None:
                continue
            try:
                price = round(float(value), 2)
            except Exception:
                continue
            seen.add(name)
            out.append({
                "name": name,
                "price_eur": price,
                "source": row["source_key"],
                "checked_at": row["checked_at"],
                "state": "live" if bool(row["fetch_ok"]) else "snapshot",
                "comparable": False,
                "note": "Öffentlich sichtbarer Benchmark; nicht als exakter Preis für das gewählte Datum gewertet.",
            })
    except Exception:
        pass
    return out


@app.get("/api/admin/rank-price-check")
def rank_price_check():
    if not _admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    query = " ".join((request.args.get("q") or DEFAULT_QUERY).split())[:180]
    room = (request.args.get("room") or "Bachblick").strip()
    if room not in legacy_app.ROOMS:
        return jsonify({"ok": False, "error": "unknown_room"}), 400
    try:
        arrival = date.fromisoformat(request.args.get("arrival") or date.today().isoformat())
        departure = date.fromisoformat(request.args.get("departure") or (arrival + timedelta(days=1)).isoformat())
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
        "price_rank_rule": "Nur Preise für exakt denselben Aufenthalt werden in der Oberfläche gerankt.",
    }), 200, {"Cache-Control": "no-store"}


PAGE = r'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rang & Preis | Zuhause am Bach</title><style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#17211f;background:#f4f6f4}*{box-sizing:border-box}body{margin:0}main{max-width:1100px;margin:auto;padding:24px}h1{margin:.2em 0}.sub{color:#5f6f69}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.card{background:#fff;border:1px solid #d8e2dd;border-radius:14px;padding:18px}.form{display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:10px;align-items:end}label{display:grid;gap:5px;font-weight:700;font-size:13px}input,select,button{min-height:44px;border:1px solid #c8d3cd;border-radius:9px;padding:9px 11px;font:inherit}button{background:#176b5a;color:white;border:0;font-weight:800;cursor:pointer}.big{font-size:44px;font-weight:900}.good{color:#176b5a}.warn{color:#9a6500}.bad{color:#a03525}.muted{color:#6c7973;font-size:13px}.comp{display:grid;grid-template-columns:1.6fr 1fr auto;gap:8px;margin:8px 0}.row{display:flex;justify-content:space-between;gap:16px;border-top:1px solid #edf0ee;padding:10px 0}.tag{font-size:12px;padding:3px 8px;background:#eef5f0;border-radius:99px}.status{margin-top:12px;padding:10px;background:#f1f5f2;border-radius:9px}@media(max-width:800px){.grid{grid-template-columns:1fr}.form{grid-template-columns:1fr 1fr}.form .wide{grid-column:1/-1}.comp{grid-template-columns:1fr 1fr}.comp button{grid-column:1/-1}}
</style></head><body><main><p><a href="/admin">← Admin</a></p><h1>Rang & Preis</h1><p class="sub">Eine Abfrage zeigt den organischen Google-Rang und euren exakten Direktpreis. Wettbewerberpreise für denselben Aufenthalt eintragen → Preisrang wird sofort berechnet.</p><section class="card"><form id="f" class="form"><label class="wide">Google-Suchbegriff<input id="q" value="unterkunft wachau nordufer" required></label><label>Zimmer<select id="room"><option>Bachblick</option><option>Marillenzimmer</option><option>Weinbergzimmer</option><option>Donauzimmer</option></select></label><label>Anreise<input id="arrival" type="date" required></label><label>Abreise<input id="departure" type="date" required></label><button>Jetzt prüfen</button></form><div id="msg" class="status">Bereit.</div></section><div class="grid" style="margin-top:16px"><section class="card"><h2>Google-Rang</h2><div id="rank" class="big">–</div><div id="rankNote" class="muted">Noch nicht abgefragt.</div></section><section class="card"><h2>Direktpreis</h2><div id="price" class="big">–</div><div id="priceNote" class="muted">Noch nicht abgefragt.</div></section></div><div class="grid" style="margin-top:16px"><section class="card"><h2>Preisrang für exakt denselben Aufenthalt</h2><div id="priceRank" class="big">–</div><p class="muted">Rang 1 = günstigster Preis. Trage nur Preise mit identischem Datum, Zimmerbelegung und vergleichbarer Leistung ein.</p><div id="competitors"></div><button id="add" type="button">+ Mitbewerber</button></section><section class="card"><h2>Öffentliche Benchmarks</h2><p class="muted">Nur Orientierung. Diese Werte werden nicht in den Preisrang gemischt, wenn sie nicht exakt zum gewählten Aufenthalt gehören.</p><div id="bench">Noch keine Daten.</div></section></div></main><script>
const f=document.getElementById('f'),q=document.getElementById('q'),room=document.getElementById('room'),arrival=document.getElementById('arrival'),departure=document.getElementById('departure'),msg=document.getElementById('msg'),rank=document.getElementById('rank'),rankNote=document.getElementById('rankNote'),price=document.getElementById('price'),priceNote=document.getElementById('priceNote'),priceRank=document.getElementById('priceRank'),competitors=document.getElementById('competitors'),bench=document.getElementById('bench');let own=null;
function localISO(d){const y=d.getFullYear(),m=String(d.getMonth()+1).padStart(2,'0'),day=String(d.getDate()).padStart(2,'0');return `${y}-${m}-${day}`}const today=new Date();const tomorrow=new Date(today);tomorrow.setDate(today.getDate()+1);arrival.value=localISO(today);departure.value=localISO(tomorrow);
function addComp(name='',value=''){const r=document.createElement('div');r.className='comp';r.innerHTML='<input class="n" placeholder="Mitbewerber" value="'+name.replaceAll('"','&quot;')+'"><input class="p" inputmode="decimal" type="number" min="0" step="0.01" placeholder="Preis €" value="'+value+'"><button type="button">Entfernen</button>';r.querySelector('button').addEventListener('click',()=>{r.remove();calc()});r.querySelector('.p').addEventListener('input',calc);competitors.appendChild(r)}
function calc(){if(own===null){priceRank.textContent='–';return}const vals=[{name:'Zuhause am Bach',price:own}];document.querySelectorAll('.comp').forEach(r=>{const p=Number(r.querySelector('.p').value),n=r.querySelector('.n').value||'Mitbewerber';if(Number.isFinite(p)&&p>0)vals.push({name:n,price:p})});vals.sort((a,b)=>a.price-b.price);const idx=vals.findIndex(x=>x.name==='Zuhause am Bach');priceRank.textContent=(idx+1)+' / '+vals.length;priceRank.className='big '+(idx===0?'good':idx===vals.length-1&&vals.length>1?'bad':'warn')}
document.getElementById('add').addEventListener('click',()=>addComp());addComp('Goldene Wachau','');addComp('Haus Gerstbauer','');
f.addEventListener('submit',async e=>{e.preventDefault();msg.textContent='Prüfe Rang und Preis …';rank.textContent='…';price.textContent='…';const u='/api/admin/rank-price-check?'+new URLSearchParams({q:q.value,room:room.value,arrival:arrival.value,departure:departure.value});try{const res=await fetch(u,{credentials:'same-origin',cache:'no-store'});const d=await res.json();if(!res.ok||!d.ok)throw new Error(d.message||d.error||'Fehler');own=Number(d.own_price.total_eur);price.textContent=own.toLocaleString('de-AT',{style:'currency',currency:'EUR'});priceNote.textContent=d.own_price.nights+' Nacht/Nächte · Ø '+Number(d.own_price.average_nightly_eur).toLocaleString('de-AT',{style:'currency',currency:'EUR'})+' pro Nacht';if(d.rank.rank!==null){rank.textContent='#'+d.rank.rank;rank.className='big good'}else{rank.textContent=d.rank.status==='not_configured'?'API fehlt':'>100 / nicht gefunden';rank.className='big warn'}rankNote.textContent=d.rank.message+' Quelle: '+d.rank.source;bench.innerHTML='';if(!d.public_benchmarks.length)bench.textContent='Noch keine belastbaren Benchmarkpreise gespeichert.';d.public_benchmarks.forEach(x=>{const r=document.createElement('div');r.className='row';r.innerHTML='<span><b>'+x.name+'</b><br><small>'+x.source+' · '+(x.checked_at||'')+'</small></span><span><b>'+Number(x.price_eur).toLocaleString('de-AT',{style:'currency',currency:'EUR'})+'</b><br><span class="tag">indikativ</span></span>';bench.appendChild(r)});calc();msg.textContent='Abfrage abgeschlossen.'}catch(err){msg.textContent='Fehler: '+err.message;rank.textContent='–';price.textContent='–'}});
</script></body></html>'''


@app.get("/admin/rank-preis")
def rank_price_page():
    if not _admin_ok():
        return redirect("/admin/login")
    return Response(PAGE, content_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/health/rank-price")
def rank_price_health():
    return {
        "ok": True,
        "dashboard": "/admin/rank-preis",
        "api": "/api/admin/rank-price-check",
        "serp_live_configured": bool(os.environ.get("SERPAPI_KEY", "").strip()),
        "target_domain": TARGET_DOMAIN,
        "price_source": "zab-direct-pricing-calendar",
    }, 200

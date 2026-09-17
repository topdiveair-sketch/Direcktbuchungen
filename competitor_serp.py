"""SERP snapshot for Zuhause am Bach and local accommodation competitors.

Uses one SerpAPI request per query and returns the organic position of the property
plus a normalized competitor table. Missing competitors are explicitly reported as
not found in the returned organic result set; no positions are estimated.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

from rank_price_gateway import SERP_LOCATION, TARGET_DOMAIN, TARGET_PATH

COMPETITORS = [
    {"name": "Goldene Wachau - Privatzimmer", "aliases": ["goldene wachau"]},
    {"name": "Haus Gerstbauer", "aliases": ["haus gerstbauer", "ferienwohnung gerstbauer"]},
    {"name": "Ferienwohnung Alte Post - Wachau", "aliases": ["alte post wachau", "ferienwohnung alte post", "alte post aggsbach"]},
    {"name": "Gästehaus Pumi", "aliases": ["gästehaus pumi", "gaestehaus pumi", "wachaupumi"]},
    {"name": "Gasthof zur Venus", "aliases": ["gasthof zur venus", "gasthaus zur venus"]},
    {"name": "Haus Birgit", "aliases": ["haus birgit aggsbach", "haus birgit wachau"]},
    {"name": "Haus Donaublick", "aliases": ["haus donaublick aggsbach", "haus donaublick wachau"]},
    {"name": "Landhaus Wachau", "aliases": ["landhaus wachau aggsbach", "landhaus wachau"]},
    {"name": "M-Haus", "aliases": ["m-haus aggsbach", "m haus aggsbach"]},
    {"name": "Villa Venus", "aliases": ["villa venus willendorf", "villa venus wachau"]},
    {"name": "Gasthof-Pension zum Kranz", "aliases": ["gasthof pension zum kranz", "gasthof-pension zum kranz", "zum kranz aggsbach"]},
]

KEYWORDS = [
    "unterkunft wachau nordufer",
    "unterkunft aggsbach markt",
    "privatzimmer wachau",
    "donauradweg unterkunft wachau",
    "welterbesteig unterkunft wachau",
]


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _own_match(item: dict) -> bool:
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
    brand_match = "zuhause am bach" in _norm(title + " " + snippet)
    return bool((domain_match and path_match) or brand_match)


def _position(item: dict) -> int | None:
    try:
        pos = int(item.get("position"))
        return pos if pos > 0 else None
    except Exception:
        return None


def _competitor_match(item: dict, aliases: list[str]) -> bool:
    title = _norm(str(item.get("title") or ""))
    snippet = _norm(str(item.get("snippet") or ""))
    link = _norm(str(item.get("link") or ""))
    haystack = f"{title} {snippet} {link}"
    return any(_norm(alias) in haystack for alias in aliases if alias)


def serp_snapshot(query: str) -> dict:
    query = " ".join((query or "").split())[:180]
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        rank = {
            "status": "not_configured",
            "rank": None,
            "query": query,
            "source": "SerpAPI",
            "message": "SERPAPI_KEY fehlt. Live-Rang wird absichtlich nicht geschätzt.",
        }
        return {
            "rank": rank,
            "competitor_rankings": [
                {"name": c["name"], "rank": None, "status": "not_configured", "title": "", "link": ""}
                for c in COMPETITORS
            ],
            "source": "SerpAPI",
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
    req = urllib.request.Request(url, headers={"User-Agent": "ZuhauseAmBach-CompetitorRank/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        rank = {
            "status": "error",
            "rank": None,
            "query": query,
            "source": "SerpAPI",
            "message": f"Live-Abfrage fehlgeschlagen: {type(exc).__name__}",
        }
        return {
            "rank": rank,
            "competitor_rankings": [
                {"name": c["name"], "rank": None, "status": "error", "title": "", "link": ""}
                for c in COMPETITORS
            ],
            "source": "SerpAPI",
        }

    organic = payload.get("organic_results") if isinstance(payload, dict) else []
    if not isinstance(organic, list):
        organic = []

    own_matches = []
    for item in organic:
        if isinstance(item, dict) and _own_match(item):
            pos = _position(item)
            if pos is not None:
                own_matches.append({
                    "position": pos,
                    "title": str(item.get("title") or ""),
                    "link": str(item.get("link") or ""),
                })
    own_matches.sort(key=lambda row: row["position"])
    if own_matches:
        rank = {
            "status": "live",
            "rank": own_matches[0]["position"],
            "query": query,
            "source": "SerpAPI / Google.at",
            "message": "Live organische Position für diese Abfrage.",
            "matches": own_matches[:5],
        }
    else:
        rank = {
            "status": "live",
            "rank": None,
            "query": query,
            "source": "SerpAPI / Google.at",
            "message": "In den abgefragten organischen Ergebnissen nicht gefunden.",
            "matches": [],
        }

    competitor_rows = []
    for competitor in COMPETITORS:
        matches = []
        for item in organic:
            if not isinstance(item, dict) or not _competitor_match(item, competitor["aliases"]):
                continue
            pos = _position(item)
            if pos is None:
                continue
            matches.append({
                "position": pos,
                "title": str(item.get("title") or ""),
                "link": str(item.get("link") or ""),
            })
        matches.sort(key=lambda row: row["position"])
        first = matches[0] if matches else None
        competitor_rows.append({
            "name": competitor["name"],
            "rank": first["position"] if first else None,
            "status": "live" if first else "not_found",
            "title": first["title"] if first else "",
            "link": first["link"] if first else "",
            "matches": matches[:3],
        })

    competitor_rows.sort(key=lambda row: (row["rank"] is None, row["rank"] or 9999, row["name"].lower()))
    return {
        "rank": rank,
        "competitor_rankings": competitor_rows,
        "source": "SerpAPI / Google.at",
        "query": query,
        "result_count": len(organic),
    }

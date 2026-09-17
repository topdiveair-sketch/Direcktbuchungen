from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date


COMPETITORS = [
    ("Goldene Wachau - Privatzimmer", ["goldene wachau", "privatzimmer goldene wachau"]),
    ("Haus Gerstbauer", ["haus gerstbauer", "gerstbauer"]),
    ("Ferienwohnung Alte Post - Wachau", ["ferienwohnung alte post", "alte post wachau"]),
    ("Gästehaus Pumi", ["gästehaus pumi", "gaestehaus pumi", "pumi"]),
    ("Gasthof zur Venus", ["gasthof zur venus", "zur venus"]),
    ("Haus Birgit", ["haus birgit"]),
    ("Haus Donaublick", ["haus donaublick", "donaublick"]),
    ("Landhaus Wachau", ["landhaus wachau"]),
    ("M-Haus", ["m-haus", "m haus"]),
    ("Villa Venus", ["villa venus"]),
    ("Gasthof-Pension zum Kranz", ["gasthof-pension zum kranz", "gasthof pension zum kranz", "zum kranz"]),
]


def _norm(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _number(value: object):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("\xa0", " ")
    match = re.search(r"([0-9]{1,5}(?:[.,][0-9]{1,2})?)", raw.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _extract_price(prop: dict):
    candidates = []
    for key in ("rate_per_night", "total_rate"):
        block = prop.get(key)
        if isinstance(block, dict):
            for nested in ("extracted_lowest", "lowest", "extracted_before_taxes_fees", "before_taxes_fees"):
                if nested in block:
                    candidates.append(block.get(nested))
        elif block is not None:
            candidates.append(block)
    for key in ("extracted_price", "price", "lowest_rate", "rate"):
        if key in prop:
            candidates.append(prop.get(key))
    for candidate in candidates:
        num = _number(candidate)
        if num is not None and 20 <= num <= 5000:
            return round(num, 2)
    return None


def _match_name(property_name: str):
    normalized = _norm(property_name)
    if not normalized:
        return None
    for canonical, aliases in COMPETITORS:
        for alias in aliases:
            n_alias = _norm(alias)
            if n_alias and (n_alias in normalized or normalized in n_alias):
                return canonical
    return None


def hotel_price_snapshot(arrival: date, departure: date) -> dict:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "SERPAPI_KEY fehlt", "prices": []}
    if departure <= arrival:
        return {"ok": False, "error": "Abreise muss nach Anreise liegen", "prices": []}

    params = {
        "engine": "google_hotels",
        "q": "Aggsbach Markt Wachau Austria",
        "check_in_date": arrival.isoformat(),
        "check_out_date": departure.isoformat(),
        "adults": "2",
        "currency": "EUR",
        "gl": "at",
        "hl": "de",
        "api_key": key,
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ZuhauseAmBach-RangPreis/1.5", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=28) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": f"Google-Hotels-Abfrage fehlgeschlagen: {type(exc).__name__}", "prices": []}

    if not isinstance(payload, dict):
        return {"ok": False, "error": "Ungültige Google-Hotels-Antwort", "prices": []}
    if payload.get("error"):
        return {"ok": False, "error": str(payload.get("error")), "prices": []}

    properties = payload.get("properties") or []
    if not isinstance(properties, list):
        properties = []

    found = {}
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        display_name = str(prop.get("name") or prop.get("title") or "").strip()
        canonical = _match_name(display_name)
        if not canonical:
            continue
        price = _extract_price(prop)
        if price is None:
            continue
        current = found.get(canonical)
        if current is None or price < current["price_eur"]:
            found[canonical] = {
                "name": canonical,
                "price_eur": price,
                "source": "Google Hotels / SerpAPI",
                "checked_at": "live",
                "state": "live",
                "comparable": True,
                "arrival": arrival.isoformat(),
                "departure": departure.isoformat(),
                "adults": 2,
                "matched_property": display_name,
                "note": "Datumsbezogener öffentlich sichtbarer Google-Hotels-Preis für 2 Erwachsene; Tarifbedingungen können abweichen.",
            }

    return {
        "ok": True,
        "source": "Google Hotels / SerpAPI",
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "adults": 2,
        "property_count": len(properties),
        "prices": list(found.values()),
    }

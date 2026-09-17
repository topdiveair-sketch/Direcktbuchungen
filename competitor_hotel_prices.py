from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta


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


def _block_price(block):
    if isinstance(block, dict):
        for key in ("extracted_lowest", "extracted_before_taxes_fees", "lowest", "before_taxes_fees"):
            if key in block:
                num = _number(block.get(key))
                if num is not None and 20 <= num <= 10000:
                    return round(num, 2)
    else:
        num = _number(block)
        if num is not None and 20 <= num <= 10000:
            return round(num, 2)
    return None


def _extract_prices(prop: dict, nights: int) -> tuple[float | None, float | None]:
    nightly = _block_price(prop.get("rate_per_night"))
    total = _block_price(prop.get("total_rate"))

    if nightly is None:
        for key in ("extracted_price", "price", "lowest_rate", "rate"):
            if key in prop:
                nightly = _number(prop.get(key))
                if nightly is not None:
                    nightly = round(nightly, 2)
                    break

    if total is None and nightly is not None:
        total = round(nightly * nights, 2)
    if nightly is None and total is not None and nights > 0:
        nightly = round(total / nights, 2)

    if nightly is not None and not 20 <= nightly <= 5000:
        nightly = None
    if total is not None and not 20 <= total <= 20000:
        total = None
    return nightly, total


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

    nights = (departure - arrival).days
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
        headers={"User-Agent": "ZuhauseAmBach-RangPreis/1.6", "Accept": "application/json"},
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
        nightly, total = _extract_prices(prop, nights)
        if nightly is None and total is None:
            continue
        current = found.get(canonical)
        candidate_total = total if total is not None else float("inf")
        current_total = current.get("total_eur") if current else None
        if current is None or current_total is None or candidate_total < current_total:
            found[canonical] = {
                "name": canonical,
                "nightly_eur": nightly,
                "total_eur": total,
                "nights": nights,
                "source": "Google Hotels / SerpAPI",
                "arrival": arrival.isoformat(),
                "departure": departure.isoformat(),
                "adults": 2,
                "matched_property": display_name,
            }

    return {
        "ok": True,
        "source": "Google Hotels / SerpAPI",
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "nights": nights,
        "adults": 2,
        "property_count": len(properties),
        "prices": list(found.values()),
    }


def competitor_stay_matrix(arrival: date) -> dict:
    """Compare every known competitor for 1-night and 3-night stays from the same arrival date."""
    one = hotel_price_snapshot(arrival, arrival + timedelta(days=1))
    three = hotel_price_snapshot(arrival, arrival + timedelta(days=3))

    one_map = {row["name"]: row for row in (one.get("prices") or []) if isinstance(row, dict) and row.get("name")}
    three_map = {row["name"]: row for row in (three.get("prices") or []) if isinstance(row, dict) and row.get("name")}

    rows = []
    for canonical, _aliases in COMPETITORS:
        r1 = one_map.get(canonical) or {}
        r3 = three_map.get(canonical) or {}
        one_total = r1.get("total_eur")
        three_total = r3.get("total_eur")
        three_nightly = r3.get("nightly_eur")
        if three_nightly is None and three_total is not None:
            try:
                three_nightly = round(float(three_total) / 3, 2)
            except Exception:
                three_nightly = None

        if one_total is not None:
            availability = "1 Nacht buchbar"
        elif three_total is not None:
            availability = "ab 3 Nächten"
        else:
            availability = "kein Preis gefunden"

        rows.append({
            "name": canonical,
            "price_eur": one_total if one_total is not None else three_nightly,
            "one_night_total_eur": one_total,
            "three_night_total_eur": three_total,
            "three_night_average_eur": three_nightly,
            "availability": availability,
            "source": "Google Hotels / SerpAPI",
            "checked_at": "live",
            "state": "live" if (one_total is not None or three_total is not None) else "unavailable",
            "comparable": one_total is not None,
            "arrival": arrival.isoformat(),
            "adults": 2,
            "matched_property_1n": r1.get("matched_property", ""),
            "matched_property_3n": r3.get("matched_property", ""),
            "note": "Google-Hotels-Preise für 2 Erwachsene, gleicher Anreisetag; 1 Nacht und 3 Nächte werden getrennt abgefragt.",
        })

    errors = []
    if not one.get("ok"):
        errors.append("1 Nacht: " + str(one.get("error") or "Fehler"))
    if not three.get("ok"):
        errors.append("3 Nächte: " + str(three.get("error") or "Fehler"))

    return {
        "ok": bool(one.get("ok") or three.get("ok")),
        "source": "Google Hotels / SerpAPI",
        "arrival": arrival.isoformat(),
        "adults": 2,
        "rows": rows,
        "one_night_property_count": one.get("property_count") or 0,
        "three_night_property_count": three.get("property_count") or 0,
        "one_night_match_count": len(one_map),
        "three_night_match_count": len(three_map),
        "error": " | ".join(errors),
    }

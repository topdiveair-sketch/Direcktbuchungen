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


def _tokens(value: object) -> set[str]:
    return {t for t in _norm(value).split() if len(t) >= 2 and t not in {"haus", "hotel", "pension", "gasthof", "wachau"}}


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
    if nightly is None and isinstance(prop.get("prices"), list):
        candidates = []
        for price_row in prop.get("prices") or []:
            if not isinstance(price_row, dict):
                continue
            value = _block_price(price_row.get("rate_per_night"))
            if value is None:
                value = _number(price_row.get("extracted_price"))
            if value is not None and 20 <= value <= 5000:
                candidates.append(float(value))
        if candidates:
            nightly = round(min(candidates), 2)
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


def _target_match_score(canonical: str, aliases: list[str], display_name: str) -> float:
    dn = _norm(display_name)
    if not dn:
        return 0.0
    variants = [canonical] + aliases
    best = 0.0
    for variant in variants:
        vn = _norm(variant)
        if not vn:
            continue
        if vn == dn:
            return 1.0
        if vn in dn or dn in vn:
            best = max(best, 0.95)
        vt = _tokens(vn)
        dt = _tokens(dn)
        if vt and dt:
            overlap = len(vt & dt) / max(1, len(vt))
            best = max(best, overlap)
    return best


def _collect_property_candidates(payload: dict) -> list[dict]:
    """Collect Google Hotels results from list and exact-property response shapes."""
    out: list[dict] = []
    seen = set()

    def add(item):
        if not isinstance(item, dict):
            return
        name = str(item.get("name") or item.get("title") or "").strip()
        if not name:
            return
        token = str(item.get("property_token") or "").strip()
        key = (token, _norm(name))
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    for field in ("properties", "ads", "non_matching_properties"):
        rows = payload.get(field) or []
        if isinstance(rows, list):
            for row in rows:
                add(row)

    # Exact q searches may return property details at the top level rather than
    # inside `properties`. This is documented by SerpAPI/Google Hotels.
    if payload.get("name") and (
        payload.get("type") in {"hotel", "vacation rental"}
        or payload.get("property_token")
        or payload.get("rate_per_night")
        or payload.get("prices")
    ):
        add(payload)

    return out


def _google_hotels(query: str, arrival: date, departure: date, vacation_rentals: bool = False) -> dict:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "SERPAPI_KEY fehlt", "properties": []}
    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": arrival.isoformat(),
        "check_out_date": departure.isoformat(),
        "adults": "2",
        "currency": "EUR",
        "gl": "at",
        "hl": "de",
        "api_key": key,
    }
    if vacation_rentals:
        params["vacation_rentals"] = "true"
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ZuhauseAmBach-RangPreis/1.8", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=28) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": f"Google-Hotels-Abfrage fehlgeschlagen: {type(exc).__name__}", "properties": []}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Ungültige Google-Hotels-Antwort", "properties": []}
    if payload.get("error"):
        return {"ok": False, "error": str(payload.get("error")), "properties": []}
    return {
        "ok": True,
        "properties": _collect_property_candidates(payload),
        "results_state": str((payload.get("search_information") or {}).get("hotels_results_state") or ""),
        "vacation_rentals": vacation_rentals,
    }


def _row_from_property(canonical: str, prop: dict, arrival: date, departure: date, source_note: str) -> dict | None:
    nights = (departure - arrival).days
    nightly, total = _extract_prices(prop, nights)
    if nightly is None and total is None:
        return None
    display_name = str(prop.get("name") or prop.get("title") or "").strip()
    return {
        "name": canonical,
        "nightly_eur": nightly,
        "total_eur": total,
        "nights": nights,
        "source": "Google Hotels / SerpAPI",
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "adults": 2,
        "matched_property": display_name,
        "match_method": source_note,
    }


def _best_targeted_match(canonical: str, aliases: list[str], properties: list[dict], arrival: date, departure: date, method: str):
    candidates = []
    for prop in properties or []:
        if not isinstance(prop, dict):
            continue
        display_name = str(prop.get("name") or prop.get("title") or "").strip()
        score = _target_match_score(canonical, aliases, display_name)
        if score < 0.55:
            continue
        row = _row_from_property(canonical, prop, arrival, departure, method)
        if row is not None:
            candidates.append((score, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].get("total_eur") or 999999))
    return candidates[0][1]


def hotel_price_snapshot(arrival: date, departure: date) -> dict:
    if departure <= arrival:
        return {"ok": False, "error": "Abreise muss nach Anreise liegen", "prices": []}

    broad = _google_hotels("Aggsbach Markt Wachau Austria", arrival, departure)
    if not broad.get("ok"):
        return {"ok": False, "error": broad.get("error") or "Google Hotels nicht verfügbar", "prices": []}

    found: dict[str, dict] = {}
    properties = broad.get("properties") or []
    for prop in properties:
        if not isinstance(prop, dict):
            continue
        display_name = str(prop.get("name") or prop.get("title") or "").strip()
        canonical = _match_name(display_name)
        if not canonical:
            continue
        row = _row_from_property(canonical, prop, arrival, departure, "Sammelsuche")
        if row is None:
            continue
        current = found.get(canonical)
        if current is None or (row.get("total_eur") or 999999) < (current.get("total_eur") or 999999):
            found[canonical] = row

    targeted_calls = 0
    targeted_errors = []
    for canonical, aliases in COMPETITORS:
        if canonical in found:
            continue

        # Exact property search first. Do not quote q: Google Hotels can return
        # exact property details as a top-level object for an exact-name query.
        query = f"{canonical} Aggsbach Wachau Austria"
        targeted = _google_hotels(query, arrival, departure)
        targeted_calls += 1
        if not targeted.get("ok"):
            targeted_errors.append(f"{canonical}: {targeted.get('error') or 'Fehler'}")
            continue

        best = _best_targeted_match(
            canonical, aliases, targeted.get("properties") or [], arrival, departure, "gezielte Hotelsuche"
        )

        # Ferienwohnungen/Gästehäuser may only appear in Google's vacation-rental
        # result mode. Retry that mode only when the normal targeted search did
        # not produce a priced match.
        if best is None:
            rental = _google_hotels(query, arrival, departure, vacation_rentals=True)
            targeted_calls += 1
            if rental.get("ok"):
                best = _best_targeted_match(
                    canonical, aliases, rental.get("properties") or [], arrival, departure, "gezielte Ferienwohnungs-Suche"
                )
            elif rental.get("error"):
                targeted_errors.append(f"{canonical} Ferienwohnung: {rental.get('error')}")

        if best is not None:
            found[canonical] = best

    return {
        "ok": True,
        "source": "Google Hotels / SerpAPI",
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "nights": (departure - arrival).days,
        "adults": 2,
        "property_count": len(properties),
        "targeted_calls": targeted_calls,
        "targeted_errors": targeted_errors[:10],
        "prices": list(found.values()),
    }


def competitor_stay_matrix(arrival: date) -> dict:
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
            availability = "kein öffentlicher Preis gefunden"
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
            "match_method_1n": r1.get("match_method", ""),
            "match_method_3n": r3.get("match_method", ""),
            "note": "Google-Hotels-Preise für 2 Erwachsene, gleicher Anreisetag; Sammelsuche, exakte Hotelsuche und Ferienwohnungs-Fallback.",
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
        "targeted_calls_1n": one.get("targeted_calls") or 0,
        "targeted_calls_3n": three.get("targeted_calls") or 0,
        "error": " | ".join(errors),
    }

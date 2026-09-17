from __future__ import annotations

"""Describe multi-room / multi-unit competitors without inventing room prices.

The live Google-Hotels lookup often exposes only the cheapest available offer for
an entire property. This module makes that limitation explicit and attaches known
published unit categories where we have a reliable public list.
"""


PROPERTY_META = {
    "Goldene Wachau - Privatzimmer": {
        "multi_unit": True,
        "unit_count": 5,
        "unit_summary": "5 veröffentlichte Zimmer-/Apartmentkategorien",
        "published_offers": [
            {"unit": "Salamandl", "nightly_from_eur": 160.0, "occupancy": "2 Personen"},
            {"unit": "Kuenringer", "nightly_from_eur": 160.0, "occupancy": "2 Personen"},
            {"unit": "Wachauerin", "nightly_from_eur": 160.0, "occupancy": "2 Personen"},
            {"unit": "Suite Goldene Wachau", "nightly_from_eur": 180.0, "occupancy": "2 Personen"},
            {"unit": "Appartement Accusabah", "nightly_from_eur": 290.0, "occupancy": "4 Personen"},
        ],
    },
    "Gasthof zur Venus": {
        "multi_unit": True,
        "unit_count": 6,
        "unit_summary": "6 Gästezimmer; öffentliche Quelle liefert nicht zuverlässig je Zimmer einen eigenen Tarif",
        "published_offers": [],
    },
    "Haus Gerstbauer": {
        "multi_unit": True,
        "unit_count": None,
        "unit_summary": "mehrere Unterkunftseinheiten; Einzelpreise können je Einheit abweichen",
        "published_offers": [],
    },
    "Ferienwohnung Alte Post - Wachau": {
        "multi_unit": False,
        "unit_count": 1,
        "unit_summary": "Ferienwohnung",
        "published_offers": [],
    },
    "Donauhaus - Natur": {
        "multi_unit": False,
        "unit_count": 1,
        "unit_summary": "gesamtes Ferienhaus; nicht 1:1 mit einem Doppelzimmer vergleichbar",
        "published_offers": [],
    },
}


def _offer_rows(meta: dict) -> list[dict]:
    rows = []
    for offer in meta.get("published_offers") or []:
        nightly = offer.get("nightly_from_eur")
        try:
            nightly = round(float(nightly), 2)
        except (TypeError, ValueError):
            continue
        rows.append({
            "unit": str(offer.get("unit") or "Zimmer/Einheit"),
            "occupancy": str(offer.get("occupancy") or ""),
            "one_night_total_eur": nightly,
            "three_night_total_eur": round(nightly * 3, 2),
            "three_night_average_eur": nightly,
            "price_scope": "veröffentlichter Ab-Preis je Einheit",
            "source_kind": "published_unit_rate",
        })
    return rows


def apply_inventory_context(rows: list[dict]) -> list[dict]:
    out = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        name = str(row.get("name") or "").strip()
        meta = PROPERTY_META.get(name, {})

        row["multi_unit"] = bool(meta.get("multi_unit", False))
        row["unit_count"] = meta.get("unit_count")
        row["unit_summary"] = str(meta.get("unit_summary") or "")
        row["unit_offers"] = _offer_rows(meta)

        state = str(row.get("state") or "")
        has_price = row.get("one_night_total_eur") is not None or row.get("three_night_total_eur") is not None
        if state == "live" and has_price:
            row["price_scope"] = "günstigstes gefundenes Angebot"
            row["comparison_level"] = "Marktuntergrenze, Zimmerkategorie nicht sicher zugeordnet"
            row["comparable"] = False
        elif state in {"published_from", "published_rate"} and has_price:
            row["price_scope"] = "veröffentlichter Ab-Preis"
            row["comparison_level"] = "veröffentlichter Richtwert, keine Live-Verfügbarkeit"
            row["comparable"] = False
        elif state == "inquiry":
            row["price_scope"] = "kein öffentlicher Preis"
            row["comparison_level"] = "nicht preislich vergleichbar"
        else:
            row["price_scope"] = row.get("price_scope") or ("günstigstes gefundenes Angebot" if has_price else "kein Preis")
            if has_price:
                row["comparable"] = False

        if row["multi_unit"] and row["unit_summary"]:
            note = str(row.get("note") or "").strip()
            inventory_note = f"Mehrere Einheiten berücksichtigt: {row['unit_summary']}."
            row["note"] = f"{note} {inventory_note}".strip()

        out.append(row)
    return out

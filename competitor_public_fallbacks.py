from __future__ import annotations

from datetime import date


INQUIRY_ONLY = {
    "Gästehaus Pumi": "Öffentlich ist derzeit nur eine direkte Anfrage/Kontaktmöglichkeit auffindbar.",
    "Villa Venus": "Booking/öffentliche Unterkunftsseiten vorhanden, aber kein belastbarer öffentlicher Preis für das gewählte Datum verfügbar.",
    "Gasthof-Pension zum Kranz": "Kein belastbarer öffentlicher Zimmerpreis gefunden; Anfrage erforderlich.",
    "M-Haus": "Kein belastbarer öffentlicher Zimmerpreis gefunden; Anfrage erforderlich.",
    "Landhaus Wachau": "Booking-Eintrag vorhanden, aber kein belastbarer öffentlicher Preis für das gewählte Datum verfügbar.",
}


def _alte_post_rate(arrival: date) -> float | None:
    # Published 2026 rates for the 2-person apartment. Cleaning and visitor tax
    # are published separately and therefore included below in the stay total.
    periods = (
        (date(2026, 4, 11), date(2026, 5, 3), 110.0),
        (date(2026, 5, 3), date(2026, 6, 20), 100.0),
        (date(2026, 9, 9), date(2026, 10, 3), 110.0),
    )
    for start, end, nightly in periods:
        if start <= arrival < end:
            return nightly
    return None


def _published_from(row: dict, one_total: float, source: str, note: str) -> None:
    one_total = round(float(one_total), 2)
    three_total = round(one_total * 3, 2)
    row.update({
        "one_night_total_eur": one_total,
        "three_night_total_eur": three_total,
        "three_night_average_eur": one_total,
        "price_eur": one_total,
        "availability": "veröffentlichter Ab-Preis",
        "state": "published_from",
        "comparable": False,
        "price_kind": "published_from",
        "source": source,
        "note": note,
    })


def apply_public_fallbacks(rows: list[dict], arrival: date, adults: int = 2) -> list[dict]:
    """Enrich missing live rows with published public rates/status.

    Fallback values are explicitly labelled as published 'from' prices and are
    never presented as live OTA availability. Exact live Google/OTA values win.
    """
    out = []
    for raw in rows or []:
        row = dict(raw) if isinstance(raw, dict) else {}
        name = str(row.get("name") or "").strip()
        has_live = row.get("one_night_total_eur") is not None or row.get("three_night_total_eur") is not None
        if has_live:
            out.append(row)
            continue

        if name == "Haus Gerstbauer":
            _published_from(
                row,
                72.60,
                "preiswert-uebernachten.de / Haus Gerstbauer",
                "Veröffentlicht: günstigster Preis ab 72,60 € pro Zimmer und Nacht; abhängig von Saison, Auslastung und Aufenthaltsdauer. Kein Live-Verfügbarkeitsnachweis für das gewählte Datum.",
            )
        elif name == "Haus Birgit":
            _published_from(
                row,
                50.0,
                "Marktgemeinde Aggsbach / Gastgeberverzeichnis",
                "Veröffentlicht: ab 50 € für 2 Personen; Nächtigungstaxe laut Gastgeberverzeichnis nicht enthalten. Kein Live-Verfügbarkeitsnachweis für das gewählte Datum.",
            )
        elif name == "Haus Donaublick":
            per_person = 65.0
            one_total = round(per_person * adults, 2)
            three_total = round(one_total * 3, 2)
            row.update({
                "one_night_total_eur": one_total,
                "three_night_total_eur": three_total,
                "three_night_average_eur": one_total,
                "price_eur": one_total,
                "availability": "veröffentlichter Ab-Preis",
                "state": "published_from",
                "comparable": False,
                "price_kind": "published_from",
                "source": "Donauregion / Haus Donaublick",
                "note": "Veröffentlicht: ab 65 € pro Person und Nacht. Für 2 Erwachsene hochgerechnet; kein Live-Verfügbarkeitsnachweis.",
            })
        elif name == "Ferienwohnung Alte Post - Wachau":
            nightly = _alte_post_rate(arrival)
            if nightly is not None:
                cleaning = 80.0
                tax_pp_night = 4.0
                one_total = nightly + cleaning + tax_pp_night * adults
                three_total = nightly * 3 + cleaning + tax_pp_night * adults * 3
                row.update({
                    "one_night_total_eur": round(one_total, 2),
                    "three_night_total_eur": round(three_total, 2),
                    "three_night_average_eur": round(three_total / 3, 2),
                    "price_eur": round(one_total, 2),
                    "availability": "veröffentlichter 2026-Preis",
                    "state": "published_rate",
                    "comparable": False,
                    "price_kind": "published_rate",
                    "source": "Offizielle Preisseite Alte Post",
                    "note": "2-Personen-Preis laut veröffentlichter 2026-Preisliste inkl. 80 € Endreinigung und 4 € Ortstaxe pro Person/Nacht; kein Live-Verfügbarkeitsnachweis.",
                })
            else:
                row.update({
                    "availability": "außerhalb veröffentlichter Preiszeiträume",
                    "state": "inquiry",
                    "price_kind": "inquiry",
                })
        elif name in INQUIRY_ONLY:
            row.update({
                "availability": "nur auf Anfrage",
                "state": "inquiry",
                "price_kind": "inquiry",
                "note": INQUIRY_ONLY[name],
            })
        else:
            row.update({
                "availability": row.get("availability") or "kein öffentlicher Preis",
                "state": row.get("state") or "unavailable",
            })
        out.append(row)
    return out

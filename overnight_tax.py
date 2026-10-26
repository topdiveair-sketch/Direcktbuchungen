"""Transparent Lower Austrian overnight tax display for direct-booking guests.
The statutory tax is collected separately; payment processor amounts are unchanged.
Only formally published rates may be represented as final amounts.
"""
from datetime import timedelta

OVERNIGHT_TAX_SOURCE = "https://www.noe.gv.at/noe/Wirtschaft-Tourismus-Technologie/Naechtigungstaxensaetze.html"
PUBLISHED_NON_SPA_RATES = {2026: 2.60, 2027: 2.70}


def overnight_tax_breakdown(arrival, departure, adults):
    guests = max(0, int(adults))
    days = max(0, (departure - arrival).days)
    lines = []
    known = True
    amount = 0.0
    current = arrival
    for _ in range(days):
        rate = PUBLISHED_NON_SPA_RATES.get(current.year)
        if rate is None:
            known = False
        else:
            subtotal = round(rate * guests, 2)
            amount = round(amount + subtotal, 2)
            if lines and lines[-1]["year"] == current.year:
                lines[-1]["nights"] += 1
                lines[-1]["amount"] = round(lines[-1]["amount"] + subtotal, 2)
            else:
                lines.append({"year": current.year, "nights": 1, "guests": guests,
                              "rate": rate, "amount": subtotal})
        current += timedelta(days=1)
    return {
        "known": known,
        "amount": round(amount, 2) if known else None,
        "lines": lines,
        "guests": guests,
        "nights": days,
        "separate_payment": True,
        "source": OVERNIGHT_TAX_SOURCE,
        "note": "Die Nächtigungstaxe wird gesondert bei der Anreise bezahlt."
                if known else "Der amtliche Nächtigungstaxensatz für einen Teil des Zeitraums ist noch nicht veröffentlicht. "
                              "Die endgültigen Gesamtkosten können erst nach Veröffentlichung bestimmt werden.",
    }


def with_guest_stay_costs(breakdown, arrival, departure, adults):
    """Enrich an existing quote without changing its processor payment amount."""
    tax = overnight_tax_breakdown(arrival, departure, adults)
    booked = round(float(breakdown["total"]), 2)
    return {
        **breakdown,
        "online_total": booked,
        "overnight_tax": tax,
        "stay_total": round(booked + tax["amount"], 2) if tax["known"] else None,
        "stay_total_known": tax["known"],
    }

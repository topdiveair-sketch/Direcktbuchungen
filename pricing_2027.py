from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "pricing-2027.json"


@lru_cache(maxsize=1)
def pricing_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse(value: str) -> date:
    return date.fromisoformat(value)


def _contains(day: date, row: dict) -> bool:
    return _parse(row["start"]) <= day <= _parse(row["end"])


def nightly_direct_rate(day: date) -> float | None:
    """Return the final direct-booking room rate for one 2027 night.

    Date overrides have priority over the seasonal weekday/weekend grid.
    The configured minimum price is enforced defensively.
    Returns None outside the configured year so the caller can fall back to
    the application's existing pricing model.
    """
    cfg = pricing_config()
    if day.year != int(cfg["year"]):
        return None

    floor = float(cfg["minimum_direct_price_eur"])

    for row in cfg.get("date_overrides", []):
        if _contains(day, row):
            return max(floor, float(row["price_eur"]))

    for row in cfg.get("season_ranges", []):
        if _contains(day, row):
            key = "fri_sat" if day.weekday() in (4, 5) else "sun_thu"
            return max(floor, float(row[key]))

    return floor


def stay_room_total(arrival: date, departure: date) -> float:
    """Calculate room-only total from the 2027 direct rate grid."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")

    total = 0.0
    current = arrival
    while current < departure:
        nightly = nightly_direct_rate(current)
        if nightly is None:
            raise ValueError("stay contains a date outside the 2027 pricing calendar")
        total += nightly
        current += timedelta(days=1)
    return round(total, 2)


def event_label(day: date) -> str | None:
    """Return the configured event/holiday label for a date override."""
    cfg = pricing_config()
    for row in cfg.get("date_overrides", []):
        if _contains(day, row):
            return str(row.get("label") or "") or None
    return None

"""Fail-closed calendar gate for future live card checkout.

Read-only validation: never mutate the calendar or payment state. A successful
provider count alone is not proof of fresh inventory; supply the timestamp from
the SAME sync attempt and the expected provider coverage explicitly.
"""
from datetime import datetime, timezone

DEFAULT_REQUIRED_SOURCES = frozenset({"booking_ical", "beds24_ical", "airbnb_ical"})


def card_checkout_calendar_ready(
    configured_sources, last_result, sync_success, *,
    synced_at=None, now=None, required_sources=DEFAULT_REQUIRED_SOURCES,
    max_age_seconds=300,
):
    """Return (ready, reason), failing closed on incomplete or stale feeds.

    synced_at and now must be timezone-aware datetime values. An absent or
    invalid timestamp is rejected, not treated as a successful sync.
    """
    sources = list(configured_sources)
    if not sources or not sync_success or not isinstance(last_result, str):
        return False, "No verified external calendar sync"
    if not isinstance(synced_at, datetime) or synced_at.tzinfo is None:
        return False, "Missing timezone-aware sync timestamp"
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        return False, "Invalid current timestamp"
    age = (now - synced_at).total_seconds()
    if not (0 <= age <= max_age_seconds <= 3600):
        return False, "External calendar sync is stale or invalid"
    if not last_result.strip():
        return False, "Missing external calendar sync report"

    parsed = []
    for entry in sources:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            return False, "Invalid calendar source configuration"
        code, label, url = entry
        if not all(isinstance(v, str) and v.strip() for v in (code, label, url)):
            return False, "Invalid calendar source configuration"
        parsed.append((code, label))

    codes = [code for code, _ in parsed]
    if len(set(codes)) != len(codes) or not set(required_sources).issubset(codes):
        return False, "Required calendar feed missing or duplicated"

    reports = last_result.split(" · ")
    if len(reports) != len(parsed):
        return False, "External calendar source count mismatch"
    for (_, label), report in zip(parsed, reports):
        prefix = label + ": "
        if not report.startswith(prefix):
            return False, "Missing or reordered provider result"
        remainder = report[len(prefix):]
        # Only nonnegative integer event counts, optionally followed by the
        # explicit successful retry suffix, are accepted.
        number = remainder.removesuffix(" (nach Retry)")
        if not number.isdecimal() or not number.isascii():
            return False, "External calendar provider failed"
    return True, "All required external calendars refreshed"

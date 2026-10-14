"""Fail-closed external calendar sync gate for future live card checkout.

The current sync_room() intentionally reports success when any provider updates.
That is useful for cached occupancy, but insufficient for instant, paid bookings.
Use this gate only after a fresh sync, using the exact configured provider list
and the summary returned from the same sync attempt. Never accept missing feeds.
"""


def card_checkout_calendar_ready(configured_sources, last_result, sync_success):
    """Return (ready, reason) without changing any calendar or booking.

    configured_sources: iterable of (source_code, display_label, url), as
    returned by the host application's _calendar_sources_for_room().
    """
    sources = list(configured_sources)
    if not sources or not sync_success or not isinstance(last_result, str):
        return False, "No verified external calendar sync"
    if not last_result.strip():
        return False, "Missing external calendar sync report"
    reports = last_result.split(" · ")
    expected_labels = [label for _, label, url in sources if isinstance(url, str) and url.strip()]
    if len(expected_labels) != len(sources) or len(reports) != len(expected_labels):
        return False, "External calendar source count mismatch"
    for label, report in zip(expected_labels, reports):
        prefix = label + ": "
        if not report.startswith(prefix):
            return False, "Missing or reordered provider result"
        remainder = report[len(prefix):]
        count = remainder.split(" ", 1)[0]
        if not count.isdecimal():
            return False, "External calendar provider failed"
    return True, "All configured external calendars refreshed"

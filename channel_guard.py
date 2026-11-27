"""Read-only availability reconciliation. Dates are nights [start, end)."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

@dataclass(frozen=True)
class Interval:
    source: str
    external_id: str
    start: date
    end: date
    status: str = "blocked"

    def __post_init__(self):
        if not self.source or not self.external_id:
            raise ValueError("source and external_id required")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.status not in {"blocked", "confirmed", "cancelled"}:
            raise ValueError("invalid status")

def reconcile(events: Iterable[Interval]) -> list[Interval]:
    """Deduplicate same source and ID. Cancellation dominates a batch.
    Persist cancellation tombstones across batches in caller storage."""
    entries = {}
    for event in events:
        key = (event.source, event.external_id)
        old = entries.get(key)
        if old is None or event.status == "cancelled":
            entries[key] = event
        elif old.status != "cancelled" and old != event:
            raise ValueError(f"conflicting versions for {key}; revision required")
    return sorted(entries.values(), key=lambda x: (x.start, x.end, x.source, x.external_id))

def conflicts(events: Iterable[Interval]):
    active = [x for x in reconcile(events) if x.status != "cancelled"]
    out = []
    for i, left in enumerate(active):
        for right in active[i + 1:]:
            if left.start < right.end and right.start < left.end:
                out.append((left, right))
    return out

def available(start: date, end: date, events: Iterable[Interval],
              channel_updates: dict[str, datetime], required_channels: Iterable[str],
              now: datetime, max_age: timedelta = timedelta(minutes=30)) -> bool:
    """Fail closed on stale feeds; not a live booking authorization."""
    if end <= start or now.tzinfo is None:
        return False
    for source in required_channels:
        stamp = channel_updates.get(source)
        if stamp is None or stamp.tzinfo is None or stamp > now or now - stamp > max_age:
            return False
    return not any(e.status != "cancelled" and e.start < end and start < e.end
                   for e in reconcile(events))

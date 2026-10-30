"""Durable provider throttling; never modifies reservations or calendar blocks."""
import hashlib
import random
import time
from datetime import timezone
from email.utils import parsedate_to_datetime


class CalendarFetchState:
    def __init__(self, db, clock=None):
        self.db, self.clock = db, clock or time.time
        with db() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS calendar_fetch_state(
                room TEXT, source TEXT, fingerprint TEXT NOT NULL,
                last_attempt REAL NOT NULL DEFAULT 0, last_success REAL NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '', event_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(room,source))''')

    def claim(self, room, source, url):
        now = self.clock()
        fingerprint = hashlib.sha256(url.encode()).hexdigest()
        with self.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''INSERT OR IGNORE INTO calendar_fetch_state(room,source,fingerprint)
                            VALUES(?,?,?)''', (room, source, fingerprint))
            state = dict(conn.execute('SELECT * FROM calendar_fetch_state WHERE room=? AND source=?',
                                      (room, source)).fetchone())
            if state['fingerprint'] != fingerprint:
                conn.execute('''UPDATE calendar_fetch_state SET fingerprint=?, last_success=0,
                                next_attempt=0,failures=0,error='' WHERE room=? AND source=?''',
                             (fingerprint, room, source))
                state.update(last_success=0, next_attempt=0, failures=0, error='')
            if state['next_attempt'] > now:
                return False, state
            # Cross-thread/process lease outlives the bounded eight-second request.
            conn.execute('''UPDATE calendar_fetch_state SET last_attempt=?,next_attempt=?
                            WHERE room=? AND source=?''', (now, now + 60, room, source))
            return True, state

    def success(self, conn, room, source, count):
        now = self.clock()
        interval = 900 if source == 'airbnb_ical' else 300
        conn.execute('''UPDATE calendar_fetch_state SET last_success=?, next_attempt=?,
                        failures=0,error='',event_count=? WHERE room=? AND source=?''',
                     (now, now + interval, count, room, source))

    def failure(self, room, source, exc, reason):
        now = self.clock()
        status = getattr(exc, 'code', 0)
        with self.db() as conn:
            state = conn.execute('SELECT failures FROM calendar_fetch_state WHERE room=? AND source=?',
                                 (room, source)).fetchone()
            failures = int(state[0]) + 1
            base = 900 if status == 429 else 60
            delay = min(21600, base * 2 ** min(failures - 1, 9))
            headers = getattr(exc, 'headers', None)
            retry = headers.get('Retry-After', '') if headers else ''
            try:
                server_delay = max(0, float(retry))
            except (ValueError, TypeError):
                try:
                    stamp = parsedate_to_datetime(retry)
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    server_delay = max(0, stamp.timestamp() - now)
                except (ValueError, TypeError, OverflowError):
                    server_delay = 0
            delay = max(delay + random.uniform(0, min(delay * .1, 60)), server_delay)
            conn.execute('''UPDATE calendar_fetch_state SET failures=?,error=?,next_attempt=?
                            WHERE room=? AND source=?''', (failures, reason, now + delay, room, source))

    def cached_ok(self, state):
        return bool(state['last_success'] and not state['error']
                    and self.clock() - state['last_success'] <= 1800)


def health_snapshot(db, sources, room='Bachblick'):
    """Read-only diagnostics without feed URLs, credentials, UIDs or guest data.

    Provider coverage proves imported snapshots only, not downstream channel receipt.
    """
    from datetime import date, datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    now = time.time()
    today = datetime.now(ZoneInfo("Europe/Vienna")).date()
    horizon = today + timedelta(days=365)
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None
    def nights(rows):
        result = set()
        for row in rows:
            start, end = date.fromisoformat(row[0]), date.fromisoformat(row[1])
            day = max(start, today)
            while day < min(end, horizon):
                result.add(day.isoformat())
                day += timedelta(days=1)
        return result
    with db() as conn:
        states = {r['source']: dict(r) for r in conn.execute(
            'SELECT * FROM calendar_fetch_state WHERE room=?', (room,))}
        blocks = conn.execute('SELECT source,start_date,end_date FROM external_blocks WHERE room=?',
                              (room,)).fetchall()
        direct = conn.execute("SELECT arrival,departure FROM bookings WHERE room=? AND status IN ('pending','confirmed')",
                              (room,)).fetchall()
    providers = []
    union = nights(direct)
    for source, label, _ in sources:
        state = states.get(source, {})
        coverage = nights([(r[1], r[2]) for r in blocks if r[0] == source])
        union |= coverage
        providers.append(dict(provider=label, source=source,
            last_attempt=stamp(state.get('last_attempt')), last_success=stamp(state.get('last_success')),
            next_attempt=stamp(state.get('next_attempt')), error=state.get('error', 'Noch nicht erfasst'),
            event_count=state.get('event_count'),
            fresh=bool(state.get('last_success') and not state.get('error')
                       and now - state['last_success'] <= 1800), occupied_nights=sorted(coverage)))
    for provider in providers:
        provider['missing_from_snapshot'] = sorted(union - set(provider['occupied_nights']))
    return dict(ok=bool(providers) and all(p['fresh'] for p in providers),
                checked_at=stamp(now), room=room, providers=providers,
                direct_occupied_nights=sorted(nights(direct)),
                scope='Stored imports only; downstream channel import not verified',
                revision='calendar-backoff-20261030')

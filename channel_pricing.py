"""Shared portal targets and a durable, idempotent price outbox."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import os
import logging
import threading
import time

from flask import jsonify, request
import beds24_rates
from booking_connectivity import push_rate as booking_push_rate, connectivity_status


PORTAL_MARKUP = Decimal("1.15")
PORTAL_MAX = Decimal("149")


def portal_price(direct):
    """Keep OTA/Beds24 target above the public direct-booking rate."""
    amount = min(PORTAL_MAX, Decimal(str(direct)) * PORTAL_MARKUP)
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class RateOutbox:
    def __init__(self, db, direct_rate, providers):
        self.db, self.direct_rate, self.providers = db, direct_rate, providers
        self.lock = threading.Lock()
        with db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS zab_manual_price_base (
                    room TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS zab_rate_managed_days (
                    room TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY(room,day)
                );
                CREATE TABLE IF NOT EXISTS zab_rate_outbox (
                    room TEXT NOT NULL, day TEXT NOT NULL, provider TEXT NOT NULL,
                    desired_price REAL NOT NULL, applied_price REAL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL, PRIMARY KEY(room,day,provider)
                );
            """)

    def manual_base(self, room):
        with self.db() as conn:
            return bool(conn.execute("SELECT 1 FROM zab_manual_price_base WHERE room=?", (room,)).fetchone())

    def manage(self, room, start, end, manual_base=False):
        if room != "Bachblick":
            return
        with self.db() as conn:
            if manual_base:
                conn.execute("INSERT OR IGNORE INTO zab_manual_price_base VALUES(?)", (room,))
            current = start
            while current <= end:
                conn.execute("INSERT OR IGNORE INTO zab_rate_managed_days VALUES(?,?)", (room, current.isoformat()))
                current += timedelta(days=1)
        self.refresh()

    def refresh(self):
        with self.db() as conn:
            rows = conn.execute("SELECT room,day FROM zab_rate_managed_days WHERE day>=?", (date.today().isoformat(),)).fetchall()
        for row in rows:
            price = portal_price(self.direct_rate(row['room'], date.fromisoformat(row['day'])))
            with self.db() as conn:
                for provider in self.providers:
                    conn.execute("""INSERT INTO zab_rate_outbox(room,day,provider,desired_price,updated_at)
                        VALUES(?,?,?,?,?) ON CONFLICT(room,day,provider) DO UPDATE SET
                        desired_price=excluded.desired_price,status='pending',attempts=0,next_attempt=0,
                        message='',updated_at=excluded.updated_at
                        WHERE zab_rate_outbox.desired_price != excluded.desired_price""",
                        (row['room'], row['day'], provider, price, datetime.now().isoformat(timespec='seconds')))

    def deliver(self, limit=5, now=None):
        now = time.time() if now is None else now
        if not self.lock.acquire(blocking=False):
            return
        try:
            failures = set()
            with self.db() as conn:
                rows = conn.execute("""SELECT * FROM zab_rate_outbox WHERE status!='applied'
                    AND next_attempt<=? AND day>=? ORDER BY next_attempt,day LIMIT ?""",
                    (now, date.today().isoformat(), limit)).fetchall()
            for row in rows:
                try:
                    result = self.providers[row['provider']](row['room'], date.fromisoformat(row['day']), row['desired_price'])
                except Exception:
                    result = {'ok': False, 'status': 'error'}
                ok = result.get('ok') is True
                status = 'applied' if ok else ('not_configured' if result.get('status') in ('not_configured', 'adapter_missing') else 'retry')
                message = ('Provider hat den Preis bestätigt.' if ok else
                           'API-Zugang oder Zimmer-/Preiszuordnung fehlt.' if status == 'not_configured' else
                           'Preisübertragung nicht bestätigt; erneuter Versuch folgt.')
                if not ok and status != 'not_configured' and row['provider'] == 'beds24':
                    message = beds24_rates.diagnostic_message(result)
                    failures.add(message)
                delay = min(3600, 300 * 2 ** min(row['attempts'], 4))
                with self.db() as conn:
                    conn.execute("""UPDATE zab_rate_outbox SET status=?,applied_price=CASE WHEN ? THEN desired_price ELSE applied_price END,
                        attempts=attempts+1,next_attempt=?,message=?,updated_at=?
                        WHERE room=? AND day=? AND provider=? AND desired_price=?""",
                        (status, int(ok), now+delay, message, datetime.now().isoformat(timespec='seconds'),
                         row['room'], row['day'], row['provider'], row['desired_price']))
            for message in sorted(failures):
                logging.getLogger(__name__).warning('Portalpreis-Synchronisierung: %s', message)
        finally:
            self.lock.release()

    def status(self):
        with self.db() as conn:
            rows = conn.execute("""SELECT provider,status,COUNT(*) AS count FROM zab_rate_outbox
                WHERE day>=? GROUP BY provider,status""", (date.today().isoformat(),)).fetchall()
        return [dict(row) for row in rows]

    def details(self):
        with self.db() as conn:
            rows = conn.execute("""SELECT day,provider,desired_price,applied_price,status,
                attempts,message,updated_at FROM zab_rate_outbox WHERE day>=?
                AND status!='applied' ORDER BY updated_at DESC,day LIMIT 5""",
                (date.today().isoformat(),)).fetchall()
        return [dict(row) for row in rows]


def init_channel_pricing(app, db, direct_rate, require_admin):
    # Choose one writer for Booking: either Beds24 forwards it or Connectivity does.
    providers = {'beds24': beds24_rates.push_rate}
    if os.environ.get('BEDS24_MANAGES_BOOKING', '').lower() not in ('1', 'true', 'yes'):
        providers['booking'] = booking_push_rate
    outbox = RateOutbox(db, direct_rate, providers)

    # Direct-booking-first policy: keep every sellable future day managed so
    # Beds24/Booking receives the OTA target instead of drifting below direct.
    # 460 days covers the configured calendar through 31.12.2027 from Oct 2026.
    outbox.manage("Bachblick", date.today(), date.today() + timedelta(days=460))

    app.extensions['zab_manual_room_base'] = outbox.manual_base
    app.extensions['zab_manage_rate_days'] = outbox.manage
    app.extensions['zab_final_direct_rate'] = direct_rate
    app.extensions['zab_portal_rate'] = lambda room, day: portal_price(direct_rate(room, day))
    app.extensions['zab_rate_outbox'] = outbox

    @app.get('/health/channel-pricing', endpoint='channel_pricing_health')
    def health():
        return jsonify(ok=True, portal_markup_percent=15, max_room_price=149,
                       beds24_configured=beds24_rates.configuration('Bachblick')['configured'],
                       booking_configured=connectivity_status('Bachblick')['configured'],
                       booking_via_beds24='booking' not in providers)

    @app.get('/os/channel-pricing/status', endpoint='channel_pricing_status')
    def status():
        if not require_admin():
            return jsonify(ok=False, error='unauthorized'), 401
        return jsonify(ok=True, rates=outbox.status(), details=outbox.details(),
                       beds24_mapping=beds24_rates.configuration('Bachblick'))

    @app.context_processor
    def pricing_context():
        if not request.path.startswith('/os/calendar'):
            return {}
        labels = {'pending': 'vorgemerkt', 'applied': 'vom Provider bestätigt',
                  'not_configured': 'API/Zuordnung fehlt', 'retry': 'erneuter Versuch nötig'}
        return {'portal_rate_sync': [{**row, 'label': labels[row['status']]} for row in outbox.status()],
                'beds24_price_ready': beds24_rates.configuration('Bachblick')['configured'],
                'booking_price_ready': connectivity_status('Bachblick')['configured']}

    def worker():
        while True:
            try:
                outbox.refresh()
                outbox.deliver()
            except Exception:
                app.logger.warning('Portalpreis-Synchronisierung unterbrochen; erneuter Versuch folgt.')
            time.sleep(60)

    threading.Thread(target=worker, name='zab-rate-sync', daemon=True).start()
    return outbox

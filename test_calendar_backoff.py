"""Exercise production sync against isolated SQLite and mocked providers."""
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import http.client
import socket
import ssl
import urllib.error
import urllib.request
from calendar_fetch_state import CalendarFetchState, health_snapshot
from test_calendar_sync import load_functions, response, feed


class CalendarBackoffTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''CREATE TABLE ical_settings(room,import_url,last_sync,last_result);
            INSERT INTO ical_settings VALUES('Bachblick','url','','');
            CREATE TABLE external_blocks(room,start_date,end_date,source,uid,summary,imported_at);
            CREATE TABLE bookings(id,room,arrival,departure,status);
            INSERT INTO bookings VALUES(42,'Bachblick','2026-11-01','2026-11-03','confirmed');
            INSERT INTO external_blocks VALUES('Bachblick','2026-11-01','2026-11-03','airbnb_ical','old','Reserved','2026-10-27');''')
        self.conn.commit()
        self.addCleanup(self.conn.close)
        @contextmanager
        def db():
            with self.conn:
                yield self.conn
        self.db = db
        self.sources = [('airbnb_ical','Airbnb','https://airbnb.test/?SECRET')]
        self.ns = dict(datetime=datetime, date=date, timedelta=timedelta, urllib=urllib,
            socket=socket, ssl=ssl, http=http, sqlite3=sqlite3, db=db, app=Mock(),
            room_is_suspended=lambda room: False, _calendar_sources_for_room=lambda room: self.sources)
        load_functions('app.py',['sync_room','parse_ical','unfold_ical','parse_ical_date','_calendar_failure'],self.ns)

    def sync(self, outcomes):
        with patch('urllib.request.urlopen', side_effect=outcomes) as opener:
            result = self.ns['sync_room']('Bachblick')
        return result, opener.call_count

    def state(self):
        return dict(self.conn.execute('SELECT * FROM calendar_fetch_state').fetchone())

    def test_429_preserves_blocks_reservation_and_honors_retry_after(self):
        with patch('calendar_fetch_state.time.time', return_value=10000):
            result, count = self.sync([urllib.error.HTTPError('SECRET',429,'SECRET',{'Retry-After':'7200'},None)])
            self.assertEqual(count,1)
            self.assertNotEqual(result[1],'Synchronisierung erfolgreich.')
            self.assertGreaterEqual(self.state()['next_attempt'],17200)
            self.assertEqual(self.state()['last_success'],0)
            self.assertEqual(self.sync([])[1],0)
        self.assertEqual(self.conn.execute('SELECT uid FROM external_blocks').fetchone()[0],'old')
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM bookings').fetchone()),
                         (42,'Bachblick','2026-11-01','2026-11-03','confirmed'))
        self.assertNotIn('SECRET',repr(self.ns['app'].logger.mock_calls))

    def test_recovery_then_cached_success_makes_no_extra_request(self):
        self.sync([urllib.error.HTTPError('SECRET',429,'SECRET',{},None)])
        self.conn.execute('UPDATE calendar_fetch_state SET next_attempt=0');self.conn.commit()
        result,count=self.sync([response(feed(2))])
        self.assertEqual((result,count),((2,'Synchronisierung erfolgreich.'),1))
        self.assertGreater(self.state()['last_success'],0)
        self.assertEqual(self.sync([]),((2,'Synchronisierung erfolgreich.'),0))
        self.assertEqual(self.state()['failures'],0)

    def test_partial_failure_cannot_claim_full_sync(self):
        self.sources.insert(0,('booking_ical','Booking.com','https://booking.test'))
        result,count=self.sync([response(feed(1)),TimeoutError()])
        self.assertEqual(count,2)
        self.assertNotEqual(result[1],'Synchronisierung erfolgreich.')
        self.assertEqual(self.sync([])[1],0)

    def test_malformed_events_cannot_clear_previous_snapshot(self):
        result,count=self.sync([response('BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VEVENT\nEND:VCALENDAR')])
        self.assertEqual(count,1)
        self.assertNotEqual(result[1],'Synchronisierung erfolgreich.')
        self.assertEqual(self.conn.execute('SELECT uid FROM external_blocks').fetchone()[0],'old')

    def test_success_metadata_and_snapshot_rollback_together(self):
        self.conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON external_blocks BEGIN SELECT RAISE(ABORT,'fail'); END")
        result,count=self.sync([response(feed(1))])
        self.assertEqual(count,1)
        self.assertEqual(self.state()['last_success'],0)
        self.assertEqual(self.conn.execute('SELECT uid FROM external_blocks').fetchone()[0],'old')

    def test_durable_lease_prevents_second_instance_fetch(self):
        first=CalendarFetchState(self.db)
        self.assertTrue(first.claim('Bachblick','airbnb_ical','url')[0])
        second=CalendarFetchState(self.db)
        self.assertFalse(second.claim('Bachblick','airbnb_ical','url')[0])

    def test_health_is_read_only_and_redacts_feed_and_guest_identifiers(self):
        self.sync([response(feed(1))])
        before=self.conn.total_changes
        payload=health_snapshot(self.db,self.sources)
        self.assertTrue(payload['ok'])
        self.assertIsNotNone(payload['providers'][0]['last_success'])
        self.assertEqual(self.conn.total_changes,before)
        self.assertNotIn('SECRET',str(payload))
        self.assertNotIn('new-0',str(payload))
        self.assertNotIn('fingerprint',str(payload))

    def test_independent_connections_claim_only_one_fetch(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'state.db')
            @contextmanager
            def db():
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                try:
                    with conn:
                        yield conn
                finally:
                    conn.close()
            CalendarFetchState(db)
            def claim(_):
                return CalendarFetchState(db).claim('Bachblick','airbnb_ical','url')[0]
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(claim, range(20))), 1)

    def test_http_date_retry_after_and_exponential_backoff(self):
        state=CalendarFetchState(self.db,clock=lambda:10000)
        state.claim('Bachblick','airbnb_ical','url')
        error=urllib.error.HTTPError('SECRET',429,'SECRET',{'Retry-After':'Thu, 01 Jan 1970 10:00:00 GMT'},None)
        state.failure('Bachblick','airbnb_ical',error,'HTTP 429')
        self.assertGreaterEqual(self.state()['next_attempt'],36000)
        state.failure('Bachblick','airbnb_ical',TimeoutError(),'timeout')
        self.assertEqual(self.state()['failures'],2)

if __name__ == '__main__':
    unittest.main()

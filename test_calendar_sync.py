"""Real sync/watchdog functions, isolated DB and mocked HTTP; no app workers."""
import ast
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import http.client
from pathlib import Path
import socket
import sqlite3
import ssl
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch


def load_functions(filename, names, namespace, parent=None):
    tree = ast.parse(Path(__file__).with_name(filename).read_text())
    nodes = tree.body
    if parent:
        nodes = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == parent).body
    selected = [n for n in nodes if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), filename, 'exec'), namespace)


def feed(count):
    events = ''.join(
        f'BEGIN:VEVENT\nUID:new-{i}\nDTSTART:20261010\nDTEND:20261012\nEND:VEVENT\n'
        for i in range(count))
    return f'BEGIN:VCALENDAR\n{events}END:VCALENDAR\n'


def response(text):
    result = Mock()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.read.return_value = text.encode()
    return result


class CalendarSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE ical_settings(room,import_url,last_sync,last_result);
            INSERT INTO ical_settings VALUES('Bachblick','https://booking.test/feed','','');
            CREATE TABLE external_blocks(room,start_date,end_date,source,uid,summary,imported_at);
            CREATE TABLE bookings(room,arrival,departure,status);
            CREATE TABLE central_overrides(room,day,availability);
        ''')
        self.sources = [(key + '_ical', label, 'https://' + key + '.test/feed?token=SECRET')
                        for key, label in [('booking', 'Booking.com'), ('beds24', 'Beds24'), ('airbnb', 'Airbnb')]]
        for source, _, _ in self.sources:
            self.conn.execute('INSERT INTO external_blocks VALUES(?,?,?,?,?,?,?)',
                              ('Bachblick', '2026-10-20', '2026-10-22', source, 'old', 'Reserved', 'old-time'))
        self.conn.commit()

        @contextmanager
        def db():
            with self.conn:
                yield self.conn

        self.ns = dict(datetime=datetime, date=date, timedelta=timedelta, urllib=urllib,
                       socket=socket, ssl=ssl, http=http, sqlite3=sqlite3, db=db,
                       app=Mock(), room_is_suspended=lambda room: False,
                       _calendar_sources_for_room=lambda room: self.sources,
                       minimum_stay_for_period=lambda *args: (1, []),
                       ROOMS={'Bachblick': {'available_from': date(2026, 8, 16)}})
        self.ns['app'].extensions = {}
        load_functions('app.py', ['unfold_ical', 'parse_ical_date', 'parse_ical', '_calendar_failure',
                                 'sync_room', 'parse_date', 'overlaps', 'room_available_in_conn',
                                 'room_available'], self.ns)
        self.old = self.blocks('beds24_ical')

    def blocks(self, source):
        return [tuple(r) for r in self.conn.execute(
            'SELECT * FROM external_blocks WHERE source=?', (source,))]

    def status(self):
        return self.conn.execute('SELECT last_result FROM ical_settings').fetchone()[0]

    def sync(self, outcomes):
        with patch('urllib.request.urlopen', side_effect=outcomes) as opener:
            result = self.ns['sync_room']('Bachblick')
        return result, opener

    def watchdog(self):
        self.ns.update(_now=datetime.now,
                       _parse_dt=lambda value: datetime.fromisoformat(value) if value else None,
                       _upsert_alert=Mock(), _resolve_alerts=Mock())
        load_functions('host_automation.py', ['_ical_watchdog'], self.ns, 'init_host_automation')
        self.ns['_ical_watchdog']()
        return self.ns['_upsert_alert']

    def test_partial_failure_keeps_snapshot_and_checkout_success(self):
        failure = urllib.error.HTTPError(self.sources[1][2], 403, 'SECRET', {}, None)
        result, opener = self.sync([response(feed(7)), failure, response(feed(1))])
        self.assertEqual(result, (8, 'Synchronisierung erfolgreich.'))
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(self.blocks('beds24_ical'), self.old)
        self.assertEqual(len(self.blocks('booking_ical')), 7)
        self.assertEqual(len(self.blocks('airbnb_ical')), 1)
        self.assertIn('Beds24: Fehler (HTTP 403; Versuche: 1; letzter Stand beibehalten)', self.status())
        alarm = self.watchdog().call_args.args
        self.assertEqual(alarm[1], 'critical')
        self.assertIn('HTTP 403', alarm[2])
        self.assertNotIn('SECRET', alarm[2])
        self.assertFalse(self.ns['room_available_in_conn'](
            self.conn, 'Bachblick', date(2026, 10, 20), date(2026, 10, 21))[0])

    def test_retry_recovers_and_replaces_only_successful_snapshot(self):
        result, opener = self.sync([response(feed(7)), urllib.error.URLError(TimeoutError('SECRET')),
                                    response(feed(2)), response(feed(1))])
        self.assertEqual(result, (10, 'Synchronisierung erfolgreich.'))
        self.assertEqual(opener.call_count, 4)
        self.assertTrue(all(call.kwargs['timeout'] == 8 for call in opener.call_args_list))
        self.assertEqual(len(self.blocks('beds24_ical')), 2)
        self.assertNotEqual(self.blocks('beds24_ical'), self.old)
        self.assertIn('Beds24: 2 (nach Retry)', self.status())
        self.assertNotIn('Fehler', self.status())
        self.watchdog().assert_not_called()
        self.ns['_resolve_alerts'].assert_called_once_with('ical:', set())

    def test_persistent_timeout_is_bounded_and_remains_critical(self):
        result, opener = self.sync([response(feed(7)), TimeoutError('SECRET'),
                                    TimeoutError('https://beds24.test/?token=SECRET'), response(feed(1))])
        self.assertEqual(result, (8, 'Synchronisierung erfolgreich.'))
        self.assertEqual(opener.call_count, 4)
        self.assertEqual(self.blocks('beds24_ical'), self.old)
        self.assertIn('Zeitüberschreitung; Versuche: 2', self.status())
        self.assertNotIn('SECRET', self.status())
        self.assertEqual(self.watchdog().call_args.args[1], 'critical')
        self.assertNotIn('SECRET', repr(self.ns['app'].logger.mock_calls))

    def test_all_sources_fail_without_success_marker_or_lost_blocks(self):
        old = [self.blocks(s) for s, _, _ in self.sources]
        result, opener = self.sync([TimeoutError('SECRET')] * 6)
        self.assertEqual(opener.call_count, 6)
        self.assertEqual(result, (0, self.status()))
        self.assertNotEqual(result[1], 'Synchronisierung erfolgreich.')
        self.assertEqual([self.blocks(s) for s, _, _ in self.sources], old)

    def test_transient_http_503_retries(self):
        self.sources = self.sources[1:2]
        failure = urllib.error.HTTPError(self.sources[0][2], 503, 'SECRET', {}, None)
        result, opener = self.sync([failure, response(feed(1))])
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(result, (1, 'Synchronisierung erfolgreich.'))

    def test_tls_failure_does_not_retry_or_leak_exception_text(self):
        self.sources = self.sources[1:2]
        failure = urllib.error.URLError(ssl.SSLCertVerificationError('SECRET'))
        result, opener = self.sync([failure])
        self.assertEqual(opener.call_count, 1)
        self.assertIn('TLS-/Zertifikatsfehler', result[1])
        self.assertNotIn('SECRET', result[1])
        self.assertEqual(self.blocks('beds24_ical'), self.old)

    def test_invalid_response_preserves_snapshot_without_retry(self):
        self.sources = self.sources[1:2]
        for payload in ['<html>SECRET</html>', feed(1).replace('END:VCALENDAR', '')]:
            with self.subTest(payload=payload):
                result, opener = self.sync([response(payload)])
                self.assertEqual(opener.call_count, 1)
                self.assertIn('Ungültige Kalenderdaten', result[1])
                self.assertEqual(self.blocks('beds24_ical'), self.old)

    def test_valid_empty_calendar_can_clear_successful_snapshot(self):
        self.sources = self.sources[1:2]
        result, _ = self.sync([response(feed(0))])
        self.assertEqual(result, (0, 'Synchronisierung erfolgreich.'))
        self.assertEqual(self.blocks('beds24_ical'), [])

    def test_database_write_failure_rolls_back_snapshot_without_retry(self):
        self.sources = self.sources[1:2]
        self.conn.execute("""CREATE TRIGGER fail_import BEFORE INSERT ON external_blocks
                             BEGIN SELECT RAISE(ABORT, 'write failed'); END""")
        result, opener = self.sync([response(feed(1))])
        self.assertEqual(opener.call_count, 1)
        self.assertIn('Datenbankfehler', result[1])
        self.assertEqual(self.blocks('beds24_ical'), self.old)

    def test_database_lock_is_diagnosed_without_network_retry(self):
        failure = sqlite3.OperationalError('SECRET')
        failure.sqlite_errorcode = sqlite3.SQLITE_BUSY
        reason, retry = self.ns['_calendar_failure'](failure)
        self.assertEqual(reason, 'Datenbank gesperrt')
        self.assertFalse(retry)

    def test_live_master_failure_still_fails_closed(self):
        self.ns['sync_room'] = Mock(return_value=(8, 'Synchronisierung erfolgreich.'))
        self.ns['live_master_availability'] = Mock(return_value=(None, 'Live-Kalender nicht erreichbar'))
        self.assertEqual(self.ns['room_available']('Bachblick', date(2026, 10, 20), date(2026, 10, 21)),
                         (False, 'Live-Kalender nicht erreichbar'))

    def test_live_master_free_cannot_override_failed_provider_snapshot(self):
        self.ns['sync_room'] = Mock(return_value=(8, 'Synchronisierung erfolgreich.'))
        self.ns['live_master_availability'] = Mock(return_value=(True, 'Live-Kalender frei'))
        self.assertFalse(self.ns['room_available'](
            'Bachblick', date(2026, 10, 20), date(2026, 10, 21))[0])


if __name__ == '__main__':
    unittest.main()

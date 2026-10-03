"""Isolated report regressions; no production database or email delivery."""
import ast
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo
from host_automation import _report_calendar_blocks


class ReportTests(unittest.TestCase):
    def test_overlapping_blocks_are_one_interval_per_room(self):
        rows = [dict(room=room, start_date=start, end_date=end, source=source)
                for room, start, end, source in [
                    ('Bachblick', '2026-10-03', '2026-10-04', 'airbnb_ical'),
                    ('Bachblick', '2026-10-01', '2026-10-04', 'beds24_ical'),
                    ('Bachblick', '2026-10-01', '2026-10-04', 'beds24_ical'),
                    ('Bachblick', '2026-10-04', '2026-10-05', 'beds24_ical'),
                    ('Gartenzimmer', '2026-10-01', '2026-10-04', 'beds24_ical')]]
        result = _report_calendar_blocks(rows)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['start_date'], '2026-10-01')
        self.assertEqual(result[0]['end_date'], '2026-10-04')
        self.assertEqual(result[0]['sources'], {'beds24_ical', 'airbnb_ical'})

    def test_mail_excludes_requests_and_reports_payment_remainder(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.executescript('''
            CREATE TABLE bookings(room,first_name,last_name,adults,arrival,departure,
                arrival_time,status,total,amount_paid,paid,created_at,source);
            CREATE TABLE external_blocks(room,start_date,end_date,source,summary);
            CREATE TABLE email_outbox(status);
            CREATE TABLE automation_alerts(severity,message,active,updated_at);
            CREATE TABLE automation_metrics(metric_day);
            INSERT INTO external_blocks VALUES
                ('Bachblick','2026-10-03','2026-10-04','airbnb_ical','Reserved'),
                ('Bachblick','2026-10-01','2026-10-04','beds24_ical','Not Available');
        ''')
        for status in ('confirmed', 'inquiry', 'pending', 'expired', 'cancelled'):
            conn.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('Gartenzimmer', 'Test', status, 2, '2026-10-03', '2026-10-04',
                 '', status, 200, 50, 0, '2026-10-02', 'direct'))
        conn.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('Donauzimmer', 'Full', 'Payment', 1, '2026-10-01', '2026-10-03',
             '', 'confirmed', 100, 100, 0, '2026-10-02', 'direct'))

        @contextmanager
        def db():
            yield conn

        # Execute the actual report without starting application workers.
        tree = ast.parse(Path(__file__).with_name('host_automation.py').read_text())
        init = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'init_host_automation')
        report = next(n for n in init.body if isinstance(n, ast.FunctionDef)
                      and n.name == '_daily_report')
        queued = []
        namespace = dict(
            _now=lambda: datetime(2026, 10, 3, 7, tzinfo=ZoneInfo('Europe/Vienna')),
            os=os, timedelta=timedelta, db=db, _report_calendar_blocks=_report_calendar_blocks,
            _run_once_key=lambda *a: True, _gap_nights=lambda: [],
            _owner_recipients=lambda: ['owner@example.test'],
            _queue_mail=lambda *args: queued.append(args),
            _upsert_alert=Mock(), app=Mock())
        exec(compile(ast.Module(body=[report], type_ignores=[]), 'host_automation.py', 'exec'), namespace)
        namespace['_daily_report']()
        namespace['_upsert_alert'].assert_not_called()
        self.assertEqual(len(queued), 1)
        body = queued[0][-1]
        for expected in (
            'Bestätigte Buchungen mit Aufenthalt heute: 1',
            'Personen laut diesen Buchungen: 2', 'Zimmer mit iCal-Sperre heute: 1',
            'Quellen beds24_ical, airbnb_ical', 'Bestätigte Anreisen heute: 1',
            'Bestätigte Abreisen heute: 1', 'Bestätigte Anreisen morgen: 0',
            'Offene Zahlungen: 1 · 150.00 EUR'):
            self.assertIn(expected, body)
        for unexpected in ('Externe Anreisen', 'Gäste aktuell im Haus', 'Test inquiry'):
            self.assertNotIn(unexpected, body)
        namespace['_now'] = lambda: datetime(2026, 10, 4, 7, tzinfo=ZoneInfo('Europe/Vienna'))
        namespace['_daily_report']()
        checkout_body = queued[-1][-1]
        self.assertIn('Bestätigte Buchungen mit Aufenthalt heute: 0', checkout_body)
        self.assertIn('Zimmer mit iCal-Sperre heute: 0', checkout_body)
        self.assertIn('Bestätigte Abreisen heute: 1', checkout_body)
        namespace['_now'] = lambda: datetime(2026, 10, 2, 7, tzinfo=ZoneInfo('Europe/Vienna'))
        namespace['_daily_report']()
        self.assertIn('Bestätigte Anreisen morgen: 1', queued[-1][-1])
        namespace['_now'] = lambda: datetime(2026, 10, 3, 7, tzinfo=ZoneInfo('Europe/Vienna'))
        run_keys = set()
        def run_once(key, details):
            if key in run_keys:
                return False
            run_keys.add(key)
            return True
        namespace['_run_once_key'] = run_once
        with patch.dict('os.environ', {
            'ZAB_DAILY_REPORT_CORRECTION_DATE': '2026-10-03',
            'ZAB_DAILY_REPORT_CORRECTION_TO': 'operator@example.test',
        }):
            before = len(queued)
            namespace['_daily_report']()
            namespace['_daily_report']()
            self.assertEqual(len(queued), before + 1)
            self.assertEqual(queued[-1][0], 'automation-report-correction:2026-10-03:v2:0')
            self.assertEqual(queued[-1][3], 'operator@example.test')
            self.assertIn('Korrigierte Tagesübersicht', queued[-1][4])
            namespace['_now'] = lambda: datetime(2026, 10, 4, 7, tzinfo=ZoneInfo('Europe/Vienna'))
            namespace['_daily_report']()
            self.assertEqual(queued[-1][0], 'automation-report:2026-10-04:0')
            self.assertEqual(queued[-1][3], 'owner@example.test')
            self.assertNotIn('Korrigierte', queued[-1][4])


if __name__ == '__main__':
    unittest.main()

"""Concurrent Flask requests against a temporary DB; no live feeds or workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from flask import Flask, jsonify, request
from test_calendar_sync import feed, load_functions, response


class CalendarBusyResponseTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.ns = dict(app=self.app, sqlite3=sqlite3, jsonify=jsonify, request=request)
        load_functions('app.py', ['calendar_database_error'], self.ns)

        @self.app.before_request
        def locked_cleanup():
            error = sqlite3.OperationalError('SECRET connection details')
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise error

        for path in ['/api/availability', '/api/calendar', '/api/paypal/quote', '/api/paypal/create-order']:
            self.app.add_url_rule(path, path, lambda: jsonify(available=True), methods=['GET', 'POST'])

    def test_busy_before_request_returns_safe_json_instead_of_html_500(self):
        client = self.app.test_client()
        for path in ['/api/availability', '/api/calendar', '/api/paypal/quote', '/api/paypal/create-order']:
            with self.subTest(path=path), self.assertLogs(self.app.logger, level='WARNING'):
                result = client.post(path)
                self.assertEqual(result.status_code, 503)
                data = result.get_json()
                self.assertFalse(data['available'])
                self.assertFalse(data['live'])
                self.assertFalse(data['ok'])
                self.assertEqual(data['status'], 'unknown')
                self.assertEqual(data['days'], {})
                self.assertNotIn('SECRET', result.get_data(as_text=True))
                self.assertEqual(result.headers['Retry-After'], '2')
                self.assertEqual(result.headers['Cache-Control'], 'no-store')


class ConcurrentHomepageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {
            'DATA_DIR': cls.tmp.name, 'APP_ENV': 'test', 'RAILWAY_ENVIRONMENT': '',
            'REQUIRE_PRODUCTION_SECRETS': '0', 'RESEND_BOOKING_ID_ON_START': '',
            'ZAB_SUSPENDED_ROOMS': '', 'BEDS24_ICAL_BACHBLICK_URL': 'https://beds24.test/feed',
            'AIRBNB_ICAL_BACHBLICK_URL': 'https://airbnb.test/feed',
        })
        cls.env.start()
        try:
            with patch('threading.Thread.start'), patch('urllib.request.urlopen', side_effect=urllib.error.URLError('disabled')):
                import railway_app
                import app as core
            cls.core = core
            cls.app = railway_app.app
            with core.db() as conn:
                conn.execute("UPDATE ical_settings SET import_url='https://booking.test/feed' WHERE room='Bachblick'")
                conn.execute('''INSERT INTO external_blocks
                    (room,start_date,end_date,source,uid,summary,imported_at)
                    VALUES('Bachblick','2026-10-20','2026-10-22','beds24_ical','old','Reserved','old')''')
        except Exception:
            cls.env.stop()
            cls.tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()

    def test_admin_price_change_becomes_authoritative_base(self):
        from datetime import date
        import railway_app
        day = date(2026,10,26)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['admin'] = True
        prices = self.core.pricing_data()[0]
        form = {f'{room}_{kind}': str(row[kind]) for room,row in prices.items()
                for kind in ('standard','weekend','high')}
        form.update({f'Bachblick_{kind}':'100' for kind in ('standard','weekend','high')})
        outbox = self.app.extensions['zab_rate_outbox']
        original = self.app.extensions['zab_manage_rate_days']
        self.app.extensions['zab_manage_rate_days'] = lambda room,*args,**kw: outbox.manage(room,day,day,**kw)
        try:
            with patch.object(self.core,'_demand_percent_for_day',return_value=(5,4)), \
                 patch.object(railway_app,'_revenue_adjustment_for_day',return_value=(0,0)):
                self.assertEqual(client.post('/admin/prices',data=form).status_code,302)
                self.assertEqual(railway_app.final_direct_rate('Bachblick',day),105)
                self.assertEqual(self.app.extensions['zab_portal_rate']('Bachblick',day),110.25)
        finally:
            self.app.extensions['zab_manage_rate_days'] = original
            with self.core.db() as conn:
                for room,row in prices.items():
                    conn.execute('UPDATE room_prices SET standard=?,weekend=?,high=? WHERE room=?',
                                 (row['standard'],row['weekend'],row['high'],room))
                conn.execute('DELETE FROM zab_manual_price_base')
                for table in ('zab_rate_managed_days','zab_rate_outbox'):
                    conn.execute(f'DELETE FROM {table} WHERE room=? AND day=?',('Bachblick',day.isoformat()))

    def test_os_base_price_gets_demand_and_portal_markup(self):
        from datetime import date
        import railway_app
        from channel_pricing import portal_price
        day = date(2026,10,26)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['admin'] = True
        try:
            with patch.object(self.core, '_demand_percent_for_day', return_value=(5,4)), \
                 patch.object(railway_app, '_revenue_adjustment_for_day', return_value=(0,0)):
                result = client.post('/os/calendar/day', data={
                    'room':'Bachblick','start_date':day.isoformat(),'end_date':day.isoformat(),
                    'direct_price':'100','direct_status':'keep','booking_status':'keep',
                })
                self.assertEqual(result.status_code, 302)
                self.assertEqual(railway_app.final_direct_rate('Bachblick', day), 105)
                self.assertEqual(self.app.extensions['zab_portal_rate']('Bachblick', day), 110.25)
                self.assertEqual(self.app.extensions['zab_channel_price_for_day']('Bachblick','booking',day), 110.25)
                with self.core.db() as conn:
                    rows = conn.execute('SELECT desired_price FROM zab_rate_outbox WHERE day=?', (day.isoformat(),)).fetchall()
                self.assertEqual([r['desired_price'] for r in rows], [110.25,110.25])
                self.assertEqual(client.get('/os/channel-pricing/status').status_code,200)
        finally:
            with self.core.db() as conn:
                for table in ('zab_channel_day_settings','zab_rate_managed_days','zab_rate_outbox'):
                    conn.execute(f'DELETE FROM {table} WHERE room=? AND day=?', ('Bachblick', day.isoformat()))

    def test_public_quote_and_checkout_use_same_final_price(self):
        def fetch(req, **kwargs):
            if 'direct-booking-calendar' in req.full_url:
                return response('{"ok":true,"events":[],"source":"test"}')
            return response(feed(1))

        payload = {'room': 'Bachblick', 'arrival': '2026-10-26',
                   'departure': '2026-10-29', 'adults': 2}
        with patch('urllib.request.urlopen', side_effect=fetch):
            for breakfast in (False, True):
                with self.subTest(breakfast=breakfast):
                    client = self.app.test_client()
                    public = client.post('/api/availability', data={
                        **payload, 'breakfast': str(breakfast).lower(),
                    })
                    checkout = client.post('/api/paypal/quote', json={
                        **payload, 'extras': {'breakfast': breakfast},
                    })
                    self.assertEqual(public.status_code, 200)
                    self.assertEqual(checkout.status_code, 200)
                    first = public.get_json()['breakdown']
                    second = checkout.get_json()['breakdown']
                    for key in ('total', 'room_total', 'extras', 'discounts', 'nightly_rates'):
                        self.assertEqual(first[key], second[key], key)
                    self.assertEqual(first['discounts'], [])
                    self.assertLessEqual(first['room_total'], 149 * 3)
                    self.assertEqual(sum(row['rate'] for row in first['nightly_rates']), first['room_total'])
                    if breakfast:
                        self.assertGreater(first['total'], first['room_total'])

    def test_parallel_home_calendar_and_checks_keep_safety_snapshot(self):
        def fetch(req, **kwargs):
            if 'beds24.test' in req.full_url:
                raise TimeoutError('secret feed URL must not be exposed')
            if 'direct-booking-calendar' in req.full_url:
                return response('{"ok":true,"events":[],"source":"test"}')
            return response(feed(1))

        def visit(index):
            client = self.app.test_client()
            kind = index % 4
            if kind == 0:
                result = client.get('/')
                return result.status_code, None
            if kind == 1:
                result = client.get('/api/calendar?room=Bachblick&year=2026&month=10')
                self.assertIn(result.get_json()['days']['2026-10-20'], ('booking', 'direct', 'pending'))
                return result.status_code, None
            arrival, departure = ('2026-10-26', '2026-10-29') if kind == 2 else ('2026-10-20', '2026-10-23')
            result = client.post('/api/availability', data={
                'room': 'Bachblick', 'arrival': arrival, 'departure': departure, 'adults': '2',
            })
            self.assertEqual(result.get_json()['available'], kind == 2)
            return result.status_code, result.get_json()['available']

        with patch('urllib.request.urlopen', side_effect=fetch), patch.object(
            self.core, 'live_master_availability', return_value=(True, 'Live-Kalender frei')
        ), self.assertLogs(self.app.logger, level='WARNING') as logs:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(visit, range(40)))
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertNotIn('database is locked', '\n'.join(logs.output))
        with self.core.db() as conn:
            row = conn.execute("SELECT uid,imported_at FROM external_blocks WHERE source='beds24_ical'").fetchone()
            self.assertEqual(tuple(row), ('old', 'old'))
            status = conn.execute("SELECT last_result FROM ical_settings WHERE room='Bachblick'").fetchone()[0]
            self.assertIn('Beds24: Fehler (Zeitüberschreitung; Versuche: 2', status)


if __name__ == '__main__':
    unittest.main()

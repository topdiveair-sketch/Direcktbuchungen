"""Portal targets, durable retries and price-only Beds24 requests."""
from contextlib import contextmanager
from datetime import date
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

import beds24_rates
from channel_pricing import RateOutbox, portal_price


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/test.db'
        self.rate = 100
        self.provider = Mock(return_value={'ok': True})
        self.outbox = RateOutbox(self.db, lambda *a: self.rate, {'beds24': self.provider})

    def tearDown(self):
        self.tmp.cleanup()

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def row(self):
        with self.db() as conn:
            return dict(conn.execute('SELECT * FROM zab_rate_outbox').fetchone())

    def test_current_markup_rounding_and_all_channel_cap(self):
        self.assertEqual(portal_price(100), 115)
        self.assertEqual(portal_price(119), 136.85)
        self.assertEqual(portal_price(141.90), 149)
        self.assertEqual(portal_price(149), 149)

    def test_demand_change_refreshes_target_and_success_is_not_resent(self):
        day = date.today()
        self.outbox.manage('Bachblick', day, day, manual_base=True)
        self.assertTrue(self.outbox.manual_base('Bachblick'))
        self.outbox.deliver(now=10)
        self.outbox.deliver(now=1000)
        self.assertEqual(self.provider.call_count, 1)
        self.rate = 110
        self.outbox.refresh()
        self.assertEqual(self.row()['desired_price'], 126.5)
        self.outbox.deliver(now=1001)
        self.assertEqual(self.provider.call_count, 2)

    def test_failure_survives_restart_and_retry_keeps_direct_price(self):
        self.provider.side_effect = [TimeoutError('SECRET token'), {'ok': True}]
        day = date.today()
        self.outbox.manage('Bachblick', day, day)
        self.outbox.deliver(now=10)
        self.assertEqual(self.row()['status'], 'retry')
        self.assertNotIn('SECRET', self.row()['message'])
        self.assertEqual(self.rate, 100)
        restarted = RateOutbox(self.db, lambda *a: self.rate, {'beds24': self.provider})
        restarted.deliver(now=20)
        self.assertEqual(self.provider.call_count, 1)
        restarted.deliver(now=311)
        self.assertEqual(self.row()['status'], 'applied')
        self.assertEqual(self.row()['applied_price'], 115)

    def test_price_change_during_delivery_cannot_be_marked_applied(self):
        day = date.today()
        self.outbox.manage('Bachblick', day, day)
        def changed(*args):
            self.rate = 120
            self.outbox.refresh()
            return {'ok': True}
        self.provider.side_effect = changed
        self.outbox.deliver(now=10)
        self.assertEqual(self.row()['status'], 'pending')
        self.assertEqual(self.row()['desired_price'], 138)

    def test_rejection_exposes_safe_cause_and_never_claims_confirmation(self):
        self.provider.return_value = {'ok': False, 'status': 'http_error',
                                     'error_code': 'forbidden', 'message': 'SECRET token'}
        self.outbox.manage('Bachblick', date.today(), date.today())
        with self.assertLogs('channel_pricing', level='WARNING') as logs:
            self.outbox.deliver(now=10)
        detail = self.outbox.details()[0]
        self.assertEqual(detail['desired_price'], 115)
        self.assertIsNone(detail['applied_price'])
        self.assertEqual(detail['status'], 'retry')
        self.assertIn('write:inventory', detail['message'])
        self.assertNotIn('SECRET', json.dumps(detail) + str(logs.output))
        self.provider.return_value = {'ok': True}
        self.outbox.deliver(now=311)
        self.assertEqual(self.outbox.details(), [])
        self.assertEqual(self.outbox.status()[0]['status'], 'applied')

    def test_missing_configuration_is_visible_and_retried(self):
        self.provider.return_value = {'ok': False, 'status': 'not_configured'}
        self.outbox.manage('Bachblick', date.today(), date.today())
        self.outbox.deliver(now=10)
        self.assertEqual(self.row()['status'], 'not_configured')
        self.assertIsNone(self.row()['applied_price'])


class Beds24Tests(unittest.TestCase):
    @patch.dict(os.environ, {'BEDS24_REFRESH_TOKEN': 'SECRET', 'BEDS24_ROOM_ID_BACHBLICK': '123',
                             'BEDS24_PORTAL_PRICE_SLOT_BACHBLICK': '1'})
    def test_http_failures_are_classified_without_exposing_credentials(self):
        for status, code in ((401, 'unauthorized'), (403, 'forbidden'),
                             (429, 'rate_limited'), (503, 'server_error')):
            error = urllib.error.HTTPError('https://example.test/SECRET', status, 'SECRET', {}, None)
            with self.subTest(status=status), patch.object(beds24_rates, '_token', return_value='SECRET'), \
                 patch.object(beds24_rates, '_request', side_effect=error):
                result = beds24_rates.push_rate('Bachblick', date.today(), 149)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error_code'], code)
                self.assertNotIn('SECRET', json.dumps(result))

    @patch.dict(os.environ, {'BEDS24_REFRESH_TOKEN': 'SECRET', 'BEDS24_ROOM_ID_BACHBLICK': '123',
                             'BEDS24_PORTAL_PRICE_SLOT_BACHBLICK': '1'})
    def test_rejected_or_malformed_response_never_confirms_price(self):
        responses = [([{'success': False, 'errors': ['RATE_IS_A_SLAVE_RATE SECRET']}], 'slave_rate'),
                     ({'data': [{'success': False, 'errors': ['missing scope SECRET']}]}, 'missing_scope'),
                     ([None], 'rejected'), (None, 'rejected')]
        for response, code in responses:
            with self.subTest(response=response), patch.object(beds24_rates, '_token', return_value='SECRET'), \
                 patch.object(beds24_rates, '_request', return_value=response):
                result = beds24_rates.push_rate('Bachblick', date.today(), 149)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error_code'], code)
                self.assertNotIn('SECRET', json.dumps(result))

    @patch.dict(os.environ, {'BEDS24_REFRESH_TOKEN': 'SECRET', 'BEDS24_ROOM_ID_BACHBLICK': '123',
                             'BEDS24_PORTAL_PRICE_SLOT_BACHBLICK': '2'})
    def test_only_portal_price_is_written_and_rejection_is_not_success(self):
        for success in (True, False):
            with self.subTest(success=success), patch.object(beds24_rates, '_token', return_value='SECRET'), \
                 patch.object(beds24_rates, '_request', return_value=[{'success': success}]) as call:
                result = beds24_rates.push_rate('Bachblick', date(2026,10,4), 124.95)
                self.assertEqual(result['ok'], success)
                self.assertEqual(call.call_args.args[0], '/inventory/rooms/calendar')
                payload = call.call_args.args[2]
                self.assertEqual(payload, [{'roomId':123,'calendar':[{'from':'2026-10-04','to':'2026-10-04','price2':124.95}]}])
                self.assertNotIn('SECRET', json.dumps(result))

    def test_invalid_or_over_cap_price_is_never_sent(self):
        with patch.object(beds24_rates, '_request') as call:
            for price in (float('nan'), float('inf'), -1, 150):
                self.assertEqual(beds24_rates.push_rate('Bachblick',date.today(),price)['status'],'invalid_price')
            call.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    def test_no_configuration_does_not_make_network_request(self):
        with patch.object(beds24_rates, '_request') as call:
            self.assertEqual(beds24_rates.push_rate('Bachblick', date.today(), 105)['status'], 'not_configured')
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()

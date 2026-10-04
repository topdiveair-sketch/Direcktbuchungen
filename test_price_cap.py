"""Room cap across public quotes, late surcharges and checkout overrides."""
from datetime import date, datetime, timedelta
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from pricing_2027 import cap_room_rate, nightly_direct_rate
from test_calendar_sync import load_functions


class PriceCapTests(unittest.TestCase):
    def test_configured_event_and_season_rates_are_capped(self):
        for section, row in [('date_overrides', {'start':'2026-10-04','end':'2026-10-04','price_eur':250}), ('season_ranges', {'start':'2026-10-04','end':'2026-10-04','sun_thu':250,'fri_sat':250})]:
            cfg = {'active_start':'2026-01-01','active_end':'2026-12-31','minimum_direct_price_eur':99,section:[row]}
            with self.subTest(section=section), patch('pricing_2027.pricing_config',return_value=cfg):
                self.assertEqual(nightly_direct_rate(date(2026,10,4)),149)
        self.assertEqual(cap_room_rate(99),99)

    def test_demand_and_override_cannot_exceed_room_cap(self):
        ns = {'cap_room_rate':cap_room_rate,'date':date,'_base_direct_nightly_price_for_day':lambda *a:300,'_demand_percent_for_day':lambda *a:(15,20),'_demand_rule_config':lambda: {'floor_eur':99,'cap_eur':159}}
        load_functions('app.py',['direct_nightly_price_for_day'],ns)
        self.assertEqual(ns['direct_nightly_price_for_day']('Bachblick',date(2026,10,4)),149)

    def test_checkout_caps_late_yield_and_channel_override_but_preserves_extras(self):
        class LateDatetime:
            @staticmethod
            def now(tz):
                return datetime(2026,10,4,21,tzinfo=tz)
        ns = {'date':date,'timedelta':timedelta,'datetime':LateDatetime,'ZoneInfo':ZoneInfo,'cap_room_rate':cap_room_rate,'pricing_config':lambda: {},'nightly_direct_rate':lambda day:149,'_booked_nights_next_30_days':lambda day:set(),'_revenue_adjustment_for_day':lambda *a,**kw:(30,85),'PUBLIC_BACHBLICK_NIGHTLY_PRICE':300,'app':SimpleNamespace(extensions={})}
        ns['price_breakdown'] = lambda *a: {'extras':[{'label':'Breakfast','amount':24}],'total':999,'room_total':999,'discounts':[]}
        load_functions('railway_app.py',['direct_checkout_price_breakdown'],ns)
        for getter in [None,lambda *a:350]:
            with self.subTest(override=bool(getter)):
                ns['app'].extensions={'zab_channel_price_for_day':getter}
                result=ns['direct_checkout_price_breakdown']('Bachblick',date(2026,10,4),date(2026,10,5),2,{'breakfast':True})
                self.assertEqual(result['room_total'],149)
                self.assertEqual(result['total'],173)
                self.assertEqual(result['revenue_management'][0]['final_rate'],149)
        ns['nightly_direct_rate']=lambda day:None
        result=ns['direct_checkout_price_breakdown']('Bachblick',date(2028,1,1),date(2028,1,3),2,{})
        self.assertEqual(result['room_total'],298)


if __name__ == '__main__':
    unittest.main()

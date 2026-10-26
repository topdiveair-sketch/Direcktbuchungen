import unittest
from datetime import date
from overnight_tax import overnight_tax_breakdown, with_guest_stay_costs


class StayCostsTests(unittest.TestCase):
    def test_two_guests_one_night(self):
        details = overnight_tax_breakdown(date(2026,11,12), date(2026,11,13), 2)
        self.assertEqual(details["amount"], 5.20)

    def test_year_boundary(self):
        details = overnight_tax_breakdown(date(2026,12,31), date(2027,1,2), 2)
        self.assertTrue(details["known"])
        self.assertEqual(details["amount"], 10.60)

    def test_next_unpublished_year(self):
        details = overnight_tax_breakdown(date(2028,6,1), date(2028,6,2), 1)
        self.assertFalse(details["known"])
        self.assertIsNone(details["amount"])

    def test_payment_unchanged_and_total_stay_calculated(self):
        quote = with_guest_stay_costs({"total":130.0}, date(2026,11,12),date(2026,11,13),2)
        self.assertEqual(quote["total"], 130.0)
        self.assertEqual(quote["stay_total"], 135.20)


if __name__ == "__main__":
    unittest.main()

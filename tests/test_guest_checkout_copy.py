import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuestCheckoutTextTests(unittest.TestCase):
    def test_public_page_excludes_account_information(self):
        home = (ROOT / "templates/index.html").read_text(encoding="utf-8")
        self.assertNotIn("bank_account_holder", home)
        self.assertNotIn("bank_iban_display", home)
        self.assertIn('id="bankDetailsAfterBooking"', home)
        success = (ROOT / "templates/success.html").read_text(encoding="utf-8")
        self.assertIn("booking.status == 'confirmed'", success)

    def test_stay_total_and_local_night_policy(self):
        home = (ROOT / "templates/index.html").read_text(encoding="utf-8")
        for key in ("taxAmount", "stayTotal", "summaryTax", "summaryStayTotal"):
            self.assertIn('id="'+key+'"', home)
        event = (ROOT / "templates/events_2027_2028.html").read_text(encoding="utf-8")
        self.assertNotIn("zwei Nächte Mindestaufenthalt", event)
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("return 1, []", app)

    def test_mobile_and_cancellation_terms(self):
        css = (ROOT / "static/css/homepage-slim.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:390px)", css)
        policy = (ROOT / "stability.py").read_text(encoding="utf-8")
        self.assertIn("90 % des gebuchten Zimmerpreises", policy)
        self.assertIn("früher abgeschlossene Buchungen", policy)


if __name__ == "__main__":
    unittest.main()

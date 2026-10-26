"""Regression checks for the compact booking homepage.

No network access, payments, booking writes, or production configuration.
Run: python -m unittest discover -s tests -p 'test_homepage_slim.py' -v
"""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "templates/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "static/css/homepage-slim.css").read_text(encoding="utf-8")
ROUTES = (ROOT / "app.py").read_text(encoding="utf-8")
STORY = (ROOT / "templates/mariandl-aggsbach-markt.html").read_text(encoding="utf-8")


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.targets = []
        self.tags = Counter()
    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        props = dict(attrs)
        if props.get("id"):
            self.ids.append(props["id"])
        if props.get("href", "").startswith("#"):
            self.targets.append(props["href"][1:])


class HomepageSlimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = Tags()
        cls.doc.feed(INDEX)

    def test_critical_booking_elements_survive(self):
        for marker in ('id="bookingForm"', 'id="checkAvailability"',
                       'id="bookingSubmit"', 'id="liveCalendar"',
                       'id="calendarRoom"', 'id="zimmer"',
                       'id="priceBreakdown"', 'id="guestArea"',
                       'id="requestForm"', 'id="gapNightOffer"',
                       'id="stripePaymentOption"', 'id="openGallery"',
                       'id="openPanorama"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, INDEX)

    def test_five_clear_areas_and_no_duplicate_ids(self):
        for key in ("start", "booking", "ausstattung", "wachau-planen", "fragen"):
            self.assertIn(key, self.doc.ids)
        duplicate = [key for key, count in Counter(self.doc.ids).items() if count > 1]
        self.assertEqual(duplicate, [])
        self.assertEqual(self.doc.tags["section"], 7)

    def test_old_anchor_urls_do_not_break(self):
        for alias in ("basislager", "winter", "eine-nacht", "oktober-direkt",
                      "fruehplaner", "filmgeschichte", "wandern-aggsbach-markt",
                      "aktiv-service", "komoot-wachau-touren", "essen-genuss"):
            self.assertIn(alias, self.doc.ids)
        self.assertEqual([x for x in self.doc.targets if x not in self.doc.ids], [])

    def test_booking_cta_count_and_no_old_promotions(self):
        self.assertLessEqual(INDEX.count('href="#booking"'), 6)
        self.assertNotIn("checkin=2026-10-24", INDEX)
        self.assertNotIn('class="local-event-shortcuts"', INDEX)
        self.assertNotIn('class="benefit-column"', INDEX)
        self.assertNotIn('id="breite-suche" class="active-service"', INDEX)
        self.assertNotIn('id="winter" class="active-service"', INDEX)

    def test_mobile_layout_and_consistent_buttons(self):
        self.assertIn("homepage-slim.css", INDEX)
        self.assertIn('class="zab-slim"', INDEX)
        self.assertIn("@media(max-width:640px)", STYLES)
        self.assertIn(".zab-slim a.btn", STYLES)
        self.assertIn(".zab-slim #bookingSubmit", STYLES)

    def test_mariandl_moved_to_independent_public_page(self):
        self.assertIn('@app.get("/mariandl-aggsbach-markt")', ROUTES)
        self.assertIn('render_template("mariandl-aggsbach-markt.html")', ROUTES)
        self.assertIn('href="/mariandl-aggsbach-markt"', INDEX)
        self.assertIn("lokaler Überlieferung", STORY)
        self.assertIn("unabhängig filmhistorisch bestätigt", STORY)


if __name__ == "__main__":
    unittest.main()

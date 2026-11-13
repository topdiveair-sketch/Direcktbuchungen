import unittest

from scripts.check_homepage_translation_change import visible_homepage_text


class HomepageTextComparisonTests(unittest.TestCase):
    def test_css_cache_buster_does_not_change_homepage_text(self):
        before = '<link rel="stylesheet" href="/static/css/style.css?v=old"><h1>Willkommen</h1>'
        after = '<link rel="stylesheet" href="/static/css/style.css?v=new"><h1>Willkommen</h1>'
        self.assertEqual(visible_homepage_text(before), visible_homepage_text(after))

    def test_markup_and_attributes_do_not_hide_a_copy_change(self):
        before = '<a href="/alt">Direkt buchen</a>'
        after = '<a href="/neu">Jetzt direkt buchen</a>'
        self.assertNotEqual(visible_homepage_text(before), visible_homepage_text(after))

    def test_accessible_text_attributes_are_checked(self):
        before = '<button aria-label="Sprachauswahl">DE</button>'
        after = '<button aria-label="Choose language">DE</button>'
        self.assertNotEqual(visible_homepage_text(before), visible_homepage_text(after))

    def test_script_and_style_source_changes_are_ignored(self):
        before = '<style>.menu{gap:4px}</style><script>const a="alt";</script><p>Guten Tag</p>'
        after = '<style>.menu{gap:8px}</style><script>const a="neu";</script><p>Guten Tag</p>'
        self.assertEqual(visible_homepage_text(before), visible_homepage_text(after))

    def test_html_entities_are_compared_as_displayed(self):
        self.assertEqual(visible_homepage_text("<p>Wachau &amp; Donau</p>"), "Wachau & Donau")


if __name__ == "__main__":
    unittest.main()

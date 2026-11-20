import unittest
from datetime import date, datetime, timedelta, timezone
from channel_guard import Interval, reconcile, conflicts, available

D = date.fromisoformat

class ChannelGuardTests(unittest.TestCase):
    def test_checkout_is_exclusive(self):
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-13"))
        b = Interval("direct", "b", D("2026-10-13"), D("2026-10-14"))
        self.assertEqual(conflicts([a, b]), [])

    def test_overlapping_sources(self):
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-14"))
        b = Interval("airbnb", "b", D("2026-10-13"), D("2026-10-15"))
        self.assertEqual(len(conflicts([a, b])), 1)

    def test_duplicate_import(self):
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-13"))
        self.assertEqual(reconcile([a, a]), [a])

    def test_cancel_tombstone(self):
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-13"))
        canceled = Interval("booking", "a", a.start, a.end, "cancelled")
        self.assertEqual(conflicts([a, canceled]), [])
        self.assertEqual(reconcile([canceled, a]), [canceled])

    def test_ambiguous_updates_rejected(self):
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-13"))
        b = Interval("booking", "a", D("2026-10-12"), D("2026-10-14"))
        with self.assertRaises(ValueError):
            reconcile([a, b])

    def test_stale_feed_fails_closed(self):
        now = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        self.assertFalse(available(D("2026-10-12"), D("2026-10-13"), [],
            {"booking": now - timedelta(minutes=31)}, ["booking"], now))
        self.assertTrue(available(D("2026-10-12"), D("2026-10-13"), [],
            {"booking": now - timedelta(minutes=10)}, ["booking"], now))

    def test_cancelled_only_does_not_block(self):
        now = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        a = Interval("booking", "a", D("2026-10-12"), D("2026-10-13"), "cancelled")
        self.assertTrue(available(a.start, a.end, [a],
            {"booking": now}, ["booking"], now))

if __name__ == "__main__":
    unittest.main()

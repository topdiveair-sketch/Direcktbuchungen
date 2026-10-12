import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from backup_retention import prune_auto_backups

class RetentionTests(unittest.TestCase):
    def test_keep_current_manual_and_daily(self):
        now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            for i in range(110):
                stamp = now - timedelta(minutes=15*i)
                name = "zab-auto-" + stamp.strftime("%Y%m%d-%H%M%S") + ".db"
                (p / name).write_bytes(b"x"*128)
            manual = p / "zab-manual-20261001-000000.db"
            manual.write_bytes(b"m"*128)
            live = p / "zab.db"
            live.write_bytes(b"v"*128)
            result = prune_auto_backups(p, now)
            self.assertGreater(result["deleted"], 50)
            self.assertEqual(manual.read_bytes(), b"m"*128)
            self.assertEqual(live.read_bytes(), b"v"*128)
            self.assertGreaterEqual(len(list(p.glob("zab-auto-*.db"))), 24)

if __name__ == "__main__":
    unittest.main()

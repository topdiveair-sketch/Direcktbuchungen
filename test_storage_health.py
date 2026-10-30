"""Storage health inspects isolated files without altering bookings or backups."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from storage_health import storage_snapshot


class StorageHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "bookings.db"

    def create_database(self):
        conn = sqlite3.connect(self.database)
        conn.execute("CREATE TABLE bookings(id INTEGER, guest TEXT)")
        conn.execute("INSERT INTO bookings VALUES(42,'PRIVATE GUEST')")
        conn.commit()
        conn.close()

    def test_missing_database_is_not_created(self):
        result = storage_snapshot(self.database, self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "database_missing")
        self.assertFalse(self.database.exists())

    def test_healthy_database_on_actual_mount_is_read_only(self):
        self.create_database()
        before = hashlib.sha256(self.database.read_bytes()).digest()
        with patch("storage_health.os.path.ismount", return_value=True):
            result = storage_snapshot(self.database, self.root)
        self.assertTrue(result["ok"])
        self.assertFalse(result["restore_tested"])
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).digest(), before)
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn(str(self.root), str(result))

    def test_unmounted_directory_never_claims_persistence(self):
        self.create_database()
        with patch("storage_health.os.path.ismount", return_value=False):
            result = storage_snapshot(self.database, self.root)
        self.assertTrue(result["database_readable"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["volume_mounted"])

    def test_database_outside_volume_is_unhealthy(self):
        self.create_database()
        with patch("storage_health.os.path.ismount", return_value=True):
            result = storage_snapshot(self.database, self.root / "other-volume")
        self.assertFalse(result["database_on_volume"])
        self.assertFalse(result["ok"])

    def test_corrupt_database_fails_safely_without_exposing_contents(self):
        self.database.write_bytes(b"PRIVATE malformed database")
        result = storage_snapshot(self.database, self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "database_unreadable")
        self.assertNotIn("PRIVATE", str(result))

    def test_missing_booking_schema_is_not_marked_ready(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute("CREATE TABLE other(value)")
        with patch("storage_health.os.path.ismount", return_value=True):
            result = storage_snapshot(self.database, self.root)
        self.assertTrue(result["integrity_ok"])
        self.assertFalse(result["bookings_table"])
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

"""Backup and restore tests using local disposable SQLite databases only."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sqlite_backup import verified_sqlite_backup


class SQLiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "live.db"
        self.target = self.root / "backup.db"

    def test_backup_restores_committed_wal_data_and_leaves_live_database_untouched(self):
        source = sqlite3.connect(self.database)
        self.addCleanup(source.close)
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("PRAGMA wal_autocheckpoint=0")
        source.execute("CREATE TABLE bookings(id INTEGER,status TEXT)")
        source.execute("INSERT INTO bookings VALUES(42,'confirmed')")
        source.commit()
        source.execute("INSERT INTO bookings VALUES(99,'uncommitted')")
        self.assertEqual(verified_sqlite_backup(self.database, self.target), self.target)
        with sqlite3.connect(self.target) as restored:
            self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(restored.execute("SELECT * FROM bookings").fetchall(), [(42, "confirmed")])
        self.assertEqual(source.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], 2)
        source.rollback()
        self.assertEqual(source.execute("SELECT COUNT(*) FROM bookings").fetchone()[0], 1)

    def test_failed_backup_preserves_previous_backup_and_cleans_temporary_file(self):
        self.database.write_bytes(b"not a SQLite database")
        self.target.write_bytes(b"previous valid backup")
        with self.assertRaises(sqlite3.DatabaseError):
            verified_sqlite_backup(self.database, self.target)
        self.assertEqual(self.target.read_bytes(), b"previous valid backup")
        self.assertEqual(list(self.root.glob(".zab-backup-*")), [])

    def test_missing_source_is_not_created(self):
        with self.assertRaises(sqlite3.OperationalError):
            verified_sqlite_backup(self.database, self.target)
        self.assertFalse(self.database.exists())
        self.assertFalse(self.target.exists())

    def test_live_database_can_never_be_backup_destination(self):
        with self.assertRaises(ValueError):
            verified_sqlite_backup(self.database, self.database)


if __name__ == "__main__":
    unittest.main()

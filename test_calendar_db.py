"""SQLite transaction and request cleanup regressions, without production workers."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_calendar_sync import load_functions


class CalendarDatabaseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'test.db'
        self.ns = dict(sqlite3=sqlite3, DB_PATH=self.path, contextmanager=contextmanager)
        load_functions('app.py', ['db'], self.ns)
        with self.ns['db']() as conn:
            conn.execute('CREATE TABLE records(value)')

    def test_db_commits_and_closes_connection(self):
        with self.ns['db']() as conn:
            conn.execute('INSERT INTO records VALUES(1)')
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')
        with self.ns['db']() as reader:
            self.assertEqual(reader.execute('SELECT value FROM records').fetchone()[0], 1)

    def test_db_rolls_back_and_closes_on_failure(self):
        with self.assertRaises(ValueError):
            with self.ns['db']() as conn:
                conn.execute('INSERT INTO records VALUES(1)')
                raise ValueError('failed')
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')
        with self.ns['db']() as reader:
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)

class PaymentCleanupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'test.db'
        self.conn = sqlite3.connect(self.path, timeout=0.05)
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE bookings(id INTEGER PRIMARY KEY,status,paid,hold_expires_at,released_at,release_reason);
            INSERT INTO bookings VALUES(1,'confirmed',1,'2000-01-01','','');
        ''')

        @contextmanager
        def db():
            with self.conn:
                yield self.conn

        self.ns = dict(datetime=datetime, db=db)
        load_functions('payment_hold.py', ['release_expired'], self.ns, 'init_payment_hold')

    def test_no_expired_hold_cleanup_does_not_require_writer_lock(self):
        writer = sqlite3.connect(self.path, timeout=0.05)
        self.addCleanup(writer.close)
        writer.execute("UPDATE bookings SET release_reason='held writer lock' WHERE id=1")
        # Read access remains possible while another request holds the writer lock.
        self.assertEqual(self.ns['release_expired'](), 0)
        writer.rollback()

    def test_only_expired_unpaid_pending_holds_are_released(self):
        future = (datetime.now() + timedelta(days=1)).isoformat(timespec='seconds')
        self.conn.executemany('INSERT INTO bookings VALUES(?,?,?,?,?,?)', [
            (2, 'pending', 0, '2000-01-01', '', ''),
            (3, 'pending', 1, '2000-01-01', '', ''),
            (4, 'pending', 0, future, '', ''),
            (5, 'pending', 0, '', '', ''),
        ])
        self.conn.commit()
        self.assertEqual(self.ns['release_expired'](), 1)
        rows = self.conn.execute('SELECT id,status,released_at FROM bookings ORDER BY id').fetchall()
        self.assertEqual([r[1] for r in rows], ['confirmed', 'cancelled', 'pending', 'pending', 'pending'])
        self.assertTrue(rows[1][2])
        self.assertEqual(self.ns['release_expired'](), 0)


if __name__ == '__main__':
    unittest.main()

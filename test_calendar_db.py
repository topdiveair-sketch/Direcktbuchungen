"""SQLite transaction and request cleanup regressions, without production workers."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from test_calendar_sync import load_functions


class CalendarDatabaseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'test.db'
        self.ns = dict(sqlite3=sqlite3, DB_PATH=self.path, contextmanager=contextmanager,
                       _DB_LOCK=threading.RLock())
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

    def test_reader_and_writer_scopes_cannot_deadlock_each_other(self):
        with self.ns['db']() as conn:
            conn.executemany('INSERT INTO records VALUES(?)', [(1,), (2,)])
        reader_ready = threading.Event()
        release_reader = threading.Event()
        writer_started = threading.Event()
        writer_entered = threading.Event()
        failures = []

        def read():
            try:
                with self.ns['db']() as conn:
                    cursor = conn.execute('SELECT value FROM records')
                    cursor.fetchone()  # Keep the SELECT active while the writer starts.
                    reader_ready.set()
                    if not release_reader.wait(3):
                        raise AssertionError('Reader was not released')
                    cursor.close()
            except Exception as exc:
                failures.append(exc)

        def write():
            writer_started.set()
            try:
                with self.ns['db']() as conn:
                    writer_entered.set()
                    conn.execute('INSERT INTO records VALUES(3)')
            except Exception as exc:
                failures.append(exc)

        reader = threading.Thread(target=read)
        writer = threading.Thread(target=write)
        reader.start()
        try:
            self.assertTrue(reader_ready.wait(3))
            writer.start()
            self.assertTrue(writer_started.wait(3))
            self.assertFalse(writer_entered.wait(0.05))
        finally:
            release_reader.set()
            reader.join(3)
            if writer.ident:
                writer.join(3)
        self.assertFalse(reader.is_alive() or writer.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(writer_entered.is_set())
        with self.ns['db']() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM records').fetchone()[0], 3)

    def test_nested_read_scope_does_not_deadlock(self):
        with self.ns['db']() as outer:
            outer.execute('INSERT INTO records VALUES(1)')
            with self.ns['db']() as inner:
                self.assertEqual(inner.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)

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

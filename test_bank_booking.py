"""Bank booking integration in an isolated DB. No live payments or email."""
from datetime import date, datetime, timedelta, timezone
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='zab-bank-test-')
os.environ['SECRET_KEY'] = 'isolated-bank-tests'
os.environ['BANK_ACCOUNT_HOLDER'] = 'Test owner'
os.environ['BANK_IBAN'] = 'AT000000000000000000'
with patch("threading.Thread.start"):
    import app as core
from bank_booking import init_bank_booking

init_bank_booking(core.app, core.db, start_worker=False)


def availability_in_conn(conn,room,arrival,departure):
    row=conn.execute("SELECT id FROM bookings WHERE room=? AND status IN ('confirmed','pending') AND arrival<? AND departure>?",(room,departure.isoformat(),arrival.isoformat())).fetchone()
    return (not row, 'Belegt' if row else 'Verfügbar')


def availability(room,arrival,departure):
    with core.db() as conn:
        return availability_in_conn(conn,room,arrival,departure)


class BankBookingTests(unittest.TestCase):
    def setUp(self):
        with core.db() as conn:
            conn.execute('DELETE FROM bookings')
        self.client=core.app.test_client()
        self.sender=Mock(return_value=True)
        core.app.extensions['zab_send_confirmation']=self.sender
        self.patches=[patch.object(core,'room_available',availability),patch.object(core,'room_available_in_conn',availability_in_conn),patch('bank_booking.send_transactional_email',return_value=(True,''))]
        for item in self.patches: item.start()
        self.addCleanup(lambda:[item.stop() for item in self.patches])
        self.arrival=date.today()+timedelta(days=10)
        self.form=dict(room='Bachblick',arrival=self.arrival.isoformat(),departure=(self.arrival+timedelta(days=2)).isoformat(),adults='2',first_name='Test',last_name='Guest',email='guest@example.test',phone='test',payment_method='Banküberweisung',idempotency_key='bank-first')

    def row(self):
        with core.db() as conn:
            return dict(conn.execute('SELECT * FROM bookings ORDER BY id DESC LIMIT 1').fetchone())

    def test_immediate_confirmation_deadline_and_idempotency(self):
        r=self.client.post('/book',data=self.form)
        self.assertEqual(r.status_code,200)
        self.assertIn('Deine Buchung ist bestätigt',r.get_data(as_text=True))
        self.assertNotIn('bankMailButton',r.get_data(as_text=True))
        row=self.row()
        self.assertEqual(row['status'],'confirmed')
        self.assertEqual(row['paid'],0)
        hours=(datetime.fromisoformat(row['bank_payment_due_at'])-datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()/3600
        self.assertTrue(47.9<hours<=48)
        self.assertFalse(availability('Bachblick',self.arrival,self.arrival+timedelta(days=2))[0])
        self.assertEqual(self.client.post('/book',data=self.form).status_code,200)
        with core.db() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],1)
        self.assertTrue(self.sender.called)

    def test_second_booking_cannot_take_reserved_room(self):
        self.client.post('/book',data=self.form)
        second=dict(self.form,idempotency_key='bank-second')
        self.assertEqual(self.client.post('/book',data=second).status_code,302)
        with core.db() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],1)

    def test_paid_booking_is_retained_after_deadline(self):
        self.client.post('/book',data=self.form)
        with core.db() as conn: conn.execute("UPDATE bookings SET bank_payment_due_at='2000-01-01',paid=1")
        self.assertEqual(core.app.extensions['zab_release_unpaid_bank_bookings'](),0)
        self.assertEqual(self.row()['status'],'confirmed')

    def test_unpaid_booking_expires_once_and_releases_room(self):
        self.client.post('/book',data=self.form)
        with core.db() as conn: conn.execute("UPDATE bookings SET bank_payment_due_at='2000-01-01'")
        cleanup=core.app.extensions['zab_release_unpaid_bank_bookings']
        self.assertEqual(cleanup(),1)
        self.assertEqual(cleanup(),0)
        self.assertEqual(self.row()['status'],'cancelled')
        with core.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM email_outbox WHERE booking_id=? AND role='bank_expired_guest'",(self.row()['id'],)).fetchone()[0],1)
        self.assertTrue(availability('Bachblick',self.arrival,self.arrival+timedelta(days=2))[0])
        with self.client.session_transaction() as session: session['admin']=True
        self.client.post(f"/admin/booking/{self.row()['id']}/paid")
        self.assertEqual(self.row()['status'],'cancelled')

    def test_disabled_onsite_and_short_notice_bank_rejected(self):
        self.assertEqual(self.client.post('/book',data=dict(self.form,payment_method='Vor Ort')).status_code,302)
        tomorrow=date.today()+timedelta(days=1)
        self.assertEqual(self.client.post('/book',data=dict(self.form,arrival=tomorrow.isoformat(),departure=(tomorrow+timedelta(days=1)).isoformat())).status_code,302)
        with core.db() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],0)

    def test_unconfigured_bank_does_not_reserve(self):
        with patch.dict(os.environ,{'BANK_IBAN':''}):
            self.assertEqual(self.client.post('/book',data=self.form).status_code,302)
        with core.db() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],0)

if __name__=='__main__': unittest.main()

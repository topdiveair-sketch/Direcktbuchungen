import test from 'node:test';
import assert from 'node:assert/strict';
import { availabilitySignals } from '../src/adapters/booking.js';
import { windisSignals, WINDIS_PARTNER_SEED } from '../src/adapters/windis.js';

test('booking adapter calculates open nights without exposing iCal secret', () => {
  const result = availabilitySignals({ ok: true, source: 'booking-ical-live', events: [{ start: '2026-09-01', end: '2026-09-03' }] }, { horizonDays: 5, from: new Date('2026-09-01T12:00:00Z') });
  assert.equal(result.blockedNights, 2);
  assert.equal(result.openNights, 3);
  assert.equal(result.occupancyRatio, 0.4);
});

test('windis adapter turns internal partner rows into planning signals only', () => {
  const result = windisSignals({ partners: WINDIS_PARTNER_SEED });
  assert.equal(result.partnerContacts, 8);
  assert.equal(result.priorityAOpen, 5);
  assert.ok(result.openPartnerActions > 0);
});

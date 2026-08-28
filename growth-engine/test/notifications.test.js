import test from 'node:test';
import assert from 'node:assert/strict';
import { buildDailyNotification, mergeNotifications } from '../src/notifications.js';

test('daily notification surfaces approvals as action priority', () => {
  const notification = buildDailyNotification({
    zuhauseSignals: { openNights: 8, occupancyRatio: 0.73 },
    windisSignals: { openPartnerActions: 4, priorityAOpen: 2 },
    execution: [{ status: 'ready' }],
    approvals: [{ status: 'pending' }],
  });
  assert.equal(notification.priority, 'action');
  assert.equal(notification.summary.approvalsPending, 1);
  assert.equal(notification.summary.zuhauseAmBach.openNights30d, 8);
});

test('warnings take high priority', () => {
  const notification = buildDailyNotification({ warnings: ['booking source unavailable'] });
  assert.equal(notification.priority, 'high');
  assert.equal(notification.summary.warnings, 1);
});

test('same-day duplicate pending summaries are suppressed', () => {
  const first = buildDailyNotification();
  const second = { ...buildDailyNotification(), createdAt: first.createdAt };
  assert.equal(mergeNotifications([first], [second]).length, 1);
});

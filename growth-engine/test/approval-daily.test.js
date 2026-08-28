import test from 'node:test';
import assert from 'node:assert/strict';
import { ApprovalQueue } from '../src/approval-queue.js';
import { DailyPlanner } from '../src/daily-planner.js';

test('approval queue stores and resolves decisions', () => {
  const queue = new ApprovalQueue();
  const item = queue.enqueue({ brand: 'windis', kind: 'publish', task: 'Publish reel' });
  assert.equal(queue.pending().length, 1);
  queue.decide(item.id, 'approved', 'ok');
  assert.equal(queue.pending().length, 0);
});

test('daily planner returns autonomous research and draft work', () => {
  const planner = new DailyPlanner();
  const result = planner.buildDay({
    zuhauseSignals: { openNights: 4, inquiries: 0, confirmedBookings: 0 },
    windisSignals: { partnerContacts: 3, partnerReplies: 0 },
  });
  assert.ok(result.execution.some((item) => item.status === 'ready'));
  assert.ok(result.execution.some((item) => item.brand === 'windis'));
});

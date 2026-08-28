import test from 'node:test';
import assert from 'node:assert/strict';
import { buildOutcome, summarizeOutcomes } from '../src/outcomes.js';

test('measures actual economic contribution against an approved action', () => {
  const outcome = buildOutcome({ approval: { id: 'a1', status: 'approved', brand: 'zuhause_am_bach', kind: 'publish', task: 'Direct booking campaign', expectedRevenue: 300, expectedCost: 50, successProbability: 0.5 }, actualRevenue: 240, actualCost: 40 });
  assert.equal(outcome.actualContribution, 200);
  assert.equal(outcome.expectedContribution, 100);
  assert.equal(outcome.varianceToExpected, 100);
});

test('rejects outcome measurement for an unapproved action', () => {
  assert.throws(() => buildOutcome({ approval: { id: 'a2', status: 'pending' }, actualRevenue: 100 }), /approval_must_be_approved/);
});

test('summarizes portfolio economics', () => {
  const summary = summarizeOutcomes([{ actualRevenue: 300, actualCost: 50, actualContribution: 250 }, { actualRevenue: 20, actualCost: 40, actualContribution: -20 }]);
  assert.equal(summary.totalRevenue, 320);
  assert.equal(summary.totalCost, 90);
  assert.equal(summary.totalContribution, 230);
  assert.equal(summary.profitableActions, 1);
  assert.equal(summary.lossMakingActions, 1);
});

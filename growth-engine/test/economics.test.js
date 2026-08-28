import test from 'node:test';
import assert from 'node:assert/strict';
import { economicScore, rankEconomicActions } from '../src/economics.js';

test('calculates expected contribution after probability and cost', () => {
  const result = economicScore({ expectedRevenue: 300, expectedCost: 50, successProbability: 0.5 });
  assert.equal(result.expectedContribution, 100);
  assert.equal(result.roi, 2);
});

test('ranks actions by expected economic contribution', () => {
  const ranked = rankEconomicActions([
    { id: 'a', brand: 'zuhause_am_bach', expectedRevenue: 100, expectedCost: 20, successProbability: 0.5 },
    { id: 'b', brand: 'windis', expectedRevenue: 300, expectedCost: 40, successProbability: 0.5 },
  ]);
  assert.equal(ranked[0].id, 'b');
});

test('marks economics unknown when no revenue evidence exists', () => {
  assert.equal(economicScore({ expectedCost: 0 }).confidence, 'unknown');
});

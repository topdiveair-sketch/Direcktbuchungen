import { economicScore } from './economics.js';

const finiteNonNegative = (value, name) => {
  if (value === null || value === undefined || value === '') throw new Error(`${name}_required`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${name}_invalid`);
  if (parsed < 0) throw new Error('negative_financial_value');
  return parsed;
};
const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;

export function buildOutcome({ approval, execution = null, actualRevenue, actualCost, note = '', source = 'manual' } = {}) {
  if (!approval?.id) throw new Error('approval_required');
  if (approval.status !== 'approved') throw new Error('approval_must_be_approved');
  if (!execution?.id) throw new Error('execution_required_before_outcome');
  if (execution.status !== 'executed') throw new Error('execution_must_be_completed_before_outcome');
  const revenue = finiteNonNegative(actualRevenue, 'actual_revenue');
  const cost = finiteNonNegative(actualCost, 'actual_cost');
  const expected = economicScore(approval);
  const actualContribution = revenue - cost;
  const actualRoi = cost > 0 ? actualContribution / cost : actualContribution > 0 ? null : 0;
  return {
    id: crypto.randomUUID(),
    approvalId: approval.id,
    executionId: execution.id,
    brand: approval.brand,
    kind: approval.kind,
    task: approval.task,
    measuredAt: new Date().toISOString(),
    source,
    note,
    expectedRevenue: expected.expectedRevenue,
    expectedCost: expected.expectedCost,
    expectedContribution: expected.expectedContribution,
    actualRevenue: revenue,
    actualCost: cost,
    actualContribution,
    actualRoi,
    varianceToExpected: expected.expectedContribution == null ? null : actualContribution - expected.expectedContribution,
    profitable: actualContribution > 0,
  };
}

export function summarizeOutcomes(outcomes = []) {
  const totalRevenue = outcomes.reduce((sum, item) => sum + number(item.actualRevenue), 0);
  const totalCost = outcomes.reduce((sum, item) => sum + number(item.actualCost), 0);
  const totalContribution = outcomes.reduce((sum, item) => sum + number(item.actualContribution), 0);
  const measuredActions = outcomes.length;
  const profitableActions = outcomes.filter((item) => number(item.actualContribution) > 0).length;
  const lossMakingActions = outcomes.filter((item) => number(item.actualContribution) < 0).length;
  const roi = measuredActions === 0 ? null : totalCost > 0 ? totalContribution / totalCost : totalContribution > 0 ? null : 0;
  return { measuredActions, profitableActions, lossMakingActions, totalRevenue, totalCost, totalContribution, roi };
}

import { economicScore } from './economics.js';

const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;

export function buildOutcome({ approval, actualRevenue = 0, actualCost = 0, note = '', source = 'manual' } = {}) {
  if (!approval?.id) throw new Error('approval_required');
  if (approval.status !== 'approved') throw new Error('approval_must_be_approved');
  const revenue = number(actualRevenue);
  const cost = number(actualCost);
  if (revenue < 0 || cost < 0) throw new Error('negative_financial_value');
  const expected = economicScore(approval);
  const actualContribution = revenue - cost;
  const actualRoi = cost > 0 ? actualContribution / cost : actualContribution > 0 ? null : 0;
  return {
    id: crypto.randomUUID(),
    approvalId: approval.id,
    brand: approval.brand,
    kind: approval.kind,
    task: approval.task,
    measuredAt: new Date().toISOString(),
    source,
    note,
    expectedContribution: expected.expectedContribution,
    actualRevenue: revenue,
    actualCost: cost,
    actualContribution,
    actualRoi,
    varianceToExpected: actualContribution - expected.expectedContribution,
  };
}

export function summarizeOutcomes(outcomes = []) {
  const totalRevenue = outcomes.reduce((sum, item) => sum + number(item.actualRevenue), 0);
  const totalCost = outcomes.reduce((sum, item) => sum + number(item.actualCost), 0);
  const totalContribution = outcomes.reduce((sum, item) => sum + number(item.actualContribution), 0);
  const measuredActions = outcomes.length;
  const profitableActions = outcomes.filter((item) => number(item.actualContribution) > 0).length;
  const lossMakingActions = outcomes.filter((item) => number(item.actualContribution) < 0).length;
  const roi = totalCost > 0 ? totalContribution / totalCost : totalContribution > 0 ? null : 0;
  return { measuredActions, profitableActions, lossMakingActions, totalRevenue, totalCost, totalContribution, roi };
}

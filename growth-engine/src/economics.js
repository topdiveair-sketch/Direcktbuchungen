const finiteOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function economicScore(action = {}, context = {}) {
  const expectedRevenue = finiteOrNull(action.expectedRevenue ?? context.expectedRevenue);
  const expectedCost = finiteOrNull(action.expectedCost ?? context.expectedCost);
  const rawProbability = finiteOrNull(action.successProbability ?? context.successProbability);
  const successProbability = rawProbability == null ? null : clamp(rawProbability, 0, 1);
  const complete = expectedRevenue != null && expectedCost != null && successProbability != null;
  const expectedContribution = complete ? expectedRevenue * successProbability - expectedCost : null;
  const roi = !complete ? null : expectedCost > 0 ? expectedContribution / expectedCost : expectedContribution > 0 ? null : 0;
  const confidence = !complete ? 'unknown' : 'estimated';
  return { expectedRevenue, expectedCost, successProbability, expectedContribution, roi, confidence };
}

export function rankEconomicActions(actions = [], contexts = {}) {
  return actions.map((action) => {
    const economics = economicScore(action, contexts[action.brand] || {});
    return { ...action, economics };
  }).sort((a, b) => {
    const av = a.economics.expectedContribution;
    const bv = b.economics.expectedContribution;
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return bv - av;
  });
}

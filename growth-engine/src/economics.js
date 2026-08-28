const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function economicScore(action = {}, context = {}) {
  const expectedRevenue = number(action.expectedRevenue ?? context.expectedRevenue);
  const expectedCost = number(action.expectedCost ?? context.expectedCost);
  const probability = clamp(number(action.successProbability ?? context.successProbability ?? 0.5), 0, 1);
  const expectedContribution = expectedRevenue * probability - expectedCost;
  const roi = expectedCost > 0 ? expectedContribution / expectedCost : expectedContribution > 0 ? null : 0;
  const confidence = action.expectedRevenue == null && context.expectedRevenue == null ? 'unknown' : action.successProbability == null && context.successProbability == null ? 'low' : 'estimated';
  return { expectedRevenue, expectedCost, successProbability: probability, expectedContribution, roi, confidence };
}

export function rankEconomicActions(actions = [], contexts = {}) {
  return actions.map((action) => {
    const economics = economicScore(action, contexts[action.brand] || {});
    return { ...action, economics };
  }).sort((a, b) => b.economics.expectedContribution - a.economics.expectedContribution);
}

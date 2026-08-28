const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const keyOf = (item = {}) => `${item.brand || 'unknown'}:${item.kind || 'unknown'}:${item.channel || 'default'}`;

export function buildLearningProfile(outcomes = []) {
  const groups = new Map();
  for (const item of outcomes) {
    const key = keyOf(item);
    const list = groups.get(key) || [];
    list.push(item);
    groups.set(key, list);
  }
  return Object.fromEntries([...groups.entries()].map(([key, list]) => {
    const wins = list.filter((item) => Number(item.actualContribution || 0) > 0).length;
    const averageContribution = list.reduce((sum, item) => sum + Number(item.actualContribution || 0), 0) / list.length;
    const empiricalProbability = (wins + 1) / (list.length + 2);
    return [key, { samples: list.length, wins, empiricalProbability, averageContribution }];
  }));
}

export function learnedProbability(action = {}, profile = {}) {
  const learned = profile[keyOf(action)];
  const prior = clamp(Number(action.successProbability ?? 0.5), 0, 1);
  if (!learned) return prior;
  const weight = Math.min(0.8, learned.samples / 10);
  return clamp(prior * (1 - weight) + learned.empiricalProbability * weight, 0.05, 0.95);
}

export function applyLearning(action = {}, profile = {}) {
  const learned = profile[keyOf(action)] || null;
  return { ...action, successProbability: learnedProbability(action, profile), learning: learned };
}

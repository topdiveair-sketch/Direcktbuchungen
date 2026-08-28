const now = () => new Date().toISOString();

export function buildDailyNotification({ zuhauseSignals = {}, windisSignals = {}, execution = [], approvals = [], warnings = [] } = {}) {
  const openNights = Number(zuhauseSignals.openNights || 0);
  const ready = execution.filter((item) => item.status === 'ready').length;
  const pending = approvals.filter((item) => item.status === 'pending').length;
  const warningCount = warnings.length;
  const priority = warningCount > 0 ? 'high' : pending > 0 ? 'action' : 'info';

  return {
    id: crypto.randomUUID(),
    createdAt: now(),
    kind: 'daily_summary',
    priority,
    status: 'pending',
    title: pending > 0 ? `Growth Engine: ${pending} Freigabe${pending === 1 ? '' : 'n'} offen` : 'Growth Engine: Tageslauf abgeschlossen',
    summary: {
      zuhauseAmBach: { openNights30d: openNights, occupancyRatio30d: zuhauseSignals.occupancyRatio ?? null },
      windis: { openPartnerActions: Number(windisSignals.openPartnerActions || 0), priorityAOpen: Number(windisSignals.priorityAOpen || 0) },
      readyActions: ready,
      approvalsPending: pending,
      warnings: warningCount,
    },
  };
}

export function mergeNotifications(existing = [], incoming = []) {
  const result = [...existing];
  for (const item of incoming) {
    const duplicate = result.some((entry) => entry.status === 'pending' && entry.kind === item.kind && entry.title === item.title && entry.createdAt?.slice(0, 10) === item.createdAt?.slice(0, 10));
    if (!duplicate) result.push(item);
  }
  return result.slice(-100);
}

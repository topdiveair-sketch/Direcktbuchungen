import { Agent, routeAgentRequest } from 'agents';
import { DailyPlanner } from '../../src/daily-planner.js';
import { availabilitySignals } from '../../src/adapters/booking.js';
import { windisSignals, WINDIS_PARTNER_SEED, WINDIS_KPI_SEED } from '../../src/adapters/windis.js';

const DAILY_CRON = '0 7 * * *';

function json(body, status = 200) {
  return Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
}

function authorized(request, env) {
  if (!env.ADMIN_TOKEN) return false;
  return request.headers.get('Authorization') === `Bearer ${env.ADMIN_TOKEN}`;
}

function mergeApprovals(existing, incoming) {
  const result = [...existing];
  for (const item of incoming) {
    const duplicate = result.some((entry) =>
      entry.status === 'pending' &&
      entry.brand === item.brand &&
      entry.kind === item.kind &&
      entry.task === item.task
    );
    if (!duplicate) result.push(item);
  }
  return result.slice(-200);
}

export class GrowthRuntime extends Agent {
  initialState = {
    lastRunAt: null,
    lastResult: null,
    approvals: [],
    warnings: [],
  };

  async onStart() {
    const cronSchedules = await this.listSchedules({ type: 'cron' });
    const exists = cronSchedules.some(
      (schedule) => schedule.callback === 'dailyRun' && schedule.cron === DAILY_CRON,
    );
    if (!exists) await this.schedule(DAILY_CRON, 'dailyRun', { source: 'scheduler' });
  }

  async loadZuhauseSignals(warnings) {
    if (!this.env.BOOKING_WORKER_URL) {
      warnings.push('BOOKING_WORKER_URL is not configured');
      return { openNights: 0, source: 'missing' };
    }
    const response = await fetch(this.env.BOOKING_WORKER_URL, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Booking worker HTTP ${response.status}`);
    return availabilitySignals(await response.json(), { horizonDays: 30 });
  }

  async loadWindisSignals(warnings) {
    if (!this.env.WINDIS_DATA_URL) {
      warnings.push('WINDIS_DATA_URL not configured; reviewed repository seed is used');
      return windisSignals({ partners: WINDIS_PARTNER_SEED, kpis: WINDIS_KPI_SEED });
    }
    const response = await fetch(this.env.WINDIS_DATA_URL, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Windis data HTTP ${response.status}`);
    const payload = await response.json();
    return windisSignals(payload);
  }

  async dailyRun(payload = { source: 'manual' }) {
    const warnings = [];
    const planner = new DailyPlanner();

    let zuhauseSignals;
    try {
      zuhauseSignals = await this.loadZuhauseSignals(warnings);
    } catch (error) {
      warnings.push(`Zuhause data error: ${error?.message || String(error)}`);
      zuhauseSignals = { openNights: 0, source: 'error' };
    }

    let windisSignalsValue;
    try {
      windisSignalsValue = await this.loadWindisSignals(warnings);
    } catch (error) {
      warnings.push(`Windis data error: ${error?.message || String(error)}`);
      windisSignalsValue = windisSignals({ partners: WINDIS_PARTNER_SEED, kpis: WINDIS_KPI_SEED });
    }

    const result = planner.buildDay({
      zuhauseSignals,
      windisSignals: windisSignalsValue,
    });

    const nextState = {
      ...this.state,
      lastRunAt: new Date().toISOString(),
      lastResult: {
        source: payload?.source || 'unknown',
        zuhauseSignals,
        windisSignals: windisSignalsValue,
        execution: result.execution,
      },
      approvals: mergeApprovals(this.state.approvals || [], result.approvalsPending || []),
      warnings,
    };
    this.setState(nextState);
    return nextState.lastResult;
  }

  decideApproval(id, decision, note = '') {
    if (!['approved', 'rejected'].includes(decision)) throw new Error('Invalid decision');
    const approvals = (this.state.approvals || []).map((item) =>
      item.id === id
        ? { ...item, status: decision, note, decidedAt: new Date().toISOString() }
        : item,
    );
    this.setState({ ...this.state, approvals });
    return approvals.find((item) => item.id === id) || null;
  }

  async onRequest(request) {
    const url = new URL(request.url);
    if (!authorized(request, this.env)) return json({ error: 'unauthorized' }, 401);

    if (request.method === 'GET' && url.pathname.endsWith('/status')) {
      return json({
        lastRunAt: this.state.lastRunAt,
        lastResult: this.state.lastResult,
        warnings: this.state.warnings,
        approvals: (this.state.approvals || []).filter((item) => item.status === 'pending'),
        schedule: DAILY_CRON,
      });
    }

    if (request.method === 'POST' && url.pathname.endsWith('/run-now')) {
      return json(await this.dailyRun({ source: 'manual' }));
    }

    if (request.method === 'POST' && (url.pathname.endsWith('/approve') || url.pathname.endsWith('/reject'))) {
      const body = await request.json();
      const decision = url.pathname.endsWith('/approve') ? 'approved' : 'rejected';
      const item = this.decideApproval(body.id, decision, body.note || '');
      if (!item) return json({ error: 'approval_not_found' }, 404);
      return json(item);
    }

    return json({ error: 'not_found' }, 404);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') {
      return json({ ok: true, service: 'zab-windis-growth-runtime' });
    }
    return (await routeAgentRequest(request, env)) || json({ error: 'not_found' }, 404);
  },
};

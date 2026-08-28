import { Agent, routeAgentRequest } from 'agents';
import { DailyPlanner } from '../../src/daily-planner.js';
import { availabilitySignals } from '../../src/adapters/booking.js';
import { windisSignals, WINDIS_PARTNER_SEED, WINDIS_KPI_SEED } from '../../src/adapters/windis.js';
import { buildDailyNotification, mergeNotifications } from '../../src/notifications.js';

const DAILY_CRON = '0 7 * * *';

function json(body, status = 200) {
  return Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
}

function authorized(request, env) {
  if (!env.ADMIN_TOKEN) return false;
  return request.headers.get('Authorization') === `Bearer ${env.ADMIN_TOKEN}`;
}

function approvalHtml() {
  return `<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Growth Engine Approval</title><style>body{font-family:system-ui,sans-serif;max-width:980px;margin:40px auto;padding:0 16px;line-height:1.4}input,button,textarea{font:inherit}input,textarea{width:100%;box-sizing:border-box;padding:10px;margin:6px 0 12px}button{padding:9px 14px;margin-right:8px;cursor:pointer}.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:12px 0}.muted{opacity:.7}.ok{font-weight:600}</style></head><body><h1>Growth Engine Approval</h1><p class="muted">Status, manueller Lauf und Freigaben für Zuhause am Bach & Windis.</p><label>Agent-Basis-URL</label><input id="base" placeholder="https://.../agents/growth-runtime/main"><label>ADMIN_TOKEN</label><input id="token" type="password"><button id="status">Status laden</button><button id="run">Jetzt ausführen</button><div id="meta"></div><div id="items"></div><script>const $=id=>document.getElementById(id);const auth=()=>({'Authorization':'Bearer '+$('token').value,'Content-Type':'application/json'});async function req(path,opts={}){const r=await fetch($('base').value.replace(/\\/$/,'')+path,{...opts,headers:{...auth(),...(opts.headers||{})}});const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}function render(s){$('meta').innerHTML='<p><b>Letzter Lauf:</b> '+(s.lastRunAt||'—')+'</p><p><b>Schedule:</b> '+(s.schedule||'—')+'</p><p><b>Warnungen:</b> '+((s.warnings||[]).join(' | ')||'keine')+'</p><p><b>Benachrichtigungen:</b> '+((s.notifications||[]).filter(n=>n.status==='pending').length)+'</p>';$('items').innerHTML=(s.approvals||[]).map(a=>'<div class="card"><div class="ok">'+a.brand+' · '+a.kind+'</div><p>'+a.task+'</p><textarea id="n-'+a.id+'" placeholder="Notiz optional"></textarea><button onclick="decide(\\''+a.id+'\\',\\'approve\\')">Freigeben</button><button onclick="decide(\\''+a.id+'\\',\\'reject\\')">Ablehnen</button></div>').join('')||'<p>Keine offenen Freigaben.</p>'}async function load(){render(await req('/status'))}async function decide(id,kind){await req('/'+kind,{method:'POST',body:JSON.stringify({id,note:$('n-'+id).value})});await load()}$('status').onclick=()=>load().catch(e=>alert(e.message));$('run').onclick=async()=>{try{await req('/run-now',{method:'POST'});await load()}catch(e){alert(e.message)}};</script></body></html>`;
}

function mergeApprovals(existing, incoming) {
  const result = [...existing];
  for (const item of incoming) {
    const duplicate = result.some((entry) => entry.status === 'pending' && entry.brand === item.brand && entry.kind === item.kind && entry.task === item.task);
    if (!duplicate) result.push(item);
  }
  return result.slice(-200);
}

export class GrowthRuntime extends Agent {
  initialState = { lastRunAt: null, lastResult: null, approvals: [], notifications: [], warnings: [] };

  async onStart() {
    const cronSchedules = await this.listSchedules({ type: 'cron' });
    const exists = cronSchedules.some((schedule) => schedule.callback === 'dailyRun' && schedule.cron === DAILY_CRON);
    if (!exists) await this.schedule(DAILY_CRON, 'dailyRun', { source: 'scheduler' });
  }

  async loadZuhauseSignals(warnings) {
    if (!this.env.BOOKING_WORKER_URL) { warnings.push('BOOKING_WORKER_URL is not configured'); return { openNights: 0, source: 'missing' }; }
    const response = await fetch(this.env.BOOKING_WORKER_URL, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Booking worker HTTP ${response.status}`);
    return availabilitySignals(await response.json(), { horizonDays: 30 });
  }

  async loadWindisSignals(warnings) {
    if (!this.env.WINDIS_DATA_URL) { warnings.push('WINDIS_DATA_URL not configured; reviewed repository seed is used'); return windisSignals({ partners: WINDIS_PARTNER_SEED, kpis: WINDIS_KPI_SEED }); }
    const response = await fetch(this.env.WINDIS_DATA_URL, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Windis data HTTP ${response.status}`);
    return windisSignals(await response.json());
  }

  async dailyRun(payload = { source: 'manual' }) {
    const warnings = [];
    const planner = new DailyPlanner();
    let zuhauseSignals;
    try { zuhauseSignals = await this.loadZuhauseSignals(warnings); }
    catch (error) { warnings.push(`Zuhause data error: ${error?.message || String(error)}`); zuhauseSignals = { openNights: 0, source: 'error' }; }
    let windisSignalsValue;
    try { windisSignalsValue = await this.loadWindisSignals(warnings); }
    catch (error) { warnings.push(`Windis data error: ${error?.message || String(error)}`); windisSignalsValue = windisSignals({ partners: WINDIS_PARTNER_SEED, kpis: WINDIS_KPI_SEED }); }
    const result = planner.buildDay({ zuhauseSignals, windisSignals: windisSignalsValue });
    const approvals = mergeApprovals(this.state.approvals || [], result.approvalsPending || []);
    const notification = buildDailyNotification({ zuhauseSignals, windisSignals: windisSignalsValue, execution: result.execution, approvals, warnings });
    const nextState = { ...this.state, lastRunAt: new Date().toISOString(), lastResult: { source: payload?.source || 'unknown', zuhauseSignals, windisSignals: windisSignalsValue, execution: result.execution }, approvals, notifications: mergeNotifications(this.state.notifications || [], [notification]), warnings };
    this.setState(nextState);
    return { ...nextState.lastResult, notification };
  }

  decideApproval(id, decision, note = '') {
    if (!['approved', 'rejected'].includes(decision)) throw new Error('Invalid decision');
    const approvals = (this.state.approvals || []).map((item) => item.id === id ? { ...item, status: decision, note, decidedAt: new Date().toISOString() } : item);
    this.setState({ ...this.state, approvals });
    return approvals.find((item) => item.id === id) || null;
  }

  acknowledgeNotification(id) {
    const notifications = (this.state.notifications || []).map((item) => item.id === id ? { ...item, status: 'acknowledged', acknowledgedAt: new Date().toISOString() } : item);
    this.setState({ ...this.state, notifications });
    return notifications.find((item) => item.id === id) || null;
  }

  async onRequest(request) {
    const url = new URL(request.url);
    if (!authorized(request, this.env)) return json({ error: 'unauthorized' }, 401);
    if (request.method === 'GET' && url.pathname.endsWith('/status')) return json({ lastRunAt: this.state.lastRunAt, lastResult: this.state.lastResult, warnings: this.state.warnings, approvals: (this.state.approvals || []).filter((item) => item.status === 'pending'), notifications: (this.state.notifications || []).filter((item) => item.status === 'pending'), schedule: DAILY_CRON });
    if (request.method === 'POST' && url.pathname.endsWith('/run-now')) return json(await this.dailyRun({ source: 'manual' }));
    if (request.method === 'POST' && url.pathname.endsWith('/notifications/ack')) {
      const body = await request.json();
      const item = this.acknowledgeNotification(body.id);
      if (!item) return json({ error: 'notification_not_found' }, 404);
      return json(item);
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
    if (url.pathname === '/health') return json({ ok: true, service: 'zab-windis-growth-runtime' });
    if (url.pathname === '/approval-ui') return new Response(approvalHtml(), { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
    return (await routeAgentRequest(request, env)) || json({ error: 'not_found' }, 404);
  },
};

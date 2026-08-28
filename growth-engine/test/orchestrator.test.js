import test from 'node:test';
import assert from 'node:assert/strict';
import { GrowthOrchestrator } from '../src/orchestrator.js';

test('keeps brands separated', () => {
  const engine = new GrowthOrchestrator();
  engine.ingest({ brand: 'zuhause_am_bach', type: 'visit' });
  engine.ingest({ brand: 'windis', type: 'visit' });
  assert.equal(engine.summarize('zuhause_am_bach').eventCount, 1);
  assert.equal(engine.summarize('windis').eventCount, 1);
});

test('blocks protected actions without approval', () => {
  const engine = new GrowthOrchestrator();
  assert.equal(engine.guard({ kind: 'publish' }).allowed, false);
  assert.equal(engine.guard({ kind: 'sendExternalMessage' }).allowed, false);
  assert.equal(engine.guard({ kind: 'spendMoney' }).allowed, false);
  assert.equal(engine.guard({ kind: 'research' }).allowed, true);
});

test('plans direct-booking work and a gated publish proposal when nights are open', () => {
  const engine = new GrowthOrchestrator();
  const plan = engine.plan('zuhause_am_bach', { openNights: 3 });
  assert.ok(plan.some((item) => item.task.includes('direct-booking')));
  const publish = plan.find((item) => item.kind === 'publish');
  assert.equal(publish.approvalRequired, true);
  assert.equal(publish.autonomous, false);
});

test('plans gated partner outreach only when a Windis opportunity is open', () => {
  const engine = new GrowthOrchestrator();
  const idle = engine.plan('windis', { openPartnerActions: 0, priorityAOpen: 0 });
  assert.equal(idle.some((item) => item.kind === 'sendExternalMessage'), false);
  const active = engine.plan('windis', { openPartnerActions: 1, priorityAOpen: 1 });
  const outreach = active.find((item) => item.kind === 'sendExternalMessage');
  assert.equal(outreach.approvalRequired, true);
  assert.equal(outreach.autonomous, false);
});

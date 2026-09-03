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

test('allows only zero-cost guarded direct-booking publishing', () => {
  const engine = new GrowthOrchestrator();
  assert.equal(engine.guard({ brand: 'zuhause_am_bach', kind: 'publish', channel: 'owned_web', estimatedCostEur: 0, message: 'ok' }).allowed, true);
  assert.equal(engine.guard({ brand: 'zuhause_am_bach', kind: 'publish', channel: 'owned_web', estimatedCostEur: 1, message: 'ok' }).allowed, false);
  assert.equal(engine.guard({ brand: 'windis', kind: 'publish', channel: 'owned_web', estimatedCostEur: 0, message: 'ok' }).allowed, false);
  assert.equal(engine.guard({ brand: 'zuhause_am_bach', kind: 'spendMoney' }).allowed, false);
});

test('plans autonomous zero-cost direct-booking publishing when nights are open', () => {
  const engine = new GrowthOrchestrator();
  const plan = engine.plan('zuhause_am_bach', { openNights: 3 });
  assert.ok(plan.some((item) => item.task.includes('direct-booking')));
  const publish = plan.find((item) => item.kind === 'publish');
  assert.equal(publish.approvalRequired, false);
  assert.equal(publish.autonomous, true);
  assert.equal(publish.estimatedCostEur, 0);
  assert.match(publish.message, /Direcktbuchungen\/index/);
});

test('requires a verified business recipient for autonomous direct-booking outreach', () => {
  const engine = new GrowthOrchestrator();
  const idle = engine.plan('zuhause_am_bach', { openNights: 0, nextPartner: { partner: 'Example Partner', recipientVerified: false } });
  assert.equal(idle.some((item) => item.kind === 'sendExternalMessage'), false);
  const active = engine.plan('zuhause_am_bach', { openNights: 0, nextPartner: { partner: 'Example Partner', recipientVerified: true } });
  const outreach = active.find((item) => item.kind === 'sendExternalMessage');
  assert.ok(outreach);
  assert.equal(outreach.approvalRequired, false);
  assert.equal(outreach.autonomous, true);
  assert.equal(outreach.estimatedCostEur, 0);
});

test('keeps Windis outreach approval-gated', () => {
  const engine = new GrowthOrchestrator();
  const active = engine.plan('windis', {
    openPartnerActions: 1,
    priorityAOpen: 1,
    nextPartner: { partner: 'Donau Niederoesterreich Tourismus GmbH / Wachau-Nibelungengau-Kremstal', recipientVerified: true },
  });
  const outreach = active.find((item) => item.kind === 'sendExternalMessage');
  assert.ok(outreach);
  assert.equal(outreach.approvalRequired, true);
  assert.equal(outreach.autonomous, false);
});

import { GrowthOrchestrator } from './orchestrator.js';

const engine = new GrowthOrchestrator();
engine.ingest({ brand: 'zuhause_am_bach', type: 'availability_snapshot', source: 'fixture', value: { openNights: 4 } });
engine.ingest({ brand: 'windis', type: 'partner_pipeline_snapshot', source: 'fixture', value: { partnerContacts: 3 } });

console.log(JSON.stringify({
  zuhause: {
    summary: engine.summarize('zuhause_am_bach'),
    plan: engine.plan('zuhause_am_bach', { openNights: 4, inquiries: 2, confirmedBookings: 0 }),
  },
  windis: {
    summary: engine.summarize('windis'),
    plan: engine.plan('windis', { partnerContacts: 3, partnerReplies: 0 }),
  },
}, null, 2));

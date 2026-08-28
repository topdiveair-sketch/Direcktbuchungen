import { BRANDS, MAX_AUTONOMY } from './config.js';

const now = () => new Date().toISOString();

export class GrowthOrchestrator {
  constructor({ events = [] } = {}) { this.events = [...events]; }

  ingest(event) {
    if (!BRANDS[event.brand]) throw new Error(`Unknown brand: ${event.brand}`);
    const normalized = { id: crypto.randomUUID(), at: now(), ...event };
    this.events.push(normalized);
    return normalized;
  }

  summarize(brand) {
    if (!BRANDS[brand]) throw new Error(`Unknown brand: ${brand}`);
    const events = this.events.filter((event) => event.brand === brand);
    const counts = Object.fromEntries([...new Set(events.map((event) => event.type))].map((type) => [type, events.filter((event) => event.type === type).length]));
    return { brand, objective: BRANDS[brand].objective, eventCount: events.length, counts };
  }

  plan(brand, signals = {}) {
    if (!BRANDS[brand]) throw new Error(`Unknown brand: ${brand}`);
    const actions = [];

    if (brand === 'zuhause_am_bach') {
      const openNights = Number(signals.openNights || 0);
      if (openNights > 0) {
        actions.push({ kind: 'research', task: `Find demand drivers for ${openNights} open night${openNights === 1 ? '' : 's'} in the next 30 days` });
        actions.push({ kind: 'draft', task: 'Create direct-booking content and landing-page variants for current availability' });
        actions.push({ kind: 'publish', task: 'Publish the strongest reviewed direct-booking availability post', channel: 'owned_social', rationale: 'Open inventory needs qualified direct demand' });
      }
      if (signals.inquiries > 0 && signals.confirmedBookings === 0) actions.push({ kind: 'analyze', task: 'Inspect inquiry-to-booking friction' });
    }

    if (brand === 'windis') {
      actions.push({ kind: 'research', task: 'Identify one Wachau family topic and one qualified partner angle' });
      actions.push({ kind: 'draft', task: 'Create a story-led multi-channel content brief' });
      const openPartnerActions = Number(signals.openPartnerActions || 0);
      const priorityAOpen = Number(signals.priorityAOpen || 0);
      if (openPartnerActions > 0 || priorityAOpen > 0) actions.push({ kind: 'sendExternalMessage', task: 'Send one reviewed, personalized partner outreach message to the highest-priority qualified partner', channel: 'partner_outreach', rationale: 'Qualified partner opportunity is open' });
      if (signals.partnerReplies === 0 && signals.partnerContacts > 0) actions.push({ kind: 'analyze', task: 'Improve partner proposition before further outreach' });
    }

    return actions.map((action) => ({ ...action, autonomous: Boolean(MAX_AUTONOMY[action.kind]), approvalRequired: !MAX_AUTONOMY[action.kind] }));
  }

  guard(action) {
    const protectedKinds = new Set(['publish', 'sendExternalMessage', 'spendMoney']);
    if (protectedKinds.has(action.kind)) return { allowed: false, reason: 'human_approval_required' };
    return { allowed: true };
  }
}

import { BRANDS, MAX_AUTONOMY, ZERO_COST_GUARD } from './config.js';

const now = () => new Date().toISOString();
const DIRECT_BOOKING_URL = 'https://topdiveair-sketch.github.io/Direcktbuchungen/index';

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
        actions.push({ kind: 'research', task: `Find demand drivers for ${openNights} open night${openNights === 1 ? '' : 's'} in the next 30 days`, estimatedCostEur: 0 });
        actions.push({ kind: 'draft', task: 'Create direct-booking content and landing-page variants for current availability', estimatedCostEur: 0 });
        actions.push({
          kind: 'publish',
          task: 'Publish a current direct-booking availability update',
          channel: 'owned_web',
          rationale: 'Open inventory needs qualified direct demand',
          estimatedCostEur: 0,
          message: `Aktuell gibt es bei Zuhause am Bach – Wachau freie Termine in den nächsten 30 Tagen. Ruhige Unterkunft in Aggsbach Markt für Donauradweg und Welterbesteig. Direkt und provisionsfrei anfragen: ${DIRECT_BOOKING_URL}`,
        });
      }

      const nextPartner = signals.nextPartner || null;
      if (nextPartner?.partner && nextPartner?.recipientVerified === true) {
        actions.push({
          kind: 'sendExternalMessage',
          task: `Send one personalized zero-cost cooperation request to ${nextPartner.partner}`,
          channel: 'partner_outreach',
          rationale: 'A verified business contact has a relevant, non-paid mutual-referral opportunity',
          recipientRef: nextPartner.partner,
          recipientVerified: true,
          estimatedCostEur: 0,
          subject: `Kostenlose Kooperationsidee: Zuhause am Bach × ${nextPartner.partner}`,
          message: `Guten Tag, wir betreiben Zuhause am Bach – Wachau in Aggsbach Markt und möchten Gästen passende regionale Angebote empfehlen. Wenn es für Sie ebenfalls sinnvoll ist, schlagen wir eine unverbindliche, kostenlose gegenseitige Empfehlung bzw. Verlinkung vor. Es entstehen keine Gebühren, Provisionen oder Verpflichtungen. Unsere Direktinformation: ${DIRECT_BOOKING_URL}`,
        });
      }

      if (signals.inquiries > 0 && signals.confirmedBookings === 0) actions.push({ kind: 'analyze', task: 'Inspect inquiry-to-booking friction', estimatedCostEur: 0 });
    }

    if (brand === 'windis') {
      actions.push({ kind: 'research', task: 'Identify one Wachau family topic and one qualified partner angle' });
      actions.push({ kind: 'draft', task: 'Create a story-led multi-channel content brief' });
      const nextPartner = signals.nextPartner || null;
      if (nextPartner?.partner) actions.push({ kind: 'sendExternalMessage', task: `Send one reviewed, personalized partner outreach message to ${nextPartner.partner}`, channel: 'partner_outreach', rationale: 'Verified qualified partner opportunity is open', recipientRef: nextPartner.partner, subject: `Kooperationsidee Wilde Wachauer Windis × ${nextPartner.partner}` });
      if (signals.partnerReplies === 0 && signals.partnerContacts > 0) actions.push({ kind: 'analyze', task: 'Improve partner proposition before further outreach' });
    }

    return actions.map((action) => {
      const enriched = { brand, ...action };
      const guard = this.guard(enriched);
      const autonomous = Boolean(MAX_AUTONOMY[action.kind]) && guard.allowed;
      return { ...enriched, autonomous, approvalRequired: !autonomous };
    });
  }

  guard(action) {
    if (action.kind === 'spendMoney') return { allowed: false, reason: 'zero_cost_policy' };

    if (action.kind === 'publish') {
      if (action.brand !== 'zuhause_am_bach') return { allowed: false, reason: 'human_approval_required' };
      if (!ZERO_COST_GUARD.allowedPublishChannels.includes(action.channel)) return { allowed: false, reason: 'channel_not_allowed' };
      if (Number(action.estimatedCostEur || 0) > ZERO_COST_GUARD.maxEstimatedCostEur) return { allowed: false, reason: 'zero_cost_policy' };
      if (!String(action.message || '').trim()) return { allowed: false, reason: 'content_required' };
      return { allowed: true };
    }

    if (action.kind === 'sendExternalMessage') {
      if (action.brand !== 'zuhause_am_bach') return { allowed: false, reason: 'human_approval_required' };
      if (!ZERO_COST_GUARD.allowedOutreachChannels.includes(action.channel)) return { allowed: false, reason: 'channel_not_allowed' };
      if (Number(action.estimatedCostEur || 0) > ZERO_COST_GUARD.maxEstimatedCostEur) return { allowed: false, reason: 'zero_cost_policy' };
      if (ZERO_COST_GUARD.requireVerifiedBusinessRecipient && (!action.recipientRef || action.recipientVerified !== true)) return { allowed: false, reason: 'verified_business_recipient_required' };
      if (!String(action.message || '').trim()) return { allowed: false, reason: 'content_required' };
      return { allowed: true };
    }

    return { allowed: true };
  }
}

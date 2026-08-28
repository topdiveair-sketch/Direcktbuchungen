const DAY_MS = 86400000;

const toDay = (value) => new Date(`${value}T00:00:00Z`);
const isoDay = (date) => date.toISOString().slice(0, 10);

export function availabilitySignals(payload, { horizonDays = 30, from = new Date() } = {}) {
  if (!payload || payload.ok !== true || !Array.isArray(payload.events)) {
    throw new Error('Invalid booking availability payload');
  }

  const start = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate()));
  const blocked = new Set();
  for (const event of payload.events) {
    for (let day = toDay(event.start); day < toDay(event.end); day = new Date(day.getTime() + DAY_MS)) {
      blocked.add(isoDay(day));
    }
  }

  let openNights = 0;
  for (let i = 0; i < horizonDays; i += 1) {
    const day = isoDay(new Date(start.getTime() + i * DAY_MS));
    if (!blocked.has(day)) openNights += 1;
  }

  return {
    source: payload.source || 'booking-ical-live',
    horizonDays,
    openNights,
    blockedNights: horizonDays - openNights,
    occupancyRatio: (horizonDays - openNights) / horizonDays,
    updatedAtIso: payload.updatedAtIso || null,
  };
}

export async function fetchBookingSignals(url, options = {}) {
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Availability HTTP ${response.status}`);
  return availabilitySignals(await response.json(), options);
}

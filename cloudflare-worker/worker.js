const ALLOWED_ORIGINS = [
  "https://topdiveair-sketch.github.io",
  "http://localhost",
  "http://127.0.0.1"
];

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allowed = ALLOWED_ORIGINS.some((entry) => origin === entry || origin.startsWith(entry + ":"));
  return {
    "Access-Control-Allow-Origin": allowed ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Cache-Control",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  };
}

function unfoldIcs(text) {
  return text.replace(/\r?\n[ \t]/g, "");
}

function parseIcsDate(value) {
  if (!value) return null;
  const raw = value.trim();
  const match = raw.match(/^(\d{4})(\d{2})(\d{2})/);
  if (!match) return null;
  return `${match[1]}-${match[2]}-${match[3]}`;
}

function parseEvents(icsText) {
  const unfolded = unfoldIcs(icsText);
  const chunks = unfolded.split("BEGIN:VEVENT").slice(1);
  const events = [];

  for (const chunk of chunks) {
    const body = chunk.split("END:VEVENT")[0] || "";
    const startLine = body.match(/(?:^|\n)DTSTART(?:;[^:]*)?:(.+)/);
    const endLine = body.match(/(?:^|\n)DTEND(?:;[^:]*)?:(.+)/);
    const start = parseIcsDate(startLine && startLine[1]);
    const end = parseIcsDate(endLine && endLine[1]);
    if (start && end && end > start) events.push({ start, end });
  }

  events.sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end));
  return events;
}

export default {
  async fetch(request, env) {
    const headers = corsHeaders(request);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers });
    }
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405, headers });
    }
    if (!env.BOOKING_ICAL_URL) {
      return Response.json({ error: "BOOKING_ICAL_URL fehlt" }, { status: 500, headers });
    }

    try {
      const response = await fetch(env.BOOKING_ICAL_URL, {
        headers: {
          "Accept": "text/calendar,text/plain;q=0.9,*/*;q=0.8",
          "User-Agent": "Zuhause-am-Bach-Availability/1.0"
        },
        cf: { cacheTtl: 30, cacheEverything: true }
      });
      if (!response.ok) throw new Error(`Booking iCal HTTP ${response.status}`);

      const ics = await response.text();
      const events = parseEvents(ics);
      const now = new Date();
      const payload = {
        ok: true,
        source: "booking-ical-live",
        updatedAt: now.toLocaleString("de-AT", { timeZone: "Europe/Vienna" }),
        updatedAtIso: now.toISOString(),
        events
      };

      return Response.json(payload, {
        headers: {
          ...headers,
          "Cache-Control": "public, max-age=15, s-maxage=30",
          "Content-Type": "application/json; charset=utf-8"
        }
      });
    } catch (error) {
      return Response.json({
        ok: false,
        error: "Booking-Kalender konnte nicht geladen werden",
        detail: String(error && error.message ? error.message : error)
      }, { status: 502, headers });
    }
  }
};

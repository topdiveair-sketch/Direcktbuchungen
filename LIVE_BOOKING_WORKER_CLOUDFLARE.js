// Legacy standalone Worker example. Prefer cloudflare-worker/worker.js for new deployments.
// Configure BOOKING_ICAL_URL as a Cloudflare Worker secret; never commit the export URL.
const BOOKING_PRICE_URL = "https://www.booking.com/city/at/aggsbach.de.html";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Cache-Control": "no-store"
};

function parseDate(value) {
  if (!value || value.length < 8) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function parseIcal(text) {
  return text.replace(/\r?\n[ \t]/g, "").split("BEGIN:VEVENT").slice(1).map((block) => {
    let start = "";
    let end = "";
    let summary = "Booking/iCal gesperrt";
    for (const rawLine of block.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (line.startsWith("DTSTART")) start = parseDate(line.split(":").pop());
      if (line.startsWith("DTEND")) end = parseDate(line.split(":").pop());
      if (line.startsWith("SUMMARY")) summary = line.split(":").slice(1).join(":") || summary;
    }
    return { start, end, summary };
  }).filter((event) => event.start && event.end && event.end > event.start);
}

function parsePriceValue(value) {
  if (!value) return null;
  let cleaned = String(value).replace(/\u00a0/g, " ").replace(/[^0-9,.-]/g, "");
  if (cleaned.includes(",") && cleaned.includes(".")) cleaned = cleaned.replace(/\./g, "").replace(",", ".");
  else cleaned = cleaned.replace(",", ".");
  const price = Number(cleaned);
  return Number.isFinite(price) ? Math.round(price * 100) / 100 : null;
}

function extractBookingPrice(html) {
  const plain = html.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ");
  const match = plain.match(/Zuhause am Bach.{0,3500}?Preis ab\s*€\s*([0-9][0-9.,]*)/i)
    || plain.match(/Zuhause am Bach.{0,3500}?€\s*([0-9][0-9.,]*)/i);
  return match ? parsePriceValue(match[1]) : null;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

    try {
      const url = new URL(request.url);
      if (url.searchParams.get("type") === "prices" || url.pathname.endsWith("/prices")) {
        const priceResponse = await fetch(BOOKING_PRICE_URL, {
          headers: { "User-Agent": "Zuhause-am-Bach-Price-Sync/1.0" },
          cf: { cacheTtl: 0, cacheEverything: false }
        });
        if (!priceResponse.ok) return Response.json({ error: `Booking price HTTP ${priceResponse.status}`, rooms: {} }, { status: 502, headers: corsHeaders });
        const price = extractBookingPrice(await priceResponse.text());
        if (!price) return Response.json({ error: "Booking-Preis konnte nicht ausgelesen werden.", rooms: {} }, { status: 502, headers: corsHeaders });
        return Response.json({
          updatedAt: new Date().toLocaleString("de-AT", { timeZone: "Europe/Vienna" }),
          rooms: { Bachblick: { price, standard: price, weekend: price, high: price } }
        }, { headers: corsHeaders });
      }

      if (!env.BOOKING_ICAL_URL) return Response.json({ error: "BOOKING_ICAL_URL fehlt", events: [] }, { status: 500, headers: corsHeaders });
      const response = await fetch(env.BOOKING_ICAL_URL, {
        headers: { "User-Agent": "Zuhause-am-Bach-Live-Calendar/2.0" },
        cf: { cacheTtl: 0, cacheEverything: false }
      });
      if (!response.ok) return Response.json({ error: `Booking iCal HTTP ${response.status}`, events: [] }, { status: 502, headers: corsHeaders });
      return Response.json({
        room: "Bachblick",
        updatedAt: new Date().toLocaleString("de-AT", { timeZone: "Europe/Vienna" }),
        events: parseIcal(await response.text())
      }, { headers: corsHeaders });
    } catch (error) {
      return Response.json({ error: String(error && error.message ? error.message : error), events: [] }, { status: 500, headers: corsHeaders });
    }
  }
};

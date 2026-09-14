const fs = require("fs");
const path = require("path");

const DEFAULT_ZAB_MASTER_ICAL_URL = "https://web-production-907d68.up.railway.app/calendar/public/Bachblick.ics";
const ZAB_MASTER_ICAL_URL = String(process.env.ZAB_MASTER_ICAL_URL || DEFAULT_ZAB_MASTER_ICAL_URL).trim();
const BOOKING_ICAL_URL = String(process.env.BOOKING_ICAL_URL || "").trim();
const ALLOW_BOOKING_FALLBACK = /^(1|true|yes|on)$/i.test(String(process.env.ZAB_MASTER_ALLOW_BOOKING_FALLBACK || "0"));
const INCLUDE_LEGACY_BLOCKS = /^(1|true|yes|on)$/i.test(String(process.env.ZAB_MASTER_INCLUDE_LEGACY_BLOCKS || "0"));
const GOOGLE_ICAL_URLS = (process.env.GOOGLE_ICAL_URLS || process.env.GOOGLE_ICAL_URL || "")
  .split(";")
  .map((url) => url.trim())
  .filter(Boolean);

function loadManualBlocks() {
  const raw = String(process.env.MANUAL_BOOKING_BLOCKS_JSON || "").trim();
  if (!raw) return [];

  let blocks;
  try {
    blocks = JSON.parse(raw);
  } catch (error) {
    throw new Error(`MANUAL_BOOKING_BLOCKS_JSON ist kein gültiges JSON: ${error.message}`);
  }
  if (!Array.isArray(blocks)) throw new Error("MANUAL_BOOKING_BLOCKS_JSON muss ein JSON-Array sein");

  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Vienna",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(new Date());

  return blocks.map((block, index) => {
    const start = String(block && block.start || "");
    const end = String(block && block.end || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || end <= start) {
      throw new Error(`Manuelle Sperre ${index + 1} hat ungültige start/end-Werte`);
    }
    if (end <= today) {
      throw new Error(`Manuelle Sperre ${index + 1} ist abgelaufen (${start} bis ${end}); bitte aus MANUAL_BOOKING_BLOCKS_JSON entfernen`);
    }
    return {
      start,
      end,
      summary: String(block.summary || "MANUELL GESCHLOSSEN - Not available"),
      source: "Legacy manuell"
    };
  });
}

function parseDate(value) {
  if (!value || value.length < 8) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function parseIcal(text, source) {
  return text
    .replace(/\r?\n[ \t]/g, "")
    .split("BEGIN:VEVENT")
    .slice(1)
    .map((block) => {
      let start = "";
      let end = "";
      let summary = "ZAB OS belegt oder geschlossen";
      for (const rawLine of block.split(/\r?\n/)) {
        const line = rawLine.trim();
        if (line.startsWith("DTSTART")) start = parseDate(line.split(":").pop());
        if (line.startsWith("DTEND")) end = parseDate(line.split(":").pop());
        if (line.startsWith("SUMMARY")) summary = line.split(":").slice(1).join(":") || summary;
      }
      return { start, end, summary, source };
    })
    .filter((event) => event.start && event.end && event.end > event.start);
}

async function fetchIcal(url, source) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const separator = url.includes("?") ? "&" : "?";
      const response = await fetch(`${url}${separator}_zab=${Date.now()}`, {
        headers: {
          "User-Agent": "Zuhause-am-Bach-Calendar-Sync/4.1",
          "Accept": "text/calendar,text/plain,*/*",
          "Cache-Control": "no-cache"
        }
      });
      if (!response.ok) throw new Error(`${source} iCal HTTP ${response.status}`);
      const text = await response.text();
      if (!text.includes("BEGIN:VCALENDAR")) throw new Error(`${source} lieferte keinen gültigen iCal-Kalender`);
      return parseIcal(text, source);
    } catch (error) {
      lastError = error;
      console.warn(`${source}: Versuch ${attempt} von 3 fehlgeschlagen: ${error.message}`);
      if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, attempt * 3000));
    }
  }
  throw lastError;
}

function dedupeEvents(events) {
  const unique = new Map();
  for (const event of events) {
    if (!event || !event.start || !event.end || event.end <= event.start) continue;
    const key = `${event.start}|${event.end}`;
    const existing = unique.get(key);
    if (!existing) {
      unique.set(key, { ...event });
      continue;
    }
    if (!String(existing.source || "").includes(String(event.source || ""))) {
      existing.source = [existing.source, event.source].filter(Boolean).join(" + ");
    }
  }
  return Array.from(unique.values())
    .sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || String(a.source).localeCompare(String(b.source)));
}

function renderFallbackBlocks(events) {
  return events
    .map((event) => `      { start: "${event.start}", end: "${event.end}" }`)
    .join(",\n");
}

function updateHtmlFallback(events, updatedAt, updatedAtIso) {
  const indexPath = path.join(process.cwd(), "index.html");
  if (!fs.existsSync(indexPath)) return false;

  const original = fs.readFileSync(indexPath, "utf8");
  let html = original;
  html = html.replace(
    /let bookingCalendarUpdated = ".*?";/,
    `let bookingCalendarUpdated = "${updatedAt}";`
  );
  html = html.replace(
    /let bookingCalendarUpdatedIso = ".*?";/,
    `let bookingCalendarUpdatedIso = "${updatedAtIso}";`
  );
  html = html.replace(
    /const BACHBLICK_BOOKING_BLOCKS = \[[\s\S]*?\n\s*\];/,
    `const BACHBLICK_BOOKING_BLOCKS = [\n${renderFallbackBlocks(events)}\n    ];`
  );

  // Fail closed while a live refresh is still pending. A generated fallback
  // snapshot is considered loaded only when it actually contains intervals.
  html = html.replace(
    /let liveBookingCalendarLoaded = (?:true|false);/,
    "let liveBookingCalendarLoaded = false;"
  );
  html = html.replace(
    /let bachblickBookingBlocks = BACHBLICK_BOOKING_BLOCKS\.slice\(\);(?:\s*liveBookingCalendarLoaded = bachblickBookingBlocks\.length > 0;)?/,
    "let bachblickBookingBlocks = BACHBLICK_BOOKING_BLOCKS.slice();\n    liveBookingCalendarLoaded = bachblickBookingBlocks.length > 0;"
  );

  // A known OS/master/Booking conflict must remain blocked even if the
  // freshness timestamp later expires. Freshness is only required to
  // positively confirm availability, never to discard a known block.
  html = html.replace(/if \(conflict && calendarIsFresh\(\)\)/g, "if (conflict)");

  if (events.length > 0 && !html.includes(`start: "${events[0].start}", end: "${events[0].end}"`)) {
    throw new Error("Kalender-Sicherheitsblöcke konnten nicht in index.html eingebettet werden");
  }

  if (html === original) return false;
  fs.writeFileSync(indexPath, html, "utf8");
  return true;
}

async function main() {
  if (!ZAB_MASTER_ICAL_URL) throw new Error("ZAB_MASTER_ICAL_URL fehlt");

  let masterEvents = [];
  let source = "ZAB OS Master-Kalender";
  try {
    masterEvents = await fetchIcal(ZAB_MASTER_ICAL_URL, "ZAB OS Master");
  } catch (error) {
    if (!ALLOW_BOOKING_FALLBACK || !BOOKING_ICAL_URL) throw error;
    console.warn(`ZAB OS Master nicht erreichbar; explizit erlaubter Booking-Fallback wird verwendet: ${error.message}`);
    masterEvents = [];
    source = "Booking iCal Fallback";
  }

  let bookingSafetyEvents = [];
  if (BOOKING_ICAL_URL) {
    // Hybrid safety net: Booking remains independently authoritative for its
    // own reservations. This prevents a fresh Railway deploy or empty master
    // DB from ever turning an existing Booking reservation into "frei".
    bookingSafetyEvents = await fetchIcal(BOOKING_ICAL_URL, "Booking iCal Sicherheitsabgleich");
    if (source === "Booking iCal Fallback") {
      source = "Booking iCal Sicherheitsabgleich";
    } else {
      source += " + Booking iCal Sicherheitsabgleich";
    }
  } else if (masterEvents.length === 0) {
    throw new Error("Master-Kalender ist leer und BOOKING_ICAL_URL fehlt; aus Sicherheitsgründen wird kein Frei-Stand veröffentlicht");
  }

  let events = dedupeEvents([...masterEvents, ...bookingSafetyEvents]);

  // Legacy feeds are off by default. External blocks belong in the OS master
  // calendar so website, checkout and channel feeds use one source of truth.
  if (INCLUDE_LEGACY_BLOCKS) {
    for (const [index, googleUrl] of GOOGLE_ICAL_URLS.entries()) {
      events.push(...await fetchIcal(googleUrl, `Google Kalender ${index + 1}`));
    }
    events.push(...loadManualBlocks());
    events = dedupeEvents(events);
    source += " + Legacy-Blöcke";
  }

  const calendarPath = path.join(process.cwd(), "booking-calendar.json");
  const now = new Date();
  const payload = {
    room: "Bachblick",
    roomDisplayName: "Gartenblick Zimmer",
    source,
    masterUrl: ZAB_MASTER_ICAL_URL,
    events,
    updatedAt: now.toLocaleString("de-AT", { timeZone: "Europe/Vienna" }),
    updatedAtIso: now.toISOString()
  };

  fs.writeFileSync(calendarPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  updateHtmlFallback(events, payload.updatedAt, payload.updatedAtIso);
  console.log(`ZAB-OS-Sicherheitskalender geprüft: ${events.length} belegt/geschlossen, davon ${masterEvents.length} Master und ${bookingSafetyEvents.length} Booking, ${payload.updatedAt}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
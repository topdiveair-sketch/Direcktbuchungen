const fs = require("fs");
const path = require("path");

const BOOKING_ICAL_URL = String(process.env.BOOKING_ICAL_URL || "").trim();
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
      source: "Manuell"
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
      let summary = "Booking/iCal belegt oder geschlossen";
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
          "User-Agent": "Zuhause-am-Bach-Calendar-Sync/3.0",
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

function stableCalendar(payload) {
  return {
    room: payload.room,
    source: payload.source,
    events: payload.events
  };
}

async function main() {
  if (!BOOKING_ICAL_URL) throw new Error("BOOKING_ICAL_URL fehlt; als GitHub Actions Secret konfigurieren");

  const events = await fetchIcal(BOOKING_ICAL_URL, "Booking");
  for (const [index, googleUrl] of GOOGLE_ICAL_URLS.entries()) {
    events.push(...await fetchIcal(googleUrl, `Google Kalender ${index + 1}`));
  }
  events.push(...loadManualBlocks());
  events.sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || a.source.localeCompare(b.source));

  const calendarPath = path.join(process.cwd(), "booking-calendar.json");
  let previous = null;
  if (fs.existsSync(calendarPath)) {
    try {
      previous = JSON.parse(fs.readFileSync(calendarPath, "utf8"));
    } catch (error) {
      console.warn(`Bestehender Kalender konnte nicht gelesen werden: ${error.message}`);
    }
  }

  const payload = {
    room: "Bachblick",
    source: GOOGLE_ICAL_URLS.length ? "Booking iCal + Google Calendar iCal" : "Booking iCal",
    events
  };

  if (previous && JSON.stringify(stableCalendar(previous)) === JSON.stringify(stableCalendar(payload))) {
    console.log(`Kalender unverändert: ${events.length} belegt/geschlossen; keine Dateiänderung.`);
    return;
  }

  const now = new Date();
  payload.updatedAt = now.toLocaleString("de-AT", { timeZone: "Europe/Vienna" });
  payload.updatedAtIso = now.toISOString();
  fs.writeFileSync(calendarPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.log(`booking-calendar.json aktualisiert: ${events.length} belegt/geschlossen, ${payload.updatedAt}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});

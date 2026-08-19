const fs = require("fs");
const path = require("path");

const BOOKING_ICAL_URL = "https://ical.booking.com/v1/export?t=e1973013-8c21-453b-b69d-13805e4630f8";
const GOOGLE_ICAL_URLS = (process.env.GOOGLE_ICAL_URLS || process.env.GOOGLE_ICAL_URL || "")
  .split(";")
  .map((url) => url.trim())
  .filter(Boolean);
const MANUAL_BLOCKS = [
  { start: "2026-08-02", end: "2026-08-03", summary: "MANUELL GESCHLOSSEN - Not available", source: "Manuell" },
  { start: "2026-08-15", end: "2026-08-21", summary: "MANUELL GESCHLOSSEN - Not available", source: "Manuell" }
];

function parseDate(value) {
  if (!value || value.length < 8) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function parseIcal(text, source) {
  return text.split("BEGIN:VEVENT").slice(1).map((block) => {
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
  }).filter((event) => event.start && event.end);
}

async function fetchIcal(url, source) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const separator = url.includes("?") ? "&" : "?";
      const response = await fetch(`${url}${separator}_zab=${Date.now()}`, {
        headers: {
          "User-Agent": "Zuhause-am-Bach-Calendar-Sync/2.0",
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

function eventData(payload) {
  return {
    room: payload.room,
    source: payload.source,
    events: payload.events
  };
}

function sameCalendarData(previous, next) {
  if (!previous) return false;
  return JSON.stringify(eventData(previous)) === JSON.stringify(eventData(next));
}

async function main() {
  const events = await fetchIcal(BOOKING_ICAL_URL, "Booking");
  for (const [index, googleUrl] of GOOGLE_ICAL_URLS.entries()) {
    events.push(...await fetchIcal(googleUrl, `Google Kalender ${index + 1}`));
  }
  events.push(...MANUAL_BLOCKS);
  events.sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end));

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

  if (sameCalendarData(previous, payload)) {
    console.log(`Kalender unverändert: ${events.length} belegt/geschlossen; kein Commit erforderlich.`);
    return;
  }

  const updatedAt = new Date().toLocaleString("de-AT", { timeZone: "Europe/Vienna" });
  const updatedAtIso = new Date().toISOString();
  payload.updatedAt = updatedAt;
  payload.updatedAtIso = updatedAtIso;

  fs.writeFileSync(calendarPath, JSON.stringify(payload, null, 2) + "\n", "utf8");

  const indexPath = path.join(process.cwd(), "index.html");
  if (fs.existsSync(indexPath)) {
    const fallbackBlocks = events.map((event) => `      { start: "${event.start}", end: "${event.end}" }`).join(",\n");
    let html = fs.readFileSync(indexPath, "utf8");
    html = html.replace(/let bookingCalendarUpdated = ".*?";/, `let bookingCalendarUpdated = "${updatedAt}";`);
    html = html.replace(/let bookingCalendarUpdatedIso = ".*?";/, `let bookingCalendarUpdatedIso = "${updatedAtIso}";`);
    html = html.replace(
      /const BACHBLICK_BOOKING_BLOCKS = \[\r?\n[\s\S]*?\r?\n\s*\];/,
      `const BACHBLICK_BOOKING_BLOCKS = [\n${fallbackBlocks}\n    ];`
    );
    fs.writeFileSync(indexPath, html, "utf8");
  }

  console.log(`booking-calendar.json und HTML-Fallback aktualisiert: ${payload.events.length} belegt/geschlossen, ${updatedAt}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

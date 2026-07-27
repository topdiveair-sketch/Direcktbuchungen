const fs = require("fs");
const path = require("path");

const BOOKING_ICAL_URL = "https://ical.booking.com/v1/export?t=e1973013-8c21-453b-b69d-13805e4630f8";
const GOOGLE_ICAL_URLS = (process.env.GOOGLE_ICAL_URLS || process.env.GOOGLE_ICAL_URL || "")
  .split(";")
  .map((url) => url.trim())
  .filter(Boolean);

function parseDate(value) {
  if (!value || value.length < 8) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function parseIcal(text, source) {
  return text
    .split("BEGIN:VEVENT")
    .slice(1)
    .map((block) => {
      let start = "";
      let end = "";
      let summary = "Booking/iCal gesperrt";
      for (const rawLine of block.split(/\r?\n/)) {
        const line = rawLine.trim();
        if (line.startsWith("DTSTART")) start = parseDate(line.split(":").pop());
        if (line.startsWith("DTEND")) end = parseDate(line.split(":").pop());
        if (line.startsWith("SUMMARY")) summary = line.split(":").slice(1).join(":") || summary;
      }
      return { start, end, summary, source };
    })
    .filter((event) => event.start && event.end);
}

async function fetchIcal(url, source) {
  const response = await fetch(url, {
    headers: { "User-Agent": "Zuhause-am-Bach-Calendar-Sync/1.0" }
  });
  if (!response.ok) {
    throw new Error(`${source} iCal HTTP ${response.status}`);
  }
  return parseIcal(await response.text(), source);
}

async function main() {
  const events = await fetchIcal(BOOKING_ICAL_URL, "Booking");
  for (const [index, googleUrl] of GOOGLE_ICAL_URLS.entries()) {
    events.push(...await fetchIcal(googleUrl, `Google Kalender ${index + 1}`));
  }
  events.sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end));
  const updatedAt = new Date().toLocaleString("de-AT", { timeZone: "Europe/Vienna" });
  const updatedAtIso = new Date().toISOString();
  const payload = {
    room: "Bachblick",
    source: GOOGLE_ICAL_URLS.length ? "Booking iCal + Google Calendar iCal" : "Booking iCal",
    updatedAt,
    updatedAtIso,
    events
  };
  fs.writeFileSync(
    path.join(process.cwd(), "booking-calendar.json"),
    JSON.stringify(payload, null, 2) + "\n",
    "utf8"
  );
  console.log(`booking-calendar.json aktualisiert: ${payload.events.length} Sperrzeiten, ${updatedAt}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

const fs = require("fs");
const path = require("path");

const BOOKING_ICAL_URL = "https://ical.booking.com/v1/export?t=e1973013-8c21-453b-b69d-13805e4630f8";

function parseDate(value) {
  if (!value || value.length < 8) return "";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function parseIcal(text) {
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
      return { start, end, summary };
    })
    .filter((event) => event.start && event.end);
}

async function main() {
  const response = await fetch(BOOKING_ICAL_URL, {
    headers: { "User-Agent": "Zuhause-am-Bach-GitHub-Pages-Calendar/1.0" }
  });
  if (!response.ok) {
    throw new Error(`Booking iCal HTTP ${response.status}`);
  }
  const text = await response.text();
  const updatedAt = new Date().toLocaleString("de-AT", { timeZone: "Europe/Vienna" });
  const payload = {
    room: "Bachblick",
    source: "Booking iCal",
    updatedAt,
    events: parseIcal(text)
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

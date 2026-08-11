const assert = require("assert");
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.resolve(__dirname, "..", "index.html"), "utf8");

for (const room of ["bachblick", "marillenzimmer", "weinbergzimmer", "donauzimmer"]) {
  assert(html.includes(`images/rooms/${room}.jpg`), `${room}.jpg fehlt`);
  assert(!html.includes(`images/rooms/${room}.webp`), `${room}.webp ist noch referenziert`);
}
for (const event of [
  "landing_view", "availability_started", "room_selected", "extras_selected",
  "request_started", "request_prepared", "request_email_clicked",
  "request_whatsapp_clicked", "request_copied", "payment_started", "booking_abandoned",
]) assert(html.includes(event), `${event} fehlt`);

assert(!html.includes("checkout_started"), "Anfrage darf checkout_started nicht auslösen");
assert(!html.includes("payment_success"), "payment_success darf nicht simuliert werden");
assert(!html.includes("booking_completed"), "booking_completed darf nicht simuliert werden");
assert(html.includes('"availability_result_" + eventState'), "Verfügbarkeitsstatus-Tracking fehlt");
assert(html.includes("google_business"), "Google-Business-Attribution fehlt");
assert(html.includes("zab_attribution"), "Session-Attribution fehlt");
assert.strictEqual((html.match(/class="mobile-booking-cta"/g) || []).length, 1);
assert.strictEqual((html.match(/class="mobile-booking-bar"/g) || []).length, 0);
console.log("Conversion-Vertrag bestanden.");

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.resolve(__dirname, "..", "index.html"), "utf8");

for (const room of ["bachblick", "marillenzimmer", "weinbergzimmer", "donauzimmer"]) {
  assert(html.includes(`images/rooms/${room}.webp`), `${room}.webp fehlt`);
}

for (const event of [
  "website_view", "booking_page_view", "availability_check", "room_selected",
  "checkout_started", "payment_started", "phone_click", "email_click", "guest_app_click",
]) {
  assert(html.includes(event), `${event} fehlt`);
}

assert(!html.includes("payment_success"), "payment_success darf nicht simuliert werden");
assert(!html.includes("booking_completed"), "booking_completed darf nicht simuliert werden");
assert.strictEqual((html.match(/class="mobile-booking-cta"/g) || []).length, 0);
assert.strictEqual((html.match(/class="mobile-booking-bar"/g) || []).length, 1);
assert(html.includes("progress >= 0.2"), "mobile Buchungsleiste muss erst nach Scrollfortschritt erscheinen");
assert(!html.includes('if (availability.state !== "ok")'), "veralteter Kalender darf die unverbindliche Anfrage nicht blockieren");
assert(html.includes('if (availability.state === "blocked")'), "nur bestätigte Kalenderkonflikte dürfen blockieren");
console.log("Conversion-Vertrag bestanden.");

const assert = require("assert");

function bookingTotalCents(roomCents, extras) {
  return extras.reduce((total, cents) => total + cents, roomCents);
}

assert.strictEqual(bookingTotalCents(10100, [2990]), 13090);
assert.strictEqual(bookingTotalCents(10100, [1200 * 2 * 1]), 12500);
assert.strictEqual(bookingTotalCents(10100, [2400, 2990]), 15490);
console.log("Centgenaue Preistests bestanden.");

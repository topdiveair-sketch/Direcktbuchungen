import fs from 'node:fs/promises';
import { DailyPlanner } from './daily-planner.js';
import { availabilitySignals } from './adapters/booking.js';
import { partnerSignals } from './adapters/windis.js';

async function readJson(path) {
  return JSON.parse(await fs.readFile(path, 'utf8'));
}

const [bookingPath, windisPath] = process.argv.slice(2);
if (!bookingPath || !windisPath) {
  console.error('Usage: node src/run-daily.js <booking.json> <windis.json>');
  process.exit(1);
}

const bookingPayload = await readJson(bookingPath);
const windisRows = await readJson(windisPath);

const planner = new DailyPlanner();
const result = planner.buildDay({
  zuhauseSignals: availabilitySignals(bookingPayload),
  windisSignals: partnerSignals(windisRows),
});

console.log(JSON.stringify(result, null, 2));

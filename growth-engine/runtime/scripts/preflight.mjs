const required = ['BOOKING_WORKER_URL','ADMIN_TOKEN'];
const missing = required.filter((key) => !process.env[key]);
if (missing.length) {
  console.error(JSON.stringify({ ok:false, missing }, null, 2));
  process.exit(1);
}
try { new URL(process.env.BOOKING_WORKER_URL); }
catch { console.error(JSON.stringify({ ok:false, invalid:['BOOKING_WORKER_URL'] }, null, 2)); process.exit(1); }
if (process.env.ADMIN_TOKEN.length < 24) {
  console.error(JSON.stringify({ ok:false, invalid:['ADMIN_TOKEN_TOO_SHORT'] }, null, 2)); process.exit(1);
}
console.log(JSON.stringify({ ok:true, configured:['BOOKING_WORKER_URL','ADMIN_TOKEN'], optional:{ WINDIS_DATA_URL:Boolean(process.env.WINDIS_DATA_URL) } }, null, 2));

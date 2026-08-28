const base = process.argv[2];
if (!base) { console.error('Usage: node scripts/postdeploy-check.mjs <base-url>'); process.exit(1); }
const health = await fetch(base.replace(/\/$/,'') + '/health');
if (!health.ok) { console.error(`Health HTTP ${health.status}`); process.exit(1); }
const body = await health.json();
if (!body.ok || body.service !== 'zab-windis-growth-runtime') { console.error('Unexpected health payload'); process.exit(1); }
console.log(JSON.stringify({ ok:true, health:body }, null, 2));

const fs = require("fs");
const path = require("path");

const htmlPath = path.resolve(__dirname, "..", "index.html");
const html = fs.readFileSync(htmlPath, "utf8");
const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter((match) => !/type=["']application\/ld\+json["']/i.test(match[1]))
  .map((match) => match[2])
  .filter((source) => source.trim());

for (const [index, source] of scripts.entries()) {
  try {
    new Function(source);
  } catch (error) {
    console.error(`Inline-Script ${index}: ${error.message}`);
    process.exit(1);
  }
}
console.log(`Inline-JavaScript Syntax bestanden (${scripts.length} Blöcke).`);

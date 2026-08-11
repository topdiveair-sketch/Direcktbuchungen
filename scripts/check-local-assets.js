const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const sourceExtensions = new Set([".html", ".css", ".js"]);
const imageExtensions = new Set([".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg", ".ico", ".gif"]);
const ignoredDirectories = new Set([".git", "node_modules", "data", "__pycache__"]);
const missing = [];

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (ignoredDirectories.has(entry.name)) return [];
    const full = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

for (const source of walk(root).filter((file) => sourceExtensions.has(path.extname(file).toLowerCase()))) {
  const text = fs.readFileSync(source, "utf8");
  const references = [
    ...text.matchAll(/(?:src|href|content)=["']([^"']+)["']/gi),
    ...text.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi),
  ].map((match) => match[1].split(/[?#]/)[0]);
  for (const reference of references) {
    if (!imageExtensions.has(path.extname(reference).toLowerCase())) continue;
    if (/^(?:https?:|data:|\/\/)/i.test(reference) || reference.includes("{{")) continue;
    let decoded = reference;
    try { decoded = decodeURIComponent(reference); } catch (_) {}
    const target = decoded.startsWith("/")
      ? path.resolve(root, decoded.replace(/^\/+/, ""))
      : path.resolve(path.dirname(source), decoded);
    if (!fs.existsSync(target)) missing.push(`${path.relative(root, source)} -> ${reference}`);
  }
}

if (missing.length) {
  console.error("Fehlende lokale Bilddateien:\n" + missing.join("\n"));
  process.exit(1);
}
console.log("Lokale Bildprüfung bestanden.");

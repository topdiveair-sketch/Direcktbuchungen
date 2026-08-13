import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve(new URL('..',import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
const publicDirs=['donauradweg-unterkunft-wachau','welterbesteig-unterkunft-wachau','ruhige-unterkunft-wachau','aggsbach-markt-wachau','wachau-tipps','wilde-wachauer-windis','ebike-unterkunft-wachau','radfahrer-unterkunft-wachau','wanderer-unterkunft-wachau','unterkunft-aggsbach-markt','unterkunft-maria-laach-welterbesteig'];
const htmlFiles=[path.join(root,'index.html'),...publicDirs.map(dir=>path.join(root,dir,'index.html'))];
assert.equal(htmlFiles.length,12,'Startseite plus elf Themenseiten erwartet');
for(const file of htmlFiles){
  const html=fs.readFileSync(file,'utf8');
  assert.equal((html.match(/<title>/g)||[]).length,1,`${file}: genau ein title erwartet`);
  assert.match(html,/<title>[^<]+<\/title>/,`${file}: title fehlt`);
  assert.equal((html.match(/<meta name="description"/g)||[]).length,1,`${file}: genau eine description erwartet`);
  assert.match(html,/<meta name="description" content="[^"]+">/,`${file}: description fehlt`);
  assert.equal((html.match(/<link rel="canonical"/g)||[]).length,1,`${file}: genau ein canonical erwartet`);
  assert.match(html,/<link rel="canonical" href="https:\/\//,`${file}: canonical fehlt`);
  assert.equal((html.match(/<h1\b/g)||[]).length,1,`${file}: genau eine H1 erwartet`);
  const ids=[...html.matchAll(/\sid="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,`${file}: doppelte IDs gefunden`);
  for(const img of html.matchAll(/<img\b[^>]*>/g))assert.match(img[0],/\balt="[^"]+"/,`${file}: Bild ohne beschreibenden Alt-Text`);
  for(const match of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g))JSON.parse(match[1]);
  for(const match of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)){
    if(/application\/ld\+json/.test(match[1]))continue;
    if(match[2].trim())new Function(match[2]);
  }
  for(const match of html.matchAll(/(?:href|src)="([^"#][^"]*)"/g)){
    const ref=match[1];
    if(/^(?:https?:|mailto:|tel:)/.test(ref))continue;
    const target=path.resolve(path.dirname(file),ref.split('#')[0].split('?')[0]);
    const resolved=ref.endsWith('/')?path.join(target,'index.html'):target;
    assert.ok(fs.existsSync(resolved),`${file}: lokales Ziel fehlt: ${ref}`);
  }
}
const home=fs.readFileSync(path.join(root,'index.html'),'utf8');
assert.doesNotMatch(home,/5\s*%|5 Prozent|Bestpreis|Sofortzahlung/i,'Startseite: alte Preisvergleichs- oder Sofortzahlungsaussage gefunden');
assert.match(home,/Zuhause am Bach \| Unterkunft Donauradweg & Welterbesteig Wachau/,'Startseite: Ziel-Title fehlt');
assert.match(home,/Zuhause am Bach – Unterkunft am Donauradweg & Welterbesteig Wachau/,'Startseite: Ziel-H1 fehlt');
assert.match(home,/images\/aggsbach-markt-luftbild\.webp/,'Startseite: optimiertes Hero-Bild fehlt');
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
for(const file of htmlFiles){
  const rel=path.relative(root,file).replaceAll('\\','/');
  const url=rel==='index.html'?'https://topdiveair-sketch.github.io/Direcktbuchungen/':`https://topdiveair-sketch.github.io/Direcktbuchungen/${path.dirname(rel)}/`;
  assert.ok(sitemap.includes(`<loc>${url}</loc>`),`Sitemap-Eintrag fehlt: ${url}`);
}
console.log(`OK: ${htmlFiles.length} HTML-Seiten, Metadaten, JSON-LD, lokale Links und Sitemap geprüft.`);

import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve(new URL('..',import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
const htmlFiles=[];
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory()&&!['.git','.github'].includes(e.name))walk(p);else if(e.isFile()&&e.name.endsWith('.html'))htmlFiles.push(p)}}
walk(root);
assert.equal(htmlFiles.length,7,'Startseite plus sechs Themenseiten erwartet');
for(const file of htmlFiles){
  const html=fs.readFileSync(file,'utf8');
  assert.match(html,/<title>[^<]+<\/title>/,`${file}: title fehlt`);
  assert.match(html,/<meta name="description" content="[^"]+">/,`${file}: description fehlt`);
  assert.match(html,/<link rel="canonical" href="https:\/\//,`${file}: canonical fehlt`);
  assert.equal((html.match(/<h1\b/g)||[]).length,1,`${file}: genau eine H1 erwartet`);
  for(const match of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g))JSON.parse(match[1]);
  for(const match of html.matchAll(/(?:href|src)="([^"#][^"]*)"/g)){
    const ref=match[1];
    if(/^(?:https?:|mailto:|tel:)/.test(ref))continue;
    const target=path.resolve(path.dirname(file),ref.split('#')[0].split('?')[0]);
    const resolved=ref.endsWith('/')?path.join(target,'index.html'):target;
    assert.ok(fs.existsSync(resolved),`${file}: lokales Ziel fehlt: ${ref}`);
  }
}
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
for(const file of htmlFiles){
  const rel=path.relative(root,file).replaceAll('\\','/');
  const url=rel==='index.html'?'https://topdiveair-sketch.github.io/Direcktbuchungen/':`https://topdiveair-sketch.github.io/Direcktbuchungen/${path.dirname(rel)}/`;
  assert.ok(sitemap.includes(`<loc>${url}</loc>`),`Sitemap-Eintrag fehlt: ${url}`);
}
console.log(`OK: ${htmlFiles.length} HTML-Seiten, Metadaten, JSON-LD, lokale Links und Sitemap geprüft.`);

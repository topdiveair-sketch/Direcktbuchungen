#!/usr/bin/env python3
from pathlib import Path
import shutil

repo=Path.cwd()
index=repo/"index.html"
if not index.exists():
    raise SystemExit("Bitte im Stammordner von Direcktbuchungen ausführen.")

src=Path(__file__).resolve().parent
html=index.read_text(encoding="utf-8")

shutil.copy2(src/"zab-guest-price.js",repo/"zab-guest-price.js")
shutil.copy2(src/"zab-live-calculator-config.json",repo/"zab-live-calculator-config.json")

section='\n<section id="gepaeckpreis" aria-labelledby="gepaeckpreis-title">\n  <div class="section-head">\n    <span class="eyebrow">ZAB GepäckFrei · Sofortpreis</span>\n    <h2 id="gepaeckpreis-title">Was kostet Ihr Gepäcktransport?</h2>\n    <p>Unterkunft, Ort oder Adresse eingeben. Wir berechnen Ihren Gepäckpreis aus der tatsächlichen Fahrstrecke und aktuellen Betriebskosten.</p>\n  </div>\n\n  <div class="panel zab-guest-price-box">\n    <div class="form-grid">\n      <label>Richtung\n        <select id="zabGuestMode">\n          <option value="to">Von Zuhause am Bach zur nächsten Unterkunft</option>\n          <option value="from">Von der vorherigen Unterkunft zu Zuhause am Bach</option>\n        </select>\n      </label>\n      <label>Unterkunft, Ort oder Adresse\n        <input id="zabGuestDestination" autocomplete="off" placeholder="z. B. Hotel in Spitz oder genaue Adresse">\n        <div id="zabGuestSuggestions" class="zab-suggestions" hidden></div>\n      </label>\n    </div>\n\n    <button id="zabGuestCalc" type="button" class="btn">Gepäckpreis berechnen</button>\n    <div id="zabGuestStatus" class="hint">Noch keine Berechnung.</div>\n\n    <div id="zabGuestResult" class="zab-guest-result" hidden>\n      <span>Ihr berechneter Gepäckpreis</span>\n      <strong id="zabGuestPrice">–</strong>\n      <p id="zabGuestRoute"></p>\n      <small id="zabGuestMeta"></small>\n      <button id="zabGuestUsePrice" type="button" class="btn">Diesen Gepäcktransport anfragen</button>\n      <small class="zab-price-note">Preis auf Basis der aktuellen Routen- und Betriebskalkulation. Die Leistung wird mit unserer persönlichen Bestätigung verbindlich.</small>\n    </div>\n  </div>\n</section>\n'
css='\n<style>\n.zab-guest-price-box{max-width:860px;position:relative}\n.zab-suggestions{position:absolute;z-index:50;left:0;right:0;margin-top:2px;border:1px solid #cfded7;border-radius:10px;background:#fff;box-shadow:0 12px 30px rgba(0,0,0,.15);overflow:hidden}\n.zab-suggestion{display:block;width:100%;border:0;border-bottom:1px solid #eef2ef;background:#fff;padding:11px 12px;text-align:left;font:inherit;cursor:pointer}\n.zab-suggestion:hover,.zab-suggestion:focus{background:#eef7f2}\n.zab-guest-result{display:grid;gap:7px;margin-top:16px;padding:20px;border:2px solid #176b5a;border-radius:14px;background:#eef8f3;text-align:center}\n.zab-guest-result>strong{font-size:clamp(34px,7vw,58px);line-height:1;color:#176b5a}\n.zab-guest-result p{margin:0;font-weight:850}\n.zab-guest-result small{color:#5f6f69}\n.zab-guest-result .btn{justify-self:center;margin-top:8px}\n.zab-price-note{max-width:620px;justify-self:center}\n#zabGuestDestination{position:relative}\n@media(max-width:640px){.zab-guest-price-box{padding:15px}.zab-guest-result>strong{font-size:42px}}\n</style>\n'

if 'id="gepaeckpreis"' not in html:
    marker='    <section id="zimmer">'
    if marker not in html:
        marker='</main>'
    html=html.replace(marker,section+"\n"+marker,1)

if 'class="zab-guest-price-box"' in html and '.zab-guest-price-box' not in html:
    html=html.replace('</head>',css+'\n</head>',1)

tag='  <script src="zab-guest-price.js" defer></script>\n'
if 'zab-guest-price.js' not in html:
    html=html.replace('</body>',tag+'</body>',1)

index.write_text(html,encoding="utf-8")
check=index.read_text(encoding="utf-8")
assert 'id="gepaeckpreis"' in check
assert 'zab-guest-price.js' in check
print("OK: Gäste-Sofortpreis eingebaut.")

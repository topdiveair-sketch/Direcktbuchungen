#!/usr/bin/env python3
from pathlib import Path
import json, shutil

root = Path.cwd()
index_path = root / "index.html"
if not index_path.exists(): raise SystemExit("Im Stammordner von Direcktbuchungen ausführen.")
html = index_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    n = text.count(old)
    if n != 1: raise SystemExit(f"{label}: erwartet 1 Treffer, gefunden {n}")
    return text.replace(old, new, 1)

old_extra = '              <label class="choice">\n                <input type="checkbox" name="extra" value="Gepäcktransport" data-price="15" data-unit="once">\n                <span><strong>Gepäcktransport</strong><small>15,00 EUR einmalig</small></span>\n                <b class="price">+15,00</b>\n              </label>'
new_extra = '              <label class="choice">\n                <input id="luggageTransport" type="checkbox" name="extra" value="ZAB GepäckFrei" data-price="0" data-unit="once">\n                <span><strong>ZAB GepäckFrei</strong><small>Gepäcktransport nach Strecke – Preis wird vorab bestätigt</small></span>\n                <b class="price">auf Anfrage</b>\n              </label>\n              <div id="luggageDetails" class="hidden" style="padding:12px;border:1px solid #b9d5c8;border-radius:10px;background:#f4faf7;display:grid;gap:10px">\n                <strong>🧳 Gepäcktransport planen</strong>\n                <label>Transportart\n                  <select id="luggageDirection" name="luggage_direction">\n                    <option value="outbound">Zuhause am Bach → nächste Unterkunft</option>\n                    <option value="inbound">vorherige Unterkunft → Zuhause am Bach</option>\n                    <option value="both">beide Richtungen</option>\n                  </select>\n                </label>\n                <div id="luggagePreviousFields" class="hidden">\n                  <label>Vorherige Unterkunft<input id="previousAccommodation" name="previous_accommodation"></label>\n                  <label>Ort<input id="previousTown" name="previous_town"></label>\n                  <label>Adresse<input id="previousAddress" name="previous_address"></label>\n                </div>\n                <div id="luggageNextFields">\n                  <label>Nächste Unterkunft<input id="nextAccommodation" name="next_accommodation"></label>\n                  <label>Ort<input id="nextTown" name="next_town"></label>\n                  <label>Adresse<input id="nextAddress" name="next_address"></label>\n                </div>\n                <label>Abholdatum<input id="luggagePickupDate" name="luggage_pickup_date" type="date"></label>\n                <label>Anzahl Gepäckstücke<input id="luggagePieces" name="luggage_pieces" type="number" min="1" max="10" value="1"></label>\n                <label><input id="luggageTaxi" name="luggage_taxi" type="checkbox"> Personentransfer / Taxi zusätzlich anfragen</label>\n                <label>Bemerkung<textarea id="luggageNote" name="luggage_note"></textarea></label>\n                <div class="hint"><strong>Preis nach Strecke.</strong> Transport, Abholzeit und Preis werden persönlich bestätigt. Der Gepäckpreis ist nicht im angezeigten Zimmerpreis enthalten.</div>\n              </div>'
html = once(html, old_extra, new_extra, "15-EUR-Gepäck-Extra")

nav = '        <a href="welterbesteig-unterkunft-wachau/">Welterbesteig</a>\n'
if 'href="wandern-ohne-gepaeck-wachau/">GepäckFrei' not in html:
    html = once(html, nav, nav + '        <a href="wandern-ohne-gepaeck-wachau/">GepäckFrei</a>\n', "Navigation")

feature = '    <section id="gepaeckfrei">\n      <div class="section-head">\n        <span class="eyebrow">ZAB GepäckFrei · Wandern ohne schweres Gepäck</span>\n        <h2>Eine Nacht. Eine Etappe. Kein schweres Gepäck.</h2>\n        <p>Sie planen Ihre Wachau-Tour selbst? Hausgäste können Gepäcktransport von der vorherigen Unterkunft zu uns und/oder von Zuhause am Bach zur nächsten Unterkunft anfragen. Keine komplette Wanderpauschale notwendig. Transport, Abholzeit und Preis werden vorab persönlich bestätigt.</p>\n      </div>\n      <div class="facts">\n        <article class="fact"><strong>🧳 Einzelne Etappe</strong><small>Auch für nur eine Übernachtung anfragbar.</small></article>\n        <article class="fact"><strong>↔ Beide Richtungen</strong><small>Vorherige Unterkunft → ZAB → nächste Unterkunft.</small></article>\n        <article class="fact"><strong>🚕 Optional Taxi</strong><small>Personentransfer kann zusätzlich angefragt werden.</small></article>\n        <article class="fact"><strong>✓ Persönlich bestätigt</strong><small>Keine erfundenen Pauschalpreise.</small></article>\n      </div>\n      <p><a class="btn" href="#booking-title">ZAB GepäckFrei mit Aufenthalt anfragen</a> &nbsp; <a href="wandern-ohne-gepaeck-wachau/">Mehr erfahren</a></p>\n    </section>\n\n'
if 'id="gepaeckfrei"' not in html:
    html = once(html, '    <section id="zimmer">\n', feature + '    <section id="zimmer">\n', "Produktsektion")

html = html.replace('<article class="fact"><strong>Gepäcktransport</strong><small>15,00 EUR einmalig, besonders praktisch für Radfahrer und Wanderer.</small></article>', '<article class="fact"><strong>ZAB GepäckFrei</strong><small>Gepäcktransport nach Strecke anfragbar. Transport, Abholzeit und Preis werden vorab persönlich bestätigt.</small></article>')

oldfaq = '<details><summary>Ist Gepäcktransport möglich?</summary><p>Ja, auf Anfrage als Zusatzleistung.</p></details>'
newfaq = '<details><summary>Kann ich Gepäcktransport auch für nur eine Etappe anfragen?</summary><p>Ja. ZAB GepäckFrei kann unabhängig von einer kompletten Wanderpauschale angefragt werden. Wir prüfen Strecke, Transport, Abholzeit und Preis persönlich.</p></details><details><summary>Kann mein Gepäck zur nächsten Unterkunft gebracht werden?</summary><p>Das kann angefragt werden. Bitte Unterkunft, Adresse und Gepäckstücke eintragen.</p></details><details><summary>Was kostet der Gepäcktransport?</summary><p>Der Preis hängt von Strecke und Umfang ab und wird vor einer verbindlichen Buchung bestätigt.</p></details>'
html = once(html, oldfaq, newfaq, "FAQ")

anchor = '    const copyConfirmation = document.getElementById("copyConfirmation");\n'
consts = '    const luggageTransport = document.getElementById("luggageTransport");\n    const luggageDetails = document.getElementById("luggageDetails");\n    const luggageDirection = document.getElementById("luggageDirection");\n    const luggagePreviousFields = document.getElementById("luggagePreviousFields");\n    const luggageNextFields = document.getElementById("luggageNextFields");\n'
if "const luggageTransport =" not in html: html = once(html, anchor, anchor + consts, "JS-Konstanten")

selected = '    function selectedExtras() {\n      return Array.from(form.querySelectorAll(\'input[name="extra"]:checked\'));\n    }\n'
funcs = '\n    function luggageSelected() {\n      return Boolean(luggageTransport && luggageTransport.checked);\n    }\n\n    function updateLuggageDetails() {\n      if (!luggageTransport || !luggageDetails || !luggageDirection) return;\n      const active = luggageTransport.checked;\n      luggageDetails.classList.toggle("hidden", !active);\n      const direction = luggageDirection.value || "outbound";\n      luggagePreviousFields?.classList.toggle("hidden", !active || direction === "outbound");\n      luggageNextFields?.classList.toggle("hidden", !active || direction === "inbound");\n      const pickup = document.getElementById("luggagePickupDate");\n      if (pickup && !pickup.value) pickup.value = direction === "inbound" ? arrival.value : departure.value;\n    }\n\n    function luggageRequestLines() {\n      if (!luggageSelected()) return [];\n      const direction = luggageDirection?.value || "outbound";\n      const dir = direction === "inbound" ? "vorherige Unterkunft → Zuhause am Bach" : direction === "both" ? "vorherige Unterkunft → Zuhause am Bach → nächste Unterkunft" : "Zuhause am Bach → nächste Unterkunft";\n      const previous = [document.getElementById("previousAccommodation")?.value, document.getElementById("previousTown")?.value, document.getElementById("previousAddress")?.value].filter(Boolean).join(", ");\n      const next = [document.getElementById("nextAccommodation")?.value, document.getElementById("nextTown")?.value, document.getElementById("nextAddress")?.value].filter(Boolean).join(", ");\n      return ["", "ZAB GEPÄCKFREI", "Transport: " + dir,\n        ...(direction !== "outbound" ? ["Vorherige Unterkunft: " + (previous || "-")] : []),\n        ...(direction !== "inbound" ? ["Nächste Unterkunft: " + (next || "-")] : []),\n        "Abholdatum: " + (document.getElementById("luggagePickupDate")?.value || "-"),\n        "Gepäckstücke: " + (document.getElementById("luggagePieces")?.value || "1"),\n        "Personentransfer / Taxi: " + (document.getElementById("luggageTaxi")?.checked ? "Ja" : "Nein"),\n        "Bemerkung: " + (document.getElementById("luggageNote")?.value || "-"),\n        "Preisstatus: nach Strecke – wird persönlich bestätigt; nicht im angezeigten Zimmerpreis enthalten."];\n    }\n\n    function validateLuggageRequest() {\n      if (!luggageSelected()) return true;\n      const d = luggageDirection?.value || "outbound";\n      const required = [document.getElementById("luggagePickupDate"), document.getElementById("luggagePieces")];\n      if (d !== "outbound") required.push(document.getElementById("previousAccommodation"), document.getElementById("previousTown"), document.getElementById("previousAddress"));\n      if (d !== "inbound") required.push(document.getElementById("nextAccommodation"), document.getElementById("nextTown"), document.getElementById("nextAddress"));\n      const missing = required.find(x => !x || !String(x.value || "").trim());\n      if (missing) { missing?.focus(); alert("Bitte die Angaben für ZAB GepäckFrei vervollständigen."); return false; }\n      return true;\n    }\n'
if "function luggageSelected()" not in html: html = once(html, selected, selected + funcs, "JS-Funktionen")

html = once(html, '      total.textContent = money(sumCents);\n      discountNote.textContent = "Zimmerpreis und gewählte Zusatzleistungen – verbindlich erst nach persönlicher Bestätigung.";', '      total.textContent = money(sumCents) + (luggageSelected() ? " + Gepäcktransport auf Anfrage" : "");\n      discountNote.textContent = luggageSelected() ? "Zimmerpreis und berechenbare Zusatzleistungen. ZAB GepäckFrei ist im angezeigten Betrag noch nicht enthalten; Transport, Abholzeit und Preis werden vorab persönlich bestätigt." : "Zimmerpreis und gewählte Zusatzleistungen – verbindlich erst nach persönlicher Bestätigung.";\n      updateLuggageDetails();', "Preislogik")

mail = '        tr("labelExtras") + ": " + extras,\n'
if "...luggageRequestLines()," not in html: html = once(html, mail, mail + "        ...luggageRequestLines(),\n", "E-Mail")

submit = "      const n = nightCount();\n      if (n < 1) {"
if "if (!validateLuggageRequest()) return;" not in html: html = once(html, submit, "      if (!validateLuggageRequest()) return;\n" + submit, "Validierung")

listener = '    form.addEventListener("input", function() {\n'
prelude = '    luggageTransport?.addEventListener("change", function() { updateLuggageDetails(); });\n    luggageDirection?.addEventListener("change", updateLuggageDetails);\n    updateLuggageDetails();\n\n'
if "luggageDirection?.addEventListener" not in html: html = once(html, listener, prelude + listener, "Listener")

html = html.replace('"dateModified": "2026-08-10"', '"dateModified": "2026-08-11"')
html = html.replace('"dateModified":"2026-08-10"', '"dateModified":"2026-08-11"')
index_path.write_text(html, encoding="utf-8")

src = Path(__file__).resolve().parent / "files"
shutil.copy2(src / "luggage-routes.json", root / "luggage-routes.json")
dst = root / "wandern-ohne-gepaeck-wachau" / "index.html"
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src / "wandern-ohne-gepaeck-wachau" / "index.html", dst)

wpath = root / "welterbesteig-unterkunft-wachau" / "index.html"
if wpath.exists():
    w = wpath.read_text(encoding="utf-8")
    w = w.replace("Gepäcktransport lässt sich als Zusatzleistung anfragen.", "Mit ZAB GepäckFrei kann Gepäcktransport für einzelne Etappen angefragt werden; Transport, Abholzeit und Preis werden vorab persönlich bestätigt.")
    wpath.write_text(w, encoding="utf-8")

spath = root / "sitemap.xml"
if spath.exists():
    sm = spath.read_text(encoding="utf-8")
    u = '  <url><loc>https://topdiveair-sketch.github.io/Direcktbuchungen/wandern-ohne-gepaeck-wachau/</loc></url>'
    if u not in sm: sm = sm.replace("</urlset>", u + "\n</urlset>")
    spath.write_text(sm, encoding="utf-8")

final = index_path.read_text(encoding="utf-8")
assert 'data-price="15"' not in final
assert 'id="luggageTransport"' in final
assert "function validateLuggageRequest()" in final
assert "...luggageRequestLines()," in final
assert dst.exists()
matrix = json.loads((root / "luggage-routes.json").read_text(encoding="utf-8"))
assert all(r["price"] is None for r in matrix["routes"])
print("OK: ZAB GepäckFrei eingebaut und statisch geprüft.")

# SEO-Umsetzungsbericht – Zuhause am Bach

Stand: 10. August 2026

## Technische Analyse

- Architektur: statische HTML-/CSS-/JavaScript-Website ohne Framework und ohne Buildsystem.
- Routing: `index.html` sowie physische Unterordner mit jeweils eigener `index.html`.
- Header/Footer: vollständig in der Startseite enthalten; neue Seiten verwenden eine gemeinsame, crawlbare Navigation und einen kompakten Footer.
- Buchung: Anfrageformular mit Datum, Zimmerlogik, Preisberechnung, Kalender-JSON, E-Mail, WhatsApp und PayPal-Hinweisen. Diese Logik wurde nicht verändert.
- Bestehendes SEO: Title, Description, Canonical, OpenGraph und LodgingBusiness/BedAndBreakfast-JSON-LD waren auf der Startseite vorhanden.
- Fehlend waren Sitemap, robots.txt, eigenständige Landingpages, Breadcrumbs und individuelle Metadaten für Unterthemen.
- Google Analytics/Search Console: keine Einbindung im Repository gefunden.
- 404-Seite: Bei GitHub Pages ist eine benutzerdefinierte 404-Seite möglich, wurde aber nicht ergänzt, da Hostingpfad und gewünschtes Fehlerseitenverhalten vor Veröffentlichung bestätigt werden sollten.

## Umgesetzte Maßnahmen

- Startseite: präziser Title, Description, H1 und Einleitung; sichtbare Einstiege in die neuen Themenbereiche; kompakter Faktenbereich.
- OpenGraph/Twitter Cards: ergänzt bzw. vereinheitlicht.
- Strukturierte Daten: bestehendes Unterkunftsschema um Telefon, Check-in 14:00, Check-out 10:00, sichere Fahrradunterbringung und E-Bike-Laden ergänzt.
- Unterseiten: BreadcrumbList und WebPage-JSON-LD; FAQPage ausschließlich auf der sichtbar dargestellten Donauradweg-FAQ.
- Interne Links: Startseite, Landingpages, Guide, Tipps-Hub und Buchungsformular sinnvoll miteinander verbunden.
- Performance: Das verwirrende erste Titelbild wurde entfernt. Das als Hero-Hintergrund verwendete Luftbild wurde von ca. 3,7 MB auf ca. 244 KB als WebP optimiert; nicht kritische Bilder laden lazy.
- Indexierung: `robots.txt` und XML-Sitemap mit allen sieben öffentlichen URLs erstellt.
- Inhalte: keine unbelegten Rankings, Bewertungen, Auszeichnungen, Entfernungen oder Öffnungszeiten ergänzt.
- Sprachumschaltung: Die neu ergänzten Startseiten-, Navigations- und Fakteninhalte wurden in die vorhandenen Wörterbücher für Englisch, Tschechisch, Ungarisch, Spanisch und Französisch aufgenommen und im Browser geprüft.
- Vorteils-Audit für Radfahrer und Wanderer: Die beiden Pillar-Pages bündeln jetzt sichere Fahrradunterbringung, E-Bike-Laden, Frühstück einschließlich vegetarischer/veganer Wünsche, Jause, Gepäcktransport, Gäste-App, persönliche Tipps, Direktanfrage und den eigenen Etappenstempel. Fidel, Gloria und Pia schaffen Wiedererkennung, während die Unterkunft der klare Hauptgegenstand bleibt.
- KI-Lesbarkeit: Kurze Faktenblöcke erklären Angebot, Zielgruppen, Ort und Nutzen in direkter Sprache. Die maschinenlesbaren Unterkunftsdaten der Unterseiten enthalten außerdem Telefon, Check-in/Check-out sowie die zentralen Ausstattungsmerkmale.

## Neue URLs

- `/donauradweg-unterkunft-wachau/`
- `/welterbesteig-unterkunft-wachau/`
- `/ruhige-unterkunft-wachau/`
- `/aggsbach-markt-wachau/`
- `/wachau-tipps/`
- `/wilde-wachauer-windis/`

## Geänderte Dateien

- `index.html`
- `images/windis-wachau-app.webp` (neu)
- `images/aggsbach-markt-luftbild.webp` (neu)
- `seo-pages.css` (neu)
- `robots.txt` (neu)
- `sitemap.xml` (neu)
- `donauradweg-unterkunft-wachau/index.html` (neu)
- `welterbesteig-unterkunft-wachau/index.html` (neu)
- `ruhige-unterkunft-wachau/index.html` (neu)
- `aggsbach-markt-wachau/index.html` (neu)
- `wachau-tipps/index.html` (neu)
- `wilde-wachauer-windis/index.html` (neu)
- `scripts/test-seo-site.mjs` (neu)
- `SEO_UMSETZUNGSBERICHT.md` (neu)

## Prüfungen

- Kein Buildbefehl vorhanden: Die Website wird direkt als statische Dateien ausgeliefert.
- Kein Linter konfiguriert.
- JavaScript-Syntax der Funktionsskripte erfolgreich mit Node geprüft.
- Automatischer Test erfolgreich: sieben HTML-Seiten, Metadaten, genau eine H1 je Seite, JSON-LD, lokale Links und Sitemap.
- Browserprüfung mit Microsoft Edge/Playwright erfolgreich: Desktop und Mobil, keine JavaScript-Seitenfehler, kein mobiler horizontaler Overflow.
- Sprachprüfung erfolgreich: DE, EN, CS, HU, ES und FR ändern H1, zentrale neue Inhalte und das HTML-Sprachattribut korrekt.
- Buchungs-, Preis-, Kalender-, Zahlungs- und Zimmerfreigabe-Code wurde nicht verändert.

## Noch zu bestätigen / manuell zu erledigen

- Die Canonical-Basis lautet wie im Ausgangsprojekt `https://topdiveair-sketch.github.io/Direcktbuchungen/`. Falls eine eigene Domain verwendet wird, müssen Canonicals, OpenGraph-URLs, Schema-URLs, Sitemap und robots.txt vor Veröffentlichung auf diese Domain umgestellt werden.
- Sitemap nach Veröffentlichung in der Google Search Console einreichen.
- Google Search Console und optional datenschutzkonformes Analytics einrichten; im Code war keine bestehende Einbindung vorhanden.
- Google-Unternehmensprofil aktuell halten und auf die endgültige Website verlinken.
- E-Bike-Ladeort, sichere Fahrradunterbringung sowie vegane/vegetarische Frühstücksabläufe intern bestätigen und bei Änderungen in den Texten aktualisieren.
- Eine individuelle `404.html` ergänzen, sobald endgültiger Hostingpfad und gewünschte Navigation bestätigt sind.
- Aktuelle Öffnungszeiten, Fahrpläne und saisonale Hinweise weiterhin nur über Primärquellen pflegen.

## Statusübersicht

| PRIORITÄT | MASSNAHME | STATUS | SEO-WIRKUNG |
|---|---|---|---|
| Hoch | Eindeutige Startseiten-Signale für Unterkunft, Ort, Welterbesteig und Donauradweg | erledigt | Klare lokale und thematische Einordnung |
| Hoch | Donauradweg- und Welterbesteig-Pillar-Pages | erledigt | Relevante, eigenständige Suchintentionen |
| Hoch | Individuelle Titles, Descriptions, Canonicals und Social-Metadaten | erledigt | Bessere Indexierung und Snippet-Grundlage |
| Hoch | Interne Linkarchitektur und crawlbare Navigation | erledigt | Themenbeziehungen und Auffindbarkeit |
| Hoch | XML-Sitemap und robots.txt | erledigt | Technische Crawlbarkeit |
| Hoch | Strukturierte Daten für Unterkunft, Breadcrumbs und sichtbare FAQ | erledigt | Maschinenlesbare Entity- und Seitenstruktur |
| Mittel | Aggsbach-Markt-Guide, ruhige Unterkunft und Tipps-Hub | erledigt | Lokale Autorität und Long-Tail-Abdeckung |
| Mittel | Windi-Markenseite mit klarer Unterkunftseinordnung | erledigt | Markenbezug ohne thematische Verschiebung |
| Hoch | LCP-relevante Bildoptimierung und Lazy Loading | erledigt | Deutlich geringeres Übertragungsvolumen |
| Hoch | Buchungs- und Kalenderlogik erhalten | erledigt | Kein Funktionsrisiko durch SEO-Ausbau |
| Hoch | Eigene Domain in allen absoluten URLs bestätigen | manuell erforderlich | Vermeidet falsche Canonicals nach Domainwechsel |
| Hoch | Sitemap in Search Console einreichen | manuell erforderlich | Schnellere Entdeckung neuer URLs |
| Mittel | Search Console/Analytics einrichten | manuell erforderlich | Messbarkeit von Impressionen und Verhalten |
| Mittel | Individuelle GitHub-Pages-404 ergänzen | teilweise erledigt | Bessere Navigation bei fehlerhaften URLs |
| Mittel | Inhalte mit saisonalen lokalen Tipps ausbauen | teilweise erledigt | Wachsende lokale Themenautorität |

## SEO- und KI-Vorteilsprüfung für aktive Gäste

| Vorteil | Radfahrer-Seite | Wanderer-Seite | Einordnung |
|---|---|---|---|
| Ruhige persönliche Unterkunft in Aggsbach Markt | enthalten | enthalten | Kernpositionierung |
| Donauradweg / Welterbesteig | enthalten | enthalten | Klare Suchintention |
| Sichere Fahrradunterbringung | enthalten | als allgemeiner Unterkunftsfakt enthalten | Praktischer Radreisevorteil |
| E-Bike-Lademöglichkeit | enthalten | als allgemeiner Unterkunftsfakt enthalten | Praktischer E-Bike-Vorteil |
| Frühstück | enthalten | enthalten | Etappenstart |
| Vegetarisch/vegan nach Absprache | enthalten | enthalten | Konkreter Ernährungsnutzen |
| Wachauer Jause | enthalten | auf der Startseite buchbar | Zusatzleistung |
| Gepäcktransport | enthalten | enthalten | Nutzen für Etappenreisende |
| Gäste-App | enthalten | enthalten | Wetter, Hausinfo und Orientierung |
| Persönliche Wachau-Tipps | enthalten | enthalten | Lokaler Gastgebervorteil |
| Eigener Wachau-Etappenstempel | enthalten, transparent erklärt | enthalten, transparent erklärt | Einprägsames Hausgast-Erlebnis |
| Fidel, Gloria und Pia | enthalten | enthalten | Emotionales Markenelement |
| Direkte persönliche Anfrage | enthalten | enthalten | Vertrauen und Klarheit |

Die Seiten vermeiden weiterhin nicht belegbare Aussagen wie „beste Unterkunft“, „Nr. 1“ oder garantierte Entfernungen. Statt eines künstlichen „Muss“-Versprechens vermitteln sie belegbare Gründe, warum die Unterkunft für Radfahrer und Wanderer besonders passend und erinnerungswürdig ist.

## Abschlussstatus der Codex-Aufgabenliste

| Priorität | Aufgabe | Status | Datei | Bemerkung |
|---|---|---|---|---|
| 1 | Ziel-Title, H1 und Meta Description | erledigt | `index.html` | Exakte Zielformulierungen, jeweils nur einmal vorhanden |
| 1 | Canonical | erledigt | `index.html` | Startseite canonicalisiert auf `/Direcktbuchungen/` |
| 1 | robots.txt | erledigt | `robots.txt` | Öffentliche Seiten, CSS, JavaScript und Bilder erlaubt |
| 1 | XML-Sitemap | erledigt | `sitemap.xml` | Sieben öffentliche URLs, keine Testseiten |
| 2 | Donauradweg-Landingpage | erledigt | `donauradweg-unterkunft-wachau/index.html` | Bestehende GitHub-Pages-Ordnerstruktur verwendet |
| 2 | Welterbesteig-Landingpage | erledigt | `welterbesteig-unterkunft-wachau/index.html` | Keine erfundenen Distanzen oder Gehzeiten |
| 2 | Aggsbach-Markt-Seite | erledigt | `aggsbach-markt-wachau/index.html` | Keine veraltenden Öffnungszeiten festgeschrieben |
| 2 | Wachau-Tipps-Hub | erledigt | `wachau-tipps/index.html` | Erweiterbare Themenkarten |
| 3 | BedAndBreakfast-/LodgingBusiness-Daten | erledigt | `index.html`, SEO-Unterseiten | Check-in 14:00, Check-out 10:00, verifizierte Merkmale |
| 3 | Breadcrumbs und BreadcrumbList | erledigt | SEO-Unterseiten | Sichtbar und maschinenlesbar |
| 3 | Interne Verlinkung | erledigt | `index.html`, SEO-Unterseiten | Relevante Kontextlinks und Buchungsanfrage |
| 3 | Überschriften, IDs und Alt-Texte | erledigt | alle HTML-Dateien | Automatisch geprüft |
| 4 | Anfrage-/Zahlungsmodell vereinheitlichen | erledigt | `index.html` | „Verfügbarkeit prüfen und direkt anfragen“, Zahlung erst nach Bestätigung |
| 4 | 5-%-Preisvergleich entfernen | erledigt | `index.html` | Text und automatische Rabattberechnung entfernt |
| 4 | Preise und Unternehmensdaten | erledigt | `index.html`, strukturierte Daten | Konsistent geprüft |
| 5 | Hero-Bild optimieren | erledigt | `index.html`, `images/aggsbach-markt-luftbild.webp` | 3,7-MB-PNG durch ca. 244-KB-WebP ersetzt |
| 5 | Tippbilder lazy laden | erledigt | `index.html` | CSS-Hintergründe durch echte Lazy-Loading-Bilder ersetzt |
| 5 | Bildabmessungen | erledigt | `index.html` | `width`/`height` für Inhaltsbilder ergänzt |
| 5 | Doppelte JavaScript-Prüfkopien | erledigt | Projektstamm | Sechs ungenutzte Kopien entfernt; Funktionsskripte bleiben inline |
| 5 | Mobile Tests | erledigt | `index.html` | 320, 375, 390 px und Tablet ohne horizontalen Overflow |
| 6 | Faktenblock und Entity-Beziehungen | erledigt | `index.html` | Unterkunft, Ort, Region und Zielgruppen eindeutig verbunden |
| 6 | Windi-Seite | erledigt | `wilde-wachauer-windis/index.html` | Unterkunft bleibt Hauptthema |
| 7 | Links, HTML-Struktur und JSON-LD prüfen | erledigt | gesamte Website | Automatisierte Tests bestanden |
| 7 | Build/Linter | nicht möglich | – | Statische Website ohne Build- oder Lint-Konfiguration |
| 7 | Search Console und Google Business | manuell erforderlich | externe Dienste | Sitemap einreichen, Indexierung anstoßen, Profil pflegen |

### Neu angelegte öffentliche URLs

- `/Direcktbuchungen/donauradweg-unterkunft-wachau/`
- `/Direcktbuchungen/welterbesteig-unterkunft-wachau/`
- `/Direcktbuchungen/ruhige-unterkunft-wachau/`
- `/Direcktbuchungen/aggsbach-markt-wachau/`
- `/Direcktbuchungen/wachau-tipps/`
- `/Direcktbuchungen/wilde-wachauer-windis/`

### Aktuell geänderte Dateien

- `index.html`
- `robots.txt`
- `SEO_UMSETZUNGSBERICHT.md`

### Entfernte Dateien

- `script_0.js`, `script_1.js`, `script_2.js`
- `check_inline_0.js`, `check_inline_1.js`, `check_inline_2.js`

### Manuell außerhalb des Codes

- Sitemap in der Google Search Console einreichen und Haupt-, Donauradweg- sowie Welterbesteig-Seite zur Indexierung anstoßen.
- Google-Unternehmensprofil mit endgültiger Website-Adresse, Kontaktdaten, Frühstück, Fahrradunterbringung und E-Bike-Laden aktuell halten.
- Falls künftig eine eigene Domain genutzt wird, Canonicals, OpenGraph-URLs, Schema-URLs, Sitemap und robots.txt gemeinsam umstellen.

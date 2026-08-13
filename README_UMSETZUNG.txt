WINDIS-MARKENZENTRUM – Umsetzung

Enthalten:
1. windis.html
   Zentrale öffentliche Windis-Seite mit SEO, OpenGraph und Schema.org-JSON-LD.
2. windis-brand.json
   Maschinenlesbare Marken- und Figurenregeln für KI, Automationen und spätere Software.
3. WINDIS_MARKENBIBEL.md
   Verbindliche Regeln für Fidel, Gloria und Pia.
4. apply_windis_patch.py
   Ergänzt die bestehende index.html automatisch um:
   - Navigationslink „Die Windis“
   - sichtbaren Windis-Teaser
   - Verbindung im <head>

Installation:
- Dateien ins Hauptverzeichnis von Direcktbuchungen kopieren.
- Im Repository-Hauptverzeichnis ausführen:
  python apply_windis_patch.py index.html
- Danach index.html, windis.html, windis-brand.json und WINDIS_MARKENBIBEL.md committen/pushen.
- index.html.bak nicht committen.

Ziel-URL:
https://topdiveair-sketch.github.io/Direcktbuchungen/windis.html

Die Seite verwendet das bereits vorhandene Asset:
images/windis-wachau-app.webp

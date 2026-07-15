# Zuhause am Bach OS - V13.1 Fix 1

Stand: 15.07.2026

## Geaendert

- Lokaler HTTP-Login funktioniert mit `SESSION_COOKIE_SECURE=0`.
- `STARTEN.bat` setzt `SESSION_COOKIE_SECURE=0` fuer den lokalen Start.
- Mitarbeiterrollen bekommen nach `/staff/login` passende Arbeitsbereiche.
- Admin-Login bereinigt alte Sessions, nutzt konstante Passwortpruefung und sperrt nach mehreren Fehlversuchen kurzzeitig.
- Livebetrieb bricht bei fehlendem `SECRET_KEY` oder unsicherem `ADMIN_PASSWORD` ab.
- Buchungen werden vor dem Eintragen unter SQLite-Schreibsperre erneut auf Konflikte geprueft.
- Neuer Regressionstest: `REGRESSIONTEST_V13_1.py`.
- Live-Daten koennen ueber Railway-/Env-Variablen importiert werden: SMTP, PayPal, Google, iCal, Kontakt, Rechtstexte und Channel-Felder.
- Neue Dateien: `.env.production.template` und `LIVE_DATEN_EINTRAGEN.md`.
- Fix 3: Betreiber-/Kontaktdaten fuer Laura Prem, Adresse Aggsbach Markt 82, Gmail-SMTP-Grunddaten, PayPal-Mail, Google-Rating-Angabe und Rechtstext-Entwuerfe vorbereitet.
- Neue Dateien: `RAILWAY_VARIABLES_ZAB.md` und `DATEN_ANNAHMEN_UND_QUELLEN.md`.
- Fix 4: Live-Preflight `LIVE_PREFLIGHT.py` prueft Railway-Variablen vor dem Deploy.
- Fix 5: Fruehstueck, Wachauer Jause und Gepaecktransport werden in der Buchungsabfrage oberhalb der Zimmer angezeigt; Gepaecktransport kostet jetzt 15,00 EUR einmalig.
- Fix 6 Online Ready: `ONLINE_READY_CHECK.py`, `POST_DEPLOY_CHECK.py`, `README_DEPLOY_RAILWAY.md`, `.railwayignore` und `.dockerignore` ergaenzt.
- Fix 7 UTF-8: JSON-Ausgabe liefert Umlaute als UTF-8, Availability-Meldungen korrigiert und Encoding-Pruefung gegen kaputte Umlaut-Sequenzen ergaenzt.

## Paket

- Das Verteilungspaket darf keine Betriebsdaten, Backups, Restore-Points oder `__pycache__` enthalten.
- Fuer Railway muss `DATA_DIR=/data` gesetzt und ein Volume nach `/data` gemountet werden.

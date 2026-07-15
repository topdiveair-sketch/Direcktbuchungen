# Online stellen mit Railway

## Status

Diese Version ist technisch deploybereit. Noch einzutragen sind:

- echtes Gmail-App-Passwort in `SMTP_PASSWORD`
- Bachblick-iCal-Link in `ICAL_BACHBLICK_URL`
- derselbe Bachblick-iCal-Link in `CHANNEL_BOOKING_COM_IMPORT_URL`

## 1. Private Variablen fertigstellen

Die Datei `RAILWAY_VARIABLES_ZAB_PRIVATE_20260715.txt` liegt ausserhalb des App-ZIPs im `outputs`-Ordner. Dort die zwei Platzhalter ersetzen:

```text
SMTP_PASSWORD=...
ICAL_BACHBLICK_URL=...
CHANNEL_BOOKING_COM_IMPORT_URL=...
```

Danach lokal pruefen:

```bash
python LIVE_PREFLIGHT.py RAILWAY_VARIABLES_ZAB_PRIVATE_20260715.txt
```

Erwartet: `18/18 Live-Checks OK`.

## 2. GitHub vorbereiten

Nur den Inhalt dieses Projektordners in GitHub hochladen. Nicht hochladen:

- `data/*.db`
- Backups / Restore-Points
- `.env`
- `RAILWAY_VARIABLES_ZAB_PRIVATE*.txt`
- `__pycache__`
- lokale Logs

Die Dateien `.gitignore`, `.railwayignore` und `.dockerignore` sind vorbereitet.

## 3. Railway-Projekt

1. Railway oeffnen.
2. Neues Projekt erstellen oder bestehendes Projekt verwenden.
3. GitHub-Repository verbinden.
4. Volume erstellen und nach `/data` mounten.
5. Alle Variablen aus `RAILWAY_VARIABLES_ZAB_PRIVATE_20260715.txt` in Railway unter **Variables** eintragen.
6. Deploy starten.

Railway nutzt:

```text
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app
```

## 4. Nach dem Deploy pruefen

```bash
python POST_DEPLOY_CHECK.py https://deine-railway-domain.up.railway.app
```

Optional mit Admin-Login-Test:

```bash
set ADMIN_PASSWORD=<dein Admin-Passwort>
python POST_DEPLOY_CHECK.py https://deine-railway-domain.up.railway.app
```

Danach im Browser:

1. `/health`
2. Startseite
3. `/admin/login`
4. `/admin` und iCal-Sync testen
5. Testbuchung erstellen
6. E-Mail-Versand pruefen
7. Testbuchung wieder stornieren

## 5. Grenzen

- SQLite ist fuer eine kleine Ein-Instanz-App geeignet. Keine parallelen Railway-Instanzen betreiben.
- Das Volume `/data` ist Pflicht, sonst gehen Betriebsdaten bei Redeploy verloren.
- Rechtstexte sind Entwuerfe und muessen vor Livegang juristisch geprueft werden.

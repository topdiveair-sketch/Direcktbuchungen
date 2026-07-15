# Railway-Bereitstellung – Zuhause am Bach OS V13.1

Aktueller Ablauf: siehe `README_DEPLOY_RAILWAY.md`.

## 1. GitHub
Den Inhalt dieses Ordners in das Repository `topdiveair-sketch/Direcktbuchungen` laden.
Die Ordner `data`, Datenbanken, Backups, Rechnungen und `.env` dürfen nicht hochgeladen werden.

## 2. Railway-Projekt
1. In Railway **New Project → Deploy from GitHub repo** wählen.
2. Repository `Direcktbuchungen` verbinden.
3. Einen **Volume** anlegen und nach `/data` mounten.
4. Unter **Variables** folgende Werte setzen:
   - `DATA_DIR=/data`
   - `SECRET_KEY=<lange zufällige Zeichenfolge>`
   - `ADMIN_PASSWORD=<neues starkes Passwort>`
   - `PAYPAL_EMAIL=topdiveair@gmail.com`
   - `SESSION_COOKIE_SECURE=1`
5. Öffentliche Domain in Railway erzeugen.

## 3. Technischer Betrieb
- Start: Gunicorn mit einem Worker und vier Threads.
- Healthcheck: `/health`.
- Datenhaltung: SQLite auf dem Railway-Volume.
- Für diesen kleinen Beherbergungsbetrieb ist das zunächst ausreichend, solange nur eine App-Instanz läuft.

## 4. Wichtige Einschränkung
Railway ohne Volume würde bei einem Redeploy alle SQLite-Betriebsdaten verlieren. Das Volume ist daher zwingend.
Mehrere parallele App-Instanzen dürfen mit dieser SQLite-Version nicht betrieben werden.

## 5. Nach dem ersten Start
- `/setup` öffnen.
- Admin-Passwort testen.
- Booking-iCal-Links eintragen.
- E-Mail, Adresse, Telefonnummer, Bewertungslink und PayPal prüfen.
- Testbuchung durchführen.

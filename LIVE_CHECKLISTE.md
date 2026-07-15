# Live-Checkliste

Vor oeffentlichem Betrieb pruefen:

1. Railway-Volume nach `/data` mounten.
2. Railway-Variablen setzen:
   - `DATA_DIR=/data`
   - `SECRET_KEY=<mindestens 32 zufaellige Zeichen>`
   - `ADMIN_PASSWORD=<starkes Passwort>`
   - `PAYPAL_EMAIL=<echte Adresse>`
   - `SESSION_COOKIE_SECURE=1`
   - `REQUIRE_PRODUCTION_SECRETS=1`
   - SMTP-Werte: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`
   - iCal-Werte: `ICAL_BACHBLICK_URL`, `ICAL_MARILLENZIMMER_URL`, `ICAL_WEINBERGZIMMER_URL`, `ICAL_DONAUZIMMER_URL`
   - Google/PayPal/Kontakt laut `.env.production.template`
3. Admin-Login testen und Standardpasswort nicht verwenden.
4. Booking-iCal-Links pro Zimmer eintragen und Sync pruefen.
5. SMTP-Daten fuer Buchungs-E-Mails eintragen.
6. Echte Zimmerbilder hochladen.
7. Impressum, Datenschutz, Buchungs- und Stornobedingungen rechtlich pruefen.
8. PayPal.Me-Link oder spaeter echten PayPal-Checkout eintragen.
9. Testbuchung anlegen, E-Mail pruefen, Rechnung pruefen, Buchung wieder stornieren.
10. GitHub/ZIP vor Upload pruefen: keine `data/*.db`, keine Backups, keine Restore-Points, kein `__pycache__`.

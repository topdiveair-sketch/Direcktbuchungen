# Echte Live-Daten eintragen

Diese Version liest echte Betriebsdaten beim Start aus Umgebungsvariablen. Trage die Werte in Railway unter **Variables** ein. Secrets gehoeren nicht in GitHub und nicht dauerhaft in ZIP-Dateien.

## Was automatisch uebernommen wird

- Kontakt: `SITE_PHONE`, `SITE_EMAIL`, `SITE_ADDRESS`
- Oeffentliche URL: `PUBLIC_BASE_URL`
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`
- PayPal: `PAYPAL_EMAIL`, `PAYPAL_ME_URL`
- Google: `GOOGLE_RATING`, `GOOGLE_REVIEW_COUNT`, `GOOGLE_REVIEW_URL`, optional `GOOGLE_PLACES_API_KEY`
- Booking-iCal: `ICAL_BACHBLICK_URL`, `ICAL_MARILLENZIMMER_URL`, `ICAL_WEINBERGZIMMER_URL`, `ICAL_DONAUZIMMER_URL`
- Weitere Channel-Felder: `CHANNEL_BOOKING_COM_*`, `CHANNEL_AIRBNB_*`, `CHANNEL_EXPEDIA_*`, `CHANNEL_FEWO_DIREKT_*`, `CHANNEL_GOOGLE_HOTELS_*`
- Rechtstexte: `LEGAL_IMPRESSUM_TEXT`, `LEGAL_DATENSCHUTZ_TEXT`, `LEGAL_AGB_TEXT`, `LEGAL_STORNO_TEXT`

## Rechtstexte

Die App kann Rechtstexte speichern und anzeigen. Sie erstellt aber keine rechtlich verbindlichen Texte. Setze nur gepruefte Texte ein. Lange Texte sind im Adminbereich unter `/admin/legal` leichter zu pflegen als in Railway-Variablen.

## Nach dem Eintragen

1. Railway neu deployen oder Service neu starten.
2. `/health` pruefen.
3. Admin-Login pruefen.
4. `/admin` oeffnen und die uebernommenen Werte kontrollieren.
5. Booking-iCal manuell synchronisieren.
6. Testbuchung anlegen und E-Mail-Versand pruefen.
7. Testbuchung stornieren oder loeschen.

## Preflight vor Railway

Vor dem Deploy kann die Variablen-Datei lokal geprueft werden:

```bash
python LIVE_PREFLIGHT.py RAILWAY_VARIABLES_ZAB_PRIVATE_20260715.txt
```

Der Check muss vollstaendig gruen sein. Solange Gmail-App-Passwort oder Bachblick-iCal-Link noch Platzhalter sind, meldet der Preflight absichtlich `FEHLT`.

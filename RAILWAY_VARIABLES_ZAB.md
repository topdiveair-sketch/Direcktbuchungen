# Railway Variables - Zuhause am Bach

Diese Werte in Railway unter **Variables** eintragen. Geheimwerte nicht in GitHub committen.

## Pflicht

```text
APP_ENV=production
REQUIRE_PRODUCTION_SECRETS=1
DATA_DIR=/data
SESSION_COOKIE_SECURE=1
SECRET_KEY=<mindestens 32 zufaellige Zeichen>
ADMIN_PASSWORD=<neues Admin-Passwort, mindestens 12 Zeichen, nicht wiederverwenden>
```

Produktionspasswörter und andere Zugangsdaten dürfen weder hier noch in Issues, Commits oder Logs dokumentiert werden. Bereits veröffentlichte Zugangsdaten müssen rotiert werden.

## Betrieb / Kontakt

```text
SITE_PHONE=<Telefonnummer>
SITE_EMAIL=<E-Mail-Adresse>
SITE_ADDRESS=<Adresse>
PUBLIC_BASE_URL=<öffentliche Basis-URL>
PAYPAL_EMAIL=<PayPal-E-Mail-Adresse>
PAYPAL_ME_URL=
```

## Gmail SMTP

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<SMTP-Benutzer>
SMTP_PASSWORD=<eigenes Gmail-App-Passwort, nicht das Admin-Passwort>
SMTP_SENDER=<Absender>
```

## Google

```text
GOOGLE_RATING=<aktueller Wert>
GOOGLE_REVIEW_COUNT=<aktueller Wert>
GOOGLE_REVIEW_URL=<öffentliche Bewertungs-URL>
GOOGLE_PLACES_API_KEY=
```

## Booking-iCal

Die iCal-Export-URLs sind Zugangsdaten und gehören ausschließlich in Railway-/GitHub-/Cloudflare-Secrets.

```text
ICAL_BACHBLICK_URL=<Secret>
ICAL_MARILLENZIMMER_URL=<Secret oder leer>
ICAL_WEINBERGZIMMER_URL=<Secret oder leer>
ICAL_DONAUZIMMER_URL=<Secret oder leer>
```

Für den GitHub-Actions-Kalenderjob zusätzlich das Repository-Secret `BOOKING_ICAL_URL` setzen.

## Rechtstexte

Die App enthaelt Entwuerfe. Vor Livegang bitte im Adminbereich `/admin/legal` pruefen und final speichern.

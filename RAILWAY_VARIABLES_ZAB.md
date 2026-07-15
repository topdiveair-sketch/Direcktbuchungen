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

Hinweis: Das genannte Passwort `Padi971552` ist fuer den Produktionscheck zu kurz und sollte nicht wiederverwendet werden.

## Betrieb / Kontakt

```text
SITE_PHONE=+43 664 6437526
SITE_EMAIL=topdiveair@gmail.com
SITE_ADDRESS=Aggsbach Markt 82, 3641 Aggsbach Markt, Oesterreich
PUBLIC_BASE_URL=https://topdiveair-sketch.github.io/Gaeste/
PAYPAL_EMAIL=topdiveair@gmail.com
PAYPAL_ME_URL=
```

## Gmail SMTP

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=topdiveair@gmail.com
SMTP_PASSWORD=<eigenes Gmail-App-Passwort, nicht das Admin-Passwort>
SMTP_SENDER=Zuhause am Bach <topdiveair@gmail.com>
```

## Google

```text
GOOGLE_RATING=4.8
GOOGLE_REVIEW_COUNT=4
GOOGLE_REVIEW_URL=https://www.google.com/maps/search/?api=1&query=Zuhause%20am%20Bach%20-%20Wachau%20Aggsbach%20Markt%2082
GOOGLE_PLACES_API_KEY=
```

Die Bewertungswerte stammen aus einem externen Verzeichnis und sollten im Google-Unternehmensprofil kontrolliert werden.

## Booking-iCal

```text
ICAL_BACHBLICK_URL=<vorhandenen Bachblick-iCal-Link eintragen>
ICAL_MARILLENZIMMER_URL=
ICAL_WEINBERGZIMMER_URL=
ICAL_DONAUZIMMER_URL=
```

## Rechtstexte

Die App enthaelt Entwuerfe. Vor Livegang bitte im Adminbereich `/admin/legal` pruefen und final speichern.

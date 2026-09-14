# ZAB OS – Production hardening

Stand: 2026-09-14

## Ziel

Das lokale Windows-Zuhause-am-Bach-OS wird die operative Schaltzentrale. Railway bleibt der dauerhaft erreichbare Transaktions- und Synchronisationsknoten.

## Bereits aktiv

- ZAB-Masterkalender und Kanalsteuerung
- öffentlicher Sicherheitskalender aus ZAB-Master + Booking-iCal
- Direct-Price API mit Fail-Closed-Logik im aktuellen Code
- ZAB Control Center V3 mit `direct`, `booking`, `airbnb`, `other`
- private Gastmetadaten, Frühstück, Personenzahl und Anreiseart
- Booking-Connectivity-Adapter (nur aktiv, wenn echte Zugangsdaten + Room/Rate Mapping vorhanden sind)

## Kritischer Produktionsblocker

Der Railway-Service verwendet aktuell SQLite unter `/app/data/zab.db`, aber ohne persistentes Volume. Ein Deployment/Containerwechsel kann deshalb operative Daten verlieren.

**Keine Volume-Umstellung durchführen, bevor die aktuelle Live-Datenbank außerhalb des laufenden Containers gesichert wurde.**

Sicherheitsreihenfolge:

1. aktuelle `/app/data/zab.db` konsistent außerhalb des ephemeren Containers sichern;
2. Checksumme und Dateigröße dokumentieren;
3. persistentes Railway-Volume bereitstellen;
4. Volume an einen persistenten Datenpfad mounten;
5. gesicherte DB in das Volume zurückspielen;
6. `DATA_DIR` auf den Volume-Pfad setzen;
7. Deployment durchführen;
8. Tabellen, Buchungen, externe Blocks, Tagespreise und Kanalsteuerung verifizieren;
9. erst danach weitere automatische Deployments zulassen.

## Booking-Sicherheit

Bis Booking Connectivity vollständig konfiguriert und getestet ist:

- `ZAB_MASTER_CALENDAR_MODE=hybrid`
- `ZAB_MASTER_PAYPAL_INDEPENDENT=0`
- Booking-iCal bleibt zusätzliche Belegungssicherung.

## Windows OS

Windows V112.2.17 nutzt die V3-API `/api/central/zab-calendar` und sendet Änderungen nicht mehr still ins Leere, wenn bereits ein Hintergrundvorgang läuft. Railway-Verbindungen müssen HTTPS verwenden; HTTP ist nur für localhost-Entwicklung zulässig.

## Noch vor Produktivfreigabe Booking-Preis

Benötigt werden mindestens:

- `BOOKING_CONNECTIVITY_CLIENT_ID`
- `BOOKING_CONNECTIVITY_CLIENT_SECRET`
- `BOOKING_ROOM_ID_BACHBLICK`
- `BOOKING_RATE_ID_BACHBLICK`

Danach zuerst einen einzelnen Testtag für Gartenblick Zimmer synchronisieren und den Verkaufspreis im Booking-Extranet gegenprüfen.

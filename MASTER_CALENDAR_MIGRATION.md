# Zuhause am Bach OS – Master-Kalender

## Ziel

Die lokale ZAB-Datenbank ist die betriebliche Quelle für Direktbuchungen und eigene Sperren. Booking.com bleibt zunächst als externer Verkaufskanal angebunden und wird über iCal eingelesen. Gleichzeitig stellt das OS pro Zimmer einen eigenen anonymisierten iCal-Feed bereit, den Booking.com importieren kann.

Damit wird die Datenrichtung schrittweise umgedreht:

1. Direktbuchung / OS-Sperre entsteht im Zuhause-am-Bach-OS.
2. Das OS blockiert den Zeitraum sofort lokal.
3. Der Booking-Feed des OS veröffentlicht nur den Zeitraum – keine Gastdaten.
4. Booking.com importiert diesen Feed und schließt den Zeitraum dort.
5. Neue Booking.com-Reservierungen werden weiterhin als externe Belegung eingelesen, solange Booking als Verkaufskanal offen ist.

## Sicherheitsprinzip

Der Rollout startet absichtlich im `hybrid`-Modus. In diesem Modus bleiben die vorhandenen Booking/iCal-Sicherheitsprüfungen beim PayPal-Checkout aktiv. Das verhindert, dass die neue Kanalsteuerung während der Migration versehentlich Doppelbuchungen erzeugt.

Railway-Variable:

```text
ZAB_MASTER_CALENDAR_MODE=hybrid
```

`master` ist als nächster Migrationsschritt vorgesehen. Er darf erst produktiv verwendet werden, wenn die Booking-Feeds pro Zimmer im Extranet importiert und die Rücksynchronisation einer Testbuchung geprüft wurde.

## Neue OS-Seite

Nach Deployment:

```text
/os/calendar
```

Dort können pro Zimmer:

- Direktbuchungen geöffnet/geschlossen werden,
- Booking.com geöffnet/geschlossen werden,
- globale Sperren gesetzt werden,
- nur für einen Kanal geltende Sperren gesetzt werden,
- Booking/iCal manuell synchronisiert werden,
- die anonymisierten ZAB-iCal-Feeds kopiert werden.

## Booking.com Feed

Für jedes Zimmer erzeugt das OS einen URL-geschützten Feed:

```text
/calendar/channel/booking/<Zimmer>.ics?token=<zufälliger Token>
```

Der Feed enthält nur:

- Anreise-/Abreisedatum der belegten Zeiträume,
- generische Belegungsbezeichnungen,
- technische UIDs.

Nicht enthalten sind Gastname, E-Mail, Telefonnummer, Preis oder Zahlungsinformationen.

## Reihenfolge für die Produktivumstellung

1. Branch/PR deployen und `/health/master-calendar` prüfen.
2. `/os/calendar` öffnen.
3. Booking-Feed für **Bachblick** kopieren.
4. Diesen Feed im Booking.com-Extranet als Kalenderimport für Bachblick hinzufügen.
5. Eine Test-Sperre im OS setzen und warten, bis Booking.com sie übernimmt.
6. Test-Sperre wieder entfernen und Rücknahme prüfen.
7. Erst danach weitere Zimmer verbinden.
8. Booking-Kanal niemals schließen, bevor bestehende Reservierungen und Extranet-Verfügbarkeiten geprüft wurden.

## Technische Regeln

- Lokale Direktbuchungen werden in `bookings` gespeichert.
- Booking/iCal-Importe bleiben in `external_blocks`.
- OS-eigene Gesamtsperren liegen in `zab_master_blocks`.
- Kanalbezogene Sperren liegen in `zab_channel_blocks`.
- Kanalstatus liegt in `zab_channel_controls`.
- Der Feed-Token wird einmalig in `zab_calendar_meta` erzeugt.
- Das Booking-Exportfeed spiegelt Booking-iCal-Ereignisse **nicht** zurück, damit keine iCal-Schleife entsteht.

## Wichtiger Rollout-Hinweis

Das Verbinden des neuen Feeds mit Booking.com ist ein manueller Extranet-Schritt. Der Code allein ändert noch keine Booking.com-Verfügbarkeit. So bleibt der aktuelle Verkaufskanal während des Tests unverändert und es gibt einen kontrollierten Rückweg.

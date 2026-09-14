# Zuhause am Bach OS – Master-Kalender

## Ziel

Die lokale ZAB-Datenbank ist die betriebliche Quelle für Direktbuchungen, eigene Sperren und die interne Kalendersteuerung. Booking.com bleibt zunächst als externer Verkaufskanal angebunden und wird über iCal eingelesen. Gleichzeitig stellt das OS pro Zimmer einen eigenen anonymisierten iCal-Feed bereit, den Booking.com importieren kann.

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

## OS-Seite

Nach Deployment:

```text
/os/calendar
```

Dort können pro Zimmer:

- Direktbuchungen global geöffnet/geschlossen werden,
- Booking.com global geöffnet/geschlossen werden,
- einzelne Tage oder Zeiträume für einen Kanal geöffnet/geschlossen werden,
- Direktpreise pro Tag/Zeitraum gesetzt werden,
- Booking-Sollpreise pro Tag/Zeitraum gespeichert werden,
- globale Sperren gesetzt werden,
- nur für einen Kanal geltende Sperren gesetzt werden,
- Booking/iCal manuell synchronisiert werden,
- die anonymisierten ZAB-iCal-Feeds kopiert werden.

Der Monatskalender zeigt intern außerdem:

- Direktbuchungen mit Gastname,
- Land/Nationalität aus dem Gästeprofil,
- Booking.com-Belegungen,
- optional manuell ergänzten Booking-Gastnamen, Land/Nationalität, Personenzahl und Referenz,
- Direktpreis und Booking-Sollpreis je Tag,
- den Öffnungs-/Schließstatus beider Kanäle.

## Preise

### Direktbuchung

Ein im OS-Kalender gesetzter Direkt-Tagespreis wird für Bachblick in den öffentlichen Preis-API-Antworten und im PayPal-Checkout als finaler Direktpreis verwendet. Ohne OS-Override greift der bestehende dynamische Direktpreiskalender.

### Booking.com

Der Booking-Sollpreis wird im OS gespeichert und angezeigt, **aber nicht über iCal an Booking.com übertragen**. iCal kann Verfügbarkeit/Belegung, aber keine Preise übertragen. Bis eine echte Booking-Connectivity-/Channel-Manager-Schnittstelle angebunden ist, muss der Booking-Preis im Extranet manuell gesetzt werden.

## Booking.com Feed

Für jedes Zimmer erzeugt das OS einen URL-geschützten Feed:

```text
/calendar/channel/booking/<Zimmer>.ics?token=<zufälliger Token>
```

Der Feed enthält nur:

- Anreise-/Abreisedatum der belegten Zeiträume,
- generische Belegungsbezeichnungen,
- technische UIDs,
- kanalbezogene Sperrzeiträume.

Nicht enthalten sind Gastname, Nationalität/Land, E-Mail, Telefonnummer, Preis oder Zahlungsinformationen.

Tagesbezogene Öffnungs-/Schließ-Overrides werden für den Feed zu zusammenhängenden Sperrintervallen verdichtet. Booking/iCal-Ereignisse werden im Booking-Exportfeed nicht zurückgespiegelt, damit keine Synchronisationsschleife entsteht.

## Gastname und Nationalität

Direktbuchungen lesen den Namen aus `bookings` und das Land aus `guest_profiles.country`.

Booking.com-iCal liefert Gastname und Nationalität nicht zuverlässig. Deshalb können diese Daten im internen OS-Kalender manuell zur konkreten externen Belegung ergänzt werden. Sie werden in `zab_external_guest_meta` gespeichert und niemals in den öffentlichen iCal-Feed geschrieben.

## Reihenfolge für die Produktivumstellung

1. Branch/PR deployen und `/health/master-calendar` prüfen.
2. `/os/calendar` öffnen und Monatsansicht prüfen.
3. Einen Direkt-Tagespreis testweise setzen und `/api/direct-price` kontrollieren.
4. Booking-Feed für **Bachblick** kopieren.
5. Diesen Feed im Booking.com-Extranet als Kalenderimport für Bachblick hinzufügen.
6. Eine Test-Sperre im OS setzen und warten, bis Booking.com sie übernimmt.
7. Test-Sperre wieder entfernen und Rücknahme prüfen.
8. Erst danach weitere Zimmer verbinden.
9. Booking-Kanal niemals schließen, bevor bestehende Reservierungen und Extranet-Verfügbarkeiten geprüft wurden.

## Technische Regeln

- Lokale Direktbuchungen werden in `bookings` gespeichert.
- Booking/iCal-Importe bleiben in `external_blocks`.
- OS-eigene Gesamtsperren liegen in `zab_master_blocks`.
- Kanalbezogene Bereichssperren liegen in `zab_channel_blocks`.
- Tagesbezogene Kanal- und Preiseinstellungen liegen in `zab_channel_day_settings`.
- Ergänzte Metadaten externer Gäste liegen in `zab_external_guest_meta`.
- Kanalstatus liegt in `zab_channel_controls`.
- Der Feed-Token wird einmalig in `zab_calendar_meta` erzeugt.
- Der Booking-Exportfeed spiegelt Booking-iCal-Ereignisse **nicht** zurück.

## Wichtiger Rollout-Hinweis

Das Verbinden des neuen Feeds mit Booking.com ist ein manueller Extranet-Schritt. Der Code allein ändert noch keine Booking.com-Verfügbarkeit. So bleibt der aktuelle Verkaufskanal während des Tests unverändert und es gibt einen kontrollierten Rückweg.

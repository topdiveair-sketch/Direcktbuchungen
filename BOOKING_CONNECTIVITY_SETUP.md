# Booking.com Connectivity für Zuhause am Bach OS

Ziel: Das lokale Windows **Zuhause am Bach OS** steuert den Kalender. Für das interne Zimmer `Bachblick` zeigt die Windows-Oberfläche den Namen **Gartenblick Zimmer**.

## Was die Verbindung macht

Nach vollständiger Booking.com-Connectivity-Konfiguration kann das OS:

- einen im Windows-Kalender gesetzten **Booking.com Preis pro Nacht** direkt über die Booking.com Rates & Availability API senden;
- den von Booking.com bestätigten oder abgelehnten Synchronisationsstatus pro Tag im OS anzeigen;
- künftige Booking.com Reservierungen privat anreichern: Gastname, Booking-Referenz, Personenzahl, Booking-Land/Wohnsitzland und – soweit aus dem Reservierungsdatensatz eindeutig ableitbar – Frühstück enthalten/nicht enthalten;
- diese Gastdaten ausschließlich intern halten. Öffentliche und Channel-iCal-Feeds enthalten keine PII.

Airbnb und andere iCal-Kanäle liefern in dieser Stufe nur Verfügbarkeit/Belegung. Deren Preise bleiben OS-Zielpreise, bis eine jeweilige offizielle Preis-API angebunden ist.

## Booking.com Voraussetzungen

Die Preisübertragung läuft **nicht über iCal**. Booking.com verlangt einen Connectivity Machine Account mit API-Token-Authentifizierung. Die Rate-API benötigt zusätzlich die echte Booking.com Room-Type-ID und die Rate-Plan-ID.

Offizielle Endpunkte, die diese Implementierung verwendet:

- Token: `POST https://connectivity-authentication.booking.com/token-based-authentication/exchange`
- Preise: `POST https://supply-xml.booking.com/hotels/ota/OTA_HotelRateAmountNotif`
- Reservierungen: `POST https://secure-supply-xml.booking.com/hotels/xml/reservations`
- Reservierungsübersicht: `POST https://secure-supply-xml.booking.com/hotels/xml/reservationssummary`

Booking.com Connectivity Dokumentation:

- https://developers.booking.com/connectivity/docs/token-based-authentication
- https://developers.booking.com/connectivity/docs/ota-rateamountnotif
- https://developers.booking.com/connectivity/docs/reservations-api/managing-reservations-bxml
- https://developers.booking.com/connectivity/docs/b_xml-reservationssummary

## Railway Variablen

Die Werte gehören nur in Railway `Variables`, niemals als echte Secrets ins Repository.

```text
BOOKING_CONNECTIVITY_CLIENT_ID=...
BOOKING_CONNECTIVITY_CLIENT_SECRET=...
BOOKING_HOTEL_ID=10657485
BOOKING_ROOM_ID_BACHBLICK=<Booking Room-Type-ID Gartenblick>
BOOKING_RATE_ID_BACHBLICK=<Booking Rate-Plan-ID Gartenblick>
BOOKING_RATE_AMOUNT_MODE=after_tax
BOOKING_AUTO_SYNC_GUESTS=1
```

Für spätere Zimmer gilt dasselbe Namensschema:

```text
BOOKING_ROOM_ID_MARILLENZIMMER=...
BOOKING_RATE_ID_MARILLENZIMMER=...
BOOKING_ROOM_ID_WEINBERGZIMMER=...
BOOKING_RATE_ID_WEINBERGZIMMER=...
BOOKING_ROOM_ID_DONAUZIMMER=...
BOOKING_RATE_ID_DONAUZIMMER=...
```

`BOOKING_RATE_AMOUNT_MODE` muss zur Booking.com Steuerkonfiguration passen:

- `after_tax`: Preis inklusive Steuern;
- `before_tax`: Preis vor Steuern.

## Sichere Aktivierungsreihenfolge

1. `ZAB_MASTER_CALENDAR_MODE=hybrid` beibehalten.
2. Booking.com iCal für Gartenblick weiter eingehend synchronisieren.
3. Booking Connectivity Machine Account erstellen/zuordnen und Client ID/Secret in Railway setzen.
4. Echte Room-Type-ID und Rate-Plan-ID des Gartenblick Zimmers in Railway setzen.
5. `/health/booking-connectivity` prüfen: Adapter vorhanden und `configured=true` für `Bachblick`.
6. Im Windows Zuhause-am-Bach OS einen einzelnen zukünftigen Testtag auswählen, Booking-Preis setzen und speichern.
7. Im Kalender muss bei **Booking-Sync** `synced` / „Booking.com Preis bestätigt“ erscheinen. Zusätzlich Preis im Booking.com Extranet kontrollieren.
8. Erst danach einen Zeitraum testen.
9. Booking-Gäste über „Booking-Gäste jetzt synchronisieren“ prüfen. Das Feld „Land / Herkunft“ ist das von Booking.com gelieferte Land/Wohnsitzland und keine amtlich geprüfte Staatsangehörigkeit.
10. Website-Masterkalender prüfen. Er wird nach der Migration aus dem anonymen OS-Feed `/calendar/public/Bachblick.ics` gespeist.
11. Erst wenn alle Rückwege sicher sind, optional `ZAB_MASTER_CALENDAR_MODE=master` setzen.
12. `ZAB_MASTER_PAYPAL_INDEPENDENT=1` erst nach erfolgreicher Master-Migration setzen. Im Hybridmodus bleibt die bisherige Booking-iCal-Sicherheitsprüfung für PayPal erhalten.

## Fehlerverhalten

Wenn Booking-Zugang oder Zimmer-/Rate-Mapping fehlen, wird der Preis nur lokal im OS gespeichert. Der Synchronisationsstatus lautet `not_configured`. Das System meldet **nicht** fälschlich, dass Booking.com geändert wurde.

Wenn Booking.com einen Rate-Request ablehnt, speichert das OS den Fehler pro Tag in `zab_booking_rate_sync` und zeigt ihn in der Windows-Spalte **Booking-Sync** an. Der lokale Sollpreis bleibt erhalten und kann mit „Booking-Preise dieses Zeitraums erneut senden“ erneut übertragen werden.

## Datenschutz

Gastname, Land/Herkunft, Personen, Frühstück, Anreiseart und interne Notizen werden nicht in den öffentlichen oder Channel-iCal-Feeds ausgegeben. Die Booking-Reservierungsanreicherung wird nur über die authentifizierte Windows-Central-API ausgelöst. Kreditkartendaten werden von der ZAB-Anreicherung nicht gespeichert oder verarbeitet.

# Gemeinsame Zimmerpreise für Zuhause am Bach OS v112.11

Der im OS eingetragene Direkt-Tagespreis ist die Basis vor Nachfrage-,
Auslastungs- und Spätbuchungsaufschlägen. Ohne Tagespreis gilt die konfigurierte
Preistabelle. Nach einem Speichern unter /admin/prices hat die dort eingegebene
Standard-/Wochenend-/Hochsaison-Tabelle Vorrang vor der JSON-Saisontabelle.
Ein expliziter Tagespreis hat weiterhin Vorrang vor dieser Tabelle.

Homepage, Buchungsanfragen und PayPal verwenden dieselbe Berechnung. Für Bachblick
bleibt die bestehende Nachfrage-Untergrenze von 99 EUR erhalten. Der effektive
Zimmerpreis ist pro Nacht auf 149 EUR begrenzt. Optionale Extras bleiben separat.

Der Portal-Sollpreis ist der effektive Direkt-Zimmerpreis mal 1,05, kaufmännisch
auf Cent gerundet und ebenfalls maximal 149 EUR. Beispiel: 100 EUR Basis plus
5 Prozent Nachfrage ergibt 105 EUR direkt und 110,25 EUR auf den Portalen.
Bei 149 EUR direkt beträgt auch der Portalpreis maximal 149 EUR.

## Übertragung

Neue OS-Preisänderungen markieren betroffene Tage zur automatischen Übertragung.
Änderungen der allgemeinen Preistabelle markieren heute bis einschließlich heute
plus 370 Tage. Bereits bestehende Preise werden beim Start nicht ungeprüft an
externe Anbieter gesendet. Markierte Tage werden jede Minute neu berechnet;
pro Durchlauf werden höchstens fünf fällige Preisübertragungen versucht.

Die SQLite-Warteschlange liegt in derselben persistenten Datenbank wie das OS.
Sie unterscheidet vorgemerkt, bestätigt, fehlende Konfiguration und Wiederholung.
Nach Fehlern erfolgt ein begrenzter exponentieller Abstand zwischen Versuchen.
Nur bestätigte Änderungen gelten als übertragen. Eine während der Übertragung
neu gespeicherte Preisänderung kann nicht durch die alte Bestätigung überschrieben
werden. Belegungen, Sperren, iCal-Snapshots und Zahlungen werden nicht verändert.

Das OS-Master-Kalender-Dashboard zeigt Konfiguration und Übertragungsstatus.
/health/channel-pricing liefert ausschließlich Konfigurations-Bools und die
Preisregel. /os/channel-pricing/status erfordert eine Admin-Anmeldung.

## Beds24 V2 einrichten

In Railway als geheime Variable setzen, niemals ins Repository einchecken:

- BEDS24_REFRESH_TOKEN: Beds24-V2-Refresh-Token mit Schreibberechtigung für Inventory.
- BEDS24_ROOM_ID_BACHBLICK: zugehörige numerische Beds24-Zimmer-ID.
- BEDS24_PORTAL_PRICE_SLOT_BACHBLICK: explizit zugeordnete tägliche Preiszeile 1–16.
  Diese Preiszeile muss den gewünschten Portal-Tarifen für zwei Personen zugeordnet
  sein. Keine zusätzliche 5-Prozent-Verknüpfung einstellen, da der gesendete Preis
  den Aufschlag bereits enthält. Eine separate Direktpreiszeile bleibt unverändert.
- BEDS24_MANAGES_BOOKING=1, wenn Beds24 auch Booking verwaltet. In diesem Fall
  wird Booking nicht parallel über den Connectivity-Adapter beschrieben.

Die API schreibt ausschließlich die zugeordnete tägliche Preiszeile über
POST /inventory/rooms/calendar; keine Anzahl verfügbarer Zimmer, Buchungen,
Sperren, Mindestaufenthalte oder Kanalverbindungen.

Alternativ benötigt der vorhandene Booking-Connectivity-Adapter
BOOKING_CONNECTIVITY_CLIENT_ID, BOOKING_CONNECTIVITY_CLIENT_SECRET,
BOOKING_HOTEL_ID, BOOKING_ROOM_ID_BACHBLICK und BOOKING_RATE_ID_BACHBLICK.
Die tatsächlich vom Adapter verwendeten Zuordnungsnamen stehen in
booking_connectivity.py::_room_mapping.

Einrichten und am Provider nachprüfen, bevor eine externe Übertragung als live
funktionierend bezeichnet wird. Eine API-Bestätigung belegt die Annahme beim
Provider, nicht den bereits sichtbaren Verkaufspreis auf jedem Portal.
Booking-Genius, Mobil-, Mitglieds- und andere aktive Aktionsrabatte sowie
Steuern und Gebühren werden durch einen Basistarif-Push nicht ausgeschaltet.

Offizielle Beds24-Referenzen:
https://beds24.com/api/v2/apiV2.yaml
https://wiki.beds24.com/index.php/PMSs:_How_to_connect_to_Beds24_and_use_Airbnb_via_API_V2

## Regressionen

python -m unittest -q test_channel_pricing.py test_price_cap.py test_calendar_concurrency.py test_calendar_db.py test_calendar_sync.py test_daily_report.py test_booking_connectivity.py

# WachauEtappe Zentrale

Windows-Betreiberprogramm fuer die Saison 2027.

## Ziel
Eine zentrale Betreiberoberflaeche fuer:
- Dashboard
- Reisen und mehrtaegige Touren
- Gastgeber und Freigaben
- Verfuegbarkeiten
- Routen und Etappen
- Gepaecktransporte
- Stornos
- Kandidaten/Partnergewinnung

## Architektur
- Windows Desktop: .NET + WPF
- Lokaler Offline-Cache: SQLite
- Zentrale Plattformdaten spaeter: separate API + PostgreSQL
- Bestehende Zuhause-am-Bach-Direktbuchung bleibt getrennt.

## Kontrollprinzipien
- Nur Betreiber kann Gastgeber verifizieren, veroeffentlichen oder sperren.
- Gastgeber sehen und bearbeiten spaeter nur ihre eigenen Daten.
- Unterkunftszahlung erfolgt direkt beim Gastgeber; die Plattform haelt keine Unterkunftsgelder.
- Keine Speicherung roher Kreditkartendaten.
- Jede Reise erhaelt eine eindeutige WachauEtappe-Referenz.
- Aenderungen an Buchung, Gastgeberstatus und Storno werden spaeter revisionsfaehig protokolliert.

## Hauptnavigation
1. Dashboard
2. Reisen
3. Gastgeber
4. Verfuegbarkeit
5. Routenplaner
6. Gepaeck
7. Stornos
8. Kandidaten
9. Einstellungen

## Datenmodell (erste Version)
- Host
- Room
- Availability
- Trip
- TripDay
- Booking
- Route
- RouteSegment
- LuggageTransfer
- CancellationPolicy
- Candidate
- AuditEvent

## Entwicklungsreihenfolge
1. Windows-Shell und Navigation
2. Lokales Datenmodell/SQLite
3. Import der bestehenden JSON-Daten
4. Dashboard und Gastgeberverwaltung
5. Reisen und Etappen
6. Gepaeck- und Stornoworkflow
7. Separate zentrale API/PostgreSQL
8. Synchronisation und Gastgeberzugang

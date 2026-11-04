# ZAB OS – Windows-Kalendervergleich

## Status und Zweck
Eigenstaendiges, lesendes Windows-Hilfsprogramm, **nicht** das vollstaendige ZAB OS V113.0. Keine Buchungen, Preise, Sperren oder Verfuegbarkeiten werden geschrieben. Ein fehlender Eintrag beweist **keine** freie Nacht. Die Quellen-Synchronisierung ist nicht verifiziert.

## Windows-EXE herunterladen
1. GitHub-Repository `topdiveair-sketch/Direcktbuchungen` > Actions > **ZAB OS calendar Windows EXE** oeffnen.
2. Den letzten **erfolgreichen** Lauf auf Branch `feature/zab-os-production-integration-20261013` auswaehlen.
3. Unter **Artifacts** das Archiv **ZAB-Kalendervergleich-Windows** herunterladen und entpacken.
4. `ZAB-Kalendervergleich.exe` lokal starten. Es wird kein Python benoetigt. Windows-SmartScreen gegebenenfalls sorgfaeltig pruefen; die EXE ist nicht codesigniert.
5. Das Artefakt laeuft nach 14 Tagen ab; dann einen neuen Build ueber GitHub Actions starten.

## Offline-Vergleich
Zwei unabhaengig erzeugte JSON-Dateien mit unterschiedlichen `source_id`-Werten laden. Beide Dateien muessen `bookings` und `blocks` als Listen enthalten. Ein `source_id` allein belegt die Herkunft nicht: Dateien und Quellensysteme muessen vor der Verwendung tatsaechlich unabhaengig geprueft werden. Zeitraum eingeben; Enddatum ist exklusiv. **Kalender sicher vergleichen** zeigt nur Abweichungen und Ueberschneidungen.

## Geschuetzter Live-Snapshot (noch nicht produktiv freigeschaltet)
Die Schaltflaeche **ZAB-Snapshot abrufen (nur lesen)** nutzt die Windows-Umgebungsvariablen `ZAB_OS_SNAPSHOT_URL` (HTTPS-Basisadresse) und `ZAB_BRIDGE_TOKEN` (separater Zugriffsschluessel). Token **niemals** in Screenshots, Protokolle, GitHub oder Chat kopieren. Server muss die API `/internal/os/v1/snapshot` aktiviert haben. Auf der produktiven Homepage ist diese Integration **noch nicht ausgerollt**. Die Funktion kann bis dahin nicht produktiv genutzt werden. Ein Abruf legt eine neue JSON-Datei an; vorhandene Dateien werden nicht ueberschrieben.

## Produktionsfreigabe
Erst nach gesichertem Backup und erfolgreichem Restore-Test, Schema-Pruefung, sicherer Token-Konfiguration, getrennten Tests von Booking.com, Airbnb, Beds24 und Direktbuchung sowie dokumentiertem Rollback. Der PR #74 bleibt bis dahin Entwurf. Keine automatische Freigabe vermeintlich freier Naechte.

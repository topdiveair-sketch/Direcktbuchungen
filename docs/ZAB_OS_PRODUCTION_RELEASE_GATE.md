# ZAB OS V113 – Produktivfreigabe (Stand 2026-10-13)

**Status: NICHT FREIGEGEBEN.** Dieses Dokument ist eine Prüfliste, keine Deployment-Anweisung.

## Verifizierter Ist-Stand
- Produktivservice `homepage-preview`: Railway SUCCESS, Quellbranch `fix/booking-section-order`, persistentes Volume `/data`.
- Produktivservice hat **keine** Variable `ZAB_BRIDGE_TOKEN`. Die neue Snapshot-Route ist im Produktivbranch noch nicht enthalten.
- Stagingservice `zab-os-staging`: Railway SUCCESS, Quellbranch `feature/zab-os-snapshot-v38-20261013`, kein persistentes Volume, eigene Testdaten.
- Integrations-PR #74: `feature/zab-os-production-integration-20261013`, nur lesende Schnittstelle und Tests; nicht gemergt.
- Staging-Testergebnis mit null Buchungen/Sperren ist **keine** Aussage über echte Verfügbarkeit.
- Snapshot meldet `sync.verified=false`; die Clientauswertung gibt niemals Nächte automatisch frei.

## Freigabegates
- [x] Automatisierte Flask-/Client-/Sicherheitsprüfungen für Commit `2ae0eae` bestanden.
- [x] Produktivservice und Stagingservice anhand der Railway-Konfiguration getrennt geprüft.
- [ ] Integrationsbranch nach allen Änderungen vollständig getestet.
- [ ] Produktionsdatenbank vor Deployment gesichert; Wiederherstellung getestet.
- [ ] Datenmodell und SQL-Queries gegen produktive DB-Schemaversion geprüft.
- [ ] Alle Datenquellen (Direktbuchung, Booking.com, Airbnb, Beds24, zentrale Sperren) anhand unabhängiger Belegungsnachweise verglichen.
- [ ] Abweichungen bei Anreise/Abreise, Storno, Pending, Sperren und Doppelbuchungen protokolliert und geklärt.
- [ ] Sicheren Bridge-Token als neue Railway-Variable für Produktivservice setzen, **nicht** im Repository oder Chat speichern; bestehende `OS_SYNC_TOKEN`-Funktion nicht umwidmen.
- [ ] Rollout und Rollback in Wartungsfenster planen; nach Rollout nur GET-Tests mit autorisiertem Client durchführen.
- [ ] Belegen, dass Preise, Reservierungen und externe Kanäle unverändert geblieben sind.

## Sicherer Live-Smoketest nach expliziter Freigabe
1. Authentifizierten GET `/internal/os/v1/snapshot?start=YYYY-MM-DD&end=YYYY-MM-DD` ausführen; niemals schreibende Endpunkte.
2. `room_id=Bachblick` (technische Altkennung, einziges Gartenzimmer) prüfen.
3. Buchungen, externe Sperren und zentrale Sperren gegen **unabhängige** Originalquellen vergleichen.
4. `sync.verified=false` als Warnung anzeigen; fehlende Belegung nie als buchbar markieren.
5. Bei Fehlern keine Kalenderänderung, keinen Preis-Push, keine Freigabe; Rückfall auf bestehenden Produktivbranch.

## Aktuelle Einschränkungen
- Der Snapshot enthält direkte Buchungen, `external_blocks` und zentrale Sperren. Er beweist nicht, dass OTA-Imports vollständig oder aktuell sind.
- Der Client ist ein eigenständiges Python-Modul, noch keine vollständige Windows-Installer-Integration.
- Ein Vergleich zweier Kopien derselben Datenquelle ist kein unabhängiger Kanalabgleich.

# ZAB OS – Production hardening

Stand: 2026-09-14

## Ziel

Das lokale Windows-Zuhause-am-Bach-OS wird die operative Schaltzentrale. Railway bleibt der dauerhaft erreichbare Transaktions- und Synchronisationsknoten.

## Bereits aktiv bzw. auf diesem PR vorbereitet

- ZAB-Masterkalender und Kanalsteuerung
- öffentlicher Sicherheitskalender aus ZAB-Master + Booking-iCal
- Direct-Price API mit Fail-Closed-Logik
- ZAB Control Center V3 mit `direct`, `booking`, `airbnb`, `other`
- private Gastmetadaten, Frühstück, Personenzahl und Anreiseart
- Booking-Connectivity-Adapter (nur aktiv, wenn echte Zugangsdaten + Room/Rate Mapping vorhanden sind)
- gehärtete SQLite-Verbindungen mit 30 s Busy-Timeout, Foreign Keys und WAL-Anforderung
- geschützter CENTRAL-Datenbankexport mit SHA-256 und `PRAGMA integrity_check`
- Storage-Healthcheck mit separater Anzeige von Adapterstatus, echter Booking-Verbindung und persistenter Speicherung
- ein einmaliger, verifizierter Restore-Pfad für die Volume-Migration
- anonymer Booking-Safety-Mirror als Fail-Closed-Wiederherstellung bekannter Sperren, wenn in einer frischen DB noch kein echter Booking-iCal konfiguriert ist

## Kritischer Produktionsblocker

Der Railway-Service verwendet aktuell SQLite unter `/app/data/zab.db`, aber ohne persistentes Volume. Ein Deployment/Containerwechsel kann deshalb operative Daten verlieren. Railway übernimmt bestehende Dateien beim Anhängen eines Volumes nicht automatisch.

**Keine Volume-Umstellung und kein Backend-Redeploy durchführen, bevor die aktuelle Live-Datenbank außerhalb des laufenden Containers gesichert wurde.**

## Exakter Zero-Loss-Ablauf

### 1. Laufende Produktionsdatenbank ohne Restart herunterladen

Mit der aktuellen Railway CLI auf einem administrativen Rechner:

```bash
railway service files download /app/data/zab.db ./zab-production-before-volume.db
```

Der Befehl liest nur das Dateisystem des aktuell laufenden Service. Er darf keinen Restart oder Redeploy auslösen.

Prüfen:

```bash
sqlite3 ./zab-production-before-volume.db "PRAGMA integrity_check;"
```

Erwartet:

```text
ok
```

SHA-256 dokumentieren, unter Windows PowerShell:

```powershell
Get-FileHash .\zab-production-before-volume.db -Algorithm SHA256
```

Erst weitergehen, wenn die Datei lokal vorhanden ist und der Integrity-Check `ok` liefert.

### 2. Persistentes Volume bereitstellen

Empfohlener Mount-Pfad: `/app/data`. Damit bleibt der bestehende Standardpfad `/app/data/zab.db` erhalten und es ist keine separate `DATA_DIR`-Migration nötig.

### 3. Gesicherte Produktions-DB zunächst als Importdatei auf das Volume laden

```bash
railway volume files --volume <VOLUME_NAME> upload ./zab-production-before-volume.db /zab-import.db
```

Die Importdatei darf **nicht** direkt blind als `zab.db` überschrieben werden. Der Startcode übernimmt die verifizierte Transaktion.

### 4. Einmaligen Restore konfigurieren

Für den ersten Start mit Volume:

```text
ZAB_RESTORE_ON_BOOT=1
ZAB_RESTORE_FROM_PATH=/app/data/zab-import.db
REQUIRE_PERSISTENT_STORAGE=1
```

`production_hardening.py` prüft vor dem Austausch:

- `PRAGMA integrity_check`
- Kerntabellen `bookings`, `external_blocks`, `ical_settings`
- Dateigröße
- SHA-256
- Belegungs-/Buchungszähler

Vor dem Austausch wird auf dem Volume zusätzlich eine `zab.before-restore-*.db` erzeugt. Nach erfolgreichem Restore wird die Importdatei in `zab-import.applied-<Zeit>-<SHA>.db` umbenannt. Dadurch kann ein späteres Deployment die alte Sicherung nicht erneut einspielen.

### 5. Nach erstem erfolgreichen Start prüfen

Pflichtchecks:

```text
/health/zab-storage
/health/wachauetappe_production
```

Zusätzlich im Windows-OS:

- Gartenblick Zimmer zeigt alle bekannten Booking-Belegungen als belegt
- Direktbuchung lehnt diese Zeiträume ab
- Tagespreise/Kanalschalter sind vorhanden
- vorhandene Direktbuchungen und Gästedaten sind erhalten

Erst wenn diese Prüfung grün ist:

```text
ZAB_RESTORE_ON_BOOT=0
```

Der persistent gespeicherte `zab.db` bleibt danach die operative Datenbank.

## Railway-Redeploy-Schleife

Der Railway-Service beobachtet nur noch Backend-/Template-/Static-Dateien, die einen Server-Redeploy rechtfertigen. Die alle fünf Minuten aktualisierten Root-Dateien `booking-calendar.json` und `index.html` sollen keinen Railway-Redeploy mehr auslösen. Damit wird die frühere Kette „Kalender-Commit → Railway-Build → weiterer Kalender-Commit“ unterbrochen.

## Booking-Sicherheit

Bis Booking Connectivity vollständig konfiguriert und getestet ist:

- `ZAB_MASTER_CALENDAR_MODE=hybrid`
- `ZAB_MASTER_PAYPAL_INDEPENDENT=0`
- Booking-iCal bzw. der anonyme Booking-Sicherheits-Snapshot bleibt zusätzliche Belegungssicherung.

Der öffentliche Snapshot darf ausschließlich bekannte Belegungen/Sperren wiederherstellen. Er ist **nie** Beweis dafür, dass ein Termin frei ist.

## Windows OS

Windows V112.2.17 nutzt die V3-API `/api/central/zab-calendar` und sendet Änderungen nicht mehr still ins Leere, wenn bereits ein Hintergrundvorgang läuft. Railway-Verbindungen müssen HTTPS verwenden; HTTP ist nur für localhost-Entwicklung zulässig.

## Noch vor Produktivfreigabe Booking-Preis

Benötigt werden mindestens:

- `BOOKING_CONNECTIVITY_CLIENT_ID`
- `BOOKING_CONNECTIVITY_CLIENT_SECRET`
- `BOOKING_ROOM_ID_BACHBLICK`
- `BOOKING_RATE_ID_BACHBLICK`

Danach zuerst einen einzelnen Testtag für **Gartenblick Zimmer** synchronisieren und den tatsächlichen Verkaufspreis im Booking-Extranet gegenprüfen.

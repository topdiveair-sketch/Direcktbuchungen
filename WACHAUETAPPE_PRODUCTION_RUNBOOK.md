# WachauEtappe Produktions-Runbook

## Launch-Gate

Ein Release gilt technisch als freigegeben, wenn:

1. GitHub CI erfolgreich ist:
   - WachauEtappe 2.0 CI
   - Backend smoke test
   - WachauEtappe Windows Build
   - WachauEtappe Production Smoke
2. Railway-Deployment des Services `cooperative-adaptation / web / production` erfolgreich ist.
3. `/health/wachauetappe_production` HTTP 200 liefert.
4. `/health/wachauetappe-bookings` HTTP 200 liefert.
5. `/health/wachauetappe_market_ready` HTTP 200 liefert.
6. Windows-Zentrale kann sich mit dem verschlüsselt gespeicherten ADMIN_PASSWORD verbinden.
7. Ein Testdurchlauf wurde vollständig durchgeführt:
   Gast plant Reise → mehrere Nächte → Anfrage → Gastgeber bestätigt/ablehnt → Ersatzbedarf → Meine Reise → Live Operations.

## Kritische Konfiguration

Im produktiven Railway-Service müssen vorhanden sein:
- ADMIN_PASSWORD
- SECRET_KEY
- SMTP_HOST
- SMTP_PORT
- SMTP_USER
- SMTP_PASSWORD
- SMTP_SENDER

Zugangsdaten dürfen nicht in GitHub, Dokumentation oder Screenshots eingecheckt werden.

## Tägliche Betriebsroutine

In WachauEtappe Zentrale → Live Operations zuerst den Tab **Heute** öffnen.

Priorität:
1. Anfragen >12 Stunden beantworten.
2. Reisen mit Ersatzbedarf bearbeiten.
3. Neue Partner-Leads kontaktieren.
4. Heute anreisende bestätigte Aufenthalte prüfen.
5. Freie Zimmer der nächsten Tage kontrollieren.

## Buchungsprinzip

WachauEtappe vermittelt. Beherbergungsvertrag und Unterkunftszahlung bleiben direkt zwischen Gast und Gastgeber. Rechnerische Provisionen im Dashboard sind keine automatische Forderung und keine automatische Zahlungsbuchung.

## Rollback

Bei einem kritischen Produktionsfehler:
1. Railway → cooperative-adaptation → web → Deployments.
2. Letztes erfolgreiches Deployment vor dem fehlerhaften Release auswählen.
3. Rollback/Redeploy dieses Snapshots ausführen.
4. Danach Healthchecks erneut prüfen.
5. Fehler auf separatem Branch beheben und erst nach grüner CI erneut ausrollen.

## Windows-Release

Der Windows-Build erzeugt:
- portable x64-Version
- WachauEtappe-Zentrale-Setup.exe

Neue Installerversionen müssen den vollständigen WPF-Build und die Installer-Erstellung in GitHub Actions erfolgreich abschließen.

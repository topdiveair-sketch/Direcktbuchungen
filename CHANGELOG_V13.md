# Zuhause am Bach OS – Version 13.0

## Zweck dieser Version

Version 13.0 ist die neue zentrale Hauptversion. Sie fasst den bisher geprüften Entwicklungsstand in einem einzigen Arbeitsstand zusammen.

## Enthaltene Hauptbereiche

- Direktbuchung und Live-Verfügbarkeit
- Booking-iCal-Import und -Export
- Preismanager, Saisonen, Rabatte und Zusatzleistungen
- Gastgeber-Assistent und Heute-Ansicht
- Smart Host und Autopilot
- Gloria: Reinigung, Frühstück, Wäsche, Inventar und Wartung
- Fidel: Wander-, Rad- und Ausflugswissen
- Pia: Kinder- und Familieninhalte
- Gästeportal und Online-Check-in
- Rechnungen, CSV-Exporte und Backups
- Wissensverwaltung, Medienbibliothek und Dokumentvorlagen
- Qualitätszentrum, Einrichtungsassistent und Rollenverwaltung

## Entwicklungsregel ab V13

- Nur noch eine aktuelle Hauptversion
- Neue Module werden in V13 integriert
- Vor jeder Erweiterung wird ein Wiederherstellungspunkt erstellt
- Jede Auslieferung erhält einen Funktionstest und ein Änderungsprotokoll

## V13.1 – Railway Ready
- Persistenter Datenpfad über `DATA_DIR`
- Railway-Konfiguration und Gunicorn-Produktionsstart
- Healthcheck-Konfiguration
- sichere Cookie-Grundeinstellungen
- PayPal-E-Mail über Umgebungsvariable
- `.env.example` und `.gitignore`
- Betriebsdaten, Backups und personenbezogene Daten aus dem Verteilungspaket entfernt
- Debug-Modus standardmäßig deaktiviert

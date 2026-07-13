
# Zuhause am Bach – Direktbuchung Pro

Professionelle Direktbuchungssoftware mit dem originalen Luftbild von Aggsbach Markt.

## Enthalten

- Original-Luftbild als Titelbild
- responsive Darstellung für Desktop, Tablet und Handy
- Live-Verfügbarkeitskalender
- Booking.com-iCal-Import pro Zimmer
- eigener iCal-Export pro Zimmer
- Sperre belegter Tage
- Direktbuchungen mit Preisberechnung
- Frühstück 12 € pro Person und Nacht
- PayPal-Zahlungswahl an topdiveair@gmail.com
- Banküberweisung und Zahlung vor Ort
- Zimmerbilder im Adminbereich austauschbar
- Google-Bewertung und Bewertungsanzahl im Adminbereich editierbar
- Gäste-App mit funktionierendem QR-Code
- Adminbereich
- SQLite-Datenbank
- Zimmerfreigabe:
  - bis einschließlich 15.08.2026 nur Bachblick
  - ab 16.08.2026 alle vier Zimmer

## Start unter Windows

1. Python 3.11 oder neuer installieren.
2. ZIP-Datei entpacken.
3. Eingabeaufforderung im Projektordner öffnen.
4. Ausführen:

```bash
pip install -r requirements.txt
python app.py
```

5. Im Browser öffnen:

```text
http://127.0.0.1:5000
```

## Verwaltung

```text
http://127.0.0.1:5000/admin/login
```

Standardpasswort:

```text
windis2026
```

Für den Livebetrieb über die Umgebungsvariable `ADMIN_PASSWORD` ändern.

## Booking.com-iCal

Im Adminbereich für jedes Zimmer den Booking-iCal-Exportlink eintragen und synchronisieren.

Die eigenen Exportkalender werden im Adminbereich vollständig angezeigt, beispielsweise:

```text
https://IHRE-DOMAIN/calendar/Bachblick.ics
```

Diesen Link anschließend bei Booking.com als externen Kalender importieren.

## Zimmerbilder

Die mitgelieferten Bilder sind Platzhalter auf Basis des Aggsbach-Luftbilds. Im Adminbereich können die echten Zimmerfotos für jedes Zimmer hochgeladen und sofort ersetzt werden.

## Google-Bewertungen

Bewertung, Anzahl und Link werden im Adminbereich gepflegt. Eine echte Live-Anbindung an die Google Places API benötigt zusätzlich einen Google-API-Schlüssel und ein aktiviertes Abrechnungskonto.

## PayPal

PayPal ist als Zahlungsart mit dem Empfänger `topdiveair@gmail.com` integriert. Die Zahlung soll erst nach persönlicher Buchungsbestätigung erfolgen. Ein vollautomatischer Checkout benötigt eine PayPal-Client-ID und Serverintegration.

## Sicherheit und Livebetrieb

Vor Veröffentlichung erforderlich:

- HTTPS
- sicheres Adminpasswort
- Datenschutzerklärung und Impressum
- E-Mail-Versand für Buchungsbestätigungen
- regelmäßige Datenbanksicherung
- Serverhosting mit Python/Flask
- automatischer iCal-Abgleich per Cronjob

iCal kann zeitversetzt synchronisieren. Das Doppelbuchungsrisiko wird stark reduziert, aber nicht vollständig ausgeschlossen.


## Schnellstart unter Windows

1. ZIP-Datei vollständig entpacken.
2. Im entpackten Ordner `STARTEN.bat` doppelklicken.
3. Beim ersten Start werden die benötigten Python-Pakete installiert.
4. Danach öffnet sich die Direktbuchung automatisch im Browser.

Falls Windows eine Sicherheitswarnung zeigt:
- `Weitere Informationen`
- `Trotzdem ausführen`

Falls die Meldung erscheint, dass Python fehlt:
- Python 3 installieren
- bei der Installation unbedingt `Add Python to PATH` auswählen

Zum Beenden:
- Serverfenster schließen oder
- `STOPPEN.bat` doppelklicken


## Version 4 Preismanager
Standard-, Wochenend- und Hochsaisonpreise, Saisonen, Rabatte und Zusatzleistungen sind im Adminbereich verwaltbar.


# Version 5 KOMPLETT

Zusätzlich enthalten:

- automatische Buchungs-E-Mail über konfigurierbares SMTP
- E-Mail an Gast und Betreiber
- persönliche Gästeportal-Links
- Stornierung über sicheren Link
- PDF-Rechnung mit Rechnungsnummer
- Tagesdashboard mit Anreisen, Abreisen, Umsatz und offenen Zahlungen
- Frühstücksliste
- Zimmerstatus und Housekeeping
- Gäste-Bestellungen und spätere Anreise
- CSV-Export der Buchungen
- CSV-Kurtaxenliste
- Datenbank-Backup
- Gutscheincodes
- Windis Concierge mit geprüften, hinterlegten Antworten
- Einstellungen für PayPal.Me
- responsive Handyansicht

## Noch einzutragende externe Zugangsdaten

Diese Dinge können aus Sicherheitsgründen nicht in einer allgemeinen ZIP vorgefüllt werden:

1. SMTP-Server, Benutzername und App-Passwort für den E-Mail-Versand.
2. Öffentliche Domain/HTTPS-Adresse.
3. PayPal.Me-Link oder PayPal-Client-ID für einen vollautomatischen Checkout.
4. Booking.com-iCal-Links pro Zimmer.
5. Echte Google-Bewertungsdaten bzw. API-Zugang.
6. Echte Zimmerbilder.

Die Einstellfelder dafür sind im Adminbereich vorbereitet.


# Version 6 GESAMT

Neu:

- Online-Check-in mit Adresse, Ausweisdaten, Kennzeichen und Ankunftszeit
- Sprachen: Deutsch, Englisch, Tschechisch, Slowakisch
- Wartungs- und Renovierungssperren
- Dokumentenverwaltung pro Buchung
- Gastgeber-Mobilansicht
- Statistiken pro Monat und Zimmer
- vorbereitete Channel-Anschlüsse für Booking.com, Airbnb, Expedia, FeWo-direkt und Google Hotels
- Mitteilungsübersicht für Gastgeber
- technische Grundlage für spätere Push-Benachrichtigungen

## Wichtige Grenze

Ein echter vollständiger Channel Manager für Airbnb, Expedia, Google Hotels und andere Plattformen kann nicht allein durch Programmcode aktiviert werden. Dafür braucht es jeweilige Partnerfreigaben, API-Schlüssel und Verträge. iCal-Abgleich ist direkt nutzbar; Preise und vollständige Buchungsdaten werden über iCal nicht übertragen.

Die V6 enthält alle Einstellfelder und technischen Anschlusspunkte, aber keine erfundenen Zugangsdaten.


# Version 7 STABIL

Neu eingebaut:

- automatische iCal-Synchronisierung im Hintergrund
- einstellbares Synchronisationsintervall
- automatische Datenbank-Backups
- Backup-Rotation
- manueller Systemtest
- Health-Check unter `/health`
- Systemprotokoll
- Rechtstext-Verwaltung
- Impressum, Datenschutz, Buchungs- und Stornobedingungen
- Gutscheincodes werden jetzt tatsächlich in der Preisberechnung angewandt
- Wartungsmodus-Einstellung
- `SYSTEMTEST.bat` für eine schnelle lokale Prüfung

## Start

`STARTEN.bat` doppelklicken.

## Prüfung

`SYSTEMTEST.bat` doppelklicken.

## Wichtig

Die mitgelieferten Rechtstexte sind Platzhalter und müssen vor Veröffentlichung rechtlich geprüft und mit den echten Unternehmensdaten ergänzt werden.


# Version 8 – Zuhause am Bach OS

Neue Gastgeber-Plattform:

- zentrale OS-Startseite
- Gästekartei mit Buchungshistorie und Stammgastdaten
- Aufgabenverwaltung mit Prioritäten und Fälligkeit
- Zimmerinventar mit Mindestbestand und Zustandswarnungen
- Finanzzentrale mit Umsatz, Kosten und Gewinn vor Steuer
- CSV-Finanzexport
- Windis-Center für Fidel, Gloria und Pia
- Marketing-Center für Google, Facebook, Instagram, Newsletter und Presse
- automatische Übernahme bestehender Gäste aus den Buchungen

## Aufruf

Nach dem Start:

- Buchungsseite: `http://127.0.0.1:5000`
- Verwaltung: `http://127.0.0.1:5000/admin/login`
- Zuhause am Bach OS: `http://127.0.0.1:5000/os`

Die vorhandenen Funktionen der V7 bleiben erhalten.


# Version 9 – ALLTAG

Neue Startzentrale unter:

`http://127.0.0.1:5000/heute`

Nach der Admin-Anmeldung wird diese Seite automatisch geöffnet.

Sie zeigt auf einem Bildschirm:

- heutige Anreisen
- heutige Abreisen
- Frühstücke
- Reinigungsaufgaben
- offene Zahlungen
- Gästeanfragen
- fällige Aufgaben
- Vorbereitungen für morgen
- Einkaufsliste
- erledigte Tagespunkte

Ein Klick auf das Häkchen erledigt den Punkt und aktualisiert – je nach Typ – auch:

- Aufgabenstatus
- Gästeanfragen
- Zahlungsstatus
- Housekeeping-Status

Zusätzlich können spontane Tagesaufgaben und Einkäufe direkt eingetragen werden.


# Version 10.0 – Gastgeber-Assistent

Neue Standardzentrale:

`http://127.0.0.1:5000/assistent`

Nach der Admin-Anmeldung öffnet sich der Gastgeber-Assistent automatisch.

Neu:

- Tagesübersicht mit Anreisen, Abreisen, Frühstück, Reinigung und Zahlungen
- Gloria-Hinweis mit automatischer Handlungsempfehlung
- Frühstücksmodus
- Reinigungsmodus mit vollständiger Zimmercheckliste
- Zimmerfreigabe erst nach abgeschlossener Checkliste
- Vorbereitungen für morgen
- Inventarwarnungen
- heutiger Umsatz, Kosten und Gewinn
- Tagesabschluss mit Notiz
- vorbereitetes Wetterfeld für Aggsbach Markt

Externe Live-Wetterdaten werden später über einen Wetterdienst verbunden.


# Version 11 – Smart Host & Autopilot

Neu:

- Smart-Host-Dashboard unter `/smart`
- Autopilot für iCal-Synchronisierung, Backup und Empfehlungen
- Anreise-Countdown
- Auslastung für 14 und 30 Tage
- datenbasierte Marketing- und Betriebshinweise
- Gloria-Wäscheverwaltung
- Wartungsplan mit Wiederholungsintervallen
- Fidel-Bereich für Wandern, Rad und Ausflüge
- Pia-Bereich für Kinder und Abenteuer
- automatische Hinweise bei niedrigem Wäschebestand
- Empfehlungen bei niedriger Auslastung

Nach dem Admin-Login öffnet sich Smart Host automatisch.

Live-Wetter, echte Fahrpläne, Heurigen und aktuelle Veranstaltungen benötigen später externe Datenquellen.


# Version 11.1 – Datenbasis & Wissensverwaltung

Neu:

- zentrale Wissensverwaltung unter `/wissen`
- Stammdaten für Unterkunft, Preise, Leistungen und Hausregeln
- Fidel-, Gloria- und Pia-Wissenseinträge
- FAQ-Verwaltung
- Dokumentvorlagen
- Medienbibliothek für Bilder, PDFs und Videos
- CSV-Export der Wissensdatenbank
- Such-API für Gäste-App und Windis-Concierge
- Stammdaten-API

Wichtige Adressen:

- `/wissen`
- `/wissen/stammdaten`
- `/wissen/eintraege`
- `/wissen/faq`
- `/wissen/vorlagen`
- `/wissen/medien`

Die Inhalte können künftig ohne Änderung am Programmcode gepflegt werden.

# Version 12 – Qualität & Integration

Diese Version konzentriert sich auf Betriebsreife statt auf weitere Einzelmodule.

Neu:

- Einrichtungsassistent unter `/setup`
- Qualitätszentrum unter `/quality`
- automatische System- und Datenbankprüfung
- Sicherheitsheader für Browser
- Benutzer und Rollen für Mitarbeiter, Reinigung, Buchhaltung und Manager
- getrennte Mitarbeiter-Anmeldung unter `/staff/login`
- CSV-Import vorhandener Buchungen
- CSV-Importvorlage
- automatische Wiederherstellungspunkte vor Importen
- manuelle Wiederherstellungspunkte
- Qualitätsbericht als JSON
- Integrations-Testskript `INTEGRATIONSTEST_V12.py`

Wichtig: Die Benutzerrollen sind vorbereitet. Eine vollständige Berechtigungsprüfung für jede einzelne Route sollte vor einem öffentlich erreichbaren Mehrbenutzerbetrieb nochmals separat sicherheitsgeprüft werden.

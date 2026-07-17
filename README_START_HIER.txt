EINFACHE ONLINE-VERSION

Diese Version laeuft als einfache Website auf GitHub Pages. Sie braucht
keine Datenbank, keinen Adminbereich und keinen Python-Server.

So verwendest du sie:

1. Den Inhalt dieses Ordners auf GitHub Pages hochladen.
2. Die Datei index.html ist die Startseite.
3. Gaeste fuellen die Buchungsanfrage aus.
4. Bachblick wird gegen den aktuellen Booking-Kalenderstand geprueft.
5. Beim Absenden wird eine vorbereitete Nachricht an topdiveair@gmail.com erstellt.
6. Du pruefst Verfuegbarkeit und bestaetigst die Buchung persoenlich.

Wichtig:

- Das ist eine Buchungsanfrage, keine automatische Sofortbuchung.
- Derzeit ist nur Bachblick buchbar.
- Bachblick-Preis wurde am 16.07.2026 mit Booking.com abgeglichen:
  101,10 EUR fuer 1 Nacht / 2 Erwachsene.
- Direktbuchung berechnet 5 Prozent Rabatt auf den Zimmerpreis.
- Bei Anreise am heutigen Datum gilt der volle Booking-Preis ohne Rabatt.
- Bei freiem Termin wird PayPal-Zahlung an topdiveair@gmail.com nach
  persoenlicher Bestaetigung ausgewiesen.
- Bachblick nutzt jetzt das echte hochaufloesende Zimmerfoto
  `images/rooms/bachblick.jpg`.
- Marillenzimmer, Weinbergzimmer und Donauzimmer nutzen jetzt die gelieferten
  PNG-Zimmerbilder.
- Die Gaesteapp ist als exklusiver Bereich mit QR-Code eingebunden:
  https://topdiveair-sketch.github.io/Gaeste/index
- Das Design nutzt jetzt den Wachau-Windis-App-Stil mit Hero-Motiv,
  farbigen Schnellzugriffen, Zimmerkarten und Wachau-Tipps.
- Das Hero-Motiv wird in voller Breite und ohne abgeschnittene Bildbereiche
  angezeigt.
- Die zusaetzlichen Sprachbuttons wurden entfernt, weil sie noch keine
  echte Sprachumschaltung hatten.
- Das Wetter wird live ueber Open-Meteo fuer Aggsbach Markt geladen.
- Die Wachau-Geheimtipps verwenden echte lokale Bilddateien im Ordner
  `images/tips`; die Quellen stehen in `images/BILDQUELLEN_WACHAU_TIPPS.txt`.
- Marillenzimmer, Weinbergzimmer und Donauzimmer sind fruehestens ab
  15.08.2026 vorbereitet, bleiben aber gesperrt, bis du sie freigibst.
- Freigabe in `index.html`: `OTHER_ROOMS_RELEASED` von `false` auf `true`
  setzen.
- Die Booking-Pruefung ist ein Kalender-Snapshot vom 16.07.2026.
- Fuer echte Live-Abfrage liegt jetzt `LIVE_BOOKING_WORKER_CLOUDFLARE.js`
  und `LIVE_KALENDER_EINRICHTEN.txt` bei.
- Erst wenn die Cloudflare-Worker-URL in `index.html` bei
  `LIVE_BOOKING_API_URL` eingetragen ist, wird der Booking-Kalender bei
  jedem Seitenaufruf live geladen.
- Fuer die Live-Preisabfrage alle 10 Minuten dieselbe Worker-URL mit
  `?type=prices` bei `LIVE_PRICE_API_URL` eintragen.
- Es gibt keinen Admin-Bereich und keine automatische iCal-Sperre.
- Fuer den ersten einfachen Online-Start ist diese Variante direkt geeignet.

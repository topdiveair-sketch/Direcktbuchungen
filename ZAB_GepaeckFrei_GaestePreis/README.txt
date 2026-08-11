ZAB GEPÄCKFREI – GÄSTE-SOFORTPREIS

Was neu ist
-----------
Gast gibt nur Unterkunft, Ort oder Adresse ein.
Der Rechner:
- sucht passende Orte/Adressen,
- berechnet Straßenroute und Fahrzeit,
- verwendet aktuellen Dieselpreis bzw. sicheren Fallback,
- berechnet intern Kosten und Gewinn,
- zeigt dem Gast NUR den fertigen Gepäckpreis,
- übernimmt den Preis anschließend in die GepäckFrei-Anfrage.

Installation
------------
Im Stammordner des Repositories Direcktbuchungen:
python ZAB_GepaeckFrei_GaestePreis/apply_guest_price.py

Danach testen:
1. Zuhause am Bach -> Spitz
2. Maria Laach -> Zuhause am Bach
3. genaue Hoteladresse
4. unbekannte Adresse
5. E-Control/API-Ausfall
6. Android/mobile Ansicht
7. Preis in Anfrage übernehmen

Hinweis
-------
Die sichtbare Gästeansicht zeigt bewusst keine interne Marge oder Kostenaufschlüsselung.
Die Werte stehen zentral in zab-live-calculator-config.json.

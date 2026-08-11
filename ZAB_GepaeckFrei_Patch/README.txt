ZAB GEPÄCKFREI PATCH

Ausführung im Stammordner des Repositories Direcktbuchungen:
python ZAB_GepaeckFrei_Patch/apply_zab_gepaeckfrei.py

Danach Diff prüfen, Buchungsanfrage mit/ohne GepäckFrei testen, committen und pushen.

Codex:
Führe ZAB_GepaeckFrei_Patch/apply_zab_gepaeckfrei.py aus. Prüfe danach den Diff und teste:
1) ohne GepäckFrei
2) ZAB → nächste Unterkunft
3) vorherige Unterkunft → ZAB
4) beide Richtungen
5) E-Mail-/WhatsApp-Zusammenfassung
6) mobile Ansicht
Committe und pushe nur bei erfolgreichen Tests.

Wichtig: luggage-routes.json enthält absichtlich price=null, bis echte Partnerpreise vorliegen.

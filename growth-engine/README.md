# Growth Engine v1

Gemeinsamer Automationskern fuer **Zuhause am Bach** und **Die Wilden Wachauer Windis**.

## Sicherheitsprinzip

- Keine automatischen Werbeausgaben ohne explizit gesetzte Freigabegrenzen.
- Keine automatische Veroeffentlichung auf Social Media, solange die jeweiligen Konten/APIs nicht autorisiert sind.
- Produktionsaenderungen erfolgen erst nach Review/Merge dieses Branches.
- Bestehende Buchungslogik bleibt unangetastet.

## Zwei getrennte Engines

### Zuhause am Bach
Primaerziel: profitable Direktbuchungen und bessere Nutzung freier Zeitraeume.

Signale:
- Verfuegbarkeit
- Saison und Nachfrageanlaesse
- Content-/Kampagnenquelle
- Landingpage-Besuche
- Buchungsanfragen und Buchungen

Kern-KPIs:
- Direktbuchungen
- Direktbuchungsumsatz
- Conversion Rate
- belegte Naechte
- Kosten je bestaetigter Direktbuchung

### Wilde Wachauer Windis
Primaerziel: regionale Familienmarke, Buchverkaeufe und qualifizierte Partnerschaften.

Signale:
- Content-Themen und Figuren
- reale Wachau-Orte
- Partner-Pipeline
- Reichweite/Engagement
- Shop-/Buch-Conversions

Kern-KPIs:
- Buchverkaeufe
- qualifizierte Partner
- Partner-Conversions
- Content-Reichweite
- Conversion Rate

## Agentenrollen

1. Orchestrator: priorisiert Aufgaben anhand von Daten und Regeln.
2. Research: sammelt aktuelle Themen, Nachfrage- und Partner-Signale.
3. Content: erzeugt Briefings, Hooks, Skripte und Varianten.
4. Funnel: empfiehlt Landingpage-/CTA-Experimente.
5. Analytics: bewertet Ergebnisse und schreibt Learnings.
6. Experiment: erzeugt kontrollierte A/B-Tests.
7. Approval Gate: blockiert kostenpflichtige oder externe Aktionen ohne Freigabe.

## Event-Schema

Jedes messbare Ereignis soll mindestens enthalten:

```json
{
  "brand": "zab|windis",
  "event": "content_view|landing_view|lead|booking|sale|partner_lead|partner_won",
  "source": "organic|meta|google|partner|direct",
  "campaign": "string",
  "content_id": "string",
  "value_eur": 0,
  "timestamp": "ISO-8601"
}
```

## Naechste technische Stufe

Der bestehende Cloudflare-Worker fuer den Booking-iCal bleibt separat. Der Growth-Orchestrator wird erst nach Cloudflare-Autorisierung als eigener Worker/Agent deployed. Dadurch kann die neue Automation die bestehende Direktbuchungsfunktion nicht destabilisieren.

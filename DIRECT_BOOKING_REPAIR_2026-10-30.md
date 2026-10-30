# Direktbuchung – Reparaturbericht vom 30. Oktober 2026

**Prüfstand vor Veröffentlichung: lokal umgesetzt und getestet; Live-Übernahme noch nicht bestätigt.**

Vorbereitet sind Reparaturen für Kalenderabrufe nach HTTP 429, die erneute
Reservierungsprüfung vor einer PayPal-Bestätigung, den PayPal-Browser-Abbruch,
konsistente SQLite-Sicherungen sowie die Diagnose von Speicher und Kalendern.
Vor dem ersten Start des reparierten Codes wird eine geprüfte Sicherung der
vorhandenen Datenbank angelegt. Scheitert sie, bricht der neue Start ab.

**120 unterschiedliche lokale Tests bestanden:** 67 Zahlungs-/Kalender-/Speicher-
und Sicherungsprüfungen, 10 SQLite-/Parallelitätsprüfungen, 6 Bankbuchungsprüfungen,
25 bestehende Buchungs-/Preis-/Oberflächenprüfungen und 12 Kanalpreisprüfungen.
Zusätzlich bestanden Python-/JavaScript-Syntaxprüfung, Übersetzungskatalog und
`git diff --check`. Getestet wurde mit Python 3.12 und den Projektabhängigkeiten.

Nicht bestätigt sind echte Zahlungsvorgänge beim Anbieter, der vollständige
aktuelle Kanalabgleich und die Wiederherstellung der produktiven Datenbank.
Die nachfolgenden technischen Details beschreiben die vorbereitete Reparatur.

Nach der zunächst abgelehnten Veröffentlichung wurde das Hochladen vom Nutzer
am 30. Oktober 2026 ausdrücklich freigegeben. Dieser Prüfbericht dokumentiert
den getesteten Stand; GitHub-Prüfungen und Live-Kontrolle folgen nach dem Upload.

## Scope and baseline

Prepared against `fix/booking-section-order` at `60c7884`; the verified live
deployment was `0446ace` (the subsequent base commit changes SEO documentation).
This repair contains no price, inventory, credential or provider-setting changes.

The inspected production code already validates Stripe email addresses, removes
the old six-hour retry lock, and treats explicit OS day prices as final direct
rates. Old open PRs are not evidence that those fixes are missing from production.

## Implemented repairs

- Calendar fetches use a persistent SQLite lease and per-provider cooldown.
  HTTP 429 observes Retry-After and exponential backoff. No immediate second
  request is made. Concurrent requests reuse a recent successful snapshot.
  A partial failure cannot declare full success; old occupancy blocks survive
  malformed responses, failed imports and database rollback.
- PayPal browser cancellation no longer changes reservations. A verified capture
  rechecks order, method, amount, current reservation status, competing bookings,
  external blocks and room closures inside one transaction before confirmation.
  Invalid email is rejected before calendar or payment calls. Replayed successful
  returns do not capture again. A captured payment that cannot be assigned safely
  remains a manual reconciliation case; no automatic refund is attempted.
- Automatic SQLite backups use SQLite's online backup API, an integrity check
  and atomic publication instead of copying a potentially active database file.
  Committed WAL data is included; a failed backup preserves the previous copy.
- Before the repaired app first starts against an existing database, it creates
  a protected, verified pre-repair backup. Failure stops startup. Rollback code
  can ignore the added calendar-state table; restoring the database is not a
  normal code-rollback step because that could discard newer real bookings.
- `/health/zab-storage` checks actual mount membership, database readability,
  booking schema and quick integrity. `/health/calendar-sync` exposes stored
  per-provider freshness without feed URLs, guest names or booking IDs. Both
  diagnostics bypass request cleanup/notification hooks and do not refresh feeds.

## Validation and limits

Offline tests reproduced five PayPal failures before repair (browser cancellation,
manual cancellation during capture, competing booking, external block and closure).
The corresponding tests pass after repair. Existing and new tests also cover
Stripe settlement, concurrent calendar requests, rollback, throttling, restored
backup contents, read-only diagnostics, manual-price precedence and quote parity.

Two old concurrency expectations were corrected: explicitly entered day rates
are final rates, and quote test dates must be in the future. Booking protection
assertions were retained and strengthened; no production price logic was changed.
An outdated bathroom-copy assertion now checks the existing, explicit disclosure
that the private bathroom is opposite the room on the corridor; the page is unchanged.

Local verification used Python 3.12 and the repository's pinned requirements.
The dedicated GitHub workflow runs on Python 3.13. Local success does not prove a
live PayPal/Stripe transaction or successful downstream OTA imports. Production
backup recovery and all provider-specific live timestamps still require checks.

## Release verification

1. Require passing repair CI and confirm the production branch has not changed.
2. Deploy only this reviewed patch to the mapped homepage service.
3. Verify `ZAB_PRE_REPAIR_BACKUP verified`, successful deployment and live health.
4. Read both diagnostic endpoints. Investigate stale providers or missing mount
   confirmation; do not remove reservations or override conservative blockers.
5. Complete sandbox payment/cancel tests and authenticated downstream calendar
   comparison before claiming complete payment/channel verification.

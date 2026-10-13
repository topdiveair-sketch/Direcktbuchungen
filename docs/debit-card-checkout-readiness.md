# Debit- und Kreditkartenzahlungen – Freigabekriterien

Stand: 13.10.2026. **Noch nicht produktiv freigeschaltet.**

## Ziel
Gäste sollen Visa Debit, Debit Mastercard sowie unterstützte Kreditkarten ohne verpflichtendes PayPal-Konto nutzen können. Die tatsächliche Kartenakzeptanz ist vom Zahlungsanbieter, Land und Händlerkonto abhängig. Maestro/V PAY nicht ohne Nachweis bewerben.

## Geplanter Checkout
1. Server synchronisiert den Zimmerkalender, prüft Verfügbarkeit und berechnet den Endbetrag inklusive Extras neu.
2. Server legt eine zeitlich begrenzte, eindeutige Reservierung an und erstellt bei einem PCI-konformen Anbieter (bevorzugt Stripe Checkout) eine Checkout-Session mit dem **serverseitigen** EUR-Betrag. Browser erhält nur die gehostete Checkout-URL; niemals Kartennummer oder CVC.
3. Webhook mit verifizierter Signatur ordnet die bezahlte Checkout-Session eindeutig der Buchungs-ID zu. Betrag, Währung, Session-/PaymentIntent-ID und Zahlungsstatus müssen stimmen.
4. Bestätigung und Kalenderblockierung erfolgen in einer atomaren Datenbanktransaktion. Wiederholte Webhooks sind idempotent. Gast und Gastgeber werden erst danach informiert.
5. Abbruch/Timeout darf eine Buchung nur freigeben, wenn keine bestätigte oder möglicherweise erfolgreiche Zahlung existiert.
6. Bei unbekanntem Status: nicht automatisch freigeben, Gastgeber warnen, manuelle Prüfung dokumentieren.
7. Erstattung nur über authentifizierte Verwaltung mit eindeutigem Zahlungsbeleg, Audit-Log und separater Berechtigung.

## Vor produktiver Freigabe
- Stripe-Händlerkonto und Auszahlungskonto rechtmäßig eingerichtet; API- und Webhook-Schlüssel ausschließlich als Railway-Secrets.
- Testkartenfälle: Zahlung erfolgreich, 3-D-Secure, abgelehnt, abgebrochen, Timeout, doppelte Webhooks, Rückgabe ohne Webhook, Webhook ohne Browser-Rückgabe.
- Zwei gleichzeitige Buchungsversuche auf die einzige verfügbare Nacht: maximal eine bestätigte Reservierung.
- Echte Kleinbetragszahlung mit Debitkarte und verifizierter Auszahlung; anschließende kontrollierte Erstattung.
- Kartenlogos und die Bezeichnung „Debitkarte“ erst anzeigen, wenn diese Zahlungsart für das Händlerkonto nachweislich aktiviert ist.
- Gebühren und Rückerstattungsregeln in der Buchungsbestätigung und den Bedingungen korrekt ausweisen.

**Status im Code:** `stripe_checkout_implemented = false`, `card_payment_live_verified = false`. PayPal-Checkout ist keine Bestätigung für kartengestützten Gast-Checkout.

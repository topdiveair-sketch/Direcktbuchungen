from pathlib import Path

# Route international CTAs into a language-aware checkout.
for code in ("en", "cs", "sk", "hu", "pl", "nl"):
    fp = Path(code) / "index.html"
    text = fp.read_text(encoding="utf-8")
    text = text.replace(
        f'../?utm_source={code}&utm_medium=international&utm_campaign=direct_booking#requestForm',
        f'../?lang={code}&utm_source={code}&utm_medium=international&utm_campaign=direct_booking#requestForm',
    )
    fp.write_text(text, encoding="utf-8")

# Root checkout: honour a supported ?lang= parameter. The existing translation
# framework provides native EN/CS/HU content and English fallback for SK/PL/NL.
p = Path("index.html")
s = p.read_text(encoding="utf-8")
s = s.replace(
    '// Root page is German. Other languages use dedicated static SEO pages.\n    let currentLang = "de";',
    '// Root page is German by default. International landing pages pass ?lang=... into the checkout.\n    const requestedCheckoutLang = new URLSearchParams(window.location.search).get("lang");\n    let currentLang = LANGUAGES[requestedCheckoutLang] ? requestedCheckoutLang : "de";',
)
p.write_text(s, encoding="utf-8")

# PayPal checkout surface: never fall back to German for an international checkout.
# Native landing pages stay in their language; the transactional checkout uses
# English as the universal fallback where a full native checkout dictionary is
# not available yet.
js = Path("zab-paypal-checkout.js")
t = js.read_text(encoding="utf-8")
anchor = '    const totalField=document.getElementById("total");\n    if(!paypalLink||!form) return;'
insert = '''    const totalField=document.getElementById("total");
    if(!paypalLink||!form) return;

    const checkoutLang=(new URLSearchParams(window.location.search).get("lang")||document.documentElement.lang||"de").slice(0,2).toLowerCase();
    const deCheckout=checkoutLang==="de";
    const L=(de,en)=>deCheckout?de:en;'''
if anchor in t:
    t = t.replace(anchor, insert, 1)

pairs = [
    ('totalField.textContent="Termin wählen";', 'totalField.textContent=L("Termin wählen","Choose dates");'),
    ('if(heroEyebrow) heroEyebrow.textContent="Direkt buchen ohne Buchungsplattform";', 'if(heroEyebrow) heroEyebrow.textContent=L("Direkt buchen ohne Buchungsplattform","Book direct without another booking platform");'),
    ('if(bookingTitle) bookingTitle.textContent="Wachau-Etappe direkt buchen";', 'if(bookingTitle) bookingTitle.textContent=L("Wachau-Etappe direkt buchen","Book your Wachau stay direct");'),
    ('bookingIntro.textContent="Reisedaten wählen, Live-Verfügbarkeit prüfen und einen freien Termin sicher mit PayPal oder Kredit-/Debitkarte direkt buchen. Falls Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.";', 'bookingIntro.textContent=L("Reisedaten wählen, Live-Verfügbarkeit prüfen und einen freien Termin sicher mit PayPal oder Kredit-/Debitkarte direkt buchen. Falls Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.","Choose your dates, check live availability and book an available stay securely via PayPal. PayPal may also offer debit or credit card payment. If instant booking is unavailable, you can still send a personal request.");'),
    ('if(trustStrong) trustStrong.textContent="Direkt buchen bei den Gastgebern";', 'if(trustStrong) trustStrong.textContent=L("Direkt buchen bei den Gastgebern","Book directly with your hosts");'),
    ('if(trustSpan) trustSpan.textContent="Live-Verfügbarkeit, transparenter Preis und sichere Zahlung über PayPal – auch per Kredit- oder Debitkarte, soweit PayPal dies anbietet.";', 'if(trustSpan) trustSpan.textContent=L("Live-Verfügbarkeit, transparenter Preis und sichere Zahlung über PayPal – auch per Kredit- oder Debitkarte, soweit PayPal dies anbietet.","Live availability, transparent direct price and secure payment via PayPal; debit or credit card may also be offered by PayPal.");'),
    ('if(trustSmall) trustSmall.textContent="Ohne Provision oder Umweg über eine zusätzliche Buchungsplattform.";', 'if(trustSmall) trustSmall.textContent=L("Ohne Provision oder Umweg über eine zusätzliche Buchungsplattform.","No detour through another booking platform.");'),
    ('if(bookingTileTitle) bookingTileTitle.textContent="Direkt buchen";', 'if(bookingTileTitle) bookingTileTitle.textContent=L("Direkt buchen","Book direct");'),
    ('if(bookingTileSmall) bookingTileSmall.textContent="Verfügbarkeit live prüfen";', 'if(bookingTileSmall) bookingTileSmall.textContent=L("Verfügbarkeit live prüfen","Check live availability");'),
    ('if(bookingTile) bookingTile.setAttribute("aria-label","Direkt buchen – Verfügbarkeit live prüfen");', 'if(bookingTile) bookingTile.setAttribute("aria-label",L("Direkt buchen – Verfügbarkeit live prüfen","Book direct – check live availability"));'),
    ('if(submitRequest) submitRequest.textContent="Buchungsanfrage senden";', 'if(submitRequest) submitRequest.textContent=L("Buchungsanfrage senden","Send booking request");'),
    ('checkoutHeading("⛔ Belegt – bitte anderen Termin wählen");', 'checkoutHeading(L("⛔ Belegt – bitte anderen Termin wählen","⛔ Unavailable – please choose different dates"));'),
    ('if(paypalHint) paypalHint.textContent=message||"Das Zimmer ist für diesen Zeitraum bereits belegt.";', 'if(paypalHint) paypalHint.textContent=message||L("Das Zimmer ist für diesen Zeitraum bereits belegt.","The room is unavailable for these dates.");'),
    ('availability.textContent="⛔ Belegt – bitte einen anderen Termin wählen.";', 'availability.textContent=L("⛔ Belegt – bitte einen anderen Termin wählen.","⛔ Unavailable – please choose different dates.");'),
    ('checkoutHeading("Verfügbarkeit wird geprüft");', 'checkoutHeading(L("Verfügbarkeit wird geprüft","Checking availability"));'),
    ('if(paypalHint) paypalHint.textContent="Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …";', 'if(paypalHint) paypalHint.textContent=L("Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …","Availability is being checked against the current Booking calendar …");'),
    ('? `Jetzt ${total.toFixed(2).replace(".",",")} EUR mit PayPal oder Karte bezahlen`\n        : "Jetzt mit PayPal oder Karte bezahlen";', '? (deCheckout?`Jetzt ${total.toFixed(2).replace(".",",")} EUR mit PayPal oder Karte bezahlen`:`Pay ${total.toFixed(2)} EUR securely with PayPal`)\n        : L("Jetzt mit PayPal oder Karte bezahlen","Pay securely with PayPal");'),
    ('checkoutHeading("✅ Termin frei – sichere Direktzahlung");', 'checkoutHeading(L("✅ Termin frei – sichere Direktzahlung","✅ Available – secure direct payment"));'),
    ('if(paypalHint) paypalHint.textContent="Termin ist laut aktuellem Booking-Kalender frei. Beim Klick wird der Termin serverseitig reserviert und vor PayPal nochmals sicher geprüft. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten; die tatsächliche Verfügbarkeit bestimmt PayPal.";', 'if(paypalHint) paypalHint.textContent=L("Termin ist laut aktuellem Booking-Kalender frei. Beim Klick wird der Termin serverseitig reserviert und vor PayPal nochmals sicher geprüft. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten; die tatsächliche Verfügbarkeit bestimmt PayPal.","These dates are available according to the current Booking calendar. When you continue, the stay is held server-side and checked once more before PayPal. PayPal may offer debit or credit card payment in guest checkout; availability is determined by PayPal.");'),
    ('availability.textContent="✅ Frei – live über den aktuellen Booking-Kalender geprüft.";', 'availability.textContent=L("✅ Frei – live über den aktuellen Booking-Kalender geprüft.","✅ Available – checked live against the current Booking calendar.");'),
    ('hidePayPal("Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.");', 'hidePayPal(L("Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.","Instant payment is not fully available right now. Please send a booking request instead."));'),
    ('showBlocked("Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.");', 'showBlocked(L("Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.","The Booking calendar blocks these dates. Please choose different dates."));'),
    ('hidePayPal("Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.");', 'hidePayPal(L("Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.","Luggage transfer has a route-dependent price. Please deselect it to pay for the stay now, or send a request first."));'),
    ('hidePayPal("Live-Verfügbarkeitsprüfung derzeit nicht erreichbar. Bitte Buchungsanfrage senden oder später erneut versuchen.");', 'hidePayPal(L("Live-Verfügbarkeitsprüfung derzeit nicht erreichbar. Bitte Buchungsanfrage senden oder später erneut versuchen.","Live availability is temporarily unavailable. Please send a booking request or try again later."));'),
    ('checkoutHeading("PayPal wird vorbereitet …");', 'checkoutHeading(L("PayPal wird vorbereitet …","Preparing PayPal …"));'),
    ('if(paypalHint) paypalHint.textContent="Verfügbarkeit und Preis werden jetzt serverseitig final geprüft.";', 'if(paypalHint) paypalHint.textContent=L("Verfügbarkeit und Preis werden jetzt serverseitig final geprüft.","Availability and price are now being checked one final time on the server.");'),
    ('checkoutHeading("⚠️ PayPal konnte nicht gestartet werden");', 'checkoutHeading(L("⚠️ PayPal konnte nicht gestartet werden","⚠️ PayPal could not be started"));'),
]
for old, new in pairs:
    if old in t:
        t = t.replace(old, new)
js.write_text(t, encoding="utf-8")

# Validate language routing and checkout fallback.
root = Path("index.html").read_text(encoding="utf-8")
assert "requestedCheckoutLang" in root
for code in ("en", "cs", "sk", "hu", "pl", "nl"):
    page = (Path(code) / "index.html").read_text(encoding="utf-8")
    assert f"?lang={code}&utm_source={code}" in page
checkout = Path("zab-paypal-checkout.js").read_text(encoding="utf-8")
assert "const checkoutLang=" in checkout
assert "Book your Wachau stay direct" in checkout
print("Language-aware checkout patch validation passed")

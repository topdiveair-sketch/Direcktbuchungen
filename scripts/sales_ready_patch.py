from pathlib import Path


def replace_if_present(text: str, old: str, new: str) -> str:
    return text.replace(old, new) if old in text else text


# Main German page
p = Path("index.html")
s = p.read_text(encoding="utf-8")
replacements = [
    ("<title>Zuhause am Bach – Wachau | Donauradweg & Welterbesteig</title>",
     "<title>Zuhause am Bach – Direkt buchen in der Wachau | Donauradweg & Welterbesteig</title>"),
    ('<meta name="description" content="Ruhig übernachten in Aggsbach Markt in der Wachau – ideal für Radfahrer am Donauradweg und Wanderer am Welterbesteig. Frühstück, Fahrradgarage und persönliche Wachau-Tipps.">',
     '<meta name="description" content="Zuhause am Bach in Aggsbach Markt direkt buchen: Live-Verfügbarkeit, transparenter Direktpreis und sichere PayPal-Zahlung für Donauradweg, Welterbesteig und Wachau-Aufenthalte.">'),
    ('<meta property="og:title" content="Zuhause am Bach – Wachau | Donauradweg & Welterbesteig">',
     '<meta property="og:title" content="Zuhause am Bach – Direkt buchen in der Wachau">'),
    ('<meta property="og:description" content="Ruhig übernachten in Aggsbach Markt – für Radfahrer am Donauradweg und Wanderer am Welterbesteig, mit Frühstück und persönlichen Wachau-Tipps.">',
     '<meta property="og:description" content="Live-Verfügbarkeit prüfen, Direktpreis sehen und sicher über PayPal direkt bei Zuhause am Bach buchen.">'),
    ('<meta name="twitter:title" content="Zuhause am Bach – Wachau | Donauradweg & Welterbesteig">',
     '<meta name="twitter:title" content="Zuhause am Bach – Direkt buchen in der Wachau">'),
    ('<meta name="twitter:description" content="Ruhig und persönlich übernachten in Aggsbach Markt – mit Frühstück für Wanderer und Radfahrer.">',
     '<meta name="twitter:description" content="Direkt buchen mit Live-Verfügbarkeit, transparentem Preis und sicherer PayPal-Zahlung.">'),
    ('"dateModified": "2026-09-02"', '"dateModified": "2026-09-13"'),
    ('"dateModified":"2026-09-02"', '"dateModified":"2026-09-13"'),
    ('"sameAs": ["https://www.booking.com/Share-O4rtfLD"]',
     '"sameAs": ["https://www.donau.com/unterkunft/zu-hause-am-bach-wachau"]'),
    ("Direkt anfragen ohne Buchungsplattform", "Direkt buchen ohne Buchungsplattform"),
    ('<h2 id="booking-title">Wachau-Etappe direkt anfragen</h2>',
     '<h2 id="booking-title">Wachau-Etappe direkt buchen</h2>'),
    ('<p class="booking-intro">Reisedaten wählen, persönlich anfragen und bei der Ankunft Ihren Wachau-Etappenstempel für Wanderpass oder Radreise-Tagebuch erhalten.</p>',
     '<p class="booking-intro">Reisedaten wählen, Live-Verfügbarkeit und Direktpreis prüfen und einen freien Termin sicher über PayPal direkt buchen. Wenn Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.</p>'),
    ('<div class="direct-booking-trust"><strong>Direkt bei den Gastgebern</strong><span>Persönliche Anfrage, transparente Leistungen und Live-Verfügbarkeitsprüfung.</span><small>Ohne Umweg über eine zusätzliche Buchungsplattform.</small></div>',
     '<div class="direct-booking-trust"><strong>Direkt bei den Gastgebern buchen</strong><span>Live-Verfügbarkeit, transparenter Direktpreis und sichere Zahlung über PayPal. Debit- oder Kreditkarte kann PayPal im Gast-Checkout anbieten.</span><small>Ohne Umweg über eine zusätzliche Buchungsplattform.</small></div>'),
    ('<a class="quick-tile book" href="#requestForm"><span>Verfügbarkeit prüfen</span><small>Direkt anfragen</small></a>',
     '<a class="quick-tile book" href="#requestForm"><span>Direkt buchen</span><small>Verfügbarkeit live prüfen</small></a>'),
    ("Meine Wachau-Etappe anfragen", "Verfügbarkeit prüfen & direkt buchen"),
    ('<a id="paypalLink" class="btn hidden" href="https://www.paypal.com/myaccount/transfer/homepage/send" target="_blank" rel="noopener">PayPal öffnen</a>',
     '<a id="paypalLink" class="btn hidden" href="#">Sicher mit PayPal bezahlen</a>\n            <small class="payment-terms">Mit der Zahlung akzeptieren Sie die <a href="#impressum">Buchungs- und Stornobedingungen</a> sowie die Datenschutzhinweise.</small>'),
    ('<button id="submitRequest" class="btn" type="submit">Wachau-Etappe anfragen</button>',
     '<button id="submitRequest" class="btn" type="submit">Buchungsanfrage senden</button>'),
    ('<h2 id="direkt-vorteile-title">Direkt anfragen – klar und persönlich</h2>',
     '<h2 id="direkt-vorteile-title">Direkt buchen – sicher und persönlich</h2>'),
    ('<p>Reisedaten, Zimmer und Extras auswählen, den berechneten Gesamtpreis prüfen und die Verfügbarkeit direkt bei Zuhause am Bach anfragen.</p>',
     '<p>Reisedaten, Zimmer und Extras auswählen, Live-Verfügbarkeit und Direktpreis prüfen und einen freien Termin sicher direkt buchen. Die persönliche Anfrage bleibt als Fallback verfügbar.</p>'),
    ('<article class="fact"><strong>Direkter Kontakt</strong><span>Ihre Anfrage geht ohne Umweg direkt an die Gastgeber.</span></article>',
     '<article class="fact"><strong>Direkt bei den Gastgebern</strong><span>Buchung oder Anfrage geht ohne Umweg direkt an Zuhause am Bach.</span></article>'),
    ("Frühstück kann in der Direktanfrage als Zusatzleistung gewählt werden.",
     "Frühstück kann bei der Direktbuchung oder in einer Anfrage als Zusatzleistung gewählt werden."),
    ("Frühstück kann in der Direktanfrage gewählt werden.",
     "Frühstück kann bei der Direktbuchung oder in einer Anfrage gewählt werden."),
    ('<p>Die per E-Mail übermittelten Daten werden zur Bearbeitung der Buchungsanfrage verwendet.</p>\n          <p>Es werden Name, Kontaktdaten, Reisedaten, Zimmerwunsch und Nachricht verarbeitet.</p>',
     '<p>Personenbezogene Daten werden zur Bearbeitung von Direktbuchungen und Anfragen verarbeitet. Dazu gehören insbesondere Name, Kontaktdaten, Reisedaten, Zimmer, gewählte Zusatzleistungen und Nachricht.</p>\n          <p>Bei einer Direktbuchung werden die für Buchung und Zahlung erforderlichen Daten über das technische Buchungsbackend verarbeitet und zur Zahlungsabwicklung an PayPal übermittelt. PayPal verarbeitet Zahlungsdaten nach den eigenen Datenschutzbestimmungen.</p>'),
    ('<p>Nach Ihrer Anfrage prüfen wir die Verfügbarkeit persönlich. Ihre Buchung wird mit unserer Bestätigung verbindlich.</p>\n          <p>Preise und Verfügbarkeit werden in der Bestätigung geprüft.</p>',
     '<p><strong>Direktbuchung:</strong> Bei einem als frei bestätigten Termin werden Verfügbarkeit und Preis serverseitig geprüft. Nach erfolgreich bestätigter PayPal-Zahlung ist die Reservierung als bezahlt und bestätigt erfasst.</p>\n          <p><strong>Anfrage:</strong> Wenn keine Sofortbuchung möglich ist oder eine Leistung persönliche Klärung braucht, entsteht erst mit unserer ausdrücklichen Bestätigung eine verbindliche Buchung.</p>'),
    ('<p>Stornierungen müssen schriftlich per E-Mail an Zuhause.am.Bach@outlook.com erfolgen.</p>\n          <p>Die konkrete Regelung wird mit der Buchungsbestätigung bekanntgegeben.</p>',
     '<p>Stornierungen müssen schriftlich per E-Mail an Zuhause.am.Bach@outlook.com erfolgen.</p>\n          <p>Maßgeblich sind die für die jeweilige Buchung vereinbarten Stornobedingungen; sie werden in der Buchungsbestätigung dokumentiert. Bei Fragen vor der Zahlung kontaktieren Sie uns bitte vor Abschluss der Direktbuchung.</p>'),
    ("zab-paypal-checkout.js?v=20260910-1", "zab-paypal-checkout.js?v=20260913-4"),
]
for old, new in replacements:
    s = replace_if_present(s, old, new)

old_lang = '''const LANGUAGES = {
      de: { html: "de", locale: "de-AT" },
      en: { html: "en", locale: "en-GB" },
      cs: { html: "cs", locale: "cs-CZ" },
      hu: { html: "hu", locale: "hu-HU" },
      es: { html: "es", locale: "es-ES" },
      fr: { html: "fr", locale: "fr-FR" }
    };'''
new_lang = '''const LANGUAGES = {
      de: { html: "de", locale: "de-AT" },
      en: { html: "en", locale: "en-GB" },
      cs: { html: "cs", locale: "cs-CZ" },
      sk: { html: "sk", locale: "sk-SK" },
      hu: { html: "hu", locale: "hu-HU" },
      pl: { html: "pl", locale: "pl-PL" },
      nl: { html: "nl", locale: "nl-NL" }
    };'''
s = replace_if_present(s, old_lang, new_lang)
p.write_text(s, encoding="utf-8")

# English page
fp = Path("en/index.html")
page = fp.read_text(encoding="utf-8")
page = page.replace("Breakfast can be added to your direct booking request so you can start the next stage prepared.",
                    "Breakfast can be added to your direct booking so you can start the next stage prepared.")
page = page.replace('<article><h3>Personal confirmation</h3><p>Your booking becomes binding when the hosts personally confirm it.</p></article>',
                    '<article><h3>Secure direct payment</h3><p>When live availability is confirmed, you can complete the booking securely via PayPal. PayPal may also offer debit or credit card payment. A successfully confirmed payment confirms the reservation.</p></article>')
fp.write_text(page, encoding="utf-8")

# Payment truth blocks for other languages
localized = {
    "cs": ("Bezpečná přímá platba", "Pokud je termín podle živé dostupnosti volný, můžete rezervaci bezpečně dokončit přes PayPal. PayPal může podle dostupnosti nabídnout také platbu debetní nebo kreditní kartou. Úspěšně potvrzená platba potvrzuje rezervaci."),
    "sk": ("Bezpečná priama platba", "Ak je termín podľa živej dostupnosti voľný, rezerváciu môžete bezpečne dokončiť cez PayPal. PayPal môže podľa dostupnosti ponúknuť aj platbu debetnou alebo kreditnou kartou. Úspešne potvrdená platba potvrdzuje rezerváciu."),
    "hu": ("Biztonságos közvetlen fizetés", "Ha az élő elérhetőség szerint az időpont szabad, a foglalás biztonságosan befejezhető PayPalon keresztül. A PayPal jogosultságtól függően betéti vagy hitelkártyás fizetést is felajánlhat. A sikeresen visszaigazolt fizetés megerősíti a foglalást."),
    "pl": ("Bezpieczna płatność bezpośrednia", "Jeśli termin jest dostępny w sprawdzeniu na żywo, rezerwację można bezpiecznie zakończyć przez PayPal. PayPal może również udostępnić płatność kartą debetową lub kredytową. Pomyślnie potwierdzona płatność potwierdza rezerwację."),
    "nl": ("Veilige rechtstreekse betaling", "Als de live beschikbaarheid bevestigt dat de datum vrij is, kunt u de boeking veilig afronden via PayPal. PayPal kan, afhankelijk van beschikbaarheid, ook betaling met een betaalpas of creditcard aanbieden. Een succesvol bevestigde betaling bevestigt de reservering."),
}
for code, (heading, body) in localized.items():
    fp = Path(code) / "index.html"
    page = fp.read_text(encoding="utf-8")
    marker = f"<h2>{heading}</h2>"
    if marker not in page:
        anchor = '<section><div class="cta">'
        if anchor not in page:
            raise RuntimeError(f"CTA anchor missing in {fp}")
        block = f'<section><div class="card"><h2>{heading}</h2><p>{body}</p></div></section>'
        page = page.replace(anchor, block + anchor, 1)
    fp.write_text(page, encoding="utf-8")

# Vienna date edge case
rp = Path("railway_app.py")
rs = rp.read_text(encoding="utf-8")
rs = rs.replace("from datetime import date, timedelta", "from datetime import datetime, timedelta")
if "from zoneinfo import ZoneInfo" not in rs:
    rs = rs.replace("from email.utils import parseaddr\n", "from email.utils import parseaddr\nfrom zoneinfo import ZoneInfo\n")
rs = rs.replace('    if arrival < date.today():\n', '    if arrival < datetime.now(ZoneInfo("Europe/Vienna")).date():\n')
rs = rs.replace('PAYPAL_CHECKOUT_DEPLOY_REV = "2026-09-13-paypal-unified-card-v3"',
                'PAYPAL_CHECKOUT_DEPLOY_REV = "2026-09-13-sales-ready-v4"')
rp.write_text(rs, encoding="utf-8")

# PayPal reconciliation
pp = Path("paypal_checkout.py")
ps = pp.read_text(encoding="utf-8")
old_unit = '''                            {
                                "amount": {
                                    "currency_code": "EUR",
                                    "value": f"{total:.2f}",
                                }
                            }'''
new_unit = '''                            {
                                "custom_id": f"ZAB-{booking_id}",
                                "description": f"Zuhause am Bach - {room} {arrival.isoformat()} bis {departure.isoformat()}",
                                "amount": {
                                    "currency_code": "EUR",
                                    "value": f"{total:.2f}",
                                },
                            }'''
if old_unit in ps:
    ps = ps.replace(old_unit, new_unit, 1)
pp.write_text(ps, encoding="utf-8")

# Assertions
checks = {
    "index.html": ["Direkt buchen ohne Buchungsplattform", "Buchungs- und Stornobedingungen", "zab-paypal-checkout.js?v=20260913-4", 'pl: { html: "pl", locale: "pl-PL" }', 'nl: { html: "nl", locale: "nl-NL" }'],
    "en/index.html": ["Secure direct payment", "A successfully confirmed payment confirms the reservation."],
    "cs/index.html": ["Bezpečná přímá platba"],
    "sk/index.html": ["Bezpečná priama platba"],
    "hu/index.html": ["Biztonságos közvetlen fizetés"],
    "pl/index.html": ["Bezpieczna płatność bezpośrednia"],
    "nl/index.html": ["Veilige rechtstreekse betaling"],
    "railway_app.py": ["Europe/Vienna", "2026-09-13-sales-ready-v4"],
    "paypal_checkout.py": ['"custom_id": f"ZAB-{booking_id}"'],
}
for file, needles in checks.items():
    text = Path(file).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise RuntimeError(f"Missing expected text in {file}: {needle}")

print("Sales-ready patch validation passed")

(function(){
"use strict";

function ready(fn){
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn, {once:true});
  else fn();
}

ready(function(){
  setTimeout(function(){
    const apiBase=String(window.ZAB_DIRECT_BOOKING_API_URL||"").replace(/\/+$/,"");
    let paypalLink=document.getElementById("paypalLink");
    const paypalBox=document.getElementById("paypalBox");
    let paypalHint=document.getElementById("paypalHint");
    const form=document.getElementById("requestForm");
    const availability=document.getElementById("availabilityStatus");
    const submitRequest=document.getElementById("submitRequest");
    const totalField=document.getElementById("total");
    if(!paypalLink||!form) return;

    const requestedLang=(new URLSearchParams(window.location.search).get("lang")||document.documentElement.lang||"de").slice(0,2).toLowerCase();
    const supportedCheckoutLangs=new Set(["de","en","cs","sk","hu","pl","nl"]);
    const checkoutLang=supportedCheckoutLangs.has(requestedLang)?requestedLang:"de";
    const T={
      de:{choose:"Termin wählen",hero:"Direkt buchen ohne Buchungsplattform",title:"Wachau-Etappe direkt buchen",intro:"Reisedaten wählen, Live-Verfügbarkeit prüfen und einen freien Termin sicher mit PayPal direkt buchen. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten. Falls Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.",trust:"Direkt buchen bei den Gastgebern",trust2:"Live-Verfügbarkeit, transparenter Preis und sichere Zahlung über PayPal – auch per Kredit- oder Debitkarte, soweit PayPal dies anbietet.",trust3:"Ohne Provision oder Umweg über eine zusätzliche Buchungsplattform.",tile:"Direkt buchen",tile2:"Verfügbarkeit live prüfen",request:"Buchungsanfrage senden",blocked:"⛔ Belegt – bitte anderen Termin wählen",blocked2:"Das Zimmer ist für diesen Zeitraum bereits belegt.",blocked3:"⛔ Belegt – bitte einen anderen Termin wählen.",checking:"Verfügbarkeit wird geprüft",checking2:"Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …",pay:"Jetzt mit PayPal bezahlen",available:"✅ Termin frei – sichere Direktzahlung",available2:"Termin ist laut aktuellem Booking-Kalender frei. Beim Klick wird der Termin serverseitig reserviert und vor PayPal nochmals sicher geprüft. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten; die tatsächliche Verfügbarkeit bestimmt PayPal.",available3:"✅ Frei – live über den aktuellen Booking-Kalender geprüft.",config:"Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.",calendarBlock:"Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.",luggage:"Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.",unreachable:"Live-Verfügbarkeitsprüfung derzeit nicht erreichbar. Bitte Buchungsanfrage senden oder später erneut versuchen.",preparing:"PayPal wird vorbereitet …",finalCheck:"Verfügbarkeit und Preis werden jetzt serverseitig final geprüft.",paypalError:"⚠️ PayPal konnte nicht gestartet werden"},
      en:{choose:"Choose dates",hero:"Book direct without another booking platform",title:"Book your Wachau stay direct",intro:"Choose your dates, check live availability and book an available stay securely via PayPal. PayPal may also offer debit or credit card payment. If instant booking is unavailable, you can still send a personal request.",trust:"Book directly with your hosts",trust2:"Live availability, transparent direct price and secure payment via PayPal; debit or credit card may also be offered by PayPal.",trust3:"No detour through another booking platform.",tile:"Book direct",tile2:"Check live availability",request:"Send booking request",blocked:"⛔ Unavailable – please choose different dates",blocked2:"The room is unavailable for these dates.",blocked3:"⛔ Unavailable – please choose different dates.",checking:"Checking availability",checking2:"Availability is being checked against the current Booking calendar …",pay:"Pay securely with PayPal",available:"✅ Available – secure direct payment",available2:"These dates are available according to the current Booking calendar. When you continue, the stay is held server-side and checked once more before PayPal. PayPal may offer debit or credit card payment in guest checkout; availability is determined by PayPal.",available3:"✅ Available – checked live against the current Booking calendar.",config:"Instant payment is not fully available right now. Please send a booking request instead.",calendarBlock:"The Booking calendar blocks these dates. Please choose different dates.",luggage:"Luggage transfer has a route-dependent price. Please deselect it to pay for the stay now, or send a request first.",unreachable:"Live availability is temporarily unavailable. Please send a booking request or try again later.",preparing:"Preparing PayPal …",finalCheck:"Availability and price are now being checked one final time on the server.",paypalError:"⚠️ PayPal could not be started"},
      cs:{choose:"Vyberte termín",hero:"Rezervujte přímo bez rezervační platformy",title:"Rezervujte si pobyt ve Wachau přímo",intro:"Vyberte termín, ověřte živou dostupnost a volný pobyt bezpečně rezervujte přes PayPal. PayPal může nabídnout také platbu debetní nebo kreditní kartou. Pokud okamžitá rezervace není možná, můžete odeslat osobní poptávku.",trust:"Rezervace přímo u hostitelů",trust2:"Živá dostupnost, transparentní přímá cena a bezpečná platba přes PayPal; PayPal může nabídnout i platbu kartou.",trust3:"Bez prostředníka a další rezervační platformy.",tile:"Rezervovat přímo",tile2:"Ověřit živou dostupnost",request:"Odeslat poptávku",blocked:"⛔ Obsazeno – vyberte jiný termín",blocked2:"Pokoj není v tomto termínu dostupný.",blocked3:"⛔ Obsazeno – vyberte jiný termín.",checking:"Ověřujeme dostupnost",checking2:"Dostupnost se ověřuje podle aktuálního kalendáře Booking …",pay:"Zaplatit bezpečně přes PayPal",available:"✅ Volno – bezpečná přímá platba",available2:"Termín je podle aktuálního kalendáře Booking volný. Před přesměrováním na PayPal je rezervace na serveru ještě jednou bezpečně ověřena. PayPal může v režimu hosta nabídnout platbu kartou.",available3:"✅ Volno – ověřeno podle aktuálního kalendáře Booking.",config:"Okamžitá platba není nyní plně dostupná. Odešlete prosím poptávku.",calendarBlock:"Kalendář Booking tento termín blokuje. Vyberte jiný termín.",luggage:"Přeprava zavazadel má cenu podle trasy. Pro okamžitou platbu ji zrušte, nebo nejprve odešlete poptávku.",unreachable:"Živou dostupnost nyní nelze ověřit. Odešlete poptávku nebo to zkuste později.",preparing:"Připravujeme PayPal …",finalCheck:"Dostupnost a cena se nyní naposledy ověřují na serveru.",paypalError:"⚠️ PayPal se nepodařilo spustit"},
      sk:{choose:"Vyberte termín",hero:"Rezervujte priamo bez rezervačnej platformy",title:"Rezervujte si pobyt vo Wachau priamo",intro:"Vyberte termín, overte živú dostupnosť a voľný pobyt bezpečne rezervujte cez PayPal. PayPal môže ponúknuť aj platbu debetnou alebo kreditnou kartou. Ak okamžitá rezervácia nie je možná, môžete odoslať osobnú požiadavku.",trust:"Rezervácia priamo u hostiteľov",trust2:"Živá dostupnosť, transparentná priama cena a bezpečná platba cez PayPal; PayPal môže ponúknuť aj platbu kartou.",trust3:"Bez sprostredkovateľa a ďalšej rezervačnej platformy.",tile:"Rezervovať priamo",tile2:"Overiť živú dostupnosť",request:"Odoslať požiadavku",blocked:"⛔ Obsadené – vyberte iný termín",blocked2:"Izba nie je v tomto termíne dostupná.",blocked3:"⛔ Obsadené – vyberte iný termín.",checking:"Overujeme dostupnosť",checking2:"Dostupnosť sa overuje podľa aktuálneho kalendára Booking …",pay:"Zaplatiť bezpečne cez PayPal",available:"✅ Voľné – bezpečná priama platba",available2:"Termín je podľa aktuálneho kalendára Booking voľný. Pred presmerovaním na PayPal sa rezervácia na serveri ešte raz bezpečne overí. PayPal môže v režime hosťa ponúknuť platbu kartou.",available3:"✅ Voľné – overené podľa aktuálneho kalendára Booking.",config:"Okamžitá platba momentálne nie je plne dostupná. Odošlite prosím požiadavku.",calendarBlock:"Kalendár Booking tento termín blokuje. Vyberte iný termín.",luggage:"Preprava batožiny má cenu podľa trasy. Pre okamžitú platbu ju zrušte alebo najprv odošlite požiadavku.",unreachable:"Živú dostupnosť teraz nemožno overiť. Odošlite požiadavku alebo to skúste neskôr.",preparing:"Pripravujeme PayPal …",finalCheck:"Dostupnosť a cena sa teraz naposledy overujú na serveri.",paypalError:"⚠️ PayPal sa nepodarilo spustiť"},
      hu:{choose:"Válasszon dátumot",hero:"Foglaljon közvetlenül foglalási platform nélkül",title:"Foglalja le közvetlenül wachaui tartózkodását",intro:"Válassza ki a dátumokat, ellenőrizze az élő elérhetőséget, és foglalja le biztonságosan a szabad időpontot PayPalon keresztül. A PayPal bank- vagy hitelkártyás fizetést is felajánlhat. Ha az azonnali foglalás nem lehetséges, személyes érdeklődést küldhet.",trust:"Foglalás közvetlenül a házigazdáknál",trust2:"Élő elérhetőség, átlátható közvetlen ár és biztonságos PayPal-fizetés; a PayPal kártyás fizetést is felajánlhat.",trust3:"Közvetítő és további foglalási platform nélkül.",tile:"Közvetlen foglalás",tile2:"Élő elérhetőség ellenőrzése",request:"Foglalási érdeklődés küldése",blocked:"⛔ Foglalt – válasszon másik dátumot",blocked2:"A szoba ezekre a dátumokra nem elérhető.",blocked3:"⛔ Foglalt – válasszon másik dátumot.",checking:"Elérhetőség ellenőrzése",checking2:"Az elérhetőséget az aktuális Booking-naptár alapján ellenőrizzük …",pay:"Biztonságos fizetés PayPallal",available:"✅ Szabad – biztonságos közvetlen fizetés",available2:"A dátum az aktuális Booking-naptár szerint szabad. A PayPalra irányítás előtt a foglalást a szerver még egyszer ellenőrzi. A PayPal vendégként kártyás fizetést is felajánlhat.",available3:"✅ Szabad – az aktuális Booking-naptár alapján ellenőrizve.",config:"Az azonnali fizetés jelenleg nem teljesen elérhető. Küldjön inkább foglalási érdeklődést.",calendarBlock:"A Booking-naptár blokkolja ezt az időpontot. Válasszon másik dátumot.",luggage:"A csomagszállítás ára útvonalfüggő. Az azonnali fizetéshez törölje ezt az opciót, vagy előbb küldjön érdeklődést.",unreachable:"Az élő elérhetőség jelenleg nem ellenőrizhető. Küldjön érdeklődést vagy próbálja később.",preparing:"PayPal előkészítése …",finalCheck:"Az elérhetőséget és az árat a szerver most még egyszer véglegesen ellenőrzi.",paypalError:"⚠️ A PayPal nem indítható"},
      pl:{choose:"Wybierz termin",hero:"Rezerwuj bezpośrednio bez platformy rezerwacyjnej",title:"Zarezerwuj pobyt w Wachau bezpośrednio",intro:"Wybierz termin, sprawdź dostępność na żywo i bezpiecznie zarezerwuj wolny pobyt przez PayPal. PayPal może również zaoferować płatność kartą debetową lub kredytową. Jeśli rezerwacja natychmiastowa nie jest możliwa, możesz wysłać zapytanie.",trust:"Rezerwacja bezpośrednio u gospodarzy",trust2:"Dostępność na żywo, przejrzysta cena bezpośrednia i bezpieczna płatność przez PayPal; PayPal może także zaoferować płatność kartą.",trust3:"Bez pośrednika i dodatkowej platformy rezerwacyjnej.",tile:"Rezerwuj bezpośrednio",tile2:"Sprawdź dostępność na żywo",request:"Wyślij zapytanie",blocked:"⛔ Zajęte – wybierz inny termin",blocked2:"Pokój nie jest dostępny w tym terminie.",blocked3:"⛔ Zajęte – wybierz inny termin.",checking:"Sprawdzamy dostępność",checking2:"Dostępność jest sprawdzana w aktualnym kalendarzu Booking …",pay:"Zapłać bezpiecznie przez PayPal",available:"✅ Wolne – bezpieczna płatność bezpośrednia",available2:"Termin jest wolny według aktualnego kalendarza Booking. Przed przejściem do PayPal rezerwacja jest ponownie bezpiecznie sprawdzana na serwerze. PayPal może w trybie gościa zaoferować płatność kartą.",available3:"✅ Wolne – sprawdzone w aktualnym kalendarzu Booking.",config:"Płatność natychmiastowa nie jest obecnie w pełni dostępna. Wyślij zapytanie.",calendarBlock:"Kalendarz Booking blokuje ten termin. Wybierz inny termin.",luggage:"Transport bagażu ma cenę zależną od trasy. Aby zapłacić od razu, odznacz tę opcję lub najpierw wyślij zapytanie.",unreachable:"Nie można teraz sprawdzić dostępności na żywo. Wyślij zapytanie lub spróbuj później.",preparing:"Przygotowujemy PayPal …",finalCheck:"Dostępność i cena są teraz ostatecznie sprawdzane na serwerze.",paypalError:"⚠️ Nie udało się uruchomić PayPal"},
      nl:{choose:"Kies data",hero:"Boek rechtstreeks zonder boekingsplatform",title:"Boek uw verblijf in de Wachau rechtstreeks",intro:"Kies uw data, controleer de live beschikbaarheid en boek een vrij verblijf veilig via PayPal. PayPal kan ook betaling met een betaalpas of creditcard aanbieden. Als direct boeken niet mogelijk is, kunt u een persoonlijke aanvraag sturen.",trust:"Boek rechtstreeks bij de hosts",trust2:"Live beschikbaarheid, transparante directe prijs en veilige betaling via PayPal; PayPal kan ook kaartbetaling aanbieden.",trust3:"Zonder tussenpersoon of extra boekingsplatform.",tile:"Direct boeken",tile2:"Live beschikbaarheid controleren",request:"Boekingsaanvraag sturen",blocked:"⛔ Bezet – kies andere data",blocked2:"De kamer is voor deze data niet beschikbaar.",blocked3:"⛔ Bezet – kies andere data.",checking:"Beschikbaarheid controleren",checking2:"De beschikbaarheid wordt gecontroleerd met de actuele Booking-kalender …",pay:"Veilig betalen met PayPal",available:"✅ Vrij – veilige rechtstreekse betaling",available2:"De data zijn volgens de actuele Booking-kalender beschikbaar. Voor u naar PayPal gaat, wordt de reservering nogmaals server-side gecontroleerd. PayPal kan in de gastcheckout kaartbetaling aanbieden.",available3:"✅ Vrij – gecontroleerd met de actuele Booking-kalender.",config:"Direct betalen is momenteel niet volledig beschikbaar. Stuur daarom een boekingsaanvraag.",calendarBlock:"De Booking-kalender blokkeert deze data. Kies andere data.",luggage:"Bagagevervoer heeft een routeafhankelijke prijs. Schakel deze optie uit om nu te betalen, of stuur eerst een aanvraag.",unreachable:"Live beschikbaarheid kan momenteel niet worden gecontroleerd. Stuur een aanvraag of probeer het later opnieuw.",preparing:"PayPal voorbereiden …",finalCheck:"Beschikbaarheid en prijs worden nu een laatste keer op de server gecontroleerd.",paypalError:"⚠️ PayPal kon niet worden gestart"}
    };
    const tx=(key)=>T[checkoutLang]?.[key]||T.en[key]||T.de[key]||key;
    const L=(de,en)=>checkoutLang==="de"?de:(checkoutLang==="en"?en:(en||de));

    const requestedLang=(new URLSearchParams(window.location.search).get("lang")||document.documentElement.lang||"de").slice(0,2).toLowerCase();
    const supportedCheckoutLangs=new Set(["de","en","cs","sk","hu","pl","nl"]);
    const checkoutLang=supportedCheckoutLangs.has(requestedLang)?requestedLang:"de";
    const T={
      de:{choose:"Termin wählen",hero:"Direkt buchen ohne Buchungsplattform",title:"Wachau-Etappe direkt buchen",intro:"Reisedaten wählen, Live-Verfügbarkeit prüfen und einen freien Termin sicher mit PayPal direkt buchen. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten. Falls Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.",trust:"Direkt buchen bei den Gastgebern",trust2:"Live-Verfügbarkeit, transparenter Preis und sichere Zahlung über PayPal – auch per Kredit- oder Debitkarte, soweit PayPal dies anbietet.",trust3:"Ohne Provision oder Umweg über eine zusätzliche Buchungsplattform.",tile:"Direkt buchen",tile2:"Verfügbarkeit live prüfen",request:"Buchungsanfrage senden",blocked:"⛔ Belegt – bitte anderen Termin wählen",blocked2:"Das Zimmer ist für diesen Zeitraum bereits belegt.",blocked3:"⛔ Belegt – bitte einen anderen Termin wählen.",checking:"Verfügbarkeit wird geprüft",checking2:"Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …",pay:"Jetzt mit PayPal bezahlen",available:"✅ Termin frei – sichere Direktzahlung",available2:"Termin ist laut aktuellem Booking-Kalender frei. Beim Klick wird der Termin serverseitig reserviert und vor PayPal nochmals sicher geprüft. Eine Kredit-/Debitkartenzahlung kann PayPal im Gast-Checkout anbieten; die tatsächliche Verfügbarkeit bestimmt PayPal.",available3:"✅ Frei – live über den aktuellen Booking-Kalender geprüft.",config:"Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.",calendarBlock:"Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.",luggage:"Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.",unreachable:"Live-Verfügbarkeitsprüfung derzeit nicht erreichbar. Bitte Buchungsanfrage senden oder später erneut versuchen.",preparing:"PayPal wird vorbereitet …",finalCheck:"Verfügbarkeit und Preis werden jetzt serverseitig final geprüft.",paypalError:"⚠️ PayPal konnte nicht gestartet werden"},
      en:{choose:"Choose dates",hero:"Book direct without another booking platform",title:"Book your Wachau stay direct",intro:"Choose your dates, check live availability and book an available stay securely via PayPal. PayPal may also offer debit or credit card payment. If instant booking is unavailable, you can still send a personal request.",trust:"Book directly with your hosts",trust2:"Live availability, transparent direct price and secure payment via PayPal; debit or credit card may also be offered by PayPal.",trust3:"No detour through another booking platform.",tile:"Book direct",tile2:"Check live availability",request:"Send booking request",blocked:"⛔ Unavailable – please choose different dates",blocked2:"The room is unavailable for these dates.",blocked3:"⛔ Unavailable – please choose different dates.",checking:"Checking availability",checking2:"Availability is being checked against the current Booking calendar …",pay:"Pay securely with PayPal",available:"✅ Available – secure direct payment",available2:"These dates are available according to the current Booking calendar. When you continue, the stay is held server-side and checked once more before PayPal. PayPal may offer debit or credit card payment in guest checkout; availability is determined by PayPal.",available3:"✅ Available – checked live against the current Booking calendar.",config:"Instant payment is not fully available right now. Please send a booking request instead.",calendarBlock:"The Booking calendar blocks these dates. Please choose different dates.",luggage:"Luggage transfer has a route-dependent price. Please deselect it to pay for the stay now, or send a request first.",unreachable:"Live availability is temporarily unavailable. Please send a booking request or try again later.",preparing:"Preparing PayPal …",finalCheck:"Availability and price are now being checked one final time on the server.",paypalError:"⚠️ PayPal could not be started"},
      cs:{choose:"Vyberte termín",hero:"Rezervujte přímo bez rezervační platformy",title:"Rezervujte si pobyt ve Wachau přímo",intro:"Vyberte termín, ověřte živou dostupnost a volný pobyt bezpečně rezervujte přes PayPal. PayPal může nabídnout také platbu debetní nebo kreditní kartou. Pokud okamžitá rezervace není možná, můžete odeslat osobní poptávku.",trust:"Rezervace přímo u hostitelů",trust2:"Živá dostupnost, transparentní přímá cena a bezpečná platba přes PayPal; PayPal může nabídnout i platbu kartou.",trust3:"Bez prostředníka a další rezervační platformy.",tile:"Rezervovat přímo",tile2:"Ověřit živou dostupnost",request:"Odeslat poptávku",blocked:"⛔ Obsazeno – vyberte jiný termín",blocked2:"Pokoj není v tomto termínu dostupný.",blocked3:"⛔ Obsazeno – vyberte jiný termín.",checking:"Ověřujeme dostupnost",checking2:"Dostupnost se ověřuje podle aktuálního kalendáře Booking …",pay:"Zaplatit bezpečně přes PayPal",available:"✅ Volno – bezpečná přímá platba",available2:"Termín je podle aktuálního kalendáře Booking volný. Před přesměrováním na PayPal je rezervace na serveru ještě jednou bezpečně ověřena. PayPal může v režimu hosta nabídnout platbu kartou.",available3:"✅ Volno – ověřeno podle aktuálního kalendáře Booking.",config:"Okamžitá platba není nyní plně dostupná. Odešlete prosím poptávku.",calendarBlock:"Kalendář Booking tento termín blokuje. Vyberte jiný termín.",luggage:"Přeprava zavazadel má cenu podle trasy. Pro okamžitou platbu ji zrušte, nebo nejprve odešlete poptávku.",unreachable:"Živou dostupnost nyní nelze ověřit. Odešlete poptávku nebo to zkuste později.",preparing:"Připravujeme PayPal …",finalCheck:"Dostupnost a cena se nyní naposledy ověřují na serveru.",paypalError:"⚠️ PayPal se nepodařilo spustit"},
      sk:{choose:"Vyberte termín",hero:"Rezervujte priamo bez rezervačnej platformy",title:"Rezervujte si pobyt vo Wachau priamo",intro:"Vyberte termín, overte živú dostupnosť a voľný pobyt bezpečne rezervujte cez PayPal. PayPal môže ponúknuť aj platbu debetnou alebo kreditnou kartou. Ak okamžitá rezervácia nie je možná, môžete odoslať osobnú požiadavku.",trust:"Rezervácia priamo u hostiteľov",trust2:"Živá dostupnosť, transparentná priama cena a bezpečná platba cez PayPal; PayPal môže ponúknuť aj platbu kartou.",trust3:"Bez sprostredkovateľa a ďalšej rezervačnej platformy.",tile:"Rezervovať priamo",tile2:"Overiť živú dostupnosť",request:"Odoslať požiadavku",blocked:"⛔ Obsadené – vyberte iný termín",blocked2:"Izba nie je v tomto termíne dostupná.",blocked3:"⛔ Obsadené – vyberte iný termín.",checking:"Overujeme dostupnosť",checking2:"Dostupnosť sa overuje podľa aktuálneho kalendára Booking …",pay:"Zaplatiť bezpečne cez PayPal",available:"✅ Voľné – bezpečná priama platba",available2:"Termín je podľa aktuálneho kalendára Booking voľný. Pred presmerovaním na PayPal sa rezervácia na serveri ešte raz bezpečne overí. PayPal môže v režime hosťa ponúknuť platbu kartou.",available3:"✅ Voľné – overené podľa aktuálneho kalendára Booking.",config:"Okamžitá platba momentálne nie je plne dostupná. Odošlite prosím požiadavku.",calendarBlock:"Kalendár Booking tento termín blokuje. Vyberte iný termín.",luggage:"Preprava batožiny má cenu podľa trasy. Pre okamžitú platbu ju zrušte alebo najprv odošlite požiadavku.",unreachable:"Živú dostupnosť teraz nemožno overiť. Odošlite požiadavku alebo to skúste neskôr.",preparing:"Pripravujeme PayPal …",finalCheck:"Dostupnosť a cena sa teraz naposledy overujú na serveri.",paypalError:"⚠️ PayPal sa nepodarilo spustiť"},
      hu:{choose:"Válasszon dátumot",hero:"Foglaljon közvetlenül foglalási platform nélkül",title:"Foglalja le közvetlenül wachaui tartózkodását",intro:"Válassza ki a dátumokat, ellenőrizze az élő elérhetőséget, és foglalja le biztonságosan a szabad időpontot PayPalon keresztül. A PayPal bank- vagy hitelkártyás fizetést is felajánlhat. Ha az azonnali foglalás nem lehetséges, személyes érdeklődést küldhet.",trust:"Foglalás közvetlenül a házigazdáknál",trust2:"Élő elérhetőség, átlátható közvetlen ár és biztonságos PayPal-fizetés; a PayPal kártyás fizetést is felajánlhat.",trust3:"Közvetítő és további foglalási platform nélkül.",tile:"Közvetlen foglalás",tile2:"Élő elérhetőség ellenőrzése",request:"Foglalási érdeklődés küldése",blocked:"⛔ Foglalt – válasszon másik dátumot",blocked2:"A szoba ezekre a dátumokra nem elérhető.",blocked3:"⛔ Foglalt – válasszon másik dátumot.",checking:"Elérhetőség ellenőrzése",checking2:"Az elérhetőséget az aktuális Booking-naptár alapján ellenőrizzük …",pay:"Biztonságos fizetés PayPallal",available:"✅ Szabad – biztonságos közvetlen fizetés",available2:"A dátum az aktuális Booking-naptár szerint szabad. A PayPalra irányítás előtt a foglalást a szerver még egyszer ellenőrzi. A PayPal vendégként kártyás fizetést is felajánlhat.",available3:"✅ Szabad – az aktuális Booking-naptár alapján ellenőrizve.",config:"Az azonnali fizetés jelenleg nem teljesen elérhető. Küldjön inkább foglalási érdeklődést.",calendarBlock:"A Booking-naptár blokkolja ezt az időpontot. Válasszon másik dátumot.",luggage:"A csomagszállítás ára útvonalfüggő. Az azonnali fizetéshez törölje ezt az opciót, vagy előbb küldjön érdeklődést.",unreachable:"Az élő elérhetőség jelenleg nem ellenőrizhető. Küldjön érdeklődést vagy próbálja később.",preparing:"PayPal előkészítése …",finalCheck:"Az elérhetőséget és az árat a szerver most még egyszer véglegesen ellenőrzi.",paypalError:"⚠️ A PayPal nem indítható"},
      pl:{choose:"Wybierz termin",hero:"Rezerwuj bezpośrednio bez platformy rezerwacyjnej",title:"Zarezerwuj pobyt w Wachau bezpośrednio",intro:"Wybierz termin, sprawdź dostępność na żywo i bezpiecznie zarezerwuj wolny pobyt przez PayPal. PayPal może również zaoferować płatność kartą debetową lub kredytową. Jeśli rezerwacja natychmiastowa nie jest możliwa, możesz wysłać zapytanie.",trust:"Rezerwacja bezpośrednio u gospodarzy",trust2:"Dostępność na żywo, przejrzysta cena bezpośrednia i bezpieczna płatność przez PayPal; PayPal może także zaoferować płatność kartą.",trust3:"Bez pośrednika i dodatkowej platformy rezerwacyjnej.",tile:"Rezerwuj bezpośrednio",tile2:"Sprawdź dostępność na żywo",request:"Wyślij zapytanie",blocked:"⛔ Zajęte – wybierz inny termin",blocked2:"Pokój nie jest dostępny w tym terminie.",blocked3:"⛔ Zajęte – wybierz inny termin.",checking:"Sprawdzamy dostępność",checking2:"Dostępność jest sprawdzana w aktualnym kalendarzu Booking …",pay:"Zapłać bezpiecznie przez PayPal",available:"✅ Wolne – bezpieczna płatność bezpośrednia",available2:"Termin jest wolny według aktualnego kalendarza Booking. Przed przejściem do PayPal rezerwacja jest ponownie bezpiecznie sprawdzana na serwerze. PayPal może w trybie gościa zaoferować płatność kartą.",available3:"✅ Wolne – sprawdzone w aktualnym kalendarzu Booking.",config:"Płatność natychmiastowa nie jest obecnie w pełni dostępna. Wyślij zapytanie.",calendarBlock:"Kalendarz Booking blokuje ten termin. Wybierz inny termin.",luggage:"Transport bagażu ma cenę zależną od trasy. Aby zapłacić od razu, odznacz tę opcję lub najpierw wyślij zapytanie.",unreachable:"Nie można teraz sprawdzić dostępności na żywo. Wyślij zapytanie lub spróbuj później.",preparing:"Przygotowujemy PayPal …",finalCheck:"Dostępność i cena są teraz ostatecznie sprawdzane na serwerze.",paypalError:"⚠️ Nie udało się uruchomić PayPal"},
      nl:{choose:"Kies data",hero:"Boek rechtstreeks zonder boekingsplatform",title:"Boek uw verblijf in de Wachau rechtstreeks",intro:"Kies uw data, controleer de live beschikbaarheid en boek een vrij verblijf veilig via PayPal. PayPal kan ook betaling met een betaalpas of creditcard aanbieden. Als direct boeken niet mogelijk is, kunt u een persoonlijke aanvraag sturen.",trust:"Boek rechtstreeks bij de hosts",trust2:"Live beschikbaarheid, transparante directe prijs en veilige betaling via PayPal; PayPal kan ook kaartbetaling aanbieden.",trust3:"Zonder tussenpersoon of extra boekingsplatform.",tile:"Direct boeken",tile2:"Live beschikbaarheid controleren",request:"Boekingsaanvraag sturen",blocked:"⛔ Bezet – kies andere data",blocked2:"De kamer is voor deze data niet beschikbaar.",blocked3:"⛔ Bezet – kies andere data.",checking:"Beschikbaarheid controleren",checking2:"De beschikbaarheid wordt gecontroleerd met de actuele Booking-kalender …",pay:"Veilig betalen met PayPal",available:"✅ Vrij – veilige rechtstreekse betaling",available2:"De data zijn volgens de actuele Booking-kalender beschikbaar. Voor u naar PayPal gaat, wordt de reservering nogmaals server-side gecontroleerd. PayPal kan in de gastcheckout kaartbetaling aanbieden.",available3:"✅ Vrij – gecontroleerd met de actuele Booking-kalender.",config:"Direct betalen is momenteel niet volledig beschikbaar. Stuur daarom een boekingsaanvraag.",calendarBlock:"De Booking-kalender blokkeert deze data. Kies andere data.",luggage:"Bagagevervoer heeft een routeafhankelijke prijs. Schakel deze optie uit om nu te betalen, of stuur eerst een aanvraag.",unreachable:"Live beschikbaarheid kan momenteel niet worden gecontroleerd. Stuur een aanvraag of probeer het later opnieuw.",preparing:"PayPal voorbereiden …",finalCheck:"Beschikbaarheid en prijs worden nu een laatste keer op de server gecontroleerd.",paypalError:"⚠️ PayPal kon niet worden gestart"}
    };
    const tx=(key)=>T[checkoutLang]?.[key]||T.en[key]||T.de[key]||key;
    const L=(de,en)=>checkoutLang==="de"?de:(checkoutLang==="en"?en:(en||de));

    const checkoutLang=(new URLSearchParams(window.location.search).get("lang")||document.documentElement.lang||"de").slice(0,2).toLowerCase();
    const deCheckout=checkoutLang==="de";
    const L=(de,en)=>deCheckout?de:en;

    const style=document.createElement("style");
    style.textContent='.zab-paypal-primary #submitRequest,.zab-booking-blocked #submitRequest{display:none!important;}';
    document.head.appendChild(style);

    const contactNote=form.querySelector(".checkin-data-note");
    if(paypalBox&&contactNote&&contactNote.nextElementSibling!==paypalBox){
      contactNote.insertAdjacentElement("afterend",paypalBox);
    }

    const isolatedLink=paypalLink.cloneNode(true);
    isolatedLink.id="paypalLink";
    paypalLink.replaceWith(isolatedLink);
    paypalLink=isolatedLink;

    if(paypalHint){
      const isolatedHint=paypalHint.cloneNode(true);
      isolatedHint.id="paypalHint";
      paypalHint.replaceWith(isolatedHint);
      paypalHint=isolatedHint;
    }

    const oldHeading=paypalBox?.querySelector("strong");
    if(oldHeading){
      const isolatedHeading=oldHeading.cloneNode(true);
      oldHeading.replaceWith(isolatedHeading);
    }

    let verifiedSignature="";
    let quoteTimer=0;
    let quoteSequence=0;

    function configured(){
      return /^https:\/\//i.test(apiBase) && !/(PASTE|DEIN|EXAMPLE|RAILWAY-DOMAIN)/i.test(apiBase);
    }

    function value(id){ return (document.getElementById(id)?.value||"").trim(); }
    function selectedRoom(){ return form.querySelector('input[name="room"]:checked'); }
    function selectedExtraByValue(name){
      return Array.from(form.querySelectorAll('input[name="extra"]:checked')).some(x=>x.value===name);
    }

    function etappenAdults(){
      return Math.max(1,Math.min(2,Number(value("adults")||2)));
    }

    function parseLocalDate(text){
      if(!/^\d{4}-\d{2}-\d{2}$/.test(text||"")) return null;
      const parts=text.split("-").map(Number);
      const d=new Date(parts[0],parts[1]-1,parts[2]);
      return Number.isNaN(d.getTime())?null:d;
    }

    function ymd(date){
      const y=date.getFullYear();
      const m=String(date.getMonth()+1).padStart(2,"0");
      const d=String(date.getDate()).padStart(2,"0");
      return `${y}-${m}-${d}`;
    }

    function enforceValidStay(){
      const arrival=document.getElementById("arrival");
      const departure=document.getElementById("departure");
      if(!arrival||!departure) return;
      const a=parseLocalDate(arrival.value);
      if(!a) return;
      const minDeparture=new Date(a.getTime());
      minDeparture.setDate(minDeparture.getDate()+1);
      const minValue=ymd(minDeparture);
      departure.min=minValue;
      const d=parseLocalDate(departure.value);
      if(!d||d<=a) departure.value=minValue;
    }

    function stayNights(){
      const a=parseLocalDate(value("arrival"));
      const d=parseLocalDate(value("departure"));
      if(!a||!d||d<=a) return 0;
      return Math.round((d-a)/86400000);
    }

    function updateEtappenjausePrice(){
      const input=document.getElementById("etappenjauseExtra");
      if(!input) return;
      const amount=12.9*etappenAdults();
      input.dataset.price=String(amount);
      input.dataset.unit="once";
      const price=input.closest(".choice")?.querySelector(".price");
      if(price) price.textContent=`+${amount.toFixed(2).replace(".",",")}`;
    }

    function recalculateVisibleTotal(){
      if(!totalField) return;
      const nights=stayNights();
      if(nights<=0){
        totalField.textContent=tx("choose");
        return;
      }
      const adults=etappenAdults();
      const room=selectedRoom();
      let sum=Number(room?.dataset.price||0)*nights;
      for(const extra of form.querySelectorAll('input[name="extra"]:checked')){
        const price=Number(extra.dataset.price||0);
        const unit=extra.dataset.unit||"once";
        if(unit==="person_night") sum+=price*adults*nights;
        else if(unit==="night") sum+=price*nights;
        else sum+=price;
      }
      totalField.textContent=`${sum.toFixed(2).replace(".",",")} EUR`;
    }

    function refreshPricing(){
      enforceValidStay();
      updateEtappenjausePrice();
      setTimeout(recalculateVisibleTotal,0);
    }

    function installEtappenjause(){
      if(document.getElementById("etappenjauseExtra")) return;
      const extras=form.querySelector(".extras");
      if(!extras) return;
      const luggage=form.querySelector("#luggageTransport")?.closest(".choice");
      const label=document.createElement("label");
      label.className="choice";
      label.innerHTML='<input id="etappenjauseExtra" type="checkbox" name="extra" value="Etappenjause für unterwegs" data-price="25.8" data-unit="once"><span><strong>Etappenjause für unterwegs</strong><small>12,90 EUR pro Person · Weckerl, Obst, kleine Stärkung und Wasser · bitte bis Vorabend bestellen</small></span><b class="price">+25,80</b>';
      if(luggage) extras.insertBefore(label,luggage);
      else extras.appendChild(label);
      updateEtappenjausePrice();
    }

    function promoteDirectBookingSurface(){
      const heroEyebrow=document.querySelector(".hero-copy .eyebrow");
      if(heroEyebrow) heroEyebrow.textContent=tx("hero");
      const bookingTitle=document.getElementById("booking-title");
      if(bookingTitle) bookingTitle.textContent=tx("title");
      const bookingIntro=document.querySelector(".booking-intro");
      if(bookingIntro){
        bookingIntro.textContent=tx("intro");
      }
      const trust=form.closest(".panel")?.querySelector(".direct-booking-trust");
      const trustStrong=trust?.querySelector("strong");
      const trustSpan=trust?.querySelector("span");
      const trustSmall=trust?.querySelector("small");
      if(trustStrong) trustStrong.textContent=tx("trust");
      if(trustSpan) trustSpan.textContent=tx("trust2");
      if(trustSmall) trustSmall.textContent=tx("trust3");
      const bookingTile=document.querySelector(".quick-tile.book");
      const bookingTileTitle=bookingTile?.querySelector("span");
      const bookingTileSmall=bookingTile?.querySelector("small");
      if(bookingTileTitle) bookingTileTitle.textContent=tx("tile");
      if(bookingTileSmall) bookingTileSmall.textContent=tx("tile2");
      if(bookingTile) bookingTile.setAttribute("aria-label",`${tx("tile")} – ${tx("tile2")}`);
      if(submitRequest) submitRequest.textContent=tx("request");
    }

    function setRequestFallback(visible){
      form.classList.remove("zab-booking-blocked");
      form.classList.toggle("zab-paypal-primary",!visible);
      if(visible && submitRequest){
        submitRequest.classList.remove("hidden");
        submitRequest.style.removeProperty("display");
      }
    }

    function payload(){
      const luggage=form.querySelector('#luggageTransport');
      return {
        room:selectedRoom()?.value||"",
        arrival:value("arrival"),
        departure:value("departure"),
        adults:Number(value("adults")||2),
        first_name:value("firstName"),
        last_name:value("lastName"),
        email:value("email"),
        phone:value("phone"),
        message:value("message"),
        extras:{
          breakfast:selectedExtraByValue("Frühstück"),
          jause:selectedExtraByValue("Wachauer Jause"),
          etappenjause:selectedExtraByValue("Etappenjause für unterwegs"),
          luggage:Boolean(luggage?.checked)
        }
      };
    }

    function quoteSignature(data){
      return JSON.stringify({room:data.room,arrival:data.arrival,departure:data.departure,adults:data.adults,extras:data.extras});
    }

    function validDates(data){
      return /^\d{4}-\d{2}-\d{2}$/.test(data.arrival)
        && /^\d{4}-\d{2}-\d{2}$/.test(data.departure)
        && data.departure > data.arrival
        && Boolean(data.room);
    }

    function missingCustomer(data){
      if(!data.first_name) return document.getElementById("firstName");
      if(!data.last_name) return document.getElementById("lastName");
      if(!data.email) return document.getElementById("email");
      if(!data.phone) return document.getElementById("phone");
      return null;
    }

    function checkoutHeading(text){
      const heading=paypalBox?.querySelector("strong");
      if(heading) heading.textContent=text;
    }

    function localCalendarBlocked(){
      return Boolean(availability && availability.classList.contains("blocked"));
    }

    function hidePayPal(message=""){
      verifiedSignature="";
      form.classList.remove("zab-paypal-primary","zab-booking-blocked");
      paypalLink.classList.add("hidden");
      paypalBox?.classList.remove("zab-paypal-ready");
      if(message && paypalHint) paypalHint.textContent=message;
      setRequestFallback(Boolean(message));
    }

    function showBlocked(message){
      verifiedSignature="";
      form.classList.remove("zab-paypal-primary");
      form.classList.add("zab-booking-blocked");
      paypalBox?.classList.remove("hidden","zab-paypal-ready");
      paypalLink.classList.add("hidden");
      checkoutHeading(tx("blocked"));
      if(paypalHint) paypalHint.textContent=message||tx("blocked2");
      if(availability){
        availability.className="availability-status blocked";
        availability.textContent=tx("blocked3");
      }
      if(submitRequest){
        submitRequest.classList.add("hidden");
        submitRequest.style.setProperty("display","none","important");
      }
    }

    function showChecking(){
      form.classList.remove("zab-booking-blocked");
      setRequestFallback(false);
      paypalBox?.classList.remove("hidden");
      paypalBox?.classList.remove("zab-paypal-ready");
      paypalLink.classList.add("hidden");
      checkoutHeading(tx("checking"));
      if(paypalHint) paypalHint.textContent=tx("checking2");
    }

    function showAvailable(data,result){
      if(localCalendarBlocked()){
        showBlocked("Der Booking-Kalender sperrt diesen Zeitraum. Eine Backend-Frei-Meldung darf diese Sperre nicht überschreiben.");
        return false;
      }
      form.classList.remove("zab-booking-blocked");
      setRequestFallback(false);
      verifiedSignature=quoteSignature(data);
      const total=Number(result.total||0);
      paypalBox?.classList.remove("hidden");
      paypalBox?.classList.add("zab-paypal-ready");
      paypalLink.classList.remove("hidden");
      paypalLink.href="#";
      paypalLink.removeAttribute("target");
      paypalLink.removeAttribute("rel");
      paypalLink.dataset.secureCheckout="1";
      paypalLink.textContent=total>0
        ? `${tx("pay")} · ${total.toFixed(2).replace(".", checkoutLang==="de"?",":".")} EUR`
        : tx("pay");
      checkoutHeading(tx("available"));
      if(paypalHint) paypalHint.textContent=tx("available2");
      if(availability){
        availability.className="availability-status ok zab-backend-ok";
        availability.textContent=tx("available3");
      }
    }

    function isClearlyBlocked(result){
      const message=String(result?.message||"").toLowerCase();
      return result?.available===false && /(belegt|direktbuchung|already booked|occupied|not available)/i.test(message);
    }

    async function verifyAvailability(data){
      if(!configured()){
        hidePayPal(tx("config"));
        return false;
      }
      if(!validDates(data)){
        hidePayPal();
        return false;
      }
      if(localCalendarBlocked()){
        showBlocked(tx("calendarBlock"));
        return false;
      }
      if(data.extras.etappenjause){
        hidePayPal("Etappenjause ist ausgewählt. Bitte die Buchungsanfrage senden; die Jause wird für die nächste Etappe vorbereitet und separat bestätigt.");
        return false;
      }
      if(data.extras.luggage){
        hidePayPal(tx("luggage"));
        return false;
      }
      const signature=quoteSignature(data);
      if(verifiedSignature===signature && !paypalLink.classList.contains("hidden")){
        setRequestFallback(false);
        return true;
      }
      const sequence=++quoteSequence;
      showChecking();
      try{
        const response=await fetch(apiBase+"/api/paypal/quote",{
          method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)
        });
        const result=await response.json().catch(()=>({}));
        if(sequence!==quoteSequence) return false;
        if(isClearlyBlocked(result)){
          showBlocked(result.message);
          return false;
        }
        if(!response.ok||!result.ok||!result.available){
          hidePayPal(result.message||"Dieser Termin ist aktuell nicht für eine Sofortbuchung verfügbar.");
          return false;
        }
        showAvailable(data,result);
        return true;
      }catch(error){
        if(sequence!==quoteSequence) return false;
        hidePayPal(tx("unreachable"));
        return false;
      }
    }

    function scheduleVerification(){
      clearTimeout(quoteTimer);
      verifiedSignature="";
      quoteTimer=setTimeout(()=>verifyAvailability(payload()),350);
    }

    async function startCheckout(event){
      event.preventDefault();
      event.stopImmediatePropagation();
      const data=payload();
      if(localCalendarBlocked()){
        showBlocked(tx("calendarBlock"));
        return;
      }
      const missing=missingCustomer(data);
      if(missing){
        missing.focus();
        missing.scrollIntoView({behavior:"smooth",block:"center"});
        checkoutHeading("Kontaktdaten vervollständigen");
        if(paypalHint) paypalHint.textContent="Für die Sofortbuchung bitte zuerst Name, E-Mail und Telefonnummer vollständig eintragen.";
        return;
      }
      if(data.extras.etappenjause){
        if(paypalHint) paypalHint.textContent="Die Etappenjause wird über die persönliche Buchungsanfrage bestätigt. Bitte dafür die Buchungsanfrage senden.";
        document.getElementById("etappenjauseExtra")?.focus();
        setRequestFallback(true);
        return;
      }
      if(data.extras.luggage){
        if(paypalHint) paypalHint.textContent="Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.";
        document.getElementById("luggageTransport")?.focus();
        return;
      }
      const oldText=paypalLink.textContent;
      paypalLink.setAttribute("aria-busy","true");
      paypalLink.textContent="Termin wird reserviert und PayPal vorbereitet …";
      paypalLink.style.pointerEvents="none";
      checkoutHeading(tx("preparing"));
      if(paypalHint) paypalHint.textContent=tx("finalCheck");
      try{
        const response=await fetch(apiBase+"/api/paypal/create-order",{
          method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)
        });
        const result=await response.json().catch(()=>({}));
        if(!response.ok||!result.ok||!result.approval_url) throw new Error(result.message||"PayPal-Checkout konnte nicht gestartet werden.");
        window.zabTrack?.("direct_paypal_checkout_started",{booking_id:result.booking_id,order_id:result.order_id,total:result.total});
        window.location.assign(result.approval_url);
      }catch(error){
        paypalLink.textContent=oldText;
        paypalLink.style.pointerEvents="";
        paypalLink.removeAttribute("aria-busy");
        paypalLink.href="#";
        paypalLink.removeAttribute("target");
        paypalLink.classList.remove("hidden");
        paypalBox?.classList.add("zab-paypal-ready");
        setRequestFallback(true);
        checkoutHeading(tx("paypalError"));
        if(paypalHint){
          paypalHint.textContent="Sofortbuchung nicht gestartet: "+(error.message||error)+" Bitte nicht mehrfach klicken; bei Bedarf die Buchungsanfrage senden.";
          paypalHint.style.fontWeight="800";
          paypalHint.style.color="#8b2f1f";
        }
      }
    }

    installEtappenjause();
    promoteDirectBookingSurface();
    refreshPricing();

    form.addEventListener("change",function(event){
      if(event.target?.id==="arrival") enforceValidStay();
      refreshPricing();
      scheduleVerification();
    },true);

    form.addEventListener("input",function(event){
      const id=event.target?.id||"";
      const name=event.target?.name||"";
      if(["arrival","departure","adults","luggageTransport","etappenjauseExtra"].includes(id)||["room","extra"].includes(name)){
        refreshPricing();
        scheduleVerification();
      }
    },true);

    paypalLink.removeAttribute("target");
    paypalLink.removeAttribute("rel");
    paypalLink.href="#";
    paypalLink.addEventListener("click",startCheckout,true);

    // The primary form CTA must enter the same secure checkout path.
    // This prevents the legacy inquiry handler from winning on mobile when
    // a stay is eligible for instant direct booking.
    form.addEventListener("submit", async function(event){
      const data=payload();
      if(!configured() || !validDates(data) || data.extras.etappenjause || data.extras.luggage){
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();

      const ok=await verifyAvailability(data);
      if(!ok){
        setRequestFallback(true);
        paypalBox?.scrollIntoView({behavior:"smooth",block:"center"});
        return;
      }

      const missing=missingCustomer(data);
      if(missing){
        missing.focus();
        missing.scrollIntoView({behavior:"smooth",block:"center"});
        checkoutHeading(checkoutLang==="de" ? "Kontaktdaten vervollständigen" : "Complete your contact details");
        if(paypalHint) paypalHint.textContent=checkoutLang==="de"
          ? "Für die Sofortbuchung bitte zuerst Name, E-Mail und Telefonnummer vollständig eintragen."
          : "Please complete your name, email address and phone number before direct checkout.";
        return;
      }

      await startCheckout({preventDefault(){},stopImmediatePropagation(){}});
    },true);

    if(!configured()){
      hidePayPal("Sofortzahlung wird nach Einrichtung des sicheren PayPal-Checkouts aktiviert. Bis dahin bitte Buchungsanfrage senden.");
      return;
    }

    scheduleVerification();
  },0);
});
})();
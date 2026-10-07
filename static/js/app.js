const checkoutLang = new URLSearchParams(window.location.search).get("lang") || "de";
const I18N = {
  de:{blocked:"⛔ Termin nicht verfügbar.",roomLabel:"Zimmer",afterCheck:"Nach Verfügbarkeitsprüfung",missing:"Bitte Reisedaten und Zimmer auswählen.",checking:"Verfügbarkeit wird geprüft …",fail:"Die Prüfung konnte nicht durchgeführt werden.",free:"✅ Termin frei – direkt buchbar.",unknown:"Verfügbarkeit bitte persönlich anfragen.",paypal:"MIT PAYPAL BEZAHLEN",paypalNote:"Nach dem Klick prüfen wir den Termin erneut und öffnen PayPal. Nach erfolgreicher Zahlung ist eure Buchung bestätigt. Ohne abgeschlossene Zahlung entsteht keine bestätigte Buchung.",bank:"ANFRAGE SENDEN & BANKDATEN ERHALTEN",bankNote:"Die Bankverbindung wird direkt angezeigt. Der Termin wird erst nach persönlicher Bestätigung verbindlich reserviert.",onsite:"BUCHUNGSANFRAGE SENDEN",onsiteNote:"Ihr sendet zunächst eine Anfrage. Bitte bestätigt eure E-Mail innerhalb von 2 Stunden; danach wird der Zeitraum vorläufig reserviert. Verbindlich wird die Buchung mit unserer persönlichen Bestätigung. Zahlung bei Anreise; weniger als 3 Tage vorher nicht verfügbar.",personal:"VERFÜGBARKEIT PERSÖNLICH ANFRAGEN",stickyBook:"Jetzt direkt buchen",stickyAsk:"Persönlich anfragen",book:"Buchen",ask:"Anfragen",sending:"Anfrage wird gesendet …",paypalPrep:"PAYPAL WIRD VORBEREITET …",finalCheck:"Verfügbarkeit und Preis werden nochmals sicher geprüft.",paypalOpen:"PAYPAL WIRD GEÖFFNET …",calendarLive:"Live-Kalender aktuell",calendarDown:"Live-Kalender derzeit nicht erreichbar – freie Tage werden nicht automatisch bestätigt.",months:["Jänner","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],days:["Mo","Di","Mi","Do","Fr","Sa","So"]},
  cs:{blocked:"⛔ Termín není dostupný.",roomLabel:"Pokoj",afterCheck:"Po ověření dostupnosti",missing:"Vyberte prosím termín a pokoj.",checking:"Ověřujeme dostupnost …",fail:"Dostupnost se nepodařilo ověřit.",free:"✅ Termín je volný – můžete rezervovat přímo.",unknown:"Dostupnost prosím ověřte osobně.",paypal:"ZAPLATIT PŘES PAYPAL",paypalNote:"Po kliknutí ještě jednou ověříme termín a poté se otevře zabezpečená platba přes PayPal.",bank:"ODESLAT POPTÁVKU A ZÍSKAT BANKOVNÍ ÚDAJE",bankNote:"Bankovní údaje se zobrazí přímo. Termín je závazně rezervován až po našem osobním potvrzení.",onsite:"ODESLAT POPTÁVKU",onsiteNote:"Termín je závazně rezervován až po našem osobním potvrzení. Platba proběhne při příjezdu.",personal:"OSOBNĚ OVĚŘIT DOSTUPNOST",stickyBook:"Rezervovat přímo",stickyAsk:"Osobní dotaz",book:"Rezervovat",ask:"Zeptat se",sending:"Odesíláme poptávku …",paypalPrep:"PŘIPRAVUJEME PAYPAL …",finalCheck:"Ještě jednou bezpečně ověřujeme dostupnost a cenu.",paypalOpen:"OTEVÍRÁME PAYPAL …",calendarLive:"Aktuální kalendář",calendarDown:"Aktuální kalendář není právě dostupný – volné dny proto automaticky nepotvrzujeme.",months:["leden","únor","březen","duben","květen","červen","červenec","srpen","září","říjen","listopad","prosinec"],days:["Po","Út","St","Čt","Pá","So","Ne"]},
  sk:{blocked:"⛔ Termín nie je dostupný.",roomLabel:"Izba",afterCheck:"Po overení dostupnosti",missing:"Vyberte si prosím termín a izbu.",checking:"Overujeme dostupnosť …",fail:"Dostupnosť sa nepodarilo overiť.",free:"✅ Termín je voľný – môžete rezervovať priamo.",unknown:"Dostupnosť si prosím overte osobne.",paypal:"ZAPLATIŤ CEZ PAYPAL",paypalNote:"Po kliknutí ešte raz overíme termín a potom sa otvorí zabezpečená platba cez PayPal.",bank:"ODOSLAŤ POŽIADAVKU A ZÍSKAŤ BANKOVÉ ÚDAJE",bankNote:"Bankové údaje sa zobrazia priamo. Termín je záväzne rezervovaný až po našom osobnom potvrdení.",onsite:"ODOSLAŤ POŽIADAVKU",onsiteNote:"Termín je záväzne rezervovaný až po našom osobnom potvrdení. Platba prebehne pri príchode.",personal:"OSOBNE OVERIŤ DOSTUPNOSŤ",stickyBook:"Rezervovať priamo",stickyAsk:"Osobná požiadavka",book:"Rezervovať",ask:"Opýtať sa",sending:"Odosielame požiadavku …",paypalPrep:"PRIPRAVUJEME PAYPAL …",finalCheck:"Ešte raz bezpečne overujeme dostupnosť a cenu.",paypalOpen:"OTVÁRAME PAYPAL …",calendarLive:"Aktuálny kalendár",calendarDown:"Aktuálny kalendár momentálne nie je dostupný – voľné dni preto automaticky nepotvrdzujeme.",months:["január","február","marec","apríl","máj","jún","júl","august","september","október","november","december"],days:["Po","Ut","St","Št","Pi","So","Ne"]},
  en:{blocked:"⛔ These dates are not available.",roomLabel:"Room",afterCheck:"After availability check",missing:"Please select travel dates and a room.",checking:"Checking availability …",fail:"Availability could not be checked.",free:"✅ Available – book direct.",unknown:"Please request availability personally.",paypal:"PAY SECURELY WITH PAYPAL",paypalNote:"We check your dates again before opening PayPal. Your booking is confirmed after successful payment. An unfinished payment does not confirm a booking.",bank:"SEND REQUEST & GET BANK DETAILS",bankNote:"Bank details will be shown directly. The stay becomes binding only after our personal confirmation.",onsite:"SEND BOOKING REQUEST",onsiteNote:"The stay becomes binding only after our personal confirmation. Payment is made on arrival.",personal:"REQUEST AVAILABILITY",stickyBook:"Book direct",stickyAsk:"Send request",book:"Book",ask:"Request",sending:"Sending request …",paypalPrep:"PREPARING PAYPAL …",finalCheck:"Availability and price are being checked once more.",paypalOpen:"OPENING PAYPAL …",calendarLive:"Live calendar up to date",calendarDown:"Live calendar is currently unavailable – free dates are not automatically confirmed.",months:["January","February","March","April","May","June","July","August","September","October","November","December"],days:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]},
  hu:{blocked:"⛔ Ez az időpont nem elérhető.",roomLabel:"Szoba",afterCheck:"Elérhetőség ellenőrzése után",missing:"Kérjük, válasszon dátumot és szobát.",checking:"Elérhetőség ellenőrzése …",fail:"Az elérhetőség ellenőrzése nem sikerült.",free:"✅ Szabad – közvetlenül foglalható.",unknown:"Kérjük, érdeklődjön személyesen az elérhetőségről.",paypal:"BIZTONSÁGOS FIZETÉS PAYPALLAL",paypalNote:"A PayPal megnyitása előtt még egyszer ellenőrizzük a dátumot.",bank:"ÉRDEKLŐDÉS KÜLDÉSE ÉS BANKI ADATOK",bankNote:"A banki adatok közvetlenül megjelennek. A foglalás személyes visszaigazolásunk után válik véglegessé.",onsite:"FOGLALÁSI ÉRDEKLŐDÉS KÜLDÉSE",onsiteNote:"A foglalás személyes visszaigazolásunk után válik véglegessé. Fizetés érkezéskor.",personal:"ELÉRHETŐSÉG KÉRÉSE",stickyBook:"Közvetlen foglalás",stickyAsk:"Érdeklődés",book:"Foglalás",ask:"Érdeklődés",sending:"Érdeklődés küldése …",paypalPrep:"PAYPAL ELŐKÉSZÍTÉSE …",finalCheck:"Az elérhetőséget és az árat még egyszer ellenőrizzük.",paypalOpen:"PAYPAL MEGNYITÁSA …",calendarLive:"Élő naptár aktuális",calendarDown:"Az élő naptár jelenleg nem elérhető – a szabad napokat nem erősítjük meg automatikusan.",months:["január","február","március","április","május","június","július","augusztus","szeptember","október","november","december"],days:["H","K","Sze","Cs","P","Szo","V"]},
  nl:{blocked:"⛔ Deze data zijn niet beschikbaar.",roomLabel:"Kamer",afterCheck:"Na controle van beschikbaarheid",missing:"Kies uw reisdata en kamer.",checking:"Beschikbaarheid controleren …",fail:"Beschikbaarheid kon niet worden gecontroleerd.",free:"✅ Beschikbaar – direct boeken.",unknown:"Vraag de beschikbaarheid persoonlijk aan.",paypal:"VEILIG BETALEN MET PAYPAL",paypalNote:"We controleren de data nog één keer voordat de beveiligde PayPal-checkout opent.",bank:"AANVRAAG VERSTUREN & BANKGEGEVENS ONTVANGEN",bankNote:"De bankgegevens worden direct getoond. De reservering is pas definitief na onze persoonlijke bevestiging.",onsite:"BOEKINGSAANVRAAG VERSTUREN",onsiteNote:"De reservering is pas definitief na onze persoonlijke bevestiging. Betaling bij aankomst.",personal:"BESCHIKBAARHEID AANVRAGEN",stickyBook:"Direct boeken",stickyAsk:"Aanvragen",book:"Boeken",ask:"Aanvragen",sending:"Aanvraag wordt verzonden …",paypalPrep:"PAYPAL VOORBEREIDEN …",finalCheck:"Beschikbaarheid en prijs worden nogmaals gecontroleerd.",paypalOpen:"PAYPAL WORDT GEOPEND …",calendarLive:"Live kalender actueel",calendarDown:"De live kalender is momenteel niet bereikbaar – vrije dagen worden niet automatisch bevestigd.",months:["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"],days:["ma","di","wo","do","vr","za","zo"]},
  pl:{blocked:"⛔ Ten termin nie jest dostępny.",roomLabel:"Pokój",afterCheck:"Po sprawdzeniu dostępności",missing:"Wybierz termin i pokój.",checking:"Sprawdzamy dostępność …",fail:"Nie udało się sprawdzić dostępności.",free:"✅ Termin wolny – rezerwuj bezpośrednio.",unknown:"Zapytaj nas o dostępność.",paypal:"ZAPŁAĆ BEZPIECZNIE PRZEZ PAYPAL",paypalNote:"Przed otwarciem bezpiecznej płatności PayPal ponownie sprawdzimy termin.",bank:"WYŚLIJ ZAPYTANIE I OTRZYMAJ DANE BANKOWE",bankNote:"Dane bankowe zostaną wyświetlone bezpośrednio. Rezerwacja staje się wiążąca po naszym osobistym potwierdzeniu.",onsite:"WYŚLIJ ZAPYTANIE O REZERWACJĘ",onsiteNote:"Rezerwacja staje się wiążąca po naszym osobistym potwierdzeniu. Płatność przy przyjeździe.",personal:"ZAPYTAJ O DOSTĘPNOŚĆ",stickyBook:"Rezerwuj bezpośrednio",stickyAsk:"Wyślij zapytanie",book:"Rezerwuj",ask:"Zapytaj",sending:"Wysyłanie zapytania …",paypalPrep:"PRZYGOTOWUJEMY PAYPAL …",finalCheck:"Ponownie sprawdzamy dostępność i cenę.",paypalOpen:"OTWIERAMY PAYPAL …",calendarLive:"Kalendarz na żywo aktualny",calendarDown:"Kalendarz na żywo jest obecnie niedostępny – wolne dni nie są automatycznie potwierdzane.",months:["styczeń","luty","marzec","kwiecień","maj","czerwiec","lipiec","sierpień","wrzesień","październik","listopad","grudzień"],days:["pon.","wt.","śr.","czw.","pt.","sob.","niedz."]},
  it:{blocked:"⛔ Queste date non sono disponibili.",roomLabel:"Camera",afterCheck:"Dopo la verifica della disponibilità",missing:"Seleziona le date e la camera.",checking:"Verifica disponibilità …",fail:"Non è stato possibile verificare la disponibilità.",free:"✅ Disponibile – prenota direttamente.",unknown:"Richiedi la disponibilità direttamente.",paypal:"PAGA IN SICUREZZA CON PAYPAL",paypalNote:"Controlleremo ancora una volta le date prima di aprire il pagamento sicuro con PayPal.",bank:"INVIA RICHIESTA E RICEVI I DATI BANCARI",bankNote:"I dati bancari vengono mostrati direttamente. La prenotazione diventa vincolante solo dopo la nostra conferma personale.",onsite:"INVIA RICHIESTA DI PRENOTAZIONE",onsiteNote:"La prenotazione diventa vincolante solo dopo la nostra conferma personale. Pagamento all'arrivo.",personal:"RICHIEDI DISPONIBILITÀ",stickyBook:"Prenota direttamente",stickyAsk:"Invia richiesta",book:"Prenota",ask:"Richiedi",sending:"Invio richiesta …",paypalPrep:"PREPARAZIONE PAYPAL …",finalCheck:"Disponibilità e prezzo vengono verificati ancora una volta.",paypalOpen:"APERTURA PAYPAL …",calendarLive:"Calendario aggiornato",calendarDown:"Il calendario live non è disponibile al momento – le date libere non vengono confermate automaticamente.",months:["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"],days:["lun","mar","mer","gio","ven","sab","dom"]},
  es:{blocked:"⛔ Estas fechas no están disponibles.",roomLabel:"Habitación",afterCheck:"Después de comprobar la disponibilidad",missing:"Seleccione las fechas y la habitación.",checking:"Comprobando disponibilidad …",fail:"No se pudo comprobar la disponibilidad.",free:"✅ Disponible – reserve directamente.",unknown:"Consulte la disponibilidad directamente.",paypal:"PAGAR DE FORMA SEGURA CON PAYPAL",paypalNote:"Volveremos a comprobar las fechas antes de abrir el pago seguro de PayPal.",bank:"ENVIAR SOLICITUD Y RECIBIR DATOS BANCARIOS",bankNote:"Los datos bancarios se mostrarán directamente. La reserva será vinculante después de nuestra confirmación personal.",onsite:"ENVIAR SOLICITUD DE RESERVA",onsiteNote:"La reserva será vinculante después de nuestra confirmación personal. Pago a la llegada.",personal:"CONSULTAR DISPONIBILIDAD",stickyBook:"Reservar directamente",stickyAsk:"Consultar",book:"Reservar",ask:"Consultar",sending:"Enviando solicitud …",paypalPrep:"PREPARANDO PAYPAL …",finalCheck:"Volvemos a comprobar la disponibilidad y el precio.",paypalOpen:"ABRIENDO PAYPAL …",calendarLive:"Calendario actualizado",calendarDown:"El calendario en vivo no está disponible en este momento – las fechas libres no se confirman automáticamente.",months:["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],days:["lun","mar","mié","jue","vie","sáb","dom"]},
  fr:{blocked:"⛔ Ces dates ne sont pas disponibles.",roomLabel:"Chambre",afterCheck:"Après vérification des disponibilités",missing:"Veuillez choisir vos dates et la chambre.",checking:"Vérification des disponibilités …",fail:"Impossible de vérifier les disponibilités.",free:"✅ Disponible – réservez en direct.",unknown:"Veuillez demander les disponibilités directement.",paypal:"PAYER EN TOUTE SÉCURITÉ AVEC PAYPAL",paypalNote:"Nous vérifions encore une fois les dates avant d'ouvrir le paiement sécurisé PayPal.",bank:"ENVOYER LA DEMANDE ET RECEVOIR LES COORDONNÉES BANCAIRES",bankNote:"Les coordonnées bancaires s'affichent directement. La réservation devient ferme après notre confirmation personnelle.",onsite:"ENVOYER UNE DEMANDE DE RÉSERVATION",onsiteNote:"La réservation devient ferme après notre confirmation personnelle. Paiement à l'arrivée.",personal:"DEMANDER LES DISPONIBILITÉS",stickyBook:"Réserver en direct",stickyAsk:"Demander",book:"Réserver",ask:"Demander",sending:"Envoi de la demande …",paypalPrep:"PRÉPARATION DE PAYPAL …",finalCheck:"Les disponibilités et le prix sont vérifiés une dernière fois.",paypalOpen:"OUVERTURE DE PAYPAL …",calendarLive:"Calendrier à jour",calendarDown:"Le calendrier en direct est actuellement indisponible – les dates libres ne sont pas confirmées automatiquement.",months:["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"],days:["lun","mar","mer","jeu","ven","sam","dim"]},
  ar:{blocked:"⛔ هذه التواريخ غير متاحة.",roomLabel:"الغرفة",afterCheck:"بعد التحقق من التوافر",missing:"يرجى اختيار تواريخ السفر والغرفة.",checking:"جارٍ التحقق من التوافر …",fail:"تعذر التحقق من التوافر.",free:"✅ الموعد متاح – يمكنك الحجز مباشرة.",unknown:"يرجى الاستفسار عن التوافر مباشرة.",paypal:"الدفع بأمان عبر PAYPAL",paypalNote:"سنتحقق من الموعد مرة أخرى قبل فتح الدفع الآمن عبر PayPal.",bank:"إرسال الطلب واستلام بيانات البنك",bankNote:"ستظهر بيانات البنك مباشرة. يصبح الحجز ملزماً فقط بعد تأكيدنا الشخصي.",onsite:"إرسال طلب الحجز",onsiteNote:"يصبح الحجز ملزماً فقط بعد تأكيدنا الشخصي. يتم الدفع عند الوصول.",personal:"الاستفسار عن التوافر",stickyBook:"احجز مباشرة",stickyAsk:"استفسر",book:"احجز",ask:"استفسر",sending:"جارٍ إرسال الطلب …",paypalPrep:"جارٍ تجهيز PAYPAL …",finalCheck:"نعيد التحقق من التوافر والسعر.",paypalOpen:"جارٍ فتح PAYPAL …",calendarLive:"التقويم المباشر محدث",calendarDown:"التقويم المباشر غير متاح حالياً – لا يتم تأكيد الأيام الشاغرة تلقائياً.",months:["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"],days:["اث","ثل","أر","خم","جم","سب","أح"]},
  ch:{blocked:"⛔ Dä Termin isch nöd verfügbar.",roomLabel:"Zimmer",afterCheck:"Nach de Verfügbarkeitsprüefig",missing:"Bitte Reisedate und Zimmer uswähle.",checking:"Verfügbarkeit wird prüeft …",fail:"D Verfügbarkeit het nöd chöne prüeft werde.",free:"✅ Termin frei – direkt buechbar.",unknown:"Bitte Verfügbarkeit persönlich afrage.",paypal:"SICHER MIT PAYPAL ZAHLE",paypalNote:"Vor em sichere PayPal-Checkout prüefed mir de Termin no einisch.",bank:"AFRAG SENDE & BANKDATE ERHALTE",bankNote:"D Bankdate werded direkt azeigt. D Reservation wird erscht nach üsere persönliche Bestätigung verbindlich.",onsite:"BUCHIGSAFRAG SENDE",onsiteNote:"D Reservation wird erscht nach üsere persönliche Bestätigung verbindlich. Zahlig bi de Aareis.",personal:"VERFÜGBARKEIT AFRAGE",stickyBook:"Direkt bueche",stickyAsk:"Afrage",book:"Bueche",ask:"Afrage",sending:"Afrag wird gsendet …",paypalPrep:"PAYPAL WIRD VORBEREITET …",finalCheck:"Verfügbarkeit und Priis werded no einisch sicher prüeft.",paypalOpen:"PAYPAL WIRD UFGMACHT …",calendarLive:"Live-Kalender aktuell",calendarDown:"De Live-Kalender isch grad nöd erreichbar – freii Täg werded nöd automatisch bestätigt.",months:["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],days:["Mo","Di","Mi","Do","Fr","Sa","So"]}
};
const tx=(key)=> (I18N[checkoutLang] || I18N.de)[key] || I18N.de[key];


const arrival = document.getElementById("arrival");
const departure = document.getElementById("departure");
const adults = document.getElementById("adults");
const extraIds=["breakfast","jause","luggage","dog","baby_bed"];
const extraInputs=extraIds.map(x=>document.getElementById(x)).filter(Boolean);
const priceBreakdown=document.getElementById("priceBreakdown");
const couponCode = document.getElementById("couponCode");
const nightsEl = document.getElementById("nights");
const totalPrice = document.getElementById("totalPrice");
const result = document.getElementById("availabilityResult");
const guestArea = document.getElementById("guestArea");
const roomRadios = [...document.querySelectorAll('input[name="room"]')];
const bookingSubmit = document.getElementById("bookingSubmit");
const stickyLabel = document.getElementById("stickyLabel");
const stickyCta = document.getElementById("stickyCta");
const paymentRadios = [...document.querySelectorAll('input[name="payment_method"]')];
const paymentNotice = document.getElementById("paymentNotice");
const bankTransferDetails = document.getElementById("bankTransferDetails");
const bookingSummary = document.getElementById("bookingSummary");
const summaryDates = document.getElementById("summaryDates");
const summaryNights = document.getElementById("summaryNights");
const summaryGuests = document.getElementById("summaryGuests");
const summaryExtras = document.getElementById("summaryExtras");
const summaryPayment = document.getElementById("summaryPayment");
const summaryTotal = document.getElementById("summaryTotal");
let checkoutOpen = false;
let bookingSubmitted = false;
let lastQuotedTotal = null;
let guestDetailsTracked = false;

function track(event) {
  const body = JSON.stringify({event});
  if (navigator.sendBeacon && event === "booking_abandoned") {
    navigator.sendBeacon("/api/events", new Blob([body], {type:"application/json"}));
    return;
  }
  fetch("/api/events", {method:"POST", headers:{"Content-Type":"application/json"}, body, keepalive:true}).catch(()=>{});
}

const DEMAND_TRACKING_URL = "https://direcktbuchungen-production.up.railway.app/api/demand-event";
function trackDemand(event, details = {}) {
  const body = JSON.stringify({event, details:{...details, language:checkoutLang, room:selectedRoom()?.value || "Bachblick"}});
  fetch(DEMAND_TRACKING_URL, {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body,
    keepalive:true,
    mode:"cors"
  }).catch(()=>{});
}

document.getElementById("idempotencyKey").value =
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
track("landing_view");
trackDemand("page_view");
const bookingSection=document.getElementById("booking");
if (bookingSection && "IntersectionObserver" in window) {
  let bookingViewed=false;
  const observer=new IntersectionObserver(entries=>{
    if(!bookingViewed && entries.some(e=>e.isIntersecting)){
      bookingViewed=true;
      track("booking_section_view");
      observer.disconnect();
    }
  },{threshold:.25});
  observer.observe(bookingSection);
}

function selectedRoom() {
  return document.querySelector('input[name="room"]:checked');
}

function nights() {
  if (!arrival.value || !departure.value) return 0;
  const a = new Date(arrival.value + "T12:00:00");
  const b = new Date(departure.value + "T12:00:00");
  return Math.max(0, Math.round((b-a)/86400000));
}

function euro(v) {
  const localeMap={de:"de-AT",en:"en-GB",cs:"cs-CZ",sk:"sk-SK",hu:"hu-HU",nl:"nl-NL",pl:"pl-PL",it:"it-IT",fr:"fr-FR",es:"es-ES",ar:"ar-SA",ch:"de-CH"};
  return new Intl.NumberFormat(localeMap[checkoutLang]||"de-AT", {style:"currency", currency:"EUR"}).format(v);
}

function updateBookingSummary() {
  if (!bookingSummary) return;
  if (summaryDates) summaryDates.textContent = arrival.value && departure.value ? `${arrival.value} – ${departure.value}` : "–";
  if (summaryNights) summaryNights.textContent = nights() ? String(nights()) : "–";
  if (summaryGuests) summaryGuests.textContent = adults.value || "–";
  if (summaryPayment) summaryPayment.textContent = selectedPayment();
  if (summaryTotal) summaryTotal.textContent = lastQuotedTotal != null ? euro(lastQuotedTotal) : "–";
  if (summaryExtras) {
    const labels = extraInputs.filter(el=>el.checked).map(el=>el.closest("label")?.querySelector("strong")?.textContent?.trim()).filter(Boolean);
    summaryExtras.textContent = labels.length ? labels.join(", ") : "Keine";
  }
}

function updateTotals() {
  const n = nights();
  nightsEl.value = n;
  totalPrice.textContent = n ? tx("afterCheck") : "ab 99,00 € / Nacht";
  priceBreakdown.innerHTML = "";
}

function updateRoomRelease() {
  const selectedArrival = arrival.value;
  roomRadios.forEach(radio => {
    const card = radio.closest(".room-option");
    const disabled = Boolean(selectedArrival && selectedArrival < radio.dataset.from);
    radio.disabled = disabled;
    card.classList.toggle("disabled", disabled);
  });
  if (selectedRoom()?.disabled) {
    document.querySelector('input[name="room"][value="Bachblick"]').checked = true;
  }
  updateTotals();
}

function selectedPayment() {
  return document.querySelector('input[name="payment_method"]:checked')?.value || "PayPal";
}

function onsiteAllowedForArrival() {
  if (!arrival.value) return true;
  const chosen = new Date(arrival.value + "T12:00:00");
  const today = new Date();
  today.setHours(12,0,0,0);
  return Math.round((chosen - today) / 86400000) >= 3;
}

function updateOnsiteOption() {
  const onsiteRadio = document.querySelector('input[name="payment_method"][value="Vor Ort"]');
  if (!onsiteRadio) return;
  const allowed = onsiteAllowedForArrival();
  onsiteRadio.disabled = !allowed;
  const card = onsiteRadio.closest("label");
  if (card) {
    card.classList.toggle("disabled", !allowed);
    const small = card.querySelector("small");
    if (small && checkoutLang === "de") {
      small.textContent = allowed
        ? "E-Mail-Bestätigung innerhalb von 2 Stunden"
        : "Nicht verfügbar bei Anreise in weniger als 3 Tagen";
    }
  }
  if (!allowed && onsiteRadio.checked) {
    const bank = document.querySelector('input[name="payment_method"][value="Banküberweisung"]');
    if (bank) bank.checked = true;
  }
}

function updatePaymentUI() {
  updateOnsiteOption();
  const method = selectedPayment();

  bookingSubmit.disabled = false;
  bookingSubmit.removeAttribute("aria-busy");

  if (bankTransferDetails) {
    bankTransferDetails.classList.toggle("hidden", method !== "Banküberweisung");
  }

  if (method === "PayPal") {
    bookingSubmit.textContent = tx("paypal");
    if (paymentNotice) paymentNotice.textContent = tx("paypalNote");
  } else if (method === "Banküberweisung") {
    bookingSubmit.textContent = tx("bank");
    if (paymentNotice) paymentNotice.textContent = tx("bankNote");
  } else {
    bookingSubmit.textContent = tx("onsite");
    if (paymentNotice) paymentNotice.textContent = tx("onsiteNote");
  }
  updateBookingSummary();
}
function resetAvailability() {
  result.classList.add("hidden");
  guestArea.classList.add("hidden");
  lastQuotedTotal = null;
  updateBookingSummary();
}

arrival.addEventListener("change", () => {
  if (arrival.value) {
    const d = new Date(arrival.value + "T12:00:00");
    d.setDate(d.getDate()+1);
    departure.min = d.toISOString().slice(0,10);
    if (!departure.value || departure.value <= arrival.value) departure.value = departure.min;
  }
  updateOnsiteOption();
  updateRoomRelease();
  resetAvailability();
});

[departure, adults, ...extraInputs, ...roomRadios].forEach(el => {
  el.addEventListener("change", () => {
    if (el.matches('input[name="room"]')) track("room_selected");
    if (extraInputs.includes(el)) track("extras_selected");
    updateTotals();
    updateBookingSummary();
    resetAvailability();
  });
});

document.getElementById("checkAvailability").addEventListener("click", async () => {
  if (!arrival.value || !departure.value || !selectedRoom()) {
    result.textContent = tx("missing");
    result.className = "availability-result bad";
    return;
  }
  const fd = new FormData();
  fd.append("arrival", arrival.value);
  fd.append("departure", departure.value);
  fd.append("room", selectedRoom().value);
  fd.append("adults", adults.value);
  extraIds.forEach(id=>{const el=document.getElementById(id);fd.append(id,el&&el.checked?"true":"false")});
  fd.append("coupon_code", couponCode?.value.trim() || "");

  result.textContent = tx("checking");
  result.className = "availability-result";
  track("availability_started");
  trackDemand("dates_selected", {
    arrival:arrival.value,
    departure:departure.value,
    nights:nights()
  });

  try {
    const response = await fetch("/api/availability", {method:"POST", body:fd});
    const data = await response.json();
    const status = data.status || (data.available === true ? "free" : data.available === false ? "blocked" : "unknown");
    result.textContent = checkoutLang === "de"
      ? data.message
      : (status === "free" ? tx("free") : status === "unknown" ? tx("unknown") : tx("blocked"));
    result.className = status === "free" ? "availability-result ok" : status === "unknown" ? "availability-result unknown" : "availability-result bad";
    track(`availability_result_${status}`);
    if (status === "free") {
      trackDemand("price_quote_loaded", {
        arrival:arrival.value,
        departure:departure.value,
        nights:nights(),
        total:Number(data.total || 0)
      });
    }
    if (status === "free" || status === "unknown") {
      guestArea.classList.remove("hidden");
      checkoutOpen = true;
      track("checkout_started");
      trackDemand("checkout_started", {
        arrival:arrival.value,
        departure:departure.value,
        nights:nights(),
        total:Number(data.total || 0)
      });
      if (status === "free") updatePaymentUI();
      else bookingSubmit.textContent = tx("personal");
      stickyLabel.textContent = status === "free" ? tx("stickyBook") : tx("stickyAsk");
      stickyCta.textContent = status === "free" ? tx("book") : tx("ask");
      lastQuotedTotal = Number(data.total);
      totalPrice.textContent=euro(data.total);
      updateBookingSummary();
      if(data.breakdown){let h=`<div><span>${tx("roomLabel")}</span><strong>${euro(data.breakdown.room_total)}</strong></div>`;data.breakdown.extras.forEach(x=>h+=`<div><span>${x.label}</span><strong>${euro(x.amount)}</strong></div>`);data.breakdown.discounts.forEach(x=>h+=`<div class="discount-line"><span>${x.label} (${x.percent}%)</span><strong>− ${euro(x.amount)}</strong></div>`);priceBreakdown.innerHTML=h;}
    } else {
      guestArea.classList.add("hidden");
    }
  } catch {
    result.textContent = tx("fail");
    result.className = "availability-result bad";
  }
});

paymentRadios.forEach(radio => radio.addEventListener("change", () => {
  bookingSubmitted = false;
  track("payment_method_selected");
  updatePaymentUI();
}));

guestArea?.addEventListener("input", () => {
  if (!guestDetailsTracked) {
    guestDetailsTracked = true;
    track("guest_details_started");
  }
}, {passive:true});

document.getElementById("bookingForm").addEventListener("submit", async (event) => {
  const method = selectedPayment();
  if (method !== "PayPal") {
    track("booking_submit_nonpaypal");
    bookingSubmitted = true;
    bookingSubmit.disabled = true;
    bookingSubmit.textContent = tx("sending");
    return;
  }

  event.preventDefault();
  event.stopPropagation();

  const form = event.currentTarget;
  if (!form.reportValidity()) return;

  const payload = {
    room: selectedRoom()?.value || "",
    arrival: arrival.value,
    departure: departure.value,
    adults: Number(adults.value || 2),
    first_name: form.querySelector('[name="first_name"]')?.value.trim() || "",
    last_name: form.querySelector('[name="last_name"]')?.value.trim() || "",
    email: form.querySelector('[name="email"]')?.value.trim() || "",
    phone: form.querySelector('[name="phone"]')?.value.trim() || "",
    message: form.querySelector('[name="message"]')?.value.trim() || "",
    coupon_code: couponCode?.value.trim() || "",
    source: form.querySelector('[name="source"]')?.value || "",
    utm_medium: form.querySelector('[name="utm_medium"]')?.value || "",
    utm_campaign: form.querySelector('[name="utm_campaign"]')?.value || "",
    landing_page: form.querySelector('[name="landing_page"]')?.value || "",
    referrer: form.querySelector('[name="referrer"]')?.value || "",
    extras: {
      breakfast: Boolean(document.getElementById("breakfast")?.checked),
      jause: Boolean(document.getElementById("jause")?.checked),
      luggage: Boolean(document.getElementById("luggage")?.checked)
    }
  };

  bookingSubmit.disabled = true;
  bookingSubmit.textContent = tx("paypalPrep");
  if (paymentNotice) paymentNotice.textContent = tx("finalCheck");

  try {
    const quoteResponse = await fetch("/api/paypal/quote", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      cache: "no-store",
      body: JSON.stringify(payload)
    });
    const quote = await quoteResponse.json();
    if (!quoteResponse.ok || !quote.ok || !quote.available) {
      throw new Error(quote.message || "Termin ist nicht mehr verfügbar.");
    }
    track("paypal_quote_success");

    const orderResponse = await fetch("/api/paypal/create-order", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      cache: "no-store",
      body: JSON.stringify(payload)
    });
    const order = await orderResponse.json();
    if (!orderResponse.ok || !order.ok || !order.approval_url) {
      throw new Error(order.message || "PayPal konnte nicht gestartet werden.");
    }
    track("paypal_order_created");

    bookingSubmitted = true;
    bookingSubmit.textContent = tx("paypalOpen");
    window.location.assign(order.approval_url);
  } catch (error) {
    track("paypal_checkout_error");
    bookingSubmit.disabled = false;
    bookingSubmit.textContent = tx("paypal");
    if (paymentNotice) paymentNotice.textContent = "⚠️ " + (error?.message || "PayPal konnte nicht gestartet werden.");
  }
});
window.addEventListener("pagehide", () => {
  if (checkoutOpen && !bookingSubmitted) {
    track("booking_abandoned");
    trackDemand("booking_abandoned", {
      arrival:arrival.value,
      departure:departure.value,
      nights:nights(),
      total:Number(lastQuotedTotal || 0)
    });
  }
});

window.addEventListener("pageshow", () => {
  bookingSubmitted = false;
  if (bookingSubmit) {
    bookingSubmit.disabled = false;
    bookingSubmit.removeAttribute("aria-busy");
  }
  updatePaymentUI();
});

// Live calendar
const cal = document.getElementById("liveCalendar");
const calTitle = document.getElementById("calendarTitle");
const calRoom = document.getElementById("calendarRoom");
let current = new Date();
current.setDate(1);

async function renderCalendar() {
  const year = current.getFullYear();
  const month = current.getMonth()+1;
  const monthNames = tx("months");
  calTitle.textContent = `${monthNames[month-1]} ${year}`;

  const response = await fetch(`/api/calendar?room=${encodeURIComponent(calRoom.value)}&year=${year}&month=${month}`);
  const data = await response.json();
  cal.innerHTML = "";

  let statusNote = document.getElementById("calendarStatusNote");
  if (!statusNote) {
    statusNote = document.createElement("div");
    statusNote.id = "calendarStatusNote";
    statusNote.className = "calendar-status-note";
    cal.parentElement.insertBefore(statusNote, cal);
  }
  statusNote.textContent = data.live
    ? `${tx("calendarLive")}${data.updatedAt ? " · " + data.updatedAt : ""}`
    : tx("calendarDown");

  tx("days").forEach(d => {
    const e = document.createElement("div");
    e.className = "cal-head";
    e.textContent = d;
    cal.appendChild(e);
  });

  const first = new Date(year, month-1, 1);
  const startOffset = (first.getDay()+6)%7;
  for (let i=0;i<startOffset;i++) {
    const e = document.createElement("div");
    e.className = "cal-day empty";
    cal.appendChild(e);
  }

  const daysInMonth = new Date(year, month, 0).getDate();
  for (let day=1;day<=daysInMonth;day++) {
    const key = `${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    const state = data.days[key] || "unknown";
    const e = document.createElement("div");
    e.className = `cal-day ${state}`;
    e.textContent = day;
    cal.appendChild(e);
  }
}
document.getElementById("prevMonth").addEventListener("click",()=>{current.setMonth(current.getMonth()-1);renderCalendar()});
document.getElementById("nextMonth").addEventListener("click",()=>{current.setMonth(current.getMonth()+1);renderCalendar()});
calRoom.addEventListener("change",renderCalendar);

updateRoomRelease();
updateTotals();
updatePaymentUI();
updateBookingSummary();
renderCalendar();

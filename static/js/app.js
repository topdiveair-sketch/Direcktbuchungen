const checkoutLang = new URLSearchParams(window.location.search).get("lang") || "de";
const I18N = {
  de:{afterCheck:"Nach Verfügbarkeitsprüfung",missing:"Bitte Reisedaten und Zimmer auswählen.",checking:"Verfügbarkeit wird geprüft …",fail:"Die Prüfung konnte nicht durchgeführt werden.",free:"✅ Termin frei – direkt buchbar.",unknown:"Verfügbarkeit bitte persönlich anfragen.",paypal:"MIT PAYPAL BEZAHLEN",paypalNote:"Nach dem Klick wird der Termin nochmals geprüft und anschließend der sichere PayPal-Checkout geöffnet.",bank:"ANFRAGE SENDEN & BANKDATEN ERHALTEN",bankNote:"Die Bankverbindung wird direkt angezeigt. Der Termin wird erst nach persönlicher Bestätigung verbindlich reserviert.",onsite:"BUCHUNGSANFRAGE SENDEN",onsiteNote:"Der Termin wird erst nach persönlicher Bestätigung verbindlich reserviert. Zahlung erfolgt bei Anreise.",personal:"VERFÜGBARKEIT PERSÖNLICH ANFRAGEN",stickyBook:"Jetzt direkt buchen",stickyAsk:"Persönlich anfragen",book:"Buchen",ask:"Anfragen",sending:"Anfrage wird gesendet …",paypalPrep:"PAYPAL WIRD VORBEREITET …",finalCheck:"Verfügbarkeit und Preis werden nochmals sicher geprüft.",paypalOpen:"PAYPAL WIRD GEÖFFNET …",calendarLive:"Live-Kalender aktuell",calendarDown:"Live-Kalender derzeit nicht erreichbar – freie Tage werden nicht automatisch bestätigt.",months:["Jänner","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],days:["Mo","Di","Mi","Do","Fr","Sa","So"]},
  cs:{afterCheck:"Po ověření dostupnosti",missing:"Vyberte prosím termín a pokoj.",checking:"Ověřujeme dostupnost …",fail:"Dostupnost se nepodařilo ověřit.",free:"✅ Termín je volný – můžete rezervovat přímo.",unknown:"Dostupnost prosím ověřte osobně.",paypal:"ZAPLATIT PŘES PAYPAL",paypalNote:"Po kliknutí ještě jednou ověříme termín a poté se otevře zabezpečená platba přes PayPal.",bank:"ODESLAT POPTÁVKU A ZÍSKAT BANKOVNÍ ÚDAJE",bankNote:"Bankovní údaje se zobrazí přímo. Termín je závazně rezervován až po našem osobním potvrzení.",onsite:"ODESLAT POPTÁVKU",onsiteNote:"Termín je závazně rezervován až po našem osobním potvrzení. Platba proběhne při příjezdu.",personal:"OSOBNĚ OVĚŘIT DOSTUPNOST",stickyBook:"Rezervovat přímo",stickyAsk:"Osobní dotaz",book:"Rezervovat",ask:"Zeptat se",sending:"Odesíláme poptávku …",paypalPrep:"PŘIPRAVUJEME PAYPAL …",finalCheck:"Ještě jednou bezpečně ověřujeme dostupnost a cenu.",paypalOpen:"OTEVÍRÁME PAYPAL …",calendarLive:"Aktuální kalendář",calendarDown:"Aktuální kalendář není právě dostupný – volné dny proto automaticky nepotvrzujeme.",months:["leden","únor","březen","duben","květen","červen","červenec","srpen","září","říjen","listopad","prosinec"],days:["Po","Út","St","Čt","Pá","So","Ne"]},
  sk:{afterCheck:"Po overení dostupnosti",missing:"Vyberte si prosím termín a izbu.",checking:"Overujeme dostupnosť …",fail:"Dostupnosť sa nepodarilo overiť.",free:"✅ Termín je voľný – môžete rezervovať priamo.",unknown:"Dostupnosť si prosím overte osobne.",paypal:"ZAPLATIŤ CEZ PAYPAL",paypalNote:"Po kliknutí ešte raz overíme termín a potom sa otvorí zabezpečená platba cez PayPal.",bank:"ODOSLAŤ POŽIADAVKU A ZÍSKAŤ BANKOVÉ ÚDAJE",bankNote:"Bankové údaje sa zobrazia priamo. Termín je záväzne rezervovaný až po našom osobnom potvrdení.",onsite:"ODOSLAŤ POŽIADAVKU",onsiteNote:"Termín je záväzne rezervovaný až po našom osobnom potvrdení. Platba prebehne pri príchode.",personal:"OSOBNE OVERIŤ DOSTUPNOSŤ",stickyBook:"Rezervovať priamo",stickyAsk:"Osobná požiadavka",book:"Rezervovať",ask:"Opýtať sa",sending:"Odosielame požiadavku …",paypalPrep:"PRIPRAVUJEME PAYPAL …",finalCheck:"Ešte raz bezpečne overujeme dostupnosť a cenu.",paypalOpen:"OTVÁRAME PAYPAL …",calendarLive:"Aktuálny kalendár",calendarDown:"Aktuálny kalendár momentálne nie je dostupný – voľné dni preto automaticky nepotvrdzujeme.",months:["január","február","marec","apríl","máj","jún","júl","august","september","október","november","december"],days:["Po","Ut","St","Št","Pi","So","Ne"]}
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
let checkoutOpen = false;
let bookingSubmitted = false;

function track(event) {
  const body = JSON.stringify({event});
  if (navigator.sendBeacon && event === "booking_abandoned") {
    navigator.sendBeacon("/api/events", new Blob([body], {type:"application/json"}));
    return;
  }
  fetch("/api/events", {method:"POST", headers:{"Content-Type":"application/json"}, body, keepalive:true}).catch(()=>{});
}

document.getElementById("idempotencyKey").value =
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
track("landing_view");

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
  return new Intl.NumberFormat("de-AT", {style:"currency", currency:"EUR"}).format(v);
}

function updateTotals() {
  const n = nights();
  nightsEl.value = n;
  totalPrice.textContent = n ? tx("afterCheck") : euro(0);
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

function updatePaymentUI() {
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
}
function resetAvailability() {
  result.classList.add("hidden");
  guestArea.classList.add("hidden");
}

arrival.addEventListener("change", () => {
  if (arrival.value) {
    const d = new Date(arrival.value + "T12:00:00");
    d.setDate(d.getDate()+1);
    departure.min = d.toISOString().slice(0,10);
    if (!departure.value || departure.value <= arrival.value) departure.value = departure.min;
  }
  updateRoomRelease();
  resetAvailability();
});

[departure, adults, ...extraInputs, ...roomRadios].forEach(el => {
  el.addEventListener("change", () => {
    if (el.matches('input[name="room"]')) track("room_selected");
    if (extraInputs.includes(el)) track("extras_selected");
    updateTotals();
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

  try {
    const response = await fetch("/api/availability", {method:"POST", body:fd});
    const data = await response.json();
    const status = data.status || (data.available === true ? "free" : data.available === false ? "blocked" : "unknown");
    result.textContent = checkoutLang === "cs" || checkoutLang === "sk"
      ? (status === "free" ? tx("free") : status === "unknown" ? tx("unknown") : (checkoutLang === "cs" ? "⛔ Termín není dostupný." : "⛔ Termín nie je dostupný."))
      : data.message;
    result.className = status === "free" ? "availability-result ok" : status === "unknown" ? "availability-result unknown" : "availability-result bad";
    track(`availability_result_${status}`);
    if (status === "free" || status === "unknown") {
      guestArea.classList.remove("hidden");
      checkoutOpen = true;
      track("checkout_started");
      if (status === "free") updatePaymentUI();
      else bookingSubmit.textContent = tx("personal");
      stickyLabel.textContent = status === "free" ? tx("stickyBook") : tx("stickyAsk");
      stickyCta.textContent = status === "free" ? tx("book") : tx("ask");
      totalPrice.textContent=euro(data.total); if(data.breakdown){let h=`<div><span>Zimmer</span><strong>${euro(data.breakdown.room_total)}</strong></div>`;data.breakdown.extras.forEach(x=>h+=`<div><span>${x.label}</span><strong>${euro(x.amount)}</strong></div>`);data.breakdown.discounts.forEach(x=>h+=`<div class="discount-line"><span>${x.label} (${x.percent}%)</span><strong>− ${euro(x.amount)}</strong></div>`);priceBreakdown.innerHTML=h;}
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
  updatePaymentUI();
}));

document.getElementById("bookingForm").addEventListener("submit", async (event) => {
  const method = selectedPayment();
  if (method !== "PayPal") {
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

    bookingSubmitted = true;
    bookingSubmit.textContent = tx("paypalOpen");
    window.location.assign(order.approval_url);
  } catch (error) {
    bookingSubmit.disabled = false;
    bookingSubmit.textContent = tx("paypal");
    if (paymentNotice) paymentNotice.textContent = "⚠️ " + (error?.message || "PayPal konnte nicht gestartet werden.");
  }
});
window.addEventListener("pagehide", () => {
  if (checkoutOpen && !bookingSubmitted) track("booking_abandoned");
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
renderCalendar();

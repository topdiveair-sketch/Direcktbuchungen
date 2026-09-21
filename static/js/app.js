
const arrival = document.getElementById("arrival");
const departure = document.getElementById("departure");
const adults = document.getElementById("adults");
const extraIds=["breakfast","jause","luggage","dog","baby_bed"];
const extraInputs=extraIds.map(x=>document.getElementById(x)).filter(Boolean);
const priceBreakdown=document.getElementById("priceBreakdown");
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
  totalPrice.textContent = n ? "Nach Verfügbarkeitsprüfung" : euro(0);
  priceBreakdown.innerHTML = "";
}

function updateRoomRelease() {
  const selectedArrival = arrival.value;
  roomRadios.forEach(radio => {
    const card = radio.closest(".room-option");
    const disabled = !selectedArrival || selectedArrival < radio.dataset.from;
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
    bookingSubmit.textContent = "MIT PAYPAL BEZAHLEN";
    if (paymentNotice) paymentNotice.textContent = "Nach dem Klick wird der Termin nochmals geprüft und anschließend der sichere PayPal-Checkout geöffnet.";
  } else if (method === "Banküberweisung") {
    bookingSubmit.textContent = "JETZT BUCHEN";
    if (paymentNotice) paymentNotice.textContent = "Die Bankverbindung wird direkt angezeigt. Nach der Buchung erhalten Sie Betrag und Verwendungszweck nochmals bestätigt.";
  } else {
    bookingSubmit.textContent = "JETZT DIREKT BUCHEN";
    if (paymentNotice) paymentNotice.textContent = "Zahlung erfolgt bei Anreise.";
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
    result.textContent = "Bitte Reisedaten und Zimmer auswählen.";
    result.className = "availability-result bad";
    return;
  }
  const fd = new FormData();
  fd.append("arrival", arrival.value);
  fd.append("departure", departure.value);
  fd.append("room", selectedRoom().value);
  fd.append("adults", adults.value);
  extraIds.forEach(id=>{const el=document.getElementById(id);fd.append(id,el&&el.checked?"true":"false")});

  result.textContent = "Verfügbarkeit wird geprüft …";
  result.className = "availability-result";
  track("availability_started");

  try {
    const response = await fetch("/api/availability", {method:"POST", body:fd});
    const data = await response.json();
    const status = data.status || (data.available === true ? "free" : data.available === false ? "blocked" : "unknown");
    result.textContent = data.message;
    result.className = status === "free" ? "availability-result ok" : status === "unknown" ? "availability-result unknown" : "availability-result bad";
    track(`availability_result_${status}`);
    if (status === "free" || status === "unknown") {
      guestArea.classList.remove("hidden");
      checkoutOpen = true;
      track("checkout_started");
      if (status === "free") updatePaymentUI();
      else bookingSubmit.textContent = "VERFÜGBARKEIT PERSÖNLICH ANFRAGEN";
      stickyLabel.textContent = status === "free" ? "Jetzt direkt buchen" : "Persönlich anfragen";
      stickyCta.textContent = status === "free" ? "Buchen" : "Anfragen";
      totalPrice.textContent=euro(data.total); if(data.breakdown){let h=`<div><span>Zimmer</span><strong>${euro(data.breakdown.room_total)}</strong></div>`;data.breakdown.extras.forEach(x=>h+=`<div><span>${x.label}</span><strong>${euro(x.amount)}</strong></div>`);data.breakdown.discounts.forEach(x=>h+=`<div class="discount-line"><span>${x.label} (${x.percent}%)</span><strong>− ${euro(x.amount)}</strong></div>`);priceBreakdown.innerHTML=h;}
    } else {
      guestArea.classList.add("hidden");
    }
  } catch {
    result.textContent = "Die Prüfung konnte nicht durchgeführt werden.";
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
    bookingSubmit.textContent = method === "Banküberweisung" ? "Buchung wird gespeichert …" : "Wird sicher gespeichert …";
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
    extras: {
      breakfast: Boolean(document.getElementById("breakfast")?.checked),
      jause: Boolean(document.getElementById("jause")?.checked),
      luggage: Boolean(document.getElementById("luggage")?.checked)
    }
  };

  bookingSubmit.disabled = true;
  bookingSubmit.textContent = "PAYPAL WIRD VORBEREITET …";
  if (paymentNotice) paymentNotice.textContent = "Verfügbarkeit und Preis werden nochmals sicher geprüft.";

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
    bookingSubmit.textContent = "PAYPAL WIRD GEÖFFNET …";
    window.location.assign(order.approval_url);
  } catch (error) {
    bookingSubmit.disabled = false;
    bookingSubmit.textContent = "MIT PAYPAL BEZAHLEN";
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
  const monthNames = ["Jänner","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];
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
    ? `Live-Kalender aktuell${data.updatedAt ? " · Stand " + data.updatedAt : ""}`
    : "Live-Kalender derzeit nicht erreichbar – freie Tage werden nicht automatisch bestätigt.";

  ["Mo","Di","Mi","Do","Fr","Sa","So"].forEach(d => {
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

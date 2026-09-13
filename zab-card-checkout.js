/* Card checkout UI for Zuhause am Bach. Stripe stays invisible until the backend
   confirms that STRIPE_SECRET_KEY is configured. PayPal remains available. */
(function () {
  "use strict";

  const API_BASE = String(window.ZAB_DIRECT_BOOKING_API_URL || "").replace(/\/+$/, "");
  if (!API_BASE) return;

  function value(id) {
    return (document.getElementById(id)?.value || "").trim();
  }

  function selectedExtra(label) {
    return Array.from(document.querySelectorAll('input[name="extra"]:checked'))
      .some((input) => input.value === label);
  }

  function payload() {
    return {
      room: document.querySelector('input[name="room"]:checked')?.value || "",
      arrival: value("arrival"),
      departure: value("departure"),
      adults: Number(value("adults") || 2),
      first_name: value("firstName"),
      last_name: value("lastName"),
      email: value("email"),
      phone: value("phone"),
      message: value("message"),
      extras: {
        breakfast: selectedExtra("Frühstück"),
        jause: selectedExtra("Wachauer Jause"),
        luggage: Boolean(document.getElementById("luggageTransport")?.checked)
      }
    };
  }

  function formReady() {
    const p = payload();
    const availability = document.getElementById("availabilityStatus");
    const total = (document.getElementById("total")?.textContent || "").trim();
    return p.room === "Bachblick" && p.arrival && p.departure && p.first_name &&
      p.last_name && p.email && p.phone && !p.extras.luggage &&
      availability?.classList.contains("ok") && total && !/^0(?:[,.]00)?\s*EUR$/i.test(total);
  }

  function installStyle() {
    if (document.getElementById("zab-card-style")) return;
    const style = document.createElement("style");
    style.id = "zab-card-style";
    style.textContent = `
      .zab-payment-choice{display:grid;gap:9px;margin-top:10px}
      .zab-card-button{width:100%;min-height:54px;border:0;border-radius:10px;padding:12px 16px;
        background:linear-gradient(135deg,#176b5a,#0d4d40);color:#fff;font:inherit;font-size:16px;
        font-weight:900;cursor:pointer;box-shadow:0 10px 22px rgba(23,107,90,.22)}
      .zab-card-button:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}
      .zab-payment-separator{display:flex;align-items:center;gap:8px;color:#697a74;font-size:11px;font-weight:800}
      .zab-payment-separator::before,.zab-payment-separator::after{content:"";height:1px;flex:1;background:#d8e2dd}
      .zab-payment-note{margin:0;color:#526b63;font-size:12px;line-height:1.4}
      #paypalLink.zab-paypal-secondary{width:100%;min-height:48px;background:#fff!important;color:#075a9c!important;
        border:1px solid #9fc8e4;box-shadow:none!important;font-size:14px!important}
    `;
    document.head.appendChild(style);
  }

  async function configured() {
    try {
      const response = await fetch(API_BASE + "/api/stripe/status", { cache: "no-store" });
      const data = await response.json();
      return Boolean(response.ok && data.ok && data.configured);
    } catch (_) {
      return false;
    }
  }

  function sync(button, note) {
    const ready = formReady();
    button.disabled = !ready;
    if (payload().extras.luggage) {
      note.textContent = "Gepäcktransport wird nach Strecke berechnet. Dafür bitte zuerst eine persönliche Anfrage senden.";
    } else if (!ready) {
      note.textContent = "Karte wird freigeschaltet, sobald Reisedaten, Kontaktdaten, Direktpreis und freie Verfügbarkeit bestätigt sind.";
    } else {
      note.textContent = "Sichere Kartenzahlung über Stripe. Der Betrag wird serverseitig nochmals geprüft.";
    }
  }

  async function install() {
    if (!(await configured())) return;
    if (document.getElementById("zab-card-payment")) return;
    installStyle();

    const paypalBox = document.getElementById("paypalBox");
    const paypalLink = document.getElementById("paypalLink");
    if (!paypalBox) return;

    const wrap = document.createElement("div");
    wrap.id = "zab-card-payment";
    wrap.className = "zab-payment-choice";
    wrap.innerHTML = '<button type="button" id="zabCardPay" class="zab-card-button" disabled>💳 Mit Karte bezahlen</button><p id="zabCardNote" class="zab-payment-note"></p><div class="zab-payment-separator">oder</div>';
    paypalBox.insertBefore(wrap, paypalLink || null);

    if (paypalLink) {
      paypalLink.classList.add("zab-paypal-secondary");
      const observer = new MutationObserver(function () {
        if (!paypalLink.classList.contains("hidden")) paypalLink.textContent = "Mit PayPal bezahlen";
      });
      observer.observe(paypalLink, { attributes: true, childList: true, subtree: true });
    }

    const button = document.getElementById("zabCardPay");
    const note = document.getElementById("zabCardNote");
    const form = document.getElementById("requestForm");
    const availability = document.getElementById("availabilityStatus");
    const total = document.getElementById("total");

    const resync = function () { sync(button, note); };
    form?.addEventListener("input", resync);
    form?.addEventListener("change", function () { setTimeout(resync, 50); });
    if (availability) new MutationObserver(resync).observe(availability, { attributes: true, childList: true, subtree: true });
    if (total) new MutationObserver(resync).observe(total, { childList: true, subtree: true });
    resync();

    button.addEventListener("click", async function () {
      if (!formReady()) {
        resync();
        return;
      }
      const old = button.textContent;
      button.disabled = true;
      button.textContent = "Sichere Kartenzahlung wird geöffnet …";
      try {
        window.zabTrack?.("card_payment_started");
        const response = await fetch(API_BASE + "/api/stripe/create-checkout-session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          body: JSON.stringify(payload())
        });
        const data = await response.json().catch(function () { return {}; });
        if (!response.ok || !data.ok || !data.checkout_url) {
          throw new Error(data.message || "Kartenzahlung konnte nicht gestartet werden.");
        }
        window.location.assign(data.checkout_url);
      } catch (error) {
        note.textContent = error.message || "Kartenzahlung derzeit nicht verfügbar. Bitte PayPal oder Anfrage verwenden.";
        button.disabled = false;
        button.textContent = old;
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
  else install();
})();

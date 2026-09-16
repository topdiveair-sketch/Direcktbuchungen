/* Privacy-light first-party demand tracking for Zuhause am Bach.
   No names, email addresses, phone numbers, message text, IP or user agent are sent. */
(function () {
  "use strict";
  const ENDPOINT = "https://web-production-2b242.up.railway.app/api/demand-event";

  function details(extra) {
    const arrival = document.getElementById("arrival");
    const departure = document.getElementById("departure");
    const room = document.querySelector('input[name="room"]:checked');
    const a = arrival && arrival.value;
    const d = departure && departure.value;
    let nights = null;
    if (a && d) {
      const ms = new Date(d + "T00:00:00") - new Date(a + "T00:00:00");
      if (Number.isFinite(ms) && ms > 0) nights = Math.round(ms / 86400000);
    }
    const totalText = (document.getElementById("total") || {}).textContent || "";
    const totalMatch = totalText.replace(",", ".").match(/([0-9]+(?:\.[0-9]+)?)/);
    return Object.assign({
      arrival: a || "",
      departure: d || "",
      nights: nights,
      room: room ? room.value : "",
      total: totalMatch ? Number(totalMatch[1]) : null,
      language: document.documentElement.lang || "de"
    }, extra || {});
  }

  function send(event, extra) {
    const payload = JSON.stringify({ event: event, details: details(extra) });
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: "application/json" });
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      }
    } catch (_) {}
    fetch(ENDPOINT, {
      method: "POST",
      mode: "cors",
      cache: "no-store",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: payload
    }).catch(function () {});
  }

  function oncePerSession(key, event, extra) {
    try {
      const storageKey = "zab-demand-" + key;
      if (sessionStorage.getItem(storageKey)) return;
      sessionStorage.setItem(storageKey, "1");
    } catch (_) {}
    send(event, extra);
  }

  function ready() {
    oncePerSession("view", "page_view");

    document.addEventListener("click", function (ev) {
      const tracked = ev.target.closest("[data-track], a[href*='#booking'], a[href*='#arrival']");
      if (tracked) send("booking_cta_click", { cta: tracked.getAttribute("data-track") || (tracked.textContent || "").trim().slice(0, 70) });

      const email = ev.target.closest("#sendEmailLink");
      if (email) send("email_click");
      const whatsapp = ev.target.closest("#sendWhatsappLink");
      if (whatsapp) send("whatsapp_click");
      const copy = ev.target.closest("#copyRequestButton");
      if (copy) send("copy_request_click");
    }, true);

    const form = document.getElementById("requestForm");
    if (form) {
      let dateTimer = null;
      form.addEventListener("change", function (ev) {
        if (!["arrival", "departure"].includes(ev.target.name)) return;
        clearTimeout(dateTimer);
        dateTimer = setTimeout(function () {
          const a = document.getElementById("arrival");
          const d = document.getElementById("departure");
          if (a && a.value && d && d.value) send("dates_selected");
        }, 300);
      });
      form.addEventListener("submit", function () {
        setTimeout(function () {
          const options = document.getElementById("sendOptions");
          if (options && options.classList.contains("show")) send("request_prepared");
        }, 800);
      });
    }

    const price = document.querySelector('input[name="room"][value="Bachblick"]')?.closest(".choice")?.querySelector("b.price");
    if (price) {
      let last = "";
      new MutationObserver(function () {
        const text = (price.textContent || "").trim();
        if (!text || text === last || /^ab\s+99/i.test(text)) return;
        last = text;
        send("price_quote_loaded");
      }).observe(price, { childList: true, subtree: true, characterData: true });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready, { once: true });
  else ready();
})();

/* Conversion UX 2026-09-13: keep direct booking visible and reduce booking friction.
   Additive only: no price, calendar or payment logic is changed here. */
(function () {
  "use strict";

  function enhanceConversion() {
    if (document.getElementById("zab-conversion-ux-20260913")) return;

    const style = document.createElement("style");
    style.id = "zab-conversion-ux-20260913";
    style.textContent = `
      .zab-hero-direct-message{
        display:flex;align-items:center;gap:12px;max-width:680px;margin:14px 0 0;
        padding:12px 14px;border:1px solid rgba(255,255,255,.58);border-radius:13px;
        background:rgba(255,255,255,.95);color:#17372f!important;
        box-shadow:0 9px 24px rgba(0,0,0,.16);text-shadow:none!important;
        font-size:14px!important;font-weight:850;line-height:1.4
      }
      .zab-hero-direct-message a{
        margin-left:auto;display:inline-grid;place-items:center;min-height:42px;padding:8px 12px;
        border-radius:9px;background:var(--brand);color:#fff;text-decoration:none;
        white-space:nowrap;font-size:13px;font-weight:900
      }
      .zab-booking-facts{
        display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 12px;
        margin:10px 0 0;padding:0;list-style:none
      }
      .zab-booking-facts li{font-size:13px;font-weight:820;color:#314841}
      .zab-booking-facts li::before{content:"✓ ";color:var(--brand);font-weight:950}
      .zab-floating-booking{
        position:fixed;z-index:115;right:22px;bottom:22px;display:flex;align-items:center;gap:12px;
        max-width:400px;padding:12px 14px;border:1px solid #c8dfd4;border-radius:14px;
        background:rgba(255,255,255,.97);box-shadow:0 16px 42px rgba(0,0,0,.19);
        transform:translateY(140%);opacity:0;pointer-events:none;
        transition:transform .2s ease,opacity .2s ease
      }
      .zab-floating-booking.is-visible{transform:translateY(0);opacity:1;pointer-events:auto}
      .zab-floating-booking strong{display:block;color:#17372f;font-size:14px;line-height:1.25}
      .zab-floating-booking small{display:block;margin-top:2px;color:#5f6f69;font-size:11px}
      .zab-floating-booking a{
        display:grid;place-items:center;min-height:44px;padding:8px 12px;border-radius:9px;
        background:var(--brand);color:#fff;text-decoration:none;white-space:nowrap;
        font-size:13px;font-weight:900
      }
      @media (min-width:901px){
        .hero-grid>.panel{position:sticky;top:16px;align-self:start}
      }
      @media (max-width:900px){
        .zab-floating-booking{display:none!important}
      }
      @media (max-width:640px){
        .zab-hero-direct-message{display:grid;grid-template-columns:1fr;margin-top:12px!important}
        .zab-hero-direct-message a{margin-left:0;width:100%}
        .zab-booking-facts{grid-template-columns:1fr}
      }
    `;
    document.head.appendChild(style);

    const heroCopy = document.querySelector(".hero-copy");
    const heroIntro = heroCopy && heroCopy.querySelector("p:not(.mobile-hero-benefits)");
    if (heroIntro && !document.getElementById("zab-hero-direct-message")) {
      const message = document.createElement("div");
      message.id = "zab-hero-direct-message";
      message.className = "zab-hero-direct-message";
      message.innerHTML = '<span>Direkt beim Gastgeber buchen – persönlicher Kontakt, keine Buchungsplattform nötig.</span><a href="#booking-title" data-track="hero_direct_booking">Verfügbarkeit prüfen</a>';
      heroIntro.insertAdjacentElement("afterend", message);
    }

    const directBox = document.getElementById("zab-direct-box") || document.querySelector(".direct-booking-trust");
    if (directBox) {
      const existingBenefits = directBox.querySelector(".zab-direct-benefits");
      if (existingBenefits) {
        existingBenefits.innerHTML = [
          "Privates Badezimmer",
          "Frühstück auf Wunsch zubuchbar",
          "Fahrradgarage",
          "E-Bike-Lademöglichkeit",
          "Kostenloser Parkplatz",
          "Direkter Gastgeberkontakt"
        ].map(function (item) { return "<li>" + item + "</li>"; }).join("");
      } else if (!directBox.querySelector(".zab-booking-facts")) {
        const list = document.createElement("ul");
        list.className = "zab-booking-facts";
        list.innerHTML = [
          "Privates Badezimmer",
          "Frühstück auf Wunsch zubuchbar",
          "Fahrradgarage",
          "E-Bike-Lademöglichkeit",
          "Kostenloser Parkplatz",
          "Direkter Gastgeberkontakt"
        ].map(function (item) { return "<li>" + item + "</li>"; }).join("");
        directBox.appendChild(list);
      }
    }

    const mobileBar = document.querySelector(".mobile-booking-bar");
    if (mobileBar) {
      const strong = mobileBar.querySelector("strong");
      const link = mobileBar.querySelector("a");
      if (strong) strong.textContent = "Direkt bei Zuhause am Bach";
      if (link) {
        link.textContent = "Verfügbarkeit prüfen";
        link.setAttribute("data-track", "mobile_sticky_booking");
      }
    }

    if (!document.getElementById("zab-floating-booking")) {
      const floating = document.createElement("aside");
      floating.id = "zab-floating-booking";
      floating.className = "zab-floating-booking";
      floating.setAttribute("aria-label", "Direktbuchung");
      floating.innerHTML = '<div><strong>Direkt bei Zuhause am Bach buchen</strong><small>Persönlich · ohne zusätzliche Buchungsplattform</small></div><a href="#booking-title" data-track="desktop_sticky_booking">Verfügbarkeit prüfen</a>';
      document.body.appendChild(floating);

      const bookingPanel = document.querySelector(".hero-grid > .panel");
      function updateFloatingBooking() {
        if (window.innerWidth < 901) {
          floating.classList.remove("is-visible");
          return;
        }
        const panelBottom = bookingPanel ? bookingPanel.getBoundingClientRect().bottom : 0;
        const show = window.scrollY > 180 && panelBottom < 120;
        floating.classList.toggle("is-visible", show);
      }
      window.addEventListener("scroll", updateFloatingBooking, { passive: true });
      window.addEventListener("resize", updateFloatingBooking);
      updateFloatingBooking();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceConversion, { once: true });
  } else {
    enhanceConversion();
  }
})();

/* Unified payment copy: all online payments are routed through the existing
   PayPal business checkout. PayPal decides whether guest card checkout is
   available for the individual buyer/account/region. */
(function () {
  "use strict";

  function enhancePayPalChoice() {
    const paypalBox = document.getElementById("paypalBox");
    const paypalLink = document.getElementById("paypalLink");
    if (!paypalBox || !paypalLink) return false;

    paypalLink.textContent = "Mit PayPal oder Karte bezahlen";
    paypalLink.setAttribute("data-track", "paypal_or_card_payment");

    if (!document.getElementById("zab-paypal-card-note")) {
      const note = document.createElement("p");
      note.id = "zab-paypal-card-note";
      note.style.cssText = "margin:8px 0 0;color:#526b63;font-size:12px;line-height:1.45";
      note.textContent = "PayPal-Zahlung oder – sofern von PayPal für den Gast freigegeben – Kredit-/Debitkarte. Die Auszahlung läuft zentral über das PayPal-Geschäftskonto.";
      paypalLink.insertAdjacentElement("afterend", note);
    }
    return true;
  }

  function install() {
    if (enhancePayPalChoice()) return;
    const observer = new MutationObserver(function () {
      if (enhancePayPalChoice()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(function () { observer.disconnect(); }, 15000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
  else install();
})();

/* Fail-safe booking request fallback.
   Instant booking stays fail-closed, but a normal personal request must not hang
   forever when the live direct-price endpoint is temporarily unavailable. */
(function () {
  "use strict";

  function validStay() {
    const a = document.getElementById("arrival")?.value || "";
    const d = document.getElementById("departure")?.value || "";
    return /^\d{4}-\d{2}-\d{2}$/.test(a) && /^\d{4}-\d{2}-\d{2}$/.test(d) && d > a;
  }

  function requiredFieldsComplete(form) {
    const required = Array.from(form.querySelectorAll("[required]"));
    const missing = required.find(function (field) { return !String(field.value || "").trim(); });
    if (missing) {
      missing.focus();
      missing.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    return true;
  }

  function buildFallbackRequest(form) {
    const room = form.querySelector('input[name="room"]:checked')?.value || "Bachblick";
    const extras = Array.from(form.querySelectorAll('input[name="extra"]:checked')).map(function (x) { return x.value; });
    const lines = [
      "Buchungsanfrage Zuhause am Bach",
      "",
      "Name: " + (document.getElementById("firstName")?.value || "") + " " + (document.getElementById("lastName")?.value || ""),
      "E-Mail: " + (document.getElementById("email")?.value || ""),
      "Telefon: " + (document.getElementById("phone")?.value || ""),
      "",
      "Anreise: " + (document.getElementById("arrival")?.value || ""),
      "Abreise: " + (document.getElementById("departure")?.value || ""),
      "Personen: " + (document.getElementById("adults")?.value || ""),
      "Zimmer: " + room,
      "Extras: " + (extras.length ? extras.join(", ") : "keine"),
      "Direktpreis: wird persönlich bestätigt",
      "",
      "Nachricht:",
      document.getElementById("message")?.value || "-",
      "",
      "Hinweis: Die Live-Preisprüfung war beim Absenden vorübergehend nicht erreichbar. Verfügbarkeit und Preis bitte persönlich bestätigen."
    ];
    return lines.join("\n");
  }

  function installFallback() {
    const form = document.getElementById("requestForm");
    const button = document.getElementById("submitRequest");
    const availability = document.getElementById("availabilityStatus");
    const sendOptions = document.getElementById("sendOptions");
    const emailLink = document.getElementById("sendEmailLink");
    const whatsappLink = document.getElementById("sendWhatsappLink");
    if (!form || !button || !sendOptions || !emailLink || !whatsappLink) return;

    let checkingSince = 0;

    function refresh() {
      const text = (button.textContent || "").trim();
      const checking = /Preis wird geprüft|Price is being checked/i.test(text);
      const blocked = availability?.classList.contains("blocked");
      if (checking && validStay() && !blocked) {
        if (!checkingSince) checkingSince = Date.now();
        if (Date.now() - checkingSince >= 2500) {
          button.disabled = false;
          button.dataset.priceFallback = "1";
          button.textContent = "Buchungsanfrage senden – Preis wird bestätigt";
          if (availability && !availability.classList.contains("blocked")) {
            availability.className = "availability-status note";
            availability.textContent = "Live-Preis derzeit nicht erreichbar. Ihre Anfrage kann trotzdem gesendet werden; Verfügbarkeit und Preis werden persönlich bestätigt.";
          }
        }
      } else {
        checkingSince = 0;
        if (!checking && button.dataset.priceFallback === "1") delete button.dataset.priceFallback;
      }
    }

    setInterval(refresh, 400);

    button.addEventListener("click", function (event) {
      if (button.dataset.priceFallback !== "1") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!requiredFieldsComplete(form)) {
        alert("Bitte alle Pflichtfelder ausfüllen.");
        return;
      }
      if (!validStay()) {
        alert("Bitte Anreise und Abreise korrekt auswählen.");
        return;
      }
      if (availability?.classList.contains("blocked")) {
        alert(availability.textContent || "Der gewählte Termin ist nicht verfügbar.");
        return;
      }

      const subject = "Buchungsanfrage Zuhause am Bach";
      const body = buildFallbackRequest(form);
      emailLink.href = "mailto:Zuhause.am.Bach@outlook.com?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
      whatsappLink.href = "https://wa.me/436646437526?text=" + encodeURIComponent(subject + "\n\n" + body);
      sendOptions.classList.add("show");
      sendOptions.scrollIntoView({ behavior: "smooth", block: "center" });
      window.zabTrack?.("booking_request_fallback_prepared", { reason: "direct_price_unavailable" });
    }, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", installFallback, { once: true });
  else installFallback();
})();

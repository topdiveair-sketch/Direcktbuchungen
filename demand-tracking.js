/* Privacy-light first-party demand tracking for Zuhause am Bach.
   No names, email addresses, phone numbers, message text, IP or user agent are sent. */
(function () {
  "use strict";
  const ENDPOINT = "https://web-production-907d68.up.railway.app/api/demand-event";

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
        // The main booking script blocks invalid/no-price submits before exposing
        // the send options. Record intent here; request_prepared is emitted below
        // only once the send options actually become visible.
        setTimeout(function () {
          const options = document.getElementById("sendOptions");
          if (options && options.classList.contains("show")) send("request_prepared");
        }, 800);
      });
    }

    // Detect successful server quote via the visible price label mutation.
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

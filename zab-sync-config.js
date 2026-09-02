window.ZAB_BOOKING_SYNC_URL = "https://PASTE-YOUR-WORKER.workers.dev";

/* Railway-Backend fuer serverseitig gepruefte Direktbuchung + PayPal. */
window.ZAB_DIRECT_BOOKING_API_URL = "https://web-production-f05a4.up.railway.app";

(function () {
  "use strict";

  /* Zusatzzimmer nur nach ausdruecklicher manueller Freigabe anzeigen. */
  window.SHOW_ADDITIONAL_ROOMS = false;

  const blockedRooms = new Set(["Marillenzimmer", "Weinbergzimmer", "Donauzimmer"]);
  const API_BASE = String(window.ZAB_DIRECT_BOOKING_API_URL || "").replace(/\/+$/, "");
  const ATTRIBUTION_KEY = "zab_attribution_v1";

  function removeUnreleasedRooms() {
    if (window.SHOW_ADDITIONAL_ROOMS === true) return;

    document.querySelectorAll("[data-future-room]").forEach((element) => element.remove());

    document.querySelectorAll('input[name="room"]').forEach((input) => {
      if (blockedRooms.has(input.value)) input.closest(".choice")?.remove();
    });

    /* Auch in statischen Zimmerkarten keinerlei Freigabedatum oder Prognose zeigen. */
    document.querySelectorAll(".room-card").forEach((card) => {
      const title = (card.querySelector("h3")?.textContent || "").trim();
      if (!blockedRooms.has(title)) return;
      card.querySelectorAll("small, p, strong, span").forEach((node) => {
        const text = (node.textContent || "").trim();
        if (/15[./-]0?8[./-]2026|2026-0?8-1[56]|freigabe|buchbar ab|available from|prepared from|od 15|desde 15|à partir du 15/i.test(text)) {
          node.remove();
        }
      });
      if (!card.querySelector(".zab-room-status")) {
        const status = document.createElement("p");
        status.className = "zab-room-status";
        status.textContent = "Derzeit nicht buchbar.";
        card.querySelector("div")?.appendChild(status);
      }
    });

    const bachblick = document.querySelector('input[name="room"][value="Bachblick"]');
    if (bachblick) {
      bachblick.disabled = false;
      bachblick.checked = true;
    }
  }

  function scrubReleaseDates(root = document) {
    if (window.SHOW_ADDITIONAL_ROOMS === true) return;
    const walker = document.createTreeWalker(root.body || root, NodeFilter.SHOW_TEXT);
    const replacements = [
      [/ab\s+15\.08\.2026,?\s*erst nach Freigabe/gi, "derzeit nicht buchbar"],
      [/ab\s+15\.08\.2026/gi, ""],
      [/from\s+15\/08\/2026,?\s*after release/gi, "currently not bookable"],
      [/prepared from\s+15\/08\/2026[^.]*\.?/gi, "currently not bookable."],
      [/od\s+15\.\s*8\.\s*2026[^,.;]*/gi, "zatím nelze rezervovat"],
      [/2026\.08\.15-től[^,.;]*/gi, "jelenleg nem foglalható"],
      [/desde\s+15\/08\/2026[^,.;]*/gi, "actualmente no reservable"],
      [/à partir du\s+15\/08\/2026[^,.;]*/gi, "actuellement non réservable"]
    ];
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((textNode) => {
      let value = textNode.nodeValue || "";
      replacements.forEach(([pattern, replacement]) => { value = value.replace(pattern, replacement); });
      textNode.nodeValue = value;
    });
  }

  function captureAttribution() {
    const params = new URLSearchParams(window.location.search);
    let saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(ATTRIBUTION_KEY) || "{}"); } catch (_) {}
    const current = {
      source: params.get("utm_source") || saved.source || "",
      medium: params.get("utm_medium") || saved.medium || "",
      campaign: params.get("utm_campaign") || saved.campaign || "",
      referrer: saved.referrer || document.referrer || ""
    };
    if (params.get("utm_source") || params.get("utm_medium") || params.get("utm_campaign") || (!saved.referrer && document.referrer)) {
      try { sessionStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(current)); } catch (_) {}
    }
    return current;
  }

  function addEvergreenLanguageLinks() {
    if (document.getElementById("zab-evergreen-languages")) return;
    const switcher = document.querySelector(".language-switcher");
    if (!switcher) return;
    const nav = document.createElement("div");
    nav.id = "zab-evergreen-languages";
    nav.setAttribute("aria-label", "Internationale Seiten");
    nav.innerHTML = [
      ['./', 'DE', 'de-AT'],
      ['en/', 'EN', 'en'],
      ['cs/', 'CZ', 'cs'],
      ['sk/', 'SK', 'sk'],
      ['hu/', 'HU', 'hu'],
      ['pl/', 'PL', 'pl'],
      ['nl/', 'NL', 'nl']
    ].map(([href,label,lang]) => `<a href="${href}" hreflang="${lang}">${label}</a>`).join('');
    const style = document.createElement("style");
    style.textContent = `
      #zab-evergreen-languages{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;width:100%;margin-top:4px}
      #zab-evergreen-languages a{display:inline-grid;place-items:center;min-width:34px;min-height:30px;padding:4px 8px;border-radius:999px;background:rgba(255,255,255,.93);color:#17211f;text-decoration:none;font-size:12px;font-weight:900;box-shadow:0 2px 8px rgba(0,0,0,.16)}
      .zab-room-status{margin-top:6px!important;padding:7px 9px;border-radius:8px;background:#f4f0e8;color:#715725!important;font-size:12px!important;font-weight:800}
      .zab-direct-send-ok{padding:12px;border-radius:10px;background:#e8f7ef;color:#155f48;font-weight:850}
      .zab-direct-send-error{padding:12px;border-radius:10px;background:#fff0eb;color:#8c341f;font-weight:850}
      @media(max-width:640px){#zab-evergreen-languages{justify-content:center;margin:6px 0 2px}}
    `;
    document.head.appendChild(style);
    switcher.appendChild(nav);
  }

  function selectedExtra(form, value) {
    return Array.from(form.querySelectorAll('input[name="extra"]:checked')).some((input) => input.value === value);
  }

  function formValue(id) {
    return (document.getElementById(id)?.value || "").trim();
  }

  function directInquiryPayload(form) {
    const attribution = captureAttribution();
    return {
      room: form.querySelector('input[name="room"]:checked')?.value || "",
      arrival: formValue("arrival"),
      departure: formValue("departure"),
      adults: Number(formValue("adults") || 0),
      first_name: formValue("firstName"),
      last_name: formValue("lastName"),
      email: formValue("email"),
      phone: formValue("phone"),
      message: formValue("message"),
      extras: {
        breakfast: selectedExtra(form, "Frühstück"),
        jause: selectedExtra(form, "Wachauer Jause"),
        luggage: Boolean(document.getElementById("luggageTransport")?.checked)
      },
      source: attribution.source,
      utm_medium: attribution.medium,
      utm_campaign: attribution.campaign,
      page: window.location.href,
      referrer: attribution.referrer,
      website: ""
    };
  }

  function showLegacyFallback(payload, errorMessage) {
    const sendOptions = document.getElementById("sendOptions");
    const sendEmailLink = document.getElementById("sendEmailLink");
    const sendWhatsappLink = document.getElementById("sendWhatsappLink");
    const statusBox = document.getElementById("status");
    const subject = `Direktanfrage Zuhause am Bach: ${payload.arrival} bis ${payload.departure}`;
    const extras = [
      payload.extras.breakfast ? "Frühstück" : "",
      payload.extras.jause ? "Wachauer Jause" : "",
      payload.extras.luggage ? "Gepäcktransport" : ""
    ].filter(Boolean).join(", ") || "keine";
    const body = [
      `Gast: ${payload.first_name} ${payload.last_name}`,
      `Zimmer: ${payload.room}`,
      `Anreise: ${payload.arrival}`,
      `Abreise: ${payload.departure}`,
      `Personen: ${payload.adults}`,
      `Zusatzleistungen: ${extras}`,
      `Telefon: ${payload.phone}`,
      `E-Mail: ${payload.email}`,
      `Nachricht: ${payload.message || 'keine'}`,
      payload.source ? `Quelle: ${payload.source}` : ""
    ].filter(Boolean).join("\n");
    if (sendEmailLink) sendEmailLink.href = "mailto:Zuhause.am.Bach@outlook.com?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
    if (sendWhatsappLink) sendWhatsappLink.href = "https://wa.me/436646437526?text=" + encodeURIComponent(subject + "\n\n" + body);
    if (sendOptions) sendOptions.classList.add("show");
    if (statusBox) {
      statusBox.className = "status show zab-direct-send-error";
      statusBox.textContent = errorMessage || "Direktversand konnte nicht bestätigt werden. Bitte E-Mail oder WhatsApp verwenden.";
    }
    sendOptions?.scrollIntoView({behavior:"smooth",block:"center"});
  }

  function installOneClickInquiry() {
    const form = document.getElementById("requestForm");
    const submit = document.getElementById("submitRequest");
    if (!form || !submit || !API_BASE || form.dataset.zabDirectInquiry === "1") return;
    form.dataset.zabDirectInquiry = "1";

    form.addEventListener("submit", async (event) => {
      if (form.classList.contains("zab-paypal-primary") || form.classList.contains("zab-booking-blocked")) return;
      event.preventDefault();
      event.stopImmediatePropagation();

      if (!form.reportValidity()) return;
      const payload = directInquiryPayload(form);
      if (payload.room !== "Bachblick") {
        showLegacyFallback(payload, "Dieses Zimmer ist derzeit nicht für Direktanfragen freigegeben.");
        return;
      }

      const oldText = submit.textContent;
      submit.disabled = true;
      submit.setAttribute("aria-busy", "true");
      submit.textContent = "Anfrage wird direkt gesendet …";
      const statusBox = document.getElementById("status");
      try {
        const response = await fetch(API_BASE + "/api/inquiry", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          cache: "no-store",
          body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) throw new Error(result.message || "Direktversand nicht bestätigt.");

        window.zabTrack?.("direct_inquiry_sent", {
          inquiry_id: result.inquiry_id,
          source: payload.source || "direct",
          campaign: payload.utm_campaign || ""
        });
        document.getElementById("sendOptions")?.classList.remove("show");
        if (statusBox) {
          statusBox.className = "status show zab-direct-send-ok";
          statusBox.textContent = "✓ Ihre Anfrage wurde direkt an Zuhause am Bach übermittelt. Sie ist noch keine verbindliche Buchung; wir bestätigen sie persönlich.";
          statusBox.scrollIntoView({behavior:"smooth",block:"center"});
        }
        submit.textContent = "✓ Anfrage direkt übermittelt";
      } catch (error) {
        showLegacyFallback(payload, error.message || "Direktversand nicht erreichbar. Bitte E-Mail oder WhatsApp verwenden.");
        submit.disabled = false;
        submit.textContent = oldText;
      } finally {
        submit.removeAttribute("aria-busy");
      }
    }, true);
  }

  document.addEventListener("DOMContentLoaded", () => {
    captureAttribution();
    removeUnreleasedRooms();
    scrubReleaseDates();
    document.getElementById("zab-evergreen-languages")?.remove();
    installOneClickInquiry();

    const form = document.getElementById("requestForm");
    ["input", "change"].forEach((eventName) => {
      form?.addEventListener(eventName, () => {
        removeUnreleasedRooms();
        setTimeout(() => {
          removeUnreleasedRooms();
          scrubReleaseDates();
        }, 0);
      });
    });

    document.querySelectorAll("[data-lang], #mobileLanguage").forEach((element) => {
      element.addEventListener("click", () => setTimeout(() => { removeUnreleasedRooms(); scrubReleaseDates(); }, 0));
      element.addEventListener("change", () => setTimeout(() => { removeUnreleasedRooms(); scrubReleaseDates(); }, 0));
    });

    /* index.html laedt das Checkout-Script bereits. Nur als Fallback nachladen. */
    if (!document.querySelector('script[src*="zab-paypal-checkout.js"]')) {
      const script = document.createElement("script");
      script.src = "zab-paypal-checkout.js?v=20260902-1";
      script.defer = true;
      script.dataset.zabPaypalCheckout = "1";
      document.body.appendChild(script);
    }
  });
})();

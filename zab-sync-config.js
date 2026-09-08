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
      submit.textContent = "Direktbuchung wird vorbereitet …";
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
          statusBox.textContent = "✓ Ihre Buchungsanfrage wurde direkt übermittelt. Sobald wir sie persönlich bestätigen, ist Ihre Buchung verbindlich.";
          statusBox.scrollIntoView({behavior:"smooth",block:"center"});
        }
        submit.textContent = "✓ Buchungsanfrage übermittelt";
      } catch (error) {
        showLegacyFallback(payload, error.message || "Direktversand nicht erreichbar. Bitte E-Mail oder WhatsApp verwenden.");
        submit.disabled = false;
        submit.textContent = oldText;
      } finally {
        submit.removeAttribute("aria-busy");
      }
    }, true);
  }

  function strengthenStagePositioning() {
    const path = window.location.pathname || "";
    const isGermanHome = !/\/(en|cs|sk|hu|pl|nl)\//.test(path);
    if (!isGermanHome) return;

    document.title = "Zuhause am Bach – Direkt buchen in der Wachau | Donauradweg & Welterbesteig";

    const description = document.querySelector('meta[name="description"]');
    if (description) {
      description.setAttribute("content", "Zuhause am Bach in Aggsbach Markt direkt buchen: Direktpreis, Live-Verfügbarkeit, sichere Fahrradunterbringung, E-Bike laden, Frühstück und persönliche Wachau-Tipps.");
    }

    const desktopTitle = document.querySelector(".desktop-hero-title");
    if (desktopTitle) desktopTitle.textContent = "Zuhause am Bach – direkt bei den Gastgebern buchen";

    const mobileTitle = document.querySelector(".mobile-hero-title");
    if (mobileTitle) mobileTitle.textContent = "Zuhause am Bach – direkt buchen";

    const mobileBenefits = document.querySelector(".mobile-hero-benefits");
    if (mobileBenefits) mobileBenefits.innerHTML = "✓ Direktpreis · ✓ Live-Verfügbarkeit<br>🚴 Fahrrad sicher · ⚡ E-Bike laden · 🍳 Frühstück";

    const heroTrust = document.querySelector(".hero-trust");
    if (heroTrust && !heroTrust.querySelector("[data-zab-dry]")) {
      const dry = document.createElement("span");
      dry.dataset.zabDry = "1";
      dry.textContent = "✓ Kleidung trocknen";
      heroTrust.appendChild(dry);
    }

    const bookingIntro = document.querySelector(".booking-intro");
    if (bookingIntro) {
      bookingIntro.textContent = "Reisedaten wählen, Live-Verfügbarkeit prüfen und Ihren Direktpreis sehen. Bei eindeutig freiem Termin können Sie direkt bezahlen; die persönliche Bestätigung macht die Buchung verbindlich.";
    }
  }

  function optimizeDirectBookingCopy() {
    const path = window.location.pathname || "";
    if (/\/(en|cs|sk|hu|pl|nl)\//.test(path)) return;

    const bookingTitle = document.getElementById("booking-title");
    if (bookingTitle) bookingTitle.textContent = "Verfügbarkeit prüfen & direkt buchen";

    const kicker = document.querySelector(".booking-kicker");
    if (kicker) kicker.textContent = "Direktpreis · Live-Verfügbarkeit · Persönliche Bestätigung";

    const directTrust = document.querySelector(".direct-booking-trust");
    if (directTrust) {
      const strong = directTrust.querySelector("strong");
      const span = directTrust.querySelector("span");
      const small = directTrust.querySelector("small");
      if (strong) strong.textContent = "Direkt bei Zuhause am Bach";
      if (span) span.textContent = "Reisedaten prüfen, transparenten Direktpreis sehen und bei freiem Termin direkt bezahlen.";
      if (small) small.textContent = "Ohne Umweg über eine zusätzliche Buchungsplattform.";
    }

    const directBoxTitle = document.getElementById("zab-direct-title");
    if (directBoxTitle) directBoxTitle.textContent = "Ihr direkter Weg zur Buchung";
    const directBox = document.getElementById("zab-direct-box");
    const directBoxText = directBox?.querySelector("p");
    if (directBoxText) directBoxText.textContent = "1. Reisedaten wählen. 2. Live-Verfügbarkeit und Direktpreis prüfen. 3. Bei freiem Termin direkt bezahlen. 4. Persönliche Buchungsbestätigung erhalten.";

    const submit = document.getElementById("submitRequest");
    if (submit && !submit.disabled && !/^✓/.test(submit.textContent || "")) submit.textContent = "Verfügbarkeit prüfen & Direktpreis sichern";

    const status = document.getElementById("status");
    if (status && !status.classList.contains("show")) status.textContent = "Ihre Anfrage wird direkt an uns übermittelt. Verbindlich wird die Buchung mit unserer persönlichen Bestätigung.";

    const sendTitle = document.getElementById("sendOptionsTitle");
    if (sendTitle) sendTitle.textContent = "Buchungsanfrage vorbereitet";
    const sendText = document.getElementById("sendOptionsText");
    if (sendText) sendText.textContent = "Falls der Direktversand nicht klappt, wählen Sie hier E-Mail oder WhatsApp.";

    const directAdvantagesTitle = document.getElementById("direkt-vorteile-title");
    if (directAdvantagesTitle) directAdvantagesTitle.textContent = "Direkt buchen – transparent und persönlich";
    const directAdvantages = document.querySelector("#direkt-vorteile .section-head p");
    if (directAdvantages) directAdvantages.textContent = "Reisedaten und Zimmer wählen, Direktpreis prüfen und ohne zusätzliche Buchungsplattform direkt mit Zuhause am Bach buchen.";

    const heroEyebrow = document.querySelector(".hero-copy .eyebrow");
    if (heroEyebrow) heroEyebrow.textContent = "Direktpreis statt Plattform-Umweg";
  }

  function loadWinterJauerlingPromo() {
    const path = window.location.pathname || "";
    const isGermanHome = !/\/(en|cs|sk|hu|pl|nl)\//.test(path);
    const month = new Date().getMonth() + 1;
    const winterWindow = month >= 9 || month <= 3;
    if (!isGermanHome || !winterWindow || document.querySelector('script[src*="winter-jauerling-promo.js"]')) return;
    const script = document.createElement("script");
    script.src = "winter-jauerling-promo.js?v=20260906-1";
    script.defer = true;
    script.dataset.zabWinterJauerling = "1";
    document.body.appendChild(script);
  }

  document.addEventListener("DOMContentLoaded", () => {
    captureAttribution();
    strengthenStagePositioning();
    removeUnreleasedRooms();
    scrubReleaseDates();
    document.getElementById("zab-evergreen-languages")?.remove();
    installOneClickInquiry();
    loadWinterJauerlingPromo();
    optimizeDirectBookingCopy();
    setTimeout(optimizeDirectBookingCopy, 0);

    const form = document.getElementById("requestForm");
    ["input", "change"].forEach((eventName) => {
      form?.addEventListener(eventName, () => {
        removeUnreleasedRooms();
        setTimeout(() => {
          removeUnreleasedRooms();
          scrubReleaseDates();
          optimizeDirectBookingCopy();
        }, 0);
      });
    });

    document.querySelectorAll("[data-lang], #mobileLanguage").forEach((element) => {
      element.addEventListener("click", () => setTimeout(() => { removeUnreleasedRooms(); scrubReleaseDates(); optimizeDirectBookingCopy(); }, 0));
      element.addEventListener("change", () => setTimeout(() => { removeUnreleasedRooms(); scrubReleaseDates(); optimizeDirectBookingCopy(); }, 0));
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
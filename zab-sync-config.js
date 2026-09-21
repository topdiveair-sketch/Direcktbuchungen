window.ZAB_BOOKING_SYNC_URL = "https://PASTE-YOUR-WORKER.workers.dev";

/* Railway-Backend fuer serverseitig gepruefte Direktbuchung + PayPal. */
window.ZAB_DIRECT_BOOKING_API_URL = "https://web-production-2b242.up.railway.app";

(function () {
  "use strict";

  /* Auf der Homepage wird ausschließlich das Gartenzimmer angeboten.
     Der technische Zimmerwert "Bachblick" bleibt für die bestehende Backend-Schnittstelle erhalten. */
  window.SHOW_ADDITIONAL_ROOMS = false;

  const API_BASE = String(window.ZAB_DIRECT_BOOKING_API_URL || "").replace(/\/+$/, "");
  const ATTRIBUTION_KEY = "zab_attribution_v1";

  function removeUnreleasedRooms() {
    document.querySelectorAll("[data-future-room]").forEach((element) => element.remove());

    document.querySelectorAll('input[name="room"]').forEach((input) => {
      if (input.value !== "Bachblick") input.closest(".choice")?.remove();
    });

    document.querySelectorAll(".room-card").forEach((card) => {
      const title = (card.querySelector("h3")?.textContent || "").trim();
      if (title && title !== "Gartenzimmer") card.remove();
    });

    const primaryRoom = document.querySelector('input[name="room"][value="Bachblick"]');
    if (primaryRoom) {
      primaryRoom.disabled = false;
      primaryRoom.checked = true;
    }

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const removePatterns = [
      /Bis einschließlich\s*15\.08\.2026[^.]*\./gi,
      /Ab\s*16\.08\.2026[^.]*\./gi,
      /nur das Zimmer\s*Bachblick[^.]*\./gi,
      /alle vier Zimmer[^.]*\./gi
    ];
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      let value = node.nodeValue || "";
      removePatterns.forEach((pattern) => { value = value.replace(pattern, ""); });
      node.nodeValue = value;
    });
  }

  function scrubReleaseDates() {
    /* Keine Freigabedaten oder Hinweise auf weitere Zimmer öffentlich anzeigen. */
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

  function installSalesHomepageUpgrade() {
    const path = window.location.pathname || "";
    if (/\/(en|cs|sk|hu|pl|nl)\//.test(path) || document.getElementById("zab-sales-upgrade")) return;

    const style = document.createElement("style");
    style.id = "zab-sales-upgrade";
    style.textContent = `
      .zab-sales-proof{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:18px}
      .zab-sales-proof span{padding:12px;border:1px solid rgba(255,255,255,.4);border-radius:12px;background:rgba(12,42,34,.62);color:#fff;font-size:13px;font-weight:850;text-align:center;backdrop-filter:blur(4px)}
      .zab-booking-reasons{display:grid;gap:9px;margin:4px 0 2px;padding:13px;border-radius:12px;background:#fff7e8;border:1px solid #ead8b6}
      .zab-booking-reasons strong{color:#17372f;font-size:14px}
      .zab-booking-reasons ul{display:grid;gap:5px;margin:0;padding-left:20px;color:#455e56;font-size:13px;font-weight:750}
      .zab-sales-section{padding:46px min(5vw,56px);background:#fffaf0}
      .zab-sales-section h2{margin:0 0 10px;font-size:clamp(28px,4vw,42px);color:#17372f}
      .zab-sales-section>p{max-width:820px;margin:0 0 22px;color:#5f6f69}
      .zab-sales-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
      .zab-sales-card{padding:20px;border:1px solid #d8e2dd;border-radius:16px;background:#fff;box-shadow:0 10px 25px rgba(20,38,32,.07)}
      .zab-sales-card strong{display:block;margin-bottom:7px;color:#176b5a;font-size:18px}
      .zab-sales-card p{margin:0;color:#5f6f69;font-size:14px}
      .zab-sales-cta{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:22px}
      .zab-sales-cta a{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:11px 18px;border-radius:9px;background:#176b5a;color:#fff;text-decoration:none;font-weight:900}
      .zab-sales-cta small{color:#5f6f69;font-weight:750}
      @media(max-width:760px){.zab-sales-proof,.zab-sales-grid{grid-template-columns:1fr 1fr}.zab-sales-proof span{font-size:12px}}
      @media(max-width:480px){.zab-sales-proof,.zab-sales-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);

    const heroP = document.querySelector(".hero-copy > p:not(.mobile-hero-benefits)");
    if (heroP) heroP.textContent = "Ihre persönliche Wachau-Basis direkt am Welterbesteig und nahe dem Donauradweg: ruhig schlafen, Fahrrad sicher abstellen, E-Bike laden und auf Wunsch mit Frühstück in den Tag starten.";

    const trust = document.querySelector(".hero-trust");
    if (trust) {
      trust.innerHTML = "<span>✓ Persönlich geführt</span><span>✓ Fahrrad sicher</span><span>✓ E-Bike laden</span><span>✓ Frühstück auf Wunsch</span>";
      const proof = document.createElement("div");
      proof.className = "zab-sales-proof";
      proof.innerHTML = "<span>🚴 Für Donauradweg-Gäste</span><span>🥾 Für Welterbesteig-Wanderer</span><span>🅿 Kostenlos parken</span><span>📱 Digitale Gäste-App</span>";
      trust.after(proof);
    }

    const intro = document.querySelector(".booking-intro");
    if (intro) intro.textContent = "In weniger als einer Minute: Reisedaten wählen, Live-Verfügbarkeit prüfen, Direktpreis sehen und bei freiem Termin direkt bezahlen.";

    const directTrust = document.querySelector(".direct-booking-trust");
    if (directTrust) {
      directTrust.innerHTML = "<strong>Direkt buchen statt Plattform-Umweg</strong><span>Live-Verfügbarkeit und transparenter Direktpreis direkt bei Zuhause am Bach.</span><small>Persönliche Gastgeber bleiben Ihre direkten Ansprechpartner.</small>";
      const reasons = document.createElement("div");
      reasons.className = "zab-booking-reasons";
      reasons.innerHTML = "<strong>Darum passt Zuhause am Bach zu Ihrer Wachau-Reise:</strong><ul><li>ruhiger Ausgangspunkt zwischen Melk und Dürnstein</li><li>abschließbare Fahrrad-Unterbringung und E-Bike-Lademöglichkeit</li><li>Trockenmöglichkeit für Wander- und Radbekleidung</li><li>Frühstück auf Vorbestellung, auch vegetarisch oder vegan</li></ul>";
      directTrust.after(reasons);
    }

    const header = document.querySelector("header.top");
    if (header) {
      const section = document.createElement("section");
      section.className = "zab-sales-section";
      section.setAttribute("aria-label","Warum Zuhause am Bach");
      section.innerHTML = `
        <h2>Die Wachau erleben – ohne an Kleinigkeiten denken zu müssen</h2>
        <p>Zuhause am Bach ist bewusst keine anonyme Großunterkunft. Sie wohnen persönlich, ruhig und mit genau den Leistungen, die für eine Wander-, Rad- oder Genussreise in der Wachau praktisch sind.</p>
        <div class="zab-sales-grid">
          <article class="zab-sales-card"><strong>Für Radfahrer</strong><p>Fahrrad sicher unterbringen, E-Bike laden und am nächsten Morgen direkt weiter Richtung Melk, Spitz oder Dürnstein.</p></article>
          <article class="zab-sales-card"><strong>Für Wanderer</strong><p>Welterbesteig vor der Haustür, Trockenmöglichkeit für Kleidung und Unterstützung beim Gepäcktransport nach Vereinbarung.</p></article>
          <article class="zab-sales-card"><strong>Für Genießer</strong><p>Ruhige Nächte, Frühstück auf Wunsch und persönliche Empfehlungen für Heurige, Ausflüge und besondere Plätze der Wachau.</p></article>
        </div>
        <div class="zab-sales-cta"><a href="#booking-title">Jetzt Verfügbarkeit prüfen</a><small>Reisedaten eingeben → Direktpreis sehen → freien Termin buchen</small></div>
      `;
      header.after(section);

      const proofSection = document.createElement("section");
      proofSection.className = "zab-sales-section";
      proofSection.setAttribute("aria-label","Gästestimmen und Passung");
      proofSection.innerHTML = `
        <h2>Persönlich geführt – und genau dafür geschätzt</h2>
        <p>Gäste bewerten besonders die herzliche Betreuung, die ruhige Lage, das Frühstück und die Eignung für Radreisen. Auf Booking.com liegt Zuhause am Bach aktuell bei 8,8/10, die Gastgeberbewertung bei 9,8/10 und das Preis-Leistungs-Verhältnis bei 9,2/10 (Stand September 2026).</p>
        <div class="zab-sales-grid">
          <article class="zab-sales-card"><strong>„Ideal mit dem Fahrrad“</strong><p>Mehrere Gäste heben die sichere Fahrradunterbringung, die ruhige Lage und die gute Eignung für eine Donauradweg-Etappe hervor.</p></article>
          <article class="zab-sales-card"><strong>Frühstück, das in Erinnerung bleibt</strong><p>Bewertungen beschreiben das Frühstück wiederholt als reichhaltig, liebevoll vorbereitet und besonders angenehm vor einem aktiven Tag.</p></article>
          <article class="zab-sales-card"><strong>Persönlich statt anonym</strong><p>Die Unterkunft ist bewusst privat geführt. Wer direkten Kontakt, ehrliche Wachau-Tipps und eine familiäre Atmosphäre schätzt, ist hier richtig.</p></article>
        </div>
        <div class="zab-sales-cta"><a href="https://www.booking.com/hotel/at/zu-hause-am-bach.de.html" target="_blank" rel="noopener">Aktuelle Gästebewertungen ansehen</a><small>Externe Bewertungen bei Booking.com</small></div>
      `;
      section.after(proofSection);

      const fitSection = document.createElement("section");
      fitSection.className = "zab-sales-section";
      fitSection.setAttribute("aria-label","Passt Zuhause am Bach zu mir");
      fitSection.innerHTML = `
        <h2>Passt Zuhause am Bach zu Ihrer Reise?</h2>
        <p>Wir möchten, dass die Unterkunft wirklich zu Ihnen passt. Das verhindert Enttäuschungen und macht den Aufenthalt für beide Seiten angenehmer.</p>
        <div class="zab-sales-grid">
          <article class="zab-sales-card"><strong>Sehr passend, wenn …</strong><p>Sie die Wachau aktiv erleben, ruhig schlafen, persönliche Gastgeber schätzen und lieber direkt als anonym übernachten.</p></article>
          <article class="zab-sales-card"><strong>Gut zu wissen</strong><p>Zum Zuhause gehören die freundlichen Windhunde Fidel, Gloria und Pia. Bei Hundeangst oder Hundeallergie ist die Unterkunft daher möglicherweise nicht die beste Wahl.</p></article>
          <article class="zab-sales-card"><strong>Klare Hausregeln</strong><p>Nichtraucher-Unterkunft, keine Partys und keine mitgebrachten Haustiere. So bleibt es ruhig und angenehm für alle Gäste.</p></article>
        </div>
        <div class="zab-sales-cta"><a href="#booking-title">Passt für mich – Verfügbarkeit prüfen</a><small>Direktpreis und freie Termine sofort prüfen</small></div>
      `;
      proofSection.after(fitSection);
    }

    const submit = document.getElementById("submitRequest");
    if (submit && !submit.disabled && !/^✓/.test(submit.textContent || "")) submit.textContent = "Jetzt Verfügbarkeit & Direktpreis prüfen";
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
    installSalesHomepageUpgrade();
    setTimeout(() => { optimizeDirectBookingCopy(); installSalesHomepageUpgrade(); }, 0);

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
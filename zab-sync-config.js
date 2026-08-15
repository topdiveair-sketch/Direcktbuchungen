window.ZAB_BOOKING_SYNC_URL = "https://PASTE-YOUR-WORKER.workers.dev";

(function () {
  const RELEASE_DATE = "2026-08-16";

  function viennaDateIso() {
    try {
      const parts = new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Europe/Vienna",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      }).formatToParts(new Date());
      const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      return `${values.year}-${values.month}-${values.day}`;
    } catch (error) {
      return new Date().toISOString().slice(0, 10);
    }
  }

  window.SHOW_ADDITIONAL_ROOMS = viennaDateIso() >= RELEASE_DATE;

  const dateReplacements = [
    ["15.08.2026", "16.08.2026"],
    ["15/08/2026", "16/08/2026"],
    ["15. 8. 2026", "16. 8. 2026"],
    ["2026.08.15", "2026.08.16"]
  ];

  const releasedLabel = {
    de: "ab 90 EUR pro Nacht",
    en: "from 90 EUR per night",
    cs: "od 90 EUR za noc",
    hu: "90 EUR/éj ártól",
    es: "desde 90 EUR por noche",
    fr: "à partir de 90 EUR par nuit"
  };

  const pendingLabel = {
    de: "buchbar ab 16.08.2026",
    en: "bookable from 16/08/2026",
    cs: "rezervovatelné od 16. 8. 2026",
    hu: "foglalható 2026.08.16-tól",
    es: "reservable desde el 16/08/2026",
    fr: "réservable à partir du 16/08/2026"
  };

  function patchRoomReleaseUi() {
    const released = window.SHOW_ADDITIONAL_ROOMS === true;
    const lang = (document.documentElement.lang || "de").slice(0, 2);

    document.querySelectorAll("[data-future-room]").forEach((element) => {
      element.hidden = !released;
      const input = element.querySelector('input[name="room"]');
      if (input) input.dataset.from = RELEASE_DATE;

      if (element.matches("article.room-card")) {
        const status = element.querySelector("strong");
        if (status) status.textContent = released
          ? (releasedLabel[lang] || releasedLabel.de)
          : (pendingLabel[lang] || pendingLabel.de);
      }
    });

    document.querySelectorAll('input[name="room"][data-from]').forEach((input) => {
      if (input.value !== "Bachblick") input.dataset.from = RELEASE_DATE;
    });

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      let value = node.nodeValue;
      if (!value || !value.trim()) continue;
      for (const [from, to] of dateReplacements) value = value.split(from).join(to);
      if (value !== node.nodeValue) node.nodeValue = value;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    patchRoomReleaseUi();

    document.querySelectorAll("[data-lang], #mobileLanguage").forEach((element) => {
      element.addEventListener("click", () => setTimeout(patchRoomReleaseUi, 0));
      element.addEventListener("change", () => setTimeout(patchRoomReleaseUi, 0));
    });
  });
})();

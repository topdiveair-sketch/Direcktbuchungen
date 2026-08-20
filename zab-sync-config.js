window.ZAB_BOOKING_SYNC_URL = "https://PASTE-YOUR-WORKER.workers.dev";

(function () {
  const RELEASE_DATE = "2026-08-16";

  /* Sicherheitsregel: Zusatz­zimmer werden niemals automatisch nach Datum
     freigegeben. Sichtbarkeit nur nach ausdrücklicher manueller Freigabe. */
  window.SHOW_ADDITIONAL_ROOMS = false;

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
    de: "noch nicht freigegeben",
    en: "not released yet",
    cs: "zatím neuvolněno",
    hu: "még nincs felszabadítva",
    es: "aún no liberada",
    fr: "pas encore libérée"
  };

  function patchRoomReleaseUi() {
    const released = window.SHOW_ADDITIONAL_ROOMS === true;
    const lang = (document.documentElement.lang || "de").slice(0, 2);

    document.querySelectorAll("[data-future-room]").forEach((element) => {
      element.hidden = !released;
      const input = element.querySelector('input[name="room"]');
      if (input) {
        input.dataset.from = RELEASE_DATE;
        input.disabled = !released;
        if (!released) input.checked = false;
      }

      if (element.matches("article.room-card")) {
        const status = element.querySelector("strong");
        if (status) status.textContent = released
          ? (releasedLabel[lang] || releasedLabel.de)
          : (pendingLabel[lang] || pendingLabel.de);
      }
    });

    if (!released) {
      const bachblick = document.querySelector('input[name="room"][value="Bachblick"]');
      if (bachblick) bachblick.checked = true;
    }

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

    document.querySelectorAll("[data-lang], #mobileLanguage, #arrival, #departure").forEach((element) => {
      element.addEventListener("click", () => setTimeout(patchRoomReleaseUi, 0));
      element.addEventListener("input", () => setTimeout(patchRoomReleaseUi, 0));
      element.addEventListener("change", () => setTimeout(patchRoomReleaseUi, 0));
    });
  });
})();

window.ZAB_BOOKING_SYNC_URL = "https://PASTE-YOUR-WORKER.workers.dev";

(function () {
  /* Zusatz­zimmer nur nach ausdrücklicher manueller Freigabe anzeigen. */
  window.SHOW_ADDITIONAL_ROOMS = false;

  const blockedRooms = new Set(["Marillenzimmer", "Weinbergzimmer", "Donauzimmer"]);

  function removeUnreleasedRooms() {
    if (window.SHOW_ADDITIONAL_ROOMS === true) return;

    document.querySelectorAll("[data-future-room]").forEach((element) => element.remove());

    document.querySelectorAll('input[name="room"]').forEach((input) => {
      if (blockedRooms.has(input.value)) input.closest(".choice")?.remove();
    });

    const bachblick = document.querySelector('input[name="room"][value="Bachblick"]');
    if (bachblick) {
      bachblick.disabled = false;
      bachblick.checked = true;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    removeUnreleasedRooms();

    const form = document.getElementById("requestForm");
    ["input", "change"].forEach((eventName) => {
      form?.addEventListener(eventName, () => {
        removeUnreleasedRooms();
        setTimeout(removeUnreleasedRooms, 0);
      });
    });

    document.querySelectorAll("[data-lang], #mobileLanguage").forEach((element) => {
      element.addEventListener("click", () => setTimeout(removeUnreleasedRooms, 0));
      element.addEventListener("change", () => setTimeout(removeUnreleasedRooms, 0));
    });
  });
})();

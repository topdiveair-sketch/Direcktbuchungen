/* Stripe card option for the native Railway booking form.
   Hidden until the backend explicitly reports live checkout ready. */
(function () {
  "use strict";
  const form = document.getElementById("bookingForm");
  const grid = form?.querySelector(".payment-grid");
  if (!form || !grid) return;

  const field = name => (form.querySelector('[name="' + name + '"]')?.value || "").trim();
  const checked = id => Boolean(document.getElementById(id)?.checked);
  const note = document.createElement("p");
  note.setAttribute("role", "status");
  note.style.fontSize = "13px";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn full";
  button.textContent = "Mit Debit- oder Kreditkarte bezahlen";
  button.style.marginTop = "12px";
  button.disabled = true;
  let busy = false;

  function ready() {
    return !busy && form.checkValidity() &&
      Boolean(field("arrival") && field("departure") &&
      form.querySelector('input[name="room"]:checked')?.value === "Bachblick") &&
      !field("coupon_code") && !checked("luggage") &&
      !document.getElementById("guestArea")?.classList.contains("hidden") &&
      !document.getElementById("availabilityResult")?.classList.contains("hidden") &&
      !document.getElementById("bookingSubmit")?.disabled;
  }

  function update() {
    button.disabled = !ready();
    note.textContent = field("coupon_code")
      ? "Gutscheine bitte über die anderen Zahlungsarten einlösen."
      : checked("luggage")
        ? "Gepäcktransport bitte separat anfragen."
        : "Sichere Kartenzahlung über Stripe, nach erneuter Preis- und Terminprüfung.";
  }

  async function install() {
    try {
      const response = await fetch("/api/stripe/status", {cache:"no-store"});
      const status = await response.json();
      if (!response.ok || !status.ok || !status.configured || !status.webhook_configured) return;
    } catch (_) { return; }
    grid.after(button, note);
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    new MutationObserver(update).observe(document.getElementById("bookingSubmit"), {attributes:true});
    update();
    button.addEventListener("click", async () => {
      if (!ready()) return;
      busy = true;
      update();
      try {
        const payload = {
          room: form.querySelector('input[name="room"]:checked')?.value,
          arrival: field("arrival"), departure: field("departure"),
          adults: Number(field("adults") || 2),
          first_name: field("first_name"), last_name: field("last_name"),
          email: field("email"), phone: field("phone"), message: field("message"),
          extras: {breakfast: checked("breakfast"), jause: checked("jause"),
                   luggage: checked("luggage")}
        };
        const response = await fetch("/api/stripe/create-checkout-session", {
          method:"POST", headers:{"Content-Type":"application/json"},
          cache:"no-store", body:JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok || !data.ok || !/^https:\/\/checkout\.stripe\.com\//.test(data.checkout_url || "")) {
          throw new Error(data.message || "Kartenzahlung derzeit nicht verfügbar.");
        }
        window.location.assign(data.checkout_url);
      } catch (error) {
        note.textContent = error.message || "Kartenzahlung nicht verfügbar.";
        busy = false;
        button.disabled = false;
      }
    });
  }
  install();
})();

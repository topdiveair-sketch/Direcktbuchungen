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

  // Lightweight, responsive badge directly below the live Stripe button.
  // No card brand is claimed beyond the successfully verified Mastercard test.
  const cardBadge = document.createElement("div");
  cardBadge.className = "zab-card-payment-badge";
  cardBadge.setAttribute("aria-label", "Debit- und Kreditkarten, Mastercard akzeptiert");
  cardBadge.innerHTML = `
    <span class="zab-card-payment-icons" aria-hidden="true">
      <span class="zab-card-icon zab-card-icon-blue"><span class="zab-card-chip"></span>)))</span>
      <span class="zab-card-icon zab-card-icon-light"><span class="zab-card-chip"></span>)))</span>
    </span>
    <span class="zab-card-payment-label"><strong>Debit- &amp; Kreditkarten</strong><small><span class="zab-mastercard-circles"><i></i><i></i></span> Mastercard akzeptiert</small></span>
    <span class="zab-card-payment-check" aria-hidden="true">✓</span>`;
  const badgeStyle = document.createElement("style");
  badgeStyle.textContent = `
    .zab-card-payment-badge{display:flex;align-items:center;justify-content:center;gap:12px;max-width:420px;margin:10px auto 5px;padding:9px 12px;border:1px solid #cbe7d2;border-radius:12px;background:#f7fcf8;color:#103f31;box-sizing:border-box}
    .zab-card-payment-icons{position:relative;display:block;width:76px;height:44px;flex:0 0 76px}
    .zab-card-icon{position:absolute;display:flex;align-items:center;justify-content:space-around;width:54px;height:33px;border-radius:6px;box-shadow:0 2px 5px #0002;font-size:12px;font-weight:bold}
    .zab-card-icon-blue{left:1px;top:1px;background:#0756a5;color:#fff;transform:rotate(-9deg)}
    .zab-card-icon-light{left:19px;top:11px;background:linear-gradient(130deg,#fff 45%,#98dfb0);color:#0b4975;transform:rotate(6deg)}
    .zab-card-chip{display:inline-block;width:13px;height:10px;background:#eac357;border:1px solid #bb8d2b;border-radius:2px}
    .zab-card-payment-label{display:flex;flex-direction:column;gap:3px;line-height:1.25;min-width:0}
    .zab-card-payment-label strong{font-size:14px;font-weight:700}
    .zab-card-payment-label small{font-size:12px;display:flex;align-items:center;gap:6px}
    .zab-mastercard-circles{display:inline-flex;align-items:center;width:28px;height:17px;flex:0 0 28px}
    .zab-mastercard-circles i{width:17px;height:17px;border-radius:50%;background:#eb001b}
    .zab-mastercard-circles i+i{background:#f79e1b;margin-left:-6px;opacity:.93}
    .zab-card-payment-check{display:grid;place-items:center;flex:0 0 24px;width:24px;height:24px;border-radius:50%;background:#26aa59;color:white;font-weight:bold}
    @media(max-width:420px){.zab-card-payment-badge{gap:7px;padding:8px}.zab-card-payment-icons{transform:scale(.83);transform-origin:left center;flex-basis:63px}.zab-card-payment-label strong{font-size:12px}.zab-card-payment-label small{font-size:11px}}
  `;

  let busy = false;

  function ready() {
    return !busy && form.checkValidity() &&
      Boolean(field("arrival") && field("departure") &&
      form.querySelector('input[name="room"]:checked')?.value === "Bachblick") &&
      !field("coupon_code") &&
      !document.getElementById("guestArea")?.classList.contains("hidden") &&
      !document.getElementById("availabilityResult")?.classList.contains("hidden") &&
      !document.getElementById("bookingSubmit")?.disabled;
  }

  function update() {
    button.disabled = !ready();
    note.textContent = field("coupon_code")
      ? "Gutscheine bitte über die anderen Zahlungsarten einlösen."
      : checked("luggage")
        ? `Gepäcktransport: ${Number(document.getElementById("luggage")?.dataset.price || 15).toLocaleString("de-AT", {style:"currency", currency:"EUR"})} pro Strecke für bis zu 2 Gäste. Im Gesamtpreis enthalten.`
        : "Sichere Kartenzahlung über Stripe, nach erneuter Preis- und Terminprüfung.";
  }

  async function install() {
    try {
      const response = await fetch("/api/stripe/status", {cache:"no-store"});
      const status = await response.json();
      if (!response.ok || !status.ok || !status.configured || !status.webhook_configured) return;
    } catch (_) { return; }
    document.head.appendChild(badgeStyle);
    grid.after(button, cardBadge, note);
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

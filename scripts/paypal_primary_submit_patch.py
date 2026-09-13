from pathlib import Path

js = Path("zab-paypal-checkout.js")
text = js.read_text(encoding="utf-8")

anchor = '''    paypalLink.removeAttribute("target");
    paypalLink.removeAttribute("rel");
    paypalLink.href="#";
    paypalLink.addEventListener("click",startCheckout,true);

    if(!configured()){
'''
replacement = '''    paypalLink.removeAttribute("target");
    paypalLink.removeAttribute("rel");
    paypalLink.href="#";
    paypalLink.addEventListener("click",startCheckout,true);

    // The primary form CTA must enter the same secure checkout path.
    // This prevents the legacy inquiry handler from winning on mobile when
    // a stay is eligible for instant direct booking.
    form.addEventListener("submit", async function(event){
      const data=payload();
      if(!configured() || !validDates(data) || data.extras.etappenjause || data.extras.luggage){
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();

      const ok=await verifyAvailability(data);
      if(!ok){
        setRequestFallback(true);
        paypalBox?.scrollIntoView({behavior:"smooth",block:"center"});
        return;
      }

      const missing=missingCustomer(data);
      if(missing){
        missing.focus();
        missing.scrollIntoView({behavior:"smooth",block:"center"});
        checkoutHeading(checkoutLang==="de" ? "Kontaktdaten vervollständigen" : "Complete your contact details");
        if(paypalHint) paypalHint.textContent=checkoutLang==="de"
          ? "Für die Sofortbuchung bitte zuerst Name, E-Mail und Telefonnummer vollständig eintragen."
          : "Please complete your name, email address and phone number before direct checkout.";
        return;
      }

      await startCheckout({preventDefault(){},stopImmediatePropagation(){}});
    },true);

    if(!configured()){
'''

if anchor not in text:
    raise SystemExit("Expected PayPal listener anchor not found")
text = text.replace(anchor, replacement, 1)
js.write_text(text, encoding="utf-8")

index = Path("index.html")
html = index.read_text(encoding="utf-8")
html = html.replace("zab-paypal-checkout.js?v=20260913-4", "zab-paypal-checkout.js?v=20260913-5")
index.write_text(html, encoding="utf-8")

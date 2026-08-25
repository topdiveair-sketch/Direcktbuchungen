(function(){
"use strict";

function ready(fn){
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn, {once:true});
  else fn();
}

ready(function(){
  const apiBase=String(window.ZAB_DIRECT_BOOKING_API_URL||"").replace(/\/+$/,"");
  const paypalLink=document.getElementById("paypalLink");
  const paypalBox=document.getElementById("paypalBox");
  const paypalHint=document.getElementById("paypalHint");
  const form=document.getElementById("requestForm");
  const availability=document.getElementById("availabilityStatus");
  if(!paypalLink||!form) return;

  function configured(){
    return /^https:\/\//i.test(apiBase) && !/(PASTE|DEIN|EXAMPLE|RAILWAY-DOMAIN)/i.test(apiBase);
  }

  function value(id){ return (document.getElementById(id)?.value||"").trim(); }
  function selectedRoom(){ return form.querySelector('input[name="room"]:checked'); }
  function selectedExtraByValue(name){
    return Array.from(form.querySelectorAll('input[name="extra"]:checked')).some(x=>x.value===name);
  }

  function payload(){
    const luggage=form.querySelector('#luggageTransport');
    return {
      room:selectedRoom()?.value||"",
      arrival:value("arrival"),
      departure:value("departure"),
      adults:Number(value("adults")||2),
      first_name:value("firstName"),
      last_name:value("lastName"),
      email:value("email"),
      phone:value("phone"),
      message:value("message"),
      extras:{
        breakfast:selectedExtraByValue("Frühstück"),
        jause:selectedExtraByValue("Wachauer Jause"),
        luggage:Boolean(luggage?.checked)
      }
    };
  }

  function missingCustomer(data){
    if(!data.first_name) return document.getElementById("firstName");
    if(!data.last_name) return document.getElementById("lastName");
    if(!data.email) return document.getElementById("email");
    if(!data.phone) return document.getElementById("phone");
    return null;
  }

  async function startCheckout(event){
    event.preventDefault();
    event.stopImmediatePropagation();

    if(!configured()){
      if(paypalHint) paypalHint.textContent="Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.";
      paypalLink.classList.add("hidden");
      paypalBox?.classList.remove("zab-paypal-ready");
      return;
    }
    if(!availability?.classList.contains("ok")){
      if(paypalHint) paypalHint.textContent="PayPal wird erst freigeschaltet, wenn der Termin eindeutig als frei erkannt wurde.";
      return;
    }

    const data=payload();
    const missing=missingCustomer(data);
    if(missing){
      missing.focus();
      missing.scrollIntoView({behavior:"smooth",block:"center"});
      if(paypalHint) paypalHint.textContent="Für die Sofortbuchung bitte zuerst Name, E-Mail und Telefonnummer vollständig eintragen.";
      return;
    }
    if(data.extras.luggage){
      if(paypalHint) paypalHint.textContent="Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.";
      document.getElementById("luggageTransport")?.focus();
      return;
    }

    const oldText=paypalLink.textContent;
    paypalLink.setAttribute("aria-busy","true");
    paypalLink.textContent="Termin wird nochmals geprüft …";
    paypalLink.style.pointerEvents="none";
    try{
      const response=await fetch(apiBase+"/api/paypal/create-order",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        cache:"no-store",
        body:JSON.stringify(data)
      });
      const result=await response.json().catch(()=>({}));
      if(!response.ok||!result.ok||!result.approval_url){
        throw new Error(result.message||"PayPal-Checkout konnte nicht gestartet werden.");
      }
      window.zabTrack?.("direct_paypal_checkout_started",{
        booking_id:result.booking_id,
        order_id:result.order_id,
        total:result.total
      });
      window.location.assign(result.approval_url);
    }catch(error){
      paypalLink.textContent=oldText;
      paypalLink.style.pointerEvents="";
      paypalLink.removeAttribute("aria-busy");
      if(paypalHint) paypalHint.textContent="Sofortbuchung nicht gestartet: "+(error.message||error)+" Bitte die Buchungsanfrage senden, wenn das Problem bleibt.";
    }
  }

  paypalLink.removeAttribute("target");
  paypalLink.removeAttribute("rel");
  paypalLink.href="#";
  paypalLink.addEventListener("click",startCheckout,true);

  if(!configured()){
    paypalLink.classList.add("hidden");
    paypalBox?.classList.remove("zab-paypal-ready");
    if(paypalHint) paypalHint.textContent="Sofortzahlung wird nach Einrichtung des sicheren PayPal-Checkouts aktiviert. Bis dahin bitte Buchungsanfrage senden.";
  }
});
})();

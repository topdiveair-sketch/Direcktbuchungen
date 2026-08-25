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

  let verifiedSignature="";
  let quoteTimer=0;
  let quoteSequence=0;

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

  function quoteSignature(data){
    return JSON.stringify({
      room:data.room,
      arrival:data.arrival,
      departure:data.departure,
      adults:data.adults,
      extras:data.extras
    });
  }

  function validDates(data){
    return /^\d{4}-\d{2}-\d{2}$/.test(data.arrival)
      && /^\d{4}-\d{2}-\d{2}$/.test(data.departure)
      && data.departure > data.arrival
      && Boolean(data.room);
  }

  function missingCustomer(data){
    if(!data.first_name) return document.getElementById("firstName");
    if(!data.last_name) return document.getElementById("lastName");
    if(!data.email) return document.getElementById("email");
    if(!data.phone) return document.getElementById("phone");
    return null;
  }

  function hidePayPal(message=""){
    verifiedSignature="";
    paypalLink.classList.add("hidden");
    paypalBox?.classList.remove("zab-paypal-ready");
    if(message && paypalHint) paypalHint.textContent=message;
  }

  function showChecking(){
    paypalBox?.classList.remove("hidden");
    paypalBox?.classList.remove("zab-paypal-ready");
    paypalLink.classList.add("hidden");
    if(paypalHint) paypalHint.textContent="Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …";
  }

  function showAvailable(data,result){
    verifiedSignature=quoteSignature(data);
    const total=Number(result.total||0);
    paypalBox?.classList.remove("hidden");
    paypalBox?.classList.add("zab-paypal-ready");
    paypalLink.classList.remove("hidden");
    paypalLink.textContent=total>0
      ? `Jetzt ${total.toFixed(2).replace(".",",")} EUR sicher mit PayPal buchen`
      : "Jetzt sicher mit PayPal buchen";
    if(paypalHint){
      paypalHint.textContent="✅ Termin ist laut aktuellem Booking-Kalender frei. Der Preis wird beim Start der Zahlung nochmals serverseitig geprüft.";
    }
    if(availability){
      availability.className="availability-status ok zab-backend-ok";
      availability.textContent="✅ Frei – live über den aktuellen Booking-Kalender geprüft.";
    }
  }

  async function verifyAvailability(data,{force=false}={}){
    if(!configured()){
      hidePayPal("Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.");
      return false;
    }
    if(!validDates(data)){
      hidePayPal();
      return false;
    }
    if(data.extras.luggage){
      hidePayPal("Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.");
      return false;
    }

    const signature=quoteSignature(data);
    if(!force && verifiedSignature===signature && !paypalLink.classList.contains("hidden")) return true;

    const sequence=++quoteSequence;
    showChecking();
    try{
      const response=await fetch(apiBase+"/api/paypal/quote",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        cache:"no-store",
        body:JSON.stringify(data)
      });
      const result=await response.json().catch(()=>({}));
      if(sequence!==quoteSequence) return false;
      if(!response.ok||!result.ok||!result.available){
        hidePayPal(result.message||"Dieser Termin ist aktuell nicht für eine Sofortbuchung verfügbar.");
        return false;
      }
      showAvailable(data,result);
      return true;
    }catch(error){
      if(sequence!==quoteSequence) return false;
      hidePayPal("Live-Verfügbarkeitsprüfung derzeit nicht erreichbar. Bitte Buchungsanfrage senden oder später erneut versuchen.");
      return false;
    }
  }

  function scheduleVerification(){
    clearTimeout(quoteTimer);
    verifiedSignature="";
    quoteTimer=setTimeout(()=>verifyAvailability(payload()),350);
  }

  async function startCheckout(event){
    event.preventDefault();
    event.stopImmediatePropagation();

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

    const isStillFree=await verifyAvailability(data,{force:true});
    if(!isStillFree) return;

    const oldText=paypalLink.textContent;
    paypalLink.setAttribute("aria-busy","true");
    paypalLink.textContent="Termin wird reserviert und PayPal vorbereitet …";
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
    hidePayPal("Sofortzahlung wird nach Einrichtung des sicheren PayPal-Checkouts aktiviert. Bis dahin bitte Buchungsanfrage senden.");
    return;
  }

  form.addEventListener("change",scheduleVerification);
  form.addEventListener("input",function(event){
    const id=event.target?.id||"";
    const name=event.target?.name||"";
    if(["arrival","departure","adults","luggageTransport"].includes(id)||["room","extra"].includes(name)){
      scheduleVerification();
    }
  });

  scheduleVerification();
});
})();

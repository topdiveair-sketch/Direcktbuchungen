(function(){
"use strict";

function ready(fn){
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn, {once:true});
  else fn();
}

ready(function(){
  setTimeout(function(){
    const apiBase=String(window.ZAB_DIRECT_BOOKING_API_URL||"").replace(/\/+$/,"");
    let paypalLink=document.getElementById("paypalLink");
    const paypalBox=document.getElementById("paypalBox");
    let paypalHint=document.getElementById("paypalHint");
    const form=document.getElementById("requestForm");
    const availability=document.getElementById("availabilityStatus");
    const submitRequest=document.getElementById("submitRequest");
    const totalField=document.getElementById("total");
    if(!paypalLink||!form) return;

    const style=document.createElement("style");
    style.textContent='.zab-paypal-primary #submitRequest,.zab-booking-blocked #submitRequest{display:none!important;}';
    document.head.appendChild(style);

    const contactNote=form.querySelector(".checkin-data-note");
    if(paypalBox&&contactNote&&contactNote.nextElementSibling!==paypalBox){
      contactNote.insertAdjacentElement("afterend",paypalBox);
    }

    const isolatedLink=paypalLink.cloneNode(true);
    isolatedLink.id="paypalLink";
    paypalLink.replaceWith(isolatedLink);
    paypalLink=isolatedLink;

    if(paypalHint){
      const isolatedHint=paypalHint.cloneNode(true);
      isolatedHint.id="paypalHint";
      paypalHint.replaceWith(isolatedHint);
      paypalHint=isolatedHint;
    }

    const oldHeading=paypalBox?.querySelector("strong");
    if(oldHeading){
      const isolatedHeading=oldHeading.cloneNode(true);
      oldHeading.replaceWith(isolatedHeading);
    }

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

    function etappenAdults(){
      return Math.max(1,Math.min(2,Number(value("adults")||2)));
    }

    function parseLocalDate(text){
      if(!/^\d{4}-\d{2}-\d{2}$/.test(text||"")) return null;
      const parts=text.split("-").map(Number);
      const d=new Date(parts[0],parts[1]-1,parts[2]);
      return Number.isNaN(d.getTime())?null:d;
    }

    function ymd(date){
      const y=date.getFullYear();
      const m=String(date.getMonth()+1).padStart(2,"0");
      const d=String(date.getDate()).padStart(2,"0");
      return `${y}-${m}-${d}`;
    }

    function enforceValidStay(){
      const arrival=document.getElementById("arrival");
      const departure=document.getElementById("departure");
      if(!arrival||!departure) return;
      const a=parseLocalDate(arrival.value);
      if(!a) return;
      const minDeparture=new Date(a.getTime());
      minDeparture.setDate(minDeparture.getDate()+1);
      const minValue=ymd(minDeparture);
      departure.min=minValue;
      const d=parseLocalDate(departure.value);
      if(!d||d<=a) departure.value=minValue;
    }

    function stayNights(){
      const a=parseLocalDate(value("arrival"));
      const d=parseLocalDate(value("departure"));
      if(!a||!d||d<=a) return 0;
      return Math.round((d-a)/86400000);
    }

    function updateEtappenjausePrice(){
      const input=document.getElementById("etappenjauseExtra");
      if(!input) return;
      const amount=12.9*etappenAdults();
      input.dataset.price=String(amount);
      input.dataset.unit="once";
      const price=input.closest(".choice")?.querySelector(".price");
      if(price) price.textContent=`+${amount.toFixed(2).replace(".",",")}`;
    }

    function recalculateVisibleTotal(){
      if(!totalField) return;
      const nights=stayNights();
      if(nights<=0){
        totalField.textContent="Termin wählen";
        return;
      }
      const adults=etappenAdults();
      const room=selectedRoom();
      let sum=Number(room?.dataset.price||0)*nights;
      for(const extra of form.querySelectorAll('input[name="extra"]:checked')){
        const price=Number(extra.dataset.price||0);
        const unit=extra.dataset.unit||"once";
        if(unit==="person_night") sum+=price*adults*nights;
        else if(unit==="night") sum+=price*nights;
        else sum+=price;
      }
      totalField.textContent=`${sum.toFixed(2).replace(".",",")} EUR`;
    }

    function refreshPricing(){
      enforceValidStay();
      updateEtappenjausePrice();
      setTimeout(recalculateVisibleTotal,0);
    }

    function installEtappenjause(){
      if(document.getElementById("etappenjauseExtra")) return;
      const extras=form.querySelector(".extras");
      if(!extras) return;
      const luggage=form.querySelector("#luggageTransport")?.closest(".choice");
      const label=document.createElement("label");
      label.className="choice";
      label.innerHTML='<input id="etappenjauseExtra" type="checkbox" name="extra" value="Etappenjause für unterwegs" data-price="25.8" data-unit="once"><span><strong>Etappenjause für unterwegs</strong><small>12,90 EUR pro Person · Weckerl, Obst, kleine Stärkung und Wasser · bitte bis Vorabend bestellen</small></span><b class="price">+25,80</b>';
      if(luggage) extras.insertBefore(label,luggage);
      else extras.appendChild(label);
      updateEtappenjausePrice();
    }

    function promoteDirectBookingSurface(){
      const heroEyebrow=document.querySelector(".hero-copy .eyebrow");
      if(heroEyebrow) heroEyebrow.textContent="Direkt buchen ohne Buchungsplattform";
      const bookingTitle=document.getElementById("booking-title");
      if(bookingTitle) bookingTitle.textContent="Wachau-Etappe direkt buchen";
      const bookingIntro=document.querySelector(".booking-intro");
      if(bookingIntro){
        bookingIntro.textContent="Reisedaten wählen, Live-Verfügbarkeit prüfen und einen freien Termin sicher mit PayPal direkt buchen. Falls Sofortbuchung nicht möglich ist, bleibt die persönliche Anfrage verfügbar.";
      }
      const trust=form.closest(".panel")?.querySelector(".direct-booking-trust");
      const trustStrong=trust?.querySelector("strong");
      const trustSpan=trust?.querySelector("span");
      const trustSmall=trust?.querySelector("small");
      if(trustStrong) trustStrong.textContent="Direkt buchen bei den Gastgebern";
      if(trustSpan) trustSpan.textContent="Live-Verfügbarkeit, transparenter Preis und sichere PayPal-Zahlung.";
      if(trustSmall) trustSmall.textContent="Ohne Provision oder Umweg über eine zusätzliche Buchungsplattform.";
      const bookingTile=document.querySelector(".quick-tile.book");
      const bookingTileTitle=bookingTile?.querySelector("span");
      const bookingTileSmall=bookingTile?.querySelector("small");
      if(bookingTileTitle) bookingTileTitle.textContent="Direkt buchen";
      if(bookingTileSmall) bookingTileSmall.textContent="Verfügbarkeit live prüfen";
      if(bookingTile) bookingTile.setAttribute("aria-label","Direkt buchen – Verfügbarkeit live prüfen");
      if(submitRequest) submitRequest.textContent="Buchungsanfrage senden";
    }

    function setRequestFallback(visible){
      form.classList.remove("zab-booking-blocked");
      form.classList.toggle("zab-paypal-primary",!visible);
      if(visible && submitRequest){
        submitRequest.classList.remove("hidden");
        submitRequest.style.removeProperty("display");
      }
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
          etappenjause:selectedExtraByValue("Etappenjause für unterwegs"),
          luggage:Boolean(luggage?.checked)
        }
      };
    }

    function quoteSignature(data){
      return JSON.stringify({room:data.room,arrival:data.arrival,departure:data.departure,adults:data.adults,extras:data.extras});
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

    function checkoutHeading(text){
      const heading=paypalBox?.querySelector("strong");
      if(heading) heading.textContent=text;
    }

    function localCalendarBlocked(){
      return Boolean(availability && availability.classList.contains("blocked"));
    }

    function hidePayPal(message=""){
      verifiedSignature="";
      form.classList.remove("zab-paypal-primary","zab-booking-blocked");
      paypalLink.classList.add("hidden");
      paypalBox?.classList.remove("zab-paypal-ready");
      if(message && paypalHint) paypalHint.textContent=message;
      setRequestFallback(Boolean(message));
    }

    function showBlocked(message){
      verifiedSignature="";
      form.classList.remove("zab-paypal-primary");
      form.classList.add("zab-booking-blocked");
      paypalBox?.classList.remove("hidden","zab-paypal-ready");
      paypalLink.classList.add("hidden");
      checkoutHeading("⛔ Belegt – bitte anderen Termin wählen");
      if(paypalHint) paypalHint.textContent=message||"Das Zimmer ist für diesen Zeitraum bereits belegt.";
      if(availability){
        availability.className="availability-status blocked";
        availability.textContent="⛔ Belegt – bitte einen anderen Termin wählen.";
      }
      if(submitRequest){
        submitRequest.classList.add("hidden");
        submitRequest.style.setProperty("display","none","important");
      }
    }

    function showChecking(){
      form.classList.remove("zab-booking-blocked");
      setRequestFallback(false);
      paypalBox?.classList.remove("hidden");
      paypalBox?.classList.remove("zab-paypal-ready");
      paypalLink.classList.add("hidden");
      checkoutHeading("Verfügbarkeit wird geprüft");
      if(paypalHint) paypalHint.textContent="Verfügbarkeit wird direkt mit dem aktuellen Booking-Kalender geprüft …";
    }

    function showAvailable(data,result){
      if(localCalendarBlocked()){
        showBlocked("Der Booking-Kalender sperrt diesen Zeitraum. Eine Backend-Frei-Meldung darf diese Sperre nicht überschreiben.");
        return false;
      }
      form.classList.remove("zab-booking-blocked");
      setRequestFallback(false);
      verifiedSignature=quoteSignature(data);
      const total=Number(result.total||0);
      paypalBox?.classList.remove("hidden");
      paypalBox?.classList.add("zab-paypal-ready");
      paypalLink.classList.remove("hidden");
      paypalLink.href="#";
      paypalLink.removeAttribute("target");
      paypalLink.removeAttribute("rel");
      paypalLink.dataset.secureCheckout="1";
      paypalLink.textContent=total>0
        ? `Jetzt ${total.toFixed(2).replace(".",",")} EUR sicher mit PayPal buchen`
        : "Jetzt sicher mit PayPal buchen";
      checkoutHeading("✅ Termin frei – sichere Direktzahlung");
      if(paypalHint) paypalHint.textContent="Termin ist laut aktuellem Booking-Kalender frei. Beim Klick wird der Termin serverseitig reserviert und vor PayPal nochmals sicher geprüft.";
      if(availability){
        availability.className="availability-status ok zab-backend-ok";
        availability.textContent="✅ Frei – live über den aktuellen Booking-Kalender geprüft.";
      }
    }

    function isClearlyBlocked(result){
      const message=String(result?.message||"").toLowerCase();
      return result?.available===false && /(belegt|direktbuchung|already booked|occupied|not available)/i.test(message);
    }

    async function verifyAvailability(data){
      if(!configured()){
        hidePayPal("Sofortzahlung ist noch nicht vollständig eingerichtet. Bitte senden Sie stattdessen die Buchungsanfrage.");
        return false;
      }
      if(!validDates(data)){
        hidePayPal();
        return false;
      }
      if(localCalendarBlocked()){
        showBlocked("Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.");
        return false;
      }
      if(data.extras.etappenjause){
        hidePayPal("Etappenjause ist ausgewählt. Bitte die Buchungsanfrage senden; die Jause wird für die nächste Etappe vorbereitet und separat bestätigt.");
        return false;
      }
      if(data.extras.luggage){
        hidePayPal("Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.");
        return false;
      }
      const signature=quoteSignature(data);
      if(verifiedSignature===signature && !paypalLink.classList.contains("hidden")){
        setRequestFallback(false);
        return true;
      }
      const sequence=++quoteSequence;
      showChecking();
      try{
        const response=await fetch(apiBase+"/api/paypal/quote",{
          method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)
        });
        const result=await response.json().catch(()=>({}));
        if(sequence!==quoteSequence) return false;
        if(isClearlyBlocked(result)){
          showBlocked(result.message);
          return false;
        }
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
      if(localCalendarBlocked()){
        showBlocked("Der Booking-Kalender sperrt diesen Zeitraum. Bitte einen anderen Termin wählen.");
        return;
      }
      const missing=missingCustomer(data);
      if(missing){
        missing.focus();
        missing.scrollIntoView({behavior:"smooth",block:"center"});
        checkoutHeading("Kontaktdaten vervollständigen");
        if(paypalHint) paypalHint.textContent="Für die Sofortbuchung bitte zuerst Name, E-Mail und Telefonnummer vollständig eintragen.";
        return;
      }
      if(data.extras.etappenjause){
        if(paypalHint) paypalHint.textContent="Die Etappenjause wird über die persönliche Buchungsanfrage bestätigt. Bitte dafür die Buchungsanfrage senden.";
        document.getElementById("etappenjauseExtra")?.focus();
        setRequestFallback(true);
        return;
      }
      if(data.extras.luggage){
        if(paypalHint) paypalHint.textContent="Gepäcktransport hat einen streckenabhängigen Preis. Bitte Gepäcktransport abwählen und die Übernachtung bezahlen oder zuerst eine Anfrage senden.";
        document.getElementById("luggageTransport")?.focus();
        return;
      }
      const oldText=paypalLink.textContent;
      paypalLink.setAttribute("aria-busy","true");
      paypalLink.textContent="Termin wird reserviert und PayPal vorbereitet …";
      paypalLink.style.pointerEvents="none";
      checkoutHeading("PayPal wird vorbereitet …");
      if(paypalHint) paypalHint.textContent="Verfügbarkeit und Preis werden jetzt serverseitig final geprüft.";
      try{
        const response=await fetch(apiBase+"/api/paypal/create-order",{
          method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)
        });
        const result=await response.json().catch(()=>({}));
        if(!response.ok||!result.ok||!result.approval_url) throw new Error(result.message||"PayPal-Checkout konnte nicht gestartet werden.");
        window.zabTrack?.("direct_paypal_checkout_started",{booking_id:result.booking_id,order_id:result.order_id,total:result.total});
        window.location.assign(result.approval_url);
      }catch(error){
        paypalLink.textContent=oldText;
        paypalLink.style.pointerEvents="";
        paypalLink.removeAttribute("aria-busy");
        paypalLink.href="#";
        paypalLink.removeAttribute("target");
        paypalLink.classList.remove("hidden");
        paypalBox?.classList.add("zab-paypal-ready");
        setRequestFallback(true);
        checkoutHeading("⚠️ PayPal konnte nicht gestartet werden");
        if(paypalHint){
          paypalHint.textContent="Sofortbuchung nicht gestartet: "+(error.message||error)+" Bitte nicht mehrfach klicken; bei Bedarf die Buchungsanfrage senden.";
          paypalHint.style.fontWeight="800";
          paypalHint.style.color="#8b2f1f";
        }
      }
    }

    installEtappenjause();
    promoteDirectBookingSurface();
    refreshPricing();

    form.addEventListener("change",function(event){
      if(event.target?.id==="arrival") enforceValidStay();
      refreshPricing();
      scheduleVerification();
    },true);

    form.addEventListener("input",function(event){
      const id=event.target?.id||"";
      const name=event.target?.name||"";
      if(["arrival","departure","adults","luggageTransport","etappenjauseExtra"].includes(id)||["room","extra"].includes(name)){
        refreshPricing();
        scheduleVerification();
      }
    },true);

    paypalLink.removeAttribute("target");
    paypalLink.removeAttribute("rel");
    paypalLink.href="#";
    paypalLink.addEventListener("click",startCheckout,true);

    if(!configured()){
      hidePayPal("Sofortzahlung wird nach Einrichtung des sicheren PayPal-Checkouts aktiviert. Bis dahin bitte Buchungsanfrage senden.");
      return;
    }

    scheduleVerification();
  },0);
});
})();
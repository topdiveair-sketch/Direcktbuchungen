(function(){
"use strict";

const COPY={
  de:{button:"Verfügbarkeit prüfen & mit PayPal bezahlen",checking:"Verfügbarkeit und Preis werden geprüft …",redirect:"Termin wird reserviert · PayPal wird geöffnet …",missing:"Bitte füllen Sie Name, E-Mail und Telefonnummer vollständig aus.",unavailable:"Dieser Termin ist nicht für die Sofortbuchung verfügbar.",extra:"Für Gepäcktransport oder Etappenjause bitte zuerst eine persönliche Anfrage senden.",error:"PayPal konnte nicht gestartet werden. Bitte versuchen Sie es erneut."},
  en:{button:"Check availability & pay with PayPal",checking:"Checking availability and price …",redirect:"Holding your stay · opening PayPal …",missing:"Please complete your name, email and phone number.",unavailable:"These dates are not available for instant booking.",extra:"For luggage transfer or the stage snack, please send a personal request first.",error:"PayPal could not be started. Please try again."},
  cs:{button:"Ověřit dostupnost & zaplatit přes PayPal",checking:"Ověřujeme dostupnost a cenu …",redirect:"Rezervujeme termín · otevíráme PayPal …",missing:"Doplňte prosím jméno, e-mail a telefon.",unavailable:"Tento termín není dostupný pro okamžitou rezervaci.",extra:"Pro přepravu zavazadel nebo etapu s občerstvením nejprve odešlete osobní poptávku.",error:"PayPal se nepodařilo spustit. Zkuste to prosím znovu."},
  sk:{button:"Overiť dostupnosť & zaplatiť cez PayPal",checking:"Overujeme dostupnosť a cenu …",redirect:"Rezervujeme termín · otvárame PayPal …",missing:"Doplňte prosím meno, e-mail a telefón.",unavailable:"Tento termín nie je dostupný na okamžitú rezerváciu.",extra:"Pre prepravu batožiny alebo etapu s občerstvením najprv odošlite osobnú požiadavku.",error:"PayPal sa nepodarilo spustiť. Skúste to prosím znova."},
  hu:{button:"Elérhetőség ellenőrzése & fizetés PayPallal",checking:"Elérhetőség és ár ellenőrzése …",redirect:"Időpont lefoglalása · PayPal megnyitása …",missing:"Kérjük, töltse ki a nevet, e-mail-címet és telefonszámot.",unavailable:"Ez az időpont nem foglalható azonnal.",extra:"Csomagszállítás vagy úti csomag esetén előbb küldjön személyes érdeklődést.",error:"A PayPal nem indítható. Kérjük, próbálja újra."},
  pl:{button:"Sprawdź dostępność & zapłać przez PayPal",checking:"Sprawdzamy dostępność i cenę …",redirect:"Rezerwujemy termin · otwieramy PayPal …",missing:"Uzupełnij imię, e-mail i numer telefonu.",unavailable:"Ten termin nie jest dostępny do natychmiastowej rezerwacji.",extra:"W przypadku transportu bagażu lub prowiantu etapowego najpierw wyślij zapytanie.",error:"Nie udało się uruchomić PayPal. Spróbuj ponownie."},
  nl:{button:"Beschikbaarheid controleren & betalen met PayPal",checking:"Beschikbaarheid en prijs worden gecontroleerd …",redirect:"Verblijf wordt vastgehouden · PayPal wordt geopend …",missing:"Vul naam, e-mail en telefoonnummer volledig in.",unavailable:"Deze data zijn niet beschikbaar voor directe boeking.",extra:"Stuur voor bagagevervoer of etappepakket eerst een persoonlijke aanvraag.",error:"PayPal kon niet worden gestart. Probeer het opnieuw."}
};

function boot(){
  const form=document.getElementById("requestForm");
  const button=document.getElementById("submitRequest");
  if(!form||!button) return;

  const langRaw=(new URLSearchParams(location.search).get("lang")||document.documentElement.lang||"de").slice(0,2).toLowerCase();
  const lang=COPY[langRaw]?langRaw:"de";
  const t=COPY[lang];
  const apiBase=String(window.ZAB_DIRECT_BOOKING_API_URL||"").replace(/\/+$/,"");
  const status=document.getElementById("availabilityStatus");
  const paypalBox=document.getElementById("paypalBox");
  const paypalHint=document.getElementById("paypalHint");

  function setButton(text,busy){
    if(button.textContent!==text) button.textContent=text;
    button.disabled=Boolean(busy);
    button.setAttribute("aria-busy",busy?"true":"false");
  }
  function keepPrimary(){
    if(!button.disabled && button.textContent!==t.button) button.textContent=t.button;
  }
  setButton(t.button,false);
  const observer=new MutationObserver(()=>setTimeout(keepPrimary,0));
  observer.observe(button,{childList:true,subtree:true,characterData:true});

  function val(id){return (document.getElementById(id)?.value||"").trim();}
  function extraSelected(value){return Array.from(form.querySelectorAll('input[name="extra"]:checked')).some(x=>x.value===value);}
  function payload(){
    return {
      room:form.querySelector('input[name="room"]:checked')?.value||"",
      arrival:val("arrival"),departure:val("departure"),adults:Number(val("adults")||2),
      first_name:val("firstName"),last_name:val("lastName"),email:val("email"),phone:val("phone"),message:val("message"),
      extras:{
        breakfast:extraSelected("Frühstück"),
        jause:extraSelected("Wachauer Jause"),
        etappenjause:extraSelected("Etappenjause für unterwegs"),
        luggage:Boolean(document.getElementById("luggageTransport")?.checked)
      }
    };
  }
  function message(text,ok){
    if(paypalBox) paypalBox.classList.remove("hidden");
    if(paypalHint) paypalHint.textContent=text;
    if(status){status.textContent=text;status.className="availability-status "+(ok?"ok":"blocked");}
  }

  async function directCheckout(event){
    if(event.target!==form) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const data=payload();
    if(!apiBase.startsWith("https://")){message(t.error,false);return;}
    if(!data.first_name||!data.last_name||!data.email||!data.phone){message(t.missing,false);setButton(t.button,false);return;}
    if(data.extras.luggage||data.extras.etappenjause){message(t.extra,false);setButton(t.button,false);return;}

    try{
      setButton(t.checking,true);message(t.checking,true);
      const q=await fetch(apiBase+"/api/paypal/quote",{method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)});
      const qr=await q.json().catch(()=>({}));
      if(!q.ok||!qr.ok||!qr.available) throw new Error(qr.message||t.unavailable);

      setButton(t.redirect,true);message(t.redirect,true);
      const r=await fetch(apiBase+"/api/paypal/create-order",{method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(data)});
      const result=await r.json().catch(()=>({}));
      if(!r.ok||!result.ok||!result.approval_url) throw new Error(result.message||t.error);
      window.zabTrack?.("direct_paypal_checkout_started",{booking_id:result.booking_id,order_id:result.order_id,total:result.total});
      location.assign(result.approval_url);
    }catch(err){
      message(String(err?.message||t.error),false);
      setButton(t.button,false);
    }
  }

  window.addEventListener("submit",directCheckout,true);
  form.addEventListener("input",()=>setTimeout(keepPrimary,0),true);
  form.addEventListener("change",()=>setTimeout(keepPrimary,0),true);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",boot,{once:true});
else boot();
})();

(function () {
  "use strict";

  const FALLBACK_CONFIG = {
    home: { label:"Zuhause am Bach", lat:48.2945, lon:15.4068 },
    vehicle: { consumption_l_per_100km:6.5, wear_eur_per_km:0.18 },
    business: {
      labor_eur_per_hour:22,
      organization_fee_eur:5,
      profit_fixed_eur:12,
      profit_percent:10,
      minimum_price_eur:29,
      round_to_eur:1,
      calculate_return_to_home:true
    },
    fuel: {
      type:"DIE",
      fallback_diesel_eur_per_l:2.10,
      min_reasonable_price_eur_per_l:0.80,
      max_reasonable_price_eur_per_l:4.00
    }
  };

  let cfg = FALLBACK_CONFIG;
  const $ = id => document.getElementById(id);
  const money = n => Number(n||0).toLocaleString("de-AT",{style:"currency",currency:"EUR",maximumFractionDigits:0});

  async function loadConfig(){
    try{
      const r = await fetch("zab-live-calculator-config.json",{cache:"no-store"});
      if(r.ok) cfg = await r.json();
    }catch(e){}
  }

  async function searchPlaces(query){
    const q = String(query||"").trim();
    if(q.length < 3) return [];
    const url = "https://nominatim.openstreetmap.org/search?format=json&limit=5&countrycodes=at,de,cz,sk,hu&addressdetails=1&q=" + encodeURIComponent(q);
    const r = await fetch(url,{headers:{"Accept":"application/json"}});
    if(!r.ok) throw new Error("Ortssuche derzeit nicht erreichbar.");
    return await r.json();
  }

  async function geocode(query){
    if(/^zuhause am bach$/i.test(String(query||"").trim())) return cfg.home;
    const rows = await searchPlaces(query);
    if(!rows.length) throw new Error("Ort oder Unterkunft nicht gefunden.");
    const x = rows[0];
    return {lat:Number(x.lat),lon:Number(x.lon),label:x.display_name};
  }

  async function route(a,b){
    const url = `https://router.project-osrm.org/route/v1/driving/${a.lon},${a.lat};${b.lon},${b.lat}?overview=false`;
    const r = await fetch(url);
    if(!r.ok) throw new Error("Route konnte nicht berechnet werden.");
    const d = await r.json();
    if(!d.routes?.length) throw new Error("Keine Fahrroute gefunden.");
    return {distance_m:Number(d.routes[0].distance),duration_s:Number(d.routes[0].duration)};
  }

  function fuelValid(x){
    x=Number(x);
    return Number.isFinite(x) && x>=cfg.fuel.min_reasonable_price_eur_per_l && x<=cfg.fuel.max_reasonable_price_eur_per_l;
  }

  async function liveDiesel(){
    const {lat,lon}=cfg.home;
    const url=`https://api.e-control.at/sprit/1.0/search/gas-stations/by-address?latitude=${lat}&longitude=${lon}&fuelType=${encodeURIComponent(cfg.fuel.type)}&includeClosed=false`;
    try{
      const r=await fetch(url,{headers:{"Accept":"application/json"},cache:"no-store"});
      if(!r.ok) throw new Error("fuel");
      const data=await r.json();
      const arr=[];
      for(const s of Array.isArray(data)?data:[]){
        for(const p of (s.prices||[])){
          if(p.fuelType===cfg.fuel.type && fuelValid(p.amount)){
            arr.push({amount:Number(p.amount),station:s.name||"Tankstelle"});
          }
        }
      }
      if(!arr.length) throw new Error("fuel");
      arr.sort((a,b)=>a.amount-b.amount);
      const best=arr[0];
      localStorage.setItem("zab_last_diesel",JSON.stringify({...best,ts:Date.now()}));
      return {...best,source:"live"};
    }catch(e){
      try{
        const last=JSON.parse(localStorage.getItem("zab_last_diesel")||"null");
        if(last && fuelValid(last.amount)) return {...last,source:"last"};
      }catch(e2){}
      return {amount:Number(cfg.fuel.fallback_diesel_eur_per_l),station:"Sicherheitswert",source:"fallback"};
    }
  }

  function roundUp(n){
    const step=Math.max(.01,Number(cfg.business.round_to_eur||1));
    return Math.ceil(n/step)*step;
  }

  function renderSuggestions(rows){
    const box=$("zabGuestSuggestions");
    box.innerHTML="";
    if(!rows.length){box.hidden=true;return;}
    rows.forEach((r)=>{
      const b=document.createElement("button");
      b.type="button";
      b.className="zab-suggestion";
      b.textContent=r.display_name;
      b.addEventListener("click",()=>{
        $("zabGuestDestination").value=r.display_name;
        $("zabGuestDestination").dataset.lat=r.lat;
        $("zabGuestDestination").dataset.lon=r.lon;
        box.hidden=true;
      });
      box.appendChild(b);
    });
    box.hidden=false;
  }

  let searchTimer=null;
  async function autocomplete(){
    clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{
      try{
        const rows=await searchPlaces($("zabGuestDestination").value);
        renderSuggestions(rows);
      }catch(e){
        renderSuggestions([]);
      }
    },350);
  }

  async function destinationPoint(){
    const el=$("zabGuestDestination");
    if(el.dataset.lat && el.dataset.lon){
      return {lat:Number(el.dataset.lat),lon:Number(el.dataset.lon),label:el.value};
    }
    return geocode(el.value);
  }

  async function calculate(){
    const btn=$("zabGuestCalc");
    const status=$("zabGuestStatus");
    btn.disabled=true;
    status.textContent="Preis wird aktuell berechnet …";
    $("zabGuestResult").hidden=true;
    try{
      const mode=$("zabGuestMode").value;
      const dest=await destinationPoint();
      const home=cfg.home;

      let totalDistance=0,totalDuration=0;
      if(mode==="to"){
        const a=await route(home,dest);
        totalDistance+=a.distance_m; totalDuration+=a.duration_s;
        if(cfg.business.calculate_return_to_home){
          const b=await route(dest,home);
          totalDistance+=b.distance_m; totalDuration+=b.duration_s;
        }
      }else{
        const a=await route(dest,home);
        totalDistance+=a.distance_m; totalDuration+=a.duration_s;
        if(cfg.business.calculate_return_to_home){
          const b=await route(home,dest);
          totalDistance+=b.distance_m; totalDuration+=b.duration_s;
        }
      }

      const diesel=await liveDiesel();
      const km=totalDistance/1000;
      const hrs=totalDuration/3600;
      const liters=km*Number(cfg.vehicle.consumption_l_per_100km)/100;
      const fuel=liters*diesel.amount;
      const wear=km*Number(cfg.vehicle.wear_eur_per_km);
      const labor=hrs*Number(cfg.business.labor_eur_per_hour);
      const org=Number(cfg.business.organization_fee_eur);
      const base=fuel+wear+labor+org;
      const profit=Number(cfg.business.profit_fixed_eur)+base*Number(cfg.business.profit_percent)/100;
      const sale=Math.max(Number(cfg.business.minimum_price_eur),roundUp(base+profit));

      const routeLabel=mode==="to" ? "Zuhause am Bach → "+dest.label : dest.label+" → Zuhause am Bach";
      $("zabGuestPrice").textContent=money(sale);
      $("zabGuestRoute").textContent=routeLabel;
      $("zabGuestMeta").textContent=`ca. ${km.toFixed(1)} km Fahrzeugstrecke · ${Math.round(totalDuration/60)} Min. Fahrzeit`;
      $("zabGuestResult").hidden=false;
      status.textContent=diesel.source==="live" ? "Aktuell berechnet." : "Preis berechnet; Dieselwert mit Sicherheits-Fallback.";

      window.zabGuestPriceData={
        mode,destination:dest.label,total_km:km,duration_min:Math.round(totalDuration/60),
        sale_price:sale,calculated_at:new Date().toISOString()
      };
      try{sessionStorage.setItem("zab_guest_price",JSON.stringify(window.zabGuestPriceData));}catch(e){}
    }catch(e){
      status.textContent="Preis konnte nicht berechnet werden: "+(e.message||e);
    }finally{
      btn.disabled=false;
    }
  }

  function usePrice(){
    const d=window.zabGuestPriceData;
    if(!d) return;
    const luggage=$("luggageTransport");
    if(luggage && !luggage.checked){
      luggage.checked=true;
      luggage.dispatchEvent(new Event("change",{bubbles:true}));
    }
    const dir=$("luggageDirection");
    if(dir){
      dir.value=d.mode==="to"?"outbound":"inbound";
      dir.dispatchEvent(new Event("change",{bubbles:true}));
    }
    if(d.mode==="to"){
      const n=$("nextAccommodation"); if(n) n.value=d.destination;
    }else{
      const p=$("previousAccommodation"); if(p) p.value=d.destination;
    }
    const msg=$("message");
    if(msg){
      const line=`ZAB GepäckFrei Livepreis: ${d.destination} · ${money(d.sale_price)} · berechnet am ${new Date(d.calculated_at).toLocaleString("de-AT")}`;
      msg.value=(msg.value?msg.value+"\n":"")+line;
    }
    document.getElementById("booking-title")?.scrollIntoView({behavior:"smooth"});
  }

  async function init(){
    await loadConfig();
    const q=$("zabGuestDestination");
    if(!q) return;
    q.addEventListener("input",()=>{
      delete q.dataset.lat; delete q.dataset.lon;
      autocomplete();
    });
    q.addEventListener("focus",autocomplete);
    $("zabGuestCalc")?.addEventListener("click",calculate);
    $("zabGuestUsePrice")?.addEventListener("click",usePrice);
    document.addEventListener("click",e=>{
      if(!e.target.closest("#zabGuestDestination")&&!e.target.closest("#zabGuestSuggestions")) $("zabGuestSuggestions").hidden=true;
    });
  }
  document.addEventListener("DOMContentLoaded",init);
})();

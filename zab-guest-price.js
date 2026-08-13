(function(){
"use strict";
const $=id=>document.getElementById(id);
const money=n=>Number(n||0).toLocaleString("de-AT",{style:"currency",currency:"EUR",maximumFractionDigits:0});
let cfg;
async function getJson(u,o){const r=await fetch(u,o);if(!r.ok)throw Error("Dienst nicht erreichbar");return r.json();}
const geoCache=new Map();
function distanceKm(a,b){
 const rad=x=>x*Math.PI/180,dLat=rad(b.lat-a.lat),dLon=rad(b.lon-a.lon);
 const h=Math.sin(dLat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dLon/2)**2;
 return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
}
async function searchGeo(q){
 q=String(q||"").trim();
 if(q.length<2)return [];
 const key=q.toLocaleLowerCase("de-AT");
 if(geoCache.has(key))return geoCache.get(key);
 const queries=[q,`${q}, Wachau, Österreich`,`${q}, Niederösterreich, Österreich`];
 const found=[];
 for(const query of queries){
  const url="https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&namedetails=1&limit=8&countrycodes=at,de,cz,sk,hu&q="+encodeURIComponent(query);
  const rows=await getJson(url,{headers:{Accept:"application/json"}});
  for(const row of rows){
   const item={lat:+row.lat,lon:+row.lon,label:row.display_name,type:row.type||"",category:row.category||row.class||""};
   if(!Number.isFinite(item.lat)||!Number.isFinite(item.lon))continue;
   const id=`${item.lat.toFixed(5)},${item.lon.toFixed(5)}`;
   if(!found.some(x=>x.id===id))found.push({...item,id});
  }
  if(found.length)break;
 }
 found.sort((a,b)=>{
  const accommodation=x=>/(hotel|guest_house|hostel|motel|chalet|apartment|restaurant)/i.test(`${x.type} ${x.category}`)?0:1;
  return accommodation(a)-accommodation(b)||distanceKm(cfg.home,a)-distanceKm(cfg.home,b);
 });
 const result=found.slice(0,6);
 geoCache.set(key,result);
 return result;
}
async function geo(q){
 q=String(q||"").trim();
 if(!q) throw Error("Bitte Unterkunft, Ort oder Adresse eingeben.");
 if(/^zuhause am bach$/i.test(q)) return cfg.home;
 const results=await searchGeo(q);
 if(!results.length) throw Error("Unterkunft nicht gefunden. Bitte Hotelname mit Ort oder die genaue Adresse eingeben.");
 return results[0];
}
async function route(a,b){
 const d=await getJson(`https://router.project-osrm.org/route/v1/driving/${a.lon},${a.lat};${b.lon},${b.lat}?overview=false`);
 if(!d.routes?.length) throw Error("Keine Fahrroute gefunden.");
 return {m:+d.routes[0].distance,s:+d.routes[0].duration};
}
function fuelOk(x){
 x=+x;
 return Number.isFinite(x)&&x>=cfg.fuel.min_reasonable_price_eur_per_l&&x<=cfg.fuel.max_reasonable_price_eur_per_l;
}
async function diesel(){
 try{
  const d=await getJson(`https://api.e-control.at/sprit/1.0/search/gas-stations/by-address?latitude=${cfg.home.lat}&longitude=${cfg.home.lon}&fuelType=DIE&includeClosed=false`,{cache:"no-store"});
  const p=[];
  for(const s of Array.isArray(d)?d:[]) for(const x of (s.prices||[])) if(x.fuelType==="DIE"&&fuelOk(x.amount)) p.push(+x.amount);
  if(!p.length) throw 0;
  p.sort((a,b)=>a-b);
  localStorage.setItem("zabDiesel",String(p[0]));
  return p[0];
 }catch(e){
  const x=+localStorage.getItem("zabDiesel");
  return fuelOk(x)?x:+cfg.fuel.fallback_diesel_eur_per_l;
 }
}
function roundUp(n){const s=Math.max(.01,+cfg.business.round_to_eur||1);return Math.ceil(n/s)*s;}
async function calc(){
 const b=$("zabGuestCalc"),st=$("zabGuestStatus");
 b.disabled=true; st.textContent="Route, Fahrzeit und Dieselpreis werden berechnet …"; $("zabGuestResult").hidden=true;
 try{
  const mode=$("zabGuestMode").value,dest=await geo($("zabGuestDestination").value);
  let r=mode==="to"?await route(cfg.home,dest):await route(dest,cfg.home),m=r.m,s=r.s;
  if(cfg.business.calculate_return_to_home){
   r=mode==="to"?await route(dest,cfg.home):await route(cfg.home,dest);m+=r.m;s+=r.s;
  }
  const km=m/1000,h=s/3600,dp=await diesel();
  const fuel=km*cfg.vehicle.consumption_l_per_100km/100*dp;
  const wear=km*cfg.vehicle.wear_eur_per_km;
  const labor=h*cfg.business.labor_eur_per_hour;
  const base=fuel+wear+labor+cfg.business.organization_fee_eur;
  const raw=base+cfg.business.profit_fixed_eur+base*cfg.business.profit_percent/100;
  const sale=Math.max(cfg.business.minimum_price_eur,roundUp(raw));
  $("zabGuestPrice").textContent=money(sale);
  $("zabGuestRoute").textContent=(mode==="to"?"Zuhause am Bach → ":"Abholung → Zuhause am Bach: ")+dest.label;
  $("zabGuestMeta").textContent=`${km.toFixed(1)} km Fahrzeugstrecke · ${Math.round(s/60)} Min.`;
  $("zabGuestResult").hidden=false; st.textContent="Preis aktuell berechnet.";
  window.zabGuestPriceData={destination:dest.label,sale_price:sale};
 }catch(e){st.textContent="Berechnung nicht möglich: "+(e.message||e);}
 finally{b.disabled=false;}
}
function usePrice(){
 const d=window.zabGuestPriceData;if(!d)return;
 const l=$("luggageTransport");if(l){l.checked=true;l.dispatchEvent(new Event("change",{bubbles:true}));}
 const m=$("message");if(m)m.value=(m.value?m.value+"\n":"")+`ZAB GepäckFrei: ${d.destination} – kalkulierter Preis ${money(d.sale_price)}`;
 $("requestForm")?.scrollIntoView({behavior:"smooth"});
}
function renderSuggestions(items){
 const box=$("zabGuestSuggestions");
 if(!box)return;
 box.replaceChildren();
 for(const item of items){
  const button=document.createElement("button");
  button.type="button";
  button.textContent=item.label;
  button.addEventListener("click",()=>{
   $("zabGuestDestination").value=item.label;
   geoCache.set(item.label.toLocaleLowerCase("de-AT"),[item]);
   box.hidden=true;
  });
  box.appendChild(button);
 }
 box.hidden=!items.length;
}
document.addEventListener("DOMContentLoaded",async()=>{
 try{cfg=await getJson("zab-live-calculator-config.json",{cache:"no-store"});}catch(e){return;}
 $("zabGuestCalc")?.addEventListener("click",calc);
 $("zabGuestUsePrice")?.addEventListener("click",usePrice);
 const input=$("zabGuestDestination");
 let timer;
 input?.addEventListener("input",()=>{
  clearTimeout(timer);
  const query=input.value.trim();
  if(query.length<3){renderSuggestions([]);return;}
  timer=setTimeout(async()=>{
   try{renderSuggestions(await searchGeo(query));}catch(e){renderSuggestions([]);}
  },350);
 });
 input?.addEventListener("keydown",event=>{
  if(event.key==="Escape")renderSuggestions([]);
 });
});
})();

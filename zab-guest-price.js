(function(){
"use strict";
const $=id=>document.getElementById(id);
const money=n=>Number(n||0).toLocaleString("de-AT",{style:"currency",currency:"EUR",maximumFractionDigits:0});
const TEXT={
 de:{required:"Bitte Unterkunft, Ort oder Adresse eingeben.",notFound:"Unterkunft nicht gefunden. Bitte Hotelname mit Ort oder die genaue Adresse eingeben.",loading:"Route, Fahrzeit und Dieselpreis werden berechnet …",done:"Preis aktuell berechnet.",failed:"Berechnung nicht möglich: ",accommodation:"Unterkunft",address:"Adresse",place:"Ort",to:"Zuhause am Bach → ",from:"Abholung → Zuhause am Bach: ",distance:"km Fahrzeugstrecke",minutes:"Min.",calculatedFor:"Berechnet für"},
 en:{required:"Please enter an accommodation, place or address.",notFound:"Accommodation not found. Please enter the hotel name with its town or the exact address.",loading:"Calculating route, driving time and diesel price …",done:"Price calculated with current data.",failed:"Calculation not possible: ",accommodation:"Accommodation",address:"Address",place:"Place",to:"Zuhause am Bach → ",from:"Pickup → Zuhause am Bach: ",distance:"km driving distance",minutes:"min.",calculatedFor:"Calculated for"},
 cs:{required:"Zadejte ubytování, místo nebo adresu.",notFound:"Ubytování nebylo nalezeno. Zadejte název hotelu s místem nebo přesnou adresu.",loading:"Počítáme trasu, dobu jízdy a cenu nafty …",done:"Cena byla aktuálně vypočtena.",failed:"Výpočet není možný: ",accommodation:"Ubytování",address:"Adresa",place:"Místo",to:"Zuhause am Bach → ",from:"Vyzvednutí → Zuhause am Bach: ",distance:"km jízdní trasy",minutes:"min.",calculatedFor:"Vypočteno pro"},
 hu:{required:"Adjon meg szállást, helyet vagy címet.",notFound:"A szállás nem található. Adja meg a hotel nevét a településsel vagy a pontos címet.",loading:"Útvonal, menetidő és dízelár számítása …",done:"Az ár aktuálisan kiszámítva.",failed:"A számítás nem lehetséges: ",accommodation:"Szállás",address:"Cím",place:"Hely",to:"Zuhause am Bach → ",from:"Felvétel → Zuhause am Bach: ",distance:"km járműút",minutes:"perc",calculatedFor:"Kiszámítva erre"},
 es:{required:"Introduzca un alojamiento, lugar o dirección.",notFound:"Alojamiento no encontrado. Introduzca el nombre del hotel con la localidad o la dirección exacta.",loading:"Calculando ruta, tiempo de viaje y precio del diésel …",done:"Precio calculado con datos actuales.",failed:"No se puede calcular: ",accommodation:"Alojamiento",address:"Dirección",place:"Lugar",to:"Zuhause am Bach → ",from:"Recogida → Zuhause am Bach: ",distance:"km de recorrido",minutes:"min.",calculatedFor:"Calculado para"},
 fr:{required:"Saisissez un hébergement, un lieu ou une adresse.",notFound:"Hébergement introuvable. Saisissez le nom de l’hôtel avec la localité ou l’adresse exacte.",loading:"Calcul de l’itinéraire, du temps de trajet et du prix du diesel …",done:"Prix calculé avec les données actuelles.",failed:"Calcul impossible : ",accommodation:"Hébergement",address:"Adresse",place:"Lieu",to:"Zuhause am Bach → ",from:"Ramassage → Zuhause am Bach : ",distance:"km de trajet",minutes:"min",calculatedFor:"Calculé pour"}
};
const t=key=>(TEXT[document.documentElement.lang]||TEXT.de)[key]||TEXT.de[key]||key;
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
 const found=[];
 const url="https://photon.komoot.io/api/?limit=10&lang=de&lat="+cfg.home.lat+"&lon="+cfg.home.lon+"&q="+encodeURIComponent(q);
 const payload=await getJson(url,{headers:{Accept:"application/json"}});
 for(const feature of payload.features||[]){
   const row=feature.properties||{},coordinates=feature.geometry?.coordinates||[];
   const address={road:row.street||"",house_number:row.housenumber||"",city:row.city||row.locality||row.district||""};
   const parts=[row.name,[row.street,row.housenumber].filter(Boolean).join(" "),row.postcode,row.city||row.locality,row.state,row.country].filter(Boolean);
   const item={lat:+coordinates[1],lon:+coordinates[0],label:[...new Set(parts)].join(", "),type:row.type||"",category:row.osm_value||"",address};
   if(!Number.isFinite(item.lat)||!Number.isFinite(item.lon))continue;
   const id=`${item.lat.toFixed(5)},${item.lon.toFixed(5)}`;
   if(!found.some(x=>x.id===id))found.push({...item,id});
 }
 found.sort((a,b)=>{
  const normalized=x=>x.toLocaleLowerCase("de-AT").normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  const query=normalized(q),tokens=query.split(/[^a-z0-9]+/).filter(x=>x.length>1);
  const accommodation=x=>/(hotel|pension|gasthof|guest_house|hostel|motel|chalet|apartment|tourism)/i.test(`${x.label} ${x.type} ${x.category}`);
  const locality=x=>/(city|town|village|locality|municipality)/i.test(`${x.type} ${x.category}`);
  const score=x=>{
   const label=normalized(x.label);
   let value=tokens.reduce((sum,token)=>sum+(label.includes(token)?3:0),0);
   if(label.includes(query))value+=12;
   if(/\d/.test(query)&&x.address?.house_number&&query.includes(normalized(x.address.house_number)))value+=8;
   if(/^(hotel|pension|gasthof|unterkunft)/i.test(q)&&accommodation(x))value+=10;
   if(!/\d/.test(q)&&tokens.length===1&&locality(x))value+=8;
   if(distanceKm(cfg.home,x)<80)value+=4;
   return value;
  };
  return score(b)-score(a)||distanceKm(cfg.home,a)-distanceKm(cfg.home,b);
 });
 const result=found.slice(0,6);
 geoCache.set(key,result);
 return result;
}
async function geo(q){
 q=String(q||"").trim();
 if(!q) throw Error(t("required"));
 if(/^zuhause am bach$/i.test(q)) return cfg.home;
 const results=await searchGeo(q);
 if(!results.length) throw Error(t("notFound"));
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
 b.disabled=true; st.textContent=t("loading"); $("zabGuestResult").hidden=true;
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
  $("zabGuestRoute").textContent=(mode==="to"?t("to"):t("from"))+dest.label;
  $("zabGuestMeta").textContent=`${km.toFixed(1)} ${t("distance")} · ${Math.round(s/60)} ${t("minutes")}`;
  $("zabGuestResult").hidden=false; st.textContent=t("done");
  window.zabGuestPriceData={destination:dest.label,sale_price:sale};
 }catch(e){st.textContent=t("failed")+(e.message||e);}
 finally{b.disabled=false;}
}
function usePrice(){
 const d=window.zabGuestPriceData;if(!d)return;
 const l=$("luggageTransport");
 if(l){
  l.dataset.price=String(d.sale_price);
  l.dataset.calculatedDestination=d.destination;
  l.checked=true;
  const priceLabel=l.closest(".choice")?.querySelector("b.price");
  if(priceLabel)priceLabel.textContent="+"+money(d.sale_price);
  const detailLabel=l.closest(".choice")?.querySelector("small");
  if(detailLabel)detailLabel.textContent=`${t("calculatedFor")} ${d.destination}`;
  l.dispatchEvent(new Event("change",{bubbles:true}));
 }
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
  const kind=document.createElement("strong");
  const description=document.createElement("span");
  kind.textContent=/(hotel|pension|gasthof|guest_house|hostel|motel|chalet|apartment|tourism)/i.test(`${item.label} ${item.type} ${item.category}`)
   ? t("accommodation")
   : (item.address?.road||item.address?.house_number ? t("address") : t("place"));
  description.textContent=item.label;
  button.append(kind,description);
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

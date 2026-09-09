const API_BASE = (window.WACHAUETAPPE_API_BASE || '').replace(/\/$/,'');
const ROUTE_URL = '../plattform/routes.json';
const HOSTS_URL = '../plattform/hosts.json';

const $ = (id) => document.getElementById(id);
let routeData = null;
let hosts = [];
let activeBooking = null;

function iso(d){return d.toISOString().slice(0,10)}
function addDays(s,n){const d=new Date(`${s}T12:00:00`);d.setDate(d.getDate()+n);return iso(d)}
function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function eq(a,b){return String(a||'').trim().toLowerCase()===String(b||'').trim().toLowerCase()}

async function loadData(){
  const [routeRes,hostRes]=await Promise.all([fetch(ROUTE_URL),fetch(HOSTS_URL)]);
  if(!routeRes.ok) throw new Error('Routendaten konnten nicht geladen werden.');
  routeData=await routeRes.json();
  if(hostRes.ok){const h=await hostRes.json();hosts=(h.hosts||[]).filter(x=>x.published&&x.status==='verified'&&x.accepting_bookings);}
  initPlaces();
}

function currentRoute(){return (routeData?.routes||[]).find(r=>r.id===$('route').value)||(routeData?.routes||[])[0]}
function routePlaces(route){const result=[];(route?.segments||[]).forEach(s=>{if(!result.some(x=>eq(x,s.from)))result.push(s.from);if(!result.some(x=>eq(x,s.to)))result.push(s.to)});return result}

function initPlaces(){
  const route=currentRoute();
  const places=routePlaces(route);
  $('startPlace').innerHTML=places.map(p=>`<option>${esc(p)}</option>`).join('');
  $('endPlace').innerHTML=places.map(p=>`<option>${esc(p)}</option>`).join('');
  $('startPlace').value='Krems'; $('endPlace').value='Krems';
  $('places').innerHTML=places.map(p=>`<option value="${esc(p)}"></option>`).join('');
}

function selectedSegments(route,start,end){
  const segs=route.segments||[];
  const startIndex=segs.findIndex(s=>eq(s.from,start));
  if(startIndex<0) throw new Error('Startort nicht in der Route gefunden.');
  if(eq(start,end)) return segs.slice(startIndex).concat(segs.slice(0,startIndex));
  for(let offset=0;offset<segs.length;offset++){
    const idx=(startIndex+offset)%segs.length;
    if(eq(segs[idx].to,end)) return Array.from({length:offset+1},(_,i)=>segs[(startIndex+i)%segs.length]);
  }
  throw new Error('Zielort nicht in der Route gefunden.');
}

function planDays(segments,target,tolerance=4){
  const days=[];let i=0;
  while(i<segments.length){
    let sum=0,best=i,bestDiff=Infinity;
    for(let j=i;j<segments.length;j++){
      sum+=Number(segments[j].km||0);const diff=Math.abs(sum-target);
      if(diff<bestDiff||diff<=tolerance){best=j;bestDiff=diff}
      if(sum>target+tolerance&&j>i)break;
    }
    const chosen=segments.slice(i,best+1);
    days.push({from:chosen[0].from,to:chosen[chosen.length-1].to,km:chosen.reduce((a,s)=>a+Number(s.km||0),0),officialStages:chosen.map(s=>s.stage)});
    i=best+1;
  }
  return days;
}

function renderTrip(days,startDate){
  const total=days.reduce((a,d)=>a+d.km,0);
  $('tripResult').hidden=false;
  $('tripResult').innerHTML=`<div class="trip-summary"><strong>${days.length} Reisetage</strong><span>${total.toFixed(1)} km gesamt</span><span>${esc(startDate)} bis ${esc(addDays(startDate,days.length-1))}</span></div><div class="trip-days">${days.map((d,i)=>`<article class="trip-day"><div class="day-number">${i+1}</div><div><h3>${esc(d.from)} → ${esc(d.to)}</h3><p>${esc(addDays(startDate,i))} · offizielle Etappe${d.officialStages.length>1?'n':''} ${d.officialStages.join(', ')}</p><div class="host-actions" style="margin-top:10px"><button class="btn secondary" type="button" data-find-host="${esc(d.to)}" data-date="${esc(addDays(startDate,i))}">Gastgeber in ${esc(d.to)} finden</button></div></div><div class="km">${d.km.toFixed(1)} km</div></article>`).join('')}</div>`;
  document.querySelectorAll('[data-find-host]').forEach(btn=>btn.addEventListener('click',()=>{$('stayPlace').value=btn.dataset.findHost;$('stayDate').value=btn.dataset.date;$('stayGuests').value=$('guests').value;$('stayLuggage').checked=$('luggage').checked;location.hash='unterkunft';searchHosts();}));
}

async function searchHosts(){
  const place=$('stayPlace').value.trim();const date=$('stayDate').value;const guests=Math.max(1,Number($('stayGuests').value||1));const luggage=$('stayLuggage').checked;
  if(!place||!date)return;
  let results=[];
  if(API_BASE){
    try{const r=await fetch(`${API_BASE}/api/hosts/search?location=${encodeURIComponent(place)}&date=${encodeURIComponent(date)}&guests=${guests}&luggage=${luggage?'1':'0'}`);if(r.ok)results=await r.json();}
    catch(e){console.warn('API nicht erreichbar, statische Partnerdaten werden verwendet.',e)}
  }
  if(!results.length){results=hosts.filter(h=>h.location&&eq(h.location,place)&&(!luggage||(h.features||[]).some(f=>/gepäck/i.test(f)))).map(h=>({hostId:h.id,name:h.name,location:h.location,price:null,directUrl:h.direct_url,email:h.email,phone:h.phone,features:h.features||[]}));}
  renderHosts(results,date,guests);
}

function renderHosts(results,date,guests){
  const box=$('stayResult');
  if(!results.length){box.innerHTML='<div class="empty"><strong>Noch kein freigegebener Gastgeber verfügbar.</strong><br>Dieser Ort wird als Partnerlücke für WachauEtappe behandelt.</div>';return}
  box.innerHTML=results.map(h=>`<article class="host-card"><span class="eyebrow">GEPRÜFTER PARTNER</span><h3>${esc(h.name)}</h3><div class="location">${esc(h.location||'')}</div><div class="chips"><span class="chip">1 Nacht</span><span class="chip">Direktzahlung</span>${(h.features||[]).slice(0,3).map(f=>`<span class="chip">${esc(f)}</span>`).join('')}</div>${h.price!=null?`<p><strong>ab € ${Number(h.price).toFixed(2)}</strong></p>`:'<p>Preis wird vom Gastgeber bestätigt.</p>'}<div class="host-actions"><button class="btn primary" type="button" data-book='${encodeURIComponent(JSON.stringify({hostId:h.hostId||h.id,name:h.name,location:h.location,date,guests,price:h.price??null,email:h.email||'',phone:h.phone||''}))}'>Anfragen</button>${h.directUrl?`<a class="btn secondary" href="${esc(h.directUrl)}" target="_blank" rel="noopener">Direktseite</a>`:''}</div></article>`).join('');
  box.querySelectorAll('[data-book]').forEach(btn=>btn.addEventListener('click',()=>openBooking(JSON.parse(decodeURIComponent(btn.dataset.book)))));
}

function openBooking(data){activeBooking=data;$('bookingHostId').value=data.hostId;$('bookingDate').value=data.date;$('bookingGuests').value=data.guests;$('bookingSummary').textContent=`${data.name} · ${data.location} · ${data.date}`;$('bookingModal').hidden=false;document.body.style.overflow='hidden'}
function closeBooking(){$('bookingModal').hidden=true;document.body.style.overflow='';activeBooking=null}

async function submitBooking(e){
  e.preventDefault(); if(!activeBooking)return;
  const payload={hostId:activeBooking.hostId,stayDate:activeBooking.date,guests:Number($('bookingGuests').value||1),guestName:$('guestName').value.trim(),guestEmail:$('guestEmail').value.trim(),guestPhone:$('guestPhone').value.trim(),note:$('bookingNote').value.trim(),price:activeBooking.price??null,paymentMethod:'host'};
  if(!API_BASE){
    const draft={...payload,reference:`WEB-${Date.now()}`,status:'local-demo',createdAt:new Date().toISOString()};
    const arr=JSON.parse(localStorage.getItem('wachauetappe_guest_requests')||'[]');arr.push(draft);localStorage.setItem('wachauetappe_guest_requests',JSON.stringify(arr));
    alert('Die Gäste-Webseite ist fertig, aber die Online-API ist noch nicht verbunden. Diese Anfrage wurde nur lokal in diesem Browser gespeichert und noch nicht an WachauEtappe übertragen.');
    closeBooking();return;
  }
  try{
    const r=await fetch(`${API_BASE}/api/bookings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!r.ok)throw new Error(await r.text()||'Buchung konnte nicht gesendet werden.');
    const result=await r.json();alert(`Buchungsanfrage ${result.reference||''} wurde gesendet. Der Gastgeber bestätigt zuerst die Verfügbarkeit.`);$('bookingForm').reset();closeBooking();
  }catch(err){alert(`Buchungsanfrage konnte nicht gesendet werden: ${err.message}`)}
}

$('tripForm').addEventListener('submit',e=>{e.preventDefault();try{const route=currentRoute(),segments=selectedSegments(route,$('startPlace').value,$('endPlace').value),days=planDays(segments,Math.max(5,Number($('dailyKm').value||18)));renderTrip(days,$('startDate').value)}catch(err){alert(err.message)}});
$('stayForm').addEventListener('submit',e=>{e.preventDefault();searchHosts()});
$('bookingForm').addEventListener('submit',submitBooking);
$('closeModal').addEventListener('click',closeBooking);
$('bookingModal').addEventListener('click',e=>{if(e.target===$('bookingModal'))closeBooking()});
$('route').addEventListener('change',initPlaces);

const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);$('startDate').value=iso(tomorrow);$('stayDate').value=iso(tomorrow);
loadData().catch(err=>{console.error(err);alert('WachauEtappe konnte die Routendaten nicht laden.')});
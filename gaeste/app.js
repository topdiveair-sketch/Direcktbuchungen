const API_BASE=(window.WACHAUETAPPE_API_BASE||'https://web-production-907d68.up.railway.app').replace(/\/$/,'');
const ROUTE_URL='../plattform/routes.json';
const HOSTS_URL='../plattform/hosts.json';
const $=id=>document.getElementById(id);
let routeData=null,hosts=[],activeBooking=null,currentTrip=null;

function iso(d){return d.toISOString().slice(0,10)}
function addDays(s,n){const d=new Date(`${s}T12:00:00`);d.setDate(d.getDate()+n);return iso(d)}
function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function eq(a,b){return String(a||'').trim().toLowerCase()===String(b||'').trim().toLowerCase()}

async function loadData(){
  const [routeRes,hostRes]=await Promise.all([fetch(ROUTE_URL),fetch(HOSTS_URL)]);
  if(!routeRes.ok)throw new Error('Routendaten konnten nicht geladen werden.');
  routeData=await routeRes.json();
  if(hostRes.ok){const h=await hostRes.json();hosts=(h.hosts||[]).filter(x=>x.published&&x.status==='verified'&&x.accepting_bookings)}
  initPlaces();
}
function currentRoute(){return (routeData?.routes||[]).find(r=>r.id===$('route').value)||(routeData?.routes||[])[0]}
function routePlaces(route){const result=[];(route?.segments||[]).forEach(s=>{if(!result.some(x=>eq(x,s.from)))result.push(s.from);if(!result.some(x=>eq(x,s.to)))result.push(s.to)});return result}
function initPlaces(){const places=routePlaces(currentRoute());$('startPlace').innerHTML=places.map(p=>`<option>${esc(p)}</option>`).join('');$('endPlace').innerHTML=places.map(p=>`<option>${esc(p)}</option>`).join('');$('startPlace').value='Krems';$('endPlace').value='Krems';$('places').innerHTML=places.map(p=>`<option value="${esc(p)}"></option>`).join('')}

function selectedSegments(route,start,end){
  const segs=route.segments||[],startIndex=segs.findIndex(s=>eq(s.from,start));
  if(startIndex<0)throw new Error('Startort nicht in der Route gefunden.');
  if(eq(start,end))return segs.slice(startIndex).concat(segs.slice(0,startIndex));
  for(let offset=0;offset<segs.length;offset++){const idx=(startIndex+offset)%segs.length;if(eq(segs[idx].to,end))return Array.from({length:offset+1},(_,i)=>segs[(startIndex+i)%segs.length])}
  throw new Error('Zielort nicht in der Route gefunden.');
}
function planDays(segments,target,tolerance=4){
  const days=[];let i=0;
  while(i<segments.length){let sum=0,best=i,bestDiff=Infinity;for(let j=i;j<segments.length;j++){sum+=Number(segments[j].km||0);const diff=Math.abs(sum-target);if(diff<bestDiff||diff<=tolerance){best=j;bestDiff=diff}if(sum>target+tolerance&&j>i)break}const chosen=segments.slice(i,best+1);days.push({from:chosen[0].from,to:chosen[chosen.length-1].to,km:chosen.reduce((a,s)=>a+Number(s.km||0),0),officialStages:chosen.map(s=>s.stage)});i=best+1}
  return days;
}

async function getAvailableHosts(place,date,guests,luggage){
  try{
    const r=await fetch(`${API_BASE}/api/hosts/search?location=${encodeURIComponent(place)}&date=${encodeURIComponent(date)}&guests=${guests}&luggage=${luggage?'1':'0'}`);
    if(r.ok){const data=await r.json();return {online:true,items:Array.isArray(data)?data:[]}}
  }catch(e){console.warn('Online-Verfügbarkeit nicht erreichbar.',e)}
  return {online:false,items:hosts.filter(h=>h.location&&eq(h.location,place)&&(!luggage||(h.features||[]).some(f=>/gepäck/i.test(f)))).map(h=>({hostId:h.id,name:h.name,location:h.location,price:null,directUrl:h.direct_url,email:h.email,phone:h.phone,features:h.features||[]}))};
}

async function renderTrip(days,startDate){
  const total=days.reduce((a,d)=>a+d.km,0),guests=Math.max(1,Number($('guests').value||1)),luggage=$('luggage').checked;
  currentTrip={days:days.map((d,i)=>({...d,date:addDays(startDate,i),hosts:[],selected:null,online:false})),startDate,guests,luggage};
  $('tripResult').hidden=false;
  $('tripResult').innerHTML=`<div class="trip-summary"><strong>${days.length} Reisetage</strong><span>${total.toFixed(1)} km gesamt</span><span>${esc(startDate)} bis ${esc(addDays(startDate,days.length-1))}</span></div><div class="trip-days" id="tripDays"></div><div id="tripBookingAction" class="panel" style="margin-top:18px" hidden></div>`;
  const wrap=$('tripDays');
  for(let i=0;i<currentTrip.days.length;i++){
    const d=currentTrip.days[i],needsStay=i<currentTrip.days.length-1;
    wrap.insertAdjacentHTML('beforeend',`<article class="trip-day" style="display:block"><div style="display:grid;grid-template-columns:70px 1fr auto;gap:16px;align-items:center"><div class="day-number">${i+1}</div><div><h3>${esc(d.from)} → ${esc(d.to)}</h3><p>${esc(d.date)} · offizielle Etappe${d.officialStages.length>1?'n':''} ${d.officialStages.join(', ')}</p></div><div class="km">${d.km.toFixed(1)} km</div></div><div id="tripHost-${i}" style="margin-top:16px;margin-left:86px">${needsStay?'Verfügbare Gastgeber werden geprüft …':'<strong>Ziel erreicht.</strong> Für diesen Tag ist keine weitere Übernachtung erforderlich.'}</div></article>`);
    if(needsStay){const result=await getAvailableHosts(d.to,d.date,guests,luggage);d.hosts=result.items;d.online=result.online;renderTripHosts(i)}
  }
  updateTripAction();
}

function renderTripHosts(dayIndex){
  const d=currentTrip.days[dayIndex],box=$(`tripHost-${dayIndex}`);
  if(!d.hosts.length){box.innerHTML=d.online?'<div class="empty"><strong>Keine freie Partnerunterkunft gefunden.</strong><br>Für diese Nacht ist aktuell kein freies Kontingent gemeldet.</div>':'<div class="empty"><strong>Online-Verfügbarkeit derzeit nicht erreichbar.</strong><br>Es wird kein Betrieb als frei ausgegeben, solange die Live-Prüfung fehlt.</div>';return}
  const note=d.online?'<small style="display:block;margin-bottom:10px">Live verfügbare Gastgeber für diese Nacht</small>':'<small style="display:block;margin-bottom:10px">Partner vorhanden – Live-Verfügbarkeit muss noch bestätigt werden</small>';
  box.innerHTML=note+`<div class="host-grid" style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr));margin-top:0">${d.hosts.map((h,j)=>{const id=h.hostId||h.id,selected=d.selected&&String(d.selected.hostId)===String(id);return `<article class="host-card" style="outline:${selected?'3px solid #173D32':'none'}"><span class="eyebrow">${d.online?'FREI':'PARTNER'}</span><h3>${esc(h.name)}</h3><div class="location">${esc(h.location||d.to)}</div>${h.price!=null?`<p><strong>€ ${Number(h.price).toFixed(2)}</strong></p>`:'<p>Preis wird bestätigt.</p>'}<div class="chips"><span class="chip">1 Nacht</span><span class="chip">Direktzahlung</span></div><button class="btn ${selected?'secondary':'primary'}" type="button" data-select-trip-host="${dayIndex}:${j}">${selected?'Ausgewählt ✓':'Gastgeber auswählen'}</button></article>`}).join('')}</div>`;
  box.querySelectorAll('[data-select-trip-host]').forEach(btn=>btn.addEventListener('click',()=>{const [di,hi]=btn.dataset.selectTripHost.split(':').map(Number);const h=currentTrip.days[di].hosts[hi];currentTrip.days[di].selected={hostId:h.hostId||h.id,name:h.name,location:h.location||currentTrip.days[di].to,date:currentTrip.days[di].date,price:h.price??null};renderTripHosts(di);updateTripAction()}));
}

function updateTripAction(){
  const box=$('tripBookingAction');if(!box||!currentTrip)return;
  const nights=currentTrip.days.slice(0,-1),selected=nights.filter(d=>d.selected).length;
  box.hidden=false;
  if(selected<nights.length){box.innerHTML=`<strong>${selected} von ${nights.length} Übernachtungen ausgewählt.</strong><p style="margin-bottom:0">Wähle für jede Nacht einen Gastgeber. Erst danach kannst du die gesamte Reise anfragen.</p>`;return}
  box.innerHTML=`<strong>Alle ${nights.length} Übernachtungen ausgewählt.</strong><p>Jetzt sendest du eine gemeinsame Reiseanfrage. Die ausgewählten Gastgeber bestätigen anschließend ihre Verfügbarkeit.</p><button id="requestWholeTrip" class="btn primary" type="button">Gesamte Reise anfragen</button>`;
  $('requestWholeTrip').addEventListener('click',()=>openTripBooking());
}

async function searchHosts(){const place=$('stayPlace').value.trim(),date=$('stayDate').value,guests=Math.max(1,Number($('stayGuests').value||1)),luggage=$('stayLuggage').checked;if(!place||!date)return;const result=await getAvailableHosts(place,date,guests,luggage);renderHosts(result.items,date,guests,result.online)}
function renderHosts(results,date,guests,online=true){const box=$('stayResult');if(!results.length){box.innerHTML='<div class="empty"><strong>Keine freie Partnerunterkunft gefunden.</strong></div>';return}box.innerHTML=results.map(h=>`<article class="host-card"><span class="eyebrow">${online?'FREI':'PARTNER'}</span><h3>${esc(h.name)}</h3><div class="location">${esc(h.location||'')}</div><div class="chips"><span class="chip">1 Nacht</span><span class="chip">Direktzahlung</span></div>${h.price!=null?`<p><strong>€ ${Number(h.price).toFixed(2)}</strong></p>`:'<p>Preis wird bestätigt.</p>'}<div class="host-actions"><button class="btn primary" type="button" data-book='${encodeURIComponent(JSON.stringify({hostId:h.hostId||h.id,name:h.name,location:h.location,date,guests,price:h.price??null}))}'>Gastgeber auswählen</button></div></article>`).join('');box.querySelectorAll('[data-book]').forEach(btn=>btn.addEventListener('click',()=>openBooking(JSON.parse(decodeURIComponent(btn.dataset.book)))))}

function openTripBooking(){const items=currentTrip.days.slice(0,-1).map(d=>d.selected);activeBooking={type:'trip',items,guests:currentTrip.guests};$('bookingGuests').value=currentTrip.guests;$('bookingSummary').textContent=`Du fragst ${items.length} ausgewählte Gastgeber für deine komplette Reise an.`;$('bookingModal').style.display='grid';$('bookingModal').hidden=false;document.body.style.overflow='hidden';setBookingState('',false)}
function openBooking(data){if(!data||!data.hostId||!data.name)return;activeBooking={type:'single',items:[data],guests:data.guests};$('bookingGuests').value=data.guests;$('bookingSummary').textContent=`Du fragst jetzt ${data.name} in ${data.location} für ${data.date} an.`;$('bookingModal').style.display='grid';$('bookingModal').hidden=false;document.body.style.overflow='hidden';setBookingState('',false)}
function closeBooking(){$('bookingModal').hidden=true;$('bookingModal').style.display='none';document.body.style.overflow='';activeBooking=null}
function setBookingState(message,isError=false){let status=$('bookingStatus');if(!status){status=document.createElement('div');status.id='bookingStatus';status.style.marginTop='12px';status.style.padding='12px';status.style.borderRadius='10px';$('bookingForm').appendChild(status)}if(!message){status.hidden=true;status.textContent='';return}status.hidden=false;status.textContent=message;status.style.background=isError?'#fff0eb':'#edf7f1';status.style.color=isError?'#9a351f':'#174b3b'}

async function submitBooking(e){
  e.preventDefault();if(!activeBooking){setBookingState('Bitte zuerst Gastgeber auswählen.',true);return}
  const submit=e.submitter||$('bookingForm').querySelector('button[type="submit"]'),oldText=submit.textContent,refs=[];submit.disabled=true;submit.textContent='Wird gesendet …';setBookingState(`Anfrage an ${activeBooking.items.length} Gastgeber wird übertragen …`);
  try{
    for(const item of activeBooking.items){const payload={hostId:item.hostId,stayDate:item.date,guests:Number($('bookingGuests').value||1),guestName:$('guestName').value.trim(),guestEmail:$('guestEmail').value.trim(),guestPhone:$('guestPhone').value.trim(),note:$('bookingNote').value.trim(),price:item.price??null,paymentMethod:'host'};const r=await fetch(`${API_BASE}/api/guest-bookings`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const result=await r.json().catch(()=>({}));if(!r.ok)throw new Error(result.error||'Anfrage konnte nicht gesendet werden.');refs.push(result.reference)}
    setBookingState(`✓ Reiseanfrage übertragen. Referenzen: ${refs.join(', ')}. Die Gastgeber bestätigen nun ihre Nächte.`);submit.textContent='Anfrage gesendet ✓';
  }catch(err){setBookingState(`Anfrage konnte nicht gesendet werden: ${err.message}`,true);submit.disabled=false;submit.textContent=oldText}
}

$('tripForm').addEventListener('submit',async e=>{e.preventDefault();try{const route=currentRoute(),segments=selectedSegments(route,$('startPlace').value,$('endPlace').value),days=planDays(segments,Math.max(5,Number($('dailyKm').value||18)));await renderTrip(days,$('startDate').value)}catch(err){alert(err.message)}});
$('stayForm').addEventListener('submit',e=>{e.preventDefault();searchHosts()});$('bookingForm').addEventListener('submit',submitBooking);$('closeModal').addEventListener('click',closeBooking);$('bookingModal').addEventListener('click',e=>{if(e.target===$('bookingModal'))closeBooking()});$('route').addEventListener('change',initPlaces);
closeBooking();const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);$('startDate').value=iso(tomorrow);$('stayDate').value=iso(tomorrow);loadData().catch(err=>{console.error(err);alert('WachauEtappe konnte die Routendaten nicht laden.')});
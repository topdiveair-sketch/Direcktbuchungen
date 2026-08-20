/* ZAB Conversion Layer 2026-08-14
   Additive UI only: no booking, calendar, price or payment logic is replaced. */
(function(){
"use strict";

function ready(fn){
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",fn,{once:true});
  else fn();
}
function el(tag,attrs={},html=""){
  const node=document.createElement(tag);
  Object.entries(attrs).forEach(([key,value])=>{
    if(key==="class") node.className=value;
    else if(key==="id") node.id=value;
    else node.setAttribute(key,value);
  });
  if(html) node.innerHTML=html;
  return node;
}

ready(function(){
  function removeUnreleasedRooms(){
    if(window.SHOW_ADDITIONAL_ROOMS === true) return;

    document.querySelectorAll('[data-future-room]').forEach(function(element){
      element.remove();
    });

    document.querySelectorAll('input[name="room"]').forEach(function(input){
      if(["Marillenzimmer","Weinbergzimmer","Donauzimmer"].includes(input.value)){
        input.closest('.choice')?.remove();
      }
    });

    const bachblick = document.querySelector('input[name="room"][value="Bachblick"]');
    if(bachblick) bachblick.checked = true;
  }

  removeUnreleasedRooms();
  const bookingForm = document.getElementById('requestForm');
  ['input','change'].forEach(function(eventName){
    bookingForm?.addEventListener(eventName,function(){
      removeUnreleasedRooms();
      setTimeout(removeUnreleasedRooms,0);
    });
  });

  if(document.getElementById("zab-conv-style")) return;

  const style=el("style",{id:"zab-conv-style"},`
    .zab-audience-entry{max-width:1180px;margin:0 auto 28px;padding:0 2px}
    .zab-audience-entry h2{margin:0 0 8px;font-size:clamp(25px,4vw,38px)}
    .zab-audience-entry>p{margin:0 0 16px;color:var(--muted)}
    .zab-entry-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .zab-entry-card{display:grid;gap:5px;min-height:112px;padding:18px;border:1px solid var(--line);border-radius:16px;background:#fff;text-decoration:none;box-shadow:0 9px 22px rgba(23,55,47,.08);transition:.18s ease}
    .zab-entry-card:hover,.zab-entry-card:focus-visible{transform:translateY(-2px);border-color:var(--brand);box-shadow:0 15px 30px rgba(23,55,47,.13);outline:none}
    .zab-entry-card strong{font-size:18px;color:var(--ink)}
    .zab-entry-card span{color:var(--muted);font-size:14px}
    .zab-sales-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
    .zab-sales-card{padding:24px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(145deg,#fff,#f3f8f5);box-shadow:0 12px 30px rgba(23,55,47,.08)}
    .zab-sales-card h2{font-size:clamp(25px,3.4vw,36px);margin-bottom:12px}
    .zab-benefits{display:grid;gap:8px;margin:15px 0 20px;padding:0;list-style:none}
    .zab-benefits li{display:flex;gap:9px;align-items:flex-start;color:#314841;font-weight:720}
    .zab-benefits li:before{content:"✓";display:grid;place-items:center;flex:0 0 23px;height:23px;border-radius:50%;background:var(--brand);color:#fff;font-size:12px;font-weight:900}
    .zab-sales-card .btn{display:inline-grid;place-items:center;min-height:52px}
    .zab-pia-tip{margin-top:14px;padding:12px 14px;border-radius:12px;background:#fff8df;color:#624b1c;font-size:14px;font-weight:760}
    .zab-review-box{display:grid;gap:10px;margin:0 0 17px;padding:16px;border:1px solid #e0d2ad;border-radius:14px;background:#fffaf0}
    .zab-review-box h3{margin:0;font-size:18px}
    .zab-review-box blockquote{margin:0;padding:10px 12px;border-left:4px solid var(--brand);background:#fff;color:#30443d;font-size:13px}
    .zab-review-box .btn{margin-top:2px;width:100%;display:grid;place-items:center}
    .zab-gf-usecases{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:14px 0 18px}
    .zab-gf-usecases span{padding:12px;border:1px solid var(--line);border-radius:11px;background:#fff;color:#38534b;font-size:13px;font-weight:800;text-align:center}
    #gepaeckpreis.zab-gf-upgraded{padding:clamp(20px,4vw,34px);border:1px solid #d8e4dc;border-radius:18px;background:linear-gradient(145deg,#f7fbf8,#fffaf0)}
    #gepaeckpreis.zab-gf-upgraded .section-head h2{font-size:clamp(30px,4.3vw,44px)}
    @media(max-width:760px){
      .zab-entry-grid,.zab-sales-grid,.zab-gf-usecases{grid-template-columns:1fr}
      .zab-entry-card{min-height:86px;padding:15px}
      .zab-sales-card{padding:18px}
    }
  `);
  document.head.appendChild(style);

  const h1=document.querySelector("h1");
  if(h1) h1.textContent="Zuhause am Bach – Unterkunft am Donauradweg und Welterbesteig Wachau";

  const main=document.querySelector("main");
  if(main){
    const entry=el("section",{class:"zab-audience-entry",id:"zab-einstieg","aria-labelledby":"zab-einstieg-title"},`
      <span class="eyebrow">Welche Wachau-Auszeit planen Sie?</span>
      <h2 id="zab-einstieg-title">In wenigen Sekunden zum passenden Etappenstopp</h2>
      <p>Wählen Sie Ihren Reisegrund – danach sehen Sie sofort die für Sie wichtigsten Leistungen.</p>
      <div class="zab-entry-grid">
        <a class="zab-entry-card" href="#zab-radfahrer" data-track="audience_bike"><strong>🚴 Ich fahre den Donauradweg</strong><span>Rad sicher, E-Bike laden, Frühstück und Gepäcktransport.</span></a>
        <a class="zab-entry-card" href="#zab-wanderer" data-track="audience_hike"><strong>🥾 Ich wandere den Welterbesteig</strong><span>Ruhig schlafen, Frühstück, Etappentipps und Gepäck weiter.</span></a>
        <a class="zab-entry-card" href="#zimmer" data-track="audience_wachau"><strong>🌿 Ich möchte einfach in die Wachau</strong><span>Persönlich übernachten, Ruhe genießen und die Region entdecken.</span></a>
      </div>
    `);
    main.insertBefore(entry,main.firstChild);

    const dashboard=main.querySelector(".dashboard-strip");
    const sales=el("section",{class:"zab-sales-grid",id:"zab-zielgruppen","aria-label":"Angebote für Radfahrer und Wanderer"},`
      <article class="zab-sales-card" id="zab-radfahrer">
        <span class="eyebrow">Unterkunft am Donauradweg in Aggsbach Markt</span>
        <h2>🚴 Dein Etappenstopp am Donauradweg</h2>
        <ul class="zab-benefits">
          <li>Sichere Fahrradunterbringung</li>
          <li>E-Bike kostenlos laden</li>
          <li>Frühstück optional</li>
          <li>ZAB GepäckFrei verfügbar</li>
          <li>Ruhige Lage für die Nacht</li>
          <li>Persönliche Unterkunft statt großes Hotel</li>
          <li>Die Wachauer Windis als unverwechselbares Extra</li>
        </ul>
        <a class="btn" href="#booking-title" data-track="bike_booking_cta">Verfügbarkeit für meine Radetappe prüfen</a>
        <div class="zab-pia-tip">🐾 <strong>Pias Etappentipp:</strong> Dein Rad schläft sicher – und du hoffentlich noch besser.</div>
      </article>
      <article class="zab-sales-card" id="zab-wanderer">
        <span class="eyebrow">Unterkunft am Welterbesteig Wachau</span>
        <h2>🥾 Deine Nacht am Welterbesteig Wachau</h2>
        <ul class="zab-benefits">
          <li>Unterkunft in Aggsbach Markt</li>
          <li>Ruhige Übernachtung</li>
          <li>Frühstück vor der nächsten Etappe</li>
          <li>Gepäcktransport zur nächsten Unterkunft</li>
          <li>Informationen zur nächsten Etappe</li>
          <li>Wachauer Etappenstempel für Hausgäste</li>
          <li>Gäste-App mit regionalen Informationen</li>
        </ul>
        <a class="btn" href="#booking-title" data-track="hike_booking_cta">Meine Welterbesteig-Nacht prüfen</a>
      </article>
    `);
    if(dashboard) dashboard.insertAdjacentElement("afterend",sales);
    else entry.insertAdjacentElement("afterend",sales);
  }

  const form=document.getElementById("requestForm");
  if(form && !document.getElementById("zab-reviews")){
    const reviews=el("aside",{class:"zab-review-box",id:"zab-reviews","aria-labelledby":"zab-reviews-title"},`
      <h3 id="zab-reviews-title">⭐ Das sagen unsere Gäste</h3>
      <blockquote>„Wunderbar ruhige und sehr freundliche Unterkunft am Donauradweg.“</blockquote>
      <blockquote>„Die Fahrräder werden in einem Schuppen sicher untergestellt.“</blockquote>
      <blockquote>„Die Jausenplatte und das Frühstück waren phantastisch.“</blockquote>
      <a class="btn" href="#arrival" data-track="reviews_booking_cta">Jetzt meine Übernachtung prüfen</a>
    `);
    form.parentNode?.insertBefore(reviews,form);
  }

  const gf=document.getElementById("gepaeckpreis");
  if(gf){
    gf.classList.add("zab-gf-upgraded");
    const eyebrow=gf.querySelector(".section-head .eyebrow");
    if(eyebrow) eyebrow.textContent="ZAB GepäckFrei";
    const title=gf.querySelector(".section-head h2");
    if(title) title.textContent="🧳 Du gehst oder radelst. Wir bringen dein Gepäck weiter.";
    const intro=gf.querySelector(".section-head p");
    if(intro) intro.textContent="Ziel eingeben, Preis aus der tatsächlichen Fahrstrecke berechnen und den Transport direkt mit der Übernachtung anfragen.";
    if(!gf.querySelector(".zab-gf-usecases")){
      const usecases=el("div",{class:"zab-gf-usecases"},`
        <span>Vorherige Unterkunft → Zuhause am Bach</span>
        <span>Zuhause am Bach → nächste Unterkunft</span>
        <span>Etappe → Etappe auf Anfrage</span>
      `);
      gf.querySelector(".section-head")?.insertAdjacentElement("afterend",usecases);
    }
    const useButton=document.getElementById("zabGuestUsePrice");
    if(useButton) useButton.textContent="Gepäcktransport mit meiner Übernachtung anfragen";
  }

  const submit=document.getElementById("submitRequest");
  if(submit) submit.textContent="Diese Etappe anfragen";

  document.querySelectorAll('a[href="#booking-title"],a[href="#requestForm"],a[href="#arrival"]').forEach(link=>{
    link.addEventListener("click",function(){
      window.zabTrack?.("conversion_cta_click",{label:(link.textContent||"").trim()});
    });
  });
});
})();

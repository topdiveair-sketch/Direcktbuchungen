(function(){
  "use strict";

  const CAMPAIGN="winter_jauerling_2026_27";
  const ATTRIBUTION_KEY="zab_attribution_v1";
  const METRICS_KEY="zab_winter_metrics_v1";

  function isGermanHome(){
    const path=window.location.pathname||"";
    return !/\/(en|cs|sk|hu|pl|nl)\//.test(path) && !/skifahren-jauerling-unterkunft-wachau|winter-wachau-jauerling/.test(path);
  }

  function inWinterCampaignWindow(){
    const month=new Date().getMonth()+1;
    return month>=9 || month<=3;
  }

  function readJson(storage,key,fallback){
    try{return JSON.parse(storage.getItem(key)||"")||fallback;}catch(_){return fallback;}
  }

  function writeJson(storage,key,value){
    try{storage.setItem(key,JSON.stringify(value));}catch(_){}
  }

  function markWinterAttribution(source,medium){
    const existing=readJson(sessionStorage,ATTRIBUTION_KEY,{});
    writeJson(sessionStorage,ATTRIBUTION_KEY,{
      source:source||existing.source||"website",
      medium:medium||existing.medium||"internal",
      campaign:CAMPAIGN,
      referrer:existing.referrer||document.referrer||""
    });
  }

  function recordWinterEvent(name,details){
    const data=readJson(localStorage,METRICS_KEY,{events:[],counts:{}});
    data.counts=data.counts||{};
    data.counts[name]=(data.counts[name]||0)+1;
    data.events=Array.isArray(data.events)?data.events:[];
    data.events.push({
      event:name,
      campaign:CAMPAIGN,
      page:window.location.pathname,
      at:new Date().toISOString(),
      details:details||{}
    });
    if(data.events.length>200)data.events=data.events.slice(-200);
    writeJson(localStorage,METRICS_KEY,data);

    try{
      window.dataLayer=window.dataLayer||[];
      window.dataLayer.push({event:name,campaign:CAMPAIGN,...(details||{})});
    }catch(_){}
  }

  if(typeof window.zabTrack!=="function"){
    window.zabTrack=function(name,details){recordWinterEvent(name,details);};
  }

  function inferWinterReturn(){
    if(/skifahren-jauerling-unterkunft-wachau|winter-wachau-jauerling/i.test(document.referrer||"")){
      markWinterAttribution("website","winter_landingpage");
      recordWinterEvent("winter_return_to_booking",{referrer:document.referrer});
    }
  }

  function installWinterPromo(){
    inferWinterReturn();
    if(!isGermanHome() || !inWinterCampaignWindow() || document.getElementById("zab-winter-jauerling")) return;

    const section=document.createElement("section");
    section.id="zab-winter-jauerling";
    section.setAttribute("aria-labelledby","zab-winter-jauerling-title");
    section.innerHTML=`
      <div class="zab-winter-card">
        <div>
          <span class="zab-winter-kicker">❄️ Winter in der Wachau · Jauerling</span>
          <h2 id="zab-winter-jauerling-title">Jauerling-Wochenende mit ruhiger Übernachtung in der Wachau</h2>
          <p>Skifahren, Flutlicht oder einfach ein ruhiges Winterwochenende: Zuhause am Bach in Aggsbach Markt ist der persönliche Ausgangspunkt für 1–2 Nächte. Frühstück auf Vorbestellung, Parkplatz und ruhige Lage inklusive.</p>
          <p class="zab-winter-note">Liftbetrieb, Schneelage, Skischule und Verleih bitte immer aktuell direkt beim Jauerling prüfen.</p>
        </div>
        <div class="zab-winter-actions">
          <a class="zab-winter-primary" href="skifahren-jauerling-unterkunft-wachau/?utm_source=website&utm_medium=internal&utm_campaign=${CAMPAIGN}">Jauerling-Wochenende ansehen</a>
          <a class="zab-winter-secondary" href="#requestForm">Verfügbarkeit prüfen</a>
        </div>
      </div>`;

    const style=document.createElement("style");
    style.textContent=`
      #zab-winter-jauerling{margin:22px min(5vw,56px) 12px}
      .zab-winter-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center;padding:24px;border:1px solid #cbdce5;border-radius:12px;background:linear-gradient(135deg,#f5fbff,#eef5f0);box-shadow:0 10px 28px rgba(24,54,70,.10)}
      .zab-winter-kicker{display:inline-block;margin-bottom:7px;font-size:13px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;color:#315d75}
      .zab-winter-card h2{margin:0 0 9px;font-size:clamp(24px,3vw,34px);line-height:1.08}
      .zab-winter-card p{margin:0 0 8px;color:#52645e}
      .zab-winter-note{font-size:13px}
      .zab-winter-actions{display:grid;gap:9px;min-width:230px}
      .zab-winter-actions a{display:inline-flex;justify-content:center;align-items:center;min-height:46px;padding:11px 15px;border-radius:7px;text-decoration:none;font-weight:900}
      .zab-winter-primary{background:#315d75;color:#fff}
      .zab-winter-secondary{background:#fff;color:#315d75;border:1px solid #9eb7c4}
      @media(max-width:760px){.zab-winter-card{grid-template-columns:1fr}.zab-winter-actions{min-width:0}}
    `;
    document.head.appendChild(style);

    const main=document.querySelector("main");
    if(main) main.insertAdjacentElement("beforebegin",section);
    else document.body.appendChild(section);

    recordWinterEvent("winter_promo_impression");

    section.querySelector(".zab-winter-primary")?.addEventListener("click",()=>{
      markWinterAttribution("website","internal");
      recordWinterEvent("winter_landingpage_click");
    });

    section.querySelector(".zab-winter-secondary")?.addEventListener("click",()=>{
      markWinterAttribution("website","winter_booking_cta");
      recordWinterEvent("winter_booking_cta_click");
    });
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",installWinterPromo,{once:true});
  else installWinterPromo();
})();

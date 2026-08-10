
    (function(){
      const a=document.getElementById('arrival');
      const d=document.getElementById('departure');
      const steps=[...document.querySelectorAll('.booking-progress span')];
      const today=()=>{const x=new Date();x.setMinutes(x.getMinutes()-x.getTimezoneOffset());return x.toISOString().slice(0,10)};
      if(a)a.min=today();
      function sync(){
        if(a&&d){d.min=a.value||today();if(d.value&&a.value&&d.value<=a.value)d.value='';}
        let n=0;
        if(a&&d&&a.value&&d.value)n=1;
        if(n===1&&document.querySelector('input[name="room"]:checked'))n=2;
        steps.forEach((s,i)=>{s.style.background=i===n?'var(--brand)':'#edf5f1';s.style.color=i===n?'#fff':'#38534b';});
      }
      a&&a.addEventListener('change',sync);
      d&&d.addEventListener('change',sync);
      document.querySelectorAll('input[name="room"]').forEach(x=>x.addEventListener('change',sync));
      sync();
    })();
  
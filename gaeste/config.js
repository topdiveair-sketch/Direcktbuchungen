// Online-API der Gäste-Webseite.
window.WACHAUETAPPE_API_BASE = 'https://web-production-907d68.up.railway.app';

// Zusatzmodule der öffentlichen Gäste-Seite laden.
window.addEventListener('DOMContentLoaded', () => {
  const script = document.createElement('script');
  script.src = 'account.js?v=259e5e2';
  script.defer = true;
  document.body.appendChild(script);
});

(() => {
  const rows = [...document.querySelectorAll('[data-radar-row]')];
  const search = document.querySelector('[data-radar-search]');
  const filters = [...document.querySelectorAll('[data-radar-filter]')];
  const visibleCount = document.querySelector('[data-radar-visible-count]');
  let active = 'all';

  function apply() {
    const q = (search?.value || '').trim().toLowerCase();
    let count = 0;
    rows.forEach(row => {
      const traffic = row.dataset.traffic || 'gray';
      const text = (row.dataset.search || row.textContent || '').toLowerCase();
      const okTraffic = active === 'all' || traffic === active;
      const okQuery = !q || text.includes(q);
      const show = okTraffic && okQuery;
      row.hidden = !show;
      if (show) count += 1;
    });
    if (visibleCount) visibleCount.textContent = String(count);
  }

  filters.forEach(btn => btn.addEventListener('click', () => {
    active = btn.dataset.radarFilter || 'all';
    filters.forEach(x => x.classList.toggle('active', x === btn));
    apply();
  }));
  search?.addEventListener('input', apply);
  apply();

  document.querySelectorAll('[data-confirm-action]').forEach(form => {
    form.addEventListener('submit', e => {
      const message = form.dataset.confirmAction;
      if (message && !window.confirm(message)) e.preventDefault();
    });
  });
})();

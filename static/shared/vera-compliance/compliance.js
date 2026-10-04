(() => {
  const rows = [...document.querySelectorAll('.requirement')];
  const groups = [...document.querySelectorAll('.requirement-group')];
  const buttons = [...document.querySelectorAll('[data-filter]')];
  const search = document.querySelector('#search');
  const result = document.querySelector('.filter-result');
  const toolbar = document.querySelector('.toolbar');
  const example = document.querySelector('#report-esempio');
  const reportDisclosure = example.querySelector('details');
  reportDisclosure.addEventListener('toggle', () => {
    example.querySelector('.disclosure-action').textContent = reportDisclosure.open ? 'Chiudi l’esempio −' : 'Apri l’esempio +';
  });
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const searchable = new Map(rows.map(row => [row, normalize(row.textContent)]));
  let currentFilter = 'all';
  const applyFilters = () => {
    const terms = normalize(search.value).trim().split(/\s+/).filter(Boolean);
    rows.forEach(row => {
      row.hidden = (currentFilter !== 'all' && row.dataset.status !== currentFilter) || !terms.every(term => searchable.get(row).includes(term));
    });
    groups.forEach(group => {
      const visible = [...group.querySelectorAll('.requirement')].filter(row => !row.hidden).length;
      group.hidden = visible === 0;
      group.querySelector('.group-count').textContent = `${visible} ${visible === 1 ? 'voce' : 'voci'}`;
    });
    example.hidden = document.querySelector('#g1-3').hidden;
    const visible = rows.filter(row => !row.hidden).length;
    result.textContent = visible === rows.length ? `${rows.length} voci` : `${visible} di ${rows.length} voci`;
    document.querySelector('.empty-state').hidden = visible > 0;
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === currentFilter)));
  };
  const reset = () => { currentFilter = 'all'; search.value = ''; applyFilters(); };
  buttons.forEach(button => button.addEventListener('click', () => { currentFilter = button.dataset.filter; applyFilters(); }));
  search.addEventListener('input', applyFilters);
  document.querySelector('#clear-filters').addEventListener('click', () => { reset(); search.focus(); });
  const reveal = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    if (target.matches('.requirement,.requirement-group,.example-row')) reset();
    if (target === example) example.querySelector('details').open = true;
    requestAnimationFrame(() => target.scrollIntoView({block: 'start'}));
  };
  window.addEventListener('hashchange', reveal);
  document.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click', () => {
    if (link.hash === location.hash) reveal();
  }));
  document.querySelector('.search').hidden = false;
  document.querySelector('.filter-row').hidden = false;
  const resize = () => document.documentElement.style.setProperty('--toolbar-height', `${toolbar.getBoundingClientRect().height}px`);
  new ResizeObserver(resize).observe(toolbar);
  resize();
  applyFilters();
  reveal();
})();

(() => {
  const items = [...document.querySelectorAll('.requirement')];
  const groups = [...document.querySelectorAll('.requirement-group')];
  const buttons = [...document.querySelectorAll('[data-filter]')];
  const expand = document.querySelector('.expand-all');
  const result = document.querySelector('.filter-result');
  const visible = () => items.filter(item => !item.hidden);
  const updateExpand = () => {
    const allOpen = visible().every(item => item.querySelector('details').open);
    expand.setAttribute('aria-pressed', String(allOpen));
    expand.textContent = allOpen ? 'Chiudi tutti i dettagli' : 'Apri tutti i dettagli';
  };
  const filter = value => {
    items.forEach(item => { item.hidden = value !== 'all' && item.dataset.status !== value; });
    groups.forEach(group => { group.hidden = ![...group.querySelectorAll('.requirement')].some(item => !item.hidden); });
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === value)));
    result.textContent = `${visible().length} di ${items.length} voci`;
    updateExpand();
  };
  buttons.forEach(button => button.addEventListener('click', () => filter(button.dataset.filter)));
  expand.addEventListener('click', () => {
    const open = expand.getAttribute('aria-pressed') !== 'true';
    visible().forEach(item => { item.querySelector('details').open = open; });
    updateExpand();
  });
  items.forEach(item => item.querySelector('details').addEventListener('toggle', updateExpand));
  const revealAnchor = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    if (target.classList.contains('requirement')) {
      filter('all');
      target.querySelector('details').open = true;
    } else if (target.classList.contains('requirement-group')) filter('all');
    requestAnimationFrame(() => target.scrollIntoView());
  };
  document.querySelector('.filters').hidden = false;
  filter('all');
  window.addEventListener('hashchange', revealAnchor);
  revealAnchor();
})();

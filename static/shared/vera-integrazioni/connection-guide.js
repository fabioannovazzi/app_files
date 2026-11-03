(() => {
  const locales = JSON.parse(document.getElementById('locales').textContent);
  const requested = new URLSearchParams(location.search).get('lang');
  const lang = Object.hasOwn(locales, requested) ? requested : 'it';
  document.documentElement.lang = lang;
  document.title = locales[lang].copy[0] + ' | Vera';
  for (const kind of ['ui', 'copy']) {
    for (const node of document.querySelectorAll('[data-' + kind + ']')) {
      node.textContent = locales[lang][kind][Number(node.dataset[kind])];
    }
  }
  document.getElementById('back').href = '../index.html?lang=' + lang;
  document.querySelector('nav a[lang="' + lang + '"]').setAttribute('aria-current','page');
})();

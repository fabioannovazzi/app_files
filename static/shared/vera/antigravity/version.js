(() => {
  fetch('/static/shared/vera/downloads/vera-antigravity-plugin.json', { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(manifest => {
      if (manifest.name !== 'vera' || !/^\d+\.\d+\.\d+$/.test(manifest.version)) return;
      document.querySelectorAll('[data-antigravity-version]').forEach(label => {
        label.textContent = `ZIP · v${manifest.version}`;
        label.hidden = false;
      });
    })
    .catch(() => {}); // The download remains available if metadata cannot load.
})();

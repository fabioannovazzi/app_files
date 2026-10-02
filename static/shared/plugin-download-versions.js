(() => {
  const repository = "https://raw.githubusercontent.com/fabioannovazzi/app_files/main";
  const products = ["vera", "clara", "lucia"];

  for (const product of products) {
    const labels = document.querySelectorAll(`[data-plugin-zip-version="${product}"]`);
    if (!labels.length) continue;

    // Release CI checks that this manifest and the ZIP at the same main ref agree.
    // Read the small manifest rather than downloading the whole ZIP on page load.
    fetch(`${repository}/plugins/${product}/.codex-plugin/plugin.json`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((manifest) => {
        if (manifest.name !== product || typeof manifest.version !== "string" ||
            !/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(manifest.version)) return;
        for (const label of labels) {
          label.textContent = ` · v${manifest.version}`;
          if (label.tagName === "P") label.textContent = `ZIP · v${manifest.version}`;
          label.hidden = false;
        }
      })
      .catch(() => {
        // Keep downloads usable without displaying an unverified version.
      });
  }
})();

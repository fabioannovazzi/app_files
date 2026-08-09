(() => {
  "use strict";

  const search = document.querySelector("[data-privacy-register-search]");
  const entries = Array.from(
    document.querySelectorAll("[data-privacy-register-entry]"),
  );
  const groups = Array.from(
    document.querySelectorAll("[data-privacy-register-group]"),
  );
  const count = document.querySelector("[data-privacy-register-count]");
  const countLabel = document.querySelector(
    "[data-privacy-register-count-label]",
  );
  const empty = document.querySelector("[data-privacy-register-empty]");

  if (!search || !entries.length || !count || !countLabel || !empty) return;

  const singular = search.closest(".privacy-register")?.dataset.resultSingular;
  const plural = search.closest(".privacy-register")?.dataset.resultPlural;

  const normalize = (value) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase();

  const update = () => {
    const query = normalize(search.value.trim());
    let visible = 0;

    entries.forEach((entry) => {
      const matches = !query || normalize(entry.dataset.search || "").includes(query);
      entry.hidden = !matches;
      if (matches) visible += 1;
    });

    groups.forEach((group) => {
      group.hidden = !group.querySelector(
        "[data-privacy-register-entry]:not([hidden])",
      );
    });

    count.textContent = String(visible);
    if (singular && plural) countLabel.textContent = visible === 1 ? singular : plural;
    empty.hidden = visible !== 0;
  };

  search.addEventListener("input", update);

  document
    .querySelectorAll('.privacy-entry__service-links a[href^="#service-"]')
    .forEach((link) => {
      link.addEventListener("click", () => {
        const target = document.getElementById(link.hash.slice(1));
        if (target instanceof HTMLDetailsElement) target.open = true;
      });
    });

  const targetHash = window.location.hash;
  if (/^#(?:privacy|service)-[a-z0-9-]+$/.test(targetHash)) {
    const target = document.getElementById(targetHash.slice(1));
    if (target instanceof HTMLDetailsElement) target.open = true;
  }
})();

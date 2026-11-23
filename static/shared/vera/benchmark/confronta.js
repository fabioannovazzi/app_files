(() => {
  const data = window.fiscalBenchmarkComparison;
  const examples = window.fiscalBenchmarkExamples;
  const byId = (id) => document.getElementById(id);
  const controls = {
    left: byId("left"), right: byId("right"), query: byId("query"), sort: byId("sort"),
    totals: byId("totals"), filters: byId("filters"), cases: byId("cases"),
    count: byId("visible-count"), detail: byId("detail"), workspace: byId("workspace")
  };
  const defaultLeft = "vera-astra-62";
  const defaultRight = "codex-astra-62";
  const configNames = new Map(data.configs.map(({ id, label }) => [id, label]));
  const dataCases = new Map(data.cases.map((item) => [item.id, item]));
  const mobile = matchMedia("(max-width: 760px)");
  const validFilters = ["all", "left", "tie", "right", "different"];

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function button(text, action, className) {
    const element = node("button", text, className);
    element.type = "button";
    element.addEventListener("click", action);
    return element;
  }

  function isAstra62Pair({ left, right }) {
    return (left === defaultLeft && right === defaultRight) ||
      (left === defaultRight && right === defaultLeft);
  }

  function readState() {
    const params = new URLSearchParams(location.search);
    const candidate = params.get("a");
    const left = configNames.has(candidate) ? candidate : defaultLeft;
    const requested = params.get("b");
    const right = configNames.has(requested) && requested !== left
      ? requested : data.configs.find(({ id }) => id !== left).id;
    const filter = params.get("esito");
    const selected = params.get("caso");
    return {
      left, right,
      query: params.get("cerca") || "",
      sort: params.get("ordine") === "codice" ? "code" : "gap",
      filter: validFilters.includes(filter) ? filter : "all",
      selected: dataCases.has(selected) ? selected : null
    };
  }

  let state = readState();
  let scrollBeforeDetail = 0;

  function updateUrl(push) {
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("a", state.left);
    url.searchParams.set("b", state.right);
    if (state.query) url.searchParams.set("cerca", state.query);
    if (state.sort === "code") url.searchParams.set("ordine", "codice");
    if (state.filter !== "all") url.searchParams.set("esito", state.filter);
    if (state.selected) url.searchParams.set("caso", state.selected);
    try {
      history[push ? "pushState" : "replaceState"](null, "", url);
    } catch {
      // Some local HTML previews restrict history changes.
    }
  }

  function formatScore(score, withPercent = false) {
    if (!score || score[1] === 0) return "—";
    const [n, d, minimum] = score;
    const percentage = withPercent ? ` (${Math.round(n * 100 / d)}%)` : "";
    return `${minimum ? "≥ " : ""}${n.toLocaleString("it-IT")}/${d.toLocaleString("it-IT")}${percentage}`;
  }

  function normalized(value) {
    return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("it");
  }

  function resultType(gap) {
    if (gap > 0) return "left";
    if (gap < 0) return "right";
    return "tie";
  }

  function scoredCases() {
    return data.cases.map((item) => {
      const gap = item.scores[state.left].content[0] - item.scores[state.right].content[0];
      const different = gap === 0 && isAstra62Pair(state) && item.astra62.veraOnly > 0;
      return { item, gap, different };
    });
  }

  function updateSelectors() {
    for (const side of ["left", "right"]) {
      const other = side === "left" ? state.right : state.left;
      const options = data.configs.map(({ id, label }) => {
        const option = new Option(label, id, false, state[side] === id);
        option.disabled = id === other;
        return option;
      });
      controls[side].replaceChildren(...options);
    }
    controls.query.value = state.query;
    controls.sort.value = state.sort;
  }

  function renderTotals() {
    const cards = ["left", "right"].map((side) => {
      const id = state[side];
      const totals = data.cases.reduce(([n, d], item) => {
        const [caseNumerator, caseDenominator] = item.scores[id].content;
        return [n + caseNumerator, d + caseDenominator];
      }, [0,0]);
      const card = node("div", undefined, `total ${side}-card`);
      card.append(node("span", configNames.get(id)), node("strong", formatScore(totals, true)));
      return card;
    });
    controls.totals.replaceChildren(...cards);
  }

  function renderFilters(cases) {
    const counts = {all: cases.length, left: 0, tie: 0, right: 0, different: 0};
    for (const {gap, different} of cases) {
      counts[resultType(gap)]++;
      if (different) counts.different++;
    }
    const labels = {
      all: "Tutti", left: `${configNames.get(state.left)} avanti`, tie: "Pari",
      right: `${configNames.get(state.right)} avanti`, different: "Pari, punti diversi"
    };
    const filters = validFilters.filter((filter) => filter !== "different" || isAstra62Pair(state));
    controls.filters.replaceChildren(...filters.map((filter) => {
      const element = button(`${labels[filter]} · ${counts[filter]}`, () => {
        state.filter = filter;
        updateUrl(false);
        renderList();
        updatePressedFilters();
      });
      element.dataset.filter = filter;
      return element;
    }));
    updatePressedFilters();
  }

  function updatePressedFilters() {
    for (const control of controls.filters.children) {
      control.setAttribute("aria-pressed", String(control.dataset.filter === state.filter));
    }
  }

  function renderList() {
    const query = normalized(state.query.trim());
    const visible = scoredCases().filter(({item, gap, different}) => {
      const match = state.filter === "all" ||
        (state.filter === "different" ? different : resultType(gap) === state.filter);
      const searchable = `${item.id} ${item.title} ${examples[item.id]?.summary || ""}`;
      return match && normalized(searchable).includes(query);
    });
    if (state.sort === "gap") visible.sort((a,b) =>
      Math.abs(b.gap) - Math.abs(a.gap) || Number(b.different) - Number(a.different));

    controls.count.textContent = `${visible.length} di ${data.cases.length} quesiti`;
    controls.cases.replaceChildren(...visible.map(({item, gap, different}) => {
      const row = button(undefined, () => openCase(item.id), "case-row");
      row.dataset.case = item.id;
      row.setAttribute("aria-pressed", String(state.selected === item.id));
      const badges = node("span", undefined, "case-scores");
      for (const side of ["left", "right"]) {
        const id = state[side];
        const score = formatScore(item.scores[id].content);
        const badge = node("span", score, `score ${side}`);
        badge.setAttribute("aria-label", `${configNames.get(id)} ${score}`);
        badges.append(badge);
      }
      const details = different ? `${item.id} · punti diversi` : item.id;
      row.append(node("span", item.title, "case-title"), node("span", details, "case-meta"), badges,
        node("span", gap === 0 ? "Pari" : `Δ ${gap > 0 ? "+" : "−"}${Math.abs(gap)}`, "delta"));
      return row;
    }));
    if (!visible.length) controls.cases.append(node("p", "Nessun quesito corrisponde ai filtri.", "muted"));
  }

  function metricsTable(item) {
    const table = node("table", undefined, "metrics");
    const head = table.createTHead().insertRow();
    for (const title of ["Indicatore", configNames.get(state.left), configNames.get(state.right)]) {
      const th = node("th", title);
      th.scope = "col";
      head.append(th);
    }
    const body = table.createTBody();
    for (const [key, title] of [["content","Contenuti"],["coverage","Supporto documentale"],["citations","Citazioni pertinenti"]]) {
      const row = body.insertRow();
      const label = node("th", title);
      label.scope = "row";
      row.append(label, ...[state.left,state.right].map((id) =>
        node("td", formatScore(item.scores[id][key], true))));
    }
    return table;
  }

  function pointsBreakdown(item) {
    const counts = item.astra62;
    const ideas = [
      [counts.both, "Entrambi"],
      [counts.veraOnly, "Solo Vera"],
      [counts.codexOnly, "Solo Codex"],
      [counts.neither, "Nessuno dei due"]
    ];
    const section = node("div", undefined, "detail-notes");
    section.append(node("h3", "Chi ha soddisfatto i punti"));
    const grid = node("div", undefined, "breakdown");
    for (const [value, label] of ideas) {
      const cell = node("div");
      cell.append(node("strong", String(value)), document.createTextNode(label));
      grid.append(cell);
    }
    section.append(grid);
    return section;
  }

  function renderExample(example) {
    const section = node("div", undefined, "detail-notes");
    section.append(node("h3", "Perché questi punteggi"));
    for (const point of example.points) {
      const article = node("article");
      article.append(node("h3",point.title));
      const excerptPair = node("div", undefined, "excerpts");
      for (const side of ["left", "right"]) {
        const selected = state[side];
        const excerpt = node("div", undefined, `excerpt ${side}-card`);
        excerpt.append(node("strong", configNames.get(selected)), node("blockquote",
          selected === defaultLeft ? point.vera : point.codex));
        excerptPair.append(excerpt);
      }
      article.append(excerptPair, node("p", point.note));
      section.append(article);
    }
    return section;
  }

  function renderDetail() {
    const item = dataCases.get(state.selected);
    controls.workspace.classList.toggle("has-case", Boolean(item));
    if (!item) {
      const title = node("h2", "Apri un quesito");
      title.id = "detail-title";
      controls.detail.replaceChildren(title, node("p", "Scegli un caso dalla lista per vedere i tre indicatori."));
      if (isAstra62Pair(state)) controls.detail.append(button("Vedi un pareggio con punti diversi",
        () => openCase("E26-B02-09"), "suggestion"));
      return;
    }
    const example = isAstra62Pair(state) ? examples[item.id] : undefined;
    const title = node("h2", item.title, "case-heading");
    title.id = "detail-title";
    controls.detail.replaceChildren(button("← Torna ai quesiti", closeCase, "detail-back"),
      node("p", item.id, "muted"), title);
    if (example) controls.detail.append(node("p", example.summary));
    controls.detail.append(metricsTable(item));
    if (isAstra62Pair(state)) controls.detail.append(pointsBreakdown(item));
    if (example) controls.detail.append(renderExample(example));
    else controls.detail.append(node("p", "Per questo confronto sono disponibili i conteggi del caso.", "muted"));

    const share = node("a", "Link a questo confronto e quesito", "link-share");
    share.href = location.href;
    controls.detail.append(share);
  }

  function openCase(id) {
    if (!state.selected) scrollBeforeDetail = window.scrollY;
    state.selected = id;
    updateUrl(true);
    for (const row of controls.cases.children) row.setAttribute("aria-pressed", String(row.dataset.case === id));
    renderDetail();
    controls.detail.focus({preventScroll: true});
    if (mobile.matches) controls.detail.scrollIntoView();
  }

  function closeCase() {
    const id = state.selected;
    state.selected = null;
    updateUrl(false);
    renderDetail();
    const row = Array.from(controls.cases.children).find((entry) => entry.dataset.case === id);
    if (row) {
      row.setAttribute("aria-pressed","false");
      row.focus({preventScroll: true});
    } else controls.query.focus({preventScroll: true});
    if (mobile.matches) window.scrollTo(0, scrollBeforeDetail);
  }

  function renderAll() {
    if (state.filter === "different" && !isAstra62Pair(state)) state.filter = "all";
    updateSelectors();
    renderTotals();
    renderFilters(scoredCases());
    renderList();
    renderDetail();
  }

  for (const side of ["left", "right"]) {
    controls[side].addEventListener("change", () => {
      state[side] = controls[side].value;
      renderAll();
      updateUrl(false);
    });
  }
  byId("swap").addEventListener("click", () => {
    [state.left,state.right] = [state.right,state.left];
    if (state.filter === "left") state.filter = "right";
    else if (state.filter === "right") state.filter = "left";
    renderAll();
    updateUrl(false);
  });
  controls.query.addEventListener("input", () => {
    state.query = controls.query.value;
    updateUrl(false);
    renderList();
  });
  controls.sort.addEventListener("change", () => {
    state.sort = controls.sort.value;
    updateUrl(false);
    renderList();
  });
  window.addEventListener("popstate", () => {
    state = readState();
    renderAll();
    if (!state.selected && mobile.matches) window.scrollTo(0, scrollBeforeDetail);
  });
  renderAll();
  updateUrl(false);
  if (state.selected && mobile.matches) controls.detail.scrollIntoView();
})();

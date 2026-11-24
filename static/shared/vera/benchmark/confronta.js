(() => {
  const data = window.fiscalBenchmarkComparison;
  const examples = window.fiscalBenchmarkExamples;
  const outcomes = window.fiscalBenchmarkOutcomes;
  const pointRegisters = window.fiscalBenchmarkPointRegisters;
  const byId = (id) => document.getElementById(id);
  const controls = {
    left: byId("left"), right: byId("right"), query: byId("query"), sort: byId("sort"),
    totals: byId("totals"), measure: byId("measure"), filters: byId("filters"), cases: byId("cases"),
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
      ? requested : left === defaultRight ? defaultLeft : defaultRight;
    const filter = params.get("esito");
    const selected = params.get("caso");
    return {
      left, right,
      measure: params.get("indicatore") === "concordanza" ? "outcome" : "content",
      query: params.get("cerca") || "",
      sort: params.get("ordine") === "codice" ? "code" : "gap",
      filter: validFilters.includes(filter) ? filter : "all",
      selected: dataCases.has(selected) ? selected : null
    };
  }

  let state = readState();
  let scrollBeforeDetail = 0;

  function updateUrl(push) {
    const url = comparisonUrl();
    try {
      history[push ? "pushState" : "replaceState"](null, "", url);
    } catch {
      // Some local HTML previews restrict history changes.
    }
  }

  function comparisonUrl() {
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("a", state.left);
    url.searchParams.set("b", state.right);
    if (state.measure === "outcome") url.searchParams.set("indicatore", "concordanza");
    if (state.query) url.searchParams.set("cerca", state.query);
    if (state.sort === "code") url.searchParams.set("ordine", "codice");
    if (state.filter !== "all") url.searchParams.set("esito", state.filter);
    if (state.selected) url.searchParams.set("caso", state.selected);
    return url;
  }

  function formatScore(score, withPercent = false) {
    if (!score || score[1] === 0) return "—";
    const [n, d, minimum] = score;
    if (d === null) return n ? `${n.toLocaleString("it-IT")} pertinenti · totale aperto` : "Totale aperto";
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

  const outcomeLabels = ["Non concorda", "Esito variabile", "Concorda"];

  function outcomePasses(caseId, configId) {
    return outcomes[caseId].results[configId].filter(({result}) => result === "pass").length;
  }

  function showsDifferentPoints() {
    return state.measure === "content" && isAstra62Pair(state);
  }

  function scoredCases() {
    return data.cases.map((item) => {
      const gap = state.measure === "outcome"
        ? outcomePasses(item.id, state.left) - outcomePasses(item.id, state.right)
        : item.scores[state.left].content[0] - item.scores[state.right].content[0];
      const different = gap === 0 && showsDifferentPoints() && item.astra62.veraOnly > 0;
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
      let score;
      if (state.measure === "outcome") {
        const passes = data.cases.reduce((n, item) => n + outcomePasses(item.id, id), 0);
        const judgments = data.cases.reduce((n, item) => n + outcomes[item.id].results[id].length, 0);
        score = `${Math.round(passes * 100 / judgments)}%`;
      } else {
        const totals = data.cases.reduce(([n, d], item) => {
          const [caseNumerator, caseDenominator] = item.scores[id].content;
          return [n + caseNumerator, d + caseDenominator];
        }, [0, 0]);
        score = formatScore(totals, true);
      }
      const card = node("div", undefined, `total ${side}-card`);
      card.append(node("span", configNames.get(id)), node("strong", score));
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
    const filters = validFilters.filter((filter) => filter !== "different" || showsDifferentPoints());
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
      const searchable = `${item.id} ${item.title} ${examples[item.id]?.summary || ""} ${outcomes[item.id].question}`;
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
        const agreement = state.measure === "outcome";
        const passes = agreement ? outcomePasses(item.id, id) : null;
        const score = agreement ? ["No", "Varia", "Sì"][passes] : formatScore(item.scores[id].content);
        const badge = node("span", score, `score ${side}${agreement ? " outcome-score" : ""}`);
        const label = agreement ? outcomeLabels[passes] : score;
        badge.setAttribute("aria-label", `${configNames.get(id)} · ${label}`);
        if (agreement) badge.title = label;
        badges.append(badge);
      }
      const details = different ? `${item.id} · punti diversi` : item.id;
      row.append(node("span", item.title, "case-title"), node("span", details, "case-meta"), badges);
      if (state.measure === "content") {
        row.append(node("span", gap === 0 ? "Pari" : `Δ ${gap > 0 ? "+" : "−"}${Math.abs(gap)}`, "delta"));
      }
      return row;
    }));
    if (!visible.length) controls.cases.append(node("p", "Nessun quesito corrisponde ai filtri.", "muted"));
  }

  function metricsTable(item, available, showReview) {
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
      row.append(label, ...[state.left,state.right].map((id) => {
        const score = formatScore(item.scores[id][key], true);
        const cell = node("td");
        if (key === "content" && available.includes(id)) {
          const control = button(score, () => showReview(id), "point-score");
          control.setAttribute("aria-label", `${score} · Vedi i singoli punti di ${configNames.get(id)}`);
          control.setAttribute("aria-controls", "point-review");
          cell.append(control);
        } else {
          cell.textContent = score;
        }
        return cell;
      }));
    }
    return table;
  }

  const reviewsByCase = new Map();

  function loadPointReview(item, container, tools, afterRender) {
    const render = (review) => {
      if (!container.isConnected) return;
      container.replaceChildren(pointsBreakdown(review, tools));
      if (afterRender) afterRender();
    };
    const cached = reviewsByCase.get(item.id);
    if (cached) {
      render(cached);
      return;
    }
    const status = node("p", "Caricamento dei singoli punti…", "muted");
    status.setAttribute("role", "status");
    container.replaceChildren(status);
    fetch(`dettagli-estesi/${encodeURIComponent(item.id)}.json`)
      .then((response) => {
        if (!response.ok) throw new Error("Dettaglio non disponibile");
        return response.json();
      })
      .then((review) => {
        reviewsByCase.set(item.id, review);
        render(review);
      })
      .catch(() => {
        if (!container.isConnected) return;
        status.textContent = "Il dettaglio dei punti non è disponibile al momento.";
        container.append(button("Riprova", () => loadPointReview(item, container, tools, afterRender), "detail-back"));
      });
  }

  function pointsBreakdown(review, tools) {
    const name = (id) => id === defaultLeft ? "Vera" : id === defaultRight ? "Codex" : configNames.get(id);
    const [left, right] = tools;
    const ideas = right ? [
      ["both", "Entrambi", (p) => p.results[left].score && p.results[right].score],
      ["left", `Solo ${name(left)}`, (p) => p.results[left].score && !p.results[right].score],
      ["right", `Solo ${name(right)}`, (p) => !p.results[left].score && p.results[right].score],
      ["neither", "Nessuno dei due", (p) => !p.results[left].score && !p.results[right].score]
    ] : [
      ["zero", "Punti non assegnati", (p) => !p.results[left].score],
      ["one", "Punti assegnati", (p) => p.results[left].score],
      ["all", "Tutti i punti", () => true]
    ];
    const groups = ideas.map(([group, label, test]) => [group, label, review.points.filter(test)]);
    const section = node("div", undefined, "detail-notes");
    section.append(node("h3", right ? "Chi ha soddisfatto i punti" : `Dettaglio · ${configNames.get(left)}`));
    const grid = node("div", undefined, "breakdown");
    const status = node("span");
    status.setAttribute("role", "status");
    status.className = "muted";
    const list = node("div", undefined, "point-list");
    list.id = "point-list";

    function show(group, label, points) {
      status.textContent = `${label} · ${points.length} ${points.length === 1 ? "punto" : "punti"}`;
      list.replaceChildren(...points.map((point) => renderPoint(point, review.opinions, tools)));
      for (const control of grid.children) {
        control.setAttribute("aria-pressed", String(control.dataset.group === group));
      }
    }

    for (const [group, label, points] of groups) {
      const control = button(`${label} · ${points.length}`, () => show(group, label, points));
      control.dataset.group = group;
      control.setAttribute("aria-controls", list.id);
      control.disabled = points.length === 0;
      grid.append(control);
    }
    section.append(grid, status, list);
    const order = right
      ? (right === defaultLeft ? ["left", "right", "neither", "both"] : ["right", "left", "neither", "both"])
      : ["zero", "one", "all"];
    const first = order.map((key) => groups.find(([group]) => group === key)).find((group) => group[2].length);
    show(...first);
    return section;
  }

  function renderPoint(point, opinions, tools) {
    const article = node("article", undefined, "review-point");
    const requirement = tools.length === 1 ? point.results[tools[0]].requirement || point.requirement : point.requirement;
    article.append(node("p", point.id, "muted"),
      node("h3", "Cosa doveva spiegare la risposta"), node("p", requirement));
    const cards = node("div", undefined, tools.length === 2 ? "excerpts" : "point-excerpt");
    for (const id of tools) {
      const side = id === state.left ? "left" : "right";
      const result = point.results[id];
      const card = node("div", undefined, `excerpt ${side}-card`);
      const product = id === defaultLeft ? "Vera" : id === defaultRight ? "Codex" : configNames.get(id);
      if (result.requirement && tools.length === 2) {
        card.append(node("h4", "Requisito usato per questo strumento"), node("p", result.requirement));
      }
      card.append(node("h4", `Cosa ha scritto ${product}`));
      if (result.context) {
        card.append(node("blockquote", result.context));
      }
      result.evidence.forEach(({line, paragraph, text}, i) => {
        const disclosure = node("details", undefined, "review-passage");
        const label = i === 0 && !result.context ? "Brano della risposta" : "Altro brano della risposta";
        disclosure.open = i === 0 && !result.context;
        const locator = line ? ` · riga ${line}` : paragraph ? ` · paragrafo ${paragraph}` : "";
        disclosure.append(node("summary", label + locator),
          node("blockquote", text.replace(/\*\*/g, "").replace(/\[([^\[\]\n]+)\]\(https?:\/\/[^\s)]+\)/g, "$1")));
        card.append(disclosure);
      });
      if (result.summary) card.append(node("p", "Sintesi nel registro", "muted"), node("p", result.summary));
      if (!result.context && !result.summary && !result.evidence.length) {
        card.append(node("p", "Il registro non indica un brano della risposta per questo punto.", "muted"));
      }
      if (opinions[id]) {
        const open = button("Apri il parere completo", () => openOpinion(id, opinions[id]), "detail-back");
        open.setAttribute("aria-label", `Apri il parere completo di ${product}`);
        card.append(open);
      }
      const verdict = result.score ? "Perché il valutatore ha dato un punto" : "Perché il valutatore ha dato zero";
      card.append(node("h4", verdict, "review-verdict"), node("p", result.reason));
      if (result.unresolved) card.append(node("p", "Punto da riesaminare.", "muted"));
      cards.append(card);
    }
    article.append(cards);
    return article;
  }

  function openOpinion(id, opinion) {
    const dialog = node("dialog", undefined, "full-opinion");
    dialog.setAttribute("aria-labelledby", "opinion-title");
    const heading = node("h2", `Parere completo · ${configNames.get(id)}`);
    heading.id = "opinion-title";
    const toolbar = node("div", undefined, "opinion-toolbar");
    toolbar.append(heading, button("Chiudi", () => dialog.close(), "detail-back"));
    const body = node("div", undefined, "opinion-body");
    body.innerHTML = opinion;
    dialog.append(toolbar, body);
    dialog.addEventListener("close", () => dialog.remove(), {once: true});
    document.body.append(dialog);
    dialog.showModal();
  }

  function shareCase() {
    const section = node("div", undefined, "link-share");
    const status = node("span");
    status.setAttribute("role", "status");
    const field = node("input");
    field.type = "url";
    field.readOnly = true;
    field.hidden = true;
    field.setAttribute("aria-label", "Link al quesito");
    const copy = button("Copia il link al quesito", async () => {
      const url = comparisonUrl().href;
      try {
        await navigator.clipboard.writeText(url);
        field.hidden = true;
        status.textContent = "Link copiato.";
      } catch {
        field.value = url;
        field.hidden = false;
        field.focus();
        field.select();
        status.textContent = "Copia il link selezionato.";
      }
    });
    section.append(copy, status, field);
    return section;
  }

  const judgmentLabels = {
    pass: "Concorda",
    different: "Conclusione diversa",
    not_established: "Concordanza non accertata"
  };

  function renderOutcome(item) {
    const outcome = outcomes[item.id];
    const section = node("section", undefined, "outcome-detail");
    const context = node("div", undefined, "outcome-reference");
    const question = node("p", outcome.question);
    const reference = node("p", outcome.reference);
    context.append(node("h3", "Domanda centrale"), question,
      node("h3", "Conclusione canonica"), reference);
    section.append(context);

    const columns = node("div", undefined, "excerpts");
    for (const id of [state.left, state.right]) {
      const records = outcome.results[id];
      const result = outcomeLabels[outcomePasses(item.id, id)];
      const column = node("div", undefined, "excerpt");
      column.append(node("h3", configNames.get(id)), node("p", result, "outcome-result"));
      for (const [index, record] of records.entries()) {
        if (index > 0 && record.result === records[0].result &&
            record.evidence === records[0].evidence && record.reason === records[0].reason) continue;
        const check = node("details", undefined, "outcome-check");
        check.open = index === 0 || result === "Esito variabile";
        check.append(node("summary", judgmentLabels[record.result]));
        if (record.evidence) {
          const passage = node("blockquote", record.evidence);
          passage.translate = false;
          check.append(node("p", "Passaggio della risposta", "muted"), passage);
        }
        if (record.reason) {
          const reason = node("p", record.reason);
          check.append(node("p", "Perché questo esito", "muted"), reason);
        }
        column.append(check);
      }
      columns.append(column);
    }
    section.append(columns);
    return section;
  }

  function renderDetail() {
    const item = dataCases.get(state.selected);
    controls.workspace.classList.toggle("has-case", Boolean(item));
    if (!item) {
      const title = node("h2", "Apri un quesito");
      title.id = "detail-title";
      const description = state.measure === "outcome"
        ? "Scegli un quesito per confrontare la conclusione dei due strumenti con quella canonica."
        : "Scegli un quesito dalla lista per vedere i risultati.";
      controls.detail.replaceChildren(title, node("p", description));
      if (showsDifferentPoints()) controls.detail.append(button("Vedi un pareggio con punti diversi",
        () => openCase("E26-B02-09"), "suggestion"));
      return;
    }
    const example = isAstra62Pair(state) ? examples[item.id] : undefined;
    const title = node("h2", item.title, "case-heading");
    title.id = "detail-title";
    controls.detail.replaceChildren(button("← Torna ai quesiti", closeCase, "detail-back"),
      node("p", item.id, "muted"), title);
    if (state.measure === "outcome") {
      controls.detail.append(renderOutcome(item), shareCase());
      return;
    }
    if (example) controls.detail.append(node("p", example.summary));
    if (example?.scoreNote) controls.detail.append(node("p", example.scoreNote));
    const available = [state.left, state.right].filter((id) => pointRegisters[item.id]?.includes(id));
    const review = node("div");
    review.id = "point-review";
    review.tabIndex = -1;
    let panel = node("div");
    review.append(panel);
    const show = (tools, focus = false) => {
      const nextPanel = node("div");
      panel.replaceWith(nextPanel);
      panel = nextPanel;
      loadPointReview(item, panel, tools, focus ? () => {
        review.scrollIntoView({block: "nearest"});
        review.focus({preventScroll: true});
      } : undefined);
    };
    const table = metricsTable(item, available, (id) => show([id], true));
    controls.detail.append(table);
    if (available.length === 2) {
      controls.detail.append(button("Confronta punto per punto", () => show(available, true), "detail-back"));
    } else if (available.length < 2) {
      const missing = [state.left, state.right].filter((id) => !available.includes(id)).map((id) => configNames.get(id));
      controls.detail.append(node("p", `Dettaglio dei singoli punti non disponibile per ${missing.join(" e ")} su questo quesito.`, "muted"));
    }
    controls.detail.append(review);
    if (isAstra62Pair(state)) show(available);
    controls.detail.append(shareCase());
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
    if (state.filter === "different" && !showsDifferentPoints()) state.filter = "all";
    for (const control of controls.measure.children) {
      control.setAttribute("aria-pressed", String(control.dataset.measure === state.measure));
    }
    byId("outcome-note").hidden = state.measure !== "outcome";
    updateSelectors();
    renderTotals();
    renderFilters(scoredCases());
    renderList();
    renderDetail();
  }

  for (const control of controls.measure.children) {
    control.addEventListener("click", () => {
      if (control.dataset.measure === state.measure) return;
      state.measure = control.dataset.measure;
      renderAll();
      updateUrl(true);
    });
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

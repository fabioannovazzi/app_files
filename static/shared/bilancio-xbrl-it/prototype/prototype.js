"use strict";

const STORAGE_KEY = "mparanza-vera-bilancio-public-demo-v1";

const ACTION_LABELS = {
  request_more_documents: "Richiedi documenti",
  mark_unclear: "Segna da chiarire",
  skip: "Rinvia con motivazione",
};

const ACTION_EFFECTS = {
  request_more_documents: "La voce resta aperta fino all'arrivo della nuova evidenza.",
  mark_unclear: "L'incertezza resta esplicita e non genera una conclusione contabile.",
  skip: "La voce resta esclusa dalla revisione corrente con una motivazione tracciata.",
};

const STATUS_LABELS = {
  partial: "Parziale",
  blocked: "Bloccato",
  source_only: "Solo fonte",
  needs_evidence: "Serve evidenza",
  not_run: "Non eseguito",
  unavailable: "Non disponibile",
  available: "Disponibile",
  simulated: "Simulato",
  source_available: "Fonte disponibile",
};

const CASE_DATA = {
  caseId: "pagopa_2024_public_demo",
  entity: "PAGOPA S.P.A.",
  revision: "demo_rev_7",
  workflow: [
    { label: "Fonti", status: "partial", summary: "1 documento pubblico acquisito; fonte contabile di lavoro assente." },
    { label: "Bilancio di verifica", status: "blocked", summary: "Il bilancio di verifica non è stato fornito." },
    { label: "Mappature", status: "blocked", summary: "Nessun conto può essere mappato senza la fonte contabile." },
    { label: "Prospetti", status: "source_only", summary: "Importi mostrati dal PDF pubblicato; non ricalcolati da Vera." },
    { label: "Schede", status: "needs_evidence", summary: "Schede lavori in corso, crediti e debiti da acquisire." },
    { label: "Nota integrativa", status: "source_only", summary: "Testo pubblicato disponibile come fonte; nessuna nuova bozza Vera." },
    { label: "Validazione", status: "not_run", summary: "Non eseguibile su una demo priva del caso canonico." },
    { label: "Approvazione", status: "unavailable", summary: "La demo non approva né deposita il bilancio." },
  ],
  documents: [
    { id: "public_accounts", name: "Bilancio e nota integrativa 2024", kind: "PDF pubblico", version: "20-05-2025", source: "PagoPA S.p.A. · Società Trasparente", status: "available", receipt: "e1e70944…4221b3" },
    { id: "trial_balance", name: "Bilancio di verifica 2024", kind: "CSV o XLSX", version: "—", source: "Gestionale contabile", status: "blocked", receipt: "—" },
    { id: "wip_schedule", name: "Scheda lavori in corso", kind: "XLSX", version: "—", source: "Contabilità analitica", status: "blocked", receipt: "—" },
    { id: "receivables_schedule", name: "Dettaglio crediti verso altri", kind: "XLSX o CSV", version: "—", source: "Partitario e altri crediti", status: "blocked", receipt: "—" },
    { id: "related_debt_schedule", name: "Dettaglio debiti verso correlate", kind: "XLSX o CSV", version: "—", source: "Partitario fornitori e correlate", status: "blocked", receipt: "—" },
  ],
  facts: [
    { label: "Totale attivo", current: 147304328, comparative: 81998490, page: 2 },
    { label: "Patrimonio netto", current: 25657971, comparative: 16628234, page: 3 },
    { label: "Totale debiti", current: 112889263, comparative: 60609329, page: 3 },
    { label: "Valore della produzione", current: 125854215, comparative: 78880803, page: 4 },
    { label: "Utile d'esercizio", current: 9029737, comparative: 7378753, page: 4 },
    { label: "Disponibilità liquide", current: 30313477, comparative: 22495134, page: 2 },
  ],
  reviewItems: [
    {
      id: "review_trial_balance",
      stage: "Fonti",
      severity: "blocker",
      title: "Bilancio di verifica non disponibile",
      summary: "Il PDF pubblicato consente di vedere il risultato finale, ma non sostituisce la popolazione contabile da mappare e riconciliare.",
      requestedDocument: "Bilancio di verifica 2024 con apertura, movimenti Dare/Avere e saldi di chiusura",
      owner: "Studio",
      evidence: ["Il fascicolo contiene il bilancio pubblicato, non il bilancio di verifica.", "Mappatura dei conti e quadrature non sono eseguibili senza la fonte contabile."],
    },
    {
      id: "review_parser_convention",
      stage: "Bilancio di verifica",
      severity: "blocker",
      title: "Convenzione contabile da confermare",
      summary: "La presenza delle scritture di chiusura non può essere dedotta dal PDF finale.",
      requestedDocument: "Conferma del commercialista sulla convenzione del bilancio di verifica e sulle scritture di chiusura",
      owner: "Commercialista",
      evidence: ["Lo stato resta bloccato finché la convenzione non è confermata professionalmente."],
    },
    {
      id: "review_wip",
      stage: "Schede",
      severity: "high",
      title: "Lavori in corso su ordinazione",
      summary: "Il saldo pubblicato passa da 23.842.162 euro a 25.085.875 euro. La variazione è un punto di revisione, non una conclusione.",
      requestedDocument: "Scheda lavori in corso con commesse, costi sostenuti, avanzamento e criteri di valutazione",
      owner: "Amministrazione",
      evidence: ["Rimanenze lavori in corso: 25.085.875 euro nel 2024; 23.842.162 euro nel 2023.", "La scheda analitica non è disponibile nella demo."],
    },
    {
      id: "review_other_receivables",
      stage: "Schede",
      severity: "high",
      title: "Crediti verso altri: dettaglio richiesto",
      summary: "Il saldo pubblicato passa da 9.222.109 euro a 42.435.443 euro. Serve il dettaglio per natura, scadenza e controparte.",
      requestedDocument: "Partitario e scheda crediti verso altri con ageing e riconciliazione al saldo",
      owner: "Amministrazione",
      evidence: ["Crediti verso altri: 42.435.443 euro nel 2024; 9.222.109 euro nel 2023.", "Il confronto identifica una variazione; non ne attribuisce la causa."],
    },
    {
      id: "review_related_debt",
      stage: "Schede",
      severity: "high",
      title: "Debiti verso imprese correlate",
      summary: "Il saldo pubblicato passa da 15.269.999 euro a 45.222.105 euro. Composizione e riconciliazione restano da verificare.",
      requestedDocument: "Dettaglio rapporti con imprese correlate e riconciliazione saldi al 31-12-2024",
      owner: "Amministrazione",
      evidence: ["Debiti verso imprese sottoposte al controllo delle controllanti: 45.222.105 euro nel 2024; 15.269.999 euro nel 2023.", "Il PDF non sostituisce la riconciliazione per controparte."],
    },
    {
      id: "review_internal_work",
      stage: "Nota integrativa",
      severity: "medium",
      title: "Incrementi per lavori interni",
      summary: "La voce pubblicata passa da 223.459 euro a 2.119.861 euro. Occorre collegare criteri dichiarati e costi capitalizzati.",
      requestedDocument: "Scheda costi capitalizzati per progetto con criteri, ore e approvazioni",
      owner: "Amministrazione",
      evidence: ["Incrementi di immobilizzazioni per lavori interni: 2.119.861 euro nel 2024; 223.459 euro nel 2023."],
    },
  ],
  artifacts: [
    { label: "Bilancio pubblicato", kind: "PDF", status: "source_available", verification: "SHA-256 registrato" },
    { label: "Report mappature", kind: "JSON / XLSX", status: "blocked", verification: "Richiede bilancio di verifica" },
    { label: "Report validazione", kind: "JSON / HTML", status: "not_run", verification: "Caso canonico non creato" },
    { label: "XBRL approvato", kind: "XBRL", status: "unavailable", verification: "Nessuna approvazione professionale" },
  ],
};

const state = {
  decisions: new Map(),
  activeReviewId: CASE_DATA.reviewItems[0].id,
  revision: CASE_DATA.revision,
  simulatedUpdate: false,
  dirty: false,
  toastTimer: null,
};

const currency = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

function element(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clear(node) {
  node.replaceChildren();
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  window.clearTimeout(state.toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  state.toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3600);
}

function readStoredState() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const stored = JSON.parse(raw);
    if (stored.case_id !== CASE_DATA.caseId || !Array.isArray(stored.decisions)) return;
    const knownItems = new Set(CASE_DATA.reviewItems.map((item) => item.id));
    stored.decisions.forEach((decision) => {
      if (!knownItems.has(decision.review_item_id)) return;
      if (!Object.hasOwn(ACTION_LABELS, decision.action)) return;
      state.decisions.set(decision.review_item_id, {
        review_item_id: decision.review_item_id,
        action: decision.action,
        note: typeof decision.note === "string" ? decision.note.slice(0, 2000) : "",
      });
    });
    state.simulatedUpdate = stored.prototype_simulation === true;
    state.revision = state.simulatedUpdate ? "demo_rev_8" : CASE_DATA.revision;
  } catch (error) {
    if (!(error instanceof DOMException) && !(error instanceof SyntaxError)) throw error;
  }
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status.replaceAll("_", " ");
}

function setDirty(dirty) {
  state.dirty = dirty;
  const decisionState = document.querySelector("#decision-state");
  const saveStatus = document.querySelector("#save-status");
  if (dirty) {
    decisionState.textContent = "Modifiche da salvare";
    saveStatus.textContent = "Decisioni non salvate";
  } else if (state.decisions.size > 0 || state.simulatedUpdate) {
    decisionState.textContent = `${state.decisions.size} decisioni salvate`;
    saveStatus.textContent = "Demo salvata nel browser";
  } else {
    decisionState.textContent = "Nessuna decisione";
    saveStatus.textContent = "Nessuna decisione salvata";
  }
}

function setPanel(panelName, reviewId = null) {
  document.querySelectorAll("[data-panel-view]").forEach((panel) => {
    const active = panel.dataset.panelView === panelName;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-panel]").forEach((button) => {
    const active = button.dataset.panel === panelName;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (reviewId) {
    state.activeReviewId = reviewId;
    renderReview();
  }
  document.querySelector(".workbench").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderWorkflow() {
  const list = document.querySelector("#workflow-list");
  clear(list);
  CASE_DATA.workflow.forEach((stage, index) => {
    const row = element("li", "workflow-row");
    row.append(
      element("span", "workflow-index", String(index + 1).padStart(2, "0")),
      element("span", "workflow-label", stage.label),
      element("span", `status-badge status-${stage.status}`, statusLabel(stage.status)),
      element("span", "workflow-summary", stage.summary),
    );
    list.append(row);
  });
}

function renderAttention() {
  const list = document.querySelector("#attention-list");
  clear(list);
  CASE_DATA.reviewItems.slice(0, 4).forEach((item) => {
    const button = element("button", "attention-item");
    button.type = "button";
    button.addEventListener("click", () => setPanel("review", item.id));
    const meta = element("span");
    meta.append(element("span", "", item.stage), element("span", "", item.severity === "blocker" ? "Bloccante" : item.owner));
    button.append(meta, element("strong", "", item.title));
    list.append(button);
  });
}

function renderFacts() {
  const grid = document.querySelector("#facts-grid");
  const ledger = document.querySelector("#statement-ledger");
  clear(grid);
  clear(ledger);
  CASE_DATA.facts.forEach((fact) => {
    const change = ((fact.current - fact.comparative) / Math.abs(fact.comparative)) * 100;
    const comparison = element("span", "fact-comparison");
    comparison.append(
      element("span", "", `2023 ${currency.format(fact.comparative)}`),
      element("span", "fact-change", `${change >= 0 ? "+" : ""}${change.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`),
    );
    const card = element("article", "fact-item");
    card.append(element("span", "fact-label", fact.label), element("strong", "fact-value", currency.format(fact.current)), comparison);
    grid.append(card);

    const row = element("div", "statement-row");
    row.append(
      element("span", "statement-label", fact.label),
      element("span", "statement-value", currency.format(fact.current)),
      element("span", "statement-value", currency.format(fact.comparative)),
      element("span", "statement-source", `PDF · p. ${fact.page}`),
    );
    ledger.append(row);
  });
}

function renderDocuments() {
  const body = document.querySelector("#documents-body");
  clear(body);
  CASE_DATA.documents.forEach((documentRecord) => {
    const simulated = state.simulatedUpdate && documentRecord.id === "trial_balance";
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.append(element("span", "document-name", documentRecord.name), element("span", "document-kind", documentRecord.kind));
    const status = simulated ? "simulated" : documentRecord.status;
    const statusCell = document.createElement("td");
    statusCell.append(element("span", `status-badge status-${status}`, statusLabel(status)));
    row.append(
      nameCell,
      element("td", "", simulated ? "simulata · demo_rev_8" : documentRecord.version),
      element("td", "", simulated ? "Interazione dimostrativa · nessun file letto" : documentRecord.source),
      statusCell,
      element("td", "receipt", simulated ? "nessuna ricevuta reale" : documentRecord.receipt),
    );
    body.append(row);
  });
}

function renderArtifacts() {
  const list = document.querySelector("#artifact-list");
  clear(list);
  CASE_DATA.artifacts.forEach((artifact) => {
    const row = element("div", "artifact-row");
    row.append(
      element("span", "artifact-name", artifact.label),
      element("span", "artifact-kind", artifact.kind),
      element("span", `artifact-status status-${artifact.status}`, statusLabel(artifact.status)),
      element("span", "artifact-verification", artifact.verification),
    );
    list.append(row);
  });
}

function updateDecision(item, action) {
  const current = state.decisions.get(item.id);
  state.decisions.set(item.id, {
    review_item_id: item.id,
    action,
    note: current?.note || "",
  });
  setDirty(true);
  renderReview();
}

function renderReviewQueue() {
  const queue = document.querySelector("#review-queue");
  clear(queue);
  CASE_DATA.reviewItems.forEach((item) => {
    const active = item.id === state.activeReviewId;
    const button = element("button", `queue-item severity-${item.severity}${active ? " is-active" : ""}`);
    button.type = "button";
    button.setAttribute("aria-pressed", String(active));
    button.addEventListener("click", () => {
      state.activeReviewId = item.id;
      renderReview();
    });
    const copy = element("span");
    copy.append(element("span", "queue-stage", item.stage), element("span", "queue-title", item.title), element("span", "queue-owner", `Responsabile · ${item.owner}`));
    const decision = state.decisions.get(item.id);
    if (decision) copy.append(element("span", "queue-decision", ACTION_LABELS[decision.action]));
    button.append(element("span", "queue-marker"), copy);
    queue.append(button);
  });
}

function renderReviewDetail() {
  const detail = document.querySelector("#review-detail");
  clear(detail);
  const item = CASE_DATA.reviewItems.find((candidate) => candidate.id === state.activeReviewId);
  if (!item) return;

  const severityLabel = item.severity === "blocker" ? "Bloccante" : item.severity === "high" ? "Priorità alta" : "Priorità media";
  const meta = element("div", "detail-meta");
  meta.append(element("span", `detail-severity severity-${item.severity}`, severityLabel), element("span", "", item.stage), element("span", "", `Responsabile · ${item.owner}`));
  detail.append(meta, element("h4", "", item.title), element("p", "detail-summary", item.summary));

  const evidenceBlock = element("section", "detail-block");
  evidenceBlock.append(element("span", "detail-label", "Fatti osservati"));
  const evidenceList = element("ul", "evidence-list");
  item.evidence.forEach((evidence) => evidenceList.append(element("li", "", evidence)));
  evidenceBlock.append(evidenceList);

  const requestBlock = element("section", "detail-block");
  requestBlock.append(element("span", "detail-label", "Evidenza richiesta"), element("p", "request-copy", item.requestedDocument));

  const decisionBlock = element("section", "detail-block");
  decisionBlock.append(element("span", "detail-label", "Decisione professionale"));
  const options = element("div", "decision-options");
  const current = state.decisions.get(item.id);
  Object.keys(ACTION_LABELS).forEach((action) => {
    const button = element("button", `decision-option${current?.action === action ? " is-selected" : ""}`, ACTION_LABELS[action]);
    button.type = "button";
    button.setAttribute("aria-pressed", String(current?.action === action));
    button.addEventListener("click", () => updateDecision(item, action));
    options.append(button);
  });
  decisionBlock.append(options);
  if (current) {
    const noteLabel = element("label", "decision-note-label", "Nota di revisione");
    const note = element("textarea", "decision-note");
    note.value = current.note;
    note.maxLength = 2000;
    note.placeholder = current.action === "skip" ? "Motivazione necessaria per il rinvio" : "Contesto utile per il seguito";
    note.addEventListener("input", (event) => {
      current.note = event.target.value;
      state.decisions.set(item.id, current);
      setDirty(true);
    });
    noteLabel.append(note);
    decisionBlock.append(noteLabel, element("p", "decision-effect", ACTION_EFFECTS[current.action]));
  } else {
    decisionBlock.append(element("p", "decision-effect", "Seleziona un'azione. La demo non genera una conclusione contabile."));
  }
  detail.append(evidenceBlock, requestBlock, decisionBlock);
}

function renderReview() {
  renderReviewQueue();
  renderReviewDetail();
}

function showRevisionImpact() {
  const impact = document.querySelector("#revision-impact");
  impact.hidden = !state.simulatedUpdate;
  clear(document.querySelector("#impact-list"));
  if (!state.simulatedUpdate) return;
  ["Mappature", "Prospetti", "Schede", "Nota", "Validazione"].forEach((area) => {
    document.querySelector("#impact-list").append(element("li", "", `${area} · da ricalcolare`));
  });
}

function simulateUpdate() {
  if (state.simulatedUpdate) {
    setPanel("overview");
    return;
  }
  state.simulatedUpdate = true;
  state.revision = "demo_rev_8";
  document.querySelector("#revision-label").textContent = state.revision;
  document.querySelector("#simulate-update").textContent = "Aggiornamento simulato";
  renderDocuments();
  showRevisionImpact();
  setDirty(true);
  showToast("Nuova versione simulata: nessun file contabile è stato letto.");
  setPanel("overview");
}

function saveReview() {
  const unexplainedSkip = Array.from(state.decisions.entries()).find(([, decision]) => decision.action === "skip" && !decision.note.trim());
  if (unexplainedSkip) {
    setPanel("review", unexplainedSkip[0]);
    showToast("Aggiungi una motivazione prima di rinviare questa voce.");
    document.querySelector(".decision-note")?.focus();
    return;
  }
  const payload = {
    schema_version: 1,
    case_id: CASE_DATA.caseId,
    revision_id: state.revision,
    status: "public_demo_review",
    saved_at: new Date().toISOString(),
    decisions: Array.from(state.decisions.values()),
    prototype_simulation: state.simulatedUpdate,
    data_posture: {
      public_source_only: true,
      actual_trial_balance_ingested: false,
      sent_to_mparanza: false,
      sent_to_model: false,
    },
  };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
    showToast("Il browser non consente il salvataggio locale. Le scelte restano visibili finché la pagina resta aperta.");
    return;
  }
  setDirty(false);
  showToast("Revisione salvata soltanto in questo browser.");
}

function resetDemo() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
  }
  state.decisions.clear();
  state.activeReviewId = CASE_DATA.reviewItems[0].id;
  state.revision = CASE_DATA.revision;
  state.simulatedUpdate = false;
  document.querySelector("#revision-label").textContent = state.revision;
  document.querySelector("#simulate-update").textContent = "Simula aggiornamento fonte";
  renderDocuments();
  renderReview();
  showRevisionImpact();
  setDirty(false);
  setPanel("overview");
  showToast("Demo azzerata. Nessun dato è stato inviato.");
}

function bindInteractions() {
  document.querySelectorAll("[data-panel]").forEach((button) => button.addEventListener("click", () => setPanel(button.dataset.panel)));
  document.querySelectorAll("[data-jump]").forEach((button) => button.addEventListener("click", () => setPanel(button.dataset.jump)));
  document.querySelector("#simulate-update").addEventListener("click", simulateUpdate);
  document.querySelector("#save-review").addEventListener("click", saveReview);
  document.querySelector("#reset-demo").addEventListener("click", resetDemo);
}

function initialise() {
  readStoredState();
  bindInteractions();
  document.querySelector("#case-name").textContent = CASE_DATA.entity;
  document.querySelector("#source-count").textContent = CASE_DATA.documents.length;
  document.querySelector("#review-count").textContent = CASE_DATA.reviewItems.length;
  document.querySelector("#revision-label").textContent = state.revision;
  if (state.simulatedUpdate) document.querySelector("#simulate-update").textContent = "Aggiornamento simulato";
  renderWorkflow();
  renderAttention();
  renderFacts();
  renderDocuments();
  renderArtifacts();
  renderReview();
  showRevisionImpact();
  setDirty(false);
  document.querySelector(".workbench").dataset.loading = "false";
}

initialise();

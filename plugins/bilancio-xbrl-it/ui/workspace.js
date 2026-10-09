"use strict";
(() => {
  const root = document.getElementById("app");
  const status = document.getElementById("status");
  const pending = new Map();
  let requestId = 0;
  let epoch = 0;
  let host = {};
  let catalogue;
  let snapshot;
  let selectedCase;
  let view = "ISSUES_PANEL";
  let offset = 0;
  let dirty = false;
  let busy = false;
  let submission;
  const tabs = { CASE_DASHBOARD: "Riepilogo", SOURCE_REVIEW: "Documenti", MAPPING_GRID: "Mappature", STATEMENTS: "Prospetti", SCHEDULES: "Tabelle", QUESTIONNAIRE: "Domande", NOTES_EDITOR: "Nota integrativa", ISSUES_PANEL: "Rilievi", PREVIEW: "Anteprima", APPROVAL_EXPORT: "Approvazione e file" };
  const states = { VALIDATION_FAILED: "Controlli da completare", READY_FOR_REVIEW: "Pronto per la revisione", INPUT_REVIEW: "Dati da verificare", ACKNOWLEDGED: "Presa visione salvata", UNREVIEWED: "Da esaminare", OVERRIDDEN: "Deroga registrata", MEDIUM: "Avvertenza", HIGH: "Rilievo significativo", BLOCKER: "Bloccante", INFO: "Informazione", LOW: "Osservazione" };
  // Exact UI localization, not classification or a change to the finding.
  const findingTitles = { "INPUT.PRIOR_XBRL_RECOMMENDED": "Manca il bilancio XBRL dell'esercizio precedente", "FORM.SELECTION_REQUIRED": "La forma di bilancio non è confermata", "MAPPING.COVERAGE": "La mappatura dei conti è incompleta", "STATEMENT.NOT_COMPUTED": "I prospetti non sono ancora calcolati", "MAPPING.TAXONOMY_INDEX_REQUIRED": "Manca l'indice della tassonomia ufficiale", "STATEMENT.STATUTORY_PRESENTATION_REQUIRED": "La copertura dei prospetti obbligatori va verificata", "DISCLOSURE.NEGATIVE_CONFIRMATIONS": "Mancano conferme annuali", "DISCLOSURE.RULE_PACK_REQUIRED": "Le regole informative non sono ancora attivate", "REVIEW.PREVIEW_REQUIRED": "Manca l'anteprima da rivedere" };
  const findingTitle = issue => findingTitles[issue.rule_id] || issue.message;
  const labels = { case_id: "Fascicolo", revision_id: "Revisione", state: "Stato", source_ref: "Riferimento", document_id: "Documento", sheet: "Foglio", row: "Riga", column: "Colonna", cell: "Cella", raw_value: "Valore fonte", value: "Valore", content_sha256: "SHA-256", file_name: "Nome file", severity: "Livello", rule_id: "Controllo", reason: "Motivazione", action: "Decisione", reviewed_by: "Revisore", review_status: "Revisione", status: "Stato", message: "Esito", account_code: "Codice conto", account_description: "Descrizione conto", closing_signed: "Saldo", prior_closing_signed: "Saldo precedente", question_id: "Domanda", text: "Testo", current_value: "Esercizio corrente", prior_value: "Esercizio precedente", source_refs: "Fonti", decision: "Decisione", section_id: "Sezione", title: "Titolo" };
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
  const button = (text, action, cls = "") => { const node = el("button", text, cls); node.type = "button"; node.addEventListener("click", () => run(action)); return node; };
  const say = (text, error = false) => { status.textContent = text; status.className = error ? "error" : ""; };
  function request(method, params) {
    const id = ++requestId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(method === "ui/message"
          ? "La chat non ha confermato la ricezione. Controlla le chat aperte prima di inviare di nuovo. La decisione nel fascicolo non è stata modificata."
          : "Il servizio non risponde. Riprova: la stessa richiesta non duplica il salvataggio."));
      }, method === "ui/message" ? 300000 : 30000);
      pending.set(id, { resolve, reject, timer });
      window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
    });
  }
  async function call(name, args = {}) {
    const result = await request("tools/call", { name, arguments: args });
    if (result.isError) throw new Error(result.content?.find(item => item.type === "text")?.text || "Operazione non riuscita");
    return result;
  }
  async function run(action) {
    if (busy) return;
    busy = true; root.setAttribute("aria-busy", "true");
    try { await action(); } catch (error) { say(error.message, true); }
    finally { busy = false; root.setAttribute("aria-busy", "false"); }
  }
  function leaveDraft() {
    if (dirty) throw new Error("La nota contiene modifiche non salvate. Salvale o scegli «Scarta modifiche».");
  }
  async function loadCatalogue(page = 0) {
    leaveDraft(); const generation = ++epoch;
    say("Caricamento degli incarichi…");
    const result = await call("xbrl_workspace_open", { offset: page });
    if (generation !== epoch) return;
    catalogue = result._meta.workspace; selectedCase = null; snapshot = null; submission = null;
    renderCatalogue(); say("Scegli un incarico per aprire il suo fascicolo.");
  }
  async function openCase(caseId, nextView = "ISSUES_PANEL", page = 0, issueId, sourceRef) {
    leaveDraft(); const generation = ++epoch;
    say("Caricamento del fascicolo…");
    const args = { case_id: caseId, view: nextView, offset: page };
    if (issueId) { args.issue_id = issueId; args.revision_id = snapshot.revision_id; }
    if (sourceRef) args.source_ref = sourceRef;
    const result = await call("xbrl_workspace_view", args);
    if (generation !== epoch) return;
    snapshot = result._meta.workspace; selectedCase = caseId; view = nextView; offset = page; submission = null;
    renderCase(); say("Dati letti dal fascicolo · " + snapshot.revision_id);
  }
  function shell() {
    root.replaceChildren(); const wrapper = el("div", undefined, "shell");
    const rail = el("aside", undefined, "rail"); rail.append(el("p", "Studio Archive", "eyebrow"), el("h2", "Il lavoro dello studio"));
    const nav = el("nav"); nav.setAttribute("aria-label", "Sezioni del fascicolo"); rail.append(nav);
    const main = el("main", undefined, "main"); wrapper.append(rail, main); root.append(wrapper);
    return { nav, main };
  }
  function renderCatalogue() {
    const { nav, main } = shell(); nav.append(button("Clienti e incarichi", () => loadCatalogue()), button("Più recenti in questa pagina", async () => { catalogue.cases.sort((a,b) => b.created_at.localeCompare(a.created_at)); renderCatalogue(); }));
    main.append(el("p", "Bilancio OIC", "eyebrow"), el("h1", "Clienti e incarichi"), el("p", "Riprendi un fascicolo già collegato a Studio Archive.", "sub"));
    const search = el("label", undefined, "search"); search.append(el("span", "Cerca in questa pagina")); const input = el("input"); input.type = "search"; search.append(input); main.append(search);
    const list = el("div", undefined, "workspace-list"); main.append(list);
    function rows() {
      list.replaceChildren();
      const cases = catalogue.cases.filter(item => `${item.legal_name} ${item.label} ${item.period.end}`.toLowerCase().includes(input.value.toLowerCase()));
      for (const item of cases) {
        const row = el("section", undefined, "case-row"); const text = el("div"); text.append(el("h2", item.legal_name), el("p", `${item.label} · al ${item.period.end}`), el("p", `${states[item.state] || item.state} · ${item.revision_id}`));
        row.append(text, button("Apri fascicolo →", () => openCase(item.case_id))); list.append(row);
      }
      if (!cases.length) list.append(el("p", "Nessun fascicolo disponibile in questa pagina. I collegamenti a clienti e incarichi sono configurati dal responsabile dello studio.", "empty"));
    }
    input.addEventListener("input", rows); rows();
    pageControls(main, catalogue.offset, catalogue.total, catalogue.has_more, page => loadCatalogue(page));
  }
  function pageControls(parent, start, total, more, action) {
    const node = el("div", undefined, "pagination");
    const prev = button("Precedenti", () => action(Math.max(0,start-30))); prev.disabled = start === 0;
    const next = button("Successivi", () => action(start+30)); next.disabled = !more;
    node.append(prev, el("span", total ? `${start+1}–${Math.min(start+30,total)} di ${total}` : "0 elementi"), next); parent.append(node);
  }
  function fields(value, depth = 0) {
    const node = el("dl");
    for (const [key, item] of Object.entries(value || {})) {
      if (item === null || item === undefined || key === "model_context" || key === "review_ticket") continue;
      node.append(el("dt", labels[key] || key.replaceAll("_", " ")));
      const dd = el("dd");
      if (typeof item === "object") {
        const detail = el("details"); detail.append(el("summary", Array.isArray(item) ? `${item.length} elementi` : "Dettagli"));
        if (depth < 3) {
          if (Array.isArray(item)) for (const row of item.slice(0,30)) detail.append(typeof row === "object" ? fields(row, depth+1) : el("p", String(row)));
          else detail.append(fields(item, depth+1));
        } else detail.append(el("p", "Apri la vista specifica per esaminare questi dati."));
        dd.append(detail);
      } else dd.textContent = String(item);
      node.append(dd);
    }
    return node;
  }
  function renderCase() {
    const { nav, main } = shell();
    for (const [key,label] of Object.entries(tabs)) { const b = button(label, () => openCase(selectedCase,key)); if (key === view) b.setAttribute("aria-current", "page"); nav.append(b); }
    nav.append(button("← Clienti e incarichi", () => loadCatalogue(), "case-link"));
    const header = el("div", undefined, "case-head"); header.append(el("p", snapshot.archive.label, "eyebrow"), el("h1", snapshot.legal_name), el("p", `Esercizio ${snapshot.period.start} — ${snapshot.period.end}`, "sub"));
    const context = el("div", undefined, "context"); context.append(el("span", states[snapshot.dashboard.state] || snapshot.dashboard.state), el("span", snapshot.revision_id), el("span", snapshot.case_id)); header.append(context); main.append(header);
    if (!snapshot.validation_current) main.append(el("p", "La validazione non è aggiornata a questa revisione. Le decisioni salvate restano nel fascicolo; esegui nuovamente i controlli prima di proseguire.", "notice"));
    if (view === "ISSUES_PANEL") renderIssues(main);
    else if (view === "CASE_DASHBOARD") {
      main.append(el("h2", "Stato del fascicolo"), fields(snapshot.dashboard));
    } else {
      main.append(el("h2", tabs[view]));
      const review = snapshot.review;
      const collections = Object.entries(review).filter(([,value]) => value && typeof value === "object" && value.page && value.items);
      if (!collections.length) main.append(fields(Object.fromEntries(Object.entries(review).filter(([key]) => !["view", "case_id", "revision_id", "state"].includes(key)))));
      for (const [key,collection] of collections) {
        main.append(el("h3", labels[key] || key.replaceAll("_", " ")));
        for (const row of collection.items) { const article=el("section", undefined,"record"); article.append(fields(row)); main.append(article); }
        if (!collection.items.length) main.append(el("p", "Non sono presenti elementi in questa vista.", "empty"));
        pageControls(main, collection.page.offset, collection.page.total, collection.page.has_more, page => openCase(selectedCase,view,page));
      }
      main.append(el("p", "Vista di consultazione. Le modifiche e le approvazioni restano disponibili tramite le operazioni del fascicolo in conversazione.", "caption"));
    }
  }
  function renderIssues(main) {
    const issues = snapshot.review.issues; main.append(el("h2", "Rilievi da esaminare"));
    const split = el("div", undefined, "split"); const list = el("div"); const detail = el("section", undefined, "detail"); detail.setAttribute("aria-label", "Rilievo selezionato"); split.append(list,detail); main.append(split);
    for (const issue of issues.items) {
      const b = button("", () => openCase(selectedCase,view,offset,issue.issue_id), "finding"); b.setAttribute("aria-pressed", String(snapshot.selection?.issue.issue_id === issue.issue_id));
      b.append(el("span", states[issue.severity] || issue.severity, `severity ${issue.severity === "BLOCKER" ? "blocker" : "info"}`), el("strong", findingTitle(issue)), el("small", states[issue.review_status] || "Da esaminare")); list.append(b);
    }
    if (!issues.items.length) list.append(el("p", "Non ci sono rilievi nella validazione corrente. Se il fascicolo è stato modificato, esegui nuovamente la validazione prima della revisione.", "empty"));
    pageControls(list, issues.page.offset, issues.page.total, issues.page.has_more, page => openCase(selectedCase,view,page));
    if (!snapshot.selection) { detail.append(el("p", "Seleziona un rilievo per leggerne le fonti e registrare la revisione.", "empty")); return; }
    const selected = snapshot.selection; const issue = selected.issue;
    detail.append(el("p", issue.rule_id, "eyebrow"), el("h2", findingTitle(issue)));
    const original = el("details"); original.append(el("summary", "Esito originale del controllo"), el("p", issue.message)); detail.append(original, el("h3", "Evidenza disponibile"));
    if (selected.evidence.anchors.length) { for (const doc of selected.evidence.documents) detail.append(fields(doc)); for (const anchor of selected.evidence.anchors) detail.append(fields(anchor)); }
    else detail.append(el("p", "Questo controllo non contiene un collegamento diretto a una cella o pagina. Puoi consultare i documenti del fascicolo; Vera riceverà il rilievo e questa limitazione.", "notice"));
    const sourcePicker = el("div");
    async function chooseSource(page = 0) {
      say("Caricamento delle celle sorgente…");
      const result = await call("xbrl_workspace_view", { case_id: selectedCase, revision_id: snapshot.revision_id, view: "SOURCE_REVIEW", offset: page });
      const sources = result._meta.workspace.review.anchors;
      sourcePicker.replaceChildren(el("p", "Scegli una cella da discutere. Il collegamento è una tua scelta di revisione, non una conclusione automatica.", "caption"));
      for (const anchor of sources.items) {
        sourcePicker.append(button(`${anchor.sheet} · riga ${anchor.row}, ${anchor.column}: ${anchor.raw_value}`, () => openCase(selectedCase,view,offset,issue.issue_id,anchor.source_ref), "finding"));
      }
      pageControls(sourcePicker, sources.page.offset, sources.page.total, sources.page.has_more, chooseSource);
      say("Scegli una cella sorgente da esaminare.");
    }
    detail.append(button("Consulta una cella sorgente", () => chooseSource()), sourcePicker);
    if (selected.source_ref) detail.append(el("p", `Evidenza scelta da te: ${selected.source_ref}`, "caption"));
    const canDiscuss = !!host.hostCapabilities?.message?.text && !!host.hostCapabilities?.experimental?.["openai/message"];
    const explain = button("Discuti in una nuova chat", explainSelection); explain.disabled = !canDiscuss; detail.append(explain);
    detail.append(el("p", canDiscuss
      ? "La richiesta contiene i riferimenti della selezione. Vera li usa per leggere soltanto questo rilievo e le sue fonti. Una spiegazione non salva decisioni."
      : "La chat non è disponibile in questa anteprima. Puoi consultare le fonti e salvare la revisione; per discutere il rilievo serve il pannello Vera collegato alla chat.", "caption"));
    detail.append(el("h3", "La tua decisione"));
    const saved = snapshot.review.review_decisions.filter(item => item.issue_id === issue.issue_id);
    if (saved.length) detail.append(fields(saved[saved.length-1]));
    if (!snapshot.validation_current) { detail.append(el("p", "Rivalida il fascicolo per registrare una nuova decisione.", "notice")); return; }
    if (issue.severity === "BLOCKER" || !issue.override_allowed) { detail.append(el("p", "Il controllo è bloccante: correggi i dati o completa le evidenze. Non può essere superato da questa interfaccia.", "notice")); return; }
    const action = issue.severity === "HIGH" ? "OVERRIDDEN" : "ACKNOWLEDGED";
    detail.append(el("p", action === "OVERRIDDEN" ? "Deroga professionale motivata" : "Presa visione con nota di revisione", "sub"));
    const label = el("label", "Nota del revisore"); const note = el("textarea"); note.id = "review-note"; label.htmlFor = note.id; note.maxLength = 4000; note.addEventListener("input", () => { dirty = !!note.value; submission = null; }); detail.append(label,note);
    const checkLabel = el("label", undefined, "check"); const check = el("input"); check.type = "checkbox"; checkLabel.append(check, el("span", "Ho verificato il rilievo e le evidenze disponibili. Confermo questa decisione.")); detail.append(checkLabel);
    const actions = el("div", undefined, "actions");
    actions.append(button("Salva decisione", async () => {
      if (!check.checked) throw new Error("Conferma la revisione prima di salvare.");
      if (!note.value.trim()) throw new Error("Scrivi una nota di revisione.");
      if (!submission) submission = { case_id: selectedCase, revision_id: snapshot.revision_id, issue_id: issue.issue_id, action, reason: note.value.trim(), human_reviewed: true, review_ticket: snapshot.review_ticket, idempotency_key: crypto.randomUUID() };
      say("Salvataggio della decisione…");
      const result = await call("xbrl_workspace_review_issue", submission);
      dirty = false; await openCase(selectedCase);
      say(`Decisione salvata · ${result.structuredContent.revision_id}. Il fascicolo va rivalidato dopo la modifica.`);
    }, "primary"), button("Scarta modifiche", async () => { note.value = ""; check.checked = false; dirty = false; submission = null; say("Modifiche non salvate scartate."); })); detail.append(actions);
    detail.append(el("p", "Questa decisione non approva il bilancio. Autore, motivazione e revisione sono conservati nel fascicolo.", "caption"));
  }
  async function explainSelection() {
    // A panel cannot prove that the existing chat contains no other client's
    // history. This private pilot always requests a fresh conversation.
    if (!host.hostCapabilities?.message?.text) throw new Error("Questo host non consente l'invio alla conversazione. Chiedi a Vera di aprire il fascicolo in chat.");
    if (!host.hostCapabilities?.experimental?.["openai/message"]) throw new Error("Questo host non consente al pannello di aprire una nuova conversazione. La spiegazione non è stata inviata.");
    say("Verifica della revisione e delle fonti selezionate…");
    const result = await call("xbrl_workspace_view", { case_id: selectedCase, revision_id: snapshot.revision_id, issue_id: snapshot.selection.issue.issue_id, ...(snapshot.selection.source_ref ? { source_ref: snapshot.selection.source_ref } : {}) });
    const current = result._meta.workspace;
    say("Conferma l'invio nella finestra della chat, oppure scegli Cancel per annullare.");
    const sent = await request("ui/message", buildExplanationMessage(current, findingTitle(current.selection.issue)));
    if (sent?.isError) throw new Error("Invio annullato o non completato. Puoi riprovare dal rilievo.");
    say("Rilievo inviato in una nuova chat. La decisione resta da rivedere e salvare.");
  }
  document.getElementById("refresh").addEventListener("click", () => run(() => selectedCase ? openCase(selectedCase,view,offset) : loadCatalogue(catalogue?.offset || 0)));
  window.addEventListener("message", event => {
    if (event.source !== window.parent || event.data?.jsonrpc !== "2.0") return;
    const message = event.data;
    if (pending.has(message.id)) { const p=pending.get(message.id); pending.delete(message.id); clearTimeout(p.timer); message.error ? p.reject(new Error(message.error.message)) : p.resolve(message.result); return; }
    if (message.method === "ui/notifications/tool-result" && !catalogue && message.params?._meta?.workspace) {
      const payload = message.params._meta.workspace;
      if (payload.error) { say(payload.error,true); root.setAttribute("aria-busy","false"); return; }
      if (payload.cases) { catalogue=payload; renderCatalogue(); say("Scegli un incarico per aprire il suo fascicolo."); root.setAttribute("aria-busy","false"); }
    }
    if (message.method === "ui/notifications/host-context-changed") host.hostContext = { ...host.hostContext, ...message.params };
    if (message.method === "ui/resource-teardown") {
      window.parent.postMessage({ jsonrpc:"2.0", id:message.id, result:{} },"*");
    }
  });
  async function init() {
    say("Connessione al fascicolo…");
    host = await request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Vera Bilancio workspace", version: "1.0.0" }, appCapabilities: { availableDisplayModes: ["inline","fullscreen"] } });
    document.getElementById("refresh").disabled = false;
    window.parent.postMessage({ jsonrpc:"2.0", method:"ui/notifications/initialized" },"*");
    // Entrypoints deliver an initial result; do not fetch twice on mount.
    say("Connessione pronta. Caricamento degli incarichi…");
  }
  run(init);
})();

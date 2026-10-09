"use strict";

// The host confirmation displays all text blocks, even assistant-only ones.
// Send readable references; the new chat retrieves the exact bounded evidence
// through xbrl_workspace_explain, which enforces authorization and revision.
function buildExplanationMessage(snapshot, title) {
  const selection = snapshot.selection;
  const reference = `Fascicolo: ${snapshot.case_id} · rilievo: ${selection.issue.issue_id} · revisione: ${snapshot.revision_id}.`;
  const source = selection.source_ref
    ? `Fonte scelta: ${selection.source_ref}.`
    : "Nessuna cella sorgente aggiunta alla selezione.";
  const prompt = `Spiega il rilievo «${title}» del bilancio al ${snapshot.period.end}.\n\n`
    + `${reference}\n${source}\n\n`
    + "Prima di rispondere, recupera con Vera questo rilievo e le sole fonti selezionate. "
    + "Se la revisione non è più disponibile, chiedimi di riaprire il rilievo. "
    + "Indica cosa manca e quali documenti o verifiche servono. Non salvare decisioni.";
  return {
    role: "user",
    content: [{ type: "text", text: prompt }],
    _meta: { "openai/message": { target: "new" } },
  };
}

if (typeof module !== "undefined") module.exports = { buildExplanationMessage };

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/research`;
const currentLang = window.appLanguage || "en";
const appCopy = window.appCopy || {};
const languageCode = String(currentLang || "")
  .trim()
  .toLowerCase()
  .split("-")[0];
const isItalian = languageCode === "it";

const FALLBACK_COPY_BY_PATH = {
  page_help: {
    en: "Review the answer by extracting a small set of key claims, checking the cited sources, and deciding whether each claim is supported and logically sound.",
    it: "Esamina la risposta estraendo un piccolo insieme di affermazioni chiave, controllando le fonti citate e valutando se ogni affermazione sia supportata e logicamente solida.",
  },
  "panels.input.title": {
    en: "Paste or upload Deep Research output",
    it: "Incolla o carica l'output di Deep Research",
  },
  "panels.input.subtitle": {
    en: "Paste the full response or upload the PDF exported from Deep Research.",
    it: "Incolla la risposta completa oppure carica il PDF esportato da Deep Research.",
  },
  "panels.results.title": {
    en: "Verification results",
    it: "Risultati della verifica",
  },
  "panels.results.subtitle": {
    en: "Review flagged claims, correction prompt, and final notes.",
    it: "Esamina le affermazioni segnalate, il prompt di correzione e le note finali.",
  },
  "panels.coherence.title": {
    en: "Coherence summary",
    it: "Sintesi di coerenza",
  },
  "buttons.choose_file": {
    en: "Select Deep Research file",
    it: "Seleziona file Deep Research",
  },
  "buttons.run_validation": {
    en: "Run verification",
    it: "Avvia verifica",
  },
  "buttons.confirm_edits": {
    en: "Confirm selections",
    it: "Conferma selezioni",
  },
  "buttons.generate_validated": {
    en: "Generate validated document",
    it: "Genera documento validato",
  },
  "buttons.download_docx": {
    en: "Download validated docx",
    it: "Scarica docx validato",
  },
  "buttons.locate_claim_source": {
    en: "Find in original text",
    it: "Trova nel testo originale",
  },
  "buttons.clear_located_passage": {
    en: "Clear highlight",
    it: "Rimuovi evidenziazione",
  },
  "placeholders.research_input": {
    en: "Paste the research text including links...",
    it: "Incolla il testo della ricerca, inclusi i link...",
  },
  "messages.upload_hint": {
    en: "Upload the PDF or Markdown export to pre-fill the text area.",
    it: "Carica il PDF o l'export Markdown per precompilare l'area di testo.",
  },
  "messages.decisions_hint": {
    en: "Confirm each issue to control what goes into the correction prompt and merged document.",
    it: "Conferma ogni problema per controllare cosa entra nel prompt di correzione e nel documento unificato.",
  },
  "messages.paste_first": {
    en: "Please paste the research text first.",
    it: "Incolla prima il testo della ricerca.",
  },
  "messages.running_verification": {
    en: "Running verification...",
    it: "Verifica in corso...",
  },
  "messages.completed_with_findings": {
    en: "Verification completed.",
    it: "Verifica completata.",
  },
  "messages.no_findings": {
    en: "No issues detected.",
    it: "Nessun problema rilevato.",
  },
  "messages.manual_fix_required": {
    en: "No suggested fix available - edit or ignore this issue.",
    it: "Nessuna correzione suggerita: modifica o ignora questo problema.",
  },
  "messages.claim_source_found": {
    en: "Passage highlighted in the original text.",
    it: "Passaggio evidenziato nel testo originale.",
  },
  "messages.claim_source_brought_into_view": {
    en: "Passage brought into view below and highlighted in the original text.",
    it: "Il passaggio e stato portato in vista qui sotto ed evidenziato nel testo originale.",
  },
  "messages.claim_source_not_found": {
    en: "Passage not found in the original text.",
    it: "Passaggio non trovato nel testo originale.",
  },
  "messages.selection_missing": {
    en: "Select an action for every issue.",
    it: "Seleziona un'azione per ogni problema.",
  },
  "messages.edit_required": {
    en: "Provide replacement text for edited issues.",
    it: "Inserisci il testo sostitutivo per i problemi modificati.",
  },
  "messages.no_claims": {
    en: "No claims to confirm yet.",
    it: "Nessuna affermazione da confermare.",
  },
  "messages.session_missing": {
    en: "Start by running verification.",
    it: "Avvia prima la verifica.",
  },
  "messages.saving_decisions": {
    en: "Saving your selections...",
    it: "Salvataggio selezioni in corso...",
  },
  "messages.decisions_saved": {
    en: "Selections saved. You can now download the validated document.",
    it: "Selezioni salvate. Ora puoi scaricare il documento validato.",
  },
  "messages.download_paste_first": {
    en: "Paste the research text before downloading.",
    it: "Incolla il testo della ricerca prima di scaricare.",
  },
  "messages.download_after_confirm": {
    en: "Confirm your issue selections before downloading.",
    it: "Conferma le selezioni dei problemi prima di scaricare.",
  },
  "messages.download_started": {
    en: "Downloading validated document...",
    it: "Download del documento validato...",
  },
  "messages.verify_failed": {
    en: "Verification failed.",
    it: "Verifica non riuscita.",
  },
  "messages.download_failed": {
    en: "Download failed.",
    it: "Download non riuscito.",
  },
  "messages.uploading_file": {
    en: "Uploading {name}...",
    it: "Caricamento di {name}...",
  },
  "messages.upload_success": {
    en: "Loaded {name}.",
    it: "{name} caricato.",
  },
  "messages.upload_success_status": {
    en: "File uploaded successfully.",
    it: "File caricato correttamente.",
  },
  "messages.upload_failed": {
    en: "Unable to read file.",
    it: "Impossibile leggere il file.",
  },
  "labels.claim_number": {
    en: "Claim #{index}",
    it: "Affermazione n. {index}",
  },
  "labels.claims_count": {
    en: "Claims reviewed: {count}",
    it: "Affermazioni esaminate: {count}",
  },
  "labels.flagged_issues_count": {
    en: "Issues flagged: {count}",
    it: "Problemi rilevati: {count}",
  },
  "labels.issue_count": {
    en: "Issues: {count}",
    it: "Problemi: {count}",
  },
  "labels.references_label": {
    en: "Supporting links",
    it: "Fonti di supporto",
  },
  "labels.no_claims": {
    en: "No claims were flagged.",
    it: "Nessuna affermazione è stata segnalata.",
  },
  "labels.issue_default": {
    en: "Issue",
    it: "Problema",
  },
  "labels.fix_prefix": {
    en: "Fix:",
    it: "Correzione:",
  },
  "labels.importance_level": {
    en: "Importance {level}/5",
    it: "Importanza {level}/5",
  },
  "labels.why_flagged": {
    en: "Why flagged",
    it: "Perché segnalato",
  },
  "labels.edit_placeholder": {
    en: "Provide replacement text...",
    it: "Inserisci il testo sostitutivo...",
  },
  "labels.claim_source_quote": {
    en: "Source passage",
    it: "Passaggio nel testo",
  },
  "labels.accept_issue": {
    en: "Accept fix",
    it: "Accetta correzione",
  },
  "labels.ignore_issue": {
    en: "Ignore",
    it: "Ignora",
  },
  "labels.edit_issue": {
    en: "Edit text",
    it: "Modifica testo",
  },
  "labels.claim_no_issues": {
    en: "No issues found.",
    it: "Nessun problema rilevato.",
  },
  "labels.risk_factor_templates.issue": {
    en: "Issue: {value}",
    it: "Problema: {value}",
  },
  "labels.risk_factor_templates.materiality": {
    en: "Materiality: {value}",
    it: "Materialità: {value}",
  },
  "labels.review_method": {
    en: "Review method",
    it: "Metodo di verifica",
  },
  "labels.review_stage.claims": {
    en: "Key claims extracted",
    it: "Affermazioni chiave estratte",
  },
  "labels.review_stage.sources": {
    en: "Source existence checked",
    it: "Esistenza della fonte verificata",
  },
  "labels.review_stage.support": {
    en: "Source support compared",
    it: "Coerenza con la fonte confrontata",
  },
  "labels.review_stage.logic": {
    en: "Logic reviewed",
    it: "Logica esaminata",
  },
  "labels.active_claim": {
    en: "Active claim",
    it: "Affermazione attiva",
  },
  "labels.source_dossier": {
    en: "Source dossier",
    it: "Dossier della fonte",
  },
  "labels.original_text": {
    en: "Original research text",
    it: "Testo originale della ricerca",
  },
  "labels.located_passage": {
    en: "Located passage",
    it: "Passaggio individuato",
  },
  "labels.located_passage_note": {
    en: "The matching fragment is surfaced below so you do not need to hunt through the full text area.",
    it: "Il frammento corrispondente e mostrato qui sotto, cosi non devi cercarlo in tutta l'area di testo.",
  },
  "labels.located_passage_range": {
    en: "Lines {start}-{end} in the original text",
    it: "Righe {start}-{end} nel testo originale",
  },
  "labels.source_quote_missing": {
    en: "No pinpointed passage was returned for this claim. Review the original text and links directly.",
    it: "Per questa affermazione non è stato restituito un passaggio preciso. Controlla direttamente il testo originale e i link.",
  },
  "labels.claim_index": {
    en: "Claim docket",
    it: "Indice delle affermazioni",
  },
  "labels.claim_index_hint": {
    en: "Work one claim at a time while keeping the full review set visible.",
    it: "Lavora su un'affermazione alla volta mantenendo visibile l'intero set di verifica.",
  },
  "labels.claim_filter.all": {
    en: "All",
    it: "Tutte",
  },
  "labels.claim_filter.attention": {
    en: "Needs review",
    it: "Da rivedere",
  },
  "labels.claim_filter.clear": {
    en: "Clear",
    it: "Pulite",
  },
  "labels.claim_status.attention": {
    en: "Needs review",
    it: "Da rivedere",
  },
  "labels.claim_status.clear": {
    en: "Clear",
    it: "Pulita",
  },
  "labels.claim_status.ready": {
    en: "Ready",
    it: "Pronto",
  },
  "labels.claim_status.pending": {
    en: "Pending",
    it: "In attesa",
  },
  "labels.summary.claims_extracted": {
    en: "Claims extracted",
    it: "Affermazioni estratte",
  },
  "labels.summary.claims_attention": {
    en: "Claims needing review",
    it: "Affermazioni da rivedere",
  },
  "labels.summary.issues_flagged": {
    en: "Issues flagged",
    it: "Problemi rilevati",
  },
  "labels.summary.doc_ready": {
    en: "Validated doc",
    it: "Documento validato",
  },
  "labels.issue_status.incorrect": {
    en: "Incorrect",
    it: "Non corretto",
  },
  "labels.issue_status.review": {
    en: "Needs review",
    it: "Da rivedere",
  },
  "labels.issue_status.caution": {
    en: "Caution",
    it: "Attenzione",
  },
  "labels.evidence_gate": {
    en: "Deterministic source gate",
    it: "Controllo deterministico della fonte",
  },
  "labels.evidence_gate_note": {
    en: "This gate checks source integrity first. Semantic support and reasoning are reviewed separately below.",
    it: "Questo controllo verifica prima l'integrità della fonte. Supporto semantico e ragionamento vengono esaminati separatamente qui sotto.",
  },
  "labels.evidence_gate_checked_url": {
    en: "Checked source",
    it: "Fonte verificata",
  },
  "labels.evidence_gate_excerpt": {
    en: "Matched source excerpt",
    it: "Estratto della fonte trovato",
  },
  "labels.evidence_gate_status.pass": {
    en: "Passed",
    it: "Superato",
  },
  "labels.evidence_gate_status.warning": {
    en: "Limited",
    it: "Parziale",
  },
  "labels.evidence_gate_status.fail": {
    en: "Failed",
    it: "Fallito",
  },
  "labels.evidence_gate_status.na": {
    en: "Not available",
    it: "Non disponibile",
  },
  "labels.evidence_gate_step.source_listed": {
    en: "Source listed",
    it: "Fonte indicata",
  },
  "labels.evidence_gate_step.source_retrieved": {
    en: "Source retrieved",
    it: "Fonte recuperata",
  },
  "labels.evidence_gate_step.source_parsed": {
    en: "Source parsed",
    it: "Fonte analizzata",
  },
  "labels.evidence_gate_step.source_quote_matched": {
    en: "Source passage matched",
    it: "Passaggio della fonte trovato",
  },
  "labels.support_review": {
    en: "Semantic support review",
    it: "Verifica semantica del supporto",
  },
  "labels.support_review_note": {
    en: "This review asks whether the source supports the actual claim, not just whether the link exists.",
    it: "Questa verifica valuta se la fonte supporta davvero l'affermazione, non solo se il link esiste.",
  },
  "labels.support_review_checked_url": {
    en: "Source reviewed",
    it: "Fonte esaminata",
  },
  "labels.support_review_passage": {
    en: "Supporting passage",
    it: "Passaggio di supporto",
  },
  "labels.support_review_scope": {
    en: "Support scope",
    it: "Ambito del supporto",
  },
  "labels.support_review_verdict.supported": {
    en: "Supported",
    it: "Supportata",
  },
  "labels.support_review_verdict.partially_supported": {
    en: "Partially supported",
    it: "Parzialmente supportata",
  },
  "labels.support_review_verdict.not_supported": {
    en: "Not supported",
    it: "Non supportata",
  },
  "labels.support_review_verdict.contradicted": {
    en: "Contradicted",
    it: "Contraddetta",
  },
  "labels.support_review_verdict.na": {
    en: "Not reviewed",
    it: "Non verificata",
  },
  "labels.support_review_scope.same_conclusion": {
    en: "Same conclusion",
    it: "Stessa conclusione",
  },
  "labels.support_review_scope.same_fact": {
    en: "Same fact only",
    it: "Solo stesso fatto",
  },
  "labels.support_review_scope.related_context": {
    en: "Related context only",
    it: "Solo contesto collegato",
  },
  "labels.support_review_scope.unclear": {
    en: "Unclear",
    it: "Non chiaro",
  },
  "labels.reasoning_review": {
    en: "Reasoning review",
    it: "Verifica del ragionamento",
  },
  "labels.reasoning_review_note": {
    en: "This review checks the claim's internal logic and, when relevant, whether the linked claims justify the final conclusion.",
    it: "Questa verifica controlla la logica interna dell'affermazione e, quando rilevante, se le affermazioni collegate giustificano la conclusione finale.",
  },
  "labels.reasoning_logic": {
    en: "Internal logic",
    it: "Logica interna",
  },
  "labels.reasoning_logic_verdict.coherent": {
    en: "Coherent",
    it: "Coerente",
  },
  "labels.reasoning_logic_verdict.questionable": {
    en: "Questionable",
    it: "Da rivedere",
  },
  "labels.reasoning_logic_verdict.na": {
    en: "Not reviewed",
    it: "Non verificata",
  },
  "labels.conclusion_review": {
    en: "Conclusion support",
    it: "Supporto della conclusione",
  },
  "labels.conclusion_review_conclusion_id": {
    en: "Conclusion ID",
    it: "ID conclusione",
  },
  "labels.conclusion_review_linked_claims": {
    en: "Linked claims reviewed",
    it: "Affermazioni collegate esaminate",
  },
  "labels.conclusion_review_relied_on_claims": {
    en: "Claims relied on",
    it: "Affermazioni utilizzate",
  },
  "labels.conclusion_review_missing_step": {
    en: "Missing step",
    it: "Passaggio mancante",
  },
  "labels.reasoning_recommended_improvements": {
    en: "Suggested repair",
    it: "Correzione suggerita",
  },
  "labels.conclusion_review_recommended_fix": {
    en: "Suggested narrowing",
    it: "Riformulazione suggerita",
  },
  "labels.conclusion_review_verdict.supported": {
    en: "Supported",
    it: "Supportata",
  },
  "labels.conclusion_review_verdict.missing_inferential_step": {
    en: "Missing inferential step",
    it: "Passaggio inferenziale mancante",
  },
  "labels.conclusion_review_verdict.overstated_conclusion": {
    en: "Overstated conclusion",
    it: "Conclusione troppo ampia",
  },
  "labels.conclusion_review_verdict.recommendation_not_supported": {
    en: "Recommendation not supported",
    it: "Raccomandazione non supportata",
  },
  "labels.conclusion_review_verdict.unclear": {
    en: "Unclear",
    it: "Non chiara",
  },
  "labels.conclusion_review_verdict.na": {
    en: "Not reviewed",
    it: "Non verificata",
  },
};

const BACKEND_ERROR_TRANSLATIONS_IT = {
  "Provide non-empty research text.": "Inserisci un testo di ricerca non vuoto.",
  "Uploaded file is empty.": "Il file caricato è vuoto.",
  "Unable to parse uploaded file.": "Impossibile analizzare il file caricato.",
  "Unsupported file type. Upload a PDF, HTML, Markdown, or text document.":
    "Tipo di file non supportato. Carica un documento PDF, HTML, Markdown o di testo.",
  "Validation job not found.": "Job di validazione non trovato.",
  "Re-run verification after editing the research text.":
    "Riesegui la verifica dopo aver modificato il testo della ricerca.",
  "Confirm claim decisions before downloading.":
    "Conferma le decisioni sulle affermazioni prima di scaricare.",
};

function readBootstrap() {
  const node = document.getElementById("researchValidateBootstrap");
  if (!node) {
    return {};
  }
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (_err) {
    return {};
  }
}

const bootstrap = readBootstrap();

function t(path, fallback = "") {
  if (!path) {
    return fallback;
  }
  const value = path.split(".").reduce((acc, key) => {
    if (acc && typeof acc === "object" && key in acc) {
      return acc[key];
    }
    return undefined;
  }, appCopy);
  if (value !== undefined && value !== null) {
    return value;
  }

  const fallbackByPath = FALLBACK_COPY_BY_PATH[path];
  if (fallbackByPath && typeof fallbackByPath === "object") {
    if (languageCode && fallbackByPath[languageCode]) {
      return fallbackByPath[languageCode];
    }
    if (fallbackByPath.en) {
      return fallbackByPath.en;
    }
    if (fallbackByPath.it) {
      return fallbackByPath.it;
    }
  }
  return fallback;
}

function localizeBackendError(detail) {
  const raw = String(detail || "").trim();
  if (!raw || !isItalian) {
    return raw;
  }
  if (raw in BACKEND_ERROR_TRANSLATIONS_IT) {
    return BACKEND_ERROR_TRANSLATIONS_IT[raw];
  }
  if (raw.includes("research session") && raw.includes("not found")) {
    return "Sessione di verifica non trovata.";
  }
  return raw;
}

function formatTemplate(template, values = {}) {
  if (typeof template !== "string") {
    return "";
  }
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    if (values[key] === undefined || values[key] === null) {
      return "";
    }
    return String(values[key]);
  });
}

function toIssueToken(value) {
  if (value === undefined || value === null) {
    return "";
  }
  return String(value).trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function humanizeIssueToken(token) {
  if (!token) {
    return "";
  }
  return token.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function localizeIssueGravity(value) {
  const token = toIssueToken(value);
  if (!token) {
    return "";
  }
  return t(`labels.gravity.${token}`, "") || humanizeIssueToken(token);
}

function toImportanceLevel(issue) {
  const score = Number(issue?.risk_score);
  if (!Number.isFinite(score)) {
    return null;
  }
  if (score >= 80) {
    return 5;
  }
  if (score >= 65) {
    return 4;
  }
  if (score >= 45) {
    return 3;
  }
  if (score >= 25) {
    return 2;
  }
  return 1;
}

function localizeIssueKind(value) {
  const token = toIssueToken(value);
  if (!token) {
    return "";
  }
  return t(`labels.issue_kind.${token}`, "") || String(value).trim();
}

function localizeMateriality(value) {
  const token = toIssueToken(value);
  if (!token) {
    return "";
  }
  return t(`labels.materiality.${token}`, "") || t(`labels.gravity.${token}`, "") || humanizeIssueToken(token);
}

function localizeRiskFactor(value) {
  const token = toIssueToken(value);
  if (!token) {
    return "";
  }

  if (token.startsWith("issue:")) {
    const issueToken = toIssueToken(token.slice("issue:".length));
    return formatTemplate(t("labels.risk_factor_templates.issue", "Issue: {value}"), {
      value: localizeIssueKind(issueToken) || humanizeIssueToken(issueToken),
    });
  }

  if (token.startsWith("materiality:")) {
    const materialityToken = toIssueToken(token.slice("materiality:".length));
    return formatTemplate(t("labels.risk_factor_templates.materiality", "Materiality: {value}"), {
      value: localizeMateriality(materialityToken),
    });
  }

  return t(`labels.risk_factors.${token}`, "") || humanizeIssueToken(token);
}

function formatIssueHeader(issue) {
  const rawId = String(issue?.id || "").trim();
  const rawGravity = String(issue?.risk_band || issue?.gravity || "").trim();
  const issueDefault = t("labels.issue_default", "Issue");
  let label = issueDefault;
  let gravity = rawGravity;

  if (rawId) {
    const parsed = rawId.match(/^(.*?)(?:\s*\(([^()]+)\)\s*)?$/);
    if (parsed) {
      const base = String(parsed[1] || "").trim();
      const suffixGravity = String(parsed[2] || "").trim();
      label = base ? localizeIssueKind(base) : issueDefault;
      if (!gravity && suffixGravity) {
        gravity = suffixGravity;
      }
    } else {
      label = localizeIssueKind(rawId);
    }
  }

  const localizedGravity = localizeIssueGravity(gravity);
  if (!localizedGravity) {
    return label;
  }
  return `${label} (${localizedGravity})`;
}

function getIssueImportanceLabel(issue) {
  const level = toImportanceLevel(issue);
  if (!level) {
    return "";
  }
  return t("labels.importance_level", "Importance {level}/5").replace("{level}", String(level));
}

function serializeHtmlWithLinks(fragment) {
  if (!fragment) {
    return "";
  }
  const parts = [];
  fragment.childNodes.forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      parts.push(node.textContent || "");
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return;
    }
    const element = node;
    if (element.tagName === "A") {
      const href = element.getAttribute("href") || "";
      const text = element.textContent || "";
      if (href) {
        parts.push(`<a href="${href}">${text}</a>`);
      } else {
        parts.push(text);
      }
      return;
    }
    parts.push(serializeHtmlWithLinks(element));
  });
  return parts.join("");
}

function getIssueKey(claimIndex, issueId) {
  return `${claimIndex}::${issueId}`;
}

function getClaimKeyValue(claim) {
  const claimIndex = claim?.claim_index;
  if (claimIndex === undefined || claimIndex === null) {
    return "";
  }
  return String(claimIndex);
}

function getClaimIssueCount(claim) {
  return Array.isArray(claim?.issues) ? claim.issues.length : 0;
}

function getClaimStatus(claim) {
  return getClaimIssueCount(claim) > 0 ? "attention" : "clear";
}

function getIssueReviewStatus(issue) {
  const level = toImportanceLevel(issue);
  if (level >= 4) {
    return "incorrect";
  }
  if (level >= 2) {
    return "review";
  }
  return "caution";
}

function getIssueStatusLabel(issue) {
  const status = getIssueReviewStatus(issue);
  const fallbackMap = {
    incorrect: "Incorrect",
    review: "Needs review",
    caution: "Caution",
  };
  return t(`labels.issue_status.${status}`, fallbackMap[status] || "Needs review");
}

function getEvidenceGate(claim) {
  const gate = claim?.evidence_gate;
  if (!gate || typeof gate !== "object") {
    return null;
  }
  return gate;
}

function getEvidenceGateBadgeStatus(status) {
  const token = toIssueToken(status);
  if (token === "pass") {
    return "clear";
  }
  if (token === "fail") {
    return "incorrect";
  }
  if (token === "warning") {
    return "caution";
  }
  return "review";
}

function getEvidenceGateStatusLabel(status) {
  const token = toIssueToken(status) || "na";
  const fallbackMap = {
    pass: "Passed",
    warning: "Limited",
    fail: "Failed",
    na: "Not available",
  };
  return t(`labels.evidence_gate_status.${token}`, fallbackMap[token] || "Not available");
}

function getEvidenceGateStepLabel(stepKey) {
  const token = toIssueToken(stepKey);
  const fallbackMap = {
    source_listed: "Source listed",
    source_retrieved: "Source retrieved",
    source_parsed: "Source parsed",
    source_quote_matched: "Source passage matched",
  };
  return t(`labels.evidence_gate_step.${token}`, fallbackMap[token] || humanizeIssueToken(token));
}

function EvidenceGatePanel({ claim }) {
  const gate = getEvidenceGate(claim);
  if (!gate) {
    return null;
  }

  const gateStatus = toIssueToken(gate.status) || "na";
  const checkedUrl = String(gate.checked_url || "").trim();
  const checkedHref = toSafeExternalHref(checkedUrl);
  const sourceExcerpt = String(gate.source_excerpt || "").trim();
  const steps = Array.isArray(gate.steps) ? gate.steps : [];

  return (
    <div className="research-evidence-gate">
      <div className="research-evidence-head">
        <div>
          <p className="research-evidence-label">{t("labels.evidence_gate", "Deterministic source gate")}</p>
          <p className="research-evidence-note">
            {t(
              "labels.evidence_gate_note",
              "This gate checks source integrity first. Semantic support and reasoning are reviewed separately below.",
            )}
          </p>
        </div>
        <span className={`research-status-badge research-status-badge--${getEvidenceGateBadgeStatus(gateStatus)}`}>
          {getEvidenceGateStatusLabel(gateStatus)}
        </span>
      </div>

      {checkedUrl ? (
        <div className="research-evidence-link-row">
          <span className="research-evidence-link-label">
            {t("labels.evidence_gate_checked_url", "Checked source")}
          </span>
          {checkedHref ? (
            <a className="research-evidence-link" href={checkedHref} target="_blank" rel="noreferrer">
              {checkedUrl}
            </a>
          ) : (
            <span className="research-ref-invalid">{checkedUrl}</span>
          )}
        </div>
      ) : null}

      {sourceExcerpt ? (
        <div className="research-evidence-excerpt-shell">
          <p className="research-evidence-excerpt-label">
            {t("labels.evidence_gate_excerpt", "Matched source excerpt")}
          </p>
          <blockquote className="research-evidence-excerpt">{sourceExcerpt}</blockquote>
        </div>
      ) : null}

      {steps.length > 0 ? (
        <ul className="research-evidence-steps">
          {steps.map((step, index) => {
            const stepStatus = toIssueToken(step?.status) || "na";
            return (
              <li className="research-evidence-step" key={`evidence-step-${index}-${step?.key || "unknown"}`}>
                <div className="research-evidence-step__head">
                  <strong>{getEvidenceGateStepLabel(step?.key)}</strong>
                  <span
                    className={`research-status-badge research-status-badge--${getEvidenceGateBadgeStatus(stepStatus)}`}
                  >
                    {getEvidenceGateStatusLabel(stepStatus)}
                  </span>
                </div>
                {String(step?.detail || "").trim() ? (
                  <p className="research-evidence-step__detail">{String(step.detail)}</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function getSupportReview(claim) {
  const review = claim?.support_review;
  if (!review || typeof review !== "object") {
    return null;
  }
  return review;
}

function getSupportReviewBadgeStatus(verdict) {
  const token = toIssueToken(verdict);
  if (token === "supported") {
    return "clear";
  }
  if (token === "partially_supported") {
    return "caution";
  }
  if (token === "not_supported" || token === "contradicted") {
    return "incorrect";
  }
  return "review";
}

function getSupportVerdictLabel(verdict) {
  const token = toIssueToken(verdict) || "na";
  const fallbackMap = {
    supported: "Supported",
    partially_supported: "Partially supported",
    not_supported: "Not supported",
    contradicted: "Contradicted",
    na: "Not reviewed",
  };
  return t(`labels.support_review_verdict.${token}`, fallbackMap[token] || "Not reviewed");
}

function getSupportScopeLabel(scope) {
  const token = toIssueToken(scope) || "unclear";
  const fallbackMap = {
    same_conclusion: "Same conclusion",
    same_fact: "Same fact only",
    related_context: "Related context only",
    unclear: "Unclear",
  };
  return (
    t(`labels.support_review_scope_values.${token}`, "") ||
    t(`labels.support_review_scope.${token}`, fallbackMap[token] || "Unclear")
  );
}

function SupportReviewPanel({ claim }) {
  const review = getSupportReview(claim);
  if (!review) {
    return null;
  }

  const verdict = toIssueToken(review.verdict) || "na";
  const checkedUrl = String(review.checked_url || "").trim();
  const checkedHref = toSafeExternalHref(checkedUrl);
  const supportingPassage = String(review.supporting_passage || "").trim();
  const explanation = String(review.explanation || "").trim();

  return (
    <div className="filters-subcard research-subcard research-subcard--support">
      <div className="research-support-head">
        <div>
          <p className="research-support-label">{t("labels.support_review", "Semantic support review")}</p>
          <p className="research-support-note">
            {t(
              "labels.support_review_note",
              "This review asks whether the source supports the actual claim, not just whether the link exists.",
            )}
          </p>
        </div>
        <span
          className={`research-status-badge research-status-badge--${getSupportReviewBadgeStatus(verdict)}`}
        >
          {getSupportVerdictLabel(verdict)}
        </span>
      </div>

      <div className="research-support-meta">
        <p className="research-support-meta__item">
          {t("labels.support_review_scope", "Support scope")}: {getSupportScopeLabel(review.support_scope)}
        </p>
        {checkedUrl ? (
          <p className="research-support-meta__item">
            {t("labels.support_review_checked_url", "Source reviewed")}:{" "}
            {checkedHref ? (
              <a className="research-evidence-link" href={checkedHref} target="_blank" rel="noreferrer">
                {checkedUrl}
              </a>
            ) : (
              <span className="research-ref-invalid">{checkedUrl}</span>
            )}
          </p>
        ) : null}
      </div>

      {explanation ? <p className="research-support-explanation">{explanation}</p> : null}

      {supportingPassage ? (
        <div className="research-support-passage-shell">
          <p className="research-support-passage-label">
            {t("labels.support_review_passage", "Supporting passage")}
          </p>
          <blockquote className="research-support-passage">{supportingPassage}</blockquote>
        </div>
      ) : null}
    </div>
  );
}

function getReasoningReview(claim) {
  const review = claim?.reasoning_review;
  if (!review || typeof review !== "object") {
    return null;
  }
  return review;
}

function getReasoningLogicVerdictLabel(verdict) {
  const token = toIssueToken(verdict) || "na";
  const fallbackMap = {
    coherent: "Coherent",
    questionable: "Questionable",
    na: "Not reviewed",
  };
  return t(`labels.reasoning_logic_verdict.${token}`, fallbackMap[token] || "Not reviewed");
}

function getConclusionVerdictLabel(verdict) {
  const token = toIssueToken(verdict) || "na";
  const fallbackMap = {
    supported: "Supported",
    missing_inferential_step: "Missing inferential step",
    overstated_conclusion: "Overstated conclusion",
    recommendation_not_supported: "Recommendation not supported",
    unclear: "Unclear",
    na: "Not reviewed",
  };
  return t(`labels.conclusion_review_verdict.${token}`, fallbackMap[token] || "Not reviewed");
}

function getReasoningReviewBadgeStatus(review) {
  const conclusionVerdict = toIssueToken(review?.conclusion_verdict);
  if (conclusionVerdict === "supported") {
    return "clear";
  }
  if (
    conclusionVerdict === "missing_inferential_step" ||
    conclusionVerdict === "overstated_conclusion" ||
    conclusionVerdict === "recommendation_not_supported"
  ) {
    return "incorrect";
  }
  const logicVerdict = toIssueToken(review?.logic_verdict);
  if (logicVerdict === "coherent") {
    return "clear";
  }
  if (logicVerdict === "questionable" || conclusionVerdict === "unclear") {
    return "review";
  }
  return "review";
}

function formatClaimIndexList(indices) {
  if (!Array.isArray(indices) || indices.length === 0) {
    return "";
  }
  return indices
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0)
    .join(", ");
}

function ReasoningReviewPanel({ claim }) {
  const review = getReasoningReview(claim);
  if (!review) {
    return null;
  }

  const logicVerdict = toIssueToken(review.logic_verdict) || "na";
  const conclusionVerdict = toIssueToken(review.conclusion_verdict) || "na";
  const logicExplanation = String(review.logic_explanation || "").trim();
  const recommendedImprovements = String(review.recommended_improvements || "").trim();
  const conclusionExplanation = String(review.conclusion_explanation || "").trim();
  const missingStep = String(review.missing_step || "").trim();
  const recommendedFix = String(review.recommended_fix || "").trim();
  const conclusionId = String(review.conclusion_id || "").trim();
  const linkedClaimCount = Number(review.linked_claim_count || 0);
  const reliedOnClaims = formatClaimIndexList(review.relied_on_claim_indices);
  const primaryVerdict =
    conclusionVerdict && conclusionVerdict !== "na"
      ? getConclusionVerdictLabel(conclusionVerdict)
      : getReasoningLogicVerdictLabel(logicVerdict);

  return (
    <div className="filters-subcard research-subcard research-subcard--reasoning">
      <div className="research-reasoning-head">
        <div>
          <p className="research-reasoning-label">{t("labels.reasoning_review", "Reasoning review")}</p>
          <p className="research-reasoning-note">
            {t(
              "labels.reasoning_review_note",
              "This review checks the claim's internal logic and, when relevant, whether the linked claims justify the final conclusion.",
            )}
          </p>
        </div>
        <span
          className={`research-status-badge research-status-badge--${getReasoningReviewBadgeStatus(review)}`}
        >
          {primaryVerdict}
        </span>
      </div>

      <div className="research-reasoning-grid">
        <div className="research-reasoning-block">
          <p className="research-reasoning-block__label">{t("labels.reasoning_logic", "Internal logic")}</p>
          <p className="research-reasoning-block__value">{getReasoningLogicVerdictLabel(logicVerdict)}</p>
          {logicExplanation ? <p className="research-reasoning-block__text">{logicExplanation}</p> : null}
          {recommendedImprovements ? (
            <p className="research-reasoning-block__text">
              {t("labels.reasoning_recommended_improvements", "Suggested repair")}: {recommendedImprovements}
            </p>
          ) : null}
        </div>

        <div className="research-reasoning-block">
          <p className="research-reasoning-block__label">{t("labels.conclusion_review", "Conclusion support")}</p>
          <p className="research-reasoning-block__value">{getConclusionVerdictLabel(conclusionVerdict)}</p>
          {conclusionId ? (
            <p className="research-reasoning-block__meta">
              {t("labels.conclusion_review_conclusion_id", "Conclusion ID")}: {conclusionId}
            </p>
          ) : null}
          {linkedClaimCount > 0 ? (
            <p className="research-reasoning-block__meta">
              {t("labels.conclusion_review_linked_claims", "Linked claims reviewed")}: {linkedClaimCount}
            </p>
          ) : null}
          {reliedOnClaims ? (
            <p className="research-reasoning-block__meta">
              {t("labels.conclusion_review_relied_on_claims", "Claims relied on")}: {reliedOnClaims}
            </p>
          ) : null}
          {conclusionExplanation ? (
            <p className="research-reasoning-block__text">{conclusionExplanation}</p>
          ) : null}
          {missingStep ? (
            <p className="research-reasoning-block__text">
              {t("labels.conclusion_review_missing_step", "Missing step")}: {missingStep}
            </p>
          ) : null}
          {recommendedFix ? (
            <p className="research-reasoning-block__text">
              {t("labels.conclusion_review_recommended_fix", "Suggested narrowing")}: {recommendedFix}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function defaultActionForIssue(issue) {
  return issue?.proposed_fix && String(issue.proposed_fix).trim() ? "accept" : "edit";
}

function getBaseSelection(issue) {
  const baseAction = String(issue?.user_action || defaultActionForIssue(issue)).toLowerCase();
  const action = ["accept", "ignore", "edit"].includes(baseAction) ? baseAction : "accept";
  const userText = String(issue?.user_text || "").trim() || String(issue?.proposed_fix || "");
  return { action, userText };
}

function buildSelectionsFromClaims(claims) {
  const selections = {};
  (claims || []).forEach((claim) => {
    (claim?.issues || []).forEach((issue) => {
      selections[getIssueKey(claim?.claim_index, issue?.id)] = getBaseSelection(issue);
    });
  });
  return selections;
}

function normalizeUrlForComparison(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, "")
    .replace(/[.,;:!?]+$/g, "")
    .toLowerCase();
}

function getIssueDescriptionText(claim, issue) {
  const raw = String(issue?.description || "").trim();
  if (!raw) {
    return "";
  }
  const arrowIdx = raw.indexOf("⇒");
  if (arrowIdx <= 0) {
    return raw;
  }
  const prefix = raw.slice(0, arrowIdx).trim();
  const suffix = raw.slice(arrowIdx + 1).trim();
  if (!suffix) {
    return raw;
  }
  const refs = Array.isArray(claim?.reference_urls) ? claim.reference_urls : [];
  const normalizedPrefix = normalizeUrlForComparison(prefix);
  if (!normalizedPrefix) {
    return raw;
  }
  const isDuplicatedRef = refs.some((url) => normalizeUrlForComparison(url) === normalizedPrefix);
  return isDuplicatedRef ? suffix : raw;
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function findRangeInSourceText(sourceText, needle) {
  const text = String(sourceText || "");
  const target = String(needle || "").trim();
  if (!text || !target) {
    return null;
  }

  let start = text.indexOf(target);
  if (start >= 0) {
    return { start, end: start + target.length };
  }

  const lowerText = text.toLowerCase();
  const lowerTarget = target.toLowerCase();
  start = lowerText.indexOf(lowerTarget);
  if (start >= 0) {
    return { start, end: start + target.length };
  }

  const escaped = escapeRegExp(target).replace(/\s+/g, "\\s+");
  if (!escaped) {
    return null;
  }
  const match = new RegExp(escaped, "i").exec(text);
  if (!match || match.index === undefined) {
    return null;
  }
  return { start: match.index, end: match.index + match[0].length };
}

function buildLocatedPassagePreview(sourceText, range) {
  const text = String(sourceText || "");
  if (!text || !range) {
    return null;
  }

  const start = Math.max(0, Number(range.start) || 0);
  const end = Math.max(start + 1, Number(range.end) || start + 1);
  const previewRadius = 220;
  const previewStart = Math.max(0, start - previewRadius);
  const previewEnd = Math.min(text.length, end + previewRadius);

  const compact = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const prefix = compact(text.slice(previewStart, start));
  const match = compact(text.slice(start, end));
  const suffix = compact(text.slice(end, previewEnd));
  const startLine = text.slice(0, start).split("\n").length;
  const endLine = text.slice(0, end).split("\n").length;

  return {
    start,
    end,
    startLine,
    endLine,
    prefix,
    match,
    suffix,
    leadingEllipsis: previewStart > 0,
    trailingEllipsis: previewEnd < text.length,
  };
}

function toSafeExternalHref(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  try {
    const parsed = new URL(raw);
    const protocol = parsed.protocol.toLowerCase();
    if (protocol !== "http:" && protocol !== "https:") {
      return null;
    }
    return parsed.toString();
  } catch (_err) {
    return null;
  }
}

async function raiseFromResponse(resp) {
  let detail = resp.statusText;
  try {
    const data = await resp.json();
    detail = data.detail || detail;
  } catch (_err) {
    // ignore parse errors
  }
  throw new Error(localizeBackendError(detail));
}

function ResearchValidateApp() {
  const textareaRef = useRef(null);
  const uploadInputRef = useRef(null);
  const pollTimerRef = useRef(null);
  const currentJobRef = useRef(null);
  const locatedPassageTimerRef = useRef(null);
  const inputFocusRef = useRef(null);

  const [researchInput, setResearchInput] = useState("");
  const [status, setStatus] = useState({ message: "", type: "info" });
  const [uploadStatus, setUploadStatus] = useState(
    t("messages.upload_hint", "Upload the PDF or Markdown export to pre-fill the text area."),
  );

  const [latestClaims, setLatestClaims] = useState([]);
  const [issueSelections, setIssueSelections] = useState({});
  const [claimFilter, setClaimFilter] = useState("all");
  const [activeClaimKey, setActiveClaimKey] = useState("");
  const [resultsVisible, setResultsVisible] = useState(false);
  const [coherenceSummary, setCoherenceSummary] = useState("");

  const [docReady, setDocReady] = useState(false);
  const [sessionId, setSessionId] = useState("");

  const [runInFlight, setRunInFlight] = useState(false);
  const [applyInFlight, setApplyInFlight] = useState(false);
  const [locatedPassage, setLocatedPassage] = useState(null);
  const [locatedPassageActive, setLocatedPassageActive] = useState(false);

  const homeAriaLabel = {
    en: "Return to the home page",
    it: "Torna alla pagina principale",
    fr: "Retour à la page d'accueil",
    de: "Zurück zur Startseite",
  }[languageCode] || "Return to the home page";
  const defaultPageLabel = {
    en: "Validate Deep Research",
    it: "Valida Deep Research",
    fr: "Valider Deep Research",
    de: "Deep Research prüfen",
  }[languageCode] || "Validate Deep Research";

  const showStatus = useCallback((message, type = "info") => {
    setStatus({ message: message || "", type });
  }, []);

  const stopJobPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    currentJobRef.current = null;
    setRunInFlight(false);
  }, []);

  const updateClaims = useCallback((claims) => {
    const safeClaims = Array.isArray(claims) ? claims : [];
    setLatestClaims(safeClaims);
    setIssueSelections(buildSelectionsFromClaims(safeClaims));
    setActiveClaimKey(getClaimKeyValue(safeClaims[0]) || "");
    setResultsVisible(true);
  }, []);

  const resetResultsPanel = useCallback(() => {
    stopJobPolling();
    setLatestClaims([]);
    setIssueSelections({});
    setClaimFilter("all");
    setActiveClaimKey("");
    setResultsVisible(false);
    setCoherenceSummary("");
    setDocReady(false);
    setSessionId("");
  }, [stopJobPolling]);

  const handleValidationResult = useCallback(
    (result) => {
      if (!result) {
        throw new Error(t("messages.verify_failed", "Verification failed."));
      }
      setSessionId(result.session_id || "");
      if (result.original_text) {
        setResearchInput((prev) => (prev.trim() ? prev : result.original_text));
      }
      updateClaims(result.claims || []);
      setCoherenceSummary("");
      setDocReady(Boolean(result.updated_document));
      showStatus(
        result.claims?.length
          ? t("messages.completed_with_findings", "Verification completed.")
          : t("messages.no_findings", "No issues detected."),
      );
    },
    [showStatus, updateClaims],
  );

  const pollValidationJob = useCallback(
    async (jobId) => {
      if (!jobId || currentJobRef.current !== jobId) {
        return;
      }
      try {
        const resp = await fetch(`${apiBase}/validate/jobs/${jobId}?lang=${encodeURIComponent(currentLang)}`, {
          credentials: "include",
        });
        if (!resp.ok) {
          await raiseFromResponse(resp);
        }
        const data = await resp.json();
        const statusValue = data.status || "pending";
        if (statusValue === "completed") {
          stopJobPolling();
          handleValidationResult(data.result);
          return;
        }
        if (statusValue === "failed") {
          stopJobPolling();
          showStatus(data.error || t("messages.verify_failed", "Verification failed."), "error");
          return;
        }
        showStatus(t("messages.running_verification", "Running verification..."));
        pollTimerRef.current = window.setTimeout(() => {
          pollValidationJob(jobId);
        }, 1500);
      } catch (err) {
        stopJobPolling();
        showStatus(err?.message || t("messages.verify_failed", "Verification failed."), "error");
      }
    },
    [handleValidationResult, showStatus, stopJobPolling],
  );

  useEffect(() => {
    return () => {
      stopJobPolling();
      if (locatedPassageTimerRef.current) {
        clearTimeout(locatedPassageTimerRef.current);
      }
    };
  }, [stopJobPolling]);

  useEffect(() => {
    const initialJobId = new URLSearchParams(window.location.search).get("job");
    if (!initialJobId) {
      return;
    }
    setRunInFlight(true);
    currentJobRef.current = initialJobId;
    showStatus(t("messages.running_verification", "Running verification..."));
    pollValidationJob(initialJobId);
  }, [pollValidationJob, showStatus]);

  const decisionButtonLabel = useMemo(() => {
    const hasIssues = latestClaims.some((claim) => Array.isArray(claim?.issues) && claim.issues.length > 0);
    return hasIssues
      ? t("buttons.confirm_edits", "Confirm selections")
      : t("buttons.generate_validated", "Generate validated document");
  }, [latestClaims]);

  const claimsCount = latestClaims.length;
  const issuesCount = useMemo(
    () =>
      latestClaims.reduce((total, claim) => {
        if (!Array.isArray(claim?.issues)) {
          return total;
        }
        return total + claim.issues.length;
      }, 0),
    [latestClaims],
  );
  const claimsNeedingAttention = useMemo(
    () => latestClaims.filter((claim) => getClaimStatus(claim) === "attention").length,
    [latestClaims],
  );
  const filteredClaims = useMemo(() => {
    if (claimFilter === "attention") {
      return latestClaims.filter((claim) => getClaimStatus(claim) === "attention");
    }
    if (claimFilter === "clear") {
      return latestClaims.filter((claim) => getClaimStatus(claim) === "clear");
    }
    return latestClaims;
  }, [claimFilter, latestClaims]);
  const activeClaim = useMemo(() => {
    const selectedClaim = filteredClaims.find((claim) => getClaimKeyValue(claim) === activeClaimKey);
    if (selectedClaim) {
      return selectedClaim;
    }
    if (filteredClaims.length > 0) {
      return filteredClaims[0];
    }
    if (latestClaims.length > 0) {
      return latestClaims[0];
    }
    return null;
  }, [activeClaimKey, filteredClaims, latestClaims]);

  useEffect(() => {
    if (filteredClaims.length === 0) {
      if (latestClaims.length === 0 && activeClaimKey) {
        setActiveClaimKey("");
      }
      return;
    }
    if (!filteredClaims.some((claim) => getClaimKeyValue(claim) === activeClaimKey)) {
      setActiveClaimKey(getClaimKeyValue(filteredClaims[0]) || "");
    }
  }, [activeClaimKey, filteredClaims, latestClaims.length]);

  useEffect(() => {
    setLocatedPassage(null);
    setLocatedPassageActive(false);
    if (locatedPassageTimerRef.current) {
      clearTimeout(locatedPassageTimerRef.current);
      locatedPassageTimerRef.current = null;
    }
  }, [activeClaimKey]);

  const topDownloadDisabled = !(docReady && sessionId);
  const showDecisionActions = resultsVisible && latestClaims.length > 0;
  const showInlineDownload = resultsVisible && Boolean(sessionId);
  const activeClaimIssueCount = getClaimIssueCount(activeClaim);
  const filterCounts = {
    all: claimsCount,
    attention: claimsNeedingAttention,
    clear: Math.max(claimsCount - claimsNeedingAttention, 0),
  };
  const reviewMethodSteps = [
    t("labels.review_stage.claims", "Key claims extracted"),
    t("labels.review_stage.sources", "Source existence checked"),
    t("labels.review_stage.support", "Source support compared"),
    t("labels.review_stage.logic", "Logic reviewed"),
  ];
  const summaryItems = [
    {
      key: "claims",
      label: t("labels.summary.claims_extracted", "Claims extracted"),
      value: String(claimsCount),
    },
    {
      key: "attention",
      label: t("labels.summary.claims_attention", "Claims needing review"),
      value: String(claimsNeedingAttention),
    },
    {
      key: "issues",
      label: t("labels.summary.issues_flagged", "Issues flagged"),
      value: String(issuesCount),
    },
    {
      key: "ready",
      label: t("labels.summary.doc_ready", "Validated doc"),
      value: docReady
        ? t("labels.claim_status.ready", "Ready")
        : t("labels.claim_status.pending", "Pending"),
    },
  ];

  const handleRunValidation = async () => {
    const text = researchInput.trim();
    if (!text) {
      showStatus(t("messages.paste_first", "Please paste the research text first."), "error");
      return;
    }

    resetResultsPanel();
    showStatus(t("messages.running_verification", "Running verification..."));
    setRunInFlight(true);

    try {
      const resp = await fetch(`${apiBase}/validate/jobs?lang=${encodeURIComponent(currentLang)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text }),
      });
      if (!resp.ok) {
        await raiseFromResponse(resp);
      }
      const data = await resp.json();
      const jobId = data.job_id || "";
      if (!jobId) {
        throw new Error(t("messages.verify_failed", "Verification failed."));
      }
      currentJobRef.current = jobId;
      pollValidationJob(jobId);
    } catch (err) {
      stopJobPolling();
      resetResultsPanel();
      showStatus(err?.message || t("messages.verify_failed", "Verification failed."), "error");
    }
  };

  const collectDecisions = () => {
    const decisions = [];
    latestClaims.forEach((claim) => {
      (claim?.issues || []).forEach((issue) => {
        const key = getIssueKey(claim?.claim_index, issue?.id);
        const selection = issueSelections[key];
        if (!selection) {
          throw new Error(t("messages.selection_missing", "Select an action for every issue."));
        }
        const action = selection.action || "accept";
        const payload = {
          claim_index: claim.claim_index,
          issue_id: issue.id,
          action,
          user_text: action === "edit" ? String(selection.userText || "").trim() : "",
        };
        if (payload.action === "edit" && !payload.user_text) {
          throw new Error(t("messages.edit_required", "Provide replacement text for edited issues."));
        }
        decisions.push(payload);
      });
    });
    return decisions;
  };

  const handleApplyDecisions = async () => {
    if (!latestClaims.length) {
      showStatus(t("messages.no_claims", "No claims to confirm yet."), "warning");
      return;
    }
    if (!sessionId) {
      showStatus(t("messages.session_missing", "Start by running verification."), "error");
      return;
    }
    const text = researchInput.trim();
    if (!text) {
      showStatus(t("messages.paste_first", "Please paste the research text first."), "error");
      return;
    }

    let decisions;
    try {
      decisions = collectDecisions();
    } catch (err) {
      showStatus(err?.message || t("messages.verify_failed", "Verification failed."), "error");
      return;
    }

    showStatus(t("messages.saving_decisions", "Saving your selections..."));
    setApplyInFlight(true);

    try {
      const resp = await fetch(`${apiBase}/validate/actions?lang=${encodeURIComponent(currentLang)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text, decisions, session_id: sessionId }),
      });
      if (!resp.ok) {
        await raiseFromResponse(resp);
      }
      const data = await resp.json();
      setSessionId(data.session_id || sessionId);
      updateClaims(data.claims || []);
      setCoherenceSummary(data.coherence_summary || "");
      setDocReady(Boolean(data.updated_document));
      showStatus(
        t(
          "messages.decisions_saved",
          "Selections saved. You can now download the validated document.",
        ),
      );
    } catch (err) {
      showStatus(err?.message || t("messages.verify_failed", "Verification failed."), "error");
    } finally {
      setApplyInFlight(false);
    }
  };

  const handleDownloadDocx = async () => {
    const text = researchInput.trim();
    if (!text) {
      showStatus(t("messages.download_paste_first", "Paste the research text before downloading."), "error");
      return;
    }
    if (!sessionId) {
      showStatus(t("messages.session_missing", "Start by running verification."), "error");
      return;
    }
    if (!docReady) {
      showStatus(
        t(
          "messages.download_after_confirm",
          "Confirm your issue selections before downloading.",
        ),
        "error",
      );
      return;
    }

    try {
      const resp = await fetch(`${apiBase}/validate/docx?lang=${encodeURIComponent(currentLang)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text, session_id: sessionId }),
      });
      if (!resp.ok) {
        await raiseFromResponse(resp);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "validated_document.docx";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      showStatus(t("messages.download_started", "Downloading validated document..."));
    } catch (err) {
      showStatus(err?.message || t("messages.download_failed", "Download failed."), "error");
    }
  };

  const handleUploadClick = () => {
    uploadInputRef.current?.click();
  };

  const handleUploadChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setUploadStatus(formatTemplate(t("messages.uploading_file", "Uploading {name}..."), { name: file.name }));

    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch(`${apiBase}/upload?lang=${encodeURIComponent(currentLang)}`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!resp.ok) {
        await raiseFromResponse(resp);
      }
      const data = await resp.json();
      setResearchInput(data.text || "");
      setUploadStatus(formatTemplate(t("messages.upload_success", "Loaded {name}."), { name: file.name }));
      showStatus(t("messages.upload_success_status", "File uploaded successfully."));
    } catch (err) {
      const message = err?.message || t("messages.upload_failed", "Unable to read file.");
      setUploadStatus(message);
      showStatus(message, "error");
    } finally {
      event.target.value = "";
    }
  };

  const handleInputPaste = (event) => {
    const html = event.clipboardData?.getData("text/html");
    if (!html) {
      return;
    }
    event.preventDefault();

    const fragment = document.createElement("div");
    fragment.innerHTML = html;
    const serialized = serializeHtmlWithLinks(fragment);

    const textarea = event.target;
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;

    setResearchInput((prev) => {
      const before = prev.slice(0, start);
      const after = prev.slice(end);
      return `${before}${serialized}${after}`;
    });

    const nextCursor = start + serialized.length;
    requestAnimationFrame(() => {
      if (!textareaRef.current) {
        return;
      }
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(nextCursor, nextCursor);
    });
  };

  const handleLocateClaimSource = (sourceQuote) => {
    const found = findRangeInSourceText(researchInput, sourceQuote);
    if (!found) {
      setLocatedPassage(null);
      setLocatedPassageActive(false);
      showStatus(t("messages.claim_source_not_found", "Passage not found in the original text."), "warning");
      return;
    }

    const textarea = textareaRef.current;
    const start = Math.max(0, Number(found.start) || 0);
    const end = Math.max(start + 1, Number(found.end) || start + 1);
    setLocatedPassage(buildLocatedPassagePreview(researchInput, { start, end }));
    setLocatedPassageActive(true);

    if (locatedPassageTimerRef.current) {
      clearTimeout(locatedPassageTimerRef.current);
    }
    locatedPassageTimerRef.current = window.setTimeout(() => {
      setLocatedPassageActive(false);
      locatedPassageTimerRef.current = null;
    }, 2800);

    requestAnimationFrame(() => {
      if (inputFocusRef.current) {
        inputFocusRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      if (!textarea) {
        return;
      }
      const computedStyle = window.getComputedStyle(textarea);
      const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 26;
      const linesBefore = Math.max(0, researchInput.slice(0, start).split("\n").length - 1);
      const selectedLines = Math.max(1, researchInput.slice(start, end).split("\n").length);
      const targetTop = Math.max(
        0,
        linesBefore * lineHeight - textarea.clientHeight / 2 + (selectedLines * lineHeight) / 2,
      );
      textarea.focus();
      textarea.setSelectionRange(start, end);
      if (typeof textarea.scrollTo === "function") {
        textarea.scrollTo({ top: targetTop, behavior: "smooth" });
      } else {
        textarea.scrollTop = targetTop;
      }
    });

    showStatus(
      t(
        "messages.claim_source_brought_into_view",
        "Passage brought into view below and highlighted in the original text.",
      ),
    );
  };

  const clearLocatedPassage = () => {
    setLocatedPassage(null);
    setLocatedPassageActive(false);
    if (locatedPassageTimerRef.current) {
      clearTimeout(locatedPassageTimerRef.current);
      locatedPassageTimerRef.current = null;
    }
  };

  const setIssueAction = (claimIndex, issue, action) => {
    const key = getIssueKey(claimIndex, issue.id);
    setIssueSelections((prev) => {
      const current = prev[key] || getBaseSelection(issue);
      const nextText = String(current.userText || "") || String(issue?.proposed_fix || "");
      return {
        ...prev,
        [key]: {
          action,
          userText: nextText,
        },
      };
    });
  };

  const setIssueUserText = (claimIndex, issueId, value) => {
    const key = getIssueKey(claimIndex, issueId);
    setIssueSelections((prev) => ({
      ...prev,
      [key]: { action: "edit", userText: value },
    }));
  };

  return (
    <>
      <header className="landing-header">
        <a
          href={`/?lang=${currentLang || "en"}`}
          className="landing-logo-link"
          aria-label={homeAriaLabel}
        >
          <img className="landing-logo" src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" alt="Mparanza" />
        </a>
      </header>
      <main className="app-main research-main">
        <div className="container research-wrapper research-page">
          <h1 className="page-title">
            {bootstrap.page_label || defaultPageLabel}
          </h1>
          <p className="research-lead">
            {t(
              "page_help",
              "Review the answer by extracting a small set of key claims, checking the cited sources, and deciding whether each claim is supported and logically sound.",
            )}
          </p>

          <div className="research-summary-strip" aria-label={t("panels.results.title", "Verification results")}>
            {summaryItems.map((item) => (
              <div className="research-summary-tile" key={item.key}>
                <span className="research-summary-tile__value">{item.value}</span>
                <span className="research-summary-tile__label">{item.label}</span>
              </div>
            ))}
          </div>

          <div className="research-layout">
            <section className="panel research-panel research-panel--input">
              <div className="panel-header">
                <h2
                  className="panel-title panel-title--with-help"
                  data-tooltip={
                    t(
                      "panels.input.subtitle",
                      "Paste the full response or upload the PDF exported from Deep Research.",
                    )
                  }
                  aria-label={
                    t(
                      "panels.input.subtitle",
                      "Paste the full response or upload the PDF exported from Deep Research.",
                    )
                  }
                >
                  {t("panels.input.title", "Paste or upload Deep Research output")}
                </h2>
              </div>

              <div className="filters-subcard research-subcard research-subcard--method">
                <div className="research-section-kicker">
                  {t("labels.review_method", "Review method")}
                </div>
                <ol className="research-method-list">
                  {reviewMethodSteps.map((step, index) => (
                    <li className="research-method-list__item" key={step}>
                      <span className="research-method-list__index">{index + 1}</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {activeClaim && (
                <div className="filters-subcard research-subcard research-subcard--dossier">
                  <div className="research-section-kicker">
                    {t("labels.source_dossier", "Source dossier")}
                  </div>
                  <div className="research-dossier-head">
                    <div>
                      <p className="research-dossier-label">
                        {t("labels.active_claim", "Active claim")}
                      </p>
                      <h3>
                        {formatTemplate(t("labels.claim_number", "Claim #{index}"), {
                          index: activeClaim.claim_index,
                        })}
                      </h3>
                    </div>
                    <span className={`research-status-badge research-status-badge--${getClaimStatus(activeClaim)}`}>
                      {t(
                        `labels.claim_status.${getClaimStatus(activeClaim)}`,
                        getClaimStatus(activeClaim) === "attention" ? "Needs review" : "Clear",
                      )}
                    </span>
                  </div>
                  <p className="research-dossier-claim">{activeClaim.claim_text || ""}</p>
                  {String(activeClaim?.source_quote || "").trim() ? (
                    <>
                      <blockquote className="research-dossier-quote">
                        {String(activeClaim.source_quote)}
                      </blockquote>
                      <button
                        type="button"
                        className="ghost-button research-claim-locate"
                        onClick={() => handleLocateClaimSource(String(activeClaim.source_quote || ""))}
                      >
                        {t("buttons.locate_claim_source", "Find in original text")}
                      </button>
                    </>
                  ) : (
                    <p className="research-source-missing">
                      {t(
                        "labels.source_quote_missing",
                        "No pinpointed passage was returned for this claim. Review the original text and links directly.",
                      )}
                    </p>
                  )}
                  <EvidenceGatePanel claim={activeClaim} />
                </div>
              )}

              <div ref={inputFocusRef} className="research-text-header">
                <div className="research-section-kicker">
                  {t("labels.original_text", "Original research text")}
                </div>
              </div>

              {locatedPassage ? (
                <div
                  className={`filters-subcard research-subcard research-subcard--located${
                    locatedPassageActive ? " is-active" : ""
                  }`}
                  role="status"
                  aria-live="polite"
                >
                  <div className="research-locate-head">
                    <div>
                      <p className="research-locate-label">{t("labels.located_passage", "Located passage")}</p>
                      <p className="research-locate-range">
                        {formatTemplate(t("labels.located_passage_range", "Lines {start}-{end} in the original text"), {
                          start: locatedPassage.startLine,
                          end: locatedPassage.endLine,
                        })}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="ghost-button research-locate-dismiss"
                      onClick={clearLocatedPassage}
                    >
                      {t("buttons.clear_located_passage", "Clear highlight")}
                    </button>
                  </div>
                  <p className="research-locate-note">
                    {t(
                      "labels.located_passage_note",
                      "The matching fragment is surfaced below so you do not need to hunt through the full text area.",
                    )}
                  </p>
                  <blockquote className="research-locate-preview">
                    {locatedPassage.leadingEllipsis ? (
                      <span className="research-locate-preview__fade">...</span>
                    ) : null}
                    {locatedPassage.prefix ? (
                      <span className="research-locate-preview__context">{locatedPassage.prefix} </span>
                    ) : null}
                    <mark className="research-locate-preview__match">{locatedPassage.match}</mark>
                    {locatedPassage.suffix ? (
                      <span className="research-locate-preview__context"> {locatedPassage.suffix}</span>
                    ) : null}
                    {locatedPassage.trailingEllipsis ? (
                      <span className="research-locate-preview__fade">...</span>
                    ) : null}
                  </blockquote>
                </div>
              ) : null}

              <textarea
                ref={textareaRef}
                id="researchInput"
                className={`prompt-textarea${locatedPassageActive ? " is-located" : ""}`}
                rows={12}
                value={researchInput}
                placeholder={t("placeholders.research_input", "Paste the research text including links...")}
                onChange={(event) => setResearchInput(event.target.value)}
                onPaste={handleInputPaste}
              />

              <div className="filters-subcard research-subcard research-subcard--input-actions">
                <div className="upload-controls">
                  <button id="triggerUpload" className="ghost-button" type="button" onClick={handleUploadClick}>
                    {t("buttons.choose_file", "Select Deep Research file")}
                  </button>
                  <input
                    ref={uploadInputRef}
                    id="researchUpload"
                    type="file"
                    accept=".pdf,.html,.htm,.md,.markdown,.txt,application/pdf,text/plain,text/markdown,text/html"
                    hidden
                    onChange={handleUploadChange}
                  />
                  <small id="uploadStatus" className="upload-status">
                    {uploadStatus}
                  </small>
                </div>

                <div className="actions research-actions">
                  <button
                    id="runValidation"
                    className="primary-button"
                    type="button"
                    disabled={runInFlight}
                    onClick={handleRunValidation}
                  >
                    {t("buttons.run_validation", "Run verification")}
                  </button>
                  <button
                    id="downloadDocx"
                    className="ghost-button"
                    type="button"
                    disabled={topDownloadDisabled}
                    onClick={handleDownloadDocx}
                  >
                    {t("buttons.download_docx", "Download validated docx")}
                  </button>
                </div>

                <div
                  id="validationStatus"
                  role="status"
                  className={`status-bar${status.type === "error" ? " status-bar__error" : ""}${
                    status.type === "warning" ? " status-bar__warning" : ""
                  }`}
                >
                  {status.message}
                </div>
              </div>
            </section>

            {resultsVisible && (
              <section className="panel research-panel research-panel--results" id="resultsPanel">
                <div className="panel-header">
                  <h2>{t("panels.results.title", "Verification results")}</h2>
                  <small>
                    {t(
                      "panels.results.subtitle",
                      "Review flagged claims, correction prompt, and final notes.",
                    )}
                  </small>
                  <div className="pill-group research-pill-group research-results-meta">
                    <span className="pill is-selected research-pill-static">
                      {formatTemplate(t("labels.claims_count", "Claims reviewed: {count}"), {
                        count: claimsCount,
                      })}
                    </span>
                    <span className="pill research-pill-static">
                      {formatTemplate(t("labels.flagged_issues_count", "Issues flagged: {count}"), {
                        count: issuesCount,
                      })}
                    </span>
                  </div>
                </div>

                {!latestClaims.length ? (
                  <div className="research-empty-state">
                    <p>{t("labels.no_claims", "No claims were flagged.")}</p>
                  </div>
                ) : (
                  <div className="research-results-shell">
                    <aside className="research-claim-index">
                      <div className="research-index-head">
                        <div className="research-section-kicker">
                          {t("labels.claim_index", "Claim docket")}
                        </div>
                        <p className="research-index-hint">
                          {t(
                            "labels.claim_index_hint",
                            "Work one claim at a time while keeping the full review set visible.",
                          )}
                        </p>
                      </div>

                      <div className="research-filter-pills" role="tablist" aria-label={t("labels.claim_index", "Claim docket")}>
                        {["all", "attention", "clear"].map((filterValue) => (
                          <button
                            key={filterValue}
                            type="button"
                            className={`research-filter-pill${claimFilter === filterValue ? " is-active" : ""}`}
                            onClick={() => setClaimFilter(filterValue)}
                          >
                            <span>{t(`labels.claim_filter.${filterValue}`, filterValue)}</span>
                            <strong>{filterCounts[filterValue]}</strong>
                          </button>
                        ))}
                      </div>

                      <div id="claimsContainer" className="research-claim-list">
                        {filteredClaims.map((claim, claimPosition) => {
                          const claimIndex = claim?.claim_index ?? "";
                          const issueCount = getClaimIssueCount(claim);
                          const statusKey = getClaimStatus(claim);
                          const isActive = getClaimKeyValue(claim) === getClaimKeyValue(activeClaim);

                          return (
                            <button
                              type="button"
                              className={`research-claim-nav${isActive ? " is-active" : ""}`}
                              key={`claim-nav-${claimIndex}`}
                              style={{ "--claim-delay": `${Math.min(claimPosition, 10) * 45}ms` }}
                              onClick={() => setActiveClaimKey(getClaimKeyValue(claim))}
                            >
                              <div className="research-claim-nav__head">
                                <span className="research-claim-nav__number">
                                  {formatTemplate(t("labels.claim_number", "Claim #{index}"), {
                                    index: claimIndex,
                                  })}
                                </span>
                                <span className={`research-status-badge research-status-badge--${statusKey}`}>
                                  {t(
                                    `labels.claim_status.${statusKey}`,
                                    statusKey === "attention" ? "Needs review" : "Clear",
                                  )}
                                </span>
                              </div>
                              <p className="research-claim-nav__text">{claim?.claim_text || ""}</p>
                              <div className="research-claim-nav__meta">
                                <span>
                                  {formatTemplate(t("labels.issue_count", "Issues: {count}"), {
                                    count: issueCount,
                                  })}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </aside>

                    <div className="research-claim-detail">
                      {activeClaim ? (
                        <article className="research-claim research-claim--active" key={`claim-${activeClaim.claim_index}`}>
                          <div className="research-claim-head">
                            <div>
                              <h4>
                                {formatTemplate(t("labels.claim_number", "Claim #{index}"), {
                                  index: activeClaim.claim_index,
                                })}
                              </h4>
                              <span className="research-claim-status-line">
                                {t(
                                  `labels.claim_status.${getClaimStatus(activeClaim)}`,
                                  getClaimStatus(activeClaim) === "attention" ? "Needs review" : "Clear",
                                )}
                              </span>
                            </div>
                            <span className={`pill research-inline-pill${activeClaimIssueCount > 0 ? " is-selected" : ""}`}>
                              {formatTemplate(t("labels.issue_count", "Issues: {count}"), {
                                count: activeClaimIssueCount,
                              })}
                            </span>
                          </div>

                          <p className="research-claim-text">{activeClaim?.claim_text || ""}</p>

                          {String(activeClaim?.source_quote || "").trim() && (
                            <div className="filters-subcard research-subcard research-subcard--quote">
                              <p className="research-claim-quote-label">
                                {t("labels.claim_source_quote", "Source passage")}
                              </p>
                              <blockquote className="research-claim-quote">{String(activeClaim.source_quote)}</blockquote>
                              <button
                                type="button"
                                className="ghost-button research-claim-locate"
                                onClick={() => handleLocateClaimSource(String(activeClaim.source_quote || ""))}
                              >
                                {t("buttons.locate_claim_source", "Find in original text")}
                              </button>
                            </div>
                          )}

                          {Array.isArray(activeClaim?.reference_urls) && activeClaim.reference_urls.length > 0 && (
                            <div className="filters-subcard research-subcard research-subcard--refs">
                              <p className="research-refs-label">
                                {t("labels.references_label", "Supporting links")}
                              </p>
                              <ul className="research-refs">
                                {activeClaim.reference_urls.map((url, idx) => {
                                  const safeHref = toSafeExternalHref(url);
                                  return (
                                    <li key={`claim-${activeClaim.claim_index}-ref-${idx}`}>
                                      {safeHref ? (
                                        <a href={safeHref} target="_blank" rel="noreferrer">
                                          {String(url || "")}
                                        </a>
                                      ) : (
                                        <span className="research-ref-invalid">{String(url || "")}</span>
                                      )}
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          )}

                          <SupportReviewPanel claim={activeClaim} />
                          <ReasoningReviewPanel claim={activeClaim} />

                          {Array.isArray(activeClaim?.issues) && activeClaim.issues.length > 0 ? (
                            <div className="research-issues">
                              {activeClaim.issues.map((issue, issueIdx) => {
                                const issueId = issue?.id || `issue-${issueIdx}`;
                                const key = getIssueKey(activeClaim.claim_index, issueId);
                                const selection = issueSelections[key] || getBaseSelection(issue);
                                const action = selection.action || "accept";
                                const userText = String(selection.userText || "");
                                const importanceLevel = toImportanceLevel(issue) || 0;
                                const importanceLabel = getIssueImportanceLabel(issue);
                                const issueStatus = getIssueReviewStatus(issue);

                                const factors = Array.isArray(issue?.risk_factors) ? issue.risk_factors : [];
                                const issueToken = toIssueToken(String(issue?.id || "").replace(/\(.*/, "").trim());
                                const formattedFactors = factors
                                  .map((factor) => ({
                                    token: toIssueToken(factor),
                                    text: localizeRiskFactor(factor),
                                  }))
                                  .filter((factor) => Boolean(factor.text))
                                  .filter((factor) => factor.token !== `issue:${issueToken}`)
                                  .map((factor) => factor.text);

                                return (
                                  <div
                                    className="research-issue filters-subcard research-subcard"
                                    data-importance={importanceLevel}
                                    data-status={issueStatus}
                                    key={`claim-${activeClaim.claim_index}-issue-${issueId}-${issueIdx}`}
                                  >
                                    <div className="research-issue-head">
                                      <div className="research-issue-headline">
                                        <span className={`research-status-badge research-status-badge--${issueStatus}`}>
                                          {getIssueStatusLabel(issue)}
                                        </span>
                                        <h5>{formatIssueHeader(issue)}</h5>
                                      </div>
                                      {importanceLabel ? (
                                        <span className="pill research-issue-pill">{importanceLabel}</span>
                                      ) : null}
                                    </div>

                                    {formattedFactors.length > 0 && (
                                      <p className="issue-risk">
                                        {t("labels.why_flagged", "Why flagged")}: {formattedFactors.join(", ")}
                                      </p>
                                    )}

                                    <p className="research-issue-description">
                                      {getIssueDescriptionText(activeClaim, issue)}
                                    </p>

                                    {issue?.proposed_fix && (
                                      <p className="research-fix">
                                        {t("labels.fix_prefix", "Fix:")} {String(issue.proposed_fix)}
                                      </p>
                                    )}

                                    <div className="issue-actions">
                                      <label className="issue-action">
                                        <input
                                          type="radio"
                                          name={`issue-${activeClaim.claim_index}-${issueIdx}`}
                                          value="accept"
                                          checked={action === "accept"}
                                          onChange={() => setIssueAction(activeClaim.claim_index, issue, "accept")}
                                        />
                                        <span>{t("labels.accept_issue", "Accept fix")}</span>
                                      </label>
                                      <label className="issue-action">
                                        <input
                                          type="radio"
                                          name={`issue-${activeClaim.claim_index}-${issueIdx}`}
                                          value="ignore"
                                          checked={action === "ignore"}
                                          onChange={() => setIssueAction(activeClaim.claim_index, issue, "ignore")}
                                        />
                                        <span>{t("labels.ignore_issue", "Ignore")}</span>
                                      </label>
                                      <label className="issue-action">
                                        <input
                                          type="radio"
                                          name={`issue-${activeClaim.claim_index}-${issueIdx}`}
                                          value="edit"
                                          checked={action === "edit"}
                                          onChange={() => setIssueAction(activeClaim.claim_index, issue, "edit")}
                                        />
                                        <span>{t("labels.edit_issue", "Edit text")}</span>
                                      </label>
                                    </div>

                                    {action === "edit" && (
                                      <textarea
                                        className="issue-edit"
                                        placeholder={t("labels.edit_placeholder", "Provide replacement text...")}
                                        value={userText}
                                        onChange={(event) =>
                                          setIssueUserText(activeClaim.claim_index, issueId, event.target.value)
                                        }
                                      />
                                    )}

                                    {!issue?.proposed_fix && (
                                      <p className="issue-warning">
                                        {t(
                                          "messages.manual_fix_required",
                                          "No suggested fix available - edit or ignore this issue.",
                                        )}
                                      </p>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="filters-subcard research-subcard research-subcard--ok">
                              <p className="research-no-issues">
                                {t("labels.claim_no_issues", "No issues flagged for this claim.")}
                              </p>
                            </div>
                          )}
                        </article>
                      ) : (
                        <div className="research-empty-state">
                          <p>{t("labels.no_claims", "No claims were flagged.")}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {showDecisionActions && (
                  <div className="filters-subcard research-subcard research-subcard--decisions">
                    <div className="actions research-actions" id="decisionActions">
                      <button
                        id="applyDecisions"
                        className="primary-button"
                        type="button"
                        disabled={applyInFlight}
                        onClick={handleApplyDecisions}
                      >
                        {decisionButtonLabel}
                      </button>
                    </div>
                    <p className="actions-hint">
                      {t(
                        "messages.decisions_hint",
                        "Confirm each issue to control what goes into the correction prompt and merged document.",
                      )}
                    </p>
                  </div>
                )}

                {Boolean(coherenceSummary) && (
                  <section className="panel-subsection filters-subcard research-subcard" id="coherenceSection">
                    <h3>{t("panels.coherence.title", "Coherence summary")}</h3>
                    <p id="coherenceSummary">{coherenceSummary}</p>
                  </section>
                )}

                {showInlineDownload && (
                  <div className="filters-subcard research-subcard">
                    <div className="actions research-actions" id="resultsDownloadActions">
                      <button
                        id="downloadDocxInline"
                        className="ghost-button"
                        type="button"
                        disabled={topDownloadDisabled}
                        onClick={handleDownloadDocx}
                      >
                        {t("buttons.download_docx", "Download validated docx")}
                      </button>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      </main>
    </>
  );
}

const rootNode = document.getElementById("researchValidateReactApp");
if (rootNode) {
  createRoot(rootNode).render(<ResearchValidateApp />);
}

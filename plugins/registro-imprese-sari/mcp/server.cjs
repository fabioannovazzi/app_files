#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const SERVER_NAME = "registro-imprese-sari-review";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const PLUGIN_NAME = "registro-imprese-sari";
const WIDGET_URI = "ui://widget/registro-imprese-sari-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const MAX_TEXT_LENGTH = 10_000;
const MAX_PERSISTENCE_CONTEXTS = 128;
const PERSISTENCE_CONTEXT_TTL_MS = 4 * 60 * 60 * 1000;
const PERSISTENCE_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const PERSISTENCE_CONTEXTS = new Map();
const TOOL_NAMES = {
  validate: "validate_registro_imprese_sari_review",
  render: "render_registro_imprese_sari_review",
  save: "save_registro_imprese_sari_decisions",
  apply: "apply_registro_imprese_sari_decisions",
};
const ALLOWED_ACTIONS = new Set([
  "accept",
  "reject",
  "edit",
  "mark_unclear",
  "request_more_documents",
  "skip",
]);
const ITEM_TYPES = new Set([
  "case_fact",
  "practice_step",
  "official_source",
  "missing_information",
  "audit_check",
  "artifact",
]);
const ACTION_STATUS = {
  accept: "accepted",
  reject: "rejected",
  edit: "edited_revision_required",
  mark_unclear: "needs_clarification",
  request_more_documents: "needs_documents",
  skip: "skipped",
};
const FORBIDDEN_REVIEW_KEYS = new Set([
  "activity_description",
  "case_summary",
  "client_name",
  "codice_fiscale",
  "document_quote",
  "email",
  "full_name",
  "partita_iva",
  "proposed_value",
  "sari_question_draft",
]);
const EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;
const TAX_CODE_RE = /\b[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]\b/i;
const VAT_RE = /(^|\D)\d{11}(?!\d)/;
const PHONE_RE = /(^|\W)(?:\+?39[ .-]?)?(?:0\d{1,3}|3\d{2})[ .-]?\d{5,8}(?!\w)/;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function objectSchema(properties, required = [], additionalProperties = true) {
  return { type: "object", properties, required, additionalProperties };
}

function toolUiMeta() {
  return {
    ui: { resourceUri: WIDGET_URI, visibility: ["model"] },
    "ui/resourceUri": WIDGET_URI,
    "openai/outputTemplate": WIDGET_URI,
    "openai/widgetAccessible": true,
    "openai/toolInvocation/invoking": "Apertura revisione Registro Imprese",
    "openai/toolInvocation/invoked": "Revisione Registro Imprese aperta",
  };
}

function widgetMeta() {
  return {
    ui: { resourceUri: WIDGET_URI },
    "openai/widgetDescription":
      "Revisione locale e minimizzata di fonti ufficiali, passaggi DIRE, informazioni mancanti e controlli della pratica Registro Imprese.",
    "openai/widgetPrefersBorder": false,
    "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
    "openai/widgetDomain": "https://chatgpt.com",
  };
}

function toolDefinitions() {
  const reviewPayload = objectSchema(
    {
      schema_version: { type: "string" },
      plugin: { type: "string" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      review_type: { type: "string" },
      status: { type: "string" },
      item_count: { type: "number" },
      items: { type: "array", items: { type: "object" } },
      privacy_notice: { type: "string" },
      filing_status: { type: "string" },
      filing_authorized: { type: "boolean" },
    },
    ["schema_version", "plugin", "workflow", "run_id", "item_count", "items"],
  );
  const reviewInput = objectSchema(
    {
      run_intake: { type: "object" },
      review_payload: reviewPayload,
      ui_decisions: { type: "object" },
      final_artifacts: { type: "object" },
    },
    ["review_payload"],
  );
  const decision = objectSchema(
    {
      item_id: { type: "string" },
      action: { type: "string", enum: Array.from(ALLOWED_ACTIONS) },
      reviewer_note: { type: "string" },
      edit_value: { type: "string" },
      requested_documents: { type: "array", items: { type: "string" } },
    },
    ["item_id", "action"],
  );
  const decisionInput = objectSchema(
    {
      run_intake: { type: "object" },
      persistence_token: { type: "string" },
      review_payload: reviewPayload,
      decisions: { type: "array", items: decision },
      decision_source: { type: "string" },
      reviewer: { type: "string" },
      ui_decisions: { type: "object" },
      final_artifacts: { type: "object" },
    },
    ["review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validate,
      title: "Valida revisione Registro Imprese e SARI",
      description:
        `Valida il payload minimizzato prima della visualizzazione. Chiamare prima di ${TOOL_NAMES.render}.`,
      inputSchema: reviewInput,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.render,
      title: "Apri revisione Registro Imprese e SARI",
      description:
        "Mostra fonti ufficiali, passaggi DIRE, informazioni mancanti e controlli senza includere dati identificativi o testi integrali del caso.",
      inputSchema: reviewInput,
      _meta: toolUiMeta(),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.save,
      title: "Salva decisioni Registro Imprese e SARI",
      description:
        "Convalida e salva ui_decisions.json nella sola cartella del run; non modifica la pratica e non accede a portali.",
      inputSchema: decisionInput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.apply,
      title: "Applica decisioni alla carta di lavoro",
      description:
        "Scrive applied_decisions.json e aggiorna lo stato del pacchetto. Le modifiche restano richieste di revisione: nessun accesso, firma o invio.",
      inputSchema: decisionInput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
  ];
}

function resources() {
  return [
    {
      uri: WIDGET_URI,
      name: "registro_imprese_sari_review_widget",
      title: "Revisione Registro Imprese e SARI",
      description: "Superficie interattiva per la revisione professionale della pratica.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetMeta(),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "registro-imprese-sari-review-widget.html"),
    "utf8",
  );
}

function requireText(value, field, maxLength = MAX_TEXT_LENGTH) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${field} must be a non-empty string`);
  }
  if (value.length > maxLength) throw new Error(`${field} exceeds ${maxLength} characters`);
  return value.trim();
}

function optionalText(value, field, maxLength = MAX_TEXT_LENGTH) {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error(`${field} must be text when provided`);
  if (value.length > maxLength) throw new Error(`${field} exceeds ${maxLength} characters`);
  return value.trim();
}

function auditPrivacy(value, field = "review_payload") {
  if (Array.isArray(value)) {
    value.forEach((entry, index) => auditPrivacy(entry, `${field}[${index}]`));
    return;
  }
  if (isObject(value)) {
    for (const [key, entry] of Object.entries(value)) {
      if (FORBIDDEN_REVIEW_KEYS.has(key.toLowerCase())) {
        throw new Error(`${field}.${key} is forbidden in the minimized review payload`);
      }
      auditPrivacy(entry, `${field}.${key}`);
    }
    return;
  }
  if (
    typeof value === "string"
    && (EMAIL_RE.test(value) || TAX_CODE_RE.test(value) || VAT_RE.test(value) || PHONE_RE.test(value))
  ) {
    throw new Error(`${field} contains a direct identifier`);
  }
}

function publicRunIntake(value, review) {
  if (!isObject(value)) return null;
  return {
    schema_version: value.schema_version || null,
    plugin: value.plugin || null,
    workflow: value.workflow || null,
    run_id: review.run_id,
    reference_date: value.reference_date || null,
    status: value.status || null,
  };
}

function validateItem(item, index) {
  if (!isObject(item)) throw new Error(`review_payload.items[${index}] must be an object`);
  requireText(item.id, `review_payload.items[${index}].id`, 160);
  requireText(item.title, `review_payload.items[${index}].title`, 400);
  const itemType = requireText(item.item_type, `review_payload.items[${index}].item_type`, 80);
  if (!ITEM_TYPES.has(itemType)) throw new Error(`unsupported item type: ${itemType}`);
  if (!Array.isArray(item.allowed_actions) || !item.allowed_actions.length) {
    throw new Error(`review_payload.items[${index}].allowed_actions must be non-empty`);
  }
  for (const action of item.allowed_actions) {
    if (!ALLOWED_ACTIONS.has(action)) throw new Error(`unsupported allowed action: ${action}`);
  }
  if (item.recommended_action != null && !ALLOWED_ACTIONS.has(item.recommended_action)) {
    throw new Error(`unsupported recommended action for ${item.id}`);
  }
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!isObject(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalValue(value[key])]),
  );
}

function canonicalJson(value) {
  return JSON.stringify(canonicalValue(value));
}

function sha256Bytes(raw) {
  return crypto.createHash("sha256").update(raw).digest("hex");
}

function validateReview(args) {
  if (!isObject(args)) throw new Error("tool arguments must be an object");
  const review = args.review_payload;
  if (!isObject(review)) throw new Error("review_payload must be an object");
  requireText(review.schema_version, "review_payload.schema_version", 20);
  if (review.plugin !== PLUGIN_NAME || review.workflow !== PLUGIN_NAME) {
    throw new Error(`review_payload plugin and workflow must be ${PLUGIN_NAME}`);
  }
  requireText(review.run_id, "review_payload.run_id", 80);
  if (!Array.isArray(review.items)) throw new Error("review_payload.items must be an array");
  if (review.items.length > MAX_ITEMS) throw new Error(`review payload exceeds ${MAX_ITEMS} items`);
  if (review.item_count !== review.items.length) {
    throw new Error("review_payload.item_count must equal review_payload.items.length");
  }
  review.items.forEach(validateItem);
  auditPrivacy(review);
  if (review.filing_authorized !== false || review.filing_status !== "not_filed") {
    throw new Error("review payload must remain not_filed with filing_authorized=false");
  }
  const runIntake = isObject(args.run_intake) ? args.run_intake : null;
  if (runIntake?.run_id != null && runIntake.run_id !== review.run_id) {
    throw new Error("run_intake.run_id must match review_payload.run_id");
  }
  if (runIntake?.plugin != null && runIntake.plugin !== PLUGIN_NAME) {
    throw new Error(`run_intake.plugin must be ${PLUGIN_NAME}`);
  }
  const finalArtifacts = isObject(args.final_artifacts) ? args.final_artifacts : null;
  if (
    finalArtifacts
    && (
      finalArtifacts.plugin !== PLUGIN_NAME
      || finalArtifacts.run_id !== review.run_id
      || finalArtifacts.ready_to_file !== false
      || finalArtifacts.filing_status !== "not_filed"
    )
  ) {
    throw new Error("final_artifacts must match the run and preserve the no-filing boundary");
  }
  const payload = {
    widget_type: "registro_imprese_sari_review",
    run_intake: publicRunIntake(runIntake, review),
    review_payload: review,
    ui_decisions: isObject(args.ui_decisions) ? args.ui_decisions : null,
    final_artifacts: publicFinalArtifacts(finalArtifacts, review),
    decision_policy: {
      save_tool: TOOL_NAMES.save,
      apply_tool: TOOL_NAMES.apply,
      edits_modify_practice_directly: false,
      portal_actions_enabled: false,
      fallback: "copy_json",
    },
  };
  if (Buffer.byteLength(JSON.stringify(payload), "utf8") > MAX_PAYLOAD_BYTES) {
    throw new Error(`widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
}

function publicFinalArtifacts(value, review) {
  const finalArtifacts = isObject(value) ? value : null;
  if (!finalArtifacts) return null;
  return {
    schema_version: finalArtifacts.schema_version || null,
    plugin: finalArtifacts.plugin || null,
    workflow: finalArtifacts.workflow || null,
    run_id: finalArtifacts.run_id || review.run_id,
    status: finalArtifacts.status || null,
    professional_review_required: finalArtifacts.professional_review_required !== false,
    ready_to_file: false,
    filing_status: "not_filed",
    portal_access_performed: false,
    signature_performed: false,
    submission_performed: false,
    blocker_count: Array.isArray(finalArtifacts.blockers) ? finalArtifacts.blockers.length : 0,
    output_count: Array.isArray(finalArtifacts.outputs) ? finalArtifacts.outputs.length : 0,
  };
}

function findGitRoot(start) {
  let current = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(current, ".git"))) return current;
    const parent = path.dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}

function isWithin(parent, child) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function persistenceContextForOutputDir(rawOutputDir, review, runIntakeArg = null) {
  const outputDir = path.resolve(rawOutputDir);
  const gitRoot = findGitRoot(PLUGIN_ROOT);
  if (gitRoot && isWithin(gitRoot, outputDir)) {
    throw new Error("run output directory must remain outside the Git workspace");
  }
  const stat = fs.lstatSync(outputDir);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("run output directory must be a regular directory");
  }
  if (process.platform !== "win32" && (stat.mode & 0o077) !== 0) {
    throw new Error("run output directory must be owner-only (0700)");
  }
  const realOutput = fs.realpathSync(outputDir);
  if (realOutput !== outputDir) throw new Error("run output directory may not traverse symlinks");
  const storedRunPath = path.join(outputDir, "run_intake.json");
  const storedRun = readJson(storedRunPath);
  if (storedRun.plugin !== PLUGIN_NAME || storedRun.run_id !== review.run_id) {
    throw new Error("stored run_intake.json does not match the review payload");
  }
  if (runIntakeArg.plugin != null && runIntakeArg.plugin !== PLUGIN_NAME) {
    throw new Error("run_intake.plugin must match the plugin");
  }
  return { outputDir, storedRun, storedRunPath };
}

function prunePersistenceContexts(now = Date.now()) {
  for (const [token, context] of PERSISTENCE_CONTEXTS.entries()) {
    if (context.expiresAt <= now) PERSISTENCE_CONTEXTS.delete(token);
  }
  while (PERSISTENCE_CONTEXTS.size >= MAX_PERSISTENCE_CONTEXTS) {
    const oldest = PERSISTENCE_CONTEXTS.keys().next().value;
    if (oldest == null) break;
    PERSISTENCE_CONTEXTS.delete(oldest);
  }
}

function issuePersistenceToken(args, review) {
  const context = resolvePersistenceContext(args, review);
  if (!context) return null;
  const verified = verifyStoredPackage(context, review);
  prunePersistenceContexts();
  const token = crypto.randomBytes(32).toString("base64url");
  PERSISTENCE_CONTEXTS.set(token, {
    outputDir: context.outputDir,
    runId: review.run_id,
    reviewHash: verified.reviewHash,
    expiresAt: Date.now() + PERSISTENCE_CONTEXT_TTL_MS,
  });
  return token;
}

function resolvePersistenceContext(args, review) {
  const token = optionalText(args.persistence_token, "persistence_token", 128);
  const runIntakeArg = isObject(args.run_intake) ? args.run_intake : null;
  if (token) {
    if (!PERSISTENCE_TOKEN_RE.test(token)) {
      throw new Error("persistence_token has an invalid format");
    }
    prunePersistenceContexts();
    const storedContext = PERSISTENCE_CONTEXTS.get(token);
    if (!storedContext || storedContext.expiresAt <= Date.now()) {
      throw new Error("persistence_token is unknown or expired; render the review again");
    }
    if (storedContext.runId !== review.run_id) {
      throw new Error("persistence_token belongs to another run");
    }
    const context = persistenceContextForOutputDir(
      storedContext.outputDir,
      review,
      runIntakeArg,
    );
    const storedReviewHash = sha256Bytes(
      fs.readFileSync(path.join(context.outputDir, "review_payload.json")),
    );
    if (storedReviewHash !== storedContext.reviewHash) {
      throw new Error("persistence_token review binding no longer matches the stored package");
    }
    return context;
  }
  const rawOutputDir = typeof runIntakeArg?.output_dir === "string" ? runIntakeArg.output_dir.trim() : "";
  if (!rawOutputDir) return null;
  return persistenceContextForOutputDir(rawOutputDir, review, runIntakeArg);
}

function readJson(filePath) {
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`expected regular JSON file: ${filePath}`);
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJsonAtomic(filePath, value) {
  if (fs.existsSync(filePath) && fs.lstatSync(filePath).isSymbolicLink()) {
    throw new Error(`refusing to replace symbolic link: ${filePath}`);
  }
  const temporary = `${filePath}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, filePath);
  fs.chmodSync(filePath, 0o600);
}

function verifyStoredPackage(context, review) {
  const reviewPath = path.join(context.outputDir, "review_payload.json");
  const reviewBytes = fs.readFileSync(reviewPath);
  const storedReview = JSON.parse(reviewBytes.toString("utf8"));
  if (canonicalJson(storedReview) !== canonicalJson(review)) {
    throw new Error("tool review_payload does not match stored review_payload.json");
  }
  const finalPath = path.join(context.outputDir, "final_artifacts.json");
  const finalArtifacts = readJson(finalPath);
  if (finalArtifacts.plugin !== PLUGIN_NAME || finalArtifacts.run_id !== review.run_id) {
    throw new Error("stored final_artifacts.json does not match the review payload");
  }
  if (finalArtifacts.ready_to_file !== false || finalArtifacts.filing_status !== "not_filed") {
    throw new Error("stored package violates the no-filing boundary");
  }
  const reviewHash = sha256Bytes(reviewBytes);
  if (finalArtifacts.review_payload_sha256 !== reviewHash) {
    throw new Error("stored review payload hash does not match final_artifacts.json");
  }
  const auditPath = path.join(context.outputDir, "practice_validation_audit.json");
  const audit = readJson(auditPath);
  if (audit.plugin !== PLUGIN_NAME || audit.run_id !== review.run_id || audit.status === "schema_error") {
    throw new Error("practice validation audit is missing, mismatched, or invalid");
  }
  if (finalArtifacts.validation_audit_sha256 !== sha256Bytes(fs.readFileSync(auditPath))) {
    throw new Error("practice validation audit hash does not match final_artifacts.json");
  }
  return { reviewHash, finalArtifacts, finalPath, audit };
}

function normalizeRequestedDocuments(value, field) {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value.map((entry, index) => requireText(entry, `${field}[${index}]`, 300));
}

function normalizeDecision(decision, index, itemById, seen, decidedAt) {
  if (!isObject(decision)) throw new Error(`decisions[${index}] must be an object`);
  const itemId = requireText(decision.item_id, `decisions[${index}].item_id`, 160);
  if (seen.has(itemId)) throw new Error(`duplicate decision item_id: ${itemId}`);
  seen.add(itemId);
  const item = itemById.get(itemId);
  if (!item) throw new Error(`unknown decision item_id: ${itemId}`);
  const action = requireText(decision.action, `decisions[${index}].action`, 80);
  if (!ALLOWED_ACTIONS.has(action) || !item.allowed_actions.includes(action)) {
    throw new Error(`action ${action} is not allowed for ${itemId}`);
  }
  const reviewerNote = optionalText(decision.reviewer_note, `decisions[${index}].reviewer_note`);
  const editValue = optionalText(decision.edit_value, `decisions[${index}].edit_value`);
  if (action === "edit" && !editValue) {
    throw new Error(`decisions[${index}].edit_value is required for edit`);
  }
  const requestedDocuments = normalizeRequestedDocuments(
    decision.requested_documents,
    `decisions[${index}].requested_documents`,
  );
  if (action === "request_more_documents" && !requestedDocuments.length) {
    throw new Error(`decisions[${index}].requested_documents is required for document requests`);
  }
  const normalized = {
    item_id: itemId,
    item_type: item.item_type,
    title: item.title,
    action,
    status: ACTION_STATUS[action],
    decided_at: decidedAt,
  };
  if (reviewerNote) normalized.reviewer_note = reviewerNote;
  if (editValue) normalized.edit_value = editValue;
  if (requestedDocuments.length) normalized.requested_documents = requestedDocuments;
  return normalized;
}

function buildUiDecisions(args, review) {
  if (!Array.isArray(args.decisions)) throw new Error("decisions must be an array");
  if (args.decisions.length > review.items.length) throw new Error("too many decisions");
  auditPrivacy(args.decisions, "decisions");
  const itemById = new Map(review.items.map((item) => [item.id, item]));
  const seen = new Set();
  const decidedAt = new Date().toISOString();
  const decisions = args.decisions.map((decision, index) =>
    normalizeDecision(decision, index, itemById, seen, decidedAt),
  );
  const reviewer = optionalText(args.reviewer, "reviewer", 160);
  const decisionSource = optionalText(args.decision_source, "decision_source", 120) || "mcp_widget";
  if (reviewer) auditPrivacy(reviewer, "reviewer");
  auditPrivacy(decisionSource, "decision_source");
  const status = decisions.length === 0
    ? "pending_review"
    : decisions.length === review.items.length
      ? "reviewed"
      : "partial_review";
  const payload = {
    schema_version: review.schema_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    decided_at: decisions.length ? decidedAt : null,
    decision_source: decisionSource,
    review_payload_path: "review_payload.json",
    review_payload_sha256: null,
    decisions,
    decision_count: decisions.length,
    item_count: review.items.length,
    status,
  };
  if (reviewer) payload.reviewer = reviewer;
  return payload;
}

function saveDecisions(args) {
  const widget = validateReview(args);
  const review = widget.review_payload;
  const uiDecisions = buildUiDecisions(args, review);
  const context = resolvePersistenceContext(args, review);
  let storedPath = null;
  if (context) {
    const verified = verifyStoredPackage(context, review);
    uiDecisions.review_payload_sha256 = verified.reviewHash;
    storedPath = path.join(context.outputDir, "ui_decisions.json");
    writeJsonAtomic(storedPath, uiDecisions);
  }
  return {
    ok: true,
    validation_type: "registro_imprese_sari_decisions",
    run_id: review.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted: Boolean(storedPath),
    ui_decisions_path: storedPath ? "ui_decisions.json" : null,
    message: storedPath
      ? `Salvate ${uiDecisions.decision_count} decisioni di revisione.`
      : "Decisioni valide; nessuna cartella di run è stata fornita per il salvataggio.",
    ui_decisions: uiDecisions,
  };
}

function applyDecisions(args) {
  const widget = validateReview(args);
  const review = widget.review_payload;
  const uiDecisions = buildUiDecisions(args, review);
  const context = resolvePersistenceContext(args, review);
  if (!context) {
    return {
      ok: true,
      validation_type: "registro_imprese_sari_application_preview",
      run_id: review.run_id,
      persisted: false,
      message: "Applicazione validata; nessuna cartella di run è stata fornita.",
    };
  }
  const verified = verifyStoredPackage(context, review);
  uiDecisions.review_payload_sha256 = verified.reviewHash;
  const decidedIds = new Set(uiDecisions.decisions.map((decision) => decision.item_id));
  const undecided = review.items
    .filter((item) => !decidedIds.has(item.id))
    .map((item) => ({ item_id: item.id, reason: "decision_missing" }));
  const blockers = [
    ...undecided,
    ...uiDecisions.decisions
      .filter((decision) => decision.action !== "accept")
      .map((decision) => ({
        item_id: decision.item_id,
        action: decision.action,
        reason: decision.status,
      })),
  ];
  const revisions = uiDecisions.decisions
    .filter((decision) => decision.action === "edit")
    .map((decision) => ({
      item_id: decision.item_id,
      status: "revision_required",
      edit_value: decision.edit_value,
      direct_artifact_modification_performed: false,
    }));
  const appliedAt = new Date().toISOString();
  const applicationStatus = blockers.length
    ? "review_incomplete_or_revision_required"
    : "reviewed_no_portal_action";
  const applied = {
    schema_version: review.schema_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    applied_at: appliedAt,
    review_payload_sha256: verified.reviewHash,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    blocker_count: blockers.length,
    revision_required_count: revisions.length,
    application_status: applicationStatus,
    blockers,
    revisions,
    portal_access_performed: false,
    signature_performed: false,
    submission_performed: false,
    ready_to_file: false,
  };
  const updatedFinal = {
    ...verified.finalArtifacts,
    status: verified.finalArtifacts.status,
    ready_to_file: false,
    filing_status: "not_filed",
    portal_access_performed: false,
    signature_performed: false,
    submission_performed: false,
    review_application: {
      applied_at: appliedAt,
      application_status: applicationStatus,
      decision_count: uiDecisions.decision_count,
      blocker_count: blockers.length,
      revision_required_count: revisions.length,
      applied_decisions_path: "applied_decisions.json",
      direct_artifact_modification_performed: false,
    },
  };
  const uiPath = path.join(context.outputDir, "ui_decisions.json");
  const appliedPath = path.join(context.outputDir, "applied_decisions.json");
  writeJsonAtomic(uiPath, uiDecisions);
  writeJsonAtomic(appliedPath, applied);
  writeJsonAtomic(verified.finalPath, updatedFinal);
  const executionTrace = Array.isArray(context.storedRun.execution_trace)
    ? [...context.storedRun.execution_trace]
    : [];
  executionTrace.push({
    step_id: `apply_registro_imprese_sari_decisions_${executionTrace.length + 1}`,
    kind: "deterministic_review_apply",
    command: [TOOL_NAMES.apply],
    execution_location: "local_mcp",
    status: "passed",
    inputs: ["review_payload.json", "ui_decisions.json", "final_artifacts.json"],
    outputs: ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"],
  });
  writeJsonAtomic(context.storedRunPath, {
    ...context.storedRun,
    status: updatedFinal.status,
    execution_trace: executionTrace,
  });
  return {
    ok: true,
    validation_type: "registro_imprese_sari_application",
    run_id: review.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    blocker_count: blockers.length,
    revision_required_count: revisions.length,
    application_status: applicationStatus,
    persisted: true,
    ui_decisions_path: path.basename(uiPath),
    applied_decisions_path: path.basename(appliedPath),
    final_artifacts_path: path.basename(verified.finalPath),
    ready_to_file: false,
    portal_actions_performed: false,
    message: "Decisioni applicate alla sola carta di lavoro; nessun accesso o invio è stato eseguito.",
    applied_decisions: applied,
    final_artifacts: publicFinalArtifacts(updatedFinal, review),
  };
}

function callTool(name, args) {
  if (name === TOOL_NAMES.validate) {
    const payload = validateReview(args);
    return {
      ok: true,
      validation_type: "registro_imprese_sari_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      message: `Payload valido. È possibile chiamare ${TOOL_NAMES.render}.`,
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.render) {
    const payload = validateReview(args);
    const persistenceToken = issuePersistenceToken(args, payload.review_payload);
    return {
      ...payload,
      persistence_available: Boolean(persistenceToken),
      persistence_token: persistenceToken,
    };
  }
  if (name === TOOL_NAMES.save) return saveDecisions(args);
  if (name === TOOL_NAMES.apply) return applyDecisions(args);
  throw new Error(`unknown tool: ${name}`);
}

function toolResult(payload, name) {
  const result = {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
  if (name === TOOL_NAMES.render) result._meta = toolUiMeta();
  return result;
}

function toolError(error) {
  const payload = { ok: false, error: error instanceof Error ? error.message : String(error) };
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: true,
  };
}

function rpcResult(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function handleRpc(message) {
  const id = message.id ?? null;
  const params = isObject(message.params) ? message.params : {};
  try {
    if (message.method === "initialize") {
      return rpcResult(id, {
        protocolVersion: params.protocolVersion || "2024-11-05",
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: { tools: {}, resources: {}, prompts: {} },
        instructions:
          `Call ${TOOL_NAMES.validate} before ${TOOL_NAMES.render}; save/apply use a run-scoped opaque persistence token and never perform portal actions.`,
      });
    }
    if (message.method === "notifications/initialized") return null;
    if (message.method === "tools/list") return rpcResult(id, { tools: toolDefinitions() });
    if (message.method === "tools/call") {
      if (typeof params.name !== "string") return rpcError(id, -32602, "tools/call requires a tool name");
      if (!isObject(params.arguments)) return rpcError(id, -32602, "tools/call arguments must be an object");
      try {
        return rpcResult(id, toolResult(callTool(params.name, params.arguments), params.name));
      } catch (error) {
        return rpcResult(id, toolError(error));
      }
    }
    if (message.method === "resources/list") return rpcResult(id, { resources: resources() });
    if (message.method === "resources/read") {
      if (typeof params.uri !== "string") return rpcError(id, -32602, "resources/read requires a URI");
      return rpcResult(id, {
        contents: [
          {
            uri: params.uri,
            mimeType: WIDGET_MIME_TYPE,
            text: resourceText(params.uri),
            _meta: widgetMeta(),
          },
        ],
      });
    }
    if (message.method === "resources/templates/list") return rpcResult(id, { resourceTemplates: [] });
    if (message.method === "prompts/list") return rpcResult(id, { prompts: [] });
    return rpcError(id, -32601, "method not found");
  } catch (error) {
    return rpcError(id, -32000, error instanceof Error ? error.message : String(error));
  }
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function main() {
  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  lines.on("line", (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      send(rpcError(null, -32700, "parse error"));
      return;
    }
    const response = handleRpc(message);
    if (response !== null && message.id != null) send(response);
  });
}

main();

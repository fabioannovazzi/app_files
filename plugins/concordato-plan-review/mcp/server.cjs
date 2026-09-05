"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const { spawnSync } = require("node:child_process");

const SERVER_NAME = "concordato-plan-review-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const CONCORDATO_PLUGIN_IMPLEMENTATION_PATHS = [
  ".codex-plugin/plugin.json",
  ".app.json",
  ".mcp.json",
  "assets/concordato-plan-review-widget.html",
  "assets/icon.svg",
  "assets/review-workbench-adapter.json",
  "mcp/server.cjs",
  "scripts/apply_review_edits.py",
  "scripts/check_dependencies.py",
  "scripts/concordato_plan_core.py",
  "scripts/concordato_semantic.py",
  "scripts/finalize_output_closure.py",
  "scripts/implementation_bootstrap.py",
  "scripts/output_closure.py",
  "scripts/replay_assurance.py",
  "scripts/review_case_model.py",
  "scripts/review_session.py",
  "scripts/review_source_roles.py",
  "scripts/run_concordato_review.py",
];
const CONCORDATO_SHARED_IMPLEMENTATION_PATHS = [
  "__init__.py",
  "contracts.py",
  "decisions.py",
  "envelope.py",
  "money.py",
  "relationships.py",
  "review_output_transaction.cjs",
  "serialization.py",
];
const CONCORDATO_ASSURANCE_IMPLEMENTATION_ROOT = (() => {
  const vendored = path.join(
    PLUGIN_ROOT,
    "vendor",
    "modules",
    "vera_assurance",
  );
  return fs.existsSync(vendored)
    ? vendored
    : path.resolve(
        PLUGIN_ROOT,
        "..",
        "_shared",
        "vendor",
        "modules",
        "vera_assurance",
      );
})();
validateConcordatoImplementationTree();
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/concordato-plan-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const MAX_MODEL_REVIEW_ITEMS = 25;
const REVIEW_REFERENCE_SCHEMA = "concordato.review_reference.v1";
const TOOL_NAMES = {
  validateReview: "validate_concordato_plan_review",
  renderReview: "render_concordato_plan_review",
  readReviewItems: "read_concordato_plan_review_items",
  saveDecisions: "save_concordato_plan_decisions",
  applyDecisions: "apply_concordato_plan_decisions",
};
const ALLOWED_ACTIONS = new Set([
  "accept",
  "reject",
  "edit",
  "mark_unclear",
  "request_more_documents",
  "skip",
]);
const ACTION_STATUSES = {
  accept: "accepted",
  reject: "rejected",
  edit: "edited",
  mark_unclear: "needs_evidence",
  request_more_documents: "needs_evidence",
  skip: "skipped",
};
const MAX_DECISION_TEXT_LENGTH = 10_000;
const ITEM_TYPES = new Set([
  "source_inventory",
  "source_role_attention",
  "semantic_case_status",
  "procedure_identity",
  "semantic_review_question",
  "semantic_issue",
  "creditor_class_treatment",
  "mechanical_consistency_check",
  "candidate_amount_match",
  "unmatched_plan_amount",
  "extraction_error",
  "review_artifact",
  "codex_review_memo",
]);

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map((entry) => stableJson(entry)).join(",")}]`;
  if (isPlainObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function reviewPayloadContentSha256(reviewPayload) {
  const content = { ...reviewPayload };
  delete content.content_sha256;
  return crypto
    .createHash("sha256")
    .update(stableJson(content), "utf8")
    .digest("hex");
}

function normalizeLanguage(value) {
  const normalized = typeof value === "string" ? value.trim().toLowerCase().replaceAll("_", "-") : "";
  const code = normalized.split("-", 1)[0];
  return code === "es" || code === "spa" ? "es" : "en";
}

function languageFromArgs(inputArgs) {
  if (!isPlainObject(inputArgs)) return "en";
  const reviewPayload = isPlainObject(inputArgs.review_payload) ? inputArgs.review_payload : {};
  const reviewSummary = isPlainObject(reviewPayload.summary) ? reviewPayload.summary : {};
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : {};
  const assumptions = isPlainObject(runIntake.assumptions) ? runIntake.assumptions : {};
  const meta = isPlainObject(inputArgs._meta)
    ? inputArgs._meta
    : isPlainObject(inputArgs.meta)
      ? inputArgs.meta
      : {};
  const candidates = [
    reviewPayload.language,
    reviewSummary.language,
    runIntake.language,
    assumptions.language,
    inputArgs.language,
    inputArgs.locale,
    meta.language,
    meta.locale,
    meta["openai/locale"],
  ];
  const selected = candidates.find((value) => typeof value === "string" && value.trim());
  return normalizeLanguage(selected);
}

function isSpanish(language) {
  return normalizeLanguage(language) === "es";
}

function localizeRuntimeError(message, language) {
  if (!isSpanish(language)) return message;
  const text = String(message || "");
  let match;
  if ((match = text.match(/^(.+) must be a non-empty string$/))) return `${match[1]} debe ser una cadena no vacía`;
  if ((match = text.match(/^(.+) must be a string when provided$/))) return `${match[1]} debe ser una cadena cuando se proporcione`;
  if ((match = text.match(/^(.+) exceeds (\d+) characters$/))) return `${match[1]} supera los ${match[2]} caracteres`;
  if ((match = text.match(/^(.+) must be an object$/))) return `${match[1]} debe ser un objeto`;
  if ((match = text.match(/^(.+) must be an array(?: when provided)?$/))) return `${match[1]} debe ser una matriz`;
  if ((match = text.match(/^(.+) must equal (.+)$/))) return `${match[1]} debe ser igual a ${match[2]}`;
  if ((match = text.match(/^(.+) exceeds (\d+) items$/))) return `${match[1]} supera el límite de ${match[2]} elementos`;
  if ((match = text.match(/^(.+) is not supported(?:: (.+))?$/))) return `${match[1]} no es compatible${match[2] ? `: ${match[2]}` : ""}`;
  if ((match = text.match(/^(.+) contains unsupported action: (.+)$/))) return `${match[1]} contiene una acción no compatible: ${match[2]}`;
  if ((match = text.match(/^(.+) is not allowed for item (.+): (.+)$/))) return `${match[1]} no está permitida para el elemento ${match[2]}: ${match[3]}`;
  if ((match = text.match(/^(.+) is not in review_payload\.items: (.+)$/))) return `${match[1]} no figura en review_payload.items: ${match[2]}`;
  if ((match = text.match(/^(.+) is required when action is edit$/))) return `${match[1]} es obligatorio cuando la acción es edit`;
  if ((match = text.match(/^(.+) cannot exceed (.+)$/))) return `${match[1]} no puede superar ${match[2]}`;
  if ((match = text.match(/^(.+) payload exceeds (\d+) bytes$/i))) return `Los datos de ${match[1]} superan los ${match[2]} bytes`;
  if (text.startsWith("decisions contains duplicate item_id:")) return text.replace("decisions contains duplicate item_id:", "decisions contiene un item_id duplicado:");
  if (text === "run_intake.run_id must match review_payload.run_id") return "run_intake.run_id debe coincidir con review_payload.run_id";
  if (text === "CSV parse failed: unclosed quoted field") return "No se pudo interpretar el CSV: hay un campo entrecomillado sin cerrar";
  if (text === "structured artifact records must be an array") return "Los registros del artefacto estructurado deben ser una matriz";
  if (text === "CSV structured edit requires a header row") return "La edición estructurada del CSV requiere una fila de encabezado";
  if ((match = text.match(/^CSV structured edit missing (.+)$/))) return `En la edición estructurada del CSV falta ${match[1]}`;
  if (text === "JSON structured edit requires an object, array, or explicit records_key array") return "La edición estructurada de JSON requiere un objeto, una matriz o una matriz records_key explícita";
  if (text.endsWith(" native regeneration failed.")) return "No se pudo completar la regeneración nativa del artefacto.";
  return text;
}

function assetDataUrl(fileName, mimeType) {
  const assetBytes = fs.readFileSync(path.join(PLUGIN_ROOT, "assets", fileName));
  return `data:${mimeType};base64,${assetBytes.toString("base64")}`;
}

function icon() {
  return {
    src: assetDataUrl("icon.svg", "image/svg+xml"),
    mimeType: "image/svg+xml",
    sizes: ["24x24"],
  };
}

function objectSchema(properties, required = [], additionalProperties = true) {
  return { type: "object", properties, required, additionalProperties };
}

function toolUiMeta(resourceUri, toolName = null) {
  const componentOnly =
    toolName === TOOL_NAMES.saveDecisions ||
    toolName === TOOL_NAMES.applyDecisions;
  const meta = {
    ui: { resourceUri, visibility: componentOnly ? ["app"] : ["model"] },
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    meta["openai/toolInvocation/invoking"] = "Rendering Concordato Preventivo review";
    meta["openai/toolInvocation/invoked"] = "Rendered Concordato Preventivo review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Concordato Preventivo review for procedure, documents, creditor treatment, feasibility, issues, mechanical checks, and the numerical appendix.",
    "openai/widgetPrefersBorder": false,
    "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
    "openai/widgetDomain": "https://chatgpt.com",
  };
}

function toolDefinitions() {
  const reviewReference = objectSchema(
    {
      schema_version: { type: "string" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      output_dir: { type: "string" },
      review_payload_content_sha256: {
        type: "string",
        pattern: "^[0-9a-f]{64}$",
      },
    },
    [
      "schema_version",
      "workflow",
      "run_id",
      "output_dir",
      "review_payload_content_sha256",
    ],
    false,
  );
  const inputSchema = objectSchema(
    {
      client_engagement: { type: "string", description: "Absolute path to the current portable customer-run context.json." },
      review_reference: reviewReference,
      language: { type: "string", description: "Optional response language hint." },
    },
    ["client_engagement", "review_reference"],
    false,
  );
  const decisionSchema = objectSchema(
    {
      item_id: { type: "string", description: "Review item id from review_payload.items[].id." },
      action: { type: "string", enum: Array.from(ALLOWED_ACTIONS) },
      reviewer_note: { type: "string", description: "Optional reviewer note." },
      edit_value: { type: "string", description: "Required replacement text or value when action is edit." },
      requested_documents: {
        type: "array",
        items: { type: "string" },
        description: "Optional document requests when action is request_more_documents.",
      },
    },
    ["item_id", "action"],
  );
  const decisionInputSchema = objectSchema(
    {
      client_engagement: { type: "string", description: "Absolute path to the current portable customer-run context.json; required for persistence." },
      review_reference: reviewReference,
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: { type: "string", description: "Optional reviewer name or role." },
    },
    ["client_engagement", "review_reference", "decisions"],
    false,
  );
  const reviewItemInputSchema = objectSchema(
    {
      client_engagement: { type: "string", description: "Absolute path to the current portable customer-run context.json." },
      review_reference: reviewReference,
      item_ids: {
        type: "array",
        items: { type: "string" },
        maxItems: MAX_MODEL_REVIEW_ITEMS,
        description: "Optional exact review item ids to inspect.",
      },
      item_types: {
        type: "array",
        items: { type: "string", enum: Array.from(ITEM_TYPES) },
        description: "Optional review item types to inspect.",
      },
      offset: { type: "integer", minimum: 0 },
      limit: {
        type: "integer",
        minimum: 1,
        maximum: MAX_MODEL_REVIEW_ITEMS,
      },
    },
    ["client_engagement", "review_reference"],
    false,
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate Concordato Preventivo review payload",
      description:
        "Validate a reference-bound persisted Concordato Preventivo review before rendering. The complete review rows remain local.",
      inputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.renderReview,
      title: "Render Concordato Preventivo review",
      description:
        "Render the reference-bound Concordato Preventivo review. The model receives counts and status; the component receives the complete local review payload.",
      inputSchema,
      _meta: toolUiMeta(WIDGET_URI, TOOL_NAMES.renderReview),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.readReviewItems,
      title: "Read selected Concordato Preventivo review items",
      description:
        "Read at most 25 purpose-selected review items after semantic confirmation. Technical paths, hashes, and source filenames are omitted or replaced with stable source aliases; substantive professional evidence is preserved.",
      inputSchema: reviewItemInputSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.saveDecisions,
      title: "Save Concordato Preventivo review decisions",
      description:
        "Validate Concordato Preventivo review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
      _meta: toolUiMeta(WIDGET_URI, TOOL_NAMES.saveDecisions),
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.applyDecisions,
      title: "Apply Concordato Preventivo review decisions",
      description:
        "Validate Concordato Preventivo review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
      _meta: toolUiMeta(WIDGET_URI, TOOL_NAMES.applyDecisions),
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
  ];
}

function resources() {
  return [
    {
      uri: WIDGET_URI,
      name: "concordato_plan_review_widget",
      title: "Concordato Preventivo review widget",
      description:
        "Renders Concordato Preventivo payloads with searchable procedure, creditor, issue, evidence, check, and appendix rows.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown Concordato Preventivo review widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "concordato-plan-review-widget.html"),
    "utf8",
  );
}

function payloadBytes(payload) {
  return Buffer.byteLength(JSON.stringify(payload), "utf8");
}

function requireString(value, fieldPath) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${fieldPath} must be a non-empty string`);
  }
}

function boundedOptionalString(value, fieldPath) {
  if (value == null) return "";
  if (typeof value !== "string") {
    throw new Error(`${fieldPath} must be a string when provided`);
  }
  if (value.length > MAX_DECISION_TEXT_LENGTH) {
    throw new Error(`${fieldPath} exceeds ${MAX_DECISION_TEXT_LENGTH} characters`);
  }
  return value.trim();
}

function validateReviewReference(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  requireString(inputArgs.client_engagement, "client_engagement");
  if (!path.isAbsolute(inputArgs.client_engagement)) {
    throw new Error("client_engagement must be an absolute path");
  }
  const reference = inputArgs.review_reference;
  if (!isPlainObject(reference)) throw new Error("review_reference must be an object");
  const expectedKeys = [
    "output_dir",
    "review_payload_content_sha256",
    "run_id",
    "schema_version",
    "workflow",
  ];
  if (stableJson(Object.keys(reference).sort()) !== stableJson(expectedKeys)) {
    throw new Error("review_reference contains unsupported fields");
  }
  if (reference.schema_version !== REVIEW_REFERENCE_SCHEMA) {
    throw new Error(`review_reference.schema_version must equal ${REVIEW_REFERENCE_SCHEMA}`);
  }
  if (reference.workflow !== "concordato-plan-review") {
    throw new Error('review_reference.workflow must equal "concordato-plan-review"');
  }
  requireString(reference.run_id, "review_reference.run_id");
  requireString(reference.output_dir, "review_reference.output_dir");
  if (!/^[0-9a-f]{64}$/.test(reference.review_payload_content_sha256 || "")) {
    throw new Error("review_reference.review_payload_content_sha256 must be a SHA-256 digest");
  }
  return reference;
}

function hydratePersistedReviewArgs(inputArgs) {
  const reference = validateReviewReference(inputArgs);
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir) throw new Error("review_reference does not resolve to a customer-run output");
  const runIntake = readJsonFileIfPresent(path.join(outputDir, "run_intake.json"));
  const reviewPayload = readJsonFileIfPresent(path.join(outputDir, "review_payload.json"));
  const uiDecisions = readJsonFileIfPresent(path.join(outputDir, "ui_decisions.json"));
  const finalArtifacts = readJsonFileIfPresent(path.join(outputDir, "final_artifacts.json"));
  if (
    !isPlainObject(runIntake) ||
    !isPlainObject(reviewPayload) ||
    !isPlainObject(uiDecisions) ||
    !isPlainObject(finalArtifacts)
  ) {
    throw new Error(
      "Persisted run_intake.json, review_payload.json, ui_decisions.json, and final_artifacts.json are required",
    );
  }
  const persistedReference = finalArtifacts.review_reference;
  if (!isPlainObject(persistedReference) || stableJson(persistedReference) !== stableJson(reference)) {
    throw new Error("review_reference does not match the persisted final artifact index");
  }
  if (
    runIntake.run_id !== reference.run_id ||
    reviewPayload.run_id !== reference.run_id ||
    finalArtifacts.run_id !== reference.run_id ||
    runIntake.output_dir !== reference.output_dir ||
    reviewPayload.content_sha256 !== reference.review_payload_content_sha256 ||
    finalArtifacts.review_payload?.content_sha256 !==
      reference.review_payload_content_sha256
  ) {
    throw new Error("review_reference does not match the persisted review state");
  }
  const discoveredContext = concordatoClientEngagementPath(outputDir);
  if (
    !discoveredContext ||
    path.resolve(discoveredContext) !== path.resolve(inputArgs.client_engagement)
  ) {
    throw new Error("client_engagement does not match the persisted customer run");
  }
  return {
    ...inputArgs,
    run_intake: runIntake,
    review_payload: reviewPayload,
    ui_decisions: uiDecisions,
    final_artifacts: finalArtifacts,
  };
}

function validateItem(item, index) {
  if (!isPlainObject(item)) throw new Error(`review_payload.items[${index}] must be an object`);
  requireString(item.id, `review_payload.items[${index}].id`);
  requireString(item.item_type, `review_payload.items[${index}].item_type`);
  requireString(item.title, `review_payload.items[${index}].title`);
  if (!ITEM_TYPES.has(item.item_type)) {
    throw new Error(`review_payload.items[${index}].item_type is not supported: ${item.item_type}`);
  }
  if (!Array.isArray(item.allowed_actions) || item.allowed_actions.length === 0) {
    throw new Error(`review_payload.items[${index}].allowed_actions must be a non-empty array`);
  }
  for (const action of item.allowed_actions) {
    if (!ALLOWED_ACTIONS.has(action)) {
      throw new Error(`review_payload.items[${index}].allowed_actions contains unsupported action: ${action}`);
    }
  }
  if (item.recommended_action != null && !ALLOWED_ACTIONS.has(item.recommended_action)) {
    throw new Error(`review_payload.items[${index}].recommended_action is not supported`);
  }
}

function validateReviewPayload(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const reviewPayload = inputArgs.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.plugin !== "concordato-plan-review") {
    throw new Error('review_payload.plugin must be "concordato-plan-review"');
  }
  requireString(reviewPayload.workflow, "review_payload.workflow");
  requireString(reviewPayload.run_id, "review_payload.run_id");
  requireString(reviewPayload.content_sha256, "review_payload.content_sha256");
  if (!isPlainObject(reviewPayload.assurance) || reviewPayload.assurance.final_ready !== false) {
    throw new Error("review_payload.assurance.final_ready must be false");
  }
  if (!Array.isArray(reviewPayload.items)) {
    throw new Error("review_payload.items must be an array");
  }
  if (reviewPayload.items.length > MAX_ITEMS) {
    throw new Error(`review_payload.items exceeds ${MAX_ITEMS} items`);
  }
  if (reviewPayload.item_count !== reviewPayload.items.length) {
    throw new Error("review_payload.item_count must equal review_payload.items.length");
  }
  reviewPayload.items.forEach((item, index) => validateItem(item, index));
  if (reviewPayload.content_sha256 !== reviewPayloadContentSha256(reviewPayload)) {
    throw new Error("review_payload.content_sha256 is stale");
  }
  const payload = {
    widget_type: "concordato_plan_review",
    client_engagement:
      typeof inputArgs.client_engagement === "string"
        ? inputArgs.client_engagement
        : null,
    review_reference: isPlainObject(inputArgs.review_reference)
      ? inputArgs.review_reference
      : null,
    run_intake: isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null,
    review_payload: reviewPayload,
    ui_decisions: isPlainObject(inputArgs.ui_decisions) ? inputArgs.ui_decisions : null,
    final_artifacts: isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : null,
    decision_policy: {
      save_tool: TOOL_NAMES.saveDecisions,
      apply_tool: TOOL_NAMES.applyDecisions,
      can_persist: Boolean(resolveDecisionOutputPath(inputArgs)),
      fallback: "copy_json",
    },
  };
  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
    throw new Error(`Concordato Preventivo review payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
}

// BEGIN GENERATED REVIEW OUTPUT TRANSACTION
const GENERATED_REVIEW_TRANSACTION_LIMITS = {
  maxEntryCount: 20_000,
  maxFileBytes: 128 * 1024 * 1024,
  maxTotalBytes: 512 * 1024 * 1024,
};

let generatedReviewWriteCounter = 0;
const GENERATED_REVIEW_TRANSACTION_ERROR_KIND = Symbol(
  "generated-review-transaction-error-kind",
);
const GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR = Symbol(
  "generated-review-transaction-operation-error",
);

function generatedReviewPathEntryStat(targetPath) {
  try {
    return fs.lstatSync(targetPath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function generatedReviewPathEntryExists(targetPath) {
  return generatedReviewPathEntryStat(targetPath) !== null;
}

function generatedReviewRemoveExactPath(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry) return;
  if (entry.isDirectory() && !entry.isSymbolicLink()) {
    fs.rmSync(targetPath, {
      recursive: true,
      force: true,
      maxRetries: 3,
      retryDelay: 25,
    });
    return;
  }
  fs.unlinkSync(targetPath);
}

function generatedReviewDirectoryIdentity(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry || !entry.isDirectory() || entry.isSymbolicLink()) {
    throw new Error("Review transaction root must be a real directory.");
  }
  return { dev: entry.dev, ino: entry.ino };
}

function generatedReviewIdentityMatches(entry, identity) {
  return (
    entry != null &&
    entry.isDirectory() &&
    !entry.isSymbolicLink() &&
    entry.dev === identity.dev &&
    entry.ino === identity.ino
  );
}

function generatedReviewTrackedRootsWithinParent(outputParent, identity) {
  generatedReviewValidateRealDirectoryAncestors(outputParent);
  const matches = [];
  for (const name of fs.readdirSync(outputParent).sort()) {
    const candidate = path.join(outputParent, name);
    const entry = generatedReviewPathEntryStat(candidate);
    if (generatedReviewIdentityMatches(entry, identity)) {
      matches.push(candidate);
    }
  }
  return matches;
}

function generatedReviewRemoveTrackedRootWithinParent(
  outputParent,
  expectedPath,
  identity,
) {
  const matches = generatedReviewTrackedRootsWithinParent(
    outputParent,
    identity,
  );
  const expected = path.resolve(expectedPath);
  const relocated = matches.some(
    (candidate) => path.resolve(candidate) !== expected,
  );
  for (const candidate of matches) {
    generatedReviewRemoveExactPath(candidate);
  }
  if (
    generatedReviewTrackedRootsWithinParent(outputParent, identity).length
  ) {
    throw new Error("Review transaction root cleanup did not close.");
  }
  return { found: matches.length > 0, relocated };
}

function generatedReviewValidateRealDirectoryAncestors(targetDir) {
  const resolved = path.resolve(targetDir);
  const parsed = path.parse(resolved);
  let current = parsed.root;
  for (const component of resolved
    .slice(parsed.root.length)
    .split(path.sep)
    .filter(Boolean)) {
    current = path.join(current, component);
    const entry = generatedReviewPathEntryStat(current);
    if (!entry || !entry.isDirectory() || entry.isSymbolicLink()) {
      throw new Error("Review output parent must be a real directory.");
    }
  }
}

function generatedReviewCanonicalRelativePath(value) {
  if (
    typeof value !== "string" ||
    value !== value.trim() ||
    !value ||
    /[\u0000-\u001f\u007f\\]/.test(value) ||
    path.posix.isAbsolute(value)
  ) {
    throw new Error("Review transaction received an invalid output path.");
  }
  const normalized = path.posix.normalize(value);
  if (
    normalized !== value ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../")
  ) {
    throw new Error("Review transaction received an invalid output path.");
  }
  return normalized;
}

function generatedReviewAbsolutePath(root, relativePath) {
  const canonical = generatedReviewCanonicalRelativePath(relativePath);
  return path.join(root, ...canonical.split("/"));
}

function generatedReviewCaptureDirectoryImage(outputDir) {
  const rootEntry = generatedReviewPathEntryStat(outputDir);
  if (!rootEntry || !rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("Review output must be a real directory.");
  }
  const directories = [];
  const files = [];
  let entryCount = 0;
  let totalBytes = 0;
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current).sort()) {
      entryCount += 1;
      if (entryCount > GENERATED_REVIEW_TRANSACTION_LIMITS.maxEntryCount) {
        throw new Error("Review output exceeds the transaction entry limit.");
      }
      const candidate = path.join(current, name);
      const observed = generatedReviewPathEntryStat(candidate);
      if (!observed || observed.isSymbolicLink()) {
        throw new Error("Review output contains an unsafe filesystem entry.");
      }
      const relativePath = path
        .relative(outputDir, candidate)
        .split(path.sep)
        .join("/");
      generatedReviewCanonicalRelativePath(relativePath);
      if (observed.isDirectory()) {
        directories.push({
          path: relativePath,
          mode: observed.mode & 0o7777,
        });
        pending.push(candidate);
        continue;
      }
      if (
        !observed.isFile() ||
        observed.nlink !== 1 ||
        observed.size > GENERATED_REVIEW_TRANSACTION_LIMITS.maxFileBytes
      ) {
        throw new Error("Review output contains an unsupported file.");
      }
      totalBytes += observed.size;
      if (totalBytes > GENERATED_REVIEW_TRANSACTION_LIMITS.maxTotalBytes) {
        throw new Error("Review output exceeds the transaction byte limit.");
      }
      const noFollow = fs.constants.O_NOFOLLOW || 0;
      let descriptor;
      try {
        descriptor = fs.openSync(candidate, fs.constants.O_RDONLY | noFollow);
        const before = fs.fstatSync(descriptor);
        const payload = fs.readFileSync(descriptor);
        const after = fs.fstatSync(descriptor);
        if (
          !before.isFile() ||
          before.nlink !== 1 ||
          before.dev !== observed.dev ||
          before.ino !== observed.ino ||
          before.dev !== after.dev ||
          before.ino !== after.ino ||
          before.size !== after.size ||
          before.mtimeMs !== after.mtimeMs ||
          payload.length !== after.size
        ) {
          throw new Error("Review output changed during transaction capture.");
        }
        files.push({
          path: relativePath,
          mode: after.mode & 0o7777,
          payload,
        });
      } finally {
        if (descriptor !== undefined) fs.closeSync(descriptor);
      }
    }
  }
  directories.sort((left, right) => left.path.localeCompare(right.path));
  files.sort((left, right) => left.path.localeCompare(right.path));
  return {
    rootMode: rootEntry.mode & 0o7777,
    directories,
    files,
  };
}

function generatedReviewImagesEqual(left, right) {
  if (left == null || right == null) return left === right;
  if (
    left.rootMode !== right.rootMode ||
    left.directories.length !== right.directories.length ||
    left.files.length !== right.files.length
  ) {
    return false;
  }
  for (let index = 0; index < left.directories.length; index += 1) {
    const leftEntry = left.directories[index];
    const rightEntry = right.directories[index];
    if (
      leftEntry.path !== rightEntry.path ||
      leftEntry.mode !== rightEntry.mode
    ) {
      return false;
    }
  }
  for (let index = 0; index < left.files.length; index += 1) {
    const leftEntry = left.files[index];
    const rightEntry = right.files[index];
    if (
      leftEntry.path !== rightEntry.path ||
      leftEntry.mode !== rightEntry.mode ||
      !leftEntry.payload.equals(rightEntry.payload)
    ) {
      return false;
    }
  }
  return true;
}

function generatedReviewMaterializeDirectoryImage(targetDir, image) {
  if (generatedReviewPathEntryExists(targetDir)) {
    throw new Error("Review transaction target already exists.");
  }
  fs.mkdirSync(targetDir, { mode: 0o700 });
  const effectiveImage =
    image || { rootMode: 0o755, directories: [], files: [] };
  for (const directory of [...effectiveImage.directories].sort(
    (left, right) =>
      left.path.split("/").length - right.path.split("/").length ||
      left.path.localeCompare(right.path),
  )) {
    fs.mkdirSync(generatedReviewAbsolutePath(targetDir, directory.path), {
      mode: 0o700,
    });
  }
  for (const file of effectiveImage.files) {
    const target = generatedReviewAbsolutePath(targetDir, file.path);
    generatedReviewValidateRealDirectoryAncestors(path.dirname(target));
    const noFollow = fs.constants.O_NOFOLLOW || 0;
    const descriptor = fs.openSync(
      target,
      fs.constants.O_WRONLY |
        fs.constants.O_CREAT |
        fs.constants.O_EXCL |
        noFollow,
      0o600,
    );
    try {
      fs.writeFileSync(descriptor, file.payload);
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    fs.chmodSync(target, file.mode);
  }
  for (const directory of [...effectiveImage.directories].sort(
    (left, right) =>
      right.path.split("/").length - left.path.split("/").length ||
      left.path.localeCompare(right.path),
  )) {
    fs.chmodSync(
      generatedReviewAbsolutePath(targetDir, directory.path),
      directory.mode,
    );
  }
  fs.chmodSync(targetDir, effectiveImage.rootMode);
  const replay = generatedReviewCaptureDirectoryImage(targetDir);
  if (!generatedReviewImagesEqual(effectiveImage, replay)) {
    throw new Error("Review transaction materialization did not replay.");
  }
}

function generatedReviewWritableLeafSignature(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry) return null;
  if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
    throw new Error("Review output contains an unsafe writable file.");
  }
  return [
    entry.dev,
    entry.ino,
    entry.size,
    entry.mtimeMs,
    entry.mode,
  ].join(":");
}

function generatedReviewAtomicWriteFileSync(
  targetPath,
  payload,
  encoding = null,
) {
  generatedReviewValidateRealDirectoryAncestors(path.dirname(targetPath));
  const initialSignature = generatedReviewWritableLeafSignature(targetPath);
  const targetEntry = generatedReviewPathEntryStat(targetPath);
  const targetMode = targetEntry ? targetEntry.mode & 0o7777 : 0o644;
  generatedReviewWriteCounter += 1;
  const tempPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.generated-review-write-${process.pid}-${generatedReviewWriteCounter}`,
  );
  let descriptor;
  let tempExists = false;
  try {
    const noFollow = fs.constants.O_NOFOLLOW || 0;
    descriptor = fs.openSync(
      tempPath,
      fs.constants.O_WRONLY |
        fs.constants.O_CREAT |
        fs.constants.O_EXCL |
        noFollow,
      targetMode,
    );
    tempExists = true;
    fs.writeFileSync(
      descriptor,
      payload,
      encoding ? { encoding } : undefined,
    );
    fs.fchmodSync(descriptor, targetMode);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    if (
      generatedReviewWritableLeafSignature(targetPath) !== initialSignature
    ) {
      throw new Error("Review output changed during an atomic write.");
    }
    generatedReviewValidateRealDirectoryAncestors(path.dirname(targetPath));
    fs.renameSync(tempPath, targetPath);
    tempExists = false;
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    if (tempExists) {
      try {
        fs.unlinkSync(tempPath);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
  }
}

function generatedReviewImageEntryMaps(image) {
  const directoryModes = new Map();
  const files = new Map();
  if (!image) {
    return {
      rootMode: 0o755,
      directoryModes,
      files,
    };
  }
  for (const entry of image.directories) {
    directoryModes.set(entry.path, entry.mode);
  }
  for (const entry of image.files) {
    files.set(entry.path, entry);
  }
  return {
    rootMode: image.rootMode,
    directoryModes,
    files,
  };
}

function generatedReviewAuthorizedPathSet(paths) {
  if (!Array.isArray(paths)) {
    throw new Error("Review transaction requires an authorized write set.");
  }
  const authorized = new Set();
  for (const value of paths) {
    authorized.add(generatedReviewCanonicalRelativePath(value));
  }
  return authorized;
}

function generatedReviewDirectoryIsAuthorized(relativePath, authorized) {
  if (authorized.has(relativePath)) return true;
  const prefix = `${relativePath}/`;
  return Array.from(authorized).some((entry) => entry.startsWith(prefix));
}

function generatedReviewValidateAuthorizedChanges(
  beforeImage,
  afterImage,
  authorizedWritePaths,
) {
  const authorized = generatedReviewAuthorizedPathSet(authorizedWritePaths);
  const before = generatedReviewImageEntryMaps(beforeImage);
  const after = generatedReviewImageEntryMaps(afterImage);
  if (before.rootMode !== after.rootMode) {
    throw new Error("Review transaction changed the output directory mode.");
  }
  const directoryPaths = new Set([
    ...before.directoryModes.keys(),
    ...after.directoryModes.keys(),
  ]);
  for (const relativePath of directoryPaths) {
    const beforeMode = before.directoryModes.get(relativePath);
    const afterMode = after.directoryModes.get(relativePath);
    if (beforeMode === afterMode) continue;
    if (
      beforeMode != null ||
      afterMode == null ||
      !generatedReviewDirectoryIsAuthorized(relativePath, authorized)
    ) {
      throw new Error("Review transaction changed an unauthorized directory.");
    }
  }
  const filePaths = new Set([...before.files.keys(), ...after.files.keys()]);
  for (const relativePath of filePaths) {
    const beforeEntry = before.files.get(relativePath);
    const afterEntry = after.files.get(relativePath);
    const unchanged =
      beforeEntry != null &&
      afterEntry != null &&
      beforeEntry.mode === afterEntry.mode &&
      beforeEntry.payload.equals(afterEntry.payload);
    if (unchanged) continue;
    if (!authorized.has(relativePath)) {
      throw new Error("Review transaction changed an unauthorized file.");
    }
    if (
      beforeEntry != null &&
      afterEntry != null &&
      beforeEntry.mode !== afterEntry.mode
    ) {
      throw new Error("Review transaction changed an artifact mode.");
    }
  }
  return authorized;
}

function generatedReviewTransactionEnvelope(result, authorizedWritePaths) {
  return { result, authorizedWritePaths };
}

function generatedReviewArgsForWorkingOutput(inputArgs, workingOutputDir) {
  const runIntake = isPlainObject(inputArgs.run_intake)
    ? { ...inputArgs.run_intake, output_dir: workingOutputDir }
    : { output_dir: workingOutputDir };
  return { ...inputArgs, run_intake: runIntake };
}

function generatedReviewRewriteOutputPaths(
  value,
  workingOutputDir,
  canonicalOutputDir,
) {
  if (Array.isArray(value)) {
    return value.map((entry) =>
      generatedReviewRewriteOutputPaths(
        entry,
        workingOutputDir,
        canonicalOutputDir,
      ),
    );
  }
  if (value != null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        generatedReviewRewriteOutputPaths(
          entry,
          workingOutputDir,
          canonicalOutputDir,
        ),
      ]),
    );
  }
  if (typeof value !== "string") return value;
  if (value === workingOutputDir) return canonicalOutputDir;
  const prefix = `${workingOutputDir}${path.sep}`;
  if (!value.startsWith(prefix)) return value;
  return path.join(canonicalOutputDir, value.slice(prefix.length));
}

function generatedReviewCollectApplicationWritePaths(result) {
  const paths = new Set([
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
    "run_intake.json",
    "review_handoff.md",
  ]);
  function add(value) {
    if (Array.isArray(value)) {
      for (const entry of value) add(entry);
      return;
    }
    if (typeof value !== "string" || !value) return;
    paths.add(generatedReviewCanonicalRelativePath(value));
  }
  const applied = isPlainObject(result?.applied_decisions)
    ? result.applied_decisions
    : {};
  const finalArtifacts = isPlainObject(result?.final_artifacts)
    ? result.final_artifacts
    : {};
  const application = isPlainObject(finalArtifacts.review_application)
    ? finalArtifacts.review_application
    : {};
  for (const source of [result, applied, application]) {
    for (const fieldName of [
      "revision_paths",
      "target_update_paths",
      "structured_update_paths",
      "native_regeneration_paths",
      "native_regenerated_paths",
      "downstream_regenerated_paths",
      "original_backup_paths",
      "backup_paths",
    ]) {
      add(source?.[fieldName]);
    }
  }
  for (const effect of Array.isArray(applied.effects) ? applied.effects : []) {
    if (!isPlainObject(effect)) continue;
    for (const fieldName of [
      "revision_artifact",
      "original_artifact_backup",
      "derived_native_regeneration_paths",
      "native_regenerated_paths",
    ]) {
      add(effect[fieldName]);
    }
  }
  return Array.from(paths);
}

function generatedReviewWorkflowTransactionOptions(kind, inputArgs) {
  if (typeof workflowReviewTransactionOptions !== "function") return {};
  const options = workflowReviewTransactionOptions(kind, inputArgs);
  if (options == null) return {};
  if (!isPlainObject(options)) {
    throw new Error("Workflow review transaction options must be an object.");
  }
  return options;
}

function generatedReviewRestoreFromTrustedImage(
  outputDir,
  trustedImage,
  outputParent,
) {
  // Recovery is deliberately created only after the untrusted operation has
  // returned. It never depends on a transaction tree that the operation knew.
  const recoveryRoot = fs.mkdtempSync(
    path.join(outputParent, ".generated-review-recovery-"),
  );
  fs.chmodSync(recoveryRoot, 0o700);
  const recoveryIdentity =
    generatedReviewDirectoryIdentity(recoveryRoot);
  const recoveryOutput = path.join(recoveryRoot, "output");
  let restored = false;
  try {
    if (trustedImage) {
      generatedReviewMaterializeDirectoryImage(
        recoveryOutput,
        trustedImage,
      );
      const recoveryReplay =
        generatedReviewCaptureDirectoryImage(recoveryOutput);
      if (!generatedReviewImagesEqual(trustedImage, recoveryReplay)) {
        throw new Error("Review output recovery did not replay.");
      }
    }
    generatedReviewRemoveExactPath(outputDir);
    if (trustedImage) {
      if (generatedReviewPathEntryExists(outputDir)) {
        throw new Error("Review output changed during recovery.");
      }
      fs.renameSync(recoveryOutput, outputDir);
      const canonicalReplay =
        generatedReviewCaptureDirectoryImage(outputDir);
      if (!generatedReviewImagesEqual(trustedImage, canonicalReplay)) {
        throw new Error("Review output recovery did not close.");
      }
    } else if (generatedReviewPathEntryExists(outputDir)) {
      throw new Error("Review output recovery did not restore absence.");
    }
    restored = true;
  } finally {
    const cleanup = generatedReviewRemoveTrackedRootWithinParent(
      outputParent,
      recoveryRoot,
      recoveryIdentity,
    );
    if (!cleanup.found || cleanup.relocated) {
      throw new Error("Review output recovery root changed.");
    }
  }
  if (!restored) {
    throw new Error("Review output recovery did not close.");
  }
}

function generatedReviewCanonicalMatchesTrusted(outputDir, trustedImage) {
  if (!trustedImage) {
    return !generatedReviewPathEntryExists(outputDir);
  }
  try {
    return generatedReviewImagesEqual(
      trustedImage,
      generatedReviewCaptureDirectoryImage(outputDir),
    );
  } catch {
    return false;
  }
}

function generatedReviewRunOutputTransaction(
  outputDir,
  operation,
  options = {},
) {
  if (!outputDir) {
    const envelope = operation({
      workingOutputDir: null,
      canonicalOutputDir: null,
      trustedImage: null,
    });
    if (
      !isPlainObject(envelope) ||
      !Object.hasOwn(envelope, "result") ||
      !Array.isArray(envelope.authorizedWritePaths)
    ) {
      throw new Error("Review transaction operation returned an invalid result.");
    }
    return envelope.result;
  }
  const resolvedOutputDir = path.resolve(outputDir);
  if (resolvedOutputDir === path.parse(resolvedOutputDir).root) {
    throw new Error("Review output transaction rejected the output path.");
  }
  const outputParent = path.dirname(resolvedOutputDir);
  generatedReviewValidateRealDirectoryAncestors(outputParent);
  const outputExisted = generatedReviewPathEntryExists(resolvedOutputDir);
  const trustedImage = outputExisted
    ? generatedReviewCaptureDirectoryImage(resolvedOutputDir)
    : null;
  let transactionRoot = null;
  let transactionIdentity = null;
  let workingOutputDir = null;
  let commitRoot = null;
  let commitIdentity = null;
  let canonicalDetached = false;
  let committed = false;
  try {
    transactionRoot = fs.mkdtempSync(
      path.join(outputParent, ".generated-review-transaction-"),
    );
    fs.chmodSync(transactionRoot, 0o700);
    transactionIdentity =
      generatedReviewDirectoryIdentity(transactionRoot);
    workingOutputDir = path.join(transactionRoot, "working");
    generatedReviewMaterializeDirectoryImage(
      workingOutputDir,
      trustedImage,
    );
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed before transaction start.");
    }
    const envelope = operation({
      workingOutputDir,
      canonicalOutputDir: resolvedOutputDir,
      trustedImage,
    });
    if (
      !isPlainObject(envelope) ||
      !Object.hasOwn(envelope, "result") ||
      !Array.isArray(envelope.authorizedWritePaths)
    ) {
      throw new Error("Review transaction operation returned an invalid result.");
    }
    const workingImage =
      generatedReviewCaptureDirectoryImage(workingOutputDir);
    const authorized = generatedReviewValidateAuthorizedChanges(
      trustedImage,
      workingImage,
      envelope.authorizedWritePaths,
    );
    if (typeof options.validateWholeTree === "function") {
      options.validateWholeTree({
        canonicalOutputDir: resolvedOutputDir,
        workingOutputDir,
        trustedImage,
        workingImage,
        authorizedWritePaths: authorized,
        result: envelope.result,
      });
    }
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed during the transaction.");
    }

    // The validated working tree is now held in parent memory. Close the
    // child-visible tree before creating any commit or recovery material.
    const transactionCleanup =
      generatedReviewRemoveTrackedRootWithinParent(
        outputParent,
        transactionRoot,
        transactionIdentity,
      );
    transactionIdentity = null;
    if (!transactionCleanup.found || transactionCleanup.relocated) {
      throw new Error("Review transaction root changed.");
    }

    commitRoot = fs.mkdtempSync(
      path.join(outputParent, ".generated-review-commit-"),
    );
    fs.chmodSync(commitRoot, 0o700);
    commitIdentity = generatedReviewDirectoryIdentity(commitRoot);
    const commitCandidate = path.join(commitRoot, "candidate");
    const commitBackup = path.join(commitRoot, "trusted-backup");
    generatedReviewMaterializeDirectoryImage(
      commitCandidate,
      workingImage,
    );
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed before transaction commit.");
    }
    if (outputExisted) {
      fs.renameSync(resolvedOutputDir, commitBackup);
      canonicalDetached = true;
    } else if (generatedReviewPathEntryExists(resolvedOutputDir)) {
      throw new Error("Review output changed before transaction commit.");
    }
    if (generatedReviewPathEntryExists(resolvedOutputDir)) {
      throw new Error("Review output changed during transaction commit.");
    }
    fs.renameSync(commitCandidate, resolvedOutputDir);
    committed = true;
    const committedImage =
      generatedReviewCaptureDirectoryImage(resolvedOutputDir);
    if (!generatedReviewImagesEqual(workingImage, committedImage)) {
      throw new Error("Review output changed during transaction commit.");
    }
    const commitCleanup = generatedReviewRemoveTrackedRootWithinParent(
      outputParent,
      commitRoot,
      commitIdentity,
    );
    commitIdentity = null;
    if (!commitCleanup.found || commitCleanup.relocated) {
      throw new Error("Review transaction commit root changed.");
    }
    return envelope.result;
  } catch (operationError) {
    let rollbackFailed = false;
    if (
      canonicalDetached ||
      committed ||
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      try {
        generatedReviewRestoreFromTrustedImage(
          resolvedOutputDir,
          trustedImage,
          outputParent,
        );
      } catch {
        rollbackFailed = true;
      }
    }
    for (const [trackedPath, trackedIdentity] of [
      [transactionRoot, transactionIdentity],
      [commitRoot, commitIdentity],
    ]) {
      if (!trackedPath || !trackedIdentity) continue;
      try {
        generatedReviewRemoveTrackedRootWithinParent(
          outputParent,
          trackedPath,
          trackedIdentity,
        );
      } catch {
        rollbackFailed = true;
      }
    }
    if (rollbackFailed) {
      const rollbackError = new Error(
        options.rollbackFailureMessage ||
          "Review output transaction could not be restored safely.",
      );
      rollbackError[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] = "rollback";
      throw rollbackError;
    }
    const transactionError = new Error(
      options.failureMessage || "Review output transaction failed safely.",
    );
    transactionError[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] = "operation";
    transactionError[GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR] =
      operationError;
    throw transactionError;
  }
}

function generatedReviewMappedOperationFailure(error, options, fallback) {
  if (
    error?.[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] !== "operation" ||
    typeof options.mapOperationError !== "function"
  ) {
    return fallback;
  }
  try {
    const candidate = options.mapOperationError(
      error[GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR],
    );
    if (
      typeof candidate !== "string" ||
      !candidate ||
      candidate.length > 512 ||
      /[\\/\u0000-\u001f\u007f]/.test(candidate) ||
      /Traceback|\bFile\s+["']|file:|~[\\/]/i.test(candidate)
    ) {
      return fallback;
    }
    return candidate;
  } catch {
    return fallback;
  }
}

function withGeneratedReviewOutputTransaction(
  outputDir,
  operation,
  options = {},
) {
  const failureMessage =
    options.failureMessage || "Review output transaction failed safely.";
  const rollbackFailureMessage =
    options.rollbackFailureMessage ||
    "Review output transaction could not be restored safely.";
  try {
    return generatedReviewRunOutputTransaction(outputDir, operation, {
      ...options,
      failureMessage,
      rollbackFailureMessage,
    });
  } catch (error) {
    const rollbackFailed =
      error?.[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] === "rollback";
    const publicMessage = rollbackFailed
      ? rollbackFailureMessage
      : generatedReviewMappedOperationFailure(
          error,
          options,
          failureMessage,
        );
    throw new Error(publicMessage);
  }
}

// Limitation: this is a bounded transaction contract, not an OS sandbox.
// Same-identity code can copy or move data outside the output parent and a
// hostile background descendant can mutate canonical output after return.
// The parent restores canonical bytes/modes from memory and removes a renamed
// transaction sibling by inode inside the bounded output parent; deleting
// arbitrary external copies requires an OS sandbox or a separate identity.
// END GENERATED REVIEW OUTPUT TRANSACTION

function resolveDecisionOutputPath(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  return outputDir ? path.join(outputDir, "ui_decisions.json") : null;
}

function normalizeRequestedDocuments(value, fieldPath) {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error(`${fieldPath} must be an array when provided`);
  return value.map((entry, index) => {
    const documentName = boundedOptionalString(entry, `${fieldPath}[${index}]`);
    if (!documentName) throw new Error(`${fieldPath}[${index}] must be a non-empty string`);
    return documentName;
  });
}

function normalizeDecision(decision, itemById, seenIds, decidedAt, index) {
  // Decision persistence is an audit contract: ids, actions, and edit payloads are mechanically verifiable.
  if (!isPlainObject(decision)) throw new Error(`decisions[${index}] must be an object`);
  const itemId = boundedOptionalString(decision.item_id ?? decision.id, `decisions[${index}].item_id`);
  if (!itemId) throw new Error(`decisions[${index}].item_id must be a non-empty string`);
  if (seenIds.has(itemId)) throw new Error(`decisions contains duplicate item_id: ${itemId}`);
  seenIds.add(itemId);
  const item = itemById.get(itemId);
  if (!item) throw new Error(`decisions[${index}].item_id is not in review_payload.items: ${itemId}`);
  const action = boundedOptionalString(decision.action, `decisions[${index}].action`);
  if (!ALLOWED_ACTIONS.has(action)) throw new Error(`decisions[${index}].action is not supported: ${action}`);
  if (!item.allowed_actions.includes(action)) {
    throw new Error(`decisions[${index}].action is not allowed for item ${itemId}: ${action}`);
  }
  const reviewerNote = boundedOptionalString(
    decision.reviewer_note ?? decision.note,
    `decisions[${index}].reviewer_note`,
  );
  const editValue = boundedOptionalString(
    decision.edit_value ?? decision.user_text,
    `decisions[${index}].edit_value`,
  );
  if (action === "edit" && !editValue) {
    throw new Error(`decisions[${index}].edit_value is required when action is edit`);
  }
  const explicitRequestedDocuments = normalizeRequestedDocuments(
    decision.requested_documents,
    `decisions[${index}].requested_documents`,
  );
  // Missing-document requests copy only explicit review metadata; no semantic evidence inference happens here.
  const requestedDocuments = requestedDocumentsFromReviewContext(
    { action, requested_documents: explicitRequestedDocuments },
    item,
    isPlainObject(item.data) ? item.data : {},
  );
  // Follow-up context copies only explicit item/evidence metadata to make blocker queues actionable.
  const followupContext = followupContextFromReviewContext(
    { action },
    item,
    isPlainObject(item.data) ? item.data : {},
  );
  const normalized = {
    item_id: itemId,
    item_type: item.item_type,
    title: item.title,
    action,
    status: ACTION_STATUSES[action],
    decided_at: decidedAt,
  };
  if (reviewerNote) normalized.reviewer_note = reviewerNote;
  if (editValue) normalized.edit_value = editValue;
  if (requestedDocuments.length) normalized.requested_documents = requestedDocuments;
  if (Object.keys(followupContext).length) normalized.followup_context = followupContext;
  return normalized;
}

function buildUiDecisions(inputArgs) {
  const payload = validateReviewPayload(inputArgs);
  const reviewPayload = payload.review_payload;
  const runIntake = payload.run_intake;
  if (runIntake?.run_id != null && runIntake.run_id !== reviewPayload.run_id) {
    throw new Error("run_intake.run_id must match review_payload.run_id");
  }
  replayPersistedReviewContext(inputArgs);
  if (!Array.isArray(inputArgs.decisions)) throw new Error("decisions must be an array");
  if (inputArgs.decisions.length > reviewPayload.items.length) {
    throw new Error("decisions cannot exceed review_payload.items.length");
  }
  const decidedAt = new Date().toISOString();
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const seenIds = new Set();
  const decisions = inputArgs.decisions.map((decision, index) =>
    normalizeDecision(decision, itemById, seenIds, decidedAt, index),
  );
  const decisionSource =
    boundedOptionalString(inputArgs.decision_source, "decision_source") || "mcp_widget";
  const reviewer = boundedOptionalString(inputArgs.reviewer, "reviewer");
  const currentUiDecisions = isPlainObject(inputArgs.ui_decisions) ? inputArgs.ui_decisions : null;
  const reviewPayloadPath =
    typeof currentUiDecisions?.review_payload_path === "string"
      ? path.basename(currentUiDecisions.review_payload_path)
      : "review_payload.json";
  const status =
    decisions.length === 0
      ? "pending_review"
      : decisions.length === reviewPayload.items.length
        ? "reviewed"
        : "partial_review";
  const uiDecisions = {
    schema_version: reviewPayload.schema_version,
    plugin: reviewPayload.plugin,
    workflow: reviewPayload.workflow,
    run_id: reviewPayload.run_id,
    decided_at: decisions.length ? decidedAt : null,
    decision_source: decisionSource,
    review_payload_path: reviewPayloadPath,
    review_payload_content_sha256: reviewPayload.content_sha256,
    decisions,
    decision_count: decisions.length,
    item_count: reviewPayload.items.length,
    status,
  };
  if (reviewer) uiDecisions.reviewer = reviewer;
  return {
    uiDecisions,
    decisionOutputPath: resolveDecisionOutputPath(inputArgs),
  };
}

const CONCORDATO_CHILD_OUTPUT_MAX_BYTES = 1_000_000;
const CONCORDATO_CHILD_RESULT_MAX_CHARS = 500_000;

function concordatoChildMessages(phase) {
  if (phase === "replay") {
    return {
        start: "Concordato assurance replay could not start.",
        failure: "Concordato assurance replay failed.",
        invalid: "Concordato assurance replay returned an invalid result.",
    };
  }
  if (phase === "finalize") {
    return {
      start: "Concordato successor assurance could not start.",
      failure: "Concordato successor assurance failed.",
      invalid: "Concordato successor assurance returned an invalid result.",
    };
  }
  return {
    start: "Concordato review application could not start.",
    failure: "Concordato review application failed.",
    invalid: "Concordato review application returned an invalid result.",
  };
}

function canonicalConcordatoPathArray(value) {
  if (value == null) return [];
  if (!Array.isArray(value)) return null;
  try {
    return value.map((entry) => generatedReviewCanonicalRelativePath(entry));
  } catch {
    return null;
  }
}

const CONCORDATO_ASSURANCE_GATE_NAMES = [
  "source",
  "preparation",
  "reconciliation",
  "semantic_review",
  "reporting",
  "publication",
];
const CONCORDATO_ASSURANCE_GATE_STATUSES = new Set([
  "passed",
  "failed",
  "blocked",
  "not_assessed",
  "not_applicable",
  "withheld",
]);
const CONCORDATO_ASSURANCE_GATE_DEPENDENCIES = {
  preparation: ["source"],
  reconciliation: ["preparation"],
  semantic_review: ["preparation"],
  reporting: ["reconciliation", "semantic_review"],
  publication: ["reporting"],
};
const CONCORDATO_CANONICAL_IDENTIFIER_RE =
  /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const CONCORDATO_SHA256_RE = /^[0-9a-f]{64}$/;

function concordatoHasExactKeys(value, required, optional = []) {
  if (!isPlainObject(value)) return false;
  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(value);
  return (
    required.every((key) => Object.hasOwn(value, key)) &&
    keys.every((key) => allowed.has(key))
  );
}

function concordatoCanonicalJsonSha256(value) {
  return crypto
    .createHash("sha256")
    .update(stableJson(value), "utf8")
    .digest("hex");
}

function concordatoIsCanonicalIdentifier(value) {
  return (
    typeof value === "string" &&
    CONCORDATO_CANONICAL_IDENTIFIER_RE.test(value)
  );
}

function concordatoIsNonEmptyTrimmedString(value) {
  return (
    typeof value === "string" &&
    Boolean(value) &&
    value === value.trim()
  );
}

function concordatoSafeRelativeArtifactPath(value) {
  if (typeof value !== "string" || !value.trim()) return false;
  const normalized = value.replaceAll("\\", "/");
  if (
    path.posix.isAbsolute(normalized) ||
    /^[A-Za-z]:\//.test(normalized)
  ) {
    return false;
  }
  const parts = normalized.split("/");
  return (
    !parts.includes("..") &&
    !parts.includes("") &&
    normalized === path.posix.normalize(normalized)
  );
}

function concordatoPathIsInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return (
    relative === "" ||
    (!relative.startsWith("..") && !path.isAbsolute(relative))
  );
}

function concordatoReadRegularFileSnapshot(filePath) {
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  let descriptor;
  try {
    descriptor = fs.openSync(
      filePath,
      fs.constants.O_RDONLY | noFollow,
    );
    const before = fs.fstatSync(descriptor);
    if (!before.isFile() || before.nlink !== 1) {
      throw new Error("Concordato assurance artifact is not a regular file.");
    }
    const payload = fs.readFileSync(descriptor);
    const after = fs.fstatSync(descriptor);
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      after.nlink !== 1 ||
      payload.length !== after.size
    ) {
      throw new Error(
        "Concordato assurance artifact changed while it was read.",
      );
    }
    return {
      byteCount: payload.length,
      sha256: crypto.createHash("sha256").update(payload).digest("hex"),
    };
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function concordatoValidateReceiptPath(root, relativePath) {
  const resolvedRoot = path.resolve(root);
  const rootStat = generatedReviewPathEntryStat(resolvedRoot);
  if (
    !rootStat ||
    !rootStat.isDirectory() ||
    rootStat.isSymbolicLink()
  ) {
    throw new Error("Concordato assurance root is unavailable.");
  }
  const target = path.resolve(resolvedRoot, relativePath);
  if (!concordatoPathIsInside(resolvedRoot, target)) {
    throw new Error("Concordato assurance receipt escapes its root.");
  }
  let current = resolvedRoot;
  const parts = path
    .relative(resolvedRoot, target)
    .split(path.sep)
    .filter(Boolean);
  for (let index = 0; index < parts.length; index += 1) {
    current = path.join(current, parts[index]);
    const currentStat = generatedReviewPathEntryStat(current);
    if (!currentStat || currentStat.isSymbolicLink()) {
      throw new Error(
        "Concordato assurance receipt path is missing or linked.",
      );
    }
    if (index < parts.length - 1 && !currentStat.isDirectory()) {
      throw new Error(
        "Concordato assurance receipt has a non-directory ancestor.",
      );
    }
    if (index === parts.length - 1 && !currentStat.isFile()) {
      throw new Error(
        "Concordato assurance receipt is not a regular file.",
      );
    }
  }
  return target;
}

function validateConcordatoArtifactReceiptAgainstRoots(receipt, roots) {
  const required = [
    "schema_version",
    "artifact_id",
    "root_id",
    "role",
    "path",
    "byte_count",
    "sha256",
  ];
  if (
    !concordatoHasExactKeys(receipt, required, ["media_type"]) ||
    receipt.schema_version !== "vera.artifact_receipt.v1" ||
    !concordatoIsCanonicalIdentifier(receipt.artifact_id) ||
    !concordatoIsCanonicalIdentifier(receipt.root_id) ||
    !concordatoIsNonEmptyTrimmedString(receipt.role) ||
    !concordatoSafeRelativeArtifactPath(receipt.path) ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0 ||
    !CONCORDATO_SHA256_RE.test(receipt.sha256 || "") ||
    (Object.hasOwn(receipt, "media_type") &&
      !concordatoIsNonEmptyTrimmedString(receipt.media_type))
  ) {
    throw new Error("Concordato assurance artifact receipt is invalid.");
  }
  const root = roots[receipt.root_id];
  if (!root) {
    throw new Error("Concordato assurance receipt root is unavailable.");
  }
  const artifactPath = concordatoValidateReceiptPath(root, receipt.path);
  const snapshot = concordatoReadRegularFileSnapshot(artifactPath);
  if (
    snapshot.byteCount !== receipt.byte_count ||
    snapshot.sha256 !== receipt.sha256
  ) {
    throw new Error(
      "Concordato assurance receipt does not match current bytes.",
    );
  }
  return receipt;
}

function validateConcordatoGateRegister(value) {
  if (
    !concordatoHasExactKeys(value, [
      "schema_version",
      "gates",
      "report_ready",
    ]) ||
    value.schema_version !== "vera.assurance_gates.v1" ||
    !isPlainObject(value.gates) ||
    Object.keys(value.gates).sort().join(",") !==
      [...CONCORDATO_ASSURANCE_GATE_NAMES].sort().join(",") ||
    typeof value.report_ready !== "boolean"
  ) {
    throw new Error("Concordato assurance gate register is invalid.");
  }
  for (const name of CONCORDATO_ASSURANCE_GATE_NAMES) {
    const gate = value.gates[name];
    if (
      !concordatoHasExactKeys(gate, [
        "status",
        "evidence_refs",
        "limitations",
      ]) ||
      !CONCORDATO_ASSURANCE_GATE_STATUSES.has(gate.status) ||
      !Array.isArray(gate.evidence_refs) ||
      gate.evidence_refs.some(
        (reference) => !concordatoIsCanonicalIdentifier(reference),
      ) ||
      new Set(gate.evidence_refs).size !== gate.evidence_refs.length ||
      !Array.isArray(gate.limitations) ||
      gate.limitations.some(
        (limitation) => !concordatoIsNonEmptyTrimmedString(limitation),
      ) ||
      (gate.status === "passed" && gate.evidence_refs.length === 0)
    ) {
      throw new Error("Concordato assurance gate register is invalid.");
    }
  }
  for (const [name, dependencies] of Object.entries(
    CONCORDATO_ASSURANCE_GATE_DEPENDENCIES,
  )) {
    if (value.gates[name].status !== "passed") continue;
    if (
      dependencies.some(
        (dependency) =>
          !["passed", "not_applicable"].includes(
            value.gates[dependency].status,
          ),
      )
    ) {
      throw new Error("Concordato assurance gate dependency is open.");
    }
  }
  const computedReady = [
    "source",
    "preparation",
    "reconciliation",
    "semantic_review",
    "reporting",
  ].every((name) =>
    ["passed", "not_applicable"].includes(value.gates[name].status),
  );
  if (value.report_ready !== computedReady) {
    throw new Error("Concordato assurance report readiness is stale.");
  }
  return value;
}

function validateConcordatoReviewedDecisionReceipt(value) {
  const required = [
    "schema_version",
    "decision_id",
    "decision_type",
    "status",
    "reviewer_ref",
    "reviewed_on",
    "adapter_id",
    "adapter_version",
    "source_artifact_refs",
    "content",
    "content_sha256",
  ];
  if (
    !concordatoHasExactKeys(value, required) ||
    value.schema_version !== "vera.reviewed_decision_receipt.v1" ||
    !concordatoIsCanonicalIdentifier(value.decision_id) ||
    !concordatoIsCanonicalIdentifier(value.decision_type) ||
    !["draft", "reviewed", "rejected", "superseded"].includes(
      value.status,
    ) ||
    !concordatoIsCanonicalIdentifier(value.reviewer_ref) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.reviewed_on || "") ||
    !concordatoIsCanonicalIdentifier(value.adapter_id) ||
    !concordatoIsCanonicalIdentifier(value.adapter_version) ||
    !Array.isArray(value.source_artifact_refs) ||
    value.source_artifact_refs.length === 0 ||
    value.source_artifact_refs.some(
      (reference) => !concordatoIsCanonicalIdentifier(reference),
    ) ||
    new Set(value.source_artifact_refs).size !==
      value.source_artifact_refs.length ||
    !isPlainObject(value.content) ||
    !CONCORDATO_SHA256_RE.test(value.content_sha256 || "") ||
    concordatoCanonicalJsonSha256(value.content) !== value.content_sha256
  ) {
    throw new Error(
      "Concordato assurance reviewed-decision receipt is invalid.",
    );
  }
  return value;
}

function concordatoAssuranceRoots(outputDir, runIntake) {
  if (
    !Array.isArray(runIntake.input_paths) ||
    runIntake.input_paths.length !== 1 ||
    !concordatoIsNonEmptyTrimmedString(runIntake.input_paths[0])
  ) {
    throw new Error("Concordato assurance source root is unavailable.");
  }
  const sourceRef = runIntake.input_paths[0];
  const contextPath = concordatoClientEngagementPath(outputDir);
  const sourceRoot = path.isAbsolute(sourceRef)
    ? path.resolve(sourceRef)
    : contextPath
      ? path.resolve(path.dirname(contextPath), sourceRef)
      : null;
  if (!sourceRoot) {
    throw new Error("Concordato assurance source root is unavailable.");
  }
  const sourceStat = generatedReviewPathEntryStat(sourceRoot);
  if (
    !sourceStat ||
    !sourceStat.isDirectory() ||
    sourceStat.isSymbolicLink()
  ) {
    throw new Error("Concordato assurance source root is unavailable.");
  }
  return {
    source: sourceRoot,
    run: outputDir,
    implementation: PLUGIN_ROOT,
    assurance_implementation: CONCORDATO_ASSURANCE_IMPLEMENTATION_ROOT,
  };
}

function concordatoExpectedImplementationDirectories(relativePaths) {
  const expected = new Set();
  for (const relativePath of relativePaths) {
    let parent = path.posix.dirname(relativePath);
    while (parent && parent !== ".") {
      expected.add(parent);
      parent = path.posix.dirname(parent);
    }
  }
  return expected;
}

function concordatoScanImplementationRoot(root, scanRoots, rootFiles) {
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("invalid Concordato implementation root");
  }
  const files = new Set();
  const directories = new Set();
  for (const relativePath of rootFiles) {
    const entryPath = path.join(root, relativePath);
    const entry = fs.lstatSync(entryPath);
    if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
      throw new Error("invalid Concordato implementation artifact");
    }
    files.add(relativePath);
  }
  const pending = scanRoots.map((relativePath) => {
    const scanPath = path.join(root, relativePath);
    const entry = fs.lstatSync(scanPath);
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      throw new Error("invalid Concordato implementation directory");
    }
    if (relativePath !== ".") directories.add(relativePath);
    return scanPath;
  });
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current).sort()) {
      const entryPath = path.join(current, name);
      const entry = fs.lstatSync(entryPath);
      const relative = path
        .relative(root, entryPath)
        .split(path.sep)
        .join("/");
      if (entry.isSymbolicLink()) {
        throw new Error("invalid Concordato implementation symlink");
      }
      if (entry.isDirectory()) {
        // Generated caches are inert; the executable source contract stays exact.
        if (name === "__pycache__") continue;
        directories.add(relative);
        pending.push(entryPath);
        continue;
      }
      if (!entry.isFile() || entry.nlink !== 1) {
        throw new Error("invalid Concordato implementation artifact");
      }
      if (name.endsWith(".pyc") || name.endsWith(".pyo")) continue;
      files.add(relative);
    }
  }
  return { files, directories };
}

function validateConcordatoImplementationTree() {
  const pluginTree = concordatoScanImplementationRoot(
    PLUGIN_ROOT,
    [".codex-plugin", "assets", "mcp", "scripts"],
    [".app.json", ".mcp.json"],
  );
  const sharedTree = concordatoScanImplementationRoot(
    CONCORDATO_ASSURANCE_IMPLEMENTATION_ROOT,
    ["."],
    [],
  );
  const expectedPluginDirectories =
    concordatoExpectedImplementationDirectories(
      CONCORDATO_PLUGIN_IMPLEMENTATION_PATHS,
    );
  if (
    stableJson([...pluginTree.files].sort()) !==
      stableJson([...CONCORDATO_PLUGIN_IMPLEMENTATION_PATHS].sort()) ||
    stableJson([...pluginTree.directories].sort()) !==
      stableJson([...expectedPluginDirectories].sort()) ||
    stableJson([...sharedTree.files].sort()) !==
      stableJson([...CONCORDATO_SHARED_IMPLEMENTATION_PATHS].sort()) ||
    sharedTree.directories.size !== 0
  ) {
    throw new Error("Concordato implementation tree is not exact.");
  }
}

function concordatoImplementationContractLocations(_roots) {
  return [
    ...CONCORDATO_PLUGIN_IMPLEMENTATION_PATHS.map((entry) => [
      "implementation",
      entry,
    ]),
    ...CONCORDATO_SHARED_IMPLEMENTATION_PATHS.map((entry) => [
      "assurance_implementation",
      entry,
    ]),
  ];
}

function validateConcordatoAssuranceEnvelopeStructure(envelope, roots) {
  validateConcordatoImplementationTree();
  const required = [
    "schema_version",
    "run_id",
    "workflow_id",
    "workflow_version",
    "artifact_receipts",
    "implementation_artifact_refs",
    "reviewed_decisions",
    "source_qualifications",
    "allocation_ledgers",
    "numeric_evidence_ledgers",
    "gate_register",
    "limitations",
    "content_sha256",
  ];
  if (
    !concordatoHasExactKeys(envelope, required) ||
    envelope.schema_version !== "vera.assurance_envelope.v1" ||
    !concordatoIsCanonicalIdentifier(envelope.run_id) ||
    !concordatoIsCanonicalIdentifier(envelope.workflow_id) ||
    !concordatoIsCanonicalIdentifier(envelope.workflow_version) ||
    !Array.isArray(envelope.artifact_receipts) ||
    !Array.isArray(envelope.implementation_artifact_refs) ||
    envelope.implementation_artifact_refs.length === 0 ||
    !Array.isArray(envelope.reviewed_decisions) ||
    !Array.isArray(envelope.source_qualifications) ||
    !Array.isArray(envelope.allocation_ledgers) ||
    !Array.isArray(envelope.numeric_evidence_ledgers) ||
    !Array.isArray(envelope.limitations) ||
    envelope.limitations.some(
      (value) => !concordatoIsNonEmptyTrimmedString(value),
    ) ||
    !CONCORDATO_SHA256_RE.test(envelope.content_sha256 || "")
  ) {
    throw new Error("Concordato assurance envelope is invalid.");
  }
  const artifacts = envelope.artifact_receipts.map((receipt) =>
    validateConcordatoArtifactReceiptAgainstRoots(receipt, roots),
  );
  const artifactById = new Map();
  const artifactPaths = new Set();
  for (const receipt of artifacts) {
    const pathKey = `${receipt.root_id}:${receipt.path}`;
    if (artifactById.has(receipt.artifact_id) || artifactPaths.has(pathKey)) {
      throw new Error(
        "Concordato assurance artifact identities are not unique.",
      );
    }
    artifactById.set(receipt.artifact_id, receipt);
    artifactPaths.add(pathKey);
  }
  const implementationArtifacts = artifacts.filter((receipt) =>
    ["implementation", "assurance_implementation"].includes(receipt.root_id),
  );
  const implementationLocations = implementationArtifacts.map((receipt) => [
    receipt.root_id,
    receipt.path,
  ]);
  if (
    stableJson(implementationLocations) !==
    stableJson(concordatoImplementationContractLocations(roots))
  ) {
    throw new Error("Concordato assurance implementation set is stale.");
  }
  if (
    envelope.implementation_artifact_refs.some(
      (reference) =>
        !concordatoIsCanonicalIdentifier(reference) ||
        artifactById.get(reference)?.role !== "implementation",
    ) ||
    new Set(envelope.implementation_artifact_refs).size !==
      envelope.implementation_artifact_refs.length ||
    stableJson(envelope.implementation_artifact_refs) !==
      stableJson(
        implementationArtifacts.map((receipt) => receipt.artifact_id),
      )
  ) {
    throw new Error("Concordato assurance implementation binding is invalid.");
  }
  const decisions = envelope.reviewed_decisions.map(
    validateConcordatoReviewedDecisionReceipt,
  );
  const decisionById = new Map();
  for (const decision of decisions) {
    if (
      decisionById.has(decision.decision_id) ||
      decision.source_artifact_refs.some(
        (reference) => artifactById.get(reference)?.role !== "source",
      )
    ) {
      throw new Error(
        "Concordato assurance reviewed-decision binding is invalid.",
      );
    }
    decisionById.set(decision.decision_id, decision);
  }
  const qualificationIds = new Set();
  for (const qualification of envelope.source_qualifications) {
    if (
      !isPlainObject(qualification) ||
      !concordatoIsCanonicalIdentifier(qualification.qualification_id) ||
      qualificationIds.has(qualification.qualification_id)
    ) {
      throw new Error(
        "Concordato assurance source qualification is invalid.",
      );
    }
    qualificationIds.add(qualification.qualification_id);
  }
  const allocationIds = new Set();
  for (const ledger of envelope.allocation_ledgers) {
    if (
      !isPlainObject(ledger) ||
      !concordatoIsCanonicalIdentifier(ledger.ledger_id) ||
      allocationIds.has(ledger.ledger_id)
    ) {
      throw new Error("Concordato assurance allocation ledger is invalid.");
    }
    allocationIds.add(ledger.ledger_id);
  }
  const numericIds = new Set();
  for (const ledger of envelope.numeric_evidence_ledgers) {
    if (
      !isPlainObject(ledger) ||
      !concordatoIsCanonicalIdentifier(ledger.ledger_id) ||
      numericIds.has(ledger.ledger_id)
    ) {
      throw new Error("Concordato assurance numeric ledger is invalid.");
    }
    numericIds.add(ledger.ledger_id);
  }
  const gateRegister = validateConcordatoGateRegister(
    envelope.gate_register,
  );
  const knownReferences = new Set([
    ...artifactById.keys(),
    ...decisionById.keys(),
    ...qualificationIds,
    ...allocationIds,
    ...numericIds,
  ]);
  for (const gate of Object.values(gateRegister.gates)) {
    if (
      gate.evidence_refs.some(
        (reference) => !knownReferences.has(reference),
      )
    ) {
      throw new Error(
        "Concordato assurance gate references unknown evidence.",
      );
    }
  }
  const content = { ...envelope };
  delete content.content_sha256;
  if (
    concordatoCanonicalJsonSha256(content) !== envelope.content_sha256
  ) {
    throw new Error("Concordato assurance envelope digest is stale.");
  }
  return { envelope, gateRegister };
}

const CONCORDATO_OUTPUT_CLOSURE_NAME = "workflow_output_closure.json";
const CONCORDATO_INITIAL_OUTPUT_PATHS = new Set([
  "amount_candidates.csv",
  "assurance_envelope.json",
  "assurance_gates.json",
  "concordato_case_model.json",
  "concordato_preventivo_review_summary.docx",
  "concordato_review_summary.docx",
  "concordato_review_workpaper.xlsx",
  "concordato_semantic_checks.json",
  "concordato_semantic_review.md",
  "concordato_tie_out_workpaper.xlsx",
  "creditor_class_summary.csv",
  "creditor_treatment.csv",
  "exact_amount_matches.csv",
  "final_artifacts.json",
  "inventory.json",
  "liquidity_schedule.csv",
  "numeric_evidence_ledger.json",
  "raw_amount_candidates.csv",
  "review_handoff.md",
  "review_packet.md",
  "review_payload.json",
  "reviewed_decisions.json",
  "run_audit.json",
  "run_intake.json",
  "source_pages.json",
  "source_qualifications.json",
  "source_receipts.json",
  "sources_and_uses.csv",
  "suggested_concordato_case_model.json",
  "suggested_source_role_recipe.json",
  "ui_decisions.json",
  "workbook_sheets.json",
]);
const CONCORDATO_REVIEW_OUTPUT_PATH_FIELDS = [
  "revision_paths",
  "target_update_paths",
  "structured_update_paths",
  "native_regeneration_paths",
  "native_regenerated_paths",
  "original_backup_paths",
];

function concordatoClosedAuthorizedOutputPaths(outputDir) {
  const authorized = new Set(CONCORDATO_INITIAL_OUTPUT_PATHS);
  const applied = readJsonFileIfPresent(
    path.join(outputDir, "applied_decisions.json"),
  );
  if (!isPlainObject(applied)) return authorized;
  authorized.add("applied_decisions.json");
  for (const field of CONCORDATO_REVIEW_OUTPUT_PATH_FIELDS) {
    const raw = applied[field];
    const values = Array.isArray(raw) ? raw : raw == null ? [] : [raw];
    for (const value of values) {
      const relative = generatedReviewCanonicalRelativePath(value);
      if (
        relative === CONCORDATO_OUTPUT_CLOSURE_NAME ||
        relative === "assurance_envelope.json"
      ) {
        throw new Error("Concordato review output authority is invalid.");
      }
      authorized.add(relative);
    }
  }
  return authorized;
}

function concordatoPhysicalOutputPaths(outputDir) {
  const root = path.resolve(outputDir);
  const rootStat = generatedReviewPathEntryStat(root);
  if (!rootStat || !rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("Concordato output closure root is unavailable.");
  }
  const paths = new Set();
  const pending = [root];
  while (pending.length) {
    const directory = pending.pop();
    for (const name of fs.readdirSync(directory)) {
      const current = path.join(directory, name);
      const observed = generatedReviewPathEntryStat(current);
      if (!observed || observed.isSymbolicLink()) {
        throw new Error("Concordato output closure contains an unsafe entry.");
      }
      if (observed.isDirectory()) {
        pending.push(current);
      } else if (observed.isFile() && observed.nlink === 1) {
        paths.add(normalizeRelativePath(path.relative(root, current)));
      } else {
        throw new Error("Concordato output closure contains an unsafe entry.");
      }
    }
  }
  return paths;
}

function validateConcordatoOutputClosure(outputDir, envelope) {
  const closure = readJsonFileIfPresent(
    path.join(outputDir, CONCORDATO_OUTPUT_CLOSURE_NAME),
  );
  const fields = [
    "schema_version",
    "workflow_id",
    "run_id",
    "phase",
    "self_path",
    "previous_closure_content_sha256",
    "declared_paths",
    "artifact_receipts",
    "assurance_envelope_content_sha256",
    "content_sha256",
  ];
  if (
    !concordatoHasExactKeys(closure, fields) ||
    closure.schema_version !==
      "concordato.workflow_output_closure.v1" ||
    closure.workflow_id !== "concordato-plan-review" ||
    closure.self_path !== CONCORDATO_OUTPUT_CLOSURE_NAME ||
    ![
      "initial_run_finalization",
      "review_save_finalization",
      "review_apply_finalization",
    ].includes(closure.phase) ||
    !Array.isArray(closure.declared_paths) ||
    !Array.isArray(closure.artifact_receipts) ||
    !CONCORDATO_SHA256_RE.test(closure.content_sha256 || "") ||
    (closure.previous_closure_content_sha256 !== null &&
      !CONCORDATO_SHA256_RE.test(
        closure.previous_closure_content_sha256 || "",
      ))
  ) {
    throw new Error("Concordato output closure is invalid.");
  }
  if (closure.run_id !== envelope.run_id) {
    throw new Error("Concordato output closure run identity is stale.");
  }
  const declared = closure.declared_paths;
  if (
    declared.some((entry) => !concordatoSafeRelativeArtifactPath(entry)) ||
    stableJson(declared) !==
      stableJson(Array.from(new Set(declared)).sort())
  ) {
    throw new Error("Concordato output closure paths are invalid.");
  }
  const authorized = Array.from(
    concordatoClosedAuthorizedOutputPaths(outputDir),
  ).sort();
  if (stableJson(declared) !== stableJson(authorized)) {
    throw new Error("Concordato output closure allowlist is stale.");
  }
  const physical = Array.from(concordatoPhysicalOutputPaths(outputDir)).sort();
  const expectedPhysical = [...declared, CONCORDATO_OUTPUT_CLOSURE_NAME].sort();
  if (stableJson(physical) !== stableJson(expectedPhysical)) {
    throw new Error("Concordato output closure file set is stale.");
  }
  const roots = { run: path.resolve(outputDir) };
  const receiptPaths = closure.artifact_receipts.map((receipt) => {
    validateConcordatoArtifactReceiptAgainstRoots(receipt, roots);
    return receipt.path;
  });
  if (stableJson(receiptPaths) !== stableJson(declared)) {
    throw new Error("Concordato output closure receipts are incomplete.");
  }
  if (
    closure.assurance_envelope_content_sha256 !== envelope.content_sha256
  ) {
    throw new Error("Concordato output closure envelope binding is stale.");
  }
  const content = { ...closure };
  delete content.content_sha256;
  if (concordatoCanonicalJsonSha256(content) !== closure.content_sha256) {
    throw new Error("Concordato output closure digest is stale.");
  }
  return closure;
}

function validateConcordatoPersistedAssurance(
  outputDir,
  runIntake,
  reviewPayload,
  finalArtifacts,
) {
  const envelope = readJsonFileIfPresent(
    path.join(outputDir, "assurance_envelope.json"),
  );
  const persistedGates = readJsonFileIfPresent(
    path.join(outputDir, "assurance_gates.json"),
  );
  const roots = concordatoAssuranceRoots(outputDir, runIntake);
  const validated = validateConcordatoAssuranceEnvelopeStructure(
    envelope,
    roots,
  );
  if (
    !isPlainObject(persistedGates) ||
    stableJson(persistedGates) !== stableJson(validated.gateRegister) ||
    envelope.run_id !== runIntake.run_id ||
    envelope.run_id !== reviewPayload.run_id
  ) {
    throw new Error("Concordato assurance persisted state is stale.");
  }
  for (const assurance of [
    reviewPayload.assurance,
    finalArtifacts.assurance,
  ]) {
    if (
      !isPlainObject(assurance) ||
      assurance.envelope_path !== "assurance_envelope.json" ||
      assurance.envelope_content_sha256 !== envelope.content_sha256 ||
      stableJson(assurance.gate_register) !==
        stableJson(validated.gateRegister) ||
      assurance.final_ready !== false
    ) {
      throw new Error("Concordato assurance review binding is stale.");
    }
  }
  const closure = validateConcordatoOutputClosure(outputDir, envelope);
  return {
    ok: true,
    run_id: envelope.run_id,
    review_payload_content_sha256: reviewPayload.content_sha256,
    assurance_envelope_content_sha256: envelope.content_sha256,
    workflow_output_closure_content_sha256: closure.content_sha256,
    workflow_output_closure_previous_content_sha256:
      closure.previous_closure_content_sha256,
    workflow_output_closure_phase: closure.phase,
    report_ready: validated.gateRegister.report_ready,
  };
}

function validateConcordatoChildResult(parsed, phase) {
  if (!isPlainObject(parsed) || parsed.ok !== true) return false;
  if (phase === "replay") {
    return true;
  }
  if (phase === "finalize") {
    return (
      ["review_save_finalization", "review_apply_finalization"].includes(
        parsed.phase,
      ) &&
      CONCORDATO_SHA256_RE.test(parsed.content_sha256 || "") &&
      Number.isInteger(parsed.declared_path_count) &&
      parsed.declared_path_count > 0
    );
  }
  return (
    Number.isInteger(parsed.updated_effect_count) &&
    parsed.updated_effect_count >= 0 &&
    canonicalConcordatoPathArray(parsed.native_regenerated_paths) !== null &&
    canonicalConcordatoPathArray(parsed.backup_paths) !== null &&
    isPlainObject(parsed.applied_decisions) &&
    isPlainObject(parsed.final_artifacts)
  );
}

function runConcordatoChild(args, phase) {
  const messages = concordatoChildMessages(phase);
  const python = concordatoChildPython();
  if (!python) throw new Error(messages.start);
  let completed;
  try {
    completed = spawnSync(python.executable, ["-I", "-B", ...args], {
      cwd: PLUGIN_ROOT,
      encoding: "utf8",
      env: python.environment,
      maxBuffer: CONCORDATO_CHILD_OUTPUT_MAX_BYTES,
    });
  } catch {
    throw new Error(messages.start);
  }
  if (completed.error) throw new Error(messages.start);
  if (completed.status !== 0) throw new Error(messages.failure);
  const stdout =
    typeof completed.stdout === "string" ? completed.stdout : "";
  const output = stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  if (!output || output.length > CONCORDATO_CHILD_RESULT_MAX_CHARS) {
    throw new Error(messages.invalid);
  }
  let parsed;
  try {
    parsed = JSON.parse(output);
  } catch {
    throw new Error(messages.invalid);
  }
  if (!validateConcordatoChildResult(parsed, phase)) {
    throw new Error(messages.invalid);
  }
  return parsed;
}

function finalizeConcordatoWorkingOutput(outputDir, phase) {
  const script = path.join(
    PLUGIN_ROOT,
    "scripts",
    "finalize_output_closure.py",
  );
  const clientEngagement = concordatoClientEngagementPath(outputDir);
  if (!clientEngagement) {
    throw new Error("Concordato customer-run context is unavailable.");
  }
  return runConcordatoChild(
    [
      script,
      "--output-dir",
      outputDir,
      "--client-engagement",
      clientEngagement,
      "--persistent-output-dir",
      concordatoPersistentOutputDir(clientEngagement),
      "--phase",
      phase,
    ],
    "finalize",
  );
}

function replayPersistedReviewContext(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir) return null;
  const persistedRunIntake = readJsonFileIfPresent(path.join(outputDir, "run_intake.json"));
  const persistedReviewPayload = readJsonFileIfPresent(path.join(outputDir, "review_payload.json"));
  const persistedFinalArtifacts = readJsonFileIfPresent(
    path.join(outputDir, "final_artifacts.json"),
  );
  if (
    !isPlainObject(persistedRunIntake) ||
    !isPlainObject(persistedReviewPayload) ||
    !isPlainObject(persistedFinalArtifacts)
  ) {
    throw new Error(
      "Persisted run_intake.json, review_payload.json, and final_artifacts.json are required before review writes",
    );
  }
  const comparablePersistedRunIntake = {
    ...persistedRunIntake,
    output_dir: inputArgs.run_intake?.output_dir,
  };
  if (
    stableJson(comparablePersistedRunIntake) !==
    stableJson(inputArgs.run_intake)
  ) {
    throw new Error("Caller run_intake does not match the persisted run intake");
  }
  if (stableJson(persistedReviewPayload) !== stableJson(inputArgs.review_payload)) {
    throw new Error("Caller review_payload does not match the persisted review payload");
  }
  if (
    isPlainObject(inputArgs.final_artifacts) &&
    stableJson(persistedFinalArtifacts) !== stableJson(inputArgs.final_artifacts)
  ) {
    throw new Error("Caller final_artifacts does not match the persisted final artifacts");
  }
  const replayScript = path.join(PLUGIN_ROOT, "scripts", "replay_assurance.py");
  const clientEngagement = concordatoClientEngagementPath(outputDir);
  if (!clientEngagement) {
    throw new Error("Concordato customer-run context is unavailable.");
  }
  const replay = runConcordatoChild(
    [
      replayScript,
      "--output-dir",
      outputDir,
      "--client-engagement",
      clientEngagement,
      "--persistent-output-dir",
      concordatoPersistentOutputDir(clientEngagement),
    ],
    "replay",
  );
  if (!isPlainObject(replay) || replay.ok !== true) {
    throw new Error(
      "Concordato assurance replay returned an invalid result.",
    );
  }
  try {
    return validateConcordatoPersistedAssurance(
      outputDir,
      persistedRunIntake,
      persistedReviewPayload,
      persistedFinalArtifacts,
    );
  } catch {
    throw new Error(
      "Concordato assurance replay returned an invalid result.",
    );
  }
}

function reviewIntegerOrZero(value) {
  return Number.isInteger(value) ? value : 0;
}

function reviewResponseMatches(result, expected) {
  if (!isPlainObject(result) || !isPlainObject(expected)) return false;
  return (
    stableJson(Object.keys(result).sort()) ===
      stableJson(Object.keys(expected).sort()) &&
    Object.keys(expected).every(
      (key) => stableJson(result[key]) === stableJson(expected[key]),
    )
  );
}

const CONCORDATO_REVIEW_TRANSACTION_STATE = Symbol(
  "concordato-review-transaction-state",
);

function cloneConcordatoReviewTransactionValue(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function concordatoReviewTransactionJsonFromImage(image, relativePath) {
  const entry = image?.files?.find((candidate) => candidate.path === relativePath);
  if (!entry) return null;
  try {
    const parsed = JSON.parse(entry.payload.toString("utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function initializeConcordatoReviewTransactionState(
  state,
  trustedImage,
  inputArgs,
) {
  state.baselinePaths = new Set(
    Array.isArray(trustedImage?.files)
      ? trustedImage.files.map((entry) => entry.path)
      : [],
  );
  state.baselineRunIntake =
    concordatoReviewTransactionJsonFromImage(
      trustedImage,
      "run_intake.json",
    ) ||
    (isPlainObject(inputArgs.run_intake)
      ? cloneConcordatoReviewTransactionValue(inputArgs.run_intake)
      : null);
  state.baselineOutputClosure =
    concordatoReviewTransactionJsonFromImage(
      trustedImage,
      CONCORDATO_OUTPUT_CLOSURE_NAME,
    );
  state.childWritePaths = [];
}

function concordatoReviewParentWritePaths(
  state,
  revisionOutputs,
  targetOutputs,
  backupOutputs,
  runIntakePath,
) {
  const paths = new Set([
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
  ]);
  for (const output of [...revisionOutputs, ...targetOutputs]) {
    paths.add(generatedReviewCanonicalRelativePath(output.path));
  }
  for (const output of backupOutputs) {
    const relativePath = generatedReviewCanonicalRelativePath(output.path);
    if (!state.baselinePaths.has(relativePath)) paths.add(relativePath);
  }
  for (const relativePath of state.childWritePaths) {
    paths.add(generatedReviewCanonicalRelativePath(relativePath));
  }
  if (runIntakePath) paths.add("run_intake.json");
  if (state.expectedReviewHandoffContent != null) {
    paths.add("review_handoff.md");
  }
  return Array.from(paths);
}

function concordatoFinalArtifactsWithCurrentReceipts(
  finalArtifacts,
  outputDir,
) {
  const expected = cloneConcordatoReviewTransactionValue(finalArtifacts);
  if (!Array.isArray(expected?.outputs)) {
    throw new Error("Concordato final artifact index is invalid.");
  }
  expected.outputs = expected.outputs.map((output) => {
    if (!isPlainObject(output)) {
      throw new Error("Concordato final artifact index is invalid.");
    }
    const relative = generatedReviewCanonicalRelativePath(output.path);
    const snapshot = concordatoReadRegularFileSnapshot(
      path.join(outputDir, relative),
    );
    return {
      ...output,
      size_bytes: snapshot.byteCount,
      sha256: snapshot.sha256,
    };
  });
  return expected;
}

function validateConcordatoParentTransactionState(
  kind,
  state,
  workingOutputDir,
  authorizedWritePaths,
  persistedUiDecisions,
  persistedAppliedDecisions = null,
  persistedFinalArtifacts = null,
) {
  if (!state?.complete) {
    throw new Error("Concordato parent transaction state is incomplete.");
  }
  const expectedAuthorized = [...state.authorizedWritePaths].sort();
  const observedAuthorized = Array.from(authorizedWritePaths).sort();
  if (
    stableJson(expectedAuthorized) !== stableJson(observedAuthorized)
  ) {
    throw new Error("Concordato write authorization did not close.");
  }
  if (
    stableJson(persistedUiDecisions) !==
    stableJson(state.expectedUiDecisions)
  ) {
    throw new Error("Concordato UI receipt did not close.");
  }
  if (kind === "apply") {
    const expectedFinalArtifacts =
      concordatoFinalArtifactsWithCurrentReceipts(
        state.expectedFinalArtifacts,
        workingOutputDir,
      );
    if (
      stableJson(persistedAppliedDecisions) !==
        stableJson(state.expectedAppliedDecisions) ||
      stableJson(persistedFinalArtifacts) !==
        stableJson(expectedFinalArtifacts)
    ) {
      throw new Error("Concordato parent application did not close.");
    }
    if (state.expectedRunIntake != null) {
      const persistedRunIntake = readJsonFileIfPresent(
        path.join(workingOutputDir, "run_intake.json"),
      );
      if (
        stableJson(persistedRunIntake) !==
        stableJson(state.expectedRunIntake)
      ) {
        throw new Error("Concordato run receipt did not close.");
      }
    }
    if (state.expectedReviewHandoffContent != null) {
      const handoffPath = path.join(workingOutputDir, "review_handoff.md");
      if (
        !fs.existsSync(handoffPath) ||
        fs.readFileSync(handoffPath, "utf8") !==
          state.expectedReviewHandoffContent
      ) {
        throw new Error("Concordato review handoff did not close.");
      }
    }
  }
}

function validateConcordatoReviewTransaction(
  kind,
  inputArgs,
  context,
  parentState,
) {
  const {
    canonicalOutputDir,
    workingOutputDir,
    workingImage,
    authorizedWritePaths,
    result,
  } = context;
  if (!isPlainObject(result) || result.ok !== true || result.persisted !== true) {
    throw new Error("Concordato review transaction result is invalid.");
  }
  const requiredPaths =
    kind === "save"
      ? ["ui_decisions.json"]
      : ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
  const filePaths = new Set(workingImage.files.map((entry) => entry.path));
  if (!requiredPaths.every((relativePath) => filePaths.has(relativePath))) {
    throw new Error("Concordato review transaction is incomplete.");
  }
  const persistedUiDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "ui_decisions.json"),
  );
  if (!isPlainObject(persistedUiDecisions)) {
    throw new Error("Concordato review transaction is incomplete.");
  }
  if (kind === "save") {
    validateConcordatoParentTransactionState(
      kind,
      parentState,
      workingOutputDir,
      authorizedWritePaths,
      persistedUiDecisions,
    );
    const language = languageFromArgs(inputArgs);
    const expectedResult = {
      ok: true,
      validation_type: "concordato_plan_decisions",
      run_id: persistedUiDecisions?.run_id,
      decision_count: persistedUiDecisions?.decision_count,
      item_count: persistedUiDecisions?.item_count,
      status: persistedUiDecisions?.status,
      persisted: true,
      ui_decisions_path: path.join(
        canonicalOutputDir,
        "ui_decisions.json",
      ),
      message: isSpanish(language)
        ? `Se guardaron ${persistedUiDecisions?.decision_count} decisiones de revisión del concordato preventivo.`
        : `Saved ${persistedUiDecisions?.decision_count} Concordato Preventivo review decisions.`,
      ui_decisions: persistedUiDecisions,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Concordato saved decisions did not close.");
    }
  } else {
    const persistedAppliedDecisions = readJsonFileIfPresent(
      path.join(workingOutputDir, "applied_decisions.json"),
    );
    const persistedFinalArtifacts = readJsonFileIfPresent(
      path.join(workingOutputDir, "final_artifacts.json"),
    );
    if (
      !isPlainObject(persistedAppliedDecisions) ||
      !isPlainObject(persistedFinalArtifacts)
    ) {
      throw new Error("Concordato review transaction is incomplete.");
    }
    result.final_artifacts =
      concordatoFinalArtifactsWithCurrentReceipts(
        result.final_artifacts,
        workingOutputDir,
      );
    validateConcordatoParentTransactionState(
      kind,
      parentState,
      workingOutputDir,
      authorizedWritePaths,
      persistedUiDecisions,
      persistedAppliedDecisions,
      persistedFinalArtifacts,
    );
    if (
      stableJson(persistedAppliedDecisions) !==
        stableJson(result.applied_decisions) ||
      stableJson(persistedFinalArtifacts) !==
        stableJson(result.final_artifacts)
    ) {
      throw new Error("Concordato applied decisions did not close.");
    }
    if (
      persistedUiDecisions.run_id !== persistedAppliedDecisions.run_id ||
      persistedUiDecisions.decision_count !==
        persistedAppliedDecisions.decision_count ||
      stableJson(persistedUiDecisions.decisions) !==
        stableJson(persistedAppliedDecisions.decisions)
    ) {
      throw new Error("Concordato review decision state did not close.");
    }
    if (
      persistedFinalArtifacts.final_ready !== false ||
      persistedFinalArtifacts.status === "final_ready" ||
      persistedFinalArtifacts.review_status === "final_ready" ||
      persistedAppliedDecisions.application_status === "final_ready"
    ) {
      throw new Error("Concordato professional authority was not withheld.");
    }
    const language = languageFromArgs(inputArgs);
    const expectedResult = {
      ok: true,
      validation_type: "concordato_plan_application",
      run_id: persistedAppliedDecisions.run_id,
      decision_count: persistedAppliedDecisions.decision_count,
      item_count: persistedAppliedDecisions.item_count,
      blocker_count: persistedAppliedDecisions.blocker_count,
      revision_count: persistedAppliedDecisions.revision_count,
      target_update_count: persistedAppliedDecisions.target_update_count,
      structured_update_count:
        persistedAppliedDecisions.structured_update_count,
      native_regeneration_count:
        persistedAppliedDecisions.native_regeneration_count,
      native_regenerated_count: reviewIntegerOrZero(
        persistedAppliedDecisions.native_regenerated_count,
      ),
      application_status: persistedAppliedDecisions.application_status,
      persisted: true,
      ui_decisions_path: path.join(
        canonicalOutputDir,
        "ui_decisions.json",
      ),
      applied_decisions_path: path.join(
        canonicalOutputDir,
        "applied_decisions.json",
      ),
      final_artifacts_path: path.join(
        canonicalOutputDir,
        "final_artifacts.json",
      ),
      run_intake_path: path.join(canonicalOutputDir, "run_intake.json"),
      message: isSpanish(language)
        ? `Se aplicaron ${persistedAppliedDecisions.decision_count} decisiones de revisión del concordato preventivo.`
        : `Applied ${persistedAppliedDecisions.decision_count} Concordato Preventivo review decisions.`,
      applied_decisions: persistedAppliedDecisions,
      final_artifacts: persistedFinalArtifacts,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Concordato response did not close.");
    }
  }
  const persistedRunIntake = readJsonFileIfPresent(
    path.join(workingOutputDir, "run_intake.json"),
  );
  const persistedReviewPayload = readJsonFileIfPresent(
    path.join(workingOutputDir, "review_payload.json"),
  );
  const persistedFinalArtifacts = readJsonFileIfPresent(
    path.join(workingOutputDir, "final_artifacts.json"),
  );
  if (
    !isPlainObject(persistedRunIntake) ||
    !isPlainObject(persistedReviewPayload) ||
    !isPlainObject(persistedFinalArtifacts)
  ) {
    throw new Error("Concordato successor assurance state is incomplete.");
  }
  const successor = validateConcordatoPersistedAssurance(
    workingOutputDir,
    persistedRunIntake,
    persistedReviewPayload,
    persistedFinalArtifacts,
  );
  const expectedPhase =
    kind === "save"
      ? "review_save_finalization"
      : "review_apply_finalization";
  if (successor.workflow_output_closure_phase !== expectedPhase) {
    throw new Error("Concordato successor assurance phase is stale.");
  }
  if (
    !isPlainObject(parentState.baselineOutputClosure) ||
    successor.workflow_output_closure_previous_content_sha256 !==
      parentState.baselineOutputClosure.content_sha256
  ) {
    throw new Error("Concordato successor assurance chain is stale.");
  }
}

function workflowReviewTransactionOptions(kind, inputArgs, parentState) {
  return {
    validateWholeTree: (context) =>
      validateConcordatoReviewTransaction(
        kind,
        inputArgs,
        context,
        parentState,
      ),
    mapOperationError: (error) => error?.message,
  };
}

function saveDecisionPayload(inputArgs) {
  const canonicalOutputDir = resolveRunOutputDir(inputArgs);
  if (!canonicalOutputDir) return saveDecisionPayloadWrites(inputArgs);
  preflightClientWorkflowRun(
    canonicalOutputDir,
    inputArgs?.review_payload?.run_id,
  );
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "save",
    inputArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeConcordatoReviewTransactionState(
        parentState,
        trustedImage,
        inputArgs,
      );
      const workingArgs = generatedReviewArgsForWorkingOutput(
        inputArgs,
        workingOutputDir,
      );
      Object.defineProperty(workingArgs, CONCORDATO_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = saveDecisionPayloadWrites(workingArgs);
      finalizeConcordatoWorkingOutput(
        workingOutputDir,
        "review_save_finalization",
      );
      parentState.authorizedWritePaths = Array.from(
        new Set([
          ...parentState.authorizedWritePaths,
          "workflow_output_closure.json",
        ]),
      );
      const canonicalResult = generatedReviewRewriteOutputPaths(
        workingResult,
        workingOutputDir,
        canonicalOutputDir,
      );
      return generatedReviewTransactionEnvelope(
        canonicalResult,
        parentState.authorizedWritePaths,
      );
    },
    {
      ...workflowOptions,
      failureMessage:
        "Concordato review save transaction failed safely.",
      rollbackFailureMessage:
        "Concordato review save transaction could not be restored safely.",
    },
  );
}

function saveDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[CONCORDATO_REVIEW_TRANSACTION_STATE] || null;
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  const language = languageFromArgs(inputArgs);
  let persisted = false;
  if (decisionOutputPath) {
    fs.mkdirSync(path.dirname(decisionOutputPath), { recursive: true });
    generatedReviewAtomicWriteFileSync(
      decisionOutputPath,
      `${JSON.stringify(uiDecisions, null, 2)}\n`,
      "utf8",
    );
    persisted = true;
  }
  const result = {
    ok: true,
    validation_type: "concordato_plan_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? decisionOutputPath : null,
    message: persisted
      ? isSpanish(language)
        ? `Se guardaron ${uiDecisions.decision_count} decisiones de revisión del concordato preventivo.`
        : `Saved ${uiDecisions.decision_count} Concordato Preventivo review decisions.`
      : isSpanish(language)
        ? "Las decisiones son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
        : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneConcordatoReviewTransactionValue(uiDecisions);
    parentState.authorizedWritePaths = ["ui_decisions.json"];
    parentState.complete = true;
  }
  return result;
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const reviewReference = isPlainObject(inputArgs.review_reference)
    ? inputArgs.review_reference
    : null;
  const outputDir =
    typeof runIntake?.output_dir === "string"
      ? runIntake.output_dir.trim()
      : typeof reviewReference?.output_dir === "string"
        ? reviewReference.output_dir.trim()
        : "";
  if (!outputDir) return null;
  if (path.isAbsolute(outputDir)) return path.resolve(outputDir);
  const contextValue =
    typeof inputArgs.client_engagement === "string"
      ? inputArgs.client_engagement.trim()
      : "";
  if (!contextValue || !path.isAbsolute(contextValue)) return null;
  const runRoot = path.dirname(path.resolve(contextValue));
  const resolved = path.resolve(runRoot, outputDir);
  const relative = path.relative(runRoot, resolved);
  if (
    relative === "" ||
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error("Concordato output reference leaves the customer run.");
  }
  return resolved;
}

function concordatoClientEngagementPath(outputDir) {
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    const contextStat = generatedReviewPathEntryStat(contextPath);
    if (
      contextStat &&
      contextStat.isFile() &&
      !contextStat.isSymbolicLink()
    ) {
      return contextPath;
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) return null;
    candidate = parent;
  }
}

function concordatoPersistentOutputDir(clientEngagement) {
  return path.join(path.dirname(clientEngagement), "outputs");
}

function resolveAppliedDecisionOutputPath(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  return outputDir ? path.join(outputDir, "applied_decisions.json") : null;
}

function resolveFinalArtifactsOutputPath(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  return outputDir ? path.join(outputDir, "final_artifacts.json") : null;
}

function shortString(value) {
  return typeof value === "string" ? value.trim() : "";
}

const REVISION_TEXT_EXTENSIONS = new Set([
  ".htm",
  ".html",
  ".md",
  ".sql",
  ".txt",
  ".xml",
  ".yaml",
  ".yml",
]);

const DIRECT_TEXT_UPDATE_EXTENSIONS = new Set([
  ".htm",
  ".html",
  ".md",
  ".sql",
  ".txt",
  ".xml",
  ".yaml",
  ".yml",
]);

const STRUCTURED_UPDATE_EXTENSIONS = new Set([".csv", ".json", ".jsonl"]);

const NATIVE_REGENERATION_EXTENSIONS = new Set([
  ".docx",
  ".pdf",
  ".pptx",
  ".xls",
  ".xlsm",
  ".xlsx",
]);

const DERIVED_NATIVE_REGENERATION_TARGETS = new Map([
  ["check_results.csv", ["check_results.xlsx"]],
  ["codex_run_review.md", ["concordato_preventivo_review_summary.docx"]],
  ["reconciliation_matches.csv", ["journal_bank_reconciliation.xlsx"]],
]);

function safePathSegment(value, fallback) {
  const cleaned = shortString(value)
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return cleaned || fallback;
}

function revisionExtension(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return REVISION_TEXT_EXTENSIONS.has(extension) ? extension : ".txt";
}

function revisionRelativePath(effect) {
  const extension = revisionExtension(effect.target_artifact);
  const targetArtifact = shortString(effect.target_artifact);
  const targetExtension = path.extname(targetArtifact) || extension;
  const sourceBase = path.basename(targetArtifact || "review-item", targetExtension);
  const base = safePathSegment(sourceBase, "review-item");
  const itemId = safePathSegment(effect.item_id, "item");
  return path.join("revisions", `${base}__${itemId}${extension}`).split(path.sep).join("/");
}

function normalizeRelativePath(filePath) {
  return filePath.split(path.sep).join("/");
}

function artifactPathKey(value) {
  return normalizeRelativePath(shortString(value)).replace(/\\/g, "/").replace(/^\.\//, "");
}

function resolveSafeRunOutputPath(outputDir, value) {
  const rawPath = shortString(value);
  if (!outputDir || !rawPath) return null;
  const absolutePath = path.resolve(outputDir, rawPath);
  const relativePath = path.relative(outputDir, absolutePath);
  if (!relativePath || relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    return null;
  }
  return {
    absolutePath,
    relativePath: normalizeRelativePath(relativePath),
  };
}

function canDirectlyUpdateTextArtifact(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return DIRECT_TEXT_UPDATE_EXTENSIONS.has(extension);
}

function canUpdateStructuredArtifact(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return STRUCTURED_UPDATE_EXTENSIONS.has(extension);
}

function needsNativeRegeneration(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return NATIVE_REGENERATION_EXTENSIONS.has(extension);
}

function currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath) {
  const persisted = readJsonFileIfPresent(finalArtifactsPath);
  if (finalArtifactsPath && !isPlainObject(persisted)) {
    throw new Error("Persisted final_artifacts.json is required before review writes");
  }
  return persisted || {};
}

function finalArtifactsOutputPaths(currentFinalArtifacts) {
  const outputs = Array.isArray(currentFinalArtifacts?.outputs)
    ? currentFinalArtifacts.outputs
    : [];
  return new Set(
    outputs
      .map((output) => artifactPathKey(output?.path))
      .filter(Boolean),
  );
}

function existingDerivedNativeTargets(outputDir, currentFinalArtifacts, sourceArtifact) {
  const sourceKey = artifactPathKey(sourceArtifact);
  const candidates = DERIVED_NATIVE_REGENERATION_TARGETS.get(sourceKey) || [];
  if (!candidates.length) return [];
  const declaredOutputPaths = finalArtifactsOutputPaths(currentFinalArtifacts);
  return candidates.filter((candidate) => {
    const candidateKey = artifactPathKey(candidate);
    if (declaredOutputPaths.has(candidateKey)) return true;
    const target = resolveSafeRunOutputPath(outputDir, candidateKey);
    return Boolean(target && fs.existsSync(target.absolutePath));
  });
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (!/[",\r\n]/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inQuotes) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char === "\r") {
      if (text[index + 1] === "\n") index += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (inQuotes) throw new Error("CSV parse failed: unclosed quoted field");
  if (field !== "" || row.length || !text.endsWith("\n")) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function serializeCsv(rows) {
  return `${rows.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
}

function structuredUpdateSpec(effect) {
  // Native table/object edits are deterministic only when the review payload names the exact row and field.
  if (!effect.target_artifact || !effect.target_id_field || !effect.target_record_id || !effect.target_field) {
    return null;
  }
  return {
    idField: effect.target_id_field,
    recordId: effect.target_record_id,
    targetField: effect.target_field,
    recordsKey: effect.target_records_key || null,
  };
}

function updateMatchingRecord(records, spec, editValue) {
  if (!Array.isArray(records)) throw new Error("structured artifact records must be an array");
  let updated = 0;
  for (const record of records) {
    if (!isPlainObject(record)) continue;
    if (String(record[spec.idField] ?? "") !== spec.recordId) continue;
    record[spec.targetField] = editValue;
    updated += 1;
  }
  if (updated !== 1) {
    throw new Error(
      `structured edit expected exactly one record for ${spec.idField}=${spec.recordId}, found ${updated}`,
    );
  }
  return updated;
}

function updateCsvArtifact(filePath, effect, spec) {
  const rows = parseCsv(fs.readFileSync(filePath, "utf8"));
  if (!rows.length) throw new Error("CSV structured edit requires a header row");
  const header = rows[0];
  const idIndex = header.indexOf(spec.idField);
  const fieldIndex = header.indexOf(spec.targetField);
  if (idIndex < 0) throw new Error(`CSV structured edit missing id column ${spec.idField}`);
  if (fieldIndex < 0) throw new Error(`CSV structured edit missing target column ${spec.targetField}`);
  let updated = 0;
  for (const row of rows.slice(1)) {
    if (String(row[idIndex] ?? "") !== spec.recordId) continue;
    while (row.length < header.length) row.push("");
    row[fieldIndex] = effect.edit_value;
    updated += 1;
  }
  if (updated !== 1) {
    throw new Error(
      `CSV structured edit expected exactly one row for ${spec.idField}=${spec.recordId}, found ${updated}`,
    );
  }
  generatedReviewAtomicWriteFileSync(filePath, serializeCsv(rows), "utf8");
  return { updatedRows: updated, rowCount: Math.max(rows.length - 1, 0) };
}

function updateJsonArtifact(filePath, effect, spec) {
  const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (Array.isArray(parsed)) {
    const updatedRows = updateMatchingRecord(parsed, spec, effect.edit_value);
    generatedReviewAtomicWriteFileSync(
      filePath,
      `${JSON.stringify(parsed, null, 2)}\n`,
      "utf8",
    );
    return { updatedRows, rowCount: parsed.length };
  }
  if (isPlainObject(parsed) && spec.recordsKey && Array.isArray(parsed[spec.recordsKey])) {
    const records = parsed[spec.recordsKey];
    const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
    generatedReviewAtomicWriteFileSync(
      filePath,
      `${JSON.stringify(parsed, null, 2)}\n`,
      "utf8",
    );
    return { updatedRows, rowCount: records.length };
  }
  if (isPlainObject(parsed) && String(parsed[spec.idField] ?? "") === spec.recordId) {
    parsed[spec.targetField] = effect.edit_value;
    generatedReviewAtomicWriteFileSync(
      filePath,
      `${JSON.stringify(parsed, null, 2)}\n`,
      "utf8",
    );
    return { updatedRows: 1, rowCount: 1 };
  }
  throw new Error("JSON structured edit requires an object, array, or explicit records_key array");
}

function updateJsonlArtifact(filePath, effect, spec) {
  const text = fs.readFileSync(filePath, "utf8");
  const records = text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
  const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
  generatedReviewAtomicWriteFileSync(
    filePath,
    `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
    "utf8",
  );
  return { updatedRows, rowCount: records.length };
}

function originalBackupRelativePath(effect, targetRelativePath) {
  const extension = path.extname(targetRelativePath).toLowerCase() || ".txt";
  const sourceBase = path.basename(targetRelativePath, extension);
  const base = safePathSegment(sourceBase, "artifact");
  const itemId = safePathSegment(effect.item_id, "item");
  return normalizeRelativePath(path.join("revisions", "originals", `${base}__${itemId}${extension}`));
}

function readJsonFileIfPresent(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function uniqueStrings(values) {
  return Array.from(
    new Set(
      values
        .map((value) => shortString(value))
        .filter(Boolean),
    ),
  );
}

function collectReviewApplicationPaths(appliedDecisions, finalArtifacts) {
  const paths = ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
  const finalOutputs = Array.isArray(finalArtifacts?.outputs) ? finalArtifacts.outputs : [];
  if (
    finalOutputs.some(
      (output) => isPlainObject(output) && output.path === "review_handoff.md",
    )
  ) {
    paths.push("review_handoff.md");
  }
  const reviewApplication = isPlainObject(finalArtifacts?.review_application)
    ? finalArtifacts.review_application
    : {};
  for (const fieldName of [
    "applied_decisions_path",
    "revision_paths",
    "target_update_paths",
    "structured_update_paths",
    "native_regeneration_paths",
    "native_regenerated_paths",
    "downstream_regenerated_paths",
    "original_backup_paths",
  ]) {
    const value = reviewApplication[fieldName] ?? appliedDecisions?.[fieldName];
    if (Array.isArray(value)) paths.push(...value);
    else paths.push(value);
  }
  return uniqueStrings(paths);
}

function appendReviewApplicationExecutionTrace(
  inputArgs,
  outputDir,
  appliedDecisions,
  finalArtifacts,
) {
  if (!outputDir) return null;
  const parentState = inputArgs[CONCORDATO_REVIEW_TRANSACTION_STATE] || null;
  const runIntakePath = path.join(outputDir, "run_intake.json");
  const current = cloneConcordatoReviewTransactionValue(
    parentState?.baselineRunIntake,
  ) || readJsonFileIfPresent(runIntakePath) ||
    (isPlainObject(inputArgs.run_intake) ? { ...inputArgs.run_intake } : null);
  if (!current) return null;
  const trace = Array.isArray(current.execution_trace) ? [...current.execution_trace] : [];
  const appliedAt = shortString(appliedDecisions?.applied_at) || new Date().toISOString();
  const stepIdSuffix = appliedAt.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "concordato_plan"}_review_apply_${stepIdSuffix || Date.now()}`,
    kind: "deterministic_review_apply",
    status: "passed",
    execution_location: "local_codex_workspace",
    command: [SERVER_NAME, TOOL_NAMES.applyDecisions],
    inputs: uniqueStrings([
      appliedDecisions?.review_payload?.path || "review_payload.json",
      "ui_decisions.json",
      "final_artifacts.json",
    ]),
    outputs: collectReviewApplicationPaths(appliedDecisions, finalArtifacts),
  });
  const updated = { ...current, execution_trace: trace };
  fs.mkdirSync(path.dirname(runIntakePath), { recursive: true });
  generatedReviewAtomicWriteFileSync(
    runIntakePath,
    `${JSON.stringify(updated, null, 2)}\n`,
    "utf8",
  );
  if (parentState) {
    parentState.expectedRunIntake =
      cloneConcordatoReviewTransactionValue(updated);
  }
  return runIntakePath;
}

function requestedDocumentsFromReviewContext(decision, item, data) {
  if (Array.isArray(decision.requested_documents) && decision.requested_documents.length) {
    return decision.requested_documents;
  }
  if (decision.action !== "request_more_documents") return [];
  const candidates = [];
  function add(value) {
    if (Array.isArray(value)) {
      for (const entry of value) add(entry);
      return;
    }
    const text = shortString(value);
    if (text) candidates.push(text);
  }
  for (const key of [
    "requested_document",
    "requested_documents",
    "missing_document",
    "missing_documents",
    "required_document",
    "required_documents",
    "support_document",
    "support_documents",
  ]) {
    add(data[key]);
  }
  const evidence = Array.isArray(item.evidence) ? item.evidence : [];
  for (const record of evidence) {
    if (!isPlainObject(record)) continue;
    for (const key of [
      "requested_document",
      "requested_documents",
      "missing_document",
      "missing_documents",
      "required_document",
      "required_documents",
      "support_document",
      "support_documents",
    ]) {
      add(record[key]);
    }
  }
  return Array.from(new Set(candidates));
}

function compactContextValue(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return String(value);
  return "";
}

function followupContextFromReviewContext(decision, item, data) {
  if (isPlainObject(decision.followup_context) && Object.keys(decision.followup_context).length) {
    return decision.followup_context;
  }
  if (!["reject", "mark_unclear", "request_more_documents"].includes(decision.action)) return {};
  const records = [
    data,
    ...(Array.isArray(item.evidence) ? item.evidence.filter(isPlainObject) : []),
  ];
  const fields = [
    ["owner", ["owner", "responsible_party", "assignee", "contact", "client_contact"]],
    ["source_system", ["source_system", "system", "source_system_name"]],
    ["source_file", ["source_file", "filename", "file_name", "source_workbook"]],
    ["source_table", ["source_table", "sheet", "worksheet", "table"]],
    ["due_date", ["due_date", "deadline", "response_due_date"]],
    ["period", ["period", "tax_period", "fiscal_year", "year"]],
    ["entity", ["entity", "client", "company", "account", "counterparty", "beneficiary"]],
    ["record_id", ["record_id", "source_row", "movement_number", "bank_transaction_id", "journal_entry_id", "claim_index"]],
    ["amount", ["amount", "amount_abs", "amount_value"]],
    ["reason", ["reason", "missing_reason", "blocking_reason", "mismatches"]],
    ["priority", ["priority", "severity"]],
  ];
  const context = {};
  for (const [targetKey, sourceKeys] of fields) {
    for (const record of records) {
      for (const sourceKey of sourceKeys) {
        const value = compactContextValue(record[sourceKey]);
        if (!value) continue;
        context[targetKey] = value;
        break;
      }
      if (context[targetKey]) break;
    }
  }
  return context;
}

function buildApplicationEffect(decision, item, appliedAt) {
  const data = isPlainObject(item.data) ? item.data : {};
  const targetArtifact =
    shortString(data.target_artifact) ||
    shortString(item.output_path) ||
    shortString(data.path);
  const targetPath =
    shortString(data.target_path) ||
    shortString(data.field_path) ||
    shortString(data.field);
  const targetIdField =
    shortString(data.target_id_field) ||
    shortString(data.record_id_field);
  const targetRecordId =
    shortString(data.target_record_id) ||
    shortString(data.record_id);
  const targetField =
    shortString(data.target_field) ||
    shortString(data.edit_field);
  const targetRecordsKey =
    shortString(data.target_records_key) ||
    shortString(data.records_key);
  const requiresFollowup = new Set(["reject", "mark_unclear", "request_more_documents"]).has(
    decision.action,
  );
  const requestedDocuments = requestedDocumentsFromReviewContext(decision, item, data);
  const followupContext = followupContextFromReviewContext(decision, item, data);
  const effect = {
    item_id: decision.item_id,
    item_type: decision.item_type,
    title: decision.title,
    action: decision.action,
    status: decision.status,
    applied_at: appliedAt,
    applied: true,
    requires_followup: requiresFollowup,
    target_artifact: targetArtifact || null,
    target_path: targetPath || null,
    target_id_field: targetIdField || null,
    target_record_id: targetRecordId || null,
    target_field: targetField || null,
    target_records_key: targetRecordsKey || null,
    source_path: shortString(item.source_path) || null,
    artifact_update:
      decision.action === "edit"
        ? "revision_artifact_pending"
        : targetArtifact
          ? "decision_manifest_only"
          : "review_record_only",
  };
  if (decision.reviewer_note) effect.reviewer_note = decision.reviewer_note;
  if (decision.edit_value) effect.edit_value = decision.edit_value;
  if (requestedDocuments.length) {
    effect.requested_documents = requestedDocuments;
  }
  if (Object.keys(followupContext).length) {
    effect.followup_context = followupContext;
  }
  return effect;
}

function writeRevisionArtifacts(outputDir, effects) {
  if (!outputDir) return [];
  const revisionOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const relativePath = revisionRelativePath(effect);
    const absolutePath = path.join(outputDir, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    generatedReviewAtomicWriteFileSync(
      absolutePath,
      effect.edit_value,
      "utf8",
    );
    effect.revision_artifact = relativePath;
    effect.artifact_update = "revision_artifact_written";
    revisionOutputs.push({
      path: relativePath,
      kind: revisionExtension(effect.target_artifact).replace(/^\./, "") || "txt",
      status: "written_revision",
      source_artifact: effect.target_artifact,
      item_id: effect.item_id,
    });
  }
  return revisionOutputs;
}

function concordatoAssuranceBoundRunPaths(outputDir) {
  const envelope = readJsonFileIfPresent(
    path.join(outputDir, "assurance_envelope.json"),
  );
  if (!isPlainObject(envelope) || !Array.isArray(envelope.artifact_receipts)) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  return new Set(
    envelope.artifact_receipts
      .filter(
        (receipt) =>
          isPlainObject(receipt) &&
          receipt.root_id === "run" &&
          typeof receipt.path === "string",
      )
      .map((receipt) => artifactPathKey(receipt.path))
      .filter(Boolean),
  );
}

function writeDirectTextArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  const assuranceBoundPaths = concordatoAssuranceBoundRunPaths(outputDir);
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!canDirectlyUpdateTextArtifact(effect.target_artifact)) continue;
    // A reviewer edit may create a revision, but it cannot overwrite an
    // artifact attested by the immutable predecessor assurance envelope.
    if (assuranceBoundPaths.has(artifactPathKey(effect.target_artifact))) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target) continue;
    const stat = generatedReviewPathEntryStat(target.absolutePath);
    if (!stat) continue;
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
      throw new Error("Concordato review target is unsafe.");
    }
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      generatedReviewAtomicWriteFileSync(
        backupAbsolutePath,
        fs.readFileSync(target.absolutePath),
      );
    }
    generatedReviewAtomicWriteFileSync(
      target.absolutePath,
      effect.edit_value,
      "utf8",
    );
    effect.target_artifact = target.relativePath;
    effect.original_artifact_backup = backupRelativePath;
    effect.artifact_update = "target_artifact_updated";
    targetOutputs.push({
      path: target.relativePath,
      kind: path.extname(target.relativePath).replace(/^\./, "") || "txt",
      status: "updated_from_review",
      item_id: effect.item_id,
    });
    backupOutputs.push({
      path: backupRelativePath,
      kind: path.extname(backupRelativePath).replace(/^\./, "") || "txt",
      status: "backup_original",
      source_artifact: target.relativePath,
      item_id: effect.item_id,
    });
  }
  return { targetOutputs, backupOutputs };
}

function writeStructuredArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  const assuranceBoundPaths = concordatoAssuranceBoundRunPaths(outputDir);
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const spec = structuredUpdateSpec(effect);
    if (!spec) continue;
    if (!canUpdateStructuredArtifact(effect.target_artifact)) continue;
    if (assuranceBoundPaths.has(artifactPathKey(effect.target_artifact))) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target) continue;
    const stat = generatedReviewPathEntryStat(target.absolutePath);
    if (!stat) continue;
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
      throw new Error("Concordato structured review target is unsafe.");
    }
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      generatedReviewAtomicWriteFileSync(
        backupAbsolutePath,
        fs.readFileSync(target.absolutePath),
      );
    }
    const extension = path.extname(target.relativePath).toLowerCase();
    const result =
      extension === ".csv"
        ? updateCsvArtifact(target.absolutePath, effect, spec)
        : extension === ".jsonl"
          ? updateJsonlArtifact(target.absolutePath, effect, spec)
          : updateJsonArtifact(target.absolutePath, effect, spec);
    effect.target_artifact = target.relativePath;
    effect.original_artifact_backup = backupRelativePath;
    effect.artifact_update = "structured_artifact_updated";
    effect.structured_update = {
      id_field: spec.idField,
      record_id: spec.recordId,
      target_field: spec.targetField,
      records_key: spec.recordsKey,
      updated_rows: result.updatedRows,
    };
    targetOutputs.push({
      path: target.relativePath,
      kind: extension.replace(/^\./, "") || "file",
      status: "updated_from_review",
      item_id: effect.item_id,
      row_count: result.rowCount,
      required_columns: [spec.idField, spec.targetField],
    });
    backupOutputs.push({
      path: backupRelativePath,
      kind: path.extname(backupRelativePath).replace(/^\./, "") || "file",
      status: "backup_original",
      source_artifact: target.relativePath,
      item_id: effect.item_id,
    });
  }
  return { targetOutputs, backupOutputs };
}

function markNativeRegenerationPending(effects) {
  const nativeOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (effect.artifact_update !== "revision_artifact_written") continue;
    if (!needsNativeRegeneration(effect.target_artifact)) continue;
    effect.requires_native_regeneration = true;
    effect.native_regeneration_status = "pending";
    effect.artifact_update = "native_regeneration_pending";
    nativeOutputs.push({
      path: effect.target_artifact,
      kind: path.extname(effect.target_artifact || "").replace(/^\./, "") || "file",
      status: "native_regeneration_pending",
      item_id: effect.item_id,
      revision_artifact: effect.revision_artifact || null,
    });
  }
  return nativeOutputs;
}

function markDerivedNativeRegenerationPending(outputDir, effects, currentFinalArtifacts) {
  const nativeOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!["revision_artifact_written", "structured_artifact_updated"].includes(effect.artifact_update)) continue;
    const derivedTargets = existingDerivedNativeTargets(
      outputDir,
      currentFinalArtifacts,
      effect.target_artifact,
    );
    if (!derivedTargets.length) continue;
    effect.requires_native_regeneration = true;
    effect.native_regeneration_status = "pending";
    effect.derived_native_regeneration_paths = derivedTargets;
    for (const targetPath of derivedTargets) {
      nativeOutputs.push({
        path: targetPath,
        kind: path.extname(targetPath).replace(/^\./, "") || "file",
        status: "native_regeneration_pending",
        item_id: effect.item_id,
        source_artifact: effect.target_artifact,
      });
    }
  }
  return nativeOutputs;
}

function nativeRegenerationPathsForEffect(effect) {
  const derivedPaths = Array.isArray(effect.derived_native_regeneration_paths)
    ? effect.derived_native_regeneration_paths
    : [];
  const paths = derivedPaths.length
    ? derivedPaths
    : effect.requires_native_regeneration
      ? [effect.target_artifact]
      : [];
  return Array.from(new Set(paths.map(artifactPathKey).filter(Boolean)));
}

function statusFromEffects(effects, itemCount) {
  if (!effects.length) return "pending_review";
  if (effects.some((effect) => effect.requires_followup)) return "blocked";
  if (effects.some((effect) => effect.requires_native_regeneration)) return "partial_review_applied";
  if (effects.length < itemCount) return "partial_review_applied";
  return "review_applied_assurance_withheld";
}

const REVIEW_HANDOFF_PLUGINS = new Set([
  "check-entries",
  "client-file-preparation",
  "journal-sampling",
  "journal-bank-reconciliation",
  "deep-research-validator",
  "prompt-optimizer",
  "report-builder",
  "concordato-plan-review",
]);

function reviewHandoffOutputRecord(language = "en") {
  const requiredText = isSpanish(language)
    ? [
        "Entrega para revisión",
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
      ]
    : [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
      ];
  return {
    path: "review_handoff.md",
    kind: "md",
    status: "written",
    required_text: requiredText,
    qa_checks: ["nonempty_text", "required_text"],
  };
}

function ensureReviewHandoffCard(inputArgs, outputDir) {
  const reviewPayload = isPlainObject(inputArgs.review_payload) ? inputArgs.review_payload : {};
  const pluginName = shortString(reviewPayload.plugin);
  if (!REVIEW_HANDOFF_PLUGINS.has(pluginName) || !outputDir) return null;
  const language = languageFromArgs(inputArgs);

  const handoffPath = path.join(outputDir, "review_handoff.md");
  fs.mkdirSync(outputDir, { recursive: true });
  const existingText = fs.existsSync(handoffPath) ? fs.readFileSync(handoffPath, "utf8") : "";
  const shouldWrite = !existingText || (isSpanish(language) && !existingText.includes("Entrega para revisión"));
  if (shouldWrite) {
    const displayName = isSpanish(language)
      ? "Revisión del concordato preventivo"
      : PLUGIN_MANIFEST.name || pluginName || "Review";
    const text = isSpanish(language)
      ? [
          `# Entrega para revisión: ${displayName}`,
          "",
          "- Datos de revisión: `review_payload.json`",
          "- Datos de entrada de la ejecución: `run_intake.json`",
          "- Decisiones pendientes: `ui_decisions.json`",
          "- Decisiones aplicadas: `applied_decisions.json`",
          "- Artefactos finales: `final_artifacts.json`",
          "",
          "## Revisión en Codex",
          `1. Valide la referencia de revisión de \`final_artifacts.json\` con \`${TOOL_NAMES.validateReview}\`.`,
          `2. Muestre el espacio de revisión con la misma referencia mediante \`${TOOL_NAMES.renderReview}\`.`,
          `3. Guarde las acciones de revisión con \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Aplique las acciones de revisión con \`${TOOL_NAMES.applyDecisions}\`.`,
          "",
          "<!-- Review Handoff -->",
        ].join("\n")
      : [
          `# ${displayName} Review Handoff`,
          "",
          "- Review payload: `review_payload.json`",
          "- Run intake: `run_intake.json`",
          "- Pending decisions: `ui_decisions.json`",
          "- Applied decisions: `applied_decisions.json`",
          "- Final artifacts: `final_artifacts.json`",
          "",
          "## Review In Codex",
          `1. Validate the review reference from \`final_artifacts.json\` with \`${TOOL_NAMES.validateReview}\`.`,
          `2. Render the review workbench with the same reference through \`${TOOL_NAMES.renderReview}\`.`,
          `3. Save reviewer actions with \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Apply reviewer actions with \`${TOOL_NAMES.applyDecisions}\`.`,
        ].join("\n");
    const handoffContent = `${text}\n`;
    generatedReviewAtomicWriteFileSync(handoffPath, handoffContent, "utf8");
    const parentState = inputArgs[CONCORDATO_REVIEW_TRANSACTION_STATE] || null;
    if (parentState) {
      parentState.expectedReviewHandoffContent = handoffContent;
    }
  }
  return reviewHandoffOutputRecord(language);
}

function finalArtifactsWithApplication(
  inputArgs,
  appliedDecisions,
  finalArtifactsPath,
  revisionOutputs = [],
  targetOutputs = [],
  backupOutputs = [],
  nativeRegenerationOutputs = [],
) {
  const reviewPayload = inputArgs.review_payload;
  const current = currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath);
  const outputDir = resolveRunOutputDir(inputArgs);
  const outputs = Array.isArray(current.outputs) ? [...current.outputs] : [];
  function upsertOutput(record) {
    const existingIndex = outputs.findIndex((output) => output?.path === record.path);
    if (existingIndex >= 0) outputs[existingIndex] = { ...outputs[existingIndex], ...record };
    else outputs.push(record);
  }
  const handoffOutput = ensureReviewHandoffCard(inputArgs, outputDir);
  if (handoffOutput) upsertOutput(handoffOutput);
  upsertOutput({ path: "ui_decisions.json", kind: "json", status: "written_reviewed" });
  upsertOutput({
    path: "applied_decisions.json",
    kind: "json",
    status: appliedDecisions.application_status,
  });
  for (const output of revisionOutputs) upsertOutput(output);
  for (const output of targetOutputs) upsertOutput(output);
  for (const output of backupOutputs) upsertOutput(output);
  for (const output of nativeRegenerationOutputs) upsertOutput(output);
  const blockers = effectsToBlockers(appliedDecisions.effects);
  return {
    schema_version: current.schema_version || reviewPayload.schema_version || "1.0",
    plugin: current.plugin || reviewPayload.plugin,
    workflow: current.workflow || reviewPayload.workflow,
    run_id: current.run_id || reviewPayload.run_id,
    review_payload: isPlainObject(current.review_payload)
      ? current.review_payload
      : {
          path: "review_payload.json",
          content_sha256: reviewPayload.content_sha256,
        },
    review_reference: isPlainObject(current.review_reference)
      ? current.review_reference
      : inputArgs.review_reference,
    outputs,
    caveats: Array.isArray(current.caveats) ? current.caveats : [],
    blockers,
    next_actions: nextActionsWithReviewApplication(
      current.next_actions,
      appliedDecisions,
      blockers,
      languageFromArgs(inputArgs),
    ),
    status: appliedDecisions.application_status,
    review_status: appliedDecisions.application_status,
    final_ready: false,
    assurance: {
      ...(isPlainObject(reviewPayload.assurance) ? reviewPayload.assurance : {}),
      final_ready: false,
    },
    review_application: {
      applied_at: appliedDecisions.applied_at,
      application_status: appliedDecisions.application_status,
      decision_count: appliedDecisions.decision_count,
      item_count: appliedDecisions.item_count,
      blocker_count: appliedDecisions.blocker_count,
      revision_count: revisionOutputs.length,
      revision_paths: revisionOutputs.map((output) => output.path),
      target_update_count: targetOutputs.length,
      target_update_paths: targetOutputs.map((output) => output.path),
      structured_update_count: appliedDecisions.structured_update_count || 0,
      structured_update_paths: appliedDecisions.structured_update_paths || [],
      native_regeneration_count: appliedDecisions.native_regeneration_count || 0,
      native_regeneration_paths: appliedDecisions.native_regeneration_paths || [],
      original_backup_paths: backupOutputs.map((output) => output.path),
      applied_decisions_path: "applied_decisions.json",
    },
  };
}

function effectsToBlockers(effects) {
  return effects
    .filter((effect) => effect.requires_followup)
    .map((effect) => {
      const blocker = {
        item_id: effect.item_id,
        item_type: effect.item_type,
        title: effect.title,
        action: effect.action,
        status: effect.status,
        reviewer_note: effect.reviewer_note || null,
        requested_documents: Array.isArray(effect.requested_documents)
          ? effect.requested_documents
          : [],
      };
      if (isPlainObject(effect.followup_context) && Object.keys(effect.followup_context).length) {
        blocker.followup_context = effect.followup_context;
      }
      return blocker;
    });
}

function nextActionsWithReviewApplication(currentNextActions, appliedDecisions, blockers, language = "en") {
  const nextActions = Array.isArray(currentNextActions) ? [...currentNextActions] : [];
  if (blockers.length) {
    nextActions.push(isSpanish(language) ? "Resuelva las decisiones de revisión bloqueadas antes de considerar listos los artefactos finales." : "Resolve blocked review decisions before treating final artifacts as ready.");
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push(isSpanish(language) ? "Vuelva a generar las salidas nativas DOCX, XLSX o PDF antes de la entrega final." : "Regenerate native DOCX/XLSX/PDF outputs before final handoff.");
  } else if (appliedDecisions.application_status === "review_applied_assurance_withheld") {
    nextActions.push(isSpanish(language) ? "La revisión se registró, pero la conclusión profesional y la publicación siguen retenidas." : "Review was recorded, but professional conclusion and publication remain withheld.");
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push(isSpanish(language) ? "Complete las decisiones de revisión restantes antes de la entrega final." : "Complete remaining review decisions before final handoff.");
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const canonicalOutputDir = resolveRunOutputDir(inputArgs);
  if (!canonicalOutputDir) return applyDecisionPayloadWrites(inputArgs);
  preflightClientWorkflowRun(
    canonicalOutputDir,
    inputArgs?.review_payload?.run_id,
  );
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "apply",
    inputArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeConcordatoReviewTransactionState(
        parentState,
        trustedImage,
        inputArgs,
      );
      const workingArgs = generatedReviewArgsForWorkingOutput(
        inputArgs,
        workingOutputDir,
      );
      Object.defineProperty(workingArgs, CONCORDATO_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = applyDecisionPayloadWrites(workingArgs);
      finalizeConcordatoWorkingOutput(
        workingOutputDir,
        "review_apply_finalization",
      );
      parentState.authorizedWritePaths = Array.from(
        new Set([
          ...parentState.authorizedWritePaths,
          "workflow_output_closure.json",
        ]),
      );
      const canonicalResult = generatedReviewRewriteOutputPaths(
        workingResult,
        workingOutputDir,
        canonicalOutputDir,
      );
      return generatedReviewTransactionEnvelope(
        canonicalResult,
        parentState.authorizedWritePaths,
      );
    },
    {
      ...workflowOptions,
      failureMessage:
        "Concordato review apply transaction failed safely.",
      rollbackFailureMessage:
        "Concordato review apply transaction could not be restored safely.",
    },
  );
}

function applyDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[CONCORDATO_REVIEW_TRANSACTION_STATE] || null;
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
  const language = languageFromArgs(inputArgs);
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const appliedAt = new Date().toISOString();
  const effects = uiDecisions.decisions.map((decision) =>
    buildApplicationEffect(decision, itemById.get(decision.item_id), appliedAt),
  );
  const outputDir = resolveRunOutputDir(inputArgs);
  const revisionOutputs = writeRevisionArtifacts(outputDir, effects);
  const textUpdates = writeDirectTextArtifactUpdates(outputDir, effects);
  const structuredUpdates = writeStructuredArtifactUpdates(outputDir, effects);
  const appliedOutputPath = resolveAppliedDecisionOutputPath(inputArgs);
  const finalArtifactsPath = resolveFinalArtifactsOutputPath(inputArgs);
  const currentFinalArtifacts = currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath);
  const nativeRegenerationOutputs = [
    ...markNativeRegenerationPending(effects),
    ...markDerivedNativeRegenerationPending(outputDir, effects, currentFinalArtifacts),
  ];
  const targetOutputs = [...textUpdates.targetOutputs, ...structuredUpdates.targetOutputs];
  const backupOutputs = [...textUpdates.backupOutputs, ...structuredUpdates.backupOutputs];
  const structuredUpdatePaths = effects
    .filter((effect) => effect.artifact_update === "structured_artifact_updated")
    .map((effect) => effect.target_artifact);
  const nativeRegenerationPaths = Array.from(
    new Set(effects.flatMap((effect) => nativeRegenerationPathsForEffect(effect))),
  );
  const blockerCount = effects.filter((effect) => effect.requires_followup).length;
  const applicationStatus = statusFromEffects(effects, reviewPayload.items.length);
  const appliedDecisions = {
    schema_version: reviewPayload.schema_version,
    plugin: reviewPayload.plugin,
    workflow: reviewPayload.workflow,
    run_id: reviewPayload.run_id,
    applied_at: appliedAt,
    decision_source: uiDecisions.decision_source || "mcp_widget",
    review_payload: {
      path: uiDecisions.review_payload_path || "review_payload.json",
      content_sha256: reviewPayload.content_sha256,
      item_count: reviewPayload.items.length,
      review_type: reviewPayload.review_type || null,
    },
    decisions: uiDecisions.decisions,
    effects,
    decision_count: uiDecisions.decision_count,
    item_count: reviewPayload.items.length,
    blocker_count: blockerCount,
    revision_count: revisionOutputs.length,
    revision_paths: revisionOutputs.map((output) => output.path),
    target_update_count: targetOutputs.length,
    target_update_paths: targetOutputs.map((output) => output.path),
    structured_update_count: structuredUpdatePaths.length,
    structured_update_paths: structuredUpdatePaths,
    native_regeneration_count: nativeRegenerationPaths.length,
    native_regeneration_paths: nativeRegenerationPaths,
    original_backup_paths: backupOutputs.map((output) => output.path),
    application_status: applicationStatus,
  };
  if (uiDecisions.reviewer) appliedDecisions.reviewer = uiDecisions.reviewer;

  const finalArtifacts = finalArtifactsWithApplication(
    inputArgs,
    appliedDecisions,
    finalArtifactsPath,
    revisionOutputs,
    targetOutputs,
    backupOutputs,
    nativeRegenerationOutputs,
  );
  let persisted = false;
  if (decisionOutputPath) {
    fs.mkdirSync(path.dirname(decisionOutputPath), { recursive: true });
    generatedReviewAtomicWriteFileSync(
      decisionOutputPath,
      `${JSON.stringify(uiDecisions, null, 2)}\n`,
      "utf8",
    );
  }
  if (appliedOutputPath) {
    fs.mkdirSync(path.dirname(appliedOutputPath), { recursive: true });
    generatedReviewAtomicWriteFileSync(
      appliedOutputPath,
      `${JSON.stringify(appliedDecisions, null, 2)}\n`,
      "utf8",
    );
    persisted = true;
  }
  if (finalArtifactsPath) {
    fs.mkdirSync(path.dirname(finalArtifactsPath), { recursive: true });
    generatedReviewAtomicWriteFileSync(
      finalArtifactsPath,
      `${JSON.stringify(finalArtifacts, null, 2)}\n`,
      "utf8",
    );
  }
  const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
    parentState,
  );
  const responseAppliedDecisions =
    (isPlainObject(workflowSpecificResult?.applied_decisions)
      ? workflowSpecificResult.applied_decisions
      : null) ||
    readJsonFileIfPresent(appliedOutputPath) ||
    appliedDecisions;
  const responseFinalArtifacts =
    (isPlainObject(workflowSpecificResult?.final_artifacts)
      ? workflowSpecificResult.final_artifacts
      : null) ||
    readJsonFileIfPresent(finalArtifactsPath) ||
    finalArtifacts;
  const runIntakePath = appendReviewApplicationExecutionTrace(
    inputArgs,
    outputDir,
    responseAppliedDecisions,
    responseFinalArtifacts,
  );
  const result = {
    ok: true,
    validation_type: "concordato_plan_application",
    run_id: responseAppliedDecisions.run_id,
    decision_count: responseAppliedDecisions.decision_count,
    item_count: responseAppliedDecisions.item_count,
    blocker_count: responseAppliedDecisions.blocker_count,
    revision_count: Number.isInteger(responseAppliedDecisions.revision_count)
      ? responseAppliedDecisions.revision_count
      : revisionOutputs.length,
    target_update_count: Number.isInteger(
      responseAppliedDecisions.target_update_count,
    )
      ? responseAppliedDecisions.target_update_count
      : targetOutputs.length,
    structured_update_count: Number.isInteger(
      responseAppliedDecisions.structured_update_count,
    )
      ? responseAppliedDecisions.structured_update_count
      : structuredUpdatePaths.length,
    native_regeneration_count: reviewIntegerOrZero(
      responseAppliedDecisions.native_regeneration_count,
    ),
    native_regenerated_count: reviewIntegerOrZero(
      responseAppliedDecisions.native_regenerated_count,
    ),
    application_status:
      typeof responseAppliedDecisions.application_status === "string" &&
      responseAppliedDecisions.application_status.trim()
        ? responseAppliedDecisions.application_status
        : applicationStatus,
    persisted,
    ui_decisions_path: decisionOutputPath,
    applied_decisions_path: persisted ? appliedOutputPath : null,
    final_artifacts_path: finalArtifactsPath,
    run_intake_path: runIntakePath,
    message: persisted
      ? isSpanish(language)
        ? `Se aplicaron ${responseAppliedDecisions.decision_count} decisiones de revisión del concordato preventivo.`
        : `Applied ${responseAppliedDecisions.decision_count} Concordato Preventivo review decisions.`
      : isSpanish(language)
        ? "Las decisiones aplicadas son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
        : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneConcordatoReviewTransactionValue(uiDecisions);
    parentState.expectedAppliedDecisions =
      cloneConcordatoReviewTransactionValue(responseAppliedDecisions);
    parentState.expectedFinalArtifacts =
      cloneConcordatoReviewTransactionValue(responseFinalArtifacts);
    parentState.authorizedWritePaths = concordatoReviewParentWritePaths(
      parentState,
      revisionOutputs,
      targetOutputs,
      backupOutputs,
      runIntakePath,
    );
    parentState.complete = true;
  }
  return result;
}

function pythonExecutable() {
  const candidates = [
    process.env.PYTHON,
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : "",
    path.resolve(PLUGIN_ROOT, "..", "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return candidate;
  }
  return "python3";
}

const CONCORDATO_MANAGED_PYTHON_RESOLVER = String.raw`
import importlib.util
import json
import sys
from pathlib import Path

launcher = Path(sys.argv[1]).resolve()
plugin_root = launcher.parents[1]
spec = importlib.util.spec_from_file_location(
    "vera_concordato_managed_python_runtime",
    launcher,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load Vera managed Python runtime.")
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)
ready, target, detail = runtime.ensure_runtime(
    plugin_root,
    "concordato-plan-review",
)
if not ready:
    raise RuntimeError(detail)
print(json.dumps({
    "python": str(runtime.runtime_python(target)),
    "virtual_env": str(target),
}, separators=(",", ":")))
`;

let concordatoManagedPython;

function concordatoManagedPythonLauncher() {
  if (process.env.VERA_COMPONENT_HOST !== "1") return null;
  const candidates = [
    path.resolve(
      PLUGIN_ROOT,
      "..",
      "vera",
      "scripts",
      "managed_python_runtime.py",
    ),
    path.resolve(
      PLUGIN_ROOT,
      "..",
      "..",
      "scripts",
      "managed_python_runtime.py",
    ),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function concordatoChildPython() {
  const virtualEnvironmentPython = process.env.VIRTUAL_ENV
    ? path.join(
        process.env.VIRTUAL_ENV,
        process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
      )
    : "";
  const repositoryPython = path.resolve(
    PLUGIN_ROOT,
    "..",
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  const configuredCandidates = [
    process.env.PYTHON,
    virtualEnvironmentPython,
    repositoryPython,
  ].filter(Boolean);
  for (const candidate of configuredCandidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return { executable: candidate, environment: process.env };
  }

  if (concordatoManagedPython !== undefined) {
    return concordatoManagedPython;
  }
  const launcher = concordatoManagedPythonLauncher();
  if (!launcher) {
    return { executable: pythonExecutable(), environment: process.env };
  }
  const completed = spawnSync(
    pythonExecutable(),
    [
      "-I",
      "-B",
      "-c",
      CONCORDATO_MANAGED_PYTHON_RESOLVER,
      launcher,
    ],
    {
      cwd: PLUGIN_ROOT,
      encoding: "utf8",
      maxBuffer: 64 * 1024,
    },
  );
  if (completed.error || completed.status !== 0) {
    concordatoManagedPython = null;
    return concordatoManagedPython;
  }
  let resolved;
  try {
    resolved = JSON.parse(completed.stdout.trim());
  } catch {
    concordatoManagedPython = null;
    return concordatoManagedPython;
  }
  if (
    !isPlainObject(resolved) ||
    typeof resolved.python !== "string" ||
    !path.isAbsolute(resolved.python) ||
    !fs.existsSync(resolved.python) ||
    typeof resolved.virtual_env !== "string" ||
    !path.isAbsolute(resolved.virtual_env)
  ) {
    concordatoManagedPython = null;
    return concordatoManagedPython;
  }
  const existingPath = process.env.PATH;
  const environment = {
    ...process.env,
    PATH: existingPath
      ? `${path.dirname(resolved.python)}${path.delimiter}${existingPath}`
      : path.dirname(resolved.python),
    VIRTUAL_ENV: resolved.virtual_env,
    MPARANZA_MANAGED_RUNTIME_VERIFY: "1",
  };
  delete environment.PYTHONHOME;
  concordatoManagedPython = {
    executable: resolved.python,
    environment,
  };
  return concordatoManagedPython;
}

const CLIENT_WORKFLOW_PREFLIGHT = String.raw`
import json
import sys
from pathlib import Path

plugin_root = Path(sys.argv[1]).resolve()
output_dir = Path(sys.argv[2])
workflow_id = sys.argv[3]
candidates = (
    plugin_root.parent / "_shared" / "vendor" / "modules",
    plugin_root / "vendor" / "modules",
    plugin_root.parent.parent / "vendor" / "modules",
)
for candidate in candidates:
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break
else:
    raise RuntimeError("The required vera_assurance module is not available.")

from vera_assurance import load_client_workflow_context_for_output

context = load_client_workflow_context_for_output(
    output_dir,
    expected_workflow_id=workflow_id,
)
print(json.dumps({
    "ok": True,
    "schema_version": context["schema_version"],
    "workflow_id": context["workflow_id"],
    "run_id": context["run_id"],
}, separators=(",", ":")))
`;

function preflightClientWorkflowRun(outputDir, expectedRunId) {
  if (!outputDir) return null;
  const completed = spawnSync(
    pythonExecutable(),
    [
      "-I",
      "-B",
      "-c",
      CLIENT_WORKFLOW_PREFLIGHT,
      PLUGIN_ROOT,
      outputDir,
      "concordato-plan-review",
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8", maxBuffer: 64 * 1024 },
  );
  if (completed.error || completed.status !== 0) {
    throw new Error(
      "Concordato persistence requires a running v2 customer-folder workflow run",
    );
  }
  let result;
  try {
    result = JSON.parse(completed.stdout.trim());
  } catch {
    throw new Error(
      "Concordato customer-run preflight returned an invalid result",
    );
  }
  if (
    !isPlainObject(result) ||
    result.ok !== true ||
    result.schema_version !== "vera.client_workflow_context.v2" ||
    result.workflow_id !== "concordato-plan-review" ||
    result.run_id !== expectedRunId
  ) {
    throw new Error(
      "Concordato customer-run preflight returned an invalid result",
    );
  }
  return result;
}

const CONCORDATO_CHILD_SUMMARY_DOCX =
  "concordato_preventivo_review_summary.docx";
const CONCORDATO_CHILD_REGENERATE_ACTION =
  "Regenerate native DOCX/XLSX/PDF outputs before final handoff.";
const CONCORDATO_CHILD_FINAL_HANDOFF_ACTION =
  "Review is recorded; professional conclusion and publication remain withheld.";
const CONCORDATO_CHILD_COMPLETE_REVIEW_ACTION =
  "Complete remaining review decisions before final handoff.";
const CONCORDATO_CHILD_DOCX_XML_MAX_BYTES = 5_000_000;

function concordatoChildImageFile(image, relativePath) {
  return image?.files?.find((entry) => entry.path === relativePath) || null;
}

function concordatoChildMemoLines(markdownText) {
  const lines = [];
  for (const rawLine of markdownText.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line) continue;
    line = line.replace(/^#{1,6}\s*/, "").replace(/^[-*]\s+/, "");
    if (line) lines.push(line);
  }
  return lines;
}

function concordatoChildRequiredDocxText(memoText) {
  return Array.from(
    new Set(["Memo revisore Codex", ...concordatoChildMemoLines(memoText)]),
  );
}

function concordatoChildPendingNativePaths(effects) {
  const paths = [];
  for (const effect of effects) {
    if (!effect.requires_native_regeneration) continue;
    const rawPaths = Array.isArray(effect.derived_native_regeneration_paths)
      ? effect.derived_native_regeneration_paths
      : [effect.target_artifact];
    for (const rawPath of rawPaths) {
      const relativePath = artifactPathKey(rawPath);
      if (relativePath) paths.push(relativePath);
    }
  }
  return Array.from(new Set(paths));
}

function concordatoChildApplicationStatus(appliedDecisions) {
  if (Number(appliedDecisions.blocker_count || 0) > 0) return "blocked";
  if (Number(appliedDecisions.native_regeneration_count || 0) > 0) {
    return "partial_review_applied";
  }
  if (
    Number(appliedDecisions.decision_count || 0) <
    Number(appliedDecisions.item_count || 0)
  ) {
    return "partial_review_applied";
  }
  return "review_applied_assurance_withheld";
}

function concordatoChildNextActions(current, status) {
  const nextActions = (Array.isArray(current) ? current : [])
    .map((entry) => shortString(entry))
    .filter(
      (entry) => entry && entry !== CONCORDATO_CHILD_REGENERATE_ACTION,
    );
  if (status === "review_applied_assurance_withheld") {
    nextActions.push(CONCORDATO_CHILD_FINAL_HANDOFF_ACTION);
  } else if (status === "partial_review_applied") {
    nextActions.push(CONCORDATO_CHILD_COMPLETE_REVIEW_ACTION);
  }
  return Array.from(new Set(nextActions));
}

function concordatoChildUpsertOutput(outputs, record) {
  const existingIndex = outputs.findIndex(
    (output) => isPlainObject(output) && output.path === record.path,
  );
  if (existingIndex >= 0) {
    outputs[existingIndex] = { ...outputs[existingIndex], ...record };
  } else {
    outputs.push(record);
  }
}

function concordatoChildBackupRecord(effect, targetRelativePath) {
  const extension = path.extname(targetRelativePath) || ".docx";
  const relativePath = originalBackupRelativePath(
    effect,
    targetRelativePath,
  );
  return {
    path: relativePath,
    kind: extension.replace(/^\./, "") || "file",
    status: "backup_original",
    source_artifact: targetRelativePath,
    item_id: shortString(effect.item_id),
  };
}

function concordatoChildZipEntry(archive, expectedName) {
  if (!Buffer.isBuffer(archive) || archive.length < 22) return null;
  const minimumEndOffset = Math.max(0, archive.length - 65_557);
  let endOffset = -1;
  for (let offset = archive.length - 22; offset >= minimumEndOffset; offset -= 1) {
    if (archive.readUInt32LE(offset) === 0x06054b50) {
      endOffset = offset;
      break;
    }
  }
  if (endOffset < 0 || endOffset + 22 > archive.length) return null;
  const entryCount = archive.readUInt16LE(endOffset + 10);
  let offset = archive.readUInt32LE(endOffset + 16);
  for (let index = 0; index < entryCount; index += 1) {
    if (offset + 46 > archive.length || archive.readUInt32LE(offset) !== 0x02014b50) {
      return null;
    }
    const compressionMethod = archive.readUInt16LE(offset + 10);
    const compressedSize = archive.readUInt32LE(offset + 20);
    const uncompressedSize = archive.readUInt32LE(offset + 24);
    const nameLength = archive.readUInt16LE(offset + 28);
    const extraLength = archive.readUInt16LE(offset + 30);
    const commentLength = archive.readUInt16LE(offset + 32);
    const localOffset = archive.readUInt32LE(offset + 42);
    const nextOffset =
      offset + 46 + nameLength + extraLength + commentLength;
    if (nextOffset > archive.length) return null;
    const name = archive
      .subarray(offset + 46, offset + 46 + nameLength)
      .toString("utf8");
    offset = nextOffset;
    if (name !== expectedName) continue;
    if (
      uncompressedSize > CONCORDATO_CHILD_DOCX_XML_MAX_BYTES ||
      localOffset + 30 > archive.length ||
      archive.readUInt32LE(localOffset) !== 0x04034b50
    ) {
      return null;
    }
    const localNameLength = archive.readUInt16LE(localOffset + 26);
    const localExtraLength = archive.readUInt16LE(localOffset + 28);
    const dataOffset = localOffset + 30 + localNameLength + localExtraLength;
    const dataEnd = dataOffset + compressedSize;
    if (dataEnd > archive.length) return null;
    const compressed = archive.subarray(dataOffset, dataEnd);
    let payload;
    try {
      payload =
        compressionMethod === 0
          ? Buffer.from(compressed)
          : compressionMethod === 8
            ? zlib.inflateRawSync(compressed, {
                maxOutputLength: CONCORDATO_CHILD_DOCX_XML_MAX_BYTES,
              })
            : null;
    } catch {
      return null;
    }
    if (!payload || payload.length !== uncompressedSize) return null;
    return payload;
  }
  return null;
}

function concordatoChildDocxVisibleText(archive) {
  const documentXml = concordatoChildZipEntry(
    archive,
    "word/document.xml",
  );
  if (!documentXml) return "";
  return documentXml
    .toString("utf8")
    .replace(/<w:tab\b[^>]*\/>/g, "\t")
    .replace(/<w:(?:br|cr)\b[^>]*\/>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_match, value) =>
      String.fromCodePoint(Number(value)),
    )
    .replace(/&#x([0-9a-f]+);/gi, (_match, value) =>
      String.fromCodePoint(Number.parseInt(value, 16)),
    )
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

function buildConcordatoChildContract(
  beforeApplied,
  beforeFinalArtifacts,
  beforeChildImage,
) {
  const effects = Array.isArray(beforeApplied.effects)
    ? beforeApplied.effects
    : [];
  const candidateIndexes = effects
    .map((effect, index) => ({ effect, index }))
    .filter(
      ({ effect }) =>
        isPlainObject(effect) &&
        effect.action === "edit" &&
        shortString(effect.item_id) === "codex-review-memo" &&
        Boolean(shortString(effect.edit_value)),
    )
    .map(({ index }) => index);
  if (candidateIndexes.length !== 1) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  const effectIndex = candidateIndexes[0];
  const beforeEffect = effects[effectIndex];
  const memoText = shortString(beforeEffect.edit_value);
  const targetRelativePath = generatedReviewCanonicalRelativePath(
    shortString(beforeEffect.target_artifact) || "codex_run_review.md",
  );
  const summaryEntry = concordatoChildImageFile(
    beforeChildImage,
    CONCORDATO_CHILD_SUMMARY_DOCX,
  );
  if (!summaryEntry) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  const targetEntry = concordatoChildImageFile(
    beforeChildImage,
    targetRelativePath,
  );
  const memoBackup = targetEntry
    ? concordatoChildBackupRecord(beforeEffect, targetRelativePath)
    : null;
  const summaryBackup = concordatoChildBackupRecord(
    beforeEffect,
    CONCORDATO_CHILD_SUMMARY_DOCX,
  );
  const allowedWritePaths = new Set([
    "applied_decisions.json",
    "final_artifacts.json",
    targetRelativePath,
    CONCORDATO_CHILD_SUMMARY_DOCX,
  ]);
  if (
    memoBackup &&
    !concordatoChildImageFile(beforeChildImage, memoBackup.path)
  ) {
    allowedWritePaths.add(memoBackup.path);
  }
  if (!concordatoChildImageFile(beforeChildImage, summaryBackup.path)) {
    allowedWritePaths.add(summaryBackup.path);
  }
  return {
    beforeApplied: cloneConcordatoReviewTransactionValue(beforeApplied),
    beforeFinalArtifacts:
      cloneConcordatoReviewTransactionValue(beforeFinalArtifacts),
    beforeChildImage,
    effectIndex,
    memoText,
    targetRelativePath,
    targetEntry,
    summaryEntry,
    memoBackup,
    summaryBackup,
    allowedWritePaths: Array.from(allowedWritePaths),
  };
}

function expectedConcordatoChildApplication(contract, afterChildImage) {
  const expectedApplied = cloneConcordatoReviewTransactionValue(
    contract.beforeApplied,
  );
  const expectedFinalArtifacts = cloneConcordatoReviewTransactionValue(
    contract.beforeFinalArtifacts,
  );
  const effect = expectedApplied.effects[contract.effectIndex];
  effect.target_artifact = contract.targetRelativePath;
  effect.artifact_update = contract.targetEntry
    ? "target_artifact_updated"
    : "target_artifact_created";
  if (shortString(effect.revision_artifact)) {
    effect.promoted_from_revision = effect.revision_artifact;
  }
  if (contract.memoBackup) {
    effect.original_artifact_backup = contract.memoBackup.path;
  }
  effect.native_regeneration_status = "regenerated";
  effect.native_regenerated_paths = [CONCORDATO_CHILD_SUMMARY_DOCX];

  const pendingNativePaths = concordatoChildPendingNativePaths(
    expectedApplied.effects,
  ).filter((entry) => entry !== CONCORDATO_CHILD_SUMMARY_DOCX);
  expectedApplied.native_regeneration_count = pendingNativePaths.length;
  expectedApplied.native_regeneration_paths = pendingNativePaths;
  expectedApplied.native_regenerated_count = 1;
  expectedApplied.native_regenerated_paths = [
    CONCORDATO_CHILD_SUMMARY_DOCX,
  ];
  expectedApplied.target_update_paths = Array.from(
    new Set([
      ...(Array.isArray(expectedApplied.target_update_paths)
        ? expectedApplied.target_update_paths
        : []),
      contract.targetRelativePath,
    ]),
  );
  expectedApplied.target_update_count =
    expectedApplied.target_update_paths.length;
  expectedApplied.original_backup_paths = Array.from(
    new Set([
      ...(Array.isArray(expectedApplied.original_backup_paths)
        ? expectedApplied.original_backup_paths
        : []),
      ...(contract.memoBackup ? [contract.memoBackup.path] : []),
      contract.summaryBackup.path,
    ]),
  );
  expectedApplied.application_status =
    concordatoChildApplicationStatus(expectedApplied);

  const outputs = (Array.isArray(expectedFinalArtifacts.outputs)
    ? expectedFinalArtifacts.outputs
    : []
  ).map((output) =>
    isPlainObject(output)
      ? cloneConcordatoReviewTransactionValue(output)
      : output,
  );
  const targetEntryAfter = concordatoChildImageFile(
    afterChildImage,
    contract.targetRelativePath,
  );
  const summaryEntryAfter = concordatoChildImageFile(
    afterChildImage,
    CONCORDATO_CHILD_SUMMARY_DOCX,
  );
  if (!targetEntryAfter || !summaryEntryAfter) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  concordatoChildUpsertOutput(outputs, {
    path: contract.targetRelativePath,
    kind: path.extname(contract.targetRelativePath).replace(/^\./, "") || "md",
    status: "updated_from_review",
    item_id: shortString(effect.item_id),
    size_bytes: targetEntryAfter.payload.length,
    required_text: [contract.memoText],
    qa_checks: ["nonempty_text", "required_text"],
  });
  if (contract.memoBackup) {
    concordatoChildUpsertOutput(outputs, contract.memoBackup);
  }
  concordatoChildUpsertOutput(outputs, {
    path: CONCORDATO_CHILD_SUMMARY_DOCX,
    kind: "docx",
    status: "updated_from_review",
    native_regenerated: true,
    source_artifact: contract.targetRelativePath,
    size_bytes: summaryEntryAfter.payload.length,
    required_text: concordatoChildRequiredDocxText(contract.memoText),
    qa_checks: ["nonempty_text", "required_text"],
  });
  concordatoChildUpsertOutput(outputs, contract.summaryBackup);
  expectedFinalArtifacts.outputs = outputs;
  expectedFinalArtifacts.status = expectedApplied.application_status;
  expectedFinalArtifacts.review_status = expectedApplied.application_status;
  expectedFinalArtifacts.final_ready = false;
  const reviewApplication = isPlainObject(
    expectedFinalArtifacts.review_application,
  )
    ? expectedFinalArtifacts.review_application
    : {};
  reviewApplication.application_status = expectedApplied.application_status;
  reviewApplication.native_regeneration_count =
    expectedApplied.native_regeneration_count;
  reviewApplication.native_regeneration_paths =
    expectedApplied.native_regeneration_paths;
  reviewApplication.native_regenerated_count =
    expectedApplied.native_regenerated_count;
  reviewApplication.native_regenerated_paths =
    expectedApplied.native_regenerated_paths;
  reviewApplication.target_update_count =
    expectedApplied.target_update_count;
  reviewApplication.target_update_paths =
    expectedApplied.target_update_paths;
  reviewApplication.original_backup_paths =
    expectedApplied.original_backup_paths;
  expectedFinalArtifacts.review_application = reviewApplication;
  expectedFinalArtifacts.next_actions = concordatoChildNextActions(
    expectedFinalArtifacts.next_actions,
    expectedApplied.application_status,
  );
  return {
    appliedDecisions: expectedApplied,
    finalArtifacts: expectedFinalArtifacts,
    updatedEffectCount: 1,
    nativeRegeneratedPaths: [CONCORDATO_CHILD_SUMMARY_DOCX],
    backupPaths: [contract.summaryBackup.path],
  };
}

function validateConcordatoChildFiles(contract, afterChildImage) {
  const targetAfter = concordatoChildImageFile(
    afterChildImage,
    contract.targetRelativePath,
  );
  if (
    !targetAfter ||
    !targetAfter.payload.equals(Buffer.from(contract.memoText, "utf8"))
  ) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  const summaryAfter = concordatoChildImageFile(
    afterChildImage,
    CONCORDATO_CHILD_SUMMARY_DOCX,
  );
  if (
    !summaryAfter ||
    summaryAfter.mode !== contract.summaryEntry.mode ||
    summaryAfter.payload.length < 4 ||
    summaryAfter.payload.subarray(0, 2).toString("binary") !== "PK"
  ) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  const summaryText = concordatoChildDocxVisibleText(summaryAfter.payload);
  const predecessorSummaryText = concordatoChildDocxVisibleText(
    contract.summaryEntry.payload,
  );
  if (
    !predecessorSummaryText ||
    !summaryText.includes(predecessorSummaryText) ||
    !concordatoChildRequiredDocxText(contract.memoText).every((fragment) =>
      summaryText.includes(fragment),
    )
  ) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  for (const [record, sourceEntry] of [
    [contract.memoBackup, contract.targetEntry],
    [contract.summaryBackup, contract.summaryEntry],
  ]) {
    if (!record || !sourceEntry) continue;
    const backupAfter = concordatoChildImageFile(afterChildImage, record.path);
    if (
      !backupAfter ||
      backupAfter.mode !== sourceEntry.mode ||
      !backupAfter.payload.equals(sourceEntry.payload)
    ) {
      throw new Error(
        "Concordato review application returned an invalid result.",
      );
    }
  }
}

function validatePersistedConcordatoApplication(
  contract,
  persistedApplied,
  persistedFinalArtifacts,
  childResult,
  afterChildImage,
) {
  const expected = expectedConcordatoChildApplication(
    contract,
    afterChildImage,
  );
  if (
    !isPlainObject(persistedApplied) ||
    !isPlainObject(persistedFinalArtifacts) ||
    stableJson(persistedApplied) !==
      stableJson(expected.appliedDecisions) ||
    stableJson(persistedFinalArtifacts) !==
      stableJson(expected.finalArtifacts) ||
    stableJson(childResult.applied_decisions) !==
      stableJson(persistedApplied) ||
    stableJson(childResult.final_artifacts) !==
      stableJson(persistedFinalArtifacts) ||
    childResult.updated_effect_count !== expected.updatedEffectCount ||
    stableJson(childResult.native_regenerated_paths) !==
      stableJson(expected.nativeRegeneratedPaths) ||
    stableJson(childResult.backup_paths) !==
      stableJson(expected.backupPaths) ||
    (childResult.application_status != null &&
      childResult.application_status !==
        expected.appliedDecisions.application_status)
  ) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  validateConcordatoChildFiles(contract, afterChildImage);
}

function applyWorkflowSpecificReviewApplication(
  outputDir,
  appliedOutputPath,
  finalArtifactsPath,
  parentState = null,
) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.native_regeneration_count) return null;
  if (!hasWorkflowNativeRegenerationTarget(currentApplied)) return null;
  const currentFinalArtifacts = readJsonFileIfPresent(finalArtifactsPath);
  if (!isPlainObject(currentFinalArtifacts)) {
    throw new Error(
      "Concordato review application returned an invalid result.",
    );
  }
  const beforeChildImage = generatedReviewCaptureDirectoryImage(outputDir);
  const contract = buildConcordatoChildContract(
    currentApplied,
    currentFinalArtifacts,
    beforeChildImage,
  );
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const clientEngagement = concordatoClientEngagementPath(outputDir);
  if (!clientEngagement) {
    throw new Error("Concordato customer-run context is unavailable.");
  }
  const childResult = runConcordatoChild(
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
      "--client-engagement",
      clientEngagement,
      "--persistent-output-dir",
      concordatoPersistentOutputDir(clientEngagement),
    ],
    "apply",
  );
  const afterChildImage = generatedReviewCaptureDirectoryImage(outputDir);
  generatedReviewValidateAuthorizedChanges(
    beforeChildImage,
    afterChildImage,
    contract.allowedWritePaths,
  );
  const persistedApplied = readJsonFileIfPresent(appliedOutputPath);
  const persistedFinalArtifacts = readJsonFileIfPresent(finalArtifactsPath);
  validatePersistedConcordatoApplication(
    contract,
    persistedApplied,
    persistedFinalArtifacts,
    childResult,
    afterChildImage,
  );
  if (parentState) {
    parentState.childWritePaths = [...contract.allowedWritePaths];
  }
  return {
    ok: true,
    updated_effect_count: childResult.updated_effect_count,
    native_regenerated_paths:
      canonicalConcordatoPathArray(
        childResult.native_regenerated_paths,
      ) || [],
    backup_paths:
      canonicalConcordatoPathArray(childResult.backup_paths) || [],
    application_status: persistedApplied.application_status,
    applied_decisions: persistedApplied,
    final_artifacts: persistedFinalArtifacts,
  };
}

function hasWorkflowNativeRegenerationTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (!effect.requires_native_regeneration) return false;
    return nativeRegenerationPathsForEffect(effect).includes(
      "concordato_preventivo_review_summary.docx",
    );
  });
}

const MODEL_PROJECTION_OMIT_KEYS = new Set([
  "absolute_path",
  "content_sha256",
  "envelope_content_sha256",
  "file_name",
  "filename",
  "name",
  "output_path",
  "path",
  "plan_source_artifact_ref",
  "relative_path",
  "sha256",
  "size_bytes",
  "source_artifact_ref",
  "source_path",
  "support_source_artifact_ref",
]);

function reviewItemTypeCounts(reviewPayload) {
  const counts = {};
  for (const item of reviewPayload.items) {
    counts[item.item_type] = (counts[item.item_type] || 0) + 1;
  }
  return counts;
}

function sourceAliasReplacements(reviewPayload) {
  const values = [];
  for (const item of reviewPayload.items) {
    if (item.item_type !== "source_inventory") continue;
    const candidates = [
      item.source_path,
      item.data?.relative_path,
      item.data?.path,
      item.data?.name,
    ];
    for (const candidate of candidates) {
      if (typeof candidate === "string" && candidate.trim()) values.push(candidate.trim());
    }
  }
  const unique = Array.from(new Set(values)).sort((left, right) =>
    left.localeCompare(right),
  );
  return unique
    .map((value, index) => ({ value, alias: `[source-${String(index + 1).padStart(3, "0")}]` }))
    .sort((left, right) => right.value.length - left.value.length);
}

function replaceTechnicalSourceLabels(value, replacements) {
  let output = value;
  for (const replacement of replacements) {
    output = output.split(replacement.value).join(replacement.alias);
  }
  return output.replace(
    /(?:[A-Za-z]:\\|\/(?:Users|home|private|tmp|var)\/)[^\s,;)}\]]+/g,
    "[local-path]",
  );
}

function projectReviewItemForModel(value, replacements) {
  if (Array.isArray(value)) {
    return value.map((entry) => projectReviewItemForModel(entry, replacements));
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !MODEL_PROJECTION_OMIT_KEYS.has(key))
        .map(([key, entry]) => [
          key,
          projectReviewItemForModel(entry, replacements),
        ]),
    );
  }
  if (typeof value === "string") {
    return replaceTechnicalSourceLabels(value, replacements);
  }
  return value;
}

function readReviewItems(inputArgs) {
  const hydratedArgs = hydratePersistedReviewArgs(inputArgs);
  const payload = validateReviewPayload(hydratedArgs);
  replayPersistedReviewContext(hydratedArgs);
  const itemIds = Array.isArray(inputArgs.item_ids) ? inputArgs.item_ids : [];
  const itemTypes = Array.isArray(inputArgs.item_types) ? inputArgs.item_types : [];
  if (!itemIds.length && !itemTypes.length) {
    throw new Error("item_ids or item_types is required for purpose-selected review access");
  }
  if (itemIds.length > MAX_MODEL_REVIEW_ITEMS) {
    throw new Error(`item_ids exceeds ${MAX_MODEL_REVIEW_ITEMS} items`);
  }
  const requestedIds = new Set(
    itemIds.map((value, index) => {
      requireString(value, `item_ids[${index}]`);
      return value;
    }),
  );
  const requestedTypes = new Set(
    itemTypes.map((value, index) => {
      requireString(value, `item_types[${index}]`);
      if (!ITEM_TYPES.has(value)) throw new Error(`item_types[${index}] is not supported: ${value}`);
      return value;
    }),
  );
  const offset = Number.isInteger(inputArgs.offset) && inputArgs.offset >= 0
    ? inputArgs.offset
    : 0;
  const limit = Number.isInteger(inputArgs.limit)
    ? inputArgs.limit
    : MAX_MODEL_REVIEW_ITEMS;
  if (limit < 1 || limit > MAX_MODEL_REVIEW_ITEMS) {
    throw new Error(`limit must be between 1 and ${MAX_MODEL_REVIEW_ITEMS}`);
  }
  const matches = payload.review_payload.items.filter(
    (item) =>
      (requestedIds.size && requestedIds.has(item.id)) ||
      (requestedTypes.size && requestedTypes.has(item.item_type)),
  );
  const replacements = sourceAliasReplacements(payload.review_payload);
  const selected = matches
    .slice(offset, offset + limit)
    .map((item) => projectReviewItemForModel(item, replacements));
  const result = {
    ok: true,
    validation_type: "concordato_plan_review_items",
    run_id: payload.review_payload.run_id,
    projection: "purpose_selected_post_confirmation_v1",
    technical_metadata_removed: true,
    source_labels_replaced_with_stable_aliases: true,
    offset,
    limit,
    matched_item_count: matches.length,
    returned_item_count: selected.length,
    has_more: offset + selected.length < matches.length,
    items: selected,
  };
  if (payloadBytes(result) > MAX_PAYLOAD_BYTES) {
    throw new Error(`Selected Concordato Preventivo review items exceed ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return result;
}

function modelVisibleToolPayload(payload, toolName) {
  if (toolName === TOOL_NAMES.readReviewItems) return payload;
  if (toolName === TOOL_NAMES.validateReview || toolName === TOOL_NAMES.renderReview) {
    const reviewPayload = payload.review_payload;
    return {
      ok: true,
      validation_type: "concordato_plan_review_summary",
      run_id: reviewPayload.run_id,
      review_type: reviewPayload.review_type || null,
      status: reviewPayload.status || null,
      item_count: reviewPayload.item_count,
      item_type_counts: reviewItemTypeCounts(reviewPayload),
      review_reference: payload.review_reference,
      detailed_review_transport: "component_only",
      on_demand_review_tool: TOOL_NAMES.readReviewItems,
      on_demand_item_limit: MAX_MODEL_REVIEW_ITEMS,
      message: isSpanish(languageFromArgs(payload))
        ? "La revisión persistida es válida. El detalle permanece en el componente; solicite solo los elementos necesarios mediante read_concordato_plan_review_items."
        : "The persisted review is valid. Detail remains in the component; request only needed items through read_concordato_plan_review_items.",
    };
  }
  return {
    ok: payload?.ok === true,
    validation_type: payload?.validation_type || null,
    run_id: payload?.run_id || null,
    status: payload?.status || payload?.application_status || null,
    decision_count: payload?.decision_count ?? null,
    item_count: payload?.item_count ?? null,
    blocker_count: payload?.blocker_count ?? null,
    persisted: payload?.persisted === true,
    message: payload?.message || null,
  };
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const hydratedArgs = hydratePersistedReviewArgs(args);
    const payload = validateReviewPayload(hydratedArgs);
    replayPersistedReviewContext(hydratedArgs);
    return payload;
  }
  if (name === TOOL_NAMES.renderReview) {
    const hydratedArgs = hydratePersistedReviewArgs(args);
    const payload = validateReviewPayload(hydratedArgs);
    replayPersistedReviewContext(hydratedArgs);
    return payload;
  }
  if (name === TOOL_NAMES.readReviewItems) return readReviewItems(args);
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(hydratePersistedReviewArgs(args));
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(hydratePersistedReviewArgs(args));
  }
  throw new Error(
    isSpanish(languageFromArgs(args))
      ? `herramienta desconocida del widget de revisión del concordato preventivo: ${name}`
      : `unknown Concordato Preventivo review widget tool: ${name}`,
  );
}

function toolResult(payload, toolName) {
  const modelPayload = modelVisibleToolPayload(payload, toolName);
  const result = {
    content: [{ type: "text", text: JSON.stringify(modelPayload) }],
    structuredContent: modelPayload,
    isError: false,
  };
  if (
    toolName === TOOL_NAMES.renderReview ||
    toolName === TOOL_NAMES.saveDecisions ||
    toolName === TOOL_NAMES.applyDecisions
  ) {
    result._meta = {
      ...toolUiMeta(WIDGET_URI, toolName),
      widget_payload: payload,
    };
  }
  return result;
}

function toolError(message) {
  const payload = { ok: false, error: message };
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: true,
  };
}

function rpcResponse(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function handleRpc(message) {
  const messageId = message.id ?? null;
  const method = message.method;
  const params = isPlainObject(message.params) ? message.params : {};
  try {
    if (method === "initialize") {
      const language = languageFromArgs(params);
      return rpcResponse(messageId, {
        protocolVersion: params.protocolVersion || "2024-11-05",
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: {
          tools: {},
          resources: {},
          prompts: {},
        },
        instructions:
          isSpanish(language)
            ? "Use validate_concordato_plan_review antes de render_concordato_plan_review. Dé prioridad al widget MCP para la entrega de la revisión del concordato preventivo; use save_concordato_plan_decisions para guardar las acciones en ui_decisions.json y apply_concordato_plan_decisions para escribir applied_decisions.json y actualizar final_artifacts.json; recurra a Markdown solo si MCP no está disponible."
            : "Use validate_concordato_plan_review before render_concordato_plan_review. Prefer the MCP widget for the Concordato Preventivo review handoff; use save_concordato_plan_decisions to persist actions and apply_concordato_plan_decisions to update applied_decisions.json and final_artifacts.json; fall back to Markdown only when MCP is unavailable.",
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") return rpcResponse(messageId, { tools: toolDefinitions() });
    if (method === "tools/call") {
      const { name, arguments: args } = params;
      const language = languageFromArgs(isPlainObject(args) ? args : params);
      if (typeof name !== "string") return rpcError(messageId, -32602, isSpanish(language) ? "tools/call requiere el nombre de una herramienta" : "tools/call requires a tool name");
      if (!isPlainObject(args)) return rpcError(messageId, -32602, isSpanish(language) ? "Los argumentos de tools/call deben ser un objeto" : "tools/call arguments must be an object");
      try {
        return rpcResponse(messageId, toolResult(callTool(name, args), name));
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        return rpcResponse(messageId, toolError(localizeRuntimeError(errorMessage, language)));
      }
    }
    if (method === "resources/list") return rpcResponse(messageId, { resources: resources() });
    if (method === "resources/read") {
      const { uri } = params;
      if (typeof uri !== "string") {
        const language = languageFromArgs(params);
        return rpcError(messageId, -32602, isSpanish(language) ? "resources/read requiere el URI de un recurso" : "resources/read requires a resource uri");
      }
      const text = resourceText(uri);
      return rpcResponse(messageId, {
        contents: [
          {
            uri,
            mimeType: WIDGET_MIME_TYPE,
            text,
            _meta: widgetResourceMeta(uri),
          },
        ],
      });
    }
    if (method === "resources/templates/list") return rpcResponse(messageId, { resourceTemplates: [] });
    if (method === "prompts/list") return rpcResponse(messageId, { prompts: [] });
    return rpcError(messageId, -32601, isSpanish(languageFromArgs(params)) ? `método no encontrado: ${method}` : `method not found: ${method}`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return rpcError(messageId, -32000, localizeRuntimeError(errorMessage, languageFromArgs(params)));
  }
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function main() {
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on("line", (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      send(rpcError(null, -32700, "parse error"));
      return;
    }
    const response = handleRpc(message);
    if (response != null && message.id != null) send(response);
  });
}

main();

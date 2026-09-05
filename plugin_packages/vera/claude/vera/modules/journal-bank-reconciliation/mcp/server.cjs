"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const { TextDecoder } = require("node:util");
const { spawnSync } = require("node:child_process");

const SERVER_NAME = "journal-bank-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const SHARED_ASSURANCE_ROOT = (() => {
  const vendored = path.join(PLUGIN_ROOT, "vendor", "modules", "vera_assurance");
  return fs.existsSync(vendored)
    ? vendored
    : path.resolve(PLUGIN_ROOT, "..", "_shared", "vendor", "modules", "vera_assurance");
})();
const IMPLEMENTATION_ARTIFACT_SPECS = [
  [
    "implementation.plugin.codex_plugin.plugin_json",
    "implementation",
    ".codex-plugin/plugin.json",
  ],
  [
    "implementation.plugin.app_json",
    "implementation",
    ".app.json",
  ],
  [
    "implementation.plugin.mcp_json",
    "implementation",
    ".mcp.json",
  ],
  [
    "implementation.plugin.assets.icon_svg",
    "implementation",
    "assets/icon.svg",
  ],
  [
    "implementation.plugin.assets.journal_bank_review_widget_html",
    "implementation",
    "assets/journal-bank-review-widget.html",
  ],
  [
    "implementation.plugin.assets.review_workbench_adapter_json",
    "implementation",
    "assets/review-workbench-adapter.json",
  ],
  [
    "implementation.plugin.mcp.server_cjs",
    "implementation",
    "mcp/server.cjs",
  ],
  [
    "implementation.plugin.scripts.apply_review_edits_py",
    "implementation",
    "scripts/apply_review_edits.py",
  ],
  [
    "implementation.plugin.scripts.check_dependencies_py",
    "implementation",
    "scripts/check_dependencies.py",
  ],
  [
    "implementation.plugin.scripts.excel_sanitization_py",
    "implementation",
    "scripts/excel_sanitization.py",
  ],
  [
    "implementation.plugin.scripts.implementation_bootstrap_py",
    "implementation",
    "scripts/implementation_bootstrap.py",
  ],
  [
    "implementation.plugin.scripts.inspect_inputs_py",
    "implementation",
    "scripts/inspect_inputs.py",
  ],
  [
    "implementation.plugin.scripts.journal_bank_core_py",
    "implementation",
    "scripts/journal_bank_core.py",
  ],
  [
    "implementation.plugin.scripts.review_session_py",
    "implementation",
    "scripts/review_session.py",
  ],
  [
    "implementation.plugin.scripts.run_reconciliation_py",
    "implementation",
    "scripts/run_reconciliation.py",
  ],
  [
    "implementation.plugin.scripts.semantic_review_py",
    "implementation",
    "scripts/semantic_review.py",
  ],
  [
    "implementation.shared.vera_assurance.init_py",
    "shared_implementation",
    "__init__.py",
  ],
  [
    "implementation.shared.vera_assurance.contracts_py",
    "shared_implementation",
    "contracts.py",
  ],
  [
    "implementation.shared.vera_assurance.decisions_py",
    "shared_implementation",
    "decisions.py",
  ],
  [
    "implementation.shared.vera_assurance.envelope_py",
    "shared_implementation",
    "envelope.py",
  ],
  [
    "implementation.shared.vera_assurance.money_py",
    "shared_implementation",
    "money.py",
  ],
  [
    "implementation.shared.vera_assurance.relationships_py",
    "shared_implementation",
    "relationships.py",
  ],
  [
    "implementation.shared.vera_assurance.review_output_transaction_cjs",
    "shared_implementation",
    "review_output_transaction.cjs",
  ],
  [
    "implementation.shared.vera_assurance.serialization_py",
    "shared_implementation",
    "serialization.py",
  ],
];
validateImplementationPhysicalTree();
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/journal-bank-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const TOOL_NAMES = {
  validateReview: "validate_journal_bank_review",
  renderReview: "render_journal_bank_review",
  caseContext: "get_journal_bank_case_context",
  saveDecisions: "save_journal_bank_decisions",
  applyDecisions: "apply_journal_bank_decisions",
};
const MODEL_CONTEXT_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const MODEL_CONTEXT_TTL_MS = 4 * 60 * 60 * 1000;
const MAX_MODEL_CONTEXTS = 32;
const MAX_MODEL_CASES_PER_CALL = 25;
const MAX_MODEL_CONTEXT_BYTES = 500_000;
const MODEL_CONTEXTS = new Map();
const MODEL_CONTEXT_SAFE_STATUSES = new Set([
  "needs_review",
  "ready_for_review",
  "pending_review",
  "reviewed",
  "accepted",
  "rejected",
  "edited",
  "needs_evidence",
  "skipped",
  "open",
  "closed",
  "blocked",
  "ok",
  "fail",
  "warning",
  "matched",
  "unmatched",
  "missing_support",
]);
const MODEL_CASE_DATA_FIELDS = new Set([
  "side",
  "transaction_date",
  "value_date",
  "amount_signed",
  "bank_amount",
  "journal_amount",
  "currency",
  "unit",
  "description",
  "beneficiary",
  "counterparty",
  "account_name",
  "entity",
  "party",
  "direction",
  "stage",
  "amount_delta",
  "date_diff_days",
  "requested_document",
  "reason",
  "status",
  "shown_count",
  "total_count",
]);
const MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS = new Set([
  "reference",
  "movement_number",
  "shared_references",
  "account",
]);
const MODEL_CONTEXT_EVIDENCE_FIELDS = new Set([
  "kind",
  "status",
  "side",
  "stage",
  "amount_delta",
  "date_diff_days",
  "reason",
  "requested_document",
]);
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
  "unmatched_bank",
  "unmatched_journal",
  "matched_pair",
  "workpaper_artifact",
  "review_artifact",
]);

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
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

function objectSchema(properties, required = [], additionalProperties = true) {
  return { type: "object", properties, required, additionalProperties };
}

function toolUiMeta(resourceUri, toolName = null) {
  const meta = {
    ui: { resourceUri, visibility: ["model"] },
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    meta["openai/toolInvocation/invoking"] = "Rendering Journal-Bank review";
    meta["openai/toolInvocation/invoked"] = "Rendered Journal-Bank review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Journal-Bank Reconciliation review surface for matched pairs, unmatched bank rows, unmatched journal rows, diagnostics, and generated artifacts.",
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
      items: { type: "array", items: { type: "object" } },
      item_count: { type: "number" },
      status: { type: "string" },
    },
    ["schema_version", "plugin", "workflow", "run_id", "items", "item_count"],
  );
  const inputSchema = objectSchema(
    {
      client_engagement: { type: "string", description: "Absolute path to the current portable customer-run context.json." },
      run_intake: { type: "object", description: "Optional run_intake.json object." },
      run_intake_path: { type: "string", description: "Optional local path to run_intake.json in the run output folder." },
      review_payload: reviewPayload,
      review_payload_path: { type: "string", description: "Preferred model-led input: local path to review_payload.json so private rows are loaded inside the MCP server." },
      ui_decisions: { type: "object", description: "Optional ui_decisions.json object." },
      ui_decisions_path: { type: "string", description: "Optional local path to ui_decisions.json in the run output folder." },
      final_artifacts: { type: "object", description: "Optional final_artifacts.json object." },
      final_artifacts_path: { type: "string", description: "Optional local path to final_artifacts.json in the run output folder." },
      persistence_token: { type: "string", pattern: "^[A-Za-z0-9_-]{43}$", description: "Opaque review reference returned by validation." },
    },
    [],
  );
  const caseContextSchema = objectSchema(
    {
      persistence_token: { type: "string", pattern: "^[A-Za-z0-9_-]{43}$" },
      case_handles: {
        type: "array",
        minItems: 1,
        maxItems: MAX_MODEL_CASES_PER_CALL,
        items: { type: "string" },
        description: "Opaque case handles from model_context_index.cases.",
      },
      include_exact_identifiers: {
        type: "boolean",
        description: "Include exact references, movement numbers, shared references, or account codes only when required for the selected accounting judgment.",
      },
    },
    ["persistence_token", "case_handles"],
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
      run_intake: { type: "object", description: "Optional run_intake.json object with output_dir for persistence." },
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: { type: "string", description: "Optional reviewer name or role." },
    },
    ["client_engagement", "review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate Journal-Bank review payload",
      description:
        "Validate the Journal-Bank Reconciliation review-session payload before rendering. Call this first, then render_journal_bank_review.",
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
      title: "Render Journal-Bank review",
      description:
        "Render a Journal-Bank Reconciliation review-session payload as an MCP HTML widget for matched pairs, unmatched rows, diagnostics, and artifacts.",
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
      name: TOOL_NAMES.caseContext,
      title: "Get selected Journal-Bank case context",
      description:
        "Return purpose-limited mapped fields for up to 25 selected reconciliation cases. Start from the non-identifying case index and request exact identifiers only when needed.",
      inputSchema: caseContextSchema,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.saveDecisions,
      title: "Save Journal-Bank review decisions",
      description:
        "Validate Journal-Bank review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.applyDecisions,
      title: "Apply Journal-Bank review decisions",
      description:
        "Validate Journal-Bank review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
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
      name: "journal_bank_review_widget",
      title: "Journal-Bank review widget",
      description:
        "Renders Journal-Bank review-session payloads with searchable matched and unmatched rows.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) {
  throw new Error(`unknown Journal-Bank widget resource: ${uri}`);
  }
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "journal-bank-review-widget.html"),
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

function readPrivateReviewJson(filePath, fieldPath) {
  let stat;
  try {
    stat = fs.lstatSync(filePath);
  } catch {
    throw new Error(`${fieldPath} does not exist`);
  }
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) {
    throw new Error(`${fieldPath} must be an ordinary single-link JSON file`);
  }
  let value;
  try {
    value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    throw new Error(`${fieldPath} must point to readable JSON`);
  }
  if (!isPlainObject(value)) throw new Error(`${fieldPath} must contain a JSON object`);
  return value;
}

function materializePrivateReviewArgs(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const args = { ...inputArgs };
  let outputDir = null;
  const runIntakePath = boundedOptionalString(args.run_intake_path, "run_intake_path");
  if (runIntakePath) {
    const resolved = path.resolve(runIntakePath);
    args.run_intake = readPrivateReviewJson(resolved, "run_intake_path");
    outputDir = path.dirname(resolved);
  }
  const reviewPayloadPath = boundedOptionalString(args.review_payload_path, "review_payload_path");
  if (reviewPayloadPath) {
    const resolved = path.resolve(outputDir || process.cwd(), reviewPayloadPath);
    if (outputDir && path.dirname(resolved) !== outputDir) {
      throw new Error("review_payload_path must be in the run output folder");
    }
    args.review_payload = readPrivateReviewJson(resolved, "review_payload_path");
    outputDir ||= path.dirname(resolved);
  }
  for (const [objectField, pathField, defaultName] of [
    ["ui_decisions", "ui_decisions_path", "ui_decisions.json"],
    ["final_artifacts", "final_artifacts_path", "final_artifacts.json"],
  ]) {
    const explicit = boundedOptionalString(args[pathField], pathField);
    if (explicit) {
      const resolved = path.resolve(outputDir || process.cwd(), explicit);
      if (outputDir && path.dirname(resolved) !== outputDir) {
        throw new Error(`${pathField} must be in the run output folder`);
      }
      args[objectField] = readPrivateReviewJson(resolved, pathField);
      outputDir ||= path.dirname(resolved);
    } else if (!isPlainObject(args[objectField]) && outputDir) {
      const sibling = path.join(outputDir, defaultName);
      if (fs.existsSync(sibling)) args[objectField] = readPrivateReviewJson(sibling, pathField);
    }
  }
  if (!isPlainObject(args.run_intake) && outputDir) {
    const sibling = path.join(outputDir, "run_intake.json");
    if (fs.existsSync(sibling)) args.run_intake = readPrivateReviewJson(sibling, "run_intake_path");
  }
  delete args.run_intake_path;
  delete args.review_payload_path;
  delete args.ui_decisions_path;
  delete args.final_artifacts_path;
  return args;
}

function validateItem(item, index) {
  if (!isPlainObject(item)) {
    throw new Error(`review_payload.items[${index}] must be an object`);
  }
  requireString(item.id, `review_payload.items[${index}].id`);
  requireString(item.item_type, `review_payload.items[${index}].item_type`);
  requireString(item.title, `review_payload.items[${index}].title`);
  if (!ITEM_TYPES.has(item.item_type)) {
    throw new Error(
      `review_payload.items[${index}].item_type is not supported: ${item.item_type}`,
    );
  }
  if (!Array.isArray(item.allowed_actions) || item.allowed_actions.length === 0) {
    throw new Error(
      `review_payload.items[${index}].allowed_actions must be a non-empty array`,
    );
  }
  for (const action of item.allowed_actions) {
    if (!ALLOWED_ACTIONS.has(action)) {
      throw new Error(
        `review_payload.items[${index}].allowed_actions contains unsupported action: ${action}`,
      );
    }
  }
  if (item.recommended_action != null && !ALLOWED_ACTIONS.has(item.recommended_action)) {
    throw new Error(
      `review_payload.items[${index}].recommended_action is not supported`,
    );
  }
}

function validateReviewPayload(inputArgs) {
  inputArgs = materializePrivateReviewArgs(inputArgs);
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const reviewPayload = inputArgs.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.plugin !== "journal-bank-reconciliation") {
    throw new Error('review_payload.plugin must be "journal-bank-reconciliation"');
  }
  requireString(reviewPayload.workflow, "review_payload.workflow");
  requireString(reviewPayload.run_id, "review_payload.run_id");
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
  const payload = {
    widget_type: "journal_bank_review",
    client_engagement:
      typeof inputArgs.client_engagement === "string"
        ? inputArgs.client_engagement
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
    throw new Error(`Journal-Bank widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
}

function modelContextHasValue(value) {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (isPlainObject(value)) return Object.keys(value).length > 0;
  return true;
}

function modelContextCleanValue(value, depth = 0) {
  if (depth > 4 || !modelContextHasValue(value)) return undefined;
  if (typeof value === "string") return value.slice(0, 10_000);
  if (["number", "boolean"].includes(typeof value)) return value;
  if (Array.isArray(value)) {
    const cleaned = value.slice(0, 100)
      .map((entry) => modelContextCleanValue(entry, depth + 1))
      .filter((entry) => entry !== undefined);
    return cleaned.length ? cleaned : undefined;
  }
  if (isPlainObject(value)) {
    const cleaned = {};
    for (const [key, entry] of Object.entries(value)) {
      const projected = modelContextCleanValue(entry, depth + 1);
      if (projected !== undefined) cleaned[key] = projected;
    }
    return Object.keys(cleaned).length ? cleaned : undefined;
  }
  return undefined;
}

function modelContextProjectObject(value, allowedFields) {
  if (!isPlainObject(value)) return {};
  const projected = {};
  for (const key of allowedFields) {
    const cleaned = modelContextCleanValue(value[key]);
    if (cleaned !== undefined) projected[key] = cleaned;
  }
  return projected;
}

function modelContextProjectEvidence(evidence, semanticFields, includeExactIdentifiers) {
  if (!Array.isArray(evidence)) return [];
  const allowed = new Set(MODEL_CONTEXT_EVIDENCE_FIELDS);
  if (includeExactIdentifiers) {
    for (const field of MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS) allowed.add(field);
  }
  return evidence.slice(0, 50).map((entry) => {
    const projected = modelContextProjectObject(entry, allowed);
    for (const [key, value] of Object.entries(projected)) {
      if (Object.prototype.hasOwnProperty.call(semanticFields, key)
          && JSON.stringify(semanticFields[key]) === JSON.stringify(value)) {
        delete projected[key];
      }
    }
    return projected;
  }).filter((entry) => Object.keys(entry).length > 0);
}

function modelContextSafeStatus(value) {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  return MODEL_CONTEXT_SAFE_STATUSES.has(normalized) ? normalized : "other";
}

function modelContextIndexSignalKeys(evidence, allowedFields) {
  if (!Array.isArray(evidence)) return [];
  const present = new Set();
  for (const entry of evidence) {
    if (!isPlainObject(entry)) continue;
    for (const field of allowedFields) {
      if (modelContextHasValue(entry[field])) present.add(field);
    }
  }
  return [...present].sort();
}

function modelContextCaseIsRelevant(item) {
  return item.item_type !== "workpaper_artifact"
    && (item.item_type !== "review_artifact" || item.recommended_action !== "accept");
}

function pruneModelContexts() {
  const now = Date.now();
  for (const [token, context] of MODEL_CONTEXTS) {
    if (context.expiresAt <= now) MODEL_CONTEXTS.delete(token);
  }
  while (MODEL_CONTEXTS.size >= MAX_MODEL_CONTEXTS) {
    const oldest = MODEL_CONTEXTS.keys().next().value;
    if (oldest == null) break;
    MODEL_CONTEXTS.delete(oldest);
  }
}

function issueModelContext(privatePayload) {
  // This is deterministic schema projection, not semantic ranking: professional
  // judgment stays with the model, while paths, technical IDs, and blank fields
  // are mechanically excluded from its default transport.
  pruneModelContexts();
  const token = crypto.randomBytes(32).toString("base64url");
  const handles = new Map();
  for (const item of privatePayload.review_payload.items) {
    const digest = crypto.createHmac("sha256", token)
      .update(String(item.id), "utf8").digest("base64url").slice(0, 18);
    handles.set(`case-${digest}`, item);
  }
  MODEL_CONTEXTS.set(token, {
    privatePayload,
    handles,
    runId: privatePayload.review_payload.run_id,
    expiresAt: Date.now() + MODEL_CONTEXT_TTL_MS,
  });
  return { token, context: MODEL_CONTEXTS.get(token) };
}

function modelContextForToken(token) {
  if (typeof token !== "string" || !MODEL_CONTEXT_TOKEN_RE.test(token)) {
    throw new Error("persistence_token has an invalid format");
  }
  pruneModelContexts();
  const context = MODEL_CONTEXTS.get(token);
  if (!context || context.expiresAt <= Date.now()) {
    throw new Error("persistence_token is unknown or expired; validate the review again");
  }
  return context;
}

function modelContextIndex(token, context) {
  const counts = {};
  const cases = [];
  let omittedNonInterpretive = 0;
  const signalFields = new Set(["kind", "status", "side", "stage"]);
  for (const [handle, item] of context.handles) {
    counts[item.item_type] = (counts[item.item_type] || 0) + 1;
    if (!modelContextCaseIsRelevant(item)) {
      omittedNonInterpretive += 1;
      continue;
    }
    const signalKeys = modelContextIndexSignalKeys(item.evidence, signalFields);
    cases.push({
      case_handle: handle,
      item_type: item.item_type,
      status: modelContextSafeStatus(item.status),
      recommended_action: item.recommended_action || null,
      ...(signalKeys.length ? { control_signal_types: signalKeys } : {}),
    });
  }
  return {
    ok: true,
    widget_type: "journal_bank_review",
    item_count: context.privatePayload.review_payload.item_count,
    status: modelContextSafeStatus(context.privatePayload.review_payload.status),
    review_reference: {
      persistence_token: token,
      expires_in_seconds: Math.floor(MODEL_CONTEXT_TTL_MS / 1000),
    },
    model_context_index: {
      schema_version: "1.0",
      purpose: "Select cases that require interpretation before requesting mapped row context.",
      item_type_counts: counts,
      indexed_case_count: cases.length,
      omitted_noninterpretive_item_count: omittedNonInterpretive,
      cases,
    },
    message: "The complete review payload remains in component-only metadata. Use opaque handles to request selected cases.",
  };
}

function modelContextCases(args) {
  const context = modelContextForToken(args.persistence_token);
  if (!Array.isArray(args.case_handles) || args.case_handles.length === 0) {
    throw new Error("case_handles must be a non-empty array");
  }
  if (args.case_handles.length > MAX_MODEL_CASES_PER_CALL) {
    throw new Error(`case_handles exceeds ${MAX_MODEL_CASES_PER_CALL} items`);
  }
  if (new Set(args.case_handles).size !== args.case_handles.length) {
    throw new Error("case_handles must not contain duplicates");
  }
  const includeExactIdentifiers = args.include_exact_identifiers === true;
  const allowedDataFields = new Set(MODEL_CASE_DATA_FIELDS);
  if (includeExactIdentifiers) {
    for (const field of MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS) allowedDataFields.add(field);
  }
  const cases = args.case_handles.map((handle, index) => {
    if (typeof handle !== "string" || !context.handles.has(handle)) {
      throw new Error(`case_handles[${index}] is unknown for this review`);
    }
    const item = context.handles.get(handle);
    const semanticFields = modelContextProjectObject(item.data, allowedDataFields);
    const evidence = modelContextProjectEvidence(item.evidence, semanticFields, includeExactIdentifiers);
    return {
      case_handle: handle,
      item_type: item.item_type,
      status: modelContextSafeStatus(item.status),
      recommended_action: item.recommended_action || null,
      allowed_actions: Array.isArray(item.allowed_actions) ? item.allowed_actions : [],
      ...(Object.keys(semanticFields).length ? { semantic_fields: semanticFields } : {}),
      ...(evidence.length ? { evidence } : {}),
    };
  });
  const result = {
    ok: true,
    case_count: cases.length,
    include_exact_identifiers: includeExactIdentifiers,
    cases,
    minimization: {
      omitted: ["unmapped columns", "physical source locators", "technical row IDs", "empty fields", "derived absolute amount", "duplicate facts"],
      anonymization: false,
      pseudonymization: false,
    },
  };
  if (payloadBytes(result) > MAX_MODEL_CONTEXT_BYTES) {
    throw new Error(`selected case context exceeds ${MAX_MODEL_CONTEXT_BYTES} bytes; request fewer cases`);
  }
  return result;
}

function privatePayloadForRender(args) {
  if (args.persistence_token != null) {
    return { token: args.persistence_token, context: modelContextForToken(args.persistence_token) };
  }
  return issueModelContext(validateReviewPayload(args));
}

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

function saveDecisionPayload(inputArgs) {
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  const language = languageFromArgs(inputArgs);
  const outputDir = resolveRunOutputDir(inputArgs);
  const persist = (workingOutputDir) => {
    const workingPath = workingOutputDir
      ? path.join(workingOutputDir, "ui_decisions.json")
      : decisionOutputPath;
    const persisted = Boolean(workingPath);
    if (workingPath) {
      fs.mkdirSync(path.dirname(workingPath), { recursive: true });
      atomicWriteFileSync(
        workingPath,
        `${JSON.stringify(uiDecisions, null, 2)}\n`,
        "utf8",
      );
    }
    return {
      ok: true,
      validation_type: "journal_bank_decisions",
      run_id: uiDecisions.run_id,
      decision_count: uiDecisions.decision_count,
      item_count: uiDecisions.item_count,
      status: uiDecisions.status,
      persisted,
      ui_decisions_path: persisted ? decisionOutputPath : null,
      message: persisted
        ? isSpanish(language)
          ? `Se guardaron ${uiDecisions.decision_count} decisiones de conciliación entre diario y banco.`
          : `Saved ${uiDecisions.decision_count} Journal-Bank decisions.`
        : isSpanish(language)
          ? "Las decisiones son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
          : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
      ui_decisions: uiDecisions,
    };
  };
  if (!outputDir) return persist(null);
  preflightClientRun(outputDir, uiDecisions.run_id);
  return withOutputDirectoryTransaction(outputDir, persist);
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputReference = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputReference) return null;
  const contextValue =
    typeof inputArgs.client_engagement === "string"
      ? inputArgs.client_engagement.trim()
      : "";
  if (!contextValue && path.isAbsolute(outputReference)) {
    return path.resolve(outputReference);
  }
  if (!contextValue || !path.isAbsolute(contextValue)) {
    throw new Error("Journal-Bank persistence requires the current client_engagement context.");
  }
  const contextPath = path.resolve(contextValue);
  if (contextPath !== contextValue || path.basename(contextPath) !== "context.json") {
    throw new Error("Journal-Bank client_engagement path is invalid.");
  }
  const contextStat = pathEntryStat(contextPath);
  if (
    !contextStat ||
    !contextStat.isFile() ||
    contextStat.isSymbolicLink() ||
    contextStat.nlink !== 1
  ) {
    throw new Error("Journal-Bank client_engagement context is unavailable.");
  }
  if (!path.isAbsolute(outputReference) && runIntake?.path_reference !== "run_root_relative") {
    throw new Error("Journal-Bank output reference is not run-root-relative.");
  }
  const runRoot = path.dirname(contextPath);
  const resolved = path.isAbsolute(outputReference)
    ? path.resolve(outputReference)
    : path.resolve(runRoot, outputReference);
  const relative = path.relative(runRoot, resolved);
  if (
    relative === "" ||
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error("Journal-Bank output reference leaves the customer run.");
  }
  return resolved;
}

function pathEntryStat(targetPath) {
  try {
    return fs.lstatSync(targetPath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function pathEntryExists(targetPath) {
  return pathEntryStat(targetPath) !== null;
}

function writableLeafSignature(targetPath) {
  const targetStat = pathEntryStat(targetPath);
  if (!targetStat) return null;
  if (targetStat.isSymbolicLink()) {
    throw new Error("run_intake.output_dir cannot contain symbolic links");
  }
  if (!targetStat.isFile()) {
    throw new Error("run_intake.output_dir cannot contain special filesystem entries");
  }
  if (targetStat.nlink !== 1) {
    throw new Error("run_intake.output_dir cannot contain hardlink aliases");
  }
  return [
    targetStat.dev,
    targetStat.ino,
    targetStat.size,
    targetStat.mtimeMs,
    targetStat.mode,
  ].join(":");
}

function atomicWriteFileSync(targetPath, payload, encoding = null) {
  validateRealDirectoryAncestors(path.dirname(targetPath));
  const initialSignature = writableLeafSignature(targetPath);
  const targetStat = pathEntryStat(targetPath);
  const targetMode = targetStat ? targetStat.mode & 0o777 : 0o644;
  const tempPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.journal-bank-write-${process.pid}-${crypto.randomUUID()}`,
  );
  let tempCreated = false;
  let descriptor = null;
  try {
    descriptor = fs.openSync(
      tempPath,
      fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL,
      targetMode,
    );
    tempCreated = true;
    fs.writeFileSync(
      descriptor,
      payload,
      encoding ? { encoding } : undefined,
    );
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = null;
    if (writableLeafSignature(targetPath) !== initialSignature) {
      throw new Error("run_intake.output_dir changed during an atomic review write");
    }
    validateRealDirectoryAncestors(path.dirname(targetPath));
    fs.renameSync(tempPath, targetPath);
    tempCreated = false;
  } finally {
    if (descriptor !== null) fs.closeSync(descriptor);
    if (tempCreated) {
      try {
        fs.unlinkSync(tempPath);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
  }
}

function validateOutputDirectoryTree(outputDir) {
  const rootStat = pathEntryStat(outputDir);
  if (!rootStat) return;
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("run_intake.output_dir must be a real directory");
  }
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current)) {
      const candidate = path.join(current, name);
      const candidateStat = fs.lstatSync(candidate);
      if (candidateStat.isSymbolicLink()) {
        throw new Error("run_intake.output_dir cannot contain symbolic links");
      }
      if (candidateStat.isDirectory()) {
        pending.push(candidate);
        continue;
      }
      if (!candidateStat.isFile()) {
        throw new Error("run_intake.output_dir cannot contain special filesystem entries");
      }
      if (candidateStat.nlink !== 1) {
        throw new Error("run_intake.output_dir cannot contain hardlink aliases");
      }
    }
  }
}

function validateRealDirectoryAncestors(targetDir) {
  const resolved = path.resolve(targetDir);
  const parsed = path.parse(resolved);
  let current = parsed.root;
  for (const component of resolved.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, component);
    const currentStat = pathEntryStat(current);
    if (!currentStat) {
      throw new Error("run_intake.output_dir parent must already exist");
    }
    if (!currentStat.isDirectory() || currentStat.isSymbolicLink()) {
      throw new Error("run_intake.output_dir parent must be a real directory");
    }
  }
}

function removeTransactionPath(targetPath) {
  const stat = pathEntryStat(targetPath);
  if (!stat) return;
  if (stat.isDirectory() && !stat.isSymbolicLink()) {
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

function transactionDirectoryIdentity(targetPath) {
  const entry = pathEntryStat(targetPath);
  if (!entry || !entry.isDirectory() || entry.isSymbolicLink()) {
    throw new Error("Journal-Bank transaction root must be a real directory.");
  }
  return { dev: entry.dev, ino: entry.ino };
}

function trackedTransactionRootsWithinParent(outputParent, identity) {
  validateRealDirectoryAncestors(outputParent);
  const matches = [];
  for (const name of fs.readdirSync(outputParent).sort()) {
    const candidate = path.join(outputParent, name);
    const entry = pathEntryStat(candidate);
    if (
      entry &&
      entry.isDirectory() &&
      !entry.isSymbolicLink() &&
      entry.dev === identity.dev &&
      entry.ino === identity.ino
    ) {
      matches.push(candidate);
    }
  }
  return matches;
}

function removeTrackedTransactionRootWithinParent(
  outputParent,
  expectedPath,
  identity,
) {
  const matches = trackedTransactionRootsWithinParent(
    outputParent,
    identity,
  );
  const expected = path.resolve(expectedPath);
  const relocated = matches.some(
    (candidate) => path.resolve(candidate) !== expected,
  );
  for (const candidate of matches) {
    removeTransactionPath(candidate);
  }
  if (trackedTransactionRootsWithinParent(outputParent, identity).length) {
    throw new Error("Journal-Bank transaction root cleanup did not close.");
  }
  return { found: matches.length > 0, relocated };
}

const TRANSACTION_MAX_ENTRY_COUNT = 20_000;
const TRANSACTION_MAX_FILE_BYTES = 128 * 1024 * 1024;
const TRANSACTION_MAX_TOTAL_BYTES = 512 * 1024 * 1024;

function captureTrustedDirectoryImage(outputDir) {
  validateOutputDirectoryTree(outputDir);
  const rootStat = pathEntryStat(outputDir);
  const directories = [];
  const files = [];
  let entryCount = 0;
  let totalBytes = 0;
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current).sort()) {
      entryCount += 1;
      if (entryCount > TRANSACTION_MAX_ENTRY_COUNT) {
        throw new Error(
          "Journal-Bank output transaction exceeds its entry limit.",
        );
      }
      const candidate = path.join(current, name);
      const candidateStat = pathEntryStat(candidate);
      if (!candidateStat || candidateStat.isSymbolicLink()) {
        throw new Error(
          "Journal-Bank output transaction contains an unsafe entry.",
        );
      }
      const relative = normalizeRelativePath(
        path.relative(outputDir, candidate),
      );
      if (candidateStat.isDirectory()) {
        directories.push({
          path: relative,
          mode: candidateStat.mode & 0o777,
        });
        pending.push(candidate);
        continue;
      }
      if (
        !candidateStat.isFile() ||
        candidateStat.nlink !== 1 ||
        candidateStat.size > TRANSACTION_MAX_FILE_BYTES
      ) {
        throw new Error(
          "Journal-Bank output transaction contains an unsupported file.",
        );
      }
      totalBytes += candidateStat.size;
      if (totalBytes > TRANSACTION_MAX_TOTAL_BYTES) {
        throw new Error(
          "Journal-Bank output transaction exceeds its byte limit.",
        );
      }
      const noFollow = fs.constants.O_NOFOLLOW || 0;
      let descriptor;
      try {
        descriptor = fs.openSync(
          candidate,
          fs.constants.O_RDONLY | noFollow,
        );
        const before = fs.fstatSync(descriptor);
        const payload = fs.readFileSync(descriptor);
        const after = fs.fstatSync(descriptor);
        if (
          !before.isFile() ||
          before.nlink !== 1 ||
          before.dev !== after.dev ||
          before.ino !== after.ino ||
          before.size !== after.size ||
          before.mtimeMs !== after.mtimeMs ||
          payload.length !== after.size
        ) {
          throw new Error(
            "Journal-Bank output changed during transaction capture.",
          );
        }
        files.push({
          path: relative,
          mode: after.mode & 0o777,
          payload,
        });
      } finally {
        if (descriptor !== undefined) fs.closeSync(descriptor);
      }
    }
  }
  return {
    rootMode: rootStat.mode & 0o777,
    directories,
    files,
  };
}

function validateDirectoryImageAgainstTrusted(outputDir, trusted) {
  const current = captureTrustedDirectoryImage(outputDir);
  const directoryModes = (image) =>
    new Map(image.directories.map((entry) => [entry.path, entry.mode]));
  const fileEntries = (image) =>
    new Map(image.files.map((entry) => [entry.path, entry]));
  const expectedDirectories = directoryModes(trusted);
  const currentDirectories = directoryModes(current);
  const expectedFiles = fileEntries(trusted);
  const currentFiles = fileEntries(current);
  if (
    current.rootMode !== trusted.rootMode ||
    currentDirectories.size !== expectedDirectories.size ||
    currentFiles.size !== expectedFiles.size
  ) {
    throw new Error("trusted rollback image does not match");
  }
  for (const [relative, mode] of expectedDirectories) {
    if (currentDirectories.get(relative) !== mode) {
      throw new Error("trusted rollback directory mode does not match");
    }
  }
  for (const [relative, expected] of expectedFiles) {
    const actual = currentFiles.get(relative);
    if (
      !actual ||
      actual.mode !== expected.mode ||
      !actual.payload.equals(expected.payload)
    ) {
      throw new Error("trusted rollback file does not match");
    }
  }
}

function directoryImageMatches(outputDir, trusted) {
  if (!trusted) return !pathEntryExists(outputDir);
  try {
    validateDirectoryImageAgainstTrusted(outputDir, trusted);
    return true;
  } catch {
    return false;
  }
}

function materializeTrustedDirectoryImage(targetDir, image) {
  if (pathEntryExists(targetDir)) {
    throw new Error("Journal-Bank transaction target already exists.");
  }
  fs.mkdirSync(targetDir, { mode: 0o700 });
  const effectiveImage =
    image || { rootMode: 0o755, directories: [], files: [] };
  for (const directory of [...effectiveImage.directories].sort(
    (left, right) =>
      left.path.split("/").length - right.path.split("/").length ||
      left.path.localeCompare(right.path),
  )) {
    fs.mkdirSync(
      path.join(targetDir, ...directory.path.split("/")),
      { mode: 0o700 },
    );
  }
  for (const file of effectiveImage.files) {
    const target = path.join(targetDir, ...file.path.split("/"));
    validateRealDirectoryAncestors(path.dirname(target));
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
      path.join(targetDir, ...directory.path.split("/")),
      directory.mode,
    );
  }
  fs.chmodSync(targetDir, effectiveImage.rootMode);
  validateDirectoryImageAgainstTrusted(targetDir, effectiveImage);
}

function restoreTrustedDirectoryImage(outputDir, image) {
  const outputParent = path.dirname(outputDir);
  validateRealDirectoryAncestors(outputParent);
  const recoveryRoot = fs.mkdtempSync(
    path.join(outputParent, ".journal-bank-recovery-"),
  );
  fs.chmodSync(recoveryRoot, 0o700);
  const recoveryIdentity = transactionDirectoryIdentity(recoveryRoot);
  const recoveryOutput = path.join(recoveryRoot, "output");
  let restored = false;
  try {
    if (image) {
      materializeTrustedDirectoryImage(recoveryOutput, image);
    }
    removeTransactionPath(outputDir);
    if (image) {
      if (pathEntryExists(outputDir)) {
        throw new Error("Journal-Bank output changed during recovery.");
      }
      fs.renameSync(recoveryOutput, outputDir);
      validateDirectoryImageAgainstTrusted(outputDir, image);
    } else if (pathEntryExists(outputDir)) {
      throw new Error(
        "Journal-Bank output recovery did not restore absence.",
      );
    }
    restored = true;
  } finally {
    const cleanup = removeTrackedTransactionRootWithinParent(
      outputParent,
      recoveryRoot,
      recoveryIdentity,
    );
    if (!cleanup.found || cleanup.relocated) {
      throw new Error("Journal-Bank recovery root changed.");
    }
  }
  if (!restored) {
    throw new Error("Journal-Bank output recovery did not close.");
  }
}

function restoreOutputDirectoryTransaction(transaction) {
  restoreTrustedDirectoryImage(
    transaction.outputDir,
    transaction.trustedImage,
  );
}

function throwTransactionFailure(operationError, rollbackErrors) {
  if (!rollbackErrors.length) throw operationError;
  throw new Error(
    "Journal-Bank output transaction could not be restored safely.",
  );
}

function withOutputDirectoryTransaction(outputDir, operation) {
  if (!outputDir) return operation();
  const resolvedOutputDir = path.resolve(outputDir);
  if (resolvedOutputDir === path.parse(resolvedOutputDir).root) {
    throw new Error("run_intake.output_dir must not be a filesystem root");
  }
  const outputExisted = pathEntryExists(resolvedOutputDir);
  if (outputExisted) validateOutputDirectoryTree(resolvedOutputDir);
  const trustedImage = outputExisted
    ? captureTrustedDirectoryImage(resolvedOutputDir)
    : null;
  const outputParent = path.dirname(resolvedOutputDir);
  validateRealDirectoryAncestors(outputParent);
  const transaction = {
    outputDir: resolvedOutputDir,
    outputExisted,
    trustedImage,
  };
  let transactionRoot = null;
  let transactionIdentity = null;
  let workingPath = null;
  let commitRoot = null;
  let commitIdentity = null;
  let canonicalDetached = false;
  let committed = false;
  try {
    transactionRoot = fs.mkdtempSync(
      path.join(outputParent, ".journal-bank-apply-"),
    );
    fs.chmodSync(transactionRoot, 0o700);
    transactionIdentity =
      transactionDirectoryIdentity(transactionRoot);
    workingPath = path.join(transactionRoot, "working");
    materializeTrustedDirectoryImage(workingPath, trustedImage);
    if (!directoryImageMatches(resolvedOutputDir, trustedImage)) {
      throw new Error(
        "run_intake.output_dir changed before the apply transaction",
      );
    }
    const result = operation(workingPath);
    validateOutputDirectoryTree(workingPath);
    const workingImage = captureTrustedDirectoryImage(workingPath);
    if (!directoryImageMatches(resolvedOutputDir, trustedImage)) {
      throw new Error("run_intake.output_dir changed during the apply transaction");
    }

    // The validated child-visible tree is now held in parent memory. Remove
    // it before creating fresh commit material unknown to the completed child.
    const transactionCleanup =
      removeTrackedTransactionRootWithinParent(
        outputParent,
        transactionRoot,
        transactionIdentity,
      );
    transactionIdentity = null;
    if (!transactionCleanup.found || transactionCleanup.relocated) {
      throw new Error("Journal-Bank transaction root changed.");
    }

    commitRoot = fs.mkdtempSync(
      path.join(outputParent, ".journal-bank-commit-"),
    );
    fs.chmodSync(commitRoot, 0o700);
    commitIdentity = transactionDirectoryIdentity(commitRoot);
    const commitCandidate = path.join(commitRoot, "candidate");
    const commitBackup = path.join(commitRoot, "trusted-backup");
    materializeTrustedDirectoryImage(commitCandidate, workingImage);
    if (!directoryImageMatches(resolvedOutputDir, trustedImage)) {
      throw new Error(
        "run_intake.output_dir changed before the apply transaction commit",
      );
    }
    if (outputExisted) {
      fs.renameSync(resolvedOutputDir, commitBackup);
      canonicalDetached = true;
    } else if (pathEntryExists(resolvedOutputDir)) {
      throw new Error(
        "run_intake.output_dir changed before the apply transaction commit",
      );
    }
    if (pathEntryExists(resolvedOutputDir)) {
      throw new Error(
        "run_intake.output_dir changed during the apply transaction commit",
      );
    }
    fs.renameSync(commitCandidate, resolvedOutputDir);
    committed = true;
    validateDirectoryImageAgainstTrusted(
      resolvedOutputDir,
      workingImage,
    );
    const commitCleanup = removeTrackedTransactionRootWithinParent(
      outputParent,
      commitRoot,
      commitIdentity,
    );
    commitIdentity = null;
    if (!commitCleanup.found || commitCleanup.relocated) {
      throw new Error("Journal-Bank transaction commit root changed.");
    }
    return result;
  } catch (operationError) {
    const rollbackErrors = [];
    if (
      canonicalDetached ||
      committed ||
      !directoryImageMatches(resolvedOutputDir, trustedImage)
    ) {
      try {
        restoreOutputDirectoryTransaction(transaction);
      } catch (rollbackError) {
        rollbackErrors.push(rollbackError);
      }
    }
    for (const [trackedPath, trackedIdentity] of [
      [transactionRoot, transactionIdentity],
      [commitRoot, commitIdentity],
    ]) {
      if (!trackedPath || !trackedIdentity) continue;
      try {
        removeTrackedTransactionRootWithinParent(
          outputParent,
          trackedPath,
          trackedIdentity,
        );
      } catch (cleanupError) {
        rollbackErrors.push(cleanupError);
      }
    }
    throwTransactionFailure(operationError, rollbackErrors);
  }
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
  ["run_review.md", ["concordato_review_summary.docx"]],
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
  return (
    (isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : null) ||
    readJsonFileIfPresent(finalArtifactsPath) ||
    {}
  );
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
  atomicWriteFileSync(filePath, serializeCsv(rows), "utf8");
  return { updatedRows: updated, rowCount: Math.max(rows.length - 1, 0) };
}

function updateJsonArtifact(filePath, effect, spec) {
  const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (Array.isArray(parsed)) {
    const updatedRows = updateMatchingRecord(parsed, spec, effect.edit_value);
    atomicWriteFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    return { updatedRows, rowCount: parsed.length };
  }
  if (isPlainObject(parsed) && spec.recordsKey && Array.isArray(parsed[spec.recordsKey])) {
    const records = parsed[spec.recordsKey];
    const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
    atomicWriteFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    return { updatedRows, rowCount: records.length };
  }
  if (isPlainObject(parsed) && String(parsed[spec.idField] ?? "") === spec.recordId) {
    parsed[spec.targetField] = effect.edit_value;
    atomicWriteFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
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
  atomicWriteFileSync(
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
  const runIntakePath = path.join(outputDir, "run_intake.json");
  const current = readJsonFileIfPresent(runIntakePath) ||
    (isPlainObject(inputArgs.run_intake) ? { ...inputArgs.run_intake } : null);
  if (!current) return null;
  const trace = Array.isArray(current.execution_trace) ? [...current.execution_trace] : [];
  const appliedAt = shortString(appliedDecisions?.applied_at) || new Date().toISOString();
  const stepIdSuffix = appliedAt.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "journal_bank"}_review_apply_${stepIdSuffix || Date.now()}`,
    kind: "deterministic_review_apply",
    status: "passed",
    execution_location: "cowork_connected_folder",
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
  atomicWriteFileSync(
    runIntakePath,
    `${JSON.stringify(updated, null, 2)}\n`,
    "utf8",
  );
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
    atomicWriteFileSync(absolutePath, effect.edit_value, "utf8");
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

function writeDirectTextArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!canDirectlyUpdateTextArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target || !fs.existsSync(target.absolutePath)) continue;
    const stat = fs.statSync(target.absolutePath);
    if (!stat.isFile()) continue;
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      atomicWriteFileSync(
        backupAbsolutePath,
        fs.readFileSync(target.absolutePath, "utf8"),
        "utf8",
      );
    }
    atomicWriteFileSync(target.absolutePath, effect.edit_value, "utf8");
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
  const originalBytesByPath = new Map();
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!structuredUpdateSpec(effect) || !canUpdateStructuredArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target || !fs.existsSync(target.absolutePath)) continue;
    const stat = fs.statSync(target.absolutePath);
    if (stat.isFile() && !originalBytesByPath.has(target.absolutePath)) {
      originalBytesByPath.set(target.absolutePath, fs.readFileSync(target.absolutePath));
    }
  }
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const spec = structuredUpdateSpec(effect);
    if (!spec) continue;
    if (!canUpdateStructuredArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target || !fs.existsSync(target.absolutePath)) continue;
    const stat = fs.statSync(target.absolutePath);
    if (!stat.isFile()) continue;
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      const originalBytes = originalBytesByPath.get(target.absolutePath);
      if (!originalBytes) throw new Error("Structured edit original snapshot is unavailable");
      atomicWriteFileSync(backupAbsolutePath, originalBytes);
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
  return "partial_review_applied";
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
      ? "Conciliación entre diario y banco"
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
          "## Revisión profesional",
          `1. Valide los datos con \`${TOOL_NAMES.validateReview}\`.`,
          `2. Muestre el espacio de revisión con \`${TOOL_NAMES.renderReview}\`.`,
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
          "## Professional Review",
          `1. Validate the payload with \`${TOOL_NAMES.validateReview}\`.`,
          `2. Render the review workbench with \`${TOOL_NAMES.renderReview}\`.`,
          `3. Save reviewer actions with \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Apply reviewer actions with \`${TOOL_NAMES.applyDecisions}\`.`,
        ].join("\n");
    atomicWriteFileSync(handoffPath, `${text}\n`, "utf8");
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
  const reviewPayload = appliedDecisions.review_payload;
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
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push(isSpanish(language) ? "Use final_artifacts.json como galería de artefactos revisados para la entrega." : "Use final_artifacts.json as the reviewed artifact gallery for handoff.");
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push(isSpanish(language) ? "Complete las decisiones de revisión restantes antes de la entrega final." : "Complete remaining review decisions before final handoff.");
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const { uiDecisions } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
  const language = languageFromArgs(inputArgs);
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const appliedAt = new Date().toISOString();
  const effects = uiDecisions.decisions.map((decision) =>
    buildApplicationEffect(decision, itemById.get(decision.item_id), appliedAt),
  );
  const outputDir = resolveRunOutputDir(inputArgs);
  const applyToOutput = (workingOutputDir) => {
    const trustedAssuranceBaseline = workingOutputDir
      ? captureTrustedAssuranceBaseline(workingOutputDir)
      : null;
    const workingArgs = workingOutputDir
      ? {
          ...inputArgs,
          run_intake: {
            ...inputArgs.run_intake,
            output_dir: workingOutputDir,
          },
        }
      : inputArgs;
    const preflightResult =
      preflightWorkflowReviewApplication(workingOutputDir, outputDir);
    if (workingOutputDir) {
      validateOutputDirectoryTree(workingOutputDir);
      replayTrustedAssuranceBaseline(
        workingOutputDir,
        trustedAssuranceBaseline,
        preflightResult,
      );
    }
    const result = applyDecisionPayloadWrites({
      inputArgs: workingArgs,
      uiDecisions,
      decisionOutputPath: resolveDecisionOutputPath(workingArgs),
      reviewPayload,
      language,
      effects,
      appliedAt,
      outputDir: workingOutputDir,
      canonicalOutputDir: outputDir,
      trustedAssuranceBaseline,
    });
    if (outputDir && workingOutputDir) {
      for (const field of [
        "ui_decisions_path",
        "applied_decisions_path",
        "final_artifacts_path",
        "run_intake_path",
      ]) {
        const value = result[field];
        if (typeof value !== "string") continue;
        const relative = path.relative(workingOutputDir, value);
        if (!relative.startsWith("..") && !path.isAbsolute(relative)) {
          result[field] = path.join(outputDir, relative);
        }
      }
    }
    return result;
  };
  if (!outputDir) return applyToOutput(null);
  preflightClientRun(outputDir, uiDecisions.run_id);
  return withOutputDirectoryTransaction(outputDir, applyToOutput);
}

function applyDecisionPayloadWrites({
  inputArgs,
  uiDecisions,
  decisionOutputPath,
  reviewPayload,
  language,
  effects,
  appliedAt,
  outputDir,
  canonicalOutputDir,
  trustedAssuranceBaseline,
}) {
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
    atomicWriteFileSync(
      decisionOutputPath,
      `${JSON.stringify(uiDecisions, null, 2)}\n`,
      "utf8",
    );
  }
  if (appliedOutputPath) {
    fs.mkdirSync(path.dirname(appliedOutputPath), { recursive: true });
    atomicWriteFileSync(
      appliedOutputPath,
      `${JSON.stringify(appliedDecisions, null, 2)}\n`,
      "utf8",
    );
    persisted = true;
  }
  if (finalArtifactsPath) {
    fs.mkdirSync(path.dirname(finalArtifactsPath), { recursive: true });
    atomicWriteFileSync(
      finalArtifactsPath,
      `${JSON.stringify(finalArtifacts, null, 2)}\n`,
      "utf8",
    );
  }
  const runIntakePath = appendReviewApplicationExecutionTrace(
    inputArgs,
    outputDir,
    appliedDecisions,
    finalArtifacts,
  );
  const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
    canonicalOutputDir,
    {
      trustedAssuranceBaseline,
      expectedAppliedDecisions: appliedDecisions,
      expectedFinalArtifacts: finalArtifacts,
      expectedReviewPayload: reviewPayload,
      expectedUiDecisions: uiDecisions,
    },
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
  return {
    ok: true,
    validation_type: "journal_bank_application",
    run_id: responseAppliedDecisions.run_id,
    decision_count: responseAppliedDecisions.decision_count,
    item_count: responseAppliedDecisions.item_count,
    blocker_count: responseAppliedDecisions.blocker_count,
    revision_count: responseAppliedDecisions.revision_count || revisionOutputs.length,
    target_update_count: responseAppliedDecisions.target_update_count || targetOutputs.length,
    structured_update_count: responseAppliedDecisions.structured_update_count || structuredUpdatePaths.length,
    native_regeneration_count: responseAppliedDecisions.native_regeneration_count || 0,
    native_regenerated_count: responseAppliedDecisions.native_regenerated_count || 0,
    application_status: responseAppliedDecisions.application_status || applicationStatus,
    assurance_report_ready: responseAppliedDecisions.assurance_report_ready === true,
    assurance_limitations: responseAppliedDecisions.assurance_limitations || [],
    persisted,
    ui_decisions_path: decisionOutputPath,
    applied_decisions_path: persisted ? appliedOutputPath : null,
    final_artifacts_path: finalArtifactsPath,
    run_intake_path: runIntakePath,
    message: persisted
      ? isSpanish(language)
        ? `Se aplicaron ${responseAppliedDecisions.decision_count} decisiones de conciliación entre diario y banco.`
        : `Applied ${responseAppliedDecisions.decision_count} Journal-Bank decisions.`
      : isSpanish(language)
        ? "Las decisiones aplicadas son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
        : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
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

const CHILD_OUTPUT_MAX_BYTES = 1024 * 1024;
const CHILD_RESULT_MAX_CHARS = 512 * 1024;

function workflowChildMessages(phase) {
  return phase === "preflight"
    ? {
        start: "Journal-Bank assurance preflight could not start.",
        failure: "Journal-Bank assurance preflight failed.",
        invalid: "Journal-Bank assurance preflight returned an invalid result.",
      }
    : {
        start: "Journal-Bank review application could not start.",
        failure: "Journal-Bank review application failed.",
        invalid: "Journal-Bank review application returned an invalid result.",
      };
}

function canonicalJsonValue(value) {
  if (Array.isArray(value)) return value.map(canonicalJsonValue);
  if (!isPlainObject(value)) return value;
  const normalized = {};
  for (const key of Object.keys(value).sort()) {
    normalized[key] = canonicalJsonValue(value[key]);
  }
  return normalized;
}

function canonicalJsonSha256(value) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(canonicalJsonValue(value)))
    .digest("hex");
}

function safeRelativeArtifactPath(value) {
  if (typeof value !== "string" || !value.trim()) return false;
  const normalized = value.replaceAll("\\", "/");
  if (path.posix.isAbsolute(normalized) || /^[A-Za-z]:\//.test(normalized)) {
    return false;
  }
  const parts = normalized.split("/");
  return !parts.includes("..") && !parts.includes("") && normalized === path.posix.normalize(normalized);
}

function stringArray(value, { relativePaths = false } = {}) {
  return (
    Array.isArray(value) &&
    value.every(
      (entry) =>
        typeof entry === "string" &&
        (!relativePaths || safeRelativeArtifactPath(entry)),
    )
  );
}

const ASSURANCE_GATE_NAMES = [
  "source",
  "preparation",
  "reconciliation",
  "semantic_review",
  "reporting",
  "publication",
];
const ASSURANCE_GATE_STATUSES = new Set([
  "passed",
  "failed",
  "blocked",
  "not_assessed",
  "not_applicable",
  "withheld",
]);
const ASSURANCE_GATE_DEPENDENCIES = {
  preparation: ["source"],
  reconciliation: ["preparation"],
  semantic_review: ["preparation"],
  reporting: ["reconciliation", "semantic_review"],
  publication: ["reporting"],
};
const CANONICAL_IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const SHA256_RE = /^[0-9a-f]{64}$/;

function hasExactKeys(value, required, optional = []) {
  if (!isPlainObject(value)) return false;
  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(value);
  return (
    required.every((key) => Object.prototype.hasOwnProperty.call(value, key)) &&
    keys.every((key) => allowed.has(key))
  );
}

function canonicalJsonEqual(left, right) {
  if (left === undefined || right === undefined) return left === right;
  return canonicalJsonSha256(left) === canonicalJsonSha256(right);
}

function isCanonicalIdentifier(value) {
  return typeof value === "string" && CANONICAL_IDENTIFIER_RE.test(value);
}

function isNonEmptyTrimmedString(value) {
  return typeof value === "string" && Boolean(value) && value === value.trim();
}

function readRegularFileSnapshot(filePath) {
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  let descriptor;
  try {
    descriptor = fs.openSync(filePath, fs.constants.O_RDONLY | noFollow);
    const before = fs.fstatSync(descriptor);
    if (!before.isFile()) throw new Error("artifact is not a regular file");
    const payload = fs.readFileSync(descriptor);
    const after = fs.fstatSync(descriptor);
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      payload.length !== after.size
    ) {
      throw new Error("artifact changed while it was read");
    }
    return {
      byte_count: payload.length,
      sha256: crypto.createHash("sha256").update(payload).digest("hex"),
      mode: after.mode & 0o777,
    };
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function pathIsInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function validateReceiptPath(root, relativePath) {
  const resolvedRoot = path.resolve(root);
  const rootStat = pathEntryStat(resolvedRoot);
  if (!rootStat || !rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("artifact root is not a real directory");
  }
  const target = path.resolve(resolvedRoot, relativePath);
  if (!pathIsInside(resolvedRoot, target)) {
    throw new Error("artifact receipt escapes its root");
  }
  let current = resolvedRoot;
  const parts = path.relative(resolvedRoot, target).split(path.sep).filter(Boolean);
  for (let index = 0; index < parts.length; index += 1) {
    current = path.join(current, parts[index]);
    const currentStat = pathEntryStat(current);
    if (!currentStat || currentStat.isSymbolicLink()) {
      throw new Error("artifact receipt path is missing or linked");
    }
    if (index < parts.length - 1 && !currentStat.isDirectory()) {
      throw new Error("artifact receipt path has a non-directory ancestor");
    }
    if (index === parts.length - 1 && !currentStat.isFile()) {
      throw new Error("artifact receipt path is not a regular file");
    }
  }
  return target;
}

function validateArtifactReceiptAgainstRoots(receipt, roots) {
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
    !hasExactKeys(receipt, required, ["media_type"]) ||
    receipt.schema_version !== "vera.artifact_receipt.v1" ||
    !isCanonicalIdentifier(receipt.artifact_id) ||
    !isCanonicalIdentifier(receipt.root_id) ||
    !isNonEmptyTrimmedString(receipt.role) ||
    !safeRelativeArtifactPath(receipt.path) ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0 ||
    !SHA256_RE.test(receipt.sha256 || "") ||
    (Object.prototype.hasOwnProperty.call(receipt, "media_type") &&
      !isNonEmptyTrimmedString(receipt.media_type))
  ) {
    throw new Error("artifact receipt is invalid");
  }
  const root = roots[receipt.root_id];
  if (!root) throw new Error("artifact receipt root is unavailable");
  const artifactPath = validateReceiptPath(root, receipt.path);
  const snapshot = readRegularFileSnapshot(artifactPath);
  if (
    snapshot.byte_count !== receipt.byte_count ||
    snapshot.sha256 !== receipt.sha256
  ) {
    throw new Error("artifact receipt does not match current bytes");
  }
  return receipt;
}

function implementationArtifactRoots() {
  return {
    implementation: PLUGIN_ROOT,
    shared_implementation: SHARED_ASSURANCE_ROOT,
  };
}

function implementationExpectedDirectories(relativePaths) {
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

function scanImplementationRoot(root, scanRoots, rootFiles) {
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("implementation root must be a real directory");
  }
  const files = new Set();
  const directories = new Set();
  for (const relativePath of rootFiles) {
    const entryPath = path.join(root, relativePath);
    const entry = fs.lstatSync(entryPath);
    if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
      throw new Error("implementation artifact must be an ordinary file");
    }
    files.add(relativePath);
  }
  const pending = scanRoots.map((relativePath) => {
    const scanPath = path.join(root, relativePath);
    const entry = fs.lstatSync(scanPath);
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      throw new Error("implementation directory must be real");
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
        throw new Error("implementation entries cannot be symlinks");
      }
      if (entry.isDirectory()) {
        directories.add(relative);
        pending.push(entryPath);
        continue;
      }
      if (!entry.isFile() || entry.nlink !== 1) {
        throw new Error("implementation artifact must be an ordinary file");
      }
      files.add(relative);
    }
  }
  return { files, directories };
}

function validateImplementationPhysicalTree() {
  const pluginPaths = IMPLEMENTATION_ARTIFACT_SPECS
    .filter(([, rootId]) => rootId === "implementation")
    .map(([, , relativePath]) => relativePath);
  const sharedPaths = IMPLEMENTATION_ARTIFACT_SPECS
    .filter(([, rootId]) => rootId === "shared_implementation")
    .map(([, , relativePath]) => relativePath);
  const pluginTree = scanImplementationRoot(
    PLUGIN_ROOT,
    [".codex-plugin", "assets", "mcp", "scripts"],
    [".app.json", ".mcp.json"],
  );
  const sharedTree = scanImplementationRoot(
    SHARED_ASSURANCE_ROOT,
    ["."],
    [],
  );
  const expectedPluginDirectories =
    implementationExpectedDirectories(pluginPaths);
  if (
    JSON.stringify([...pluginTree.files].sort()) !==
      JSON.stringify([...pluginPaths].sort()) ||
    JSON.stringify([...pluginTree.directories].sort()) !==
      JSON.stringify([...expectedPluginDirectories].sort()) ||
    JSON.stringify([...sharedTree.files].sort()) !==
      JSON.stringify([...sharedPaths].sort()) ||
    sharedTree.directories.size !== 0
  ) {
    throw new Error("implementation physical tree is not exact");
  }
}

function validateImplementationSpecCoverage(roots) {
  if (
    path.resolve(roots.implementation) !== PLUGIN_ROOT ||
    path.resolve(roots.shared_implementation) !== SHARED_ASSURANCE_ROOT
  ) {
    throw new Error("implementation receipt roots are invalid");
  }
  validateImplementationPhysicalTree();
}

function buildImplementationArtifactReceipts() {
  const roots = implementationArtifactRoots();
  validateImplementationSpecCoverage(roots);
  return IMPLEMENTATION_ARTIFACT_SPECS.map(
    ([artifactId, rootId, relativePath]) => {
      const artifactPath = validateReceiptPath(roots[rootId], relativePath);
      const artifactStat = fs.lstatSync(artifactPath);
      if (artifactStat.nlink !== 1) {
        throw new Error(
          "implementation receipt path cannot have hardlink aliases",
        );
      }
      const snapshot = readRegularFileSnapshot(artifactPath);
      return {
        schema_version: "vera.artifact_receipt.v1",
        artifact_id: artifactId,
        root_id: rootId,
        role: "implementation",
        path: relativePath,
        byte_count: snapshot.byte_count,
        sha256: snapshot.sha256,
      };
    },
  );
}

function validateExactImplementationReceipts(envelope, roots) {
  const expected = buildImplementationArtifactReceipts();
  const expectedRefs = expected.map((receipt) => receipt.artifact_id);
  if (
    !Array.isArray(envelope.implementation_artifact_refs) ||
    !canonicalJsonEqual(envelope.implementation_artifact_refs, expectedRefs) ||
    !Array.isArray(envelope.artifact_receipts)
  ) {
    throw new Error("assurance implementation receipt set or order is invalid");
  }
  const actual = envelope.artifact_receipts.filter(
    (receipt) => isPlainObject(receipt) && receipt.role === "implementation",
  );
  if (!canonicalJsonEqual(actual, expected)) {
    throw new Error("assurance implementation receipts are not exact");
  }
  for (const receipt of actual) {
    validateArtifactReceiptAgainstRoots(receipt, roots);
  }
  return actual;
}

function validateGateRegister(value) {
  if (
    !hasExactKeys(value, ["schema_version", "gates", "report_ready"]) ||
    value.schema_version !== "vera.assurance_gates.v1" ||
    !isPlainObject(value.gates) ||
    Object.keys(value.gates).sort().join(",") !==
      [...ASSURANCE_GATE_NAMES].sort().join(",") ||
    typeof value.report_ready !== "boolean"
  ) {
    throw new Error("assurance gate register is invalid");
  }
  for (const name of ASSURANCE_GATE_NAMES) {
    const gate = value.gates[name];
    if (
      !hasExactKeys(gate, ["status", "evidence_refs", "limitations"]) ||
      !ASSURANCE_GATE_STATUSES.has(gate.status) ||
      !Array.isArray(gate.evidence_refs) ||
      gate.evidence_refs.some((reference) => !isCanonicalIdentifier(reference)) ||
      new Set(gate.evidence_refs).size !== gate.evidence_refs.length ||
      !Array.isArray(gate.limitations) ||
      gate.limitations.some((limitation) => !isNonEmptyTrimmedString(limitation)) ||
      (gate.status === "passed" && gate.evidence_refs.length === 0)
    ) {
      throw new Error("assurance gate register is invalid");
    }
  }
  for (const [name, dependencies] of Object.entries(ASSURANCE_GATE_DEPENDENCIES)) {
    if (value.gates[name].status !== "passed") continue;
    if (
      dependencies.some(
        (dependency) =>
          !["passed", "not_applicable"].includes(
            value.gates[dependency].status,
          ),
      )
    ) {
      throw new Error("assurance gate dependency is not closed");
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
    throw new Error("assurance report readiness is stale");
  }
  return value;
}

function validateReviewedDecisionReceipt(value) {
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
    !hasExactKeys(value, required) ||
    value.schema_version !== "vera.reviewed_decision_receipt.v1" ||
    !isCanonicalIdentifier(value.decision_id) ||
    !isCanonicalIdentifier(value.decision_type) ||
    !["draft", "reviewed", "rejected", "superseded"].includes(value.status) ||
    !isCanonicalIdentifier(value.reviewer_ref) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.reviewed_on || "") ||
    !isCanonicalIdentifier(value.adapter_id) ||
    !isCanonicalIdentifier(value.adapter_version) ||
    !Array.isArray(value.source_artifact_refs) ||
    value.source_artifact_refs.length === 0 ||
    value.source_artifact_refs.some((reference) => !isCanonicalIdentifier(reference)) ||
    new Set(value.source_artifact_refs).size !== value.source_artifact_refs.length ||
    !isPlainObject(value.content) ||
    !SHA256_RE.test(value.content_sha256 || "") ||
    canonicalJsonSha256(value.content) !== value.content_sha256
  ) {
    throw new Error("reviewed decision receipt is invalid");
  }
  return value;
}

function sourceRootsForOutput(outputDir) {
  const audit = readJsonFileIfPresent(path.join(outputDir, "reconciliation_audit.json"));
  const runIntake = readJsonFileIfPresent(path.join(outputDir, "run_intake.json")) || {};
  if (!audit) throw new Error("reconciliation audit is unavailable");
  const roots = {
    run: outputDir,
    implementation: PLUGIN_ROOT,
    shared_implementation: SHARED_ASSURANCE_ROOT,
  };
  let runRoot = null;
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    const contextStat = pathEntryStat(contextPath);
    if (
      contextStat?.isFile() &&
      !contextStat.isSymbolicLink() &&
      contextStat.nlink === 1
    ) {
      runRoot = candidate;
      break;
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) break;
    candidate = parent;
  }
  const resolveStoredReference = (value) => {
    const reference = shortString(value);
    if (!reference) return null;
    if (path.isAbsolute(reference)) return path.resolve(reference);
    if (
      !runRoot ||
      runIntake.path_reference !== "run_root_relative" ||
      reference.split(/[\\/]+/).includes("..")
    ) {
      return null;
    }
    return path.resolve(runRoot, reference);
  };
  const canonicalOutput = resolveStoredReference(runIntake.output_dir);
  for (const [side, field] of [
    ["bank", "bank_path"],
    ["journal", "journal_path"],
    ["sample", "sample_path"],
  ]) {
    const sourceValue = shortString(audit[field]);
    if (!sourceValue) continue;
    let source = resolveStoredReference(sourceValue);
    if (!source) continue;
    if (canonicalOutput && pathIsInside(canonicalOutput, source)) {
      source = path.join(outputDir, path.relative(canonicalOutput, source));
    }
    const sourceStat = pathEntryStat(source);
    if (!sourceStat || sourceStat.isSymbolicLink()) {
      throw new Error("assurance source root is unavailable");
    }
    roots[`source_${side}`] = sourceStat.isDirectory()
      ? source
      : path.dirname(source);
  }
  return roots;
}

function validateAssuranceEnvelopeStructure(envelope, roots) {
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
    !hasExactKeys(envelope, required) ||
    envelope.schema_version !== "vera.assurance_envelope.v1" ||
    !isCanonicalIdentifier(envelope.run_id) ||
    !isCanonicalIdentifier(envelope.workflow_id) ||
    !isCanonicalIdentifier(envelope.workflow_version) ||
    !Array.isArray(envelope.artifact_receipts) ||
    !Array.isArray(envelope.implementation_artifact_refs) ||
    envelope.implementation_artifact_refs.length === 0 ||
    !Array.isArray(envelope.reviewed_decisions) ||
    !Array.isArray(envelope.source_qualifications) ||
    !Array.isArray(envelope.allocation_ledgers) ||
    !Array.isArray(envelope.numeric_evidence_ledgers) ||
    !Array.isArray(envelope.limitations) ||
    envelope.limitations.some((value) => !isNonEmptyTrimmedString(value)) ||
    !SHA256_RE.test(envelope.content_sha256 || "")
  ) {
    throw new Error("assurance envelope is invalid");
  }
  const artifacts = envelope.artifact_receipts.map((receipt) =>
    validateArtifactReceiptAgainstRoots(receipt, roots),
  );
  const artifactById = new Map();
  const artifactPaths = new Set();
  for (const receipt of artifacts) {
    const pathKey = `${receipt.root_id}:${receipt.path}`;
    if (artifactById.has(receipt.artifact_id) || artifactPaths.has(pathKey)) {
      throw new Error("assurance envelope artifact identities are not unique");
    }
    artifactById.set(receipt.artifact_id, receipt);
    artifactPaths.add(pathKey);
  }
  if (
    envelope.implementation_artifact_refs.some(
      (reference) =>
        !isCanonicalIdentifier(reference) ||
        artifactById.get(reference)?.role !== "implementation",
    ) ||
    new Set(envelope.implementation_artifact_refs).size !==
      envelope.implementation_artifact_refs.length
  ) {
    throw new Error("assurance implementation binding is invalid");
  }
  validateExactImplementationReceipts(envelope, roots);
  const decisions = envelope.reviewed_decisions.map(validateReviewedDecisionReceipt);
  const decisionById = new Map();
  for (const decision of decisions) {
    if (
      decisionById.has(decision.decision_id) ||
      decision.source_artifact_refs.some(
        (reference) => artifactById.get(reference)?.role !== "source",
      )
    ) {
      throw new Error("assurance reviewed-decision binding is invalid");
    }
    decisionById.set(decision.decision_id, decision);
  }
  const qualificationIds = new Set();
  for (const qualification of envelope.source_qualifications) {
    if (
      !isPlainObject(qualification) ||
      !isCanonicalIdentifier(qualification.qualification_id) ||
      qualificationIds.has(qualification.qualification_id)
    ) {
      throw new Error("assurance source qualification is invalid");
    }
    qualificationIds.add(qualification.qualification_id);
  }
  const allocationIds = new Set();
  for (const ledger of envelope.allocation_ledgers) {
    if (
      !isPlainObject(ledger) ||
      !isCanonicalIdentifier(ledger.ledger_id) ||
      allocationIds.has(ledger.ledger_id)
    ) {
      throw new Error("assurance allocation ledger is invalid");
    }
    allocationIds.add(ledger.ledger_id);
  }
  const numericIds = new Set();
  for (const ledger of envelope.numeric_evidence_ledgers) {
    if (
      !isPlainObject(ledger) ||
      !isCanonicalIdentifier(ledger.ledger_id) ||
      numericIds.has(ledger.ledger_id)
    ) {
      throw new Error("assurance numeric ledger is invalid");
    }
    numericIds.add(ledger.ledger_id);
  }
  const gateRegister = validateGateRegister(envelope.gate_register);
  const knownReferences = new Set([
    ...artifactById.keys(),
    ...decisionById.keys(),
    ...qualificationIds,
    ...allocationIds,
    ...numericIds,
  ]);
  for (const gate of Object.values(gateRegister.gates)) {
    if (gate.evidence_refs.some((reference) => !knownReferences.has(reference))) {
      throw new Error("assurance gate references unknown evidence");
    }
  }
  const content = { ...envelope };
  delete content.content_sha256;
  if (canonicalJsonSha256(content) !== envelope.content_sha256) {
    throw new Error("assurance envelope digest is stale");
  }
  return { envelope, artifacts, artifactById, decisionById, gateRegister };
}

const STANDARD_ASSURANCE_RECEIPT_PATHS = {
  "normalized_bank.csv": "output.normalized_bank_csv",
  "normalized_journal.csv": "output.normalized_journal_csv",
  "reconciliation_matches.csv": "output.reconciliation_matches_csv",
  "unmatched_bank.csv": "output.unmatched_bank_csv",
  "unmatched_journal.csv": "output.unmatched_journal_csv",
  "bank_pdf_non_movement_rows.csv": "output.bank_pdf_non_movement_rows_csv",
  "journal_bank_reconciliation.xlsx": "output.workbook_xlsx",
  "reconciliation_audit.json": "output.audit_json",
  "review_notes.md": "output.review_notes_md",
  "source_qualifications.json": "output.source_qualifications_json",
  "reviewed_decisions.json": "output.reviewed_decisions_json",
  "lineage.json": "output.lineage_json",
  "relationship_ledger.json": "output.relationship_ledger_json",
  "assurance_gates.json": "output.assurance_gates_json",
  "review_payload.json": "output.review_payload_json",
  "ui_decisions.json": "output.ui_decisions_json",
  "applied_decisions.json": "output.applied_decisions_json",
  "final_artifacts.json": "output.final_artifacts_json",
  "run_intake.json": "output.run_intake_json",
  "assurance_envelope.json": "output.assurance_envelope_json",
  "assurance_envelope.reviewed.json":
    "output.assurance_envelope_reviewed_json",
  "review_baseline_replay.json": "output.review_baseline_replay_json",
};

function expectedResealedReceiptBundle(outputDir, initialBundle, sourceReceipts) {
  if (
    !initialBundle ||
    !Array.isArray(initialBundle.output_receipts)
  ) {
    throw new Error("initial artifact receipt bundle is unavailable");
  }
  const priorByPath = new Map(
    initialBundle.output_receipts.map((receipt) => [receipt.path, receipt]),
  );
  const paths = new Set(priorByPath.keys());
  for (const relative of Object.keys(STANDARD_ASSURANCE_RECEIPT_PATHS)) {
    if (pathEntryStat(path.join(outputDir, relative))?.isFile()) {
      paths.add(relative);
    }
  }
  const outputReceipts = [];
  for (const relative of [...paths].sort()) {
    const artifactPath = path.join(outputDir, relative);
    const artifactStat = pathEntryStat(artifactPath);
    if (!artifactStat?.isFile()) continue;
    const prior = priorByPath.get(relative) || {};
    const snapshot = readRegularFileSnapshot(artifactPath);
    const receipt = {
      schema_version: "vera.artifact_receipt.v1",
      artifact_id:
        shortString(prior.artifact_id) ||
        STANDARD_ASSURANCE_RECEIPT_PATHS[relative],
      root_id: shortString(prior.root_id) || "run",
      role:
        shortString(prior.role) ||
        `journal-bank reconciliation ${path.parse(relative).name}`,
      path: relative,
      byte_count: snapshot.byte_count,
      sha256: snapshot.sha256,
    };
    if (shortString(prior.media_type)) {
      receipt.media_type = shortString(prior.media_type);
    }
    outputReceipts.push(receipt);
  }
  return {
    schema_version: "journal_bank.artifact_receipts.v1",
    source_receipts: sourceReceipts,
    output_receipts: outputReceipts,
  };
}

function validateReceiptBundle(outputDir, roots, baseline, initialBundle) {
  const bundle = readJsonFileIfPresent(path.join(outputDir, "artifact_receipts.json"));
  if (
    !hasExactKeys(bundle, ["schema_version", "source_receipts", "output_receipts"]) ||
    bundle.schema_version !== "journal_bank.artifact_receipts.v1" ||
    !Array.isArray(bundle.source_receipts) ||
    !Array.isArray(bundle.output_receipts) ||
    !canonicalJsonEqual(bundle.source_receipts, baseline.sourceReceipts)
  ) {
    throw new Error("artifact receipt bundle is invalid");
  }
  const receipts = [...bundle.source_receipts, ...bundle.output_receipts];
  const ids = new Set();
  const paths = new Set();
  for (const receipt of receipts) {
    validateArtifactReceiptAgainstRoots(receipt, roots);
    const pathKey = `${receipt.root_id}:${receipt.path}`;
    if (ids.has(receipt.artifact_id) || paths.has(pathKey)) {
      throw new Error("artifact receipt bundle contains duplicate identities");
    }
    ids.add(receipt.artifact_id);
    paths.add(pathKey);
  }
  const expectedBundle = expectedResealedReceiptBundle(
    outputDir,
    initialBundle,
    baseline.sourceReceipts,
  );
  if (!canonicalJsonEqual(bundle, expectedBundle)) {
    throw new Error("artifact receipt bundle is not deterministically resealed");
  }
  return bundle;
}

function captureTrustedAssuranceBaseline(outputDir) {
  validateOutputDirectoryTree(outputDir);
  const roots = sourceRootsForOutput(outputDir);
  const envelope = readJsonFileIfPresent(path.join(outputDir, "assurance_envelope.json"));
  if (!envelope) throw new Error("Journal-Bank assurance baseline is unavailable.");
  const validated = validateAssuranceEnvelopeStructure(envelope, roots);
  const persistedGates = readJsonFileIfPresent(path.join(outputDir, "assurance_gates.json"));
  if (
    !persistedGates ||
    !canonicalJsonEqual(
      validateGateRegister(persistedGates),
      validated.gateRegister,
    )
  ) {
    throw new Error("Journal-Bank assurance baseline is invalid.");
  }
  const sourceReceipts = validated.artifacts.filter(
    (receipt) => receipt.role === "source",
  );
  return {
    envelope: JSON.parse(JSON.stringify(envelope)),
    gates: JSON.parse(JSON.stringify(validated.gateRegister)),
    reviewedDecisions: JSON.parse(JSON.stringify(envelope.reviewed_decisions)),
    sourceQualifications: JSON.parse(JSON.stringify(envelope.source_qualifications)),
    sourceReceipts: JSON.parse(JSON.stringify(sourceReceipts)),
    outputSnapshots: outputFileSnapshots(outputDir),
    outputTreeModes: outputTreeModeSnapshots(outputDir),
  };
}

function replayTrustedAssuranceBaseline(outputDir, baseline, replayResult) {
  try {
    validateOutputDirectoryTree(outputDir);
    const roots = sourceRootsForOutput(outputDir);
    const persistedEnvelope = readJsonFileIfPresent(
      path.join(outputDir, "assurance_envelope.json"),
    );
    const persistedGates = readJsonFileIfPresent(
      path.join(outputDir, "assurance_gates.json"),
    );
    const persistedReplay = readJsonFileIfPresent(
      path.join(outputDir, "review_baseline_replay.json"),
    );
    const expectedReplayContent = {
      schema_version: "journal_bank.review_baseline_replay.v1",
      run_id: baseline.envelope.run_id,
      envelope_path: "assurance_envelope.json",
      envelope_content_sha256: baseline.envelope.content_sha256,
      replayed_on: replayResult?.replayed_on,
      artifact_snapshots: baseline.envelope.artifact_receipts.map(
        (receipt) => ({
          artifact_id: receipt.artifact_id,
          root_id: receipt.root_id,
          path: receipt.path,
          byte_count: receipt.byte_count,
          sha256: receipt.sha256,
        }),
      ),
    };
    const expectedReplay = {
      ...expectedReplayContent,
      content_sha256: canonicalJsonSha256(expectedReplayContent),
    };
    if (
      !persistedEnvelope ||
      !persistedGates ||
      !persistedReplay ||
      !canonicalJsonEqual(persistedEnvelope, baseline.envelope) ||
      !canonicalJsonEqual(persistedGates, baseline.gates) ||
      !canonicalJsonEqual(replayResult, expectedReplay) ||
      !canonicalJsonEqual(persistedReplay, expectedReplay)
    ) {
      throw new Error("assurance baseline changed during preflight");
    }
    validateWorkflowChildFileDelta(
      baseline.outputSnapshots,
      outputFileSnapshots(outputDir),
      {
        mutable: new Set(["review_baseline_replay.json"]),
        additions: new Set(["review_baseline_replay.json"]),
      },
    );
    validateWorkflowChildTreeModes(
      baseline.outputTreeModes,
      outputTreeModeSnapshots(outputDir),
      {
        additions: new Set(["review_baseline_replay.json"]),
      },
    );
    validateAssuranceEnvelopeStructure(baseline.envelope, roots);
  } catch {
    throw new Error(workflowChildMessages("preflight").invalid);
  }
}

function validateWorkflowScriptResult(parsed, phase) {
  if (!isPlainObject(parsed)) return false;
  if (phase === "client_run") {
    return (
      parsed.ok === true &&
      parsed.schema_version === "vera.client_workflow_context.v2" &&
      parsed.workflow_id === "journal-bank-reconciliation" &&
      typeof parsed.client_run_id === "string" &&
      Boolean(parsed.client_run_id.trim())
    );
  }
  if (phase === "preflight") {
    const content = { ...parsed };
    delete content.content_sha256;
    return (
      parsed.schema_version === "journal_bank.review_baseline_replay.v1" &&
      typeof parsed.run_id === "string" &&
      Boolean(parsed.run_id.trim()) &&
      parsed.envelope_path === "assurance_envelope.json" &&
      /^[0-9a-f]{64}$/.test(parsed.envelope_content_sha256 || "") &&
      /^\d{4}-\d{2}-\d{2}$/.test(parsed.replayed_on || "") &&
      Array.isArray(parsed.artifact_snapshots) &&
      parsed.artifact_snapshots.every(
        (receipt) =>
          isPlainObject(receipt) &&
          typeof receipt.artifact_id === "string" &&
          typeof receipt.root_id === "string" &&
          safeRelativeArtifactPath(receipt.path) &&
          Number.isInteger(receipt.byte_count) &&
          receipt.byte_count >= 0 &&
          /^[0-9a-f]{64}$/.test(receipt.sha256 || ""),
      ) &&
      /^[0-9a-f]{64}$/.test(parsed.content_sha256 || "") &&
      canonicalJsonSha256(content) === parsed.content_sha256
    );
  }
  return parsed.ok === true;
}

function parseWorkflowScriptOutput(completed, phase) {
  const messages = workflowChildMessages(phase);
  if (completed.error) throw new Error(messages.start);
  if (completed.status !== 0) throw new Error(messages.failure);
  const stdout = typeof completed.stdout === "string" ? completed.stdout : "";
  const output = stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  if (!output || output.length > CHILD_RESULT_MAX_CHARS) {
    throw new Error(messages.invalid);
  }
  let parsed;
  try {
    parsed = JSON.parse(output);
  } catch {
    throw new Error(messages.invalid);
  }
  if (!validateWorkflowScriptResult(parsed, phase)) {
    throw new Error(messages.invalid);
  }
  return parsed;
}

function runWorkflowPython(args, phase) {
  let completed;
  try {
    completed = spawnSync(
      pythonExecutable(),
      ["-I", "-B", ...args],
      {
        cwd: PLUGIN_ROOT,
        encoding: "utf8",
        maxBuffer: CHILD_OUTPUT_MAX_BYTES,
        detached: process.platform !== "win32",
      },
    );
  } catch {
    throw new Error(workflowChildMessages(phase).start);
  }
  if (
    process.platform !== "win32" &&
    !completed.error &&
    Number.isInteger(completed.pid) &&
    completed.pid > 0
  ) {
    try {
      process.kill(-completed.pid, "SIGKILL");
    } catch (error) {
      if (error?.code !== "ESRCH") {
        throw new Error(workflowChildMessages(phase).failure);
      }
    }
  }
  return parseWorkflowScriptOutput(completed, phase);
}

function preflightClientRun(outputDir, expectedRunId) {
  if (!outputDir) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const result = runWorkflowPython(
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--client-run-preflight-only",
    ],
    "client_run",
  );
  if (result.client_run_id !== expectedRunId) {
    throw new Error("Journal-Bank customer-run preflight returned an invalid result.");
  }
  return result;
}

function preflightWorkflowReviewApplication(
  outputDir,
  canonicalOutputDir = null,
) {
  if (!outputDir) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const localDate = (value) =>
    [
      value.getFullYear().toString().padStart(4, "0"),
      (value.getMonth() + 1).toString().padStart(2, "0"),
      value.getDate().toString().padStart(2, "0"),
    ].join("-");
  const startedOn = localDate(new Date());
  const args = [scriptPath, "--output-dir", outputDir, "--preflight-only"];
  if (canonicalOutputDir) {
    args.push("--canonical-output-dir", canonicalOutputDir);
  }
  const result = runWorkflowPython(args, "preflight");
  const completedOn = localDate(new Date());
  if (![startedOn, completedOn].includes(result.replayed_on)) {
    throw new Error(workflowChildMessages("preflight").invalid);
  }
  return result;
}

function outputFileSnapshots(outputDir) {
  validateOutputDirectoryTree(outputDir);
  const snapshots = new Map();
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current)) {
      const candidate = path.join(current, name);
      const candidateStat = pathEntryStat(candidate);
      if (!candidateStat) throw new Error("output artifact disappeared");
      if (candidateStat.isDirectory()) {
        pending.push(candidate);
        continue;
      }
      const relative = normalizeRelativePath(path.relative(outputDir, candidate));
      snapshots.set(relative, readRegularFileSnapshot(candidate));
    }
  }
  return snapshots;
}

function outputTreeModeSnapshots(outputDir) {
  validateOutputDirectoryTree(outputDir);
  const snapshots = new Map();
  const rootStat = pathEntryStat(outputDir);
  snapshots.set(".", {
    kind: "directory",
    mode: rootStat.mode & 0o777,
  });
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current)) {
      const candidate = path.join(current, name);
      const candidateStat = pathEntryStat(candidate);
      if (!candidateStat) throw new Error("output artifact disappeared");
      const relative = normalizeRelativePath(
        path.relative(outputDir, candidate),
      );
      if (candidateStat.isDirectory()) {
        snapshots.set(relative, {
          kind: "directory",
          mode: candidateStat.mode & 0o777,
        });
        pending.push(candidate);
      } else {
        snapshots.set(relative, {
          kind: "file",
          mode: candidateStat.mode & 0o777,
        });
      }
    }
  }
  return snapshots;
}

function workflowNativeEffects(appliedDecisions) {
  const effects = Array.isArray(appliedDecisions?.effects)
    ? appliedDecisions.effects
    : [];
  return effects.filter(
    (effect) =>
      isPlainObject(effect) &&
      effect.action === "edit" &&
      effect.artifact_update === "structured_artifact_updated" &&
      artifactPathKey(effect.target_artifact) === "reconciliation_matches.csv" &&
      effect.requires_native_regeneration === true &&
      canonicalJsonEqual(effect.derived_native_regeneration_paths, [
        "journal_bank_reconciliation.xlsx",
      ]),
  );
}

function pythonSafeItemId(value) {
  return (
    shortString(value)
      .replace(/[^a-zA-Z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "item"
  );
}

function expectedWorkflowChildPaths(expectedAppliedDecisions) {
  const nativeEffects = workflowNativeEffects(expectedAppliedDecisions);
  const nativeBackupPaths = nativeEffects.length
    ? [
      `revisions/originals/journal_bank_reconciliation__${pythonSafeItemId(
        nativeEffects[0].item_id,
      )}.xlsx`,
      ]
    : [];
  return {
    nativeEffects,
    nativeBackupPaths,
    mutable: new Set([
      "applied_decisions.json",
      "artifact_receipts.json",
      "assurance_gates.json",
      "final_artifacts.json",
      "reconciliation_audit.json",
      "reviewed_decisions.json",
      "run_intake.json",
      ...(nativeEffects.length ? ["journal_bank_reconciliation.xlsx"] : []),
    ]),
    additions: new Set([
      "assurance_envelope.reviewed.json",
      ...nativeBackupPaths,
    ]),
  };
}

function validateWorkflowChildFileDelta(before, after, expectedPaths) {
  for (const [relative, snapshot] of before) {
    if (expectedPaths.mutable.has(relative) || expectedPaths.additions.has(relative)) {
      continue;
    }
    const current = after.get(relative);
    if (
      !current ||
      current.byte_count !== snapshot.byte_count ||
      current.sha256 !== snapshot.sha256 ||
      current.mode !== snapshot.mode
    ) {
      throw new Error("workflow child changed an unauthorized artifact");
    }
  }
  for (const relative of after.keys()) {
    if (
      !before.has(relative) &&
      !expectedPaths.additions.has(relative)
    ) {
      throw new Error("workflow child created an unauthorized artifact");
    }
  }
}

function validateWorkflowChildTreeModes(before, after, expectedPaths) {
  for (const [relative, snapshot] of before) {
    const current = after.get(relative);
    if (
      !current ||
      current.kind !== snapshot.kind ||
      current.mode !== snapshot.mode
    ) {
      throw new Error("workflow child changed an artifact mode");
    }
  }
  for (const [relative, snapshot] of after) {
    if (before.has(relative)) continue;
    if (
      snapshot.kind !== "file" ||
      snapshot.mode !== 0o644 ||
      !expectedPaths.additions.has(relative)
    ) {
      throw new Error("workflow child created a non-canonical tree entry");
    }
  }
}

function normalizedAppliedBinding(value) {
  const normalized = JSON.parse(JSON.stringify(value));
  for (const field of [
    "application_status",
    "assurance_report_ready",
    "assurance_limitations",
    "semantic_review_decision_ref",
  ]) {
    delete normalized[field];
  }
  return normalized;
}

function expectedAppliedAfterWorkflow(context, expectedPaths) {
  const expected = JSON.parse(JSON.stringify(context.expectedAppliedDecisions));
  const nativeItemIds = new Set(
    expectedPaths.nativeEffects.map((effect) => effect.item_id),
  );
  expected.effects = expected.effects.map((effect) => {
    if (!nativeItemIds.has(effect.item_id)) return effect;
    return {
      ...effect,
      requires_native_regeneration: false,
      native_regeneration_status: "regenerated",
      native_regenerated_paths: ["journal_bank_reconciliation.xlsx"],
    };
  });
  const pendingPaths = Array.from(
    new Set(
      expected.effects
        .filter((effect) => effect.requires_native_regeneration === true)
        .flatMap((effect) => nativeRegenerationPathsForEffect(effect)),
    ),
  ).sort();
  expected.native_regeneration_count = pendingPaths.length;
  expected.native_regeneration_paths = pendingPaths;
  expected.native_regenerated_count = expectedPaths.nativeEffects.length;
  expected.native_regenerated_paths = expectedPaths.nativeEffects.length
    ? ["journal_bank_reconciliation.xlsx"]
    : [];
  expected.original_backup_paths = Array.from(
    new Set([
      ...context.expectedAppliedDecisions.original_backup_paths,
      ...expectedPaths.nativeBackupPaths,
    ]),
  );
  return expected;
}

const JOURNAL_BANK_WORKBOOK_SHEETS = {
  matches: "reconciliation_matches.csv",
  relationship_residuals: "relationship_residuals.csv",
  unmatched_bank: "unmatched_bank.csv",
  unmatched_journal: "unmatched_journal.csv",
  bank_pdf_non_movements: "bank_pdf_non_movement_rows.csv",
  normalized_bank: "normalized_bank.csv",
  normalized_journal: "normalized_journal.csv",
};

const XLSX_MAX_ENTRY_COUNT = 10_000;
const XLSX_MAX_ENTRY_BYTES = 25_000_000;
const XLSX_MAX_TOTAL_BYTES = 100_000_000;
const CRC32_TABLE = Array.from({ length: 256 }, (_, value) => {
  let current = value;
  for (let bit = 0; bit < 8; bit += 1) {
    current =
      (current & 1) !== 0
        ? 0xedb88320 ^ (current >>> 1)
        : current >>> 1;
  }
  return current >>> 0;
});

function crc32(value) {
  let current = 0xffffffff;
  for (const byte of value) {
    current = CRC32_TABLE[(current ^ byte) & 0xff] ^ (current >>> 8);
  }
  return (current ^ 0xffffffff) >>> 0;
}

function validateXmlEntities(value) {
  const validCodePoint = (codePoint) =>
    codePoint === 0x9 ||
    codePoint === 0xa ||
    codePoint === 0xd ||
    (codePoint >= 0x20 && codePoint <= 0xd7ff) ||
    (codePoint >= 0xe000 && codePoint <= 0xfffd) ||
    (codePoint >= 0x10000 && codePoint <= 0x10ffff);
  const withoutEntities = String(value).replace(
    /&(?:amp|apos|gt|lt|quot|#\d+|#x[0-9a-f]+);/gi,
    (entity) => {
      if (entity.startsWith("&#")) {
        const hexadecimal = entity.slice(0, 3).toLowerCase() === "&#x";
        const codePoint = Number.parseInt(
          entity.slice(hexadecimal ? 3 : 2, -1),
          hexadecimal ? 16 : 10,
        );
        if (!validCodePoint(codePoint)) {
          throw new Error("workbook XML character reference is invalid");
        }
      }
      return "";
    },
  );
  if (withoutEntities.includes("&")) {
    throw new Error("workbook XML contains an invalid entity");
  }
  for (const character of withoutEntities) {
    if (!validCodePoint(character.codePointAt(0))) {
      throw new Error("workbook XML character is invalid");
    }
  }
}

function validateWellFormedXml(xml) {
  if (/<!DOCTYPE|<!ENTITY/i.test(xml)) {
    throw new Error("workbook XML declarations are unsafe");
  }
  const namePattern = /^[A-Za-z_][A-Za-z0-9_.:-]*/;
  const stack = [];
  let rootSeen = false;
  let markupSeen = false;
  let xmlDeclarationSeen = false;
  let offset = 0;
  while (offset < xml.length) {
    const tagOffset = xml.indexOf("<", offset);
    const text = tagOffset < 0 ? xml.slice(offset) : xml.slice(offset, tagOffset);
    validateXmlEntities(text);
    if (stack.length === 0 && text.trim() !== "") {
      throw new Error("workbook XML has content outside its root");
    }
    if (tagOffset < 0) {
      offset = xml.length;
      break;
    }
    if (xml.startsWith("<!--", tagOffset)) {
      const end = xml.indexOf("-->", tagOffset + 4);
      if (
        end < 0 ||
        xml.slice(tagOffset + 4, end).includes("--")
      ) {
        throw new Error("workbook XML comment is invalid");
      }
      markupSeen = true;
      offset = end + 3;
      continue;
    }
    if (xml.startsWith("<![CDATA[", tagOffset)) {
      if (stack.length === 0) {
        throw new Error("workbook XML CDATA is outside its root");
      }
      const end = xml.indexOf("]]>", tagOffset + 9);
      if (end < 0) throw new Error("workbook XML CDATA is unclosed");
      offset = end + 3;
      continue;
    }
    if (xml.startsWith("<?", tagOffset)) {
      const end = xml.indexOf("?>", tagOffset + 2);
      if (end < 0) {
        throw new Error("workbook XML processing instruction is unclosed");
      }
      const instruction = xml.slice(tagOffset + 2, end).trim();
      const target = instruction.match(namePattern)?.[0] || "";
      if (!target) {
        throw new Error("workbook XML processing instruction is invalid");
      }
      if (target.toLowerCase() === "xml") {
        const prefix = xml.slice(0, tagOffset);
        if (
          target !== "xml" ||
          xmlDeclarationSeen ||
          markupSeen ||
          rootSeen ||
          stack.length !== 0 ||
          !["", "\ufeff"].includes(prefix)
        ) {
          throw new Error("workbook XML declaration is misplaced");
        }
        if (
          !/^xml\s+version\s*=\s*(?:"1\.0"|'1\.0')(?:\s+encoding\s*=\s*(?:"utf-8"|'utf-8'))?(?:\s+standalone\s*=\s*(?:"(?:yes|no)"|'(?:yes|no)'))?\s*$/i.test(
            instruction,
          )
        ) {
          throw new Error("workbook XML declaration is invalid");
        }
        xmlDeclarationSeen = true;
      }
      markupSeen = true;
      offset = end + 2;
      continue;
    }
    if (xml.startsWith("<!", tagOffset)) {
      throw new Error("workbook XML declaration is unsupported");
    }
    if (xml.startsWith("</", tagOffset)) {
      const end = xml.indexOf(">", tagOffset + 2);
      if (end < 0) throw new Error("workbook XML closing tag is unclosed");
      const closing = xml.slice(tagOffset + 2, end).trim();
      if (
        !namePattern.test(closing) ||
        closing.match(namePattern)[0] !== closing ||
        stack.pop()?.name !== closing
      ) {
        throw new Error("workbook XML closing tag is invalid");
      }
      offset = end + 1;
      continue;
    }
    let end = tagOffset + 1;
    let quote = null;
    for (; end < xml.length; end += 1) {
      const character = xml[end];
      if (quote !== null) {
        if (character === quote) quote = null;
      } else if (character === '"' || character === "'") {
        quote = character;
      } else if (character === ">") {
        break;
      }
    }
    if (end >= xml.length || quote !== null) {
      throw new Error("workbook XML opening tag is unclosed");
    }
    let declaration = xml.slice(tagOffset + 1, end).trim();
    const selfClosing = declaration.endsWith("/");
    if (selfClosing) declaration = declaration.slice(0, -1).trimEnd();
    const nameMatch = declaration.match(namePattern);
    if (!nameMatch) throw new Error("workbook XML tag name is invalid");
    const name = nameMatch[0];
    let attributes = declaration.slice(name.length);
    const attributeNames = new Set();
    const attributeValues = new Map();
    while (attributes.trim() !== "") {
      attributes = attributes.trimStart();
      const attributeMatch = attributes.match(namePattern);
      if (!attributeMatch) {
        throw new Error("workbook XML attribute name is invalid");
      }
      const attributeName = attributeMatch[0];
      if (attributeNames.has(attributeName)) {
        throw new Error("workbook XML attribute is duplicated");
      }
      attributeNames.add(attributeName);
      attributes = attributes.slice(attributeName.length).trimStart();
      if (!attributes.startsWith("=")) {
        throw new Error("workbook XML attribute assignment is invalid");
      }
      attributes = attributes.slice(1).trimStart();
      const attributeQuote = attributes[0];
      if (!['"', "'"].includes(attributeQuote)) {
        throw new Error("workbook XML attribute value is unquoted");
      }
      const attributeEnd = attributes.indexOf(attributeQuote, 1);
      if (attributeEnd < 0) {
        throw new Error("workbook XML attribute value is unclosed");
      }
      const attributeValue = attributes.slice(1, attributeEnd);
      if (attributeValue.includes("<")) {
        throw new Error("workbook XML attribute value is invalid");
      }
      validateXmlEntities(attributeValue);
      attributeValues.set(attributeName, attributeValue);
      attributes = attributes.slice(attributeEnd + 1);
    }
    const inheritedNamespaces = stack.length
      ? stack[stack.length - 1].namespaces
      : new Map([
          ["xml", "http://www.w3.org/XML/1998/namespace"],
        ]);
    const namespaces = new Map(inheritedNamespaces);
    for (const [attributeName, attributeValue] of attributeValues) {
      if (attributeName === "xmlns") {
        namespaces.set("", attributeValue);
      } else if (attributeName.startsWith("xmlns:")) {
        const namespacePrefix = attributeName.slice("xmlns:".length);
        if (
          !/^[A-Za-z_][A-Za-z0-9_.-]*$/.test(namespacePrefix) ||
          namespacePrefix === "xmlns" ||
          (namespacePrefix === "xml" &&
            attributeValue !==
              "http://www.w3.org/XML/1998/namespace") ||
          (namespacePrefix !== "xml" && attributeValue === "")
        ) {
          throw new Error("workbook XML namespace declaration is invalid");
        }
        namespaces.set(namespacePrefix, attributeValue);
      }
    }
    const validateQualifiedName = (qualifiedName, { attribute = false } = {}) => {
      const parts = qualifiedName.split(":");
      if (parts.length > 2) {
        throw new Error("workbook XML qualified name is invalid");
      }
      if (parts.length === 1) return;
      const [namespacePrefix] = parts;
      if (
        namespacePrefix === "xmlns" ||
        (!namespaces.has(namespacePrefix) &&
          !(attribute && namespacePrefix === "xml"))
      ) {
        throw new Error("workbook XML namespace prefix is unbound");
      }
    };
    validateQualifiedName(name);
    for (const attributeName of attributeNames) {
      if (
        attributeName === "xmlns" ||
        attributeName.startsWith("xmlns:")
      ) {
        continue;
      }
      validateQualifiedName(attributeName, { attribute: true });
    }
    if (stack.length === 0) {
      if (rootSeen) throw new Error("workbook XML has multiple roots");
      rootSeen = true;
    }
    markupSeen = true;
    if (!selfClosing) stack.push({ name, namespaces });
    offset = end + 1;
  }
  if (!rootSeen || stack.length !== 0) {
    throw new Error("workbook XML root is incomplete");
  }
}

function xlsxXmlEntries(workbookPath) {
  const archive = fs.readFileSync(workbookPath);
  if (archive.length < 22) throw new Error("workbook ZIP is truncated");
  const minimumOffset = Math.max(0, archive.length - 65_557);
  let endOffset = -1;
  for (let offset = archive.length - 22; offset >= minimumOffset; offset -= 1) {
    if (archive.readUInt32LE(offset) === 0x06054b50) {
      endOffset = offset;
      break;
    }
  }
  if (endOffset < 0) throw new Error("workbook ZIP directory is missing");
  const disk = archive.readUInt16LE(endOffset + 4);
  const directoryDisk = archive.readUInt16LE(endOffset + 6);
  const diskEntries = archive.readUInt16LE(endOffset + 8);
  const entryCount = archive.readUInt16LE(endOffset + 10);
  const directorySize = archive.readUInt32LE(endOffset + 12);
  const directoryOffset = archive.readUInt32LE(endOffset + 16);
  if (
    disk !== 0 ||
    directoryDisk !== 0 ||
    diskEntries !== entryCount ||
    entryCount === 0 ||
    entryCount > XLSX_MAX_ENTRY_COUNT ||
    directoryOffset + directorySize > endOffset
  ) {
    throw new Error("workbook ZIP directory is invalid");
  }
  const xmlEntries = new Map();
  const entryDigests = {};
  const names = new Set();
  let totalBytes = 0;
  let offset = directoryOffset;
  for (let index = 0; index < entryCount; index += 1) {
    if (
      offset + 46 > archive.length ||
      archive.readUInt32LE(offset) !== 0x02014b50
    ) {
      throw new Error("workbook ZIP entry is invalid");
    }
    const flags = archive.readUInt16LE(offset + 8);
    const compression = archive.readUInt16LE(offset + 10);
    const expectedCrc = archive.readUInt32LE(offset + 16);
    const compressedSize = archive.readUInt32LE(offset + 20);
    const uncompressedSize = archive.readUInt32LE(offset + 24);
    const nameLength = archive.readUInt16LE(offset + 28);
    const extraLength = archive.readUInt16LE(offset + 30);
    const commentLength = archive.readUInt16LE(offset + 32);
    const localOffset = archive.readUInt32LE(offset + 42);
    const nextOffset =
      offset + 46 + nameLength + extraLength + commentLength;
    if (
      nextOffset > archive.length ||
      compressedSize === 0xffffffff ||
      uncompressedSize === 0xffffffff ||
      uncompressedSize > XLSX_MAX_ENTRY_BYTES ||
      ![0, 8].includes(compression) ||
      (flags & (1 | 8)) !== 0
    ) {
      throw new Error("workbook ZIP entry is unsupported");
    }
    const name = archive
      .subarray(offset + 46, offset + 46 + nameLength)
      .toString("utf8");
    if (
      !name ||
      name.includes("\\") ||
      name.startsWith("/") ||
      name.split("/").includes("..") ||
      names.has(name)
    ) {
      throw new Error("workbook ZIP entry path is invalid");
    }
    names.add(name);
    totalBytes += uncompressedSize;
    if (totalBytes > XLSX_MAX_TOTAL_BYTES) {
      throw new Error("workbook ZIP expands beyond its limit");
    }
    if (
      localOffset + 30 > archive.length ||
      archive.readUInt32LE(localOffset) !== 0x04034b50
    ) {
      throw new Error("workbook ZIP local entry is invalid");
    }
    const localNameLength = archive.readUInt16LE(localOffset + 26);
    const localExtraLength = archive.readUInt16LE(localOffset + 28);
    const localName = archive
      .subarray(localOffset + 30, localOffset + 30 + localNameLength)
      .toString("utf8");
    const dataOffset =
      localOffset + 30 + localNameLength + localExtraLength;
    if (
      archive.readUInt16LE(localOffset + 6) !== flags ||
      archive.readUInt16LE(localOffset + 8) !== compression ||
      archive.readUInt32LE(localOffset + 14) !== expectedCrc ||
      archive.readUInt32LE(localOffset + 18) !== compressedSize ||
      archive.readUInt32LE(localOffset + 22) !== uncompressedSize ||
      localName !== name ||
      dataOffset + compressedSize > directoryOffset
    ) {
      throw new Error("workbook ZIP entry bytes are truncated");
    }
    const compressed = archive.subarray(
      dataOffset,
      dataOffset + compressedSize,
    );
    let content;
    try {
      content =
        compression === 0
          ? Buffer.from(compressed)
          : zlib.inflateRawSync(compressed, {
              maxOutputLength: XLSX_MAX_ENTRY_BYTES,
            });
    } catch {
      throw new Error("workbook ZIP entry cannot be decompressed");
    }
    if (content.length !== uncompressedSize) {
      throw new Error("workbook ZIP entry size is stale");
    }
    if (crc32(content) !== expectedCrc) {
      throw new Error("workbook ZIP entry checksum is stale");
    }
    entryDigests[name] = crypto
      .createHash("sha256")
      .update(content)
      .digest("hex");
    if (/\.(?:xml|rels)$/.test(name)) {
      let xml;
      try {
        xml = new TextDecoder("utf-8", { fatal: true }).decode(content);
      } catch {
        throw new Error("workbook XML is not valid UTF-8");
      }
      validateWellFormedXml(xml);
    }
    if (
      name === "xl/workbook.xml" ||
      name === "xl/_rels/workbook.xml.rels" ||
      name === "xl/sharedStrings.xml" ||
      name === "xl/styles.xml" ||
      name === "xl/theme/theme1.xml" ||
      name === "docProps/core.xml" ||
      /^xl\/worksheets\/[^/]+\.xml$/.test(name)
    ) {
      xmlEntries.set(
        name,
        new TextDecoder("utf-8", { fatal: true }).decode(content),
      );
    }
    offset = nextOffset;
  }
  if (offset !== directoryOffset + directorySize) {
    throw new Error("workbook ZIP directory size is stale");
  }
  return {
    xmlEntries,
    entryDigests,
    entryNames: Array.from(names).sort(),
  };
}

function decodeXmlText(value) {
  return String(value).replace(
    /&(?:#x[0-9a-f]+|#\d+|amp|apos|gt|lt|quot);/gi,
    (entity) => {
      const lower = entity.toLowerCase();
      if (lower.startsWith("&#x")) {
        return String.fromCodePoint(
          Number.parseInt(lower.slice(3, -1), 16),
        );
      }
      if (lower.startsWith("&#")) {
        return String.fromCodePoint(
          Number.parseInt(lower.slice(2, -1), 10),
        );
      }
      return {
        "&amp;": "&",
        "&apos;": "'",
        "&gt;": ">",
        "&lt;": "<",
        "&quot;": '"',
      }[lower];
    },
  );
}

function xmlAttribute(fragment, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = String(fragment).match(
    new RegExp(
      `(?:^|\\s)${escaped}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`,
    ),
  );
  return match ? decodeXmlText(match[1] ?? match[2] ?? "") : null;
}

function sharedStringValues(xml) {
  if (!xml) return [];
  const values = [];
  for (const match of xml.matchAll(/<si\b[^>]*>([\s\S]*?)<\/si>/g)) {
    values.push(
      Array.from(match[1].matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g))
        .map((textMatch) => decodeXmlText(textMatch[1]))
        .join(""),
    );
  }
  return values;
}

function worksheetCellValues(xml, sharedStrings) {
  const worksheetRoot = xml.match(
    /^(?:\uFEFF)?(?:<\?xml\b[^?]*\?>)?\s*<worksheet\b([^>]*)>/,
  );
  const worksheetNamespace =
    worksheetRoot && xmlAttribute(worksheetRoot[1], "xmlns");
  if (
    worksheetNamespace !==
      "http://schemas.openxmlformats.org/spreadsheetml/2006/main" ||
    (worksheetRoot &&
      /\sxmlns(?::[A-Za-z_][A-Za-z0-9_.-]*)?\s*=/.test(
        xml.slice(worksheetRoot[0].length),
      )) ||
    /<\/?[A-Za-z_][A-Za-z0-9_.-]*:[A-Za-z_]/.test(xml) ||
    /<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?(?:hyperlink|mergeCell|drawing|legacyDrawing|oleObject)\b/.test(
      xml,
    ) ||
    Array.from(
      xml.matchAll(
        /<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?(?:row|col)\b([^>]*)>/g,
      ),
    ).some((match) =>
      ["1", "true"].includes(
        String(xmlAttribute(match[1], "hidden")).toLowerCase(),
      ),
    )
  ) {
    throw new Error("workbook sheet contains concealed or linked content");
  }
  const values = new Map();
  for (const match of xml.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/g)) {
    const reference = xmlAttribute(match[1], "r");
    const cellType = xmlAttribute(match[1], "t");
    const style = xmlAttribute(match[1], "s");
    if (!reference || !/^[A-Z]+[1-9]\d*$/.test(reference)) {
      throw new Error("workbook cell reference is invalid");
    }
    if (style !== null && style !== "0") {
      throw new Error("workbook cell styles are not permitted");
    }
    const body = match[2];
    let value = "";
    if (
      /<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?f\b/.test(body)
    ) {
      throw new Error("workbook formulas are not permitted");
    } else if (cellType === "inlineStr") {
      value = Array.from(body.matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g))
        .map((textMatch) => decodeXmlText(textMatch[1]))
        .join("");
    } else {
      const raw = body.match(/<v\b[^>]*>([\s\S]*?)<\/v>/);
      const rawValue = raw ? decodeXmlText(raw[1]) : "";
      if (cellType === "s") {
        const sharedIndex = Number(rawValue);
        if (
          !Number.isInteger(sharedIndex) ||
          sharedIndex < 0 ||
          sharedIndex >= sharedStrings.length
        ) {
          throw new Error("workbook shared-string reference is invalid");
        }
        value = sharedStrings[sharedIndex];
      } else {
        value = rawValue;
      }
    }
    if (value !== "") values.set(reference, value);
  }
  return values;
}

function expectedWorksheetCells(rows) {
  const cells = new Map();
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    for (
      let columnIndex = 0;
      columnIndex < rows[rowIndex].length;
      columnIndex += 1
    ) {
      const value = excelSanitizedText(rows[rowIndex][columnIndex]);
      if (value !== "") {
        cells.set(
          `${excelColumnName(columnIndex + 1)}${rowIndex + 1}`,
          value,
        );
      }
    }
  }
  return cells;
}

function workbookPresentationDigests(entries) {
  const result = {};
  for (const name of ["xl/styles.xml", "xl/theme/theme1.xml"]) {
    const content = entries.get(name);
    if (!content) {
      throw new Error("workbook presentation contract is missing");
    }
    result[name] = crypto
      .createHash("sha256")
      .update(content, "utf8")
      .digest("hex");
  }
  return result;
}

function normalizedWorkbookCoreProperties(xml) {
  if (!xml) {
    throw new Error("workbook core properties are missing");
  }
  const instants = {};
  let normalized = xml;
  for (const field of ["created", "modified"]) {
    const pattern = new RegExp(
      `<dcterms:${field}\\b[^>]*>([^<]*)<\\/dcterms:${field}>`,
      "g",
    );
    const values = Array.from(xml.matchAll(pattern));
    if (values.length !== 1) {
      throw new Error("workbook core timestamp is invalid");
    }
    const timestamp = decodeXmlText(values[0][1]).trim();
    const components = timestamp.match(
      /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/,
    );
    if (!components) {
      throw new Error("workbook core timestamp is invalid");
    }
    const [
      ,
      year,
      month,
      day,
      hour,
      minute,
      second,
      fractional = "",
    ] = components;
    const milliseconds = Number(fractional.padEnd(3, "0"));
    const instant = new Date(
      Date.UTC(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour),
        Number(minute),
        Number(second),
        milliseconds,
      ),
    );
    if (
      instant.getUTCFullYear() !== Number(year) ||
      instant.getUTCMonth() !== Number(month) - 1 ||
      instant.getUTCDate() !== Number(day) ||
      instant.getUTCHours() !== Number(hour) ||
      instant.getUTCMinutes() !== Number(minute) ||
      instant.getUTCSeconds() !== Number(second) ||
      instant.getUTCMilliseconds() !== milliseconds
    ) {
      throw new Error("workbook core timestamp is invalid");
    }
    instants[field] = instant.getTime();
    normalized = normalized.replace(
      pattern,
      (element) =>
        element.replace(
          values[0][1],
          `__VOLATILE_${field.toUpperCase()}_TIMESTAMP__`,
        ),
    );
  }
  if (instants.created !== instants.modified) {
    throw new Error("workbook core timestamps are inconsistent");
  }
  return normalized;
}

function workbookStaticEntryDigests(packageData) {
  const digests = Object.fromEntries(
    Object.entries(packageData.entryDigests).filter(
      ([name]) =>
        name !== "docProps/core.xml" &&
        !/^xl\/worksheets\/[^/]+\.xml$/.test(name),
    ),
  );
  digests["docProps/core.xml"] = crypto
    .createHash("sha256")
    .update(
      normalizedWorkbookCoreProperties(
        packageData.xmlEntries.get("docProps/core.xml"),
      ),
      "utf8",
    )
    .digest("hex");
  return digests;
}

function captureWorkbookPresentationContract(workbookPath) {
  const packageData = xlsxXmlEntries(workbookPath);
  return {
    entryNames: packageData.entryNames,
    staticEntryDigests: workbookStaticEntryDigests(packageData),
    presentationDigests: workbookPresentationDigests(
      packageData.xmlEntries,
    ),
  };
}

function validateJournalBankWorkbook(
  outputDir,
  workbookPath,
  expectedPresentation,
) {
  const packageData = xlsxXmlEntries(workbookPath);
  const entries = packageData.xmlEntries;
  if (
    !expectedPresentation ||
    !canonicalJsonEqual(
      packageData.entryNames,
      expectedPresentation.entryNames,
    ) ||
    !canonicalJsonEqual(
      workbookStaticEntryDigests(packageData),
      expectedPresentation.staticEntryDigests,
    ) ||
    !canonicalJsonEqual(
      workbookPresentationDigests(entries),
      expectedPresentation.presentationDigests,
    )
  ) {
    throw new Error("workbook presentation contract changed");
  }
  const workbookXml = entries.get("xl/workbook.xml");
  const relationshipsXml = entries.get("xl/_rels/workbook.xml.rels");
  if (!workbookXml || !relationshipsXml) {
    throw new Error("workbook OOXML relationships are missing");
  }
  const relationships = new Map();
  for (const match of relationshipsXml.matchAll(
    /<Relationship\b([^>]*)\/?>/g,
  )) {
    const id = xmlAttribute(match[1], "Id");
    const target = xmlAttribute(match[1], "Target");
    if (id && target) relationships.set(id, target);
  }
  const sheetEntries = [];
  for (const match of workbookXml.matchAll(/<sheet\b([^>]*)\/?>/g)) {
    const name = xmlAttribute(match[1], "name");
    const relationshipId = xmlAttribute(match[1], "r:id");
    const state = xmlAttribute(match[1], "state");
    if (
      !name ||
      !relationshipId ||
      state !== "visible" ||
      sheetEntries.some(([value]) => value === name)
    ) {
      throw new Error("workbook sheet declaration is invalid");
    }
    sheetEntries.push([name, relationshipId]);
  }
  if (
    !canonicalJsonEqual(
      sheetEntries.map(([name]) => name),
      Object.keys(JOURNAL_BANK_WORKBOOK_SHEETS),
    )
  ) {
    throw new Error("workbook sheets do not match the generated contract");
  }
  const sharedStrings = sharedStringValues(
    entries.get("xl/sharedStrings.xml"),
  );
  for (const [sheetName, relationshipId] of sheetEntries) {
    const target = relationships.get(relationshipId);
    if (!target) throw new Error("workbook sheet relationship is missing");
    const entryName = target.startsWith("/")
      ? path.posix.normalize(target.slice(1))
      : path.posix.normalize(path.posix.join("xl", target));
    if (
      entryName.startsWith("../") ||
      !entryName.startsWith("xl/worksheets/")
    ) {
      throw new Error("workbook sheet relationship escapes its package");
    }
    const sheetXml = entries.get(entryName);
    if (!sheetXml) throw new Error("workbook sheet XML is missing");
    const actualCells = worksheetCellValues(sheetXml, sharedStrings);
    const csvRows = parseCsv(
      fs.readFileSync(
        path.join(outputDir, JOURNAL_BANK_WORKBOOK_SHEETS[sheetName]),
        "utf8",
      ),
    );
    const expectedCells = expectedWorksheetCells(csvRows);
    if (
      actualCells.size !== expectedCells.size ||
      Array.from(expectedCells).some(
        ([reference, value]) => actualCells.get(reference) !== value,
      )
    ) {
      throw new Error("workbook cells do not match canonical CSV values");
    }
  }
}

function excelSanitizedText(value) {
  return String(value ?? "").replace(/[\x00-\x08\x0b-\x0c\x0e-\x1f]/g, "");
}

function excelColumnName(index) {
  let current = index;
  let letters = "";
  while (current > 0) {
    current -= 1;
    letters = String.fromCharCode(65 + (current % 26)) + letters;
    current = Math.floor(current / 26);
  }
  return letters;
}

function expectedWorkbookEvidence(outputDir, nativeEffects) {
  const requiredHeaders = {};
  let matchHeader = [];
  let matchRows = [];
  for (const [sheetName, relativePath] of Object.entries(
    JOURNAL_BANK_WORKBOOK_SHEETS,
  )) {
    const rows = parseCsv(
      fs.readFileSync(path.join(outputDir, relativePath), "utf8"),
    );
    const header = rows.length ? rows[0] : [];
    if (header.length) {
      requiredHeaders[sheetName] = header
        .filter((value) => value !== "")
        .map(excelSanitizedText);
    }
    if (sheetName === "matches") {
      matchHeader = header;
      matchRows = rows.slice(1);
    }
  }
  const cells = {};
  for (const effect of nativeEffects) {
    const update = isPlainObject(effect.structured_update)
      ? effect.structured_update
      : {};
    const idField = shortString(
      update.id_field || effect.target_id_field,
    );
    const recordId = shortString(
      update.record_id || effect.target_record_id,
    );
    const targetField = shortString(
      update.target_field || effect.target_field,
    );
    if (
      !idField ||
      !recordId ||
      !targetField ||
      !matchHeader.includes(idField) ||
      !matchHeader.includes(targetField)
    ) {
      continue;
    }
    const idIndex = matchHeader.indexOf(idField);
    const targetIndex = matchHeader.indexOf(targetField);
    const rowIndex = matchRows.findIndex(
      (row) => String(row[idIndex] ?? "") === recordId,
    );
    if (rowIndex >= 0) {
      cells[`${excelColumnName(targetIndex + 1)}${rowIndex + 2}`] =
        excelSanitizedText(effect.edit_value);
    }
  }
  return {
    sourceRowCount: matchRows.length,
    requiredHeaders,
    requiredCells: Object.keys(cells).length ? { matches: cells } : {},
  };
}

function validateNativeOutputRecords(
  outputDir,
  persistedFinal,
  context,
  expectedPaths,
  expectedApplied,
  preChildSnapshots,
) {
  if (!expectedPaths.nativeEffects.length) return;
  const outputs = persistedFinal.outputs;
  const initialOutputs = context.expectedFinalArtifacts.outputs;
  const workbookEvidence = expectedWorkbookEvidence(
    outputDir,
    expectedPaths.nativeEffects,
  );
  const workbookPath = "journal_bank_reconciliation.xlsx";
  const initialWorkbook = initialOutputs.find(
    (output) => artifactPathKey(output?.path) === workbookPath,
  );
  const currentWorkbook = outputs.find(
    (output) => artifactPathKey(output?.path) === workbookPath,
  );
  const absoluteWorkbookPath = path.join(outputDir, workbookPath);
  const workbookStat = pathEntryStat(absoluteWorkbookPath);
  const expectedWorkbook = {
    ...initialWorkbook,
    path: workbookPath,
    kind: "xlsx",
    status: "updated_from_review",
    native_regenerated: true,
    source_artifact: "reconciliation_matches.csv",
    source_row_count: workbookEvidence.sourceRowCount,
    size_bytes: workbookStat?.size,
    required_sheets: Object.keys(JOURNAL_BANK_WORKBOOK_SHEETS),
    required_sheet_headers: workbookEvidence.requiredHeaders,
    required_cells: workbookEvidence.requiredCells,
  };
  if (
    !initialWorkbook ||
    !workbookStat ||
    !workbookStat.isFile() ||
    !canonicalJsonEqual(currentWorkbook, expectedWorkbook)
  ) {
    throw new Error("regenerated workbook output is not request-bound");
  }
  validateJournalBankWorkbook(
    outputDir,
    absoluteWorkbookPath,
    context.expectedWorkbookPresentation,
  );
  const firstEffect = expectedPaths.nativeEffects[0];
  for (const backupPath of expectedPaths.nativeBackupPaths) {
    const initialBackup = initialOutputs.find(
      (output) => artifactPathKey(output?.path) === backupPath,
    );
    const expectedBackup = {
      ...(initialBackup || {}),
      path: backupPath,
      kind: "xlsx",
      status: "backup_original",
      source_artifact: workbookPath,
      item_id: firstEffect.item_id,
    };
    const currentBackup = outputs.find(
      (output) => artifactPathKey(output?.path) === backupPath,
    );
    const originalSnapshot = preChildSnapshots.get(workbookPath);
    const backupSnapshot = readRegularFileSnapshot(
      path.join(outputDir, backupPath),
    );
    if (
      !canonicalJsonEqual(currentBackup, expectedBackup) ||
      !originalSnapshot ||
      originalSnapshot.byte_count !== backupSnapshot.byte_count ||
      originalSnapshot.sha256 !== backupSnapshot.sha256
    ) {
      throw new Error("native workbook backup is not request-bound");
    }
  }
  if (
    !canonicalJsonEqual(
      expectedApplied.original_backup_paths,
      context.expectedAppliedDecisions.original_backup_paths.concat(
        expectedPaths.nativeBackupPaths,
      ),
    )
  ) {
    throw new Error("native backup paths are not deterministic");
  }
}

function normalizedFinalBinding(value, expectedPaths) {
  const normalized = JSON.parse(JSON.stringify(value));
  delete normalized.status;
  delete normalized.review_status;
  delete normalized.next_actions;
  if (Array.isArray(normalized.outputs)) {
    normalized.outputs = normalized.outputs
      .filter((output) => {
        if (!isPlainObject(output)) return true;
        const outputPath = artifactPathKey(output.path);
        if (
          expectedPaths.nativeEffects.length &&
          outputPath === "journal_bank_reconciliation.xlsx"
        ) {
          return false;
        }
        return !expectedPaths.nativeBackupPaths.includes(outputPath);
      });
  }
  if (isPlainObject(normalized.review_application)) {
    for (const field of [
      "application_status",
      "assurance_report_ready",
      "assurance_limitations",
      "native_regeneration_count",
      "native_regeneration_paths",
      "native_regenerated_count",
      "native_regenerated_paths",
      "original_backup_paths",
    ]) {
      delete normalized.review_application[field];
    }
  }
  return normalized;
}

function validateAppliedAndFinalBinding(
  persistedApplied,
  persistedFinal,
  context,
  expectedPaths,
) {
  const expectedApplied = expectedAppliedAfterWorkflow(context, expectedPaths);
  if (
    !canonicalJsonEqual(
      normalizedAppliedBinding(persistedApplied),
      normalizedAppliedBinding(expectedApplied),
    ) ||
    !canonicalJsonEqual(
      normalizedFinalBinding(persistedFinal, expectedPaths),
      normalizedFinalBinding(context.expectedFinalArtifacts, expectedPaths),
    )
  ) {
    throw new Error("persisted review application is not bound to the request");
  }
  for (const field of ["decision_count", "item_count", "blocker_count"]) {
    if (
      !Number.isInteger(persistedApplied[field]) ||
      persistedApplied[field] !== expectedApplied[field]
    ) {
      throw new Error("persisted review counts are not bound to the request");
    }
  }
  for (const field of [
    "revision_paths",
    "target_update_paths",
    "structured_update_paths",
    "native_regeneration_paths",
    "native_regenerated_paths",
    "original_backup_paths",
  ]) {
    if (!stringArray(persistedApplied[field] || [], { relativePaths: true })) {
      throw new Error("persisted review paths are invalid");
    }
  }
  if (!stringArray(persistedApplied.assurance_limitations || [])) {
    throw new Error("persisted assurance metadata is invalid");
  }
  const outputs = Array.isArray(persistedFinal.outputs)
    ? persistedFinal.outputs
    : null;
  if (
    !outputs ||
    outputs.some(
      (output) =>
        !isPlainObject(output) ||
        !safeRelativeArtifactPath(output.path),
    ) ||
    new Set(outputs.map((output) => output.path)).size !== outputs.length
  ) {
    throw new Error("final artifact paths are invalid");
  }
  const reviewApplication = isPlainObject(persistedFinal.review_application)
    ? persistedFinal.review_application
    : null;
  if (
    !reviewApplication ||
    !canonicalJsonEqual(
      {
        native_regeneration_count:
          reviewApplication.native_regeneration_count,
        native_regeneration_paths:
          reviewApplication.native_regeneration_paths,
        native_regenerated_count:
          reviewApplication.native_regenerated_count,
        native_regenerated_paths:
          reviewApplication.native_regenerated_paths,
        original_backup_paths: reviewApplication.original_backup_paths,
      },
      {
        native_regeneration_count: expectedApplied.native_regeneration_count,
        native_regeneration_paths: expectedApplied.native_regeneration_paths,
        native_regenerated_count: expectedApplied.native_regenerated_count,
        native_regenerated_paths: expectedApplied.native_regenerated_paths,
        original_backup_paths: expectedApplied.original_backup_paths,
      },
    )
  ) {
    throw new Error("final native metadata is not bound to the request");
  }
  return expectedApplied;
}

const WORKFLOW_NEXT_ACTIONS = {
  regenerate: "Regenerate native DOCX/XLSX/PDF outputs before final handoff.",
  final: "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
  complete: "Complete remaining review decisions before final handoff.",
  resolve: "Resolve withheld or failed assurance gates before final handoff.",
};

function expectedFinalNextActions(initialActions, status) {
  const dynamicActions = new Set(Object.values(WORKFLOW_NEXT_ACTIONS));
  const actions = Array.isArray(initialActions)
    ? initialActions.filter(
        (action) =>
          isNonEmptyTrimmedString(action) && !dynamicActions.has(action),
      )
    : [];
  const next =
    status === "final_ready"
      ? WORKFLOW_NEXT_ACTIONS.final
      : status === "partial_review_applied"
        ? WORKFLOW_NEXT_ACTIONS.complete
        : WORKFLOW_NEXT_ACTIONS.resolve;
  return Array.from(new Set([...actions, next]));
}

function validateRunIntakeBinding(
  outputDir,
  context,
  expectedPaths,
  expectedApplied,
) {
  const current = readJsonFileIfPresent(path.join(outputDir, "run_intake.json"));
  const expected = context.expectedRunIntake;
  if (!current || !expected) throw new Error("run intake is unavailable");
  const currentWithoutTrace = { ...current };
  const expectedWithoutTrace = { ...expected };
  delete currentWithoutTrace.execution_trace;
  delete expectedWithoutTrace.execution_trace;
  if (!canonicalJsonEqual(currentWithoutTrace, expectedWithoutTrace)) {
    throw new Error("run intake changed outside review trace authority");
  }
  const currentTrace = current.execution_trace;
  const expectedTrace = expected.execution_trace;
  if (
    !Array.isArray(currentTrace) ||
    !Array.isArray(expectedTrace) ||
    currentTrace.length !== expectedTrace.length ||
    currentTrace.length === 0
  ) {
    throw new Error("review execution trace is invalid");
  }
  const lastIndex = currentTrace.length - 1;
  for (let index = 0; index < lastIndex; index += 1) {
    if (!canonicalJsonEqual(currentTrace[index], expectedTrace[index])) {
      throw new Error("review execution trace changed a prior step");
    }
  }
  const currentStep = currentTrace[lastIndex];
  const expectedStep = expectedTrace[lastIndex];
  if (
    !isPlainObject(currentStep) ||
    !isPlainObject(expectedStep) ||
    expectedStep.kind !== "deterministic_review_apply"
  ) {
    throw new Error("review execution trace step is invalid");
  }
  const currentStepWithoutOutputs = { ...currentStep };
  const expectedStepWithoutOutputs = { ...expectedStep };
  delete currentStepWithoutOutputs.outputs;
  delete expectedStepWithoutOutputs.outputs;
  const currentOutputs = currentStep.outputs;
  const expectedOutputs = expectedStep.outputs;
  if (
    !canonicalJsonEqual(currentStepWithoutOutputs, expectedStepWithoutOutputs) ||
    !stringArray(currentOutputs, { relativePaths: true }) ||
    !stringArray(expectedOutputs, { relativePaths: true }) ||
    new Set(currentOutputs).size !== currentOutputs.length
  ) {
    throw new Error("review execution trace outputs are invalid");
  }
  const expectedCurrentOutputs = Array.from(
    new Set([
      ...expectedOutputs,
      ...expectedApplied.native_regenerated_paths,
      ...expectedPaths.nativeBackupPaths,
    ]),
  );
  if (!canonicalJsonEqual(currentOutputs, expectedCurrentOutputs)) {
    throw new Error("review execution trace contains an unauthorized output");
  }
}

function expectedReviewApplicationDecision(persistedApplied, baseline) {
  const complete =
    persistedApplied.blocker_count === 0 &&
    persistedApplied.decision_count === persistedApplied.item_count;
  if (!complete) return null;
  const content = {
    decision_count: persistedApplied.decision_count,
    item_count: persistedApplied.item_count,
    blocker_count: persistedApplied.blocker_count,
    effects_sha256: canonicalJsonSha256(persistedApplied.effects),
  };
  let reviewerValue = persistedApplied.reviewer_ref || persistedApplied.reviewer;
  if (isPlainObject(reviewerValue)) {
    reviewerValue =
      reviewerValue.reviewer_ref ||
      reviewerValue.id ||
      reviewerValue.email;
  }
  const reviewerRef = isCanonicalIdentifier(reviewerValue)
    ? reviewerValue
    : "reviewer.recorded";
  const reviewedOn = shortString(persistedApplied.applied_at).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reviewedOn)) {
    throw new Error("review application date is invalid");
  }
  return {
    schema_version: "vera.reviewed_decision_receipt.v1",
    decision_id: `decision.review_application.${canonicalJsonSha256(content).slice(0, 16)}`,
    decision_type: "journal_bank_review_application",
    status: "reviewed",
    reviewer_ref: reviewerRef,
    reviewed_on: reviewedOn,
    adapter_id: "journal_bank.review_application",
    adapter_version: "1",
    source_artifact_refs: baseline.sourceReceipts.map(
      (receipt) => receipt.artifact_id,
    ),
    content,
    content_sha256: canonicalJsonSha256(content),
  };
}

function validateReviewedDecisionApplication(
  outputDir,
  context,
  persistedApplied,
) {
  const current = readJsonFileIfPresent(
    path.join(outputDir, "reviewed_decisions.json"),
  );
  const initial = context.expectedReviewedDecisions;
  if (!current || !initial || !Array.isArray(initial.decisions)) {
    throw new Error("reviewed decision evidence is unavailable");
  }
  const decision = expectedReviewApplicationDecision(
    persistedApplied,
    context.trustedAssuranceBaseline,
  );
  const expected = JSON.parse(JSON.stringify(initial));
  if (decision) {
    expected.decisions = expected.decisions.filter(
      (value) => value.decision_id !== decision.decision_id,
    );
    expected.decisions.push(decision);
  }
  if (
    !canonicalJsonEqual(current, expected) ||
    current.decisions.some((value) => {
      try {
        validateReviewedDecisionReceipt(value);
        return false;
      } catch {
        return true;
      }
    }) ||
    persistedApplied.semantic_review_decision_ref !==
      (decision ? decision.decision_id : null)
  ) {
    throw new Error("review application decision is not request-bound");
  }
  return decision;
}

function reconciliationClosureReasons(audit, ledger) {
  const reasons = [];
  if (Number(audit.unmatched_bank_count || 0) !== 0) {
    reasons.push("Unmatched bank rows remain.");
  }
  if (Number(audit.unmatched_journal_count || 0) !== 0) {
    reasons.push("Unmatched journal rows remain.");
  }
  if (audit.relationship_balanced !== true) {
    reasons.push("The audit does not record an exactly balanced relationship.");
  }
  if (!ledger) {
    reasons.push("Relationship ledger is missing.");
  } else if (ledger.balanced !== true) {
    reasons.push("Relationship ledger contains unresolved residuals.");
  } else {
    const residuals = [
      ...(Array.isArray(ledger.source_residuals)
        ? ledger.source_residuals
        : []),
      ...(Array.isArray(ledger.target_residuals)
        ? ledger.target_residuals
        : []),
    ];
    if (
      residuals.some(
        (value) => !isPlainObject(value) || String(value.residual) !== "0",
      )
    ) {
      reasons.push(
        "Relationship ledger is within tolerance but not exactly closed.",
      );
    }
  }
  return reasons;
}

function expectedReviewedGateRegister(
  outputDir,
  context,
  persistedApplied,
  applicationDecision,
) {
  const baseline = context.trustedAssuranceBaseline.gates;
  const gates = baseline.gates;
  const closureReasons = reconciliationClosureReasons(
    context.expectedAudit,
    readJsonFileIfPresent(path.join(outputDir, "relationship_ledger.json")),
  );
  const upstreamSourcePreparation = ["source", "preparation"].every((name) =>
    ["passed", "not_applicable"].includes(gates[name].status),
  );
  const reconciliationPassed =
    ["passed", "not_applicable"].includes(gates.reconciliation.status) &&
    closureReasons.length === 0;
  const complete =
    persistedApplied.blocker_count === 0 &&
    persistedApplied.decision_count === persistedApplied.item_count;
  const reasons = [...closureReasons];
  if (!upstreamSourcePreparation) {
    reasons.push("Source or preparation assurance is not passed.");
  }
  if (!complete) {
    reasons.push("Review decisions are incomplete or contain blockers.");
  }
  const semanticPassed =
    upstreamSourcePreparation && complete && applicationDecision !== null;
  const reportingPassed = reconciliationPassed && semanticPassed;
  const expectedGates = {
    source: gates.source,
    preparation: gates.preparation,
    reconciliation: gates.reconciliation,
    semantic_review: {
      status: semanticPassed ? "passed" : "blocked",
      evidence_refs: semanticPassed
        ? [applicationDecision.decision_id]
        : [],
      limitations: semanticPassed
        ? []
        : [
            "Professional review is incomplete or upstream preparation is blocked.",
          ],
    },
    reporting: {
      status: reportingPassed ? "passed" : "blocked",
      evidence_refs: reportingPassed
        ? ["output.workbook_xlsx", "output.final_artifacts_json"]
        : [],
      limitations: reportingPassed
        ? []
        : reasons.length
          ? reasons
          : ["Reporting assurance remains withheld."],
    },
    publication: gates.publication,
  };
  return {
    schema_version: "vera.assurance_gates.v1",
    gates: expectedGates,
    report_ready: [
      "source",
      "preparation",
      "reconciliation",
      "semantic_review",
      "reporting",
    ].every((name) =>
      ["passed", "not_applicable"].includes(expectedGates[name].status),
    ),
  };
}

function validateGateTransition(current, baseline) {
  validateGateRegister(current);
  for (const name of [
    "source",
    "preparation",
    "reconciliation",
    "publication",
  ]) {
    if (!canonicalJsonEqual(current.gates[name], baseline.gates[name])) {
      throw new Error(`assurance gate changed outside review authority: ${name}`);
    }
  }
}

function validateReviewedEnvelopeForReady(
  outputDir,
  roots,
  currentGates,
  receiptBundle,
  persistedApplied,
  baseline,
) {
  const envelope = readJsonFileIfPresent(
    path.join(outputDir, "assurance_envelope.reviewed.json"),
  );
  if (!envelope) throw new Error("reviewed assurance envelope is missing");
  const validated = validateAssuranceEnvelopeStructure(envelope, roots);
  const implementationReceipts = buildImplementationArtifactReceipts();
  const implementationRefs = implementationReceipts.map(
    (receipt) => receipt.artifact_id,
  );
  const expectedLimitations = [];
  for (const name of ASSURANCE_GATE_NAMES) {
    const gate = currentGates.gates[name];
    if (["passed", "not_applicable"].includes(gate.status)) continue;
    for (const limitation of gate.limitations) {
      if (!expectedLimitations.includes(limitation)) {
        expectedLimitations.push(limitation);
      }
    }
  }
  if (
    envelope.run_id !== baseline.envelope.run_id ||
    envelope.workflow_id !== baseline.envelope.workflow_id ||
    envelope.workflow_version !== baseline.envelope.workflow_version ||
    !canonicalJsonEqual(envelope.gate_register, currentGates) ||
    !canonicalJsonEqual(envelope.limitations, expectedLimitations) ||
    !canonicalJsonEqual(
      envelope.source_qualifications,
      baseline.sourceQualifications,
    ) ||
    envelope.allocation_ledgers.length !== 0 ||
    envelope.numeric_evidence_ledgers.length !== 0 ||
    !canonicalJsonEqual(
      validated.artifacts.filter((receipt) => receipt.role === "source"),
      baseline.sourceReceipts,
    ) ||
    !canonicalJsonEqual(
      envelope.implementation_artifact_refs,
      implementationRefs,
    )
  ) {
    throw new Error("reviewed assurance envelope is not bound to the run");
  }
  const decisionsPayload = readJsonFileIfPresent(
    path.join(outputDir, "reviewed_decisions.json"),
  );
  const qualificationsPayload = readJsonFileIfPresent(
    path.join(outputDir, "source_qualifications.json"),
  );
  if (
    !decisionsPayload ||
    !Array.isArray(decisionsPayload.decisions) ||
    !canonicalJsonEqual(decisionsPayload.decisions, envelope.reviewed_decisions) ||
    !qualificationsPayload ||
    !Array.isArray(qualificationsPayload.qualifications) ||
    !canonicalJsonEqual(
      qualificationsPayload.qualifications,
      envelope.source_qualifications,
    )
  ) {
    throw new Error("reviewed assurance evidence files are stale");
  }
  for (const baselineDecision of baseline.reviewedDecisions) {
    const currentDecision = envelope.reviewed_decisions.find(
      (decision) => decision.decision_id === baselineDecision.decision_id,
    );
    if (!currentDecision || !canonicalJsonEqual(currentDecision, baselineDecision)) {
      throw new Error("reviewed assurance envelope changed a baseline decision");
    }
  }
  const expectedDecisionContent = {
    decision_count: persistedApplied.decision_count,
    item_count: persistedApplied.item_count,
    blocker_count: persistedApplied.blocker_count,
    effects_sha256: canonicalJsonSha256(persistedApplied.effects),
  };
  const semanticReferences = currentGates.gates.semantic_review.evidence_refs;
  const applicationDecisions = envelope.reviewed_decisions.filter(
    (decision) =>
      semanticReferences.includes(decision.decision_id) &&
      decision.decision_type === "journal_bank_review_application" &&
      decision.status === "reviewed" &&
      decision.adapter_id === "journal_bank.review_application" &&
      decision.adapter_version === "1" &&
      canonicalJsonEqual(decision.source_artifact_refs, [
        ...baseline.sourceReceipts.map((receipt) => receipt.artifact_id),
      ]) &&
      canonicalJsonEqual(decision.content, expectedDecisionContent),
  );
  if (
    currentGates.gates.semantic_review.status !== "passed" ||
    applicationDecisions.length !== 1 ||
    persistedApplied.semantic_review_decision_ref !==
      applicationDecisions[0].decision_id
  ) {
    throw new Error("semantic readiness is not bound to the reviewed application");
  }
  const envelopeOutputReceipts = validated.artifacts.filter(
    (receipt) => !["source", "implementation"].includes(receipt.role),
  );
  const expectedEnvelopeOutputs = receiptBundle.output_receipts.filter(
    (receipt) =>
      !["artifact_receipts.json", "assurance_envelope.reviewed.json"].includes(
        receipt.path,
      ),
  );
  const expectedEnvelopeContent = {
    schema_version: "vera.assurance_envelope.v1",
    run_id: baseline.envelope.run_id,
    workflow_id: baseline.envelope.workflow_id,
    workflow_version: baseline.envelope.workflow_version,
    artifact_receipts: [
      ...receiptBundle.source_receipts,
      ...implementationReceipts,
      ...expectedEnvelopeOutputs,
    ],
    implementation_artifact_refs: implementationRefs,
    reviewed_decisions: decisionsPayload.decisions,
    source_qualifications: qualificationsPayload.qualifications,
    allocation_ledgers: [],
    numeric_evidence_ledgers: [],
    gate_register: currentGates,
    limitations: expectedLimitations,
  };
  const expectedEnvelope = {
    ...expectedEnvelopeContent,
    content_sha256: canonicalJsonSha256(expectedEnvelopeContent),
  };
  if (
    !canonicalJsonEqual(envelope, expectedEnvelope) ||
    envelopeOutputReceipts.length !== expectedEnvelopeOutputs.length ||
    expectedEnvelopeOutputs.some((receipt) => {
      const current = envelopeOutputReceipts.find(
        (candidate) => candidate.artifact_id === receipt.artifact_id,
      );
      return !current || !canonicalJsonEqual(current, receipt);
    })
  ) {
    throw new Error("reviewed assurance envelope receipts are stale");
  }
  const receiptPaths = new Set(
    receiptBundle.output_receipts.map((receipt) => receipt.path),
  );
  for (const requiredPath of [
    "applied_decisions.json",
    "assurance_envelope.reviewed.json",
    "assurance_gates.json",
    "final_artifacts.json",
    "reviewed_decisions.json",
    "run_intake.json",
  ]) {
    if (!receiptPaths.has(requiredPath)) {
      throw new Error("reviewed assurance receipt coverage is incomplete");
    }
  }
}

function derivedApplicationStatus(persistedApplied, gates) {
  if (gates.report_ready) return "final_ready";
  if (persistedApplied.blocker_count > 0) return "blocked";
  if (persistedApplied.decision_count < persistedApplied.item_count) {
    return "partial_review_applied";
  }
  return "blocked";
}

function validateWorkflowApplyResultAgainstStaging(
  outputDir,
  appliedOutputPath,
  finalArtifactsPath,
  context,
  preChildSnapshots,
  preChildTreeModes,
) {
  try {
    validateOutputDirectoryTree(outputDir);
    const expectedPaths = expectedWorkflowChildPaths(
      context.expectedAppliedDecisions,
    );
    validateWorkflowChildFileDelta(
      preChildSnapshots,
      outputFileSnapshots(outputDir),
      expectedPaths,
    );
    validateWorkflowChildTreeModes(
      preChildTreeModes,
      outputTreeModeSnapshots(outputDir),
      expectedPaths,
    );
    const persistedApplied = readJsonFileIfPresent(appliedOutputPath);
    const persistedFinal = readJsonFileIfPresent(finalArtifactsPath);
    const persistedUiDecisions = readJsonFileIfPresent(
      path.join(outputDir, "ui_decisions.json"),
    );
    const persistedReviewPayload = readJsonFileIfPresent(
      path.join(outputDir, "review_payload.json"),
    );
    if (
      !persistedApplied ||
      !persistedFinal ||
      !persistedUiDecisions ||
      !persistedReviewPayload ||
      !canonicalJsonEqual(
        persistedUiDecisions,
        context.expectedUiDecisions,
      ) ||
      !canonicalJsonEqual(
        persistedReviewPayload,
        context.expectedReviewPayload,
      )
    ) {
      throw new Error("persisted review inputs are stale");
    }
    const expectedApplied = validateAppliedAndFinalBinding(
      persistedApplied,
      persistedFinal,
      context,
      expectedPaths,
    );
    validateNativeOutputRecords(
      outputDir,
      persistedFinal,
      context,
      expectedPaths,
      expectedApplied,
      preChildSnapshots,
    );
    const roots = sourceRootsForOutput(outputDir);
    for (const receipt of context.trustedAssuranceBaseline.envelope.artifact_receipts) {
      if (receipt.root_id !== "run") {
        validateArtifactReceiptAgainstRoots(receipt, roots);
      }
    }
    const applicationDecision = validateReviewedDecisionApplication(
      outputDir,
      context,
      persistedApplied,
    );
    const currentGates = validateGateRegister(
      readJsonFileIfPresent(path.join(outputDir, "assurance_gates.json")),
    );
    validateGateTransition(currentGates, context.trustedAssuranceBaseline.gates);
    const expectedGates = expectedReviewedGateRegister(
      outputDir,
      context,
      persistedApplied,
      applicationDecision,
    );
    validateGateRegister(expectedGates);
    if (!canonicalJsonEqual(currentGates, expectedGates)) {
      throw new Error("review assurance gates are not request-bound");
    }
    const receiptBundle = validateReceiptBundle(
      outputDir,
      roots,
      context.trustedAssuranceBaseline,
      context.expectedReceiptBundle,
    );
    if (
      !currentGates.report_ready &&
      pathEntryStat(
        path.join(outputDir, "assurance_envelope.reviewed.json"),
      )
    ) {
      throw new Error(
        "reviewed assurance envelope is invalid for a non-ready run",
      );
    }
    if (
      currentGates.report_ready &&
      (persistedApplied.blocker_count !== 0 ||
        persistedApplied.decision_count !== persistedApplied.item_count)
    ) {
      throw new Error("assurance readiness requires a complete unblocked review");
    }
    const status = derivedApplicationStatus(persistedApplied, currentGates);
    const reviewApplication = isPlainObject(persistedFinal.review_application)
      ? persistedFinal.review_application
      : null;
    if (
      persistedApplied.application_status !== status ||
      persistedApplied.assurance_report_ready !== currentGates.report_ready ||
      persistedFinal.status !== status ||
      persistedFinal.review_status !== status ||
      !reviewApplication ||
      reviewApplication.application_status !== status ||
      reviewApplication.assurance_report_ready !== currentGates.report_ready ||
      !canonicalJsonEqual(
        persistedApplied.assurance_limitations,
        currentGates.gates.reporting.limitations,
      ) ||
      !canonicalJsonEqual(
        reviewApplication.assurance_limitations,
        currentGates.gates.reporting.limitations,
      ) ||
      !canonicalJsonEqual(
        persistedFinal.next_actions,
        expectedFinalNextActions(
          context.expectedFinalArtifacts.next_actions,
          status,
        ),
      )
    ) {
      throw new Error("persisted readiness does not match assurance gates");
    }
    const expectedAudit = {
      ...context.expectedAudit,
      review_application_status: status,
      assurance_report_ready: currentGates.report_ready,
    };
    if (
      !context.expectedAudit ||
      !canonicalJsonEqual(
        readJsonFileIfPresent(
          path.join(outputDir, "reconciliation_audit.json"),
        ),
        expectedAudit,
      )
    ) {
      throw new Error("reconciliation audit review state is not request-bound");
    }
    validateRunIntakeBinding(
      outputDir,
      context,
      expectedPaths,
      expectedApplied,
    );
    if (!canonicalJsonEqual(expectedApplied.effects, persistedApplied.effects)) {
      throw new Error("review effects are not request-bound");
    }
    if (currentGates.report_ready) {
      validateReviewedEnvelopeForReady(
        outputDir,
        roots,
        currentGates,
        receiptBundle,
        persistedApplied,
        context.trustedAssuranceBaseline,
      );
    }
    return {
      ok: true,
      application_status: status,
      assurance_report_ready: currentGates.report_ready,
      applied_decisions: persistedApplied,
      final_artifacts: persistedFinal,
    };
  } catch {
    throw new Error(workflowChildMessages("apply").invalid);
  }
}

function applyWorkflowSpecificReviewApplication(
  outputDir,
  appliedOutputPath,
  finalArtifactsPath,
  canonicalOutputDir,
  context,
) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !context?.trustedAssuranceBaseline) return null;
  const validationContext = {
    ...context,
    expectedRunIntake: readJsonFileIfPresent(
      path.join(outputDir, "run_intake.json"),
    ),
    expectedAudit: readJsonFileIfPresent(
      path.join(outputDir, "reconciliation_audit.json"),
    ),
    expectedReviewedDecisions: readJsonFileIfPresent(
      path.join(outputDir, "reviewed_decisions.json"),
    ),
    expectedReceiptBundle: readJsonFileIfPresent(
      path.join(outputDir, "artifact_receipts.json"),
    ),
    expectedWorkbookPresentation: pathEntryStat(
      path.join(outputDir, "journal_bank_reconciliation.xlsx"),
    )?.isFile()
      ? captureWorkbookPresentationContract(
          path.join(outputDir, "journal_bank_reconciliation.xlsx"),
        )
      : null,
  };
  const preChildSnapshots = outputFileSnapshots(outputDir);
  const preChildTreeModes = outputTreeModeSnapshots(outputDir);
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const args = [
    scriptPath,
    "--output-dir",
    outputDir,
    "--applied-decisions",
    appliedOutputPath,
    "--final-artifacts",
    finalArtifactsPath,
  ];
  if (canonicalOutputDir) {
    args.push("--canonical-output-dir", canonicalOutputDir);
  }
  runWorkflowPython(args, "apply");
  return validateWorkflowApplyResultAgainstStaging(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
    validationContext,
    preChildSnapshots,
    preChildTreeModes,
  );
}

function hasWorkflowNativeRegenerationTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (!effect.requires_native_regeneration) return false;
    return nativeRegenerationPathsForEffect(effect).includes("journal_bank_reconciliation.xlsx");
  });
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const issued = issueModelContext(validateReviewPayload(args));
    const result = modelContextIndex(issued.token, issued.context);
    delete result.widget_type;
    result.validation_type = "journal_bank_review";
    result.review_type = issued.context.privatePayload.review_payload.review_type || null;
    result.message = isSpanish(languageFromArgs(issued.context.privatePayload))
      ? "Los datos de revisión son válidos. El payload completo permanece fuera del contexto del modelo; use la referencia opaca para abrir el widget y solicite solo los casos que necesite interpretar."
      : "Journal-Bank review payload is valid. The complete payload stays out of model context; use the opaque reference to render the widget and request only cases that need interpretation.";
    return result;
  }
  if (name === TOOL_NAMES.renderReview) {
    const resolved = privatePayloadForRender(args);
    return {
      ...modelContextIndex(resolved.token, resolved.context),
      _private_review_payload: resolved.context.privatePayload,
    };
  }
  if (name === TOOL_NAMES.caseContext) {
    return modelContextCases(args);
  }
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(
    isSpanish(languageFromArgs(args))
      ? `herramienta desconocida del widget de conciliación entre diario y banco: ${name}`
      : `unknown Journal-Bank widget tool: ${name}`,
  );
}

function toolResult(payload, toolName) {
  const privateReviewPayload = payload?._private_review_payload || null;
  const publicPayload = { ...payload };
  delete publicPayload._private_review_payload;
  const result = {
    content: [{
      type: "text",
      text: JSON.stringify({
        ok: publicPayload.ok !== false,
        run_id: publicPayload.run_id || null,
        item_count: publicPayload.item_count ?? publicPayload.case_count ?? null,
        status: publicPayload.status || publicPayload.application_status || null,
        message: publicPayload.message || null,
      }),
    }],
    structuredContent: publicPayload,
    isError: false,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    result._meta = {
      ...toolUiMeta(WIDGET_URI, toolName),
      ...(privateReviewPayload ? { private_review_payload: privateReviewPayload } : {}),
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
            ? "Use review_payload_path con validate_journal_bank_review para que el payload privado se cargue dentro del servidor. Renderice con la referencia opaca y use get_journal_bank_case_context solo para los casos seleccionados; solicite identificadores exactos únicamente cuando sean necesarios. El widget recibe el payload completo mediante metadatos privados. Use save_journal_bank_decisions y apply_journal_bank_decisions para las decisiones."
            : "Pass review_payload_path to validate_journal_bank_review so the private payload is loaded inside the server. Render with the opaque reference and use get_journal_bank_case_context only for selected cases; request exact identifiers only when needed. The widget receives the complete payload through component-only metadata. Use save_journal_bank_decisions and apply_journal_bank_decisions for decisions.",
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") return rpcResponse(messageId, { tools: toolDefinitions() });
    if (method === "tools/call") {
      const { name, arguments: args } = params;
      const language = languageFromArgs(isPlainObject(args) ? args : params);
      if (typeof name !== "string") {
        return rpcError(messageId, -32602, isSpanish(language) ? "tools/call requiere el nombre de una herramienta" : "tools/call requires a tool name");
      }
      if (!isPlainObject(args)) {
        return rpcError(messageId, -32602, isSpanish(language) ? "Los argumentos de tools/call deben ser un objeto" : "tools/call arguments must be an object");
      }
      try {
        return rpcResponse(messageId, toolResult(callTool(name, args), name));
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        return rpcResponse(
          messageId,
          toolError(localizeRuntimeError(errorMessage, language)),
        );
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
    if (method === "resources/templates/list") {
      return rpcResponse(messageId, { resourceTemplates: [] });
    }
    if (method === "prompts/list") return rpcResponse(messageId, { prompts: [] });
    return rpcError(messageId, -32601, isSpanish(languageFromArgs(params)) ? `método no encontrado: ${method}` : `method not found: ${method}`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    return rpcError(
      messageId,
      -32000,
      localizeRuntimeError(errorMessage, languageFromArgs(params)),
    );
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

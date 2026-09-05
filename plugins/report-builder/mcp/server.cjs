"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");
const zlib = require("node:zlib");
const { spawnSync } = require("node:child_process");

const SERVER_NAME = "report-builder-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const REPORT_BUILDER_PLUGIN_IMPLEMENTATION_PATHS = [
  ".codex-plugin/plugin.json",
  ".app.json",
  ".mcp.json",
  "assets/icon.svg",
  "assets/report-builder-review-widget.html",
  "assets/review-workbench-adapter.json",
  "mcp/server.cjs",
  "scripts/apply_review_edits.py",
  "scripts/build_report.py",
  "scripts/check_dependencies.py",
  "scripts/expand_model_context.py",
  "scripts/implementation_bootstrap.py",
  "scripts/implementation_contract.py",
  "scripts/inspect_inputs.py",
  "scripts/physical_output_set.py",
  "scripts/prepared_contract.py",
  "scripts/report_builder_core.py",
  "scripts/report_builder_integrity.py",
  "scripts/report_gates.py",
  "scripts/review_successor.py",
  "scripts/review_numeric_measures.py",
  "scripts/review_session.py",
  "scripts/seal_review_integrity.py",
  "scripts/validate_review_integrity.py",
];
const REPORT_BUILDER_SHARED_IMPLEMENTATION_PATHS = [
  "__init__.py",
  "contracts.py",
  "decisions.py",
  "envelope.py",
  "money.py",
  "relationships.py",
  "review_output_transaction.cjs",
  "serialization.py",
];
const REVIEW_TRANSACTION_RUNTIME = (() => {
  const vendored = path.join(
    PLUGIN_ROOT,
    "vendor",
    "modules",
    "vera_assurance",
    "review_output_transaction.cjs",
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
        "review_output_transaction.cjs",
      );
})();
const REPORT_BUILDER_ASSURANCE_IMPLEMENTATION_ROOT = path.dirname(
  REVIEW_TRANSACTION_RUNTIME,
);
validateReportBuilderImplementationTree();
const {
  generatedReviewArgsForWorkingOutput,
  generatedReviewAtomicWriteFileSync,
  generatedReviewCollectApplicationWritePaths,
  generatedReviewPathEntryStat,
  generatedReviewRewriteOutputPaths,
  generatedReviewTransactionEnvelope,
  withGeneratedReviewOutputTransaction,
} = require(REVIEW_TRANSACTION_RUNTIME);
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/report-builder-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 3000;
const MAX_PAYLOAD_BYTES = 3_000_000;
const TOOL_NAMES = {
  validateReview: "validate_report_builder_review",
  renderReview: "render_report_builder_review",
  saveDecisions: "save_report_builder_decisions",
  applyDecisions: "apply_report_builder_decisions",
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
  "report_section",
  "table_evidence",
  "review_issue",
  "report_artifact",
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
    meta["openai/toolInvocation/invoking"] = "Rendering Build Report review";
    meta["openai/toolInvocation/invoked"] = "Rendered Build Report review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Build Report review surface for report sections, table evidence, narrative gaps, and generated Word/Markdown artifacts.",
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
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional ui_decisions.json object." },
      final_artifacts: { type: "object", description: "Optional final_artifacts.json object." },
      expected_predecessor_checkpoint: {
        type: "string",
        pattern: "^[0-9a-f]{64}$",
        description:
          "Externally retained predecessor checkpoint. Required when validating or changing a successor review state.",
      },
    },
    ["review_payload"],
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
      expected_predecessor_checkpoint: {
        type: "string",
        pattern: "^[0-9a-f]{64}$",
        description:
          "Externally retained current integrity checkpoint. Required before applying a later review round.",
      },
    },
    ["client_engagement", "review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate Build Report review payload",
      description:
        "Validate the Build Report review-session payload before rendering. Call this first, then render_report_builder_review.",
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
      title: "Render Build Report review",
      description:
        "Render a Build Report review-session payload as an MCP HTML widget for report sections, table evidence, narrative gaps, and report artifacts.",
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
      name: TOOL_NAMES.saveDecisions,
      title: "Save Build Report review decisions",
      description:
        "Validate Build Report review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
      title: "Apply Build Report review decisions",
      description:
        "Validate Build Report review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
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
      name: "report_builder_review_widget",
      title: "Build Report review widget",
      description:
        "Renders Build Report review-session payloads with searchable sections, table evidence, issues, and generated artifacts.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) {
  throw new Error(`unknown Build Report widget resource: ${uri}`);
  }
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "report-builder-review-widget.html"),
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
  if (item.item_type === "report_artifact" && item.allowed_actions.includes("edit")) {
    throw new Error(
      `review_payload.items[${index}] cannot edit a report artifact without an exact application adapter`,
    );
  }
  if (item.recommended_action != null && !ALLOWED_ACTIONS.has(item.recommended_action)) {
    throw new Error(
      `review_payload.items[${index}].recommended_action is not supported`,
    );
  }
}

function validateReviewPayload(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const reviewPayload = inputArgs.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.plugin !== "report-builder") {
    throw new Error('review_payload.plugin must be "report-builder"');
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
    widget_type: "report_builder_review",
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
    throw new Error(`Build Report widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
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
  const outputDir = resolveRunOutputDir(inputArgs);
  const persist = (
    trustedArgs,
    workingOutputDir,
    reviewPayloadDigest = null,
  ) => {
    const { uiDecisions, decisionOutputPath } =
      buildUiDecisions(trustedArgs);
    const language = languageFromArgs(trustedArgs);
    const persisted = Boolean(workingOutputDir);
    if (workingOutputDir) {
      uiDecisions.review_payload_sha256 = reviewPayloadDigest;
      generatedReviewAtomicWriteFileSync(
        path.join(workingOutputDir, "ui_decisions.json"),
        `${JSON.stringify(uiDecisions, null, 2)}\n`,
        "utf8",
      );
      sealReportBuilderIntegrityParent(
        workingOutputDir,
        trustedArgs.expected_predecessor_checkpoint || null,
      );
    }
    const currentIntegrity = workingOutputDir
      ? readJsonFileIfPresent(
          path.join(workingOutputDir, "review_integrity.json"),
        )
      : null;
    const result = {
      ok: true,
      validation_type: "report_builder_decisions",
      run_id: uiDecisions.run_id,
      decision_count: uiDecisions.decision_count,
      item_count: uiDecisions.item_count,
      status: uiDecisions.status,
      persisted,
      ui_decisions_path: persisted ? decisionOutputPath : null,
      predecessor_checkpoint:
        currentIntegrity?.predecessor_checkpoint || null,
      integrity_checkpoint: currentIntegrity?.content_sha256 || null,
      message: persisted
        ? isSpanish(language)
          ? `Se guardaron ${uiDecisions.decision_count} decisiones del Generador de informes.`
          : `Saved ${uiDecisions.decision_count} Build Report decisions.`
        : isSpanish(language)
          ? "Las decisiones son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
          : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
      ui_decisions: uiDecisions,
    };
    return generatedReviewTransactionEnvelope(
      result,
      persisted
        ? ["ui_decisions.json", "review_integrity.json"]
        : [],
    );
  };
  if (!outputDir) return persist(inputArgs, null).result;
  preflightClientWorkflowRun(outputDir, inputArgs?.review_payload?.run_id);
  validateReportBuilderTransactionInput(outputDir);
  return withGeneratedReviewOutputTransaction(
    outputDir,
    ({ workingOutputDir, trustedImage }) => {
      const authority = parentBoundReportBuilderArgs(inputArgs, {
        outputDir,
        trustedImage,
        trustedImageCaptured: true,
      });
      const integrity = validateReportBuilderIntegrityAuthority(
        workingOutputDir,
        {
          required: authority.assured,
          failureMessage: REPORT_BUILDER_AUTHORIZATION_FAILURE,
          expectedPredecessorCheckpoint:
            authority.args.expected_predecessor_checkpoint || null,
        },
      );
      if (!integrity) {
        throw new Error(REPORT_BUILDER_AUTHORIZATION_FAILURE);
      }
      return persist(
        authority.args,
        workingOutputDir,
        integrity.reviewPayloadDigest,
      );
    },
    reportBuilderTransactionOptions("save"),
  );
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputReference = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputReference) return null;
  const contextValue =
    typeof inputArgs.client_engagement === "string"
      ? inputArgs.client_engagement.trim()
      : "";
  if (!contextValue || !path.isAbsolute(contextValue)) {
    throw new Error("Report Builder persistence requires the current client_engagement context.");
  }
  const contextPath = path.resolve(contextValue);
  if (contextPath !== contextValue || path.basename(contextPath) !== "context.json") {
    throw new Error("Report Builder client_engagement path is invalid.");
  }
  const contextStat = generatedReviewPathEntryStat(contextPath);
  if (
    !contextStat ||
    !contextStat.isFile() ||
    contextStat.isSymbolicLink() ||
    contextStat.nlink !== 1
  ) {
    throw new Error("Report Builder client_engagement context is unavailable.");
  }
  if (!path.isAbsolute(outputReference) && runIntake?.path_reference !== "run_root_relative") {
    throw new Error("Report Builder output reference is not run-root-relative.");
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
    throw new Error("Report Builder output reference leaves the customer run.");
  }
  return resolved;
}

function reportBuilderClientEngagementPath(outputDir) {
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    const contextStat = generatedReviewPathEntryStat(contextPath);
    if (
      contextStat &&
      contextStat.isFile() &&
      !contextStat.isSymbolicLink() &&
      contextStat.nlink === 1
    ) {
      return contextPath;
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) return null;
    candidate = parent;
  }
}

function reportBuilderPersistentOutputDir(clientEngagement) {
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
  ["codex_run_review.md", ["concordato_review_summary.docx"]],
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

function fileSha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function persistedReviewPayloadDigest(outputDir) {
  if (!outputDir) return null;
  const integrity = readJsonFileIfPresent(path.join(outputDir, "review_integrity.json"));
  const digest = shortString(integrity?.payload_digests?.review_payload);
  if (!digest) {
    throw new Error("Report Builder review payload digest is missing");
  }
  return digest;
}

function preflightReportBuilderEffects(effects, itemById, outputDir) {
  // Exact adapter/ID validation is mechanically verifiable and must precede every write.
  const recipe = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "used_recipe.json"))
    : null;
  const editedTargets = new Set();
  for (const effect of effects) {
    if (effect.action !== "edit") continue;
    const item = itemById.get(effect.item_id);
    const data = isPlainObject(item?.data) ? item.data : {};
    const targetPath = shortString(data.target_path);
    const targetArtifact = artifactPathKey(data.target_artifact);
    const commentMatch = /^sections\.([^.]+)\.codex_comment$/.exec(targetPath);
    const mappingMatch = /^sections\.([^.]+)\.assigned_table$/.exec(targetPath);
    if (
      targetArtifact !== "report.docx" ||
      (!commentMatch && !mappingMatch) ||
      !["report_section", "table_evidence", "review_issue"].includes(item?.item_type)
    ) {
      throw new Error(
        `Edit item ${effect.item_id} has no exact Report Builder application adapter`,
      );
    }
    const sectionKey = (commentMatch || mappingMatch)[1];
    if (editedTargets.has(targetPath)) {
      throw new Error(`Multiple edits target the same Report Builder field: ${targetPath}`);
    }
    editedTargets.add(targetPath);
    if (
      recipe &&
      (!isPlainObject(recipe.sections) || !isPlainObject(recipe.sections[sectionKey]))
    ) {
      throw new Error(`Edit item ${effect.item_id} targets an unknown report section`);
    }
    if (mappingMatch) {
      const available = Array.isArray(data.available_table_ids)
        ? data.available_table_ids.map(shortString).filter(Boolean)
        : [];
      if (!available.includes(shortString(effect.edit_value))) {
        throw new Error(
          `Report Builder source mapping edit must use an exact local table_id: ${shortString(effect.edit_value)}`,
        );
      }
    }
  }
}

const REPORT_BUILDER_TRANSACTION_FAILURE =
  "Report Builder review transaction failed safely.";
const REPORT_BUILDER_ROLLBACK_FAILURE =
  "Report Builder review transaction could not be restored safely.";
const REPORT_BUILDER_AUTHORIZATION_FAILURE =
  "Report Builder persisted review authorization failed.";

function reportBuilderMappedTransactionError(error) {
  const message = error instanceof Error ? error.message : "";
  if (
    message.length > 512 ||
    /[\\/\u0000-\u001f\u007f]/.test(message) ||
    /Traceback|\bFile\s+["']|file:|~[\\/]/i.test(message)
  ) {
    return null;
  }
  if (message === REPORT_BUILDER_AUTHORIZATION_FAILURE) return message;
  return (
    [
      "Report Builder integrity step ",
      "Report Builder native regeneration ",
    ].some((prefix) => message.startsWith(prefix))
      ? message
      : null
  );
}

function reportBuilderCanonicalJson(value) {
  if (Array.isArray(value)) {
    return value.map((entry) => reportBuilderCanonicalJson(entry));
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, reportBuilderCanonicalJson(value[key])]),
    );
  }
  return value;
}

function reportBuilderJsonValuesEqual(left, right) {
  return (
    JSON.stringify(reportBuilderCanonicalJson(left)) ===
    JSON.stringify(reportBuilderCanonicalJson(right))
  );
}

function cloneReportBuilderJson(value) {
  return JSON.parse(JSON.stringify(reportBuilderCanonicalJson(value)));
}

const REPORT_BUILDER_ASSURED_MARKERS = [
  "review_integrity.json",
  "source_index.json",
  "report_audit.json",
  "used_recipe.json",
  "report_analysis.json",
];

function reportBuilderTrustedImageJson(trustedImage, relativePath) {
  const entry = (trustedImage?.files || []).find(
    (file) => file.path === relativePath,
  );
  if (!entry) return null;
  try {
    const parsed = JSON.parse(entry.payload.toString("utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function assertReportBuilderCallerMatch(caller, persisted) {
  if (caller == null) return;
  if (!isPlainObject(caller) || !reportBuilderJsonValuesEqual(caller, persisted)) {
    throw new Error(REPORT_BUILDER_AUTHORIZATION_FAILURE);
  }
}

function parentBoundReportBuilderArgs(
  inputArgs,
  {
    outputDir = resolveRunOutputDir(inputArgs),
    trustedImage = null,
    trustedImageCaptured = false,
  } = {},
) {
  if (!outputDir) return { args: inputArgs, outputDir: null, assured: false };
  const imageJson = (name) =>
    trustedImageCaptured
      ? reportBuilderTrustedImageJson(trustedImage, name)
      : readJsonFileIfPresent(path.join(outputDir, name));
  const persistedRunIntake = imageJson("run_intake.json");
  const persistedReviewPayload = imageJson("review_payload.json");
  const persistedUiDecisions = imageJson("ui_decisions.json");
  const persistedFinalArtifacts = imageJson("final_artifacts.json");
  const assured = trustedImageCaptured
    ? REPORT_BUILDER_ASSURED_MARKERS.some((name) =>
        (trustedImage?.files || []).some((file) => file.path === name),
      )
    : REPORT_BUILDER_ASSURED_MARKERS.some((name) =>
        fs.existsSync(path.join(outputDir, name)),
      );
  if (
    assured &&
    [
      persistedRunIntake,
      persistedReviewPayload,
      persistedUiDecisions,
      persistedFinalArtifacts,
      imageJson("source_index.json"),
      imageJson("review_integrity.json"),
    ].some((value) => !isPlainObject(value))
  ) {
    throw new Error(REPORT_BUILDER_AUTHORIZATION_FAILURE);
  }
  if (persistedRunIntake) {
    assertReportBuilderCallerMatch(inputArgs.run_intake, persistedRunIntake);
  }
  if (persistedReviewPayload) {
    assertReportBuilderCallerMatch(
      inputArgs.review_payload,
      persistedReviewPayload,
    );
  }
  if (persistedUiDecisions) {
    assertReportBuilderCallerMatch(
      inputArgs.ui_decisions,
      persistedUiDecisions,
    );
  }
  if (persistedFinalArtifacts) {
    assertReportBuilderCallerMatch(
      inputArgs.final_artifacts,
      persistedFinalArtifacts,
    );
  }
  if (
    persistedRunIntake &&
    (typeof persistedRunIntake.output_dir !== "string" ||
      resolveRunOutputDir({
        ...inputArgs,
        run_intake: persistedRunIntake,
      }) !== path.resolve(outputDir))
  ) {
    throw new Error(REPORT_BUILDER_AUTHORIZATION_FAILURE);
  }
  return {
    args: {
      ...inputArgs,
      ...(persistedRunIntake
        ? { run_intake: cloneReportBuilderJson(persistedRunIntake) }
        : {}),
      ...(persistedReviewPayload
        ? { review_payload: cloneReportBuilderJson(persistedReviewPayload) }
        : {}),
      ...(persistedUiDecisions
        ? { ui_decisions: cloneReportBuilderJson(persistedUiDecisions) }
        : {}),
      ...(persistedFinalArtifacts
        ? { final_artifacts: cloneReportBuilderJson(persistedFinalArtifacts) }
        : {}),
    },
    outputDir,
    assured,
  };
}

function reportBuilderCanonicalSha256(value) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(reportBuilderCanonicalJson(value)), "utf8")
    .digest("hex");
}

function reportBuilderCheckpoint(value, { required = false } = {}) {
  const checkpoint = typeof value === "string" ? value.trim() : "";
  if (!checkpoint) {
    if (required) {
      throw new Error("Report Builder predecessor checkpoint is required");
    }
    return null;
  }
  if (!/^[0-9a-f]{64}$/.test(checkpoint)) {
    throw new Error("Report Builder predecessor checkpoint is malformed");
  }
  return checkpoint;
}

function reportBuilderExactFields(value, required, optional = []) {
  if (!isPlainObject(value)) return false;
  const allowed = new Set([...required, ...optional]);
  return (
    required.every((field) => Object.hasOwn(value, field)) &&
    Object.keys(value).every((field) => allowed.has(field))
  );
}

function reportBuilderIdentifier(value) {
  return (
    typeof value === "string" &&
    value === value.trim() &&
    /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value)
  );
}

function reportBuilderCanonicalRelativePath(value) {
  if (
    typeof value !== "string" ||
    !value ||
    value !== value.trim() ||
    value.includes("\\") ||
    path.posix.isAbsolute(value) ||
    path.posix.normalize(value) !== value ||
    value === "." ||
    value === ".." ||
    value.startsWith("../") ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    throw new Error("invalid Report Builder integrity path");
  }
  return value;
}

function reportBuilderStableFileSnapshot(filePath) {
  const unresolved = path.resolve(filePath);
  const entry = fs.lstatSync(unresolved);
  if (!entry.isFile() || entry.isSymbolicLink() || entry.nlink !== 1) {
    throw new Error("invalid Report Builder integrity artifact");
  }
  const descriptor = fs.openSync(
    unresolved,
    fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0),
  );
  try {
    const before = fs.fstatSync(descriptor);
    if (!before.isFile() || before.nlink !== 1) {
      throw new Error("invalid Report Builder integrity artifact");
    }
    const payload = fs.readFileSync(descriptor);
    const after = fs.fstatSync(descriptor);
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      payload.length !== after.size
    ) {
      throw new Error("Report Builder integrity artifact changed while read");
    }
    return {
      payload,
      byte_count: payload.length,
      sha256: crypto.createHash("sha256").update(payload).digest("hex"),
    };
  } finally {
    fs.closeSync(descriptor);
  }
}

function reportBuilderContainedFile(rootPath, relativePath) {
  const canonical = reportBuilderCanonicalRelativePath(relativePath);
  const root = path.resolve(rootPath);
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("invalid Report Builder source root");
  }
  const resolvedRoot = fs.realpathSync.native(root);
  const unresolved = path.join(resolvedRoot, canonical);
  const unresolvedEntry = fs.lstatSync(unresolved);
  if (unresolvedEntry.isSymbolicLink()) {
    throw new Error("invalid Report Builder integrity artifact");
  }
  const resolved = fs.realpathSync.native(unresolved);
  const relative = path.relative(resolvedRoot, resolved);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Report Builder integrity path escapes its root");
  }
  return resolved;
}

function validateReportBuilderRelativeReceipt(outputDir, receipt) {
  if (
    !reportBuilderExactFields(
      receipt,
      ["path", "role", "byte_count", "sha256"],
    ) ||
    receipt.role !== "review_handoff" ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0 ||
    !/^[0-9a-f]{64}$/.test(receipt.sha256)
  ) {
    throw new Error("invalid Report Builder protected receipt");
  }
  const artifactPath = reportBuilderContainedFile(outputDir, receipt.path);
  const snapshot = reportBuilderStableFileSnapshot(artifactPath);
  if (
    receipt.byte_count !== snapshot.byte_count ||
    receipt.sha256 !== snapshot.sha256
  ) {
    throw new Error("stale Report Builder protected receipt");
  }
}

function reportBuilderSourceRoot(outputDir, rootPath) {
  if (path.isAbsolute(rootPath)) return path.resolve(rootPath);
  const relative = reportBuilderCanonicalRelativePath(rootPath);
  const clientEngagement = reportBuilderClientEngagementPath(outputDir);
  if (!clientEngagement) {
    throw new Error("Report Builder portable source root has no customer run");
  }
  const runRoot = path.dirname(clientEngagement);
  const resolved = path.resolve(runRoot, relative);
  const containment = path.relative(runRoot, resolved);
  if (
    !containment ||
    containment === ".." ||
    containment.startsWith(`..${path.sep}`) ||
    path.isAbsolute(containment)
  ) {
    throw new Error("Report Builder source root leaves the customer run");
  }
  return resolved;
}

function validateReportBuilderSourceRecord(record, outputDir) {
  if (
    !reportBuilderExactFields(record, [
      "artifact_id",
      "identity_key",
      "root_path",
      "receipt",
    ]) ||
    typeof record.artifact_id !== "string" ||
    !record.artifact_id ||
    typeof record.identity_key !== "string" ||
    !record.identity_key ||
    typeof record.root_path !== "string" ||
    !record.root_path
  ) {
    throw new Error("invalid Report Builder source record");
  }
  const receipt = record.receipt;
  if (
    !reportBuilderExactFields(
      receipt,
      [
        "schema_version",
        "artifact_id",
        "root_id",
        "role",
        "path",
        "byte_count",
        "sha256",
      ],
      ["media_type"],
    ) ||
    receipt.schema_version !== "vera.artifact_receipt.v1" ||
    receipt.artifact_id !== record.artifact_id ||
    !reportBuilderIdentifier(receipt.root_id) ||
    receipt.role !== "source" ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0 ||
    !/^[0-9a-f]{64}$/.test(receipt.sha256)
  ) {
    throw new Error("invalid Report Builder source receipt");
  }
  const sourcePath = reportBuilderContainedFile(
    reportBuilderSourceRoot(outputDir, record.root_path),
    receipt.path,
  );
  const snapshot = reportBuilderStableFileSnapshot(sourcePath);
  if (
    receipt.byte_count !== snapshot.byte_count ||
    receipt.sha256 !== snapshot.sha256
  ) {
    throw new Error("stale Report Builder source receipt");
  }
  return { record, sourcePath, snapshot };
}

function reportBuilderZipMemberPath(value) {
  if (typeof value !== "string") {
    throw new Error("invalid ZIP member path");
  }
  const normalized = value.replaceAll("\\", "/").normalize("NFC");
  return reportBuilderCanonicalRelativePath(normalized);
}

function reportBuilderZipName(nameBytes, utf8) {
  if (!utf8 && nameBytes.some((value) => value > 0x7f)) {
    throw new Error("legacy non-ASCII ZIP member names are unsupported");
  }
  const decoded = nameBytes.toString(utf8 ? "utf8" : "ascii");
  if (decoded.includes("\ufffd")) {
    throw new Error("invalid ZIP member name");
  }
  return decoded;
}

function reportBuilderZipManifest(sourceBytes) {
  const minimumEocdOffset = Math.max(0, sourceBytes.length - 65_557);
  let eocdOffset = -1;
  for (let offset = sourceBytes.length - 22; offset >= minimumEocdOffset; offset -= 1) {
    if (sourceBytes.readUInt32LE(offset) === 0x06054b50) {
      const commentLength = sourceBytes.readUInt16LE(offset + 20);
      if (offset + 22 + commentLength === sourceBytes.length) {
        eocdOffset = offset;
        break;
      }
    }
  }
  if (eocdOffset < 0) throw new Error("invalid ZIP end record");
  const diskNumber = sourceBytes.readUInt16LE(eocdOffset + 4);
  const centralDisk = sourceBytes.readUInt16LE(eocdOffset + 6);
  const diskEntryCount = sourceBytes.readUInt16LE(eocdOffset + 8);
  const entryCount = sourceBytes.readUInt16LE(eocdOffset + 10);
  const centralSize = sourceBytes.readUInt32LE(eocdOffset + 12);
  const centralOffset = sourceBytes.readUInt32LE(eocdOffset + 16);
  if (
    diskNumber !== 0 ||
    centralDisk !== 0 ||
    diskEntryCount !== entryCount ||
    entryCount === 0xffff ||
    centralSize === 0xffffffff ||
    centralOffset === 0xffffffff ||
    centralOffset + centralSize > eocdOffset
  ) {
    throw new Error("unsupported ZIP structure");
  }
  const manifest = [];
  const portableNames = new Set();
  let cursor = centralOffset;
  let totalUncompressed = 0;
  for (let index = 0; index < entryCount; index += 1) {
    if (
      cursor + 46 > sourceBytes.length ||
      sourceBytes.readUInt32LE(cursor) !== 0x02014b50
    ) {
      throw new Error("invalid ZIP central directory");
    }
    const flags = sourceBytes.readUInt16LE(cursor + 8);
    const method = sourceBytes.readUInt16LE(cursor + 10);
    const compressedSize = sourceBytes.readUInt32LE(cursor + 20);
    const uncompressedSize = sourceBytes.readUInt32LE(cursor + 24);
    const nameLength = sourceBytes.readUInt16LE(cursor + 28);
    const extraLength = sourceBytes.readUInt16LE(cursor + 30);
    const commentLength = sourceBytes.readUInt16LE(cursor + 32);
    const externalAttributes = sourceBytes.readUInt32LE(cursor + 38);
    const localOffset = sourceBytes.readUInt32LE(cursor + 42);
    const nextCursor =
      cursor + 46 + nameLength + extraLength + commentLength;
    if (
      nextCursor > sourceBytes.length ||
      compressedSize === 0xffffffff ||
      uncompressedSize === 0xffffffff ||
      localOffset === 0xffffffff ||
      (flags & 0x1) !== 0 ||
      ![0, 8].includes(method)
    ) {
      throw new Error("unsupported ZIP member");
    }
    const rawName = reportBuilderZipName(
      sourceBytes.subarray(cursor + 46, cursor + 46 + nameLength),
      (flags & 0x800) !== 0,
    );
    cursor = nextCursor;
    if (rawName.endsWith("/")) continue;
    const memberPath = reportBuilderZipMemberPath(rawName);
    const portableIdentity = memberPath.toLocaleLowerCase("und");
    if (portableNames.has(portableIdentity)) {
      throw new Error("duplicate canonical ZIP member path");
    }
    portableNames.add(portableIdentity);
    const unixMode = externalAttributes >>> 16;
    if ((unixMode & 0o170000) === 0o120000) {
      throw new Error("ZIP symbolic links are unsupported");
    }
    if (
      localOffset + 30 > sourceBytes.length ||
      sourceBytes.readUInt32LE(localOffset) !== 0x04034b50
    ) {
      throw new Error("invalid ZIP local header");
    }
    const localNameLength = sourceBytes.readUInt16LE(localOffset + 26);
    const localExtraLength = sourceBytes.readUInt16LE(localOffset + 28);
    const localName = reportBuilderZipName(
      sourceBytes.subarray(
        localOffset + 30,
        localOffset + 30 + localNameLength,
      ),
      (flags & 0x800) !== 0,
    );
    if (reportBuilderZipMemberPath(localName) !== memberPath) {
      throw new Error("ZIP central/local member identity mismatch");
    }
    const dataOffset =
      localOffset + 30 + localNameLength + localExtraLength;
    if (dataOffset + compressedSize > sourceBytes.length) {
      throw new Error("truncated ZIP member");
    }
    totalUncompressed += uncompressedSize;
    if (
      uncompressedSize > 512 * 1024 * 1024 ||
      totalUncompressed > 1024 * 1024 * 1024
    ) {
      throw new Error("ZIP member expansion exceeds the integrity limit");
    }
    const compressed = sourceBytes.subarray(
      dataOffset,
      dataOffset + compressedSize,
    );
    const payload =
      method === 0 ? Buffer.from(compressed) : zlib.inflateRawSync(compressed);
    if (payload.length !== uncompressedSize) {
      throw new Error("ZIP member size mismatch");
    }
    manifest.push({
      path: memberPath,
      byte_count: payload.length,
      sha256: crypto.createHash("sha256").update(payload).digest("hex"),
    });
  }
  if (cursor !== centralOffset + centralSize) {
    throw new Error("ZIP central directory size mismatch");
  }
  return manifest.sort((left, right) =>
    left.path
      .toLocaleLowerCase("und")
      .localeCompare(right.path.toLocaleLowerCase("und")),
  );
}

function validateReportBuilderSourceIndex(outputDir) {
  const sourceIndex = readJsonFileIfPresent(
    path.join(outputDir, "source_index.json"),
  );
  if (
    !reportBuilderExactFields(sourceIndex, [
      "schema_version",
      "sources",
      "archive_manifests",
      "archive_member_bindings",
      "content_sha256",
    ]) ||
    sourceIndex.schema_version !== "report_builder.source_index.v2" ||
    !Array.isArray(sourceIndex.sources) ||
    sourceIndex.sources.length === 0 ||
    !Array.isArray(sourceIndex.archive_manifests) ||
    !Array.isArray(sourceIndex.archive_member_bindings)
  ) {
    throw new Error("invalid Report Builder source index");
  }
  const content = { ...sourceIndex };
  delete content.content_sha256;
  if (reportBuilderCanonicalSha256(content) !== sourceIndex.content_sha256) {
    throw new Error("stale Report Builder source-index digest");
  }
  const sourcesById = new Map();
  for (const source of sourceIndex.sources) {
    const validated = validateReportBuilderSourceRecord(source, outputDir);
    if (sourcesById.has(source.artifact_id)) {
      throw new Error("duplicate Report Builder source identity");
    }
    sourcesById.set(source.artifact_id, validated);
  }
  const manifestsByContainer = new Map();
  for (const rawManifest of sourceIndex.archive_manifests) {
    if (
      !reportBuilderExactFields(rawManifest, [
        "container_artifact_id",
        "members",
      ]) ||
      typeof rawManifest.container_artifact_id !== "string" ||
      !Array.isArray(rawManifest.members) ||
      manifestsByContainer.has(rawManifest.container_artifact_id)
    ) {
      throw new Error("invalid Report Builder archive manifest");
    }
    const container = sourcesById.get(rawManifest.container_artifact_id);
    if (!container) {
      throw new Error("missing Report Builder archive container");
    }
    const currentManifest = reportBuilderZipManifest(
      container.snapshot.payload,
    );
    if (!reportBuilderJsonValuesEqual(rawManifest.members, currentManifest)) {
      throw new Error("stale Report Builder archive member manifest");
    }
    manifestsByContainer.set(
      rawManifest.container_artifact_id,
      currentManifest,
    );
  }
  const seenBindings = new Set();
  const boundMemberIds = new Set();
  for (const binding of sourceIndex.archive_member_bindings) {
    if (
      !reportBuilderExactFields(binding, [
        "container_artifact_id",
        "member_path",
        "member_artifact_id",
        "byte_count",
        "sha256",
      ]) ||
      typeof binding.container_artifact_id !== "string" ||
      typeof binding.member_artifact_id !== "string" ||
      !Number.isInteger(binding.byte_count) ||
      binding.byte_count < 0 ||
      !/^[0-9a-f]{64}$/.test(binding.sha256)
    ) {
      throw new Error("invalid Report Builder archive-member binding");
    }
    const memberPath = reportBuilderZipMemberPath(binding.member_path);
    const bindingKey = `${binding.container_artifact_id}\u0000${memberPath}`;
    if (
      seenBindings.has(bindingKey) ||
      boundMemberIds.has(binding.member_artifact_id)
    ) {
      throw new Error("duplicate Report Builder archive-member binding");
    }
    seenBindings.add(bindingKey);
    boundMemberIds.add(binding.member_artifact_id);
    const manifest = manifestsByContainer.get(binding.container_artifact_id);
    const member = manifest?.find((entry) => entry.path === memberPath);
    const source = sourcesById.get(binding.member_artifact_id);
    if (
      !member ||
      !source ||
      binding.byte_count !== member.byte_count ||
      binding.sha256 !== member.sha256 ||
      source.record.receipt.byte_count !== member.byte_count ||
      source.record.receipt.sha256 !== member.sha256 ||
      !source.record.identity_key.endsWith(`::${memberPath}`)
    ) {
      throw new Error("stale Report Builder archive-member binding");
    }
  }
  const extractedMemberIds = new Set(
    [...sourcesById.entries()]
      .filter(([, source]) => source.record.identity_key.includes("::"))
      .map(([artifactId]) => artifactId),
  );
  if (!reportBuilderJsonValuesEqual(
    [...extractedMemberIds].sort(),
    [...boundMemberIds].sort(),
  )) {
    throw new Error("incomplete Report Builder archive-member bindings");
  }
  return sourceIndex;
}

const REPORT_BUILDER_PUBLIC_OUTPUT_ALLOWLIST = new Set([
  "report_tables.json",
  "report_tables.xlsx",
  "report_analysis.json",
  "report_draft.md",
  "report.docx",
  "report_audit.json",
  "used_recipe.json",
  "numeric_evidence_ledger.json",
  "source_receipts.json",
  "review_handoff.md",
]);

const REPORT_BUILDER_BASE_OUTPUT_PATHS = new Set([
  "final_artifacts.json",
  "report.docx",
  "report_analysis.json",
  "report_audit.json",
  "report_draft.md",
  "report_tables.json",
  "report_tables.xlsx",
  "review_handoff.md",
  "review_integrity.json",
  "review_payload.json",
  "run_intake.json",
  "source_index.json",
  "ui_decisions.json",
  "used_recipe.json",
]);
const REPORT_BUILDER_INSPECTION_OUTPUT_PATHS = new Set([
  "inspection.json",
  "inspection_control.json",
  "model_context_receipt.json",
  "suggested_recipe.json",
]);
const REPORT_BUILDER_NUMERIC_OUTPUT_PATHS = new Set([
  "numeric_evidence_ledger.json",
  "source_receipts.json",
]);

function reportBuilderImplementationMediaType(relativePath) {
  return {
    ".cjs": "text/javascript",
    ".html": "text/html",
    ".json": "application/json",
    ".py": "text/x-python",
    ".svg": "image/svg+xml",
  }[path.extname(relativePath).toLowerCase()];
}

function reportBuilderImplementationArtifactId(namespace, relativePath) {
  return `implementation.${namespace}.${relativePath.replaceAll("/", ".")}`;
}

function reportBuilderImplementationSpecifications() {
  return [
    ...REPORT_BUILDER_PLUGIN_IMPLEMENTATION_PATHS.map((relativePath) => ({
      artifact_id: reportBuilderImplementationArtifactId(
        "report_builder",
        relativePath,
      ),
      root_id: "implementation",
      path: relativePath,
      media_type: reportBuilderImplementationMediaType(relativePath),
    })),
    ...REPORT_BUILDER_SHARED_IMPLEMENTATION_PATHS.map((relativePath) => ({
      artifact_id: reportBuilderImplementationArtifactId(
        "vera_assurance",
        relativePath,
      ),
      root_id: "assurance_implementation",
      path: relativePath,
      media_type: reportBuilderImplementationMediaType(relativePath),
    })),
  ];
}

function reportBuilderImplementationRoot(rootId) {
  if (rootId === "implementation") return PLUGIN_ROOT;
  if (rootId === "assurance_implementation") {
    return REPORT_BUILDER_ASSURANCE_IMPLEMENTATION_ROOT;
  }
  throw new Error("invalid Report Builder implementation root");
}

function reportBuilderImplementationSnapshot(specification) {
  const root = reportBuilderImplementationRoot(specification.root_id);
  let current = root;
  const parts = specification.path.split("/");
  for (let index = 0; index < parts.length; index += 1) {
    current = path.join(current, parts[index]);
    const entry = fs.lstatSync(current);
    if (entry.isSymbolicLink()) {
      throw new Error("invalid Report Builder implementation symlink");
    }
    if (index < parts.length - 1 && !entry.isDirectory()) {
      throw new Error("invalid Report Builder implementation parent");
    }
    if (
      index === parts.length - 1 &&
      (!entry.isFile() || entry.nlink !== 1)
    ) {
      throw new Error("invalid Report Builder implementation artifact");
    }
  }
  const artifactPath = reportBuilderContainedFile(root, specification.path);
  return reportBuilderStableFileSnapshot(artifactPath);
}

function buildReportBuilderImplementationReceipts() {
  validateReportBuilderImplementationTree();
  return reportBuilderImplementationSpecifications().map((specification) => {
    const snapshot = reportBuilderImplementationSnapshot(specification);
    return {
      ...specification,
      role: "implementation",
      byte_count: snapshot.byte_count,
      sha256: snapshot.sha256,
    };
  });
}

function reportBuilderScanImplementationRoot(root, scanRoots, rootFiles) {
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("invalid Report Builder implementation root");
  }
  const files = new Set();
  const directories = new Set();
  for (const relativePath of rootFiles) {
    const entryPath = path.join(root, relativePath);
    const entry = fs.lstatSync(entryPath);
    if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
      throw new Error("invalid Report Builder implementation artifact");
    }
    files.add(relativePath);
  }
  const pending = scanRoots.map((relativePath) => {
    const scanPath = path.join(root, relativePath);
    const entry = fs.lstatSync(scanPath);
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      throw new Error("invalid Report Builder implementation directory");
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
        throw new Error("invalid Report Builder implementation symlink");
      }
      if (entry.isDirectory()) {
        // Generated caches are inert; the executable source contract stays exact.
        if (name === "__pycache__") continue;
        directories.add(relative);
        pending.push(entryPath);
        continue;
      }
      if (!entry.isFile() || entry.nlink !== 1) {
        throw new Error("invalid Report Builder implementation artifact");
      }
      if (name.endsWith(".pyc") || name.endsWith(".pyo")) continue;
      files.add(relative);
    }
  }
  return { files, directories };
}

function validateReportBuilderImplementationTree() {
  const pluginTree = reportBuilderScanImplementationRoot(
    PLUGIN_ROOT,
    [".codex-plugin", "assets", "mcp", "scripts"],
    [".app.json", ".mcp.json"],
  );
  const sharedTree = reportBuilderScanImplementationRoot(
    REPORT_BUILDER_ASSURANCE_IMPLEMENTATION_ROOT,
    ["."],
    [],
  );
  const expectedPluginFiles = new Set(
    REPORT_BUILDER_PLUGIN_IMPLEMENTATION_PATHS,
  );
  const expectedPluginDirectories = reportBuilderExpectedDirectories(
    REPORT_BUILDER_PLUGIN_IMPLEMENTATION_PATHS,
  );
  const expectedSharedFiles = new Set(
    REPORT_BUILDER_SHARED_IMPLEMENTATION_PATHS,
  );
  if (
    !reportBuilderJsonValuesEqual(
      [...pluginTree.files].sort(),
      [...expectedPluginFiles].sort(),
    ) ||
    !reportBuilderJsonValuesEqual(
      [...pluginTree.directories].sort(),
      [...expectedPluginDirectories].sort(),
    ) ||
    !reportBuilderJsonValuesEqual(
      [...sharedTree.files].sort(),
      [...expectedSharedFiles].sort(),
    ) ||
    sharedTree.directories.size !== 0
  ) {
    throw new Error("Report Builder implementation tree is not exact");
  }
}

function validateReportBuilderImplementationContract(integrity) {
  validateReportBuilderImplementationTree();
  const specifications = reportBuilderImplementationSpecifications();
  const expectedIds = specifications.map(
    (specification) => specification.artifact_id,
  );
  if (
    !Array.isArray(integrity.implementation_artifact_refs) ||
    !Array.isArray(integrity.implementation_receipts) ||
    !reportBuilderJsonValuesEqual(
      integrity.implementation_artifact_refs,
      expectedIds,
    ) ||
    integrity.implementation_receipts.length !== specifications.length
  ) {
    throw new Error("invalid Report Builder implementation receipt set");
  }
  for (let index = 0; index < specifications.length; index += 1) {
    const specification = specifications[index];
    const receipt = integrity.implementation_receipts[index];
    if (
      !reportBuilderExactFields(receipt, [
        "artifact_id",
        "root_id",
        "path",
        "media_type",
        "role",
        "byte_count",
        "sha256",
      ]) ||
      receipt.artifact_id !== specification.artifact_id ||
      receipt.root_id !== specification.root_id ||
      receipt.path !== specification.path ||
      receipt.media_type !== specification.media_type ||
      receipt.role !== "implementation" ||
      !Number.isInteger(receipt.byte_count) ||
      receipt.byte_count < 0 ||
      !/^[0-9a-f]{64}$/.test(receipt.sha256 || "")
    ) {
      throw new Error("invalid Report Builder implementation receipt");
    }
    const snapshot = reportBuilderImplementationSnapshot(specification);
    if (
      receipt.byte_count !== snapshot.byte_count ||
      receipt.sha256 !== snapshot.sha256
    ) {
      throw new Error("stale Report Builder implementation receipt");
    }
  }
}

function reportBuilderExpectedDirectories(relativePaths) {
  const directories = new Set();
  for (const relativePath of relativePaths) {
    let parent = path.posix.dirname(relativePath);
    while (parent !== ".") {
      directories.add(parent);
      parent = path.posix.dirname(parent);
    }
  }
  return directories;
}

function reportBuilderPhysicalTree(outputDir) {
  const root = path.resolve(outputDir);
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("invalid Report Builder physical output root");
  }
  const files = new Set();
  const directories = new Set();
  const pending = [root];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current)) {
      const entryPath = path.join(current, name);
      const entry = fs.lstatSync(entryPath);
      const relative = path
        .relative(root, entryPath)
        .split(path.sep)
        .join("/");
      if (entry.isSymbolicLink()) {
        throw new Error("invalid Report Builder physical output symlink");
      }
      if (entry.isDirectory()) {
        directories.add(relative);
        pending.push(entryPath);
        continue;
      }
      if (!entry.isFile() || entry.nlink !== 1) {
        throw new Error("invalid Report Builder physical output artifact");
      }
      files.add(relative);
    }
  }
  return { files, directories };
}

function reportBuilderHistoryPaths(applied, outputDir) {
  const rawPaths = Array.isArray(applied.review_history_paths)
    ? applied.review_history_paths
    : [];
  if (
    rawPaths.length !== new Set(rawPaths).size ||
    !rawPaths.every(
      (relativePath) =>
        typeof relativePath === "string" &&
        /^revisions\/history\/application__[0-9a-f]{64}\.json$/.test(
          relativePath,
        ),
    )
  ) {
    throw new Error("invalid Report Builder review history perimeter");
  }
  for (const relativePath of rawPaths) {
    const historyPath = path.join(outputDir, relativePath);
    const history = readJsonFileIfPresent(historyPath);
    if (
      !isPlainObject(history) ||
      !reportBuilderExactFields(history, [
        "schema_version",
        "archived_at",
        "predecessor_checkpoint",
        "predecessor_integrity",
        "run_intake",
        "review_payload",
        "ui_decisions",
        "applied_decisions",
        "final_artifacts",
        "content_sha256",
      ]) ||
      history.schema_version !== "report_builder.review_history_entry.v2"
    ) {
      throw new Error("invalid Report Builder review history entry");
    }
    const content = { ...history };
    delete content.content_sha256;
    const digest = reportBuilderCanonicalSha256(content);
    if (
      history.content_sha256 !== digest ||
      relativePath !==
        `revisions/history/application__${digest}.json`
    ) {
      throw new Error("stale Report Builder review history entry");
    }
    const predecessorCheckpoint = reportBuilderCheckpoint(
      history.predecessor_checkpoint,
      { required: true },
    );
    const predecessorIntegrity = history.predecessor_integrity;
    if (
      !reportBuilderExactFields(predecessorIntegrity, [
        "schema_version",
        "run_id",
        "source_index",
        "predecessor_checkpoint",
        "protected_files",
        "payload_digests",
        "implementation_artifact_refs",
        "implementation_receipts",
        "prepared_validation",
        "physical_paths",
        "physical_directories",
        "content_sha256",
      ]) ||
      predecessorIntegrity.schema_version !==
        "report_builder.review_integrity.v4" ||
      predecessorIntegrity.content_sha256 !== predecessorCheckpoint
    ) {
      throw new Error("stale Report Builder predecessor checkpoint");
    }
    const predecessorContent = { ...predecessorIntegrity };
    delete predecessorContent.content_sha256;
    if (
      reportBuilderCanonicalSha256(predecessorContent) !==
      predecessorCheckpoint
    ) {
      throw new Error("stale Report Builder predecessor checkpoint");
    }
    const archivedPayloads = {
      run_intake: history.run_intake,
      review_payload: history.review_payload,
      ui_decisions: history.ui_decisions,
      applied_decisions: history.applied_decisions,
      final_artifacts: history.final_artifacts,
    };
    const expectedPayloadDigests = Object.fromEntries(
      Object.entries(archivedPayloads).map(([name, value]) => [
        name,
        reportBuilderCanonicalSha256(value),
      ]),
    );
    if (
      !Object.values(archivedPayloads).every(isPlainObject) ||
      !reportBuilderJsonValuesEqual(
        predecessorIntegrity.payload_digests,
        expectedPayloadDigests,
      )
    ) {
      throw new Error("stale Report Builder predecessor payload receipts");
    }
    const priorReviewDigest = expectedPayloadDigests.review_payload;
    const priorReview = history.review_payload;
    const priorUi = history.ui_decisions;
    const priorApplied = history.applied_decisions;
    const priorFinal = history.final_artifacts;
    const sourceMappingReviewRequired =
      priorApplied.source_mapping_review_required === true;
    if (
      priorUi.run_id !== priorReview.run_id ||
      priorUi.review_payload_sha256 !== priorReviewDigest ||
      priorApplied.run_id !== priorReview.run_id ||
      priorApplied.review_payload_sha256 !== priorReviewDigest ||
      (!sourceMappingReviewRequired &&
        (!reportBuilderJsonValuesEqual(
          priorApplied.decisions,
          priorUi.decisions,
        ) ||
          priorApplied.decision_count !== priorUi.decision_count)) ||
      (sourceMappingReviewRequired &&
        (!Array.isArray(priorUi.decisions) ||
          priorUi.decisions.length !== 0 ||
          priorUi.decision_count !== 0 ||
          !/^[0-9a-f]{64}$/.test(
            priorApplied.decision_review_payload_sha256 || "",
          ))) ||
      priorApplied.item_count !== priorReview.item_count ||
      priorFinal.run_id !== priorReview.run_id
    ) {
      throw new Error("stale Report Builder predecessor review application");
    }
    const protectedFiles = predecessorIntegrity.protected_files;
    if (!Array.isArray(protectedFiles)) {
      throw new Error("invalid Report Builder predecessor receipts");
    }
    const receiptsByPath = new Map();
    for (const receipt of protectedFiles) {
      if (
        !isPlainObject(receipt) ||
        typeof receipt.path !== "string" ||
        receiptsByPath.has(receipt.path)
      ) {
        throw new Error("invalid Report Builder predecessor receipts");
      }
      receiptsByPath.set(receipt.path, receipt);
    }
    for (const requiredPath of [
      "run_intake.json",
      "review_payload.json",
      "ui_decisions.json",
      "applied_decisions.json",
      "final_artifacts.json",
    ]) {
      if (!receiptsByPath.has(requiredPath)) {
        throw new Error("incomplete Report Builder predecessor receipts");
      }
    }
    if (!Array.isArray(priorFinal.outputs)) {
      throw new Error("invalid Report Builder predecessor outputs");
    }
    for (const output of priorFinal.outputs) {
      const receipt = isPlainObject(output)
        ? receiptsByPath.get(output.path)
        : null;
      if (
        !receipt ||
        output.size_bytes !== receipt.byte_count ||
        output.sha256 !== receipt.sha256
      ) {
        throw new Error("stale Report Builder predecessor output receipt");
      }
    }
  }
  return rawPaths;
}

function reportBuilderRetainedReviewPaths(applied, outputDir) {
  const rawPaths = Array.isArray(applied.retained_review_paths)
    ? applied.retained_review_paths
    : [];
  if (
    rawPaths.length !== new Set(rawPaths).size ||
    !rawPaths.every(
      (relativePath) =>
        typeof relativePath === "string" &&
        /^revisions\/(?:report__[A-Za-z0-9._-]+\.txt|originals\/report__[A-Za-z0-9._-]+\.docx)$/.test(
          relativePath,
        ),
    )
  ) {
    throw new Error("invalid Report Builder retained review perimeter");
  }
  for (const relativePath of rawPaths) {
    const entry = generatedReviewPathEntryStat(
      path.join(outputDir, relativePath),
    );
    if (
      !entry ||
      !entry.isFile() ||
      entry.isSymbolicLink() ||
      entry.nlink !== 1
    ) {
      throw new Error("invalid Report Builder retained review artifact");
    }
  }
  return rawPaths;
}

function reportBuilderExpectedReviewPaths(applied, outputDir) {
  if (!isPlainObject(applied) || !Array.isArray(applied.effects)) {
    throw new Error("invalid Report Builder review successor perimeter");
  }
  const paths = new Set(["applied_decisions.json"]);
  const editEffects = applied.effects.filter(
    (effect) => isPlainObject(effect) && shortString(effect.action) === "edit",
  );
  if (!applied.effects.every(isPlainObject)) {
    throw new Error("invalid Report Builder review successor effects");
  }
  for (const effect of applied.effects) {
    const revision = shortString(effect.revision_artifact);
    if (shortString(effect.action) !== "edit") {
      if (revision) {
        throw new Error("invalid Report Builder non-edit revision path");
      }
      continue;
    }
    if (shortString(effect.target_artifact) !== "report.docx") {
      throw new Error("unsupported Report Builder material edit");
    }
    const expectedRevision =
      `revisions/report__${safePathSegment(effect.item_id, "item")}.txt`;
    if (revision !== expectedRevision) {
      throw new Error("invalid Report Builder revision path");
    }
    paths.add(expectedRevision);
  }
  const expectedBackups = editEffects.length
    ? [
        "revisions/originals/" +
          `report__${safePathSegment(editEffects[0].item_id, "item")}.docx`,
      ]
    : [];
  if (
    !Array.isArray(applied.original_backup_paths) ||
    !reportBuilderJsonValuesEqual(
      applied.original_backup_paths,
      expectedBackups,
    )
  ) {
    throw new Error("invalid Report Builder backup perimeter");
  }
  expectedBackups.forEach((relativePath) => paths.add(relativePath));
  reportBuilderHistoryPaths(applied, outputDir).forEach((relativePath) =>
    paths.add(relativePath),
  );
  reportBuilderRetainedReviewPaths(applied, outputDir).forEach(
    (relativePath) => paths.add(relativePath),
  );
  return paths;
}

function reportBuilderExpectedPhysicalPaths(outputDir) {
  const expected = new Set(REPORT_BUILDER_BASE_OUTPUT_PATHS);
  const presentInspection = [
    ...REPORT_BUILDER_INSPECTION_OUTPUT_PATHS,
  ].filter((relativePath) =>
    fs.existsSync(path.join(outputDir, relativePath)),
  );
  if (
    presentInspection.length !== 0 &&
    presentInspection.length !==
      REPORT_BUILDER_INSPECTION_OUTPUT_PATHS.size
  ) {
    throw new Error("incomplete Report Builder inspection output pair");
  }
  presentInspection.forEach((relativePath) => expected.add(relativePath));
  const presentNumeric = [...REPORT_BUILDER_NUMERIC_OUTPUT_PATHS].filter(
    (relativePath) => fs.existsSync(path.join(outputDir, relativePath)),
  );
  if (
    presentNumeric.length !== 0 &&
    presentNumeric.length !== REPORT_BUILDER_NUMERIC_OUTPUT_PATHS.size
  ) {
    throw new Error("incomplete Report Builder numeric output pair");
  }
  presentNumeric.forEach((relativePath) => expected.add(relativePath));
  const extractedRoot = path.resolve(outputDir, "extracted_inputs");
  if (fs.existsSync(extractedRoot)) {
    const sourceIndex = readJsonFileIfPresent(
      path.join(outputDir, "source_index.json"),
    );
    if (
      !isPlainObject(sourceIndex) ||
      !Array.isArray(sourceIndex.sources) ||
      !Array.isArray(sourceIndex.archive_member_bindings)
    ) {
      throw new Error("invalid Report Builder extracted source perimeter");
    }
    const bindings = new Map(
      sourceIndex.archive_member_bindings
        .filter(
          (binding) =>
            isPlainObject(binding) &&
            typeof binding.member_artifact_id === "string",
        )
        .map((binding) => [binding.member_artifact_id, binding]),
    );
    for (const source of sourceIndex.sources) {
      if (
        !isPlainObject(source) ||
        typeof source.root_path !== "string" ||
        !isPlainObject(source.receipt) ||
        typeof source.receipt.path !== "string"
      ) {
        throw new Error("invalid Report Builder extracted source entry");
      }
      const sourceRoot = reportBuilderSourceRoot(
        outputDir,
        source.root_path,
      );
      const rootRelative = path.relative(extractedRoot, sourceRoot);
      if (
        rootRelative === "" ||
        rootRelative.startsWith("..") ||
        path.isAbsolute(rootRelative)
      ) {
        continue;
      }
      const rootParts = rootRelative.split(path.sep);
      if (!rootParts.length || !/^[A-Za-z0-9._-]+$/.test(rootParts[0])) {
        throw new Error("invalid Report Builder extracted source root");
      }
      const receiptPath = reportBuilderCanonicalRelativePath(
        source.receipt.path,
      );
      const memberRelative = path.posix.join(
        ...rootParts.slice(1),
        receiptPath,
      );
      const binding = bindings.get(source.artifact_id);
      if (
        !isPlainObject(binding) ||
        memberRelative !==
          reportBuilderCanonicalRelativePath(binding.member_path)
      ) {
        throw new Error("invalid Report Builder extracted source binding");
      }
      expected.add(
        path.posix.join(
          "extracted_inputs",
          rootParts[0],
          memberRelative,
        ),
      );
    }
  }
  const appliedPath = path.join(outputDir, "applied_decisions.json");
  if (fs.existsSync(appliedPath)) {
    const applied = readJsonFileIfPresent(appliedPath);
    for (const relativePath of reportBuilderExpectedReviewPaths(
      applied,
      outputDir,
    )) {
      expected.add(relativePath);
    }
  }
  return expected;
}

function validateReportBuilderPhysicalOutputSet(outputDir) {
  const expectedFiles = reportBuilderExpectedPhysicalPaths(outputDir);
  const expectedDirectories = reportBuilderExpectedDirectories(expectedFiles);
  const { files, directories } = reportBuilderPhysicalTree(outputDir);
  if (
    !reportBuilderJsonValuesEqual(
      [...files].sort(),
      [...expectedFiles].sort(),
    ) ||
    !reportBuilderJsonValuesEqual(
      [...directories].sort(),
      [...expectedDirectories].sort(),
    )
  ) {
    throw new Error("Report Builder physical output set does not close");
  }
  return {
    physical_paths: [...files].sort(),
    physical_directories: [...directories].sort(),
  };
}

function rederiveReportBuilderPreparedState(outputDir) {
  const scriptPath = path.join(
    PLUGIN_ROOT,
    "scripts",
    "prepared_contract.py",
  );
  const completed = spawnSync(
    pythonExecutable(),
    ["-I", "-B", scriptPath, "--output-dir", outputDir],
    {
      cwd: PLUGIN_ROOT,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
    },
  );
  if (completed.error || completed.status !== 0) {
    throw new Error("Report Builder prepared replay failed");
  }
  const output = completed.stdout
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .pop();
  let parsed;
  try {
    parsed = output ? JSON.parse(output) : null;
  } catch {
    throw new Error("Report Builder prepared replay was malformed");
  }
  const validation = parsed?.validation;
  if (
    !isPlainObject(parsed) ||
    parsed.ok !== true ||
    !reportBuilderExactFields(validation, [
      "schema_version",
      "source_table_count",
      "section_count",
      "numeric_evidence_status",
      "review_successor",
      "rederived_artifacts",
    ]) ||
    validation.schema_version !==
      "report_builder.prepared_validation.v1" ||
    !Number.isInteger(validation.source_table_count) ||
    validation.source_table_count < 0 ||
    !Number.isInteger(validation.section_count) ||
    validation.section_count < 0 ||
    !["passed", "not_applicable"].includes(
      validation.numeric_evidence_status,
    ) ||
    !isPlainObject(validation.review_successor) ||
    !reportBuilderExactFields(validation.review_successor, [
      "schema_version",
      "state",
      "decision_count",
      "effect_count",
      "application_status",
      "source_mapping_review_required",
      "reviewer_authentication",
    ]) ||
    validation.review_successor.schema_version !==
      "report_builder.review_successor_validation.v1" ||
    !["pending", "reviewed", "applied"].includes(
      validation.review_successor.state,
    ) ||
    !Number.isInteger(validation.review_successor.decision_count) ||
    validation.review_successor.decision_count < 0 ||
    !Number.isInteger(validation.review_successor.effect_count) ||
    validation.review_successor.effect_count < 0 ||
    ![
      null,
      "pending_review",
      "partial_review_applied",
      "blocked",
      "final_ready",
    ].includes(validation.review_successor.application_status) ||
    typeof validation.review_successor.source_mapping_review_required !==
      "boolean" ||
    validation.review_successor.reviewer_authentication !==
      "not_established" ||
    !Array.isArray(validation.rederived_artifacts) ||
    !validation.rederived_artifacts.every(
      (receipt) =>
        reportBuilderExactFields(receipt, [
          "path",
          "byte_count",
          "sha256",
        ]) &&
        typeof receipt.path === "string" &&
        Number.isInteger(receipt.byte_count) &&
        receipt.byte_count >= 0 &&
        /^[0-9a-f]{64}$/.test(receipt.sha256 || ""),
    )
  ) {
    throw new Error("Report Builder prepared replay was malformed");
  }
  return validation;
}

function validateReportBuilderFinalGallery(outputDir, finalArtifacts) {
  if (!isPlainObject(finalArtifacts) || !Array.isArray(finalArtifacts.outputs)) {
    throw new Error("invalid Report Builder final gallery");
  }
  const seen = new Set();
  for (const output of finalArtifacts.outputs) {
    if (
      !isPlainObject(output) ||
      typeof output.path !== "string" ||
      !REPORT_BUILDER_PUBLIC_OUTPUT_ALLOWLIST.has(output.path) ||
      seen.has(output.path) ||
      !Number.isInteger(output.size_bytes) ||
      output.size_bytes < 0 ||
      !/^[0-9a-f]{64}$/.test(output.sha256 || "")
    ) {
      throw new Error("invalid Report Builder final gallery output");
    }
    seen.add(output.path);
    const artifactPath = reportBuilderContainedFile(outputDir, output.path);
    const snapshot = reportBuilderStableFileSnapshot(artifactPath);
    if (
      output.size_bytes !== snapshot.byte_count ||
      output.sha256 !== snapshot.sha256
    ) {
      throw new Error("stale Report Builder final gallery output");
    }
  }
}

function reportBuilderProtectedPaths(outputDir, finalArtifacts) {
  validateReportBuilderFinalGallery(outputDir, finalArtifacts);
  const paths = [
    "run_intake.json",
    "review_payload.json",
    "final_artifacts.json",
    "source_index.json",
  ];
  for (const optional of ["ui_decisions.json", "applied_decisions.json"]) {
    if (fs.existsSync(path.join(outputDir, optional))) paths.push(optional);
  }
  const applied = readJsonFileIfPresent(
    path.join(outputDir, "applied_decisions.json"),
  );
  if (isPlainObject(applied)) {
    paths.push(...reportBuilderHistoryPaths(applied, outputDir));
    paths.push(...reportBuilderRetainedReviewPaths(applied, outputDir));
  }
  paths.push(...finalArtifacts.outputs.map((output) => output.path));
  return Array.from(new Set(paths));
}

function validateReportBuilderIntegrityAuthority(
  outputDir,
  {
    required = false,
    failureMessage = REPORT_BUILDER_AUTHORIZATION_FAILURE,
    expectedPredecessorCheckpoint = null,
    expectedCurrentCheckpoint = null,
  } = {},
) {
  try {
    const marker = REPORT_BUILDER_ASSURED_MARKERS.some((name) =>
      fs.existsSync(path.join(outputDir, name)),
    );
    if (!marker && !required) return null;
    const runIntake = readJsonFileIfPresent(
      path.join(outputDir, "run_intake.json"),
    );
    const reviewPayload = readJsonFileIfPresent(
      path.join(outputDir, "review_payload.json"),
    );
    const finalArtifacts = readJsonFileIfPresent(
      path.join(outputDir, "final_artifacts.json"),
    );
    const integrity = readJsonFileIfPresent(
      path.join(outputDir, "review_integrity.json"),
    );
    if (
      [runIntake, reviewPayload, finalArtifacts, integrity].some(
        (value) => !isPlainObject(value),
      ) ||
      !reportBuilderExactFields(integrity, [
        "schema_version",
        "run_id",
        "source_index",
        "predecessor_checkpoint",
        "protected_files",
        "payload_digests",
        "implementation_artifact_refs",
        "implementation_receipts",
        "prepared_validation",
        "physical_paths",
        "physical_directories",
        "content_sha256",
      ]) ||
      integrity.schema_version !== "report_builder.review_integrity.v4" ||
      integrity.source_index !== "source_index.json" ||
      !Array.isArray(integrity.protected_files) ||
      !isPlainObject(integrity.payload_digests)
    ) {
      throw new Error("invalid Report Builder integrity state");
    }
    const content = { ...integrity };
    delete content.content_sha256;
    if (reportBuilderCanonicalSha256(content) !== integrity.content_sha256) {
      throw new Error("stale Report Builder integrity digest");
    }
    const currentCheckpoint = reportBuilderCheckpoint(
      expectedCurrentCheckpoint,
    );
    if (
      currentCheckpoint &&
      currentCheckpoint !== integrity.content_sha256
    ) {
      throw new Error("unexpected Report Builder current checkpoint");
    }
    const storedPredecessorCheckpoint = integrity.predecessor_checkpoint;
    if (
      storedPredecessorCheckpoint !== null &&
      currentCheckpoint === null
    ) {
      const suppliedPredecessorCheckpoint = reportBuilderCheckpoint(
        expectedPredecessorCheckpoint,
        { required: true },
      );
      if (
        suppliedPredecessorCheckpoint !== storedPredecessorCheckpoint
      ) {
        throw new Error("unexpected Report Builder predecessor checkpoint");
      }
    } else if (expectedPredecessorCheckpoint !== null) {
      reportBuilderCheckpoint(expectedPredecessorCheckpoint);
    }
    validateReportBuilderImplementationContract(integrity);
    const physicalState = validateReportBuilderPhysicalOutputSet(outputDir);
    if (
      !reportBuilderJsonValuesEqual(
        integrity.physical_paths,
        physicalState.physical_paths,
      ) ||
      !reportBuilderJsonValuesEqual(
        integrity.physical_directories,
        physicalState.physical_directories,
      )
    ) {
      throw new Error("stale Report Builder physical output binding");
    }
    validateReportBuilderSourceIndex(outputDir);
    if (
      !reportBuilderJsonValuesEqual(
        integrity.prepared_validation,
        rederiveReportBuilderPreparedState(outputDir),
      )
    ) {
      throw new Error("stale Report Builder prepared-output binding");
    }
    const runId = runIntake.run_id;
    if (
      typeof runId !== "string" ||
      !runId ||
      reviewPayload.run_id !== runId ||
      finalArtifacts.run_id !== runId ||
      integrity.run_id !== runId
    ) {
      throw new Error("Report Builder run identity mismatch");
    }
    const expectedPayloadDigests = {
      run_intake: reportBuilderCanonicalSha256(runIntake),
      review_payload: reportBuilderCanonicalSha256(reviewPayload),
      final_artifacts: reportBuilderCanonicalSha256(finalArtifacts),
    };
    for (const optional of ["ui_decisions", "applied_decisions"]) {
      const optionalState = readJsonFileIfPresent(
        path.join(outputDir, `${optional}.json`),
      );
      if (optionalState) {
        expectedPayloadDigests[optional] =
          reportBuilderCanonicalSha256(optionalState);
      }
    }
    if (
      !reportBuilderExactFields(
        integrity.payload_digests,
        Object.keys(expectedPayloadDigests),
      ) ||
      !reportBuilderJsonValuesEqual(
        integrity.payload_digests,
        expectedPayloadDigests,
      )
    ) {
      throw new Error("Report Builder payload identity mismatch");
    }
    const expectedPaths = reportBuilderProtectedPaths(
      outputDir,
      finalArtifacts,
    );
    const receiptPaths = [];
    for (const receipt of integrity.protected_files) {
      validateReportBuilderRelativeReceipt(outputDir, receipt);
      receiptPaths.push(receipt.path);
    }
    if (
      new Set(receiptPaths).size !== receiptPaths.length ||
      !reportBuilderJsonValuesEqual(
        [...receiptPaths].sort(),
        [...expectedPaths].sort(),
      )
    ) {
      throw new Error("Report Builder protected receipt set is incomplete");
    }
    for (const optional of ["ui_decisions.json", "applied_decisions.json"]) {
      const state = readJsonFileIfPresent(path.join(outputDir, optional));
      if (
        state &&
        (state.run_id !== runId ||
          state.review_payload_sha256 !== expectedPayloadDigests.review_payload)
      ) {
        throw new Error("Report Builder optional review binding is stale");
      }
    }
    return {
      runIntake,
      reviewPayload,
      finalArtifacts,
      integrity,
      reviewPayloadDigest: expectedPayloadDigests.review_payload,
    };
  } catch {
    throw new Error(failureMessage);
  }
}

function sealReportBuilderIntegrityParent(
  outputDir,
  expectedPredecessorCheckpoint = null,
) {
  const runIntake = readJsonFileIfPresent(
    path.join(outputDir, "run_intake.json"),
  );
  const reviewPayload = readJsonFileIfPresent(
    path.join(outputDir, "review_payload.json"),
  );
  const finalArtifacts = readJsonFileIfPresent(
    path.join(outputDir, "final_artifacts.json"),
  );
  if (![runIntake, reviewPayload, finalArtifacts].every(isPlainObject)) {
    throw new Error("Report Builder transaction result did not close.");
  }
  validateReportBuilderSourceIndex(outputDir);
  if (
    reviewPayload.run_id !== runIntake.run_id ||
    finalArtifacts.run_id !== runIntake.run_id
  ) {
    throw new Error("Report Builder transaction result did not close.");
  }
  const physicalState = validateReportBuilderPhysicalOutputSet(outputDir);
  const implementationReceipts = buildReportBuilderImplementationReceipts();
  const preparedValidation = rederiveReportBuilderPreparedState(outputDir);
  const protectedFiles = reportBuilderProtectedPaths(
    outputDir,
    finalArtifacts,
  ).map((relativePath) => {
    const snapshot = reportBuilderStableFileSnapshot(
      reportBuilderContainedFile(outputDir, relativePath),
    );
    return {
      path: relativePath,
      role: "review_handoff",
      byte_count: snapshot.byte_count,
      sha256: snapshot.sha256,
    };
  });
  const payloadDigests = {
    run_intake: reportBuilderCanonicalSha256(runIntake),
    review_payload: reportBuilderCanonicalSha256(reviewPayload),
    final_artifacts: reportBuilderCanonicalSha256(finalArtifacts),
  };
  for (const optional of ["ui_decisions", "applied_decisions"]) {
    const optionalState = readJsonFileIfPresent(
      path.join(outputDir, `${optional}.json`),
    );
    if (optionalState) {
      payloadDigests[optional] =
        reportBuilderCanonicalSha256(optionalState);
    }
  }
  let predecessorCheckpoint = null;
  const appliedDecisions = readJsonFileIfPresent(
    path.join(outputDir, "applied_decisions.json"),
  );
  if (isPlainObject(appliedDecisions)) {
    const historyPaths = reportBuilderHistoryPaths(
      appliedDecisions,
      outputDir,
    );
    if (historyPaths.length) {
      predecessorCheckpoint = reportBuilderCheckpoint(
        expectedPredecessorCheckpoint,
        { required: true },
      );
      if (
        appliedDecisions.predecessor_checkpoint !==
        predecessorCheckpoint
      ) {
        throw new Error("Report Builder predecessor checkpoint is stale");
      }
      const latestHistory = readJsonFileIfPresent(
        path.join(outputDir, historyPaths[historyPaths.length - 1]),
      );
      if (
        !isPlainObject(latestHistory) ||
        latestHistory.predecessor_checkpoint !==
          predecessorCheckpoint ||
        latestHistory.predecessor_integrity?.content_sha256 !==
          predecessorCheckpoint
      ) {
        throw new Error("Report Builder predecessor checkpoint is stale");
      }
    } else if (appliedDecisions.predecessor_checkpoint !== null) {
      throw new Error("Report Builder predecessor checkpoint is unexpected");
    }
  }
  const content = {
    schema_version: "report_builder.review_integrity.v4",
    run_id: runIntake.run_id,
    source_index: "source_index.json",
    predecessor_checkpoint: predecessorCheckpoint,
    protected_files: protectedFiles,
    payload_digests: payloadDigests,
    implementation_artifact_refs: implementationReceipts.map(
      (receipt) => receipt.artifact_id,
    ),
    implementation_receipts: implementationReceipts,
    prepared_validation: preparedValidation,
    physical_paths: physicalState.physical_paths,
    physical_directories: physicalState.physical_directories,
  };
  const sealed = {
    ...content,
    content_sha256: reportBuilderCanonicalSha256(content),
  };
  generatedReviewAtomicWriteFileSync(
    path.join(outputDir, "review_integrity.json"),
    `${JSON.stringify(sealed, null, 2)}\n`,
    "utf8",
  );
  validateReportBuilderIntegrityAuthority(outputDir, {
    required: true,
    failureMessage: "Report Builder transaction result did not close.",
    expectedPredecessorCheckpoint: predecessorCheckpoint,
  });
  return sealed;
}

function reportBuilderRunIdentityProjection(value) {
  if (!isPlainObject(value)) return null;
  const projection = { ...value };
  delete projection.execution_trace;
  return reportBuilderCanonicalJson(projection);
}

function reportBuilderEffectAuthorityProjection(effect) {
  if (!isPlainObject(effect)) return null;
  const fieldNames = [
    "item_id",
    "item_type",
    "title",
    "action",
    "status",
    "applied_at",
    "applied",
    "requires_followup",
    "target_artifact",
    "target_path",
    "target_id_field",
    "target_record_id",
    "target_field",
    "target_records_key",
    "source_path",
    "reviewer_note",
    "edit_value",
    "requested_documents",
    "followup_context",
  ];
  return Object.fromEntries(
    fieldNames
      .filter((fieldName) => Object.hasOwn(effect, fieldName))
      .map((fieldName) => [fieldName, effect[fieldName]]),
  );
}

function validateReportBuilderApplicationIdentity({
  outputDir,
  authorityArgs,
  expectedApplied,
  actualApplied,
  actualFinalArtifacts,
}) {
  const persistedRunIntake = readJsonFileIfPresent(
    path.join(outputDir, "run_intake.json"),
  );
  const persistedReviewPayload = readJsonFileIfPresent(
    path.join(outputDir, "review_payload.json"),
  );
  const expectedRunIntake = authorityArgs.run_intake;
  const expectedReviewPayload = authorityArgs.review_payload;
  const expectedFinalArtifacts = authorityArgs.final_artifacts;
  const sourceMappingRegeneration = expectedApplied.effects.some(
    (effect) =>
      effect.action === "edit" &&
      /^sections\.[A-Za-z0-9_]+\.assigned_table$/.test(
        shortString(effect.target_path),
      ),
  );
  if (
    !isPlainObject(persistedRunIntake) ||
    !isPlainObject(persistedReviewPayload) ||
    !isPlainObject(actualApplied) ||
    !isPlainObject(actualFinalArtifacts) ||
    !reportBuilderJsonValuesEqual(
      reportBuilderRunIdentityProjection(persistedRunIntake),
      reportBuilderRunIdentityProjection(expectedRunIntake),
    ) ||
    (!sourceMappingRegeneration &&
      !reportBuilderJsonValuesEqual(
        persistedReviewPayload,
        expectedReviewPayload,
      ))
  ) {
    throw new Error("Report Builder persisted application identity did not close.");
  }
  for (const fieldName of [
    "schema_version",
    "plugin",
    "workflow",
    "run_id",
  ]) {
    if (
      persistedReviewPayload[fieldName] !== expectedReviewPayload[fieldName] ||
      actualApplied[fieldName] !== expectedApplied[fieldName] ||
      actualFinalArtifacts[fieldName] !== expectedFinalArtifacts[fieldName]
    ) {
      throw new Error("Report Builder persisted application identity did not close.");
    }
  }
  for (const fieldName of [
    "applied_at",
    "decision_source",
    "review_payload",
    "decisions",
    "decision_count",
    "item_count",
    "reviewer",
    "predecessor_checkpoint",
  ]) {
    const expectedHas = Object.hasOwn(expectedApplied, fieldName);
    const actualHas = Object.hasOwn(actualApplied, fieldName);
    if (
      expectedHas !== actualHas ||
      (expectedHas &&
        !reportBuilderJsonValuesEqual(
          actualApplied[fieldName],
          expectedApplied[fieldName],
        ))
    ) {
      throw new Error("Report Builder persisted application identity did not close.");
    }
  }
  if (
    !Array.isArray(expectedApplied.effects) ||
    !Array.isArray(actualApplied.effects) ||
    expectedApplied.effects.length !== actualApplied.effects.length
  ) {
    throw new Error("Report Builder persisted application identity did not close.");
  }
  for (let index = 0; index < expectedApplied.effects.length; index += 1) {
    if (
      !reportBuilderJsonValuesEqual(
        reportBuilderEffectAuthorityProjection(actualApplied.effects[index]),
        reportBuilderEffectAuthorityProjection(expectedApplied.effects[index]),
      )
    ) {
      throw new Error("Report Builder persisted application identity did not close.");
    }
  }
}

function validateReportBuilderTransactionWholeTree(
  kind,
  {
    canonicalOutputDir,
    workingOutputDir,
    result,
  },
) {
  const resultPredecessorCheckpoint =
    kind === "apply"
      ? result?.applied_decisions?.predecessor_checkpoint || null
      : result?.predecessor_checkpoint || null;
  const integrityAuthority =
    validateReportBuilderIntegrityAuthority(workingOutputDir, {
      required: true,
      failureMessage: "Report Builder transaction result did not close.",
      expectedPredecessorCheckpoint: resultPredecessorCheckpoint,
    });
  const persistedUiDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "ui_decisions.json"),
  );
  if (
    !isPlainObject(result) ||
    result.ok !== true ||
    result.persisted !== true ||
    result.integrity_checkpoint !==
      integrityAuthority?.integrity?.content_sha256 ||
    result.ui_decisions_path !==
      path.join(canonicalOutputDir, "ui_decisions.json") ||
    !isPlainObject(persistedUiDecisions)
  ) {
    throw new Error("Report Builder transaction result did not close.");
  }
  if (kind === "save") {
    if (
      !reportBuilderJsonValuesEqual(
        result.ui_decisions,
        persistedUiDecisions,
      ) ||
      result.run_id !== persistedUiDecisions.run_id ||
      result.decision_count !== persistedUiDecisions.decision_count ||
      result.item_count !== persistedUiDecisions.item_count ||
      result.status !== persistedUiDecisions.status
    ) {
      throw new Error("Report Builder transaction result did not close.");
    }
    return;
  }
  const persistedAppliedDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "applied_decisions.json"),
  );
  const persistedFinalArtifacts = readJsonFileIfPresent(
    path.join(workingOutputDir, "final_artifacts.json"),
  );
  const sourceMappingRegenerated =
    reportBuilderValidatedWorkflowWritePaths(
      result,
      workingOutputDir,
    ).includes("review_payload.json");
  const uiStateCloses = sourceMappingRegenerated
    ? reportBuilderRegeneratedUiStateCloses(
        persistedUiDecisions,
        persistedAppliedDecisions,
        workingOutputDir,
      )
    : (
        persistedUiDecisions.run_id ===
          persistedAppliedDecisions?.run_id &&
        persistedUiDecisions.review_payload_sha256 ===
          persistedAppliedDecisions?.review_payload_sha256 &&
        persistedUiDecisions.decision_count ===
          persistedAppliedDecisions?.decision_count &&
        reportBuilderJsonValuesEqual(
          persistedUiDecisions.decisions,
          persistedAppliedDecisions?.decisions,
        )
      );
  if (
    result.applied_decisions_path !==
      path.join(canonicalOutputDir, "applied_decisions.json") ||
    result.final_artifacts_path !==
      path.join(canonicalOutputDir, "final_artifacts.json") ||
    result.run_intake_path !==
      path.join(canonicalOutputDir, "run_intake.json") ||
    !isPlainObject(persistedAppliedDecisions) ||
    !isPlainObject(persistedFinalArtifacts) ||
    !uiStateCloses ||
    !reportBuilderJsonValuesEqual(
      result.applied_decisions,
      persistedAppliedDecisions,
    ) ||
    !reportBuilderJsonValuesEqual(
      result.final_artifacts,
      persistedFinalArtifacts,
    ) ||
    result.run_id !== persistedAppliedDecisions.run_id ||
    result.decision_count !== persistedAppliedDecisions.decision_count ||
    result.item_count !== persistedAppliedDecisions.item_count ||
    result.blocker_count !== persistedAppliedDecisions.blocker_count ||
    result.revision_count !== persistedAppliedDecisions.revision_count ||
    result.target_update_count !==
      persistedAppliedDecisions.target_update_count ||
    result.structured_update_count !==
      persistedAppliedDecisions.structured_update_count ||
    result.native_regeneration_count !==
      persistedAppliedDecisions.native_regeneration_count ||
    result.native_regenerated_count !==
      persistedAppliedDecisions.native_regenerated_count ||
    result.application_status !==
      persistedAppliedDecisions.application_status
  ) {
    throw new Error("Report Builder transaction result did not close.");
  }
}

function reportBuilderTransactionOptions(kind) {
  return {
    failureMessage: REPORT_BUILDER_TRANSACTION_FAILURE,
    rollbackFailureMessage: REPORT_BUILDER_ROLLBACK_FAILURE,
    mapOperationError: reportBuilderMappedTransactionError,
    validateWholeTree: (context) =>
      validateReportBuilderTransactionWholeTree(kind, context),
  };
}

const REPORT_BUILDER_SOURCE_MAPPING_REGENERATION_PATHS = new Set([
  "report.docx",
  "report_analysis.json",
  "report_audit.json",
  "report_draft.md",
  "report_tables.json",
  "report_tables.xlsx",
  "used_recipe.json",
]);
const REPORT_BUILDER_STALE_NUMERIC_PATHS = new Set([
  "numeric_evidence_ledger.json",
  "source_receipts.json",
]);

function reportBuilderRegeneratedUiStateCloses(
  uiDecisions,
  appliedDecisions,
  workingOutputDir,
) {
  const reviewPayload = readJsonFileIfPresent(
    path.join(workingOutputDir, "review_payload.json"),
  );
  if (
    !isPlainObject(uiDecisions) ||
    !isPlainObject(appliedDecisions) ||
    !isPlainObject(reviewPayload) ||
    !Array.isArray(reviewPayload.items)
  ) {
    return false;
  }
  const reviewPayloadDigest =
    persistedReviewPayloadDigest(workingOutputDir);
  return (
    uiDecisions.schema_version === reviewPayload.schema_version &&
    uiDecisions.plugin === reviewPayload.plugin &&
    uiDecisions.workflow === reviewPayload.workflow &&
    uiDecisions.run_id === reviewPayload.run_id &&
    uiDecisions.run_id === appliedDecisions.run_id &&
    uiDecisions.review_payload_sha256 === reviewPayloadDigest &&
    appliedDecisions.review_payload_sha256 === reviewPayloadDigest &&
    uiDecisions.review_payload_path === "review_payload.json" &&
    uiDecisions.decision_source ===
      "not_collected_after_regeneration" &&
    uiDecisions.decided_at === null &&
    Array.isArray(uiDecisions.decisions) &&
    uiDecisions.decisions.length === 0 &&
    uiDecisions.decision_count === 0 &&
    uiDecisions.item_count === reviewPayload.items.length &&
    uiDecisions.item_count === reviewPayload.item_count &&
    uiDecisions.status === "pending_review"
  );
}

function reportBuilderValidatedWorkflowWritePaths(
  result,
  workingOutputDir,
  trustedImage = null,
) {
  const persistedAppliedDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "applied_decisions.json"),
  );
  if (
    !isPlainObject(persistedAppliedDecisions) ||
    !reportBuilderJsonValuesEqual(
      result?.applied_decisions,
      persistedAppliedDecisions,
    )
  ) {
    throw new Error("Report Builder persisted effects did not close.");
  }
  const authorizedPaths = [
    ...reportBuilderHistoryPaths(
      persistedAppliedDecisions,
      workingOutputDir,
    ),
  ];
  const persistedReviewPayload = readJsonFileIfPresent(
    path.join(workingOutputDir, "review_payload.json"),
  );
  const persistedReviewDigest =
    persistedReviewPayloadDigest(workingOutputDir);
  const appliedRegeneratedPaths = new Set(
    Array.isArray(persistedAppliedDecisions.native_regenerated_paths)
      ? persistedAppliedDecisions.native_regenerated_paths
      : [],
  );
  const effects = Array.isArray(persistedAppliedDecisions.effects)
    ? persistedAppliedDecisions.effects
    : [];
  let sourceMappingRegenerated = false;
  for (const effect of effects) {
    if (
      !isPlainObject(effect) ||
      effect.item_type !== "table_evidence" ||
      effect.action !== "edit" ||
      effect.status !== "edited" ||
      effect.applied !== true ||
      effect.artifact_update !== "native_artifact_regenerated" ||
      effect.native_regeneration_status !== "regenerated" ||
      effect.requires_native_regeneration !== false ||
      effect.terminal_application !== true ||
      typeof effect.target_path !== "string" ||
      !/^sections\.[A-Za-z0-9_]+\.assigned_table$/.test(
        effect.target_path,
      ) ||
      !isPlainObject(effect.application_receipt) ||
      effect.application_receipt.target_path !== effect.target_path
    ) {
      continue;
    }
    const effectRegeneratedPaths = new Set(
      Array.isArray(effect.native_regenerated_paths)
        ? effect.native_regenerated_paths
        : [],
    );
    if (
      !Array.from(REPORT_BUILDER_SOURCE_MAPPING_REGENERATION_PATHS).every(
        (relativePath) =>
          effectRegeneratedPaths.has(relativePath) &&
          appliedRegeneratedPaths.has(relativePath),
      )
    ) {
      continue;
    }
    const receipts = Array.isArray(
      effect.application_receipt.regenerated_outputs,
    )
      ? effect.application_receipt.regenerated_outputs
      : [];
    const receiptsByPath = new Map(
      receipts
        .filter((receipt) => isPlainObject(receipt))
        .map((receipt) => [receipt.path, receipt]),
    );
    const receiptsClose = Array.from(
      REPORT_BUILDER_SOURCE_MAPPING_REGENERATION_PATHS,
    ).every((relativePath) => {
      const receipt = receiptsByPath.get(relativePath);
      const artifactPath = path.join(workingOutputDir, relativePath);
      const artifact = generatedReviewPathEntryStat(artifactPath);
      return (
        isPlainObject(receipt) &&
        artifact?.isFile() === true &&
        artifact.isSymbolicLink() === false &&
        artifact.nlink === 1 &&
        receipt.byte_count === artifact.size &&
        receipt.sha256 === fileSha256(artifactPath)
      );
    });
    if (!receiptsClose) continue;
    if (
      !isPlainObject(persistedReviewPayload) ||
      persistedReviewPayload.run_id !== persistedAppliedDecisions.run_id ||
      persistedAppliedDecisions.review_payload_sha256 !==
        persistedReviewDigest
    ) {
      continue;
    }
    sourceMappingRegenerated = true;
  }
  if (!sourceMappingRegenerated) return authorizedPaths;
  authorizedPaths.push("review_payload.json");
  if (!trustedImage) return authorizedPaths;
  const trustedFiles = new Map(
    Array.isArray(trustedImage.files)
      ? trustedImage.files.map((entry) => [entry.path, entry])
      : [],
  );
  const priorFinalEntry = trustedFiles.get("final_artifacts.json");
  const currentFinalArtifacts = readJsonFileIfPresent(
    path.join(workingOutputDir, "final_artifacts.json"),
  );
  if (
    !isPlainObject(priorFinalEntry) ||
    !Buffer.isBuffer(priorFinalEntry.payload) ||
    !isPlainObject(currentFinalArtifacts)
  ) {
    return authorizedPaths;
  }
  const priorFinalArtifacts = JSON.parse(
    priorFinalEntry.payload.toString("utf8"),
  );
  const priorOutputPaths = new Set(
    Array.isArray(priorFinalArtifacts.outputs)
      ? priorFinalArtifacts.outputs
          .filter((output) => isPlainObject(output))
          .map((output) => output.path)
      : [],
  );
  const currentOutputPaths = new Set(
    Array.isArray(currentFinalArtifacts.outputs)
      ? currentFinalArtifacts.outputs
          .filter((output) => isPlainObject(output))
          .map((output) => output.path)
      : [],
  );
  for (const relativePath of REPORT_BUILDER_STALE_NUMERIC_PATHS) {
    if (
      trustedFiles.has(relativePath) &&
      priorOutputPaths.has(relativePath) &&
      !generatedReviewPathEntryStat(
        path.join(workingOutputDir, relativePath),
      ) &&
      !currentOutputPaths.has(relativePath)
    ) {
      authorizedPaths.push(relativePath);
    }
  }
  return authorizedPaths;
}

function validateReportBuilderTransactionInput(outputDir) {
  const outputStat = generatedReviewPathEntryStat(outputDir);
  if (!outputStat || !outputStat.isDirectory() || outputStat.isSymbolicLink()) {
    throw new Error(REPORT_BUILDER_TRANSACTION_FAILURE);
  }
  const lockPath = path.join(outputDir, ".report-builder-application.lock");
  if (generatedReviewPathEntryStat(lockPath)) {
    throw new Error(
      "Another Report Builder review application is already in progress",
    );
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
    step_id: `${shortString(appliedDecisions?.workflow) || "report_builder"}_review_apply_${stepIdSuffix || Date.now()}`,
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
      generatedReviewAtomicWriteFileSync(
        backupAbsolutePath,
        fs.readFileSync(target.absolutePath, "utf8"),
        "utf8",
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
  return "final_ready";
}

function reportBuilderCurrentMaterialReviewPaths(applied) {
  if (!isPlainObject(applied)) return [];
  const paths = [];
  for (const effect of Array.isArray(applied.effects) ? applied.effects : []) {
    if (!isPlainObject(effect)) continue;
    const revision = shortString(effect.revision_artifact);
    if (revision) paths.push(revision);
  }
  for (const relativePath of Array.isArray(applied.original_backup_paths)
    ? applied.original_backup_paths
    : []) {
    if (typeof relativePath === "string" && relativePath) {
      paths.push(relativePath);
    }
  }
  return Array.from(new Set(paths));
}

function archivePriorReportBuilderApplication(
  outputDir,
  priorRunIntake,
  priorApplied,
  priorUiDecisions,
  priorReviewPayload,
  priorFinalArtifacts,
  priorIntegrity,
  expectedPredecessorCheckpoint,
  archivedAt,
) {
  const carriedPaths = isPlainObject(priorApplied)
    ? reportBuilderHistoryPaths(priorApplied, outputDir)
    : [];
  if (
    !isPlainObject(priorApplied) ||
    !isPlainObject(priorUiDecisions) ||
    !isPlainObject(priorReviewPayload) ||
    !isPlainObject(priorRunIntake) ||
    !isPlainObject(priorFinalArtifacts) ||
    !isPlainObject(priorIntegrity)
  ) {
    return carriedPaths;
  }
  const predecessorCheckpoint = reportBuilderCheckpoint(
    expectedPredecessorCheckpoint,
    { required: true },
  );
  if (
    priorIntegrity.schema_version !== "report_builder.review_integrity.v4" ||
    priorIntegrity.content_sha256 !== predecessorCheckpoint
  ) {
    throw new Error("Report Builder predecessor checkpoint is stale");
  }
  const predecessorContent = { ...priorIntegrity };
  delete predecessorContent.content_sha256;
  if (
    reportBuilderCanonicalSha256(predecessorContent) !==
    predecessorCheckpoint
  ) {
    throw new Error("Report Builder predecessor checkpoint is stale");
  }
  const content = {
    schema_version: "report_builder.review_history_entry.v2",
    archived_at: archivedAt,
    predecessor_checkpoint: predecessorCheckpoint,
    predecessor_integrity: priorIntegrity,
    run_intake: priorRunIntake,
    review_payload: priorReviewPayload,
    ui_decisions: priorUiDecisions,
    applied_decisions: priorApplied,
    final_artifacts: priorFinalArtifacts,
  };
  const digest = reportBuilderCanonicalSha256(content);
  const relativePath =
    `revisions/history/application__${digest}.json`;
  fs.mkdirSync(path.dirname(path.join(outputDir, relativePath)), {
    recursive: true,
  });
  generatedReviewAtomicWriteFileSync(
    path.join(outputDir, relativePath),
    `${JSON.stringify(
      {
        ...content,
        content_sha256: digest,
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
  return Array.from(new Set([...carriedPaths, relativePath]));
}

function pendingNumericMeasureReviewCount(reviewPayload) {
  const items = Array.isArray(reviewPayload?.items) ? reviewPayload.items : [];
  return items.filter((item) => {
    if (!isPlainObject(item)) return false;
    if (shortString(item.id).startsWith("numeric-measure-review-")) return true;
    const evidence = Array.isArray(item.evidence) ? item.evidence : [];
    return evidence.some(
      (entry) =>
        isPlainObject(entry) &&
        shortString(entry.kind) === "numeric_measure_review_pending",
    );
  }).length;
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
      ? "Generador de informes"
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
          "## Review In Codex",
          `1. Validate the payload with \`${TOOL_NAMES.validateReview}\`.`,
          `2. Render the review workbench with \`${TOOL_NAMES.renderReview}\`.`,
          `3. Save reviewer actions with \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Apply reviewer actions with \`${TOOL_NAMES.applyDecisions}\`.`,
        ].join("\n");
    generatedReviewAtomicWriteFileSync(
      handoffPath,
      `${text}\n`,
      "utf8",
    );
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
  if (appliedDecisions.numeric_measure_pending_review_count) {
    blockers.push({
      kind: "numeric_measure_review",
      status: "needs_review",
      pending_count: appliedDecisions.numeric_measure_pending_review_count,
    });
  }
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
      numeric_measure_pending_review_count:
        appliedDecisions.numeric_measure_pending_review_count || 0,
      revision_count: revisionOutputs.length,
      revision_paths: revisionOutputs.map((output) => output.path),
      target_update_count: targetOutputs.length,
      target_update_paths: targetOutputs.map((output) => output.path),
      structured_update_count: appliedDecisions.structured_update_count || 0,
      structured_update_paths: appliedDecisions.structured_update_paths || [],
      native_regeneration_count: appliedDecisions.native_regeneration_count || 0,
      native_regeneration_paths: appliedDecisions.native_regeneration_paths || [],
      original_backup_paths: backupOutputs.map((output) => output.path),
      predecessor_checkpoint:
        appliedDecisions.predecessor_checkpoint || null,
      retained_review_paths: Array.isArray(
        appliedDecisions.retained_review_paths,
      )
        ? appliedDecisions.retained_review_paths
        : [],
      review_history_paths: Array.isArray(
        appliedDecisions.review_history_paths,
      )
        ? appliedDecisions.review_history_paths
        : [],
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
  const outputDir = resolveRunOutputDir(inputArgs);
  const prepareApplication = (trustedArgs) => {
    const { uiDecisions } = buildUiDecisions(trustedArgs);
    const validationPayload = validateReviewPayload(trustedArgs);
    const reviewPayload = validationPayload.review_payload;
    const itemById = new Map(
      reviewPayload.items.map((item) => [item.id, item]),
    );
    const appliedAt = new Date().toISOString();
    return {
      trustedArgs,
      uiDecisions,
      reviewPayload,
      language: languageFromArgs(trustedArgs),
      itemById,
      appliedAt,
      effects: uiDecisions.decisions.map((decision) =>
        buildApplicationEffect(
          decision,
          itemById.get(decision.item_id),
          appliedAt,
        ),
      ),
    };
  };
  const applyPrepared = (
    prepared,
    workingOutputDir,
    reviewPayloadDigest = null,
  ) => {
    const {
      trustedArgs,
      uiDecisions,
      reviewPayload,
      language,
      itemById,
      appliedAt,
      effects,
    } = prepared;
    preflightReportBuilderEffects(effects, itemById, workingOutputDir);
    const workingArgs = workingOutputDir
      ? generatedReviewArgsForWorkingOutput(trustedArgs, workingOutputDir)
      : trustedArgs;
    return applyDecisionPayloadWrites({
      inputArgs: workingArgs,
      authorityArgs: trustedArgs,
      uiDecisions,
      reviewPayload,
      reviewPayloadDigest,
      language,
      effects,
      appliedAt,
      outputDir: workingOutputDir,
    });
  };
  if (!outputDir) return applyPrepared(prepareApplication(inputArgs), null);
  preflightClientWorkflowRun(outputDir, inputArgs?.review_payload?.run_id);
  validateReportBuilderTransactionInput(outputDir);
  return withGeneratedReviewOutputTransaction(
    outputDir,
    ({
      workingOutputDir,
      canonicalOutputDir,
      trustedImage,
    }) => {
      const authority = parentBoundReportBuilderArgs(inputArgs, {
        outputDir,
        trustedImage,
        trustedImageCaptured: true,
      });
      const integrity = validateReportBuilderIntegrityAuthority(
        workingOutputDir,
        {
          required: authority.assured,
          failureMessage: REPORT_BUILDER_AUTHORIZATION_FAILURE,
          expectedCurrentCheckpoint: fs.existsSync(
            path.join(workingOutputDir, "applied_decisions.json"),
          )
            ? authority.args.expected_predecessor_checkpoint || null
            : null,
        },
      );
      if (!integrity) {
        throw new Error(REPORT_BUILDER_AUTHORIZATION_FAILURE);
      }
      const workingResult = applyPrepared(
        prepareApplication(authority.args),
        workingOutputDir,
        integrity.reviewPayloadDigest,
      );
      const authorizedWritePaths =
        generatedReviewCollectApplicationWritePaths(workingResult);
      authorizedWritePaths.push(
        ...reportBuilderValidatedWorkflowWritePaths(
          workingResult,
          workingOutputDir,
          trustedImage,
        ),
        "report_audit.json",
        "review_integrity.json",
      );
      const canonicalResult = generatedReviewRewriteOutputPaths(
        workingResult,
        workingOutputDir,
        canonicalOutputDir,
      );
      return generatedReviewTransactionEnvelope(
        canonicalResult,
        authorizedWritePaths,
      );
    },
    reportBuilderTransactionOptions("apply"),
  );
}

function applyDecisionPayloadWrites({
  inputArgs,
  authorityArgs,
  uiDecisions,
  reviewPayload,
  reviewPayloadDigest,
  language,
  effects,
  appliedAt,
  outputDir,
}) {
  const decisionOutputPath = resolveDecisionOutputPath(inputArgs);
  const priorAppliedDecisions = outputDir
    ? readJsonFileIfPresent(
        path.join(outputDir, "applied_decisions.json"),
      )
    : null;
  const priorUiDecisions = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "ui_decisions.json"))
    : null;
  const priorReviewPayload = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "review_payload.json"))
    : null;
  const priorRunIntake = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "run_intake.json"))
    : null;
  const priorFinalArtifacts = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "final_artifacts.json"))
    : null;
  const priorIntegrity = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "review_integrity.json"))
    : null;
  const predecessorCheckpoint = priorAppliedDecisions
    ? reportBuilderCheckpoint(
        inputArgs.expected_predecessor_checkpoint,
        { required: true },
      )
    : null;
  if (
    priorAppliedDecisions &&
    (!isPlainObject(priorIntegrity) ||
      priorIntegrity.content_sha256 !== predecessorCheckpoint)
  ) {
    throw new Error("Report Builder predecessor checkpoint is stale");
  }
  if (outputDir) {
    uiDecisions.review_payload_sha256 = reviewPayloadDigest;
  }
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
    const numericMeasurePendingReviewCount =
      pendingNumericMeasureReviewCount(reviewPayload);
    let applicationStatus = statusFromEffects(effects, reviewPayload.items.length);
    if (
      numericMeasurePendingReviewCount > 0 &&
      applicationStatus === "final_ready"
    ) {
      applicationStatus = "partial_review_applied";
    }
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
    review_payload_sha256: reviewPayloadDigest,
    decision_review_payload_sha256: reviewPayloadDigest,
    decisions: uiDecisions.decisions,
    effects,
    decision_count: uiDecisions.decision_count,
    item_count: reviewPayload.items.length,
    blocker_count: blockerCount,
    numeric_measure_pending_review_count: numericMeasurePendingReviewCount,
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
    predecessor_checkpoint: predecessorCheckpoint,
    };
    if (uiDecisions.reviewer) appliedDecisions.reviewer = uiDecisions.reviewer;
    appliedDecisions.review_history_paths = outputDir
      ? archivePriorReportBuilderApplication(
          outputDir,
          priorRunIntake,
          priorAppliedDecisions,
          priorUiDecisions,
          priorReviewPayload,
          priorFinalArtifacts,
          priorIntegrity,
          predecessorCheckpoint,
          appliedAt,
        )
      : [];
    const currentMaterialPaths = new Set(
      reportBuilderCurrentMaterialReviewPaths(appliedDecisions),
    );
    appliedDecisions.retained_review_paths = outputDir
      ? Array.from(
          new Set([
            ...(Array.isArray(priorAppliedDecisions?.retained_review_paths)
              ? priorAppliedDecisions.retained_review_paths
              : []),
            ...reportBuilderCurrentMaterialReviewPaths(
              priorAppliedDecisions,
            ),
          ]),
        ).filter((relativePath) => !currentMaterialPaths.has(relativePath))
      : [];

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
    applyWorkflowSpecificReviewApplication(
      outputDir,
      appliedOutputPath,
      finalArtifactsPath,
      appliedOutputPath ? fileSha256(appliedOutputPath) : null,
      finalArtifactsPath ? fileSha256(finalArtifactsPath) : null,
    );
    const responseAppliedDecisions =
      readJsonFileIfPresent(appliedOutputPath) || appliedDecisions;
    const responseFinalArtifacts =
      readJsonFileIfPresent(finalArtifactsPath) || finalArtifacts;
    if (outputDir) {
      validateReportBuilderApplicationIdentity({
        outputDir,
        authorityArgs,
        expectedApplied: appliedDecisions,
        actualApplied: responseAppliedDecisions,
        actualFinalArtifacts: responseFinalArtifacts,
      });
    }
    const runIntakePath = appendReviewApplicationExecutionTrace(
      inputArgs,
      outputDir,
      responseAppliedDecisions,
      responseFinalArtifacts,
    );
    if (outputDir) {
      sealReportBuilderIntegrityParent(
        outputDir,
        predecessorCheckpoint,
      );
    }
  const currentIntegrity = outputDir
    ? readJsonFileIfPresent(path.join(outputDir, "review_integrity.json"))
    : null;
  const result = {
    ok: true,
    validation_type: "report_builder_application",
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
    persisted,
    ui_decisions_path: decisionOutputPath,
    applied_decisions_path: persisted ? appliedOutputPath : null,
    final_artifacts_path: finalArtifactsPath,
    run_intake_path: runIntakePath,
    integrity_checkpoint: currentIntegrity?.content_sha256 || null,
    message: persisted
      ? isSpanish(language)
        ? `Se aplicaron ${responseAppliedDecisions.decision_count} decisiones del Generador de informes.`
        : `Applied ${responseAppliedDecisions.decision_count} Build Report decisions.`
      : isSpanish(language)
        ? "Las decisiones aplicadas son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
        : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
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
      "report-builder",
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8", maxBuffer: 64 * 1024 },
  );
  if (completed.error || completed.status !== 0) {
    throw new Error(
      "Report Builder persistence requires a running v2 customer-folder workflow run",
    );
  }
  let result;
  try {
    result = JSON.parse(completed.stdout.trim());
  } catch {
    throw new Error(
      "Report Builder customer-run preflight returned an invalid result",
    );
  }
  if (
    !isPlainObject(result) ||
    result.ok !== true ||
    result.schema_version !== "vera.client_workflow_context.v2" ||
    result.workflow_id !== "report-builder" ||
    result.run_id !== expectedRunId
  ) {
    throw new Error(
      "Report Builder customer-run preflight returned an invalid result",
    );
  }
  return result;
}

function sanitizedChildFailure(completed, fallback) {
  const output = [completed.stderr, completed.stdout]
    .filter((value) => typeof value === "string" && value.trim())
    .join("\n");
  const terminalLine = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .pop();
  if (!terminalLine) return fallback;
  const exception = terminalLine.match(
    /^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):\s*(.+)$/,
  );
  if (!exception) return fallback;
  const detail = exception[2]
    .replace(/\/(?:[^/\s]+\/)+[^:\s,)]+/g, "[local path]")
    .replace(/[A-Za-z]:\\(?:[^\\\s]+\\)+[^:\s,)]+/g, "[local path]");
  return `${fallback} ${exception[1]}: ${detail}`;
}

function applyWorkflowSpecificReviewApplication(
  outputDir,
  appliedOutputPath,
  finalArtifactsPath,
  expectedAppliedSha256,
  expectedFinalArtifactsSha256,
) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const clientEngagement = reportBuilderClientEngagementPath(outputDir);
  if (!clientEngagement) {
    throw new Error("Report Builder customer-run context is unavailable.");
  }
  const completed = spawnSync(
    pythonExecutable(),
    [
      "-I",
      "-B",
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
      "--expected-applied-sha256",
      expectedAppliedSha256,
      "--expected-final-artifacts-sha256",
      expectedFinalArtifactsSha256,
      "--client-engagement",
      clientEngagement,
      "--persistent-output-dir",
      reportBuilderPersistentOutputDir(clientEngagement),
    ],
    {
      cwd: PLUGIN_ROOT,
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
    },
  );
  if (completed.error) {
    throw new Error("Report Builder native regeneration could not start.");
  }
  if (completed.status !== 0) {
    throw new Error(
      sanitizedChildFailure(
        completed,
        "Report Builder native regeneration failed.",
      ),
    );
  }
  const output = completed.stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  if (!output || output.length > 512 * 1024) {
    throw new Error("Report Builder native regeneration returned an invalid result.");
  }
  let parsed;
  try {
    parsed = JSON.parse(output);
  } catch {
    throw new Error("Report Builder native regeneration returned an invalid result.");
  }
  if (!isPlainObject(parsed) || parsed.ok !== true) {
    throw new Error("Report Builder native regeneration returned an invalid result.");
  }
  return { ok: true };
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const authority = parentBoundReportBuilderArgs(args);
    const payload = validateReviewPayload(authority.args);
    if (authority.outputDir) {
      validateReportBuilderIntegrityAuthority(authority.outputDir, {
        required: authority.assured,
        expectedPredecessorCheckpoint:
          authority.args.expected_predecessor_checkpoint || null,
      });
    }
    return {
      ok: true,
      validation_type: "report_builder_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: isSpanish(languageFromArgs(args))
        ? "Los datos de revisión del Generador de informes son válidos. Puede ejecutar render_report_builder_review una vez."
        : "Build Report review payload is valid. It is safe to call render_report_builder_review once.",
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.renderReview) {
    const authority = parentBoundReportBuilderArgs(args);
    if (authority.outputDir) {
      validateReportBuilderIntegrityAuthority(authority.outputDir, {
        required: authority.assured,
        expectedPredecessorCheckpoint:
          authority.args.expected_predecessor_checkpoint || null,
      });
    }
    return validateReviewPayload(authority.args);
  }
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(
    isSpanish(languageFromArgs(args))
      ? `herramienta desconocida del widget del Generador de informes: ${name}`
      : `unknown Build Report widget tool: ${name}`,
  );
}

function toolResult(payload, toolName) {
  const result = {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    result._meta = toolUiMeta(WIDGET_URI, toolName);
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
        },
        instructions: isSpanish(language)
          ? "Use validate_report_builder_review antes de render_report_builder_review. Dé prioridad al widget MCP para la entrega de la revisión del Generador de informes; use save_report_builder_decisions para guardar las acciones de revisión en ui_decisions.json y apply_report_builder_decisions para escribir applied_decisions.json y actualizar el estado de final_artifacts.json cuando se recopilen decisiones; recurra a la revisión Markdown o estática solo si MCP no está disponible."
          : "Use validate_report_builder_review before render_report_builder_review. Prefer the MCP widget for Build Report review handoff; use save_report_builder_decisions to persist reviewer actions to ui_decisions.json and apply_report_builder_decisions to write applied_decisions.json plus final_artifacts.json status when decisions are collected; fall back to Markdown/static review only when MCP is unavailable.",
      });
    }
    if (method === "notifications/initialized") {
      return null;
    }
    if (method === "tools/list") {
      return rpcResponse(messageId, { tools: toolDefinitions() });
    }
    if (method === "tools/call") {
      const name = params.name;
      const args = isPlainObject(params.arguments) ? params.arguments : {};
      return rpcResponse(messageId, toolResult(callTool(name, args), name));
    }
    if (method === "resources/list") {
      return rpcResponse(messageId, { resources: resources() });
    }
    if (method === "resources/read") {
      const uri = params.uri;
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
    return rpcError(messageId, -32601, isSpanish(languageFromArgs(params)) ? `método no encontrado: ${method}` : `method not found: ${method}`);
  } catch (error) {
    if (method === "tools/call") {
      const args = isPlainObject(params.arguments) ? params.arguments : params;
      return rpcResponse(messageId, toolError(localizeRuntimeError(error.message, languageFromArgs(args))));
    }
    return rpcError(messageId, -32603, localizeRuntimeError(error.message, languageFromArgs(params)));
  }
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let response;
  try {
    response = handleRpc(JSON.parse(trimmed));
  } catch (error) {
    response = rpcError(null, -32700, error.message);
  }
  if (response != null) {
    process.stdout.write(`${JSON.stringify(response)}\n`);
  }
});

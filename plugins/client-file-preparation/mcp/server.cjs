"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");

const SERVER_NAME = "client-file-preparation-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/client-file-preparation-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 1_500_000;
const TOOL_NAMES = {
  validateReview: "validate_client_file_preparation_review",
  renderReview: "render_client_file_preparation_review",
  saveDecisions: "save_client_file_preparation_decisions",
  applyDecisions: "apply_client_file_preparation_decisions",
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
const MAX_LOCAL_JSON_BYTES = 25_000_000;
const MAX_PERSISTENCE_CONTEXTS = 128;
const PERSISTENCE_CONTEXT_TTL_MS = 4 * 60 * 60 * 1000;
const PERSISTENCE_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const PERSISTENCE_CONTEXTS = new Map();
const PACKAGE_HASH_BASIS = "sorted_outputs_path_size_sha256_canonical_json_v1";
const MAX_REVIEWER_REFERENCE_LENGTH = 160;
const REVIEWER_REFERENCE_SECRET_RE =
  /(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|session[_ -]?(?:token|cookie)|authorization)\s*[:=]/i;
const REVIEWER_REFERENCE_CREDENTIAL_VALUE_RE =
  /^(?:sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.)/;
const PROTECTED_RUN_FILES = new Set([
  "final_artifacts.json",
  "review_payload.json",
  "run_intake.json",
  "ui_decisions.json",
  "applied_decisions.json",
]);
const ITEM_TYPES = new Set([
  "document_inventory",
  "uncertain_file",
  "missing_document_request",
  "extracted_fiscal_field",
  "duplicate_warning",
  "formal_xml_anomaly",
  "draft_memo_section",
  "draft_client_email",
]);

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
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
  const meta = {
    ui: { resourceUri, visibility: ["model"] },
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    meta["openai/toolInvocation/invoking"] = "Rendering client file preparation review";
    meta["openai/toolInvocation/invoked"] = "Rendered client file preparation review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive New Client · File Preparation review surface for document inventory, missing documents, fiscal fields, memo, and client email draft.",
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
      run_intake: { type: "object", description: "Optional run_intake.json object." },
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional ui_decisions.json object." },
      final_artifacts: { type: "object", description: "Optional final_artifacts.json object." },
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
      run_intake: { type: "object", description: "Optional run_intake.json object with output_dir for persistence." },
      persistence_token: {
        type: "string",
        pattern: "^[A-Za-z0-9_-]{43}$",
        description: "Opaque token returned by the render tool for path-private persistence.",
      },
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: {
        type: "string",
        minLength: 1,
        maxLength: MAX_REVIEWER_REFERENCE_LENGTH,
        description:
          "Stable professional or account reference. A real professional name is allowed. Required before a complete review can become final_ready; do not enter credentials, session material, or raw local paths.",
      },
    },
    ["review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate New Client · File Preparation review payload",
      description:
        "Validate the New Client · File Preparation review-session payload before rendering. Call this first, then render_client_file_preparation_review.",
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
      title: "Render New Client · File Preparation review",
      description:
        "Render a New Client · File Preparation review-session payload as an MCP HTML widget for document inventory, exceptions, fields, memo, and email review.",
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
      title: "Save New Client · File Preparation review decisions",
      description:
        "Validate New Client · File Preparation review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.applyDecisions,
      title: "Apply New Client · File Preparation review decisions",
      description:
        "Validate New Client · File Preparation review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
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
      name: "client_file_preparation_review_widget",
      title: "New Client · File Preparation review widget",
      description:
        "Renders New Client · File Preparation review-session payloads with searchable review items and source previews.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown New Client · File Preparation widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "client-file-preparation-review-widget.html"),
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

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalValue(value[key])]),
  );
}

function canonicalJson(value) {
  return JSON.stringify(canonicalValue(value));
}

function canonicalSha256(value) {
  return crypto.createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function normalizeReviewerReference(value, fieldPath = "reviewer") {
  const reference = boundedOptionalString(value, fieldPath);
  if (!reference) return "";
  const containsControlCharacter = /[\u0000-\u001f\u007f]/.test(reference);
  const containsRawPath = reference.includes("/") || reference.includes("\\");
  if (
    reference.length > MAX_REVIEWER_REFERENCE_LENGTH
    || containsControlCharacter
    || containsRawPath
    || REVIEWER_REFERENCE_SECRET_RE.test(reference)
    || REVIEWER_REFERENCE_CREDENTIAL_VALUE_RE.test(reference)
  ) {
    throw new Error(
      `${fieldPath} must be a stable professional or account reference of at most ${MAX_REVIEWER_REFERENCE_LENGTH} characters and must not contain credentials, session material, or raw local paths`,
    );
  }
  return reference;
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

function sanitizedRunIntakeForReview(value) {
  if (!isPlainObject(value)) return null;
  const sanitized = { ...value, input_paths: [] };
  delete sanitized.output_dir;
  delete sanitized.source_snapshot;
  if (isPlainObject(value.data_posture)) {
    const localFiles = Array.isArray(value.data_posture.local_files_read)
      ? value.data_posture.local_files_read
      : [];
    sanitized.data_posture = {
      ...value.data_posture,
      local_files_read: [],
      local_files_read_count: localFiles.length,
    };
  }
  if (Array.isArray(value.execution_trace)) {
    sanitized.execution_trace = value.execution_trace.map((entry) => {
      if (!isPlainObject(entry)) return entry;
      const redactPath = (candidate) => {
        const text = shortString(candidate);
        if (!text) return text;
        return path.isAbsolute(text) || /^[A-Za-z]:[\\/]/.test(text)
          ? "<local-path>"
          : text;
      };
      return {
        ...entry,
        command: Array.isArray(entry.command) ? entry.command.map(redactPath) : entry.command,
        inputs: Array.isArray(entry.inputs) ? entry.inputs.map(redactPath) : [],
      };
    });
  }
  return sanitized;
}

function sanitizedFinalArtifactsForReview(value) {
  if (!isPlainObject(value)) return null;
  const sanitized = JSON.parse(JSON.stringify(value));
  if (Array.isArray(sanitized.outputs)) {
    sanitized.outputs = sanitized.outputs.map((output) => {
      if (!isPlainObject(output)) return output;
      if (
        typeof output.path === "string"
        && (path.isAbsolute(output.path) || /^[A-Za-z]:[\\/]/.test(output.path))
      ) {
        return { ...output, path: "<local-path>" };
      }
      return output;
    });
  }
  return sanitized;
}

function validateReviewPayload(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const reviewPayload = inputArgs.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.plugin !== "client-file-preparation") {
    throw new Error('review_payload.plugin must be "client-file-preparation"');
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
    widget_type: "client_file_preparation_review",
    run_intake: sanitizedRunIntakeForReview(inputArgs.run_intake),
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
    throw new Error(`client file preparation widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
}

function reviewPayloadForWidget(inputArgs) {
  const payload = validateReviewPayload(inputArgs);
  let persistenceToken = null;
  try {
    persistenceToken = issuePersistenceToken(inputArgs, payload.review_payload);
    payload.decision_policy.can_persist = Boolean(persistenceToken);
    if (persistenceToken) {
      payload.decision_policy.persistence_token = persistenceToken;
    }
    payload.final_artifacts = sanitizedFinalArtifactsForReview(inputArgs.final_artifacts);
    if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
      throw new Error(
        `client file preparation widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`,
      );
    }
    return payload;
  } catch (error) {
    if (persistenceToken) PERSISTENCE_CONTEXTS.delete(persistenceToken);
    throw error;
  }
}

function resolveDecisionOutputPath(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputDir) return null;
  return path.join(path.resolve(outputDir), "ui_decisions.json");
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
  const reviewer = normalizeReviewerReference(inputArgs.reviewer, "reviewer");
  const currentUiDecisions = isPlainObject(inputArgs.ui_decisions) ? inputArgs.ui_decisions : null;
  const reviewPayloadPath =
    typeof currentUiDecisions?.review_payload_path === "string"
      ? path.basename(currentUiDecisions.review_payload_path)
      : "review_payload.json";
  const status =
    decisions.length === 0
      ? "pending_review"
      : decisions.length === reviewPayload.items.length
          && decisions.every((decision) => decision.action !== "skip")
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
  const { uiDecisions } = buildUiDecisions(inputArgs);
  const reviewPayload = validateReviewPayload(inputArgs).review_payload;
  const persistentInputArgs = inputArgsWithPersistentOutput(inputArgs, reviewPayload);
  const persistence = validatePersistentState(persistentInputArgs, reviewPayload);
  const decisionOutputPath = persistence
    ? path.join(persistence.outputDir, "ui_decisions.json")
    : null;
  if (persistence) {
    stabilizeReviewer(uiDecisions, persistence.currentUiDecisions);
    uiDecisions.review_payload_sha256 = persistence.reviewBytesHash;
    uiDecisions.review_payload_canonical_sha256 = persistence.reviewCanonicalHash;
  }
  let persisted = false;
  if (persistence && decisionOutputPath) {
    withStagedRunDirectory(persistence.outputDir, (stagedDir) => {
      const stagedDecisionPath = path.join(stagedDir, "ui_decisions.json");
      const stagedFinalPath = path.join(stagedDir, "final_artifacts.json");
      fs.writeFileSync(stagedDecisionPath, `${JSON.stringify(uiDecisions, null, 2)}\n`, "utf8");
      const stagedFinal = readJsonFileIfPresent(stagedFinalPath);
      const refreshed = refreshFinalArtifactsIntegrity(stagedDir, stagedFinal);
      refreshed.review_payload_sha256 = persistence.reviewBytesHash;
      refreshed.review_payload_canonical_sha256 = persistence.reviewCanonicalHash;
      fs.writeFileSync(stagedFinalPath, `${JSON.stringify(refreshed, null, 2)}\n`, "utf8");
    });
    persisted = true;
  }
  return {
    ok: true,
    validation_type: "client_file_preparation_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? "ui_decisions.json" : null,
    message: persisted
      ? `Saved ${uiDecisions.decision_count} New Client · File Preparation decisions.`
      : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputDir) return null;
  const requested = path.resolve(outputDir);
  if (!fs.existsSync(requested)) {
    throw new Error("run_intake.output_dir must identify an existing directory");
  }
  const stat = fs.lstatSync(requested);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("run_intake.output_dir must be a regular directory without symlinks");
  }
  const resolved = fs.realpathSync(requested);
  if (resolved !== requested) {
    throw new Error("run_intake.output_dir may not traverse symlinks");
  }
  const protectedRoot = protectedOutputRoots().find((root) => isInsideOrEqual(resolved, root));
  if (protectedRoot) {
    throw new Error(
      "run_intake.output_dir must be outside the plugin package and source repository",
    );
  }
  const broadRoots = new Set([
    path.parse(resolved).root,
    path.resolve(os.homedir()),
    path.resolve(os.tmpdir()),
  ]);
  if (broadRoots.has(resolved)) {
    throw new Error("run_intake.output_dir must be a dedicated run directory");
  }
  if (process.platform !== "win32") {
    if ((stat.mode & 0o077) !== 0) {
      throw new Error("run_intake.output_dir must be owner-only (mode 0700)");
    }
    if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
      throw new Error("run_intake.output_dir must be owned by the current user");
    }
  }
  return resolved;
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

function findRepositoryRoot(start) {
  let current = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(current, ".git"))) return current;
    const parent = path.dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}

function protectedOutputRoots() {
  const roots = new Set([PLUGIN_ROOT]);
  const repositoryRoot = findRepositoryRoot(PLUGIN_ROOT);
  if (repositoryRoot) roots.add(repositoryRoot);
  return [...roots].map((entry) => fs.realpathSync(entry));
}

function isInsideOrEqual(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return (
    relative === ""
    || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))
  );
}

function validateRunRelativePath(value, fieldPath = "run output path") {
  const rawPath = shortString(value);
  if (!rawPath) throw new Error(`${fieldPath} is required`);
  if (path.isAbsolute(rawPath) || rawPath.includes("\\")) {
    throw new Error(`${fieldPath} must be a run-local POSIX relative path`);
  }
  const parsed = rawPath.split("/");
  if (parsed.some((segment) => !segment || segment === "." || segment === "..")) {
    throw new Error(`${fieldPath} must not contain empty, dot, or parent segments`);
  }
  const normalized = path.posix.normalize(rawPath);
  if (normalized !== rawPath) {
    throw new Error(`${fieldPath} must be normalized`);
  }
  return rawPath;
}

function assertOwnerOnlyStat(stat, fieldPath, expectedDirectory) {
  if (process.platform === "win32") return;
  const expectedMode = expectedDirectory ? "0700" : "0600";
  if ((stat.mode & 0o077) !== 0) {
    throw new Error(`${fieldPath} must be owner-only (mode ${expectedMode})`);
  }
  if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
    throw new Error(`${fieldPath} must be owned by the current user`);
  }
}

function resolveSafeRunOutputPath(outputDir, value, { mustExist = false } = {}) {
  if (!outputDir) return null;
  const rawPath = validateRunRelativePath(value);
  const absolutePath = path.resolve(outputDir, ...rawPath.split("/"));
  const relativePath = path.relative(outputDir, absolutePath);
  if (!relativePath || !isInsideOrEqual(absolutePath, outputDir)) return null;
  let current = outputDir;
  for (const segment of rawPath.split("/")) {
    current = path.join(current, segment);
    if (!fs.existsSync(current)) {
      if (mustExist) throw new Error(`run output is missing: ${rawPath}`);
      break;
    }
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) {
      throw new Error(`run output may not traverse symbolic links: ${rawPath}`);
    }
    if (current !== absolutePath && !stat.isDirectory()) {
      throw new Error(`run output parent is not a directory: ${rawPath}`);
    }
  }
  if (fs.existsSync(absolutePath)) {
    const resolved = fs.realpathSync(absolutePath);
    if (!isInsideOrEqual(resolved, outputDir)) {
      throw new Error(`run output resolves outside the run directory: ${rawPath}`);
    }
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
    readJsonFileIfPresent(finalArtifactsPath) ||
    (isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : null) ||
    {}
  );
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function canonicalPackageEntries(outputs) {
  return outputs
    .map((output) => ({
      path: artifactPathKey(output?.path),
      sha256: shortString(output?.sha256).toLowerCase(),
      size_bytes: Number(output?.size_bytes),
    }))
    .sort((left, right) => Buffer.compare(Buffer.from(left.path, "utf8"), Buffer.from(right.path, "utf8")));
}

function packageHash(outputs) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(canonicalPackageEntries(outputs)), "utf8")
    .digest("hex");
}

function validateManifestIntegrity(outputDir, finalArtifacts) {
  if (!outputDir || !isPlainObject(finalArtifacts)) {
    throw new Error("run_intake.output_dir must contain final_artifacts.json");
  }
  if (
    finalArtifacts.plugin !== "client-file-preparation"
    || finalArtifacts.workflow !== "client-file-preparation"
  ) {
    throw new Error("final_artifacts identity must be client-file-preparation");
  }
  requireString(finalArtifacts.run_id, "final_artifacts.run_id");
  const integrity = isPlainObject(finalArtifacts.integrity) ? finalArtifacts.integrity : null;
  if (!integrity) throw new Error("final_artifacts.integrity is required");
  if (integrity.algorithm !== "sha256") {
    throw new Error("final_artifacts.integrity.algorithm must be sha256");
  }
  if (integrity.package_hash_basis !== PACKAGE_HASH_BASIS) {
    throw new Error(`unsupported final_artifacts package_hash_basis: ${integrity.package_hash_basis}`);
  }
  if (!Array.isArray(finalArtifacts.outputs) || finalArtifacts.outputs.length === 0) {
    throw new Error("final_artifacts.outputs must be a non-empty array");
  }
  const outputs = finalArtifacts.outputs;
  const seenPaths = new Set();
  const outputRecords = new Map();
  for (const [index, output] of outputs.entries()) {
    const outputPath = validateRunRelativePath(
      output?.path,
      `final_artifacts.outputs[${index}].path`,
    );
    if (outputPath === "final_artifacts.json") {
      throw new Error("final_artifacts.json may not include itself in outputs");
    }
    if (seenPaths.has(outputPath)) throw new Error(`duplicate final artifact path: ${outputPath}`);
    seenPaths.add(outputPath);
    if (!/^[a-f0-9]{64}$/.test(shortString(output?.sha256))) {
      throw new Error(`final_artifacts.outputs[${index}].sha256 is invalid`);
    }
    if (!Number.isSafeInteger(output?.size_bytes) || output.size_bytes < 0) {
      throw new Error(`final_artifacts.outputs[${index}].size_bytes is invalid`);
    }
    const resolved = resolveSafeRunOutputPath(outputDir, outputPath, { mustExist: true });
    const outputStat = fs.lstatSync(resolved.absolutePath);
    if (!outputStat.isFile() || outputStat.isSymbolicLink()) {
      throw new Error(`final artifact is missing or unsafe: ${outputPath}`);
    }
    assertOwnerOnlyStat(outputStat, `final artifact ${outputPath}`, false);
    const actualSize = outputStat.size;
    if (actualSize !== output.size_bytes) {
      throw new Error(`final artifact size mismatch: ${outputPath}`);
    }
    const actualHash = sha256File(resolved.absolutePath);
    if (actualHash !== output.sha256) {
      throw new Error(`final artifact sha256 mismatch: ${outputPath}`);
    }
    outputRecords.set(outputPath, output);
  }
  const expectedPackageHash = packageHash(outputs);
  if (!/^[a-f0-9]{64}$/.test(shortString(integrity.package_hash))) {
    throw new Error("final_artifacts.integrity.package_hash is invalid");
  }
  if (integrity.package_hash !== expectedPackageHash) {
    throw new Error("final_artifacts package_hash mismatch");
  }
  return {
    verified: true,
    package_hash: expectedPackageHash,
    output_records: outputRecords,
  };
}

function refreshFinalArtifactsIntegrity(outputDir, finalArtifacts) {
  if (!outputDir || !isPlainObject(finalArtifacts)) return finalArtifacts;
  const outputs = Array.isArray(finalArtifacts.outputs) ? finalArtifacts.outputs : [];
  const refreshedOutputs = outputs.map((output) => {
    const outputPath = artifactPathKey(output?.path);
    const resolved = resolveSafeRunOutputPath(outputDir, outputPath);
    if (!resolved || !fs.existsSync(resolved.absolutePath) || !fs.statSync(resolved.absolutePath).isFile()) {
      throw new Error(`cannot seal missing final artifact: ${outputPath || "(empty path)"}`);
    }
    return {
      ...output,
      path: outputPath,
      size_bytes: fs.statSync(resolved.absolutePath).size,
      sha256: sha256File(resolved.absolutePath),
    };
  });
  return {
    ...finalArtifacts,
    outputs: refreshedOutputs,
    integrity: {
      algorithm: "sha256",
      package_hash_basis: PACKAGE_HASH_BASIS,
      package_hash: packageHash(refreshedOutputs),
    },
  };
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
  fs.writeFileSync(filePath, serializeCsv(rows), "utf8");
  return { updatedRows: updated, rowCount: Math.max(rows.length - 1, 0) };
}

function updateJsonArtifact(filePath, effect, spec) {
  const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (Array.isArray(parsed)) {
    const updatedRows = updateMatchingRecord(parsed, spec, effect.edit_value);
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    return { updatedRows, rowCount: parsed.length };
  }
  if (isPlainObject(parsed) && spec.recordsKey && Array.isArray(parsed[spec.recordsKey])) {
    const records = parsed[spec.recordsKey];
    const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    return { updatedRows, rowCount: records.length };
  }
  if (isPlainObject(parsed) && String(parsed[spec.idField] ?? "") === spec.recordId) {
    parsed[spec.targetField] = effect.edit_value;
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
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
  fs.writeFileSync(filePath, `${records.map((record) => JSON.stringify(record)).join("\n")}\n`, "utf8");
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

function readRunJsonFile(filePath, { required = true } = {}) {
  if (!fs.existsSync(filePath)) {
    if (!required) return null;
    throw new Error(`${path.basename(filePath)} is required in the run directory`);
  }
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${path.basename(filePath)} must be a regular JSON file without symlinks`);
  }
  assertOwnerOnlyStat(stat, path.basename(filePath), false);
  if (stat.size > MAX_LOCAL_JSON_BYTES) {
    throw new Error(`${path.basename(filePath)} exceeds ${MAX_LOCAL_JSON_BYTES} bytes`);
  }
  let value;
  try {
    value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    throw new Error(`${path.basename(filePath)} must contain valid JSON`);
  }
  if (!isPlainObject(value)) {
    throw new Error(`${path.basename(filePath)} must contain a JSON object`);
  }
  return value;
}

function validateRunTreeNoSymlinks(outputDir) {
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) {
      throw new Error("run output tree may not contain symbolic links");
    }
    if (stat.isDirectory()) {
      assertOwnerOnlyStat(stat, path.relative(outputDir, current) || "run output directory", true);
      for (const entry of fs.readdirSync(current)) pending.push(path.join(current, entry));
    } else if (stat.isFile()) {
      assertOwnerOnlyStat(stat, path.relative(outputDir, current), false);
    } else {
      throw new Error(`run output tree contains a non-regular entry: ${path.relative(outputDir, current)}`);
    }
  }
}

function validatePersistentState(inputArgs, reviewPayload) {
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir) return null;
  validateRunTreeNoSymlinks(outputDir);
  const finalArtifactsPath = path.join(outputDir, "final_artifacts.json");
  const finalArtifacts = readRunJsonFile(finalArtifactsPath);
  const integrity = validateManifestIntegrity(outputDir, finalArtifacts);
  const runIntake = readRunJsonFile(path.join(outputDir, "run_intake.json"));
  if (
    runIntake.plugin !== reviewPayload.plugin
    || runIntake.workflow !== reviewPayload.workflow
    || runIntake.run_id !== reviewPayload.run_id
    || path.resolve(shortString(runIntake.output_dir)) !== outputDir
  ) {
    throw new Error("stored run_intake.json does not bind this review to the output directory");
  }
  if (
    finalArtifacts.run_id !== reviewPayload.run_id
    || finalArtifacts.plugin !== reviewPayload.plugin
    || finalArtifacts.workflow !== reviewPayload.workflow
  ) {
    throw new Error("final_artifacts identity does not match review_payload");
  }
  for (const requiredPath of [
    "run_intake.json",
    "review_payload.json",
    "ui_decisions.json",
    "review_handoff.md",
  ]) {
    if (!integrity.output_records.has(requiredPath)) {
      throw new Error(`final_artifacts.outputs is missing required binding: ${requiredPath}`);
    }
  }
  const storedReviewPath = path.join(outputDir, "review_payload.json");
  const storedReview = readRunJsonFile(storedReviewPath);
  const reviewCanonicalHash = canonicalSha256(reviewPayload);
  const storedCanonicalHash = canonicalSha256(storedReview);
  if (storedCanonicalHash !== reviewCanonicalHash || canonicalJson(storedReview) !== canonicalJson(reviewPayload)) {
    throw new Error("stored review_payload.json does not match the reviewed payload canonical hash");
  }
  const reviewBytesHash = sha256File(storedReviewPath);
  if (integrity.output_records.get("review_payload.json").sha256 !== reviewBytesHash) {
    throw new Error("stored review_payload.json byte hash does not match the sealed manifest");
  }
  if (isPlainObject(inputArgs.final_artifacts) && canonicalJson(inputArgs.final_artifacts) !== canonicalJson(finalArtifacts)) {
    throw new Error("final_artifacts argument is stale or does not match the sealed run manifest");
  }
  const currentUiDecisions = readRunJsonFile(
    path.join(outputDir, "ui_decisions.json"),
    { required: false },
  );
  return {
    outputDir,
    finalArtifacts,
    currentUiDecisions,
    reviewBytesHash,
    reviewCanonicalHash,
  };
}

function pruneExpiredPersistenceContexts(now = Date.now()) {
  for (const [token, context] of PERSISTENCE_CONTEXTS.entries()) {
    if (context.expiresAt <= now) PERSISTENCE_CONTEXTS.delete(token);
  }
}

function reservePersistenceContextSlot() {
  pruneExpiredPersistenceContexts();
  while (PERSISTENCE_CONTEXTS.size >= MAX_PERSISTENCE_CONTEXTS) {
    const oldest = PERSISTENCE_CONTEXTS.keys().next().value;
    if (oldest == null) break;
    PERSISTENCE_CONTEXTS.delete(oldest);
  }
}

function issuePersistenceToken(inputArgs, reviewPayload) {
  const persistence = validatePersistentState(inputArgs, reviewPayload);
  if (!persistence) return null;
  reservePersistenceContextSlot();
  const token = crypto.randomBytes(32).toString("base64url");
  PERSISTENCE_CONTEXTS.set(token, {
    outputDir: persistence.outputDir,
    runId: reviewPayload.run_id,
    reviewHash: persistence.reviewCanonicalHash,
    expiresAt: Date.now() + PERSISTENCE_CONTEXT_TTL_MS,
  });
  return token;
}

function inputArgsWithPersistentOutput(inputArgs, reviewPayload) {
  const rawToken = inputArgs.persistence_token;
  if (rawToken == null || rawToken === "") return inputArgs;
  if (typeof rawToken !== "string" || !PERSISTENCE_TOKEN_RE.test(rawToken)) {
    throw new Error("persistence_token has an invalid format");
  }
  const directOutputDir = resolveRunOutputDir(inputArgs);
  pruneExpiredPersistenceContexts();
  const context = PERSISTENCE_CONTEXTS.get(rawToken);
  if (!context || context.expiresAt <= Date.now()) {
    // The local loopback workbench intentionally invokes a fresh Node process
    // per tool call and supplies its server-held output directory each time.
    // Its render-process token cannot survive, so the already-supported direct
    // binding remains authoritative when that private path is present.
    if (directOutputDir) return inputArgs;
    throw new Error("persistence_token is unknown or expired; render the review again");
  }
  if (
    context.runId !== reviewPayload.run_id
    || context.reviewHash !== canonicalSha256(reviewPayload)
  ) {
    throw new Error("persistence_token does not match this review run");
  }
  const boundOutputDir = resolveRunOutputDir({
    run_intake: { output_dir: context.outputDir },
  });
  if (directOutputDir && directOutputDir !== boundOutputDir) {
    throw new Error("persistence_token and run_intake.output_dir do not match");
  }
  return {
    ...inputArgs,
    run_intake: {
      ...(isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : {}),
      output_dir: boundOutputDir,
    },
  };
}

function stabilizeReviewer(uiDecisions, currentUiDecisions) {
  const currentReviewer = normalizeReviewerReference(currentUiDecisions?.reviewer, "ui_decisions.reviewer");
  const submittedReviewer = normalizeReviewerReference(uiDecisions.reviewer, "reviewer");
  if (currentReviewer && submittedReviewer && currentReviewer !== submittedReviewer) {
    throw new Error("reviewer reference must remain stable for the run");
  }
  const reviewer = currentReviewer || submittedReviewer;
  if (reviewer) uiDecisions.reviewer = reviewer;
  else delete uiDecisions.reviewer;
  return reviewer;
}

function hardenOwnerOnlyTree(outputDir) {
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) throw new Error("transaction output may not contain symbolic links");
    if (stat.isDirectory()) {
      if (process.platform !== "win32") fs.chmodSync(current, 0o700);
      for (const entry of fs.readdirSync(current)) pending.push(path.join(current, entry));
    } else if (stat.isFile()) {
      if (process.platform !== "win32") fs.chmodSync(current, 0o600);
    } else {
      throw new Error("transaction output may contain only regular files and directories");
    }
  }
}

function withStagedRunDirectory(outputDir, callback) {
  const parent = path.dirname(outputDir);
  const base = path.basename(outputDir);
  const transactionId = crypto.randomUUID();
  const stagedDir = path.join(parent, `.${base}.${transactionId}.tmp`);
  const backupDir = path.join(parent, `.${base}.${transactionId}.bak`);
  let backedUp = false;
  let installed = false;
  try {
    fs.cpSync(outputDir, stagedDir, {
      recursive: true,
      dereference: false,
      errorOnExist: true,
      force: false,
      preserveTimestamps: true,
    });
    hardenOwnerOnlyTree(stagedDir);
    const result = callback(stagedDir);
    hardenOwnerOnlyTree(stagedDir);
    validateRunTreeNoSymlinks(stagedDir);
    const stagedFinal = readRunJsonFile(path.join(stagedDir, "final_artifacts.json"));
    validateManifestIntegrity(stagedDir, stagedFinal);
    fs.renameSync(outputDir, backupDir);
    backedUp = true;
    fs.renameSync(stagedDir, outputDir);
    installed = true;
    fs.rmSync(backupDir, { recursive: true, force: true });
    backedUp = false;
    return result;
  } catch (error) {
    if (installed && fs.existsSync(outputDir)) {
      fs.rmSync(outputDir, { recursive: true, force: true });
      installed = false;
    }
    if (backedUp && fs.existsSync(backupDir)) {
      fs.renameSync(backupDir, outputDir);
      backedUp = false;
    }
    throw error;
  } finally {
    if (fs.existsSync(stagedDir)) fs.rmSync(stagedDir, { recursive: true, force: true });
    if (fs.existsSync(backupDir) && !backedUp) {
      fs.rmSync(backupDir, { recursive: true, force: true });
    }
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
    step_id: `${shortString(appliedDecisions?.workflow) || "client_file_preparation"}_review_apply_${stepIdSuffix || Date.now()}`,
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
  fs.writeFileSync(runIntakePath, `${JSON.stringify(updated, null, 2)}\n`, "utf8");
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
  const requiresFollowup = new Set(["reject", "mark_unclear", "request_more_documents", "skip"]).has(
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
    fs.writeFileSync(absolutePath, effect.edit_value, "utf8");
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

function writeDirectTextArtifactUpdates(outputDir, effects, currentFinalArtifacts) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  const updatedTargets = new Set();
  const declaredPaths = finalArtifactsOutputPaths(currentFinalArtifacts);
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!canDirectlyUpdateTextArtifact(effect.target_artifact)) continue;
    const targetKey = validateRunRelativePath(effect.target_artifact, `effect ${effect.item_id} target_artifact`);
    if (PROTECTED_RUN_FILES.has(targetKey)) {
      throw new Error(`effect ${effect.item_id} may not edit protected run artifact ${targetKey}`);
    }
    if (!declaredPaths.has(targetKey)) {
      throw new Error(`effect ${effect.item_id} target_artifact is not a sealed output: ${targetKey}`);
    }
    if (updatedTargets.has(targetKey)) {
      throw new Error(`multiple whole-artifact edits target ${targetKey}; combine them into one reviewed edit`);
    }
    updatedTargets.add(targetKey);
    const target = resolveSafeRunOutputPath(outputDir, targetKey, { mustExist: true });
    const stat = fs.lstatSync(target.absolutePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(`effect ${effect.item_id} target_artifact is not a regular file`);
    }
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      fs.writeFileSync(backupAbsolutePath, fs.readFileSync(target.absolutePath, "utf8"), "utf8");
    }
    fs.writeFileSync(target.absolutePath, effect.edit_value, "utf8");
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

function writeStructuredArtifactUpdates(outputDir, effects, currentFinalArtifacts) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  const updatedRecords = new Set();
  const declaredPaths = finalArtifactsOutputPaths(currentFinalArtifacts);
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const spec = structuredUpdateSpec(effect);
    if (!spec) continue;
    if (!canUpdateStructuredArtifact(effect.target_artifact)) continue;
    const targetKey = validateRunRelativePath(effect.target_artifact, `effect ${effect.item_id} target_artifact`);
    if (PROTECTED_RUN_FILES.has(targetKey)) {
      throw new Error(`effect ${effect.item_id} may not edit protected run artifact ${targetKey}`);
    }
    if (!declaredPaths.has(targetKey)) {
      throw new Error(`effect ${effect.item_id} target_artifact is not a sealed output: ${targetKey}`);
    }
    const updateKey = [targetKey, spec.recordsKey || "", spec.idField, spec.recordId, spec.targetField].join("\u0000");
    if (updatedRecords.has(updateKey)) {
      throw new Error(`multiple structured edits target the same field in ${targetKey}`);
    }
    updatedRecords.add(updateKey);
    const target = resolveSafeRunOutputPath(outputDir, targetKey, { mustExist: true });
    const stat = fs.lstatSync(target.absolutePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(`effect ${effect.item_id} target_artifact is not a regular file`);
    }
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      fs.copyFileSync(target.absolutePath, backupAbsolutePath);
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
  if (effects.some((effect) => effect.artifact_update === "revision_artifact_written")) {
    return "partial_review_applied";
  }
  if (effects.length < itemCount) return "partial_review_applied";
  return "final_ready";
}

function validateDeclaredTextQa(outputDir, finalArtifacts) {
  if (!outputDir || !isPlainObject(finalArtifacts)) return;
  const outputs = Array.isArray(finalArtifacts.outputs) ? finalArtifacts.outputs : [];
  for (const output of outputs) {
    if (!isPlainObject(output) || !Array.isArray(output.qa_checks)) continue;
    if (!output.qa_checks.includes("nonempty_text") && !output.qa_checks.includes("required_text")) {
      continue;
    }
    const target = resolveSafeRunOutputPath(
      outputDir,
      validateRunRelativePath(output.path, "final_artifacts.outputs[].path"),
      { mustExist: true },
    );
    const stat = fs.lstatSync(target.absolutePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(`artifact QA target is not a regular file: ${target.relativePath}`);
    }
    const text = fs.readFileSync(target.absolutePath, "utf8");
    if (output.qa_checks.includes("nonempty_text") && !text.trim()) {
      throw new Error(`artifact QA failed nonempty_text: ${target.relativePath}`);
    }
    if (output.qa_checks.includes("required_text")) {
      const required = Array.isArray(output.required_text) ? output.required_text : [];
      if (!required.length) {
        throw new Error(`artifact QA metadata has no required_text: ${target.relativePath}`);
      }
      const missing = required.filter(
        (fragment) => typeof fragment !== "string" || !fragment || !text.includes(fragment),
      );
      if (missing.length) {
        throw new Error(`artifact QA failed required_text for ${target.relativePath}`);
      }
    }
  }
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

function reviewHandoffOutputRecord() {
  return {
    path: "review_handoff.md",
    kind: "md",
    status: "written",
    required_text: [
      "Review Handoff",
      "review_payload.json",
      "ui_decisions.json",
      "applied_decisions.json",
      "final_artifacts.json",
    ],
    qa_checks: ["nonempty_text", "required_text"],
  };
}

function ensureReviewHandoffCard(inputArgs, outputDir) {
  const reviewPayload = isPlainObject(inputArgs.review_payload) ? inputArgs.review_payload : {};
  const pluginName = shortString(reviewPayload.plugin);
  if (!REVIEW_HANDOFF_PLUGINS.has(pluginName) || !outputDir) return null;

  const handoffPath = path.join(outputDir, "review_handoff.md");
  fs.mkdirSync(outputDir, { recursive: true });
  if (!fs.existsSync(handoffPath)) {
    const language = shortString(reviewPayload.language) || "en";
    const handoffCopy = {
      it: {
        product: "Preparazione del fascicolo cliente",
        title: "Passaggio alla revisione",
        payload: "Payload di revisione",
        intake: "Dati di esecuzione",
        pending: "Decisioni in attesa",
        applied: "Decisioni applicate",
        artifacts: "Artefatti finali",
        heading: "Revisione in Codex",
        validate: "Validare il payload con",
        render: "Aprire l’area di revisione con",
        save: "Salvare le decisioni con",
        apply: "Applicare le decisioni con",
      },
      en: {
        product: "Client file preparation",
        title: "Review handoff",
        payload: "Review payload",
        intake: "Run intake",
        pending: "Pending decisions",
        applied: "Applied decisions",
        artifacts: "Final artifacts",
        heading: "Review in Codex",
        validate: "Validate the payload with",
        render: "Open the review workbench with",
        save: "Save reviewer actions with",
        apply: "Apply reviewer actions with",
      },
      fr: {
        product: "Préparation du dossier client",
        title: "Passage à la revue",
        payload: "Données de revue",
        intake: "Paramètres d’exécution",
        pending: "Décisions en attente",
        applied: "Décisions appliquées",
        artifacts: "Livrables finaux",
        heading: "Revue dans Codex",
        validate: "Valider les données avec",
        render: "Ouvrir l’espace de revue avec",
        save: "Enregistrer les décisions avec",
        apply: "Appliquer les décisions avec",
      },
      de: {
        product: "Vorbereitung der Mandantenakte",
        title: "Übergabe zur Prüfung",
        payload: "Prüfdaten",
        intake: "Laufdaten",
        pending: "Ausstehende Entscheidungen",
        applied: "Angewandte Entscheidungen",
        artifacts: "Endartefakte",
        heading: "Prüfung in Codex",
        validate: "Prüfdaten validieren mit",
        render: "Prüfansicht öffnen mit",
        save: "Entscheidungen speichern mit",
        apply: "Entscheidungen anwenden mit",
      },
    }[language] || {
      product: "Client file preparation",
      title: "Review handoff",
      payload: "Review payload",
      intake: "Run intake",
      pending: "Pending decisions",
      applied: "Applied decisions",
      artifacts: "Final artifacts",
      heading: "Review in Codex",
      validate: "Validate the payload with",
      render: "Open the review workbench with",
      save: "Save reviewer actions with",
      apply: "Apply reviewer actions with",
    };
    const text = [
      `# ${handoffCopy.product} · ${handoffCopy.title}`,
      "<!-- review-contract: Review Handoff -->",
      "",
      `- ${handoffCopy.payload}: \`review_payload.json\``,
      `- ${handoffCopy.intake}: \`run_intake.json\``,
      `- ${handoffCopy.pending}: \`ui_decisions.json\``,
      `- ${handoffCopy.applied}: \`applied_decisions.json\``,
      `- ${handoffCopy.artifacts}: \`final_artifacts.json\``,
      "",
      `## ${handoffCopy.heading}`,
      `1. ${handoffCopy.validate} \`${TOOL_NAMES.validateReview}\`.`,
      `2. ${handoffCopy.render} \`${TOOL_NAMES.renderReview}\`.`,
      `3. ${handoffCopy.save} \`${TOOL_NAMES.saveDecisions}\`.`,
      `4. ${handoffCopy.apply} \`${TOOL_NAMES.applyDecisions}\`.`,
    ].join("\n");
    fs.writeFileSync(handoffPath, `${text}\n`, "utf8");
  }
  return reviewHandoffOutputRecord();
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
      inputArgs.review_payload?.language || reviewPayload.language,
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

function nextActionsWithReviewApplication(currentNextActions, appliedDecisions, blockers, language) {
  const nextActions = Array.isArray(currentNextActions) ? [...currentNextActions] : [];
  const copy = {
    it: {
      blockers: "Risolvere le decisioni di review bloccanti prima di considerare pronti gli artefatti finali.",
      regenerate: "Rigenerare gli output nativi DOCX/XLSX/PDF prima della consegna finale.",
      ready: "Usare final_artifacts.json come galleria verificata degli artefatti per la consegna.",
      partial: "Completare le decisioni di review mancanti prima della consegna finale.",
    },
    en: {
      blockers: "Resolve blocked review decisions before treating final artifacts as ready.",
      regenerate: "Regenerate native DOCX/XLSX/PDF outputs before final handoff.",
      ready: "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
      partial: "Complete remaining review decisions before final handoff.",
    },
    fr: {
      blockers: "Résoudre les décisions de revue bloquantes avant de considérer les livrables finaux comme prêts.",
      regenerate: "Régénérer les livrables natifs DOCX/XLSX/PDF avant la remise finale.",
      ready: "Utiliser final_artifacts.json comme galerie vérifiée des livrables à remettre.",
      partial: "Terminer les décisions de revue restantes avant la remise finale.",
    },
    de: {
      blockers: "Blockierende Prüfentscheidungen klären, bevor die Endartefakte als fertig gelten.",
      regenerate: "Native DOCX/XLSX/PDF-Ausgaben vor der endgültigen Übergabe neu erzeugen.",
      ready: "final_artifacts.json als geprüfte Artefaktübersicht für die Übergabe verwenden.",
      partial: "Verbleibende Prüfentscheidungen vor der endgültigen Übergabe abschließen.",
    },
  }[language] || {
    blockers: "Resolve blocked review decisions before treating final artifacts as ready.",
    regenerate: "Regenerate native DOCX/XLSX/PDF outputs before final handoff.",
    ready: "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
    partial: "Complete remaining review decisions before final handoff.",
  };
  if (blockers.length) {
    nextActions.push(copy.blockers);
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push(copy.regenerate);
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push(copy.ready);
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push(copy.partial);
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const { uiDecisions } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
  const persistentInputArgs = inputArgsWithPersistentOutput(inputArgs, reviewPayload);
  const persistence = validatePersistentState(persistentInputArgs, reviewPayload);
  const reviewer = persistence
    ? stabilizeReviewer(uiDecisions, persistence.currentUiDecisions)
    : normalizeReviewerReference(uiDecisions.reviewer, "reviewer");
  if (persistence) {
    uiDecisions.review_payload_sha256 = persistence.reviewBytesHash;
    uiDecisions.review_payload_canonical_sha256 = persistence.reviewCanonicalHash;
  }
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const appliedAt = new Date().toISOString();
  function executeApplication(workingDir, workingInputArgs, currentFinalArtifacts) {
    const effects = uiDecisions.decisions.map((decision) =>
      buildApplicationEffect(decision, itemById.get(decision.item_id), appliedAt),
    );
    const workingDecisionPath = workingDir ? path.join(workingDir, "ui_decisions.json") : null;
    const workingAppliedPath = workingDir ? path.join(workingDir, "applied_decisions.json") : null;
    const workingFinalPath = workingDir ? path.join(workingDir, "final_artifacts.json") : null;
    const revisionOutputs = writeRevisionArtifacts(workingDir, effects);
    const textUpdates = writeDirectTextArtifactUpdates(
      workingDir,
      effects,
      currentFinalArtifacts,
    );
    const structuredUpdates = writeStructuredArtifactUpdates(
      workingDir,
      effects,
      currentFinalArtifacts,
    );
    const nativeRegenerationOutputs = [
      ...markNativeRegenerationPending(effects),
      ...markDerivedNativeRegenerationPending(workingDir, effects, currentFinalArtifacts),
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
    if (applicationStatus === "final_ready" && !reviewer) {
      throw new Error(
        "reviewer is required as a stable professional or account reference before phase-one review can become final_ready",
      );
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
        ...(persistence
          ? {
              sha256: persistence.reviewBytesHash,
              canonical_sha256: persistence.reviewCanonicalHash,
            }
          : {}),
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
    if (reviewer) appliedDecisions.reviewer = reviewer;

    let responseFinalArtifacts = finalArtifactsWithApplication(
      workingInputArgs,
      appliedDecisions,
      workingFinalPath,
      revisionOutputs,
      targetOutputs,
      backupOutputs,
      nativeRegenerationOutputs,
    );
    validateDeclaredTextQa(workingDir, responseFinalArtifacts);
    responseFinalArtifacts.review_payload_sha256 = persistence?.reviewBytesHash || null;
    responseFinalArtifacts.review_payload_canonical_sha256 =
      persistence?.reviewCanonicalHash || null;
    if (workingDecisionPath) {
      fs.writeFileSync(workingDecisionPath, `${JSON.stringify(uiDecisions, null, 2)}\n`, "utf8");
    }
    if (workingAppliedPath) {
      fs.writeFileSync(workingAppliedPath, `${JSON.stringify(appliedDecisions, null, 2)}\n`, "utf8");
    }
    if (workingFinalPath) {
      fs.writeFileSync(workingFinalPath, `${JSON.stringify(responseFinalArtifacts, null, 2)}\n`, "utf8");
    }
    const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
      workingDir,
      workingAppliedPath,
      workingFinalPath,
    );
    const responseAppliedDecisions =
      (isPlainObject(workflowSpecificResult?.applied_decisions)
        ? workflowSpecificResult.applied_decisions
        : null)
      || readJsonFileIfPresent(workingAppliedPath)
      || appliedDecisions;
    responseFinalArtifacts =
      (isPlainObject(workflowSpecificResult?.final_artifacts)
        ? workflowSpecificResult.final_artifacts
        : null)
      || readJsonFileIfPresent(workingFinalPath)
      || responseFinalArtifacts;
    const runIntakePath = appendReviewApplicationExecutionTrace(
      workingInputArgs,
      workingDir,
      responseAppliedDecisions,
      responseFinalArtifacts,
    );
    if (workingDir && workingFinalPath) {
      responseFinalArtifacts = refreshFinalArtifactsIntegrity(workingDir, responseFinalArtifacts);
      fs.writeFileSync(
        workingFinalPath,
        `${JSON.stringify(responseFinalArtifacts, null, 2)}\n`,
        "utf8",
      );
    }
    return {
      responseAppliedDecisions,
      responseFinalArtifacts,
      runIntakePath,
      revisionOutputs,
      targetOutputs,
      structuredUpdatePaths,
      applicationStatus,
    };
  }

  let result;
  if (persistence) {
    result = withStagedRunDirectory(persistence.outputDir, (stagedDir) => {
      const stagedInputArgs = {
        ...persistentInputArgs,
        run_intake: { ...persistentInputArgs.run_intake, output_dir: stagedDir },
        final_artifacts: readJsonFileIfPresent(path.join(stagedDir, "final_artifacts.json")),
      };
      return executeApplication(
        stagedDir,
        stagedInputArgs,
        stagedInputArgs.final_artifacts,
      );
    });
  } else {
    result = executeApplication(
      null,
      inputArgs,
      isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : {},
    );
  }
  const {
    responseAppliedDecisions,
    responseFinalArtifacts,
    revisionOutputs,
    targetOutputs,
    structuredUpdatePaths,
    applicationStatus,
  } = result;
  const outputDir = persistence?.outputDir || null;
  const persisted = Boolean(outputDir);
  return {
    ok: true,
    validation_type: "client_file_preparation_application",
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
    ui_decisions_path: persisted ? "ui_decisions.json" : null,
    applied_decisions_path: persisted ? "applied_decisions.json" : null,
    final_artifacts_path: persisted ? "final_artifacts.json" : null,
    run_intake_path: persisted ? "run_intake.json" : null,
    message: persisted
      ? `Applied ${responseAppliedDecisions.decision_count} New Client · File Preparation decisions.`
      : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: sanitizedFinalArtifactsForReview(responseFinalArtifacts),
  };
}

function applyWorkflowSpecificReviewApplication(
  _outputDir,
  _appliedOutputPath,
  _finalArtifactsPath,
) {
  return null;
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const payload = validateReviewPayload(args);
    return {
      ok: true,
      validation_type: "client_file_preparation_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: "New Client · File Preparation review payload is valid. It is safe to call render_client_file_preparation_review once.",
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.renderReview) {
    return reviewPayloadForWidget(args);
  }
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(`unknown New Client · File Preparation widget tool: ${name}`);
}

function toolResult(payload, toolName) {
  const result = {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
  if (toolName === TOOL_NAMES.renderReview) result._meta = toolUiMeta(WIDGET_URI, toolName);
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
      return rpcResponse(messageId, {
        protocolVersion: params.protocolVersion || "2024-11-05",
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: {
          tools: {},
          resources: {},
          prompts: {},
        },
        instructions:
          "Use validate_client_file_preparation_review before render_client_file_preparation_review. Prefer the MCP widget for New Client · File Preparation review handoff; use save_client_file_preparation_decisions to persist reviewer actions to ui_decisions.json and apply_client_file_preparation_decisions to write applied_decisions.json plus final_artifacts.json status when decisions are collected; fall back to Markdown/static review only when MCP is unavailable.",
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") return rpcResponse(messageId, { tools: toolDefinitions() });
    if (method === "tools/call") {
      const { name, arguments: args } = params;
      if (typeof name !== "string") return rpcError(messageId, -32602, "tools/call requires a tool name");
      if (!isPlainObject(args)) return rpcError(messageId, -32602, "tools/call arguments must be an object");
      try {
        return rpcResponse(messageId, toolResult(callTool(name, args), name));
      } catch (error) {
        return rpcResponse(messageId, toolError(error instanceof Error ? error.message : String(error)));
      }
    }
    if (method === "resources/list") return rpcResponse(messageId, { resources: resources() });
    if (method === "resources/read") {
      const { uri } = params;
      if (typeof uri !== "string") return rpcError(messageId, -32602, "resources/read requires a resource uri");
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
    return rpcError(messageId, -32601, `method not found: ${method}`);
  } catch (error) {
    return rpcError(messageId, -32000, error instanceof Error ? error.message : String(error));
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

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

const SERVER_NAME = "concordato-plan-review-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/concordato-plan-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const TOOL_NAMES = {
  validateReview: "validate_concordato_plan_review",
  renderReview: "render_concordato_plan_review",
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
  "candidate_amount_match",
  "unmatched_plan_amount",
  "extraction_error",
  "review_artifact",
  "codex_review_memo",
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
    meta["openai/toolInvocation/invoking"] = "Rendering concordato plan review";
    meta["openai/toolInvocation/invoked"] = "Rendered concordato plan review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Concordato Plan Review surface for source roles, candidate amount matches, unmatched plan numbers, extraction errors, and review artifacts.",
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
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: { type: "string", description: "Optional reviewer name or role." },
    },
    ["review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate Concordato Plan Review payload",
      description:
        "Validate the Concordato Plan Review payload before rendering. Call this first, then render_concordato_plan_review.",
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
      title: "Render Concordato Plan Review",
      description:
        "Render a Concordato Plan Review payload as an MCP HTML widget for source, amount, exception, and artifact review.",
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
      title: "Save Concordato Plan Review review decisions",
      description:
        "Validate Concordato Plan Review review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
      title: "Apply Concordato Plan Review review decisions",
      description:
        "Validate Concordato Plan Review review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
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
      name: "concordato_plan_review_widget",
      title: "Concordato Plan Review widget",
      description:
        "Renders Concordato Plan Review payloads with searchable source, amount, exception, and artifact rows.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown Concordato Plan Review widget resource: ${uri}`);
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
    widget_type: "concordato_plan_review",
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
    throw new Error(`concordato plan review widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
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
  let persisted = false;
  if (decisionOutputPath) {
    fs.mkdirSync(path.dirname(decisionOutputPath), { recursive: true });
    fs.writeFileSync(decisionOutputPath, `${JSON.stringify(uiDecisions, null, 2)}\n`, "utf8");
    persisted = true;
  }
  return {
    ok: true,
    validation_type: "concordato_plan_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? decisionOutputPath : null,
    message: persisted
      ? `Saved ${uiDecisions.decision_count} Concordato Plan Review decisions.`
      : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  return outputDir ? path.resolve(outputDir) : null;
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
  if (effects.length < itemCount) return "partial_review_applied";
  return "final_ready";
}

const REVIEW_HANDOFF_PLUGINS = new Set([
  "check-entries",
  "client-intake",
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
    const displayName = PLUGIN_MANIFEST.name || pluginName || "Review";
    const text = [
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
    next_actions: nextActionsWithReviewApplication(current.next_actions, appliedDecisions, blockers),
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

function nextActionsWithReviewApplication(currentNextActions, appliedDecisions, blockers) {
  const nextActions = Array.isArray(currentNextActions) ? [...currentNextActions] : [];
  if (blockers.length) {
    nextActions.push("Resolve blocked review decisions before treating final artifacts as ready.");
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push("Regenerate native DOCX/XLSX/PDF outputs before final handoff.");
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push("Use final_artifacts.json as the reviewed artifact gallery for handoff.");
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push("Complete remaining review decisions before final handoff.");
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
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
    fs.writeFileSync(decisionOutputPath, `${JSON.stringify(uiDecisions, null, 2)}\n`, "utf8");
  }
  if (appliedOutputPath) {
    fs.mkdirSync(path.dirname(appliedOutputPath), { recursive: true });
    fs.writeFileSync(appliedOutputPath, `${JSON.stringify(appliedDecisions, null, 2)}\n`, "utf8");
    persisted = true;
  }
  if (finalArtifactsPath) {
    fs.mkdirSync(path.dirname(finalArtifactsPath), { recursive: true });
    fs.writeFileSync(finalArtifactsPath, `${JSON.stringify(finalArtifacts, null, 2)}\n`, "utf8");
  }
  const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
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
  return {
    ok: true,
    validation_type: "concordato_plan_application",
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
    message: persisted
      ? `Applied ${responseAppliedDecisions.decision_count} Concordato Plan Review decisions.`
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

function applyWorkflowSpecificReviewApplication(outputDir, appliedOutputPath, finalArtifactsPath) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.native_regeneration_count) return null;
  if (!hasWorkflowNativeRegenerationTarget(currentApplied)) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const completed = spawnSync(
    pythonExecutable(),
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8" },
  );
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    throw new Error(
      completed.stderr ||
        completed.stdout ||
        "Concordato Plan Review native regeneration failed.",
    );
  }
  const output = completed.stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  if (!output) return null;
  const parsed = JSON.parse(output);
  return isPlainObject(parsed) ? parsed : null;
}

function hasWorkflowNativeRegenerationTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (!effect.requires_native_regeneration) return false;
    return nativeRegenerationPathsForEffect(effect).includes("concordato_review_summary.docx");
  });
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const payload = validateReviewPayload(args);
    return {
      ok: true,
      validation_type: "concordato_plan_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: "Concordato Plan Review payload is valid. It is safe to call render_concordato_plan_review once.",
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.renderReview) {
    return validateReviewPayload(args);
  }
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(`unknown Concordato Plan Review widget tool: ${name}`);
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
          "Use validate_concordato_plan_review before render_concordato_plan_review. Prefer the MCP widget for Concordato Plan Review review handoff; use save_concordato_plan_decisions to persist reviewer actions to ui_decisions.json and apply_concordato_plan_decisions to write applied_decisions.json plus final_artifacts.json status when decisions are collected; fall back to Markdown/static review only when MCP is unavailable.",
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

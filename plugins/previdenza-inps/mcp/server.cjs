"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const readline = require("node:readline");

const SERVER_NAME = "previdenza-inps-review";
const SERVER_VERSION = "0.2.0";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const WIDGET_URI = "ui://widget/previdenza-inps-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 1_500_000;
const MAX_TEXT_LENGTH = 10_000;
const READY_STATUS = "ready_for_professional_review";
const REVIEW_STATUSES = new Set([READY_STATUS, "validation_fail"]);
const REVIEW_TYPES = new Set(["professional_case_review"]);
const SAFE_CONNECTORS = new Set(["inps_browser_read_only"]);
const ACQUISITION_CHANNELS = new Set([
  "inps_conditional_browser_capture",
  "inps_official_user_export",
]);
const ACQUISITION_CONNECTORS = new Set(["inps_browser_read_only"]);
const ACQUISITION_OCR_FIELDS = [
  "enabled",
  "engine",
  "language",
  "attempt_location",
  "attempted_page_count",
  "successful_page_count",
  "case_content_network_transfer",
  "model_download_allowed",
  "model_download_approval_id",
  "model_network_used",
  "visual_confirmation_required",
];
const LOWERCASE_SHA256 = /^[0-9a-f]{64}$/;
const SAFE_ITEM_STATUSES = new Set(["needs_review"]);
const SAFE_REVIEW_DATA_ENUMS = {
  review_status: new Set(["confirmed", "disputed", "pending"]),
  claim_type: new Set(["calculation_basis", "case_application", "rule"]),
  verdict: new Set(["contradicted", "not_supported", "partially_supported", "supported", "uncertain"]),
  professional_review_status: new Set(["pending"]),
  temporal_role: new Set(["later_interpretive_authority", "period_rule", "research_cutoff_authority"]),
  status: new Set(["blocked", "calculated", "passed", "pending", "validation_fail"]),
};
const SAFE_UI_STATUSES = new Set(["partial_review", "pending", "reviewed"]);
const SAFE_DECISION_STATUSES = new Set([
  "accepted",
  "edited",
  "needs_evidence",
  "rejected",
  "skipped",
]);
const SAFE_OUTPUT_KINDS = new Set(["csv", "docx", "json", "md"]);
const SAFE_OUTPUT_STATUSES = new Set([
  "blocked",
  "missing",
  "pending_review",
  "revision_required_not_applied",
  "written",
  "written_reviewed",
]);
const SAFE_FINAL_STATUSES = new Set([
  "blocked",
  "partial_review_applied",
  "pending_review",
  READY_STATUS,
  "validation_fail",
]);
const SAFE_REVIEW_DATA = {
  fact: new Set(["fact_id", "review_status", "evidence_count"]),
  finding: new Set(["claim_id", "claim_type", "verdict", "source_count", "professional_review_status"]),
  calculation: new Set(["recipe_id", "status"]),
  missing_evidence: new Set(["request_id"]),
  authority: new Set(["source_id", "temporal_role"]),
  audit_check: new Set(["status"]),
  artifact: new Set(["path"]),
};
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ITALIAN_TAX_CODE = /(?:^|[^A-Za-z0-9])[A-Za-z]{6}[0-9]{2}[A-EHLMPRSTa-ehlmprst][0-9]{2}[A-Za-z][0-9]{3}[A-Za-z](?=$|[^A-Za-z0-9])/;
const EMAIL_ADDRESS = /(?:^|[^\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])/;
const SAFE_TRACE_COMMANDS = new Set([
  "python scripts/capture_portal_snapshot.py",
  "python scripts/package_case.py",
  "python scripts/register_portal_export.py",
  "apply_previdenza_inps_decisions",
]);
const SAFE_TRACE_STEP_IDS = new Set([
  "previdenza_inps_portal_capture",
  "previdenza_inps_portal_export_registration",
  "previdenza_inps_package",
  "previdenza_inps_review_application",
]);
const SAFE_TRACE_KINDS = new Set([
  "read_only_browser_capture",
  "deterministic_export_registration",
  "deterministic_packaging",
  "professional_review_application",
]);
const SAFE_TRACE_STATUSES = new Set([
  "blocked",
  "partial_review_applied",
  "passed",
  "pending_review",
  "ready_for_professional_review",
]);
const SAFE_TRACE_LOCATIONS = new Set([
  "external_connector",
  "local_codex_workspace",
  "local_mcp_server",
]);
const SAFE_TRACE_INPUT_NAMES = new Set([
  "approved_open_browser_tab",
  "user_downloaded_official_portal_exports",
  "validated_case_records",
  "claims_review",
  "calculation_results",
  "review_payload",
  "ui_decisions",
]);
const SAFE_TRACE_OUTPUT_NAMES = new Set([
  "applied_decisions.json",
  "blocked_case_note.md",
  "calculation_audit.json",
  "calculation_results.csv",
  "calculation_results.json",
  "claims_review_normalized.json",
  "document_requests.md",
  "final_artifacts.json",
  "review_handoff.md",
  "review_payload.json",
  "revision_requirements.json",
  "studio_memo.docx",
  "studio_memo.md",
  "portal_full_page.png",
  "portal_capture_manifest.json",
  "portal_visible_text.txt",
  "portal_export_manifest",
  "registered_portal_exports",
  "ui_decisions.json",
  "validation_audit.json",
]);
const PERSISTENCE_ROOTS = new Map();
const TOOL_NAMES = {
  validate: "validate_previdenza_inps_review",
  render: "render_previdenza_inps_review",
  save: "save_previdenza_inps_decisions",
  apply: "apply_previdenza_inps_decisions",
};
const ITEM_TYPES = new Set([
  "fact",
  "finding",
  "calculation",
  "missing_evidence",
  "authority",
  "audit_check",
  "artifact",
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

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!isObject(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
}

function canonicalJson(value) {
  return JSON.stringify(canonicalValue(value));
}

function canonicalSha256(value) {
  return crypto.createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function fileSha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function safeIsoDateTime(value) {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function safeIdentifier(value, field) {
  const text = requireText(value, field);
  if (!SAFE_ID.test(text) || ITALIAN_TAX_CODE.test(text) || EMAIL_ADDRESS.test(text) || text.includes("://")) {
    throw new Error(`${field} must be an opaque identifier without personal data`);
  }
  return text;
}

function assertPrivacySafeText(value, field) {
  const text = optionalText(value, field);
  if (!text) return text;
  if (ITALIAN_TAX_CODE.test(text) || EMAIL_ADDRESS.test(text)) {
    throw new Error(`${field} must omit raw identity, tax codes, and email`);
  }
  for (const match of text.matchAll(/https?:\/\/[^\s<>"']+/gi)) {
    let url;
    try {
      url = new URL(match[0].replace(/[.,);\]]+$/, ""));
    } catch {
      throw new Error(`${field} contains an invalid URL`);
    }
    const privateHost =
      url.hostname === "localhost" ||
      url.hostname.endsWith(".local") ||
      /^(?:127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.port && url.port !== "443") ||
      privateHost
    ) {
      throw new Error(`${field} must omit private, credentialed, or tokenized URLs`);
    }
  }
  return text;
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

const SOURCE_BOUNDARY = fs.realpathSync(findGitRoot(PLUGIN_ROOT) || PLUGIN_ROOT);

function isWithin(parent, child) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

function safeExistingOutputDir(raw) {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error("run_intake.output_dir must be a non-empty string for persistence");
  }
  const requested = path.resolve(raw.trim());
  if (!fs.existsSync(requested) || !fs.statSync(requested).isDirectory()) {
    throw new Error("run_intake.output_dir must identify an existing directory");
  }
  const resolved = fs.realpathSync(requested);
  if (isWithin(SOURCE_BOUNDARY, resolved) || findGitRoot(resolved)) {
    throw new Error("run_intake.output_dir must be outside the plugin Git workspace");
  }
  if ((fs.statSync(resolved).mode & 0o077) !== 0) {
    throw new Error("run_intake.output_dir must have owner-only permissions (0700)");
  }
  return resolved;
}

function readRunIntake(outputDir) {
  const runIntakePath = path.join(outputDir, "run_intake.json");
  if (!fs.existsSync(runIntakePath)) {
    throw new Error("run_intake.output_dir must contain run_intake.json");
  }
  const stat = fs.lstatSync(runIntakePath);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("run_intake.json must be a regular file inside run_intake.output_dir");
  }
  const value = JSON.parse(fs.readFileSync(runIntakePath, "utf8"));
  if (!isObject(value)) throw new Error("run_intake.json must contain a JSON object");
  return value;
}

function assertRunIdentity(runIntake, review, fieldPrefix = "run_intake") {
  if (runIntake.run_id !== review.run_id) {
    throw new Error(`${fieldPrefix}.run_id must match review_payload.run_id`);
  }
  if (runIntake.plugin != null && runIntake.plugin !== "previdenza-inps") {
    throw new Error(`${fieldPrefix}.plugin must be "previdenza-inps"`);
  }
  if (runIntake.workflow != null && runIntake.workflow !== review.workflow) {
    throw new Error(`${fieldPrefix}.workflow must match review_payload.workflow`);
  }
}

function valueOrNull(value) {
  return value === undefined ? null : value;
}

function acquisitionStringSet(value, field, allowed) {
  if (value == null) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must be an array of strings`);
  }
  if (value.length !== new Set(value).size) {
    throw new Error(`${field} must not contain duplicates`);
  }
  if (value.some((item) => !allowed.has(item))) {
    throw new Error(`${field} contains an unsupported value`);
  }
  return [...value].sort();
}

function acquisitionBoolean(value, field) {
  if (typeof value !== "boolean") throw new Error(`${field} must be boolean`);
  return value;
}

function acquisitionReceipt(posture, name, channel, channels) {
  const value = posture[name];
  if (value == null) {
    if (channels.includes(channel)) throw new Error(`data_posture.${name} is required`);
    return null;
  }
  if (!isObject(value) || Object.keys(value).length === 0) {
    throw new Error(`data_posture.${name} must be an object`);
  }
  if (!channels.includes(channel)) {
    throw new Error(`data_posture.${name} requires acquisition channel ${channel}`);
  }
  if (!LOWERCASE_SHA256.test(value.manifest_sha256 || "")) {
    throw new Error(`data_posture.${name}.manifest_sha256 must be lowercase SHA-256`);
  }
  return value;
}

function acquisitionProjection(runIntake) {
  if (runIntake.plugin !== "previdenza-inps") {
    throw new Error('run_intake.plugin must be "previdenza-inps"');
  }
  if (runIntake.workflow !== "previdenza-inps") {
    throw new Error('run_intake.workflow must be "previdenza-inps"');
  }
  if (runIntake.status !== "inventory_complete") {
    throw new Error("run_intake.status must be inventory_complete");
  }
  if (typeof runIntake.run_id !== "string" || runIntake.run_id.trim() === "") {
    throw new Error("run_intake.run_id must be non-empty");
  }
  if (!isObject(runIntake.data_posture)) {
    throw new Error("run_intake.data_posture must be an object");
  }
  const posture = runIntake.data_posture;
  const channels = acquisitionStringSet(
    posture.acquisition_channels_used,
    "data_posture.acquisition_channels_used",
    ACQUISITION_CHANNELS,
  );
  const connectors = acquisitionStringSet(
    posture.external_connectors_used,
    "data_posture.external_connectors_used",
    ACQUISITION_CONNECTORS,
  );
  const captureReceipt = acquisitionReceipt(
    posture,
    "portal_capture_receipt",
    "inps_conditional_browser_capture",
    channels,
  );
  const exportReceipt = acquisitionReceipt(
    posture,
    "portal_export_receipt",
    "inps_official_user_export",
    channels,
  );
  if (captureReceipt !== null && canonicalJson(connectors) !== canonicalJson(["inps_browser_read_only"])) {
    throw new Error("portal capture requires the approved inps_browser_read_only connector");
  }
  if (captureReceipt === null && connectors.length > 0) {
    throw new Error("external connector posture requires a portal capture receipt");
  }
  const localOnly = acquisitionBoolean(posture.local_only, "data_posture.local_only");
  const networkCalls = acquisitionBoolean(
    posture.network_calls_by_scripts,
    "data_posture.network_calls_by_scripts",
  );
  if (!isObject(posture.ocr)) throw new Error("data_posture.ocr must be an object");
  const ocr = Object.fromEntries(
    ACQUISITION_OCR_FIELDS.map((name) => [name, valueOrNull(posture.ocr[name])]),
  );
  if (connectors.length > 0 && (localOnly || !networkCalls)) {
    throw new Error("external connector use must remain non-local and network-recorded");
  }
  if (ocr.model_network_used === true && (localOnly || !networkCalls)) {
    throw new Error("OCR model network use must remain non-local and network-recorded");
  }
  const approval = valueOrNull(posture.external_execution_approval);
  if (captureReceipt !== null && (!isObject(approval) || approval.approved !== true)) {
    throw new Error("portal capture requires recorded external execution approval");
  }
  if (captureReceipt === null && approval !== null) {
    throw new Error("external execution approval requires a portal capture receipt");
  }
  return {
    schema_version: valueOrNull(runIntake.schema_version),
    plugin: "previdenza-inps",
    workflow: "previdenza-inps",
    run_id: runIntake.run_id.trim(),
    status: "inventory_complete",
    created_at: valueOrNull(runIntake.created_at),
    completed_at: valueOrNull(runIntake.completed_at),
    reference_date: valueOrNull(runIntake.reference_date),
    data_posture: {
      local_only: localOnly,
      network_calls_by_scripts: networkCalls,
      network_access_allowed_for_model_weights: valueOrNull(
        posture.network_access_allowed_for_model_weights,
      ),
      acquisition_channels_used: channels,
      external_connectors_used: connectors,
      external_execution_approval: approval,
      portal_capture_receipt: captureReceipt,
      portal_export_receipt: exportReceipt,
      ocr,
    },
  };
}

function validateAcquisitionBinding(outputDir, review, runIntake, expected) {
  if (!isObject(expected)) {
    throw new Error("ready final_artifacts.json must contain acquisition_binding");
  }
  const inventoryPath = path.join(outputDir, "file_inventory.json");
  if (!fs.existsSync(inventoryPath)) {
    throw new Error("acquisition binding requires file_inventory.json");
  }
  const inventoryStat = fs.lstatSync(inventoryPath);
  if (!inventoryStat.isFile() || inventoryStat.isSymbolicLink()) {
    throw new Error("file_inventory.json must be a regular file inside run_intake.output_dir");
  }
  const projection = acquisitionProjection(runIntake);
  if (projection.run_id !== review.run_id || expected.run_id !== review.run_id) {
    throw new Error("acquisition binding run_id does not match review_payload.run_id");
  }
  const receipts = [];
  for (const name of ["portal_capture_receipt", "portal_export_receipt"]) {
    const receipt = projection.data_posture[name];
    if (receipt !== null) receipts.push({ kind: name, sha256: canonicalSha256(receipt) });
  }
  const core = {
    schema_version: "1.0",
    run_id: projection.run_id,
    file_inventory_sha256: fileSha256(inventoryPath),
    run_intake_acquisition_sha256: canonicalSha256(projection),
    portal_receipts: receipts,
  };
  const current = { ...core, binding_sha256: canonicalSha256(core) };
  for (const field of [
    "run_id",
    "file_inventory_sha256",
    "run_intake_acquisition_sha256",
    "portal_receipts",
    "binding_sha256",
  ]) {
    if (canonicalJson(expected[field]) !== canonicalJson(current[field])) {
      throw new Error(`final_artifacts.acquisition_binding.${field} does not match current acquisition provenance`);
    }
  }
}

function validateStoredRunIntake(outputDir, review) {
  const stored = readRunIntake(outputDir);
  assertRunIdentity(stored, review, "stored run_intake");
  const storedOutputDir = safeExistingOutputDir(stored.output_dir);
  if (storedOutputDir !== outputDir) {
    throw new Error("stored run_intake.output_dir does not match the persistence directory");
  }
  return stored;
}

function validateStoredReview(outputDir, review, runIntake, expectedHash = null) {
  const reviewPath = path.join(outputDir, "review_payload.json");
  if (!fs.existsSync(reviewPath)) throw new Error("persistence requires stored review_payload.json");
  const stat = fs.lstatSync(reviewPath);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("review_payload.json must be a regular file inside run_intake.output_dir");
  }
  const stored = JSON.parse(fs.readFileSync(reviewPath, "utf8"));
  if (!isObject(stored)) throw new Error("review_payload.json must contain a JSON object");
  if (canonicalJson(stored) !== canonicalJson(review)) {
    throw new Error("review_payload must exactly match stored review_payload.json");
  }
  const reviewSha256 = fileSha256(reviewPath);
  if (expectedHash && reviewSha256 !== expectedHash) {
    throw new Error("stored review_payload.json changed after persistence registration");
  }
  const finalPath = path.join(outputDir, "final_artifacts.json");
  const readyReview = review.status === READY_STATUS;
  if (!fs.existsSync(finalPath) && readyReview) {
    throw new Error("ready stored review_payload.json requires final_artifacts.json");
  }
  if (fs.existsSync(finalPath)) {
    const finalStat = fs.lstatSync(finalPath);
    if (!finalStat.isFile() || finalStat.isSymbolicLink()) {
      throw new Error("final_artifacts.json must be a regular file inside run_intake.output_dir");
    }
    const finalArtifacts = JSON.parse(fs.readFileSync(finalPath, "utf8"));
    if (!isObject(finalArtifacts)) throw new Error("final_artifacts.json must contain a JSON object");
    if (finalArtifacts.plugin !== "previdenza-inps") {
      throw new Error('stored final_artifacts.plugin must be "previdenza-inps"');
    }
    if (finalArtifacts.workflow !== review.workflow) {
      throw new Error("stored final_artifacts.workflow must match review_payload.workflow");
    }
    if (finalArtifacts.run_id !== review.run_id) {
      throw new Error("stored final_artifacts.run_id must match review_payload.run_id");
    }
    const readyFinal =
      finalArtifacts.status === READY_STATUS || finalArtifacts.package_status === READY_STATUS;
    if (readyReview && !readyFinal) {
      throw new Error("ready stored review_payload.json requires a ready final_artifacts.json");
    }
    if (
      readyFinal &&
      typeof finalArtifacts.review_payload_sha256 !== "string"
    ) {
      throw new Error("ready final_artifacts.json must bind review_payload_sha256");
    }
    if (
      finalArtifacts.review_payload_sha256 != null &&
      finalArtifacts.review_payload_sha256 !== reviewSha256
    ) {
      throw new Error("final_artifacts.review_payload_sha256 does not match stored review payload");
    }
    if (readyFinal || finalArtifacts.acquisition_binding != null) {
      validateAcquisitionBinding(outputDir, review, runIntake, finalArtifacts.acquisition_binding);
    }
  }
  return { stored, reviewSha256 };
}

function resolvePersistence(input, review) {
  const runIntake = isObject(input.run_intake) ? input.run_intake : null;
  if (!runIntake) return null;
  assertRunIdentity(runIntake, review);

  const token = typeof runIntake.persistence_token === "string" ? runIntake.persistence_token.trim() : "";
  if (token) {
    const registered = PERSISTENCE_ROOTS.get(token);
    if (!registered) throw new Error("run_intake.persistence_token is unknown or expired");
    if (
      registered.run_id !== review.run_id ||
      registered.workflow !== review.workflow ||
      registered.plugin !== "previdenza-inps"
    ) {
      throw new Error("run_intake.persistence_token does not match this review run");
    }
    const outputDir = safeExistingOutputDir(registered.outputDir);
    const storedRunIntake = validateStoredRunIntake(outputDir, review);
    const storedReview = validateStoredReview(
      outputDir,
      review,
      storedRunIntake,
      registered.reviewSha256,
    );
    return { token, outputDir, storedRunIntake, reviewSha256: storedReview.reviewSha256 };
  }

  if (runIntake.output_dir == null || runIntake.output_dir === "") return null;
  const outputDir = safeExistingOutputDir(runIntake.output_dir);
  const storedRunIntake = validateStoredRunIntake(outputDir, review);
  const storedReview = validateStoredReview(outputDir, review, storedRunIntake);
  const registeredToken = crypto.randomUUID();
  PERSISTENCE_ROOTS.set(registeredToken, {
    outputDir,
    run_id: review.run_id,
    workflow: review.workflow,
    plugin: "previdenza-inps",
    reviewSha256: storedReview.reviewSha256,
  });
  return {
    token: registeredToken,
    outputDir,
    storedRunIntake,
    reviewSha256: storedReview.reviewSha256,
  };
}

function publicRunIntake(runIntake, persistence) {
  if (!isObject(runIntake)) return null;
  const posture = isObject(runIntake.data_posture) ? runIntake.data_posture : {};
  const trace = Array.isArray(runIntake.execution_trace) ? runIntake.execution_trace : [];
  const decisions = isObject(runIntake.material_decisions) ? runIntake.material_decisions : {};
  const knownDecisionNames = [
    "professional_question_confirmed",
    "framework_confirmed",
    "period_scope_confirmed",
    "ambiguous_terms_resolved",
  ];
  return {
    schema_version: "1.0",
    plugin: "previdenza-inps",
    workflow: runIntake.workflow === "previdenza-inps" ? "previdenza-inps" : null,
    run_id: SAFE_ID.test(runIntake.run_id || "") ? runIntake.run_id : null,
    created_at: safeIsoDateTime(runIntake.created_at) ? runIntake.created_at : null,
    working_language: ["it", "en", "fr", "de"].includes(runIntake.working_language)
      ? runIntake.working_language
      : null,
    reference_date:
      typeof runIntake.reference_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(runIntake.reference_date)
        ? runIntake.reference_date
        : null,
    material_decisions: Object.fromEntries(
      knownDecisionNames.map((name) => [name, decisions[name] === true]),
    ),
    data_posture: {
      local_only: posture.local_only === true,
      network_calls_by_scripts: posture.network_calls_by_scripts === true,
      external_connectors_used: Array.isArray(posture.external_connectors_used)
        ? [...new Set(posture.external_connectors_used.filter((name) => SAFE_CONNECTORS.has(name)))]
        : [],
      external_execution_approval: {
        approved:
          isObject(posture.external_execution_approval) &&
          posture.external_execution_approval.approved === true,
      },
    },
    execution_trace: trace.slice(0, 100).map((entry) => ({
      step_id: safeTraceField(entry?.step_id, SAFE_TRACE_STEP_IDS),
      kind: safeTraceField(entry?.kind, SAFE_TRACE_KINDS),
      status: safeTraceField(entry?.status, SAFE_TRACE_STATUSES),
      execution_location: safeTraceField(entry?.execution_location, SAFE_TRACE_LOCATIONS),
      command: safeTraceField(entry?.command, SAFE_TRACE_COMMANDS),
      inputs: safeTraceNames(entry?.inputs, SAFE_TRACE_INPUT_NAMES),
      outputs: safeTraceNames(entry?.outputs, SAFE_TRACE_OUTPUT_NAMES),
    })),
    ...(persistence ? { persistence_token: persistence.token } : {}),
  };
}

function safeTraceField(value, allowedValues) {
  return typeof value === "string" && allowedValues.has(value) ? value : null;
}

function safeTraceNames(value, allowedNames) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.slice(0, 100).filter((name) => typeof name === "string" && allowedNames.has(name)))];
}

function objectSchema(properties, required = []) {
  return { type: "object", properties, required, additionalProperties: true };
}

function reviewSchema() {
  return objectSchema(
    {
      schema_version: { type: "string" },
      plugin: { type: "string", const: "previdenza-inps" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      review_type: { type: "string" },
      items: { type: "array", items: { type: "object" }, maxItems: MAX_ITEMS },
      item_count: { type: "number" },
      status: { type: "string" },
    },
    ["schema_version", "plugin", "workflow", "run_id", "items", "item_count"],
  );
}

function toolUiMeta() {
  return {
    ui: { resourceUri: WIDGET_URI, visibility: ["model"] },
    "ui/resourceUri": WIDGET_URI,
    "openai/outputTemplate": WIDGET_URI,
    "openai/widgetAccessible": true,
    "openai/toolInvocation/invoking": "Rendering previdenza INPS review",
    "openai/toolInvocation/invoked": "Rendered previdenza INPS review",
  };
}

function widgetMeta() {
  return {
    ui: { resourceUri: WIDGET_URI },
    "openai/widgetDescription":
      "Evidence-first review of previdenza INPS facts, findings, calculations, authorities, gaps, checks, and artifacts.",
    "openai/widgetPrefersBorder": false,
    "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
    "openai/widgetDomain": "https://chatgpt.com",
  };
}

function toolDefinitions() {
  const reviewInput = objectSchema(
    {
      run_intake: { type: "object", description: "Optional run_intake.json object." },
      review_payload: reviewSchema(),
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      final_artifacts: { type: "object", description: "Optional final_artifacts.json object." },
    },
    ["review_payload"],
  );
  const decision = objectSchema(
    {
      item_id: { type: "string" },
      action: { type: "string", enum: [...ALLOWED_ACTIONS] },
      reviewer_note: { type: "string" },
      edit_value: { type: "string" },
      requested_documents: { type: "array", items: { type: "string" } },
    },
    ["item_id", "action"],
  );
  const decisionInput = objectSchema(
    {
      run_intake: {
        type: "object",
        description: "Optional run_intake.json object; output_dir is the only persistence root.",
      },
      review_payload: reviewSchema(),
      ui_decisions: { type: "object" },
      final_artifacts: { type: "object" },
      decisions: { type: "array", items: decision },
      decision_source: { type: "string" },
      reviewer: { type: "string" },
    },
    ["review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validate,
      title: "Validate previdenza INPS review",
      description:
        "Validate a bounded previdenza INPS review payload before rendering it. This tool does not write files.",
      inputSchema: reviewInput,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    },
    {
      name: TOOL_NAMES.render,
      title: "Render previdenza INPS review",
      description:
        "Validate and render facts, findings, calculations, missing evidence, authorities, audit checks, and artifacts in an interactive review widget.",
      inputSchema: reviewInput,
      _meta: toolUiMeta(),
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    },
    {
      name: TOOL_NAMES.save,
      title: "Save previdenza INPS decisions",
      description:
        "Validate reviewer actions and persist ui_decisions.json only inside run_intake.output_dir when supplied.",
      inputSchema: decisionInput,
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: false },
    },
    {
      name: TOOL_NAMES.apply,
      title: "Apply previdenza INPS decisions",
      description:
        "Apply reviewer actions by writing ui_decisions.json, applied_decisions.json, and final_artifacts.json only inside run_intake.output_dir when supplied.",
      inputSchema: decisionInput,
      annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: false },
    },
  ];
}

function resources() {
  return [
    {
      uri: WIDGET_URI,
      name: "previdenza_inps_review_widget",
      title: "Previdenza INPS review",
      description: "Interactive evidence and decision review for a local previdenza INPS case run.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetMeta(),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error("unknown widget resource");
  return fs.readFileSync(path.join(PLUGIN_ROOT, "assets", "previdenza-inps-review-widget.html"), "utf8");
}

function requireText(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value.trim();
}

function optionalText(value, field) {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error(`${field} must be a string when provided`);
  if (value.length > MAX_TEXT_LENGTH) throw new Error(`${field} exceeds ${MAX_TEXT_LENGTH} characters`);
  return value.trim();
}

function safeReviewData(item, itemType, root) {
  const input = isObject(item.data) ? item.data : {};
  const allowed = SAFE_REVIEW_DATA[itemType] || new Set();
  const data = {};
  for (const name of allowed) {
    if (input[name] == null) continue;
    const field = `${root}.data.${name}`;
    if (["fact_id", "claim_id", "recipe_id", "request_id", "source_id"].includes(name)) {
      data[name] = safeIdentifier(input[name], field);
    } else if (["evidence_count", "source_count"].includes(name)) {
      if (!Number.isInteger(input[name]) || input[name] < 0 || input[name] > MAX_ITEMS) {
        throw new Error(`${field} must be a bounded non-negative integer`);
      }
      data[name] = input[name];
    } else if (name === "path") {
      if (!SAFE_TRACE_OUTPUT_NAMES.has(input[name])) throw new Error(`${field} is not an approved artifact name`);
      data[name] = input[name];
    } else {
      const allowedValues = SAFE_REVIEW_DATA_ENUMS[name];
      if (!allowedValues || !allowedValues.has(input[name])) {
        throw new Error(`${field} is not an approved review value`);
      }
      data[name] = input[name];
    }
  }
  const summaries = {
    fact: "Validated fact record",
    finding: "Source-reviewed finding",
    calculation: "Approved calculation record",
    missing_evidence: "Missing evidence request",
    authority: "Authority record",
    audit_check: "Package validation audit",
    artifact: "Package artifact",
  };
  data.summary = summaries[itemType];
  return data;
}

function validateItem(item, index, seenIds) {
  const root = `review_payload.items[${index}]`;
  if (!isObject(item)) throw new Error(`${root} must be an object`);
  const id = safeIdentifier(item.id, `${root}.id`);
  if (seenIds.has(id)) throw new Error("review_payload contains a duplicate item id");
  seenIds.add(id);
  const itemType = safeIdentifier(item.item_type, `${root}.item_type`);
  if (!ITEM_TYPES.has(itemType)) throw new Error(`${root}.item_type is not supported`);
  if (!Array.isArray(item.allowed_actions) || item.allowed_actions.length === 0) {
    throw new Error(`${root}.allowed_actions must be a non-empty array`);
  }
  const actions = new Set();
  for (const action of item.allowed_actions) {
    if (!ALLOWED_ACTIONS.has(action)) throw new Error(`${root}.allowed_actions contains an unsupported action`);
    if (actions.has(action)) throw new Error(`${root}.allowed_actions contains a duplicate action`);
    actions.add(action);
  }
  if (item.recommended_action != null) {
    if (!ALLOWED_ACTIONS.has(item.recommended_action)) throw new Error(`${root}.recommended_action is not supported`);
    if (!actions.has(item.recommended_action)) throw new Error(`${root}.recommended_action must be in allowed_actions`);
  }
  if (item.status != null && !SAFE_ITEM_STATUSES.has(item.status)) {
    throw new Error(`${root}.status is not supported`);
  }
  const outputPath =
    typeof item.output_path === "string" && SAFE_TRACE_OUTPUT_NAMES.has(item.output_path) ? item.output_path : null;
  const titles = {
    fact: "Fact record",
    finding: "Finding record",
    calculation: "Calculation record",
    missing_evidence: "Missing evidence request",
    authority: "Authority record",
    audit_check: "Package validation audit",
    artifact: "Package artifact",
  };
  return {
    id,
    item_type: itemType,
    title: titles[itemType],
    source_path: null,
    output_path: outputPath,
    allowed_actions: [...actions],
    recommended_action: item.recommended_action || null,
    evidence: [],
    data: safeReviewData(item, itemType, root),
    status: "needs_review",
  };
}

function publicUiDecisions(value, review) {
  if (!isObject(value)) return null;
  const itemIds = new Set(review.items.map((item) => item.id));
  const decisions = Array.isArray(value.decisions)
    ? value.decisions
        .filter((decision) => isObject(decision) && itemIds.has(decision.item_id) && ALLOWED_ACTIONS.has(decision.action))
        .slice(0, review.items.length)
        .map((decision) => ({
          item_id: decision.item_id,
          action: decision.action,
          status: SAFE_DECISION_STATUSES.has(decision.status) ? decision.status : null,
        }))
    : [];
  return {
    schema_version: "1.0",
    plugin: "previdenza-inps",
    workflow: "previdenza-inps",
    run_id: review.run_id,
    decisions,
    decision_count: decisions.length,
    status: SAFE_UI_STATUSES.has(value.status) ? value.status : "pending",
  };
}

function publicFinalArtifacts(value, review) {
  if (!isObject(value)) return null;
  const outputs = Array.isArray(value.outputs)
    ? value.outputs
        .filter((entry) => isObject(entry) && SAFE_TRACE_OUTPUT_NAMES.has(entry.path))
        .slice(0, 100)
        .map((entry) => ({
          path: entry.path,
          kind: SAFE_OUTPUT_KINDS.has(entry.kind) ? entry.kind : null,
          status: SAFE_OUTPUT_STATUSES.has(entry.status) ? entry.status : null,
        }))
    : [];
  const blockerCount = Array.isArray(value.blockers) ? Math.min(value.blockers.length, MAX_ITEMS) : 0;
  return {
    schema_version: "1.0",
    plugin: "previdenza-inps",
    workflow: "previdenza-inps",
    run_id: review.run_id,
    status: SAFE_FINAL_STATUSES.has(value.status) ? value.status : null,
    review_status:
      SAFE_FINAL_STATUSES.has(value.review_status) ? value.review_status : null,
    outputs,
    blockers: Array.from({ length: blockerCount }, () => ({ status: "blocked" })),
  };
}

function validateReview(input) {
  if (!isObject(input)) throw new Error("tool arguments must be an object");
  const review = input.review_payload;
  if (!isObject(review)) throw new Error("review_payload must be an object");
  if (review.schema_version !== "1.0") throw new Error('review_payload.schema_version must be "1.0"');
  if (review.plugin !== "previdenza-inps") throw new Error('review_payload.plugin must be "previdenza-inps"');
  if (review.workflow !== "previdenza-inps") throw new Error('review_payload.workflow must be "previdenza-inps"');
  const runId = safeIdentifier(review.run_id, "review_payload.run_id");
  if (!REVIEW_TYPES.has(review.review_type)) throw new Error("review_payload.review_type is not supported");
  if (!REVIEW_STATUSES.has(review.status)) throw new Error("review_payload.status is not supported");
  if (!Array.isArray(review.items)) throw new Error("review_payload.items must be an array");
  if (review.items.length > MAX_ITEMS) throw new Error(`review_payload.items exceeds ${MAX_ITEMS} items`);
  if (!Number.isInteger(review.item_count) || review.item_count !== review.items.length) {
    throw new Error("review_payload.item_count must equal review_payload.items.length");
  }
  const seenIds = new Set();
  const safeItems = review.items.map((item, index) => validateItem(item, index, seenIds));
  const persistence = resolvePersistence(input, review);
  const safeReview = {
    schema_version: "1.0",
    plugin: "previdenza-inps",
    workflow: "previdenza-inps",
    run_id: runId,
    review_type: review.review_type,
    items: safeItems,
    item_count: safeItems.length,
    status: review.status,
    privacy_notice:
      "Review payload omits document quotes and subject labels; inspect local artifacts for full evidence.",
  };
  if (persistence && canonicalJson(safeReview) !== canonicalJson(review)) {
    throw new Error("stored review_payload.json contains fields that are not safe for MCP exposure");
  }
  const payload = {
    widget_type: "previdenza_inps_review",
    run_intake: publicRunIntake(persistence?.storedRunIntake || input.run_intake, persistence),
    review_payload: safeReview,
    ui_decisions: publicUiDecisions(input.ui_decisions, safeReview),
    final_artifacts: publicFinalArtifacts(input.final_artifacts, safeReview),
    decision_policy: {
      save_tool: TOOL_NAMES.save,
      apply_tool: TOOL_NAMES.apply,
      can_persist: Boolean(persistence),
      persistence_root: "run_intake.output_dir",
      fallback: "copy_or_download_json",
    },
  };
  if (Buffer.byteLength(JSON.stringify(payload), "utf8") > MAX_PAYLOAD_BYTES) {
    throw new Error(`previdenza INPS widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return { payload, persistence };
}

function stringArray(value, field) {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error(`${field} must be an array when provided`);
  return value.map((entry, index) => {
    const text = assertPrivacySafeText(entry, `${field}[${index}]`);
    if (!text) throw new Error(`${field}[${index}] must be a non-empty string`);
    return text;
  });
}

function explicitDocumentHints(item) {
  const values = [];
  const sources = [item, isObject(item.data) ? item.data : {}, ...(Array.isArray(item.evidence) ? item.evidence : [])];
  for (const source of sources) {
    if (!isObject(source)) continue;
    for (const key of ["requested_document", "required_document"]) {
      if (typeof source[key] === "string" && source[key].trim()) values.push(source[key].trim());
    }
    for (const key of ["requested_documents", "missing_documents", "support_documents"]) {
      if (Array.isArray(source[key])) {
        for (const value of source[key]) if (typeof value === "string" && value.trim()) values.push(value.trim());
      }
    }
  }
  return [...new Set(values)];
}

function followupContext(item) {
  const allowed = ["owner", "responsible_party", "source_system", "due_date", "period", "entity", "record_id", "amount", "reason", "priority"];
  const result = {};
  for (const source of [item, isObject(item.data) ? item.data : {}]) {
    for (const key of allowed) if (source[key] != null && source[key] !== "") result[key] = source[key];
  }
  return result;
}

function buildDecisions(input) {
  const { payload, persistence } = validateReview(input);
  if (!Array.isArray(input.decisions)) throw new Error("decisions must be an array");
  if (input.decisions.length > payload.review_payload.items.length) {
    throw new Error("decisions cannot exceed review_payload.items.length");
  }
  const itemById = new Map(payload.review_payload.items.map((item) => [item.id, item]));
  const seenIds = new Set();
  const decidedAt = new Date().toISOString();
  const decisions = input.decisions.map((decision, index) => {
    const root = `decisions[${index}]`;
    if (!isObject(decision)) throw new Error(`${root} must be an object`);
    const itemId = safeIdentifier(decision.item_id ?? decision.id, `${root}.item_id`);
    if (seenIds.has(itemId)) throw new Error("decisions contains a duplicate item_id");
    seenIds.add(itemId);
    const item = itemById.get(itemId);
    if (!item) throw new Error(`${root}.item_id is not in review_payload.items`);
    const action = requireText(decision.action, `${root}.action`);
    if (!ALLOWED_ACTIONS.has(action)) throw new Error(`${root}.action is not supported`);
    if (!item.allowed_actions.includes(action)) throw new Error(`${root}.action is not allowed for this item`);
    const reviewerNote = assertPrivacySafeText(decision.reviewer_note ?? decision.note, `${root}.reviewer_note`);
    const editValue = assertPrivacySafeText(decision.edit_value ?? decision.user_text, `${root}.edit_value`);
    if (action === "edit" && !editValue) throw new Error(`${root}.edit_value is required when action is edit`);
    let requestedDocuments = stringArray(decision.requested_documents, `${root}.requested_documents`);
    if (action === "request_more_documents" && requestedDocuments.length === 0) {
      requestedDocuments = explicitDocumentHints(item);
    }
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
    if (["mark_unclear", "request_more_documents"].includes(action)) {
      const context = followupContext(item);
      if (Object.keys(context).length) normalized.followup_context = context;
    }
    return normalized;
  });
  const itemCount = payload.review_payload.items.length;
  const status = decisions.length === 0 ? "pending_review" : decisions.length === itemCount ? "reviewed" : "partial_review";
  const uiDecisions = {
    schema_version: payload.review_payload.schema_version,
    plugin: "previdenza-inps",
    workflow: payload.review_payload.workflow,
    run_id: payload.review_payload.run_id,
    decided_at: decisions.length ? decidedAt : null,
    decision_source: input.decision_source
      ? safeIdentifier(input.decision_source, "decision_source")
      : "mcp_widget",
    review_payload_path: "review_payload.json",
    decisions,
    decision_count: decisions.length,
    item_count: itemCount,
    status,
  };
  const reviewer = input.reviewer ? safeIdentifier(input.reviewer, "reviewer") : "";
  if (reviewer) uiDecisions.reviewer = reviewer;
  return { payload, uiDecisions, outputDir: persistence?.outputDir || null };
}

function writeJson(outputDir, fileName, value) {
  if (!outputDir) return null;
  const outputPath = path.join(outputDir, fileName);
  const temporaryPath = path.join(outputDir, `.${fileName}.${crypto.randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    });
    fs.renameSync(temporaryPath, outputPath);
  } finally {
    if (fs.existsSync(temporaryPath)) fs.unlinkSync(temporaryPath);
  }
  return fileName;
}

function saveDecisions(input) {
  const { payload, uiDecisions, outputDir } = buildDecisions(input);
  const outputPath = writeJson(outputDir, "ui_decisions.json", uiDecisions);
  return {
    ok: true,
    validation_type: "previdenza_inps_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted: Boolean(outputPath),
    ui_decisions_path: outputPath,
    message: outputPath
      ? `Saved ${uiDecisions.decision_count} previdenza INPS decisions.`
      : "Validated decisions. Nothing was written because run_intake.output_dir was not supplied.",
    ui_decisions: publicUiDecisions(uiDecisions, payload.review_payload),
  };
}

function readJsonIfPresent(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${path.basename(filePath)} must be a regular file inside run_intake.output_dir`);
  }
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!isObject(value)) throw new Error(`${path.basename(filePath)} must contain a JSON object`);
  return value;
}

function decisionBlocker(effect) {
  return {
    item_id: effect.item_id,
    item_type: effect.item_type,
    title: effect.title,
    action: effect.action,
    status: effect.status,
    reason: effect.action === "edit" ? "revision_required" : "review_followup_required",
    requested_documents: effect.requested_documents || [],
    ...(effect.followup_context ? { followup_context: effect.followup_context } : {}),
  };
}

function applyDecisions(input) {
  const { payload, uiDecisions, outputDir } = buildDecisions(input);
  const appliedAt = new Date().toISOString();
  const blockingActions = new Set(["reject", "skip", "edit", "mark_unclear", "request_more_documents"]);
  const effects = uiDecisions.decisions.map((decision) => {
    const requiresFollowup = blockingActions.has(decision.action);
    return {
      ...decision,
      applied_at: appliedAt,
      requires_followup: requiresFollowup,
      application:
        decision.action === "edit"
          ? "revision_requirement_recorded_source_artifact_unchanged"
          : "review_status_recorded",
      ...(decision.action === "edit"
        ? { revision_status: "required_not_applied", source_artifact_modified: false }
        : {}),
    };
  });
  const finalPath = outputDir ? path.join(outputDir, "final_artifacts.json") : null;
  const current =
    readJsonIfPresent(finalPath) || (isObject(input.final_artifacts) ? input.final_artifacts : null) || {};
  if (current.plugin != null && current.plugin !== "previdenza-inps") {
    throw new Error('final_artifacts.plugin must be "previdenza-inps"');
  }
  if (current.run_id != null && current.run_id !== payload.review_payload.run_id) {
    throw new Error("final_artifacts.run_id must match review_payload.run_id");
  }
  if (current.workflow != null && current.workflow !== payload.review_payload.workflow) {
    throw new Error("final_artifacts.workflow must match review_payload.workflow");
  }
  const existingBlockers = Array.isArray(current.blockers) ? [...current.blockers] : [];
  const packageStatus = current.package_status || current.status || null;
  const packageAlreadyValid =
    packageStatus === READY_STATUS &&
    payload.review_payload.status === READY_STATUS &&
    existingBlockers.length === 0;
  const allItemsDecided = effects.length === payload.review_payload.items.length;
  const allAccepted = allItemsDecided && effects.every((effect) => effect.action === "accept");
  const newBlockers = effects.filter((effect) => effect.requires_followup).map(decisionBlocker);
  if (!packageAlreadyValid && effects.length) {
    newBlockers.push({
      item_id: "package-readiness",
      item_type: "audit_check",
      action: "block",
      status: "blocked",
      reason: "package_was_not_already_ready_for_professional_review",
      package_status: packageStatus,
      review_payload_status: payload.review_payload.status || null,
    });
  }
  const blockers = [...existingBlockers, ...newBlockers];
  const applicationStatus =
    effects.length === 0
      ? packageAlreadyValid
        ? "pending_review"
        : "blocked"
      : blockers.length
        ? "blocked"
        : !allItemsDecided
          ? "partial_review_applied"
          : allAccepted && packageAlreadyValid
            ? READY_STATUS
            : "blocked";

  const revisions = effects
    .filter((effect) => effect.action === "edit")
    .map((effect) => ({
      item_id: effect.item_id,
      item_type: effect.item_type,
      title: effect.title,
      requested_change: effect.edit_value,
      reviewer_note: effect.reviewer_note || null,
      status: "revision_required_not_applied",
      source_artifact_modified: false,
    }));
  const revisionRequirements = revisions.length
    ? {
        schema_version: payload.review_payload.schema_version,
        plugin: "previdenza-inps",
        workflow: payload.review_payload.workflow,
        run_id: payload.review_payload.run_id,
        recorded_at: appliedAt,
        status: "revision_required",
        source_artifacts_modified: false,
        revisions,
      }
    : null;

  const appliedDecisions = {
    schema_version: payload.review_payload.schema_version,
    plugin: "previdenza-inps",
    workflow: payload.review_payload.workflow,
    run_id: payload.review_payload.run_id,
    applied_at: appliedAt,
    decision_source: uiDecisions.decision_source,
    review_payload: {
      path: "review_payload.json",
      item_count: payload.review_payload.items.length,
      review_type: payload.review_payload.review_type || null,
    },
    decisions: uiDecisions.decisions,
    effects,
    decision_count: uiDecisions.decision_count,
    item_count: payload.review_payload.items.length,
    blocker_count: blockers.length,
    revision_required_count: revisions.length,
    application_status: applicationStatus,
  };
  if (uiDecisions.reviewer) appliedDecisions.reviewer = uiDecisions.reviewer;

  const outputs = Array.isArray(current.outputs) ? [...current.outputs] : [];
  const upsert = (record) => {
    const index = outputs.findIndex((output) => output && output.path === record.path);
    if (index >= 0) outputs[index] = { ...outputs[index], ...record };
    else outputs.push(record);
  };
  upsert({ path: "ui_decisions.json", kind: "json", status: "written_reviewed" });
  upsert({ path: "applied_decisions.json", kind: "json", status: applicationStatus });
  if (revisionRequirements) {
    upsert({
      path: "revision_requirements.json",
      kind: "json",
      status: "revision_required_not_applied",
    });
  }
  const nextActions = Array.isArray(current.next_actions) ? [...current.next_actions] : [];
  if (revisionRequirements) {
    nextActions.push("Regenerate and re-review affected artifacts; edit decisions did not modify source artifacts.");
  }
  if (blockers.length) nextActions.push("Resolve all blocked previdenza INPS review decisions before professional handoff.");
  else if (applicationStatus === "partial_review_applied") nextActions.push("Complete the remaining previdenza INPS review decisions.");
  const caveats = Array.isArray(current.caveats) ? [...current.caveats] : [];
  if (revisionRequirements) {
    caveats.push("Edit decisions are revision requirements only; no memo or source artifact was modified.");
  }
  const finalArtifacts = {
    schema_version: current.schema_version || payload.review_payload.schema_version,
    plugin: current.plugin || "previdenza-inps",
    workflow: current.workflow || payload.review_payload.workflow,
    run_id: current.run_id || payload.review_payload.run_id,
    review_payload_sha256: current.review_payload_sha256 || null,
    acquisition_binding: isObject(current.acquisition_binding) ? current.acquisition_binding : null,
    package_status: packageStatus,
    outputs,
    caveats: [...new Set(caveats)],
    blockers,
    next_actions: [...new Set(nextActions)],
    status: applicationStatus,
    review_status: applicationStatus,
    review_application: {
      applied_at: appliedAt,
      application_status: applicationStatus,
      decision_count: uiDecisions.decision_count,
      item_count: payload.review_payload.items.length,
      blocker_count: blockers.length,
      revision_required_count: revisions.length,
      applied_decisions_path: "applied_decisions.json",
    },
  };
  const uiPath = writeJson(outputDir, "ui_decisions.json", uiDecisions);
  const appliedPath = writeJson(outputDir, "applied_decisions.json", appliedDecisions);
  const revisionRequirementsPath = revisionRequirements
    ? writeJson(outputDir, "revision_requirements.json", revisionRequirements)
    : null;
  const finalArtifactsPath = writeJson(outputDir, "final_artifacts.json", finalArtifacts);
  let runIntakePath = null;
  if (outputDir) {
    const runIntake = readRunIntake(outputDir);
    const trace = Array.isArray(runIntake.execution_trace)
      ? runIntake.execution_trace.filter((entry) => entry?.step_id !== "previdenza_inps_review_application")
      : [];
    const traceOutputs = ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
    if (revisionRequirementsPath) traceOutputs.push("revision_requirements.json");
    trace.push({
      step_id: "previdenza_inps_review_application",
      kind: "professional_review_application",
      status: applicationStatus,
      execution_location: "local_mcp_server",
      command: "apply_previdenza_inps_decisions",
      inputs: ["review_payload", "ui_decisions"],
      outputs: traceOutputs,
      applied_at: appliedAt,
    });
    runIntake.execution_trace = trace;
    runIntakePath = writeJson(outputDir, "run_intake.json", runIntake);
  }
  return {
    ok: true,
    validation_type: "previdenza_inps_application",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    blocker_count: blockers.length,
    revision_required_count: revisions.length,
    application_status: applicationStatus,
    persisted: Boolean(appliedPath),
    ui_decisions_path: uiPath,
    applied_decisions_path: appliedPath,
    revision_requirements_path: revisionRequirementsPath,
    final_artifacts_path: finalArtifactsPath,
    run_intake_path: runIntakePath,
    message: appliedPath
      ? `Applied ${uiDecisions.decision_count} previdenza INPS decisions.`
      : "Validated application. Nothing was written because run_intake.output_dir was not supplied.",
    applied_decisions: {
      schema_version: appliedDecisions.schema_version,
      plugin: "previdenza-inps",
      workflow: "previdenza-inps",
      run_id: appliedDecisions.run_id,
      decision_count: appliedDecisions.decision_count,
      item_count: appliedDecisions.item_count,
      blocker_count: appliedDecisions.blocker_count,
      revision_required_count: appliedDecisions.revision_required_count,
      application_status: appliedDecisions.application_status,
    },
    revision_requirements: revisionRequirements
      ? {
          schema_version: revisionRequirements.schema_version,
          plugin: "previdenza-inps",
          workflow: "previdenza-inps",
          run_id: revisionRequirements.run_id,
          status: "revision_required",
          revision_count: revisionRequirements.revisions.length,
        }
      : null,
    final_artifacts: publicFinalArtifacts(finalArtifacts, payload.review_payload),
  };
}

function callTool(name, args) {
  if (name === TOOL_NAMES.validate) {
    const { payload } = validateReview(args);
    return {
      ok: true,
      validation_type: "previdenza_inps_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: `Previdenza INPS review payload is valid. It is safe to call ${TOOL_NAMES.render}.`,
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.render) return validateReview(args).payload;
  if (name === TOOL_NAMES.save) return saveDecisions(args);
  if (name === TOOL_NAMES.apply) return applyDecisions(args);
  throw new Error("unknown previdenza INPS tool");
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
          `Call ${TOOL_NAMES.validate} before ${TOOL_NAMES.render}. Use ${TOOL_NAMES.save} and ${TOOL_NAMES.apply} for durable decisions; persistence is confined to run_intake.output_dir.`,
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
      if (typeof params.uri !== "string") return rpcError(id, -32602, "resources/read requires a resource uri");
      return rpcResult(id, {
        contents: [{ uri: params.uri, mimeType: WIDGET_MIME_TYPE, text: resourceText(params.uri), _meta: widgetMeta() }],
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

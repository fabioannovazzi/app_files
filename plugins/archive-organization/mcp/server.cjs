#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");
const crypto = require("node:crypto");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_NAME = "vera-archive-organization";
const SERVER_VERSION = MANIFEST.version || "0.1.0";
const CLI_PATH = path.join(PLUGIN_ROOT, "scripts", "archive_organization.py");
const WIDGET_URI = "ui://widget/archive-organization-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 5000;
const MAX_PAYLOAD_BYTES = 8_000_000;
const REVIEW_REFERENCE_TTL_MS = 4 * 60 * 60 * 1000;
const MAX_REVIEW_REFERENCES = 128;
const REVIEW_REFERENCES = new Map();
const ALLOWED_ACTIONS = new Set([
  "accept",
  "reject",
  "edit",
  "mark_unclear",
  "skip",
]);
const ITEM_TYPES = new Set([
  "archive_file_proposal",
  "exact_duplicate_proposal",
]);
const TOOL_NAMES = {
  validateReview: "validate_archive_organization_review",
  renderReview: "render_archive_organization_review",
  saveDecisions: "save_archive_organization_decisions",
  applyDecisions: "apply_archive_organization_decisions",
};

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function objectSchema(properties, required = [], additionalProperties = true) {
  return { type: "object", properties, required, additionalProperties };
}

function icon() {
  const bytes = fs.readFileSync(path.join(PLUGIN_ROOT, "assets", "icon.svg"));
  return {
    src: `data:image/svg+xml;base64,${bytes.toString("base64")}`,
    mimeType: "image/svg+xml",
    sizes: ["24x24"],
  };
}

function toolUiMeta(resourceUri, toolName = null) {
  const meta = {
    ui: { resourceUri, visibility: ["model"] },
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    meta["openai/toolInvocation/invoking"] = "Rendering archive organization review";
    meta["openai/toolInvocation/invoked"] = "Rendered archive organization review";
  }
  return meta;
}

function reviewPayloadSchema() {
  return objectSchema(
    {
      schema_version: { type: "string" },
      plugin: { type: "string" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      review_type: { type: "string" },
      items: { type: "array", maxItems: MAX_ITEMS, items: { type: "object" } },
      item_count: { type: "number" },
      status: { type: "string" },
      content_sha256: { type: "string" },
    },
    ["schema_version", "plugin", "workflow", "run_id", "items", "item_count"],
  );
}

function decisionSchema() {
  return objectSchema(
    {
      item_id: { type: "string" },
      action: { type: "string", enum: Array.from(ALLOWED_ACTIONS) },
      reviewer_note: { type: "string" },
      edit_value: {
        type: "string",
        description: "Required client-relative destination path for edit.",
      },
      requested_documents: { type: "array", items: { type: "string" } },
    },
    ["item_id", "action"],
  );
}

function toolDefinitions() {
  const validateInput = objectSchema(
    {
      client_engagement: {
        type: "string",
        description:
          "Absolute path to the current Studio Archive context.json. Used once to bind a short-lived opaque review reference.",
      },
      review_payload: reviewPayloadSchema(),
    },
    ["review_payload"],
    false,
  );
  const renderInput = objectSchema(
    {
      review_reference: {
        type: "string",
        pattern: "^archive_review_[0-9a-f]{32}$",
      },
    },
    ["review_reference"],
    false,
  );
  const decisionInput = objectSchema(
    {
      review_reference: {
        type: "string",
        pattern: "^archive_review_[0-9a-f]{32}$",
      },
      decisions: { type: "array", maxItems: MAX_ITEMS, items: decisionSchema() },
      decision_source: { type: "string" },
      reviewer: { type: "string" },
    },
    ["review_reference", "decisions", "reviewer"],
    false,
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate archive organization review",
      description:
        "Validate one dry-run archive organization payload before rendering it. This never changes client files.",
      inputSchema: validateInput,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.renderReview,
      title: "Render archive organization review",
      description:
        "Render searchable file, destination, duplicate, anomaly, and confidence rows for collaborator review.",
      inputSchema: renderInput,
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
      title: "Save archive organization decisions",
      description:
        "Persist validated collaborator decisions to ui_decisions.json. This still does not move client files.",
      inputSchema: decisionInput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.applyDecisions,
      title: "Apply archive organization review decisions",
      description:
        "Compile persisted review decisions into approved_plan.json. This does not execute filesystem moves; a separate explicit apply approval remains mandatory.",
      inputSchema: decisionInput,
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
      name: "archive_organization_review_widget",
      title: "Archive organization review widget",
      description:
        "Reviews source paths, proposed destinations, duplicate evidence, anomalies, confidence, and collaborator actions.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: {
        ui: { resourceUri: WIDGET_URI },
        "openai/widgetDescription":
          "Interactive review of a dry-run client-folder organization plan. Saving or applying decisions never performs filesystem moves.",
        "openai/widgetPrefersBorder": false,
        "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
        "openai/widgetDomain": "https://chatgpt.com",
      },
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "archive-organization-review-widget.html"),
    "utf8",
  );
}

function requireString(value, label, maximum = 4096) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) {
    throw new Error(`${label} must be a bounded non-empty string`);
  }
  return value.trim();
}

function validateReviewPayload(value) {
  if (!isPlainObject(value)) throw new Error("review_payload must be an object");
  if (value.plugin !== "archive-organization" || value.workflow !== "archive-organization") {
    throw new Error("review_payload plugin and workflow must be archive-organization");
  }
  requireString(value.run_id, "review_payload.run_id", 120);
  if (!Array.isArray(value.items) || value.items.length > MAX_ITEMS) {
    throw new Error(`review_payload.items exceeds ${MAX_ITEMS} items`);
  }
  if (value.item_count !== value.items.length) {
    throw new Error("review_payload.item_count is stale");
  }
  const itemIds = new Set();
  for (const item of value.items) {
    if (!isPlainObject(item)) throw new Error("review item must be an object");
    const itemId = requireString(item.id, "review item id", 120);
    if (itemIds.has(itemId)) throw new Error(`duplicate review item id: ${itemId}`);
    itemIds.add(itemId);
    if (!ITEM_TYPES.has(item.item_type)) {
      throw new Error(`review item ${itemId} has unsupported item_type: ${item.item_type}`);
    }
    if (!Array.isArray(item.allowed_actions) || !item.allowed_actions.length) {
      throw new Error(`review item ${itemId} has no allowed actions`);
    }
    for (const action of item.allowed_actions) {
      if (!ALLOWED_ACTIONS.has(action)) {
        throw new Error(`review item ${itemId} has unsupported action: ${action}`);
      }
    }
  }
  if (Buffer.byteLength(JSON.stringify(value), "utf8") > MAX_PAYLOAD_BYTES) {
    throw new Error(`review payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return { itemIds, itemById: new Map(value.items.map((item) => [item.id, item])) };
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

function pruneReviewReferences(now = Date.now()) {
  for (const [reference, context] of REVIEW_REFERENCES.entries()) {
    if (context.expiresAt <= now) REVIEW_REFERENCES.delete(reference);
  }
  while (REVIEW_REFERENCES.size >= MAX_REVIEW_REFERENCES) {
    const oldest = REVIEW_REFERENCES.keys().next().value;
    if (oldest == null) break;
    REVIEW_REFERENCES.delete(oldest);
  }
}

function readRegularJson(filePath, label) {
  const observed = fs.lstatSync(filePath);
  if (!observed.isFile() || observed.isSymbolicLink()) {
    throw new Error(`${label} must be a regular non-symlink file`);
  }
  const bytes = fs.readFileSync(filePath);
  if (bytes.length > MAX_PAYLOAD_BYTES) {
    throw new Error(`${label} exceeds the bounded payload size`);
  }
  let payload;
  try {
    payload = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new Error(`${label} must contain valid JSON`);
  }
  if (!isPlainObject(payload)) throw new Error(`${label} must contain an object`);
  return { payload, bytes };
}

function registerReviewReference(clientEngagement, suppliedReview) {
  if (clientEngagement == null || clientEngagement === "") {
    const reference = `archive_review_${crypto.randomBytes(16).toString("hex")}`;
    const reviewSha256 = crypto
      .createHash("sha256")
      .update(canonicalJson(suppliedReview), "utf8")
      .digest("hex");
    pruneReviewReferences();
    REVIEW_REFERENCES.set(reference, {
      clientEngagement: null,
      outputDir: null,
      reviewPath: null,
      review: suppliedReview,
      reviewSha256,
      runId: suppliedReview.run_id,
      expiresAt: Date.now() + REVIEW_REFERENCE_TTL_MS,
    });
    return { reference, reviewSha256, persistenceEnabled: false };
  }
  const requestedContext = requireString(clientEngagement, "client_engagement");
  if (!path.isAbsolute(requestedContext)) {
    throw new Error("client_engagement must be absolute");
  }
  const contextPath = path.resolve(requestedContext);
  const contextStat = fs.lstatSync(contextPath);
  if (!contextStat.isFile() || contextStat.isSymbolicLink()) {
    throw new Error("client_engagement must identify a regular context file");
  }
  const preflight = load_client_workflow_context_for_output(
    contextPath,
    suppliedReview.run_id,
  );
  const outputDir = fs.realpathSync(requireString(preflight.output_dir, "output_dir"));
  const outputStat = fs.statSync(outputDir);
  if (!outputStat.isDirectory()) throw new Error("review output is unavailable");
  const reviewPath = path.join(outputDir, "review_payload.json");
  const stored = readRegularJson(reviewPath, "stored review payload");
  validateReviewPayload(stored.payload);
  if (canonicalJson(stored.payload) !== canonicalJson(suppliedReview)) {
    throw new Error("review payload does not match the stored review package");
  }
  const reference = `archive_review_${crypto.randomBytes(16).toString("hex")}`;
  const reviewSha256 = crypto.createHash("sha256").update(stored.bytes).digest("hex");
  pruneReviewReferences();
  REVIEW_REFERENCES.set(reference, {
    clientEngagement: contextPath,
    outputDir,
    reviewPath,
    reviewSha256,
    runId: stored.payload.run_id,
    expiresAt: Date.now() + REVIEW_REFERENCE_TTL_MS,
  });
  return { reference, reviewSha256, persistenceEnabled: true };
}

function resolveReviewReference(rawReference) {
  const reference = requireString(rawReference, "review_reference", 47);
  if (!/^archive_review_[0-9a-f]{32}$/.test(reference)) {
    throw new Error("review_reference is invalid");
  }
  pruneReviewReferences();
  const context = REVIEW_REFERENCES.get(reference);
  if (!context || context.expiresAt <= Date.now()) {
    throw new Error("review_reference is unknown or expired");
  }
  const stored = context.reviewPath
    ? readRegularJson(context.reviewPath, "stored review payload")
    : { payload: context.review, bytes: null };
  const currentSha256 = context.reviewPath
    ? crypto.createHash("sha256").update(stored.bytes).digest("hex")
    : crypto
        .createHash("sha256")
        .update(canonicalJson(stored.payload), "utf8")
        .digest("hex");
  if (
    currentSha256 !== context.reviewSha256 ||
    stored.payload.run_id !== context.runId
  ) {
    throw new Error("review_reference no longer matches the stored review package");
  }
  validateReviewPayload(stored.payload);
  return { reference, context, review: stored.payload };
}

function readOptionalSidecar(outputDir, name) {
  const filePath = path.join(outputDir, name);
  if (!fs.existsSync(filePath)) return null;
  return readRegularJson(filePath, name).payload;
}

function validateDecisions(inputArgs) {
  const review = validateReviewPayload(inputArgs.review_payload);
  if (!Array.isArray(inputArgs.decisions) || inputArgs.decisions.length > MAX_ITEMS) {
    throw new Error(`decisions exceeds ${MAX_ITEMS} items`);
  }
  const seen = new Set();
  const decisions = inputArgs.decisions.map((decision) => {
    if (!isPlainObject(decision)) throw new Error("decision must be an object");
    const itemId = requireString(decision.item_id, "decision.item_id", 120);
    const action = requireString(decision.action, "decision.action", 40);
    if (!review.itemIds.has(itemId)) {
      throw new Error(`decision item_id is not in review_payload.items: ${itemId}`);
    }
    if (seen.has(itemId)) throw new Error(`decisions contains duplicate item_id: ${itemId}`);
    seen.add(itemId);
    if (!ALLOWED_ACTIONS.has(action)) throw new Error(`unsupported action: ${action}`);
    const item = review.itemById.get(itemId);
    if (!item.allowed_actions.includes(action)) {
      throw new Error(`action is not allowed for item ${itemId}: ${action}`);
    }
    const editValue = decision.edit_value == null ? "" : String(decision.edit_value).trim();
    if (action === "edit" && !editValue) {
      throw new Error(`edit_value is required when action is edit`);
    }
    if (action !== "edit" && editValue) {
      throw new Error("edit_value is allowed only when action is edit");
    }
    return {
      item_id: itemId,
      action,
      reviewer_note: String(decision.reviewer_note || "").slice(0, 1000),
      edit_value: editValue,
      requested_documents: [],
    };
  });
  return decisions;
}

function pythonExecutable() {
  return process.env.VIRTUAL_ENV
    ? path.join(process.env.VIRTUAL_ENV, process.platform === "win32" ? "Scripts/python.exe" : "bin/python")
    : process.platform === "win32"
      ? "python"
      : "python3";
}

function callCli(args) {
  const result = spawnSync(pythonExecutable(), [CLI_PATH, ...args], {
    cwd: PLUGIN_ROOT,
    encoding: "utf8",
    maxBuffer: MAX_PAYLOAD_BYTES,
    timeout: 300000,
  });
  if (result.error) throw result.error;
  const lines = String(result.stdout || "").trim().split(/\r?\n/).filter(Boolean);
  let payload = null;
  if (lines.length) {
    try {
      payload = JSON.parse(lines.at(-1));
    } catch {
      throw new Error("archive organization returned invalid JSON");
    }
  }
  if (result.status !== 0 || payload?.error) {
    throw new Error(payload?.error?.message || String(result.stderr || "").trim() || "archive organization failed");
  }
  return payload;
}

function load_client_workflow_context_for_output(clientEngagement, expectedRunId) {
  const result = callCli([
    "preflight",
    "--client-engagement",
    clientEngagement,
  ]);
  if (result.run_id !== expectedRunId) {
    throw new Error("client engagement run_id does not match review_payload.run_id");
  }
  return result;
}

function persistDecisions(inputArgs, compileApproval) {
  const resolved = resolveReviewReference(inputArgs.review_reference);
  if (!resolved.context.clientEngagement) {
    throw new Error(
      "review_reference is review-only; local persistence requires a bound Studio Archive run",
    );
  }
  const clientEngagement = resolved.context.clientEngagement;
  const boundArgs = { ...inputArgs, review_payload: resolved.review };
  load_client_workflow_context_for_output(
    clientEngagement,
    resolved.review.run_id,
  );
  const decisions = validateDecisions(boundArgs);
  const incoming = {
    schema_version: "1.0",
    plugin: "archive-organization",
    workflow: "archive-organization",
    run_id: resolved.review.run_id,
    decision_source: String(inputArgs.decision_source || "mcp_widget").slice(0, 80),
    reviewer: requireString(inputArgs.reviewer, "reviewer", 160),
    decisions,
  };
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "vera-archive-review-"));
  const temporaryDecisions = path.join(temporaryRoot, "decisions.json");
  try {
    fs.writeFileSync(temporaryDecisions, `${JSON.stringify(incoming, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600,
      flag: "wx",
    });
    const saved = callCli([
      "save-decisions",
      "--client-engagement",
      clientEngagement,
      "--decisions",
      temporaryDecisions,
    ]);
    const savedSummary = {
      status: saved.status,
      run_id: resolved.review.run_id,
      decision_count: saved.decision_count,
      reviewer: saved.reviewer,
      review_reference: resolved.reference,
      source_archive_mutated: false,
    };
    if (!compileApproval) return savedSummary;
    const approved = callCli([
      "approve",
      "--client-engagement",
      clientEngagement,
      "--decisions",
      saved.ui_decisions_path,
    ]);
    return {
      ...savedSummary,
      status: approved.status,
      approved_change_count: approved.approved_change_count,
      execution_requires_separate_explicit_approval: true,
    };
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

function callTool(name, inputArgs) {
  const args = isPlainObject(inputArgs) ? inputArgs : {};
  if (name === TOOL_NAMES.validateReview) {
    validateReviewPayload(args.review_payload);
    const registered = registerReviewReference(
      args.client_engagement,
      args.review_payload,
    );
    return {
      valid: true,
      plugin: "archive-organization",
      run_id: args.review_payload.run_id,
      item_count: args.review_payload.items.length,
      review_reference: {
        reference: registered.reference,
        run_id: args.review_payload.run_id,
        review_payload_sha256: registered.reviewSha256,
        expires_in_seconds: Math.floor(REVIEW_REFERENCE_TTL_MS / 1000),
        persistence_enabled: registered.persistenceEnabled,
      },
      source_archive_mutated: false,
    };
  }
  if (name === TOOL_NAMES.renderReview) {
    const resolved = resolveReviewReference(args.review_reference);
    return {
      plugin: "archive-organization",
      run_id: resolved.review.run_id,
      review_payload: resolved.review,
      ui_decisions: resolved.context.outputDir
        ? readOptionalSidecar(resolved.context.outputDir, "ui_decisions.json")
        : null,
      final_artifacts: resolved.context.outputDir
        ? readOptionalSidecar(resolved.context.outputDir, "final_artifacts.json")
        : null,
      review_reference: resolved.reference,
      persistence_enabled: Boolean(resolved.context.clientEngagement),
      execution_requires_separate_explicit_approval: true,
      source_archive_mutated: false,
    };
  }
  if (name === TOOL_NAMES.saveDecisions) return persistDecisions(args, false);
  if (name === TOOL_NAMES.applyDecisions) return persistDecisions(args, true);
  throw new Error("unknown archive organization tool");
}

function toolResult(payload) {
  const structured = { ok: true, ...payload };
  return {
    content: [
      {
        type: "text",
        text: "Archive Organization returned the structured review result attached to this tool response.",
      },
    ],
    structuredContent: structured,
    isError: false,
  };
}

function toolError(error) {
  const payload = {
    ok: false,
    error: {
      code: "archive_organization_review_failed",
      message: error instanceof Error ? error.message : String(error),
    },
  };
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
  const params = isPlainObject(message.params) ? message.params : {};
  if (message.method === "initialize") {
    return rpcResult(id, {
      protocolVersion: params.protocolVersion || "2024-11-05",
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      capabilities: { tools: {}, resources: {} },
      instructions:
        "Validate and render the dry-run archive plan, then persist collaborator decisions. Applying review decisions only writes approved_plan.json. Never claim that it moved files; filesystem execution requires a separate explicit apply approval.",
    });
  }
  if (message.method === "notifications/initialized") return null;
  if (message.method === "tools/list") return rpcResult(id, { tools: toolDefinitions() });
  if (message.method === "tools/call") {
    try {
      return rpcResult(id, toolResult(callTool(params.name, params.arguments)));
    } catch (error) {
      return rpcResult(id, toolError(error));
    }
  }
  if (message.method === "resources/list") return rpcResult(id, { resources: resources() });
  if (message.method === "resources/read") {
    try {
      return rpcResult(id, {
        contents: [{ uri: params.uri, mimeType: WIDGET_MIME_TYPE, text: resourceText(params.uri), _meta: resources()[0]._meta }],
      });
    } catch (error) {
      return rpcError(id, -32602, error.message);
    }
  }
  if (message.method === "resources/templates/list") return rpcResult(id, { resourceTemplates: [] });
  if (message.method === "prompts/list") return rpcResult(id, { prompts: [] });
  return rpcError(id, -32601, "method not found");
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function main() {
  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  lines.on("line", (line) => {
    if (!line.trim()) return;
    try {
      const message = JSON.parse(line);
      const response = handleRpc(message);
      if (response != null) send(response);
    } catch (error) {
      send(rpcError(null, -32700, error instanceof Error ? error.message : "parse error"));
    }
  });
}

if (require.main === module) main();

module.exports = {
  TOOL_NAMES,
  callTool,
  resources,
  toolDefinitions,
  validateDecisions,
  validateReviewPayload,
};

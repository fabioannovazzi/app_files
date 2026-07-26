"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const childProcess = require("node:child_process");

const SERVER_NAME = "journal-sampling-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const JOURNAL_SAMPLING_PLUGIN_IMPLEMENTATION_PATHS = [
  "scripts/check_dependencies.py",
  "scripts/implementation_bootstrap.py",
  "scripts/inspect_journal.py",
  "scripts/journal_sampling_core.py",
  "scripts/normalize_journal.py",
  "scripts/replay_normalization.py",
  "scripts/review_session.py",
  "scripts/review_successor.py",
  "scripts/run_sample.py",
  "mcp/server.cjs",
  "assets/icon.svg",
  "assets/journal-sampling-review-widget.html",
  "assets/review-workbench-adapter.json",
  ".app.json",
  ".mcp.json",
  ".codex-plugin/plugin.json",
];
const JOURNAL_SAMPLING_SHARED_IMPLEMENTATION_PATHS = [
  "__init__.py",
  "contracts.py",
  "decisions.py",
  "envelope.py",
  "money.py",
  "relationships.py",
  "review_output_transaction.cjs",
  "serialization.py",
];
const JOURNAL_SAMPLING_SHARED_ROOT = (() => {
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

function journalExpectedImplementationDirectories(relativePaths) {
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

function journalScanImplementationRoot(root, scanRoots, rootFiles) {
  const rootEntry = fs.lstatSync(root);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("Journal Sampling implementation root must be real.");
  }
  const files = new Set();
  const directories = new Set();
  for (const relativePath of rootFiles) {
    const entry = fs.lstatSync(path.join(root, relativePath));
    if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
      throw new Error("Journal Sampling implementation artifact is invalid.");
    }
    files.add(relativePath);
  }
  const pending = scanRoots.map((relativePath) => {
    const scanPath = path.join(root, relativePath);
    const entry = fs.lstatSync(scanPath);
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      throw new Error("Journal Sampling implementation directory is invalid.");
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
        throw new Error("Journal Sampling implementation cannot contain symlinks.");
      }
      if (entry.isDirectory()) {
        directories.add(relative);
        pending.push(entryPath);
        continue;
      }
      if (!entry.isFile() || entry.nlink !== 1) {
        throw new Error("Journal Sampling implementation artifact is invalid.");
      }
      files.add(relative);
    }
  }
  return { files, directories };
}

function validateJournalImplementationTree() {
  const pluginTree = journalScanImplementationRoot(
    PLUGIN_ROOT,
    [".codex-plugin", "assets", "mcp", "scripts"],
    [".app.json", ".mcp.json"],
  );
  const sharedTree = journalScanImplementationRoot(
    JOURNAL_SAMPLING_SHARED_ROOT,
    ["."],
    [],
  );
  const expectedPluginDirectories =
    journalExpectedImplementationDirectories(
      JOURNAL_SAMPLING_PLUGIN_IMPLEMENTATION_PATHS,
    );
  if (
    JSON.stringify([...pluginTree.files].sort()) !==
      JSON.stringify([...JOURNAL_SAMPLING_PLUGIN_IMPLEMENTATION_PATHS].sort()) ||
    JSON.stringify([...pluginTree.directories].sort()) !==
      JSON.stringify([...expectedPluginDirectories].sort()) ||
    JSON.stringify([...sharedTree.files].sort()) !==
      JSON.stringify([...JOURNAL_SAMPLING_SHARED_IMPLEMENTATION_PATHS].sort()) ||
    sharedTree.directories.size !== 0
  ) {
    throw new Error("Journal Sampling implementation tree is not exact.");
  }
}

validateJournalImplementationTree();

function readJournalImplementationText(relativePath) {
  const implementationPath = path.join(PLUGIN_ROOT, relativePath);
  const observed = fs.lstatSync(implementationPath);
  if (
    observed.isSymbolicLink() ||
    !observed.isFile() ||
    observed.nlink !== 1
  ) {
    throw new Error(
      "Journal Sampling implementation must be an ordinary single-link file.",
    );
  }
  return fs.readFileSync(implementationPath, "utf8");
}

const PLUGIN_MANIFEST = JSON.parse(
  readJournalImplementationText(".codex-plugin/plugin.json"),
);
const APP_MANIFEST = JSON.parse(
  readJournalImplementationText(".app.json"),
);
const MCP_MANIFEST = JSON.parse(
  readJournalImplementationText(".mcp.json"),
);
const REVIEW_ADAPTER = JSON.parse(
  readJournalImplementationText("assets/review-workbench-adapter.json"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/journal-sampling-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const TOOL_NAMES = {
  validateReview: "validate_journal_sampling_review",
  renderReview: "render_journal_sampling_review",
  saveDecisions: "save_journal_sampling_decisions",
  applyDecisions: "apply_journal_sampling_decisions",
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
  "sampling_control",
  "sampled_entry",
  "sample_artifact",
  "review_artifact",
]);

function validateJournalImplementationConfiguration() {
  validateJournalImplementationTree();
  const serverObserved = fs.lstatSync(__filename);
  if (
    serverObserved.isSymbolicLink() ||
    !serverObserved.isFile() ||
    serverObserved.nlink !== 1 ||
    PLUGIN_MANIFEST.name !== "journal-sampling" ||
    PLUGIN_MANIFEST.skills !== "./skills/" ||
    PLUGIN_MANIFEST.apps !== "./.app.json" ||
    PLUGIN_MANIFEST.mcpServers !== "./.mcp.json" ||
    journalReviewStableJson(APP_MANIFEST) !== '{"apps":{}}'
  ) {
    throw new Error("Journal Sampling plugin discovery configuration is stale.");
  }
  const servers = MCP_MANIFEST.mcpServers;
  const serverNames = isPlainObject(servers) ? Object.keys(servers) : [];
  const server = isPlainObject(servers)
    ? servers.journalSamplingWidgets
    : null;
  if (
    journalReviewStableJson(serverNames.sort()) !==
      '["journalSamplingWidgets"]' ||
    !isPlainObject(server) ||
    server.cwd !== "." ||
    server.command !== "node" ||
    journalReviewStableJson(server.args) !==
      '["./mcp/server.cjs","--stdio"]'
  ) {
    throw new Error("Journal Sampling MCP launch contract is stale.");
  }
  if (
    REVIEW_ADAPTER.plugin !== "journal-sampling" ||
    REVIEW_ADAPTER.saveTool !== TOOL_NAMES.saveDecisions ||
    REVIEW_ADAPTER.applyTool !== TOOL_NAMES.applyDecisions ||
    REVIEW_ADAPTER.widgetType !== "journal_sampling_review"
  ) {
    throw new Error("Journal Sampling review adapter contract is stale.");
  }
  const widget = readJournalImplementationText(
    "assets/journal-sampling-review-widget.html",
  );
  const matches = Array.from(
    widget.matchAll(/^[ \t]*const CONFIG = (\{.*\});[ \t]*$/gm),
  );
  if (
    matches.length !== 1 ||
    journalReviewStableJson(JSON.parse(matches[0][1])) !==
      journalReviewStableJson(REVIEW_ADAPTER)
  ) {
    throw new Error(
      "Journal Sampling widget does not embed the exact review adapter.",
    );
  }
}

validateJournalImplementationConfiguration();

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function normalizeRuntimeLanguage(value) {
  if (typeof value !== "string") return "";
  const normalized = value.trim().toLowerCase().replace(/_/g, "-");
  const primary = normalized.split("-")[0];
  if (["es", "spa", "spanish", "español", "espanol"].includes(normalized)) return "es";
  if (["es", "spa"].includes(primary)) return "es";
  return primary;
}

function runtimeLanguage(inputArgs = {}) {
  if (typeof inputArgs === "string") return normalizeRuntimeLanguage(inputArgs) || "en";
  const args = isPlainObject(inputArgs) ? inputArgs : {};
  const reviewPayload = isPlainObject(args.review_payload) ? args.review_payload : {};
  const runIntake = isPlainObject(args.run_intake) ? args.run_intake : {};
  const assumptions = isPlainObject(runIntake.assumptions) ? runIntake.assumptions : {};
  const meta = isPlainObject(args.meta)
    ? args.meta
    : isPlainObject(args._meta)
      ? args._meta
      : {};
  const candidate =
    reviewPayload.language ||
    reviewPayload.working_language ||
    reviewPayload.locale ||
    runIntake.language ||
    runIntake.working_language ||
    runIntake.locale ||
    assumptions.language ||
    args.language ||
    args.working_language ||
    args.locale ||
    meta.language ||
    meta.working_language ||
    meta.locale;
  return normalizeRuntimeLanguage(candidate) || "en";
}

function isSpanishRuntime(inputArgs = {}) {
  return runtimeLanguage(inputArgs) === "es";
}

function localizedValidationError(error, inputArgs = {}) {
  const message = error instanceof Error ? error.message : String(error);
  if (!isSpanishRuntime(inputArgs)) return message;
  const exact = {
    "tool arguments must be an object": "los argumentos de la herramienta deben ser un objeto",
    "review_payload must be an object": "review_payload debe ser un objeto",
    "review_payload.items must be an array": "review_payload.items debe ser una lista",
    "review_payload.item_count must equal review_payload.items.length":
      "review_payload.item_count debe coincidir con review_payload.items.length",
    "decisions must be an array": "decisions debe ser una lista",
    "run_intake.run_id must match review_payload.run_id":
      "run_intake.run_id debe coincidir con review_payload.run_id",
  };
  let translated = exact[message] || message;
  translated = translated
    .replace(/ must be a non-empty string/g, " debe ser una cadena no vacía")
    .replace(/ must be a string when provided/g, " debe ser una cadena cuando se proporcione")
    .replace(/ must be an object/g, " debe ser un objeto")
    .replace(/ must be an array when provided/g, " debe ser una lista cuando se proporcione")
    .replace(/ must be an array/g, " debe ser una lista")
    .replace(/ contains unsupported action: /g, " contiene una acción no admitida: ")
    .replace(/ is not supported: /g, " no se admite: ")
    .replace(/ is not supported/g, " no se admite")
    .replace(/ is not allowed for item /g, " no está permitida para el elemento ")
    .replace(/ is not in review_payload\.items: /g, " no figura en review_payload.items: ")
    .replace(/ is required when action is edit/g, " es obligatorio cuando action es edit")
    .replace(/ cannot exceed /g, " no puede superar ")
    .replace(/ exceeds /g, " supera ");
  return `No se pudo validar la solicitud: ${translated}`;
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
    meta["openai/toolInvocation/invoking"] = "Rendering Journal Sampling review";
    meta["openai/toolInvocation/invoked"] = "Rendered Journal Sampling review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Journal Sampling review surface for sampling parameters, filters, sampled entries, and generated artifacts.",
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
      language: { type: "string" },
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
      title: "Validate Journal Sampling review payload",
      description:
        "Validate the Journal Sampling review-session payload before rendering. Call this first, then render_journal_sampling_review.",
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
      title: "Render Journal Sampling review",
      description:
        "Render a Journal Sampling review-session payload as an MCP HTML widget for sampling controls, sampled entries, diagnostics, and artifacts.",
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
      title: "Save Journal Sampling review decisions",
      description:
        "Validate Journal Sampling review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
      title: "Apply Journal Sampling review decisions",
      description:
        "Validate Journal Sampling review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
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
      name: "journal_sampling_review_widget",
      title: "Journal Sampling review widget",
      description:
        "Renders Journal Sampling review-session payloads with searchable sampled entries and audit details.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) {
  throw new Error(`unknown Journal Sampling widget resource: ${uri}`);
  }
  return readJournalImplementationText(
    "assets/journal-sampling-review-widget.html",
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
  if (reviewPayload.plugin !== "journal-sampling") {
    throw new Error('review_payload.plugin must be "journal-sampling"');
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
    widget_type: "journal_sampling_review",
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
    throw new Error(`Journal Sampling widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
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

function reviewIntegerOrZero(value) {
  return Number.isInteger(value) ? value : 0;
}

function reviewResponseMatches(result, expected) {
  if (!isPlainObject(result) || !isPlainObject(expected)) return false;
  const resultKeys = Object.keys(result).sort();
  const expectedKeys = Object.keys(expected).sort();
  return (
    JSON.stringify(resultKeys) === JSON.stringify(expectedKeys) &&
    expectedKeys.every(
      (key) =>
        journalReviewStableJson(result[key]) ===
        journalReviewStableJson(expected[key]),
    )
  );
}

const JOURNAL_REVIEW_TRANSACTION_STATE = Symbol(
  "journal-review-transaction-state",
);

function cloneJournalReviewTransactionValue(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function journalReviewTransactionJsonFromImage(image, relativePath) {
  const entry = image?.files?.find((candidate) => candidate.path === relativePath);
  if (!entry) return null;
  try {
    const parsed = JSON.parse(entry.payload.toString("utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function journalReviewStableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((entry) => journalReviewStableJson(entry)).join(",")}]`;
  }
  if (isPlainObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${journalReviewStableJson(value[key])}`,
      )
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function journalAssuranceManifestPath(outputDir) {
  return path.join(outputDir, "sample_output_receipts.json");
}

function journalOutputHasAssuranceManifest(outputDir) {
  if (!outputDir) return false;
  const manifestPath = journalAssuranceManifestPath(outputDir);
  const observed = generatedReviewPathEntryStat(manifestPath);
  return Boolean(
    observed &&
      observed.isFile() &&
      !observed.isSymbolicLink() &&
      observed.nlink === 1,
  );
}

function journalAssurancePythonExecutable() {
  const candidates = [
    process.env.JOURNAL_SAMPLING_PYTHON,
    process.env.PYTHON,
    process.env.VIRTUAL_ENV
      ? path.join(process.env.VIRTUAL_ENV, "bin", "python")
      : "",
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

function runJournalAssuranceBridge(command, outputDir, kind = null) {
  const canonicalServer = path.join(PLUGIN_ROOT, "mcp", "server.cjs");
  if (path.resolve(__filename) !== path.resolve(canonicalServer)) {
    throw new Error(
      "Journal Sampling assured review requires the receipted MCP implementation.",
    );
  }
  const scriptPath = path.join(
    PLUGIN_ROOT,
    "scripts",
    "review_successor.py",
  );
  const args = [scriptPath, command, outputDir];
  if (kind) args.push("--kind", kind);
  const completed = childProcess.spawnSync(
    journalAssurancePythonExecutable(),
    ["-I", "-B", ...args],
    {
      cwd: PLUGIN_ROOT,
      encoding: "utf8",
      timeout: 60_000,
      maxBuffer: 16 * 1024 * 1024,
      env: process.env,
    },
  );
  if (
    completed.error ||
    completed.status !== 0 ||
    typeof completed.stdout !== "string"
  ) {
    throw new Error(`Journal Sampling assurance ${command} failed.`);
  }
  try {
    const result = JSON.parse(completed.stdout.trim());
    if (!isPlainObject(result)) throw new Error("invalid result");
    return result;
  } catch {
    throw new Error(`Journal Sampling assurance ${command} returned invalid data.`);
  }
}

function refreshJournalAssuredTransactionResult(
  kind,
  workingResult,
  workingOutputDir,
  parentState,
) {
  const successor = runJournalAssuranceBridge(
    "finalize",
    workingOutputDir,
    kind,
  );
  const persistedUiDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "ui_decisions.json"),
  );
  const persistedFinalArtifacts = readJsonFileIfPresent(
    path.join(workingOutputDir, "final_artifacts.json"),
  );
  const persistedRunIntake = readJsonFileIfPresent(
    path.join(workingOutputDir, "run_intake.json"),
  );
  if (
    !isPlainObject(persistedUiDecisions) ||
    !isPlainObject(persistedFinalArtifacts) ||
    !isPlainObject(persistedRunIntake) ||
    !Array.isArray(successor.physical_paths)
  ) {
    throw new Error("Journal Sampling successor finalization did not close.");
  }
  if (kind === "save") {
    workingResult.ui_decisions = persistedUiDecisions;
  }
  parentState.expectedUiDecisions =
    cloneJournalReviewTransactionValue(persistedUiDecisions);
  parentState.expectedFinalArtifacts =
    cloneJournalReviewTransactionValue(persistedFinalArtifacts);
  parentState.expectedRunIntake =
    cloneJournalReviewTransactionValue(persistedRunIntake);
  parentState.authorizedWritePaths = [...successor.physical_paths];
  parentState.successorStage =
    cloneJournalReviewTransactionValue(successor.stage);
  if (kind === "apply") {
    const persistedAppliedDecisions = readJsonFileIfPresent(
      path.join(workingOutputDir, "applied_decisions.json"),
    );
    if (!isPlainObject(persistedAppliedDecisions)) {
      throw new Error("Journal Sampling applied successor is incomplete.");
    }
    workingResult.run_id = persistedAppliedDecisions.run_id;
    workingResult.decision_count = persistedAppliedDecisions.decision_count;
    workingResult.item_count = persistedAppliedDecisions.item_count;
    workingResult.blocker_count = persistedAppliedDecisions.blocker_count;
    workingResult.revision_count = persistedAppliedDecisions.revision_count;
    workingResult.target_update_count =
      persistedAppliedDecisions.target_update_count;
    workingResult.structured_update_count =
      persistedAppliedDecisions.structured_update_count;
    workingResult.native_regeneration_count =
      persistedAppliedDecisions.native_regeneration_count;
    workingResult.native_regenerated_count = reviewIntegerOrZero(
      persistedAppliedDecisions.native_regenerated_count,
    );
    workingResult.application_status =
      persistedAppliedDecisions.application_status;
    workingResult.applied_decisions = persistedAppliedDecisions;
    workingResult.final_artifacts = persistedFinalArtifacts;
    parentState.expectedAppliedDecisions =
      cloneJournalReviewTransactionValue(persistedAppliedDecisions);
  }
  parentState.complete = true;
  return workingResult;
}

function validateJournalAssuredReadState(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir || !journalOutputHasAssuranceManifest(outputDir)) return null;
  const replay = runJournalAssuranceBridge("validate", outputDir);
  const fields = [
    ["run_intake", "run_intake.json"],
    ["review_payload", "review_payload.json"],
    ["ui_decisions", "ui_decisions.json"],
    ["final_artifacts", "final_artifacts.json"],
  ];
  for (const [fieldName, relativePath] of fields) {
    if (inputArgs[fieldName] == null) continue;
    const persisted = readJsonFileIfPresent(
      path.join(outputDir, relativePath),
    );
    if (
      !isPlainObject(persisted) ||
      journalReviewStableJson(inputArgs[fieldName]) !==
        journalReviewStableJson(persisted)
    ) {
      throw new Error(
        `Caller ${fieldName} does not match the persisted Journal Sampling state.`,
      );
    }
  }
  return replay;
}

function initializeJournalReviewTransactionState(state, trustedImage, inputArgs) {
  const persistedRunIntake = journalReviewTransactionJsonFromImage(
    trustedImage,
    "run_intake.json",
  );
  const persistedReviewPayload = journalReviewTransactionJsonFromImage(
    trustedImage,
    "review_payload.json",
  );
  const persistedFinalArtifacts = journalReviewTransactionJsonFromImage(
    trustedImage,
    "final_artifacts.json",
  );
  const persistedUiDecisions = journalReviewTransactionJsonFromImage(
    trustedImage,
    "ui_decisions.json",
  );
  if (
    !isPlainObject(persistedRunIntake) ||
    !isPlainObject(persistedReviewPayload) ||
    !isPlainObject(persistedFinalArtifacts)
  ) {
    throw new Error(
      "Persisted run intake, review payload, and final artifacts are required before Journal Sampling review writes.",
    );
  }
  if (
    journalReviewStableJson(inputArgs.run_intake) !==
    journalReviewStableJson(persistedRunIntake)
  ) {
    throw new Error(
      "Caller run intake does not match the persisted Journal Sampling run intake.",
    );
  }
  if (
    journalReviewStableJson(inputArgs.review_payload) !==
    journalReviewStableJson(persistedReviewPayload)
  ) {
    throw new Error(
      "Caller review payload does not match the persisted Journal Sampling review payload.",
    );
  }
  if (
    inputArgs.final_artifacts != null &&
    journalReviewStableJson(inputArgs.final_artifacts) !==
      journalReviewStableJson(persistedFinalArtifacts)
  ) {
    throw new Error(
      "Caller final artifacts do not match the persisted Journal Sampling final artifacts.",
    );
  }
  if (
    inputArgs.ui_decisions != null &&
    journalReviewStableJson(inputArgs.ui_decisions) !==
      journalReviewStableJson(persistedUiDecisions)
  ) {
    throw new Error(
      "Caller UI decisions do not match the persisted Journal Sampling UI decisions.",
    );
  }
  state.baselinePaths = new Set(
    Array.isArray(trustedImage?.files)
      ? trustedImage.files.map((entry) => entry.path)
      : [],
  );
  state.baselineRunIntake =
    cloneJournalReviewTransactionValue(persistedRunIntake);
  state.persistedRunIntake =
    cloneJournalReviewTransactionValue(persistedRunIntake);
  state.persistedReviewPayload =
    cloneJournalReviewTransactionValue(persistedReviewPayload);
  state.persistedFinalArtifacts =
    cloneJournalReviewTransactionValue(persistedFinalArtifacts);
  state.persistedUiDecisions =
    cloneJournalReviewTransactionValue(persistedUiDecisions);
}

function journalReviewTrustedArgsForWorkingOutput(
  inputArgs,
  workingOutputDir,
  state,
) {
  const trustedArgs = generatedReviewArgsForWorkingOutput(
    inputArgs,
    workingOutputDir,
  );
  trustedArgs.run_intake = {
    ...cloneJournalReviewTransactionValue(state.persistedRunIntake),
    output_dir: workingOutputDir,
  };
  trustedArgs.review_payload = cloneJournalReviewTransactionValue(
    state.persistedReviewPayload,
  );
  trustedArgs.final_artifacts = cloneJournalReviewTransactionValue(
    state.persistedFinalArtifacts,
  );
  if (state.persistedUiDecisions == null) {
    delete trustedArgs.ui_decisions;
  } else {
    trustedArgs.ui_decisions = cloneJournalReviewTransactionValue(
      state.persistedUiDecisions,
    );
  }
  return trustedArgs;
}

function journalReviewParentWritePaths(
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
  if (runIntakePath) paths.add("run_intake.json");
  if (state.expectedReviewHandoffContent != null) {
    paths.add("review_handoff.md");
  }
  return Array.from(paths);
}

function validateJournalParentTransactionState(
  kind,
  state,
  workingOutputDir,
  authorizedWritePaths,
  persistedUiDecisions,
  persistedAppliedDecisions = null,
  persistedFinalArtifacts = null,
) {
  if (!state?.complete) {
    throw new Error("Journal Sampling parent transaction state is incomplete.");
  }
  const expectedAuthorized = [...state.authorizedWritePaths].sort();
  const observedAuthorized = Array.from(authorizedWritePaths).sort();
  if (
    JSON.stringify(expectedAuthorized) !== JSON.stringify(observedAuthorized)
  ) {
    throw new Error("Journal Sampling write authorization did not close.");
  }
  if (
    JSON.stringify(persistedUiDecisions) !==
    JSON.stringify(state.expectedUiDecisions)
  ) {
    throw new Error("Journal Sampling UI receipt did not close.");
  }
  if (kind === "apply") {
    if (
      JSON.stringify(persistedAppliedDecisions) !==
        JSON.stringify(state.expectedAppliedDecisions) ||
      JSON.stringify(persistedFinalArtifacts) !==
        JSON.stringify(state.expectedFinalArtifacts)
    ) {
      throw new Error("Journal Sampling parent application did not close.");
    }
    if (state.expectedRunIntake != null) {
      const persistedRunIntake = readJsonFileIfPresent(
        path.join(workingOutputDir, "run_intake.json"),
      );
      if (
        JSON.stringify(persistedRunIntake) !==
        JSON.stringify(state.expectedRunIntake)
      ) {
        throw new Error("Journal Sampling run receipt did not close.");
      }
    }
    if (state.expectedReviewHandoffContent != null) {
      const handoffPath = path.join(workingOutputDir, "review_handoff.md");
      if (
        !fs.existsSync(handoffPath) ||
        fs.readFileSync(handoffPath, "utf8") !==
          state.expectedReviewHandoffContent
      ) {
        throw new Error("Journal Sampling review handoff did not close.");
      }
    }
  }
}

function validateJournalSamplingReviewTransaction(
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
    throw new Error("Journal Sampling review transaction result is invalid.");
  }
  if (parentState?.assured) {
    const replay = runJournalAssuranceBridge("validate", workingOutputDir);
    if (
      !isPlainObject(replay.output_set) ||
      journalReviewStableJson(replay.output_set.stage) !==
        journalReviewStableJson(parentState.successorStage)
    ) {
      throw new Error("Journal Sampling successor replay did not close.");
    }
  }
  const requiredPaths =
    kind === "save"
      ? ["ui_decisions.json"]
      : ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
  const filePaths = new Set(workingImage.files.map((entry) => entry.path));
  if (!requiredPaths.every((relativePath) => filePaths.has(relativePath))) {
    throw new Error("Journal Sampling review transaction is incomplete.");
  }
  const persistedUiDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "ui_decisions.json"),
  );
  if (!isPlainObject(persistedUiDecisions)) {
    throw new Error("Journal Sampling review transaction is incomplete.");
  }
  if (kind === "save") {
    validateJournalParentTransactionState(
      kind,
      parentState,
      workingOutputDir,
      authorizedWritePaths,
      persistedUiDecisions,
    );
    const expectedResult = {
      ok: true,
      validation_type: "journal_sampling_decisions",
      run_id: persistedUiDecisions?.run_id,
      decision_count: persistedUiDecisions?.decision_count,
      item_count: persistedUiDecisions?.item_count,
      status: persistedUiDecisions?.status,
      persisted: true,
      ui_decisions_path: path.join(
        canonicalOutputDir,
        "ui_decisions.json",
      ),
      message: isSpanishRuntime(inputArgs)
        ? `Se han guardado ${persistedUiDecisions?.decision_count} decisiones de Journal Sampling.`
        : `Saved ${persistedUiDecisions?.decision_count} Journal Sampling decisions.`,
      ui_decisions: persistedUiDecisions,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Journal Sampling saved decisions did not close.");
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
      throw new Error("Journal Sampling review transaction is incomplete.");
    }
    validateJournalParentTransactionState(
      kind,
      parentState,
      workingOutputDir,
      authorizedWritePaths,
      persistedUiDecisions,
      persistedAppliedDecisions,
      persistedFinalArtifacts,
    );
    if (
      JSON.stringify(persistedAppliedDecisions) !==
        JSON.stringify(result.applied_decisions) ||
      JSON.stringify(persistedFinalArtifacts) !==
        JSON.stringify(result.final_artifacts)
    ) {
      throw new Error("Journal Sampling applied decisions did not close.");
    }
    if (
      persistedUiDecisions.run_id !== persistedAppliedDecisions.run_id ||
      persistedUiDecisions.decision_count !==
        persistedAppliedDecisions.decision_count ||
      journalReviewStableJson(persistedUiDecisions.decisions) !==
        journalReviewStableJson(persistedAppliedDecisions.decisions)
    ) {
      throw new Error("Journal Sampling review decision state did not close.");
    }
    const expectedResult = {
      ok: true,
      validation_type: "journal_sampling_application",
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
      message: isSpanishRuntime(inputArgs)
        ? `Se han aplicado ${persistedAppliedDecisions.decision_count} decisiones de Journal Sampling.`
        : `Applied ${persistedAppliedDecisions.decision_count} Journal Sampling decisions.`,
      applied_decisions: persistedAppliedDecisions,
      final_artifacts: persistedFinalArtifacts,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Journal Sampling response did not close.");
    }
  }
}

function workflowReviewTransactionOptions(kind, inputArgs, parentState) {
  return {
    validateWholeTree: (context) =>
      validateJournalSamplingReviewTransaction(
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
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "save",
    inputArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeJournalReviewTransactionState(
        parentState,
        trustedImage,
        inputArgs,
      );
      parentState.assured =
        journalOutputHasAssuranceManifest(workingOutputDir);
      if (parentState.assured) {
        runJournalAssuranceBridge(
          "prepare",
          workingOutputDir,
          "save",
        );
      }
      const workingArgs = journalReviewTrustedArgsForWorkingOutput(
        inputArgs,
        workingOutputDir,
        parentState,
      );
      Object.defineProperty(workingArgs, JOURNAL_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = saveDecisionPayloadWrites(workingArgs);
      if (parentState.assured) {
        refreshJournalAssuredTransactionResult(
          "save",
          workingResult,
          workingOutputDir,
          parentState,
        );
      }
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
        "Journal Sampling review save transaction failed safely.",
      rollbackFailureMessage:
        "Journal Sampling review save transaction could not be restored safely.",
    },
  );
}

function saveDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[JOURNAL_REVIEW_TRANSACTION_STATE] || null;
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
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
    validation_type: "journal_sampling_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? decisionOutputPath : null,
    message: isSpanishRuntime(inputArgs)
      ? persisted
        ? `Se han guardado ${uiDecisions.decision_count} decisiones de Journal Sampling.`
        : "Las decisiones se han validado. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
      : persisted
        ? `Saved ${uiDecisions.decision_count} Journal Sampling decisions.`
        : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneJournalReviewTransactionValue(uiDecisions);
    parentState.authorizedWritePaths = ["ui_decisions.json"];
    parentState.complete = true;
  }
  return result;
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
  const parentState = inputArgs[JOURNAL_REVIEW_TRANSACTION_STATE] || null;
  const runIntakePath = path.join(outputDir, "run_intake.json");
  const current = cloneJournalReviewTransactionValue(
    parentState?.baselineRunIntake,
  ) || readJsonFileIfPresent(runIntakePath) ||
    (isPlainObject(inputArgs.run_intake) ? { ...inputArgs.run_intake } : null);
  if (!current) return null;
  const trace = Array.isArray(current.execution_trace) ? [...current.execution_trace] : [];
  const appliedAt = shortString(appliedDecisions?.applied_at) || new Date().toISOString();
  const stepIdSuffix = appliedAt.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "journal_sampling"}_review_apply_${stepIdSuffix || Date.now()}`,
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
      cloneJournalReviewTransactionValue(updated);
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

function writeDirectTextArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!canDirectlyUpdateTextArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target) continue;
    const stat = generatedReviewPathEntryStat(target.absolutePath);
    if (!stat) continue;
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
      throw new Error("Journal Sampling review target is unsafe.");
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
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const spec = structuredUpdateSpec(effect);
    if (!spec) continue;
    if (!canUpdateStructuredArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target) continue;
    const stat = generatedReviewPathEntryStat(target.absolutePath);
    if (!stat) continue;
    if (stat.isSymbolicLink() || !stat.isFile() || stat.nlink !== 1) {
      throw new Error("Journal Sampling structured review target is unsafe.");
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
  return "review_applied_with_assurance_limits";
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
    const displayName = PLUGIN_MANIFEST.name || pluginName || "Review";
    const text = isSpanishRuntime(inputArgs)
      ? [
          `# ${displayName} · Entrega para revisión`,
          "<!-- Review Handoff -->",
          "",
          "- Payload de revisión: `review_payload.json`",
          "- Datos de ejecución: `run_intake.json`",
          "- Decisiones pendientes: `ui_decisions.json`",
          "- Decisiones aplicadas: `applied_decisions.json`",
          "- Artefactos finales: `final_artifacts.json`",
          "",
          "## Revisión en Codex",
          `1. Valide el payload con \`${TOOL_NAMES.validateReview}\`.`,
          `2. Muestre el panel de revisión con \`${TOOL_NAMES.renderReview}\`.`,
          `3. Guarde las acciones de revisión con \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Aplique las acciones de revisión con \`${TOOL_NAMES.applyDecisions}\`.`,
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
    const handoffContent = `${text}\n`;
    generatedReviewAtomicWriteFileSync(handoffPath, handoffContent, "utf8");
    const parentState = inputArgs[JOURNAL_REVIEW_TRANSACTION_STATE] || null;
    if (parentState) {
      parentState.expectedReviewHandoffContent = handoffContent;
    }
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
      inputArgs,
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

function nextActionsWithReviewApplication(
  currentNextActions,
  appliedDecisions,
  blockers,
  inputArgs = {},
) {
  const nextActions = Array.isArray(currentNextActions) ? [...currentNextActions] : [];
  const spanish = isSpanishRuntime(inputArgs);
  if (blockers.length) {
    nextActions.push(
      spanish
        ? "Resuelva las decisiones de revisión bloqueadas antes de considerar listos los artefactos finales."
        : "Resolve blocked review decisions before treating final artifacts as ready.",
    );
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push(
      spanish
        ? "Vuelva a generar las salidas DOCX/XLSX/PDF nativas antes de la entrega final."
        : "Regenerate native DOCX/XLSX/PDF outputs before final handoff.",
    );
  } else if (
    appliedDecisions.application_status ===
    "review_applied_with_assurance_limits"
  ) {
    nextActions.push(
      spanish
        ? "Use los artefactos solo como muestra revisada; la suficiencia profesional, los informes y la publicación siguen pendientes."
        : "Use the artifacts only as a reviewed sample; professional sufficiency, reporting, and publication remain pending.",
    );
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push(
      spanish
        ? "Complete las decisiones de revisión restantes antes de la entrega final."
        : "Complete remaining review decisions before final handoff.",
    );
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const canonicalOutputDir = resolveRunOutputDir(inputArgs);
  if (!canonicalOutputDir) return applyDecisionPayloadWrites(inputArgs);
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "apply",
    inputArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeJournalReviewTransactionState(
        parentState,
        trustedImage,
        inputArgs,
      );
      parentState.assured =
        journalOutputHasAssuranceManifest(workingOutputDir);
      if (parentState.assured) {
        runJournalAssuranceBridge(
          "prepare",
          workingOutputDir,
          "apply",
        );
      }
      const workingArgs = journalReviewTrustedArgsForWorkingOutput(
        inputArgs,
        workingOutputDir,
        parentState,
      );
      Object.defineProperty(workingArgs, JOURNAL_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = applyDecisionPayloadWrites(workingArgs);
      if (parentState.assured) {
        refreshJournalAssuredTransactionResult(
          "apply",
          workingResult,
          workingOutputDir,
          parentState,
        );
      }
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
        "Journal Sampling review apply transaction failed safely.",
      rollbackFailureMessage:
        "Journal Sampling review apply transaction could not be restored safely.",
    },
  );
}

function applyDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[JOURNAL_REVIEW_TRANSACTION_STATE] || null;
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
  const applicationStatus = parentState?.assured
    ? "successor_pending"
    : statusFromEffects(effects, reviewPayload.items.length);
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
    validation_type: "journal_sampling_application",
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
    message: isSpanishRuntime(inputArgs)
      ? persisted
        ? `Se han aplicado ${responseAppliedDecisions.decision_count} decisiones de Journal Sampling.`
        : "Las decisiones aplicadas se han validado. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
      : persisted
        ? `Applied ${responseAppliedDecisions.decision_count} Journal Sampling decisions.`
        : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneJournalReviewTransactionValue(uiDecisions);
    parentState.expectedAppliedDecisions =
      cloneJournalReviewTransactionValue(responseAppliedDecisions);
    parentState.expectedFinalArtifacts =
      cloneJournalReviewTransactionValue(responseFinalArtifacts);
    parentState.authorizedWritePaths = journalReviewParentWritePaths(
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

function applyWorkflowSpecificReviewApplication(
  _outputDir,
  _appliedOutputPath,
  _finalArtifactsPath,
) {
  return null;
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    validateJournalAssuredReadState(args);
    const payload = validateReviewPayload(args);
    return {
      ok: true,
      validation_type: "journal_sampling_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: isSpanishRuntime(args)
        ? "El payload de revisión de Journal Sampling es válido. Ya puede llamar una vez a render_journal_sampling_review."
        : "Journal Sampling review payload is valid. It is safe to call render_journal_sampling_review once.",
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.renderReview) {
    validateJournalAssuredReadState(args);
    return validateReviewPayload(args);
  }
  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(`unknown Journal Sampling widget tool: ${name}`);
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
      return rpcResponse(messageId, {
        protocolVersion: params.protocolVersion || "2024-11-05",
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: {
          tools: {},
          resources: {},
          prompts: {},
        },
        instructions: isSpanishRuntime(params)
          ? "Use validate_journal_sampling_review antes de render_journal_sampling_review. Prefiera el widget MCP para la entrega de revisión de Journal Sampling; use save_journal_sampling_decisions para guardar las acciones del revisor en ui_decisions.json y apply_journal_sampling_decisions para escribir applied_decisions.json y el estado de final_artifacts.json cuando se recopilen decisiones; recurra a la revisión Markdown/estática solo si MCP no está disponible."
          : "Use validate_journal_sampling_review before render_journal_sampling_review. Prefer the MCP widget for Journal Sampling review handoff; use save_journal_sampling_decisions to persist reviewer actions to ui_decisions.json and apply_journal_sampling_decisions to write applied_decisions.json plus final_artifacts.json status when decisions are collected; fall back to Markdown/static review only when MCP is unavailable.",
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") return rpcResponse(messageId, { tools: toolDefinitions() });
    if (method === "tools/call") {
      const { name, arguments: args } = params;
      if (typeof name !== "string") {
        return rpcError(messageId, -32602, "tools/call requires a tool name");
      }
      if (!isPlainObject(args)) {
        return rpcError(messageId, -32602, "tools/call arguments must be an object");
      }
      try {
        return rpcResponse(messageId, toolResult(callTool(name, args), name));
      } catch (error) {
        return rpcResponse(
          messageId,
          toolError(localizedValidationError(error, args)),
        );
      }
    }
    if (method === "resources/list") return rpcResponse(messageId, { resources: resources() });
    if (method === "resources/read") {
      const { uri } = params;
      if (typeof uri !== "string") {
        return rpcError(messageId, -32602, "resources/read requires a resource uri");
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
    return rpcError(messageId, -32601, `method not found: ${method}`);
  } catch (error) {
    return rpcError(
      messageId,
      -32000,
      error instanceof Error ? error.message : String(error),
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

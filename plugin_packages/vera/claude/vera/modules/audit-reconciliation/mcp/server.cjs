"use strict";

const crypto = require("node:crypto");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const IMPLEMENTATION_CONTRACT = [
  ["plugin", "assets/audit-reconciliation-review-widget.html"],
  ["plugin", "assets/icon.svg"],
  ["plugin", "assets/review-workbench-adapter.json"],
  ["plugin", "mcp/server.cjs"],
  ["plugin", "scripts/audit_assurance.py"],
  ["plugin", "scripts/build_missing_evidence_requests.py"],
  ["plugin", "scripts/build_review_sample.py"],
  ["plugin", "scripts/check_dependencies.py"],
  ["plugin", "scripts/implementation_bootstrap.py"],
  ["plugin", "scripts/raw_input_runner.py"],
  ["plugin", "scripts/reconciliation_workflow.py"],
  ["plugin", "scripts/retained_sources/accountant_report.source"],
  ["plugin", "scripts/retained_sources/locale_support.source"],
  ["plugin", "scripts/retained_sources/reconciliation_helpers.source"],
  ["plugin", "scripts/retained_sources/review_session.source"],
  ["plugin", "scripts/retained_sources/workpaper_outputs.source"],
  ["plugin", "scripts/review_server.py"],
  ["shared_assurance", "__init__.py"],
  ["shared_assurance", "contracts.py"],
  ["shared_assurance", "decisions.py"],
  ["shared_assurance", "envelope.py"],
  ["shared_assurance", "money.py"],
  ["shared_assurance", "relationships.py"],
  ["shared_assurance", "review_output_transaction.cjs"],
  ["shared_assurance", "serialization.py"],
];

function realDirectory(target) {
  try {
    const current = fs.lstatSync(target);
    return current.isDirectory() && !current.isSymbolicLink();
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

function sharedAssuranceRoot() {
  const candidates = [
    path.join(PLUGIN_ROOT, "vendor", "modules", "vera_assurance"),
    path.join(
      path.dirname(path.dirname(PLUGIN_ROOT)),
      "vendor",
      "modules",
      "vera_assurance",
    ),
    path.join(
      path.dirname(PLUGIN_ROOT),
      "_shared",
      "vendor",
      "modules",
      "vera_assurance",
    ),
  ];
  const selected = candidates.find(realDirectory);
  if (!selected) {
    throw new Error("The required vera_assurance module is not available.");
  }
  return path.resolve(selected);
}

function implementationKey(rootId, relativePath) {
  return `${rootId}\u0000${relativePath}`;
}

function expectedImplementationDirectories() {
  const expected = new Set();
  for (const [rootId, relativePath] of IMPLEMENTATION_CONTRACT) {
    let parent = path.posix.dirname(relativePath);
    while (parent !== ".") {
      expected.add(implementationKey(rootId, parent));
      parent = path.posix.dirname(parent);
    }
  }
  return expected;
}

function scanImplementationTree(rootId, root, scanRoot, files, directories) {
  const rootStat = fs.lstatSync(scanRoot);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("implementation root must be a real directory");
  }
  const pending = [scanRoot];
  const initialRelative = path.relative(root, scanRoot).split(path.sep).join("/");
  if (initialRelative && initialRelative !== ".") {
    directories.add(implementationKey(rootId, initialRelative));
  }
  while (pending.length) {
    const directory = pending.pop();
    for (const name of fs.readdirSync(directory).sort()) {
      const candidate = path.join(directory, name);
      const current = fs.lstatSync(candidate);
      const relative = path.relative(root, candidate).split(path.sep).join("/");
      if (current.isSymbolicLink()) {
        throw new Error("implementation entries must not be symlinks");
      }
      if (current.isDirectory()) {
        directories.add(implementationKey(rootId, relative));
        pending.push(candidate);
      } else if (current.isFile() && current.nlink === 1) {
        files.add(implementationKey(rootId, relative));
      } else {
        throw new Error(
          "implementation files must be ordinary single-link regular files",
        );
      }
    }
  }
}

function setEquals(left, right) {
  return left.size === right.size && [...left].every((item) => right.has(item));
}

function validateImplementationTree() {
  const sharedRoot = sharedAssuranceRoot();
  const files = new Set();
  const directories = new Set();
  for (const [rootId, root, scanRoot] of [
    ["plugin", PLUGIN_ROOT, path.join(PLUGIN_ROOT, "assets")],
    ["plugin", PLUGIN_ROOT, path.join(PLUGIN_ROOT, "mcp")],
    ["plugin", PLUGIN_ROOT, path.join(PLUGIN_ROOT, "scripts")],
    ["shared_assurance", sharedRoot, sharedRoot],
  ]) {
    scanImplementationTree(rootId, root, scanRoot, files, directories);
  }
  const expectedFiles = new Set(
    IMPLEMENTATION_CONTRACT.map(([rootId, relativePath]) =>
      implementationKey(rootId, relativePath),
    ),
  );
  if (!setEquals(files, expectedFiles)) {
    throw new Error(
      "implementation filesystem does not match the exact 25-file contract",
    );
  }
  if (!setEquals(directories, expectedImplementationDirectories())) {
    throw new Error("implementation directories do not match the exact contract");
  }
}

// This must run before any local manifest, asset, or transaction-runtime read.
validateImplementationTree();

const SERVER_NAME = "audit-reconciliation-widgets";
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/audit-reconciliation-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const TOOL_NAMES = {
  validateReview: "validate_audit_reconciliation_review",
  renderReview: "render_audit_reconciliation_review",
  saveDecisions: "save_audit_reconciliation_decisions",
  applyDecisions: "apply_audit_reconciliation_decisions",
};
const WIDGET_TOOL_URIS = {
  [TOOL_NAMES.renderReview]: WIDGET_URI,
};
const WIDGET_TOOL_VISIBILITY = {
  [TOOL_NAMES.renderReview]: ["model"],
};
const TOOL_INVOCATION_LABELS = {
  [TOOL_NAMES.renderReview]: {
    invoking: "Rendering Audit Reconciliation review",
    invoked: "Rendered Audit Reconciliation review",
  },
};
const WIDGET_DESCRIPTION =
  "Interactive Audit Reconciliation review surface for deterministic row checks, exceptions, missing evidence, workpaper artifacts, and follow-up requests.";
const SERVER_INSTRUCTIONS = [
  "For a normal Audit Reconciliation run, the primary visible handoff is the",
  "local browser review server from scripts/review_server.py plus the mandatory",
  "artifact_card.md in the output folder. State the localhost URL explicitly to",
  "the reviewer.",
  "This MCP server remains an optional integrated professional review surface. When",
  "using it, call validate_audit_reconciliation_review with the complete review",
  "payload, or pass local run output paths such as review_payload_path and",
  "run_intake_path to avoid inlining large JSON, before",
  "render_audit_reconciliation_review. The render tool returns",
  "openai/outputTemplate for ui://widget/audit-reconciliation-review.html.",
  "Use save_audit_reconciliation_decisions to persist",
  "reviewer actions to ui_decisions.json and apply_audit_reconciliation_decisions",
  "to write applied_decisions.json plus final_artifacts.json status when",
  "decisions are collected. Use review_ui.html only as a static fallback when",
  "the local browser server cannot start or the browser cannot be opened; static",
  "HTML can copy or download JSON but cannot persist decisions by itself.",
].join(" ");
const SERVER_INSTRUCTIONS_ES = [
  "En una ejecución normal de Audit Reconciliation, la entrega visible principal es el",
  "servidor local de revisión de scripts/review_server.py junto con el archivo obligatorio",
  "artifact_card.md de la carpeta de salida. Indique expresamente la URL localhost al revisor.",
  "Este servidor MCP sigue siendo una superficie integrada opcional de revisión en Claude.",
  "Cuando lo use, llame a validate_audit_reconciliation_review con el payload completo de revisión",
  "o proporcione rutas locales de la ejecución, como review_payload_path y run_intake_path, antes de",
  "render_audit_reconciliation_review. Use save_audit_reconciliation_decisions para guardar las",
  "acciones del revisor en ui_decisions.json y apply_audit_reconciliation_decisions para escribir",
  "applied_decisions.json y el estado de final_artifacts.json. Use review_ui.html solo como alternativa",
  "estática si no se puede iniciar el servidor local o abrir el navegador.",
].join(" ");
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
  "closure_evidence_review",
  "probable_payment_review",
  "missing_evidence_review",
  "unresolved_item",
  "manual_review",
  "review_exception",
  "check_exception",
  "workpaper_artifact",
  "report_artifact",
  "evidence_request_artifact",
  "review_artifact",
]);
const REQUIRED_REVIEW_ITEM_TYPES = new Set([
  "closure_evidence_review",
  "probable_payment_review",
  "manual_review",
  "review_exception",
  "check_exception",
]);

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
  const ui = { resourceUri };
  const visibility = WIDGET_TOOL_VISIBILITY[toolName || ""];
  if (visibility) ui.visibility = visibility;
  const meta = {
    ui,
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  const invocationLabels = TOOL_INVOCATION_LABELS[toolName];
  if (invocationLabels != null) {
    meta["openai/toolInvocation/invoking"] = invocationLabels.invoking;
    meta["openai/toolInvocation/invoked"] = invocationLabels.invoked;
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    "openai/widgetDescription": WIDGET_DESCRIPTION,
    "openai/widgetPrefersBorder": false,
    "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
    ui: {
      prefersBorder: false,
      csp: { connectDomains: [], resourceDomains: [], frameDomains: [] },
    },
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
      client_engagement: {
        type: "string",
        description: "Absolute path to the current portable customer-run context.json.",
      },
      run_intake: {
        type: "object",
        description: "Optional run_intake.json object.",
      },
      run_intake_path: {
        type: "string",
        description: "Optional local path to run_intake.json in the run output folder.",
      },
      review_payload: reviewPayload,
      review_payload_path: {
        type: "string",
        description:
          "Optional local path to review_payload.json. Use this instead of inlining large payloads.",
      },
      ui_decisions: {
        type: "object",
        description: "Optional ui_decisions.json object.",
      },
      ui_decisions_path: {
        type: "string",
        description: "Optional local path to ui_decisions.json in the run output folder.",
      },
      final_artifacts: {
        type: "object",
        description: "Optional final_artifacts.json object.",
      },
      final_artifacts_path: {
        type: "string",
        description: "Optional local path to final_artifacts.json in the run output folder.",
      },
    },
    [],
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
      client_engagement: {
        type: "string",
        description: "Absolute path to the current portable customer-run context.json; required for persistence.",
      },
      run_intake: { type: "object", description: "Optional run_intake.json object with output_dir for persistence." },
      run_intake_path: { type: "string", description: "Optional local path to run_intake.json for persistence." },
      review_payload: reviewPayload,
      review_payload_path: { type: "string", description: "Optional local path to review_payload.json." },
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      ui_decisions_path: { type: "string", description: "Optional local path to ui_decisions.json." },
      final_artifacts: { type: "object", description: "Optional final_artifacts.json object." },
      final_artifacts_path: { type: "string", description: "Optional local path to final_artifacts.json." },
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: { type: "string", description: "Optional reviewer name or role." },
      expected_predecessor_checkpoint: {
        type: "string",
        pattern: "^[0-9a-f]{64}$",
        description:
          "SHA-256 predecessor checkpoint retained outside the mutable run tree. Its authority depends on that separate channel.",
      },
    },
    ["client_engagement", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validateReview,
      title: "Validate Audit Reconciliation review payload",
      description:
        "Validate the Audit Reconciliation review-session payload before optional MCP rendering. Call this first, then render_audit_reconciliation_review when using the integrated Claude surface.",
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
      title: "Render Audit Reconciliation review",
      description:
        "Render an Audit Reconciliation review-session payload as an optional MCP app for row review, checks, evidence requests, and artifacts. The normal visible handoff is the local browser server from scripts/review_server.py; call validate_audit_reconciliation_review first when using this integrated Claude surface.",
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
      title: "Save Audit Reconciliation review decisions",
      description:
        "Validate Audit Reconciliation review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
      title: "Apply Audit Reconciliation review decisions",
      description:
        "Validate Audit Reconciliation review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
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
      name: "audit_reconciliation_review_widget",
      title: "Audit Reconciliation review widget",
      description: WIDGET_DESCRIPTION,
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) {
  throw new Error(`unknown Audit Reconciliation widget resource: ${uri}`);
  }
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "audit-reconciliation-review-widget.html"),
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

function isPathInside(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function resolveLocalJsonPath(value, fieldPath, baseDir = null) {
  const text = boundedOptionalString(value, fieldPath);
  if (!text) return null;
  return path.resolve(baseDir || process.cwd(), text);
}

function readJsonObjectFromLocalPath(filePath, fieldPath) {
  if (!filePath || !fs.existsSync(filePath)) {
    throw new Error(`${fieldPath} does not exist: ${filePath}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error(
      `${fieldPath} must point to readable JSON: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
  if (!isPlainObject(parsed)) {
    throw new Error(`${fieldPath} must contain a JSON object`);
  }
  return parsed;
}

function outputDirFromRunIntake(runIntake, inputArgs) {
  return resolveRunOutputDir({ ...inputArgs, run_intake: runIntake });
}

function ensurePathInsideOutput(filePath, outputDir, fieldPath) {
  if (!outputDir) return;
  if (!isPathInside(filePath, outputDir)) {
    throw new Error(`${fieldPath} must be inside run_intake.output_dir: ${filePath}`);
  }
}

function materializeInputArgs(inputArgs) {
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const args = { ...inputArgs };
  const loadedPaths = [];
  let outputDir = null;

  const runIntakePath = resolveLocalJsonPath(args.run_intake_path, "run_intake_path");
  if (runIntakePath) {
    args.run_intake = readJsonObjectFromLocalPath(runIntakePath, "run_intake_path");
    loadedPaths.push(["run_intake_path", runIntakePath]);
    outputDir = outputDirFromRunIntake(args.run_intake, args) || path.dirname(runIntakePath);
  } else if (isPlainObject(args.run_intake)) {
    outputDir = outputDirFromRunIntake(args.run_intake, args);
  }

  const reviewPayloadPath = resolveLocalJsonPath(
    args.review_payload_path,
    "review_payload_path",
    outputDir,
  );
  if (reviewPayloadPath) {
    args.review_payload = readJsonObjectFromLocalPath(
      reviewPayloadPath,
      "review_payload_path",
    );
    loadedPaths.push(["review_payload_path", reviewPayloadPath]);
    if (!outputDir) outputDir = path.dirname(reviewPayloadPath);
  }

  if (!isPlainObject(args.run_intake) && outputDir) {
    const defaultRunIntakePath = path.join(outputDir, "run_intake.json");
    if (fs.existsSync(defaultRunIntakePath)) {
      args.run_intake = readJsonObjectFromLocalPath(
        defaultRunIntakePath,
        "run_intake_path",
      );
      loadedPaths.push(["run_intake_path", defaultRunIntakePath]);
      outputDir = outputDirFromRunIntake(args.run_intake, args) || outputDir;
    }
  }
  if (!isPlainObject(args.review_payload) && outputDir) {
    const defaultReviewPayloadPath = path.join(outputDir, "review_payload.json");
    if (fs.existsSync(defaultReviewPayloadPath)) {
      args.review_payload = readJsonObjectFromLocalPath(
        defaultReviewPayloadPath,
        "review_payload_path",
      );
      loadedPaths.push(["review_payload_path", defaultReviewPayloadPath]);
    }
  }

  for (const [fieldPath, filePath] of loadedPaths) {
    ensurePathInsideOutput(filePath, outputDir, fieldPath);
  }

  function materializeOptionalJson(objectField, pathField, defaultName) {
    const explicitPath = resolveLocalJsonPath(args[pathField], pathField, outputDir);
    if (explicitPath) {
      ensurePathInsideOutput(explicitPath, outputDir, pathField);
      args[objectField] = readJsonObjectFromLocalPath(explicitPath, pathField);
      return;
    }
    if (!isPlainObject(args[objectField]) && outputDir) {
      const defaultPath = path.join(outputDir, defaultName);
      if (fs.existsSync(defaultPath)) {
        args[objectField] = readJsonFileIfPresent(defaultPath);
      }
    }
  }

  materializeOptionalJson("ui_decisions", "ui_decisions_path", "ui_decisions.json");
  materializeOptionalJson(
    "final_artifacts",
    "final_artifacts_path",
    "final_artifacts.json",
  );

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
  const args = materializeInputArgs(inputArgs);
  const reviewPayload = args.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.plugin !== "audit-reconciliation") {
    throw new Error('review_payload.plugin must be "audit-reconciliation"');
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
    widget_type: "audit_reconciliation_review",
    client_engagement:
      typeof args.client_engagement === "string" ? args.client_engagement : null,
    run_intake: isPlainObject(args.run_intake) ? args.run_intake : null,
    review_payload: reviewPayload,
    ui_decisions: isPlainObject(args.ui_decisions)
      ? args.ui_decisions
      : null,
    final_artifacts: isPlainObject(args.final_artifacts)
      ? args.final_artifacts
      : null,
    decision_policy: {
      save_tool: TOOL_NAMES.saveDecisions,
      apply_tool: TOOL_NAMES.applyDecisions,
      can_persist: Boolean(resolveDecisionOutputPath(args)),
      fallback: "copy_json",
    },
  };
  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
    throw new Error(
      `Audit Reconciliation widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`,
    );
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
  const args = materializeInputArgs(inputArgs);
  const payload = validateReviewPayload(args);
  const reviewPayload = payload.review_payload;
  const runIntake = payload.run_intake;
  if (runIntake?.run_id != null && runIntake.run_id !== reviewPayload.run_id) {
    throw new Error("run_intake.run_id must match review_payload.run_id");
  }
  if (!Array.isArray(args.decisions)) throw new Error("decisions must be an array");
  if (args.decisions.length > reviewPayload.items.length) {
    throw new Error("decisions cannot exceed review_payload.items.length");
  }
  const decidedAt = new Date().toISOString();
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const seenIds = new Set();
  const decisions = args.decisions.map((decision, index) =>
    normalizeDecision(decision, itemById, seenIds, decidedAt, index),
  );
  const decisionSource =
    boundedOptionalString(args.decision_source, "decision_source") || "mcp_widget";
  const reviewer = boundedOptionalString(args.reviewer, "reviewer");
  const currentUiDecisions = isPlainObject(args.ui_decisions) ? args.ui_decisions : null;
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
    decisionOutputPath: resolveDecisionOutputPath(args),
    materializedArgs: args,
    validationPayload: payload,
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
      (key) => JSON.stringify(result[key]) === JSON.stringify(expected[key]),
    )
  );
}

const AUDIT_REVIEW_TRANSACTION_STATE = Symbol(
  "audit-review-transaction-state",
);

function cloneAuditReviewTransactionValue(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function auditReviewTransactionJsonFromImage(image, relativePath) {
  const entry = image?.files?.find((candidate) => candidate.path === relativePath);
  if (!entry) return null;
  try {
    const parsed = JSON.parse(entry.payload.toString("utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function auditReviewStableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((entry) => auditReviewStableJson(entry)).join(",")}]`;
  }
  if (isPlainObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) => `${JSON.stringify(key)}:${auditReviewStableJson(value[key])}`,
      )
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function auditReviewCanonicalSha256(value) {
  return crypto
    .createHash("sha256")
    .update(auditReviewStableJson(value), "utf8")
    .digest("hex");
}

function auditReviewPythonCandidates() {
  const candidates = [
    process.env.AUDIT_RECONCILIATION_PYTHON,
    process.env.VIRTUAL_ENV
      ? path.join(
          process.env.VIRTUAL_ENV,
          process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
        )
      : null,
    path.resolve(
      PLUGIN_ROOT,
      "..",
      "..",
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    ),
    path.resolve(
      process.cwd(),
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    ),
    process.platform === "win32" ? "python.exe" : "python3",
    process.platform === "win32" ? "py.exe" : "python",
  ];
  return Array.from(
    new Set(candidates.filter((candidate) => typeof candidate === "string" && candidate)),
  );
}

function auditReviewCustomerRunPaths(outputDir) {
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    let observed = null;
    try {
      observed = fs.lstatSync(contextPath);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw new Error("Customer-run context is unavailable.");
      }
    }
    if (
      observed?.isFile() &&
      !observed.isSymbolicLink() &&
      observed.nlink === 1
    ) {
      return {
        contextPath,
        persistentOutputDir: path.join(candidate, "outputs"),
      };
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) {
      throw new Error("Customer-run context is unavailable.");
    }
    candidate = parent;
  }
}

function auditReviewPythonBridge(command, outputDir, ...args) {
  const scriptPath = path.join(
    PLUGIN_ROOT,
    "scripts",
    "audit_assurance.py",
  );
  const customerRun = auditReviewCustomerRunPaths(outputDir);
  for (const executable of auditReviewPythonCandidates()) {
    const replay = childProcess.spawnSync(
      executable,
      [
        "-I",
        "-B",
        scriptPath,
        "--client-engagement",
        customerRun.contextPath,
        "--persistent-output-dir",
        customerRun.persistentOutputDir,
        command,
        outputDir,
        ...args,
      ],
      {
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
        timeout: 120_000,
        windowsHide: true,
      },
    );
    if (replay.error?.code === "ENOENT") continue;
    if (replay.error || replay.status !== 0) {
      throw new Error("Complete assurance replay failed.");
    }
    let payload;
    try {
      payload = JSON.parse(replay.stdout);
    } catch {
      throw new Error("Complete assurance replay failed.");
    }
    if (
      !isPlainObject(payload) ||
      payload.ok !== true
    ) {
      throw new Error("Complete assurance replay failed.");
    }
    return payload;
  }
  throw new Error("Complete assurance replay runtime is unavailable.");
}

function auditReviewReplayAssuranceWithPython(
  outputDir,
  expectedPredecessorCheckpoint,
) {
  const bridgeArgs = [];
  if (expectedPredecessorCheckpoint) {
    bridgeArgs.push(
      "--expected-predecessor-checkpoint",
      expectedPredecessorCheckpoint,
    );
  }
  const payload = auditReviewPythonBridge(
    "validate-run-json",
    outputDir,
    ...bridgeArgs,
  );
  if (
    !isPlainObject(payload.assurance) ||
    !isPlainObject(payload.result)
  ) {
    throw new Error("Complete assurance replay failed.");
  }
  return payload;
}

function auditReviewRequireMatchingCustomerRun(inputArgs, outputDir) {
  const boundary = auditReviewPythonBridge(
    "validate-context-json",
    outputDir,
  );
  const persistedRunIntake = readJsonFileIfPresent(
    path.join(outputDir, "run_intake.json"),
  );
  const persistedReviewPayload = readJsonFileIfPresent(
    path.join(outputDir, "review_payload.json"),
  );
  const authorities = [
    persistedRunIntake,
    persistedReviewPayload,
    inputArgs.run_intake,
    inputArgs.review_payload,
  ];
  if (
    typeof boundary.run_id !== "string" ||
    authorities.some(
      (authority) =>
        !isPlainObject(authority) ||
        authority.run_id !== boundary.run_id,
    )
  ) {
    throw new Error(
      "Audit Reconciliation review run does not match the customer-run context.",
    );
  }
  return boundary;
}

function auditReviewReplayAssurance(
  outputDir,
  decisionFingerprint,
  expectedPredecessorCheckpoint,
) {
  const replay = auditReviewReplayAssuranceWithPython(
    outputDir,
    expectedPredecessorCheckpoint,
  );
  const assurance = replay.assurance;
  const gates = assurance.gate_register;
  const authority = assurance.professional_review_authority;
  const result = replay.result;
  const semantic = gates?.gates?.semantic_review;
  const reporting = gates?.gates?.reporting;
  const reportReady =
    gates.report_ready === true &&
    ["passed", "not_applicable"].includes(semantic?.status) &&
    reporting?.status === "passed";
  const successorReplayed =
    reportReady &&
    authority.origin === "applied_decisions" &&
    authority.decision_fingerprint === decisionFingerprint;
  return {
    assurance,
    authority,
    result,
    reportReady,
    successorReplayed,
  };
}

function auditReviewDecisionFingerprint(reviewPayload, effects) {
  const itemById = new Map(
    (reviewPayload.items || [])
      .filter((item) => isPlainObject(item) && shortString(item.id))
      .map((item) => [String(item.id), item]),
  );
  const records = effects.map((effect) => {
    const item = itemById.get(String(effect.item_id)) || {};
    const data = isPlainObject(item.data) ? item.data : {};
    let recordId = shortString(data.record_id);
    if (!recordId && shortString(data.target_id_field) === "record_id") {
      recordId = shortString(data.target_record_id);
    }
    return {
      item_id: effect.item_id ?? null,
      record_id: recordId || null,
      action: effect.action ?? null,
      edit_value: effect.edit_value ?? null,
      requested_documents: Array.isArray(effect.requested_documents)
        ? effect.requested_documents
        : [],
    };
  });
  records.sort((left, right) =>
    String(left.item_id) < String(right.item_id)
      ? -1
      : String(left.item_id) > String(right.item_id)
        ? 1
        : 0,
  );
  return auditReviewCanonicalSha256({
    run_id: reviewPayload.run_id ?? null,
    decisions: records,
  });
}

function auditReviewProfessionalAuthority(
  reviewPayload,
  effects,
  reviewer,
  decisionFingerprint,
  replay,
) {
  const currentRecords = Array.isArray(replay.authority?.records)
    ? replay.authority.records
    : [];
  const metadataById = new Map(
    currentRecords
      .filter((record) => isPlainObject(record) && shortString(record.record_id))
      .map((record) => [String(record.record_id), record]),
  );
  const expectedIds = (replay.result.reconciliation_rows || [])
    .filter(
      (record) =>
        isPlainObject(record) &&
        shortString(record.record_id) &&
        shortString(record.reconciliation_status).toLowerCase() !==
          "out_of_scope",
    )
    .map((record) => String(record.record_id));
  if (new Set(expectedIds).size !== expectedIds.length) {
    throw new Error("Professional review source-row identities are not unique.");
  }
  const itemById = new Map(
    (reviewPayload.items || [])
      .filter((item) => isPlainObject(item) && shortString(item.id))
      .map((item) => [String(item.id), item]),
  );
  const effectByRecord = new Map();
  for (const effect of effects) {
    const item = itemById.get(String(effect.item_id)) || {};
    const data = isPlainObject(item.data) ? item.data : {};
    let recordId = shortString(data.record_id);
    if (!recordId && shortString(data.target_id_field) === "record_id") {
      recordId = shortString(data.target_record_id);
    }
    if (!recordId) continue;
    if (effectByRecord.has(recordId)) {
      throw new Error(
        `Professional review has duplicate decisions for ${recordId}.`,
      );
    }
    effectByRecord.set(recordId, effect);
  }
  const records = expectedIds.map((recordId) => {
    const prior = metadataById.get(recordId);
    if (!prior) {
      throw new Error(
        `Professional review authority omits source row ${recordId}.`,
      );
    }
    const action = effectByRecord.get(recordId)?.action;
    return {
      record_id: recordId,
      review_status:
        action === "accept" ? "PASS" : action === "reject" ? "FAIL" : "UNRESOLVED",
      reviewer_ref: reviewer || prior.reviewer_ref || "reviewer.local",
      reviewed_on:
        prior.reviewed_on || String(replay.assurance.run_date || "").slice(0, 10),
    };
  });
  const content = {
    schema_version: "audit_reconciliation.professional_review.v1",
    origin: "applied_decisions",
    run_id: shortString(reviewPayload.run_id) || null,
    records,
    reviewer_ref_trust: "unsigned_untrusted_label",
    decision_fingerprint: decisionFingerprint,
    predecessor_assurance_sha256: replay.assurance.content_sha256,
  };
  return {
    ...content,
    content_sha256: auditReviewCanonicalSha256(content),
  };
}

function initializeAuditReviewTransactionState(state, trustedImage, inputArgs) {
  const persistedRunIntake = auditReviewTransactionJsonFromImage(
    trustedImage,
    "run_intake.json",
  );
  const persistedReviewPayload = auditReviewTransactionJsonFromImage(
    trustedImage,
    "review_payload.json",
  );
  const persistedFinalArtifacts = auditReviewTransactionJsonFromImage(
    trustedImage,
    "final_artifacts.json",
  );
  const persistedUiDecisions = auditReviewTransactionJsonFromImage(
    trustedImage,
    "ui_decisions.json",
  );
  if (
    !isPlainObject(persistedRunIntake) ||
    !isPlainObject(persistedReviewPayload) ||
    !isPlainObject(persistedFinalArtifacts)
  ) {
    throw new Error(
      "Persisted run intake, review payload, and final artifacts are required before Audit Reconciliation review writes.",
    );
  }
  if (
    auditReviewStableJson(inputArgs.run_intake) !==
    auditReviewStableJson(persistedRunIntake)
  ) {
    throw new Error(
      "Caller run intake does not match the persisted Audit Reconciliation run intake.",
    );
  }
  if (
    auditReviewStableJson(inputArgs.review_payload) !==
    auditReviewStableJson(persistedReviewPayload)
  ) {
    throw new Error(
      "Caller review payload does not match the persisted Audit Reconciliation review payload.",
    );
  }
  if (
    inputArgs.final_artifacts != null &&
    auditReviewStableJson(inputArgs.final_artifacts) !==
      auditReviewStableJson(persistedFinalArtifacts)
  ) {
    throw new Error(
      "Caller final artifacts do not match the persisted Audit Reconciliation final artifacts.",
    );
  }
  if (
    inputArgs.ui_decisions != null &&
    auditReviewStableJson(inputArgs.ui_decisions) !==
      auditReviewStableJson(persistedUiDecisions)
  ) {
    throw new Error(
      "Caller UI decisions do not match the persisted Audit Reconciliation UI decisions.",
    );
  }
  state.baselinePaths = new Set(
    Array.isArray(trustedImage?.files)
      ? trustedImage.files.map((entry) => entry.path)
      : [],
  );
  state.baselineRunIntake =
    cloneAuditReviewTransactionValue(persistedRunIntake);
  state.persistedRunIntake =
    cloneAuditReviewTransactionValue(persistedRunIntake);
  state.persistedReviewPayload =
    cloneAuditReviewTransactionValue(persistedReviewPayload);
  state.persistedFinalArtifacts =
    cloneAuditReviewTransactionValue(persistedFinalArtifacts);
  state.persistedUiDecisions =
    cloneAuditReviewTransactionValue(persistedUiDecisions);
}

function auditReviewTrustedArgsForWorkingOutput(
  inputArgs,
  workingOutputDir,
  state,
) {
  const trustedArgs = generatedReviewArgsForWorkingOutput(
    inputArgs,
    workingOutputDir,
  );
  trustedArgs.run_intake = {
    ...cloneAuditReviewTransactionValue(state.persistedRunIntake),
    output_dir: workingOutputDir,
  };
  trustedArgs.review_payload = cloneAuditReviewTransactionValue(
    state.persistedReviewPayload,
  );
  trustedArgs.final_artifacts = cloneAuditReviewTransactionValue(
    state.persistedFinalArtifacts,
  );
  if (state.persistedUiDecisions == null) {
    delete trustedArgs.ui_decisions;
  } else {
    trustedArgs.ui_decisions = cloneAuditReviewTransactionValue(
      state.persistedUiDecisions,
    );
  }
  return trustedArgs;
}

function auditReviewParentWritePaths(
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
  if (state.expectedProfessionalReview != null) {
    paths.add("professional_review.json");
  }
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
  for (const relativePath of state.expectedTransitionHistoryPaths || []) {
    paths.add(generatedReviewCanonicalRelativePath(relativePath));
  }
  return Array.from(paths);
}

function validateAuditParentTransactionState(
  kind,
  state,
  workingOutputDir,
  authorizedWritePaths,
  persistedUiDecisions,
  persistedAppliedDecisions = null,
  persistedFinalArtifacts = null,
) {
  if (!state?.complete) {
    throw new Error("Audit Reconciliation parent transaction state is incomplete.");
  }
  const expectedAuthorized = [...state.authorizedWritePaths].sort();
  const observedAuthorized = Array.from(authorizedWritePaths).sort();
  if (
    JSON.stringify(expectedAuthorized) !== JSON.stringify(observedAuthorized)
  ) {
    throw new Error("Audit Reconciliation write authorization did not close.");
  }
  if (
    JSON.stringify(persistedUiDecisions) !==
    JSON.stringify(state.expectedUiDecisions)
  ) {
    throw new Error("Audit Reconciliation UI receipt did not close.");
  }
  if (kind === "apply") {
    if (
      JSON.stringify(persistedAppliedDecisions) !==
        JSON.stringify(state.expectedAppliedDecisions) ||
      JSON.stringify(persistedFinalArtifacts) !==
        JSON.stringify(state.expectedFinalArtifacts)
    ) {
      throw new Error("Audit Reconciliation parent application did not close.");
    }
    if (state.expectedRunIntake != null) {
      const persistedRunIntake = readJsonFileIfPresent(
        path.join(workingOutputDir, "run_intake.json"),
      );
      if (
        JSON.stringify(persistedRunIntake) !==
        JSON.stringify(state.expectedRunIntake)
      ) {
        throw new Error("Audit Reconciliation run receipt did not close.");
      }
    }
    if (state.expectedProfessionalReview != null) {
      const persistedProfessionalReview = readJsonFileIfPresent(
        path.join(workingOutputDir, "professional_review.json"),
      );
      if (
        !isPlainObject(persistedProfessionalReview) ||
        JSON.stringify(persistedProfessionalReview) !==
          JSON.stringify(state.expectedProfessionalReview)
      ) {
        throw new Error(
          "Audit Reconciliation professional review authority did not close.",
        );
      }
    }
    for (const relativePath of state.expectedTransitionHistoryPaths || []) {
      const transitionPath = path.join(workingOutputDir, relativePath);
      if (
        !fs.existsSync(transitionPath) ||
        !fs.lstatSync(transitionPath).isFile()
      ) {
        throw new Error(
          "Audit Reconciliation review transition did not close.",
        );
      }
    }
    if (state.expectedReviewHandoffContent != null) {
      const handoffPath = path.join(workingOutputDir, "review_handoff.md");
      if (
        !fs.existsSync(handoffPath) ||
        fs.readFileSync(handoffPath, "utf8") !==
          state.expectedReviewHandoffContent
      ) {
        throw new Error("Audit Reconciliation review handoff did not close.");
      }
    }
  }
}

function validateAuditReconciliationReviewTransaction(
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
    throw new Error("Audit Reconciliation review transaction result is invalid.");
  }
  const requiredPaths =
    kind === "save"
      ? ["ui_decisions.json"]
      : [
          "ui_decisions.json",
          "applied_decisions.json",
          "final_artifacts.json",
          ...(parentState.expectedProfessionalReview != null
            ? ["professional_review.json"]
            : []),
        ];
  const filePaths = new Set(workingImage.files.map((entry) => entry.path));
  if (!requiredPaths.every((relativePath) => filePaths.has(relativePath))) {
    throw new Error("Audit Reconciliation review transaction is incomplete.");
  }
  const persistedUiDecisions = readJsonFileIfPresent(
    path.join(workingOutputDir, "ui_decisions.json"),
  );
  if (!isPlainObject(persistedUiDecisions)) {
    throw new Error("Audit Reconciliation review transaction is incomplete.");
  }
  if (kind === "save") {
    validateAuditParentTransactionState(
      kind,
      parentState,
      workingOutputDir,
      authorizedWritePaths,
      persistedUiDecisions,
    );
    const expectedResult = {
      ok: true,
      validation_type: "audit_reconciliation_decisions",
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
        ? `Se han guardado ${persistedUiDecisions?.decision_count} decisiones de Audit Reconciliation.`
        : `Saved ${persistedUiDecisions?.decision_count} Audit Reconciliation decisions.`,
      ui_decisions: persistedUiDecisions,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Audit Reconciliation saved decisions did not close.");
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
      throw new Error(
        "Audit Reconciliation review transaction is incomplete.",
      );
    }
    validateAuditParentTransactionState(
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
      throw new Error("Audit Reconciliation applied decisions did not close.");
    }
    if (
      persistedUiDecisions.run_id !== persistedAppliedDecisions.run_id ||
      persistedUiDecisions.decision_count !==
        persistedAppliedDecisions.decision_count ||
      JSON.stringify(persistedUiDecisions.decisions) !==
        JSON.stringify(persistedAppliedDecisions.decisions)
    ) {
      throw new Error(
        "Audit Reconciliation review decision state did not close.",
      );
    }
    const expectedResult = {
      ok: true,
      validation_type: "audit_reconciliation_application",
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
      professional_review_path:
        parentState.expectedProfessionalReview != null
          ? path.join(canonicalOutputDir, "professional_review.json")
          : null,
      run_intake_path: path.join(canonicalOutputDir, "run_intake.json"),
      message: isSpanishRuntime(inputArgs)
        ? `Se han aplicado ${persistedAppliedDecisions.decision_count} decisiones de Audit Reconciliation.`
        : `Applied ${persistedAppliedDecisions.decision_count} Audit Reconciliation decisions.`,
      applied_decisions: persistedAppliedDecisions,
      final_artifacts: persistedFinalArtifacts,
    };
    if (!reviewResponseMatches(result, expectedResult)) {
      throw new Error("Audit Reconciliation response did not close.");
    }
  }
}

function workflowReviewTransactionOptions(kind, inputArgs, parentState) {
  return {
    validateWholeTree: (context) =>
      validateAuditReconciliationReviewTransaction(
        kind,
        inputArgs,
        context,
        parentState,
      ),
    mapOperationError: (error) => error?.message,
  };
}

function saveDecisionPayload(inputArgs) {
  const materializedArgs = materializeInputArgs(inputArgs);
  const canonicalOutputDir = resolveRunOutputDir(materializedArgs);
  if (!canonicalOutputDir) return saveDecisionPayloadWrites(materializedArgs);
  auditReviewRequireMatchingCustomerRun(materializedArgs, canonicalOutputDir);
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "save",
    materializedArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeAuditReviewTransactionState(
        parentState,
        trustedImage,
        materializedArgs,
      );
      const workingArgs = auditReviewTrustedArgsForWorkingOutput(
        materializedArgs,
        workingOutputDir,
        parentState,
      );
      Object.defineProperty(workingArgs, AUDIT_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = saveDecisionPayloadWrites(workingArgs);
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
        "Audit Reconciliation review save transaction failed safely.",
      rollbackFailureMessage:
        "Audit Reconciliation review save transaction could not be restored safely.",
    },
  );
}

function saveDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[AUDIT_REVIEW_TRANSACTION_STATE] || null;
  const { uiDecisions, decisionOutputPath, materializedArgs } = buildUiDecisions(inputArgs);
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
    validation_type: "audit_reconciliation_decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? decisionOutputPath : null,
    message: isSpanishRuntime(materializedArgs)
      ? persisted
        ? `Se han guardado ${uiDecisions.decision_count} decisiones de Audit Reconciliation.`
        : "Las decisiones se han validado. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
      : persisted
        ? `Saved ${uiDecisions.decision_count} Audit Reconciliation decisions.`
        : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneAuditReviewTransactionValue(uiDecisions);
    parentState.authorizedWritePaths = ["ui_decisions.json"];
    parentState.complete = true;
  }
  return result;
}

function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputReference = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputReference) return null;
  const contextValue =
    typeof inputArgs.client_engagement === "string"
      ? inputArgs.client_engagement.trim()
      : typeof runIntake?.client_engagement?.context_path === "string"
        ? runIntake.client_engagement.context_path.trim()
        : "";
  if (!contextValue && path.isAbsolute(outputReference)) {
    return path.resolve(outputReference);
  }
  if (!contextValue || !path.isAbsolute(contextValue)) {
    throw new Error("Audit Reconciliation persistence requires the current client_engagement context.");
  }
  const contextPath = path.resolve(contextValue);
  if (contextPath !== contextValue || path.basename(contextPath) !== "context.json") {
    throw new Error("Audit Reconciliation client_engagement path is invalid.");
  }
  const contextStat = generatedReviewPathEntryStat(contextPath);
  if (
    !contextStat ||
    !contextStat.isFile() ||
    contextStat.isSymbolicLink() ||
    contextStat.nlink !== 1
  ) {
    throw new Error("Audit Reconciliation client_engagement context is unavailable.");
  }
  if (!path.isAbsolute(outputReference) && runIntake?.path_reference !== "run_root_relative") {
    throw new Error("Audit Reconciliation output reference is not run-root-relative.");
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
    throw new Error("Audit Reconciliation output reference leaves the customer run.");
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
  const parentState = inputArgs[AUDIT_REVIEW_TRANSACTION_STATE] || null;
  const runIntakePath = path.join(outputDir, "run_intake.json");
  const current = cloneAuditReviewTransactionValue(
    parentState?.baselineRunIntake,
  ) || readJsonFileIfPresent(runIntakePath) ||
    (isPlainObject(inputArgs.run_intake) ? { ...inputArgs.run_intake } : null);
  if (!current) return null;
  const trace = Array.isArray(current.execution_trace) ? [...current.execution_trace] : [];
  const appliedAt = shortString(appliedDecisions?.applied_at) || new Date().toISOString();
  const stepIdSuffix = appliedAt.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "audit_reconciliation"}_review_apply_${stepIdSuffix || Date.now()}`,
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
  generatedReviewAtomicWriteFileSync(
    runIntakePath,
    `${JSON.stringify(updated, null, 2)}\n`,
    "utf8",
  );
  if (parentState) {
    parentState.expectedRunIntake =
      cloneAuditReviewTransactionValue(updated);
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
      throw new Error("Audit Reconciliation review target is unsafe.");
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
      throw new Error("Audit Reconciliation structured review target is unsafe.");
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

function completionBlockers(reviewPayload, effects, successorReplayed = false) {
  const blockers = [];
  const summary = isPlainObject(reviewPayload.summary) ? reviewPayload.summary : {};
  if (summary.checks_pass === false || Number(summary.failed_check_count || 0) > 0) {
    blockers.push({
      kind: "failed_deterministic_checks",
      detail: "Failed deterministic checks require correction and rerun.",
    });
  }
  const effectById = new Map(effects.map((effect) => [effect.item_id, effect]));
  for (const item of reviewPayload.items || []) {
    if (!isPlainObject(item) || !REQUIRED_REVIEW_ITEM_TYPES.has(item.item_type)) continue;
    const effect = effectById.get(item.id);
    if (!effect) {
      blockers.push({
        kind: "pending_required_review",
        detail: `Required review item remains pending: ${item.id}`,
      });
    } else if (effect.action === "skip") {
      blockers.push({
        kind: "skipped_required_review",
        detail: `Required review item was skipped: ${item.id}`,
      });
    }
  }
  if (!successorReplayed) {
    blockers.push({
      kind: "assurance_replay_required",
      detail:
        "Reviewed decisions require native regeneration and a fresh successor assurance receipt replay before final readiness.",
    });
  }
  return blockers;
}

function statusFromEffects(effects, itemCount, completionGateBlockers) {
  if (!effects.length) return "pending_review";
  if (effects.some((effect) => effect.requires_followup)) return "blocked";
  if (completionGateBlockers.length) return "blocked";
  if (effects.some((effect) => effect.requires_native_regeneration)) return "partial_review_applied";
  if (effects.length < itemCount) return "partial_review_applied";
  return "final_ready";
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
  const localizedAuditHandoff =
    pluginName === "audit-reconciliation" && isSpanishRuntime(inputArgs);
  if ((!REVIEW_HANDOFF_PLUGINS.has(pluginName) && !localizedAuditHandoff) || !outputDir) {
    return null;
  }

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
          "## Revisión profesional",
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
          "## Professional Review",
          `1. Validate the payload with \`${TOOL_NAMES.validateReview}\`.`,
          `2. Render the review workbench with \`${TOOL_NAMES.renderReview}\`.`,
          `3. Save reviewer actions with \`${TOOL_NAMES.saveDecisions}\`.`,
          `4. Apply reviewer actions with \`${TOOL_NAMES.applyDecisions}\`.`,
        ].join("\n");
    const handoffContent = `${text}\n`;
    generatedReviewAtomicWriteFileSync(handoffPath, handoffContent, "utf8");
    const parentState = inputArgs[AUDIT_REVIEW_TRANSACTION_STATE] || null;
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
  if (isPlainObject(appliedDecisions.professional_review)) {
    upsertOutput({
      path: "professional_review.json",
      kind: "json",
      status: appliedDecisions.professional_review.successor_assurance_replayed
        ? "successor_assurance_replayed"
        : "review_authority_persisted",
    });
  }
  for (const output of revisionOutputs) upsertOutput(output);
  for (const output of targetOutputs) upsertOutput(output);
  for (const output of backupOutputs) upsertOutput(output);
  for (const output of nativeRegenerationOutputs) upsertOutput(output);
  const blockers = [
    ...effectsToBlockers(appliedDecisions.effects),
    ...(Array.isArray(appliedDecisions.completion_blockers)
      ? appliedDecisions.completion_blockers
      : []),
  ];
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
      completion_blockers: Array.isArray(appliedDecisions.completion_blockers)
        ? appliedDecisions.completion_blockers
        : [],
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
      professional_review_path: isPlainObject(
        appliedDecisions.professional_review,
      )
        ? "professional_review.json"
        : null,
      decision_fingerprint: isPlainObject(
        appliedDecisions.professional_review,
      )
        ? appliedDecisions.professional_review.decision_fingerprint
        : null,
      successor_assurance_replayed:
        appliedDecisions.professional_review?.successor_assurance_replayed === true,
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
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push(
      spanish
        ? "Use final_artifacts.json como galería de artefactos revisados para la entrega."
        : "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
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
  const materializedArgs = materializeInputArgs(inputArgs);
  const canonicalOutputDir = resolveRunOutputDir(materializedArgs);
  if (!canonicalOutputDir) return applyDecisionPayloadWrites(materializedArgs);
  auditReviewRequireMatchingCustomerRun(materializedArgs, canonicalOutputDir);
  const parentState = {};
  const workflowOptions = workflowReviewTransactionOptions(
    "apply",
    materializedArgs,
    parentState,
  );
  return withGeneratedReviewOutputTransaction(
    canonicalOutputDir,
    ({ workingOutputDir, trustedImage }) => {
      initializeAuditReviewTransactionState(
        parentState,
        trustedImage,
        materializedArgs,
      );
      const workingArgs = auditReviewTrustedArgsForWorkingOutput(
        materializedArgs,
        workingOutputDir,
        parentState,
      );
      Object.defineProperty(workingArgs, AUDIT_REVIEW_TRANSACTION_STATE, {
        value: parentState,
      });
      const workingResult = applyDecisionPayloadWrites(workingArgs);
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
        "Audit Reconciliation review apply transaction failed safely.",
      rollbackFailureMessage:
        "Audit Reconciliation review apply transaction could not be restored safely.",
    },
  );
}

function applyDecisionPayloadWrites(inputArgs) {
  const parentState = inputArgs[AUDIT_REVIEW_TRANSACTION_STATE] || null;
  const { uiDecisions, decisionOutputPath, materializedArgs } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const appliedAt = new Date().toISOString();
  const effects = uiDecisions.decisions.map((decision) =>
    buildApplicationEffect(decision, itemById.get(decision.item_id), appliedAt),
  );
  const outputDir = resolveRunOutputDir(inputArgs);
  const decisionFingerprint = auditReviewDecisionFingerprint(
    reviewPayload,
    effects,
  );
  const expectedPredecessorCheckpoint = shortString(
    inputArgs.expected_predecessor_checkpoint,
  );
  let assuranceReplay = null;
  if (
    outputDir &&
    fs.existsSync(path.join(outputDir, "assurance_receipts.json"))
  ) {
    if (!/^[0-9a-f]{64}$/.test(expectedPredecessorCheckpoint)) {
      throw new Error(
        "An external expected predecessor checkpoint is required.",
      );
    }
    assuranceReplay = auditReviewReplayAssurance(
      outputDir,
      decisionFingerprint,
      expectedPredecessorCheckpoint,
    );
    if (
      assuranceReplay.authority?.origin !== "applied_decisions" &&
      assuranceReplay.assurance.content_sha256 !== expectedPredecessorCheckpoint
    ) {
      throw new Error(
        "External expected predecessor checkpoint does not match.",
      );
    }
  }
  const successorReplayed = assuranceReplay?.successorReplayed === true;
  const professionalReview = assuranceReplay
    ? successorReplayed
      ? assuranceReplay.authority
      : auditReviewProfessionalAuthority(
          reviewPayload,
          effects,
          shortString(uiDecisions.reviewer),
          decisionFingerprint,
          assuranceReplay,
        )
    : null;
  let transitionCaptureDir = null;
  if (outputDir && assuranceReplay && !successorReplayed) {
    transitionCaptureDir = fs.mkdtempSync(
      path.join(
        path.dirname(outputDir),
        ".audit-review-transition-capture-",
      ),
    );
    fs.chmodSync(transitionCaptureDir, 0o700);
    auditReviewPythonBridge(
      "capture-review-transition-json",
      outputDir,
      transitionCaptureDir,
      "--expected-predecessor-checkpoint",
      expectedPredecessorCheckpoint,
    );
  }
  const revisionOutputs = writeRevisionArtifacts(outputDir, effects);
  const textUpdates = writeDirectTextArtifactUpdates(outputDir, effects);
  const structuredUpdates = writeStructuredArtifactUpdates(outputDir, effects);
  const appliedOutputPath = resolveAppliedDecisionOutputPath(inputArgs);
  const finalArtifactsPath = resolveFinalArtifactsOutputPath(inputArgs);
  const professionalReviewPath = outputDir && professionalReview
    ? path.join(outputDir, "professional_review.json")
    : null;
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
  const completionGateBlockers = completionBlockers(
    reviewPayload,
    effects,
    successorReplayed,
  );
  const blockerCount =
    effects.filter((effect) => effect.requires_followup).length +
    completionGateBlockers.length;
  const applicationStatus = statusFromEffects(
    effects,
    reviewPayload.items.length,
    completionGateBlockers,
  );
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
    completion_blockers: completionGateBlockers,
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
  if (professionalReview) {
    appliedDecisions.professional_review = {
      path: "professional_review.json",
      decision_fingerprint: decisionFingerprint,
      successor_assurance_replayed: successorReplayed,
    };
  }
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
  if (professionalReviewPath && !successorReplayed) {
    generatedReviewAtomicWriteFileSync(
      professionalReviewPath,
      `${JSON.stringify(professionalReview, null, 2)}\n`,
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
  let transitionHistoryPaths = [];
  if (transitionCaptureDir) {
    const retained = auditReviewPythonBridge(
      "retain-review-transition-json",
      outputDir,
      transitionCaptureDir,
      "--expected-predecessor-checkpoint",
      expectedPredecessorCheckpoint,
    );
    if (!Array.isArray(retained.history_paths)) {
      throw new Error("Review transition replay failed.");
    }
    transitionHistoryPaths = retained.history_paths;
    fs.rmSync(transitionCaptureDir, { recursive: true, force: true });
    transitionCaptureDir = null;
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
    validation_type: "audit_reconciliation_application",
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
    professional_review_path: professionalReviewPath,
    run_intake_path: runIntakePath,
    message: isSpanishRuntime(materializedArgs)
      ? persisted
        ? `Se han aplicado ${responseAppliedDecisions.decision_count} decisiones de Audit Reconciliation.`
        : "Las decisiones aplicadas se han validado. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
      : persisted
        ? `Applied ${responseAppliedDecisions.decision_count} Audit Reconciliation decisions.`
        : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
  if (parentState) {
    parentState.expectedUiDecisions =
      cloneAuditReviewTransactionValue(uiDecisions);
    parentState.expectedAppliedDecisions =
      cloneAuditReviewTransactionValue(responseAppliedDecisions);
    parentState.expectedFinalArtifacts =
      cloneAuditReviewTransactionValue(responseFinalArtifacts);
    parentState.expectedProfessionalReview =
      cloneAuditReviewTransactionValue(professionalReview);
    parentState.expectedTransitionHistoryPaths = [...transitionHistoryPaths];
    parentState.authorizedWritePaths = auditReviewParentWritePaths(
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
    const payload = validateReviewPayload(args);
    return {
      ok: true,
      validation_type: "audit_reconciliation_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_type: payload.review_payload.review_type || null,
      message: isSpanishRuntime(payload)
        ? "El payload de revisión de Audit Reconciliation es válido. Use scripts/review_server.py y artifact_card.md para la entrega principal en el navegador, o llame a render_audit_reconciliation_review para la superficie MCP opcional. Las ejecuciones grandes pueden proporcionar review_payload_path y las rutas relacionadas de la salida en lugar de JSON en línea."
        : "Audit Reconciliation review payload is valid. Use scripts/review_server.py and artifact_card.md for the primary browser handoff, or call render_audit_reconciliation_review for the optional MCP surface. Large runs can pass review_payload_path and sibling run-output paths instead of inline JSON.",
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
  throw new Error(`unknown Audit Reconciliation widget tool: ${name}`);
}

function widgetUriForPayload(payload) {
  if (payload.widget_type === "audit_reconciliation_review") return WIDGET_URI;
  return null;
}

function toolResult(payload, toolName) {
  const result = {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
  const widgetUri = widgetUriForPayload(payload) || WIDGET_TOOL_URIS[toolName];
  if (widgetUri) result._meta = toolUiMeta(widgetUri, toolName);
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
  // Recheck before every public surface so post-start expansion cannot receive
  // a normal initialize, resource, prompt, or tool response.
  validateImplementationTree();
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
        instructions: isSpanishRuntime(params) ? SERVER_INSTRUCTIONS_ES : SERVER_INSTRUCTIONS,
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") {
      return rpcResponse(messageId, { tools: toolDefinitions() });
    }
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
    if (method === "resources/list") {
      return rpcResponse(messageId, { resources: resources() });
    }
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

"use strict";

const fs = require("node:fs");
const crypto = require("node:crypto");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

const SERVER_NAME = "check-entries-widgets";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const CHECK_ENTRIES_PLUGIN_IMPLEMENTATION_PATHS = [
  ".app.json",
  ".codex-plugin/plugin.json",
  ".mcp.json",
  "assets/check-entries-review-widget.html",
  "assets/icon.svg",
  "assets/review-workbench-adapter.json",
  "mcp/server.cjs",
  "scripts/apply_review_edits.py",
  "scripts/check_dependencies.py",
  "scripts/check_entries_core.py",
  "scripts/implementation_bootstrap.py",
  "scripts/implementation_contract.py",
  "scripts/inspect_entries.py",
  "scripts/invoice_support.py",
  "scripts/physical_output_set.py",
  "scripts/review_session.py",
  "scripts/run_checks.py",
  "scripts/stable_ooxml.py",
];
const CHECK_ENTRIES_SHARED_IMPLEMENTATION_PATHS = [
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
const ASSURANCE_IMPLEMENTATION_ROOT = path.dirname(
  REVIEW_TRANSACTION_RUNTIME,
);

function exactPreImportImplementationTree() {
  const roots = {
    implementation: PLUGIN_ROOT,
    assurance_implementation: ASSURANCE_IMPLEMENTATION_ROOT,
  };
  const expectedFiles = new Set([
    ...CHECK_ENTRIES_PLUGIN_IMPLEMENTATION_PATHS.map(
      (relativePath) => `implementation:${relativePath}`,
    ),
    ...CHECK_ENTRIES_SHARED_IMPLEMENTATION_PATHS.map(
      (relativePath) => `assurance_implementation:${relativePath}`,
    ),
  ]);
  const expectedDirectories = new Set();
  for (const entry of expectedFiles) {
    const separator = entry.indexOf(":");
    const rootId = entry.slice(0, separator);
    let parent = path.posix.dirname(entry.slice(separator + 1));
    while (parent && parent !== ".") {
      expectedDirectories.add(`${rootId}:${parent}`);
      parent = path.posix.dirname(parent);
    }
  }
  const observedFiles = new Set();
  const observedDirectories = new Set();
  const scan = (rootId, scanRoot) => {
    const root = roots[rootId];
    const rootEntry = fs.lstatSync(scanRoot);
    if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
      throw new Error("Check Entries implementation root is unsafe");
    }
    const scanRelative = path.relative(root, scanRoot).split(path.sep).join("/");
    if (scanRelative && scanRelative !== ".") {
      observedDirectories.add(`${rootId}:${scanRelative}`);
    }
    const pending = [scanRoot];
    while (pending.length) {
      const current = pending.pop();
      for (const name of fs.readdirSync(current).sort()) {
        const candidate = path.join(current, name);
        const observed = fs.lstatSync(candidate);
        const relative = path.relative(root, candidate).split(path.sep).join("/");
        if (observed.isSymbolicLink()) {
          throw new Error("Check Entries implementation cannot contain symlinks");
        }
        if (observed.isDirectory()) {
          observedDirectories.add(`${rootId}:${relative}`);
          pending.push(candidate);
          continue;
        }
        if (!observed.isFile() || observed.nlink !== 1) {
          throw new Error(
            "Check Entries implementation files must be ordinary single-link files",
          );
        }
        observedFiles.add(`${rootId}:${relative}`);
      }
    }
  };
  for (const [rootId, scanRoot] of [
    ["implementation", path.join(PLUGIN_ROOT, "assets")],
    ["implementation", path.join(PLUGIN_ROOT, "mcp")],
    ["implementation", path.join(PLUGIN_ROOT, "scripts")],
    ["implementation", path.join(PLUGIN_ROOT, ".codex-plugin")],
    ["assurance_implementation", ASSURANCE_IMPLEMENTATION_ROOT],
  ]) {
    scan(rootId, scanRoot);
  }
  for (const relativePath of [".app.json", ".mcp.json"]) {
    const candidate = path.join(PLUGIN_ROOT, relativePath);
    const observed = fs.lstatSync(candidate);
    if (
      observed.isSymbolicLink() ||
      !observed.isFile() ||
      observed.nlink !== 1
    ) {
      throw new Error(
        "Check Entries launcher configuration must be an ordinary single-link file",
      );
    }
    observedFiles.add(`implementation:${relativePath}`);
  }
  const exactSet = (left, right) =>
    left.size === right.size && [...left].every((entry) => right.has(entry));
  if (
    !exactSet(observedFiles, expectedFiles) ||
    !exactSet(observedDirectories, expectedDirectories)
  ) {
    throw new Error(
      "Check Entries implementation filesystem does not match the exact contract",
    );
  }
}

exactPreImportImplementationTree();

const {
  generatedReviewAtomicWriteFileSync,
  generatedReviewCaptureDirectoryImage,
  generatedReviewCollectApplicationWritePaths,
  generatedReviewPathEntryStat,
  generatedReviewTransactionEnvelope,
  withGeneratedReviewOutputTransaction,
} = require(REVIEW_TRANSACTION_RUNTIME);
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const WIDGET_URI = "ui://widget/check-entries-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 2_000_000;
const TOOL_NAMES = {
  validateReview: "validate_check_entries_review",
  renderReview: "render_check_entries_review",
  caseContext: "get_check_entries_case_context",
  saveDecisions: "save_check_entries_decisions",
  applyDecisions: "apply_check_entries_decisions",
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
  "status",
  "entry_date",
  "amount_signed",
  "amount_abs",
  "account_name",
  "description",
  "beneficiary",
  "counterparty",
  "currency",
  "unit",
  "checks_run",
  "mismatches",
  "review_notes",
  "support_type",
  "support_match_status",
  "support_match_signals",
  "professional_conclusion",
  "assurance_gate_status",
  "amount_found",
  "date_found",
  "beneficiary_found",
  "requested_document",
  "reason",
  "extractable_text",
  "text_chars",
  "error",
  "missing",
  "shown_count",
  "total_count",
]);
const MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS = new Set([
  "movement_number",
  "account",
  "invoice_number",
  "document_number",
  "document_no",
  "reference",
  "supplier_tax_id",
  "customer_tax_id",
  "tax_id",
  "vat_number",
  "fiscal_code",
]);
const MODEL_CONTEXT_EVIDENCE_FIELDS = new Set([
  "kind",
  "status",
  "checks_run",
  "mismatches",
  "review_notes",
  "support_type",
  "support_match_status",
  "support_match_signals",
  "evidence_facts",
  "professional_conclusion",
  "assurance_gate_status",
  "value",
  "requested_document",
  "reason",
  "extractable_text",
  "text_chars",
  "error",
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
  "supported_entry",
  "missing_support",
  "mismatch",
  "manual_review",
  "entry_check_result",
  "pdf_inventory",
  "mapping_issue",
  "review_artifact",
]);

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function canonicalJsonValue(value) {
  if (Array.isArray(value)) return value.map((item) => canonicalJsonValue(item));
  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalJsonValue(value[key])]),
    );
  }
  if (value == null || ["string", "boolean", "number"].includes(typeof value)) {
    return value;
  }
  throw new Error("review_payload contains a non-JSON value");
}

function reviewPayloadContentSha256(reviewPayload) {
  const content = { ...reviewPayload };
  delete content.content_sha256;
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(canonicalJsonValue(content)), "utf8")
    .digest("hex");
}

function immutableRunIntakeProjection(value) {
  if (!isPlainObject(value)) return null;
  const projection = { ...value };
  // execution_trace is append-only local execution metadata. Every authority-
  // bearing intake field remains in the exact canonical comparison.
  delete projection.execution_trace;
  return canonicalJsonValue(projection);
}

function validatePersistedRunIntake(inputArgs) {
  const caller = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir) return;
  if (!caller) throw new Error("run_intake is required for persisted writes");
  const persisted = readJsonFileIfPresent(path.join(outputDir, "run_intake.json"));
  if (!persisted) {
    // Direct, explicitly targeted review applications may start without a
    // workflow-created intake. An existing assured workflow may not bypass
    // intake replay by deleting run_intake.json.
    const workflowMarkers = [
      "assurance_envelope.json",
      "check_audit.json",
      "review_payload.json",
      "normalized_entries.csv",
    ];
    if (workflowMarkers.some((name) => fs.existsSync(path.join(outputDir, name)))) {
      throw new Error("persisted run_intake.json is required before any write");
    }
    return;
  }
  if (
    typeof persisted.output_dir !== "string" ||
    resolveRunOutputDir({ ...inputArgs, run_intake: persisted }) !== outputDir ||
    JSON.stringify(immutableRunIntakeProjection(caller)) !==
      JSON.stringify(immutableRunIntakeProjection(persisted))
  ) {
    throw new Error("run_intake does not match the persisted immutable intake");
  }
}

function cloneCanonicalJson(value) {
  return JSON.parse(JSON.stringify(canonicalJsonValue(value)));
}

function assertedPersistedMatch(callerValue, persistedValue, label) {
  if (callerValue == null) return;
  if (!isPlainObject(callerValue) || !canonicalJsonEqual(callerValue, persistedValue)) {
    if (label === "review_payload") {
      throw new Error("review_payload does not match the persisted assured review");
    }
    throw new Error(CHECK_ENTRIES_AUTHORIZATION_FAILURE);
  }
}

const CHECK_ENTRIES_ASSURANCE_MARKERS = [
    "assurance_envelope.json",
    "check_audit.json",
    "normalized_entries.csv",
    "numeric_evidence_ledger.json",
    "support_manifest.json",
];

function hasAssuredCheckEntriesMarker(outputDir) {
  return CHECK_ENTRIES_ASSURANCE_MARKERS.some((name) =>
    fs.existsSync(path.join(outputDir, name)),
  );
}

function trustedImageJsonObject(trustedImage, relativePath) {
  if (!trustedImage) return null;
  const entry = trustedImage.files.find((file) => file.path === relativePath);
  if (!entry) return null;
  try {
    const parsed = JSON.parse(entry.payload.toString("utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function parentBoundCheckEntriesArgs(
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
      ? trustedImageJsonObject(trustedImage, name)
      : readJsonFileIfPresent(path.join(outputDir, name));
  const persistedRunIntake = imageJson("run_intake.json");
  const persistedReviewPayload = imageJson("review_payload.json");
  const persistedUiDecisions = imageJson("ui_decisions.json");
  const persistedFinalArtifacts = imageJson("final_artifacts.json");
  const assured = trustedImageCaptured
    ? CHECK_ENTRIES_ASSURANCE_MARKERS.some((name) =>
        (trustedImage?.files || []).some((file) => file.path === name),
      )
    : hasAssuredCheckEntriesMarker(outputDir);
  if (
    assured &&
    [
      persistedRunIntake,
      persistedReviewPayload,
      persistedUiDecisions,
      persistedFinalArtifacts,
    ].some((value) => !isPlainObject(value))
  ) {
    throw new Error(CHECK_ENTRIES_AUTHORIZATION_FAILURE);
  }
  if (persistedRunIntake) {
    assertedPersistedMatch(inputArgs.run_intake, persistedRunIntake, "run_intake");
  } else if (!trustedImageCaptured) {
    validatePersistedRunIntake(inputArgs);
  }
  if (persistedReviewPayload) {
    assertedPersistedMatch(
      inputArgs.review_payload,
      persistedReviewPayload,
      "review_payload",
    );
  }
  if (persistedUiDecisions) {
    assertedPersistedMatch(
      inputArgs.ui_decisions,
      persistedUiDecisions,
      "ui_decisions",
    );
  }
  if (persistedFinalArtifacts) {
    assertedPersistedMatch(
      inputArgs.final_artifacts,
      persistedFinalArtifacts,
      "final_artifacts",
    );
  }
  const trustedArgs = {
    ...inputArgs,
    ...(persistedRunIntake
      ? { run_intake: cloneCanonicalJson(persistedRunIntake) }
      : {}),
    ...(persistedReviewPayload
      ? { review_payload: cloneCanonicalJson(persistedReviewPayload) }
      : {}),
    ...(persistedUiDecisions
      ? { ui_decisions: cloneCanonicalJson(persistedUiDecisions) }
      : {}),
    ...(persistedFinalArtifacts
      ? { final_artifacts: cloneCanonicalJson(persistedFinalArtifacts) }
      : {}),
  };
  if (
    persistedRunIntake &&
    (typeof persistedRunIntake.output_dir !== "string" ||
      resolveRunOutputDir({ ...inputArgs, run_intake: persistedRunIntake }) !== path.resolve(outputDir))
  ) {
    throw new Error(CHECK_ENTRIES_AUTHORIZATION_FAILURE);
  }
  return { args: trustedArgs, outputDir, assured };
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
  if (text === "persisted run_intake.json is required before any write") return "Se requiere run_intake.json persistido antes de cualquier escritura";
  if (text === "run_intake does not match the persisted immutable intake") return "run_intake no coincide con la entrada inmutable persistida";
  if (text === "review_payload.content_sha256 is stale") return "El resumen criptográfico de review_payload está obsoleto";
  if (text === "ui_decisions is bound to a different review_payload") return "ui_decisions está vinculado a otro review_payload";
  if (text === "review_payload.content_sha256 must be a lowercase SHA-256 digest") return "review_payload.content_sha256 debe ser un resumen SHA-256 en minúsculas";
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
  const meta = {
    ui: { resourceUri, visibility: ["model"] },
    "ui/resourceUri": resourceUri,
    "openai/outputTemplate": resourceUri,
    "openai/widgetAccessible": true,
  };
  if (toolName === TOOL_NAMES.renderReview) {
    meta["openai/toolInvocation/invoking"] = "Rendering Check Entries review";
    meta["openai/toolInvocation/invoked"] = "Rendered Check Entries review";
  }
  return meta;
}

function widgetResourceMeta(uri) {
  return {
    ui: { resourceUri: uri },
    "openai/widgetDescription":
      "Interactive Check Entries review surface for support coverage, mismatches, missing support, manual-review rows, PDF extraction, and generated artifacts.",
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
        description: "Include exact movement, invoice, account, tax, or reference identifiers only when the selected evidence judgment requires them.",
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
      title: "Validate Check Entries review payload",
      description:
        "Validate the Check Entries review-session payload before rendering. Call this first, then render_check_entries_review.",
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
      title: "Render Check Entries review",
      description:
        "Render a Check Entries review-session payload as an MCP HTML widget for support coverage, exceptions, PDFs, and artifacts.",
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
      title: "Get selected Check Entries case context",
      description:
        "Return purpose-limited entry and support facts for up to 25 selected cases. Exact identifiers stay out by default and can be requested only when needed for the evidence judgment.",
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
      title: "Save Check Entries review decisions",
      description:
        "Validate Check Entries row decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
      title: "Apply Check Entries review decisions",
      description:
        "Validate Check Entries review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
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
      name: "check_entries_review_widget",
      title: "Check Entries review widget",
      description:
        "Renders Check Entries review-session payloads with searchable rows and evidence details.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetResourceMeta(WIDGET_URI),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown Check Entries widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "check-entries-review-widget.html"),
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
  inputArgs = materializePrivateReviewArgs(inputArgs);
  if (!isPlainObject(inputArgs)) throw new Error("tool arguments must be an object");
  const reviewPayload = inputArgs.review_payload;
  if (!isPlainObject(reviewPayload)) throw new Error("review_payload must be an object");
  requireString(reviewPayload.schema_version, "review_payload.schema_version");
  if (reviewPayload.schema_version !== "2.0") {
    throw new Error('review_payload.schema_version must be "2.0"');
  }
  if (reviewPayload.plugin !== "check-entries") {
    throw new Error('review_payload.plugin must be "check-entries"');
  }
  requireString(reviewPayload.workflow, "review_payload.workflow");
  requireString(reviewPayload.run_id, "review_payload.run_id");
  requireString(reviewPayload.content_sha256, "review_payload.content_sha256");
  if (!/^[0-9a-f]{64}$/.test(reviewPayload.content_sha256)) {
    throw new Error("review_payload.content_sha256 must be a lowercase SHA-256 digest");
  }
  if (reviewPayload.content_sha256 !== reviewPayloadContentSha256(reviewPayload)) {
    throw new Error("review_payload.content_sha256 is stale");
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
  const itemIds = reviewPayload.items.map((item) => item.id);
  if (new Set(itemIds).size !== itemIds.length) {
    throw new Error("review_payload.items must have unique ids");
  }
  const currentUiDecisions = isPlainObject(inputArgs.ui_decisions)
    ? inputArgs.ui_decisions
    : null;
  if (
    currentUiDecisions &&
    currentUiDecisions.review_payload_content_sha256 !== reviewPayload.content_sha256
  ) {
    throw new Error("ui_decisions is bound to a different review_payload");
  }
  const payload = {
    widget_type: "check_entries_review",
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
    throw new Error(`Check Entries widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
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
  if (depth > 5 || !modelContextHasValue(value)) return undefined;
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

function modelContextProjectEvidenceFacts(value, includeExactIdentifiers, depth = 0) {
  if (depth > 5 || !modelContextHasValue(value)) return undefined;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed) || isPlainObject(parsed)) {
        return modelContextProjectEvidenceFacts(
          parsed,
          includeExactIdentifiers,
          depth + 1,
        );
      }
    } catch {
      // Non-JSON evidence text is retained because it may be the professional fact.
    }
  }
  if (Array.isArray(value)) {
    const result = value.slice(0, 100)
      .map((entry) => modelContextProjectEvidenceFacts(entry, includeExactIdentifiers, depth + 1))
      .filter((entry) => entry !== undefined);
    return result.length ? result : undefined;
  }
  if (!isPlainObject(value)) return modelContextCleanValue(value, depth);
  const technicalFields = new Set([
    "prepared_entry_id",
    "support_artifact_id",
    "source_file",
    "source_path",
    "source_row",
    "source_page",
    "source_locator",
    "path",
    "filename",
  ]);
  const result = {};
  for (const [key, entry] of Object.entries(value)) {
    const normalizedKey = key.toLowerCase();
    if (
      technicalFields.has(normalizedKey)
      || normalizedKey === "id"
      || normalizedKey.endsWith("_id")
      || normalizedKey.endsWith("_path")
      || normalizedKey.endsWith("_file")
      || normalizedKey.endsWith("_filename")
      || normalizedKey.endsWith("_locator")
      || normalizedKey.startsWith("target_")
      || normalizedKey.startsWith("output_")
    ) {
      continue;
    }
    if (MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS.has(key) && !includeExactIdentifiers) {
      if (modelContextHasValue(entry)) result[`${key}_present`] = true;
      continue;
    }
    const projected = modelContextProjectEvidenceFacts(
      entry,
      includeExactIdentifiers,
      depth + 1,
    );
    if (projected !== undefined) result[key] = projected;
  }
  return Object.keys(result).length ? result : undefined;
}

function modelContextProjectEvidence(evidence, semanticFields, includeExactIdentifiers) {
  if (!Array.isArray(evidence)) return [];
  const allowed = new Set(MODEL_CONTEXT_EVIDENCE_FIELDS);
  if (includeExactIdentifiers) {
    for (const field of MODEL_CONTEXT_EXACT_IDENTIFIER_FIELDS) allowed.add(field);
  }
  return evidence.slice(0, 50).map((entry) => {
    const projected = modelContextProjectObject(entry, allowed);
    if (Object.prototype.hasOwnProperty.call(projected, "evidence_facts")) {
      const facts = modelContextProjectEvidenceFacts(
        entry.evidence_facts,
        includeExactIdentifiers,
      );
      if (facts === undefined) delete projected.evidence_facts;
      else projected.evidence_facts = facts;
    }
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
  if (item.item_type === "review_artifact" && item.recommended_action === "accept") return false;
  if (item.item_type === "pdf_inventory" && item.recommended_action === "accept") return false;
  return true;
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
  // This deterministic projection enforces a transport boundary only. It does
  // not decide evidential relevance or replace the model's professional review.
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
  const signalFields = new Set([
    "kind",
    "status",
    "checks_run",
    "mismatches",
    "support_type",
    "support_match_status",
    "professional_conclusion",
    "assurance_gate_status",
    "extractable_text",
    "error",
  ]);
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
    widget_type: "check_entries_review",
    item_count: context.privatePayload.review_payload.item_count,
    status: modelContextSafeStatus(context.privatePayload.review_payload.status),
    review_reference: {
      persistence_token: token,
      expires_in_seconds: Math.floor(MODEL_CONTEXT_TTL_MS / 1000),
    },
    model_context_index: {
      schema_version: "1.0",
      purpose: "Select sampled-entry or support cases that require interpretation before requesting semantic context.",
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
      omitted: ["physical source paths and filenames", "prepared entry and support artifact IDs", "review write targets", "empty fields", "unmapped columns", "duplicate facts"],
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
  // Decision persistence is an audit contract: item ids, actions, and edit payloads are mechanically verifiable.
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
    plugin: "check-entries",
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

function saveDecisionPayload(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  const expectedRunId = validateReviewPayload(inputArgs).review_payload.run_id;
  const persist = (trustedArgs, workingOutputDir) => {
    const { uiDecisions, decisionOutputPath } =
      buildUiDecisions(trustedArgs);
    const language = languageFromArgs(trustedArgs);
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
    const result = {
      ok: true,
      validation_type: "check_entries_decisions",
      run_id: uiDecisions.run_id,
      decision_count: uiDecisions.decision_count,
      item_count: uiDecisions.item_count,
      status: uiDecisions.status,
      persisted,
      ui_decisions_path: persisted ? decisionOutputPath : null,
      message: persisted
        ? isSpanish(language)
          ? `Se guardaron ${uiDecisions.decision_count} decisiones de Comprobación de asientos.`
          : `Saved ${uiDecisions.decision_count} Check Entries decisions.`
        : isSpanish(language)
          ? "Las decisiones son válidas. No se proporcionó run_intake.output_dir, por lo que no se escribió ningún archivo."
          : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
      ui_decisions: uiDecisions,
    };
    return generatedReviewTransactionEnvelope(
      result,
      persisted ? ["ui_decisions.json"] : [],
    );
  };
  if (!outputDir) return persist(inputArgs, null).result;
  validateCheckEntriesTransactionInput(outputDir);
  preflightClientRun(outputDir, expectedRunId);
  let assuredWorkflow = false;
  return withGeneratedReviewOutputTransaction(
    outputDir,
    ({ workingOutputDir, trustedImage }) => {
      const authority = parentBoundCheckEntriesArgs(inputArgs, {
        outputDir,
        trustedImage,
        trustedImageCaptured: true,
      });
      assuredWorkflow = authority.assured;
      const persistedAuthority = validateCheckEntriesAssuranceAuthority(
        workingOutputDir,
        {
        required: authority.assured,
        canonicalOutputDir: outputDir,
        failureMessage: CHECK_ENTRIES_AUTHORIZATION_FAILURE,
        },
      );
      if (authority.assured) {
        const childPreflight =
          preflightWorkflowSpecificReviewApplication(
            workingOutputDir,
            outputDir,
          );
        validatePreflightAcknowledgement(childPreflight, persistedAuthority);
      }
      return persist(authority.args, workingOutputDir);
    },
    {
      ...checkEntriesTransactionOptions("save"),
      validateWholeTree: ({ workingOutputDir }) => {
        const persistedAuthority = validateCheckEntriesAssuranceAuthority(
          workingOutputDir,
          {
          required: assuredWorkflow,
          canonicalOutputDir: outputDir,
          failureMessage: CHECK_ENTRIES_AUTHORIZATION_FAILURE,
          },
        );
        if (assuredWorkflow) {
          const childPreflight =
            preflightWorkflowSpecificReviewApplication(
              workingOutputDir,
              outputDir,
            );
          validatePreflightAcknowledgement(childPreflight, persistedAuthority);
        }
      },
    },
  );
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
    throw new Error("Check Entries persistence requires the current client_engagement context.");
  }
  const contextPath = path.resolve(contextValue);
  if (contextPath !== contextValue || path.basename(contextPath) !== "context.json") {
    throw new Error("Check Entries client_engagement path is invalid.");
  }
  const contextStat = generatedReviewPathEntryStat(contextPath);
  if (
    !contextStat ||
    !contextStat.isFile() ||
    contextStat.isSymbolicLink() ||
    contextStat.nlink !== 1
  ) {
    throw new Error("Check Entries client_engagement context is unavailable.");
  }
  if (!path.isAbsolute(outputReference) && runIntake?.path_reference !== "run_root_relative") {
    throw new Error("Check Entries output reference is not run-root-relative.");
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
    throw new Error("Check Entries output reference leaves the customer run.");
  }
  return resolved;
}

function persistedRunOutputMatchesCurrent(runIntake, outputDir) {
  if (!isPlainObject(runIntake)) return false;
  const outputReference =
    typeof runIntake.output_dir === "string"
      ? runIntake.output_dir.trim()
      : "";
  if (!outputReference) return false;
  if (path.isAbsolute(outputReference)) {
    return path.resolve(outputReference) === path.resolve(outputDir);
  }
  if (runIntake.path_reference !== "run_root_relative") return false;
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    const contextStat = generatedReviewPathEntryStat(contextPath);
    if (
      contextStat?.isFile() &&
      !contextStat.isSymbolicLink() &&
      contextStat.nlink === 1
    ) {
      return (
        path.resolve(candidate, outputReference) === path.resolve(outputDir)
      );
    }
    const parent = path.dirname(candidate);
    if (parent === candidate) return false;
    candidate = parent;
  }
}

function pathEntryStat(targetPath) {
  return generatedReviewPathEntryStat(targetPath);
}

function atomicWriteFileSync(targetPath, payload, encoding = null) {
  return generatedReviewAtomicWriteFileSync(targetPath, payload, encoding);
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

const CHECK_ENTRIES_BASE_PHYSICAL_PATHS = new Set([
  "assurance_envelope.json",
  "check_audit.json",
  "check_results.csv",
  "check_results.xlsx",
  "execution_recipe.json",
  "final_artifacts.json",
  "invoice_inventory.json",
  "normalized_entries.csv",
  "numeric_evidence_ledger.json",
  "pdf_inventory.json",
  "prepared_support_facts.csv",
  "review_handoff.md",
  "review_notes.md",
  "review_payload.json",
  "run_intake.json",
  "support_manifest.json",
  "ui_decisions.json",
]);
function checkEntriesExpectedPhysicalDirectories(expectedFiles) {
  const directories = new Set();
  for (const relativePath of expectedFiles) {
    let parent = path.posix.dirname(relativePath);
    while (parent && parent !== ".") {
      directories.add(parent);
      parent = path.posix.dirname(parent);
    }
  }
  return directories;
}

function checkEntriesPhysicalTree(outputDir) {
  const files = new Set();
  const directories = new Set();
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current)) {
      const candidate = path.join(current, name);
      const observed = fs.lstatSync(candidate);
      const relativePath = path
        .relative(outputDir, candidate)
        .split(path.sep)
        .join("/");
      if (observed.isSymbolicLink()) {
        throw new Error("Check Entries physical output set contains a symlink");
      }
      if (observed.isDirectory()) {
        directories.add(relativePath);
        pending.push(candidate);
        continue;
      }
      if (!observed.isFile() || observed.nlink !== 1) {
        throw new Error("Check Entries physical output set contains an unsafe file");
      }
      files.add(relativePath);
    }
  }
  return { files, directories };
}

function checkEntriesPhysicalReviewPaths(envelope) {
  const successors = envelope.reviewed_decisions.filter(
    (decision) =>
      isPlainObject(decision) &&
      decision.decision_type === "check_entries_review_actions" &&
      ["draft", "reviewed"].includes(decision.status),
  );
  if (successors.length > 1) {
    throw new Error("Check Entries has multiple physical review successors");
  }
  if (!successors.length) return new Set();
  const content = successors[0].content;
  if (!isPlainObject(content) || !Array.isArray(content.effects)) {
    throw new Error("Check Entries physical review successor is malformed");
  }
  const paths = new Set(["applied_decisions.json"]);
  const edits = [];
  for (const effect of content.effects) {
    if (!isPlainObject(effect) || effect.action !== "edit") continue;
    if (effect.target_artifact !== "check_results.csv") {
      throw new Error("Check Entries physical review edit is unsupported");
    }
    const itemId = safePathSegment(effect.item_id, "item");
    const expectedRevision = `revisions/check_results__${itemId}.txt`;
    const expectedBackup =
      `revisions/originals/check_results__${itemId}.csv`;
    if (effect.revision_artifact != null) {
      if (effect.revision_artifact !== expectedRevision) {
        throw new Error("Check Entries physical revision path is stale");
      }
      paths.add(expectedRevision);
    }
    if (effect.original_artifact_backup !== expectedBackup) {
      throw new Error("Check Entries physical backup path is stale");
    }
    paths.add(expectedBackup);
    edits.push(effect);
  }
  if (edits.length) {
    const firstItemId = safePathSegment(edits[0].item_id, "item");
    paths.add(
      `revisions/originals/check_results__${firstItemId}.xlsx`,
    );
  }
  return paths;
}

function validateCheckEntriesPhysicalOutputSet(outputDir, envelope) {
  const expectedFiles = new Set([
    ...CHECK_ENTRIES_BASE_PHYSICAL_PATHS,
    ...checkEntriesPhysicalReviewPaths(envelope),
  ]);
  const expectedDirectories =
    checkEntriesExpectedPhysicalDirectories(expectedFiles);
  const actual = checkEntriesPhysicalTree(outputDir);
  const sameSet = (left, right) =>
    left.size === right.size && [...left].every((value) => right.has(value));
  if (
    !sameSet(actual.files, expectedFiles) ||
    !sameSet(actual.directories, expectedDirectories)
  ) {
    throw new Error("Check Entries physical output set is not exact");
  }
}

const CHECK_ENTRIES_TRANSACTION_FAILURE =
  "Check Entries review transaction failed safely.";
const CHECK_ENTRIES_ROLLBACK_FAILURE =
  "Check Entries review transaction could not be restored safely.";
const CHECK_ENTRIES_AUTHORIZATION_FAILURE =
  "Check Entries persisted review authorization failed.";

function checkEntriesMappedTransactionError(error) {
  const message = error instanceof Error ? error.message : "";
  if (
    message.length > 240 ||
    /[\\/\u0000-\u001f\u007f]/.test(message) ||
    /Traceback|\bFile\s+["']|file:|~[\\/]/i.test(message)
  ) {
    return null;
  }
  if (
    message.startsWith("Check Entries assurance preflight ") ||
    message.startsWith("Check Entries review application ")
  ) {
    return message;
  }
  const fixedMessages = new Set([
    "run_intake.output_dir must be a real directory",
    "run_intake.output_dir cannot contain symbolic links",
    "run_intake.output_dir cannot contain special filesystem entries",
    "run_intake.output_dir cannot contain hardlink aliases",
    "review_payload does not match the persisted assured review",
    CHECK_ENTRIES_AUTHORIZATION_FAILURE,
  ]);
  return fixedMessages.has(message) ? message : null;
}

function checkEntriesTransactionOptions(_kind) {
  return {
    failureMessage: CHECK_ENTRIES_TRANSACTION_FAILURE,
    rollbackFailureMessage: CHECK_ENTRIES_ROLLBACK_FAILURE,
    mapOperationError: checkEntriesMappedTransactionError,
  };
}

function validateCheckEntriesTransactionInput(outputDir) {
  try {
    validateOutputDirectoryTree(outputDir);
  } catch (error) {
    throw new Error(
      checkEntriesMappedTransactionError(error) ||
        CHECK_ENTRIES_TRANSACTION_FAILURE,
    );
  }
}

function readOnlyAssuredReviewArgs(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  if (!outputDir || !hasAssuredCheckEntriesMarker(outputDir)) {
    return inputArgs;
  }
  validateCheckEntriesTransactionInput(outputDir);
  const authority = parentBoundCheckEntriesArgs(inputArgs, { outputDir });
  const persistedAuthority = validateCheckEntriesAssuranceAuthority(outputDir, {
    required: true,
    canonicalOutputDir: outputDir,
    failureMessage: CHECK_ENTRIES_AUTHORIZATION_FAILURE,
  });
  const childPreflight = preflightWorkflowSpecificReviewApplication(outputDir);
  validatePreflightAcknowledgement(childPreflight, persistedAuthority);
  return authority.args;
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
    readJsonFileIfPresent(finalArtifactsPath) ||
    (isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : null) ||
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

function canonicalRunRelativePath(value) {
  if (
    typeof value !== "string" ||
    value !== value.trim() ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const text = value;
  if (
    !text ||
    path.isAbsolute(text) ||
    /^[A-Za-z]:\//.test(text) ||
    text.includes("\\") ||
    text === "." ||
    text.startsWith("./") ||
    text.startsWith("../") ||
    path.posix.normalize(text) !== text
  ) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  return text;
}

const REVIEW_APPLICATION_PATH_FIELDS = [
  "applied_decisions_path",
  "revision_paths",
  "target_update_paths",
  "structured_update_paths",
  "native_regeneration_paths",
  "native_regenerated_paths",
  "downstream_regenerated_paths",
  "original_backup_paths",
];

function declaredCanonicalPaths(record) {
  if (!isPlainObject(record)) return [];
  const paths = [];
  for (const fieldName of REVIEW_APPLICATION_PATH_FIELDS) {
    const value = record[fieldName];
    if (value == null) continue;
    if (Array.isArray(value)) {
      if (!canonicalRunRelativeStringArray(value)) {
        throw new Error("Check Entries review application returned an invalid result.");
      }
      paths.push(...value);
    } else if (typeof value === "string") {
      paths.push(canonicalRunRelativePath(value));
    } else {
      throw new Error("Check Entries review application returned an invalid result.");
    }
  }
  return paths;
}

function collectReviewApplicationPaths(appliedDecisions, finalArtifacts) {
  const paths = ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
  const finalOutputs = Array.isArray(finalArtifacts?.outputs) ? finalArtifacts.outputs : [];
  for (const output of finalOutputs) {
    if (!isPlainObject(output) || typeof output.path !== "string") {
      throw new Error("Check Entries review application returned an invalid result.");
    }
    paths.push(output.path);
  }
  const reviewApplication = isPlainObject(finalArtifacts?.review_application)
    ? finalArtifacts.review_application
    : {};
  paths.push(...declaredCanonicalPaths(appliedDecisions));
  paths.push(...declaredCanonicalPaths(reviewApplication));
  return Array.from(new Set(paths)).map(canonicalRunRelativePath);
}

function canonicalJsonSha256(value) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(canonicalJsonValue(value)), "utf8")
    .digest("hex");
}

function contentSha256IsCurrent(payload) {
  if (!isPlainObject(payload) || !/^[0-9a-f]{64}$/.test(payload.content_sha256 || "")) {
    return false;
  }
  const content = { ...payload };
  delete content.content_sha256;
  return canonicalJsonSha256(content) === payload.content_sha256;
}

function exactObjectFields(value, required, optional = []) {
  if (!isPlainObject(value)) return false;
  const allowed = new Set([...required, ...optional]);
  const keys = Object.keys(value);
  return required.every((field) => Object.hasOwn(value, field)) &&
    keys.every((field) => allowed.has(field));
}

function canonicalIdentifier(value) {
  return (
    typeof value === "string" &&
    value === value.trim() &&
    /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value)
  );
}

function nonEmptyTrimmedString(value) {
  return typeof value === "string" && Boolean(value) && value === value.trim();
}

function stableArtifactBytes(absolutePath) {
  const beforeEntry = fs.lstatSync(absolutePath);
  if (
    !beforeEntry.isFile() ||
    beforeEntry.isSymbolicLink() ||
    beforeEntry.nlink !== 1
  ) {
    throw new Error("invalid artifact entry");
  }
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  const descriptor = fs.openSync(
    absolutePath,
    fs.constants.O_RDONLY | noFollow,
  );
  try {
    const before = fs.fstatSync(descriptor);
    if (!before.isFile() || before.nlink !== 1) {
      throw new Error("invalid artifact entry");
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
      throw new Error("artifact changed while read");
    }
    return payload;
  } finally {
    fs.closeSync(descriptor);
  }
}

function checkEntriesCurrentRunRoot(outputDir) {
  let runRoot = null;
  let candidate = path.resolve(outputDir);
  while (true) {
    const contextPath = path.join(candidate, "context.json");
    const contextStat = generatedReviewPathEntryStat(contextPath);
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
  return runRoot;
}

function resolveCheckEntriesRunReference(outputDir, runIntake, value) {
  if (!nonEmptyTrimmedString(value)) {
    throw new Error("missing assurance roots");
  }
  if (path.isAbsolute(value)) return path.resolve(value);
  const runRoot = checkEntriesCurrentRunRoot(outputDir);
  if (
    !runRoot ||
    runIntake.path_reference !== "run_root_relative" ||
    value.split(/[\\/]+/).includes("..")
  ) {
    throw new Error("missing assurance roots");
  }
  const resolved = path.resolve(runRoot, value);
  const relative = path.relative(runRoot, resolved);
  if (
    relative === "" ||
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error("missing assurance roots");
  }
  return resolved;
}

function checkEntriesArtifactRoots(outputDir, audit) {
  if (
    !nonEmptyTrimmedString(audit.journal) ||
    !nonEmptyTrimmedString(audit.pdf_path)
  ) {
    throw new Error("missing assurance roots");
  }
  const runIntake = readJsonFileIfPresent(path.join(outputDir, "run_intake.json")) || {};
  const resolveSource = (value) => {
    return resolveCheckEntriesRunReference(outputDir, runIntake, value);
  };
  const journalPath = resolveSource(audit.journal);
  const supportPath = resolveSource(audit.pdf_path);
  const supportEntry = fs.lstatSync(supportPath);
  return {
    normalization: path.dirname(journalPath),
    support: supportEntry.isDirectory() ? supportPath : path.dirname(supportPath),
    run: path.resolve(outputDir),
    implementation: PLUGIN_ROOT,
    assurance_implementation: ASSURANCE_IMPLEMENTATION_ROOT,
  };
}

function checkEntriesImplementationMediaType(relativePath) {
  const extension = path.posix.extname(relativePath).toLowerCase();
  return {
    ".cjs": "text/javascript",
    ".html": "text/html",
    ".json": "application/json",
    ".py": "text/x-python",
    ".svg": "image/svg+xml",
  }[extension];
}

function checkEntriesImplementationSpecifications() {
  const specification = (namespace, rootId, relativePath) => ({
    artifact_id:
      `implementation.${namespace}.${relativePath.replaceAll("/", ".")}`,
    root_id: rootId,
    role: "implementation",
    path: relativePath,
    media_type: checkEntriesImplementationMediaType(relativePath),
  });
  return [
    ...CHECK_ENTRIES_PLUGIN_IMPLEMENTATION_PATHS.map((relativePath) =>
      specification("check_entries", "implementation", relativePath),
    ),
    ...CHECK_ENTRIES_SHARED_IMPLEMENTATION_PATHS.map((relativePath) =>
      specification(
        "vera_assurance",
        "assurance_implementation",
        relativePath,
      ),
    ),
  ];
}

function validateCheckEntriesOrdinaryImplementationPath(
  rootPath,
  relativePath,
) {
  const rootEntry = fs.lstatSync(rootPath);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("Check Entries implementation root is unsafe");
  }
  let current = rootPath;
  const parts = relativePath.split("/");
  for (const [index, part] of parts.entries()) {
    current = path.join(current, part);
    const observed = fs.lstatSync(current);
    if (observed.isSymbolicLink()) {
      throw new Error("Check Entries implementation path is unsafe");
    }
    if (index < parts.length - 1) {
      if (!observed.isDirectory()) {
        throw new Error("Check Entries implementation parent is unsafe");
      }
      continue;
    }
    if (!observed.isFile() || observed.nlink !== 1) {
      throw new Error("Check Entries implementation file is unsafe");
    }
  }
}

function validateCheckEntriesImplementationContract(
  envelope,
  roots,
  artifactById,
) {
  const specifications = checkEntriesImplementationSpecifications();
  const expectedIds = specifications.map(
    (specification) => specification.artifact_id,
  );
  if (
    !Array.isArray(envelope.implementation_artifact_refs) ||
    !canonicalJsonEqual(envelope.implementation_artifact_refs, expectedIds)
  ) {
    throw new Error("Check Entries implementation reference set is not exact");
  }
  const implementationReceipts = envelope.artifact_receipts.filter(
    (receipt) => isPlainObject(receipt) && receipt.role === "implementation",
  );
  if (implementationReceipts.length !== specifications.length) {
    throw new Error("Check Entries implementation receipt set is not exact");
  }
  if (
    !canonicalJsonEqual(
      implementationReceipts.map((receipt) => receipt.artifact_id),
      expectedIds,
    )
  ) {
    throw new Error("Check Entries implementation receipt order is not canonical");
  }
  for (const specification of specifications) {
    const receipt = artifactById.get(specification.artifact_id);
    if (
      !isPlainObject(receipt) ||
      !canonicalFieldEqual(receipt, specification, "artifact_id") ||
      !canonicalFieldEqual(receipt, specification, "root_id") ||
      !canonicalFieldEqual(receipt, specification, "role") ||
      !canonicalFieldEqual(receipt, specification, "path") ||
      !canonicalFieldEqual(receipt, specification, "media_type")
    ) {
      throw new Error("Check Entries implementation receipt is malformed");
    }
    validateCheckEntriesOrdinaryImplementationPath(
      roots[specification.root_id],
      specification.path,
    );
  }
}

function validateArtifactReceiptAgainstRoots(roots, receipt) {
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
    !exactObjectFields(receipt, required, ["media_type"]) ||
    receipt.schema_version !== "vera.artifact_receipt.v1" ||
    !canonicalIdentifier(receipt.artifact_id) ||
    !canonicalIdentifier(receipt.root_id) ||
    !nonEmptyTrimmedString(receipt.role) ||
    !Object.hasOwn(roots, receipt.root_id) ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0 ||
    !/^[0-9a-f]{64}$/.test(receipt.sha256)
  ) {
    throw new Error("invalid artifact receipt");
  }
  if (
    receipt.media_type != null &&
    !nonEmptyTrimmedString(receipt.media_type)
  ) {
    throw new Error("invalid artifact receipt");
  }
  const relativePath = canonicalRunRelativePath(receipt.path);
  const rootPath = path.resolve(roots[receipt.root_id]);
  const rootEntry = fs.lstatSync(rootPath);
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("invalid artifact root");
  }
  const resolvedRoot = fs.realpathSync.native(rootPath);
  const unresolvedPath = path.join(resolvedRoot, relativePath);
  const resolvedPath = fs.realpathSync.native(unresolvedPath);
  const relativeToRoot = path.relative(resolvedRoot, resolvedPath);
  if (
    relativeToRoot.startsWith("..") ||
    path.isAbsolute(relativeToRoot) ||
    relativeToRoot === ""
  ) {
    throw new Error("artifact receipt escapes root");
  }
  const payload = stableArtifactBytes(resolvedPath);
  const digest = crypto.createHash("sha256").update(payload).digest("hex");
  if (payload.length !== receipt.byte_count || digest !== receipt.sha256) {
    throw new Error("artifact receipt is stale");
  }
  return receipt;
}

const CHECK_ENTRIES_GATE_NAMES = [
  "source",
  "preparation",
  "reconciliation",
  "semantic_review",
  "reporting",
  "publication",
];
const CHECK_ENTRIES_GATE_STATUSES = new Set([
  "passed",
  "failed",
  "blocked",
  "not_assessed",
  "not_applicable",
  "withheld",
]);
const CHECK_ENTRIES_GATE_DEPENDENCIES = {
  preparation: ["source"],
  reconciliation: ["preparation"],
  semantic_review: ["preparation"],
  reporting: ["reconciliation", "semantic_review"],
  publication: ["reporting"],
};

function validateCheckEntriesGateRegister(value) {
  if (
    !exactObjectFields(value, ["schema_version", "gates", "report_ready"]) ||
    value.schema_version !== "vera.assurance_gates.v1" ||
    typeof value.report_ready !== "boolean" ||
    !isPlainObject(value.gates) ||
    !canonicalJsonEqual(Object.keys(value.gates).sort(), [...CHECK_ENTRIES_GATE_NAMES].sort())
  ) {
    throw new Error("invalid assurance gate register");
  }
  for (const gateName of CHECK_ENTRIES_GATE_NAMES) {
    const gate = value.gates[gateName];
    if (
      !exactObjectFields(gate, ["status", "evidence_refs", "limitations"]) ||
      !CHECK_ENTRIES_GATE_STATUSES.has(gate.status) ||
      !Array.isArray(gate.evidence_refs) ||
      !Array.isArray(gate.limitations) ||
      !gate.evidence_refs.every(canonicalIdentifier) ||
      new Set(gate.evidence_refs).size !== gate.evidence_refs.length ||
      !gate.limitations.every(nonEmptyTrimmedString) ||
      (gate.status === "passed" && gate.evidence_refs.length === 0)
    ) {
      throw new Error("invalid assurance gate");
    }
    if (gate.status === "passed") {
      for (const dependency of CHECK_ENTRIES_GATE_DEPENDENCIES[gateName] || []) {
        if (!["passed", "not_applicable"].includes(value.gates[dependency].status)) {
          throw new Error("invalid assurance gate dependency");
        }
      }
    }
  }
  const ready = [
    "source",
    "preparation",
    "reconciliation",
    "semantic_review",
    "reporting",
  ].every((name) =>
    ["passed", "not_applicable"].includes(value.gates[name].status),
  );
  if (value.report_ready !== ready) {
    throw new Error("invalid assurance readiness");
  }
  return value;
}

function validateCheckEntriesEnvelopeStructure(envelope, roots) {
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
    !exactObjectFields(envelope, required) ||
    envelope.schema_version !== "vera.assurance_envelope.v1" ||
    !canonicalIdentifier(envelope.run_id) ||
    !canonicalIdentifier(envelope.workflow_id) ||
    !canonicalIdentifier(envelope.workflow_version) ||
    !contentSha256IsCurrent(envelope) ||
    !Array.isArray(envelope.artifact_receipts) ||
    !Array.isArray(envelope.implementation_artifact_refs) ||
    !Array.isArray(envelope.reviewed_decisions) ||
    !Array.isArray(envelope.source_qualifications) ||
    !Array.isArray(envelope.allocation_ledgers) ||
    !Array.isArray(envelope.numeric_evidence_ledgers) ||
    !Array.isArray(envelope.limitations) ||
    !envelope.limitations.every(nonEmptyTrimmedString)
  ) {
    throw new Error("invalid assurance envelope");
  }
  const artifactById = new Map();
  const artifactPaths = new Set();
  for (const receipt of envelope.artifact_receipts) {
    validateArtifactReceiptAgainstRoots(roots, receipt);
    const pathKey = `${receipt.root_id}\u0000${receipt.path}`;
    if (artifactById.has(receipt.artifact_id) || artifactPaths.has(pathKey)) {
      throw new Error("duplicate assurance artifact");
    }
    artifactById.set(receipt.artifact_id, receipt);
    artifactPaths.add(pathKey);
  }
  if (
    envelope.implementation_artifact_refs.length === 0 ||
    !envelope.implementation_artifact_refs.every(canonicalIdentifier) ||
    new Set(envelope.implementation_artifact_refs).size !==
      envelope.implementation_artifact_refs.length ||
    envelope.implementation_artifact_refs.some(
      (reference) => artifactById.get(reference)?.role !== "implementation",
    )
  ) {
    throw new Error("invalid implementation receipt references");
  }
  const decisionById = new Map();
  for (const decision of envelope.reviewed_decisions) {
    const fields = [
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
      !exactObjectFields(decision, fields) ||
      decision.schema_version !== "vera.reviewed_decision_receipt.v1" ||
      !canonicalIdentifier(decision.decision_id) ||
      !canonicalIdentifier(decision.decision_type) ||
      !["draft", "reviewed", "rejected", "superseded"].includes(decision.status) ||
      !canonicalIdentifier(decision.reviewer_ref) ||
      !canonicalIdentifier(decision.adapter_id) ||
      !canonicalIdentifier(decision.adapter_version) ||
      !Array.isArray(decision.source_artifact_refs) ||
      decision.source_artifact_refs.length === 0 ||
      !decision.source_artifact_refs.every(
        (reference) => artifactById.get(reference)?.role === "source",
      ) ||
      !isPlainObject(decision.content) ||
      canonicalJsonSha256(decision.content) !== decision.content_sha256 ||
      decisionById.has(decision.decision_id)
    ) {
      throw new Error("invalid reviewed decision receipt");
    }
    decisionById.set(decision.decision_id, decision);
  }
  const qualificationById = new Map();
  for (const qualification of envelope.source_qualifications) {
    if (
      !isPlainObject(qualification) ||
      qualification.schema_version !== "vera.source_qualification.v1" ||
      !canonicalIdentifier(qualification.qualification_id) ||
      !["qualified", "needs_review", "unsupported_source_layout"].includes(
        qualification.status,
      ) ||
      !Array.isArray(qualification.source_artifact_refs) ||
      qualification.source_artifact_refs.length === 0 ||
      !qualification.source_artifact_refs.every(
        (reference) => artifactById.get(reference)?.role === "source",
      ) ||
      qualificationById.has(qualification.qualification_id)
    ) {
      throw new Error("invalid source qualification");
    }
    qualificationById.set(qualification.qualification_id, qualification);
  }
  const allocationById = new Map();
  for (const ledger of envelope.allocation_ledgers) {
    if (
      !isPlainObject(ledger) ||
      !canonicalIdentifier(ledger.ledger_id) ||
      allocationById.has(ledger.ledger_id)
    ) {
      throw new Error("invalid allocation ledger");
    }
    allocationById.set(ledger.ledger_id, ledger);
  }
  const numericById = new Map();
  for (const ledger of envelope.numeric_evidence_ledgers) {
    const content = isPlainObject(ledger) ? { ...ledger } : null;
    const digest = content?.content_sha256;
    if (content) delete content.content_sha256;
    if (
      !isPlainObject(ledger) ||
      ledger.schema_version !== "vera.numeric_evidence_ledger.v1" ||
      !canonicalIdentifier(ledger.ledger_id) ||
      !Array.isArray(ledger.entries) ||
      ledger.entries.length === 0 ||
      canonicalJsonSha256(content) !== digest ||
      numericById.has(ledger.ledger_id)
    ) {
      throw new Error("invalid numeric evidence ledger");
    }
    numericById.set(ledger.ledger_id, ledger);
  }
  const gates = validateCheckEntriesGateRegister(envelope.gate_register);
  const knownReferences = new Set([
    ...artifactById.keys(),
    ...decisionById.keys(),
    ...qualificationById.keys(),
    ...allocationById.keys(),
    ...numericById.keys(),
  ]);
  for (const gate of Object.values(gates.gates)) {
    if (gate.evidence_refs.some((reference) => !knownReferences.has(reference))) {
      throw new Error("assurance gate references unknown evidence");
    }
  }
  const sourceGate = gates.gates.source;
  if (
    sourceGate.status === "passed" &&
    (qualificationById.size === 0 ||
      [...qualificationById.values()].some(
        (qualification) => qualification.status !== "qualified",
      ) ||
      [...qualificationById.keys()].some(
        (reference) => !sourceGate.evidence_refs.includes(reference),
      ))
  ) {
    throw new Error("source gate lacks qualified evidence");
  }
  const semanticGate = gates.gates.semantic_review;
  const semanticDecisionTypes = new Set([
    "accounting_conclusion",
    "audit_conclusion",
    "check_entries_review_actions",
    "evidence_sufficiency_review",
    "journal_bank_review_application",
    "professional_review",
    "semantic_review",
  ]);
  if (
    semanticGate.status === "passed" &&
    !semanticGate.evidence_refs.some((reference) => {
      const decision = decisionById.get(reference);
      return (
        decision?.status === "reviewed" &&
        semanticDecisionTypes.has(decision.decision_type)
      );
    })
  ) {
    throw new Error("semantic gate lacks a reviewed decision");
  }
  const hasArtifactRole = (gateName, allowedRoles) =>
    gates.gates[gateName].evidence_refs.some((reference) =>
      allowedRoles.has(artifactById.get(reference)?.role),
    );
  if (
    gates.gates.preparation.status === "passed" &&
    !hasArtifactRole("preparation", new Set(["prepared", "output", "workpaper"]))
  ) {
    throw new Error("preparation gate lacks work-product evidence");
  }
  if (
    gates.gates.reconciliation.status === "passed" &&
    !gates.gates.reconciliation.evidence_refs.some(
      (reference) =>
        allocationById.has(reference) ||
        numericById.has(reference) ||
        ["output", "workpaper"].includes(artifactById.get(reference)?.role),
    )
  ) {
    throw new Error("reconciliation gate lacks evidence");
  }
  if (
    gates.gates.reporting.status === "passed" &&
    !gates.gates.reporting.evidence_refs.some(
      (reference) =>
        numericById.has(reference) ||
        ["output", "report", "rendered", "workpaper"].includes(
          artifactById.get(reference)?.role,
        ),
    )
  ) {
    throw new Error("reporting gate lacks evidence");
  }
  return { artifactById, gates };
}

function validateCheckEntriesAssuranceAuthority(
  outputDir,
  {
    required = false,
    canonicalOutputDir = outputDir,
    failureMessage = CHECK_ENTRIES_AUTHORIZATION_FAILURE,
  } = {},
) {
  try {
    const marker = hasAssuredCheckEntriesMarker(outputDir);
    if (!marker && !required) return noAssurancePreflight();
    const runIntake = readJsonFileIfPresent(path.join(outputDir, "run_intake.json"));
    const reviewPayload = readJsonFileIfPresent(
      path.join(outputDir, "review_payload.json"),
    );
    const uiDecisions = readJsonFileIfPresent(
      path.join(outputDir, "ui_decisions.json"),
    );
    const finalArtifacts = readJsonFileIfPresent(
      path.join(outputDir, "final_artifacts.json"),
    );
    const envelope = readJsonFileIfPresent(
      path.join(outputDir, "assurance_envelope.json"),
    );
    const audit = readJsonFileIfPresent(path.join(outputDir, "check_audit.json"));
    if (
      [runIntake, reviewPayload, uiDecisions, finalArtifacts, envelope, audit].some(
        (value) => !isPlainObject(value),
      ) ||
      !contentSha256IsCurrent(reviewPayload) ||
      !contentSha256IsCurrent(audit)
    ) {
      throw new Error("missing or stale assurance state");
    }
    const runId = runIntake.run_id;
    if (
      !canonicalIdentifier(runId) ||
      [reviewPayload, uiDecisions, finalArtifacts, envelope, audit].some(
        (value) => value.run_id !== runId,
      ) ||
      !persistedRunOutputMatchesCurrent(runIntake, canonicalOutputDir)
    ) {
      throw new Error("assurance run identity mismatch");
    }
    const roots = checkEntriesArtifactRoots(outputDir, audit);
    const validatedEnvelope = validateCheckEntriesEnvelopeStructure(
      envelope,
      roots,
    );
    validateCheckEntriesImplementationContract(
      envelope,
      roots,
      validatedEnvelope.artifactById,
    );
    const gateRegister = validatedEnvelope.gates;
    const reviewSummary = reviewPayload.summary;
    if (
      !isPlainObject(reviewSummary) ||
      !canonicalJsonEqual(reviewSummary.assurance_gates, gateRegister) ||
      !canonicalJsonEqual(audit.assurance_gates, gateRegister) ||
      !canonicalJsonEqual(finalArtifacts.assurance_gates, gateRegister)
    ) {
      throw new Error("assurance gate binding mismatch");
    }
    const professionalStatus = audit.professional_conclusion_status;
    if (
      !["pending_review", "reviewed", "withheld"].includes(professionalStatus) ||
      reviewSummary.professional_conclusion_status !== professionalStatus ||
      finalArtifacts.professional_conclusion_status !== professionalStatus ||
      (gateRegister.report_ready && professionalStatus !== "reviewed") ||
      (finalArtifacts.status === "final_ready" &&
        (!gateRegister.report_ready || professionalStatus !== "reviewed"))
    ) {
      throw new Error("professional status binding mismatch");
    }
    if (
      uiDecisions.review_payload_content_sha256 !== reviewPayload.content_sha256 ||
      finalArtifacts.review_payload_content_sha256 !==
        reviewPayload.content_sha256
    ) {
      throw new Error("review payload binding mismatch");
    }
    const canonicalEnvelopePath = path.join(
      path.resolve(canonicalOutputDir),
      "assurance_envelope.json",
    );
    for (const binding of [
      audit.assurance_envelope,
      finalArtifacts.assurance_envelope,
    ]) {
      if (
        !isPlainObject(binding) ||
        resolveCheckEntriesRunReference(
          outputDir,
          runIntake,
          binding.path,
        ) !== canonicalEnvelopePath ||
        binding.content_sha256 !== envelope.content_sha256 ||
        !canonicalJsonEqual(
          binding.artifact_receipt,
          audit.assurance_envelope.artifact_receipt,
        )
      ) {
        throw new Error("assurance envelope binding mismatch");
      }
    }
    validateArtifactReceiptAgainstRoots(
      roots,
      audit.assurance_envelope.artifact_receipt,
    );
    for (const fieldName of [
      "input_artifact_receipts",
      "output_artifact_receipts",
    ]) {
      if (!Array.isArray(audit[fieldName])) {
        throw new Error("audit receipts are missing");
      }
      for (const receipt of audit[fieldName]) {
        validateArtifactReceiptAgainstRoots(roots, receipt);
      }
    }
    const reviewBinding = audit.review_payload_binding;
    if (reviewBinding != null) {
      if (
        !isPlainObject(reviewBinding) ||
        reviewBinding.content_sha256 !== reviewPayload.content_sha256 ||
        !isPlainObject(reviewBinding.artifact_receipt) ||
        reviewBinding.artifact_receipt.root_id !== "run" ||
        reviewBinding.artifact_receipt.path !== "review_payload.json"
      ) {
        throw new Error("audit review binding mismatch");
      }
      validateArtifactReceiptAgainstRoots(roots, reviewBinding.artifact_receipt);
      const envelopeReceipt = validatedEnvelope.artifactById.get(
        reviewBinding.artifact_receipt.artifact_id,
      );
      if (!canonicalJsonEqual(envelopeReceipt, reviewBinding.artifact_receipt)) {
        throw new Error("envelope review binding mismatch");
      }
    }
    for (const output of Array.isArray(finalArtifacts.outputs)
      ? finalArtifacts.outputs
      : []) {
      if (isPlainObject(output?.artifact_receipt)) {
        validateArtifactReceiptAgainstRoots(roots, output.artifact_receipt);
      }
    }
    validateCheckEntriesPhysicalOutputSet(outputDir, envelope);
    return {
      ok: true,
      assurance_replayed: true,
      report_ready: gateRegister.report_ready,
      professional_conclusion_status: professionalStatus,
      envelope_content_sha256: envelope.content_sha256,
    };
  } catch {
    throw new Error(failureMessage);
  }
}

function validateRunArtifactReceipt(outputDir, receipt) {
  if (
    !isPlainObject(receipt) ||
    receipt.root_id !== "run" ||
    !/^[0-9a-f]{64}$/.test(receipt.sha256 || "") ||
    !Number.isInteger(receipt.byte_count) ||
    receipt.byte_count < 0
  ) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const relativePath = canonicalRunRelativePath(receipt.path);
  const absolutePath = path.join(outputDir, relativePath);
  const entryStat = pathEntryStat(absolutePath);
  if (!entryStat || !entryStat.isFile() || entryStat.isSymbolicLink() || entryStat.nlink !== 1) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const payload = fs.readFileSync(absolutePath);
  const digest = crypto.createHash("sha256").update(payload).digest("hex");
  if (payload.length !== receipt.byte_count || digest !== receipt.sha256) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
}

function validatePersistedAssurancePostcondition(
  outputDir,
  persistedApplied,
  persistedFinalArtifacts,
  canonicalOutputDir,
) {
  if (persistedApplied.assurance_replayed !== true) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const envelope = readJsonFileIfPresent(
    path.join(outputDir, "assurance_envelope.json"),
  );
  const audit = readJsonFileIfPresent(path.join(outputDir, "check_audit.json"));
  if (
    persistedApplied.assurance_envelope_content_sha256 !== envelope.content_sha256 ||
    persistedFinalArtifacts?.assurance_envelope?.content_sha256 !== envelope.content_sha256 ||
    audit?.assurance_envelope?.content_sha256 !== envelope.content_sha256
  ) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const persistedAuthority = validateCheckEntriesAssuranceAuthority(outputDir, {
    required: true,
    canonicalOutputDir,
    failureMessage: "Check Entries review application returned an invalid result.",
  });
  const childPreflight = preflightWorkflowSpecificReviewApplication(outputDir);
  validatePreflightAcknowledgement(childPreflight, persistedAuthority);
}

function canonicalJsonEqual(left, right) {
  return JSON.stringify(canonicalJsonValue(left)) === JSON.stringify(canonicalJsonValue(right));
}

function canonicalFieldEqual(left, right, fieldName) {
  const leftHasField = Object.prototype.hasOwnProperty.call(left, fieldName);
  const rightHasField = Object.prototype.hasOwnProperty.call(right, fieldName);
  return (
    leftHasField === rightHasField &&
    (!leftHasField || canonicalJsonEqual(left[fieldName], right[fieldName]))
  );
}

function immutableWorkflowEffect(effect) {
  if (!isPlainObject(effect)) return null;
  const immutable = { ...effect };
  delete immutable.requires_native_regeneration;
  delete immutable.native_regeneration_status;
  delete immutable.native_regenerated_paths;
  return immutable;
}

function expectedWorkflowNativeBackupPaths(expectedEffects, expectedFinalOutputPaths) {
  const candidate = expectedEffects.find(
    (effect) =>
      isPlainObject(effect) &&
      effect.requires_native_regeneration === true &&
      nativeRegenerationPathsForEffect(effect).includes("check_results.xlsx"),
  );
  if (!candidate || !expectedFinalOutputPaths.includes("check_results.xlsx")) {
    return [];
  }
  const itemId = safePathSegment(candidate.item_id, "item");
  return [`revisions/originals/check_results__${itemId}.xlsx`];
}

function validateFinalOutputPostcondition(outputDir, finalOutputs, allowedPaths) {
  if (!Array.isArray(finalOutputs)) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
  const actualPaths = [];
  for (const output of finalOutputs) {
    if (!isPlainObject(output)) {
      throw new Error("Check Entries review application returned an invalid result.");
    }
    const outputPath = canonicalRunRelativePath(output.path);
    if (outputPath !== output.path) {
      throw new Error("Check Entries review application returned an invalid result.");
    }
    actualPaths.push(outputPath);
    for (const fieldName of ["source_artifact", "revision_artifact"]) {
      const value = output[fieldName];
      if (value != null && canonicalRunRelativePath(value) !== value) {
        throw new Error("Check Entries review application returned an invalid result.");
      }
    }
    const absolutePath = path.join(outputDir, outputPath);
    const outputStat = pathEntryStat(absolutePath);
    if (
      !outputStat ||
      !outputStat.isFile() ||
      outputStat.isSymbolicLink() ||
      outputStat.nlink !== 1 ||
      (output.size_bytes != null &&
        (!Number.isInteger(output.size_bytes) ||
          output.size_bytes < 0 ||
          output.size_bytes !== outputStat.size))
    ) {
      throw new Error("Check Entries review application returned an invalid result.");
    }
    if (output.artifact_receipt != null) {
      if (
        !isPlainObject(output.artifact_receipt) ||
        output.artifact_receipt.root_id !== "run" ||
        output.artifact_receipt.path !== outputPath
      ) {
        throw new Error("Check Entries review application returned an invalid result.");
      }
      validateRunArtifactReceipt(outputDir, output.artifact_receipt);
    }
  }
  const uniqueActualPaths = Array.from(new Set(actualPaths));
  const uniqueAllowedPaths = Array.from(new Set(allowedPaths));
  if (
    uniqueActualPaths.length !== actualPaths.length ||
    !canonicalJsonEqual(uniqueActualPaths.sort(), uniqueAllowedPaths.sort())
  ) {
    throw new Error("Check Entries review application returned an invalid result.");
  }
}

function validatePersistedWorkflowApplication({
  appliedOutputPath,
  finalArtifactsPath,
  outputDir,
  expectedRunId,
  expectedDecisionCount,
  expectedItemCount,
  expectedPlugin,
  expectedWorkflow,
  expectedDecisions,
  expectedReviewPayloadPath,
  expectedReviewPayloadSha256,
  expectedReviewType,
  expectedNativePaths,
  expectedAppliedDecisions,
  expectedFinalArtifacts,
  assurancePreflight,
  canonicalOutputDir,
}) {
  const invalid = () => {
    throw new Error("Check Entries review application returned an invalid result.");
  };
  const persistedApplied = readJsonFileIfPresent(appliedOutputPath);
  const persistedFinalArtifacts = readJsonFileIfPresent(finalArtifactsPath);
  if (!persistedApplied || !persistedFinalArtifacts) invalid();
  if (
    persistedApplied.run_id !== expectedRunId ||
    persistedApplied.plugin !== expectedPlugin ||
    persistedApplied.workflow !== expectedWorkflow ||
    persistedApplied.decision_count !== expectedDecisionCount ||
    persistedApplied.item_count !== expectedItemCount ||
    !canonicalJsonEqual(persistedApplied.decisions, expectedDecisions) ||
    !isPlainObject(persistedApplied.review_payload) ||
    persistedApplied.review_payload.path !== expectedReviewPayloadPath ||
    canonicalRunRelativePath(persistedApplied.review_payload.path) !==
      persistedApplied.review_payload.path ||
    persistedApplied.review_payload.content_sha256 !== expectedReviewPayloadSha256 ||
    persistedApplied.review_payload.item_count !== expectedItemCount ||
    persistedApplied.review_payload.review_type !== expectedReviewType ||
    !Array.isArray(persistedApplied.effects) ||
    persistedApplied.effects.length !== expectedDecisionCount ||
    persistedFinalArtifacts.status !== persistedApplied.application_status ||
    persistedFinalArtifacts.review_status !== persistedApplied.application_status
  ) {
    invalid();
  }
  if (!isPlainObject(expectedAppliedDecisions) || !isPlainObject(expectedFinalArtifacts)) {
    invalid();
  }
  for (const fieldName of [
    "schema_version",
    "applied_at",
    "decision_source",
    "blocker_count",
    "revision_count",
    "revision_paths",
    "target_update_count",
    "target_update_paths",
    "structured_update_count",
    "structured_update_paths",
    "assurance_preflight",
    "reviewer",
  ]) {
    if (!canonicalFieldEqual(persistedApplied, expectedAppliedDecisions, fieldName)) {
      invalid();
    }
  }
  const expectedEffects = Array.isArray(expectedAppliedDecisions.effects)
    ? expectedAppliedDecisions.effects
    : null;
  if (
    expectedEffects == null ||
    expectedEffects.length !== persistedApplied.effects.length
  ) {
    invalid();
  }
  for (let index = 0; index < expectedEffects.length; index += 1) {
    const expectedEffect = expectedEffects[index];
    const persistedEffect = persistedApplied.effects[index];
    if (
      !isPlainObject(expectedEffect) ||
      !isPlainObject(persistedEffect) ||
      !canonicalJsonEqual(
        immutableWorkflowEffect(persistedEffect),
        immutableWorkflowEffect(expectedEffect),
      )
    ) {
      invalid();
    }
    const expectedRegeneration =
      expectedEffect.requires_native_regeneration === true &&
      nativeRegenerationPathsForEffect(expectedEffect).includes("check_results.xlsx");
    if (expectedRegeneration) {
      if (
        persistedEffect.requires_native_regeneration !== false ||
        persistedEffect.native_regeneration_status !== "regenerated" ||
        !canonicalJsonEqual(
          persistedEffect.native_regenerated_paths,
          ["check_results.xlsx"],
        )
      ) {
        invalid();
      }
    } else {
      for (const fieldName of [
        "requires_native_regeneration",
        "native_regeneration_status",
        "native_regenerated_paths",
      ]) {
        if (!canonicalFieldEqual(persistedEffect, expectedEffect, fieldName)) {
          invalid();
        }
      }
    }
  }
  for (const fieldName of [
    "schema_version",
    "plugin",
    "workflow",
    "run_id",
    "completed_at",
    "caveats",
    "blockers",
    "professional_conclusion_status",
  ]) {
    if (!canonicalFieldEqual(persistedFinalArtifacts, expectedFinalArtifacts, fieldName)) {
      invalid();
    }
  }
  const expectedApplicationStatus = statusFromEffects(
    persistedApplied.effects,
    expectedItemCount,
    assurancePreflight,
  );
  if (
    persistedApplied.application_status !== expectedApplicationStatus
  ) {
    invalid();
  }
  const pendingNativePaths = Array.isArray(persistedApplied.native_regeneration_paths)
    ? persistedApplied.native_regeneration_paths
    : null;
  const regeneratedNativePaths = Array.isArray(persistedApplied.native_regenerated_paths)
    ? persistedApplied.native_regenerated_paths
    : null;
  const expectedCanonicalNativePaths = expectedNativePaths.map(canonicalRunRelativePath);
  const expectedRegeneratedNativePaths = expectedCanonicalNativePaths.filter(
    (nativePath) => nativePath === "check_results.xlsx",
  );
  const expectedPendingNativePaths = expectedCanonicalNativePaths.filter(
    (nativePath) => nativePath !== "check_results.xlsx",
  );
  if (
    pendingNativePaths == null ||
    regeneratedNativePaths == null ||
    !canonicalRunRelativeStringArray(pendingNativePaths) ||
    !canonicalRunRelativeStringArray(regeneratedNativePaths) ||
    !canonicalJsonEqual(pendingNativePaths, expectedPendingNativePaths) ||
    !canonicalJsonEqual(regeneratedNativePaths, expectedRegeneratedNativePaths) ||
    persistedApplied.native_regeneration_count !== pendingNativePaths.length ||
    persistedApplied.native_regenerated_count !==
      expectedRegeneratedNativePaths.length
  ) {
    invalid();
  }
  const persistedBackupPaths = Array.isArray(persistedApplied.original_backup_paths)
    ? persistedApplied.original_backup_paths
    : null;
  const expectedFinalOutputs = Array.isArray(expectedFinalArtifacts.outputs)
    ? expectedFinalArtifacts.outputs
    : null;
  if (expectedFinalOutputs == null) invalid();
  const expectedFinalOutputPaths = expectedFinalOutputs.map((output) => {
    if (!isPlainObject(output)) invalid();
    return canonicalRunRelativePath(output.path);
  });
  const expectedNativeBackupPaths = expectedWorkflowNativeBackupPaths(
    expectedEffects,
    expectedFinalOutputPaths,
  );
  const expectedOriginalBackupPaths = [
    ...(Array.isArray(expectedAppliedDecisions.original_backup_paths)
      ? expectedAppliedDecisions.original_backup_paths
      : []),
    ...expectedNativeBackupPaths,
  ];
  if (
    persistedBackupPaths == null ||
    !canonicalRunRelativeStringArray(persistedBackupPaths) ||
    !canonicalJsonEqual(persistedBackupPaths, expectedOriginalBackupPaths)
  ) {
    invalid();
  }
  let regeneratedEffectCount = 0;
  let blockerCount = 0;
  const effectRegeneratedPaths = [];
  const effectPendingPaths = [];
  const effectRevisionPaths = [];
  const effectTargetUpdatePaths = [];
  const effectStructuredUpdatePaths = [];
  for (const effect of persistedApplied.effects) {
    if (!isPlainObject(effect)) invalid();
    const effectPaths =
      effect.native_regenerated_paths == null ? [] : effect.native_regenerated_paths;
    const pendingEffectPaths =
      effect.native_regeneration_paths == null ? [] : effect.native_regeneration_paths;
    const derivedEffectPaths =
      effect.derived_native_regeneration_paths == null
        ? []
        : effect.derived_native_regeneration_paths;
    if (
      !canonicalRunRelativeStringArray(effectPaths) ||
      !canonicalRunRelativeStringArray(pendingEffectPaths) ||
      !canonicalRunRelativeStringArray(derivedEffectPaths) ||
      effect.native_regeneration_status === "regenerated" &&
      (effect.requires_native_regeneration !== false ||
        effectPaths.length === 0)
    ) {
      invalid();
    }
    if (effect.native_regeneration_status === "regenerated") {
      regeneratedEffectCount += 1;
      effectRegeneratedPaths.push(...effectPaths);
    }
    if (effect.requires_native_regeneration === true) {
      effectPendingPaths.push(...pendingEffectPaths);
    }
    if (effect.requires_followup === true) blockerCount += 1;
    if (effect.revision_artifact != null) {
      effectRevisionPaths.push(effect.revision_artifact);
    }
    if (
      ["target_artifact_updated", "structured_artifact_updated"].includes(
        effect.artifact_update,
      )
    ) {
      effectTargetUpdatePaths.push(effect.target_artifact);
    }
    if (effect.artifact_update === "structured_artifact_updated") {
      effectStructuredUpdatePaths.push(effect.target_artifact);
    }
    for (const fieldName of [
      "target_artifact",
      "revision_artifact",
      "original_artifact_backup",
    ]) {
      const value = effect[fieldName];
      if (value != null && canonicalRunRelativePath(value) !== value) {
        invalid();
      }
    }
  }
  const finalReviewApplication = persistedFinalArtifacts.review_application;
  const uniqueSorted = (values) => Array.from(new Set(values)).sort();
  if (
    persistedApplied.blocker_count !== blockerCount ||
    persistedApplied.revision_count !== effectRevisionPaths.length ||
    !canonicalJsonEqual(persistedApplied.revision_paths, effectRevisionPaths) ||
    persistedApplied.target_update_count !== effectTargetUpdatePaths.length ||
    !canonicalJsonEqual(
      persistedApplied.target_update_paths,
      effectTargetUpdatePaths,
    ) ||
    persistedApplied.structured_update_count !== effectStructuredUpdatePaths.length ||
    !canonicalJsonEqual(
      persistedApplied.structured_update_paths,
      effectStructuredUpdatePaths,
    ) ||
    persistedApplied.native_regenerated_count !== regeneratedEffectCount ||
    !canonicalJsonEqual(
      uniqueSorted(effectRegeneratedPaths),
      uniqueSorted(regeneratedNativePaths),
    ) ||
    !canonicalJsonEqual(
      uniqueSorted(effectPendingPaths),
      uniqueSorted(pendingNativePaths),
    ) ||
    !isPlainObject(finalReviewApplication) ||
    finalReviewApplication.application_status !== expectedApplicationStatus ||
    finalReviewApplication.decision_count !== expectedDecisionCount ||
    finalReviewApplication.item_count !== expectedItemCount ||
    finalReviewApplication.blocker_count !== blockerCount ||
    finalReviewApplication.revision_count !== effectRevisionPaths.length ||
    !canonicalJsonEqual(
      finalReviewApplication.revision_paths,
      effectRevisionPaths,
    ) ||
    finalReviewApplication.target_update_count !== effectTargetUpdatePaths.length ||
    !canonicalJsonEqual(
      finalReviewApplication.target_update_paths,
      effectTargetUpdatePaths,
    ) ||
    finalReviewApplication.structured_update_count !==
      effectStructuredUpdatePaths.length ||
    !canonicalJsonEqual(
      finalReviewApplication.structured_update_paths,
      effectStructuredUpdatePaths,
    ) ||
    finalReviewApplication.native_regenerated_count !== regeneratedEffectCount ||
    !canonicalJsonEqual(
      finalReviewApplication.native_regenerated_paths,
      regeneratedNativePaths,
    ) ||
    finalReviewApplication.native_regeneration_count !== pendingNativePaths.length ||
    !canonicalJsonEqual(
      finalReviewApplication.native_regeneration_paths,
      pendingNativePaths,
    ) ||
    !canonicalJsonEqual(
      finalReviewApplication.original_backup_paths,
      persistedBackupPaths,
    ) ||
    finalReviewApplication.applied_decisions_path !== "applied_decisions.json"
  ) {
    invalid();
  }
  const finalOutputs = Array.isArray(persistedFinalArtifacts.outputs)
    ? persistedFinalArtifacts.outputs
    : null;
  if (finalOutputs == null) invalid();
  validateFinalOutputPostcondition(
    outputDir,
    finalOutputs,
    [...expectedFinalOutputPaths, ...expectedNativeBackupPaths],
  );
  for (const nativePath of regeneratedNativePaths) {
    const output = finalOutputs.find(
      (candidate) => isPlainObject(candidate) && candidate.path === nativePath,
    );
    const absolutePath = path.join(outputDir, canonicalRunRelativePath(nativePath));
    const outputStat = pathEntryStat(absolutePath);
    if (
      !output ||
      output.native_regenerated !== true ||
      !outputStat ||
      !outputStat.isFile() ||
      outputStat.isSymbolicLink() ||
      outputStat.nlink !== 1
    ) {
      invalid();
    }
  }
  collectReviewApplicationPaths(persistedApplied, persistedFinalArtifacts);
  if (assurancePreflight?.assurance_replayed === true) {
    if (persistedApplied.assurance_replayed !== true) {
      invalid();
    }
    validatePersistedAssurancePostcondition(
      outputDir,
      persistedApplied,
      persistedFinalArtifacts,
      canonicalOutputDir,
    );
  }
  return { persistedApplied, persistedFinalArtifacts };
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
  const traceInputs = Array.from(
    new Set([
      appliedDecisions?.review_payload?.path || "review_payload.json",
      "ui_decisions.json",
      "final_artifacts.json",
    ]),
  ).map(canonicalRunRelativePath);
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "check_entries"}_review_apply_${stepIdSuffix || Date.now()}`,
    kind: "deterministic_review_apply",
    status: "passed",
    execution_location: "cowork_connected_folder",
    command: [SERVER_NAME, TOOL_NAMES.applyDecisions],
    inputs: traceInputs,
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
      atomicWriteFileSync(
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

function assuranceAllowsFinal(assurancePreflight) {
  // Final readiness is authority-bearing, so only locally replayed persisted
  // assurance may grant it. Caller-provided summaries are display data.
  return (
    assurancePreflight?.assurance_replayed === true &&
    assurancePreflight?.report_ready === true &&
    assurancePreflight?.professional_conclusion_status === "reviewed"
  );
}

function statusFromEffects(effects, itemCount, assurancePreflight) {
  if (!effects.length) return "pending_review";
  if (effects.some((effect) => effect.requires_followup)) return "blocked";
  if (effects.some((effect) => effect.requires_native_regeneration)) return "partial_review_applied";
  if (effects.length < itemCount) return "partial_review_applied";
  if (!assuranceAllowsFinal(assurancePreflight)) return "blocked";
  return "final_ready";
}

function validateAssuredReviewWrite(
  outputDir,
  reviewPayload,
  effects,
  assurancePreflight,
) {
  if (assurancePreflight?.assurance_replayed !== true) return;
  const localPayloadPath = path.join(outputDir, "review_payload.json");
  const localPayload = readJsonFileIfPresent(localPayloadPath);
  if (
    !localPayload ||
    localPayload.content_sha256 !== reviewPayload.content_sha256 ||
    reviewPayloadContentSha256(localPayload) !== localPayload.content_sha256
  ) {
    throw new Error("review_payload does not match the persisted assured review");
  }
  for (const effect of effects) {
    if (effect.action !== "edit") continue;
    if (
      effect.target_artifact !== "check_results.csv" ||
      effect.target_id_field !== "prepared_entry_id" ||
      !effect.target_record_id ||
      effect.target_field !== "review_notes"
    ) {
      throw new Error(
        `assured review item does not authorize a Check Entries note edit: ${effect.item_id}`,
      );
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
      ? "Comprobación de asientos"
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
    assurance_gates: current.assurance_gates || null,
    assurance_envelope: current.assurance_envelope || null,
    review_payload_content_sha256:
      reviewPayload.content_sha256 || current.review_payload_content_sha256 || null,
    professional_conclusion_status: current.professional_conclusion_status || null,
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
    nextActions.push(
      isSpanish(language)
        ? "Resuelva las decisiones de revisión bloqueadas antes de considerar listos los artefactos finales."
        : "Resolve blocked review decisions before treating final artifacts as ready.",
    );
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push(
      isSpanish(language)
        ? "Vuelva a generar las salidas nativas DOCX, XLSX o PDF antes de la entrega final."
        : "Regenerate native DOCX/XLSX/PDF outputs before final handoff.",
    );
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push(
      isSpanish(language)
        ? "Use final_artifacts.json como galería de artefactos revisados para la entrega."
        : "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
    );
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push(
      isSpanish(language)
        ? "Complete las decisiones de revisión restantes antes de la entrega final."
        : "Complete remaining review decisions before final handoff.",
    );
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  const expectedRunId = validateReviewPayload(inputArgs).review_payload.run_id;
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
    capturedAssurancePreflight,
    assured,
  ) => {
    const {
      trustedArgs,
      uiDecisions,
      reviewPayload,
      language,
      appliedAt,
      effects,
    } = prepared;
    const workingArgs = workingOutputDir
      ? {
          ...trustedArgs,
          run_intake: {
            ...trustedArgs.run_intake,
            output_dir: workingOutputDir,
          },
        }
      : trustedArgs;
    const assurancePreflight = capturedAssurancePreflight;
    if (workingOutputDir) {
      const childPreflight =
        preflightWorkflowSpecificReviewApplication(
          workingOutputDir,
          outputDir,
        );
      validatePreflightAcknowledgement(
        childPreflight,
        capturedAssurancePreflight,
      );
      validateOutputDirectoryTree(workingOutputDir);
      const postChildPreflight = validateCheckEntriesAssuranceAuthority(
        workingOutputDir,
        {
          required: assured,
          canonicalOutputDir: outputDir,
          failureMessage: CHECK_ENTRIES_AUTHORIZATION_FAILURE,
        },
      );
      if (!canonicalJsonEqual(postChildPreflight, capturedAssurancePreflight)) {
        throw new Error(CHECK_ENTRIES_AUTHORIZATION_FAILURE);
      }
    }
    validateAssuredReviewWrite(
      workingOutputDir,
      reviewPayload,
      effects,
      assurancePreflight,
    );
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
      assurancePreflight,
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
  if (!outputDir) {
    return applyPrepared(
      prepareApplication(inputArgs),
      null,
      noAssurancePreflight(),
      false,
    );
  }
  validateCheckEntriesTransactionInput(outputDir);
  preflightClientRun(outputDir, expectedRunId);
  let assuredWorkflow = false;
  return withGeneratedReviewOutputTransaction(
    outputDir,
    ({ workingOutputDir, trustedImage }) => {
      const authority = parentBoundCheckEntriesArgs(inputArgs, {
        outputDir,
        trustedImage,
        trustedImageCaptured: true,
      });
      assuredWorkflow = authority.assured;
      const capturedAssurancePreflight =
        validateCheckEntriesAssuranceAuthority(workingOutputDir, {
          required: authority.assured,
          canonicalOutputDir: outputDir,
          failureMessage: CHECK_ENTRIES_AUTHORIZATION_FAILURE,
        });
      const result = applyPrepared(
        prepareApplication(authority.args),
        workingOutputDir,
        capturedAssurancePreflight,
        authority.assured,
      );
      validateOutputDirectoryTree(workingOutputDir);
      const authorizedWritePaths =
        generatedReviewCollectApplicationWritePaths(result);
      if (result.applied_decisions?.assurance_replayed === true) {
        authorizedWritePaths.push(
          "assurance_envelope.json",
          "check_audit.json",
        );
      }
      return generatedReviewTransactionEnvelope(
        result,
        authorizedWritePaths,
      );
    },
    {
      ...checkEntriesTransactionOptions("apply"),
      validateWholeTree: ({ workingOutputDir }) => {
        validateOutputDirectoryTree(workingOutputDir);
        if (assuredWorkflow) {
          const persistedAuthority = validateCheckEntriesAssuranceAuthority(
            workingOutputDir,
            {
              required: true,
              canonicalOutputDir: outputDir,
              failureMessage:
                "Check Entries review application returned an invalid result.",
            },
          );
          const childPreflight =
            preflightWorkflowSpecificReviewApplication(
              workingOutputDir,
              outputDir,
            );
          validatePreflightAcknowledgement(childPreflight, persistedAuthority);
        }
      },
    },
  );
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
  assurancePreflight,
}) {
  const appliedOutputPath = resolveAppliedDecisionOutputPath(inputArgs);
  const finalArtifactsPath = resolveFinalArtifactsOutputPath(inputArgs);
  const currentFinalArtifacts = currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath);
  const revisionOutputs = writeRevisionArtifacts(outputDir, effects);
  const textUpdates = writeDirectTextArtifactUpdates(outputDir, effects);
  const structuredUpdates = writeStructuredArtifactUpdates(outputDir, effects);
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
  const applicationStatus = statusFromEffects(
    effects,
    reviewPayload.items.length,
    assurancePreflight,
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
    assurance_preflight: assurancePreflight,
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
  const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
    canonicalOutputDir,
  );
  let responseAppliedDecisions = appliedDecisions;
  let responseFinalArtifacts = finalArtifacts;
  if (workflowSpecificResult) {
    const persisted = validatePersistedWorkflowApplication({
      appliedOutputPath,
      finalArtifactsPath,
      outputDir,
      expectedRunId: reviewPayload.run_id,
      expectedDecisionCount: uiDecisions.decision_count,
      expectedItemCount: reviewPayload.items.length,
      expectedPlugin: reviewPayload.plugin,
      expectedWorkflow: reviewPayload.workflow,
      expectedDecisions: uiDecisions.decisions,
      expectedReviewPayloadPath: uiDecisions.review_payload_path || "review_payload.json",
      expectedReviewPayloadSha256: reviewPayload.content_sha256,
      expectedReviewType: reviewPayload.review_type || null,
      expectedNativePaths: nativeRegenerationPaths,
      expectedAppliedDecisions: appliedDecisions,
      expectedFinalArtifacts: finalArtifacts,
      assurancePreflight,
      canonicalOutputDir,
    });
    responseAppliedDecisions = persisted.persistedApplied;
    responseFinalArtifacts = persisted.persistedFinalArtifacts;
  } else {
    responseAppliedDecisions =
      readJsonFileIfPresent(appliedOutputPath) || appliedDecisions;
    responseFinalArtifacts =
      readJsonFileIfPresent(finalArtifactsPath) || finalArtifacts;
  }
  const runIntakePath = appendReviewApplicationExecutionTrace(
    inputArgs,
    outputDir,
    responseAppliedDecisions,
    responseFinalArtifacts,
  );
  return {
    ok: true,
    validation_type: "check_entries_application",
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
      ? isSpanish(language)
        ? `Se aplicaron ${responseAppliedDecisions.decision_count} decisiones de Comprobación de asientos.`
        : `Applied ${responseAppliedDecisions.decision_count} Check Entries decisions.`
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

function noAssurancePreflight() {
  return {
    ok: true,
    assurance_replayed: false,
    report_ready: false,
    professional_conclusion_status: null,
    envelope_content_sha256: null,
  };
}

const CHILD_OUTPUT_MAX_BYTES = 1024 * 1024;
const CHILD_FAILURE_MAX_CHARS = 240;
const CHILD_RESULT_MAX_CHARS = 512 * 1024;
const SAFE_CHILD_EXCEPTION_CLASSES = new Set([
  "FileNotFoundError",
  "OSError",
  "PermissionError",
  "RuntimeError",
  "TypeError",
  "ValueError",
]);
const SAFE_CHILD_FAILURE_DETAILS = [
  /^output directory must be a real directory$/,
  /^output directory changed during validation$/,
  /^output directory cannot contain (?:symbolic links|special filesystem entries|hardlink aliases)$/,
  /^canonical output parent must be a real directory$/,
  /^canonical output path changed during the transaction$/,
  /^(?:applied decisions|final artifacts) must stay inside the run output$/,
  /^(?:applied decisions|final artifacts) cannot (?:be a symbolic link|have hardlink aliases)$/,
  /^(?:applied decisions|final artifacts) must be a regular file$/,
  /^artifact receipt does not match current bytes$/,
];

function sanitizedChildFailure(completed, fallback) {
  const output = [completed.stdout, completed.stderr]
    .filter((value) => typeof value === "string" && value.trim())
    .join("\n");
  const terminalLine = output
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .pop();
  if (!terminalLine || terminalLine.length > CHILD_FAILURE_MAX_CHARS) {
    return fallback;
  }
  const exception = terminalLine.match(
    /^([A-Za-z_][A-Za-z0-9_]{0,63}(?:Error|Exception)):\s*(.{1,160})$/,
  );
  if (!exception || !SAFE_CHILD_EXCEPTION_CLASSES.has(exception[1])) {
    return fallback;
  }
  const detail = exception[2].trim();
  if (
    !detail ||
    /Traceback|\bFile\s+["']|[A-Za-z]:[\\/]|[\\/]|file:|~[\\/]|[\u0000-\u001f\u007f]/i.test(
      detail,
    ) ||
    !SAFE_CHILD_FAILURE_DETAILS.some((pattern) => pattern.test(detail))
  ) {
    return fallback;
  }
  const sanitized = `${fallback} ${exception[1]}: ${detail}`;
  return sanitized.length <= CHILD_FAILURE_MAX_CHARS ? sanitized : fallback;
}

function workflowChildMessages(phase) {
  return phase === "preflight"
    ? {
        start: "Check Entries assurance preflight could not start.",
        failure: "Check Entries assurance preflight failed.",
        invalid: "Check Entries assurance preflight returned an invalid result.",
      }
    : {
        start: "Check Entries review application could not start.",
        failure: "Check Entries review application failed.",
        invalid: "Check Entries review application returned an invalid result.",
      };
}

function canonicalRunRelativeStringArray(value) {
  if (!Array.isArray(value)) return false;
  try {
    return value.every(
      (entry) =>
        typeof entry === "string" &&
        canonicalRunRelativePath(entry) === entry.trim(),
    );
  } catch {
    return false;
  }
}

function validateWorkflowScriptResult(parsed, phase) {
  void phase;
  return isPlainObject(parsed) && parsed.ok === true;
}

function parseWorkflowScriptOutput(completed, phase) {
  const messages = workflowChildMessages(phase);
  if (completed.error) throw new Error(messages.start);
  if (completed.status !== 0) {
    throw new Error(sanitizedChildFailure(completed, messages.failure));
  }
  const stdout = typeof completed.stdout === "string" ? completed.stdout : "";
  const output = stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  if (!output) throw new Error(messages.invalid);
  if (output.length > CHILD_RESULT_MAX_CHARS) {
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
      },
    );
  } catch {
    throw new Error(workflowChildMessages(phase).start);
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
  if (
    result.schema_version !== "vera.client_workflow_context.v2" ||
    result.workflow_id !== "check-entries" ||
    typeof result.client_run_id !== "string" ||
    !result.client_run_id.trim() ||
    result.client_run_id !== expectedRunId
  ) {
    throw new Error("Check Entries customer-run preflight returned an invalid result.");
  }
  return result;
}

function preflightWorkflowSpecificReviewApplication(
  outputDir,
  canonicalOutputDir = null,
) {
  if (!outputDir) return { ok: true };
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const args = [scriptPath, "--output-dir", outputDir, "--preflight-only"];
  if (canonicalOutputDir) {
    args.push("--canonical-output-dir", canonicalOutputDir);
  }
  return runWorkflowPython(
    args,
    "preflight",
  );
}

function validatePreflightAcknowledgement(acknowledgement, authority) {
  if (
    authority.assurance_replayed === true &&
    acknowledgement.material_rederived !== true
  ) {
    throw new Error(
      "Check Entries assurance preflight returned an invalid result.",
    );
  }
  const authorityFields = [
    "assurance_replayed",
    "report_ready",
    "professional_conclusion_status",
    "envelope_content_sha256",
  ];
  for (const fieldName of authorityFields) {
    if (
      Object.hasOwn(acknowledgement, fieldName) &&
      !canonicalJsonEqual(acknowledgement[fieldName], authority[fieldName])
    ) {
      throw new Error(
        "Check Entries assurance preflight returned an invalid result.",
      );
    }
  }
}

function applyWorkflowSpecificReviewApplication(
  outputDir,
  appliedOutputPath,
  finalArtifactsPath,
  canonicalOutputDir,
) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied) return null;
  const hasAssuranceState =
    fs.existsSync(path.join(outputDir, "assurance_envelope.json")) ||
    fs.existsSync(path.join(outputDir, "check_audit.json"));
  if (!hasAssuranceState && !hasWorkflowNativeRegenerationTarget(currentApplied)) {
    return null;
  }
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
  return runWorkflowPython(
    args,
    "apply",
  );
}

function hasWorkflowNativeRegenerationTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (!effect.requires_native_regeneration) return false;
    return nativeRegenerationPathsForEffect(effect).includes("check_results.xlsx");
  });
}

function callTool(name, args = {}) {
  if (name === TOOL_NAMES.validateReview) {
    const trustedArgs = readOnlyAssuredReviewArgs(args);
    const issued = issueModelContext(validateReviewPayload(trustedArgs));
    const result = modelContextIndex(issued.token, issued.context);
    delete result.widget_type;
    result.validation_type = "check_entries_review";
    result.review_type = issued.context.privatePayload.review_payload.review_type || null;
    result.message = isSpanish(languageFromArgs(issued.context.privatePayload))
      ? "Los datos de revisión son válidos. El payload completo permanece fuera del contexto del modelo; use la referencia opaca para abrir el widget y solicite solo los casos que necesite interpretar."
      : "Check Entries review payload is valid. The complete payload stays out of model context; use the opaque reference to render the widget and request only cases that need interpretation.";
    return result;
  }
  if (name === TOOL_NAMES.renderReview) {
    const trustedArgs = args.persistence_token != null
      ? args
      : readOnlyAssuredReviewArgs(args);
    const resolved = privatePayloadForRender(trustedArgs);
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
      ? `herramienta desconocida del widget de Comprobación de asientos: ${name}`
      : `unknown Check Entries widget tool: ${name}`,
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
            ? "Use review_payload_path con validate_check_entries_review para que el payload privado se cargue dentro del servidor. Renderice con la referencia opaca y use get_check_entries_case_context solo para los casos seleccionados; solicite identificadores exactos únicamente cuando sean necesarios. El widget recibe el payload completo mediante metadatos privados. Use save_check_entries_decisions y apply_check_entries_decisions para las decisiones."
            : "Pass review_payload_path to validate_check_entries_review so the private payload is loaded inside the server. Render with the opaque reference and use get_check_entries_case_context only for selected cases; request exact identifiers only when needed. The widget receives the complete payload through component-only metadata. Use save_check_entries_decisions and apply_check_entries_decisions for decisions.",
      });
    }
    if (method === "notifications/initialized") return null;
    if (method === "tools/list") return rpcResponse(messageId, { tools: toolDefinitions() });
    if (method === "tools/call") {
      const { name, arguments: args } = params;
      const language = languageFromArgs(isPlainObject(args) ? args : params);
      if (typeof name !== "string") {
        return rpcError(
          messageId,
          -32602,
          isSpanish(language)
            ? "tools/call requiere el nombre de una herramienta"
            : "tools/call requires a tool name",
        );
      }
      if (!isPlainObject(args)) {
        return rpcError(
          messageId,
          -32602,
          isSpanish(language)
            ? "Los argumentos de tools/call deben ser un objeto"
            : "tools/call arguments must be an object",
        );
      }
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
        return rpcError(
          messageId,
          -32602,
          isSpanish(language)
            ? "resources/read requiere el URI de un recurso"
            : "resources/read requires a resource uri",
        );
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
    return rpcError(
      messageId,
      -32601,
      isSpanish(languageFromArgs(params))
        ? `método no encontrado: ${method}`
        : `method not found: ${method}`,
    );
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

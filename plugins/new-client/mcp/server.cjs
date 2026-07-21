#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const SERVER_NAME = "new-client-review";
const PLUGIN_NAME = "new-client";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_VERSION = PLUGIN_MANIFEST.version || "0.1.0";
const CONTRACT_VERSION = "1.1";
const WIDGET_URI = "ui://widget/new-client-review.html";
const WIDGET_MIME_TYPE = "text/html;profile=mcp-app";
const MAX_ITEMS = 2500;
const MAX_PAYLOAD_BYTES = 1_500_000;
const MAX_TEXT_LENGTH = 10_000;
const MAX_SHORT_TEXT_LENGTH = 500;
const MAX_SOURCE_ARTIFACTS = 24;
const MAX_REQUESTED_DOCUMENTS = 100;
const MAX_LOCAL_JSON_BYTES = 25_000_000;
const MAX_PERSISTENCE_CONTEXTS = 128;
const PERSISTENCE_CONTEXT_TTL_MS = 4 * 60 * 60 * 1000;
const PERSISTENCE_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const PERSISTENCE_CONTEXTS = new Map();
const TOOL_NAMES = {
  validate: "validate_new_client_review",
  render: "render_new_client_review",
  save: "save_new_client_decisions",
  apply: "apply_new_client_decisions",
};

// These are the complete public review vocabularies. Domain classification remains
// upstream/model-led; this server only validates the resulting review contract.
const ITEM_TYPES = new Set([
  "party_fact",
  "representative_fact",
  "beneficial_owner_fact",
  "engagement_service",
  "screening_result",
  "document_applicability",
  "aml_risk_factor",
  "aml_mandatory_trigger",
  "aml_assessment",
  "missing_evidence",
  "document_plan",
  "monitoring_plan",
  "official_source",
  "client_file_preparation_binding",
  "privacy_processing",
  "marketing_consent",
]);
const ALLOWED_ACTIONS = new Set([
  "accept",
  "reject",
  "edit",
  "mark_unclear",
  "request_more_documents",
  "skip",
]);
const SEMANTIC_ITEM_TYPES = new Set([
  "engagement_service",
  "screening_result",
  "document_applicability",
  "aml_risk_factor",
  "aml_mandatory_trigger",
  "aml_assessment",
  "document_plan",
  "monitoring_plan",
  "official_source",
  "client_file_preparation_binding",
  "privacy_processing",
  "marketing_consent",
]);
const BLOCKER_ACTIONS = new Set([
  "reject",
  "mark_unclear",
  "request_more_documents",
]);
const ACTION_STATUSES = {
  accept: "accepted",
  reject: "rejected",
  edit: "edited",
  mark_unclear: "needs_clarification",
  request_more_documents: "needs_documents",
  skip: "skipped",
};
const SOURCE_ARTIFACT_KEYS = new Set([
  "facts",
  "sources",
  "applicability",
  "aml",
  "documents",
  "monitoring",
]);
const REQUIRED_SOURCE_ARTIFACTS = {
  facts: "case_facts_validated.json",
  sources: "source_registry.json",
  applicability: "applicability_plan_validated.json",
  aml: "aml_calculation_audit.json",
  documents: "document_plan.json",
  monitoring: "monitoring_plan.json",
};
const REQUIRED_BASIS_HASH_KEYS = new Set([
  "new_client_input",
  "aml",
  "documents",
  "monitoring",
  "sources",
]);
const REQUIRED_EXPORT_OUTPUTS = new Set([
  "run_intake.json",
  "case_facts_validated.json",
  "source_registry.json",
  "applicability_plan_validated.json",
  "aml_assessment_draft.json",
  "aml_calculation_audit.json",
  "missing_evidence.json",
  "document_plan.json",
  "monitoring_plan.json",
  "studio_new_client_memo.md",
  "client_missing_information_draft.md",
  "review_payload.json",
  "ui_decisions.json",
  "review_handoff.md",
]);
const SOURCE_ARTIFACT_FIELDS = new Set([
  "path",
  "type",
  "sha256",
  "count",
]);
const REVIEW_STATUSES = new Set([
  "pending_review",
  "ready_for_review",
  "proposals_ready",
  "revision_required",
]);
const FINAL_ARTIFACT_STATUSES = new Set([
  "blocked",
  "pending_review",
  "ready_for_review",
  "partial_review_applied",
  "proposals_ready",
  "revision_required",
  "ready_for_professional_export",
]);
const UI_DECISION_STATUSES = new Set([
  "pending",
  "pending_review",
  "partial_review",
  "reviewed",
]);
const EXPORT_GATE_STATUSES = new Set([
  "blocked",
  "pending_review",
  "ready_for_professional_export",
]);
const EXPORT_GATE_FIELDS = new Set([
  "contract_version",
  "export_scope",
  "evaluated_at",
  "review_revision",
  "status",
  "relationship_ready",
  "domain_blockers",
  "review_blockers",
  "artifact_blockers",
  "marketing_only_blockers",
  "required_outputs",
  "basis_hashes",
]);
const REVIEW_FIELDS = new Set([
  "schema_version",
  "contract_version",
  "plugin",
  "workflow",
  "run_id",
  "review_revision",
  "generated_at",
  "status",
  "client_reference",
  "source_paths",
  "review_type",
  "item_count",
  "columns",
  "allowed_actions",
  "privacy",
  "privacy_notice",
  "summary",
  "source_artifacts",
  "basis_hashes",
  "professional_review_required",
  "signature_performed",
  "client_communication_sent",
  "relationship_activation_performed",
  "items",
]);
const REVIEW_ITEM_FIELDS = new Set([
  "id",
  "item_type",
  "title",
  "status",
  "allowed_actions",
  "recommended_action",
  "source_ids",
  "data",
]);
const ITEM_DATA_FIELDS = {
  party_fact: new Set([
    "fact_code",
    "confirmation_status",
    "evidence_count",
    "raw_value_excluded",
    "document_type_recorded",
    "document_number_excluded",
    "verification_date",
  ]),
  representative_fact: new Set([
    "representative_reference",
    "role",
    "authority_basis_recorded",
    "confirmation_status",
    "verification_date",
    "document_number_excluded",
    "evidence_count",
  ]),
  beneficial_owner_fact: new Set([
    "owner_reference",
    "control_basis_recorded",
    "confirmation_status",
    "identity_verification_status",
    "verification_date",
    "document_number_excluded",
    "evidence_count",
  ]),
  engagement_service: new Set([
    "service_id",
    "confirmation_status",
    "description_recorded",
    "raw_description_excluded",
  ]),
  screening_result: new Set([
    "screening_alias",
    "subject_alias",
    "screening_type",
    "source_recorded",
    "checked_at",
    "outcome",
    "confirmation_status",
    "resolution_status",
    "relationship_decision",
    "resolution_evidence_count",
    "raw_result_excluded",
  ]),
  document_applicability: new Set([
    "topic",
    "applicability_status",
    "review_status",
    "rationale_recorded",
    "raw_rationale_excluded",
  ]),
  aml_risk_factor: new Set([
    "factor_code",
    "score",
    "confirmation_status",
    "rationale_recorded",
    "raw_rationale_excluded",
    "evidence_count",
  ]),
  aml_mandatory_trigger: new Set([
    "trigger_id",
    "status",
    "review_status",
    "rationale_recorded",
    "raw_rationale_excluded",
  ]),
  aml_assessment: new Set([
    "calculation_status",
    "effective_risk",
    "calculated_band",
    "minimum_verification_mode_for_review",
    "uses_proposed_inputs",
    "professional_review_required",
  ]),
  missing_evidence: new Set([
    "missing_evidence_count",
    "evidence_status",
    "reference",
    "reason",
  ]),
  document_plan: new Set(["documents"]),
  monitoring_plan: new Set([
    "status",
    "review_interval_months",
    "next_review_date",
    "minimum_verification_mode_for_review",
  ]),
  official_source: new Set([
    "source_id",
    "title",
    "issuer",
    "version",
    "authority",
    "public_url_recorded_locally",
  ]),
  client_file_preparation_binding: new Set([
    "binding_mode",
    "verification_status",
    "final_ready",
    "reviewed_client_file_preparation",
    "manifest_sha256",
    "relationship_blocker",
  ]),
  privacy_processing: new Set([
    "decision_alias",
    "purpose_recorded",
    "role",
    "legal_basis_code",
    "processor_authority_recorded",
    "retention_status",
    "review_status",
    "source_count",
  ]),
  marketing_consent: new Set([
    "scope",
    "request_status",
    "choice",
    "purpose_count",
    "channel_count",
    "review_status",
    "relationship_export_blocking",
  ]),
};
const FORBIDDEN_PRIVATE_KEYS = new Set([
  "address",
  "birth_date",
  "client_name",
  "codice_fiscale",
  "date_of_birth",
  "document_content",
  "document_number",
  "document_quote",
  "email",
  "field_value",
  "full_name",
  "iban",
  "legal_name",
  "partita_iva",
  "phone",
  "raw_text",
  "raw_value",
  "source_excerpt",
  "source_text",
  "street_address",
  "tax_code",
  "vat_number",
]);
const EMAIL_RE = /(?:^|[^\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])/;
const TAX_CODE_RE = /(?:^|[^A-Za-z0-9])[A-Za-z]{6}[0-9]{2}[A-EHLMPRSTa-ehlmprst][0-9]{2}[A-Za-z][0-9]{3}[A-Za-z](?=$|[^A-Za-z0-9])/;
const IBAN_RE = /(?:^|[^A-Za-z0-9])IT\d{2}[A-Z]\d{10}[A-Z0-9]{12}(?=$|[^A-Za-z0-9])/i;
const VAT_RE = /(?:^|\D)\d{11}(?!\d)/;
const INTERNATIONAL_PHONE_RE = /(?:\+39|0039)[ .-]?(?:\d[ .-]?){8,11}/;
const SAFE_IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
const LOWERCASE_SHA256_RE = /^[0-9a-f]{64}$/;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function objectSchema(properties, required = [], additionalProperties = true) {
  return { type: "object", properties, required, additionalProperties };
}

function toolUiMeta() {
  return {
    ui: { resourceUri: WIDGET_URI, visibility: ["model"] },
    "ui/resourceUri": WIDGET_URI,
    "openai/outputTemplate": WIDGET_URI,
    "openai/widgetAccessible": true,
    "openai/toolInvocation/invoking": "Rendering new client review",
    "openai/toolInvocation/invoked": "Rendered new client review",
  };
}

function widgetMeta() {
  return {
    ui: { resourceUri: WIDGET_URI },
    "openai/widgetDescription":
      "Privacy-minimized professional review of client facts, engagement scope, AML assessment, documents, and monitoring plan.",
    "openai/widgetPrefersBorder": false,
    "openai/widgetCSP": { connect_domains: [], resource_domains: [] },
    "openai/widgetDomain": "https://chatgpt.com",
  };
}

function toolDefinitions() {
  const reviewPayload = objectSchema(
    {
      schema_version: { type: "string" },
      contract_version: { type: "string" },
      plugin: { type: "string" },
      workflow: { type: "string" },
      run_id: { type: "string" },
      review_revision: { type: "integer", minimum: 1 },
      review_type: { type: "string" },
      status: { type: "string" },
      item_count: { type: "integer", minimum: 0, maximum: MAX_ITEMS },
      items: { type: "array", maxItems: MAX_ITEMS, items: { type: "object" } },
      source_artifacts: { type: "object" },
      basis_hashes: { type: "object" },
      privacy_notice: { type: "string" },
    },
    [
      "schema_version",
      "contract_version",
      "plugin",
      "workflow",
      "run_id",
      "review_revision",
      "review_type",
      "status",
      "item_count",
      "items",
      "source_artifacts",
      "basis_hashes",
      "privacy_notice",
    ],
  );
  const reviewInput = objectSchema(
    {
      run_intake: { type: "object", description: "Optional run_intake.json object." },
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      final_artifacts: { type: "object", description: "Optional current final_artifacts.json object." },
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
      reuse_saved_details: {
        type: "boolean",
        description:
          "Reuse server-held decision details after a privacy-minimized reload.",
      },
    },
    ["item_id", "action"],
  );
  const decisionInput = objectSchema(
    {
      run_intake: { type: "object", description: "Optional run_intake.json with output_dir for persistence." },
      persistence_token: {
        type: "string",
        description: "Opaque token returned by the render tool for path-private persistence.",
      },
      review_payload: reviewPayload,
      ui_decisions: { type: "object" },
      final_artifacts: { type: "object" },
      decisions: { type: "array", maxItems: MAX_ITEMS, items: decision },
      decision_source: { type: "string" },
      reviewer: { type: "string" },
      expected_decision_revision: { type: "integer", minimum: 0 },
    },
    ["review_payload", "decisions"],
  );
  return [
    {
      name: TOOL_NAMES.validate,
      title: "Validate new client review",
      description: `Validate the privacy-minimized review payload before calling ${TOOL_NAMES.render}.`,
      inputSchema: reviewInput,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.render,
      title: "Open new client review",
      description:
        "Render the professional review surface without exposing the local output directory or raw client documents.",
      inputSchema: reviewInput,
      _meta: toolUiMeta(),
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.save,
      title: "Save new client decisions",
      description:
        "Validate reviewer actions and save ui_decisions.json in the run directory when one is provided.",
      inputSchema: decisionInput,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: false,
      },
    },
    {
      name: TOOL_NAMES.apply,
      title: "Apply new client decisions",
      description:
        "Record review effects in applied_decisions.json and update final_artifacts.json without modifying domain artifacts, signing, contacting the client, or activating the relationship.",
      inputSchema: decisionInput,
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
      name: "new_client_review_widget",
      title: "New Client professional setup review",
      description: "Interactive professional review of a privacy-minimized new-client case.",
      mimeType: WIDGET_MIME_TYPE,
      _meta: widgetMeta(),
    },
  ];
}

function resourceText(uri) {
  if (uri !== WIDGET_URI) throw new Error(`unknown widget resource: ${uri}`);
  return fs.readFileSync(
    path.join(PLUGIN_ROOT, "assets", "new-client-review-widget.html"),
    "utf8",
  );
}

function requireText(value, field, maxLength = MAX_TEXT_LENGTH) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${field} must be a non-empty string`);
  }
  if (value.length > maxLength) throw new Error(`${field} exceeds ${maxLength} characters`);
  return value.trim();
}

function optionalText(value, field, maxLength = MAX_TEXT_LENGTH) {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error(`${field} must be a string when provided`);
  if (value.length > maxLength) throw new Error(`${field} exceeds ${maxLength} characters`);
  return value.trim();
}

function safeIdentifier(value, field) {
  const text = requireText(value, field, 160);
  if (
    !SAFE_IDENTIFIER_RE.test(text)
    || EMAIL_RE.test(text)
    || TAX_CODE_RE.test(text)
    || IBAN_RE.test(text)
    || text.includes("//")
  ) {
    throw new Error(`${field} must be an opaque identifier without personal data`);
  }
  return text;
}

function validatePublicUrl(raw, field) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${field} contains an invalid URL`);
  }
  const privateHost =
    url.hostname === "localhost"
    || url.hostname.endsWith(".local")
    || /^(?:127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname);
  if (
    url.protocol !== "https:"
    || url.username
    || url.password
    || url.search
    || url.hash
    || (url.port && url.port !== "443")
    || privateHost
  ) {
    throw new Error(`${field} must use a public, untokenized HTTPS URL`);
  }
}

function assertPrivacySafeText(value, field, maxLength = MAX_TEXT_LENGTH) {
  const text = optionalText(value, field, maxLength);
  if (!text) return text;
  if (
    EMAIL_RE.test(text)
    || TAX_CODE_RE.test(text)
    || IBAN_RE.test(text)
    || VAT_RE.test(text)
    || INTERNATIONAL_PHONE_RE.test(text)
  ) {
    throw new Error(`${field} must omit direct client identifiers`);
  }
  for (const match of text.matchAll(/https?:\/\/[^\s<>"']+/gi)) {
    validatePublicUrl(match[0].replace(/[.,);\]]+$/, ""), field);
  }
  return text;
}

function auditPrivacy(value, field = "review_payload") {
  if (Array.isArray(value)) {
    value.forEach((entry, index) => auditPrivacy(entry, `${field}[${index}]`));
    return;
  }
  if (isObject(value)) {
    for (const [key, entry] of Object.entries(value)) {
      if (FORBIDDEN_PRIVATE_KEYS.has(key.toLowerCase())) {
        throw new Error(`${field}.${key} is forbidden in the privacy-minimized payload`);
      }
      auditPrivacy(entry, `${field}.${key}`);
    }
    return;
  }
  // Cryptographic bindings are opaque evidence, not client identifiers. Avoid
  // treating an incidental numeric run inside a digest as an Italian VAT number.
  if (typeof value === "string" && !LOWERCASE_SHA256_RE.test(value)) {
    assertPrivacySafeText(value, field);
  }
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!isObject(value)) return value;
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

function payloadBytes(value) {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

function assertAllowedKeys(value, allowed, field) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`${field}.${key} is not allowed`);
  }
}

function validateOptionalDate(value, field) {
  if (value == null) return null;
  const text = requireText(value, field, 32);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || Number.isNaN(Date.parse(`${text}T00:00:00Z`))) {
    throw new Error(`${field} must be a YYYY-MM-DD date or null`);
  }
  return text;
}

function validateOptionalNonNegativeInteger(value, field, maximum = 1_000_000) {
  if (value == null) return null;
  if (!Number.isInteger(value) || value < 0 || value > maximum) {
    throw new Error(`${field} must be a bounded non-negative integer or null`);
  }
  return value;
}

function validateSafeIdentifierArray(value, field, maximum = 100) {
  if (value == null) return [];
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error(`${field} must be an array with at most ${maximum} entries`);
  }
  const seen = new Set();
  return value.map((entry, index) => {
    const identifier = safeIdentifier(entry, `${field}[${index}]`);
    if (seen.has(identifier)) throw new Error(`${field} contains duplicate identifier: ${identifier}`);
    seen.add(identifier);
    return identifier;
  });
}

function validateRelativeBasename(value, field) {
  const text = requireText(value, field, 300);
  if (
    path.isAbsolute(text)
    || text === "."
    || text === ".."
    || text.includes("/")
    || text.includes("\\")
    || path.basename(text) !== text
  ) {
    throw new Error(`${field} must be a run-local basename`);
  }
  return text;
}

function validateSourceArtifact(value, field) {
  if (!isObject(value)) {
    throw new Error(`${field} must be a privacy-minimized object`);
  }
  const keys = Object.keys(value);
  if (keys.length === 0) throw new Error(`${field} must not be empty`);
  for (const key of keys) {
    if (!SOURCE_ARTIFACT_FIELDS.has(key)) {
      throw new Error(`${field}.${key} is not allowed in a privacy-minimized source reference`);
    }
  }
  if (value.path == null) throw new Error(`${field} must include path`);
  const artifact = {};
  artifact.path = validateRelativeBasename(value.path, `${field}.path`);
  if (value.type != null) {
    artifact.type = safeIdentifier(value.type, `${field}.type`);
  }
  if (typeof value.sha256 !== "string" || !LOWERCASE_SHA256_RE.test(value.sha256)) {
    throw new Error(`${field}.sha256 must be a lowercase SHA-256 digest`);
  }
  artifact.sha256 = value.sha256;
  if (value.count != null) {
    if (!Number.isInteger(value.count) || value.count < 0 || value.count > 1_000_000) {
      throw new Error(`${field}.count must be a bounded non-negative integer`);
    }
    artifact.count = value.count;
  }
  return artifact;
}

function validateSourceArtifacts(value) {
  if (!isObject(value)) throw new Error("review_payload.source_artifacts must be an object");
  const entries = Object.entries(value);
  if (entries.length > MAX_SOURCE_ARTIFACTS) {
    throw new Error(`review_payload.source_artifacts exceeds ${MAX_SOURCE_ARTIFACTS} entries`);
  }
  const supplied = new Set(entries.map(([key]) => key));
  const missing = [...SOURCE_ARTIFACT_KEYS].filter((key) => !supplied.has(key));
  const unsupported = [...supplied].filter((key) => !SOURCE_ARTIFACT_KEYS.has(key));
  if (missing.length || unsupported.length) {
    const details = [];
    if (missing.length) details.push(`missing required keys: ${missing.sort().join(", ")}`);
    if (unsupported.length) details.push(`unsupported keys: ${unsupported.sort().join(", ")}`);
    throw new Error(`review_payload.source_artifacts ${details.join("; ")}`);
  }
  const artifacts = {};
  for (const [key, artifact] of entries) {
    artifacts[key] = validateSourceArtifact(
      artifact,
      `review_payload.source_artifacts.${key}`,
    );
    if (artifacts[key].path !== REQUIRED_SOURCE_ARTIFACTS[key]) {
      throw new Error(
        `review_payload.source_artifacts.${key}.path must be ${REQUIRED_SOURCE_ARTIFACTS[key]}`,
      );
    }
  }
  return artifacts;
}

function validateBasisHashes(value) {
  if (!isObject(value)) throw new Error("review_payload.basis_hashes must be an object");
  if (Object.keys(value).length > MAX_SOURCE_ARTIFACTS) {
    throw new Error(`review_payload.basis_hashes exceeds ${MAX_SOURCE_ARTIFACTS} entries`);
  }
  const supplied = new Set(Object.keys(value));
  const missing = [...REQUIRED_BASIS_HASH_KEYS].filter((key) => !supplied.has(key));
  const unsupported = [...supplied].filter((key) => !REQUIRED_BASIS_HASH_KEYS.has(key));
  if (missing.length || unsupported.length) {
    const details = [];
    if (missing.length) details.push(`missing required keys: ${missing.sort().join(", ")}`);
    if (unsupported.length) details.push(`unsupported keys: ${unsupported.sort().join(", ")}`);
    throw new Error(`review_payload.basis_hashes ${details.join("; ")}`);
  }
  const hashes = {};
  for (const [key, digest] of Object.entries(value)) {
    safeIdentifier(key, `review_payload.basis_hashes.${key}`);
    if (typeof digest !== "string" || !LOWERCASE_SHA256_RE.test(digest)) {
      throw new Error(`review_payload.basis_hashes.${key} must be a lowercase SHA-256 digest`);
    }
    hashes[key] = digest;
  }
  return hashes;
}

function requireBoolean(value, field) {
  if (typeof value !== "boolean") throw new Error(`${field} must be a boolean`);
  return value;
}

function validateCalculatedBand(value, field) {
  if (!isObject(value)) throw new Error(`${field} must be an object`);
  const fields = new Set(["code", "label_it", "interval", "baseline_verification_mode"]);
  assertAllowedKeys(value, fields, field);
  safeIdentifier(value.code, `${field}.code`);
  const label = assertPrivacySafeText(value.label_it, `${field}.label_it`, 120);
  if (!label) throw new Error(`${field}.label_it must be non-empty`);
  const interval = assertPrivacySafeText(value.interval, `${field}.interval`, 40);
  if (!interval) throw new Error(`${field}.interval must be non-empty`);
  if (!["simplified", "ordinary", "enhanced"].includes(value.baseline_verification_mode)) {
    throw new Error(`${field}.baseline_verification_mode is not supported`);
  }
}

function validateDocumentRows(value, field) {
  if (!Array.isArray(value) || value.length > 20) {
    throw new Error(`${field} must be an array with at most 20 entries`);
  }
  const fields = new Set([
    "document_type",
    "status",
    "template_reference_id",
  ]);
  const seen = new Set();
  value.forEach((record, index) => {
    const root = `${field}[${index}]`;
    if (!isObject(record)) throw new Error(`${root} must be an object`);
    assertAllowedKeys(record, fields, root);
    const documentType = safeIdentifier(record.document_type, `${root}.document_type`);
    if (seen.has(documentType)) throw new Error(`${field} contains duplicate document_type: ${documentType}`);
    seen.add(documentType);
    safeIdentifier(record.status, `${root}.status`);
    if (record.template_reference_id != null) {
      safeIdentifier(record.template_reference_id, `${root}.template_reference_id`);
    }
  });
}

function validateReviewItemData(data, itemType, field) {
  if (!isObject(data)) throw new Error(`${field} must be an object`);
  const allowed = ITEM_DATA_FIELDS[itemType];
  if (!allowed) throw new Error(`${field} has no declared allowlist for ${itemType}`);
  assertAllowedKeys(data, allowed, field);

  for (const key of [
    "fact_code",
    "representative_reference",
    "role",
    "confirmation_status",
    "owner_reference",
    "identity_verification_status",
    "service_id",
    "screening_alias",
    "subject_alias",
    "screening_type",
    "outcome",
    "resolution_status",
    "relationship_decision",
    "topic",
    "applicability_status",
    "review_status",
    "factor_code",
    "trigger_id",
    "status",
    "calculation_status",
    "minimum_verification_mode_for_review",
    "evidence_status",
    "reference",
    "reason",
    "document_type",
    "template_id",
    "source_id",
    "authority",
    "binding_mode",
    "verification_status",
    "decision_alias",
    "legal_basis_code",
    "retention_status",
    "scope",
    "request_status",
    "choice",
  ]) {
    if (data[key] != null) safeIdentifier(data[key], `${field}.${key}`);
  }
  for (const key of [
    "raw_value_excluded",
    "document_type_recorded",
    "document_number_excluded",
    "authority_basis_recorded",
    "control_basis_recorded",
    "description_recorded",
    "raw_description_excluded",
    "source_recorded",
    "raw_result_excluded",
    "rationale_recorded",
    "raw_rationale_excluded",
    "uses_proposed_inputs",
    "professional_review_required",
    "public_url_recorded_locally",
    "final_ready",
    "reviewed_client_file_preparation",
    "relationship_blocker",
    "purpose_recorded",
    "processor_authority_recorded",
    "relationship_export_blocking",
  ]) {
    if (data[key] != null) requireBoolean(data[key], `${field}.${key}`);
  }
  for (const key of [
    "evidence_count",
    "missing_evidence_count",
    "review_interval_months",
    "source_count",
    "purpose_count",
    "channel_count",
    "resolution_evidence_count",
  ]) {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      validateOptionalNonNegativeInteger(data[key], `${field}.${key}`);
    }
  }
  for (const key of ["verification_date", "next_review_date"]) {
    if (Object.prototype.hasOwnProperty.call(data, key)) validateOptionalDate(data[key], `${field}.${key}`);
  }
  if (data.checked_at != null) {
    const checkedAt = requireText(data.checked_at, `${field}.checked_at`, 64);
    if (Number.isNaN(Date.parse(checkedAt)) || !/[zZ]|[+-]\d{2}:\d{2}$/.test(checkedAt)) {
      throw new Error(`${field}.checked_at must be an ISO-8601 timestamp with timezone`);
    }
  }
  for (const key of ["score", "effective_risk"]) {
    if (data[key] != null) {
      if (typeof data[key] !== "number" || !Number.isFinite(data[key]) || data[key] < 1 || data[key] > 4) {
        throw new Error(`${field}.${key} must be a finite number from 1 to 4`);
      }
    }
  }
  if (data.calculated_band != null) validateCalculatedBand(data.calculated_band, `${field}.calculated_band`);
  if (data.documents != null) validateDocumentRows(data.documents, `${field}.documents`);
  if (
    data.manifest_sha256 != null
    && (typeof data.manifest_sha256 !== "string"
      || !LOWERCASE_SHA256_RE.test(data.manifest_sha256))
  ) {
    throw new Error(`${field}.manifest_sha256 must be a lowercase SHA-256 digest`);
  }
  for (const key of ["title", "issuer", "version"]) {
    if (data[key] != null) {
      const text = assertPrivacySafeText(data[key], `${field}.${key}`, 400);
      if (!text) throw new Error(`${field}.${key} must be non-empty`);
    }
  }
}

function validateItem(item, index, seenIds) {
  const root = `review_payload.items[${index}]`;
  if (!isObject(item)) throw new Error(`${root} must be an object`);
  assertAllowedKeys(item, REVIEW_ITEM_FIELDS, root);
  const id = safeIdentifier(item.id, `${root}.id`);
  if (seenIds.has(id)) throw new Error(`review_payload.items contains duplicate id: ${id}`);
  seenIds.add(id);
  const itemType = safeIdentifier(item.item_type, `${root}.item_type`);
  if (!ITEM_TYPES.has(itemType)) throw new Error(`${root}.item_type is not supported: ${itemType}`);
  const title = assertPrivacySafeText(item.title, `${root}.title`, 400);
  if (!title) throw new Error(`${root}.title must be a non-empty string`);
  if (!Array.isArray(item.allowed_actions) || item.allowed_actions.length === 0) {
    throw new Error(`${root}.allowed_actions must be a non-empty array`);
  }
  const seenActions = new Set();
  for (const action of item.allowed_actions) {
    if (!ALLOWED_ACTIONS.has(action)) throw new Error(`${root}.allowed_actions contains unsupported action: ${action}`);
    if (seenActions.has(action)) throw new Error(`${root}.allowed_actions contains duplicate action: ${action}`);
    seenActions.add(action);
  }
  if (item.recommended_action != null) {
    if (!ALLOWED_ACTIONS.has(item.recommended_action)) {
      throw new Error(`${root}.recommended_action is not supported`);
    }
    if (!seenActions.has(item.recommended_action)) {
      throw new Error(`${root}.recommended_action must be present in allowed_actions`);
    }
  }
  if (item.status != null && !["needs_review", "pending_review"].includes(item.status)) {
    throw new Error(`${root}.status is not supported`);
  }
  validateSafeIdentifierArray(item.source_ids, `${root}.source_ids`);
  validateReviewItemData(item.data || {}, itemType, `${root}.data`);
}

function validateBoundaryFlags(value, field) {
  if (!isObject(value)) return;
  if (value.professional_review_required != null && value.professional_review_required !== true) {
    throw new Error(`${field}.professional_review_required must be true`);
  }
  for (const key of [
    "signature_performed",
    "client_communication_sent",
    "relationship_activation_performed",
  ]) {
    if (value[key] != null && value[key] !== false) {
      throw new Error(`${field}.${key} must be false`);
    }
  }
}

function validateExportScope(value, field) {
  const scope = requireText(value, field, 200);
  if (
    scope !== "relationship_export"
    && scope !== "marketing_use"
    && !/^document:[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(scope)
  ) {
    throw new Error(`${field} is not a supported export-gate scope`);
  }
  return scope;
}

function validateExportBlockers(value, field, includeDomain) {
  if (!Array.isArray(value) || value.length > MAX_ITEMS) {
    throw new Error(`${field} must be an array with at most ${MAX_ITEMS} entries`);
  }
  const allowed = includeDomain
    ? new Set(["code", "reference", "scope", "domain"])
    : new Set(["code", "reference", "scope"]);
  const seen = new Set();
  value.forEach((blocker, index) => {
    const root = `${field}[${index}]`;
    if (!isObject(blocker)) throw new Error(`${root} must be an object`);
    assertAllowedKeys(blocker, allowed, root);
    if (Object.keys(blocker).length !== allowed.size) {
      throw new Error(`${root} must contain exactly ${[...allowed].join(", ")}`);
    }
    const code = safeIdentifier(blocker.code, `${root}.code`);
    const reference = safeIdentifier(blocker.reference, `${root}.reference`);
    const scope = validateExportScope(blocker.scope, `${root}.scope`);
    const domain = includeDomain
      ? safeIdentifier(blocker.domain, `${root}.domain`)
      : "";
    const identity = `${code}\u0000${reference}\u0000${scope}\u0000${domain}`;
    if (seen.has(identity)) throw new Error(`${field} contains a duplicate blocker`);
    seen.add(identity);
  });
}

function validateExportGate(gate, review, manifestRecords = null) {
  if (!isObject(gate)) throw new Error("final_artifacts.export_gate must be an object");
  assertAllowedKeys(gate, EXPORT_GATE_FIELDS, "final_artifacts.export_gate");
  if (Object.keys(gate).length !== EXPORT_GATE_FIELDS.size) {
    throw new Error("final_artifacts.export_gate must contain the complete 1.1 contract");
  }
  if (gate.contract_version !== CONTRACT_VERSION) {
    throw new Error(`final_artifacts.export_gate.contract_version must be "${CONTRACT_VERSION}"`);
  }
  if (gate.export_scope !== "owner_only_professional_review_dossier") {
    throw new Error(
      "final_artifacts.export_gate.export_scope must be owner_only_professional_review_dossier",
    );
  }
  const evaluatedAt = requireText(
    gate.evaluated_at,
    "final_artifacts.export_gate.evaluated_at",
    64,
  );
  if (Number.isNaN(Date.parse(evaluatedAt)) || !/[zZ]|[+-]\d{2}:\d{2}$/.test(evaluatedAt)) {
    throw new Error(
      "final_artifacts.export_gate.evaluated_at must be an ISO-8601 timestamp with timezone",
    );
  }
  if (gate.review_revision !== review.review_revision) {
    throw new Error(
      "final_artifacts.export_gate.review_revision must match review_payload.review_revision",
    );
  }
  if (!EXPORT_GATE_STATUSES.has(gate.status)) {
    throw new Error("final_artifacts.export_gate.status is not supported");
  }
  requireBoolean(
    gate.relationship_ready,
    "final_artifacts.export_gate.relationship_ready",
  );
  validateExportBlockers(
    gate.domain_blockers,
    "final_artifacts.export_gate.domain_blockers",
    true,
  );
  validateExportBlockers(
    gate.review_blockers,
    "final_artifacts.export_gate.review_blockers",
    false,
  );
  validateExportBlockers(
    gate.artifact_blockers,
    "final_artifacts.export_gate.artifact_blockers",
    false,
  );
  validateExportBlockers(
    gate.marketing_only_blockers,
    "final_artifacts.export_gate.marketing_only_blockers",
    false,
  );
  if (
    !Array.isArray(gate.required_outputs)
    || gate.required_outputs.length === 0
    || gate.required_outputs.length > MAX_ITEMS
  ) {
    throw new Error("final_artifacts.export_gate.required_outputs must be non-empty");
  }
  const requiredOutputs = gate.required_outputs.map((entry, index) =>
    validateRelativeBasename(
      entry,
      `final_artifacts.export_gate.required_outputs[${index}]`,
    ));
  if (new Set(requiredOutputs).size !== requiredOutputs.length) {
    throw new Error("final_artifacts.export_gate.required_outputs must be unique");
  }
  const requiredOutputSet = new Set(requiredOutputs);
  if (
    requiredOutputSet.size !== REQUIRED_EXPORT_OUTPUTS.size
    || [...REQUIRED_EXPORT_OUTPUTS].some((name) => !requiredOutputSet.has(name))
  ) {
    throw new Error(
      "final_artifacts.export_gate.required_outputs must match the complete 1.1 base package",
    );
  }
  const basisHashes = validateBasisHashes(gate.basis_hashes);
  for (const key of REQUIRED_BASIS_HASH_KEYS) {
    if (basisHashes[key] !== review.basis_hashes[key]) {
      throw new Error(
        `final_artifacts.export_gate.basis_hashes.${key} must match review_payload`,
      );
    }
  }
  if (manifestRecords) {
    const missingRequiredOutputs = requiredOutputs.filter(
      (name) => !manifestRecords.has(name),
    );
    if (missingRequiredOutputs.length > 0) {
      throw new Error(
        `final_artifacts.export_gate.required_outputs are missing from manifest outputs: ${missingRequiredOutputs.join(", ")}`,
      );
    }
  }
  return gate;
}

function validateRunIdentity(runIntake, review) {
  if (!isObject(runIntake)) return;
  if (runIntake.schema_version != null && runIntake.schema_version !== CONTRACT_VERSION) {
    throw new Error(`run_intake.schema_version must be "${CONTRACT_VERSION}"`);
  }
  if (runIntake.run_id != null && runIntake.run_id !== review.run_id) {
    throw new Error("run_intake.run_id must match review_payload.run_id");
  }
  if (runIntake.plugin != null && runIntake.plugin !== PLUGIN_NAME) {
    throw new Error(`run_intake.plugin must be ${PLUGIN_NAME}`);
  }
  if (runIntake.workflow != null && runIntake.workflow !== review.workflow) {
    throw new Error("run_intake.workflow must match review_payload.workflow");
  }
}

function validateFinalIdentity(finalArtifacts, review) {
  if (!isObject(finalArtifacts)) return;
  if (finalArtifacts.schema_version != null && finalArtifacts.schema_version !== CONTRACT_VERSION) {
    throw new Error(`final_artifacts.schema_version must be "${CONTRACT_VERSION}"`);
  }
  if (
    finalArtifacts.contract_version != null
    && finalArtifacts.contract_version !== CONTRACT_VERSION
  ) {
    throw new Error(`final_artifacts.contract_version must be "${CONTRACT_VERSION}"`);
  }
  if (finalArtifacts.plugin != null && finalArtifacts.plugin !== PLUGIN_NAME) {
    throw new Error(`final_artifacts.plugin must be ${PLUGIN_NAME}`);
  }
  if (finalArtifacts.workflow != null && finalArtifacts.workflow !== review.workflow) {
    throw new Error("final_artifacts.workflow must match review_payload.workflow");
  }
  if (finalArtifacts.run_id != null && finalArtifacts.run_id !== review.run_id) {
    throw new Error("final_artifacts.run_id must match review_payload.run_id");
  }
  if (
    finalArtifacts.status != null
    && !FINAL_ARTIFACT_STATUSES.has(finalArtifacts.status)
  ) {
    throw new Error(
      `final_artifacts.status is not supported; expected one of ${[...FINAL_ARTIFACT_STATUSES].join(", ")}`,
    );
  }
  if (
    finalArtifacts.review_status != null
    && !FINAL_ARTIFACT_STATUSES.has(finalArtifacts.review_status)
    && !UI_DECISION_STATUSES.has(finalArtifacts.review_status)
  ) {
    throw new Error("final_artifacts.review_status is not supported");
  }
  validateExportGate(finalArtifacts.export_gate, review);
  validateBoundaryFlags(finalArtifacts, "final_artifacts");
}

function validateUiDecisionIdentity(uiDecisions, review) {
  if (!isObject(uiDecisions)) return;
  if (uiDecisions.schema_version != null && uiDecisions.schema_version !== CONTRACT_VERSION) {
    throw new Error(`ui_decisions.schema_version must be "${CONTRACT_VERSION}"`);
  }
  if (
    uiDecisions.contract_version != null
    && uiDecisions.contract_version !== CONTRACT_VERSION
  ) {
    throw new Error(`ui_decisions.contract_version must be "${CONTRACT_VERSION}"`);
  }
  if (uiDecisions.plugin != null && uiDecisions.plugin !== PLUGIN_NAME) {
    throw new Error(`ui_decisions.plugin must be ${PLUGIN_NAME}`);
  }
  if (uiDecisions.workflow != null && uiDecisions.workflow !== review.workflow) {
    throw new Error("ui_decisions.workflow must match review_payload.workflow");
  }
  if (uiDecisions.run_id != null && uiDecisions.run_id !== review.run_id) {
    throw new Error("ui_decisions.run_id must match review_payload.run_id");
  }
  if (
    uiDecisions.review_revision != null
    && uiDecisions.review_revision !== review.review_revision
  ) {
    throw new Error("ui_decisions.review_revision must match review_payload.review_revision");
  }
  if (uiDecisions.status != null && !UI_DECISION_STATUSES.has(uiDecisions.status)) {
    throw new Error("ui_decisions.status is not supported");
  }
  if (uiDecisions.reviewer != null) {
    safeIdentifier(uiDecisions.reviewer, "ui_decisions.reviewer");
  }
}

function validateReviewMetadata(review) {
  assertAllowedKeys(review, REVIEW_FIELDS, "review_payload");
  if (review.contract_version !== CONTRACT_VERSION) {
    throw new Error(`review_payload.contract_version must be "${CONTRACT_VERSION}"`);
  }
  if (review.client_reference != null) {
    safeIdentifier(review.client_reference, "review_payload.client_reference");
  }
  if (review.generated_at != null) {
    const generatedAt = requireText(review.generated_at, "review_payload.generated_at", 64);
    if (Number.isNaN(Date.parse(generatedAt)) || !/[zZ]|[+-]\d{2}:\d{2}$/.test(generatedAt)) {
      throw new Error("review_payload.generated_at must be an ISO-8601 timestamp with timezone");
    }
  }
  if (review.source_paths != null) {
    if (!Array.isArray(review.source_paths) || review.source_paths.length !== 0) {
      throw new Error("review_payload.source_paths must be an empty array");
    }
  }
  if (review.columns != null) {
    const expected = ["title", "status", "source_ids", "data"];
    if (!Array.isArray(review.columns) || canonicalJson(review.columns) !== canonicalJson(expected)) {
      throw new Error(`review_payload.columns must be ${expected.join(", ")}`);
    }
  }
  if (review.allowed_actions != null) {
    if (!Array.isArray(review.allowed_actions)) {
      throw new Error("review_payload.allowed_actions must be an array");
    }
    const supplied = new Set(review.allowed_actions);
    if (
      supplied.size !== ALLOWED_ACTIONS.size
      || [...ALLOWED_ACTIONS].some((action) => !supplied.has(action))
    ) {
      throw new Error("review_payload.allowed_actions must contain the complete action vocabulary");
    }
  }
  if (review.privacy != null) {
    if (!isObject(review.privacy)) throw new Error("review_payload.privacy must be an object");
    assertAllowedKeys(review.privacy, new Set(["classification", "excluded"]), "review_payload.privacy");
    if (review.privacy.classification !== "pseudonymous_review_payload") {
      throw new Error("review_payload.privacy.classification must be pseudonymous_review_payload");
    }
    if (!Array.isArray(review.privacy.excluded) || review.privacy.excluded.length > 20) {
      throw new Error("review_payload.privacy.excluded must be a bounded array");
    }
    review.privacy.excluded.forEach((entry, index) => {
      const text = assertPrivacySafeText(entry, `review_payload.privacy.excluded[${index}]`, 120);
      if (!text) throw new Error(`review_payload.privacy.excluded[${index}] must be non-empty`);
    });
  }
  if (review.summary != null) {
    if (!isObject(review.summary)) throw new Error("review_payload.summary must be an object");
    const summaryFields = new Set([
      "review_item_count",
      "missing_information_count",
      "aml_status",
      "document_count",
      "language",
    ]);
    assertAllowedKeys(review.summary, summaryFields, "review_payload.summary");
    for (const key of ["review_item_count", "missing_information_count", "document_count"]) {
      if (review.summary[key] != null) {
        validateOptionalNonNegativeInteger(review.summary[key], `review_payload.summary.${key}`);
      }
    }
    for (const key of ["aml_status", "language"]) {
      if (review.summary[key] != null) safeIdentifier(review.summary[key], `review_payload.summary.${key}`);
    }
  }
}

function publicRunIntake(value, review) {
  if (!isObject(value)) return null;
  return {
    schema_version: value.schema_version || null,
    plugin: value.plugin || PLUGIN_NAME,
    workflow: value.workflow || PLUGIN_NAME,
    run_id: review.run_id,
    reference_date: value.reference_date || null,
    language: ["it", "en", "fr", "de"].includes(value.language)
      ? value.language
      : null,
    status: value.status || null,
  };
}

function publicUiDecisions(value, review) {
  if (!isObject(value)) return null;
  const itemIds = new Set(review.items.map((item) => item.id));
  const decisions = Array.isArray(value.decisions)
    ? value.decisions
        .filter(
          (decision) =>
            isObject(decision)
            && itemIds.has(decision.item_id)
            && ALLOWED_ACTIONS.has(decision.action),
        )
        .slice(0, review.items.length)
        .map((decision) => ({
          item_id: decision.item_id,
          action: decision.action,
          status: ACTION_STATUSES[decision.action],
        }))
    : [];
  return {
    schema_version: review.schema_version,
    contract_version: review.contract_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    review_revision: review.review_revision,
    decision_revision:
      Number.isInteger(value.decision_revision) && value.decision_revision >= 0
        ? value.decision_revision
        : 0,
    review_payload_sha256:
      typeof value.review_payload_sha256 === "string"
        ? value.review_payload_sha256
        : null,
    decisions,
    decision_count: decisions.length,
    item_count: review.items.length,
    status: typeof value.status === "string" ? value.status : "pending_review",
    reviewer:
      typeof value.reviewer === "string"
        ? safeIdentifier(value.reviewer, "ui_decisions.reviewer")
        : null,
  };
}

function publicFinalArtifacts(value, review) {
  if (!isObject(value)) return null;
  const outputs = Array.isArray(value.outputs)
    ? value.outputs
        .filter((record) => {
          if (!isObject(record) || typeof record.path !== "string") return false;
          const fileName = record.path.trim();
          return fileName
            && fileName.length <= 240
            && fileName !== "."
            && fileName !== ".."
            && path.basename(fileName) === fileName;
        })
        .slice(0, MAX_ITEMS)
        .map((record) => ({
          path: record.path.trim(),
          kind: typeof record.kind === "string" ? record.kind.slice(0, 80) : "file",
          status:
            typeof record.status === "string" ? record.status.slice(0, 120) : null,
          size_bytes:
            Number.isInteger(record.size_bytes) && record.size_bytes >= 0
              ? record.size_bytes
              : null,
          sha256:
            typeof record.sha256 === "string" && LOWERCASE_SHA256_RE.test(record.sha256)
              ? record.sha256
              : null,
        }))
    : [];
  return {
    schema_version: value.schema_version || review.schema_version,
    contract_version: value.contract_version || review.contract_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    status: typeof value.status === "string" ? value.status : null,
    review_payload_sha256:
      typeof value.review_payload_sha256 === "string" ? value.review_payload_sha256 : null,
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
    blocker_count: Array.isArray(value.blockers) ? Math.min(value.blockers.length, MAX_ITEMS) : 0,
    output_count: outputs.length,
    outputs,
    export_gate: isObject(value.export_gate)
      ? {
          status: value.export_gate.status || null,
          relationship_ready: value.export_gate.relationship_ready === true,
          domain_blocker_count: Array.isArray(value.export_gate.domain_blockers)
            ? value.export_gate.domain_blockers.length
            : 0,
          review_blocker_count: Array.isArray(value.export_gate.review_blockers)
            ? value.export_gate.review_blockers.length
            : 0,
          artifact_blocker_count: Array.isArray(value.export_gate.artifact_blockers)
            ? value.export_gate.artifact_blockers.length
            : 0,
          marketing_only_blocker_count: Array.isArray(value.export_gate.marketing_only_blockers)
            ? value.export_gate.marketing_only_blockers.length
            : 0,
          required_output_count: Array.isArray(value.export_gate.required_outputs)
            ? value.export_gate.required_outputs.length
            : 0,
        }
      : null,
    review_application: isObject(value.review_application)
      ? {
          status: value.review_application.status || null,
          decision_count: value.review_application.decision_count || 0,
          item_count: value.review_application.item_count || review.items.length,
          blocker_count: value.review_application.blocker_count || 0,
          pending_count: value.review_application.pending_count || 0,
          domain_artifacts_modified: false,
        }
      : null,
  };
}

function validateReview(input) {
  if (!isObject(input)) throw new Error("tool arguments must be an object");
  const review = input.review_payload;
  if (!isObject(review)) throw new Error("review_payload must be an object");
  if (review.schema_version !== CONTRACT_VERSION) {
    throw new Error(`review_payload.schema_version must be "${CONTRACT_VERSION}"`);
  }
  if (review.plugin !== PLUGIN_NAME || review.workflow !== PLUGIN_NAME) {
    throw new Error(`review_payload.plugin and workflow must be ${PLUGIN_NAME}`);
  }
  validateReviewMetadata(review);
  safeIdentifier(review.run_id, "review_payload.run_id");
  if (!Number.isInteger(review.review_revision) || review.review_revision < 1) {
    throw new Error("review_payload.review_revision must be a positive integer");
  }
  requireText(review.review_type, "review_payload.review_type", 120);
  requireText(review.status, "review_payload.status", 120);
  if (!REVIEW_STATUSES.has(review.status)) {
    throw new Error(
      `review_payload.status is not supported; expected one of ${[...REVIEW_STATUSES].join(", ")}`,
    );
  }
  requireText(review.privacy_notice, "review_payload.privacy_notice", 1_000);
  if (!Array.isArray(review.items)) throw new Error("review_payload.items must be an array");
  if (review.items.length > MAX_ITEMS) {
    throw new Error(`review_payload.items exceeds ${MAX_ITEMS} items`);
  }
  if (!Number.isInteger(review.item_count) || review.item_count !== review.items.length) {
    throw new Error("review_payload.item_count must equal review_payload.items.length");
  }
  validateSourceArtifacts(review.source_artifacts);
  validateBasisHashes(review.basis_hashes);
  const seenIds = new Set();
  review.items.forEach((item, index) => validateItem(item, index, seenIds));
  auditPrivacy(review);
  const runIntake = isObject(input.run_intake) ? input.run_intake : null;
  const uiDecisions = isObject(input.ui_decisions) ? input.ui_decisions : null;
  const finalArtifacts = isObject(input.final_artifacts) ? input.final_artifacts : null;
  validateRunIdentity(runIntake, review);
  validateUiDecisionIdentity(uiDecisions, review);
  validateFinalIdentity(finalArtifacts, review);
  validateBoundaryFlags(review, "review_payload");
  const reviewPayloadSha256 = canonicalSha256(review);
  const payload = {
    widget_type: "new_client_review",
    run_intake: publicRunIntake(runIntake, review),
    review_payload: review,
    review_payload_sha256: reviewPayloadSha256,
    ui_decisions: publicUiDecisions(uiDecisions, review),
    final_artifacts: publicFinalArtifacts(finalArtifacts, review),
    decision_policy: {
      save_tool: TOOL_NAMES.save,
      apply_tool: TOOL_NAMES.apply,
      can_persist: Boolean(
        isObject(runIntake)
        && typeof runIntake.output_dir === "string"
        && runIntake.output_dir.trim(),
      ),
      edits_are_review_instructions: true,
      domain_artifacts_modified: false,
      professional_review_required: true,
      fallback: "copy_or_download_json",
    },
  };
  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
    throw new Error(`new client widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return payload;
}

function normalizeRequestedDocuments(value, field) {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error(`${field} must be an array when provided`);
  if (value.length > MAX_REQUESTED_DOCUMENTS) {
    throw new Error(`${field} exceeds ${MAX_REQUESTED_DOCUMENTS} entries`);
  }
  const seen = new Set();
  return value.map((entry, index) => {
    const text = assertPrivacySafeText(entry, `${field}[${index}]`, 300);
    if (!text) throw new Error(`${field}[${index}] must be a non-empty string`);
    if (seen.has(text)) throw new Error(`${field} contains duplicate document request: ${text}`);
    seen.add(text);
    return text;
  });
}

function normalizeDecision(decision, index, itemById, seenIds, decidedAt) {
  const root = `decisions[${index}]`;
  if (!isObject(decision)) throw new Error(`${root} must be an object`);
  const itemId = safeIdentifier(decision.item_id, `${root}.item_id`);
  if (seenIds.has(itemId)) throw new Error(`decisions contains duplicate item_id: ${itemId}`);
  seenIds.add(itemId);
  const item = itemById.get(itemId);
  if (!item) throw new Error(`${root}.item_id is not in review_payload.items: ${itemId}`);
  const action = requireText(decision.action, `${root}.action`, 80);
  if (!ALLOWED_ACTIONS.has(action)) throw new Error(`${root}.action is not supported: ${action}`);
  if (!item.allowed_actions.includes(action)) {
    throw new Error(`${root}.action is not allowed for item ${itemId}: ${action}`);
  }
  const reviewerNote = assertPrivacySafeText(
    decision.reviewer_note ?? decision.note,
    `${root}.reviewer_note`,
  );
  const editValue = assertPrivacySafeText(
    decision.edit_value ?? decision.user_text,
    `${root}.edit_value`,
  );
  if (action === "edit" && !editValue) {
    throw new Error(`${root}.edit_value is required when action is edit`);
  }
  if (action === "edit" && SEMANTIC_ITEM_TYPES.has(item.item_type) && !reviewerNote) {
    throw new Error(`${root}.reviewer_note is required for semantic edits`);
  }
  const requestedDocuments = normalizeRequestedDocuments(
    decision.requested_documents,
    `${root}.requested_documents`,
  );
  if (action === "request_more_documents" && requestedDocuments.length === 0) {
    throw new Error(`${root}.requested_documents is required for document requests`);
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
  return normalized;
}

function mergeSavedDecisionDetails(decision, index, savedDecisionById) {
  const root = `decisions[${index}]`;
  if (decision.reuse_saved_details == null || decision.reuse_saved_details === false) {
    return decision;
  }
  if (decision.reuse_saved_details !== true) {
    throw new Error(`${root}.reuse_saved_details must be boolean when provided`);
  }
  for (const field of ["reviewer_note", "edit_value", "requested_documents"]) {
    if (Object.prototype.hasOwnProperty.call(decision, field)) {
      throw new Error(
        `${root}.${field} cannot be supplied when reuse_saved_details is true`,
      );
    }
  }
  const savedDecision = savedDecisionById.get(decision.item_id);
  if (!savedDecision || savedDecision.action !== decision.action) {
    throw new Error(
      `${root}.reuse_saved_details requires a saved decision with the same item_id and action`,
    );
  }
  return {
    ...decision,
    ...(savedDecision.reviewer_note
      ? { reviewer_note: savedDecision.reviewer_note }
      : {}),
    ...(savedDecision.edit_value ? { edit_value: savedDecision.edit_value } : {}),
    ...(Array.isArray(savedDecision.requested_documents)
      && savedDecision.requested_documents.length
      ? { requested_documents: [...savedDecision.requested_documents] }
      : {}),
  };
}

function buildUiDecisions(input, payload = validateReview(input), savedUiDecisions = null) {
  const review = payload.review_payload;
  if (!Array.isArray(input.decisions)) throw new Error("decisions must be an array");
  if (input.decisions.length > review.items.length) {
    throw new Error("decisions cannot exceed review_payload.items.length");
  }
  if (payloadBytes(input.decisions) > MAX_PAYLOAD_BYTES) {
    throw new Error(`decisions payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  const itemById = new Map(review.items.map((item) => [item.id, item]));
  const savedDecisionById = new Map(
    Array.isArray(savedUiDecisions?.decisions)
      ? savedUiDecisions.decisions.map((decision) => [decision.item_id, decision])
      : [],
  );
  const seenIds = new Set();
  const decidedAt = new Date().toISOString();
  const decisions = input.decisions.map((decision, index) => {
    if (!isObject(decision)) throw new Error(`decisions[${index}] must be an object`);
    const merged = mergeSavedDecisionDetails(decision, index, savedDecisionById);
    return normalizeDecision(merged, index, itemById, seenIds, decidedAt);
  });
  const decisionSource = input.decision_source
    ? safeIdentifier(input.decision_source, "decision_source")
    : "mcp_widget";
  const reviewer = input.reviewer ? safeIdentifier(input.reviewer, "reviewer") : "";
  const status =
    decisions.length === 0
      ? "pending_review"
      : decisions.length === review.items.length
        ? "reviewed"
        : "partial_review";
  const uiDecisions = {
    schema_version: review.schema_version,
    contract_version: review.contract_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    review_revision: review.review_revision,
    decision_revision: 0,
    decided_at: decisions.length ? decidedAt : null,
    decision_source: decisionSource,
    review_payload_path: "review_payload.json",
    review_payload_sha256: payload.review_payload_sha256,
    decisions,
    decision_count: decisions.length,
    item_count: review.items.length,
    status,
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
  };
  if (reviewer) uiDecisions.reviewer = reviewer;
  if (payloadBytes(uiDecisions) > MAX_PAYLOAD_BYTES) {
    throw new Error(`ui_decisions payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }
  return { payload, uiDecisions };
}

function currentDecisionRevision(value) {
  if (value == null) return 0;
  if (!isObject(value)) throw new Error("ui_decisions.json must contain an object");
  const revision = value.decision_revision ?? 0;
  if (!Number.isInteger(revision) || revision < 0) {
    throw new Error("ui_decisions.decision_revision must be a non-negative integer");
  }
  return revision;
}

function expectedDecisionRevision(input) {
  const explicit = input.expected_decision_revision;
  const embedded = isObject(input.ui_decisions) ? input.ui_decisions.decision_revision : null;
  const revision = explicit ?? embedded ?? 0;
  if (!Number.isInteger(revision) || revision < 0) {
    throw new Error("expected_decision_revision must be a non-negative integer");
  }
  return revision;
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

function validatePersistentState(outputDir, payload) {
  verifyStoredReview(
    outputDir,
    payload.review_payload,
    payload.review_payload_sha256,
  );
  const currentFinal = readJsonIfPresent(
    path.join(outputDir, "final_artifacts.json"),
  );
  if (!currentFinal) {
    throw new Error("run_intake.output_dir must contain final_artifacts.json");
  }
  validateCurrentFinalArtifacts(
    currentFinal,
    payload.review_payload,
    payload.review_payload_sha256,
  );
  const manifestRecords = verifyLocalArtifactBindings(
    outputDir,
    payload.review_payload,
    payload.review_payload_sha256,
    currentFinal,
  );
  const currentUiDecisions = readJsonIfPresent(
    path.join(outputDir, "ui_decisions.json"),
  );
  if (currentUiDecisions) {
    validateUiDecisionIdentity(currentUiDecisions, payload.review_payload);
  }
  return { currentFinal, currentUiDecisions, manifestRecords };
}

function issuePersistenceToken(input, payload) {
  const outputDir = resolveOutputDir(input);
  if (!outputDir) return null;
  validatePersistentState(outputDir, payload);
  reservePersistenceContextSlot();
  const token = crypto.randomBytes(32).toString("base64url");
  PERSISTENCE_CONTEXTS.set(token, {
    outputDir,
    runId: payload.review_payload.run_id,
    reviewHash: payload.review_payload_sha256,
    expiresAt: Date.now() + PERSISTENCE_CONTEXT_TTL_MS,
  });
  return token;
}

function resolvePersistentOutputDir(input, payload) {
  const rawToken = input.persistence_token;
  if (rawToken == null || rawToken === "") return resolveOutputDir(input);
  if (typeof rawToken !== "string" || !PERSISTENCE_TOKEN_RE.test(rawToken)) {
    throw new Error("persistence_token has an invalid format");
  }
  pruneExpiredPersistenceContexts();
  const context = PERSISTENCE_CONTEXTS.get(rawToken);
  if (!context || context.expiresAt <= Date.now()) {
    throw new Error("persistence_token is unknown or expired; render the review again");
  }
  if (
    context.runId !== payload.review_payload.run_id
    || context.reviewHash !== payload.review_payload_sha256
  ) {
    throw new Error("persistence_token does not match this review run");
  }
  const outputDir = resolveOutputDir({
    run_intake: { output_dir: context.outputDir },
  });
  const directOutputDir = resolveOutputDir(input);
  if (directOutputDir && directOutputDir !== outputDir) {
    throw new Error("persistence_token and run_intake.output_dir do not match");
  }
  return outputDir;
}

function preparePersistentRun(input, payload) {
  const outputDir = resolvePersistentOutputDir(input, payload);
  if (!outputDir) {
    return {
      outputDir: null,
      currentFinal: {},
      currentUiDecisions: null,
      manifestRecords: null,
      nextDecisionRevision: 1,
    };
  }
  const { currentFinal, currentUiDecisions, manifestRecords } =
    validatePersistentState(outputDir, payload);
  const currentRevision = currentDecisionRevision(currentUiDecisions);
  const expectedRevision = expectedDecisionRevision(input);
  if (expectedRevision !== currentRevision) {
    throw new Error(
      `stale decision revision: expected ${expectedRevision}, current ${currentRevision}`,
    );
  }
  return {
    outputDir,
    currentFinal,
    currentUiDecisions,
    manifestRecords,
    nextDecisionRevision: currentRevision + 1,
  };
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
  const parent = path.dirname(PLUGIN_ROOT);
  if (path.basename(parent) === "modules") roots.add(path.dirname(parent));
  return [...roots].map((entry) => fs.realpathSync(entry));
}

function isInsideOrEqual(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

function resolveOutputDir(input) {
  const raw = isObject(input.run_intake) ? input.run_intake.output_dir : null;
  if (typeof raw !== "string" || !raw.trim()) return null;
  const requested = path.resolve(raw.trim());
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
  if (process.platform !== "win32" && (stat.mode & 0o077) !== 0) {
    throw new Error("run_intake.output_dir must be owner-only (mode 0700)");
  }
  return resolved;
}

function readJsonIfPresent(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${path.basename(filePath)} must be a regular JSON file`);
  }
  if (stat.size > MAX_LOCAL_JSON_BYTES) {
    throw new Error(`${path.basename(filePath)} exceeds ${MAX_LOCAL_JSON_BYTES} bytes`);
  }
  if (process.platform !== "win32" && (stat.mode & 0o077) !== 0) {
    throw new Error(`${path.basename(filePath)} must be owner-only (mode 0600)`);
  }
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!isObject(value)) throw new Error(`${path.basename(filePath)} must contain a JSON object`);
  return value;
}

function verifyStoredReview(outputDir, review, expectedHash) {
  if (!outputDir) return;
  const storedPath = path.join(outputDir, "review_payload.json");
  const stored = readJsonIfPresent(storedPath);
  if (!stored) {
    throw new Error("run_intake.output_dir must contain the reviewed review_payload.json");
  }
  const storedHash = canonicalSha256(stored);
  if (storedHash !== expectedHash || canonicalJson(stored) !== canonicalJson(review)) {
    throw new Error("stored review_payload.json does not match the reviewed payload hash");
  }
}

function manifestOutputRecords(outputDir, finalArtifacts) {
  if (!Array.isArray(finalArtifacts.outputs)) {
    throw new Error("final_artifacts.outputs must be an array");
  }
  const records = new Map();
  for (const [index, record] of finalArtifacts.outputs.entries()) {
    const field = `final_artifacts.outputs[${index}]`;
    if (!isObject(record)) throw new Error(`${field} must be an object`);
    const fileName = validateRelativeBasename(record.path, `${field}.path`);
    if (records.has(fileName)) throw new Error(`final_artifacts.outputs contains duplicate path: ${fileName}`);
    if (typeof record.sha256 !== "string" || !LOWERCASE_SHA256_RE.test(record.sha256)) {
      throw new Error(`${field}.sha256 must be a lowercase SHA-256 digest`);
    }
    const filePath = path.join(outputDir, fileName);
    if (!fs.existsSync(filePath)) throw new Error(`manifest output is missing: ${fileName}`);
    const stat = fs.lstatSync(filePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(`manifest output must be a regular file without symlinks: ${fileName}`);
    }
    if (process.platform !== "win32" && (stat.mode & 0o077) !== 0) {
      throw new Error(`manifest output must be owner-only (mode 0600): ${fileName}`);
    }
    if (sha256File(filePath) !== record.sha256) {
      throw new Error(`manifest output hash mismatch: ${fileName}`);
    }
    records.set(fileName, record);
  }
  const packageHash = outputPackageHash([...records.values()]);
  if (finalArtifacts.package_hash !== packageHash) {
    throw new Error("final_artifacts.package_hash does not match manifest outputs");
  }
  return records;
}

function verifyLocalArtifactBindings(outputDir, review, reviewHash, finalArtifacts) {
  const manifestRecords = manifestOutputRecords(outputDir, finalArtifacts);
  validateExportGate(finalArtifacts.export_gate, review, manifestRecords);
  for (const required of ["run_intake.json", "review_payload.json", ...Object.values(REQUIRED_SOURCE_ARTIFACTS)]) {
    if (!manifestRecords.has(required)) {
      throw new Error(`final_artifacts.outputs is missing required binding: ${required}`);
    }
  }
  const storedReviewPath = path.join(outputDir, "review_payload.json");
  if (canonicalSha256(readJsonIfPresent(storedReviewPath)) !== reviewHash) {
    throw new Error("review_payload.json canonical hash does not match the reviewed payload");
  }
  if (
    finalArtifacts.review_payload_sha256 != null
    && finalArtifacts.review_payload_sha256 !== reviewHash
  ) {
    throw new Error("final_artifacts.review_payload_sha256 does not match the reviewed payload");
  }

  const canonicalArtifactHashes = {};
  for (const [key, expectedPath] of Object.entries(REQUIRED_SOURCE_ARTIFACTS)) {
    const reference = review.source_artifacts[key];
    if (reference.path !== expectedPath) {
      throw new Error(`review_payload.source_artifacts.${key}.path must be ${expectedPath}`);
    }
    const artifact = readJsonIfPresent(path.join(outputDir, expectedPath));
    if (!artifact) throw new Error(`required source artifact is missing: ${expectedPath}`);
    const digest = canonicalSha256(artifact);
    if (digest !== reference.sha256) {
      throw new Error(`canonical source artifact hash mismatch: ${expectedPath}`);
    }
    canonicalArtifactHashes[key] = digest;
  }

  const facts = readJsonIfPresent(path.join(outputDir, REQUIRED_SOURCE_ARTIFACTS.facts));
  if (
    typeof facts.input_hash !== "string"
    || !LOWERCASE_SHA256_RE.test(facts.input_hash)
    || review.basis_hashes.new_client_input !== facts.input_hash
  ) {
    throw new Error("review_payload.basis_hashes.new_client_input does not match case_facts_validated.json");
  }
  const expectedBasis = {
    aml: canonicalArtifactHashes.aml,
    documents: canonicalArtifactHashes.documents,
    monitoring: canonicalArtifactHashes.monitoring,
    sources: canonicalArtifactHashes.sources,
  };
  for (const [key, digest] of Object.entries(expectedBasis)) {
    if (review.basis_hashes[key] !== digest) {
      throw new Error(`review_payload.basis_hashes.${key} does not match its local artifact`);
    }
  }

  const storedRunIntake = readJsonIfPresent(path.join(outputDir, "run_intake.json"));
  if (
    storedRunIntake.plugin !== PLUGIN_NAME
    || storedRunIntake.workflow !== review.workflow
    || storedRunIntake.run_id !== review.run_id
    || path.resolve(storedRunIntake.output_dir || "") !== outputDir
  ) {
    throw new Error("stored run_intake.json does not bind this review to the output directory");
  }
  return manifestRecords;
}

function serializeJson(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function artifactRecordForJson(fileName, value, status = "written_reviewed") {
  const serialized = serializeJson(value);
  return {
    path: fileName,
    kind: "json",
    status,
    size_bytes: Buffer.byteLength(serialized, "utf8"),
    sha256: crypto.createHash("sha256").update(serialized, "utf8").digest("hex"),
  };
}

function writeJsonBatchAtomic(outputDir, valuesByName) {
  if (!outputDir) return [];
  const transactionId = crypto.randomUUID();
  const staged = [];
  const backups = [];
  const installed = [];
  const names = Object.keys(valuesByName);
  if (new Set(names).size !== names.length) throw new Error("transaction contains duplicate file names");
  try {
    for (const fileName of names) {
      validateRelativeBasename(fileName, `transaction.${fileName}`);
      const outputPath = path.join(outputDir, fileName);
      if (fs.existsSync(outputPath)) {
        const current = fs.lstatSync(outputPath);
        if (!current.isFile() || current.isSymbolicLink()) {
          throw new Error(`refusing to replace non-regular file: ${fileName}`);
        }
      }
      const temporaryPath = path.join(outputDir, `.${fileName}.${transactionId}.tmp`);
      fs.writeFileSync(temporaryPath, serializeJson(valuesByName[fileName]), {
        encoding: "utf8",
        flag: "wx",
        mode: 0o600,
      });
      staged.push({ fileName, outputPath, temporaryPath });
    }
    for (const entry of staged) {
      if (fs.existsSync(entry.outputPath)) {
        const backupPath = path.join(outputDir, `.${entry.fileName}.${transactionId}.bak`);
        fs.renameSync(entry.outputPath, backupPath);
        backups.push({ ...entry, backupPath });
      }
    }
    for (const entry of staged) {
      fs.renameSync(entry.temporaryPath, entry.outputPath);
      installed.push(entry);
      if (process.platform !== "win32") fs.chmodSync(entry.outputPath, 0o600);
    }
    for (const entry of backups) fs.unlinkSync(entry.backupPath);
    return names;
  } catch (error) {
    for (const entry of [...installed].reverse()) {
      if (fs.existsSync(entry.outputPath)) fs.unlinkSync(entry.outputPath);
    }
    for (const entry of [...backups].reverse()) {
      if (fs.existsSync(entry.backupPath)) fs.renameSync(entry.backupPath, entry.outputPath);
    }
    throw error;
  } finally {
    for (const entry of staged) {
      if (fs.existsSync(entry.temporaryPath)) fs.unlinkSync(entry.temporaryPath);
    }
    for (const entry of backups) {
      if (fs.existsSync(entry.backupPath)) fs.unlinkSync(entry.backupPath);
    }
  }
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function mergeOutputRecords(existing, additions) {
  const byPath = new Map();
  for (const record of Array.isArray(existing) ? existing : []) {
    if (isObject(record) && typeof record.path === "string") {
      byPath.set(record.path, record);
    }
  }
  for (const record of additions) byPath.set(record.path, record);
  return [...byPath.values()].sort((left, right) => left.path.localeCompare(right.path));
}

function outputPackageHash(outputs) {
  return canonicalSha256(
    Object.fromEntries(outputs.map((record) => [record.path, record.sha256 || null])),
  );
}

function buildSavedDecisionManifest(current, review, reviewHash, uiDecisions) {
  const outputs = mergeOutputRecords(current.outputs, [
    artifactRecordForJson("ui_decisions.json", uiDecisions, "written_pending_application"),
  ]);
  const savedAt = new Date().toISOString();
  const decisionByItemId = new Map(
    uiDecisions.decisions.map((decision) => [decision.item_id, decision]),
  );
  const reviewBlockers = buildReviewGateBlockers(review, decisionByItemId);
  const relationshipReviewBlockers = reviewBlockers.filter(
    (blocker) => blocker.scope !== "marketing_use",
  );
  const exportGate = isObject(current.export_gate)
    ? {
        ...current.export_gate,
        evaluated_at: savedAt,
        review_revision: review.review_revision,
        status: "pending_review",
        relationship_ready: false,
        review_blockers: reviewBlockers,
        basis_hashes: { ...review.basis_hashes },
      }
    : null;
  const domainBlockers = exportGate?.domain_blockers || [];
  const artifactBlockers = exportGate?.artifact_blockers || [];
  const relationshipBlockers = [
    ...domainBlockers,
    ...artifactBlockers,
    ...relationshipReviewBlockers,
  ];
  const savedStatus = relationshipBlockers.length > 0 ? "blocked" : "pending_review";
  if (exportGate) exportGate.status = savedStatus;
  return {
    ...current,
    status: exportGate ? savedStatus : current.status,
    review_status: uiDecisions.status,
    review_payload_sha256: reviewHash,
    ...(exportGate
      ? {
          export_gate: exportGate,
          blockers: relationshipBlockers,
        }
      : {}),
    outputs,
    artifacts: outputs,
    package_hash: outputPackageHash(outputs),
    review_application: {
      status: savedStatus,
      decision_count: uiDecisions.decision_count,
      item_count: review.items.length,
      pending_count: review.items.length - uiDecisions.decision_count,
      blocker_count: relationshipBlockers.length,
      review_payload_sha256: reviewHash,
      domain_artifacts_modified: false,
      professional_review_required: true,
      signature_performed: false,
      client_communication_sent: false,
      relationship_activation_performed: false,
    },
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
  };
}

function saveDecisions(input) {
  const payload = validateReview(input);
  const persistent = preparePersistentRun(input, payload);
  const { uiDecisions } = buildUiDecisions(
    input,
    payload,
    persistent.currentUiDecisions,
  );
  uiDecisions.decision_revision = persistent.nextDecisionRevision;
  let finalArtifactsPath = null;
  let outputPath = null;
  if (persistent.outputDir) {
    const refreshed = buildSavedDecisionManifest(
      persistent.currentFinal,
      payload.review_payload,
      payload.review_payload_sha256,
      uiDecisions,
    );
    writeJsonBatchAtomic(persistent.outputDir, {
      "ui_decisions.json": uiDecisions,
      "final_artifacts.json": refreshed,
    });
    outputPath = "ui_decisions.json";
    finalArtifactsPath = "final_artifacts.json";
  }
  return {
    ok: true,
    validation_type: "new_client_decisions",
    run_id: uiDecisions.run_id,
    review_payload_sha256: uiDecisions.review_payload_sha256,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted: Boolean(outputPath),
    ui_decisions_path: outputPath,
    final_artifacts_path: finalArtifactsPath,
    message: outputPath
      ? `Saved ${uiDecisions.decision_count} new client decisions.`
      : "Validated decisions. Nothing was written because run_intake.output_dir was not supplied.",
    ui_decisions: publicUiDecisions(uiDecisions, payload.review_payload),
  };
}

function validateCurrentFinalArtifacts(current, review, reviewHash) {
  if (!isObject(current) || Object.keys(current).length === 0) return;
  validateFinalIdentity(current, review);
  if (
    current.review_payload_sha256 != null
    && current.review_payload_sha256 !== reviewHash
  ) {
    throw new Error("final_artifacts.review_payload_sha256 does not match the reviewed payload");
  }
}

function reviewItemScope(item) {
  if (item.item_type === "marketing_consent") return "marketing_use";
  if (item.item_type === "document_applicability") {
    return `document:${safeIdentifier(item.data.topic, `review item ${item.id} topic`)}`;
  }
  return "relationship_export";
}

function decisionBlocker(decision, item) {
  return {
    item_id: decision.item_id,
    item_type: decision.item_type,
    action: decision.action,
    status: decision.status,
    scope: reviewItemScope(item),
    requested_documents: decision.requested_documents || [],
  };
}

function reviewBlockerCode(action) {
  return {
    edit: "professional_revision_required",
    mark_unclear: "professional_review_unclear",
    reject: "professional_review_rejected",
    request_more_documents: "professional_documents_requested",
    skip: "professional_review_skipped",
  }[action] || "professional_review_pending";
}

function buildReviewGateBlockers(review, decisionByItemId) {
  const blockers = [];
  for (const item of review.items) {
    const decision = decisionByItemId.get(item.id);
    if (decision?.action === "accept") continue;
    blockers.push({
      code: reviewBlockerCode(decision?.action),
      reference: item.id,
      scope: reviewItemScope(item),
    });
  }
  return blockers;
}

function applyDecisions(input) {
  const payload = validateReview(input);
  const review = payload.review_payload;
  const reviewHash = payload.review_payload_sha256;
  const persistent = preparePersistentRun(input, payload);
  const { uiDecisions } = buildUiDecisions(
    input,
    payload,
    persistent.currentUiDecisions,
  );
  const outputDir = persistent.outputDir;
  uiDecisions.decision_revision = persistent.nextDecisionRevision;
  const currentFinal = outputDir
    ? persistent.currentFinal
    : (isObject(input.final_artifacts) ? input.final_artifacts : {});
  validateCurrentFinalArtifacts(currentFinal, review, reviewHash);

  const decidedIds = new Set(uiDecisions.decisions.map((decision) => decision.item_id));
  const pendingItemIds = review.items
    .filter((item) => !decidedIds.has(item.id))
    .map((item) => item.id);
  const reviewItemById = new Map(review.items.map((item) => [item.id, item]));
  const blockerDecisions = uiDecisions.decisions
    .filter((decision) => BLOCKER_ACTIONS.has(decision.action))
    .map((decision) => decisionBlocker(decision, reviewItemById.get(decision.item_id)));
  const relationshipBlockerDecisions = blockerDecisions.filter(
    (blocker) => blocker.scope !== "marketing_use",
  );
  const currentExportGate = isObject(currentFinal.export_gate)
    ? currentFinal.export_gate
    : null;
  const domainBlockers = currentExportGate
    ? currentExportGate.domain_blockers.map((blocker) => ({ ...blocker }))
    : [];
  const artifactBlockers = currentExportGate
    ? currentExportGate.artifact_blockers.map((blocker) => ({ ...blocker }))
    : [];
  const preservedMarketingOnlyBlockers = currentExportGate
    ? currentExportGate.marketing_only_blockers.map((blocker) => ({ ...blocker }))
    : [];
  const existingDomainBlockerCount = domainBlockers.length;
  const existingArtifactBlockerCount = artifactBlockers.length;
  const relationshipItems = review.items.filter(
    (item) => item.item_type !== "marketing_consent",
  );
  const decisionByItemId = new Map(
    uiDecisions.decisions.map((decision) => [decision.item_id, decision]),
  );
  const professionalReviewerBlockers = uiDecisions.reviewer
    || !outputDir
    || relationshipItems.length === 0
    || !relationshipItems.every((item) => {
      const decision = decisionByItemId.get(item.id);
      return decision != null && ["accept", "edit"].includes(decision.action);
    })
    ? []
    : [
        {
          code: "professional_reviewer_required",
          reference: "ui_decisions",
          scope: "relationship_export",
        },
      ];
  const reviewGateBlockers = [
    ...buildReviewGateBlockers(review, decisionByItemId),
    ...professionalReviewerBlockers,
  ];
  const relationshipReviewGateBlockers = reviewGateBlockers.filter(
    (blocker) => blocker.scope !== "marketing_use",
  );
  const marketingReviewGateBlockers = reviewGateBlockers.filter(
    (blocker) => blocker.scope === "marketing_use",
  );
  const allRelationshipItemsAcceptedOrEdited =
    relationshipItems.length > 0
    && relationshipItems.every((item) => {
      const decision = decisionByItemId.get(item.id);
      return decision != null && ["accept", "edit"].includes(decision.action);
    });
  const editedItemIds = uiDecisions.decisions
    .filter((decision) => decision.action === "edit")
    .map((decision) => decision.item_id);
  const relationshipEditedItemIds = uiDecisions.decisions
    .filter(
      (decision) =>
        decision.action === "edit" && decision.item_type !== "marketing_consent",
    )
    .map((decision) => decision.item_id);
  const validatedPersistentOutputs = Boolean(
    outputDir
    && persistent.manifestRecords instanceof Map
    && persistent.manifestRecords.size > 0
    && currentExportGate,
  );
  const professionalReviewerRequiredForReady = Boolean(
    allRelationshipItemsAcceptedOrEdited
    && validatedPersistentOutputs
    && !uiDecisions.reviewer,
  );
  const applicationStatus =
    relationshipBlockerDecisions.length > 0
      || existingDomainBlockerCount > 0
      || existingArtifactBlockerCount > 0
      || professionalReviewerRequiredForReady
      ? "blocked"
      : relationshipEditedItemIds.length > 0
        ? "proposals_ready"
      : allRelationshipItemsAcceptedOrEdited && validatedPersistentOutputs
        && uiDecisions.reviewer
        ? "ready_for_professional_export"
        : "partial_review_applied";
  const exportGateStatus =
    applicationStatus === "ready_for_professional_export"
      ? "ready_for_professional_export"
      : applicationStatus === "blocked"
        ? "blocked"
        : "pending_review";
  const relationshipBlockerCount =
    existingDomainBlockerCount
    + existingArtifactBlockerCount
    + relationshipReviewGateBlockers.length;
  const marketingUseBlockerCount =
    preservedMarketingOnlyBlockers.length + marketingReviewGateBlockers.length;
  const appliedAt = new Date().toISOString();
  const effects = uiDecisions.decisions.map((decision) => ({
    ...decision,
    applied_at: appliedAt,
    application:
      decision.action === "edit"
        ? "revision_instruction_recorded_domain_artifacts_unchanged"
        : "review_status_recorded_domain_artifacts_unchanged",
    domain_artifacts_modified: false,
  }));
  const appliedDecisions = {
    schema_version: review.schema_version,
    contract_version: review.contract_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    review_revision: review.review_revision,
    applied_at: appliedAt,
    decision_source: uiDecisions.decision_source,
    ...(uiDecisions.reviewer ? { reviewer: uiDecisions.reviewer } : {}),
    review_payload_path: "review_payload.json",
    review_payload_sha256: reviewHash,
    decisions: uiDecisions.decisions,
    effects,
    decision_count: uiDecisions.decision_count,
    item_count: review.items.length,
    pending_item_ids: pendingItemIds,
    pending_count: pendingItemIds.length,
    edited_item_ids: editedItemIds,
    relationship_edited_item_ids: relationshipEditedItemIds,
    revision_required: relationshipEditedItemIds.length > 0,
    marketing_revision_required:
      editedItemIds.length > relationshipEditedItemIds.length,
    blockers: blockerDecisions,
    blocker_count: relationshipBlockerCount,
    marketing_use_blocker_count: marketingUseBlockerCount,
    existing_domain_blocker_count: existingDomainBlockerCount,
    existing_artifact_blocker_count: existingArtifactBlockerCount,
    application_status: applicationStatus,
    domain_artifacts_modified: false,
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
  };
  let finalArtifacts = {
    ...currentFinal,
    schema_version: currentFinal.schema_version || review.schema_version,
    contract_version: currentFinal.contract_version || review.contract_version,
    plugin: PLUGIN_NAME,
    workflow: PLUGIN_NAME,
    run_id: review.run_id,
    status: currentExportGate ? exportGateStatus : applicationStatus,
    review_status: applicationStatus,
    review_payload_sha256: reviewHash,
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
    ...(currentExportGate
      ? {
          export_gate: {
            ...currentExportGate,
            evaluated_at: appliedAt,
            review_revision: review.review_revision,
            status: exportGateStatus,
            relationship_ready:
              applicationStatus === "ready_for_professional_export",
            domain_blockers: domainBlockers,
            review_blockers: reviewGateBlockers,
            artifact_blockers: artifactBlockers,
            marketing_only_blockers: preservedMarketingOnlyBlockers,
            basis_hashes: { ...review.basis_hashes },
          },
          blockers: [
            ...domainBlockers,
            ...artifactBlockers,
            ...relationshipReviewGateBlockers,
          ],
        }
      : {}),
    review_application: {
      applied_at: appliedAt,
      status: applicationStatus,
      decision_count: uiDecisions.decision_count,
      item_count: review.items.length,
      pending_count: pendingItemIds.length,
      edited_item_ids: editedItemIds,
      relationship_edited_item_ids: relationshipEditedItemIds,
      revision_required: relationshipEditedItemIds.length > 0,
      marketing_revision_required:
        editedItemIds.length > relationshipEditedItemIds.length,
      blocker_count: relationshipBlockerCount,
      marketing_use_blocker_count: marketingUseBlockerCount,
      applied_decisions_path: "applied_decisions.json",
      history_path: null,
      review_payload_sha256: reviewHash,
      domain_artifacts_modified: false,
      professional_review_required: true,
      signature_performed: false,
      client_communication_sent: false,
      relationship_activation_performed: false,
    },
  };
  if (payloadBytes(appliedDecisions) > MAX_PAYLOAD_BYTES) {
    throw new Error(`applied_decisions payload exceeds ${MAX_PAYLOAD_BYTES} bytes`);
  }

  let uiPath = null;
  let appliedPath = null;
  let historyPath = null;
  if (outputDir) {
    const historyStamp = appliedAt.replace(/[^0-9]/g, "");
    historyPath = `applied_decisions.history.r${review.review_revision}.d${uiDecisions.decision_revision}.${historyStamp}.${crypto.randomUUID().slice(0, 8)}.json`;
    const outputs = mergeOutputRecords(currentFinal.outputs, [
      artifactRecordForJson("ui_decisions.json", uiDecisions),
      artifactRecordForJson("applied_decisions.json", appliedDecisions),
      artifactRecordForJson(historyPath, appliedDecisions, "written_immutable_history"),
    ]);
    finalArtifacts = {
      ...finalArtifacts,
      outputs,
      artifacts: outputs,
      package_hash: outputPackageHash(outputs),
      review_application: {
        ...finalArtifacts.review_application,
        history_path: historyPath,
      },
    };
    validateExportGate(finalArtifacts.export_gate, review);
    writeJsonBatchAtomic(outputDir, {
      "ui_decisions.json": uiDecisions,
      "applied_decisions.json": appliedDecisions,
      [historyPath]: appliedDecisions,
      "final_artifacts.json": finalArtifacts,
    });
    uiPath = "ui_decisions.json";
    appliedPath = "applied_decisions.json";
  }
  const finalPath = outputDir ? "final_artifacts.json" : null;
  return {
    ok: true,
    validation_type: "new_client_application",
    run_id: review.run_id,
    review_payload_sha256: reviewHash,
    decision_count: uiDecisions.decision_count,
    item_count: review.items.length,
    pending_count: pendingItemIds.length,
    edited_item_ids: editedItemIds,
    relationship_edited_item_ids: relationshipEditedItemIds,
    revision_required: relationshipEditedItemIds.length > 0,
    marketing_revision_required:
      editedItemIds.length > relationshipEditedItemIds.length,
    blocker_count: relationshipBlockerCount,
    marketing_use_blocker_count: marketingUseBlockerCount,
    application_status: applicationStatus,
    persisted: Boolean(outputDir),
    ui_decisions_path: uiPath,
    applied_decisions_path: appliedPath,
    review_history_path: historyPath,
    final_artifacts_path: finalPath,
    ui_decisions: publicUiDecisions(uiDecisions, review),
    domain_artifacts_modified: false,
    professional_review_required: true,
    signature_performed: false,
    client_communication_sent: false,
    relationship_activation_performed: false,
    message: outputDir
      ? "Review decisions recorded; domain artifacts, signatures, client communications, and relationship activation remain untouched."
      : "Application preview validated. Nothing was written because run_intake.output_dir was not supplied.",
    applied_decisions: appliedDecisions,
    final_artifacts: publicFinalArtifacts(finalArtifacts, review),
  };
}

function callTool(name, input) {
  if (name === TOOL_NAMES.validate) {
    const payload = validateReview(input);
    return {
      ok: true,
      validation_type: "new_client_review",
      run_id: payload.review_payload.run_id,
      item_count: payload.review_payload.item_count,
      review_payload_sha256: payload.review_payload_sha256,
      message: `Review payload is valid; call ${TOOL_NAMES.render} to open it.`,
      review_payload: payload.review_payload,
    };
  }
  if (name === TOOL_NAMES.render) {
    const payload = validateReview(input);
    let persistenceToken = null;
    try {
      persistenceToken = issuePersistenceToken(input, payload);
      payload.decision_policy.can_persist = Boolean(persistenceToken);
      payload.decision_policy.persistence_token = persistenceToken;
      if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {
        throw new Error(
          `new client widget payload exceeds ${MAX_PAYLOAD_BYTES} bytes`,
        );
      }
      return payload;
    } catch (error) {
      if (persistenceToken) PERSISTENCE_CONTEXTS.delete(persistenceToken);
      throw error;
    }
  }
  if (name === TOOL_NAMES.save) return saveDecisions(input);
  if (name === TOOL_NAMES.apply) return applyDecisions(input);
  throw new Error(`unknown tool: ${name}`);
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
  const payload = {
    ok: false,
    error: error instanceof Error ? error.message : String(error),
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
  const params = isObject(message.params) ? message.params : {};
  try {
    if (message.method === "initialize") {
      return rpcResult(id, {
        protocolVersion: params.protocolVersion || "2024-11-05",
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: { tools: {}, resources: {}, prompts: {} },
        instructions:
          `Call ${TOOL_NAMES.validate} before ${TOOL_NAMES.render}. Save/apply only record professional review decisions; they never modify domain artifacts, sign documents, contact the client, or activate the relationship.`,
      });
    }
    if (message.method === "notifications/initialized") return null;
    if (message.method === "tools/list") return rpcResult(id, { tools: toolDefinitions() });
    if (message.method === "tools/call") {
      if (typeof params.name !== "string") {
        return rpcError(id, -32602, "tools/call requires a tool name");
      }
      if (!isObject(params.arguments)) {
        return rpcError(id, -32602, "tools/call arguments must be an object");
      }
      try {
        return rpcResult(id, toolResult(callTool(params.name, params.arguments), params.name));
      } catch (error) {
        return rpcResult(id, toolError(error));
      }
    }
    if (message.method === "resources/list") return rpcResult(id, { resources: resources() });
    if (message.method === "resources/read") {
      if (typeof params.uri !== "string") {
        return rpcError(id, -32602, "resources/read requires a resource URI");
      }
      return rpcResult(id, {
        contents: [
          {
            uri: params.uri,
            mimeType: WIDGET_MIME_TYPE,
            text: resourceText(params.uri),
            _meta: widgetMeta(),
          },
        ],
      });
    }
    if (message.method === "resources/templates/list") {
      return rpcResult(id, { resourceTemplates: [] });
    }
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

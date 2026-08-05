#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const BRIDGE = path.join(PLUGIN_ROOT, "scripts", "service_bridge.py");

const COMMON_MUTATION = {
  case_id: { type: "string", minLength: 1 },
  revision_id: { type: "string", minLength: 1 },
  idempotency_key: { type: "string", minLength: 1 },
};

function objectSchema(properties, required) {
  return { type: "object", properties, required, additionalProperties: false };
}

const TOOLS = [
  {
    name: "xbrl_case_create",
    title: "Create intelligent bilancio case",
    description: "Create a tenant-scoped intelligent Italian OIC annual-accounts case.",
    inputSchema: objectSchema(
      {
        payload: { type: "object" },
        idempotency_key: { type: "string", minLength: 1 },
      },
      ["payload", "idempotency_key"],
    ),
  },
  {
    name: "xbrl_document_ingest",
    title: "Understand bilancio evidence",
    description: "Ingest a local trial balance or prior filed XBRL into a case.",
    inputSchema: objectSchema(
      {
        ...COMMON_MUTATION,
        document_kind: { enum: ["TRIAL_BALANCE", "PRIOR_XBRL"] },
        source_path: { type: "string", minLength: 1 },
        sheet: { type: "string" },
      },
      ["case_id", "revision_id", "idempotency_key", "document_kind", "source_path"],
    ),
  },
  {
    name: "xbrl_case_analyze",
    title: "Advance intelligent bilancio",
    description: "Run one guarded preparation step and return the next reviewable case status.",
    inputSchema: objectSchema(
      {
        ...COMMON_MUTATION,
        operation: {
          enum: [
            "confirm_parser",
            "migrate_regulatory_versions",
            "determine_forms",
            "select_form",
            "compute_statements",
            "record_schedule",
            "record_schedule_taxonomy_adapter",
            "ingest_schedule",
            "activate_disclosures",
            "preview",
            "load_client_history",
            "remember_client_history",
            "record_issue_reviews",
            "record_adjustments",
            "record_taxonomy_facts",
            "record_statutory_presentation",
            "record_taxonomy_representation",
            "record_micro_reporting",
          ],
        },
        payload: { type: "object" },
      },
      ["case_id", "revision_id", "idempotency_key", "operation", "payload"],
    ),
  },
  {
    name: "xbrl_mapping_get_review_packet",
    title: "Get mapping review packet",
    description: "Return reviewed mapping records for one authorized case.",
    inputSchema: objectSchema({ case_id: { type: "string", minLength: 1 } }, ["case_id"]),
  },
  {
    name: "xbrl_mapping_apply_decisions",
    title: "Apply mapping decisions",
    description: "Apply explicit balancing mapping, split, or exclusion decisions.",
    inputSchema: objectSchema(
      { ...COMMON_MUTATION, decisions: { type: "array", items: { type: "object" } } },
      ["case_id", "revision_id", "idempotency_key", "decisions"],
    ),
  },
  {
    name: "xbrl_questionnaire_get",
    title: "Get Bilancio questionnaire",
    description: "Return active structured questions and their evidence reasons.",
    inputSchema: objectSchema({ case_id: { type: "string", minLength: 1 } }, ["case_id"]),
  },
  {
    name: "xbrl_questionnaire_submit",
    title: "Submit questionnaire answers",
    description: "Record structured answers without treating unknown or absent data as zero.",
    inputSchema: objectSchema(
      { ...COMMON_MUTATION, answers: { type: "array", items: { type: "object" } } },
      ["case_id", "revision_id", "idempotency_key", "answers"],
    ),
  },
  {
    name: "xbrl_draft_generate",
    title: "Generate structured notes draft",
    description: "Record provenance-bound narrative blocks and render a review preview.",
    inputSchema: objectSchema(
      {
        ...COMMON_MUTATION,
        operation: { enum: ["record_narratives", "preview"] },
        payload: { type: "object" },
      },
      ["case_id", "revision_id", "idempotency_key", "operation", "payload"],
    ),
  },
  {
    name: "xbrl_case_validate",
    title: "Validate intelligent bilancio",
    description: "Run the independent deterministic validation layers.",
    inputSchema: objectSchema(COMMON_MUTATION, ["case_id", "revision_id", "idempotency_key"]),
  },
  {
    name: "xbrl_case_prepare_xbrl_review",
    title: "Prepare validated XBRL review",
    description:
      "Render the current case and run the configured local XBRL processor before approval.",
    inputSchema: objectSchema(COMMON_MUTATION, ["case_id", "revision_id", "idempotency_key"]),
  },
  {
    name: "xbrl_case_approve",
    title: "Approve bilancio snapshot",
    description: "Create an immutable reviewer-approved snapshot after every blocking gate passes.",
    inputSchema: objectSchema(
      { ...COMMON_MUTATION, declaration: { type: "object" } },
      ["case_id", "revision_id", "idempotency_key", "declaration"],
    ),
  },
  {
    name: "xbrl_case_export",
    title: "Export approved bilancio",
    description: "Render XBRL and the other review artifacts from the approved canonical bilancio.",
    inputSchema: objectSchema(COMMON_MUTATION, ["case_id", "revision_id", "idempotency_key"]),
  },
  {
    name: "xbrl_case_get_workpaper",
    title: "Get Bilancio workpaper",
    description: "Return the authorized approved workpaper resource, not the XBRL bytes.",
    inputSchema: objectSchema({ case_id: { type: "string", minLength: 1 } }, ["case_id"]),
  },
  {
    name: "xbrl_case_artifact_download_grant",
    title: "Create Bilancio artifact download grant",
    description:
      "Create an audited short-lived download URL for one checksum-verified approved artifact.",
    inputSchema: objectSchema(
      {
        case_id: { type: "string", minLength: 1 },
        artifact_id: { type: "string", minLength: 1 },
        idempotency_key: { type: "string", minLength: 1 },
        ttl_seconds: { type: "integer", minimum: 30, maximum: 900 },
      },
      ["case_id", "artifact_id", "idempotency_key"],
    ),
  },
  {
    name: "xbrl_case_get_intelligence_packet",
    title: "Get intelligent participation packet",
    description: "Return minimum-necessary case context for one semantic workflow task.",
    inputSchema: objectSchema(
      {
        case_id: { type: "string", minLength: 1 },
        task: {
          enum: [
            "AUTO",
            "WORKFLOW_GUIDANCE",
            "ACCOUNT_MAPPING",
            "QUESTION_PRIORITIZATION",
            "NARRATIVE_DRAFT",
            "PRIOR_YEAR_COMPARISON",
            "ISSUE_EXPLANATION",
          ],
        },
        subject_ids: { type: "array", items: { type: "string" } },
      },
      ["case_id", "task"],
    ),
  },
  {
    name: "xbrl_case_record_intelligence",
    title: "Record intelligent workflow suggestion",
    description: "Validate and record a non-authoritative model suggestion for professional review.",
    inputSchema: objectSchema(
      {
        ...COMMON_MUTATION,
        task: { type: "string" },
        subject_ids: { type: "array", items: { type: "string" } },
        output: { type: "object" },
        model_metadata: { type: "object" },
      },
      [
        "case_id",
        "revision_id",
        "idempotency_key",
        "task",
        "output",
        "model_metadata",
      ],
    ),
  },
  {
    name: "xbrl_case_enqueue_job",
    title: "Queue Bilancio processing",
    description:
      "Queue a long-running case operation against the exact current revision; the host worker executes it later.",
    inputSchema: objectSchema(
      {
        case_id: { type: "string", minLength: 1 },
        revision_id: { type: "string", minLength: 1 },
        job_id: { type: "string", minLength: 1 },
        operation: {
          enum: [
            "ingest",
            "ingest_prior_xbrl",
            "ingest_schedule",
            "mapping_candidates",
            "record_intelligence",
            "record_narratives",
            "preview",
            "validate",
            "prepare_xbrl_review",
            "export",
            "taxonomy_catalogue_build",
            "invoke_intelligence",
          ],
        },
        payload: { type: "object" },
        max_attempts: { type: "integer", minimum: 1, maximum: 10 },
      },
      ["case_id", "revision_id", "job_id", "operation", "payload"],
    ),
  },
  {
    name: "xbrl_case_job_get",
    title: "Get Bilancio job status",
    description:
      "Return the compact integrity-verified status of one tenant-scoped background job.",
    inputSchema: objectSchema(
      {
        case_id: { type: "string", minLength: 1 },
        job_id: { type: "string", minLength: 1 },
      },
      ["case_id", "job_id"],
    ),
  },
  {
    name: "xbrl_case_get_review_view",
    title: "Get Bilancio professional review view",
    description:
      "Return one bounded structured review surface without returning source files or generated artifact bytes.",
    inputSchema: objectSchema(
      {
        case_id: { type: "string", minLength: 1 },
        view: {
          enum: [
            "CASE_DASHBOARD",
            "SOURCE_REVIEW",
            "MAPPING_GRID",
            "STATEMENTS",
            "SCHEDULES",
            "QUESTIONNAIRE",
            "NOTES_EDITOR",
            "ISSUES_PANEL",
            "PREVIEW",
            "APPROVAL_EXPORT",
          ],
        },
        offset: { type: "integer", minimum: 0 },
        limit: { type: "integer", minimum: 1, maximum: 500 },
      },
      ["case_id", "view"],
    ),
  },
].map((tool) => ({
  ...tool,
  annotations: {
    readOnlyHint: tool.name.includes("_get_"),
    destructiveHint: false,
    openWorldHint: false,
  },
}));

function response(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function errorResponse(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function callBridge(tool, args) {
  const python = process.env.VERA_XBRL_PYTHON || "python3";
  const result = spawnSync(python, [BRIDGE], {
    cwd: PLUGIN_ROOT,
    env: process.env,
    input: JSON.stringify({ tool, arguments: args }),
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "Service bridge failed").trim());
  }
  return JSON.parse(result.stdout);
}

function handle(message) {
  if (message.method === "notifications/initialized") return null;
  if (message.method === "initialize") {
    return response(message.id, {
      protocolVersion: "2025-03-26",
      capabilities: { tools: {} },
      serverInfo: { name: "vera-bilancio-xbrl-it", version: MANIFEST.version },
    });
  }
  if (message.method === "tools/list") return response(message.id, { tools: TOOLS });
  if (message.method === "tools/call") {
    const tool = TOOLS.find((item) => item.name === message.params?.name);
    if (!tool) return errorResponse(message.id, -32601, "Unknown tool");
    try {
      const payload = callBridge(tool.name, message.params?.arguments || {});
      return response(message.id, {
        content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
        structuredContent: payload,
        isError: false,
      });
    } catch (error) {
      return errorResponse(message.id, -32000, String(error.message || error));
    }
  }
  if (message.id == null) return null;
  return errorResponse(message.id, -32601, "Method not found");
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  if (!line.trim()) return;
  try {
    const result = handle(JSON.parse(line));
    if (result != null) process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify(errorResponse(null, -32700, String(error.message || error)))}\n`,
    );
  }
});

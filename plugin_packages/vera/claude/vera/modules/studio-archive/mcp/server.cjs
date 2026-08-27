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
const SERVER_NAME = "vera-studio-archive";
const SERVER_VERSION = MANIFEST.version || "0.1.0";
const CLI_PATH = path.join(PLUGIN_ROOT, "scripts", "studio_archive.py");
const MAX_OUTPUT_BYTES = 8_000_000;
const TOOL_NAMES = {
  status: "studio_archive_status",
  clients: "list_studio_archive_clients",
  resolveClient: "resolve_studio_archive_client",
  clientFolder: "get_studio_client_folder",
  createClient: "create_studio_archive_client",
  createEngagement: "create_studio_client_engagement",
  importDocument: "import_studio_client_document",
  snapshotFolder: "snapshot_studio_client_folder",
  googleDriveStatus: "studio_archive_google_drive_status",
  bindGoogleDrive: "bind_studio_client_google_drive",
  snapshotGoogleDrive: "snapshot_studio_client_google_drive",
  archiveInventory: "get_studio_archive_organization_inventory",
  openArchiveItem: "open_studio_archive_organization_item",
  engagements: "list_studio_client_engagements",
  prepareWorkflow: "prepare_studio_client_workflow",
  startCheckEntriesFromSample: "start_check_entries_from_sample",
  startWorkflow: "start_studio_client_workflow",
  failWorkflow: "fail_studio_client_workflow",
  cancelWorkflow: "cancel_studio_client_workflow",
  finalizeWorkflow: "finalize_studio_client_workflow",
  completeWorkflow: "complete_studio_client_workflow",
  closeEngagement: "close_studio_client_engagement",
  recoverLedger: "recover_studio_client_ledger",
  retentionReport: "report_studio_client_retention",
  setup: "setup_studio_archive",
  diagnoseAccess: "diagnose_studio_archive_access",
  configure: "configure_studio_archive",
  refresh: "refresh_studio_archive",
  search: "search_studio_archive",
  open: "open_studio_archive_source",
  configureClient: "configure_studio_archive_client",
  planGmail: "plan_studio_archive_gmail_search",
  matchEmail: "match_studio_archive_email",
};
const VERA_CLIENT_WORKFLOW_IDS = Object.freeze([
  "open-item-reconciliation",
  "archive-organization",
  "client-file-preparation",
  "new-client",
  "journal-sampling",
  "check-entries",
  "journal-bank-reconciliation",
  "passive-invoice-audit",
  "sales-plan",
  "business-planning",
  "variance-analysis",
  "management-control-pack",
  "centrale-rischi-review",
  "financial-analysis",
  "report-builder",
  "concordato-plan-review",
  "prompt-optimizer",
  "deep-research-validator",
  "previdenza-inps",
  "registro-imprese-sari",
  "bandi-agevolazioni",
]);
const CLIENT_WORKFLOW_IDS = Object.freeze([
  ...VERA_CLIENT_WORKFLOW_IDS,
  ...(process.env.LUCIA_ASSURANCE_HOST === "1" ? ["apertura-pratica"] : []),
]);

function objectSchema(properties, required = []) {
  return {
    type: "object",
    properties,
    required,
    additionalProperties: false,
  };
}

function runIdentityProperties() {
  return {
    client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
    engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
    run_id: { type: "string", pattern: "^run_[0-9a-f]{24}$" },
  };
}

function runIdentitySchema() {
  return objectSchema(runIdentityProperties(), [
    "client_id",
    "engagement_id",
    "run_id",
  ]);
}

function annotations(readOnly, idempotent = true, openWorld = false) {
  return {
    readOnlyHint: readOnly,
    destructiveHint: false,
    idempotentHint: idempotent,
    openWorldHint: openWorld,
  };
}

function toolDefinitions() {
  return [
    {
      name: TOOL_NAMES.status,
      title: "Check Vera Studio Archive status",
      description:
        "Read the local Studio Archive configuration, exact available scopes, refresh state, index counts, and named evidence gaps. Call this before searching.",
      inputSchema: objectSchema({}),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.clients,
      title: "List Studio Archive clients",
      description:
        "List registered client and orphaned-profile records using stable IDs, display labels, status, and private-identity counts. Stored email addresses, legal names, and tax identifiers remain local.",
      inputSchema: objectSchema({}),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.resolveClient,
      title: "Resolve one exact Studio Archive client identity",
      description:
        "Compare one user-supplied email address, legal name, or tax identifier against the private local registry and return only matching safe client directory rows. The supplied value and stored identity values are not echoed.",
      inputSchema: objectSchema(
        {
          identity_kind: {
            type: "string",
            enum: ["email_address", "legal_name", "tax_identifier"],
          },
          identity_value: { type: "string", minLength: 1, maxLength: 254 },
        },
        ["identity_kind", "identity_value"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.clientFolder,
      title: "Get one Studio Archive client folder",
      description:
        "Return a digest-bound folder record for one stable registered client. Other Vera workflows use this record to reject cross-client inputs and namespace engagement runs.",
      inputSchema: objectSchema(
        {
          client_id: {
            type: "string",
            pattern: "^client_[0-9a-f]{24}$",
            description: "Stable client_id returned by Studio Archive.",
          },
        },
        ["client_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.createClient,
      title: "Create a new Studio Archive client",
      description:
        "After the user explicitly chooses New client, create a safely named top-level folder, assign a stable client ID independent of that folder name, and register the confirmed identity. This begins but does not complete Vera's New Client professional workflow.",
      inputSchema: objectSchema(
        {
          legal_name: {
            type: "string",
            minLength: 1,
            maxLength: 160,
            description: "Confirmed client legal name; Vera derives the folder label.",
          },
          email_addresses: {
            type: "array",
            maxItems: 20,
            items: { type: "string", minLength: 3, maxLength: 254 },
            description: "Optional confirmed full email or PEC addresses.",
          },
          tax_identifiers: {
            type: "array",
            maxItems: 20,
            items: { type: "string", minLength: 5, maxLength: 32 },
            description: "Optional confirmed codice fiscale or partita IVA values.",
          },
        },
        ["legal_name"],
      ),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.importDocument,
      title: "Import a document into one client engagement",
      description:
        "After the user confirms the exact client and copy action, preserve the original file and copy one regular source, journal, or support file into a managed client engagement with a byte receipt.",
      inputSchema: objectSchema(
        {
          client_id: {
            type: "string",
            pattern: "^client_[0-9a-f]{24}$",
          },
          source_path: {
            type: "string",
            minLength: 1,
            maxLength: 4096,
            description: "Absolute path to the user-selected source, journal, or support file.",
          },
          role: {
            type: "string",
            enum: ["journal", "source", "support"],
          },
          engagement_id: {
            type: "string",
            pattern: "^eng_[0-9a-f]{24}$",
            description: "Exact engagement selected or created before this separate import action.",
          },
        },
        ["client_id", "source_path", "role", "engagement_id"],
      ),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.snapshotFolder,
      title: "Snapshot one Studio Archive client folder",
      description:
        "After selecting one registered client and open engagement, hash a bounded client-folder view locally and return its complete projected Archive Organization inventory. Raw hashes and absolute paths stay local; client documents are not copied or moved.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
        },
        ["client_id", "engagement_id"],
      ),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.googleDriveStatus,
      title: "Check Studio Archive Google Drive status",
      description:
        "Read whether a private Google Drive OAuth token and exact client-folder bindings are present. This does not call Google Drive.",
      inputSchema: objectSchema({}),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.bindGoogleDrive,
      title: "Bind one client to one Google Drive folder",
      description:
        "After explicit client and Google Drive folder selection, validate the remote folder ID and persist a one-to-one private binding. This calls Google Drive but does not move documents.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          folder_id: {
            type: "string",
            pattern: "^[A-Za-z0-9_-]{3,256}$",
            description: "Exact Google Drive client-folder ID selected by the user.",
          },
        },
        ["client_id", "folder_id"],
      ),
      annotations: annotations(false, false, true),
    },
    {
      name: TOOL_NAMES.snapshotGoogleDrive,
      title: "Snapshot one bound Google Drive client folder",
      description:
        "Recursively read one exact bound My Drive or Shared Drive folder and return its complete projected Archive Organization inventory. Stable IDs, versions, parents, capabilities, and checksums stay in the local receipt.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
        },
        ["client_id", "engagement_id"],
      ),
      annotations: annotations(false, false, true),
    },
    {
      name: TOOL_NAMES.archiveInventory,
      title: "Resume one Archive Organization inventory",
      description:
        "Return the complete model-facing inventory for one immutable client snapshot. Opaque item references preserve local mapping while raw hashes, storage IDs, capabilities, and absolute paths stay local.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
          snapshot_input_id: { type: "string", pattern: "^input_[0-9a-f]{24}$" },
        },
        ["client_id", "engagement_id", "snapshot_input_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.openArchiveItem,
      title: "Open one snapshotted Archive Organization item",
      description:
        "Resolve one opaque inventory item locally, revalidate its immutable snapshot identity, and return bounded citable content. Raw local paths, Drive IDs, hashes, versions, and capabilities are not returned.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
          snapshot_input_id: { type: "string", pattern: "^input_[0-9a-f]{24}$" },
          item_ref: { type: "string", pattern: "^archive_item_[0-9a-f]{24}$" },
        },
        ["client_id", "engagement_id", "snapshot_input_id", "item_ref"],
      ),
      annotations: annotations(true, true, true),
    },
    {
      name: TOOL_NAMES.createEngagement,
      title: "Create a Studio Archive client engagement",
      description:
        "Create one durable engagement and managed input folder for an exact registered client without assuming a journal or any other document type.",
      inputSchema: objectSchema(
        {
          client_id: {
            type: "string",
            pattern: "^client_[0-9a-f]{24}$",
          },
          engagement_label: {
            type: "string",
            minLength: 1,
            maxLength: 160,
          },
        },
        ["client_id", "engagement_label"],
      ),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.engagements,
      title: "List one client's Studio engagements",
      description:
        "List durable engagement IDs, imported-file receipts, persisted workflow contexts, and exact available output paths for one stable client so a later chat can resume the journal engagement without relying on chat history.",
      inputSchema: objectSchema(
        {
          client_id: {
            type: "string",
            pattern: "^client_[0-9a-f]{24}$",
          },
        },
        ["client_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.prepareWorkflow,
      title: "Prepare a client-bound Vera workflow run",
      description:
        "Prepare or replay one exact customer-folder run bound to selected immutable input receipts and upstream artifacts. A repeated request is idempotent; new_run must be explicit.",
      inputSchema: objectSchema(
        {
          engagement_id: {
            type: "string",
            pattern: "^eng_[0-9a-f]{24}$",
          },
          workflow_id: {
            type: "string",
            enum: CLIENT_WORKFLOW_IDS,
          },
          input_ids: {
            type: "array",
            maxItems: 10000,
            items: { type: "string", pattern: "^input_[0-9a-f]{24}$" },
            description: "Exact imported input IDs selected for this run.",
          },
          upstream_artifacts: {
            type: "array",
            maxItems: 10000,
            items: objectSchema(
              {
                run_id: { type: "string", pattern: "^run_[0-9a-f]{24}$" },
                artifact_id: { type: "string", minLength: 1, maxLength: 120 },
                role: { type: "string", minLength: 1, maxLength: 80 },
              },
              ["run_id", "artifact_id", "role"],
            ),
            description: "Exact completed same-engagement artifact references.",
          },
          label: { type: "string", minLength: 1, maxLength: 160 },
          purpose: { type: "string", minLength: 1, maxLength: 500 },
          idempotency_key: { type: "string", minLength: 1, maxLength: 200 },
          new_run: {
            type: "boolean",
            description: "True only when the user explicitly requests a separate run. Reuse the same idempotency_key for safe retries and choose a new key for another distinct run.",
          },
        },
        ["engagement_id", "workflow_id"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.startWorkflow,
      title: "Start a Vera workflow run",
      description:
        "Move one exact prepared or failed run to running after its input receipts still validate.",
      inputSchema: runIdentitySchema(),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.startCheckEntriesFromSample,
      title: "Start Check Entries from a completed sample",
      description:
        "Resolve and validate the complete internal Journal Sampling handoff, then prepare and start Check Entries against the selected support batch. The caller selects the sampling run and support inputs; no internal filenames or artifact IDs are required.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
          sample_run_id: { type: "string", pattern: "^run_[0-9a-f]{24}$" },
          support_input_ids: {
            type: "array",
            minItems: 1,
            maxItems: 10000,
            uniqueItems: true,
            items: { type: "string", pattern: "^input_[0-9a-f]{24}$" },
          },
          label: { type: "string", minLength: 1, maxLength: 160 },
          purpose: { type: "string", minLength: 1, maxLength: 500 },
          idempotency_key: { type: "string", minLength: 1, maxLength: 200 },
          new_run: { type: "boolean" },
        },
        ["client_id", "engagement_id", "sample_run_id", "support_input_ids"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.failWorkflow,
      title: "Record a Vera workflow failure",
      description:
        "Retain a failed run and record a bounded reason instead of treating its output folder as available.",
      inputSchema: objectSchema(
        {
          ...runIdentityProperties(),
          reason: { type: "string", minLength: 1, maxLength: 1000 },
        },
        ["client_id", "engagement_id", "run_id", "reason"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.cancelWorkflow,
      title: "Cancel a Vera workflow run",
      description: "Explicitly cancel one abandoned non-terminal run without deleting it.",
      inputSchema: runIdentitySchema(),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.finalizeWorkflow,
      title: "Finalize Vera workflow artifacts",
      description:
        "Declare every physical output with its purpose, audience, and media type, hash the closed output tree, and mark the run ready for review.",
      inputSchema: objectSchema(
        {
          ...runIdentityProperties(),
          artifacts: {
            type: "array",
            minItems: 1,
            maxItems: 20000,
            items: objectSchema(
              {
                artifact_id: { type: "string", minLength: 1, maxLength: 120 },
                path: { type: "string", minLength: 1, maxLength: 4096 },
                purpose: { type: "string", minLength: 1, maxLength: 500 },
                audience: {
                  type: "string",
                  enum: ["internal", "review", "deliverable"],
                },
                media_type: { type: "string", minLength: 1, maxLength: 160 },
              },
              ["artifact_id", "path", "purpose", "audience", "media_type"],
            ),
          },
        },
        ["client_id", "engagement_id", "run_id", "artifacts"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.completeWorkflow,
      title: "Complete a Vera workflow run",
      description:
        "Mark a review-ready run completed only while every declared artifact still matches its receipt.",
      inputSchema: runIdentitySchema(),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.closeEngagement,
      title: "Close a Studio client engagement",
      description:
        "Close one engagement only after all prepared, running, or review-ready runs are completed or cancelled.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          engagement_id: { type: "string", pattern: "^eng_[0-9a-f]{24}$" },
        },
        ["client_id", "engagement_id"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.recoverLedger,
      title: "Recover Vera customer-folder ledger",
      description:
        "Rebuild private client pointers from portable customer manifests and verify all engagement, input, and run records.",
      inputSchema: objectSchema({}),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.retentionReport,
      title: "Review Vera retention candidates",
      description:
        "Build a non-destructive size, age, and lifecycle report. This tool never deletes customer files.",
      inputSchema: objectSchema(
        {
          client_id: { type: "string", pattern: "^client_[0-9a-f]{24}$" },
          older_than_days: { type: "integer", minimum: 0, maximum: 365000 },
        },
        ["client_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.setup,
      title: "Set up Vera Studio Archive",
      description:
        "Open the operating system's native folder chooser, diagnose the selected shared archive folder, and save this user's private local configuration. Use this guided action before asking the user to type an absolute path.",
      inputSchema: objectSchema({}),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.diagnoseAccess,
      title: "Diagnose Studio Archive access",
      description:
        "Check path resolution and root listing without persisting configuration. Returns path-safe categories for host sandbox denial, SMB session or credential errors, share reachability, and share/filesystem permissions.",
      inputSchema: objectSchema(
        {
          archive_root: {
            type: "string",
            minLength: 1,
            maxLength: 4096,
            description:
              "Absolute local, mounted, or native Windows UNC path selected for the shared studio archive.",
          },
        },
        ["archive_root"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.configure,
      title: "Configure Vera Studio Archive",
      description:
        "Set one absolute shared archive folder for this user. This writes only a private local configuration and discovers exact top-level search scopes.",
      inputSchema: objectSchema(
        {
          archive_root: {
            type: "string",
            minLength: 1,
            maxLength: 4096,
            description:
              "Absolute path to the shared or synced studio archive folder.",
          },
        },
        ["archive_root"],
      ),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.refresh,
      title: "Refresh Vera Studio Archive",
      description:
        "Hash every supported source, incrementally update this user's private local full-text index, adopt top-level scope changes, and report skipped or partially extracted documents. Source files are read but never modified. OCR is local-only and never downloads model weights.",
      inputSchema: objectSchema({
        rebuild: {
          type: "boolean",
          description: "Discard and rebuild the derived local index.",
        },
        enable_ocr: {
          type: "boolean",
          description:
            "Try already-installed local OCR for scans and sparse PDF pages.",
        },
      }),
      annotations: annotations(false),
    },
    {
      name: TOOL_NAMES.search,
      title: "Search Vera Studio Archive",
      description:
        "Search one exact configured scope. Use scope_id='all' only when the user explicitly requests a studio-wide search. Results are candidates and must be opened before citation.",
      inputSchema: objectSchema(
        {
          query: {
            type: "string",
            minLength: 1,
            maxLength: 500,
            description: "Compact lexical query; Claude may issue several variants.",
          },
          scope_id: {
            type: "string",
            pattern: "^(?:all|scope_[0-9a-f]{24})$",
            description:
              "Exact scope_id returned by studio_archive_status, or all after explicit user intent.",
          },
          limit: {
            type: "integer",
            minimum: 1,
            maximum: 20,
            description: "Maximum candidate chunks; defaults to 10.",
          },
        },
        ["query", "scope_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.open,
      title: "Open and verify a Studio Archive source",
      description:
        "Open one search result by opaque source_id, re-hash the current file, and return its citable text and locator. Fails if the source changed after indexing.",
      inputSchema: objectSchema(
        {
          source_id: {
            type: "string",
            pattern: "^src_[0-9a-f]{24}$",
            description: "Opaque source_id returned by search_studio_archive.",
          },
          context_chunks: {
            type: "integer",
            minimum: 0,
            maximum: 2,
            description: "Adjacent chunks on each side; defaults to 0.",
          },
        },
        ["source_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.configureClient,
      title: "Register one existing Studio Archive client",
      description:
        "Assign a stable client ID and bind confirmed legal names, full email addresses, and tax identifiers to one exact existing archive scope in the private local registry. Vera stores no Gmail credentials, messages, or attachments.",
      inputSchema: objectSchema(
        {
          scope_id: {
            type: "string",
            pattern: "^scope_[0-9a-f]{24}$",
            description:
              "Exact client scope_id returned by studio_archive_status.",
          },
          email_addresses: {
            type: "array",
            maxItems: 20,
            items: { type: "string", minLength: 3, maxLength: 254 },
            description:
              "Confirmed full email or PEC addresses unique to this client.",
          },
          legal_names: {
            type: "array",
            maxItems: 20,
            items: { type: "string", minLength: 1, maxLength: 160 },
            description:
              "Confirmed legal names used only to find candidates, never for automatic routing.",
          },
          tax_identifiers: {
            type: "array",
            maxItems: 20,
            items: { type: "string", minLength: 5, maxLength: 32 },
            description:
              "Confirmed codice fiscale or partita IVA values used to find candidates.",
          },
          replace_orphaned_scope_id: {
            type: "string",
            pattern: "^scope_[0-9a-f]{24}$",
            description:
              "Explicitly move one listed orphaned profile to this target scope. Supply no identity arrays in the same call.",
          },
        },
        ["scope_id"],
      ),
      annotations: annotations(false, false),
    },
    {
      name: TOOL_NAMES.planGmail,
      title: "Plan a client-scoped Gmail search",
      description:
        "Return bounded Gmail-native queries for one exact client scope. This local tool does not call Gmail; Claude must use the connected Gmail search/read tools and review every shortlisted message.",
      inputSchema: objectSchema(
        {
          scope_id: {
            type: "string",
            pattern: "^scope_[0-9a-f]{24}$",
            description:
              "Exact client scope_id; studio-wide Gmail search is not supported.",
          },
          topic: {
            type: "string",
            minLength: 1,
            maxLength: 200,
            description: "Optional compact topic phrase from the user's question.",
          },
          after: {
            type: "string",
            pattern: "^\\d{4}-\\d{2}-\\d{2}$",
            description: "Optional inclusive lower date bound in YYYY-MM-DD.",
          },
          before: {
            type: "string",
            pattern: "^\\d{4}-\\d{2}-\\d{2}$",
            description: "Optional exclusive upper date bound in YYYY-MM-DD.",
          },
        },
        ["scope_id"],
      ),
      annotations: annotations(true),
    },
    {
      name: TOOL_NAMES.matchEmail,
      title: "Match Gmail headers to a Studio Archive client",
      description:
        "Match all available Gmail From, To, Cc, and Bcc header values only against unique confirmed full addresses. Missing, incomplete, or unparseable headers fail closed.",
      inputSchema: objectSchema(
        {
          header_addresses: {
            type: "array",
            minItems: 1,
            maxItems: 100,
            items: { type: "string", minLength: 1, maxLength: 2000 },
            description:
              "Raw address values copied from Gmail message headers.",
          },
          headers_complete: {
            type: "boolean",
            description:
              "True only after the full message read exposed all available From, To, Cc, and Bcc fields and every non-empty value was supplied.",
          },
          expected_scope_id: {
            type: "string",
            pattern: "^scope_[0-9a-f]{24}$",
            description:
              "Optional selected client scope used for the fail-closed answer check.",
          },
        },
        ["header_addresses", "headers_complete"],
      ),
      annotations: annotations(true),
    },
  ];
}

function pythonExecutable() {
  const candidates = [
    process.env.VERA_STUDIO_ARCHIVE_PYTHON,
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

function requirePlainObject(value) {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Tool arguments must be an object.");
  }
  return value;
}

function requireString(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} must be a non-empty string.`);
  }
  return value;
}

function assertOnlyKeys(args, allowed) {
  const unknown = Object.keys(args).filter((key) => !allowed.has(key));
  if (unknown.length) {
    throw new Error(`Unknown tool argument: ${unknown.join(", ")}.`);
  }
}

function optionalInteger(value, name, minimum, maximum) {
  if (value === undefined) return null;
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${maximum}.`);
  }
  return value;
}

function optionalBoolean(value, name) {
  if (value === undefined) return false;
  if (typeof value !== "boolean") throw new Error(`${name} must be a boolean.`);
  return value;
}

function requireBoolean(value, name) {
  if (typeof value !== "boolean") throw new Error(`${name} must be a boolean.`);
  return value;
}

function optionalString(value, name, maximum) {
  if (value === undefined) return null;
  if (
    typeof value !== "string" ||
    value.trim() === "" ||
    value.length > maximum
  ) {
    throw new Error(`${name} must be a non-empty string of at most ${maximum} characters.`);
  }
  return value;
}

function optionalStringArray(value, name, maximumItems, maximumLength) {
  if (value === undefined) return [];
  if (
    !Array.isArray(value) ||
    value.length > maximumItems ||
    value.some(
      (item) =>
        typeof item !== "string" ||
        item.trim() === "" ||
        item.length > maximumLength,
    )
  ) {
    throw new Error(
      `${name} must contain at most ${maximumItems} bounded strings.`,
    );
  }
  return value;
}

function runIdentityCommand(args, commandName, extraKeys = []) {
  assertOnlyKeys(
    args,
    new Set(["client_id", "engagement_id", "run_id", ...extraKeys]),
  );
  const clientId = requireString(args.client_id, "client_id");
  const engagementId = requireString(args.engagement_id, "engagement_id");
  const runId = requireString(args.run_id, "run_id");
  if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
    throw new Error("client_id is invalid.");
  }
  if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
    throw new Error("engagement_id is invalid.");
  }
  if (!/^run_[0-9a-f]{24}$/.test(runId)) {
    throw new Error("run_id is invalid.");
  }
  return [
    commandName,
    "--client-id",
    clientId,
    "--engagement-id",
    engagementId,
    "--run-id",
    runId,
  ];
}

function commandForTool(name, rawArgs) {
  const args = requirePlainObject(rawArgs);
  if (name === TOOL_NAMES.status) {
    assertOnlyKeys(args, new Set());
    return ["status"];
  }
  if (name === TOOL_NAMES.clients) {
    assertOnlyKeys(args, new Set());
    return ["clients"];
  }
  if (name === TOOL_NAMES.resolveClient) {
    assertOnlyKeys(args, new Set(["identity_kind", "identity_value"]));
    const identityKind = requireString(args.identity_kind, "identity_kind");
    if (!/^(?:email_address|legal_name|tax_identifier)$/.test(identityKind)) {
      throw new Error("identity_kind is invalid.");
    }
    return [
      "resolve-client",
      "--identity-kind",
      identityKind,
      "--identity-value",
      requireString(args.identity_value, "identity_value"),
    ];
  }
  if (name === TOOL_NAMES.clientFolder) {
    assertOnlyKeys(args, new Set(["client_id"]));
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    return ["client-folder", "--client-id", clientId];
  }
  if (name === TOOL_NAMES.createClient) {
    assertOnlyKeys(
      args,
      new Set(["legal_name", "email_addresses", "tax_identifiers"]),
    );
    const command = [
      "create-client",
      "--legal-name",
      requireString(args.legal_name, "legal_name"),
    ];
    for (const value of optionalStringArray(
      args.email_addresses,
      "email_addresses",
      20,
      254,
    )) {
      command.push("--email-address", value);
    }
    for (const value of optionalStringArray(
      args.tax_identifiers,
      "tax_identifiers",
      20,
      32,
    )) {
      command.push("--tax-identifier", value);
    }
    return command;
  }
  if (name === TOOL_NAMES.importDocument) {
    assertOnlyKeys(
      args,
      new Set([
        "client_id",
        "source_path",
        "role",
        "engagement_id",
      ]),
    );
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    const role = requireString(args.role, "role");
    if (!/^(?:journal|source|support)$/.test(role)) {
      throw new Error("role must be journal, source, or support.");
    }
    const command = [
      "import-document",
      "--client-id",
      clientId,
      "--source-path",
      requireString(args.source_path, "source_path"),
      "--role",
      role,
    ];
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    command.push("--engagement-id", engagementId);
    return command;
  }
  if (name === TOOL_NAMES.createEngagement) {
    assertOnlyKeys(args, new Set(["client_id", "engagement_label"]));
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    return [
      "create-engagement",
      "--client-id",
      clientId,
      "--engagement-label",
      requireString(args.engagement_label, "engagement_label"),
    ];
  }
  if (name === TOOL_NAMES.snapshotFolder) {
    assertOnlyKeys(args, new Set(["client_id", "engagement_id"]));
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    return [
      "snapshot-client-folder",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
    ];
  }
  if (name === TOOL_NAMES.googleDriveStatus) {
    assertOnlyKeys(args, new Set());
    return ["google-drive-status"];
  }
  if (name === TOOL_NAMES.bindGoogleDrive) {
    assertOnlyKeys(args, new Set(["client_id", "folder_id"]));
    const clientId = requireString(args.client_id, "client_id");
    const folderId = requireString(args.folder_id, "folder_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^[A-Za-z0-9_-]{3,256}$/.test(folderId)) {
      throw new Error("folder_id must be an exact Google Drive folder ID.");
    }
    return ["bind-google-drive", "--client-id", clientId, "--folder-id", folderId];
  }
  if (name === TOOL_NAMES.snapshotGoogleDrive) {
    assertOnlyKeys(args, new Set(["client_id", "engagement_id"]));
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    return [
      "snapshot-google-drive",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
    ];
  }
  if (name === TOOL_NAMES.archiveInventory) {
    assertOnlyKeys(
      args,
      new Set(["client_id", "engagement_id", "snapshot_input_id"]),
    );
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    const inputId = requireString(args.snapshot_input_id, "snapshot_input_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    if (!/^input_[0-9a-f]{24}$/.test(inputId)) {
      throw new Error("snapshot_input_id is invalid.");
    }
    return [
      "archive-organization-inventory",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
      "--snapshot-input-id",
      inputId,
    ];
  }
  if (name === TOOL_NAMES.openArchiveItem) {
    assertOnlyKeys(
      args,
      new Set(["client_id", "engagement_id", "snapshot_input_id", "item_ref"]),
    );
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    const inputId = requireString(args.snapshot_input_id, "snapshot_input_id");
    const itemRef = requireString(args.item_ref, "item_ref");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    if (!/^input_[0-9a-f]{24}$/.test(inputId)) {
      throw new Error("snapshot_input_id is invalid.");
    }
    if (!/^archive_item_[0-9a-f]{24}$/.test(itemRef)) {
      throw new Error("item_ref is invalid.");
    }
    return [
      "open-archive-organization-item",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
      "--snapshot-input-id",
      inputId,
      "--item-ref",
      itemRef,
    ];
  }
  if (name === TOOL_NAMES.engagements) {
    assertOnlyKeys(args, new Set(["client_id"]));
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    return ["engagements", "--client-id", clientId];
  }
  if (name === TOOL_NAMES.prepareWorkflow) {
    assertOnlyKeys(
      args,
      new Set([
        "engagement_id",
        "workflow_id",
        "input_ids",
        "upstream_artifacts",
        "label",
        "purpose",
        "idempotency_key",
        "new_run",
      ]),
    );
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    const workflowId = requireString(args.workflow_id, "workflow_id");
    if (!CLIENT_WORKFLOW_IDS.includes(workflowId)) {
      throw new Error("workflow_id is unsupported.");
    }
    const command = [
      "prepare-workflow",
      "--engagement-id",
      engagementId,
      "--workflow-id",
      workflowId,
    ];
    for (const inputId of optionalStringArray(
      args.input_ids,
      "input_ids",
      10000,
      30,
    )) {
      if (!/^input_[0-9a-f]{24}$/.test(inputId)) {
        throw new Error("input_ids contains an invalid input ID.");
      }
      command.push("--input-id", inputId);
    }
    const upstream = args.upstream_artifacts ?? [];
    if (!Array.isArray(upstream) || upstream.length > 10000) {
      throw new Error("upstream_artifacts must be a bounded array.");
    }
    for (const reference of upstream) {
      const value = requirePlainObject(reference);
      assertOnlyKeys(value, new Set(["run_id", "artifact_id", "role"]));
      const runId = requireString(value.run_id, "upstream run_id");
      const artifactId = requireString(value.artifact_id, "artifact_id");
      const role = requireString(value.role, "upstream role");
      if (!/^run_[0-9a-f]{24}$/.test(runId)) {
        throw new Error("upstream run_id is invalid.");
      }
      if (artifactId.includes(":") || role.includes(":")) {
        throw new Error("artifact_id and role cannot contain a colon.");
      }
      command.push("--upstream-artifact", `${runId}:${artifactId}:${role}`);
    }
    for (const [key, flag, maximum] of [
      ["label", "--label", 160],
      ["purpose", "--purpose", 500],
      ["idempotency_key", "--idempotency-key", 200],
    ]) {
      const value = optionalString(args[key], key, maximum);
      if (value !== null) command.push(flag, value);
    }
    if (optionalBoolean(args.new_run, "new_run")) command.push("--new-run");
    return command;
  }
  if (name === TOOL_NAMES.startWorkflow) {
    return runIdentityCommand(args, "start-workflow");
  }
  if (name === TOOL_NAMES.startCheckEntriesFromSample) {
    assertOnlyKeys(
      args,
      new Set([
        "client_id",
        "engagement_id",
        "sample_run_id",
        "support_input_ids",
        "label",
        "purpose",
        "idempotency_key",
        "new_run",
      ]),
    );
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    const sampleRunId = requireString(args.sample_run_id, "sample_run_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    if (!/^run_[0-9a-f]{24}$/.test(sampleRunId)) {
      throw new Error("sample_run_id is invalid.");
    }
    const supportInputIds = optionalStringArray(
      args.support_input_ids,
      "support_input_ids",
      10000,
      30,
    );
    if (supportInputIds.length < 1 || new Set(supportInputIds).size !== supportInputIds.length) {
      throw new Error("support_input_ids must be a non-empty unique array.");
    }
    const command = [
      "start-check-entries-from-sample",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
      "--sample-run-id",
      sampleRunId,
    ];
    for (const inputId of supportInputIds) {
      if (!/^input_[0-9a-f]{24}$/.test(inputId)) {
        throw new Error("support_input_ids contains an invalid input ID.");
      }
      command.push("--support-input-id", inputId);
    }
    for (const [key, flag, maximum] of [
      ["label", "--label", 160],
      ["purpose", "--purpose", 500],
      ["idempotency_key", "--idempotency-key", 200],
    ]) {
      const value = optionalString(args[key], key, maximum);
      if (value !== null) command.push(flag, value);
    }
    if (optionalBoolean(args.new_run, "new_run")) command.push("--new-run");
    return command;
  }
  if (name === TOOL_NAMES.failWorkflow) {
    const command = runIdentityCommand(args, "fail-workflow", ["reason"]);
    command.push("--reason", requireString(args.reason, "reason"));
    return command;
  }
  if (name === TOOL_NAMES.cancelWorkflow) {
    return runIdentityCommand(args, "cancel-workflow");
  }
  if (name === TOOL_NAMES.finalizeWorkflow) {
    const command = runIdentityCommand(args, "finalize-workflow", ["artifacts"]);
    if (
      !Array.isArray(args.artifacts) ||
      args.artifacts.length < 1 ||
      args.artifacts.length > 20000
    ) {
      throw new Error("artifacts must be a non-empty bounded array.");
    }
    for (const rawArtifact of args.artifacts) {
      const artifact = requirePlainObject(rawArtifact);
      assertOnlyKeys(
        artifact,
        new Set(["artifact_id", "path", "purpose", "audience", "media_type"]),
      );
      requireString(artifact.artifact_id, "artifact_id");
      requireString(artifact.path, "artifact path");
      requireString(artifact.purpose, "artifact purpose");
      if (!new Set(["internal", "review", "deliverable"]).has(artifact.audience)) {
        throw new Error("artifact audience is invalid.");
      }
      requireString(artifact.media_type, "artifact media_type");
    }
    command.push("--artifacts-json", JSON.stringify(args.artifacts));
    return command;
  }
  if (name === TOOL_NAMES.completeWorkflow) {
    return runIdentityCommand(args, "complete-workflow");
  }
  if (name === TOOL_NAMES.closeEngagement) {
    assertOnlyKeys(args, new Set(["client_id", "engagement_id"]));
    const clientId = requireString(args.client_id, "client_id");
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id is invalid.");
    }
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    return [
      "close-engagement",
      "--client-id",
      clientId,
      "--engagement-id",
      engagementId,
    ];
  }
  if (name === TOOL_NAMES.recoverLedger) {
    assertOnlyKeys(args, new Set());
    return ["recover-ledger"];
  }
  if (name === TOOL_NAMES.retentionReport) {
    assertOnlyKeys(args, new Set(["client_id", "older_than_days"]));
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id is invalid.");
    }
    const command = ["retention-report", "--client-id", clientId];
    const days = optionalInteger(
      args.older_than_days,
      "older_than_days",
      0,
      365000,
    );
    if (days !== null) command.push("--older-than-days", String(days));
    return command;
  }
  if (name === TOOL_NAMES.setup) {
    assertOnlyKeys(args, new Set());
    return ["setup"];
  }
  if (name === TOOL_NAMES.configure) {
    assertOnlyKeys(args, new Set(["archive_root"]));
    return [
      "configure",
      "--archive-root",
      requireString(args.archive_root, "archive_root"),
    ];
  }
  if (name === TOOL_NAMES.diagnoseAccess) {
    assertOnlyKeys(args, new Set(["archive_root"]));
    return [
      "diagnose-access",
      "--archive-root",
      requireString(args.archive_root, "archive_root"),
    ];
  }
  if (name === TOOL_NAMES.refresh) {
    assertOnlyKeys(args, new Set(["rebuild", "enable_ocr"]));
    const command = ["refresh"];
    if (optionalBoolean(args.rebuild, "rebuild")) command.push("--rebuild");
    if (optionalBoolean(args.enable_ocr, "enable_ocr")) {
      command.push("--enable-ocr");
    }
    return command;
  }
  if (name === TOOL_NAMES.search) {
    assertOnlyKeys(args, new Set(["query", "scope_id", "limit"]));
    const query = requireString(args.query, "query");
    const scopeId = requireString(args.scope_id, "scope_id");
    if (!/^(?:all|scope_[0-9a-f]{24})$/.test(scopeId)) {
      throw new Error("scope_id must be an exact configured scope or all.");
    }
    const limit = optionalInteger(args.limit, "limit", 1, 20) ?? 10;
    return [
      "search",
      "--query",
      query,
      "--scope-id",
      scopeId,
      "--limit",
      String(limit),
    ];
  }
  if (name === TOOL_NAMES.open) {
    assertOnlyKeys(args, new Set(["source_id", "context_chunks"]));
    const sourceId = requireString(args.source_id, "source_id");
    if (!/^src_[0-9a-f]{24}$/.test(sourceId)) {
      throw new Error("source_id is invalid.");
    }
    const context = optionalInteger(
      args.context_chunks,
      "context_chunks",
      0,
      2,
    ) ?? 0;
    return [
      "open",
      "--source-id",
      sourceId,
      "--context-chunks",
      String(context),
    ];
  }
  if (name === TOOL_NAMES.configureClient) {
    assertOnlyKeys(
      args,
      new Set([
        "scope_id",
        "email_addresses",
        "legal_names",
        "tax_identifiers",
        "replace_orphaned_scope_id",
      ]),
    );
    const scopeId = requireString(args.scope_id, "scope_id");
    if (!/^scope_[0-9a-f]{24}$/.test(scopeId)) {
      throw new Error("scope_id must be an exact configured client scope.");
    }
    const command = ["configure-client", "--scope-id", scopeId];
    const emails = optionalStringArray(
      args.email_addresses,
      "email_addresses",
      20,
      254,
    );
    const legalNames = optionalStringArray(
      args.legal_names,
      "legal_names",
      20,
      160,
    );
    const taxIdentifiers = optionalStringArray(
      args.tax_identifiers,
      "tax_identifiers",
      20,
      32,
    );
    for (const value of emails) command.push("--email-address", value);
    for (const value of legalNames) command.push("--legal-name", value);
    for (const value of taxIdentifiers) {
      command.push("--tax-identifier", value);
    }
    const replaceOrphanedScopeId = optionalString(
      args.replace_orphaned_scope_id,
      "replace_orphaned_scope_id",
      30,
    );
    if (
      replaceOrphanedScopeId !== null &&
      !/^scope_[0-9a-f]{24}$/.test(replaceOrphanedScopeId)
    ) {
      throw new Error(
        "replace_orphaned_scope_id must be an exact listed orphaned scope.",
      );
    }
    if (replaceOrphanedScopeId !== null) {
      command.push("--replace-orphaned-scope-id", replaceOrphanedScopeId);
    }
    return command;
  }
  if (name === TOOL_NAMES.planGmail) {
    assertOnlyKeys(args, new Set(["scope_id", "topic", "after", "before"]));
    const scopeId = requireString(args.scope_id, "scope_id");
    if (!/^scope_[0-9a-f]{24}$/.test(scopeId)) {
      throw new Error("scope_id must be an exact configured client scope.");
    }
    const command = ["plan-gmail", "--scope-id", scopeId];
    const topic = optionalString(args.topic, "topic", 200);
    const after = optionalString(args.after, "after", 10);
    const before = optionalString(args.before, "before", 10);
    if (topic !== null) command.push("--topic", topic);
    if (after !== null) command.push("--after", after);
    if (before !== null) command.push("--before", before);
    return command;
  }
  if (name === TOOL_NAMES.matchEmail) {
    assertOnlyKeys(
      args,
      new Set([
        "header_addresses",
        "headers_complete",
        "expected_scope_id",
      ]),
    );
    const headers = optionalStringArray(
      args.header_addresses,
      "header_addresses",
      100,
      2000,
    );
    if (!headers.length) {
      throw new Error("header_addresses must contain at least one value.");
    }
    const headersComplete = requireBoolean(
      args.headers_complete,
      "headers_complete",
    );
    const expectedScopeId = optionalString(
      args.expected_scope_id,
      "expected_scope_id",
      30,
    );
    if (
      expectedScopeId !== null &&
      !/^scope_[0-9a-f]{24}$/.test(expectedScopeId)
    ) {
      throw new Error("expected_scope_id must be an exact configured scope.");
    }
    const command = ["match-email"];
    for (const value of headers) command.push("--header-address", value);
    if (headersComplete) command.push("--headers-complete");
    if (expectedScopeId !== null) {
      command.push("--expected-scope-id", expectedScopeId);
    }
    return command;
  }
  throw new Error("Unknown Studio Archive tool.");
}

function callTool(name, args) {
  const spawnOptions = {
    cwd: PLUGIN_ROOT,
    encoding: "utf8",
    maxBuffer: MAX_OUTPUT_BYTES,
  };
  if (name !== TOOL_NAMES.refresh) {
    spawnOptions.timeout = 300_000;
  }
  const completed = spawnSync(
    pythonExecutable(),
    [CLI_PATH, ...commandForTool(name, args)],
    spawnOptions,
  );
  if (completed.error) throw completed.error;
  const lines = String(completed.stdout || "")
    .trim()
    .split(/\r?\n/)
    .filter(Boolean);
  let payload = null;
  if (lines.length) {
    try {
      payload = JSON.parse(lines.at(-1));
    } catch {
      throw new Error("Studio Archive returned invalid JSON.");
    }
  }
  if (completed.status !== 0 || payload?.error) {
    const detail =
      payload?.error?.message ||
      String(completed.stderr || "").trim() ||
      "Studio Archive operation failed.";
    const error = new Error(detail);
    error.code = payload?.error?.code || "archive_operation_failed";
    if (
      payload?.error?.details &&
      typeof payload.error.details === "object" &&
      !Array.isArray(payload.error.details)
    ) {
      error.details = payload.error.details;
    }
    throw error;
  }
  if (payload == null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Studio Archive returned no structured result.");
  }
  return payload;
}

function toolResult(payload) {
  return {
    content: [
      {
        type: "text",
        text: "Studio Archive returned the structured result attached to this tool response.",
      },
    ],
    structuredContent: payload,
    isError: false,
  };
}

function toolError(error) {
  const details =
    error &&
    error.details &&
    typeof error.details === "object" &&
    !Array.isArray(error.details)
      ? error.details
      : null;
  const payload = {
    ok: false,
    error: {
      code:
        error && typeof error.code === "string"
          ? error.code
          : "archive_operation_failed",
      message: error instanceof Error ? error.message : String(error),
      ...(details === null ? {} : { details }),
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
  const params =
    message.params && typeof message.params === "object" ? message.params : {};
  if (message.method === "initialize") {
    return rpcResult(id, {
      protocolVersion: params.protocolVersion || "2024-11-05",
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      capabilities: { tools: {} },
      instructions:
        "For client work, list the safe registered-client directory first. If it returns configured=false and setup_required=true, tell the user that the native folder chooser will open and call setup_studio_archive before requesting an absolute path manually. Use the manual diagnose/configure fallback only when the guided tool reports archive_folder_picker_unavailable. Ask the user to choose Existing or New when no exact client is established. Resolve a user-supplied identity through the exact local resolver; never infer identity from a filename. Register a confirmed existing scope or create a new client, obtain its stable client ID, and import files only after the user authorizes the copy. Archive Organization uses the complete projected inventory and opaque item references; raw hashes, storage IDs, capabilities, and absolute paths remain local. Search one exact archive scope and open every file result used as evidence. For Gmail, use the connected Gmail read tools and fail closed on ambiguous routing.",
    });
  }
  if (message.method === "notifications/initialized") return null;
  if (message.method === "tools/list") {
    return rpcResult(id, { tools: toolDefinitions() });
  }
  if (message.method === "tools/call") {
    if (typeof params.name !== "string") {
      return rpcError(id, -32602, "tools/call requires a tool name");
    }
    if (
      params.arguments == null ||
      typeof params.arguments !== "object" ||
      Array.isArray(params.arguments)
    ) {
      return rpcError(id, -32602, "tools/call arguments must be an object");
    }
    try {
      return rpcResult(id, toolResult(callTool(params.name, params.arguments)));
    } catch (error) {
      return rpcResult(id, toolError(error));
    }
  }
  if (message.method === "resources/list") {
    return rpcResult(id, { resources: [] });
  }
  if (message.method === "resources/templates/list") {
    return rpcResult(id, { resourceTemplates: [] });
  }
  if (message.method === "prompts/list") {
    return rpcResult(id, { prompts: [] });
  }
  return rpcError(id, -32601, "method not found");
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function main() {
  const lines = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });
  lines.on("line", (line) => {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      send(rpcError(null, -32700, "parse error"));
      return;
    }
    if (
      message == null ||
      typeof message !== "object" ||
      Array.isArray(message)
    ) {
      send(rpcError(null, -32600, "invalid request"));
      return;
    }
    const response = handleRpc(message);
    if (response !== null && message.id != null) send(response);
  });
}

main();

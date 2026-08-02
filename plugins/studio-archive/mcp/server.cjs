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
  clientFolder: "get_studio_client_folder",
  createClient: "create_studio_archive_client",
  importDocument: "import_studio_client_document",
  engagements: "list_studio_client_engagements",
  prepareWorkflow: "prepare_studio_client_workflow",
  configure: "configure_studio_archive",
  refresh: "refresh_studio_archive",
  search: "search_studio_archive",
  open: "open_studio_archive_source",
  configureClient: "configure_studio_archive_client",
  planGmail: "plan_studio_archive_gmail_search",
  matchEmail: "match_studio_archive_email",
};

function objectSchema(properties, required = []) {
  return {
    type: "object",
    properties,
    required,
    additionalProperties: false,
  };
}

function annotations(readOnly, idempotent = true) {
  return {
    readOnlyHint: readOnly,
    destructiveHint: false,
    idempotentHint: idempotent,
    openWorldHint: false,
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
      title: "List Studio Archive client identities",
      description:
        "Read the private client identity profiles for current scopes and report orphaned profiles after folder changes. Call this before an explicit profile rebind.",
      inputSchema: objectSchema({}),
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
        "After the user confirms the exact client and copy action, preserve the original file, copy one regular file into a managed client engagement, receipt its bytes, and return the next client-bound workflow context.",
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
            description: "Absolute path to the user-selected journal or support file.",
          },
          role: {
            type: "string",
            enum: ["journal", "support"],
          },
          engagement_id: {
            type: "string",
            pattern: "^eng_[0-9a-f]{24}$",
            description: "Required for support; omit for the first journal import.",
          },
          engagement_label: {
            type: "string",
            minLength: 1,
            maxLength: 160,
          },
        },
        ["client_id", "source_path", "role"],
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
        "Create and persist the only permitted run context and output path for Journal Sampling, Check Entries, or Audit Reconciliation under one existing engagement.",
      inputSchema: objectSchema(
        {
          engagement_id: {
            type: "string",
            pattern: "^eng_[0-9a-f]{24}$",
          },
          workflow_id: {
            type: "string",
            enum: ["journal-sampling", "check-entries", "audit-reconciliation"],
          },
        },
        ["engagement_id", "workflow_id"],
      ),
      annotations: annotations(false, false),
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
            description: "Compact lexical query; Codex may issue several variants.",
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
        "Return bounded Gmail-native queries for one exact client scope. This local tool does not call Gmail; Codex must use the connected Gmail search/read tools and review every shortlisted message.",
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
        "engagement_label",
      ]),
    );
    const clientId = requireString(args.client_id, "client_id");
    if (!/^client_[0-9a-f]{24}$/.test(clientId)) {
      throw new Error("client_id must be an exact registered client.");
    }
    const role = requireString(args.role, "role");
    if (!/^(?:journal|support)$/.test(role)) {
      throw new Error("role must be journal or support.");
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
    const engagementId = optionalString(
      args.engagement_id,
      "engagement_id",
      28,
    );
    if (
      engagementId !== null &&
      !/^eng_[0-9a-f]{24}$/.test(engagementId)
    ) {
      throw new Error("engagement_id is invalid.");
    }
    if (engagementId !== null) {
      command.push("--engagement-id", engagementId);
    }
    const label = optionalString(
      args.engagement_label,
      "engagement_label",
      160,
    );
    if (label !== null) command.push("--engagement-label", label);
    return command;
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
    assertOnlyKeys(args, new Set(["engagement_id", "workflow_id"]));
    const engagementId = requireString(args.engagement_id, "engagement_id");
    if (!/^eng_[0-9a-f]{24}$/.test(engagementId)) {
      throw new Error("engagement_id is invalid.");
    }
    const workflowId = requireString(args.workflow_id, "workflow_id");
    if (
      !/^(?:journal-sampling|check-entries|audit-reconciliation)$/.test(
        workflowId,
      )
    ) {
      throw new Error("workflow_id is unsupported.");
    }
    return [
      "prepare-workflow",
      "--engagement-id",
      engagementId,
      "--workflow-id",
      workflowId,
    ];
  }
  if (name === TOOL_NAMES.configure) {
    assertOnlyKeys(args, new Set(["archive_root"]));
    return [
      "configure",
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
    throw error;
  }
  if (payload == null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Studio Archive returned no structured result.");
  }
  return payload;
}

function toolResult(payload) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError: false,
  };
}

function toolError(error) {
  const payload = {
    ok: false,
    error: {
      code:
        error && typeof error.code === "string"
          ? error.code
          : "archive_operation_failed",
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
  const params =
    message.params && typeof message.params === "object" ? message.params : {};
  if (message.method === "initialize") {
    return rpcResult(id, {
      protocolVersion: params.protocolVersion || "2024-11-05",
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      capabilities: { tools: {} },
      instructions:
        "For client work, list registered clients first and ask the user to choose Existing or New when no exact client is established. Never infer identity from a filename. Register a confirmed existing scope or create a new client, obtain its stable client ID, and import files only after the user authorizes the copy. Search one exact archive scope and open every file result used as evidence. For Gmail, use the connected Gmail read tools and fail closed on ambiguous routing.",
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

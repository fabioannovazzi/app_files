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
  configure: "configure_studio_archive",
  refresh: "refresh_studio_archive",
  search: "search_studio_archive",
  open: "open_studio_archive_source",
};

function objectSchema(properties, required = []) {
  return {
    type: "object",
    properties,
    required,
    additionalProperties: false,
  };
}

function annotations(readOnly) {
  return {
    readOnlyHint: readOnly,
    destructiveHint: false,
    idempotentHint: true,
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

function commandForTool(name, rawArgs) {
  const args = requirePlainObject(rawArgs);
  if (name === TOOL_NAMES.status) {
    assertOnlyKeys(args, new Set());
    return ["status"];
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
        "Call studio_archive_status first. Search one exact scope, open every result used as evidence, and refresh when a source changed.",
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

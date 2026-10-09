"use strict";

// Local persistence only. The host calls already-connected Calendar/email tools;
// this server never holds OAuth credentials or sends an external request.
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");
const ROOT = path.resolve(__dirname, "..");
const panel = require("./studio-work-panel.cjs");
const string = { type: "string", minLength: 1, maxLength: 20000 };
const object = { type: "object" };
const revision = { type: "integer", minimum: 0 };
const key = { request_key: string };
const item = { item_id: string, expected_revision: revision };
function definition(action, description, properties, required) {
  return { name: "vera_studio_work_" + action, description,
    inputSchema: { type: "object", additionalProperties: false, properties, required } };
}
const TOOLS = [
  definition("report_workspace", "Create an owner-local output folder for this substantive work's actual model-data report. Does not generate the report or stamp a receipt.", { ...key, label: string }, ["request_key", "label"]),
  definition("settings", "Read studio scheduling preferences before asking setup questions.", {}, []),
  definition("configure", "Persist user-selected timezone, calendar and scheduling preferences. Does not connect accounts or install a scheduler.", { ...key, expected_revision: revision, preferences: object }, ["request_key", "expected_revision", "preferences"]),
  definition("capture", "Persist a model-interpreted commitment with explicit source. No event is created. Same request key/content safely replays.", { ...key, item: object }, ["request_key", "item"]),
  definition("read", "Read a commitment's exact current revision, source, status and calendar link.", { item_id: string }, ["item_id"]),
  definition("change", "Update local work status, owner, notes, deadlines or dependencies at an exact revision. Calendar-linked time/title/cancellation requires the external operation workflow.", { ...key, ...item, patch: object }, ["request_key", "item_id", "expected_revision", "patch"]),
  definition("meeting", "Atomically retain a source-based meeting summary and its follow-up commitments. Never invent decisions, dates or responsible people.", { ...key, meeting: object, actions: { type: "array", maxItems: 100, items: object } }, ["request_key", "meeting"]),
  definition("context", "Read persistent work across chats, overdue/follow-up flags, recent meeting summaries and unresolved calendar operations. Page all items before making a complete briefing. Refresh the external calendar separately.", { day: string, offset: revision, include_closed: { type: "boolean" } }, ["day"]),
  definition("prepare", "Record an authorized ordinary calendar create/update/delete intent. No external write. Invitations/recurrence excluded. One unresolved operation per commitment.", { ...key, ...item, action: { enum: ["create", "update", "delete"] }, event: object, authorization: string }, ["request_key", "item_id", "expected_revision", "action", "event", "authorization"]),
  definition("claim", "Persist dispatch before calling the connected Calendar plugin. Execute ONLY if execute=true. A repeat returns false. A lost response requires recovery, never a blind retry.", { ...key, operation_id: string }, ["request_key", "operation_id"]),
  definition("operation", "Read a persisted external intent/outcome for recovery; this never authorizes redispatch.", { operation_id: string }, ["operation_id"]),
  definition("resolve", "Record real connector read-back evidence, definitive no-write failure or uncertainty. Verification checks exact event fields and identity. This is not independent Google verification: supply actual tool evidence, never fabricate it.", { ...key, operation_id: string, outcome: { enum: ["verified", "failed", "uncertain"] }, evidence: object }, ["request_key", "operation_id", "outcome", "evidence"]),
  definition("abandon", "Cancel an undispatched prepared operation at the user's instruction. Dispatched/uncertain operations require connector recovery.", { ...key, operation_id: string, authorization: string }, ["request_key", "operation_id", "authorization"]),
  ...panel.TOOLS,
];

function bridge(action, args) {
  let python = process.env.VERA_STUDIO_WORK_PYTHON;
  if (!python) {
    const resolved = spawnSync(process.platform === "win32" ? "python" : "python3",
      [path.join(ROOT, "scripts/studio_work_runtime.py")],
      { encoding: "utf8", timeout: 30000 });
    if (resolved.error) throw resolved.error;
    if (resolved.status !== 0) throw new Error("Complete Vera's managed Python setup before using studio work");
    python = resolved.stdout.trim();
  }
  const result = spawnSync(python, [path.join(ROOT, "scripts/studio_work.py")], {
    input: JSON.stringify({ action, arguments: args }), encoding: "utf8",
    timeout: 30000, maxBuffer: 4 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim().split("\n").at(-1) || "Studio work refused the request");
  return JSON.parse(result.stdout);
}

function call(name, args) {
  if (name.startsWith(panel.PREFIX)) return panel.call(name, args);
  const tool = TOOLS.find(candidate => candidate.name === name);
  if (!tool) throw new Error("Unknown studio work tool");
  if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("Arguments must be an object");
  const schema = tool.inputSchema;
  for (const field of schema.required) if (!(field in args)) throw new Error("Missing " + field);
  for (const [field, value] of Object.entries(args)) {
    const rule = schema.properties[field];
    if (!rule) throw new Error("Unknown " + field);
    if (rule.type === "string" && (typeof value !== "string" || !value.trim() || value.length > 20000)) throw new Error("Invalid " + field);
    if (rule.type === "integer" && (!Number.isInteger(value) || value < 0)) throw new Error("Invalid " + field);
    if (rule.type === "boolean" && typeof value !== "boolean") throw new Error("Invalid " + field);
    if (rule.type === "object" && (!value || typeof value !== "object" || Array.isArray(value))) throw new Error("Invalid " + field);
    if (rule.type === "array" && (!Array.isArray(value) || value.length > rule.maxItems || value.some(x => !x || typeof x !== "object" || Array.isArray(x)))) throw new Error("Invalid " + field);
    if (rule.enum && !rule.enum.includes(value)) throw new Error("Invalid " + field);
  }
  return bridge(name.replace("vera_studio_work_", ""), args);
}

function handle(request) {
  if (request.method === "notifications/initialized") return null;
  if (request.method === "initialize") return { protocolVersion: "2024-11-05", capabilities: { tools: {}, resources: {} }, serverInfo: { name: "vera-studio-work", version: "1.0.0" } };
  if (request.method === "ping") return {};
  if (request.method === "tools/list") return { tools: TOOLS };
  if (request.method === "resources/list") return { resources: [{ uri: panel.URI, name: "Organizzazione del lavoro", mimeType: panel.MIME }] };
  if (request.method === "resources/read" && request.params?.uri === panel.URI) return panel.resource();
  if (request.method === "tools/call") {
    try {
      const value = call(request.params.name, request.params.arguments || {});
      if (request.params.name.startsWith(panel.PREFIX)) return value;
      return { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value };
    } catch (error) {
      return { isError: true, content: [{ type: "text", text: error.message }] };
    }
  }
  throw new Error("Unsupported method");
}
if (require.main === module) {
  readline.createInterface({ input: process.stdin }).on("line", line => {
    let request;
    try {
      if (Buffer.byteLength(line) > 1024 * 1024) throw new Error("Oversized request");
      request = JSON.parse(line);
      const result = handle(request);
      if (request.id !== undefined && result !== null) process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: request.id, result }) + "\n");
    } catch (error) {
      process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: request?.id ?? null, error: { code: -32600, message: error.message } }) + "\n");
    }
  });
}
module.exports = { TOOLS, call, handle };

"use strict";

// Local state only; actual WhatsApp UI actions belong to the host Computer Use.
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const PREFIX = "vera_whatsapp_";
const string = { type: "string", minLength: 1, maxLength: 20000 };
const object = { type: "object" };
const key = { request_key: string };
const id = { id: string };
const token = { token: string };
const revision = { expected_revision: { type: "integer", minimum: 0 } };
function definition(action, description, properties, required) {
  return { name: PREFIX + action, description, inputSchema: { type: "object", additionalProperties: false, properties, required } };
}
const TOOLS = [
  definition("context", "Resume this account's local WhatsApp requests, due follow-ups, uncertain sends and pending Archive copies. Page all requests for a complete briefing. No background scheduler or WhatsApp reads.", { account: string, day: string, offset: { type: "integer", minimum: 0 }, include_closed: { type: "boolean" } }, ["account", "day"]),
  definition("read", "Read an exact local binding, request, attachment or send receipt. This does not refresh WhatsApp.", id, ["id"]),
  definition("acquire", "Claim exclusive local WhatsApp UI ownership before any search/read/download/send. On first setup omit account, inspect its profile, then bind the verified account while retaining this token. A stale owner must be reconciled; locks never expire into a duplicate send.", { ...key, account: string, owner: string }, ["request_key", "owner"]),
  definition("release", "Release a completed or recovered UI session using its token and real evidence that UI work ended. Resolve a dispatch as accepted, failed or uncertain first.", { ...key, ...token, evidence: string }, ["request_key", "token", "evidence"]),
  definition("bind", "Retain a user-confirmed client/phone mapping after verifying the selected account and exact phone in the one-to-one contact information UI. Alias can differ from client name. Never invent observation or confirmation.", { ...key, ...token, account: string, phone: string, observed_phone: string, client: string, alias: string, evidence: string, confirmation: string, platform: { enum: ["mac", "windows"] } }, ["request_key", "token", "account", "phone", "observed_phone", "client", "alias", "evidence", "confirmation", "platform"]),
  definition("capture", "Save a document request with title, owner, source, items (id, description, status) and optional engagement/due_date/follow_up_date. Requires an existing verified contact binding. Receiving is distinct from professional checking/completion.", { ...key, binding_id: string, request: object }, ["request_key", "binding_id", "request"]),
  definition("change", "Revise request items, dates, owner or status using the current revision. Received/checked/complete/correction_requested items require source or review evidence. No WhatsApp write.", { ...key, ...id, ...revision, patch: object }, ["request_key", "id", "expected_revision", "patch"]),
  definition("stage", "Copy an explicitly selected local attachment into durable private staging; hash the retained bytes and preserve its message/source locator. Does not download or upload. direction is incoming or outgoing.", { ...key, ...id, path: string, source: string, direction: { enum: ["incoming", "outgoing"] } }, ["request_key", "id", "path", "source", "direction"]),
  definition("archive", "Record actual Archive import receipt (matching sha256) or its failure. Retains staged source and recovery metadata even if Archive fails. Does not import by itself.", { ...key, ...id, status: { enum: ["pending", "failed", "archived"] }, sha256: string, evidence: string }, ["request_key", "id", "status", "evidence"]),
  definition("prepare", "Persist exact recipient, message body, selected staged attachments and specific user send authorization. No UI write; draft in chat first unless that exact send is already authorized. Repeated content returns its existing operation. retry_of permits only a cancelled or definitively unsent operation; repeat_of permits a deliberate repeat of an accepted message. Both require a new specific user instruction.", { ...key, ...id, ...revision, body: { type: "string", maxLength: 20000 }, attachment_ids: { type: "array", items: string }, authorization: string, retry_of: string, repeat_of: string }, ["request_key", "id", "expected_revision", "body", "authorization"]),
  definition("claim", "Record dispatch BEFORE composing or clicking Send, after rechecking the account, exact phone and empty composer in the UI. Execute only when execute=true. Replays return false; interrupted claims require evidence-based recovery, never blind resend.", { ...key, ...id, ...token, observed_phone: string, observed_account: string }, ["request_key", "id", "token", "observed_phone", "observed_account"]),
  definition("resolve", "Record real UI evidence after dispatch: accepted (exact phone/body/attachment_names and locator), failed (definitive_no_send=true), uncertain, or cancelled before dispatch. UI acceptance is separate from delivery/read. Never fabricate evidence.", { ...key, ...id, outcome: { enum: ["accepted", "failed", "uncertain", "cancelled"] }, evidence: object }, ["request_key", "id", "outcome", "evidence"]),
];
function call(name, args) {
  const tool = TOOLS.find(t => t.name === name);
  if (!tool || !args || typeof args !== "object" || Array.isArray(args)) throw new Error("Invalid WhatsApp call");
  for (const field of tool.inputSchema.required) if (!(field in args)) throw new Error("Missing " + field);
  for (const [field, value] of Object.entries(args)) {
    const rule = tool.inputSchema.properties[field];
    if (!rule || (rule.enum && !rule.enum.includes(value))) throw new Error("Invalid " + field);
    if (rule.type === "string" && (typeof value !== "string" || value.length > 20000 || (rule.minLength && !value.trim()))) throw new Error("Invalid " + field);
    if (rule.type === "integer" && (!Number.isInteger(value) || value < 0)) throw new Error("Invalid " + field);
    if (rule.type === "object" && (!value || typeof value !== "object" || Array.isArray(value))) throw new Error("Invalid " + field);
    if (rule.type === "boolean" && typeof value !== "boolean") throw new Error("Invalid " + field);
    if (rule.type === "array" && (!Array.isArray(value) || value.some(x => typeof x !== "string" || !x))) throw new Error("Invalid " + field);
  }
  const root = path.resolve(__dirname, "..");
  // JSON pipes must keep Italian text and emoji intact on non-UTF-8 Windows hosts.
  const env = { ...process.env, PYTHONIOENCODING: "utf-8" };
  let python = process.env.VERA_STUDIO_WORK_PYTHON;
  if (!python) {
    const probe = spawnSync(process.platform === "win32" ? "python" : "python3", [path.join(root, "scripts/studio_work_runtime.py")], { env, encoding: "utf8", timeout: 30000 });
    if (probe.error) throw probe.error;
    if (probe.status !== 0) throw new Error("Complete Vera's managed Python setup before using WhatsApp requests");
    python = probe.stdout.trim();
  }
  const result = spawnSync(python, [path.join(root, "scripts/whatsapp_requests.py")], { env, input: JSON.stringify({ action: name.slice(PREFIX.length), arguments: args }), encoding: "utf8", timeout: 30000, maxBuffer: 4 * 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim().split("\n").at(-1) || "WhatsApp request failed");
  return JSON.parse(result.stdout);
}
module.exports = { PREFIX, TOOLS, call };

"use strict";

// Fixed native operations only. Guest diagnostics and commands are never inputs.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");
const { createHash, randomUUID } = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const manifestPath = fs.existsSync(path.join(ROOT, ".codex-plugin/plugin.json")) ? ".codex-plugin/plugin.json" : ".claude-plugin/plugin.json";
const PRODUCT = JSON.parse(fs.readFileSync(path.join(ROOT, manifestPath), "utf8")).name;
if (!["vera", "clara", "lucia"].includes(PRODUCT)) throw new Error("Unsupported reporting product");
const SESSION = randomUUID();
class HostFailure extends Error {}
const uuid = { type: "string", format: "uuid" };
const capability = { type: "string", minLength: 32, maxLength: 128, pattern: "^[A-Za-z0-9_-]+$" };
const credentials = { type: "object", additionalProperties: false,
  properties: { installation_id: uuid, installation_key: capability }, required: ["installation_id", "installation_key"] };
const TOOLS = [
  { name: `${PRODUCT}_incident_host_context`, description: "Read or create the native host's random public incident code. Never returns its private key. A Cowork Linux guest remains explicitly unlinked. This does not report a guest workflow version.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false } },
  { name: `${PRODUCT}_incident_host_link`, description: "Automatically bind a guest's existing local incident capability to this native host and app at Mparanza. Pass exactly {credentials: {installation_id, installation_key}} using the guest's existing values. The argument is credentials, not capability; do not add run_id. The host key stays out of tool results; no client files, diagnostics or commands are inputs. Does not close an incident.",
    inputSchema: { type: "object", properties: { credentials }, required: ["credentials"], additionalProperties: false },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true } },
  { name: `${PRODUCT}_workflow_usage`, description: "Retain and deliver one task's usage events through this installed product's native service and existing userID/computer identity. Prefer this over a shell command that cannot write the user-scoped reporting database. Start requires pipeline, observed host and sample_kind; record requires an observed kind and its optional fields. Reuse the same UUID through retries. Status verifies the same task's server identity; flush retries only that task. No client documents, paths, shell commands, credentials or global queue operations are accepted. A reporting failure does not invalidate professional work.",
    inputSchema: { type: "object", additionalProperties: false, required: ["operation", "run_id"], properties: {
      operation: { type: "string", enum: ["start", "record", "status", "flush"] }, run_id: uuid,
      pipeline: { type: "string" }, host: { type: "string", enum: ["codex", "cowork", "chatgpt", "antigravity", "unknown"] },
      sample_kind: { type: "string", enum: ["user", "synthetic", "agent_test"] },
      kind: { type: "string", enum: ["resumed", "completed", "failed", "cancelled", "feedback_prompted", "feedback", "incident"] },
      fields: { type: "object", additionalProperties: false, properties: {
        stars: { type: "integer", minimum: 1, maximum: 5 }, comment: { type: "string", maxLength: 2000 },
        feedback_source: { type: "string", enum: ["user_chat", "user_form", "synthetic_test"] }, incident_report_id: uuid,
      } },
    } },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true } },
];
function checked(relative, index) {
  const file = path.join(ROOT, relative), info = fs.lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new HostFailure("Native incident component is unavailable");
  const bytes = fs.readFileSync(file);
  if (index && createHash("sha256").update(bytes).digest("hex") !== index[relative])
    throw new HostFailure("Native incident component does not match its build index; use the independent incident connector");
  return bytes;
}
function bridge(command, args) {
  const indexPath = path.join(ROOT, "execution-files.json");
  let index;
  if (fs.existsSync(indexPath)) {
    index = JSON.parse(checked("execution-files.json")).files;
    if (!index || typeof index !== "object" || Array.isArray(index)) throw new HostFailure("Native incident build index is invalid");
  }
  else if (!(fs.existsSync(path.resolve(ROOT, "../../.git")) && fs.existsSync(path.resolve(ROOT, "../_shared"))))
    throw new HostFailure("Native incident build index is unavailable; use the independent incident connector");
  checked("scripts/incident_host_mcp.cjs", index);
  const reporter = checked("scripts/operational_incidents.py", index);
  const productHelper = checked("scripts/reporting_product.py", index);
  const collector = checked("scripts/technical_runner.py", index);
  const manifest = fs.existsSync(path.join(ROOT, ".codex-plugin/plugin.json")) ? ".codex-plugin/plugin.json" : ".claude-plugin/plugin.json";
  const metadata = checked(manifest, index);
  const workflow = command === "workflow-usage" ? {
    "scripts/workflow_usage.py": checked("scripts/workflow_usage.py", index),
    "usage/pipelines.json": checked("usage/pipelines.json", index),
  } : {};
  const runtimeRoot = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
    ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
    : path.join(os.homedir(), ".local/share/mparanza/runtime"));
  const managed = path.join(runtimeRoot, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const python = fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3");
  const snapshot = fs.mkdtempSync(path.join(os.tmpdir(), `${PRODUCT}-incident-host-`));
  try {
    fs.chmodSync(snapshot, 0o700);
    fs.mkdirSync(path.join(snapshot, "scripts"));
    fs.mkdirSync(path.dirname(path.join(snapshot, manifest)), { recursive: true });
    fs.writeFileSync(path.join(snapshot, "scripts/operational_incidents.py"), reporter, { mode: 0o600 });
    fs.writeFileSync(path.join(snapshot, "scripts/reporting_product.py"), productHelper, { mode: 0o600 });
    fs.writeFileSync(path.join(snapshot, "scripts/technical_runner.py"), collector, { mode: 0o600 });
    fs.writeFileSync(path.join(snapshot, manifest), metadata, { mode: 0o600 });
    for (const [relative, bytes] of Object.entries(workflow)) {
      fs.mkdirSync(path.dirname(path.join(snapshot, relative)), { recursive: true });
      fs.writeFileSync(path.join(snapshot, relative), bytes, { mode: 0o600 });
    }
    const program = `import json, runpy, sys
from pathlib import Path
root = Path(sys.argv.pop(1))
sys.path.insert(0, str(root / "scripts"))
from technical_runner import exception_events
try:
    if sys.argv[1] == "workflow-usage":
        from workflow_usage import native_operation
        sys.stdout.write(json.dumps(native_operation(json.load(sys.stdin))))
    else:
        runpy.run_path(str(root / "scripts/operational_incidents.py"), run_name="__main__")
except Exception as error:
    # Process boundary: collect fixed technical facts, never values or raw stderr.
    events = exception_events(error, root)
    for event in events:
        if event["message"] == "Exception at the recorded package source location; dynamic detail retained for review.":
            event["message"] = "Exception at the recorded package source location; dynamic detail is unavailable in this native bridge."
    code = getattr(error, "code", None)
    sys.stdout.write(json.dumps({"native_error": {"events": events, "http_status": code if isinstance(code, int) else None, "errno": getattr(error, "errno", None), "sqlite_errorname": getattr(error, "sqlite_errorname", None), "capture_state": "pending" if events else "unavailable", "unavailable": ["This native bridge does not collect raw diagnostic values."]}}))
    raise SystemExit(1)
`;
    const result = spawnSync(python, ["-I", "-B", "-c", program, snapshot, command], {
      cwd: snapshot, encoding: "utf8", input: JSON.stringify(args), timeout: command === "workflow-usage" ? 60000 : 20000, maxBuffer: 1000000,
      env: { ...process.env, MPARANZA_INCIDENT_HOST_SESSION: SESSION },
    });
    if (result.error || result.status !== 0) {
      const failure = new HostFailure("Native incident host operation unavailable; inspect its structured technical facts and keep reporting through the independent connector");
      try { failure.technicalFacts = JSON.parse(result.stdout).native_error; } catch {}
      throw failure;
    }
    return JSON.parse(result.stdout);
  } finally { fs.rmSync(snapshot, { recursive: true, force: true }); }
}
function handle(message) {
  if (message.method === "initialize") return { protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: `${PRODUCT}-incident-host`, version: "1.0.0" },
    instructions: `Use ${PRODUCT}_workflow_usage for task start, observed outcomes, status and task-scoped retries. It retains the installed product's existing identity and persistent queue without requiring chat-shell write access. Use native host linking automatically when available. The native broker's version is separate from the guest's current reporting-process and failed-worker versions. If this host route is unavailable, continue automatic reporting through the product incident connector; never infer device identity from its OAuth connection or a Linux guest UUID.` };
  if (message.method === "ping") return {};
  if (message.method === "tools/list") return { tools: TOOLS };
  if (message.method !== "tools/call") throw new HostFailure("Unsupported native incident method");
  try {
    const { name, arguments: args = {} } = message.params || {};
    if (!args || typeof args !== "object" || Array.isArray(args)) throw new HostFailure("Invalid native incident arguments");
    let command;
    if (name === TOOLS[0].name && Object.keys(args).length === 0) command = "host-context";
    else if (name === TOOLS[1].name) {
      if (Object.keys(args).length !== 1 || !args.credentials ||
          typeof args.credentials !== "object" || Array.isArray(args.credentials))
        throw new HostFailure("Invalid host-link arguments. Retry this same tool with exactly {credentials: {installation_id, installation_key}} from the original guest incident context. Use credentials, not capability; omit run_id. No host linkage has occurred.");
      const value = args.credentials;
      if (Object.keys(value).sort().join(",") !== "installation_id,installation_key" ||
          typeof value.installation_id !== "string" || !/^[0-9a-f-]{36}$/i.test(value.installation_id) ||
          typeof value.installation_key !== "string" || !/^[A-Za-z0-9_-]{32,128}$/.test(value.installation_key))
        throw new HostFailure("Invalid local incident capability. credentials must contain only installation_id (UUID) and installation_key (32-128 allowed characters), copied unchanged from the original guest incident context. Do not generate replacement credentials. No host linkage has occurred.");
      command = "host-link";
    } else if (name === TOOLS[2].name) command = "workflow-usage";
    else throw new HostFailure("Unsupported native incident operation");
    const value = bridge(command, args);
    return { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value };
  } catch (error) { return { isError: true, content: [{ type: "text", text: error instanceof HostFailure ? error.message : "Native incident host operation unavailable; keep reporting through the independent connector" }],
    ...(error.technicalFacts ? { structuredContent: { technical_facts: error.technicalFacts, instruction: "These are source-bound facts only; preserve missing capture explicitly. Never infer successful host linkage or complete diagnosis. Report relevant technical evidence through the product incident connector without credentials or unrelated private content." } } : {}) }; }
}
readline.createInterface({ input: process.stdin, crlfDelay: Infinity }).on("line", line => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  if (message.id === undefined) return;
  try { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: handle(message) }) + "\n"); }
  catch { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: message.id, error: { code: -32602, message: "Invalid native incident request" } }) + "\n"); }
});

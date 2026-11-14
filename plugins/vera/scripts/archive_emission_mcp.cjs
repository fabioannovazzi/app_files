"use strict";

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

function recorderPython(pluginRoot) {
  const interpreter = process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
  const runtimeRoot = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
    ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
    : path.join(os.homedir(), ".local/share/mparanza/runtime"));
  const candidates = [
    process.env.VERA_REPORTING_PYTHON,
    path.join(runtimeRoot, "venv", interpreter),
    process.env.PYTHON,
    process.env.VIRTUAL_ENV && path.join(process.env.VIRTUAL_ENV, interpreter),
    path.resolve(pluginRoot, "../..", ".venv", interpreter),
    ...(process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"]),
  ].filter(Boolean);
  for (const candidate of new Set(candidates)) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    // Probe a usable interpreter; PATH aliases must not hide the managed runtime.
    const probe = spawnSync(candidate, ["-X", "utf8", "-I", "-B", "-c", "import sys; sys.stdout.write(sys.executable)"], {
      encoding: "utf8", windowsHide: true, timeout: 10000, maxBuffer: 8192,
    });
    if (!probe.error && probe.status === 0 && String(probe.stdout || "").trim()) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function bridge(child, component, pluginRoot, input = process.stdin, output = process.stdout) {
  // Observe our own request/response protocol before forwarding our payload.
  // No host tools, transcript access, hooks, or model-authored measurements.
  const requests = new Map();
  // Review tokens are issued by this child for one validated request. Preserve
  // that request's run binding for later token-only calls, separately per token.
  const tokenBindings = new Map();
  const reviewToken = (value) => value?.persistence_token
    || (typeof value?.review_reference === "string" ? value.review_reference
      : value?.review_reference?.persistence_token || value?.review_reference?.reference);
  const record = (envelope) => spawnSync(recorderPython(pluginRoot), ["-X", "utf8",
    path.join(pluginRoot, "scripts/archive_emit.py"),
  ], {
    input: JSON.stringify({ component, ...envelope }), encoding: "utf8",
    timeout: 30000, maxBuffer: 1024 * 1024, windowsHide: true,
  });
  const failure = (stage, request) => ({
    status: "unavailable", code: "archive_reporting_unavailable",
    operation: request.name, failure_stage: stage, response_delivered: true,
    measurement_gap: true, retry_action: "retry_reporting_only",
  });
  const recordedValue = result => {
    if (result.status !== 0) return { ok: false, value: null };
    try { return { ok: true, value: JSON.parse(result.stdout) }; }
    catch { return { ok: false, value: null }; }
  };
  const incoming = readline.createInterface({ input, crlfDelay: Infinity });
  incoming.on("line", (line) => {
    const message = JSON.parse(line);
    if (message.method === "tools/call" && message.id !== undefined) {
      const args = message.params.arguments || {};
      const owner = tokenBindings.get(reviewToken(args));
      const boundArguments = owner ? { request: args, client_engagement: path.join(owner, "context.json") } : args;
      const bound = recordedValue(record({ action: "bind", arguments: boundArguments }));
      requests.set(message.id, {
        ...message.params, binding: bound.value,
        reporting: bound.ok ? null : failure("before_tool_start", message.params),
      });
    }
    child.stdin.write(line + "\n");
  });
  incoming.on("close", () => child.stdin.end());
  const outgoing = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
  outgoing.on("line", (line) => {
    const message = JSON.parse(line);
    const request = requests.get(message.id);
    if (request) {
      requests.delete(message.id);
      const args = request.arguments || {};
      const owner = tokenBindings.get(reviewToken(args));
      const boundArguments = owner ? { request: args, client_engagement: path.join(owner, "context.json") } : args;
      const recorded = recordedValue(record({
          arguments: boundArguments, binding: request.binding,
          payload: message.result || { isError: true, content: [{ type: "text", text: JSON.stringify(message.error) }] },
          channel: "mcp", operation: request.name,
      }));
      const reporting = request.reporting || (recorded.ok ? null : failure("after_tool_return", request));
      if (reporting && message.result) {
        message.result = withReportingFailure(message.result, reporting);
        line = JSON.stringify(message);
      }
      const summary = message.result?.structuredContent;
      const token = reviewToken(summary);
      if (typeof token === "string" && message.result?.isError !== true) {
        const root = request.binding?.run_root || recorded.value?.run_root;
        if (root) tokenBindings.set(token, root);
      }
    }
    output.write(line + "\n");
  });
  child.on("close", () => incoming.close());
  return outgoing;
}

function withReportingFailure(result, detail) {
  return {
    ...result,
    content: [...(result.content || []), { type: "text", text:
      "The operation's result is available. Its model-data report is incomplete because recording failed. Continue with this result; retry reporting separately without repeating the work." }],
    _meta: { ...(result._meta || {}), reporting: detail },
  };
}

module.exports = { bridge, withReportingFailure };

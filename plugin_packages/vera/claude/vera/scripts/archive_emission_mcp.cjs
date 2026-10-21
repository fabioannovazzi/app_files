"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

function recorderPython(pluginRoot) {
  const candidates = [
    process.env.VERA_REPORTING_PYTHON,
    process.env.PYTHON,
    process.env.VIRTUAL_ENV && path.join(process.env.VIRTUAL_ENV,
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python"),
    path.resolve(pluginRoot, "../..", ".venv/bin/python"),
    "python3",
  ].filter(Boolean);
  return candidates.find((candidate) => !path.isAbsolute(candidate) || fs.existsSync(candidate));
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
  const record = (envelope) => spawnSync(recorderPython(pluginRoot), [
    path.join(pluginRoot, "scripts/archive_emit.py"),
  ], {
    input: JSON.stringify({ component, ...envelope }), encoding: "utf8",
    timeout: 30000, maxBuffer: 1024 * 1024, windowsHide: true,
  });
  const withheld = (id, stage, request) => {
    const returned = stage === "after_tool_return";
    const root = request.binding?.run_root;
    const runId = typeof root === "string" ? path.basename(root) : null;
    // Report transport state, never unrecorded case content. A returned tool
    // may already have saved work; its missing response is not permission to repeat it.
    const detail = {
      code: "archive_recording_unavailable",
      operation: request.name,
      failure_stage: stage,
      response_delivered: false,
      retry_action: returned ? "inspect_existing_result" : "restore_recording_then_retry",
      ...(runId && /^run_[0-9a-f]{24}$/.test(runId) ? { archive_run_id: runId } : {}),
    };
    output.write(JSON.stringify({
      jsonrpc: "2.0", id,
      result: { isError: true, structuredContent: detail, content: [{ type: "text", text: returned
        ? "The tool returned, but Vera could not save its outgoing-data record or deliver its response. Work may already be saved. Restore recording access and inspect the existing result in this same run before repeating any operation."
        : "Vera could not prepare this run's outgoing-data record, so the tool was not started. Restore recording access, then retry the same operation.",
      }] },
    }) + "\n");
  };
  const incoming = readline.createInterface({ input, crlfDelay: Infinity });
  incoming.on("line", (line) => {
    const message = JSON.parse(line);
    if (message.method === "tools/call" && message.id !== undefined) {
      const args = message.params.arguments || {};
      const owner = tokenBindings.get(reviewToken(args));
      const boundArguments = owner ? { request: args, client_engagement: path.join(owner, "context.json") } : args;
      const bound = record({ action: "bind", arguments: boundArguments });
      if (bound.status !== 0) {
        withheld(message.id, "before_tool_start", message.params);
        return;
      }
      requests.set(message.id, { ...message.params, binding: JSON.parse(bound.stdout) });
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
      const recorded = record({
          arguments: boundArguments, binding: request.binding,
          payload: message.result || { isError: true, content: [{ type: "text", text: JSON.stringify(message.error) }] },
          channel: "mcp", operation: request.name,
      });
      if (recorded.status !== 0) {
        withheld(message.id, "after_tool_return", request);
        return;
      }
      const summary = message.result?.structuredContent;
      const token = reviewToken(summary);
      if (typeof token === "string" && message.result?.isError !== true) {
        tokenBindings.set(token, JSON.parse(recorded.stdout).run_root);
      }
    }
    output.write(line + "\n");
  });
  child.on("close", () => incoming.close());
  return outgoing;
}

module.exports = { bridge };

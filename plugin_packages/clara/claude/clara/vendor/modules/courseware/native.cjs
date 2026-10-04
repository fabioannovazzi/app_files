"use strict";
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");
function server(root) {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, ".codex-plugin/plugin.json"), "utf8"));
  const product = manifest.name;
  const URI = `ui://${product}/course-chats-v1.html`;
  const text = { type: "string", minLength: 1, maxLength: 4000 };
  const schema = (properties, required) => ({ type: "object", properties, required, additionalProperties: false });
  const prepare = {
    name: "course_chat_open", title: `${product[0].toUpperCase()+product.slice(1)} · Chat del corso`,
    description: "After course workspace setup, open the working-chat button for any installed course. Use the actual teacher thread ID, exact state_root, current revision and selected own-product workflow. Existing pairs resume; replace_missing_worker is allowed only after native inspection confirms the worker is unavailable. Does not execute a lesson.",
    inputSchema: schema({ state_root: text, teacher_thread_id: text, workflow_id: text, title: text, goal: text, revision: { type: "integer", minimum: 1 }, kind: { enum: ["onboarding", "teaching"] }, session_id: text, mode: { enum: ["show", "together"] }, language: { enum: ["it", "en", "fr", "de", "es"] }, replace_missing_worker: { type: "boolean" } }, ["state_root", "teacher_thread_id", "workflow_id", "title", "goal", "revision", "kind"]),
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    _meta: { ui: { resourceUri: URI, visibility: ["app", "model"] }, "openai/outputTemplate": URI }
  };
  const claim = {
    name: "course_chat_claim", title: "Connect the course working chat",
    description: "In the new working chat, claim the readable course invitation with your actual native thread ID. Verifies local writing, current revision, invitation and product; returns the exact installed specialist and bounded assignment. Never invent a thread ID. Only the teacher records lesson progress.",
    inputSchema: schema({ state_root: text, invitation: text, thread_id: text }, ["state_root", "invitation", "thread_id"]),
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false }
  };
  function validate(tool, args) {
    if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("Arguments must be an object");
    for (const key of tool.inputSchema.required) if (!(key in args)) throw new Error(`Missing ${key}`);
    for (const [key, value] of Object.entries(args)) {
      const rule = tool.inputSchema.properties[key];
      if (!rule) throw new Error(`Unexpected field: ${key}`);
      if (rule.type === "string" && (typeof value !== "string" || !value.trim() || value.length > rule.maxLength)) throw new Error(`Invalid ${key}`);
      if (rule.type === "integer" && (!Number.isSafeInteger(value) || value < rule.minimum)) throw new Error(`Invalid ${key}`);
      if (rule.type === "boolean" && typeof value !== "boolean") throw new Error(`Invalid ${key}`);
      if (rule.enum && !rule.enum.includes(value)) throw new Error(`Invalid ${key}`);
    }
  }
  function bridge(operation, args) {
    const runtimeRoot = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32"
      ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr")
      : path.join(os.homedir(), ".local/share/mparanza/runtime"));
    const managed = path.join(runtimeRoot, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    // Reuse the existing shared runtime; this stdlib bridge installs nothing.
    const python = process.env.MPARANZA_COURSE_PYTHON || (fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3"));
    const result = spawnSync(python, [path.join(root, "scripts/course_chat_bridge.py")], { cwd: root, input: JSON.stringify({ operation, arguments: args }), encoding: "utf8", timeout: 30000, maxBuffer: 1000000 });
    if (result.error) throw new Error(`Course runtime unavailable: ${result.error.message}. Run the product's documented Python setup, then retry.`);
    let data;
    try { data = JSON.parse(result.stdout); } catch { throw new Error("Course runtime did not return a valid result; inspect local setup before continuing"); }
    if (result.status !== 0) throw new Error(data.error || "Course storage is blocked; authorize its exact folder and retry");
    return data;
  }
  function resource() {
    const assets = path.join(__dirname, "assets");
    const html = fs.readFileSync(path.join(assets, "chat.html"), "utf8")
      .replace("/*__JS__*/", fs.readFileSync(path.join(assets, "chat.js"), "utf8"))
      .replace("__FONT__", fs.readFileSync(path.join(assets, "InstrumentSans-Regular.ttf")).toString("base64"));
    return { contents: [{ uri: URI, mimeType: "text/html;profile=mcp-app", text: html, _meta: { ui: { csp: { connectDomains: [], resourceDomains: [] } } } }] };
  }
  function dispatch(message) {
    const params = message.params || {};
    switch (message.method) {
      case "initialize": return { protocolVersion: params.protocolVersion || "2024-11-05", capabilities: { tools: {}, resources: {} }, serverInfo: { name: `${product}-course-chats`, version: manifest.version } };
      case "ping": return {};
      case "tools/list": return { tools: [prepare, claim] };
      case "resources/list": return { resources: [{ uri: URI, name: "Course chats", mimeType: "text/html;profile=mcp-app" }] };
      case "resources/read": if (params.uri !== URI) throw new Error("Unknown course resource"); return resource();
      case "tools/call": {
        const tool = [prepare, claim].find(item => item.name === params.name);
        if (!tool) throw new Error("Unknown course tool");
        try {
          validate(tool, params.arguments);
          const data = bridge(tool === prepare ? "prepare" : "claim", params.arguments);
          if (tool === claim) return { content: [{ type: "text", text: JSON.stringify(data) }], structuredContent: data };
          return { content: [{ type: "text", text: "Course chat control ready; use the button to open or resume the working chat." }], structuredContent: { status: "ready", product, workflow_id: data.workflow_id }, _meta: { course_chat: { ...data, language: params.arguments.language || "it" } } };
        } catch (error) { return { isError: true, content: [{ type: "text", text: error.message }] }; }
      }
      default: throw new Error(`Unsupported method: ${message.method}`);
    }
  }
  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  lines.on("line", line => {
    let message;
    try { message = JSON.parse(line); } catch { return; }
    if (message.id === undefined) return;
    try { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: dispatch(message) })+"\n"); }
    catch (error) { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: message.id, error: { code: -32602, message: error.message } })+"\n"); }
  });
}
module.exports = { server };

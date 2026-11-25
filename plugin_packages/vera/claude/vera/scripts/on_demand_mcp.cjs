#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
const { ServiceClient } = require("./mcp_service_client.cjs");

const NATIVE_STARTUP_TIMEOUT_MS = 300000;

function main(root = path.resolve(__dirname, "..")) {
  require("./verify_mcp_package.cjs").verify(root);
  const catalog = JSON.parse(fs.readFileSync(path.join(root, "mcp-catalog.json"), "utf8"));
  const configurations = JSON.parse(fs.readFileSync(path.join(root, "mcp-services.json"), "utf8")).mcpServers;
  if (catalog.schema_version !== 1) throw new Error("Unsupported service catalogue");
  const product = catalog.product;
  // One connection owns one Archive session, including when the host supplies
  // no chat ID. Sibling services must not invent independent fallback owners.
  const serviceEnvironment = {
    ...process.env,
    VERA_STUDIO_ARCHIVE_SESSION_ID: process.env.VERA_STUDIO_ARCHIVE_SESSION_ID?.trim()
      || process.env.CODEX_THREAD_ID?.trim() || `${product}-${randomUUID()}`,
  };
  // One explicit reporting session is shared with the native incident service.
  const settingsIndex = process.argv.indexOf("--settings");
  const settings = settingsIndex < 0 ? {} : JSON.parse(fs.readFileSync(process.argv[settingsIndex + 1], "utf8"));
  const os = require("node:os");
  const host = fs.existsSync(path.join(root, ".codex-plugin/plugin.json")) ? "codex" : "cowork";
  let settingsPath;
  function reportingSettingsPath() {
    if (!settingsPath) {
      const settingsRoot = path.join(settings.state_dir || path.join(os.homedir(), ".mparanza", product, "incidents", host), "sessions");
      fs.mkdirSync(settingsRoot, { recursive: true, mode: 0o700 });
      settingsPath = path.join(settingsRoot, `${randomUUID()}.json`);
      fs.writeFileSync(settingsPath, JSON.stringify({ host, host_session: randomUUID(), ...settings }), { mode: 0o600, flag: "wx" });
    }
    return settingsPath;
  }
  const services = new Map();
  const startupReporters = new Set();
  const active = new Map();
  const serverRequests = new Map();
  let serverSequence = 0;
  let closing = false;
  let initialization;
  const output = message => { if (!closing) process.stdout.write(JSON.stringify(message) + "\n"); };
  const failure = (id, code, message) => output({ jsonrpc: "2.0", id, error: { code, message } });
  const isNativeExecution = name => product === "vera" && name === "veraExecution";
  function removeReportingSettings() {
    if (closing && !startupReporters.size && settingsPath)
      fs.rmSync(settingsPath, { force: true });
  }
  function reportStartupTimeout(elapsedMs) {
    try {
      const reporter = spawn(process.execPath, [path.join(root, "scripts/native_execution_mcp.cjs"),
        "--settings", reportingSettingsPath(), "--report-startup-timeout", String(elapsedMs)],
      { cwd: root, env: serviceEnvironment, stdio: ["ignore", "ignore", "inherit"] });
      startupReporters.add(reporter);
      reporter.on("error", () => process.stderr.write("Vera startup timeout reporter could not start.\n"));
      reporter.once("close", () => {
        startupReporters.delete(reporter);
        removeReportingSettings();
      });
    } catch {
      process.stderr.write("Vera startup timeout reporter could not start.\n");
    }
  }
  const items = field => catalog.services.flatMap(service => service[field] || []);
  const owners = field => {
    const map = new Map();
    for (const service of catalog.services) for (const item of service[field] || []) {
      const key = item.name;
      if (map.has(key)) throw new Error(`Duplicate ${field} name: ${key}`);
      map.set(key, service.name);
    }
    return map;
  };
  const tools = owners("tools");
  const prompts = owners("prompts");
  const resources = new Map();
  for (const service of catalog.services) for (const resource of service.resources || []) {
    if (resources.has(resource.uri)) throw new Error(`Duplicate resource URI: ${resource.uri}`);
    resources.set(resource.uri, service.name);
  }

  function service(name, reconnectForStatus) {
    if (closing) throw new Error(`${product} connection is closing`);
    // Native job state belongs to disk. A new status request can inspect it
    // through a fresh service, while the failed operation stays unreplayed.
    if (reconnectForStatus && services.get(name)?.client.closed) services.delete(name);
    if (!services.has(name)) {
      const original = configurations[name];
      const config = original?.args?.some(value => ["incident_host_mcp.cjs", "native_execution_mcp.cjs"].some(script => value.endsWith(script)))
        ? { ...original, args: [...original.args, "--settings", reportingSettingsPath()] } : original;
      if (!config) throw new Error(`Missing ${product} service: ${name}`);
      const client = new ServiceClient(root, name, config, {
        env: serviceEnvironment,
        notification: output,
        request: message => {
          const id = `${product}-service-${++serverSequence}`;
          serverRequests.set(id, { client, id: message.id });
          output({ ...message, id });
        },
      });
      const native = isNativeExecution(name);
      const started = performance.now();
      const entry = { client, initializing: true };
      entry.ready = client.initialize(initialization, native ? NATIVE_STARTUP_TIMEOUT_MS : undefined).then(() => {
        entry.initializing = false;
        return client;
      }).catch(error => {
        entry.initializing = false;
        // Initialization failed before any tool request reached this worker.
        // Preserve the existing status-only handling for a dispatched job.
        if (native && services.get(name) === entry) services.delete(name);
        client.close("SIGTERM");
        if (native && !closing && error.code === "MCP_REQUEST_TIMEOUT")
          reportStartupTimeout(Math.round(performance.now() - started));
        throw error;
      });
      // Store before waiting so simultaneous first calls share one worker.
      services.set(name, entry);
    }
    return services.get(name);
  }

  async function handle(message) {
    const id = message.id;
    if (!message.method) {
      const target = serverRequests.get(id);
      if (target) {
        serverRequests.delete(id);
        target.client.send({ ...message, id: target.id });
      }
      return;
    }
    if (message.method === "notifications/cancelled") {
      const pending = active.get(message.params?.requestId);
      if (pending) {
        pending.cancelled = message.params;
        if (pending.client) pending.client.send({ ...message, params: { ...message.params, requestId: pending.workerId } });
      }
      return;
    }
    if (id === undefined) {
      if (message.method !== "notifications/initialized")
        for (const { client } of services.values()) if (!client.error) client.send(message);
      return;
    }
    if (message.method === "initialize") {
      initialization = message.params || {};
      output({ jsonrpc: "2.0", id, result: {
        protocolVersion: initialization.protocolVersion || "2024-11-05",
        serverInfo: { name: product, version: catalog.version },
        capabilities: { tools: {}, resources: {}, prompts: {} },
        instructions: catalog.services.map(s => s.initialize.instructions).filter(Boolean).join("\n\n"),
      } });
      return;
    }
    if (!initialization) { failure(id, -32002, `Initialize ${product} before using tools`); return; }
    const lists = { "tools/list": ["tools", "tools"], "resources/list": ["resources", "resources"],
      "resources/templates/list": ["resourceTemplates", "resourceTemplates"], "prompts/list": ["prompts", "prompts"] };
    if (lists[message.method]) {
      const [field, key] = lists[message.method];
      output({ jsonrpc: "2.0", id, result: { [key]: items(field) } });
      return;
    }
    if (message.method === "ping") { output({ jsonrpc: "2.0", id, result: {} }); return; }
    const name = message.method === "tools/call" ? tools.get(message.params?.name)
      : message.method === "prompts/get" ? prompts.get(message.params?.name)
      : ["resources/read", "resources/subscribe", "resources/unsubscribe"].includes(message.method)
        ? resources.get(message.params?.uri) : undefined;
    if (!name) { failure(id, -32602, `Unknown ${product} method or target: ${message.method}`); return; }
    if (active.has(id)) { failure(id, -32600, "Duplicate active request ID"); return; }
    const pending = {};
    let startupProgress;
    active.set(id, pending);
    try {
      const reconnectForStatus = product === "vera"
        && name === "veraExecution"
        && message.method === "tools/call"
        && message.params?.name === "vera_execute"
        && message.params?.arguments?.operation === "status";
      const entry = service(name, reconnectForStatus);
      const progressToken = message.params?._meta?.progressToken;
      if (isNativeExecution(name) && entry.initializing && progressToken !== undefined) {
        let progress = 0;
        startupProgress = setInterval(() => {
          if (!pending.cancelled) output({ jsonrpc: "2.0", method: "notifications/progress", params: {
            progressToken, progress: ++progress, message: "Vera is preparing its native execution service.",
          } });
        }, 10000);
      }
      const client = await entry.ready;
      clearInterval(startupProgress);
      if (pending.cancelled) { failure(id, -32800, "Request cancelled before tool execution"); return; }
      const reply = await client.call(message.method, message.params, { started(workerId) {
        pending.client = client;
        pending.workerId = workerId;
      } });
      if (product === "vera" && message.method === "resources/read") {
        for (const resource of reply.result?.contents || []) {
          if (resource.mimeType !== "text/html;profile=mcp-app") continue;
          resource._meta ??= {};
          resource._meta["openai/ui"] = {
            ...resource._meta["openai/ui"],
            preferredDisplayMode: "fullscreen",
            availableDisplayModes: ["fullscreen"],
          };
        }
      }
      output({ ...reply, id });
    } catch (error) { failure(id, -32000, error.message); }
    finally { clearInterval(startupProgress); active.delete(id); }
  }

  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  input.on("line", line => {
    if (!line.trim()) return;
    let message;
    try { message = JSON.parse(line); }
    catch { failure(null, -32700, "Invalid JSON"); return; }
    if (!message || message.jsonrpc !== "2.0") { failure(message?.id ?? null, -32600, "Invalid JSON-RPC"); return; }
    handle(message).catch(error => failure(message.id ?? null, -32000, error.message));
  });
  const close = signal => {
    closing = true;
    removeReportingSettings();
    for (const { client } of services.values()) client.close(signal);
    input.close();
  };
  input.on("close", () => close());
  for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => close(signal));
  process.stdout.on("error", error => { if (error.code === "EPIPE") close(); else throw error; });
}

module.exports = { main };
if (require.main === module) main();

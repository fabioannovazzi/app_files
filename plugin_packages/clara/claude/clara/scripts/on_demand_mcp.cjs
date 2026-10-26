#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { ServiceClient } = require("./mcp_service_client.cjs");

function main(root = path.resolve(__dirname, "..")) {
  require("./verify_mcp_package.cjs").verify(root);
  const catalog = JSON.parse(fs.readFileSync(path.join(root, "mcp-catalog.json"), "utf8"));
  const configurations = JSON.parse(fs.readFileSync(path.join(root, "mcp-services.json"), "utf8")).mcpServers;
  if (catalog.schema_version !== 1) throw new Error("Unsupported service catalogue");
  const product = catalog.product;
  const services = new Map();
  const active = new Map();
  const serverRequests = new Map();
  let serverSequence = 0;
  let closing = false;
  let initialization;
  const output = message => { if (!closing) process.stdout.write(JSON.stringify(message) + "\n"); };
  const failure = (id, code, message) => output({ jsonrpc: "2.0", id, error: { code, message } });
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

  async function service(name) {
    if (closing) throw new Error(`${product} connection is closing`);
    if (!services.has(name)) {
      const config = configurations[name];
      if (!config) throw new Error(`Missing ${product} service: ${name}`);
      const client = new ServiceClient(root, name, config, {
        notification: output,
        request: message => {
          const id = `${product}-service-${++serverSequence}`;
          serverRequests.set(id, { client, id: message.id });
          output({ ...message, id });
        },
      });
      const ready = client.initialize(initialization).then(() => client).catch(error => {
        client.close("SIGTERM");
        throw error;
      });
      // Store before waiting so simultaneous first calls share one worker.
      services.set(name, { client, ready });
    }
    return services.get(name).ready;
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
    active.set(id, pending);
    try {
      const client = await service(name);
      if (pending.cancelled) { failure(id, -32800, "Request cancelled before tool execution"); return; }
      const reply = await client.call(message.method, message.params, { started(workerId) {
        pending.client = client;
        pending.workerId = workerId;
      } });
      output({ ...reply, id });
    } catch (error) { failure(id, -32000, error.message); }
    finally { active.delete(id); }
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
    for (const { client } of services.values()) client.close(signal);
    input.close();
  };
  input.on("close", () => close());
  for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => close(signal));
  process.stdout.on("error", error => { if (error.code === "EPIPE") close(); else throw error; });
}

module.exports = { main };
if (require.main === module) main();

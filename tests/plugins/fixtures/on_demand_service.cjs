"use strict";
const fs = require("node:fs");
const readline = require("node:readline");
const name = process.argv[2];
fs.appendFileSync(process.env.START_LOG, `${name}:${process.pid}\n`);
let value;
const waiting = new Map();
const serverRequests = new Map();
const reply = (id, result) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
const send = message => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...message }) + "\n");
const tool = { name: `use_${name}`, description: `${name} reconciliation`, inputSchema: { type: "object" }, _meta: { ui: { resourceUri: `ui://${name}` } } };
const input = readline.createInterface({ input: process.stdin });
input.on("line", line => {
  const m = JSON.parse(line), args = m.params?.arguments || {};
  if (!m.method && serverRequests.has(m.id)) {
    reply(serverRequests.get(m.id), { content: [], structuredContent: m.result });
    serverRequests.delete(m.id);
    return;
  }
  if (m.method === "initialize") { setTimeout(() => reply(m.id, { protocolVersion: m.params.protocolVersion, serverInfo: { name, version: "1" }, capabilities: { tools: {}, resources: {}, prompts: {} }, instructions: `Use ${name} for reconciliation` }), 30); return; }
  if (m.method === "tools/list") { reply(m.id, { tools: [tool] }); return; }
  if (m.method === "resources/list") { reply(m.id, { resources: [{ uri: `ui://${name}`, name, mimeType: "text/html;profile=mcp-app" }] }); return; }
  if (m.method === "resources/templates/list") { reply(m.id, { resourceTemplates: [] }); return; }
  if (m.method === "prompts/list") { reply(m.id, { prompts: [{ name: `prompt_${name}` }] }); return; }
  if (m.method === "resources/read") { reply(m.id, { contents: [{ uri: m.params.uri, text: `<html>${name}</html>` }] }); return; }
  if (m.method === "prompts/get") { reply(m.id, { messages: [{ role: "user", content: { type: "text", text: name } }] }); return; }
  if (m.method === "notifications/cancelled") { const t = waiting.get(m.params.requestId); if (t) { clearTimeout(t); waiting.delete(m.params.requestId); send({ id: m.params.requestId, error: { code: -32800, message: "cancelled" } }); } return; }
  if (m.method !== "tools/call") return;
  if (args.action === "crash") { fs.appendFileSync(process.env.WRITE_LOG, "saved\n"); process.exit(9); }
  if (args.action === "wait") { waiting.set(m.id, setTimeout(() => { waiting.delete(m.id); reply(m.id, { content: [] }); }, 5000)); return; }
  if (args.action === "error") { send({ id: m.id, error: { code: -32602, message: "original worker error" } }); return; }
  if (args.action === "malformed") { process.stdout.write(args.payload + "\n"); return; }
  if (args.action === "host-request") { serverRequests.set(1, m.id); send({ id: 1, method: "roots/list", params: {} }); return; }
  if (args.action === "save") value = args.value;
  if (m.params._meta?.progressToken) send({ method: "notifications/progress", params: { progressToken: m.params._meta.progressToken, progress: 1 } });
  reply(m.id, { content: [{ type: "text", text: JSON.stringify({ name, value: value ?? null, pid: process.pid }) }], structuredContent: { name, value: value ?? null, pid: process.pid } });
});
input.on("close", () => { for (const timer of waiting.values()) clearTimeout(timer); });

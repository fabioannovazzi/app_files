"use strict";
const fs = require("node:fs");
const readline = require("node:readline");
const path = require("node:path");
const { createHash, randomUUID } = require("node:crypto");
const name = process.argv[2];
const archiveSession = process.env.VERA_STUDIO_ARCHIVE_SESSION_ID || process.env.CODEX_THREAD_ID || randomUUID();
const archiveState = path.join(path.dirname(process.env.START_LOG), `archive-${createHash("sha256").update(archiveSession).digest("hex")}.json`);
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
  if (m.method === "initialize") { setTimeout(() => reply(m.id, { protocolVersion: m.params.protocolVersion, serverInfo: { name, version: "1" }, capabilities: { tools: {}, resources: {}, prompts: {} }, instructions: `Use ${name} for reconciliation` }), Number(process.env.INITIALIZE_DELAY_MS || 30)); return; }
  if (m.method === "tools/list") { reply(m.id, { tools: [tool] }); return; }
  if (m.method === "resources/list") { reply(m.id, { resources: [{ uri: `ui://${name}`, name, mimeType: "text/html;profile=mcp-app" }] }); return; }
  if (m.method === "resources/templates/list") { reply(m.id, { resourceTemplates: [] }); return; }
  if (m.method === "prompts/list") { reply(m.id, { prompts: [{ name: `prompt_${name}` }] }); return; }
  if (m.method === "resources/read") { reply(m.id, { contents: [{ uri: m.params.uri, mimeType: "text/html;profile=mcp-app", _meta: { ui: { prefersBorder: false } }, text: `<html>${name}</html>` }] }); return; }
  if (m.method === "prompts/get") { reply(m.id, { messages: [{ role: "user", content: { type: "text", text: name } }] }); return; }
  if (m.method === "notifications/cancelled") { const t = waiting.get(m.params.requestId); if (t) { clearTimeout(t); waiting.delete(m.params.requestId); send({ id: m.params.requestId, error: { code: -32800, message: "cancelled" } }); } return; }
  if (m.method !== "tools/call") return;
  if (args.action === "archive-configure" || args.action === "archive-read") {
    if (args.action === "archive-configure") fs.writeFileSync(archiveState, JSON.stringify(args.value));
    const archive = fs.existsSync(archiveState) ? JSON.parse(fs.readFileSync(archiveState, "utf8")) : null;
    reply(m.id, { content: [], structuredContent: { configured: archive !== null, archive } });
    return;
  }
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

"use strict";
// Preserve validation, model checks and durable decisions; retire their inspectors.
const path = require("node:path");
const readline = require("node:readline");
const {spawn} = require("node:child_process");
const component = process.argv[2];
if (!["prompt-optimizer", "deep-research-validator"].includes(component)) {
  process.stderr.write("Unknown Lucia review engine.\n"); process.exit(2);
}
const child = spawn(process.execPath, [path.join(__dirname, "run_component_mcp.cjs"), component], {stdio: ["pipe", "pipe", "inherit"]});
const requests = new Map();
const send = message => process.stdout.write(JSON.stringify(message) + "\n");
function plainMeta(value) {
  if (!value || typeof value !== "object") return;
  delete value["openai/outputTemplate"]; delete value["ui/resourceUri"]; delete value["openai/widgetAccessible"];
  if (value.ui) delete value.ui.resourceUri;
}
readline.createInterface({input: child.stdout}).on("line", line => {
  let message; try { message = JSON.parse(line); } catch { return; }
  const request = requests.get(message.id); requests.delete(message.id);
  const result = message.result;
  if (result?.serverInfo) {
    result.instructions = "Review this Lucia workflow in chat and its professional documents. Preserve required model-policy checks and explicit professional decisions. Validation, saving and applying remain separate steps; do not launch a metadata inspector or browser editor.";
    delete result.capabilities?.resources;
  }
  if (request?.method === "tools/list" && Array.isArray(result?.tools)) {
    result.tools = result.tools.filter(tool => !tool.name.startsWith("render_"));
    for (const tool of result.tools) {
      plainMeta(tool._meta);
      if (tool.name.startsWith("validate_")) tool.description = "Validate the existing hash-bound local review. Review results in chat and their professional documents. Retain the returned reference for explicit save/apply operations; validation does not approve the work.";
    }
  }
  if (request?.method === "tools/call") {
    plainMeta(result?._meta);
    if (/^validate_/.test(request.params?.name || "")) {
      for (const content of result?.content || []) {
        if (content.type === "text" && /render_(prompt_optimizer|deep_research)_review/.test(content.text))
          content.text = result.isError ? content.text : "Review validated. Discuss the professional result in chat; preserve explicit decisions and the exact-version save/apply steps.";
      }
    }
  }
  send(message);
});
readline.createInterface({input: process.stdin}).on("line", line => {
  let message; try { message = JSON.parse(line); } catch { return; }
  if (["resources/list", "resources/templates/list"].includes(message.method)) {
    send({jsonrpc:"2.0",id:message.id,result: message.method === "resources/list" ? {resources:[]} : {resourceTemplates:[]}}); return;
  }
  if (message.method === "resources/read" || (message.method === "tools/call" && message.params?.name?.startsWith("render_"))) {
    send({jsonrpc:"2.0",id:message.id,error:{code:-32601,message:"Review this workflow in chat and its documents."}}); return;
  }
  if (message.id !== undefined) requests.set(message.id, message);
  child.stdin.write(line + "\n");
});
process.stdin.on("end", () => child.stdin.end());
child.on("error", () => {process.stderr.write("Lucia review engine unavailable.\n");process.exit(1);});
child.on("exit", (code, signal) => {if(signal)process.kill(process.pid,signal);else process.exit(code ?? 1);});

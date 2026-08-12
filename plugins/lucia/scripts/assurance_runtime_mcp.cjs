#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

const ALLOWED_TOOLS = new Set([
  "studio_archive_status",
  "list_studio_archive_clients",
  "get_studio_client_folder",
  "create_studio_archive_client",
  "create_studio_client_engagement",
  "list_studio_client_engagements",
  "import_studio_client_document",
  "prepare_studio_client_workflow",
  "start_studio_client_workflow",
  "fail_studio_client_workflow",
  "cancel_studio_client_workflow",
  "finalize_studio_client_workflow",
  "complete_studio_client_workflow",
  "recover_studio_client_ledger",
  "report_studio_client_retention",
  "configure_studio_archive",
]);
const LUCIA_WORKFLOWS = new Set([
  "prompt-optimizer",
  "deep-research-validator",
  "apertura-pratica",
]);

const pluginRoot = path.resolve(__dirname, "..");
const packagedRoot = path.join(pluginRoot, "modules", "studio-archive");
const sourceRoot = path.resolve(pluginRoot, "..", "studio-archive");
const componentRoot = fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot;
const serverPath = path.join(componentRoot, "mcp", "server.cjs");

if (!fs.existsSync(serverPath)) {
  process.stderr.write(`Lucia assurance runtime not found: ${serverPath}\n`);
  process.exit(2);
}

const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
  env: { ...process.env, LUCIA_ASSURANCE_HOST: "1" },
  stdio: ["pipe", "pipe", "inherit"],
});
const listRequests = new Map();
let requestNumber = 0;

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function filterToolDefinition(tool) {
  const filtered = structuredClone(tool);
  if (filtered.name === "prepare_studio_client_workflow") {
    filtered.inputSchema.properties.workflow_id.enum = [...LUCIA_WORKFLOWS];
  }
  if (typeof filtered.title === "string") {
    filtered.title = filtered.title.replaceAll("Vera", "Lucia");
  }
  if (typeof filtered.description === "string") {
    filtered.description = filtered.description.replaceAll("Vera", "Lucia");
  }
  return filtered;
}

const childLines = readline.createInterface({ input: child.stdout });
childLines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    process.stderr.write("Lucia assurance runtime returned invalid JSON.\n");
    return;
  }
  if (listRequests.has(message.id)) {
    const originalId = listRequests.get(message.id);
    listRequests.delete(message.id);
    message.id = originalId;
    const tools = message.result?.tools;
    if (Array.isArray(tools)) {
      message.result.tools = tools
        .filter((tool) => ALLOWED_TOOLS.has(tool.name))
        .map(filterToolDefinition);
    }
  } else if (message.result?.serverInfo?.name === "vera-studio-archive") {
    message.result.serverInfo.name = "lucia-assurance-runtime";
    message.result.instructions =
      "Private lifecycle for Lucia's registered assurance and matter-opening workflows. Do not use it for archive search, email, messaging, or unrelated workflows.";
  }
  send(message);
});

const clientLines = readline.createInterface({ input: process.stdin });
clientLines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } });
    return;
  }
  if (message.method === "tools/list") {
    const internalId = `lucia-tools-list-${requestNumber += 1}`;
    listRequests.set(internalId, message.id ?? null);
    child.stdin.write(`${JSON.stringify({ ...message, id: internalId })}\n`);
    return;
  }
  if (message.method === "tools/call") {
    const toolName = message.params?.name;
    const workflowId = message.params?.arguments?.workflow_id;
    if (!ALLOWED_TOOLS.has(toolName)) {
      send({
        jsonrpc: "2.0",
        id: message.id ?? null,
        error: { code: -32601, message: "Tool not available in Lucia." },
      });
      return;
    }
    if (
      toolName === "prepare_studio_client_workflow" &&
      !LUCIA_WORKFLOWS.has(workflowId)
    ) {
      send({
        jsonrpc: "2.0",
        id: message.id ?? null,
        error: { code: -32602, message: "Workflow not available in Lucia." },
      });
      return;
    }
  }
  child.stdin.write(`${line}\n`);
});
clientLines.on("close", () => child.stdin.end());

child.on("error", (error) => {
  process.stderr.write(`Could not start Lucia assurance runtime: ${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

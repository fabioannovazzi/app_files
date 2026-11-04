#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

const pluginRoot = path.resolve(__dirname, "..");
const packagedRoot = path.join(pluginRoot, "modules", "studio-archive");
const sourceRoot = path.resolve(pluginRoot, "..", "studio-archive");
const componentRoot = fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot;
const serverPath = path.join(componentRoot, "mcp", "server.cjs");

const workflows = JSON.parse(fs.readFileSync(path.join(pluginRoot, "components.json"), "utf8"))
  .workflow_roles["studio-archive"].supports;
const excluded = new Set(["start_check_entries_from_sample", "verify_studio_run_report"]);
const descriptions = {
  get_studio_client_folder: "Return the registered client folder and identity used to bind matters and prevent cross-client imports.",
  import_studio_client_document: "Import an authorized source or support file into the selected matter with an immutable receipt. Check source access before creating records. After an import failure reuse the returned client and engagement IDs. For a saved follow-up use the support role and verify the controlled copy before reporting success.",
  copy_studio_client_source_folder: "Copy an authorized source tree to a new delivery folder outside the managed ledger. Preserve originals, relative paths and duplicate copies. Retries verify the retained receipt and bytes; an interrupted copy must be recovered before taking a snapshot.",
  snapshot_studio_client_folder: "Hash a bounded client-folder view locally and return its complete projected inventory for the selected matter. Raw hashes and absolute paths stay local; documents are not copied or moved.",
  snapshot_studio_client_google_drive: "Read one exact bound Drive folder recursively and return its projected inventory. Storage IDs, versions, parents, capabilities and checksums stay in the local receipt.",
  read_studio_run_artifact: "Read selected data from a bound input or an output of this exact run. Offset and limit select physical data units; columns are zero-based indices.",
  finalize_studio_client_workflow: "Omit artifacts to list the selected run’s actual output paths. Declare those paths with purpose, audience and media type and mark them ready for review. Before completion, correct declaration metadata using the returned declaration_sha256. Preserve file identities, bytes and earlier receipts.",
  configure_studio_archive_client: "Bind confirmed legal names, full email addresses and tax identifiers to one exact archive scope in the private local registry. The registry stores no Gmail credentials, messages or attachments.",
};

if (!fs.existsSync(serverPath)) {
  process.stderr.write(`Lucia Studio Archive not found: ${serverPath}\n`);
  process.exit(2);
}

const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
  env: { ...process.env, VERA_COMPONENT_HOST: "1", LUCIA_ASSURANCE_HOST: "1" },
  stdio: ["pipe", "pipe", "inherit"],
});
const listRequests = new Set();

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function projectTool(tool) {
  const filtered = structuredClone(tool);
  if (filtered.name === "prepare_studio_client_workflow") {
    filtered.inputSchema.properties.workflow_id.enum = workflows;
  }
  if (filtered.title) filtered.title = filtered.title.replaceAll("Vera", "Lucia");
  if (descriptions[tool.name]) filtered.description = descriptions[tool.name];
  return filtered;
}

const childLines = readline.createInterface({ input: child.stdout });
childLines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    process.stderr.write("Lucia Studio Archive returned invalid JSON.\n");
    return;
  }
  if (listRequests.delete(message.id)) {
    const tools = message.result?.tools;
    if (Array.isArray(tools)) {
      message.result.tools = tools
        .filter((tool) => !excluded.has(tool.name))
        .map(projectTool);
    }
  } else if (message.result?.serverInfo?.name === "vera-studio-archive") {
    message.result.serverInfo.name = "lucia-studio-archive";
    message.result.instructions = message.result.instructions.replace(
      "Archive Organization uses the complete projected inventory",
      "Inspect client folders using the complete projected inventory",
    );
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
    if (message.id != null) listRequests.add(message.id);
  }
  if (message.method === "tools/call") {
    const toolName = message.params?.name;
    const workflowId = message.params?.arguments?.workflow_id;
    if (typeof toolName !== "string" || excluded.has(toolName) || toolName.startsWith("lucia_assurance_")) {
      send({
        jsonrpc: "2.0",
        id: message.id ?? null,
        error: { code: -32601, message: "Tool not available in Lucia." },
      });
      return;
    }
    if (
      toolName === "prepare_studio_client_workflow" &&
      !workflows.includes(workflowId)
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
  process.stderr.write(`Could not start Lucia Studio Archive: ${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

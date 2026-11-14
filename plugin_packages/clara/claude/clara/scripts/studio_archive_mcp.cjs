#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const { createHash } = require("node:crypto");
const path = require("node:path");
const readline = require("node:readline");
const { spawn, spawnSync } = require("node:child_process");

const { randomUUID } = require("node:crypto");
process.env.VERA_STUDIO_ARCHIVE_SESSION_ID ||= process.env.CODEX_THREAD_ID || randomUUID();
const pluginRoot = path.resolve(__dirname, "..");
const packagedRoot = path.join(pluginRoot, "modules", "studio-archive");
const sourceRoot = path.resolve(pluginRoot, "..", "studio-archive");
const componentRoot = fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot;
const serverPath = path.join(componentRoot, "mcp", "server.cjs");

const workflows = JSON.parse(fs.readFileSync(path.join(pluginRoot, "components.json"), "utf8"))
  .workflow_roles["studio-archive"].supports;
const allowed = new Set(["studio_archive_status", "list_studio_archive_clients", "resolve_studio_archive_client", "get_studio_client_folder", "create_studio_archive_client", "create_studio_client_engagement", "list_studio_client_engagements", "setup_studio_archive", "configure_studio_archive", "diagnose_studio_archive_access", "configure_studio_archive_client", "refresh_studio_archive", "search_studio_archive", "open_studio_archive_source", "check_studio_import_sources", "import_studio_client_document", "verify_studio_client_inputs"]);
const excluded = { has: (name) => !allowed.has(name) };
const caseTool = {
  name: "clara_archive_case", title: "Create or resume the engagement's Clara case",
  description: "Resolve one registered client and engagement to its durable Clara advisory case. Omit case_dir to resume. Supply an existing absolute case_dir only for explicit first-time binding; files are preserved. A new case requires objective. Returned case_dir is used by the existing advisory case director.",
  inputSchema: { type: "object", properties: Object.fromEntries(["client_id", "engagement_id", "case_dir", "objective", "audience", "output_language"].map(key => [key, {type:"string", minLength:1}])), required:["client_id", "engagement_id"], additionalProperties:false },
  annotations: {readOnlyHint:false, destructiveHint:false, idempotentHint:true, openWorldHint:false}
};
function caseResult(args) {
  const os = require("node:os");
  const runtime = process.env.MPARANZA_RUNTIME_ROOT || (process.platform === "win32" ? path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData/Local"), "mpr") : path.join(os.homedir(), ".local/share/mparanza/runtime"));
  const managed = path.join(runtime, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const python = process.env.VERA_STUDIO_ARCHIVE_PYTHON || (fs.existsSync(managed) ? managed : (process.platform === "win32" ? "python" : "python3"));
  const result = spawnSync(python, ["-X", "utf8", path.join(__dirname, "clara_studio_archive.py")], {input:JSON.stringify(args), encoding:"utf8", env:process.env, maxBuffer:2000000});
  if (result.error) return {isError:true, content:[{type:"text", text:result.error.message}]};
  try { const payload = JSON.parse(result.stdout); return {isError:result.status !== 0, content:[{type:"text", text:JSON.stringify(payload)}], structuredContent:payload}; }
  catch { return {isError:true, content:[{type:"text", text:"Clara case could not be opened. Check the configured Python runtime."}]}; }
}
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
  process.stderr.write(`Clara Studio Archive not found: ${serverPath}\n`);
  process.exit(2);
}

const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
  env: { ...process.env, VERA_COMPONENT_HOST: "1", CLARA_ARCHIVE_HOST: "1" },
  stdio: ["pipe", "pipe", "inherit"],
});
const listRequests = new Set();
const panelRequests = new Map();
const panelOnly = process.env.CLARA_ARCHIVE_PANEL_ONLY === "1";
// A changed view must not reuse a retained global-sidebar resource.
const panelRevision = createHash("sha256")
  .update(fs.readFileSync(path.join(pluginRoot, "assets", "studio-archive.html")))
  .digest("hex").slice(0, 16);
const panelUri = `ui://clara/studio-archive-${panelRevision}.html`;
const panelMime = "text/html;profile=mcp-app";
const panelIcon = {
  src: "data:image/svg+xml;base64," + fs.readFileSync(path.join(pluginRoot, "assets", "icon.svg")).toString("base64"),
  mimeType: "image/svg+xml",
  sizes: ["24x24"],
};
const panelResource = { uri: panelUri, name: "Clara · Archivio dello studio", mimeType: panelMime };
const panelTools = [
  {
    name: "clara_archive_open",
    title: panelResource.name,
    icons: [panelIcon],
    description: "Open Clara’s local Studio Archive directory in Claude.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true },
    _meta: {
      ui: { resourceUri: panelUri, visibility: ["app", "model"] },
      "openai/ui": { entrypoints: [{ type: "global" }, { type: "thread" }] },
    },
  },
  {
    name: "clara_archive_list_matters",
    description: "List the matter labels for one selected registered client inside the Archive panel.",
    inputSchema: { type: "object", properties: { client_id: { type: "string", minLength: 1 } }, required: ["client_id"], additionalProperties: false },
    annotations: { readOnlyHint: true },
    _meta: { ui: { visibility: ["app"] } },
  },
];

function panelResult(name, result) {
  const data = result?.structuredContent;
  if (result?.isError || !data) {
    return { content: [{ type: "text", text: "Il pannello mostra lo stato dell’archivio di Clara." }], _meta: { archive: { error: "archive_unavailable" } } };
  }
  const archive = name === "clara_archive_open"
    ? { configured: data.configured, clients: (data.clients ?? [])
        .map(({ client_id, display_name, registration_status }) => ({ client_id, display_name, registration_status })) }
    : { engagements: (data.engagements ?? []).map(({ engagement_id, label, status }) => ({ engagement_id, label, status })) };
  return { content: [{ type: "text", text: "Archivio di Clara pronto nel pannello." }], _meta: { archive } };
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function projectTool(tool) {
  const filtered = structuredClone(tool);
  if (filtered.name === "prepare_studio_client_workflow") {
    filtered.inputSchema.properties.workflow_id.enum = workflows;
  }
  if (filtered.title) filtered.title = filtered.title.replaceAll("Vera", "Clara");
  if (descriptions[tool.name]) filtered.description = descriptions[tool.name];
  return filtered;
}

const childLines = readline.createInterface({ input: child.stdout });
childLines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    process.stderr.write("Clara Studio Archive returned invalid JSON.\n");
    return;
  }
  const panelRequest = panelRequests.get(message.id);
  if (panelRequest) {
    panelRequests.delete(message.id);
    send({ jsonrpc: "2.0", id: message.id, result: panelResult(panelRequest, message.result) });
    return;
  }
  if (listRequests.delete(message.id)) {
    const tools = message.result?.tools;
    if (Array.isArray(tools)) {
      message.result.tools = panelOnly
        ? panelTools
        : [...tools.filter((tool) => !excluded.has(tool.name)).map(projectTool), caseTool];
    }
  } else if (message.result?.serverInfo?.name === "vera-studio-archive") {
    message.result.serverInfo.name = "clara-studio-archive";
    message.result.serverInfo.icons = [panelIcon];
    if (panelOnly) message.result.capabilities.resources = {};
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
  if (message.method === "resources/list") {
    send({ jsonrpc: "2.0", id: message.id, result: { resources: panelOnly ? [panelResource] : [] } });
    return;
  }
  if (panelOnly && message.method === "resources/read" && message.params?.uri === panelUri) {
    const text = fs.readFileSync(path.join(pluginRoot, "assets", "studio-archive.html"), "utf8")
      .replace("__FONT__", fs.readFileSync(path.join(pluginRoot, "assets", "InstrumentSans-Regular.ttf")).toString("base64"))
      .replace("__FONT_BOLD__", fs.readFileSync(path.join(pluginRoot, "assets", "InstrumentSans-SemiBold.ttf")).toString("base64"));
    send({ jsonrpc: "2.0", id: message.id, result: { contents: [{
      uri: panelUri, mimeType: panelMime, text,
      _meta: {
        ui: { prefersBorder: false, csp: { connectDomains: [], resourceDomains: [] } },
        "openai/ui": { preferredDisplayMode: "fullscreen", availableDisplayModes: ["fullscreen"] },
      },
    }] } });
    return;
  }
  if (message.method === "tools/list") {
    if (message.id != null) listRequests.add(message.id);
  }
  if (message.method === "tools/call") {
    const toolName = message.params?.name;
    const workflowId = message.params?.arguments?.workflow_id;
    if (!panelOnly && toolName === caseTool.name) {
      send({jsonrpc:"2.0", id:message.id, result:caseResult(message.params.arguments || {})}); return;
    }
    if (toolName === "clara_archive_open" || toolName === "clara_archive_list_matters") {
      const clientId = message.params.arguments?.client_id;
      if (toolName === "clara_archive_list_matters" && (typeof clientId !== "string" || !clientId.trim())) {
        send({ jsonrpc: "2.0", id: message.id, error: { code: -32602, message: "Select a registered client." } });
        return;
      }
      panelRequests.set(message.id, toolName);
      const params = toolName === "clara_archive_open"
        ? { name: "list_studio_archive_clients", arguments: {} }
        : { name: "list_studio_client_engagements", arguments: { client_id: clientId } };
      child.stdin.write(JSON.stringify({ ...message, params }) + "\n");
      return;
    }
    if (panelOnly || typeof toolName !== "string" || excluded.has(toolName) || toolName.startsWith("clara_assurance_")) {
      send({
        jsonrpc: "2.0",
        id: message.id ?? null,
        error: { code: -32601, message: "Tool not available in Clara." },
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
        error: { code: -32602, message: "Workflow not available in Clara." },
      });
      return;
    }
  }
  child.stdin.write(`${line}\n`);
});
clientLines.on("close", () => child.stdin.end());

child.on("error", (error) => {
  process.stderr.write(`Could not start Clara Studio Archive: ${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

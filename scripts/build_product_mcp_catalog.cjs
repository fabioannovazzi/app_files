"use strict";

const fs = require("node:fs");
const path = require("node:path");

// The module-local servers also ship independently. In the Vera distribution
// their review engines stay callable by the owning editor, but no sibling
// renderer is advertised alongside the one archived-work entry point.
const companionSurfaces = {
  veraNativeWorkspace: "ui://vera/workspace-v1.html",
  courseChats: "ui://vera/course-chats-v1.html",
  agenziaAcquisition: "ui://vera/agenzia-acquisition-v1.html",
  researchSources: "ui://vera/research-sources.html",
  studioWork: "ui://vera/studio-work-v1.html",
};

function projectVeraReview(service, config, routes) {
  const component = config.args?.at(-1);
  const allowed = companionSurfaces[service.name];
  const isComponent = Object.hasOwn(routes, component);
  const unwanted = uri => typeof uri === "string" && uri.startsWith("ui://") && uri !== allowed;
  // Standalone component editors are not Vera entry points. An entirely new
  // service needs an explicit product decision before it can show another UI.
  if (!isComponent && [...service.resources, ...(service.resourceTemplates || [])]
      .some(row => unwanted(row.uri || row.uriTemplate))) {
    throw new Error("Unassigned Vera UI resource in " + service.name);
  }
  service.resources = service.resources.filter(row => !unwanted(row.uri));
  service.resourceTemplates = (service.resourceTemplates || []).filter(row => !unwanted(row.uriTemplate));
  service.tools = service.tools.filter(tool => {
    if (isComponent && tool.name.startsWith("validate_") && /render_|before rendering|prima della visualizzazione/i.test(tool.description)) {
      tool.description = "Validate the existing component review using its declared inputs." +
        (routes[component] ? " Open the saved work with vera_open_review only if interactive review is needed." : " Deliver the result in chat.");
    }
    const meta = tool._meta || {};
    if (![meta.ui?.resourceUri, meta["ui/resourceUri"], meta["openai/outputTemplate"]].some(unwanted)) return true;
    if (!isComponent) throw new Error("Unassigned Vera renderer " + tool.name);
    if (tool.name.startsWith("render_")) return false;
    delete meta.ui?.resourceUri;
    delete meta["ui/resourceUri"];
    delete meta["openai/outputTemplate"];
    return true;
  });
  if (isComponent && !allowed) {
    service.initialize.instructions = routes[component] === null
      ? "Deliver this Vera workflow in chat and its documents."
      : "Deliver results in chat. For interactive review use vera_open_review on the saved work in this chat. Do not launch a browser or another widget.";
  }
}

async function build(root, runtime) {
  const { ServiceClient } = require(path.join(root, "scripts/mcp_service_client.cjs"));
  const configs = JSON.parse(fs.readFileSync(path.join(root, "mcp-services.json"), "utf8")).mcpServers;
  const manifestPath = [".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "plugin.json"]
    .map(name => path.join(root, name)).find(file => fs.existsSync(file));
  const { name: product, version } = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const routes = product === "vera" && configs.veraNativeWorkspace
    ? JSON.parse(fs.readFileSync(path.join(root, "ui/review-routes.json"), "utf8")) : null;
  const services = [];
  const names = { tools: new Set(), resources: new Set(), prompts: new Set() };
  for (const [name, config] of Object.entries(configs)) {
    const client = new ServiceClient(root, name, config, { env: {
      PATH: process.env.PATH, SystemRoot: process.env.SystemRoot,
      HOME: runtime, USERPROFILE: runtime, MPARANZA_RUNTIME_ROOT: runtime,
      MPARANZA_INCIDENT_STATE_DIR: path.join(runtime, "incidents"),
      MPARANZA_INCIDENT_DEVICE_DIR: path.join(runtime, "device"),
      VERA_REPORTING_STATE_DIR: path.join(runtime, "reporting"),
      MPARANZA_INCIDENT_DELIVERY: "local-only",
    } });
    try {
      const initialize = await client.initialize({
        protocolVersion: "2024-11-05", capabilities: {},
        clientInfo: { name: "product-catalog-builder", version: "1" },
      });
      const service = { name, initialize, tools: [], resources: [], resourceTemplates: [], prompts: [] };
      for (const [method, field, capability] of [
        ["tools/list", "tools", "tools"], ["resources/list", "resources", "resources"],
        ["resources/templates/list", "resourceTemplates", "resources"], ["prompts/list", "prompts", "prompts"],
      ]) {
        if (!initialize.capabilities[capability]) continue;
        let cursor;
        const cursors = new Set();
        do {
          const reply = await client.call(method, cursor ? { cursor } : {}, { timeout: 10000 });
          if (reply.error?.code === -32601 && field !== "tools") break;
          // Older owned services return these exact unsupported-method replies
          // for optional templates. Do not discard arbitrary discovery errors.
          const unsupported = new Set(["Unsupported method", `Unsupported method: ${method}`,
            "Unknown method or resource", "Unsupported research-source method"]);
          if (field === "resourceTemplates" && (
            unsupported.has(reply.error?.message) ||
            (reply.result?.isError && unsupported.has(reply.result.content?.[0]?.text))
          )) break;
          if (reply.error || !Array.isArray(reply.result?.[field]))
            throw new Error(`${name}: invalid ${method}: ${JSON.stringify(reply.error || reply.result)}`);
          for (const item of reply.result[field]) {
            const key = field === "resources" ? item.uri : item.name;
            if (names[field]?.has(key)) throw new Error(`Duplicate ${field}: ${key}`);
            names[field]?.add(key);
            service[field].push(item);
          }
          cursor = reply.result.nextCursor;
          if (cursor && cursors.has(cursor)) throw new Error(`${name}: repeated discovery cursor`);
          cursors.add(cursor);
        } while (cursor);
      }
      if (routes) projectVeraReview(service, config, routes);
      services.push(service);
    } finally {
      client.close();
      const timer = setTimeout(() => client.child.kill("SIGTERM"), 2000);
      await client.exited;
      clearTimeout(timer);
    }
  }
  return { schema_version: 1, product, version, services };
}

module.exports = { build, projectVeraReview };
if (require.main === module) build(path.resolve(process.argv[2]), path.resolve(process.argv[3]))
  .then(catalog => process.stdout.write(JSON.stringify(catalog, null, 2) + "\n"))
  .catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });

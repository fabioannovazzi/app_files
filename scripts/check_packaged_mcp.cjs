"use strict";

// Exercise the packaged launchers: source-tree inspection cannot prove startup.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const readline = require("node:readline");
const crypto = require("node:crypto");

function validIncidentTools(tools, product = "vera") {
  // Tool names are an exact transport contract, not a diagnostic classifier.
  const expected = new Set(["register", "report", "status", "outcome", "progress"].map(action => `${product}_incident_${action}`));
  // A release is built before its API deployment. Accept the existing incident
  // contract or the complete usage extension, never a half-deployed pair.
  if (product !== "vera" || (Array.isArray(tools) && tools.some(tool => typeof tool?.name === "string" && tool.name.startsWith(`${product}_workflow_`)))) {
    expected.add(`${product}_workflow_record`);
    expected.add(`${product}_workflow_status`);
  }
  // The receipt fallback may be deployed after its package has been built.
  // Admit that one explicit extension while retaining the full base contract.
  if (Array.isArray(tools) && tools.some(tool => tool?.name === `${product}_workflow_stamp`))
    expected.add(`${product}_workflow_stamp`);
  return Array.isArray(tools) && tools.length === expected.size &&
    tools.every(tool => tool && tool.inputSchema?.type === "object" && expected.delete(tool.name)) &&
    expected.size === 0;
}

async function checkRemoteServer(name, config) {
  const product = ["vera", "clara", "lucia"].find(value => name === `${value}Incidents`);
  let url;
  try { url = new URL(config.url); } catch { return {name, error: "Invalid remote MCP URL"}; }
  if (!product || url.protocol !== "https:" || url.username || url.password || url.search || url.hash ||
      url.origin !== "https://mparanza.com" || url.pathname !== `/mcp/${product}-incidents`) {
    return {name, error: "Remote MCP endpoint is outside the reviewed incident contract"};
  }
  if (process.env.MPARANZA_VERIFY_REMOTE_MCP !== "1") {
    return {name, transport: "http", contractValid: true, remoteRuntimeChecked: false};
  }
  let credentials = null;
  let metadata = null;
  try {
    const fixedFetch = async (target, options = {}) => {
      const response = await fetch(target, {...options, redirect: "manual", signal: AbortSignal.timeout(10000)});
      return response;
    };
    const advertised = await fixedFetch("https://mparanza.com/.well-known/oauth-authorization-server");
    if (!advertised.ok) throw new Error("OAuth discovery unavailable");
    metadata = await advertised.json();
    const prefix = "https://mparanza.com/oauth/vera-incidents/";
    if (metadata.issuer !== url.origin || metadata.registration_endpoint !== prefix + "register" ||
        metadata.authorization_endpoint !== prefix + "authorize" || metadata.token_endpoint !== prefix + "token" ||
        metadata.revocation_endpoint !== prefix + "revoke") throw new Error("Unexpected incident OAuth metadata");
    const callback = "http://127.0.0.1:49191/vera-release-check";
    const registered = await fixedFetch(metadata.registration_endpoint, {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({redirect_uris: [callback], token_endpoint_auth_method: "none"})});
    if (!registered.ok) throw new Error("Anonymous verifier registration failed");
    const {client_id} = await registered.json();
    const verifier = crypto.randomBytes(48).toString("base64url");
    const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    const state = crypto.randomBytes(32).toString("base64url");
    const authorize = new URL(metadata.authorization_endpoint);
    authorize.search = new URLSearchParams({client_id, redirect_uri: callback, response_type: "code", code_challenge_method: "S256",
      code_challenge: challenge, resource: url.href, scope: `${product}:incidents`, state}).toString();
    const authorized = await fixedFetch(authorize);
    if (authorized.status !== 302) throw new Error("Anonymous verifier authorization failed");
    const returned = new URL(authorized.headers.get("location"));
    if (returned.origin + returned.pathname !== callback || returned.searchParams.get("state") !== state ||
        !returned.searchParams.get("code")) throw new Error("Invalid verifier callback");
    const tokens = await fixedFetch(metadata.token_endpoint, {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: new URLSearchParams({grant_type: "authorization_code", client_id, redirect_uri: callback,
        code: returned.searchParams.get("code"), code_verifier: verifier, resource: url.href})});
    if (!tokens.ok) throw new Error("Anonymous verifier token exchange failed");
    credentials = {...await tokens.json(), client_id};
    if (!credentials.access_token || !credentials.refresh_token) throw new Error("Incomplete verifier grant");
    const rpc = async (id, method, params) => {
      const response = await fetch(url, {method: "POST", redirect: "error",
        headers: {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Authorization": `Bearer ${credentials.access_token}`},
        body: JSON.stringify({jsonrpc: "2.0", id, method, params}), signal: AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error(`Remote MCP HTTP ${response.status}`);
      const text = await response.text();
      if (text.length > 1000000) throw new Error("Remote MCP response exceeds handshake limit");
      const result = JSON.parse(text);
      if (result.error) throw new Error("Remote MCP protocol error");
      return result.result;
    };
    const initialized = await rpc(1, "initialize", {protocolVersion: "2025-03-26", capabilities: {}, clientInfo: {name: "package-release-verifier", version: "1"}});
    if (!initialized.serverInfo?.name || !initialized.capabilities?.tools) throw new Error("Invalid remote initialize response");
    const listed = await rpc(2, "tools/list", {});
    if (!validIncidentTools(listed.tools, product)) throw new Error("Invalid remote incident tools/list");
    return {name, transport: "http", tools: listed.tools.length, remoteRuntimeChecked: true};
  } catch (error) { return {name, error: error.message}; }
  finally {
    if (credentials && metadata) {
      const revoked = await fetch(metadata.revocation_endpoint, {method: "POST", redirect: "error",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: new URLSearchParams({client_id: credentials.client_id, token: credentials.refresh_token}), signal: AbortSignal.timeout(10000)});
      if (!revoked.ok) throw new Error("Verifier credential revocation failed");
    }
  }
}

function checkServer(root, name, config, runtime) {
  if (["http", "streamable-http"].includes(config.type) || config.serverUrl) return checkRemoteServer(name, {...config, url: config.url || config.serverUrl});
  return new Promise((resolve) => {
    if (config.command !== "node" || !Array.isArray(config.args)) {
      resolve({
        name,
        error: "Unsupported local MCP launcher; add a runtime check before release",
      });
      return;
    }
    const expand = (value) => value
      .replaceAll("${PLUGIN_ROOT}", root)
      .replaceAll("${CLAUDE_PLUGIN_ROOT}", root)
      .replaceAll("${CODEX_PLUGIN_ROOT}", root);
    const child = spawn(process.execPath, config.args.map(expand), {
      cwd: path.resolve(root, expand(config.cwd || ".")),
      env: {
        PATH: process.env.PATH,
        SystemRoot: process.env.SystemRoot,
        MPARANZA_RUNTIME_ROOT: runtime,
        ...Object.fromEntries(
          Object.entries(config.env || {}).map(([key, value]) => [key, expand(value)]),
        ),
      },
      detached: process.platform !== "win32",
      stdio: ["pipe", "pipe", "pipe"],
    });
    let settled = false;
    let initialized = false;
    let tools = null;
    let stderr = "";
    let outputBytes = 0;
    const stop = () => {
      if (!child.pid) return;
      try {
        if (process.platform === "win32") {
          spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
            stdio: "ignore",
          });
        } else {
          process.kill(-child.pid, "SIGKILL");
        }
      } catch (error) {
        if (error.code !== "ESRCH") throw error;
      }
    };
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      stop();
      resolve(error ? { name, error, stderr } : { name, tools: tools.length });
    };
    const timer = setTimeout(() => finish("MCP handshake timed out"), 10000);
    const send = (payload) => child.stdin.write(`${JSON.stringify(payload)}\n`);
    child.on("error", (error) => finish(error.message));
    child.stdin.on("error", (error) => finish(error.message));
    child.stderr.on("data", (data) => {
      stderr = (stderr + data).slice(-8000);
    });
    child.stdout.on("data", (data) => {
      outputBytes += data.length;
      if (outputBytes > 8_000_000) finish("MCP output exceeds handshake limit");
    });
    const lines = readline.createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      if (settled) return;
      let response;
      try {
        response = JSON.parse(line);
      } catch {
        finish("Invalid JSON on MCP stdout");
        return;
      }
      if (!response || response.jsonrpc !== "2.0") {
        finish("Invalid JSON-RPC response");
        return;
      }
      if (response.id === 1) {
        if (
          initialized || response.error || !response.result?.serverInfo?.name ||
          !response.result?.serverInfo?.version || !response.result?.protocolVersion ||
          !response.result?.capabilities?.tools
        ) {
          finish("Invalid initialize response");
          return;
        }
        initialized = true;
        send({ jsonrpc: "2.0", method: "notifications/initialized" });
        send({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
      } else if (response.id === 2) {
        const candidate = response.result?.tools;
        if (
          !initialized || response.error || !Array.isArray(candidate) || !candidate.length ||
          candidate.some((tool) => !tool || typeof tool.name !== "string" ||
            !tool.name || tool.inputSchema?.type !== "object") ||
          new Set(candidate.map((tool) => tool.name)).size !== candidate.length ||
          response.result.nextCursor
        ) {
          finish("Invalid or incomplete tools/list response");
          return;
        }
        tools = candidate;
        child.stdin.end();
      }
    });
    child.on("close", (code) => finish(
      code === 0 && tools ? null : `Server exited ${code} before a complete handshake`,
    ));
    send({
      jsonrpc: "2.0", id: 1, method: "initialize",
      params: {
        protocolVersion: "2024-11-05", capabilities: {},
        clientInfo: { name: "mparanza-release-check", version: "1.0.0" },
      },
    });
  });
}

async function main() {
  const root = path.resolve(process.argv[2]);
  const config = JSON.parse(fs.readFileSync(path.join(root, process.argv[3] || ".mcp.json"), "utf8"));
  const servers = config.mcpServers;
  if (!servers || !Object.keys(servers).length) {
    throw new Error("Empty MCP server configuration");
  }
  const runtime = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mparanza-release-runtime-")));
  const results = [];
  try {
    for (const [name, config] of Object.entries(servers)) {
      results.push(await checkServer(root, name, config, runtime));
    }
    process.stdout.write(`${JSON.stringify(results)}\n`);
    process.exitCode = results.some((result) => result.error) ? 1 : 0;
  } finally {
    // Only this check's private code store is writable for deletion. Never
    // touch the developer's installed runtime or retained professional state.
    function writable(directory) {
      fs.chmodSync(directory, 0o700);
      for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
        const file = path.join(directory, entry.name);
        if (entry.isDirectory()) writable(file);
        else if (!entry.isSymbolicLink()) fs.chmodSync(file, 0o600);
      }
    }
    writable(runtime);
    fs.rmSync(runtime, {recursive:true, force:true});
  }
}

module.exports = { validIncidentTools };
if (require.main === module) main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});

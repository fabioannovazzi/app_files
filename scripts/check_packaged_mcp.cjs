"use strict";

// Exercise the packaged launchers: source-tree inspection cannot prove startup.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const readline = require("node:readline");
function checkServer(root, name, config, runtime) {
  if (["http", "streamable-http"].includes(config.type) || config.serverUrl) {
    return Promise.resolve({name, error: "Remote reporting MCP is retired; use HTTPS reporting"});
  }
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
    if (fs.existsSync(path.join(root, "mcp-services.json"))) {
      // Re-query the exact extracted workers: a valid static catalogue alone
      // cannot prove that every advertised function still has a working owner.
      const { build } = require("./build_vera_mcp_catalog.cjs");
      const actual = await build(root, runtime);
      const expected = JSON.parse(fs.readFileSync(path.join(root, "mcp-catalog.json"), "utf8"));
      const equal = require("node:util").isDeepStrictEqual(actual, expected);
      results.push(equal
        ? { name: "vera-catalog", services: actual.services.length, tools: actual.services.reduce((n, service) => n + service.tools.length, 0) }
        : { name: "vera-catalog", error: "Packaged service discovery differs from advertised catalogue" });
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

if (require.main === module) main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});

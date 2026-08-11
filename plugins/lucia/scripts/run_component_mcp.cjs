#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const COMPONENTS = new Set([
  "prompt-optimizer",
  "deep-research-validator",
]);

const component = process.argv[2];
if (!COMPONENTS.has(component)) {
  process.stderr.write(`Unknown Lucia workflow: ${component || "<missing>"}\n`);
  process.exit(2);
}

const pluginRoot = path.resolve(__dirname, "..");
const packagedRoot = path.join(pluginRoot, "modules", component);
const sourceRoot = path.resolve(pluginRoot, "..", component);
const componentRoot = fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot;
const serverCandidates = [
  path.join(componentRoot, "mcp", "server.cjs"),
  path.join(componentRoot, "scripts", "review_mcp_server.cjs"),
];
const serverPath = serverCandidates.find((candidate) => fs.existsSync(candidate));

if (!serverPath) {
  process.stderr.write(
    `MCP server not found for ${component}: ${serverCandidates.join(", ")}\n`,
  );
  process.exit(2);
}

const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
  env: { ...process.env, LUCIA_COMPONENT_HOST: "1" },
  stdio: "inherit",
});

child.on("error", (error) => {
  process.stderr.write(`Could not start ${component}: ${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

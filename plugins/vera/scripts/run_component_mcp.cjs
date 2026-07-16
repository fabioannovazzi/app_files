#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const COMPONENTS = new Set([
  "audit-reconciliation",
  "client-intake",
  "journal-sampling",
  "check-entries",
  "journal-bank-reconciliation",
  "report-builder",
  "concordato-plan-review",
  "prompt-optimizer",
  "deep-research-validator",
  "previdenza-inps",
  "registro-imprese-sari",
]);

const component = process.argv[2];
if (!COMPONENTS.has(component)) {
  process.stderr.write(`Unknown Vera module: ${component || "<missing>"}\n`);
  process.exit(2);
}

const pluginRoot = path.resolve(__dirname, "..");
const packagedRoot = path.join(pluginRoot, "modules", component);
const sourceRoot = path.resolve(pluginRoot, "..", component);
const componentRoot = fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot;
const serverPath = path.join(componentRoot, "mcp", "server.cjs");

if (!fs.existsSync(serverPath)) {
  process.stderr.write(`MCP server not found for ${component}: ${serverPath}\n`);
  process.exit(2);
}

const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
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

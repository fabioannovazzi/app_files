#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { bridge } = require("./archive_emission_mcp.cjs");

const COMPONENTS = new Set([
  "browser-automation",
  "archive-organization",
  "open-item-reconciliation",
  "client-file-preparation",
  "new-client",
  "journal-sampling",
  "check-entries",
  "journal-bank-reconciliation",
  "sales-plan",
  "variance-analysis",
  "financial-analysis",
  "report-builder",
  "concordato-plan-review",
  "prompt-optimizer",
  "deep-research-validator",
  "previdenza-inps",
  "registro-imprese-sari",
  "bilancio-xbrl-it",
  "studio-archive",
]);

const component = process.argv[2];
if (!COMPONENTS.has(component)) {
  process.stderr.write(`Unknown Vera module: ${component || "<missing>"}\n`);
  process.exit(2);
}

const pluginRoot = path.resolve(__dirname, "..");
const reportingScope = JSON.parse(fs.readFileSync(path.join(pluginRoot, "usage/pipelines.json"), "utf8"))
  .model_data_reporting.component_pipelines;
const recordsOutput = Object.prototype.hasOwnProperty.call(reportingScope, component);
const packagedRoot = path.join(pluginRoot, "modules", component);
const sourceRoot = path.resolve(pluginRoot, "..", component);
const prepared = require("./verify_mcp_package.cjs").componentRoot(
  pluginRoot, component, fs.existsSync(packagedRoot) ? packagedRoot : sourceRoot,
);
const componentRoot = prepared.root;
process.on("exit", () => prepared.cleanup());
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

const lease = Number(process.env.VERA_CODE_LEASE_FD);
const descriptors = recordsOutput ? ["pipe", "pipe", "inherit"] : ["inherit", "inherit", "inherit"];
if (Number.isInteger(lease) && lease >= 3) descriptors.push(lease);
const child = spawn(process.execPath, [serverPath, "--stdio"], {
  cwd: componentRoot,
  env: { ...process.env, VERA_COMPONENT_HOST: "1", VERA_REPORTING_INTERNAL: "1", ...(descriptors.length > 3 ? { VERA_CODE_LEASE_FD: "3" } : {}) },
  stdio: descriptors,
});

if (recordsOutput) bridge(child, component, pluginRoot);
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => { if (child.exitCode === null) child.kill(signal); });

child.on("error", (error) => {
  process.stderr.write(`Could not start ${component}: ${error.message}\n`);
  process.exit(1);
});

child.on("close", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

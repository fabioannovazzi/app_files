#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_NAME = "vera-sales-plan";
const SERVER_VERSION = PLUGIN_MANIFEST.version;
const TOOL_NAME = "describe_vera_sales_plan";
const ARTIFACTS = [
  "sales_plan_scenario.csv",
  "assumption_application_ledger.csv",
  "scenario_summary.csv",
  "reconciliation.json",
  "prepared_evidence_manifest.json",
  "model_use_manifest.json",
  "plan_execution_receipt.json",
];

function response(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function errorResponse(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function tools() {
  return [
    {
      name: TOOL_NAME,
      title: "Describe Vera Plan",
      description:
        "Return the reviewed Actual-to-Plan recipe and its deterministic artifacts. This tool does not calculate or approve a Plan.",
      inputSchema: {
        type: "object",
        properties: {},
        additionalProperties: false,
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
      },
    },
  ];
}

function handle(message) {
  if (message.method === "notifications/initialized") return null;
  if (message.method === "initialize") {
    return response(message.id, {
      protocolVersion: "2025-03-26",
      capabilities: { tools: {} },
      serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
    });
  }
  if (message.method === "tools/list") {
    return response(message.id, { tools: tools() });
  }
  if (message.method === "tools/call") {
    if (message.params?.name !== TOOL_NAME) {
      return errorResponse(message.id, -32601, "Unknown tool");
    }
    const payload = {
      workflow: "vera.sales_plan",
      display_name: "Plan",
      recipe_id: "sales_plan_from_reviewed_actuals.v2",
      artifacts: ARTIFACTS,
      report_ready: false,
      boundary:
        "Vera applies only reviewed assumptions; the commercialista owns their meaning and approval.",
    };
    return response(message.id, {
      content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
      structuredContent: payload,
      isError: false,
    });
  }
  if (message.id == null) return null;
  return errorResponse(message.id, -32601, "Method not found");
}

const input = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

input.on("line", (line) => {
  if (!line.trim()) return;
  try {
    const result = handle(JSON.parse(line));
    if (result != null) process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify(errorResponse(null, -32700, String(error.message || error)))}\n`,
    );
  }
});

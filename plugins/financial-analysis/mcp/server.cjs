#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PLUGIN_MANIFEST = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), "utf8"),
);
const SERVER_NAME = "vera-financial-analysis";
const SERVER_VERSION = PLUGIN_MANIFEST.version;
const TOOL_NAME = "describe_vera_financial_analysis";
const PACKS = [
  "monthly_pnl",
  "working_capital",
  "customer_concentration",
  "quality_of_earnings",
  "net_debt",
  "normalized_working_capital",
  "capex",
  "deal_bridges",
];
const CONTRACTS = [
  "data_package_manifest",
  "dataset_contract",
  "relationship_contract",
  "crosswalk_manifest",
  "analysis_pack_request",
  "reconciliation_result",
  "prepared_evidence_manifest",
  "fdd_preparation_case",
  "fdd_calculation_result",
  "fdd_metric_receipt",
  "contingent_liability_register",
  "financial_issue_register",
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
      title: "Describe Vera Financial Analysis",
      description:
        "Return the registered preparation packs and case-level contract types. This tool does not run calculations or approve conclusions.",
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
      workflow: "vera.financial_analysis",
      registered_packs: PACKS,
      contract_types: CONTRACTS,
      report_ready: false,
      boundary:
        "The workflow validates prepared evidence; professional accounting judgment remains external.",
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

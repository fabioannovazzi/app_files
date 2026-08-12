"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

const ROOT = path.resolve(__dirname, "..");
const WIDGET_URI = "ui://widget/apertura-pratica-review.html";
const WIDGET = fs.readFileSync(path.join(ROOT, "assets", "apertura-pratica-review-widget.html"), "utf8");

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function tools() {
  return [{
    name: "render_apertura_pratica_review",
    title: "Review Apertura pratica",
    description: "Render the current legal matter-opening review payload. Saving and applying decisions remain explicit file-backed steps.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: { review_payload: { type: "object" } },
      required: ["review_payload"],
    },
    _meta: {
      ui: { resourceUri: WIDGET_URI, visibility: ["model"] },
      "ui/resourceUri": WIDGET_URI,
      "openai/outputTemplate": WIDGET_URI,
      "openai/widgetAccessible": true,
    },
  }];
}

const lines = readline.createInterface({ input: process.stdin });
lines.on("line", (line) => {
  let request;
  try { request = JSON.parse(line); } catch { send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }); return; }
  const id = request.id ?? null;
  if (request.method === "initialize") {
    send({ jsonrpc: "2.0", id, result: { protocolVersion: request.params?.protocolVersion || "2024-11-05", capabilities: { tools: {}, resources: {} }, serverInfo: { name: "lucia-apertura-pratica-review", version: "0.1.0" }, instructions: "Render review only. Persist decisions through the package's explicit save and apply workflow." } });
  } else if (request.method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools: tools() } });
  } else if (request.method === "resources/list") {
    send({ jsonrpc: "2.0", id, result: { resources: [{ uri: WIDGET_URI, name: "Apertura pratica review", mimeType: "text/html;profile=mcp-app" }] } });
  } else if (request.method === "resources/read" && request.params?.uri === WIDGET_URI) {
    send({ jsonrpc: "2.0", id, result: { contents: [{ uri: WIDGET_URI, mimeType: "text/html;profile=mcp-app", text: WIDGET, _meta: { "openai/widgetDescription": "Read-only lawyer review of the current matter-opening payload.", "openai/widgetPrefersBorder": false, "openai/widgetCSP": { connect_domains: [], resource_domains: [] } } }] } });
  } else if (request.method === "tools/call" && request.params?.name === "render_apertura_pratica_review") {
    const review = request.params?.arguments?.review_payload;
    if (!review || typeof review !== "object" || Array.isArray(review) || !Array.isArray(review.items)) {
      send({ jsonrpc: "2.0", id, error: { code: -32602, message: "review_payload with items is required" } });
      return;
    }
    send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text: `Prepared ${review.items.length} matter-opening review items.` }], structuredContent: { review_payload: review }, _meta: { "openai/outputTemplate": WIDGET_URI } } });
  } else {
    send({ jsonrpc: "2.0", id, error: { code: -32601, message: "method not found" } });
  }
});

"use strict";

// Local transport for the existing widget and exact native review operations.
const http = require("node:http");
const crypto = require("node:crypto");
const path = require("node:path");

function start({ contextPath, readJson, callTool, preflightClientWorkflowRun, widget }) {
  const context = readJson(contextPath);
  const output = path.join(path.dirname(contextPath), "outputs");
  preflightClientWorkflowRun(output, context.run_id, true);
  const route = `/${crypto.randomBytes(24).toString("hex")}/`;
  const save = "save_registro_imprese_sari_decisions";
  const apply = "apply_registro_imprese_sari_decisions";
  let token;
  let origin;

  function renderPayload() {
    const gate = preflightClientWorkflowRun(output, context.run_id, true);
    const validated = callTool("validate_registro_imprese_sari_review", {
      client_engagement: contextPath,
      run_intake: readJson(path.join(output, "run_intake.json")),
      review_payload: readJson(path.join(output, "review_payload.json")),
    });
    if (!validated.review_reference) throw new Error("Stored review could not be bound");
    const payload = callTool("render_registro_imprese_sari_review", {
      persistence_token: validated.review_reference.persistence_token,
    });
    token = payload.persistence_token;
    payload.local_read_only = gate.run_status !== "running";
    return payload;
  }

  function send(response, status, value, type = "application/json; charset=utf-8") {
    const body = type.startsWith("application/json") ? JSON.stringify(value) : value;
    response.writeHead(status, {
      "Content-Type": type,
      "Content-Length": Buffer.byteLength(body),
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    });
    response.end(body);
  }

  const server = http.createServer((request, response) => {
    if (request.headers.host !== new URL(origin).host) return send(response, 403, { error: "Invalid host" });
    if (request.method === "GET" && request.url === route) {
      try {
        const payload = JSON.stringify(renderPayload()).replace(/</g, "\\u003c");
        const bridge = `<script>window.openai={toolOutput:${payload},callTool:async(name,args)=>{
          const response=await fetch(${JSON.stringify(route + "call")},{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,arguments:args})});
          const result=await response.json();if(!response.ok)throw new Error(result.error);return result;
        }};</script>`;
        send(response, 200, widget.replace("<head>", "<head>" + bridge), "text/html; charset=utf-8");
      } catch (error) { send(response, 409, { error: error.message }); }
      return;
    }
    if (request.method !== "POST" || request.url !== route + "call") return send(response, 404, { error: "Not found" });
    if (request.headers.origin !== origin || request.headers["content-type"] !== "application/json") return send(response, 403, { error: "Same-origin JSON required" });
    const chunks = [];
    let bytes = 0;
    request.on("data", chunk => {
      bytes += chunk.length;
      if (bytes > 2_000_000) { request.destroy(); return; }
      chunks.push(chunk);
    });
    request.on("end", () => {
      try {
        const message = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        if (![save, apply].includes(message.name)) throw new Error("Unsupported review action");
        if (!message.arguments || message.arguments.persistence_token !== token) throw new Error("Stale review; reload this page");
        // Do not forward arbitrary run paths or payloads from browser requests.
        const result = callTool(message.name, {
          persistence_token: token,
          client_engagement: contextPath,
          review_payload: readJson(path.join(output, "review_payload.json")),
          decisions: message.arguments.decisions,
          decision_source: "local_review_widget",
        });
        send(response, 200, result);
      } catch (error) { send(response, 409, { error: error.message }); }
    });
  });
  server.listen(0, "127.0.0.1", () => {
    origin = `http://127.0.0.1:${server.address().port}`;
    process.stdout.write(JSON.stringify({ status: "serving", url: origin + route }) + "\n");
  });
  return server;
}

module.exports = { start };

"use strict";

// Fixed public service, one process per action. Opaque references never persist.
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

async function main() {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  const root = path.resolve(request.root);
  if (path.basename(root) !== "previdenza-inps" || !["read", "apply"].includes(request.operation)) throw new Error("Unsupported INPS service action");
  const child = spawn(process.execPath, [path.join(root, "mcp/server.cjs")], { cwd: root, env: process.env, stdio: ["pipe", "pipe", "pipe"] });
  const pending = new Map(); let sequence = 0;
  const fail = error => { for (const item of pending.values()) item.reject(error); pending.clear(); };
  child.on("error", fail); child.on("exit", () => fail(new Error("INPS service stopped"))); child.stderr.resume();
  const timer = setTimeout(() => { fail(new Error("INPS service timed out")); child.kill(); }, 60000);
  readline.createInterface({ input: child.stdout }).on("line", line => {
    try {
      if (Buffer.byteLength(line) > 2_000_000) throw new Error("INPS response exceeds the complete-content limit");
      const message = JSON.parse(line), item = pending.get(message.id);
      if (!item) return; pending.delete(message.id);
      const value = message.result?.structuredContent;
      if (message.error || message.result?.isError || !value || value.ok === false) item.reject(new Error(message.error?.message || value?.error || "INPS public service refused"));
      else item.resolve(value);
    } catch (error) { fail(error); child.kill(); }
  });
  const call = (name, args) => new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, { resolve, reject });
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } }) + "\n");
  });
  try {
    const validation = await call("validate_previdenza_inps_review", request.arguments);
    const reference = validation.review_reference?.persistence_token;
    let result;
    if (request.operation === "apply") {
      if (!reference) throw new Error("Actual INPS persistence authority required");
      result = await call("apply_previdenza_inps_decisions", { persistence_token: reference, client_engagement: request.arguments.client_engagement, ...request.decisions });
    } else result = await call("render_previdenza_inps_review", reference ? { persistence_token: reference, client_engagement: request.arguments.client_engagement } : request.arguments);
    process.stdout.write(JSON.stringify(result));
  } finally { clearTimeout(timer); child.kill(); }
}
main().catch(error => { process.stderr.write(error.message + "\n"); process.exitCode = 1; });

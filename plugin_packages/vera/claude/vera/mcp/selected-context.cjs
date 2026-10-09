"use strict";

// Use maintained public tools in one process; some opaque references are
// process-local. Component metadata stays in the local native read adapter.
// This bridge contains no professional field projection.
const fs = require("node:fs");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const { createHmac } = require("node:crypto");

async function selectedContext(request) {
  const names = {
    "check-entries": ["validate_check_entries_review", "get_check_entries_case_context"],
    "open-item-reconciliation": ["validate_open_item_reconciliation_review", "get_open_item_reconciliation_case_context"],
    "journal-bank-reconciliation": ["validate_journal_bank_review", "get_journal_bank_case_context"],
    "concordato-plan-review": ["validate_concordato_plan_review", "read_concordato_plan_review_items"],
  }[request.component];
  if (!names) throw new Error("Unsupported selected-context workflow");
  const child = spawn(process.execPath, [request.server, "--stdio"], {
    stdio: ["pipe", "pipe", "pipe"], env: process.env,
  });
  const pending = new Map();
  let nextId = 1;
  const fail = error => { for (const value of pending.values()) value.reject(error); pending.clear(); };
  const timer = setTimeout(() => { fail(new Error("Selected context timed out")); child.kill(); }, 30000);
  child.on("error", fail);
  child.on("exit", () => fail(new Error("Selected context service stopped")));
  child.stderr.resume();
  readline.createInterface({ input: child.stdout }).on("line", line => {
    try {
      if (Buffer.byteLength(line) > 8 * 1024 * 1024) throw new Error("Oversized engine response");
      const response = JSON.parse(line), waiter = pending.get(response.id);
      if (!waiter) return;
      pending.delete(response.id);
      const result = response.result?.structuredContent;
      if (response.error || response.result?.isError || !result || result.ok === false) {
        waiter.reject(new Error(response.error?.message || result?.error || "Selected context was refused"));
      } else if (waiter.widget) {
        const widget = response.result?._meta?.widget_payload;
        if (!widget || typeof widget !== "object" || Array.isArray(widget)) waiter.reject(new Error("Engine returned no component payload"));
        else waiter.resolve(widget);
      } else waiter.resolve(result);
    } catch (error) { fail(error); }
  });
  const call = (name, args, widget = false) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject, widget });
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } }) + "\n");
  });
  try {
    if (request.component === "concordato-plan-review") {
      const reference = { client_engagement: request.arguments.client_engagement, review_reference: request.arguments.review_reference };
      await call(names[0], reference);
      if (request.operation) {
        const operation = { read: "render_concordato_plan_review", save: "save_concordato_plan_decisions", apply: "apply_concordato_plan_decisions" }[request.operation];
        if (!operation) throw new Error("Unsupported reference-bound operation");
        return await call(operation, request.operation === "read" ? reference : request.arguments, request.operation === "read");
      }
      return await call(names[1], { ...request.arguments, item_ids: [request.item_id], limit: 1 });
    }
    const validated = await call(names[0], request.arguments);
    const token = validated.review_reference?.persistence_token;
    if (!token) throw new Error("Engine returned no review reference");
    // These maintained engines bind an opaque case handle to its exact local
    // item ID this way. The engine verifies it; a changed contract fails closed.
    const handle = "case-" + createHmac("sha256", token).update(request.item_id, "utf8").digest("base64url").slice(0, 18);
    return await call(names[1], { persistence_token: token, case_handles: [handle], include_exact_identifiers: false });
  } finally {
    clearTimeout(timer);
    child.stdin.end();
    child.kill();
  }
}

if (require.main === module) {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  selectedContext(request).then(result => process.stdout.write(JSON.stringify(result)))
    .catch(error => { process.stderr.write(error.message + "\n"); process.exitCode = 1; });
}

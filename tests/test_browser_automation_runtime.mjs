import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  canonicalJson,
  executeCapability,
  executionContractSha256,
} from "../plugins/browser-automation/scripts/capability_runtime.mjs";

function locatorKey(kind, role, value) {
  return `${kind}:${role ?? ""}:${value ?? ""}`;
}

class FakeNode {
  constructor({ text = "", attributes = {}, visible = true, enabled = true, children = {}, onAction = null, readError = null } = {}) {
    this.text = text;
    this.attributes = attributes;
    this.visible = visible;
    this.enabled = enabled;
    this.children = children;
    this.onAction = onAction;
    this.readError = readError;
  }
}

class FakeLocator {
  constructor(nodes, tab) {
    this.nodes = nodes;
    this.tab = tab;
  }

  child(kind, role, value) {
    return new FakeLocator(
      this.nodes.flatMap((node) => node.children[locatorKey(kind, role, value)] ?? []),
      this.tab,
    );
  }

  getByRole(role, options = {}) { return this.child("role", role, options.name ?? null); }
  getByLabel(value) { return this.child("label", null, value); }
  getByPlaceholder(value) { return this.child("placeholder", null, value); }
  getByTestId(value) { return this.child("test_id", null, value); }
  getByText(value) { return this.child("text", null, value); }
  locator(value) { return this.child("css", null, value); }

  async isVisible() { return this.nodes.some((node) => node.visible); }
  async isEnabled() { return this.nodes.some((node) => node.visible && node.enabled); }
  async waitFor() {
    await this.tab.onLocatorWait?.();
    if (!(await this.isVisible())) throw new Error("not visible");
  }
  async count() { return this.nodes.length; }
  nth(index) { return new FakeLocator(this.nodes[index] == null ? [] : [this.nodes[index]], this.tab); }
  async innerText() {
    if (this.nodes[0]?.readError != null) throw this.nodes[0].readError;
    return this.nodes[0]?.text ?? "";
  }
  async textContent() { return this.nodes[0]?.text ?? null; }
  async getAttribute(name) { return this.nodes[0]?.attributes[name] ?? null; }

  async act(kind, value = null) {
    if (!(await this.isVisible())) throw new Error("not visible");
    await this.nodes[0]?.onAction?.({ kind, value, tab: this.tab });
  }

  async click() { await this.act("click"); }
  async fill(value) { await this.act("fill", value); }
  async press(value) { await this.act("press", value); }
  async selectOption(value) { await this.act("select", value); }
  async setChecked(value) { await this.act("set_checked", value); }
}

class FakePlaywright extends FakeLocator {
  constructor(tab, registry, downloadPath = "/private/tmp/synthetic-download.zip") {
    super([new FakeNode({ children: registry })], tab);
    this.downloadPath = downloadPath;
  }

  async waitForEvent() {
    return { path: async () => this.downloadPath };
  }

  async waitForLoadState() {}
  async waitForTimeout() {}
}

class FakeTab {
  constructor(registry, startUrl = "https://example.com/") {
    this.currentUrl = startUrl;
    this.onLocatorWait = null;
    this.playwright = new FakePlaywright(this, registry);
  }

  async goto(url) { this.currentUrl = url; }
  async url() { return this.currentUrl; }
}

function candidate(kind, value, role = null) {
  return { kind, role, value, exact: true };
}

function nonePostcondition() {
  return {
    kind: "none",
    locator_candidates: [],
    value: null,
    output_ref: null,
    comparator: null,
    expected: null,
    timeout_ms: 100,
  };
}

function always(nextMilestone = null, terminal = false) {
  return {
    when: {
      kind: "always",
      locator_candidates: [],
      value: null,
      output_ref: null,
      comparator: null,
      expected: null,
      timeout_ms: 100,
    },
    next_milestone: nextMilestone,
    terminal,
  };
}

function syntheticCapability({
  effect = "reversible",
  delivery = "artifact_only",
  sensitivity = "private",
} = {}) {
  return {
    schema_version: "browser-capability/v2",
    capability_id: "synthetic-search",
    version: "0.2.0",
    status: "discovered",
    site: {
      name: "Synthetic",
      allowed_origins: ["https://example.com"],
      start_url: "https://example.com/",
    },
    process: {
      name: "Synthetic search",
      objective: "Extract structured result metadata.",
      out_of_scope: [],
    },
    runtime: {
      browser: "existing_chrome",
      controller: "chrome_extension",
      semantic_driver: "model",
      mechanical_driver: "playwright",
      os_fallback: "operator_handoff_on_native_gap",
    },
    authority: {
      operator_authorized: true,
      authentication: "operator_only",
      secret_policy: "never_request_read_store",
      consequential_actions: "confirm_at_action_time",
    },
    inputs: [
      {
        name: "query",
        type: "text",
        required: true,
        sensitivity: "private_runtime_only",
        purpose: "Search expression.",
        enum_values: [],
      },
      {
        name: "max-results",
        type: "number",
        required: true,
        sensitivity: "non_sensitive",
        purpose: "Maximum visible results.",
        enum_values: [],
      },
    ],
    outputs: [
      {
        name: "messages",
        type: "record_set",
        sensitivity,
        delivery,
        description: "Visible result metadata.",
        fields: [
          { name: "sender", type: "text", required: true },
          { name: "subject", type: "text", required: true },
        ],
      },
    ],
    entry_milestone: "search",
    milestones: [
      {
        id: "search",
        intent: "Submit the query.",
        preconditions: [],
        actions: [
          {
            id: "fill-query",
            intent: "Fill the search control.",
            operation: "fill",
            effect,
            confirmation: effect === "consequential" ? "action_time" : "none",
            locator_candidates: [candidate("placeholder", "Search")],
            input_ref: "query",
            key: null,
            path: null,
            target_origin: null,
            output_ref: null,
            extract: null,
            postcondition: nonePostcondition(),
            timeout_ms: 100,
          },
        ],
        transitions: [always("collect")],
      },
      {
        id: "collect",
        intent: "Extract visible metadata.",
        preconditions: [],
        actions: [
          {
            id: "extract-messages",
            intent: "Extract result rows.",
            operation: "extract",
            effect: "read_only",
            confirmation: "none",
            locator_candidates: [candidate("role", null, "row")],
            input_ref: null,
            key: null,
            path: null,
            target_origin: null,
            output_ref: "messages",
            extract: {
              mode: "list",
              fields: [
                {
                  name: "sender",
                  locator_candidates: [candidate("test_id", "sender")],
                  read: { kind: "inner_text", attribute: null },
                  required: true,
                },
                {
                  name: "subject",
                  locator_candidates: [candidate("test_id", "subject")],
                  read: { kind: "inner_text", attribute: null },
                  required: true,
                },
              ],
              max_items: 50,
              limit_input_ref: "max-results",
              empty_allowed: true,
              dedupe_by: ["sender", "subject"],
            },
            postcondition: {
              kind: "output_count",
              locator_candidates: [],
              value: null,
              output_ref: "messages",
              comparator: "gte",
              expected: 1,
              timeout_ms: 100,
            },
            timeout_ms: 100,
          },
        ],
        transitions: [always(null, true)],
      },
    ],
    completion: {
      terminal_milestones: ["collect"],
      required_outputs: ["messages"],
    },
    privacy: {
      model_data: ["Milestone outcomes and output counts only."],
      portable_artifact_excludes: [
        "credentials",
        "cookies",
        "browser_storage",
        "session_urls",
        "page_html",
        "screenshots",
        "network_bodies",
        "downloaded_file_bytes",
        "observed_private_values",
      ],
      private_evidence_retained: false,
    },
    validation: {
      environment_scope: "not_validated",
      execution_contract_sha256: null,
      receipts: [],
      known_limits: [],
    },
    provenance: {
      source: "authorized_live_discovery",
      discovery_record_sha256: "a".repeat(64),
      discovery_approval_id: "synthetic-review",
      discovery_approved_at: "2026-08-24T20:00:00+02:00",
      portable_bundle_contains_private_evidence: false,
    },
  };
}

function syntheticDownloadCapability() {
  const capability = syntheticCapability();
  capability.outputs = [
    {
      name: "files",
      type: "download_set",
      sensitivity: "private",
      delivery: "artifact_only",
      description: "Downloaded files.",
      fields: [],
    },
  ];
  const action = capability.milestones[1].actions[0];
  action.id = "download-file";
  action.intent = "Download one synthetic file.";
  action.operation = "download";
  action.locator_candidates = [candidate("role", "Download", "button")];
  action.output_ref = "files";
  action.extract = null;
  action.postcondition.output_ref = "files";
  action.postcondition.kind = "output_count";
  action.postcondition.comparator = "gte";
  action.postcondition.expected = 1;
  capability.completion.required_outputs = ["files"];
  return capability;
}

function resultRegistry(tab) {
  const row = (sender, subject) => new FakeNode({
    children: {
      [locatorKey("test_id", null, "sender")]: [new FakeNode({ text: sender })],
      [locatorKey("test_id", null, "subject")]: [new FakeNode({ text: subject })],
    },
  });
  return {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "row", null)]: [
      row("Supplier A", "Invoice 100"),
      row("Supplier B", "Invoice 200"),
      row("Supplier A", "Invoice 100"),
    ],
  };
}

async function gmailCapability() {
  const capability = JSON.parse(
    await readFile(
      new URL(
        "../plugins/browser-automation/capabilities/gmail-search-export/capability.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  capability.status = "discovered";
  capability.provenance.source = "authorized_live_discovery";
  capability.provenance.discovery_approval_id = "synthetic-gmail-review";
  capability.provenance.discovery_approved_at = "2026-08-25T18:00:00+02:00";
  return capability;
}

function gmailRow(sender, displayedDate = "Aug 25") {
  return new FakeNode({
    children: {
      [locatorKey("css", null, "span[email]:visible")]: [new FakeNode({ text: sender })],
      [locatorKey("css", null, ".yW:visible")]: [new FakeNode({ text: sender })],
      [locatorKey("css", null, "td.xW span:visible")]: [
        new FakeNode({ text: displayedDate }),
      ],
    },
  });
}

function gmailRegistry(onSearch) {
  const search = new FakeNode({
    onAction: ({ kind, value, tab }) => {
      if (kind === "press" && value === "Enter") {
        tab.currentUrl = "https://mail.google.com/mail/u/0/#search/synthetic-private-query";
        onSearch();
      }
    },
  });
  return {
    [locatorKey("role", "textbox", "Search mail")]: [search],
  };
}

async function runGmailCapability(capability, registry, runId) {
  const tab = new FakeTab(registry, "https://mail.google.com/mail/u/0/");
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "gmail-runtime-state-test-"));
  return {
    tab,
    parent,
    execute: () => executeCapability({
      tab,
      capability,
      inputs: { query: "synthetic-private-query", "max-results": 10 },
      runDirectory: join(parent, runId),
      runId,
      environment: { locale: "en-US", origin_ui: "Synthetic Gmail" },
    }),
  };
}

test("executeCapability drives actions, extracts records, and emits hash-linked evidence", async () => {
  const capability = syntheticCapability();
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, resultRegistry(tab));
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const runDirectory = join(parent, "run-one");

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory,
    runId: "synthetic-run-one",
    clock: (() => {
      let tick = 0;
      return () => `2026-08-24T20:00:${String(tick++).padStart(2, "0")}+02:00`;
    })(),
    environment: { locale: "en" },
  });

  assert.equal(summary.result, "passed");
  assert.deepEqual(summary.completed_milestones, ["search", "collect"]);
  assert.deepEqual(summary.outputs.map((item) => item.record_count), [2]);
  assert.equal("records" in summary, false);
  assert.deepEqual(summary.delivered_outputs, {});
  const outputs = JSON.parse(await readFile(summary.outputs_path, "utf8"));
  assert.deepEqual(outputs.messages, [
    { sender: "Supplier A", subject: "Invoice 100" },
    { sender: "Supplier B", subject: "Invoice 200" },
  ]);
  const receipt = JSON.parse(await readFile(summary.receipt_path, "utf8"));
  const receiptText = await readFile(summary.receipt_path, "utf8");
  const outputsText = await readFile(summary.outputs_path, "utf8");
  const runLock = JSON.parse(await readFile(summary.lock_path, "utf8"));
  assert.equal(receipt.execution_contract_sha256, executionContractSha256(capability));
  assert.equal(receipt.outputs[0].sha256, summary.outputs[0].sha256);
  assert.equal(receipt.action_results.length, 2);
  assert.equal(receipt.input_hashes.query.length, 64);
  assert.equal(
    runLock.receipt_sha256,
    createHash("sha256").update(receiptText, "utf8").digest("hex"),
  );
  assert.equal(
    runLock.outputs_sha256,
    createHash("sha256").update(outputsText, "utf8").digest("hex"),
  );
  assert.equal((await stat(summary.outputs_path)).mode & 0o777, 0o600);
  assert.equal((await stat(runDirectory)).mode & 0o777, 0o700);
});

test("goto accepts a committed exact target after the connected tab reports a timeout", async () => {
  const capability = syntheticCapability();
  capability.milestones[0].actions[0] = {
    ...capability.milestones[0].actions[0],
    id: "open-fixture",
    intent: "Open the synthetic fixture.",
    operation: "goto",
    effect: "read_only",
    locator_candidates: [],
    input_ref: null,
    path: "/",
  };
  const tab = new FakeTab(resultRegistry(), "https://example.com/before");
  tab.goto = async (url) => {
    tab.currentUrl = url;
    throw new Error("connected tab navigation timed out after commit");
  };
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-goto-commit-test-"));

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "run-one"),
    runId: "goto-commit-run",
  });

  assert.equal(summary.result, "passed");
  assert.equal(await tab.url(), "https://example.com/");
});

test("goto rejects a timeout when the connected tab did not reach the target", async () => {
  const capability = syntheticCapability();
  capability.milestones[0].actions[0] = {
    ...capability.milestones[0].actions[0],
    id: "open-fixture",
    intent: "Open the synthetic fixture.",
    operation: "goto",
    effect: "read_only",
    locator_candidates: [],
    input_ref: null,
    path: "/",
  };
  const tab = new FakeTab(resultRegistry(), "https://example.com/before");
  tab.goto = async () => {
    throw new Error("connected tab navigation timed out before commit");
  };
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-goto-failure-test-"));

  await assert.rejects(
    () => executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "run-one"),
      runId: "goto-failure-run",
    }),
    (error) => {
      assert.equal(error.code, "run_failed");
      assert.equal(error.runSummary.result, "failed");
      assert.equal(error.runSummary.completed_milestones.length, 0);
      return true;
    },
  );
});

test("gmail capability detects mailbox readiness through an accessible search control", async () => {
  const capability = await gmailCapability();
  const registry = gmailRegistry(() => {
    registry[locatorKey("text", null, "No emails matched your search")] = [
      new FakeNode({ text: "No emails matched your search" }),
    ];
  });
  const run = await runGmailCapability(capability, registry, "gmail-mailbox-ready");

  const summary = await run.execute();

  const receipt = JSON.parse(await readFile(summary.receipt_path, "utf8"));
  const readiness = receipt.action_results.find(
    (result) => result.action_id === "wait-gmail-search",
  );
  assert.equal(readiness.locator_candidate.kind, "role");
  assert.equal(readiness.locator_candidate.index, 0);
  assert.equal(summary.terminal_milestone, "no-results");
});

test("gmail capability detects results and falls back across reviewed row DOM variants", async () => {
  const capability = await gmailCapability();
  const privateSubject = "Synthetic confidential subject";
  const validRows = [gmailRow("Synthetic sender")];
  const registry = gmailRegistry(() => {
    registry[locatorKey("role", "row", null)] = [new FakeNode()];
    registry[locatorKey("css", null, "tr.zA:visible")] = validRows;
  });
  const run = await runGmailCapability(capability, registry, "gmail-results-available");

  const summary = await run.execute();

  assert.equal(summary.terminal_milestone, "collect-results");
  assert.deepEqual(summary.completed_milestones, [
    "open-gmail",
    "submit-search",
    "collect-results",
  ]);
  assert.deepEqual(summary.delivered_outputs, {});
  const outputsText = await readFile(summary.outputs_path, "utf8");
  const outputs = JSON.parse(outputsText);
  assert.deepEqual(outputs.messages[0], {
    sender: "Synthetic sender",
    "displayed-date": "Aug 25",
  });
  const receiptText = await readFile(summary.receipt_path, "utf8");
  const receipt = JSON.parse(receiptText);
  const extraction = receipt.action_results.find(
    (result) => result.action_id === "extract-gmail-results",
  );
  assert.equal(extraction.locator_candidate.index, 1);
  assert.equal(extraction.locator_candidate.kind, "css");
  assert.equal(receiptText.includes("synthetic-private-query"), false);
  assert.equal(receiptText.includes(privateSubject), false);
  assert.equal(outputsText.includes("synthetic-private-query"), false);
  assert.equal(outputsText.includes(privateSubject), false);
});

test("gmail capability retries metadata extraction after row descendants settle", async () => {
  const capability = await gmailCapability();
  const privateSubject = "Synthetic settled subject";
  const row = gmailRow("Synthetic sender");
  const senderKey = locatorKey("css", null, "span[email]:visible");
  const senderFallbackKey = locatorKey("css", null, ".yW:visible");
  row.children[senderKey] = [];
  row.children[senderFallbackKey] = [];
  const registry = gmailRegistry(() => {
    registry[locatorKey("role", "row", null)] = [row];
  });
  const run = await runGmailCapability(capability, registry, "gmail-extraction-retry");
  let settleCalls = 0;
  run.tab.playwright.waitForTimeout = async () => {
    settleCalls += 1;
    row.children[senderKey] = [new FakeNode({ text: "Synthetic sender" })];
  };

  const summary = await run.execute();

  assert.equal(summary.terminal_milestone, "collect-results");
  assert.equal(settleCalls, 1);
  const receiptText = await readFile(summary.receipt_path, "utf8");
  const outputsText = await readFile(summary.outputs_path, "utf8");
  assert.equal(receiptText.includes(privateSubject), false);
  assert.equal(outputsText.includes(privateSubject), false);
});

test("gmail capability detects an accessible no-results state without reading rows", async () => {
  const capability = await gmailCapability();
  const registry = gmailRegistry(() => {
    registry[locatorKey("text", null, "No messages matched your search")] = [
      new FakeNode({ text: "No messages matched your search" }),
    ];
  });
  const run = await runGmailCapability(capability, registry, "gmail-no-results");

  const summary = await run.execute();

  assert.equal(summary.terminal_milestone, "no-results");
  assert.deepEqual(summary.completed_milestones, [
    "open-gmail",
    "submit-search",
    "no-results",
  ]);
  const outputs = JSON.parse(await readFile(summary.outputs_path, "utf8"));
  assert.deepEqual(outputs.messages, []);
});

test("gmail capability retries one transient loading state before extracting results", async () => {
  const capability = await gmailCapability();
  const rows = [gmailRow("Synthetic sender")];
  let locatorWaits = 0;
  const registry = gmailRegistry(() => {
    registry[locatorKey("role", "progressbar", null)] = [new FakeNode()];
  });
  const run = await runGmailCapability(capability, registry, "gmail-transient-retry");
  run.tab.onLocatorWait = () => {
    locatorWaits += 1;
    if (locatorWaits === 5) {
      registry[locatorKey("role", "progressbar", null)] = [];
      registry[locatorKey("role", "row", null)] = rows;
    }
  };

  const summary = await run.execute();

  assert.equal(summary.terminal_milestone, "collect-results");
  assert.deepEqual(summary.completed_milestones, [
    "open-gmail",
    "submit-search",
    "search-transient",
    "collect-results",
  ]);
});

test("gmail capability fails closed when loading never resolves", async () => {
  const capability = await gmailCapability();
  const registry = gmailRegistry(() => {
    registry[locatorKey("role", "progressbar", null)] = [new FakeNode()];
  });
  const run = await runGmailCapability(capability, registry, "gmail-persistent-loading");
  let caught = null;

  try {
    await run.execute();
  } catch (error) {
    caught = error;
  }

  assert.ok(caught instanceof Error);
  assert.equal(caught.code, "locator_resolution_failed");
  assert.equal(caught.runSummary.recovery_request.action.action_id, "wait-gmail-result-state");
  const receiptText = await readFile(caught.runSummary.receipt_path, "utf8");
  assert.equal(receiptText.includes("synthetic-private-query"), false);
});

test("executeCapability accepts an exact input-templated route in an encoded URL", async () => {
  const capability = syntheticCapability();
  const action = capability.milestones[0].actions[0];
  action.operation = "press";
  action.input_ref = null;
  action.key = "Enter";
  action.postcondition = {
    kind: "url_includes",
    locator_candidates: [],
    value: "#search/{{query}}",
    output_ref: null,
    comparator: null,
    expected: null,
    timeout_ms: 100,
  };
  const registry = resultRegistry();
  let searchSubmitted = false;
  registry[locatorKey("placeholder", null, "Search")][0].onAction = ({ value }) => {
    if (value === "Enter") {
      searchSubmitted = true;
    }
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  tab.playwright.waitForTimeout = async () => {
    if (searchSubmitted) {
      tab.currentUrl = "https://example.com/#search/newer_than%3A7d";
    }
  };
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "newer_than:7d", "max-results": 10 },
    runDirectory: join(parent, "encoded-query-route"),
    runId: "encoded-query-route-run",
  });

  assert.equal(summary.result, "passed");
});

test("executeCapability rejects a no-op press when the exact query route is absent", async () => {
  const capability = syntheticCapability();
  const action = capability.milestones[0].actions[0];
  action.operation = "press";
  action.input_ref = null;
  action.key = "Enter";
  action.postcondition = {
    kind: "url_includes",
    locator_candidates: [],
    value: "#search/{{query}}",
    output_ref: null,
    comparator: null,
    expected: null,
    timeout_ms: 100,
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, resultRegistry());
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "newer_than:7d", "max-results": 10 },
      runDirectory: join(parent, "missing-query-route"),
      runId: "missing-query-route-run",
    }),
    /postcondition_failed/,
  );
});

test("executeCapability rejects a legacy desktop-control fallback contract", async () => {
  const capability = syntheticCapability();
  capability.runtime.os_fallback = "computer_use_non_browser_only";
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab: new FakeTab({}),
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "legacy-fallback"),
      runId: "legacy-fallback-run",
    }),
    /capability runtime contract is unsupported/,
  );
});

test("executeCapability returns declared model outputs but keeps artifact-only values private", async () => {
  const capability = syntheticCapability({
    delivery: "model_and_artifact",
    sensitivity: "non_sensitive",
  });
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, resultRegistry(tab));
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "delivered-output"),
    runId: "delivered-output-run",
  });

  assert.deepEqual(summary.delivered_outputs.messages, [
    { sender: "Supplier A", subject: "Invoice 100" },
    { sender: "Supplier B", subject: "Invoice 200" },
  ]);
});

test("executeCapability extracts a declared model summary as text", async () => {
  const capability = syntheticCapability();
  capability.outputs = [
    {
      name: "status-summary",
      type: "summary",
      sensitivity: "non_sensitive",
      delivery: "model_summary",
      description: "Visible status summary.",
      fields: [],
    },
  ];
  const extraction = capability.milestones[1].actions[0];
  extraction.output_ref = "status-summary";
  extraction.locator_candidates = [candidate("role", null, "status")];
  extraction.extract = {
    mode: "text",
    fields: [],
    max_items: 1,
    limit_input_ref: null,
    empty_allowed: false,
    dedupe_by: [],
  };
  extraction.postcondition.output_ref = "status-summary";
  extraction.postcondition.kind = "output_nonempty";
  extraction.postcondition.comparator = null;
  extraction.postcondition.expected = null;
  capability.completion.required_outputs = ["status-summary"];
  const registry = resultRegistry();
  registry[locatorKey("role", "status", null)] = [new FakeNode({ text: "Ready" })];
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "summary-output"),
    runId: "summary-output-run",
  });

  assert.equal(summary.delivered_outputs["status-summary"], "Ready");
});

test("executeCapability records downloaded file bytes without returning the private path", async () => {
  const capability = syntheticDownloadCapability();
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const downloadPath = join(parent, "download.zip");
  await writeFile(downloadPath, "synthetic zip bytes", "utf8");
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [new FakeNode()],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry, downloadPath);

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "download-output"),
    runId: "download-output-run",
  });

  assert.deepEqual(summary.delivered_outputs, {});
  const outputs = JSON.parse(await readFile(summary.outputs_path, "utf8"));
  assert.equal(outputs.files[0].path, downloadPath);
  assert.equal(outputs.files[0].byte_length, 19);
  assert.equal(outputs.files[0].sha256.length, 64);
  const receipt = JSON.parse(await readFile(summary.receipt_path, "utf8"));
  assert.equal(receipt.schema_version, "browser-run-receipt/v2");
  assert.equal(receipt.action_results.at(-1).evidence_code, "download-bytes-verified");
  assert.equal(receipt.action_results.at(-1).mechanism_hint, "control-without-href");
});

test("executeCapability keeps identical download evidence stable across local paths", async () => {
  const capability = syntheticDownloadCapability();
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const firstPath = join(parent, "first-download.zip");
  const secondPath = join(parent, "second-download.zip");
  await writeFile(firstPath, "same synthetic zip bytes", "utf8");
  await writeFile(secondPath, "same synthetic zip bytes", "utf8");
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [new FakeNode()],
  };
  const firstTab = new FakeTab({});
  firstTab.playwright = new FakePlaywright(firstTab, registry, firstPath);
  const secondTab = new FakeTab({});
  secondTab.playwright = new FakePlaywright(secondTab, registry, secondPath);

  const first = await executeCapability({
    tab: firstTab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "first-run"),
    runId: "first-download-run",
  });
  const second = await executeCapability({
    tab: secondTab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "second-run"),
    runId: "second-download-run",
  });
  const firstOutputs = JSON.parse(await readFile(first.outputs_path, "utf8"));
  const secondOutputs = JSON.parse(await readFile(second.outputs_path, "utf8"));
  const firstReceipt = JSON.parse(await readFile(first.receipt_path, "utf8"));
  const secondReceipt = JSON.parse(await readFile(second.receipt_path, "utf8"));
  const firstLock = JSON.parse(await readFile(first.lock_path, "utf8"));
  const secondLock = JSON.parse(await readFile(second.lock_path, "utf8"));

  assert.notEqual(firstOutputs.files[0].path, secondOutputs.files[0].path);
  assert.equal(first.outputs[0].sha256, second.outputs[0].sha256);
  assert.equal(
    firstReceipt.action_results.at(-1).output_sha256,
    secondReceipt.action_results.at(-1).output_sha256,
  );
  assert.notEqual(firstLock.outputs_sha256, secondLock.outputs_sha256);
});

test("executeCapability reports a native gap when Chrome cannot expose download evidence", async () => {
  const capability = syntheticDownloadCapability();
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [new FakeNode()],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  tab.playwright.waitForEvent = async () => ({});
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  const runDirectory = join(parent, "download-native-gap");
  let caught = null;
  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory,
      runId: "download-native-gap-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.equal(caught?.code, "native_gap");
  assert.equal(caught?.reasonCode, "download-path-api-unavailable");
  assert.equal(caught?.runSummary.error.reason_code, "download-path-api-unavailable");
  const receipt = JSON.parse(await readFile(join(runDirectory, "run.receipt.json"), "utf8"));
  const failedAction = receipt.action_results.at(-1);
  assert.equal(failedAction.evidence_code, "download-path-api-unavailable");
  assert.equal(failedAction.mechanism_hint, "control-without-href");
  assert.equal(failedAction.error.reason_code, "download-path-api-unavailable");
  assert.equal(failedAction.origin, "https://example.com");
  assert.equal(failedAction.path, "/");
});

test("executeCapability distinguishes a download event with no local path", async () => {
  const capability = syntheticDownloadCapability();
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [new FakeNode()],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  tab.playwright.waitForEvent = async () => ({ path: async () => null });
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  let caught = null;
  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "download-path-missing"),
      runId: "download-path-missing-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.equal(caught?.code, "native_gap");
  assert.equal(caught?.reasonCode, "download-path-not-returned");
});

test("executeCapability distinguishes an unreadable downloaded file", async () => {
  const capability = syntheticDownloadCapability();
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [new FakeNode()],
  };
  const tab = new FakeTab({});
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  tab.playwright = new FakePlaywright(tab, registry, join(parent, "missing.zip"));

  let caught = null;
  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "download-file-unreadable"),
      runId: "download-file-unreadable-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.equal(caught?.code, "native_gap");
  assert.equal(caught?.reasonCode, "download-file-unreadable");
});

test("executeCapability distinguishes a missing download event on an unchanged page", async () => {
  const capability = syntheticDownloadCapability();
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [
      new FakeNode({ attributes: { href: "blob:private-runtime-value" } }),
    ],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  tab.playwright.waitForEvent = async () => {
    throw new Error("private timeout detail");
  };
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const runDirectory = join(parent, "download-event-unchanged");

  let caught = null;
  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory,
      runId: "download-event-unchanged-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.equal(caught?.reasonCode, "download-event-not-observed-page-unchanged");
  const receiptText = await readFile(join(runDirectory, "run.receipt.json"), "utf8");
  assert.doesNotMatch(receiptText, /private timeout detail|private-runtime-value/);
  const receipt = JSON.parse(receiptText);
  assert.equal(receipt.action_results.at(-1).mechanism_hint, "blob-url");
});

test("executeCapability distinguishes a missing download event after navigation", async () => {
  const capability = syntheticDownloadCapability();
  const registry = {
    [locatorKey("placeholder", null, "Search")]: [new FakeNode()],
    [locatorKey("role", "button", "Download")]: [
      new FakeNode({
        attributes: { href: "/download-status?secret=value" },
        onAction: ({ tab: clickedTab }) => {
          clickedTab.currentUrl = "https://example.com/?secret=value#fragment";
        },
      }),
    ],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  tab.playwright.waitForEvent = async () => {
    throw new Error("download event timed out");
  };
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const runDirectory = join(parent, "download-event-navigation");

  let caught = null;
  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory,
      runId: "download-event-navigation-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.equal(caught?.reasonCode, "download-event-not-observed-after-navigation");
  const receiptText = await readFile(join(runDirectory, "run.receipt.json"), "utf8");
  assert.doesNotMatch(receiptText, /secret=value|fragment/);
  const failedAction = JSON.parse(receiptText).action_results.at(-1);
  assert.equal(failedAction.origin, "https://example.com");
  assert.equal(failedAction.path, "/");
  assert.equal(failedAction.mechanism_hint, "same-origin-url");
});

test("executeCapability fails when a required non-collection output is unproduced", async () => {
  const capability = syntheticCapability();
  capability.outputs = [
    {
      name: "status-summary",
      type: "summary",
      sensitivity: "non_sensitive",
      delivery: "model_summary",
      description: "Visible status summary.",
      fields: [],
    },
  ];
  const action = capability.milestones[1].actions[0];
  action.id = "wait-status";
  action.operation = "wait_for";
  action.locator_candidates = [candidate("role", null, "status")];
  action.output_ref = null;
  action.extract = null;
  action.postcondition = nonePostcondition();
  capability.completion.required_outputs = ["status-summary"];
  const registry = resultRegistry();
  registry[locatorKey("role", "status", null)] = [new FakeNode({ text: "Ready" })];
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "missing-summary"),
      runId: "missing-summary-run",
    }),
    /required_output_incomplete/,
  );
});

test("executeCapability rejects undeclared inputs and consequential actions without approval", async () => {
  const capability = syntheticCapability({ effect: "consequential" });
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, resultRegistry(tab));
  const firstParent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10, unexpected: true },
      runDirectory: join(firstParent, "bad-input"),
      runId: "bad-input-run",
    }),
    /undeclared runtime input/,
  );

  const secondParent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(secondParent, "no-approval"),
      runId: "no-approval-run",
    }),
    /operator_confirmation_required/,
  );
});

test("executeCapability fails closed on malformed action effects and approval ids", async () => {
  const malformed = syntheticCapability();
  malformed.milestones[0].actions[0].effect = "reversibl";
  const badConfirmation = syntheticCapability({ effect: "consequential" });
  badConfirmation.milestones[0].actions[0].confirmation = "none";
  const valid = syntheticCapability();
  const tab = new FakeTab({});
  const inputs = { query: "invoice", "max-results": 10 };

  await assert.rejects(
    executeCapability({
      tab,
      capability: malformed,
      inputs,
      runDirectory: join(await mkdtemp(join(tmpdir(), "browser-runtime-test-")), "bad-effect"),
      runId: "bad-effect-run",
    }),
    /unsupported effect/,
  );
  await assert.rejects(
    executeCapability({
      tab,
      capability: badConfirmation,
      inputs,
      runDirectory: join(await mkdtemp(join(tmpdir(), "browser-runtime-test-")), "bad-confirmation"),
      runId: "bad-confirmation-run",
    }),
    /confirmation must be action_time/,
  );
  await assert.rejects(
    executeCapability({
      tab,
      capability: valid,
      inputs,
      runDirectory: join(await mkdtemp(join(tmpdir(), "browser-runtime-test-")), "bad-approval"),
      runId: "bad-approval-run",
      approvedConsequentialActions: ["fill-query"],
    }),
    /approval does not name a consequential action/,
  );
});

test("executeCapability rejects draft or unreviewed provenance", async () => {
  const draft = syntheticCapability();
  draft.status = "draft";
  const unreviewed = syntheticCapability();
  unreviewed.provenance.source = "live_discovery_unreviewed";
  unreviewed.provenance.discovery_approval_id = null;
  unreviewed.provenance.discovery_approved_at = null;
  const tab = new FakeTab({});
  const firstParent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  const secondParent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability: draft,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(firstParent, "draft"),
      runId: "draft-run",
    }),
    /is not executable/,
  );
  await assert.rejects(
    executeCapability({
      tab,
      capability: unreviewed,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(secondParent, "unreviewed"),
      runId: "unreviewed-run",
    }),
    /lacks reviewed discovery provenance/,
  );
});

test("executeCapability fails closed when an action leaves the allowed origin", async () => {
  const capability = syntheticCapability();
  const tab = new FakeTab({});
  const registry = resultRegistry(tab);
  registry[locatorKey("placeholder", null, "Search")][0].onAction = ({ tab: currentTab }) => {
    currentTab.currentUrl = "https://attacker.example/escaped";
  };
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "origin-escape"),
      runId: "origin-escape-run",
    }),
    /origin_boundary_violation/,
  );
});

test("executeCapability returns a sanitized recovery request for a model-led retry", async () => {
  const capability = syntheticCapability();
  const registry = resultRegistry();
  delete registry[locatorKey("placeholder", null, "Search")];
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let caught = null;

  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "recovery-request"),
      runId: "recovery-request-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.ok(caught instanceof Error);
  assert.equal(caught.code, "locator_resolution_failed");
  assert.equal(caught.runSummary.recovery_request.action.action_id, "fill-query");
  assert.equal(caught.runSummary.recovery_request.constraints.permitted_change, "one_semantic_locator_candidate");
  assert.equal(JSON.stringify(caught.runSummary.recovery_request).includes("invoice"), false);
  const receiptText = await readFile(caught.runSummary.receipt_path, "utf8");
  assert.equal(receiptText.includes("invoice"), false);
});

test("executeCapability accepts one bounded model locator recovery and hash-links the proposal", async () => {
  const capability = syntheticCapability();
  const originalCapability = structuredClone(capability);
  const registry = resultRegistry();
  registry[locatorKey("placeholder", null, "Find records")] = [new FakeNode()];
  delete registry[locatorKey("placeholder", null, "Search")];
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let request = null;

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "model-recovery"),
    runId: "model-recovery-run",
    recoveryHandler: async (candidateRequest) => {
      request = candidateRequest;
      return {
        locator_candidate: candidate("placeholder", "Find records"),
        rationale: "The visible search field has a revised accessible placeholder.",
        uncertainty: "The candidate is valid only for this run until reviewed.",
      };
    },
  });

  assert.equal(summary.result, "passed");
  assert.equal(summary.recovery_proposal_count, 1);
  assert.equal(JSON.stringify(request).includes("invoice"), false);
  assert.equal(request.constraints.permitted_change, "one_semantic_locator_candidate");
  assert.deepEqual(capability, originalCapability);
  const receipt = JSON.parse(await readFile(summary.receipt_path, "utf8"));
  const proposalsText = await readFile(summary.recovery_proposals_path, "utf8");
  const proposals = JSON.parse(proposalsText);
  const lock = JSON.parse(await readFile(summary.lock_path, "utf8"));
  assert.equal(receipt.locator_changes_during_run, true);
  assert.equal(receipt.action_results[0].locator_candidate.index, 1);
  assert.equal(proposals.portable, false);
  assert.equal(proposals.requires_operator_review_before_persistence, true);
  assert.equal(proposals.proposals[0].approved_for_persistence, false);
  assert.deepEqual(
    proposals.proposals[0].candidate,
    candidate("placeholder", "Find records"),
  );
  assert.equal(lock.schema_version, "browser-run-lock/v2");
  assert.equal(
    lock.recovery_proposals_sha256,
    createHash("sha256").update(proposalsText, "utf8").digest("hex"),
  );
});

test("executeCapability recovers one nested structured extraction field without widening the action", async () => {
  const capability = syntheticCapability();
  const originalCapability = structuredClone(capability);
  const registry = resultRegistry();
  for (const row of registry[locatorKey("role", "row", null)]) {
    const senderNode = row.children[locatorKey("test_id", null, "sender")][0];
    const sender = senderNode.text;
    senderNode.readError = new Error("multiple matching structured nodes");
    row.children[locatorKey("css", null, ".sender-summary:visible")] = [
      new FakeNode({ text: sender }),
    ];
  }
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let request = null;

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "field-recovery"),
    runId: "field-recovery-run",
    recoveryHandler: async (candidateRequest) => {
      request = candidateRequest;
      return {
        locator_candidate: {
          kind: "css",
          role: null,
          value: ".sender-summary:visible",
          exact: false,
        },
        rationale: "The bounded row exposes one visible sender summary container.",
        uncertainty: "The selector remains run-local until operator review.",
      };
    },
  });

  assert.equal(summary.result, "passed");
  assert.equal(summary.recovery_proposal_count, 1);
  assert.equal(request.recovery_target.kind, "extraction_field_locator");
  assert.equal(request.recovery_target.field_name, "sender");
  assert.equal(
    request.constraints.permitted_change,
    "one_bounded_structured_field_locator_candidate_or_resolved_action_root",
  );
  assert.deepEqual(capability, originalCapability);
  const proposals = JSON.parse(
    await readFile(summary.recovery_proposals_path, "utf8"),
  );
  assert.equal(proposals.proposals[0].target_kind, "extraction_field_locator");
  assert.equal(proposals.proposals[0].field_name, "sender");
  assert.deepEqual(proposals.proposals[0].candidate, {
    kind: "css",
    role: null,
    value: ".sender-summary:visible",
    exact: false,
  });
});

test("executeCapability recovers a self-nested extraction field by reusing the resolved action root", async () => {
  const capability = syntheticCapability({
    delivery: "model_and_artifact",
    sensitivity: "non_sensitive",
  });
  capability.outputs = [
    {
      name: "before-state",
      type: "record",
      sensitivity: "non_sensitive",
      delivery: "model_and_artifact",
      description: "Semantic trigger state before expansion.",
      fields: [{ name: "control-name", type: "text", required: true }],
    },
  ];
  capability.entry_milestone = "collect";
  capability.milestones = [capability.milestones[1]];
  const action = capability.milestones[0].actions[0];
  const rootCandidate = candidate("role", "Billing Address", "button");
  action.id = "extract-before-state";
  action.intent = "Capture the semantic trigger state before expansion.";
  action.locator_candidates = [rootCandidate];
  action.output_ref = "before-state";
  action.extract = {
    mode: "single",
    fields: [
      {
        name: "control-name",
        locator_candidates: [structuredClone(rootCandidate)],
        read: { kind: "inner_text", attribute: null },
        required: true,
      },
    ],
    max_items: 1,
    limit_input_ref: null,
    empty_allowed: false,
    dedupe_by: [],
  };
  action.postcondition.output_ref = "before-state";
  action.postcondition.kind = "output_count";
  action.postcondition.comparator = "gte";
  action.postcondition.expected = 1;
  capability.completion = {
    terminal_milestones: ["collect"],
    required_outputs: ["before-state"],
  };
  const originalCapability = structuredClone(capability);
  const registry = {
    [locatorKey("role", "button", "Billing Address")]: [
      new FakeNode({ text: "Billing Address", attributes: { "aria-expanded": "false" } }),
    ],
  };
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let request = null;

  const summary = await executeCapability({
    tab,
    capability,
    inputs: { query: "invoice", "max-results": 10 },
    runDirectory: join(parent, "resolved-root-recovery"),
    runId: "resolved-root-recovery-run",
    recoveryHandler: async (candidateRequest) => {
      request = candidateRequest;
      return {
        use_resolved_action_root: true,
        rationale: "The field is the already resolved Billing Address control itself.",
        uncertainty: "The repair remains run-local until operator review.",
      };
    },
  });

  assert.equal(summary.result, "passed");
  assert.equal(summary.recovery_proposal_count, 1);
  assert.equal(request.recovery_target.kind, "extraction_field_locator");
  assert.equal(request.recovery_target.field_name, "control-name");
  assert.equal(
    request.constraints.permitted_change,
    "one_bounded_structured_field_locator_candidate_or_resolved_action_root",
  );
  assert.deepEqual(summary.delivered_outputs["before-state"], {
    "control-name": "Billing Address",
  });
  assert.deepEqual(capability, originalCapability);
  const proposals = JSON.parse(
    await readFile(summary.recovery_proposals_path, "utf8"),
  );
  assert.equal(proposals.schema_version, "browser-recovery-proposals/v2");
  assert.equal(proposals.proposals[0].resolution, "resolved_action_root");
  assert.equal(proposals.proposals[0].candidate, null);
  assert.equal(proposals.proposals[0].candidate_index, null);
  assert.equal(proposals.proposals[0].candidate_sha256, null);
});

test("executeCapability never invokes model recovery for consequential actions", async () => {
  const capability = syntheticCapability({ effect: "consequential" });
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, resultRegistry(tab));
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let recoveryCalls = 0;

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "consequential-recovery"),
      runId: "consequential-recovery-run",
      recoveryHandler: async () => {
        recoveryCalls += 1;
        return {
          locator_candidate: candidate("placeholder", "Find records"),
          rationale: "Synthetic rationale.",
          uncertainty: "Synthetic uncertainty.",
        };
      },
    }),
    /operator_confirmation_required/,
  );
  assert.equal(recoveryCalls, 0);
});

test("executeCapability rejects non-semantic recovery locators", async () => {
  const capability = syntheticCapability();
  const registry = resultRegistry();
  delete registry[locatorKey("placeholder", null, "Search")];
  const tab = new FakeTab({});
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));

  await assert.rejects(
    executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "unsafe-recovery"),
      runId: "unsafe-recovery-run",
      recoveryHandler: async () => ({
        locator_candidate: candidate("css", "input.search"),
        rationale: "A CSS selector was proposed.",
        uncertainty: "It has not been reviewed.",
      }),
    }),
    /run_failed/,
  );
});

test("executeCapability never exposes raw browser failure text", async () => {
  const capability = syntheticCapability();
  const privateDetail = "private-runtime-value-in-browser-error";
  const tab = new FakeTab({});
  const registry = resultRegistry(tab);
  registry[locatorKey("placeholder", null, "Search")][0].onAction = () => {
    throw new Error(privateDetail);
  };
  tab.playwright = new FakePlaywright(tab, registry);
  const parent = await mkdtemp(join(tmpdir(), "browser-runtime-test-"));
  let caught = null;

  try {
    await executeCapability({
      tab,
      capability,
      inputs: { query: "invoice", "max-results": 10 },
      runDirectory: join(parent, "private-error"),
      runId: "private-error-run",
    });
  } catch (error) {
    caught = error;
  }

  assert.ok(caught instanceof Error);
  assert.equal(caught.message.includes(privateDetail), false);
  assert.equal(caught.code, "run_failed");
  assert.equal(caught.detailSha256.length, 64);
  const receiptText = await readFile(caught.runSummary.receipt_path, "utf8");
  assert.equal(receiptText.includes(privateDetail), false);
});

test("canonicalJson and execution hash are stable across key order and validation status", () => {
  assert.equal(canonicalJson({ b: 2, a: 1 }), canonicalJson({ a: 1, b: 2 }));
  const discovered = syntheticCapability();
  const validated = structuredClone(discovered);
  validated.status = "validated_local";
  validated.validation = {
    environment_scope: "existing_chrome_origin_ui",
    execution_contract_sha256: "f".repeat(64),
    receipts: [],
    known_limits: [],
  };
  assert.equal(executionContractSha256(discovered), executionContractSha256(validated));
});

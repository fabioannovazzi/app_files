import assert from "node:assert/strict";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import { collectEconsReview, validateEconsProfile } from "../plugins/browser-automation/scripts/econs_review.mjs";

const base = JSON.parse(await readFile(new URL("./fixtures/browser_automation_runtime/capability.json", import.meta.url), "utf8"));
const pythonExecutable = process.env.ECONS_TEST_PYTHON;
assert.ok(pythonExecutable, "Set ECONS_TEST_PYTHON to the activated managed Python executable");
const candidate = (value) => ({ kind: "test_id", role: null, value, exact: false });
const condition = (kind = "always", output = null) => ({ kind, locator_candidates: [], value: null, output_ref: output, comparator: null, expected: null, timeout_ms: 10 });
const fieldSets = {
  companies: ["company-code", "nightly"], company: ["company-code"],
  invoices: ["invoice-id", "invoice-number", "supplier", "status"],
  invoice: ["company-code", "invoice-id", "invoice-number", "supplier", "status"],
  lines: ["line-id", "description", "account", "vat-code", "amount"],
};

function profile() {
  const phases = {};
  for (const [name, outputs, inputs] of [
    ["companies", { companies: "record_set", "company-count": "scalar" }, []],
    ["invoices", { company: "record", invoices: "record_set", "invoice-count": "scalar" }, ["company-code"]],
    ["detail", { invoice: "record", lines: "record_set", "line-count": "scalar" }, ["company-code", "invoice-id", "invoice-number"]],
  ]) {
    const cap = structuredClone(base);
    cap.capability_id = `synthetic-econs-${name}`;
    cap.runtime.frame_selectors = ["iframe[title='Synthetic accounting']"];
    cap.inputs = inputs.map((key) => ({ name: key, type: "text", required: true, sensitivity: "private_runtime_only", purpose: "Synthetic identity", enum_values: [] }));
    cap.outputs = Object.entries(outputs).map(([key, type]) => ({ name: key, type, sensitivity: "private", delivery: "model_and_artifact", description: "Synthetic field evidence",
      fields: (fieldSets[key] ?? []).map((field) => ({ name: field, type: field === "nightly" ? "boolean" : "text", required: key !== "lines" || field === "line-id" })) }));
    const actions = [{ ...structuredClone(base.milestones[1].actions[0]), id: `open-${name}`, operation: "click", input_ref: null,
      locator_candidates: [candidate(name === "companies" ? "companies" : name === "invoices" ? "invoices-{{company-code}}" : "detail-{{invoice-id}}")], postcondition: condition("none") }];
    for (const output of cap.outputs) actions.push({
      id: `read-${output.name}`, intent: "Read bounded synthetic values", operation: "extract", effect: "read_only", confirmation: "none",
      locator_candidates: [candidate(output.name)], input_ref: null, key: null, path: null, target_origin: null, output_ref: output.name,
      extract: { mode: output.type === "record_set" ? "list" : output.type === "record" ? "single" : "text", max_items: output.type === "record_set" ? 100 : 1,
        limit_input_ref: null, empty_allowed: false, dedupe_by: [], fields: output.fields.map((field) => ({ name: field.name,
          locator_candidates: [candidate(field.name)], read: { kind: "text_content", attribute: null }, required: field.required })) },
      postcondition: condition("output_nonempty", output.name), timeout_ms: 10,
    });
    cap.entry_milestone = name;
    cap.milestones = [{ id: name, intent: "Acquire the synthetic phase", preconditions: ["Synthetic authorized fixture"], actions,
      transitions: [{ when: condition(), next_milestone: null, terminal: true }] }];
    cap.completion = { terminal_milestones: [name], required_outputs: Object.keys(outputs) };
    phases[name] = cap;
  }
  return { schema_version: "econs-review-profile/v1", phases };
}

class Locator {
  constructor(nodes, tab) { this.nodes = nodes; this.tab = tab; }
  getByTestId(key) { return new Locator(this.nodes.flatMap((node) => node[key] == null ? [] : [{ text: String(node[key]) }]), this.tab); }
  async isVisible() { return this.nodes.length > 0; }
  async isEnabled() { return true; }
  async count() { return this.nodes.length; }
  async waitFor() { assert.ok(this.nodes.length, "synthetic locator missing"); }
  nth(index) { return new Locator(this.nodes.slice(index, index + 1), this.tab); }
  async innerText() { return this.nodes[0].text; }
  async textContent() { return this.nodes[0].text; }
  async click() {
    this.tab.opened.push(this.nodes[0].text);
    this.tab.phase = this.nodes[0].text;
    if (this.tab.phase.startsWith("invoices-")) this.tab.company = this.tab.phase.slice("invoices-".length);
  }
}

class EconsTab {
  constructor({ wrongCompany = false, wrongInvoice = false, missingAccount = false, countMismatch = false, frameOrigin = base.site.allowed_origins[0] } = {}) {
    this.opened = [];
    this.phase = "";
    this.company = "A";
    this.wrongCompany = wrongCompany;
    this.wrongInvoice = wrongInvoice;
    this.missingAccount = missingAccount;
    this.countMismatch = countMismatch;
    this.frameOrigin = frameOrigin;
    const frame = { getByTestId: (key) => this.output(key), locator: () => ({ evaluate: async () => this.frameOrigin }) };
    this.playwright = { locator: () => ({ evaluateAll: async () => true }), frameLocator: () => frame, waitForTimeout: async () => {} };
  }
  async url() { return base.site.start_url; }
  async goto() { throw new Error("unexpected top-level navigation"); }
  output(key) {
    if (["companies", "invoices-A", "detail-1", "detail-2"].includes(key) &&
      (key !== "companies" || this.phase !== "companies")) return new Locator([{ text: key }], this);
    const invoiceId = this.phase === "detail-2" ? "2" : "1";
    const item = (id) => ({ "invoice-id": id, "invoice-number": `N${id}`, supplier: "Synthetic supplier", status: id === "1" ? "green" : "red" });
    const values = {
      companies: [{ "company-code": "A", nightly: true }, { "company-code": "EXCLUDED", nightly: true }, { "company-code": "DAY", nightly: false }],
      "company-count": [{ text: "3" }], company: [{ "company-code": this.wrongCompany ? "OTHER" : this.company }],
      invoices: [item("1"), item("2")], "invoice-count": [{ text: this.countMismatch ? "3" : "2" }],
      invoice: [{ "company-code": this.company, ...item(this.wrongInvoice ? "other" : invoiceId) }],
      lines: [{ "line-id": "1", description: "Full description beyond the visible column <script>bad()</script>", account: this.missingAccount ? "" : "COST", "vat-code": "VAT", amount: "123,45" }],
      "line-count": [{ text: "1" }],
    };
    return new Locator(values[key] ?? [{ text: key }], this);
  }
}

async function run(tab, changes = {}) {
  const parent = await mkdtemp(join(tmpdir(), "econs-review-test-"));
  return collectEconsReview({ tab, profile: profile(), excludedCompanyCodes: ["EXCLUDED"], runDirectory: join(parent, "run"), pythonExecutable, ...changes });
}

test("Playwright phases collect full invoice lines into a saved review, skip excluded companies and never post", async () => {
  const tab = new EconsTab();
  const result = await run(tab);
  assert.equal(result.status, "acquired");
  assert.equal(result.acquired_invoices, 2);
  assert.equal(result.pending_review, 2);
  assert.equal(result.posting_actions, 0);
  assert.deepEqual(tab.opened, ["companies", "invoices-A", "detail-1", "detail-2"]);
  const html = await readFile(result.review_path, "utf8");
  assert.match(html, /Full description beyond the visible column &lt;script&gt;/);
  assert.match(html, /COST/);
  assert.match(html, /VAT/);
  assert.ok(!JSON.stringify(result).includes("Synthetic supplier"));
});

test("saved review uses owner-only permissions on POSIX", { skip: process.platform === "win32" ? "POSIX modes do not describe Windows ACLs" : false }, async () => {
  const result = await run(new EconsTab());
  assert.equal((await stat(result.review_path)).mode & 0o777, 0o600);
});

test("blank account becomes a saved exception rather than an automatic assignment", async () => {
  const result = await run(new EconsTab({ missingAccount: true }));
  assert.equal(result.status, "acquired");
  assert.equal(result.exceptions, 2);
  assert.match(await readFile(result.review_path, "utf8"), /campi mancanti/);
});

test("multiple companies are visited and repeated invoice IDs remain separate per company", async () => {
  const tab = new EconsTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => {
    const locator = original(key);
    if (key === "companies" && tab.phase === "companies") locator.nodes.push({ "company-code": "B", nightly: true });
    if (key === "company-count") locator.nodes = [{ text: "4" }];
    return locator;
  };
  const result = await run(tab);
  assert.equal(result.status, "acquired");
  assert.equal(result.acquired_invoices, 4);
  assert.deepEqual(tab.opened, ["companies", "invoices-A", "detail-1", "detail-2", "invoices-B", "detail-1", "detail-2"]);
  const record = JSON.parse(await readFile(result.review_path.replace(/\.html$/, ".json"), "utf8"));
  assert.equal(new Set(record.payload.entries.map((entry) => entry.id)).size, 4);
});

for (const scenario of ["wrongCompany", "wrongInvoice", "countMismatch"]) {
  test(`${scenario} produces a partial review, not a successful collection`, async () => {
    const result = await run(new EconsTab({ [scenario]: true }));
    assert.equal(result.status, "partial");
    assert.equal(result.expected_items, null);
    assert.equal(result.acquired_invoices, 0);
    assert.ok(await stat(result.review_path));
  });
}

test("unapproved iframe origin prevents even the first navigation click", async () => {
  const tab = new EconsTab({ frameOrigin: "https://unapproved.example" });
  const result = await run(tab);
  assert.equal(result.status, "partial");
  assert.deepEqual(tab.opened, []);
});

test("a failed later invoice preserves the previously acquired populated review", async () => {
  const tab = new EconsTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => {
    if (tab.phase === "detail-2" && key === "invoice") tab.wrongInvoice = true;
    return original(key);
  };
  const result = await run(tab);
  assert.equal(result.status, "partial");
  assert.equal(result.acquired_invoices, 1);
  const html = await readFile(result.review_path, "utf8");
  assert.match(html, /COST/);
  assert.match(html, /Acquisizione interrotta/);
});

test("consequential and form-write phases are rejected before browser use", () => {
  const value = profile();
  value.phases.detail.milestones[0].actions[0].effect = "consequential";
  assert.throws(() => validateEconsProfile(value), /must_not_write/);
  value.phases.detail.milestones[0].actions[0].effect = "reversible";
  value.phases.detail.milestones[0].actions[0].operation = "fill";
  assert.throws(() => validateEconsProfile(value), /must_not_write/);
});

test("draft profiles and output inside Git are rejected", async () => {
  const value = profile();
  value.phases.companies.status = "draft";
  assert.throws(() => validateEconsProfile(value), /reviewed_discovery/);
  await assert.rejects(() => run(new EconsTab(), { runDirectory: resolve("econs-private-test") }), /outside_git/);
});

test("batch limit stops before collecting invoice details and preserves a partial review", async () => {
  const tab = new EconsTab();
  const result = await run(tab, { maxInvoices: 1 });
  assert.equal(result.status, "partial");
  assert.deepEqual(tab.opened, ["companies", "invoices-A"]);
});

test("duplicate invoice identities stop before opening an ambiguous detail", async () => {
  const tab = new EconsTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => {
    const locator = original(key);
    if (key === "invoices") locator.nodes[1]["invoice-id"] = "1";
    return locator;
  };
  const result = await run(tab);
  assert.equal(result.error.reason_code, "missing_or_duplicate_identity");
  assert.deepEqual(tab.opened, ["companies", "invoices-A"]);
});

test("a positively observed zero population creates an empty review without opening any company", async () => {
  const value = profile();
  const companyPhase = value.phases.companies;
  const rowAction = companyPhase.milestones[0].actions.find((action) => action.output_ref === "companies");
  companyPhase.milestones[0].actions = companyPhase.milestones[0].actions.filter((action) => action !== rowAction);
  companyPhase.milestones[0].transitions = [
    { when: { ...condition("locator_visible"), locator_candidates: [candidate("no-companies")] }, terminal: true, next_milestone: null },
    { when: condition(), terminal: false, next_milestone: "company-rows" },
  ];
  companyPhase.milestones.push({ id: "company-rows", intent: "Read the nonempty branch", preconditions: [], actions: [rowAction],
    transitions: [{ when: condition(), terminal: true, next_milestone: null }] });
  companyPhase.completion.terminal_milestones.push("company-rows");
  const tab = new EconsTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => key === "company-count" ? new Locator([{ text: "0" }], tab) : original(key);
  const result = await run(tab, { profile: value });
  assert.equal(result.status, "acquired");
  assert.equal(result.expected_items, 0);
  assert.deepEqual(tab.opened, ["companies"]);
});

test("frame navigation during locator resolution is rejected before invoice fields are read", async () => {
  const tab = new EconsTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => {
    if (key === "invoice") tab.frameOrigin = "https://unapproved.example";
    return original(key);
  };
  const result = await run(tab);
  assert.equal(result.status, "partial");
  assert.equal(result.acquired_invoices, 0);
  assert.equal(result.error.reason_code, "phase_detail_failed");
  const receipt = JSON.parse(await readFile(result.receipts.at(-1), "utf8"));
  assert.equal(receipt.result, "failed");
  assert.equal(receipt.outputs[0].record_count, 0);
});

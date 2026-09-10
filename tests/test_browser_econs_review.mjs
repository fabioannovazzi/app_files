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

// Exercise the real capability executor against a synthetic ECONS adapter.
// Synthetic receipts prove implementation behavior, never live portal support.
const { planEconsMapping, italianCents, verifyEconsJournal } = await import('../plugins/browser-automation/scripts/econs_processing.mjs');
function processingProfile() {
  const phases = {};
  const shapes = { journal: ['company-code', 'invoice-id', 'invoice-number', 'supplier', 'account', 'net', 'cost', 'vat', 'total', 'debit', 'credit'],
    posting: ['company-code', 'invoice-id', 'protocol'], company: ['company-code', 'view'], invoices: ['invoice-id'] };
  for (const name of ['select', 'map', 'journal', 'post', 'verify', 'exit']) {
    const cap = structuredClone(base);
    cap.capability_id = `synthetic-processing-${name}`;
    cap.inputs = ['company-code', 'invoice-id', 'invoice-number', 'supplier', ...(name === 'select' ? ['line-id', 'checked'] : name === 'map' ? ['anchor-line-id', 'checked'] : [])].map((key) => ({
      name: key, type: key === 'checked' ? 'boolean' : 'text', required: true, sensitivity: 'private_runtime_only', purpose: 'Synthetic context', enum_values: [] }));
    const outputNames = name === 'journal' ? ['journal'] : name === 'post' ? ['posting'] : name === 'verify' ? ['company', 'invoices', 'invoice-count'] : ['ready'];
    cap.outputs = outputNames.map((key) => ({ name: key, type: key === 'invoices' ? 'record_set' : ['invoice-count', 'ready'].includes(key) ? 'scalar' : 'record',
      sensitivity: 'private', delivery: 'model_and_artifact', description: 'Synthetic check', fields: (shapes[key] ?? []).map((field) => ({ name: field, type: 'text', required: true })) }));
    function action(id, operation, locator = id) {
      return { ...structuredClone(base.milestones[1].actions[0]), id, operation, input_ref: operation === 'set_checked' ? 'checked' : null,
        locator_candidates: [candidate(locator)], postcondition: condition('none') };
    }
    const phaseActions = name === 'select' ? [action('select-line', 'set_checked', 'line-{{line-id}}')] : name === 'map' ? [action('open-mapping', 'click'), action('associate-all', 'set_checked'), action('confirm-mapping', 'click')] : [action(`open-${name}`, 'click')];
    if (name === 'post') Object.assign(phaseActions[0], { id: 'confirm-registration', effect: 'consequential', confirmation: 'action_time' });
    for (const output of cap.outputs) phaseActions.push({ ...action(`extract-${output.name}`, 'extract', output.name), effect: 'read_only', output_ref: output.name,
      extract: { mode: output.type === 'record_set' ? 'list' : output.type === 'record' ? 'single' : 'text', max_items: output.type === 'record_set' ? 100 : 1, limit_input_ref: null, empty_allowed: output.type === 'record_set', dedupe_by: [],
        fields: output.fields.map((field) => ({ name: field.name, locator_candidates: [candidate(field.name)], read: { kind: 'text_content', attribute: null }, required: true })) } });
    cap.entry_milestone = name;
    cap.milestones = [{ id: name, intent: 'Synthetic processing phase', preconditions: [], actions: phaseActions, transitions: [{ when: condition(), terminal: true, next_milestone: null }] }];
    cap.completion = { terminal_milestones: [name], required_outputs: outputNames };
    phases[name] = cap;
  }
  return { schema_version: 'econs-processing-profile/v1', complete_status: 'complete', non_posted_view: 'non-posted', phases };
}

class ProcessingTab extends EconsTab {
  constructor(options = {}) {
    super(); this.options = options; this.checked = options.checked ?? false; this.checkboxValues = []; this.postCount = 0; this.mapped = false;
    this.playwright.getByTestId = (key) => this.output(key);
  }
  output(key) {
    const locator = super.output(key);
    const id = this.phase === 'detail-2' ? '2' : '1';
    if (key === 'lines') locator.nodes = [
      { 'line-id': '1', description: 'Long full source description', account: 'COST', 'vat-code': '22', amount: '10,00' },
      { 'line-id': '2', description: 'Second invoice line', account: this.options.discordant ? 'OTHER' : 'COST', 'vat-code': '22', amount: '10,00' },
      { 'line-id': '3', description: 'Third invoice line', account: this.mapped ? 'COST' : '', 'vat-code': '22', amount: '10,00' },
    ];
    if (key === 'line-count') locator.nodes = [{ text: this.options.partialLines ? '4' : '3' }];
    if (key === 'invoice' && this.mapped) locator.nodes[0].status = 'complete';
    if (key === 'journal') locator.nodes = [{ 'company-code': 'A', 'invoice-id': id, 'invoice-number': `N${id}`, supplier: 'Synthetic supplier', account: 'COST', net: '30,00', cost: '36,60', vat: '0,00', total: '36,60', debit: '36,60', credit: this.options.unbalanced ? '36,59' : '36,60' }];
    if (key === 'posting') locator.nodes = [{ 'company-code': 'A', 'invoice-id': id, protocol: 'SYNTHETIC-PROTOCOL' }];
    if (this.verifying && key === 'company') locator.nodes = [{ 'company-code': this.options.wrongVerifyCompany ? 'B' : 'A', view: 'non-posted' }];
    if (this.verifying && key === 'invoices') locator.nodes = this.options.stillPresent ? [{ 'invoice-id': id }] : [{ 'invoice-id': '2' }];
    if (this.verifying && key === 'invoice-count') locator.nodes = [{ text: '1' }];
    locator.setChecked = async (value) => { this.checkboxValues.push([key, value]); if (key === 'associate-all') this.checked = value; };
    if (['open-mapping', 'confirm-mapping', 'open-journal', 'open-post', 'open-verify', 'open-exit'].includes(key)) locator.click = async () => {
      this.opened.push(key);
      if (key === 'confirm-mapping' && !this.options.mappingFailed) this.mapped = this.checked;
      if (key === 'open-post') this.postCount += 1;
      if (key === 'open-verify') this.verifying = true;
      if (key === 'open-exit') this.verifying = false;
    };
    return locator;
  }
}
function processing(changes = {}) {
  return { profile: processingProfile(), classifyInvoices: async () => ({ company_code: 'A', red_invoice_ids: ['2'], reason: 'Operator-reviewed synthetic red indicator' }),
    reviewJournal: async () => ({ approved: true, reason: 'Ditta con indetraibilità confermata al 100%', company_code: 'A', treatment_source: 'Configurazione ditta verificata', vat_nondeductible_percent: 100 }),
    approvePosting: async () => true, ...changes };
}

for (const checked of [false, true]) test(`mapping and posting preserve checkbox state from ${checked} and save the client report`, async () => {
  const tab = new ProcessingTab({ checked });
  const result = await run(tab, { processing: processing() });
  assert.equal(result.status, 'processed');
  assert.equal(result.completed, 1);
  assert.equal(tab.postCount, 1);
  assert.deepEqual(tab.checkboxValues, [['line-1', true], ['line-2', true], ['line-3', true], ['associate-all', true]]);
  const html = await readFile(result.client_reviews[0], 'utf8');
  assert.match(html, /SYNTHETIC-PROTOCOL/);
  assert.match(html, /100%/);
  assert.match(html, /Long full source description/);
  assert.match(html, /rossa/);
});

for (const scenario of ['discordant', 'mappingFailed', 'unbalanced', 'wrongVerifyCompany', 'stillPresent']) test(`${scenario} remains an exception with no unsafe retry`, async () => {
  const tab = new ProcessingTab({ [scenario]: true });
  const result = await run(tab, { processing: processing() });
  assert.equal(result.completed, 0);
  assert.equal(tab.postCount, ['wrongVerifyCompany', 'stillPresent'].includes(scenario) ? 1 : 0);
  const record = JSON.parse(await readFile(result.review_path.replace(/\.html$/, '.json'), 'utf8'));
  assert.equal(record.payload.entries[0].status, tab.postCount ? 'unverified' : 'set_aside');
  assert.ok(tab.opened.includes('open-exit'));
});

test('unapproved posting never dispatches registration', async () => {
  const tab = new ProcessingTab();
  const result = await run(tab, { processing: processing({ approvePosting: async () => false }) });
  assert.equal(tab.postCount, 0);
  assert.equal(result.completed, 0);
});

test('Italian money retains thousands and cents and rejects decimal-dot ambiguity', () => {
  assert.equal(italianCents('1.234,56'), 123456n);
  assert.equal(italianCents('12'), 1200n);
  assert.throws(() => italianCents('12.34'), /invalid_italian/);
});

test('complete line population and matching VAT are required before mapping', () => {
  const detail = { 'line-count': '3', lines: [{ 'line-id': '1', description: 'A', account: 'C', 'vat-code': '22', amount: '1,00' }, { 'line-id': '2', description: 'B', account: 'C', 'vat-code': '22', amount: '1,00' }, { 'line-id': '3', description: 'C', account: '', 'vat-code': '10', amount: '1,00' }] };
  assert.throws(() => planEconsMapping(detail), /different_vat/);
  assert.throws(() => planEconsMapping({ ...detail, 'line-count': '4' }), /incomplete_line_population/);
});

test('a changed journal after approval stops before registration', async () => {
  const tab = new ProcessingTab();
  const result = await run(tab, { processing: processing({ approvePosting: async () => { tab.options.unbalanced = true; return true; } }) });
  assert.equal(result.completed, 0);
  assert.equal(tab.postCount, 0);
});

test('rounding differences require a professional explanation and 100 percent VAT must remain in cost', () => {
  const invoice = { 'company-code': 'A', 'invoice-id': '1', 'invoice-number': 'N1', supplier: 'S' };
  const journal = { ...invoice, account: 'C', net: '1,01', cost: '1,22', vat: '0,00', total: '1,22', debit: '1,22', credit: '1,22' };
  const detail = { lines: [{ amount: '1,00' }] };
  const review = { approved: true, reason: 'Confirmed company treatment', company_code: 'A', treatment_source: 'Company configuration', vat_nondeductible_percent: 100 };
  assert.throws(() => verifyEconsJournal(journal, invoice, detail, { account: 'C' }, review), /unexplained_rounding/);
  assert.doesNotThrow(() => verifyEconsJournal(journal, invoice, detail, { account: 'C' }, { ...review, rounding_explanation: 'Source invoice rounding reviewed' }));
  assert.throws(() => verifyEconsJournal({ ...journal, cost: '1,00', vat: '0,22' }, invoice, detail, { account: 'C' }, review), /not_in_cost/);
});

test('more than two consecutive red items suspend the remaining client and preserve every item in its report', async () => {
  const tab = new ProcessingTab();
  const original = tab.output.bind(tab);
  tab.output = (key) => {
    const locator = original(key);
    if (key === 'invoices' && !tab.verifying) locator.nodes = ['1', '2', '3', '4', '5'].map((id) => ({ 'invoice-id': id, 'invoice-number': `N${id}`, supplier: 'Synthetic supplier', status: ['2', '3', '4'].includes(id) ? 'red' : 'green' }));
    if (key === 'invoice-count' && !tab.verifying) locator.nodes = [{ text: '5' }];
    return locator;
  };
  const result = await run(tab, { processing: processing({ classifyInvoices: async () => ({ company_code: 'A', red_invoice_ids: ['2', '3', '4'], reason: 'Reviewed synthetic indicators' }) }) });
  assert.equal(result.completed, 1);
  assert.equal(tab.postCount, 1);
  assert.ok(!tab.opened.includes('detail-5'));
  const report = JSON.parse(await readFile(result.client_reviews[0].replace(/\.html$/, '.json'), 'utf8'));
  assert.equal(report.payload.entries.length, 5);
  assert.match(report.payload.entries[4].outcome, /oltre due rossi/);
});

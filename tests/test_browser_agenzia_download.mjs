import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { downloadAgenziaInvoices } from "../plugins/browser-automation/scripts/agenzia_download.mjs";
import { FakeAgenziaTab } from "./fixtures/browser_agenzia_tab.mjs";

async function setup(options = {}) {
  const root = await mkdtemp(join(tmpdir(), "agenzia-regression-"));
  const downloadDirectory = join(root, "downloads");
  await mkdir(downloadDirectory);
  return { tab: new FakeAgenziaTab(downloadDirectory, options),
    downloadDirectory, runDirectory: join(root, "run"), direction: "active",
    dateFrom: "2026-09-01", dateTo: "2026-09-11", executionMode: "simulated",
    expectedCounts: { active: 2 }, timeoutMs: 5000 };
}

test("active and passive downloads produce checked counts but remain prototype evidence", async () => {
  const result = await downloadAgenziaInvoices({ ...await setup(), direction: "both", expectedCounts: { active: 2, passive: 2 } });
  assert.equal(result.status, "completed");
  assert.equal(result.total_downloads, 4);
  assert.deepEqual(result.direction_counts, { active: 2, passive: 2 });
  assert.equal(result.validation_status, "prototype");
  assert.equal(result.execution_mode, "simulated");
});

test("actually advances to a second result page and downloads its distinct invoice", async () => {
  const result = await downloadAgenziaInvoices(await setup({ pages: 2, rows: 1 }));
  assert.equal(result.status, "completed");
  assert.equal(result.total_downloads, 2);
  assert.equal(result.pages_visited.active, 2);
});

test("missing tab before first download persists a sanitized failure report", async () => {
  const input = await setup();
  input.tab.url = async () => { throw new Error("No tab with id: private-tab-value"); };
  const result = await downloadAgenziaInvoices(input);
  assert.equal(result.status, "failed");
  assert.equal(result.error.code, "browser_tab_unavailable");
  assert.equal(result.total_downloads, 0);
  assert.doesNotMatch(await readFile(result.report_path, "utf8"), /private-tab-value/);
  assert.deepEqual((await readdir(input.runDirectory)).sort(), ["outputs.json", "run-state-000000.json"]);
});

test("mid-batch tab loss retains the first verified download and no completion claim", async () => {
  const result = await downloadAgenziaInvoices(await setup({ failRow: 1 }));
  assert.equal(result.status, "failed");
  assert.equal(result.total_downloads, 1);
  assert.equal(result.error.code, "browser_tab_unavailable");
  const report = JSON.parse(await readFile(result.report_path, "utf8"));
  assert.equal(report.downloads[0].sha256.length, 64);
});

test("an early last page cannot claim the independently observed total", async () => {
  const result = await downloadAgenziaInvoices({ ...await setup({ rows: 1 }), expectedCounts: { active: 2 } });
  assert.equal(result.status, "failed");
  assert.equal(result.error.code, "invoice-population-incomplete");
});

test("same detail URL for distinct rows is rejected rather than silently skipped", async () => {
  const result = await downloadAgenziaInvoices(await setup({ sameDetailUrl: true }));
  assert.equal(result.status, "failed");
  assert.equal(result.total_downloads, 1);
  assert.equal(result.error.code, "invoice-identity-not-unique");
});

test("missing observed total fails before any portal interaction", async () => {
  const input = await setup();
  input.tab.url = () => { assert.fail("must not access the portal"); };
  const result = await downloadAgenziaInvoices({ ...input, expectedCounts: null });
  assert.equal(result.error.code, "expected-invoice-counts-required");
});


test("tab loss immediately after the verified download still retains its bytes", async () => {
  const result = await downloadAgenziaInvoices(await setup({ loseTabAfterDownload: true }));
  assert.equal(result.status, "failed");
  assert.equal(result.total_downloads, 1);
  assert.equal(result.pages_visited.active, 1);
  assert.equal(result.error.code, "browser_tab_unavailable");
});

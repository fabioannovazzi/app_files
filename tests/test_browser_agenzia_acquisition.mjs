import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { acquireAgenziaInvoices } from "../plugins/browser-automation/scripts/agenzia_acquisition.mjs";
import { FakeAgenziaTab } from "./fixtures/browser_agenzia_tab.mjs";
import { syntheticSignedP7m } from "./fixtures/p7m.mjs";

const XML = "<?xml version=\"1.0\"?><p:FatturaElettronica xmlns:p=\"urn:test\"></p:FatturaElettronica>";

async function setup(options = {}) {
  const root = await mkdtemp(join(tmpdir(), "agenzia-acquisition-"));
  const downloadDirectory = join(root, "downloads");
  const nativePdfDirectory = join(root, "native-pdf");
  await mkdir(downloadDirectory);
  await mkdir(nativePdfDirectory);
  return {
    root,
    tab: new FakeAgenziaTab(downloadDirectory, options),
    downloadDirectory,
    nativePdfDirectory,
    runDirectory: join(root, "run"),
    categoryPlan: [{
      category: "fatture-emesse",
      accessibleName: "Fatture emesse",
      dateFrom: "2026-01-01",
      dateTo: "2026-12-31",
      expectedCount: 2,
      formats: { original: "available", pdf: "unavailable" }
    }],
    executionMode: "simulated",
    timeoutMs: 5000
  };
}

test("uses partial accessible category names and archives every verified P7M/XML pair", async () => {
  const input = await setup({
    categoryNames: { issued: "★ Fatture emesse" },
    originalBytes: syntheticSignedP7m(Buffer.from(XML))
  });
  const result = await acquireAgenziaInvoices(input);

  assert.equal(result.status, "completed");
  assert.equal(result.total_documents, 2);
  assert.equal(result.request_summaries[0].observed_count, 2);
  assert.equal(result.request_summaries[0].completed_count, 2);
  assert.equal(result.validation_status, "prototype");
  const report = JSON.parse(await readFile(result.report_path, "utf8"));
  assert.deepEqual(report.documents.map((item) => item.original.kind), ["p7m", "p7m"]);
  assert.equal(report.documents[0].original.extracted_xml.source_p7m_sha256,
    report.documents[0].original.original.sha256);
  assert.equal(input.tab.filled.from, "01/01/2026");
  assert.equal(input.tab.filled.to, "31/12/2026");
});

test("reconciles pagination and keeps category archives separate", async () => {
  const input = await setup({
    pages: 2,
    rows: 1,
    categoryNames: {
      issued: "Fatture emesse",
      crossBorder: "Fatture transfrontaliere ricevute"
    }
  });
  input.categoryPlan.push({
    category: "transfrontaliere-ricevute",
    accessibleName: "transfrontaliere ricevute",
    dateFrom: "2026-01-01",
    dateTo: "2026-12-31",
    expectedCount: 2,
    formats: { original: "available", pdf: "unavailable" }
  });
  const result = await acquireAgenziaInvoices(input);

  assert.equal(result.status, "completed");
  assert.deepEqual(result.request_summaries.map((item) => item.pages_visited), [2, 2]);
  assert.deepEqual((await readdir(join(input.runDirectory, "archive", "2026"))).sort(), [
    "fatture-emesse",
    "transfrontaliere-ricevute"
  ]);
});

test("verifies operator-saved PDFs but excludes native-gap runs from clean browser validation", async () => {
  const input = await setup({ categoryNames: { issued: "Fatture emesse" }, rows: 1 });
  input.categoryPlan[0].expectedCount = 1;
  input.categoryPlan[0].formats.pdf = "native_gap";
  const result = await acquireAgenziaInvoices({
    ...input,
    onNativePdf: async ({ printControl, page, row }) => {
      await printControl.click();
      await writeFile(join(input.nativePdfDirectory, `invoice-${page}-${row}.pdf`), "%PDF-1.7\nfixture\n%%EOF\n");
      return { completed: true };
    }
  });

  assert.equal(result.status, "completed");
  assert.equal(result.browser_validation_eligible, false);
  assert.deepEqual(result.native_gaps, ["operator-save-as-pdf"]);
  const report = JSON.parse(await readFile(result.report_path, "utf8"));
  assert.equal(report.documents[0].format_status.pdf, "verified_native_gap");
});

test("resumes after interruption without redownloading a retained verified artifact", async () => {
  const first = await setup({ categoryNames: { issued: "Fatture emesse" }, failRow: 1 });
  const interrupted = await acquireAgenziaInvoices(first);
  assert.equal(interrupted.status, "failed");
  assert.equal(interrupted.total_documents, 1);
  const before = JSON.parse(await readFile(interrupted.report_path, "utf8"));
  const retainedHash = before.documents[0].original.original.sha256;

  const resumed = await acquireAgenziaInvoices({
    ...first,
    tab: new FakeAgenziaTab(first.downloadDirectory, { categoryNames: { issued: "Fatture emesse" } }),
    resume: true
  });
  assert.equal(resumed.status, "completed");
  assert.equal(resumed.total_documents, 2);
  const after = JSON.parse(await readFile(resumed.report_path, "utf8"));
  assert.equal(after.documents[0].original.original.sha256, retainedHash);
  assert.deepEqual((await readdir(first.runDirectory)).filter((name) => name.startsWith("attempt-")).sort(), [
    "attempt-000001.outputs.json",
    "attempt-000002.outputs.json"
  ]);
});

test("reports a population mismatch instead of claiming an incomplete category", async () => {
  const input = await setup({ categoryNames: { issued: "Fatture emesse" }, rows: 1 });
  const result = await acquireAgenziaInvoices(input);
  assert.equal(result.status, "failed");
  assert.equal(result.error.code, "invoice-population-incomplete");
  assert.equal(result.request_summaries[0].observed_count, 1);
  assert.equal(result.missing_documents, 1);
});

test("records formats declared unavailable without attempting either acquisition route", async () => {
  const input = await setup({ categoryNames: { issued: "Fatture emesse" }, rows: 1, includePrint: false });
  input.categoryPlan[0].expectedCount = 1;
  input.categoryPlan[0].formats = { original: "unavailable", pdf: "unavailable" };
  const result = await acquireAgenziaInvoices(input);
  assert.equal(result.status, "completed");
  assert.equal(result.request_summaries[0].completed_count, 1);
  const report = JSON.parse(await readFile(result.report_path, "utf8"));
  assert.deepEqual(report.documents[0].format_status, { original: "unavailable", pdf: "unavailable" });
});

test("blocks resume when a retained artifact no longer matches its recorded hash", async () => {
  const input = await setup({ categoryNames: { issued: "Fatture emesse" }, rows: 1 });
  input.categoryPlan[0].expectedCount = 1;
  const complete = await acquireAgenziaInvoices(input);
  const report = JSON.parse(await readFile(complete.report_path, "utf8"));
  await writeFile(report.documents[0].original.original.path, `${XML}tampered`);
  const tab = new FakeAgenziaTab(input.downloadDirectory, { categoryNames: { issued: "Fatture emesse" } });
  tab.url = () => assert.fail("must not touch the portal before retained evidence passes verification");

  await assert.rejects(acquireAgenziaInvoices({ ...input, tab, resume: true }), {
    code: "download-file-changed"
  });
});

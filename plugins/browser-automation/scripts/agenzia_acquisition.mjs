/** Resumable Agenzia invoice acquisition for explicit, model-reviewed category plans. */
import { createHash } from "node:crypto";
import { chmod, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

import {
  AgenziaArtifactError,
  archiveInvoiceOriginal,
  archiveNativePdf,
  verifyArchivedArtifact
} from "./agenzia_artifacts.mjs";
import { DownloadDirectoryError, observeDownloadDirectory } from "./download_directory.mjs";
import { browserFailureCode } from "./browser_session.mjs";

const ALLOWED_ORIGIN = "https://ivaservizi.agenziaentrate.gov.it";
const FORMAT_STATES = new Set(["available", "native_gap", "unavailable"]);
const EXECUTION_MODES = new Set(["unverified", "simulated", "live_connected_chrome"]);

export class AgenziaAcquisitionError extends Error {
  constructor(code, cause) {
    super(code, cause ? { cause } : undefined);
    this.name = "AgenziaAcquisitionError";
    this.code = code;
  }
}

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function formatItalianDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value ?? "")) {
    throw new AgenziaAcquisitionError("invalid-date-format");
  }
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    throw new AgenziaAcquisitionError("invalid-date-value");
  }
  return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
}

function normalizePlan(plan) {
  if (!Array.isArray(plan) || plan.length < 1 || plan.length > 100) {
    throw new AgenziaAcquisitionError("category-plan-required");
  }
  const keys = new Set();
  return plan.map((item) => {
    if (!item || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.category ?? "")) {
      throw new AgenziaAcquisitionError("category-id-invalid");
    }
    if (typeof item.accessibleName !== "string" || item.accessibleName.trim().length < 3) {
      throw new AgenziaAcquisitionError("category-accessible-name-required");
    }
    if (!Number.isInteger(item.expectedCount) || item.expectedCount < 0) {
      throw new AgenziaAcquisitionError("expected-invoice-count-required");
    }
    const dateFrom = item.dateFrom;
    const dateTo = item.dateTo;
    const from = formatItalianDate(dateFrom);
    const to = formatItalianDate(dateTo);
    if (dateFrom > dateTo || dateFrom.slice(0, 4) !== dateTo.slice(0, 4)) {
      throw new AgenziaAcquisitionError("single-year-date-range-required");
    }
    const year = dateFrom.slice(0, 4);
    const key = `${year}-${item.category}`;
    if (keys.has(key)) throw new AgenziaAcquisitionError("category-period-duplicate");
    keys.add(key);
    const formats = {
      original: item.formats?.original ?? "available",
      pdf: item.formats?.pdf ?? "unavailable"
    };
    if (!FORMAT_STATES.has(formats.original) || !FORMAT_STATES.has(formats.pdf)) {
      throw new AgenziaAcquisitionError("format-availability-invalid");
    }
    if (formats.original === "native_gap" || formats.pdf === "available") {
      throw new AgenziaAcquisitionError("format-route-invalid");
    }
    return {
      key,
      category: item.category,
      accessibleName: item.accessibleName.trim(),
      dateFrom,
      dateTo,
      from,
      to,
      year,
      expectedCount: item.expectedCount,
      formats,
      labels: {
        from: item.labels?.from?.trim() || "Dal",
        to: item.labels?.to?.trim() || "Al"
      }
    };
  });
}

async function assertAllowedOrigin(tab) {
  const current = new URL(await tab.url());
  if (current.origin !== ALLOWED_ORIGIN) {
    throw new AgenziaAcquisitionError("origin-outside-authorized-boundary");
  }
}

async function waitUntil(tab, predicate, code, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await tab.playwright.waitForTimeout(200);
  }
  throw new AgenziaAcquisitionError(code);
}

async function unique(locator, code) {
  if ((await locator.count()) !== 1) throw new AgenziaAcquisitionError(code);
  return locator;
}

function partialName(value) {
  return new RegExp(escapeRegex(value), "i");
}

async function labeledTextbox(tab, label, code) {
  const accessibleLabel = new RegExp(`^\\s*${escapeRegex(label)}(?:\\s*:)?\\s*$`, "i");
  if (typeof tab.playwright.getByLabel === "function") {
    const labeled = tab.playwright.getByLabel(accessibleLabel);
    if ((await labeled.count()) === 1) return labeled;
  }
  return unique(tab.playwright.getByRole("textbox", { name: accessibleLabel }), code);
}

async function uniqueRoleChoice(tab, roles, name, code) {
  const matches = [];
  for (const role of roles) {
    const locator = tab.playwright.getByRole(role, { name: partialName(name) });
    if ((await locator.count()) === 1) matches.push(locator);
    else if ((await locator.count()) > 1) throw new AgenziaAcquisitionError(code);
  }
  if (matches.length !== 1) throw new AgenziaAcquisitionError(code);
  return matches[0];
}

async function persistRevision(context, state) {
  const sequence = context.nextRevision;
  const snapshot = {
    ...state,
    revision: sequence,
    previous_revision_sha256: context.previousHash
  };
  const bytes = Buffer.from(`${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  await writeFile(join(context.runDirectory, `run-state-${String(sequence).padStart(6, "0")}.json`), bytes, {
    flag: "wx",
    mode: 0o600
  });
  context.previousHash = sha256(bytes);
  context.nextRevision += 1;
  state.revision = sequence;
  state.previous_revision_sha256 = snapshot.previous_revision_sha256;
}

async function loadState(runDirectory) {
  const names = (await readdir(runDirectory))
    .filter((name) => /^run-state-\d{6}\.json$/.test(name))
    .sort();
  if (names.length < 1) throw new AgenziaAcquisitionError("resume-state-missing");
  let previousHash = null;
  let state = null;
  for (let index = 0; index < names.length; index += 1) {
    if (names[index] !== `run-state-${String(index).padStart(6, "0")}.json`) {
      throw new AgenziaAcquisitionError("resume-revision-gap");
    }
    const bytes = await readFile(join(runDirectory, names[index]));
    let payload;
    try {
      payload = JSON.parse(bytes.toString("utf8"));
    } catch (error) {
      throw new AgenziaAcquisitionError("resume-state-invalid", error);
    }
    if (payload.revision !== index || payload.previous_revision_sha256 !== previousHash) {
      throw new AgenziaAcquisitionError("resume-revision-chain-invalid");
    }
    previousHash = sha256(bytes);
    state = payload;
  }
  return {
    state,
    context: { runDirectory, nextRevision: names.length, previousHash }
  };
}

async function verifyRetainedArtifacts(state, archiveRoot) {
  for (const document of state.documents) {
    if (document.original) {
      await verifyArchivedArtifact(document.original.original, { allowedRoot: archiveRoot });
      if (document.original.extracted_xml) {
        await verifyArchivedArtifact(document.original.extracted_xml, { allowedRoot: archiveRoot });
      }
    }
    if (document.pdf) await verifyArchivedArtifact(document.pdf, { allowedRoot: archiveRoot });
  }
}

async function observeBrowserDownload({ tab, control, downloadDirectory, timeoutMs }) {
  if (typeof tab.playwright.waitForEvent !== "function") {
    throw new AgenziaAcquisitionError("download-event-api-unavailable");
  }
  const observation = await observeDownloadDirectory(downloadDirectory);
  try {
    const eventPromise = Promise.resolve(tab.playwright.waitForEvent("download", { timeoutMs })).then(
      (download) => ({ download, error: null }),
      (error) => ({ download: null, error })
    );
    await control.click({ timeoutMs });
    const event = await eventPromise;
    if (event.error || !event.download) {
      throw new AgenziaAcquisitionError("download-event-not-observed", event.error);
    }
    return await observation.wait({ timeoutMs });
  } finally {
    await observation.close();
  }
}

async function acquireOriginal({ tab, plan, documentKey, downloadDirectory, archiveRoot, timeoutMs }) {
  const control = await uniqueRoleChoice(
    tab,
    ["button", "link"],
    "download file fattura",
    "original-download-control-not-unique"
  );
  const evidence = await observeBrowserDownload({ tab, control, downloadDirectory, timeoutMs });
  return archiveInvoiceOriginal({
    evidence,
    archiveRoot,
    year: plan.year,
    category: plan.category,
    documentKey
  });
}

async function acquireNativePdf({
  tab,
  plan,
  documentKey,
  page,
  row,
  nativePdfDirectory,
  archiveRoot,
  timeoutMs,
  onNativePdf
}) {
  if (typeof onNativePdf !== "function") {
    throw new AgenziaAcquisitionError("native-pdf-handoff-required");
  }
  const viewControl = await uniqueRoleChoice(
    tab,
    ["button", "link"],
    "visualizza file fattura",
    "invoice-view-control-not-unique"
  );
  await viewControl.click({ timeoutMs });
  await waitUntil(tab, async () =>
    (await tab.playwright.getByRole("button", { name: /Stampa/i }).count()) +
      (await tab.playwright.getByRole("link", { name: /Stampa/i }).count()) > 0,
  "print-control-not-ready", timeoutMs);
  await assertAllowedOrigin(tab);
  const printControl = await uniqueRoleChoice(tab, ["button", "link"], "Stampa", "print-control-not-unique");
  const observation = await observeDownloadDirectory(nativePdfDirectory);
  try {
    let printClicked = false;
    const trackedPrintControl = {
      click: async (options) => {
        await printControl.click(options);
        printClicked = true;
      }
    };
    const handoff = await onNativePdf({
      tab,
      printControl: trackedPrintControl,
      category: plan.category,
      year: plan.year,
      page,
      row
    });
    if (!printClicked) throw new AgenziaAcquisitionError("native-pdf-print-not-invoked");
    if (handoff?.completed !== true) throw new AgenziaAcquisitionError("native-pdf-not-completed");
    const evidence = await observation.wait({ timeoutMs });
    return archiveNativePdf({
      evidence,
      archiveRoot,
      year: plan.year,
      category: plan.category,
      documentKey
    });
  } finally {
    await observation.close();
  }
}

async function openSearch(tab, plan, timeoutMs) {
  await assertAllowedOrigin(tab);
  const home = await uniqueRoleChoice(tab, ["link", "button"], "Home consultazione", "home-control-not-unique");
  await home.click({ timeoutMs });
  await assertAllowedOrigin(tab);
  const category = await unique(
    tab.playwright.getByRole("link", { name: partialName(plan.accessibleName) }),
    "category-control-not-unique"
  );
  await category.click({ timeoutMs });
  await assertAllowedOrigin(tab);
  const from = await labeledTextbox(tab, plan.labels.from, "date-from-control-not-unique");
  const to = await labeledTextbox(tab, plan.labels.to, "date-to-control-not-unique");
  await from.fill(plan.from, { timeoutMs });
  await to.fill(plan.to, { timeoutMs });
  const search = await uniqueRoleChoice(tab, ["button", "link"], "Cerca", "search-control-not-unique");
  await search.click({ timeoutMs });
  await assertAllowedOrigin(tab);
}

function detailLinks(tab) {
  return tab.playwright.getByRole("link", { name: /Dettaglio fattura/i });
}

async function detailReady(tab, plan) {
  if (plan.formats.original === "available") {
    return (await tab.playwright.getByRole("button", { name: /download file fattura/i }).count()) +
      (await tab.playwright.getByRole("link", { name: /download file fattura/i }).count()) > 0;
  }
  if (plan.formats.pdf === "native_gap") {
    return (await tab.playwright.getByRole("button", { name: /visualizza file fattura/i }).count()) +
      (await tab.playwright.getByRole("link", { name: /visualizza file fattura/i }).count()) > 0;
  }
  return (await tab.playwright.getByRole("link", { name: /Torna alla pagina precedente/i }).count()) +
    (await tab.playwright.getByRole("button", { name: /Torna alla pagina precedente/i }).count()) > 0;
}

async function resultState(tab, timeoutMs) {
  const details = detailLinks(tab);
  const empty = tab.playwright.getByRole("heading", { name: /Fatture individuate\s*\(0\)/i });
  await waitUntil(tab, async () => (await details.count()) > 0 || (await empty.count()) > 0, "invoice-results-not-ready", timeoutMs);
  return (await details.count()) === 0 ? "empty" : "results";
}

async function nextDisabled(locator) {
  return locator.evaluate((element) => {
    const classes = String(element.parentElement?.className ?? "").split(/\s+/).filter(Boolean);
    return classes.includes("disabled") || element.getAttribute("aria-disabled") === "true";
  });
}

function documentReady(document, plan) {
  return (plan.formats.original !== "available" || document.original) &&
    (plan.formats.pdf !== "native_gap" || document.pdf);
}

async function processPlan({
  tab,
  plan,
  state,
  context,
  downloadDirectory,
  nativePdfDirectory,
  archiveRoot,
  timeoutMs,
  maxPages,
  maxInvoices,
  onNativePdf,
  onProgress
}) {
  const request = state.requests[plan.key];
  await openSearch(tab, plan, timeoutMs);
  const currentResult = await resultState(tab, timeoutMs);
  if (currentResult === "empty") {
    request.pages_visited = 1;
    request.observed_count = 0;
    if (plan.expectedCount !== 0) throw new AgenziaAcquisitionError("invoice-population-incomplete");
    request.status = "completed";
    await persistRevision(context, state);
    return;
  }

  const existing = new Map(
    state.documents.filter((item) => item.request_key === plan.key).map((item) => [item.detail_sha256, item])
  );
  const seen = new Set();
  let page = 0;
  let paginationComplete = false;

  while (page < maxPages) {
    page += 1;
    request.pages_visited = page;
    await assertAllowedOrigin(tab);
    const links = detailLinks(tab);
    const count = await links.count();
    if (count < 1) throw new AgenziaAcquisitionError("invoice-list-empty-unexpectedly");
    const firstHref = await links.nth(0).getAttribute("href");

    for (let row = 0; row < count; row += 1) {
      if (seen.size >= maxInvoices) throw new AgenziaAcquisitionError("invoice-limit-exceeded");
      await assertAllowedOrigin(tab);
      await detailLinks(tab).nth(row).click({ timeoutMs });
      await waitUntil(tab, () => detailReady(tab, plan), "invoice-detail-not-ready", timeoutMs);

      const detailKey = sha256(await tab.url());
      if (seen.has(detailKey)) throw new AgenziaAcquisitionError("invoice-identity-not-unique");
      seen.add(detailKey);
      let document = existing.get(detailKey);
      if (!document) {
        document = {
          request_key: plan.key,
          category: plan.category,
          year: plan.year,
          detail_sha256: detailKey,
          first_seen: { page, row: row + 1 },
          original: null,
          pdf: null,
          format_status: {
            original: plan.formats.original === "unavailable" ? "unavailable" : "pending",
            pdf: plan.formats.pdf === "unavailable" ? "unavailable" : "pending"
          }
        };
        state.documents.push(document);
        existing.set(detailKey, document);
        await persistRevision(context, state);
      }

      if (plan.formats.original === "available" && !document.original) {
        document.original = await acquireOriginal({
          tab,
          plan,
          documentKey: detailKey,
          downloadDirectory,
          archiveRoot,
          timeoutMs
        });
        document.format_status.original = "verified";
        await persistRevision(context, state);
      }
      if (plan.formats.pdf === "native_gap" && !document.pdf) {
        if (!state.native_gaps.includes("operator-save-as-pdf")) {
          state.native_gaps.push("operator-save-as-pdf");
        }
        document.pdf = await acquireNativePdf({
          tab,
          plan,
          documentKey: detailKey,
          page,
          row: row + 1,
          nativePdfDirectory,
          archiveRoot,
          timeoutMs,
          onNativePdf
        });
        document.format_status.pdf = "verified_native_gap";
        await persistRevision(context, state);
      }

      onProgress({ event: "invoice-processed", category: plan.category, year: plan.year, completed: seen.size });
      await assertAllowedOrigin(tab);
      const back = await uniqueRoleChoice(
        tab,
        ["link", "button"],
        "Torna alla pagina precedente",
        "back-to-list-control-not-unique"
      );
      await back.click({ timeoutMs });
      await waitUntil(tab, async () => (await detailLinks(tab).count()) > 0, "invoice-list-not-restored", timeoutMs);
    }

    const next = tab.playwright.getByRole("link", { name: partialName("Pagina successiva") });
    const nextCount = await next.count();
    if (nextCount === 0 || (nextCount === 1 && (await nextDisabled(next)))) {
      paginationComplete = true;
      break;
    }
    if (nextCount !== 1) throw new AgenziaAcquisitionError("next-page-control-not-unique");
    await next.click({ timeoutMs });
    await waitUntil(tab, async () => {
      const current = detailLinks(tab);
      return (await current.count()) > 0 && (await current.nth(0).getAttribute("href")) !== firstHref;
    }, "next-page-not-loaded", timeoutMs);
  }

  if (!paginationComplete) throw new AgenziaAcquisitionError("page-limit-exceeded");
  request.observed_count = seen.size;
  if (seen.size !== plan.expectedCount) throw new AgenziaAcquisitionError("invoice-population-incomplete");
  const documents = state.documents.filter((item) => item.request_key === plan.key && seen.has(item.detail_sha256));
  if (documents.length !== plan.expectedCount || documents.some((item) => !documentReady(item, plan))) {
    throw new AgenziaAcquisitionError("invoice-artifacts-incomplete");
  }
  request.status = "completed";
  await persistRevision(context, state);
}

function failureCode(error) {
  return browserFailureCode(error) ??
    (error instanceof DownloadDirectoryError ? error.evidenceCode : null) ??
    (error instanceof AgenziaArtifactError ? error.code : null) ??
    (error instanceof AgenziaAcquisitionError ? error.code : "invoice-acquisition-failed");
}

function summaries(state) {
  return Object.values(state.requests).map((request) => {
    const documents = state.documents.filter((item) => item.request_key === request.key);
    return {
      category: request.category,
      year: request.year,
      status: request.status,
      expected_count: request.expected_count,
      observed_count: request.observed_count,
      completed_count: documents.filter((item) => item.format_status.original !== "pending" && item.format_status.pdf !== "pending").length,
      missing_count: Math.max(0, request.expected_count - documents.filter((item) => item.format_status.original !== "pending" && item.format_status.pdf !== "pending").length),
      pages_visited: request.pages_visited,
      formats: request.formats
    };
  });
}

/** Acquire exact category/year plans, retaining verified artifacts across a bounded resume. */
export async function acquireAgenziaInvoices({
  tab,
  categoryPlan,
  downloadDirectory,
  nativePdfDirectory = downloadDirectory,
  runDirectory,
  resume = false,
  timeoutMs = 30_000,
  maxPages = 100,
  maxInvoices = 10_000,
  executionMode = "unverified",
  onNativePdf = null,
  onProgress = () => {}
}) {
  if (!downloadDirectory || !runDirectory) throw new AgenziaAcquisitionError("local-directories-required");
  if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 1000) {
    throw new AgenziaAcquisitionError("invalid-page-limit");
  }
  if (!Number.isInteger(maxInvoices) || maxInvoices < 1 || maxInvoices > 100_000) {
    throw new AgenziaAcquisitionError("invalid-invoice-limit");
  }
  if (!EXECUTION_MODES.has(executionMode)) throw new AgenziaAcquisitionError("invalid-execution-mode");
  const plans = normalizePlan(categoryPlan);
  if (plans.reduce((total, plan) => total + plan.expectedCount, 0) > maxInvoices) {
    throw new AgenziaAcquisitionError("invoice-limit-exceeded");
  }
  const planHash = sha256(Buffer.from(JSON.stringify(canonical(plans)), "utf8"));
  const privateRunDirectory = resolve(runDirectory);
  let state;
  let context;

  if (resume) {
    ({ state, context } = await loadState(privateRunDirectory));
    if (state.plan_sha256 !== planHash || state.execution_mode !== executionMode) {
      throw new AgenziaAcquisitionError("resume-input-mismatch");
    }
    await verifyRetainedArtifacts(state, join(privateRunDirectory, "archive"));
    state.attempt += 1;
    state.status = "running";
    state.error = null;
  } else {
    await mkdir(dirname(privateRunDirectory), { recursive: true, mode: 0o700 });
    await mkdir(privateRunDirectory, { mode: 0o700 });
    await chmod(privateRunDirectory, 0o700);
    state = {
      schema_version: "agenzia-invoice-acquisition-output/v1",
      execution_mode: executionMode,
      validation_status: "prototype",
      browser_validation_eligible: true,
      status: "running",
      attempt: 1,
      revision: -1,
      previous_revision_sha256: null,
      plan_sha256: planHash,
      requests: Object.fromEntries(plans.map((plan) => [plan.key, {
        key: plan.key,
        category: plan.category,
        year: plan.year,
        expected_count: plan.expectedCount,
        observed_count: 0,
        pages_visited: 0,
        formats: plan.formats,
        status: "pending"
      }])),
      documents: [],
      native_gaps: [],
      error: null
    };
    context = { runDirectory: privateRunDirectory, nextRevision: 0, previousHash: null };
  }

  await persistRevision(context, state);
  try {
    if (!tab?.playwright || typeof tab.url !== "function") {
      throw new AgenziaAcquisitionError("connected-tab-required");
    }
    const archiveRoot = join(privateRunDirectory, "archive");
    for (const plan of plans) {
      await processPlan({
        tab,
        plan,
        state,
        context,
        downloadDirectory: resolve(downloadDirectory),
        nativePdfDirectory: resolve(nativePdfDirectory),
        archiveRoot,
        timeoutMs,
        maxPages,
        maxInvoices,
        onNativePdf,
        onProgress
      });
    }
    state.status = "completed";
  } catch (error) {
    state.status = "failed";
    state.error = {
      code: failureCode(error),
      detail_sha256: sha256(Buffer.from(error instanceof Error ? error.message : String(error), "utf8"))
    };
  }
  state.browser_validation_eligible = state.native_gaps.length === 0;
  await persistRevision(context, state);
  const reportPath = join(privateRunDirectory, `attempt-${String(state.attempt).padStart(6, "0")}.outputs.json`);
  await writeFile(reportPath, `${JSON.stringify(state, null, 2)}\n`, { flag: "wx", mode: 0o600 });
  const requestSummaries = summaries(state);
  return {
    status: state.status,
    execution_mode: executionMode,
    validation_status: "prototype",
    browser_validation_eligible: state.browser_validation_eligible,
    error: state.error,
    report_path: reportPath,
    request_summaries: requestSummaries,
    total_documents: state.documents.length,
    missing_documents: requestSummaries.reduce((total, item) => total + item.missing_count, 0),
    native_gaps: [...state.native_gaps]
  };
}

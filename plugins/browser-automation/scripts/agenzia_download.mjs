/** Agenzia prototype from the reviewed CR-43 handoff; live site validation is separate. */
import { createHash } from "node:crypto";
import { chmod, mkdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

import { DownloadDirectoryError, observeDownloadDirectory } from "./download_directory.mjs";
import { browserFailureCode } from "./browser_session.mjs";

const ALLOWED_ORIGIN = "https://ivaservizi.agenziaentrate.gov.it";
const DIRECTIONS = Object.freeze({
  active: "Le tue fatture emesse",
  passive: "Le tue fatture ricevute"
});

export class AgenziaAutomationError extends Error {
  constructor(code, cause) {
    super(code, cause ? { cause } : undefined);
    this.name = "AgenziaAutomationError";
    this.code = code;
  }
}

const sha256 = (value) => createHash("sha256").update(String(value)).digest("hex");

export function normalizeDirections(direction) {
  if (direction === "both") return ["active", "passive"];
  if (direction === "active" || direction === "passive") return [direction];
  throw new AgenziaAutomationError("invalid-direction");
}

export function formatItalianDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new AgenziaAutomationError("invalid-date-format");
  }
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new AgenziaAutomationError("invalid-date-value");
  }
  return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
}

export function hasDisabledClass(value) {
  return String(value ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .includes("disabled");
}

function assertDateRange(dateFrom, dateTo) {
  const from = formatItalianDate(dateFrom);
  const to = formatItalianDate(dateTo);
  if (dateFrom > dateTo) throw new AgenziaAutomationError("invalid-date-range");
  return { from, to };
}

async function assertAllowedOrigin(tab) {
  const current = new URL(await tab.url());
  if (current.origin !== ALLOWED_ORIGIN) {
    throw new AgenziaAutomationError("origin-outside-authorized-boundary");
  }
}

async function waitUntil(tab, predicate, code, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await tab.playwright.waitForTimeout(200);
  }
  throw new AgenziaAutomationError(code);
}

async function unique(locator, code) {
  const count = await locator.count();
  if (count !== 1) throw new AgenziaAutomationError(code);
  return locator;
}

async function persistRevision(runDirectory, sequence, state) {
  const filename = `run-state-${String(sequence).padStart(6, "0")}.json`;
  await writeFile(join(runDirectory, filename), `${JSON.stringify(state, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600
  });
}

async function downloadCurrentInvoice({ tab, downloadDirectory, timeoutMs }) {
  await assertAllowedOrigin(tab);
  const button = await unique(
    tab.playwright.getByRole("button", { name: "download file fattura" }),
    "download-control-not-unique"
  );

  if (typeof tab.playwright.waitForEvent !== "function") {
    throw new AgenziaAutomationError("download-event-api-unavailable");
  }

  const observation = await observeDownloadDirectory(downloadDirectory);
  try {
    const eventPromise = Promise.resolve(
      tab.playwright.waitForEvent("download", { timeoutMs })
    ).then(
      (download) => ({ download, error: null }),
      (error) => ({ download: null, error })
    );
    await button.click({ timeoutMs });
    const eventOutcome = await eventPromise;
    if (eventOutcome.error || !eventOutcome.download) {
      throw new AgenziaAutomationError("download-event-not-observed", eventOutcome.error);
    }
    // Retain verified bytes even if the tab disappears immediately afterward.
    return await observation.wait({ timeoutMs });
  } catch (error) {
    if (error instanceof AgenziaAutomationError) throw error;
    if (error?.evidenceCode?.startsWith?.("download-")) throw error;
    if (browserFailureCode(error)) throw error;
    throw new AgenziaAutomationError("download-not-verified", error);
  } finally {
    await observation.close();
  }
}

async function openSearch({ tab, direction, from, to, timeoutMs }) {
  await assertAllowedOrigin(tab);
  const home = await unique(
    tab.playwright.getByRole("link", { name: "Home consultazione" }),
    "home-link-not-unique"
  );
  await home.click({ timeoutMs });
  await assertAllowedOrigin(tab);

  const branch = await unique(
    tab.playwright.getByRole("link", { name: DIRECTIONS[direction] }),
    "invoice-direction-link-not-unique"
  );
  await branch.click({ timeoutMs });
  await assertAllowedOrigin(tab);

  const dateFrom = await unique(
    tab.playwright.getByRole("textbox", { name: "Dal:" }),
    "date-from-control-not-unique"
  );
  const dateTo = await unique(
    tab.playwright.getByRole("textbox", { name: "Al:" }),
    "date-to-control-not-unique"
  );
  await dateFrom.fill(from, { timeoutMs });
  await dateTo.fill(to, { timeoutMs });

  const search = await unique(
    tab.playwright.getByRole("button", { name: "Cerca" }),
    "search-control-not-unique"
  );
  await search.click({ timeoutMs });
  await assertAllowedOrigin(tab);
}

async function waitForResultState(tab, timeoutMs) {
  const details = tab.playwright.getByRole("link", { name: /^Dettaglio fattura / });
  const emptyHeading = tab.playwright.getByRole("heading", {
    name: /^Fatture individuate \(0\)/
  });
  await waitUntil(
    tab,
    async () => (await details.count()) > 0 || (await emptyHeading.count()) > 0,
    "invoice-results-not-ready",
    timeoutMs
  );
  return (await details.count()) === 0 ? "empty" : "results";
}

async function nextPageIsDisabled(nextPage) {
  return nextPage.evaluate((element) => {
    const classes = String(element.parentElement?.className ?? "")
      .split(/\s+/)
      .filter(Boolean);
    return classes.includes("disabled") || element.getAttribute("aria-disabled") === "true";
  });
}

async function processDirection({
  tab,
  direction,
  from,
  to,
  downloadDirectory,
  timeoutMs,
  maxPages,
  maxInvoices,
  runDirectory,
  state,
  onProgress
}) {
  await openSearch({ tab, direction, from, to, timeoutMs });
  const resultState = await waitForResultState(tab, timeoutMs);
  if (resultState === "empty") {
    state.pages_visited[direction] = 1;
    onProgress({ event: "direction-complete", direction, downloads: 0, pages: 1 });
    return;
  }

  const visitedDetails = new Set();
  let pageNumber = 0;
  let paginationComplete = false;

  while (pageNumber < maxPages) {
    pageNumber += 1;
    state.pages_visited[direction] = pageNumber;
    await assertAllowedOrigin(tab);
    const details = tab.playwright.getByRole("link", { name: /^Dettaglio fattura / });
    const count = await details.count();
    if (count < 1) throw new AgenziaAutomationError("invoice-list-empty-unexpectedly");

    const firstHref = await details.nth(0).getAttribute("href");
    for (let rowIndex = 0; rowIndex < count; rowIndex += 1) {
      if (state.downloads.length >= maxInvoices) {
        throw new AgenziaAutomationError("invoice-limit-exceeded");
      }

      await assertAllowedOrigin(tab);
      const currentLinks = tab.playwright.getByRole("link", { name: /^Dettaglio fattura / });
      await currentLinks.nth(rowIndex).click({ timeoutMs });
      await waitUntil(
        tab,
        async () =>
          (await tab.playwright.getByRole("button", { name: "download file fattura" }).count()) === 1,
        "invoice-detail-not-ready",
        timeoutMs
      );

      const detailUrl = await tab.url();
      const detailKey = sha256(detailUrl);
      // Repeated detail URLs cannot establish two distinct invoices. Stop
      // instead of silently skipping a row and later claiming a complete batch.
      if (visitedDetails.has(detailKey)) {
        throw new AgenziaAutomationError("invoice-identity-not-unique");
      }
      visitedDetails.add(detailKey);
      const evidence = await downloadCurrentInvoice({ tab, downloadDirectory, timeoutMs });
      state.downloads.push({
        direction,
        page: pageNumber,
        row: rowIndex + 1,
        detail_sha256: detailKey,
        ...evidence
      });
      state.direction_counts[direction] += 1;
      await persistRevision(runDirectory, state.downloads.length, state);
      onProgress({
        event: "invoice-downloaded",
        direction,
        completed: state.direction_counts[direction]
      });

      await assertAllowedOrigin(tab);
      const back = await unique(
        tab.playwright.getByRole("link", { name: "Torna alla pagina precedente" }),
        "back-to-list-control-not-unique"
      );
      await back.click({ timeoutMs });
      await waitUntil(
        tab,
        async () => (await tab.playwright.getByRole("link", { name: /^Dettaglio fattura / }).count()) > 0,
        "invoice-list-not-restored",
        timeoutMs
      );
    }

    state.pages_visited[direction] = pageNumber;
    const nextPage = tab.playwright.getByRole("link", { name: "Pagina successiva" });
    const nextCount = await nextPage.count();
    if (nextCount === 0 || (nextCount === 1 && (await nextPageIsDisabled(nextPage)))) {
      paginationComplete = true;
      break;
    }
    if (nextCount !== 1) throw new AgenziaAutomationError("next-page-control-not-unique");

    await assertAllowedOrigin(tab);
    await nextPage.click({ timeoutMs });
    await waitUntil(
      tab,
      async () => {
        const nextDetails = tab.playwright.getByRole("link", { name: /^Dettaglio fattura / });
        if ((await nextDetails.count()) < 1) return false;
        return (await nextDetails.nth(0).getAttribute("href")) !== firstHref;
      },
      "next-page-not-loaded",
      timeoutMs
    );
  }

  if (!paginationComplete) throw new AgenziaAutomationError("page-limit-exceeded");
  onProgress({
    event: "direction-complete",
    direction,
    downloads: state.direction_counts[direction],
    pages: state.pages_visited[direction]
  });
}

/**
 * Download all invoices in the requested direction(s) from an authenticated,
 * operator-selected Agenzia delle Entrate profile.
 */
export async function downloadAgenziaInvoices({
  tab,
  direction,
  dateFrom,
  dateTo,
  downloadDirectory,
  runDirectory,
  timeoutMs = 30_000,
  maxPages = 100,
  maxInvoices = 10_000,
  onProgress = () => {},
  expectedCounts = null,
  executionMode = "unverified"
}) {
  if (!downloadDirectory || !runDirectory) {
    throw new AgenziaAutomationError("local-directories-required");
  }
  if (!Number.isInteger(maxPages) || maxPages < 1 || maxPages > 1000) {
    throw new AgenziaAutomationError("invalid-page-limit");
  }
  if (!Number.isInteger(maxInvoices) || maxInvoices < 1 || maxInvoices > 100_000) {
    throw new AgenziaAutomationError("invalid-invoice-limit");
  }

  const directions = normalizeDirections(direction);
  const { from, to } = assertDateRange(dateFrom, dateTo);
  const privateRunDirectory = resolve(runDirectory);
  await mkdir(dirname(privateRunDirectory), { recursive: true, mode: 0o700 });
  await mkdir(privateRunDirectory, { mode: 0o700 });
  await chmod(privateRunDirectory, 0o700);

  const state = {
    schema_version: "agenzia-invoice-download-output/v2",
    execution_mode: executionMode,
    validation_status: "prototype",
    error: null,
    status: "running",
    input_hashes: {
      direction: sha256(direction),
      date_from: sha256(dateFrom),
      date_to: sha256(dateTo)
    },
    direction_counts: { active: 0, passive: 0 },
    expected_counts: Object.fromEntries(directions.map((value) => [value,
      Number.isInteger(expectedCounts?.[value]) && expectedCounts[value] >= 0 ? expectedCounts[value] : null])),
    pages_visited: { active: 0, passive: 0 },
    downloads: []
  };

  await persistRevision(privateRunDirectory, 0, state);
  try {
    if (!["unverified", "simulated", "live_connected_chrome"].includes(executionMode)) {
      throw new AgenziaAutomationError("invalid-execution-mode");
    }
    if (!tab?.playwright || typeof tab.url !== "function") {
      throw new AgenziaAutomationError("connected-tab-required");
    }
    if (directions.some((value) => !Number.isInteger(expectedCounts?.[value]) || expectedCounts[value] < 0)) {
      throw new AgenziaAutomationError("expected-invoice-counts-required");
    }
    for (const requestedDirection of directions) {
      await processDirection({
        tab,
        direction: requestedDirection,
        from,
        to,
        downloadDirectory: resolve(downloadDirectory),
        timeoutMs,
        maxPages,
        maxInvoices,
        runDirectory: privateRunDirectory,
        state,
        onProgress
      });
    }

    for (const value of directions) {
      if (state.direction_counts[value] !== expectedCounts[value]) {
        throw new AgenziaAutomationError("invoice-population-incomplete");
      }
    }
    state.status = "completed";
  } catch (error) {
    state.status = "failed";
    state.error = {
      code: browserFailureCode(error) ?? (error instanceof DownloadDirectoryError ? error.evidenceCode : null) ??
        (error instanceof AgenziaAutomationError ? error.code : "invoice-run-failed"),
      detail_sha256: sha256(error instanceof Error ? error.message : String(error))
    };
  }
  await writeFile(join(privateRunDirectory, "outputs.json"), `${JSON.stringify(state, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600
  });

  return {
    status: state.status,
    execution_mode: executionMode,
    validation_status: "prototype",
    error: state.error,
    report_path: join(privateRunDirectory, "outputs.json"),
    direction_counts: { ...state.direction_counts },
    pages_visited: { ...state.pages_visited },
    total_downloads: state.downloads.length
  };
}

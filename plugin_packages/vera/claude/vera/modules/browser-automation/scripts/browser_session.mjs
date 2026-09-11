/**
 * Diagnose the selected Chrome session without changing its profile or page.
 * Exact transport errors and API outcomes are mechanical evidence; they do not
 * establish why an extension failed or which fiscal profile the operator chose.
 */
import { createHash } from "node:crypto";
import { chmod, mkdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

export function browserFailureCode(error) {
  const message = error instanceof Error ? error.message : String(error);
  if (/^No tab with id: /u.test(message)) return "browser_tab_unavailable";
  if (/^Browser is not available: /u.test(message)) return "browser_binding_unavailable";
  return null;
}

/** Preserve an unfinished task tab for this turn's login or user-input handoff. */
export async function preserveBrowserHandoff({ tab }) {
  if (typeof tab?.markHandoff !== "function") {
    return { status: "browser_handoff_api_unavailable", detail_sha256: null };
  }
  try {
    await tab.markHandoff();
    return { status: "handoff_marked_for_current_turn", detail_sha256: null };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return {
      status: browserFailureCode(error) ?? "browser_handoff_failed",
      detail_sha256: createHash("sha256").update(detail).digest("hex"),
    };
  }
}

/** Reacquire only the same task tab; report other candidates without selecting them. */
export async function inspectBrowserSession({
  browser,
  tab = null,
  tabId = tab?.id,
  allowedOrigins,
  reportDirectory,
}) {
  if (!Array.isArray(allowedOrigins) || allowedOrigins.length === 0) {
    throw new Error("session inspection requires allowed origins");
  }
  const origins = new Set(allowedOrigins.map((value) => new URL(value).origin));
  const directory = resolve(reportDirectory);
  await mkdir(dirname(directory), { recursive: true, mode: 0o700 });
  await mkdir(directory, { mode: 0o700 });
  await chmod(directory, 0o700);
  const checks = [];
  let selectedTab = tab;
  let status = "browser_tab_unavailable";
  let matchingTabIds = [];

  const recordFailure = (operation, error) => {
    const detail = error instanceof Error ? error.message : String(error);
    const code = browserFailureCode(error) ?? "browser_probe_failed";
    checks.push({ operation, result: code, detail_sha256: createHash("sha256").update(detail).digest("hex") });
    return code;
  };
  const probe = async (candidate, operation) => {
    if (typeof candidate?.url !== "function") return "browser_tab_unavailable";
    try {
      const url = await candidate.url();
      if (!url) return "browser_tab_url_unavailable";
      if (!origins.has(new URL(url).origin)) return "browser_origin_not_allowed";
      if (!candidate.playwright) return "browser_playwright_unavailable";
      checks.push({ operation, result: "ready", detail_sha256: null });
      return "ready";
    } catch (error) {
      return recordFailure(operation, error);
    }
  };

  status = await probe(selectedTab, "existing_task_tab");
  // A stale tab object is not a disconnected browser. Obtain a new object for
  // exactly the same id before considering any other page or asking the user.
  if (status === "browser_tab_unavailable" && tabId != null &&
      typeof browser?.tabs?.get === "function") {
    try {
      selectedTab = await browser.tabs.get(String(tabId));
      status = await probe(selectedTab, "reacquire_same_tab");
    } catch (error) {
      status = recordFailure("reacquire_same_tab", error);
    }
  }
  if (status === "browser_tab_unavailable" || status === "browser_probe_failed") {
    if (typeof browser?.tabs?.list === "function") {
      try {
        const tabs = await browser.tabs.list();
        if (!Array.isArray(tabs)) throw new Error("invalid tab inventory");
        // Inspect inventory metadata locally, never page contents. Unrelated
        // URLs, titles and ids do not leave this projection or enter a report.
        matchingTabIds = tabs.filter((item) => {
          try { return origins.has(new URL(item.url).origin); } catch { return false; }
        }).map((item) => String(item.id));
        checks.push({ operation: "tab_inventory", result: tabs.length === 0 ? "empty" : "available", detail_sha256: null });
        status = tabs.length === 0 ? "browser_tab_inventory_empty" : "browser_task_tab_missing";
      } catch (error) {
        status = recordFailure("tab_inventory", error);
      }
    }
  }
  const report = {
    schema_version: "browser-session-report/v1",
    checked_at: new Date().toISOString(),
    status,
    same_tab_reacquired: status === "ready" && selectedTab !== tab,
    matching_task_tab_count: matchingTabIds.length,
    cause: status === "ready" ? null : "not_established",
    checks,
  };
  const reportPath = join(directory, "browser-session.json");
  await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  return { ...report, report_path: reportPath, tab: status === "ready" ? selectedTab : null,
    matching_tab_ids: matchingTabIds };
}

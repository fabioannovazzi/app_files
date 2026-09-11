import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { inspectBrowserSession, preserveBrowserHandoff } from "../plugins/browser-automation/scripts/browser_session.mjs";

const origin = "https://example.test";
const unavailable = () => { throw new Error("No tab with id: private-task-id"); };
async function options() {
  const root = await mkdtemp(join(tmpdir(), "browser-session-test-"));
  return { allowedOrigins: [origin], reportDirectory: join(root, "report") };
}

test("reacquires the same stale task tab without browsing other tabs", async () => {
  const fresh = { id: "task", playwright: {}, url: async () => origin + "/ready?private=value" };
  const result = await inspectBrowserSession({
    ...await options(), tab: { id: "task", url: unavailable },
    browser: { tabs: { get: async (id) => { assert.equal(id, "task"); return fresh; } } },
  });
  assert.equal(result.status, "ready");
  assert.equal(result.same_tab_reacquired, true);
  assert.equal(result.tab, fresh);
  assert.doesNotMatch(await readFile(result.report_path, "utf8"), /private-task-id|private=value/);
});

test("an empty inventory does not claim extension disconnection", async () => {
  const result = await inspectBrowserSession({ ...await options(),
    tab: { id: "task", url: unavailable },
    browser: { tabs: { get: unavailable, list: async () => [] } },
  });
  assert.equal(result.status, "browser_tab_inventory_empty");
  assert.equal(result.cause, "not_established");
});

test("explicit unavailable browser binding is distinguished from empty inventory", async () => {
  const result = await inspectBrowserSession({ ...await options(),
    tab: { url: async () => { throw new Error("Browser is not available: 3"); } },
  });
  assert.equal(result.status, "browser_binding_unavailable");
  assert.doesNotMatch(await readFile(result.report_path, "utf8"), /available: 3/);
});

test("reports only allowed-origin candidates and never selects another account tab", async () => {
  const result = await inspectBrowserSession({ ...await options(),
    browser: { tabs: { list: async () => [
      { id: "candidate", url: origin + "/private?session=secret" },
      { id: "unrelated", url: "https://unrelated.test/mail", title: "private message" },
    ] } },
  });
  assert.equal(result.status, "browser_task_tab_missing");
  assert.deepEqual(result.matching_tab_ids, ["candidate"]);
  assert.equal(result.tab, null);
  assert.doesNotMatch(await readFile(result.report_path, "utf8"), /secret|unrelated|private message|candidate/);
});

test("wrong origin does not trigger a new tab", async () => {
  const wrong = await inspectBrowserSession({ ...await options(), tab: { url: async () => "https://other.test" } });
  assert.equal(wrong.status, "browser_origin_not_allowed");
});

test("unavailable Playwright does not trigger a new tab", async () => {
  const noApi = await inspectBrowserSession({ ...await options(), tab: { url: async () => origin } });
  assert.equal(noApi.status, "browser_playwright_unavailable");
});

test("marks the actual task tab for a handoff in the current turn", async () => {
  let calls = 0;
  const result = await preserveBrowserHandoff({ tab: { markHandoff: async () => { calls += 1; } } });
  assert.equal(calls, 1);
  assert.equal(result.status, "handoff_marked_for_current_turn");
});

test("does not claim retention when the host lacks the handoff API", async () => {
  const result = await preserveBrowserHandoff({ tab: {} });
  assert.equal(result.status, "browser_handoff_api_unavailable");
});

test("sanitizes a failed handoff without claiming the tab was kept", async () => {
  const result = await preserveBrowserHandoff({ tab: { markHandoff: unavailable } });
  assert.equal(result.status, "browser_tab_unavailable");
  assert.match(result.detail_sha256, /^[a-f0-9]{64}$/u);
  assert.doesNotMatch(JSON.stringify(result), /private-task-id/);
});

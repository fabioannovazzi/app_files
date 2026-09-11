# Resume the authorized Chrome task

Keep the current browser/profile and the task tab reference across authentication
and turns. The host's current documentation governs browser selection and tab
lifecycle; do not cache a browser id as a permanent installation identifier.

Before yielding for login, user input or any unfinished workflow, preserve the
actual task tab using the current host's documented lifecycle API. On Chrome
hosts exposing `tab.markHandoff()`, use:

```js
const { preserveBrowserHandoff } = await import(moduleRoot + "/scripts/browser_session.mjs");
const handoff = await preserveBrowserHandoff({ tab });
```

Record the returned status in the teaching checkpoint before yielding. Only
`handoff_marked_for_current_turn` confirms the call succeeded. Marks apply to
one turn: repeat the call before each later handoff while work is unfinished.
Unmarked agent-created Chrome tabs close at turn end; unmarked claimed user
tabs are released from control but left open. An empty task inventory after
that cleanup is not an extension failure. If the installed host lacks the API
or marking fails, preserve the diagnostic and checkpoint and follow its current
documented handoff route; do not claim the live tab has been retained. Never
mark unrelated research tabs or completed intermediate pages to evade cleanup.

For an extension-backed `tab.playwright` session, call the shipped helper in the
same supported persistent Node session before resuming:

```js
const { inspectBrowserSession } = await import(moduleRoot + "/scripts/browser_session.mjs");
const session = await inspectBrowserSession({
  browser, tab, tabId: tab?.id, allowedOrigins,
  reportDirectory: freshPrivateSessionReportDirectory
});
// Do not emit the tab object or any unfiltered tab inventory.
```

Use a fresh report directory outside the repository. The helper probes only the
task tab URL and, on a missing tab, reacquires the same id once. If that fails it
reads inventory metadata locally and exposes only ids whose origins match the
authorized process. It writes `browser-session.json` even when a probe fails.
The report has categories, counts and error hashes; no URLs, titles, browser
ids, tab ids, credentials or page content. Returned candidate ids are ephemeral
handles, not proof of the selected fiscal account.

- `ready`: use `session.tab`. Verify the current authorized profile and process
  milestone from bounded page evidence before continuing business actions.
- `browser_tab_inventory_empty`: the browser answered with zero visible tabs.
  This is not extension-disconnection evidence. Keep the binding; follow the
  host's documented tab claiming/creation route for this task. A fresh task tab
  may use the ordinary public entry URL. Do not repeatedly open new tabs when
  one cannot survive a turn boundary. Preserve the report and stop that loop.
- `browser_task_tab_missing`: inspect only the returned authorized-origin
  candidates. Select using the actual task context; do not silently switch to
  another account because it shares an origin. Use host-supported claiming if
  the operator's authenticated tab is outside the visible task inventory.
- `browser_binding_unavailable`: the selected binding itself was reported
  unavailable. Refresh the available browser inventory once through the host's
  documented provider API, select the same authorized Chrome profile if it is
  unambiguous, read its effective documentation, and reacquire the task tab.
  Do not assume that a numeric browser id remains valid. If this fails, use the
  host's documented extension/native-host diagnostics and retain their sanitized
  results; never install native components or change security settings yourself.
- `browser_playwright_unavailable`: the tab can be reached but its controller
  is unavailable. Use documented alternatives for bounded diagnosis only. Stop
  the portable Playwright executor; do not invent API methods or describe it as
  validated through an unrelated controller.
- `browser_origin_not_allowed`, `browser_tab_url_unavailable`, or
  `browser_probe_failed`: preserve the exact category and error hash and let the
  current model investigate within the authorized boundary. Cause is unknown.

Only a diagnostic result showing the extension missing/disabled or an explicit
disconnection justifies that explanation to the operator. Follow the host's
supported repair if needed; do not make reconnection a repeated ritual.

The helper never logs in, creates or closes a tab, changes an account, reloads
a page or replays an action. After an interruption, reconcile the saved outputs
with the actual page. Do not blindly rerun a download or consequential action.
Save the interruption in the existing teaching checkpoint and link its report.
Previously learned work and a partial development export remain usable while
Chrome is unavailable; do not require a working connection merely to export them.

# Individual invoice downloads: CR-43 prototype

`scripts/agenzia_download.mjs` incorporates the inspected individual-invoice
prototype supplied with CR-43. It does not establish current Agenzia selectors,
Chrome availability on the reporter's Windows machine, or completed live replay.
Do not confuse it with the `agenzia-invoice-zip` batch-request scaffold.

Use the existing authorized Chrome profile and the current host's documented
`tab.playwright` API. Run the session inspection described in `browser-session.md`
after the operator completes authentication. Vera reads and verifies the
selected fiscal profile, date filters and total for each requested direction
within the already authorized data boundary. Do not ask the operator to write
selectors, configure the module or supply a new confirmation for ordinary reads.
Before yielding for authentication or an unfinished batch, preserve the task tab
as described there; repeat the handoff mark in every turn that needs it.

Before running, verify that the current controls match the supplied process:
Home consultazione, Le tue fatture emesse/ricevute, Dal:, Al:, Cerca, Dettaglio
fattura, download file fattura, Torna alla pagina precedente, Pagina successiva.
Resolve any mismatch from bounded observed controls, not guessed locators.

```js
const { downloadAgenziaInvoices } = await import(moduleRoot + "/scripts/agenzia_download.mjs");
const result = await downloadAgenziaInvoices({
  tab: session.tab, direction, dateFrom, dateTo,
  expectedCounts, // Counts Vera independently read for these exact filters.
  downloadDirectory: actualChromeDownloadsDirectory,
  runDirectory: freshPrivateRunDirectory,
  executionMode: "live_connected_chrome"
});
```

`expectedCounts` maps each requested direction (`active`, `passive`, or both)
to its non-negative observed invoice total. Missing counts stop before portal
actions. Simulated tests use `executionMode: "simulated"`; omitted mode is
`unverified`. Do not label a fake adapter as live. API assumptions must be checked
against the effective installed browser documentation, not ordinary Playwright.

Downloads run sequentially through the shared local folder observer and require
a download event plus one stable new file. Only private run artifacts contain
paths, byte lengths, file hashes and detail-URL hashes. Results expose counts,
status and sanitized error metadata. They do not expose invoice contents.

The runner saves its initial state, an exclusive revision after each verified
download, and a final `outputs.json` on success or handled failure. A lost tab
before the first download still leaves a report. Mid-batch failures retain
completed downloads. A repeated detail identity or a total differing from the
independently observed population fails; it cannot silently declare all invoices
downloaded. Run directories must be new and private, outside the repository.

On failure, reconcile retained file evidence and current state before a fresh
run; there is no blind automatic replay or cross-run deduplication. The report
cannot determine which account was selected or infer tax meaning. No login state
or credentials are saved or transferred.

Every result retains `validation_status: "prototype"`, even after a successful
live batch. Report exactly which direction, pages and downloads were exercised
by this module. Four simulated tests or earlier manual/model-guided downloads
do not establish live compatibility. Complete two clean supervised target-site
runs, including received invoices and multiple pages, before preparing a
validated process-specific handoff through the existing capability workflow.

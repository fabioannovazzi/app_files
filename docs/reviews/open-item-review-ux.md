# Open-item review implementation — 7 September 2026

Working preview: http://127.0.0.1:56000/review

Retained branch: `codex/open-item-review-ux` in
`/Users/fabio/.codex/worktrees/a740/app_files`.
Implementation base: `4856ae9f3a80c8a7ba84a6d8caee09a64aa3a736`, the completed Vera
audit/remediation release (PR #556). The subsequent authorized deployment
candidate is rebased onto `21da5609` (PR #558), retaining the Python 3.12 runtime
standardization and published-version announcement. Deployment evidence belongs
to PR #559; Marketplace publication remains separate.

## What changed

- The page starts with purpose, source-population count, cut-off, bounded review
  scope and recorded accounting results. Technical processing, review progress
  and final-output readiness have distinct descriptions.
- Accounting items, failed checks/source exceptions and document reviews use
  separate sections. Document existence is not presented as accounting evidence.
- Accounting detail precedes decisions: document, counterparty, source reference,
  original amount, supported settlement, residual, evidence reference and dates.
  Missing values remain explicitly unavailable. Failed allocation controls do
  not turn payment references or stale allocated amounts into supported settlement.
- Missing support is explained, including counterparty mismatch. Original
  evidence and technical fields remain available in a disclosure. Diagnostic
  provenance, artifact inventory and JSON recovery controls are secondary.
- Bulk recommended approval is removed. A reviewer chooses an action explicitly;
  note entry does not implicitly accept a recommendation or lose focus while typing.
- Save progress and Save and apply explain their different effects. Accepting an
  unresolved classification does not close its balance. Document requests are
  recorded, not sent. Proposed notes are distinguished from changes to numbers.
- The required independently retained predecessor checkpoint has an inline field.
  It no longer relies on `prompt()`, which the in-app browser does not support.
- Offline export explicitly says it has not saved decisions to the run.
- Regeneration restores display facts from an unambiguous same-run record-ID
  match. It preserves accounting item IDs from the predecessor mapping already
  replayed by `prepare_assurance_run`, allowing the original decision set to be
  recognized after regeneration. Authority records and accounting classifications
  are not changed by this display join.
- Italian, English, French, German and Spanish copy; local embedded Instrument
  Sans; white canvas and shared blue identity; responsive evidence/decision layout.

The shared generator still serves its other consumers. Custom composition is
selected only for `open-item-reconciliation`. Editable UI sources are
`scripts/open_item_review_widget.py` and `scripts/review_widgets/`; regenerate with
`python -m scripts.generate_non_plotting_review_widgets --plugin open-item-reconciliation`.
No retired UI was changed.

## Verified behavior

All case data is synthetic. Fixtures execute the normal normalized-record
workflow in Studio Archive client/engagement run directories. This is not a new
qualification of raw CSV/PDF parsing or a real client engagement.

| Case | Recorded result |
| --- | --- |
| INV-1 / Alfa | 1,000 EUR closed by matching bank evidence |
| INV-2 / Beta | 400 EUR allocated; 600 EUR residual |
| INV-3 / Gamma | Unresolved; settlement evidence not established |
| INV-4 / Delta | Payment reference exists; counterparty mismatch withholds settlement |

Browser acceptance saved and reopened a decision and note in a new tab, then
saved/applied four accounting decisions including a proposed note, a document
request and uncertainty. Missing checkpoint recovery and offline export were
exercised. Desktop and 390 × 844 mobile rendering were inspected; mobile content
width was 390 pixels with no horizontal overflow.

The final-source supported-case execution verified save/reopen, unchanged native
Word/Excel bytes immediately after apply, regeneration, retained accounting
display, predecessor replay and `final_ready`. The final-source mixed case
verified save/apply/regeneration/replay and remained blocked by its actual
accounting failures. Evidence:

- [Supported-case receipt](/private/tmp/open-item-review-ux/positive-delivery/verification.json)
- [Mixed-case receipt](/private/tmp/open-item-review-ux/mixed-delivery/verification.json)
- [Browser output-effects receipt](/private/tmp/open-item-review-ux/acceptance/output-effects.json)
- [Before desktop](/private/tmp/open-item-review-ux/before-desktop.png)
- [After desktop](/private/tmp/open-item-review-ux/after-desktop.png)
- [Before mobile](/private/tmp/open-item-review-ux/before-mobile.png)
- [After mobile](/private/tmp/open-item-review-ux/after-mobile.png)

Before/after desktop captures use the same synthetic population and recorded
payload, with the released widget for the baseline.

Validation: 78 focused UI, workflow, transaction, lifecycle and icon tests passed;
373 package-integrity tests passed. The seven UI/locale tests were rerun after
the final additional status translations and passed. Black, Isort, diff checks,
unsuppressed Mypy for the new generator composer and Bandit for that composer
passed. No repository-wide coverage or whole-application green claim is made.
Logs are retained in `/private/tmp/open-item-review-ux`.

## Packaging versus host qualification

Candidate versions: Open-item Reconciliation **0.1.53**, Vera **0.1.213**.
Vera 0.1.212 was observed in the installed cache during validation, so this
candidate uses a distinct higher version. This does not assert publication status.

Codex, ChatGPT upload and Cowork candidates were rebuilt and checked against
source. Cowork package validation initialized and listed tools for all 18 MCP
servers. The generated marketplace catalog and downloadable ZIP in this checkout
are candidate files only. No installed Codex/Cowork plugin was changed or used to
claim installed-host acceptance.

- `plugin_packages/vera/vera-plugin.zip`
- `plugin_packages/vera/vera-chatgpt-upload.zip`
- `plugin_packages/vera/vera-claude-plugin.zip`

Privacy source fingerprints were refreshed. The model-context routing and
external-data boundaries are unchanged; the local review page itself does not
add a model call or external connector.

## Remaining limits

1. The implementation-stage update-notification failure (manifest 0.1.205 versus
   installed 0.1.212) is resolved by upstream PR #558. All 468 focused workflow,
   UI, package, icon and update-notification cases pass after rebasing. The public
   announcement remains 0.1.212; building 0.1.213 does not announce it as Published.
2. On a successor with failed accounting controls, repeating Apply with the old
   predecessor checkpoint is rejected with
   `external expected predecessor checkpoint does not match`. The failed repeat
   leaves the tree unchanged; no readiness or control waiver is claimed. Correct
   the underlying evidence/control problem through a new controlled run.
3. A proposed note targeting an unavailable structured artifact is recorded as
   `revision_artifact_pending`; it is not automatically inserted into Word/Excel.
   The interface states that it remains to be incorporated during regeneration.
4. The initial synthetic run using tolerance `0.01` was rejected by an existing
   native-report guard:
   `relazione_riconciliazione_audit.docx contains a material figure outside a workflow-owned table address`.
   Acceptance used exact matching (`amount_tolerance: "0"`). That separate report
   guard was not weakened or modified.

## Resume the preview

The running server uses only `127.0.0.1:56000`. The exact run output directory is
in [preview/case.json](/private/tmp/open-item-review-ux/preview/case.json).
If the process is stopped, activate the primary checkout's `.venv` and run this
worktree's `plugins/open-item-reconciliation/scripts/review_server.py` with that
output directory, `--port 56000 --no-open`. Use `python -I -B`.
The separately retained synthetic checkpoint is in
[preview/checkpoint.txt](/private/tmp/open-item-review-ux/preview/checkpoint.txt).

Repository inventory at handoff: 5 local branches, 3 remote branches excluding
`origin/HEAD`, 5 registered worktrees (one unrelated registration is prunable),
0 stashes. Only this task's branch/worktree is retained by this task's request;
other tasks' resources were preserved. Temporary test servers were stopped.

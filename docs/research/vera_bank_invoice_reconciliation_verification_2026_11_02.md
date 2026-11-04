# Verification of the Vera reconciliation study

2 November 2026 · Source baseline `1b86d7735ca28f272edf763b67cfe95f1ecda4b3`

This record accompanies [the study](vera_bank_invoice_reconciliation_study_2026_11_02.md). It records research checks, not acceptance of a customer reconciliation or a released package.

## Source and scope checks

- Inspected the actual open-item classification, candidate generation, partial settlement, allocation control, semantic resolution, workpaper and review producers; inspected bank matching stages, relationship ledger, semantic bounds and review targets.
- Inspected the maintained Archive import-to-delivery operation, reviewed tabular contract, Vera wrappers, native review code and model-context documentation.
- Checked 29 commit-pinned source links against existing local files and valid line numbers; no missing file or out-of-bounds anchor was found. This checks reference structure, not remote GitHub access or every semantic claim automatically.
- Read the historical Test 1 summary only to bound acceptance claims. The original `outputs/vera-ui-acceptance-20261101/test01` directory was absent. Current source was used for present behavior; historical host results remain historical.
- No client sources were imported, no real reconciliation was started, no installed plugin was changed and no bookkeeping records were updated. Tests use isolated synthetic fixtures and controlled workers where provided by the existing harness.

## Executed regressions

All Python commands used the existing repository virtual environment, activated with `source .venv/bin/activate`.

### Allocation and operation behavior

```bash
pytest -q \
  tests/open_item_reconciliation/test_reconciliation_helpers.py \
  tests/open_item_reconciliation/test_semantic_resolution.py \
  tests/plugins/test_reconciliation_operation.py \
  tests/plugins/test_journal_bank_reconciliation_plugin.py \
  -k 'partial or party or grouped or allocation or ambiguous_rows or reference_group or competing_singletons or declared or semantic_packet or operation'
```

Observed result: exit code 0; all 72 selected tests passed. The selection count was independently obtained using the same arguments with `--collect-only -o addopts=''`: 72 of 644 collected, 572 deselected. Output included PyMuPDF/Swig deprecation warnings. No source changes were made to make tests pass.

The tests include partial residual preservation, wrong-party rejection, reused evidence, grouped relationships, overlapping groups, competing singleton order independence, declared-list drafts, repeat-request resumption and retained failed runs. They demonstrate the selected behavior on fixtures; they do not estimate production error rates.

### Native review adapter

```bash
pytest -q tests/plugins/test_vera_native_workspace.py \
  -k 'open_items or bank_' \
  --junitxml=/private/tmp/vera-reconciliation-study-ui-tests.xml
```

Observed result: 6 tests, 0 failures, 0 errors, 0 skipped; exit code 0. JUnit duration: 22.828 seconds. These are mechanism tests of current adapters, selected-case context, assured review and review-note edits. They do not establish visual or native Codex host acceptance.

### Exact automatic review and semantic edge cases

```bash
pytest -q \
  tests/open_item_reconciliation/test_simple_reconciliation.py \
  tests/open_item_reconciliation/test_semantic_resolution.py \
  -k 'literal_invoice or incompatible_or_inexact or duplicate_identity or case_thirteen or uncertainty_never or correct_semantics_reach or incompatible_or_oversized' \
  --junitxml=/private/tmp/vera-reconciliation-study-semantic-tests.xml
```

Observed result: 33 tests, 0 failures, 0 errors, 0 skipped; exit code 0. JUnit duration: 7.358 seconds. These verify automatic review of exact supported matches, refusal of duplicate/ambiguous authority, preserved source names/dates in the shortened-payer fixture, nonclosing uncertainty, native workpaper propagation and oversized-packet abstention. Controlled semantic responses do not prove live model accuracy.

The first three commands therefore passed 111 selected test executions. The selections overlap in some behavior; this is not a count of 111 independent production scenarios.

### Actual browser rendering and saved-work navigation

```bash
VERA_REVIEW_SCREENSHOTS=/private/tmp/vera-reconciliation-study-screens \
pytest -q \
  'tests/plugins/test_vera_review_browser.py::test_chat_and_archive_show_same_saved_bank_editor_in_browser[several]' \
  'tests/plugins/test_vera_review_browser.py::test_chat_and_archive_show_same_saved_bank_editor_in_browser[one]' \
  --junitxml=/private/tmp/vera-reconciliation-study-browser-tests.xml
```

Initial result: 2 failures before page creation. Chromium terminated with `bootstrap_check_in ... MachPortRendezvousServer ... Permission denied (1100)` in the sandbox. Effect: no visual acceptance could be established from that attempt. This was an environment launch failure, not an assertion that the review UI behaved incorrectly.

Recovery: reran the exact two tests outside the sandbox through the reviewed escalation, using `vera-reconciliation-study-browser-retry-tests.xml` for the new result. No code, browser security settings or product checks were changed. Both tests passed. The real packaged MCP resource was served by the actual workspace server with an isolated test-host message transport and synthetic inputs. This is still distinct from the installed Codex host.

I opened and visually inspected both generated screenshots. The several-case screen shows the saved `Da chiarire` decision and note after Archive reopening. The single-case screen shows the matched movement and decision selector without unrelated queue controls. Source evidence is collapsed initially. English source/title text in this synthetic fixture is not sufficient to diagnose production localization. The tests exercise a 560 by 900 viewport; they do not establish usability at every size or the ability to edit allocation relationships.

Total successful test executions: **113**. Separately retained: **2 initial browser-launch failures, recovered**. No product defect was established by those launch failures.

Artifacts are retained under [the study evidence folder](../../outputs/vera-reconciliation-study-20261102/provenance.json):

- [Several-case review screenshot](../../outputs/vera-reconciliation-study-20261102/bank-several.png).
- [Single-case review screenshot](../../outputs/vera-reconciliation-study-20261102/bank-one.png).
- [Native-adapter JUnit](../../outputs/vera-reconciliation-study-20261102/vera-reconciliation-study-ui-tests.xml).
- [Semantic-edge-case JUnit](../../outputs/vera-reconciliation-study-20261102/vera-reconciliation-study-semantic-tests.xml).
- [Initial browser-launch failures](../../outputs/vera-reconciliation-study-20261102/vera-reconciliation-study-browser-tests.xml).
- [Successful browser retry](../../outputs/vera-reconciliation-study-20261102/vera-reconciliation-study-browser-retry-tests.xml).

The manifest records source commit, synthetic-data status, resource/test origin, viewport and SHA-256 hashes. Generated evidence remains outside tracked documentation; no commit or publication is authorized.

## External research limitations

- The supplied TeamSystem Contabilità in Cloud commercialista landing page returned only an iframe. Integration claims instead use the readable official Reviso help and API reference, and the exact product distinction is preserved.
- The DATEV DK Konto page timed out on direct fetch. Its official indexed text supports only the limited acquisition/automation description used. The Italian developer portal and documentation categories were directly readable; they do not establish a DK Set settlement-write API.
- The supplied Xero Central article had no readable body; the attempted Find & Match article was inaccessible. The study instead uses Xero's readable official developer guide on aggregate processor receipts and clearing accounts, explicitly as an architectural example.
- Direct opens of the 2022 MEF ISA 500 and 505 PDFs returned HTTP 503. Official indexed text and the current MEF standards index were available. The study uses general evidence principles and does not claim full legal verification of every applicable standard.
- No vendor account was accessed, licence purchased, API credential requested, tenant configured or write operation attempted. A published API model or import specification establishes a documented surface, not operational access or support in every edition.

## Acceptance and privacy outcomes

Pipeline mechanism checks: passed as detailed above. Real reconciliation acceptance: not performed. Installed-host acceptance: not established. Professional acceptance and comparative savings: not established.

Privacy-report acceptance: not performed for a real run. The source supports separate accounting/readiness and reporting outcomes. Synthetic fixture reports and a source inventory do not establish completeness of a live run's measured transmissions or provider isolation. Historical measurement gaps remain historical evidence, not a newly verified pass or failure.

Full `make check`, full-suite coverage and release checks were not run: this task adds research documents only and changes no executable behavior. Focused regressions were run to substantiate behavioral claims in the assessment.

## Repository preservation

Initial checkout was clean on `main`; this study created no task branch, worktree or stash. Final checked inventory: **2 local branches, 1 remote branch (`origin/main`; `origin/HEAD` is symbolic), 2 registered worktrees, 0 stashes**. Another branch/worktree appeared during the assessment; it was preserved as unrelated work rather than deleted. The primary checkout's source HEAD remained unchanged. All documentation-relative links and retained artifact hashes passed validation. Research files are intentionally delivered in the primary checkout without a commit, merge, deployment or publication.

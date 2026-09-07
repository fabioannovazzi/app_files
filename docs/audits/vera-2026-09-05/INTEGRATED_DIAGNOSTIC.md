# Integrated diagnostic baseline — 2026-09-06

The process in session 48596 terminated with exit code 1. Result: **9,532 passed,
103 failed, 19 errors, 34 skipped**, in 10,377.04 seconds. Coverage is **79.50%**,
below the required 80%; the rounded table display of 80% is not a passing gate.

This run began before subsequent source, test, privacy and package changes.
It is a diagnostic baseline, not qualification of one unchanged final tree.
Raw log and JUnit: `/private/tmp/vera-remediation-01a07083/integrated-current.log`
and `integrated-current.xml`. Extracted full failure traces: `integrated-failures.json`
in that directory. Do not restart this completed process.

## Initial classification

- Vera security-sensitive investigation: 22 Open Item MCP expansion rejection failures
  include missing expected rejections and a timeout. These require current-source
  reproduction; do not weaken the rejection assertions.
- Accounting: Check Entries credit-note difference assertion and Journal–Bank Italian
  missing-support wording assertion need current-source reconciliation.
- Contract inventories and packages: archive-organization inventory additions, lifecycle
  bootstrap entries, privacy fingerprints and package differences require comparison
  with post-launch focused evidence; baseline failures alone do not establish current drift.
- Environment: browser fixture reports loopback binding Operation not permitted.
  Existing separately authorized fixture execution is relevant evidence, not a reason
  to mark this integrated run green.
- Clara: monthly reporting setup reports generated logs, locks and generation files as
  output-set drift (19 errors and 2 failures); case_store import and release/package
  failures are separately recorded. Preserve unrelated work.
- Legacy UI, PDP, retailer discovery, OCR, website copy and styling failures are present.
  Their occurrence is observed; pre-existence and ownership must not be inferred solely
  from their paths. Do not alter production code merely to satisfy stale test expectations.

The user subsequently confirmed Astra Medium and requested resumption. The
model handoff is complete; do not ask again. Current replay evidence appears below.

## Complete failure/error inventory

| Count | Outcome | Test module |
| ---: | --- | --- |
| 4 | failure | `tests.modules.layout.test_modules_layout_filter_widgets` |
| 1 | failure | `tests.modules.layout.test_modules_layout_theme` |
| 4 | failure | `tests.modules.layout.test_modules_layout_widgets` |
| 1 | failure | `tests.modules.pdp.test_app_lifecycle` |
| 6 | failure | `tests.modules.pdp.test_homepage_compliance_section` |
| 15 | failure | `tests.modules.pdp.test_prejoin_sales` |
| 1 | failure | `tests.modules.validation.test_modules_validation_layers` |
| 1 | failure | `tests.plugins.test_business_planning_shared` |
| 1 | failure | `tests.plugins.test_check_entries_plugin` |
| 1 | failure | `tests.plugins.test_clara_advisory_deliverable_validator` |
| 3 | failure | `tests.plugins.test_clara_claude_package` |
| 1 | failure | `tests.plugins.test_clara_html_deck` |
| 19 | error | `tests.plugins.test_clara_monthly_pnl_reporting_handoff` |
| 2 | failure | `tests.plugins.test_clara_monthly_pnl_reporting_handoff` |
| 2 | failure | `tests.plugins.test_clara_plugin` |
| 1 | failure | `tests.plugins.test_clara_privacy_surfaces` |
| 1 | failure | `tests.plugins.test_claude_plugin_packages` |
| 3 | failure | `tests.plugins.test_codex_plugin_packages` |
| 1 | failure | `tests.plugins.test_journal_bank_reconciliation_plugin` |
| 4 | failure | `tests.plugins.test_lucia_plugin` |
| 22 | failure | `tests.plugins.test_open_item_reconciliation_plugin` |
| 1 | failure | `tests.plugins.test_plugin_update_notifications` |
| 1 | failure | `tests.plugins.test_vera_client_workflow_filesystem` |
| 1 | failure | `tests.plugins.test_vera_privacy_surfaces` |
| 1 | failure | `tests.scripts.test_audit_non_plotting_review_workbench_demos` |
| 4 | failure | `tests.scripts.test_audit_openai_pattern_adoption_readiness` |
| 1 | failure | `tests.scripts.test_audit_plugin_interaction_patterns` |
| 1 | failure | `tests.scripts.test_audit_review_payload_contract_coverage` |
| 1 | failure | `tests.scripts.test_build_openai_pattern_adoption_evidence` |
| 1 | failure | `tests.scripts.test_build_png_examples_gallery` |
| 1 | failure | `tests.scripts.test_build_retailer_category_evidence_pack` |
| 1 | failure | `tests.scripts.test_build_spanish_video_editions` |
| 1 | failure | `tests.scripts.test_serve_review_workbench` |
| 1 | failure | `tests.security.test_publication_security` |
| 1 | failure | `tests.src.slides.test_ocr_payload` |
| 1 | failure | `tests.test_browser_automation_acceptance_fixture` |
| 3 | failure | `tests.test_browser_automation_capabilities` |
| 1 | failure | `tests.test_final_pass_filter_utils` |
| 5 | failure | `tests.test_saloncentric_discovery` |
| 1 | failure | `tests.test_website_typography` |

## Open Item current-source diagnosis

Both initialize cases reproduce in `open-item-diagnostic-current.xml` (2 failures).
The test adds `mcp/__pycache__/rogue.pyc`; the current MCP tree scanner explicitly
ignores cache directories and .pyc/.pyo files while retaining the executable source
contract. Thus these failures establish a cache-policy/test mismatch, not by
themselves proof that unapproved executable source is accepted. The prior
implementation record also documents source-only startup and malicious-bytecode
non-execution tests. Current malicious-bytecode and real source-expansion checks
must be verified before changing these assertions. The timeout in the full run
is separate from the reproducible missing-rejection assertion.

Current execution confirms both timestamp-valid malicious-bytecode cases pass
(2 passed, no skips; `open-item-bytecode-diagnostic.xml`). Neither injected marker
executed; source and cache bytes remained unchanged. An independent copied-tree
probe added `mcp/unauthorized.cjs`: all 11 public surfaces rejected the expanded
source tree before returning any response (`open-item-source-expansion-diagnostic.json`).
This supports updating the cache-only rejection fixtures to test real executable
source expansion while preserving separate cache non-execution coverage. Post-start
real-source expansion still needs the corresponding regression during remediation.
No production code or existing assertions were modified for this diagnosis.

## Accounting reproduction and remediation handoff

Both accounting cases reproduce in `accounting-diagnostic-current.xml`.
Journal–Bank explicitly runs with Italian language and document language, but its
missing-support assertions still expect English. Correct the localized expectations
without reverting Italian output. Check Entries verifies signed amounts -10 and -11
and differences -1/1 successfully, then expects `amount_found is None`; current output
retains `11`. Resolve that field's intended reporting contract before changing the
assertion; the observed failure does not establish incorrect signed arithmetic.

The integrated diagnostic baseline and initial failure classification are now ready
for the requested Astra Medium handoff. This is not completion of T01–T20 or a claim
that every failing case has a proven root cause. Further reproduction and root-cause
work belongs in remediation alongside the fixes, using this inventory and the full
implementation status. Do not repeat the entire baseline before addressing known
failures. Preserve unrelated changes and do not deploy, merge or publish.

Next implementation priorities:
1. Reconcile cache-only rejection tests with real executable-source expansion checks,
   including post-start expansion, retaining malicious-bytecode non-execution coverage.
2. Reconcile accounting field semantics and locale assertions with intended outputs.
3. Reconcile contract inventory tests and current privacy/package evidence; distinguish
   post-launch fixes from remaining drift before rebuilding only affected packages.
4. Resolve remaining in-scope failures, audit coverage shortfall and retain unrelated
   findings for their owning work. Unclassified root causes remain open, not waived.
5. Complete outstanding T01–T20 qualification requirements in IMPLEMENTATION_STATUS.md
   and the original handoff, then run final gates on a stable source/package state.

User notification: switch this task to Astra with Medium reasoning before continuing
this implementation phase. No model-setting change has been made or verified here.

## Current replay after remediation — 2026-09-06

122 original failed/error cases replayed: **84 passed, 38 failed, no errors or skips**,
in 82.048 seconds. Two renamed tests were explicitly mapped; collection failure
from the first attempt remains retained. This replay does not measure whole-suite
coverage. Exact selection, JUnit and traces are in diagnostic-failure-replay-current
files and remaining-diagnostic-failures.json under the retained temporary directory.

Shared package follow-up: Vera and Lucia public Cowork ZIP bytes equal their local
release ZIPs; Clara bytes differ. The repository Claude catalog differs in Vera
and Clara version fields only. These are local generated-artifact findings, not
evidence that the remote site or Marketplace changed. The two render DNS failures
have separately passed with approved network access; loopback fixture failure
remains environment-specific. Legacy UI findings are retained without developing
the retired UI. Other failures require ownership and contract review.

| Test module | Remaining failures |
| --- | ---: |
| `tests.modules.layout.test_modules_layout_filter_widgets` | 4 |
| `tests.modules.layout.test_modules_layout_theme` | 1 |
| `tests.modules.layout.test_modules_layout_widgets` | 4 |
| `tests.modules.pdp.test_app_lifecycle` | 1 |
| `tests.modules.pdp.test_homepage_compliance_section` | 6 |
| `tests.plugins.test_clara_html_deck` | 1 |
| `tests.plugins.test_claude_plugin_packages` | 1 |
| `tests.plugins.test_codex_plugin_packages` | 2 |
| `tests.plugins.test_lucia_plugin` | 4 |
| `tests.plugins.test_plugin_update_notifications` | 1 |
| `tests.scripts.test_audit_plugin_interaction_patterns` | 1 |
| `tests.scripts.test_build_png_examples_gallery` | 1 |
| `tests.scripts.test_build_retailer_category_evidence_pack` | 1 |
| `tests.scripts.test_build_spanish_video_editions` | 1 |
| `tests.security.test_publication_security` | 1 |
| `tests.src.slides.test_ocr_payload` | 1 |
| `tests.test_browser_automation_acceptance_fixture` | 1 |
| `tests.test_saloncentric_discovery` | 5 |
| `tests.test_website_typography` | 1 |

### 2026-09-06 — Further reconciliation of Astra test expectations

Inspected current production behavior before applying test-only corrections. For
`tests/src/slides/test_ocr_payload.py`, `tests/scripts/test_build_png_examples_gallery.py`,
and `tests/test_saloncentric_discovery.py`, verified the complete local file matched
`e0b98921^` before taking the already released `e0b98921` test revision. OCR preserves
individual list items; gallery labels replace hyphens with spaces; SalonCentric rank
bands use 20% and 50% cumulative cutoffs and the permanent taxonomy now contains four
attribute families. Explicit alternate-family coverage remains in the revised test.

In `tests/scripts/test_build_spanish_video_editions.py`, removed only the assertion
that a repository-derived absolute path cannot contain `/Users/fabio/`. Retained
both repository-relative derivation and environment override assertions. No production
files changed in this batch; no legacy UI work performed.

Verification with repository venv and bundled Node PATH: three OCR/gallery/video
modules **66 passed, zero failures/errors/skips** (8.579 s); SalonCentric module
**12 passed, zero failures/errors/skips** (3.150 s). Evidence:
`/private/tmp/vera-remediation-01a07083/astra-three-test-reconciliation.xml` and
`astra-saloncentric-reconciliation.xml`, with corresponding logs. These close eight
failures from the prior 38-failure replay; they do not establish full-suite success
or improve the recorded 79.50% full-suite coverage by assertion. Goal remains active.

### 2026-09-06 — Remaining Astra expectation reconciliation and import finding

Applied the released `e0b98921` test-only revisions to homepage compliance,
website typography and retailer category evidence-pack tests after verifying
all three local files exactly matched `e0b98921^`. Inspected current five-language
homepage strings, both shared CSS selector groups and bundle-key component parsing.
The fixture now supplies its actual structured Terrace/Logo Detail key; production
classification was not changed. **120 tests passed, zero failures/errors/skips**
(16.096 s), recorded in `astra-final-expectation-reconciliation.xml` and its log
under `/private/tmp/vera-remediation-01a07083/`.

The Clara case-bound deck import is a distinct unresolved issue, not a stale
expectation: an isolated interpreter loading the builder with its script directory
on sys.path reproduces `ModuleNotFoundError: No module named 'case_store'` in
`advisory_evidence_lineage.py`. The documented builder command supplies `--case-dir`;
its lineage loader does not establish the sibling scripts dependency path.
Traceback: `clara-lineage-isolated-import.log`. No test monkeypatch or production
change was made. Repository instructions prohibit production edits to resolve test
import failures; this issue remains explicitly reported.

`diagnostic-reconciliation-ledger.json` matches individual test names/classes to
saved passing JUnit cases and hashes their receipts. Of the prior 38 failures,
21 have separate passing evidence and 17 remain unclosed. Some passing evidence
uses an authorized network/loopback environment; it is not evidence that restricted
environment runs pass. Remaining: nine legacy UI tests (excluded from development
by repository instruction), four Lucia tests, the Clara import, Clara public-version
lag, Clara public ZIP promotion mismatch, and the interaction audit for apertura-pratica
workflow metadata. This is not a fresh full-suite pass or 80% coverage proof.

### 2026-09-06 — Sales Plan CI gate and deliberate-regression qualification

The inspected dedicated plugin correctness workflow did not execute Sales Plan.
Added a separate Ubuntu/Python 3.12/Node 22 job running its complete test module
with declared requirements, bytecode disabled and an explicit 80% preparation-engine
coverage gate in `tests/plugin_sales_plan.coveragerc`. Corrected the MCP test to
compare the advertised version to the actual component manifest after the 0.1.7
bump, rather than its stale 0.1.6 literal. No production source was changed.

Exact CI test command passes locally: 29 tests, zero failures/errors/skips;
86.06% statement coverage of the 581-statement preparation engine (500 covered).
Initial CI-style attempt found the stale version assertion; it is retained in
`sales-ci-qualification.log`. Passing evidence is `sales-ci-final.xml/log`.
This is local command evidence, not a hosted Actions run or whole-repository coverage.

Three isolated temporary source copies qualify regression detection. The clean
copy passes all five selected missing-value/zero controls. Reintroducing the old
missing-discount-as-zero calculation fails two tests; allowing partial summary
totals fails four. All failures are assertions, with zero import/setup errors.
The production source SHA-256 was checked before/after and is unchanged. Evidence:
`/private/tmp/vera-remediation-01a07083/sales-regression-detection/result.json` and
variant-specific JUnit/logs; driver `qualify_sales_regression_detection.py`.
This supplies concrete T09 regression-detection evidence for the T16 correction.
Broader T01–T20 acceptance and the previously recorded external gaps remain open.

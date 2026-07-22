# OpenAI Plugin Pattern Adoption Audit

Date: 2026-06-07

This note audits the current repository state from the OpenAI plugin pattern
adoption effort. It separates verified behavior from generated package churn
and remaining product gaps.

## Intent

Adopt interaction patterns from OpenAI role-based plugins only where they fit
the Mparanza model:

- local files and deterministic scripts remain the execution baseline;
- Codex orchestrates, reviews, explains, and applies user decisions;
- review UIs capture decisions durably instead of showing static summaries;
- external uploads, remote SQL, or hosted notebooks require explicit approval.

## Current Change Shape

The UI work is centered on OpenAI-pattern interaction audits, shared
non-plotting review workbench QA, and package rebuilds.

Main groups:

- Shared non-plotting review workbench generator:
  `scripts/generate_non_plotting_review_widgets.py`.
- Generated non-plotting widget assets for Audit Reconciliation, Check Entries,
  New Client's client-file-preparation engine, Concordato Plan Review, Deep
  Research Validator, Journal-Bank Reconciliation, Journal Sampling, Prompt
  Optimizer, and Report Builder.
- Regression coverage:
  `tests/plugins/test_non_plotting_review_workbench.py`.
- Repo-level OpenAI-pattern interaction catalog and scorecard:
  `docs/openai_plugin_interaction_patterns.json`,
  `scripts/audit_plugin_interaction_patterns.py`, and
  `tests/scripts/test_audit_plugin_interaction_patterns.py`.
- Shared workbench demo-quality scorecard:
  `scripts/audit_non_plotting_review_workbench_demos.py` and
  `tests/scripts/test_audit_non_plotting_review_workbench_demos.py`.
- Shared workbench visual smoke audit:
  `scripts/audit_non_plotting_review_workbench_visuals.py` and
  `tests/scripts/test_audit_non_plotting_review_workbench_visuals.py`.
- Shared local-browser write-back server for generated workbenches:
  `scripts/serve_review_workbench.py`,
  `scripts/audit_local_review_workbench_writeback.py`, and
  `tests/scripts/test_serve_review_workbench.py`.
- Generated review-payload contract coverage audit:
  `scripts/audit_review_payload_contract_coverage.py` and
  `tests/scripts/test_audit_review_payload_contract_coverage.py`.
- Combined human-facing readiness scorecard:
  `scripts/audit_openai_pattern_adoption_readiness.py` and
  `tests/scripts/test_audit_openai_pattern_adoption_readiness.py`.
- Packaging:
  `plugin_packages/clara/clara-plugin.zip` and
  `plugin_packages/vera/vera-plugin.zip`.
  Some archive entries changed because generated workbench assets changed;
  others are content-identical deterministic refreshes kept so the current
  package builder's byte-for-byte `--check` passes.

## Verified

The following checks passed in the current worktree:

- `.venv/bin/python scripts/build_codex_plugin_zip.py --check`
- `.venv/bin/python -m pytest tests/plugins/test_non_plotting_review_workbench.py -q`
- `.venv/bin/python -m pytest tests/scripts/test_audit_plugin_interaction_patterns.py -q`
- `.venv/bin/python scripts/audit_plugin_interaction_patterns.py --format markdown --fail-on blocker`
- `.venv/bin/python -m pytest tests/scripts/test_audit_non_plotting_review_workbench_demos.py -q`
- `.venv/bin/python scripts/audit_non_plotting_review_workbench_demos.py --format markdown --fail-on medium`
- `.venv/bin/python -m pytest tests/scripts/test_audit_non_plotting_review_workbench_visuals.py -q`
- `.venv/bin/python scripts/audit_non_plotting_review_workbench_visuals.py --format markdown --fail-on high --languages en,it,fr,de,es --screenshots-dir /private/tmp/non_plotting_workbench_visuals_i18n`
- `.venv/bin/python scripts/audit_local_review_workbench_writeback.py --format markdown --fail-on high --screenshots-dir /private/tmp/local_review_writeback`
- `.venv/bin/python -m pytest tests/scripts/test_serve_review_workbench.py -q`
- `.venv/bin/python -m pytest tests/scripts/test_audit_review_payload_contract_coverage.py -q`
- `.venv/bin/python scripts/audit_review_payload_contract_coverage.py --format markdown --fail-on high`
- `.venv/bin/python -m pytest tests/scripts/test_audit_openai_pattern_adoption_readiness.py -q`
- `.venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py --format markdown --fail-on medium`
- `.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py -q`
- `git diff --check`

The ZIP check confirms current downloadable plugin archives match repo source.
The non-plotting workbench test confirms the shared HTML contract, localized
labels, decision controls, MCP save/apply hooks, artifact QA panels, mobile
ordering, and mobile wrapping controls are present across the generated
non-plotting widgets. It also runs each generated adapter demo payload through
the plugin's own MCP save/apply tools, proving that the UI demos are not just
renderable but accepted by the durable writer path. The full package test
passes in the current worktree.

The interaction-pattern audit reports 16 plugins audited, all with `ok` status.
It finds no blocker, high, or medium interaction issues. The only findings are
six informational `custom_stateful_review_surface` notes for chart plugins that
use custom review surfaces rather than the generated non-plotting workbench.
The same command now emits both a pattern coverage table and a pattern catalog.
The coverage table shows applicable, satisfied, and missing-applicable plugins
for each extracted OpenAI-derived interaction lesson; the catalog ties each
lesson to a local rule, adoption scope, and verifier path.
`scripts/build_codex_plugin_zip.py --check` now reuses this audit during plugin
source validation, so blocker/high/medium interaction-pattern drift fails the
normal package check.

The workbench demo audit reports 9 generated non-plotting adapters audited, all
with `ok` status. It verifies the embedded sample review payloads have at least
two review items, multiple item types and recommended actions, evidence rows,
explicit edit-target metadata, populated detail groups, and English, Italian,
French, German, and Spanish workflow labels. It also checks adapter demo item
types and actions
against each plugin MCP server's declared validator sets, so rendered demo rows
cannot use values the save/apply writer rejects. The audit now reports each
adapter's workflow mode and fails duplicate `detailMode` values or shallow
panel definitions, which keeps the shared HTML renderer from becoming one
undifferentiated page across all workflows. The package builder now reuses this
audit for plugins that ship `assets/review-workbench-adapter.json`, so shallow,
duplicated, or writer-incompatible generated demos cannot pass the normal ZIP
check.
The adapter-demo save/apply regression additionally catches mismatches where a
demo item type is visible in HTML but rejected by the workflow MCP validator.
The shared review-session validator now applies the same MCP item/action
compatibility check to real generated `review_payload.json` files when a plugin
declares static `ITEM_TYPES` and `ALLOWED_ACTIONS`, so workflow outputs cannot
silently drift away from their save/apply validators.
The review-payload contract coverage audit reports 9 generated non-plotting
workbench plugins audited, all with `ok` status. It now names both the
plugin-owned contract test file and the workflow-scenario test file that
validates generated review-session artifacts for each plugin, so unrelated
plugin name mentions do not inflate coverage.
`scripts/build_codex_plugin_zip.py --check` now reuses this audit for plugins
that ship `assets/review-workbench-adapter.json`, so a generated workbench
plugin cannot be packaged without generated-output contract validation coverage
from a workflow-like scenario.

The visual smoke audit reports 9 generated non-plotting workbenches audited, all
with `ok` status across English, Italian, French, German, and Spanish at both desktop and
mobile viewports. It opens each local HTML widget in headless Chrome, injects a
sample MCP-style review payload for each language, checks that queue rows,
detail decision controls, localized labels, final outputs, data posture,
execution provenance, and review safeguards render, checks for console/page
errors and horizontal overflow, and writes screenshots under
`/private/tmp/non_plotting_workbench_visuals_i18n`.
When the browser write-back report is included in
`scripts/build_openai_pattern_adoption_evidence.py`, the bundle now also writes
`browser_writeback_gallery.html` and copies available screenshots into the
bundle, so reviewers can scan the actual local review surfaces alongside the
machine-readable readiness JSON.

Visual QA was also run against generated review workbench demos using local
headless Chrome. Check Entries was reviewed first at desktop and narrow mobile
widths. Deep Research Validator, Report Builder, New Client's
client-file-preparation engine, Audit
Reconciliation, Journal Sampling, Journal-Bank Reconciliation, Prompt
Optimizer, and Concordato Plan Review were then reviewed with generated demo
payloads. The desktop views open into workflow-specific queues and detail
panels such as claim vs citation, section editor, document decision, row vs
evidence, sample rationale, journal vs bank, prompt revision, and plan vs
support.

The initial mobile capture exposed clipped action buttons and crowded
safeguard/provenance rows. A later multi-workflow mobile pass showed a larger
UX problem: data posture, execution provenance, and safeguards pushed the
actual queue/evidence task too far down the page. The shared widget generator
now uses mobile-only ordering so decision controls, review state, filters,
queue, selected detail, and final artifacts come before provenance/safeguards.
It also stacks progress/actions and safeguards and forces long queue/detail
text to wrap. A second mobile pass exposed action-button overflow in the detail
decision panel. The shared generator now uses single-column mobile decision
actions and single-column mobile decision-impact summaries. Post-fix mobile
captures for Deep Research, Report Builder, Journal-Bank Reconciliation, Prompt
Optimizer, and Concordato show the primary review task before metadata, with
queue rows, selected detail text, status pills, and decision controls contained
inside the viewport.

During the audit, the combined test run exposed test-order pollution from
plugin-script imports. `tests/plugins/test_codex_plugin_packages.py` now restores
repo-root imports and evicts plugin-vendored `modules.*` entries before importing
the FastAPI app. This is a test-hygiene fix, not a production change.

## What Is Actually Better

- MCP review tools now expose host-facing metadata: widget template URI,
  widget accessibility, model-visible resource URI, safe intent annotations,
  and render invocation status labels.
- Mobile review widgets now prioritize the actual review task before metadata:
  progress/actions, state filters, queue, detail, and artifact state appear
  before data posture, execution provenance, and safeguards.
- Non-plotting MCP-first workflows have a visible `review_handoff.md` artifact
  that points to review payloads, pending decisions, applied decisions, final
  artifacts, and exact validate/render/save/apply tool names.
- The strict review contract validator now fails runs that omit the expected
  review handoff card for supported MCP-first non-plotting plugins.
- Apply paths preserve or create the handoff card and include it in the review
  application trace when it is part of final artifacts.
- Report Builder source-table mapping edits are treated as native-regeneration
  triggers, not as inert comments.
- The repo now has a structured interaction-pattern catalog plus a repeatable
  scorecard for future plugin reviews. The catalog lives at
  `docs/openai_plugin_interaction_patterns.json`; the scorecard checks no
  `continue` theater, material approval boundaries, local/deterministic
  posture language, MCP review widgets, stateful decision persistence, visible
  handoff cards, and custom review-surface exceptions.
- The shared non-plotting workbench now has a repeatable demo-quality scorecard
  so the sample review path exercises queue selection, evidence comparison,
  decision variety, edit targets, and localized labels instead of remaining a
  thin placeholder.
- The shared non-plotting workbench now has a repeatable local-browser smoke
  audit for multilingual desktop/mobile rendering, runtime errors, horizontal
  overflow, localized labels, and screenshot capture.
- Generated workbench plugins now have a shared local-browser write-back
  server. The server injects the same host bridge used by the MCP widget,
  routes Save/Apply to the plugin MCP server, and writes durable decisions,
  applied decisions, target artifact edits, execution-trace updates, and final
  artifact state inside the run output folder. `scripts/build_codex_plugin_zip.py`
  injects this fallback as `scripts/review_server.py` for generated workbench
  plugins that do not already ship a custom local review server, and package
  tests verify that the fallback is present in downloadable ZIPs. The
  browser-level audit command opens the local server for every generated
  non-plotting workbench, clicks each plugin's actual Save/Apply controls,
  verifies `ui_decisions.json`, `applied_decisions.json`,
  `final_artifacts.json`, and the declared target-artifact edit, and saves
  screenshots as fixture evidence. The customer-validation recorder rejects
  run artifacts that still carry synthetic/demo/browser-audit markers, so this
  fixture evidence cannot be accidentally promoted into the real-customer
  readiness manifest. When the browser audit is saved with `--format json`,
  `scripts/audit_openai_pattern_adoption_readiness.py --browser-writeback-report <path>`
  reports it as the separate `browser_writeback_mechanism` tier; use
  `--require-browser-writeback` and `--verify-browser-writeback-screenshots`
  when that mechanism proof should be enforced.
- The scorecard doubles as a compact knowledge catalog: material questions
  only, local deterministic boundary, stateful decision review, visible review
  handoff, local browser write-back, bounded validated rendering, and shared UI
  with explicit exceptions.
- The scorecard now reports per-pattern coverage, so future reviews can see
  whether a pattern is absent from an applicable plugin instead of relying on a
  broad "all plugins OK" status.
- Severe scorecard failures are now part of plugin source validation in the
  package builder, so future plugin ZIP checks protect against the most
  important interaction regressions automatically.
- The combined readiness scorecard gives reviewers one OpenAI-pattern adoption
  report covering interaction-pattern coverage, workbench demo quality, and
  workflow-scenario contract coverage, while explicitly warning that green
  checks do not prove real customer-folder visual or semantic quality. Its
  validation tiers mark interaction contracts, demo UI contracts, and workflow
  fixture contracts as covered, while marking real customer-folder validation
  as `not_assessed`. It also emits the next evidence steps: collect
  representative customer cases, run the local review surface, validate final
  artifact semantics, and record a customer-validation manifest. The scorecard
  reads `docs/openai_pattern_customer_validation_manifest.json` when present;
  `docs/openai_pattern_customer_validation_manifest.example.json` shows the
  required shape without changing the default assessment. It can also write a
  TODO-filled starter with
  `--write-customer-validation-template <path>`, using the same expected plugin
  set as the scorecard, and it can upsert a real case with
  `--record-customer-validation-case` from a local workflow output folder. By
  default, real customer validation is expected across generated non-plotting
  workbench plugins; use `--expected-customer-plugin` to audit a narrower
  validation wave intentionally. Use
  `--require-customer-validation --verify-customer-validation-artifacts --fail-on medium`
  only when the live manifest is meant to act as a release-grade gate; that
  strict path verifies declared files exist, required JSON artifacts parse and
  contain evidence, screenshots/readbacks are non-empty, and
  `final_artifacts.json` is not still pending review. It also requires a
  reviewer UX verdict of `usable` for each passing covered case.

## Not Yet Proven

- This audit does not prove the visual quality is OpenAI-level. It proves
  contracts, metadata, persistence, packaging, focused workflow behavior,
  desktop/mobile browser smoke checks, and responsive visual QA across the nine
  generated non-plotting review widgets.
- This audit does not include a full `pytest -q` or `make check` run.
- The visual QA now covers English, Italian, French, German, and Spanish sample payloads,
  but it still uses generated demos rather than real customer payloads.
- This audit does not prove every native artifact type can be semantically
  edited and regenerated. Several DOCX/XLSX/PDF/PPTX paths still require
  workflow-specific regeneration when edits should modify those outputs.
- This audit does not prove the UX is "perfect." The shared workbench now has
  the right contract direction and usable responsive behavior, but final polish
  still depends on reviewing real customer payloads rather than demo rows.

## Recommended Next Gate

Before adding more features, review the adopted change in three slices:

1. Keep or revise the audit/build changes that gate interaction and demo QA.
2. Review the browser screenshots under
   `/private/tmp/non_plotting_workbench_visuals` for visual polish decisions.
3. Keep or revise the regenerated plugin ZIPs and accounting packs.
4. Use `scripts/audit_openai_pattern_adoption_readiness.py --format markdown`
   as the customer-validation intake: start with the listed next actions and
   generate a TODO-filled manifest with
   `scripts/audit_openai_pattern_adoption_readiness.py --write-customer-validation-template <path>`.
   Follow `docs/openai_pattern_customer_validation_runbook.md` for the actual
   real-customer validation procedure: case selection, local review UI use,
   screenshots, native-output readback, and manifest recording.
   For actual runs, prefer `--record-customer-validation-case` so case metadata,
   required run artifacts, screenshots, and decision-summary counts are
   recorded consistently from the local workflow output folder. Pass
   `--ux-verdict usable` only when the reviewer can complete queue selection,
   evidence comparison, decisions/edits, and artifact handoff without blocking
   UX issues, and mark every required `--ux-check`: `queue_clear`,
   `evidence_comparison_clear`, `decision_controls_complete`,
   `edit_flow_usable`, `artifact_handoff_clear`, and `no_blocking_issues`.
   When real validation exists in
   `docs/openai_pattern_customer_validation_manifest.json`,
   rerun the scorecard with
   `--require-customer-validation --verify-customer-validation-artifacts --fail-on medium`
   before claiming real-customer coverage. The strict command now checks both
   path existence and basic artifact content sanity.

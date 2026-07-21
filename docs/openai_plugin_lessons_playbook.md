# OpenAI Plugin Lessons For Mparanza Plugins

This playbook captures reusable patterns observed in OpenAI's bundled and
role-specific plugins, then adapts them to the Mparanza plugin model.

The Mparanza model stays different:

- source data stays local by default;
- deterministic Python owns calculations, parsing, matching, reconciliation,
  and chart-ready evidence;
- Codex owns orchestration, review, narrative, and handoff;
- local HTML/MCP surfaces render bounded payloads and capture decisions;
- no remote SQL or hosted notebook path is assumed unless the user explicitly
  chooses it.

The goal is to adopt interaction and reliability patterns, not OpenAI's data
execution model.

## Sources Reviewed

- Data Analytics plugin README and manifest:
  `openai/role-based-plugins` currently redirects to
  `openai/role-specific-plugins`.
- Data Analytics skills: `index`, `product-business-analysis`,
  `analyze-data-quality`, `validate-data`, `build-dashboard`,
  `jupyter-notebooks`.
- Data Analytics MCP artifact contract: `src/analytics-app-core.md` and
  `mcp/server.cjs`.
- OpenAI primary runtime document/presentation skills and Google Drive skill
  references for final-readback, artifact QA, native-surface write safety, and
  completion gates.

## Adopted Principles

### Ask Only When The Answer Changes The Work

OpenAI plugins do not ask for confirmation at every step. They ask when a
choice materially changes the source, method, destination, authority, or write
scope.

Mparanza rule:

- Do not ask the user to type `continue` as theater.
- Do ask before irreversible external writes, emails, uploads, destructive
  changes, or ambiguous source/method choices that materially affect the work.
- Use Plan-mode choices for 2-3 discrete setup decisions when available.
- Use chat for free-form answers or one-off clarifications.
- Use local HTML review only when many rows, fields, findings, mappings, or
  evidence items need stateful review.

### Preflight Before Write-Heavy Work

OpenAI's Data Analytics plugin has a user-context preflight and source-access
gate. Our equivalent should be local and deterministic.

Every substantial plugin run should write `run_intake.json` before
write-heavy execution. It records:

- plugin, workflow, language, input paths, output directory;
- inferred task, assumptions, unresolved material questions;
- dependency-check result and relevant script versions;
- local data posture, including whether any data was or will be sent to an LLM
  or connector.

### Required Source Means Required Source

OpenAI's source-access guardrail stops a path when the controlling source is
missing. This is directly useful for local professional workflows.

Mparanza rule:

- If a required local file, support document, ledger, bank extract, source PDF,
  mapping table, or deterministic output is missing, mark the run `blocked` or
  `partial`.
- Do not replace a missing required source with model inference.
- Optional enrichment may be skipped, but it must appear as a caveat when it
  matters.

### Deterministic Evidence First

OpenAI often generates SQL/Python dynamically. Mparanza should not copy that
for core accounting and chart calculations.

Mparanza rule:

- Deterministic scripts produce the analytical facts first.
- Codex reads structured outputs, requests follow-up runs when needed, and
  writes the review/narrative layer.
- The model may draft explanations, memos, emails, prompts, and review notes,
  but it must not silently override deterministic results.
- If a calculation was not produced by the deterministic path, label it as
  provisional or exploratory.

### Local Execution Boundary

OpenAI Data Analytics can work from uploaded files, pasted results, notebooks,
or connected warehouses. In that model, SQL may run in the local Codex session
for local files, or in an external system such as BigQuery, Snowflake, or
Databricks when a warehouse connector is the source of truth. The UI then
renders bounded reviewed rows and provenance; it is not the SQL execution
engine.

Mparanza rule:

- Commercialista plugin source files stay local by default.
- Deterministic parsing, reconciliation, checking, and report-generation
  scripts run locally in the Codex workspace/sandbox.
- External SQL, hosted notebooks, connector reads, uploads, or remote
  execution paths require an explicit user choice and must be recorded in
  `run_intake.json` and `final_artifacts.json`.
- If bounded excerpts are sent to a model, `run_intake.json` records excerpt
  metadata such as `excerpt_id`, source, purpose, content type, redaction
  status, and row/character counts; it does not repeat raw excerpt text.
- Strict review-contract validation rejects external connectors, uploads,
  remote SQL, or hosted execution unless `run_intake.json` records an explicit
  approval object with `approved=true`, `approved_by`, `approved_at`, `scope`,
  and `reason`.
- UI widgets render bounded evidence and capture decisions; they do not own
  authoritative calculations.

### Bounded Payloads And Reviewable Snapshots

OpenAI's Data Analytics MCP contract renders bounded snapshots, not arbitrary
raw data dumps.

Mparanza rule:

- Review UIs and MCP widgets receive bounded payloads.
- Non-plotting MCP review payloads are rejected before rendering when they
  exceed the server's item-count or serialized widget-payload byte limits.
- Payloads include source paths, row counts, truncation markers, evidence
  metadata, and the deterministic command or script that produced them.
- Use deterministic samples or previews for large outputs.
- Never put secrets, credentials, direct payment/contact identifiers, or raw
  unnecessary personal data into widget payloads.
- Never put raw model excerpt content into `model_excerpts_sent`; use compact
  metadata so the reviewer can see what was exposed without exposing it again.

### Validate Before Render Or Final Handoff

OpenAI's artifact path validates before rendering. Documents and Slides skills
verify final artifacts before claiming completion.

Mparanza rule:

- Validate `review_payload.json` before rendering a review UI.
- Validate or schema-check `ui_decisions.json` before applying decisions.
- Validate `final_artifacts.json` before final response.
- For native Excel/Word/PDF outputs, publish mechanical QA expectations in
  `final_artifacts.json` when the workflow knows them, such as required
  workbook sheets, required sheet headers, required workbook cells, required
  Word/report text in DOCX, HTML, Markdown, or plain text, or Office document
  members, so validators and review UIs can prove the artifact is inspectable
  before handoff.
- Prefer business-value workbook cells over pure header checks when a native
  workbook has stable summary rows, control totals, statuses, or mapped source
  fields that should be visible to the reviewer.
- PDF outputs may also declare `required_text`; strict validation checks a
  readable text layer when available and falls back to printable text extraction
  for simple generated PDFs before accepting the artifact.
- Open or render final files when the artifact format is visual or layout
  sensitive.
- Do not claim completion from file existence alone.

### First-Class Partial And Blocked States

OpenAI's artifact contract treats `partial` and `blocked` as visible states.
That is a strong pattern for professional workflows.

Mparanza rule:

- Use a shared state vocabulary: `pending`, `ready_for_review`, `reviewed`,
  `accepted`, `rejected`, `edited`, `needs_evidence`, `partial`,
  `blocked`, `final_ready`.
- Do not bury blocked evidence in caveats.
- Review UIs should show the state model directly: decision progress, pending
  rows, reviewed rows, needs-evidence rows, blocked rows, and final artifact
  state should be visible and filterable without opening raw JSON.
- `final_ready` requires both deterministic outputs and any required user
  decisions.

### Decision Capture Is The Interaction Contract

The useful part of a review UI is not that it exists. It is that user choices
write back into the workflow.

Mparanza rule:

- Decisions are persisted to `ui_decisions.json`.
- Allowed actions remain explicit: `accept`, `reject`, `edit`,
  `mark_unclear`, `request_more_documents`, `skip`.
- Applying decisions writes an applied-decisions artifact and updates
  `final_artifacts.json`.
- Review UIs should show the selected action's write-back impact before the
  user saves or applies it: persistence mode, explicit edit target when
  present, and explicit requested-document hints when present.
- Review UIs should also show review persistence state after reload or edits:
  current decisions, saved `ui_decisions.json` decisions, applied
  `applied_decisions.json` decisions, recovered widget drafts, and unsaved
  changes should be visible without opening JSON.
- Review UIs should summarize the main safeguards in one place: local/remote
  execution, external approval status, bounded payload count, decision
  persistence mode, and final artifact declaration.
- When persistence is unavailable or a save/apply call fails, the UI should
  show a recovery path beside the controls: which tool was attempted, the last
  error when available, and whether the reviewer can copy/download decision
  JSON or must reopen through the MCP/local-server surface.
- Generated review workbenches should not be copy-only HTML. When the MCP
  widget is not the primary visible surface, use the shared local browser
  server from `scripts/serve_review_workbench.py` or a workflow-specific
  `scripts/review_server.py` so the same Save/Apply controls can call the
  plugin MCP writer and persist decisions inside the local run output folder.
- `request_more_documents` decisions should not make the reviewer retype a
  document name already present in the review item. Save/apply tools may copy
  explicit fields such as `requested_document`, `missing_documents`,
  `required_document`, or `support_documents` from the item data/evidence into
  `ui_decisions.json`, `applied_decisions.json`, and blocker records. This is
  only a metadata carry-forward rule; it must not infer missing evidence from
  semantic content.
- Blocker queues should preserve explicit follow-up context when it is already
  present in item data/evidence, such as owner/responsible party, source
  system, due date, period, entity, record id, amount, reason, or priority. The
  shared field is `followup_context`, and it is copied into saved decisions,
  applied effects, and `final_artifacts.json` blockers.
- Missing-mapping or missing-support rows should publish actionable request
  text and context in the review item itself, so the reviewer can choose
  `request_more_documents` without retyping what the workflow already knows.
- `edit` decisions may update native text, CSV, JSON, or JSONL artifacts only
  when the review item carries an explicit target contract, such as target
  artifact, record id field, record id, and target field. Otherwise the edit
  stays as a review revision artifact.
- When an edit targets DOCX, XLSX/XLSM, PDF, PPTX, or another native binary
  output without a workflow-specific regeneration path, mark the artifact
  `native_regeneration_pending` and keep the run `partial_review_applied`
  rather than claiming `final_ready`.
- A workflow-specific regeneration path may clear that pending state only when
  the edit has an explicit target contract and the plugin rerenders the native
  artifact from local source state. Report Builder does this for section
  comments and source-table mappings by updating `used_recipe.json`,
  recomputing `report_analysis.json` and table outputs where needed, then
  regenerating `report_draft.md` and `report.docx`.
- Static HTML may copy/download JSON, but persistent save/apply requires an MCP
  or local-server path.

### Visible Handoff Beats Hidden JSON

OpenAI-style plugin handoff works because the user sees an app/card surface, not
because internal JSON exists. Local workflows should leave the same kind of
visible trail.

Mparanza rule:

- Every normal review-session run should leave a human-readable handoff card in
  the output folder.
- For MCP-first review plugins, the card is `review_handoff.md` and names the
  review payload, intake, pending decisions, applied decisions, final artifacts,
  and exact validate/render/save/apply tool names.
- For Audit Reconciliation, the primary normal handoff remains
  `artifact_card.md` plus the local browser review server URL.
- The handoff card is also listed in `final_artifacts.json` with required text
  checks so strict validation proves it is present and readable.
- The card is a navigation aid, not a substitute for persisting decisions to
  `ui_decisions.json` and applying them to `applied_decisions.json` plus
  `final_artifacts.json`.

### Provenance Must Survive The UI

OpenAI artifacts preserve source query metadata. Our equivalent is source
file, deterministic command, version, row count, and evidence object metadata.

Mparanza rule:

- Every material finding should trace back to source paths and deterministic
  output files.
- Every generated memo/report/email should trace to the decisions and evidence
  used to produce it.
- Do not make the final artifact the only record of what happened.
- For runs promoted to strict review-session validation, write
  `run_intake.execution_trace[]` with `step_id`, `kind`, `status`,
  `execution_location`, `command`, `inputs`, and `outputs`.
- `execution_location` should normally be `local_codex_workspace`; remote
  warehouse, hosted notebook, external connector, or upload execution remains
  opt-in and must also be recorded in `data_posture` with explicit
  `external_execution_approval`.
- Run `scripts/validate_plugin_review_contract.py --strict-execution-trace`
  when a workflow claims replayable local deterministic provenance. In that
  mode every written final output must be listed in an execution-trace output.
- The shared non-plotting workbench must render the same execution trace
  visibly, so reviewers can see whether work ran in `local_codex_workspace` or
  through an approved external path.

## Patterns To Reject Or Modify

Do not copy these patterns blindly:

- Remote warehouse execution as the default. Our default is local execution.
- Model-generated calculations where a deterministic script already owns the
  domain logic.
- Asking the user to type `continue` after every progress checkpoint.
- A separate one-off HTML app per plugin.
- Raw JSON review views when workflow-specific evidence panels are possible.
- Static HTML pretending to persist decisions when it can only copy/download
  JSON.
- UI polish that hides source gaps, blocked states, or missing evidence.

## Implementation Map

### Skills

Each plugin skill should state:

- what deterministic scripts own;
- what Codex owns;
- which user choices are material;
- when to stop, ask, proceed, or mark `partial`/`blocked`;
- which review payload and decision files are expected;
- what proves completion.

### Scripts

Plugin scripts should standardize on:

- `run_intake.json`;
- `review_payload.json` when review or rendering is needed;
- `ui_decisions.json` when the user reviews anything;
- `applied_decisions.json` when decisions alter outputs;
- `final_artifacts.json` for final files, caveats, blockers, and next actions.

### Local UI / MCP

Shared UI should:

- validate payloads before rendering;
- show workflow-specific evidence views;
- show the run's data posture in the review surface, including local files,
  model excerpts, connectors/uploads, and whether remote SQL or hosted
  execution was used;
- show execution provenance in the review surface, including local/remote
  location, command, status, inputs, and outputs for replayable steps;
- capture decisions with editable fields;
- show decision impact in the detail pane, including whether the MCP bridge can
  persist decisions, whether the current edit has an explicit artifact/field
  target, and what document request was prefilled from item data/evidence;
- show saved/applied/recovered/unsaved decision state in the action band so a
  reopened review does not hide already persisted decisions;
- show a compact safeguards panel that summarizes local execution, external
  approval, payload bounds, decision persistence, and final artifact readiness;
- show fallback/failure recovery guidance when static HTML can only copy JSON
  or when save/apply does not persist;
- persist decisions through the MCP/local-server bridge;
- when a workflow has both a primary local browser server and an optional MCP
  widget, test that the primary browser HTML exposes the same safeguards,
  provenance, and persistence bridge rather than treating the MCP widget as the
  only polished surface;
- render final artifact QA metadata from `final_artifacts.json`, including
  row counts, required workbook sheets, required table columns, blockers,
  caveats, and next actions;
- fall back to Markdown or JSON copy/download when MCP is unavailable.

### Tests

Each migrated plugin should have tests for:

- deterministic script output contracts;
- the shared review-session contract with
  `scripts/validate_plugin_review_contract.py`;
- plugin-specific review payload schema;
- bounded item-count and payload-byte rejection before rendering, covered for
  non-plotting and chart MCP review servers;
- render tools reject malformed payloads before returning a visible widget,
  covered for non-plotting and chart MCP review servers;
- decision save/apply schema;
- final artifact manifest, including output `path`, `kind`, `status`,
  caveats, next actions, review status, and blockers when present;
- strict final-output path and content validation where the workflow writes
  durable files.
- fallback behavior when UI/MCP is unavailable.
- structured interaction-pattern catalog at
  `docs/openai_plugin_interaction_patterns.json` plus a repo-level
  interaction-pattern audit with
  `scripts/audit_plugin_interaction_patterns.py --format markdown`, so plugin
  skills and MCP review surfaces are checked for no `continue` theater,
  material approval boundaries, local/deterministic posture language,
  stateful decision persistence, visible handoff cards, and render-only or
  custom review-surface exceptions. The audit also reports per-pattern
  coverage, including applicable, satisfied, and missing-applicable plugins,
  plus playbook traceability and rejected OpenAI-style patterns with their
  local replacements and guardrail signals.
- shared workbench demo-payload audit with
  `scripts/audit_non_plotting_review_workbench_demos.py --format markdown`,
  so generated non-plotting demos must exercise a real queue, multiple review
  item types/actions, evidence rows, explicit edit targets, populated detail
  panels, localized workflow labels, and item/action values accepted by each
  plugin MCP validator. The audit also exposes workflow identity fields and
  fails duplicate `detailMode` values or shallow panel definitions, so a shared
  renderer remains a shared shell with plugin-specific review desks rather than
  one generic page repeated across workflows.
- adapter-demo save/apply regression tests in
  `tests/plugins/test_non_plotting_review_workbench.py`, so every generated
  non-plotting demo payload is accepted by the same MCP decision writer that
  persists `ui_decisions.json`, applies decisions, and updates
  `final_artifacts.json`.
- real review-payload contract validation through
  `scripts/validate_plugin_review_contract.py`, so generated workflow
  `review_payload.json` item types and actions are checked against the plugin
  MCP writer contract when available.
- generated review-payload coverage audit with
  `scripts/audit_review_payload_contract_coverage.py --format markdown`, so
  each generated non-plotting workbench plugin must have a plugin-owned
  contract test and a workflow-scenario test that validates actual run
  artifacts with `validate_contract(...)`.
- combined adoption readiness scorecard with
  `scripts/audit_openai_pattern_adoption_readiness.py --format markdown --report-path <path>`,
  so reviewers can persist interaction-pattern coverage, workbench demo quality,
  and workflow-scenario contract coverage in one human-facing report, with
  validation tiers that keep real customer-folder validation separate from
  fixture-based workflow evidence and next actions for collecting representative
  cases, screenshots, saved decisions, final artifact readback, and a
  customer-validation manifest. Keep the live manifest at
  `docs/openai_pattern_customer_validation_manifest.json` when real validation
  exists; use `docs/openai_pattern_customer_validation_manifest.example.json`
  as the static shape reference. Generate an evidence checklist with
  `scripts/audit_openai_pattern_adoption_readiness.py --write-customer-validation-template <path>`
  before running real cases, preflight each candidate run with
  `scripts/audit_openai_pattern_adoption_readiness.py --preflight-customer-validation-case`
  so artifact, screenshot, UX-check, synthetic-marker, and manifest-schema
  problems are caught without modifying the live evidence file. Use
  `--infer-case-metadata-from-run` only for low-risk run metadata
  (`--plugin`, `--scenario-name`, `--language`); keep case id, input case,
  reviewer, screenshots, UX checks, and reviewer notes as explicit validation
  evidence. Then record each completed local run with
  `scripts/audit_openai_pattern_adoption_readiness.py --record-customer-validation-case`
  so required artifacts, screenshots, and decision summaries come from the run
  output folder instead of hand-edited JSON. Passing covered cases must include
  `--ux-verdict usable`, all required `--ux-check` values for queue clarity,
  evidence comparison, decision controls, edit flow, artifact handoff, and no
  blocking UX issues, plus reviewer notes; `usable_with_issues` remains partial
  evidence until the issue is fixed or explicitly accepted. The default
  expected coverage is
  the generated non-plotting workbench plugin set; pass
  `--expected-customer-plugin` for a deliberately narrower validation wave.
  After real evidence exists, add
  `--require-customer-validation --verify-customer-validation-artifacts --fail-on medium`
  to turn missing or partial customer-folder coverage, including missing local
  artifact files, malformed/empty JSON evidence, empty screenshots/readbacks,
  still-pending `final_artifacts.json`, non-usable UX verdicts, or incomplete
  UX checks, into a failing gate.
- persisted adoption evidence bundles with
  `scripts/build_openai_pattern_adoption_evidence.py --output-dir <dir>`, so the
  readiness JSON/Markdown, browser write-back HTML gallery, customer-validation
  template, customer-validation Markdown/JSON plans, customer-validation HTML
  checklist, completion assessment, adoption review dashboard, optional browser
  write-back report, bundle manifest, and reviewer README live together. The
  completion
  assessment maps the original objective to evidence and remains incomplete
  until real customer-folder validation is covered. The manifest and README
  include rerunnable commands for mechanism evidence, bundle rebuild, and strict
  customer validation. Run the local browser write-back audit separately when
  available, then pass its JSON report with
  `--browser-writeback-report <path>`; the bundle copies available screenshots
  into `browser_writeback_gallery.html` so reviewers can visually scan the
  generated review surfaces. Open `adoption_review_dashboard.html` first for a
  single status page across validation tiers, evidence links, objective
  requirements, per-plugin adoption status, adopted lessons, rejected patterns,
  local replacements, pattern coverage, and next actions. The companion
  `customer_validation_checklist.html` shows per-plugin real-case status,
  required artifacts, required UX checks, preflight/record commands, and the
  narrow fields allowed for `--infer-case-metadata-from-run`. After
  representative customer cases are recorded, pass
  `--customer-validation-manifest <path>
  --require-customer-validation --verify-customer-validation-artifacts` so the
  same bundle records the strict real-customer gate result. Add
  `--require-complete-objective` only when the bundle command itself should fail
  unless every objective requirement is covered.
- local-browser smoke audit with
  `scripts/audit_non_plotting_review_workbench_visuals.py --format markdown`
  when Chrome/Playwright is available, so generated workbenches are opened at
  desktop and mobile sizes across selected languages, sample MCP-style payloads
  are loaded, rows/details/actions/localized labels are checked, runtime errors
  and horizontal overflow are caught, and screenshots are written for review.
- plugin package validation through `scripts/build_codex_plugin_zip.py --check`,
  which now reuses the interaction-pattern, workbench-demo, and
  generated-payload coverage audits and fails plugin source validation on
  blocker/high/medium interaction, demo-quality, or coverage issues.

## Near-Term Adoption Backlog

| Pattern | Current Status | Next Implementation |
| --- | --- | --- |
| Shared review UI strategy | Partial | Keep non-plotting widgets on the shared renderer and remove plugin-specific drift. |
| Shared workbench demo QA | Adopted for generated non-plotting widgets | `scripts/audit_non_plotting_review_workbench_demos.py` verifies that every generated demo payload has enough workflow content to exercise the actual review UI: queue, detail panels, evidence, action variety, edit-target impact, localized labels, and item/action values accepted by the plugin MCP validator. It now also reports each adapter's workflow mode and fails duplicate `detailMode` values or shallow panel definitions, so shared HTML remains workflow-specific in presentation. `tests/plugins/test_non_plotting_review_workbench.py` also runs those adapter demos through the plugin MCP save/apply path, so demo item types cannot drift away from workflow validators. The package builder now runs the demo-quality check for plugins that ship `review-workbench-adapter.json`. Keep this as a cheap gate before visual QA with real customer payloads. |
| Shared workbench visual smoke | Adopted as a local-browser QA step | `scripts/audit_non_plotting_review_workbench_visuals.py` opens every generated workbench in headless Chrome at desktop and mobile sizes, loads sample MCP-style review payloads, checks rows/details/decision controls/key sections/localized labels, detects console/page errors and horizontal overflow, and can write screenshots. It supports `--languages en,it,fr,de` for multilingual smoke review. Keep it as an evidence step when reviewing UI changes; do not make it a package gate because it depends on local browser availability. |
| Local browser write-back | Adopted for generated workbenches | `scripts/serve_review_workbench.py` injects a local `window.openai` bridge into generated workbench HTML, routes Save/Apply to the plugin MCP server, and persists `ui_decisions.json`, `applied_decisions.json`, target artifact edits, execution-trace updates, and `final_artifacts.json` under the run output folder. Package generation injects this fallback as `scripts/review_server.py` for generated workbench plugins that do not already ship a custom local server. `scripts/audit_local_review_workbench_writeback.py` now provides browser-level fixture evidence across every generated non-plotting workbench by opening the local server, clicking each plugin's actual Save/Apply controls, and verifying the declared target artifact was updated. Save that audit with `--format json` and pass it through `--browser-writeback-report` when the readiness scorecard should show this as the separate `browser_writeback_mechanism` tier. |
| Generated payload contract coverage | Adopted for generated non-plotting widgets | `scripts/audit_review_payload_contract_coverage.py` reports the plugin-owned contract test and the workflow-scenario test that validates generated review-session artifacts for each shared-workbench plugin with `validate_contract(...)`. It ignores unrelated plugin-name mentions and flags contract tests that do not appear to exercise workflow-generated artifacts. The package builder now runs this check for plugins that ship `review-workbench-adapter.json`. Keep it as the minimum evidence that workflow outputs, not only adapter demos, are covered. |
| Decision persistence | Adopted for MCP review plugins | Keep save/apply decision tools covered for non-plotting and chart review plugins; require persistence to `ui_decisions.json`, application to `applied_decisions.json`, and final status updates in `final_artifacts.json`. |
| First-class partial/blocked states | Adopted for non-plotting MCP save/apply | Report Builder missing-section rows and Concordato unmatched-plan/extraction-error rows now publish requested-document hints and follow-up context, and request-more-documents decisions carry them into blocker records. Extend partial/blocked checks into workflow-specific evidence and final-artifact QA where needed. |
| Edit/revision handoff | Partial | MCP apply tools for non-plotting and chart review plugins write safe text revisions under `revisions/`, directly update existing text final artifacts inside `run_intake.output_dir`, back up originals under `revisions/originals/`, update explicit CSV/JSON/JSONL row targets, and list all updates in `final_artifacts.json`. Audit Reconciliation review-row edits now update the exact `codex_review_packet.json` row through the primary local browser server by `review_id`, so reviewer notes become part of the durable review packet rather than a disconnected revision. Deep Research claim edits now write reviewer corrections to `claims_review.json.claims[].proposed_fix` through the shared JSON records-key path, then deterministically refresh `validation_audit.json` and `validation_package.md` from the updated review JSON so the final Markdown package includes the correction and strict `required_text` readback proves it; when `validated_document.docx` is declared or present, the apply path regenerates the Word output from the refreshed validation package, records `native_regenerated_paths`, and strict DOCX visible-text readback proves the correction is in the native artifact. Concordato Plan Review memo edits now create or update `codex_run_review.md`, append the reviewed memo to `concordato_review_summary.docx` when the Word summary is part of the artifact gallery, record `native_regenerated_paths`, and publish strict DOCX visible-text checks for the memo. Prompt Optimizer edits to `optimized_prompt.md` now rerun deterministic prompt validation and refresh `prompt_audit.json`, `prompt_package.md`, `source_domains.txt`, and `source_domains_comma.txt`, with strict readback proving both the edited prompt and refreshed package metadata. When a structured edit makes a declared workbook stale, Check Entries and Journal-Bank now regenerate the dependent XLSX, record `native_regenerated_paths`, and publish strict workbook sheet/header/cell checks for the edited cell. Add deterministic native regeneration where other workflows need DOCX/XLSX/PDF refresh after review edits. |
| Local data posture | Adopted for review-session plugins | Keep `data_posture` required in strict review-session tests for non-plotting and chart plugins, including local files read, model excerpts sent, external connectors used, upload paths used, and local deterministic calculation mode. Strict validation rejects external connectors, uploads, remote SQL, or hosted notebooks unless `external_execution_approval` records `approved=true`, `approved_by`, `approved_at`, `scope`, and `reason`. |
| Execution trace | Adopted for review sessions and review application | `scripts/validate_plugin_review_contract.py --strict-execution-trace` can require `run_intake.execution_trace[]` with replayable deterministic steps and reject written final outputs that are not listed in trace outputs. Current non-plotting review-session plugins and chart/review-session plugins append local deterministic execution traces after writing `final_artifacts.json`, and generated-run fixture tests enable strict execution-trace validation. MCP apply tools for non-plotting and chart review plugins now append a `deterministic_review_apply` trace step when reviewer decisions are applied, and the Audit Reconciliation local browser server does the same for browser-based Apply. Strict validation requires a review-apply trace when `final_artifacts.json.review_application` exists and verifies that applied manifests, changed artifacts, regenerated outputs, backups, and `final_artifacts.json` are listed in review-apply outputs. Remote execution locations in the trace require explicit `data_posture.external_execution_approval`. |
| No `type continue` theater | Adopted for current plugin skills | Added to `plugin-ui-strategy` and plugin guide checklist; plugin skills now use execution checkpoints and ask for approval only for external, destructive, approval-sensitive, or materially unresolved steps. `tests/plugins/test_codex_plugin_packages.py::test_plugin_skills_do_not_require_continue_theater` now blocks literal continue-command prompts and requires the approval boundary in plugin skill text. |
| Final artifact gallery | Partial | `scripts/validate_plugin_review_contract.py` now requires each final output to include `path`, `kind`, and `status`, and requires `caveats` and `next_actions` to be lists. MCP apply paths for non-plotting and chart review plugins preserve caveats/next actions, add blocker lists from follow-up decisions, and record `review_status`. The shared non-plotting workbench shows compact artifact QA chips plus an expandable verification detail panel for exact required text fragments, columns, sheets, headers, workbook cells, and QA checks. Extend richer native handoff surfaces where needed. |
| Final artifact path/content QA | Partial | Strict review-session validation can now fail when `final_artifacts.json` references a missing written or updated output path, or an unreadable final output. It checks JSON/JSONL parsing, non-empty text-like files plus optional `required_text` fragments, HTML visible text for required fragments, DOCX Office ZIP structure plus optional `required_text` fragments, PDF headers plus optional `required_text` fragments through text-layer/printable-text readback, XLSX workbook sheets and worksheet XML, optional `required_sheets`, `required_sheet_headers`, and `required_cells` metadata, optional table `row_count`/`min_rows`/`required_columns` metadata for CSV/JSON/JSONL, PNG signatures, SVG XML roots, and generic nonzero file size. Audit Reconciliation publishes required Word report sections plus workbook sheet/header/cell checks; those workbook checks now include business-value readback for visible index entries, assumption values, first reconciliation-row document/id cells, and commercialista row counts, and the plugin publishes/updates `codex_review_packet.json` with required `review_id` and `review_notes` columns for reviewed packet edits. New Client's client-file-preparation engine publishes client/year/file/missing-request/email-question/fiscal-field required-text checks plus inventory, structured-field, and XML summary row/column checks; Check Entries, Journal-Bank Reconciliation, Deep Research Validator, Prompt Optimizer, Concordato Plan Review, and Report Builder publish required Markdown/text sections where the workflow writes stable headings. Check Entries initial workbook handoff publishes first-row movement/status/support/checks cells, and regenerated Check Entries workbooks publish the reviewer-edited review-note cell. Journal-Bank initial workbook handoff publishes first matched, unmatched-bank, and unmatched-journal business cells, and regenerated Journal-Bank workbooks publish the reviewer-edited review-note cell. Journal Sampling initial sample handoff publishes required columns and first-row CSV/XLSX sampled-entry values. Deep Research edited-claim packages add the reviewer correction itself to `validation_package.md` required text after downstream refresh and to regenerated `validated_document.docx` visible required text when Word is declared or present; Concordato memo edits add the reviewed memo fragments to regenerated `concordato_review_summary.docx` visible required text; Prompt Optimizer edited prompts add required text for `optimized_prompt.md` plus refreshed source-domain text in `prompt_package.md`; initial and source-map-regenerated Report Builder `report_tables.xlsx` outputs publish summary sheet headers, first section/status/table/row/column cell checks, and first mapped section preview-sheet header/first-row checks; Concordato Plan Review `concordato_tie_out_workpaper.xlsx` now publishes sheet/header/cell checks for source inventory, amount-candidate, and candidate-match business values; selected New Client, Report Builder, and Concordato table outputs publish row/count column expectations in their artifact galleries. Keep adding workflow-specific readback checks for rendered layouts and broader business-specific native artifacts. |
| Structured source packages | Partial | Use structured source packages for workflows where they add value beyond the normal review payload. |
| Validation before rendering | Adopted for non-plotting MCP review plugins | Non-plotting render tools call the same validators as their `validate_*_review` tools, and the shared workbench test now proves malformed render payloads are rejected before a visible widget is returned. Extend equivalent coverage to chart plugins when their render contracts are touched. |
| Interaction-pattern catalog and audit | Adopted as a repo scorecard and package gate | `docs/openai_plugin_interaction_patterns.json` is the structured catalog of adopted and rejected OpenAI-derived interaction patterns. `scripts/audit_plugin_interaction_patterns.py` loads that catalog and reports per-plugin adoption, per-pattern coverage, playbook traceability, and rejected-pattern guardrails without forcing every plugin into the same UI. `scripts/build_codex_plugin_zip.py --check` reuses that audit during plugin source validation and fails on blocker/high/medium interaction issues. `tests/scripts/test_audit_plugin_interaction_patterns.py` and `tests/plugins/test_codex_plugin_packages.py` prove the audit detects `continue` theater, missing approval boundaries, missing stateful decision contracts, missing visible handoff cards, applicability-aware pattern coverage, malformed catalog entries, rejected-pattern drift from the playbook, unknown guardrail signals, and builder integration. Keep this as the first cheap check before deeper workflow-specific review. |

## Working Rule

When deciding whether to adopt an OpenAI plugin pattern, use this test:

1. Does it improve user control, evidence quality, repeatability, or handoff?
2. Can it preserve local deterministic execution?
3. Can it be shared across plugins instead of becoming a one-off UI?
4. Can it be verified through files, tests, or rendered artifacts?

Adopt the pattern only when the answer is yes to all four.

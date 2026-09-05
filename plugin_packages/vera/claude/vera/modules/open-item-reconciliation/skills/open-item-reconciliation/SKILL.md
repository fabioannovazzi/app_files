---
name: open-item-reconciliation
description: Use when a user has a population reported as open at a cut-off and wants Claude to determine which items are closed, partly closed, or still open from ledgers, journals, bank statements, payment orders, factoring or advance evidence, and compensation evidence, then produce reviewable Excel and Word workpapers. Do not use for direct bank-statement-to-journal matching; use journal-bank-reconciliation for that task. This is a Claude workflow plugin, not a standalone CLI.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive client/engagement run path described below; never
choose a sibling output folder.

# Open-item Reconciliation

Use this skill when the starting population is a list of items reported as open
at a cut-off. Determine which items are closed, partly closed, or still open
from the available accounting evidence, then document residuals, exceptions,
and missing support. Ledgers, journals, bank statements, payment batches,
factoring or advance records, and compensation evidence support that test; they
do not replace the required open-item population.

If the starting population is instead the movements in a bank statement and
the task is to match them directly to journal or ledger entries, use
`journal-bank-reconciliation`.

The plugin is a **Claude workflow plugin**. Helper scripts are deterministic support code; Claude remains responsible for inspecting the folder, asking for missing assumptions, running the workflow, reviewing the output, and explaining limitations.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Keep progress and handoff concise. Use a checklist, Run Intake table, Decision
Table, or Artifact Card when it helps the user review complex work; their chat
format is optional. Preserve all required saved mappings, review decisions,
validation records, and artifacts. Resolve material choices before dependent
execution and continue independent authorized work while awaiting an answer.
Obtain authorization for external, destructive, or approval-sensitive actions
when not already given, and preserve workflow-specific approval gates.
At delivery, link outputs and state their purpose, review status, unresolved
items, and next action. Create `run_review.md` when a durable review index
is useful; never edit plugin source or generated ZIPs during a user-data run.

## Beta Positioning

Present the plugin as one vertical professional workflow:

```text
Test a reported open-item population against ledger, bank, payment,
factoring/advance, and compensation evidence, then show which items are
closed, partly closed, or still open in reviewable Excel/Word workpapers.
```

Do not present it as a generic accounting chatbot, a standalone app, or an MCP/API service. The user experience should feel like a guided Claude run: inspect the folder, confirm assumptions, run deterministic helpers, review exceptions, and deliver workpapers with clear limitations.

## Source Rule

For development, the repo source is the only editable source:

```text
plugins/open-item-reconciliation
```

Do not edit downloaded plugin folders, ZIP contents, or Claude cache copies as source.

Filename and text keyword matches are source-role suggestions only. Before raw
ingestion, Claude must record one `reviewed_source_decisions` entry per current
source. Each entry contains the reviewed role, adapter family, reviewer
identity/date, accounting perimeter, cent-only monetary convention
(`reported_increment: "0.01"`), and `date.order` (`day_first` or
`month_first`). The v2 decision and one qualification carrying its
`reviewed_mapping_ref` are bound to exactly one current-byte source receipt.
Plain `reviewed_source_roles` or
`reviewed_source_adapters` maps are not authority. Ambiguous or unreviewed files
abstain and surface `needs_review`; unsupported layouts surface
`unsupported_source_layout` and emit no accounting rows. The legacy Italian
PDF/print-export parser may be named only inside this reviewed decision with
adapter `legacy_it_accounting_export_v1`; do not ask the user to edit plugin
files.

Every `reviewer_ref` is an unsigned, unauthenticated, untrusted label. Its
canonical syntax and sealed bytes do not prove the reviewer's identity or
authorization.

## Core Principle

Deterministic code is the authority for row-level classifications.

Vera-assisted review is a quality-control layer. It may find issues, identify missed patterns, or propose rule changes, but it must not silently override deterministic results. If review finds a material error, fix the deterministic rule, rerun, and regenerate outputs.

## Required Questions

Ask only what is needed. If not obvious, ask for:

- input folder;
- year or cut-off date;
- working language and source-document language;
- which file is the population reported as open at the cut-off;
- which files are ledgers, journals, bank statements, payment orders, factoring/operator evidence, or compensation support;
- whether post-cut-off events are excluded;
- whether payment orders are only bridge documents or can be treated as evidence;
- whether compensation requires bank evidence or documented accounting support is sufficient.

Default factoring treatment: when a factor/operator or pro-soluto bridge is tied
deterministically to a bank-statement payment from the bank files provided, treat
that as closing evidence. Do not run a second conservative pass that disables
factoring/advance closure merely because the user did not explicitly confirm
the default. Ask only when the user wants factoring/advance references to be
treated as non-closing, or when the link to the bank statement is ambiguous.
Treat that request as a stricter-than-default factoring treatment.

Do not ask the user to edit JSON, YAML, or plugin files.

## First Run Onboarding

For a beta user's first run, guide the work in this order:

1. Confirm the input folder and inventory the available files.
2. Confirm period, cut-off date, working language, and source-document language.
3. Identify the population to reconcile and map source roles for evidence files.
4. Confirm evidence assumptions only when not inferable: post-cut-off events, payment orders, and compensation support. Use the default factoring/advance treatment unless the user explicitly asks for a stricter pass.
5. Run `python scripts/check_dependencies.py` from the plugin directory before helper scripts; add `--requirements requirements-ocr.txt` only when scanned PDFs or OCR are needed.
6. Run extraction/reconciliation and write Excel, Word, JSON audit artifacts, and review rows.
7. Summarize exceptions, missing evidence, review sample status, and concrete next steps.

Expected delivery artifacts are:

- `riconciliazione_audit.xlsx`;
- `scheda_operativa_commercialista.xlsx`;
- `relazione_riconciliazione_audit.docx`;
- `assurance_final_outputs/reconciliation_results.json` as the versioned
  canonical machine-readable record. Its `source_processing` and `analyses`
  sections contain the schedules rendered in the workbook; do not create one
  standalone JSON file per schedule;
- `source_pages.json`;
- `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
  `final_artifacts.json` for browser/widget review handoff;
- `artifact_card.md` as the mandatory visible handoff card for every normal
  run;
- `review_ui.html` as a standalone local fallback when the local browser server
  cannot start or the browser cannot be opened;
- professional review rows in the workbook;
- targeted missing-evidence requests when the user needs an operational follow-up pack.
- `prepared_records.json`, `assurance_receipts.json`, `assurance_gates.json`,
  `final_output_inventory.json`, and the exact `assurance_final_outputs/`
  boundary for replayable mechanical assurance.

Skipped sources, unsupported layouts, and parser failures must be visible as
review items, on the workbook's `Source processing issues` sheet, and in
`source_processing.extraction_errors` in the canonical record.

## Client folder gate

Every raw-input run must be bound to one exact Studio Archive client folder.
Do not infer the client from a person's name, a filename, an engagement label,
or the contents of an accounting file.

1. Call `studio_archive_status`, select one exact client and engagement, and
   refresh first if Studio Archive reports changed top-level scopes.
2. Import the reviewed sources into that engagement, then call
   `prepare_studio_client_workflow` with workflow ID `open-item-reconciliation`.
   Pass its returned `client_engagement_path` unchanged as
   `--client-engagement` to `raw_input_runner.py`.
3. Start that run before executing the helper. The portable context fixes the
   execution inputs as `Vera/engagements/<engagement-id>/runs/<run-id>/inputs`
   and the only permitted output path as the sibling `outputs` directory in
   the selected customer folder. Never substitute a freely chosen directory.
4. Stop when the context, input receipt, execution copy, lifecycle, or customer
   manifest is stale or edited. Do not copy, merge, or relabel another
   customer's files to make validation pass.

Call `finalize_studio_client_workflow` after the last output write and declare
every physical file with a stable artifact ID, relative path, concrete purpose,
audience, and media type. Review that closed declaration, then call
`complete_studio_client_workflow`; record `failed` or explicitly cancel an
abandoned run instead of treating a partial directory as a result.

The same client/engagement context must appear in `run_intake.json`,
`review_payload.json`, `run_manifest.json`, `prepared_records.json`, the
canonical reconciliation record, and `assurance_receipts.json`. The portable
folder binding intentionally excludes email addresses, legal names, tax
identifiers, document content, and mailbox content.

## Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. Review those artifacts directly. Report the package as
`ready_for_professional_review` where that status exists, otherwise as
`pending_review`.

When a validated MCP tool, browser interface, or local workbench is callable, it
may optionally persist or apply reviewer actions. Its absence never blocks
delivery. Never claim `applied` or `final_ready` unless corresponding persisted
artifacts prove it. A file or chat review without those artifacts remains
pending professional review.

Review actions cannot waive a failed deterministic check. Keep failed checks,
missing evidence, unresolved decisions, and applicable blockers visible in the
artifact card and final response.

## Starter Prompt Bank

Load `references/starter-prompts.md` for beta-facing prompt examples. Keep this `SKILL.md` focused on routing, guardrails, first-run flow, dependency checks, deterministic workflow ownership, feedback, and packaging.

## Evidence Standards, Data, And Checks

Load `references/evidence-and-checks.md` when deciding evidence strength, canonical fields, source roles, or deterministic accounting checks.

Load `references/workflow-reference.md` for the exact source-decision contract,
receipt replay points, gate meanings, and promotion rules.

Core rule: row-level classifications must be supported by deterministic evidence and preserved source references. Candidate allocations and aggregate roll-forward checks may guide review, but they must not close individual rows unless a deterministic rule connects row-level evidence.

## Deterministic Run

Before running extraction or reconciliation helpers, check the plugin runtime dependencies from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If scanned PDFs or OCR are needed, also check optional OCR dependencies:

```bash
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

If dependencies are missing, install from the declared requirement file when the environment allows it. If installation is not available or requires approval, tell the user in non-technical language which capability is missing and what permission or package set is needed. Do not fail silently and do not continue into a partial run that will produce unreliable output.

`run_intake.json` records a `dependency_check` object automatically when the
run intake is written. It includes status, timestamp, checked requirement
files, and missing packages. If OCR/scanned-PDF support is requested through run
assumptions, the intake check includes `requirements-ocr.txt`.

The deterministic workflow should:

1. inventory source files and capture full current-byte receipts;
2. record/replay one v2 reviewed source, perimeter, adapter, cent-only money,
   and date-order decision plus one mapping-bound qualification per source;
   suggestions never authorize parsing;
3. extract only sources with qualified adapters and abstain on ambiguous money,
   floats, or unsupported layouts;
4. normalize rows to exact decimal text and the reviewed entity, party,
   currency, unit, direction, and allocation perimeter;
5. replay source, decision, qualification, bounded record/value locators, and
   implementation receipts, then atomically seal `prepared_records.json`;
6. classify rows and build exact allocation/conservation ledgers, preserving
   non-zero residuals;
7. produce workpapers, diagnostics, an exact one-row-per-record review set, and
   record-aware material-value addresses for every declared Excel/Word/JSON;
8. publish only the declared regular files into `assurance_final_outputs/`,
   receipt every ordinary single-link file, reject symlinks/hardlinks/special
   files, and replay declared-versus-physical equality;
9. write independent assurance gates. Pending/failed professional review blocks
   reporting; publication remains withheld as a separate action. Build and
   replay final controls in staging before transactional promotion.

The raw runner does not interpret arbitrary CSV or arbitrary spreadsheet
layouts. Such a source requires a qualified adapter or reviewed external
preparation; do not coerce it through a similar-looking parser.

When extracting long PDFs, enable `verbose_extraction` and set
`pdf_progress_every_pages` when the default cadence is too sparse. The runner
emits file-start, page-progress, OCR page, cache-hit, and file-done progress
messages so the reviewer can see which PDF is consuming time.

For generic runs, pass `scope_year` and `cutoff_date` through assumptions when the work is period-specific. Do not rely on a hidden default year.

Useful helper scripts include:

- `scripts/raw_input_runner.py`: client-bound input-folder orchestration; its
  CLI requires the exact Studio Archive `--client-engagement` context and
  `--assumptions-json`;
- `scripts/reconciliation_workflow.py`: normalized-row reconciliation and native output orchestration;
- `scripts/audit_assurance.py`: isolated validation, predecessor capture/retention, and assurance replay commands;
- `scripts/build_review_sample.py`: post-run selection of a small reviewer-friendly sample, with Italian operational wording and a Markdown request draft.
- `scripts/build_missing_evidence_requests.py`: post-run workbook of targeted missing-evidence requests that distinguishes evidence already acquired from the exact missing item per row, using localized operational labels instead of internal status/rule codes.

Run every secondary helper with the same still-running portable context; each
helper rejects an input or persistent output outside that run:

```bash
python -I -B scripts/audit_assurance.py \
  --client-engagement <customer-run>/context.json \
  validate-run-json <client-run-output>
python scripts/build_review_sample.py <client-run-output>/riconciliazione_audit.xlsx \
  --client-engagement <customer-run>/context.json
python scripts/build_missing_evidence_requests.py <client-run-output>/riconciliazione_audit.xlsx \
  --client-engagement <customer-run>/context.json
```

Normalization/matching and workpaper-output internals are retained source units
loaded by the validated entrypoints; do not import or execute them directly.

## Review, Outputs, Locales, And Wording

Load `references/review-and-outputs.md` when producing workpapers, reviewing deterministic classifications, or preparing operational follow-up requests.

Load `references/locales-and-wording.md` when choosing language settings or writing localized evidence requests.

Before delivery, Claude must review the deterministic output, preserve limitations, and avoid exposing internal status/rule labels in client-facing requests.

## Packaging

After changing this plugin source, use the repo-local `plugin-release` workflow:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py open-item-reconciliation
.venv/bin/python scripts/build_codex_plugin_zip.py open-item-reconciliation --check
.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py
```

Do not patch the downloadable ZIP manually.

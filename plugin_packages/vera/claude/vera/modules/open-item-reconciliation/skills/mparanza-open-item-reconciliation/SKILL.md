---
name: mparanza-open-item-reconciliation
description: Use when a user has a population reported as open at a cut-off and wants Claude to determine which items are closed, partly closed, or still open from ledgers, journals, bank statements, payment orders, factoring or advance evidence, and compensation evidence, then produce reviewable Excel and Word workpapers. Do not use for direct bank-statement-to-journal matching; use journal-bank-reconciliation for that task. This is a Claude workflow plugin, not a standalone CLI.
---

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive client/engagement run path described below; never
choose a sibling output folder.

# Open-item Reconciliation

## Jurisdiction and Geneva

For a CH-GE mandate, read `references/geneva.md` before the steps below. It specifies the Geneva input, source and output adaptations within this existing function. Choose governing jurisdiction independently of output language; the ordinary Italian path remains available for IT.


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

Currency: carry the currency evidenced by the source or confirmed for the engagement (including CHF). Never infer currency from output language or silently default to EUR. If unresolved, obtain the currency before computing or matching amounts. Keep different currencies separate; conversion requires an explicit reviewed rate, date and basis.

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
source. Each entry contains the reviewed role, adapter family,
accounting perimeter, cent-only monetary convention
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

For ordinary header-based CSV and XLSX exports, use the maintained
`reviewed_tabular_accounting_v1` adapter with an explicit reviewed `tabular`
layout. Read `../../references/tabular-source-layout.md` before qualifying these
files. professional reviews the actual headers, table bounds, source role, evidence
meaning and perimeter; the parser does not infer them. It supports open-item,
bank and journal tables, preserves source rows and critical dates, reads native
Excel monetary values from exact XML numbers, and rejects mapped formulas,
invalid dates/amounts, ambiguous headers and perimeter contradictions. Do not
convert a normal export to a special PDF layout merely to fit a legacy parser.
Create/replay the source-bound decision through the same maintained intake;
never fabricate prepared records or ask the professional to author JSON.

Every `reviewer_ref` is an unsigned, unauthenticated, untrusted label. Its
canonical syntax and sealed bytes do not prove the reviewer's identity or
authorization.
For new plain mappings, intake supplies the run date and a valid technical
reviewer label when omitted or syntactically invalid. These are bookkeeping
metadata, not user decisions. Previously sealed receipts retain strict replay.

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
- `artifact_card.md` as an optional navigation card for every normal
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

1. Call `studio_archive_status` and select one exact registered client and
   engagement. Validate that selected identity and its inputs. A changed
   top-level folder or stale search index does not require a refresh before
   this work; refresh is needed only for a requested content search.
2. Import the reviewed sources into that engagement, then call
   `prepare_studio_client_workflow` with workflow ID `open-item-reconciliation`.
   Pass its returned `client_engagement_path` unchanged as
   `--client-engagement` to `raw_input_runner.py`.
3. Start that run before executing the helper. The portable context fixes the
   execution inputs as `Vera/engagements/<engagement-id>/runs/<run-id>/inputs`
   and the only permitted output path as the sibling `outputs` directory in
   the selected customer folder. Never substitute a freely chosen directory.
   When the host also requires run-level disclosure artifacts, pass
   `--output-subdirectory reconciliation` for a new run and every regeneration.
   This uses only the fixed `outputs/reconciliation/` child for the exact native
   assurance package; retain disclosures in the owning `outputs/` directory.
   Open review and validate assurance against the returned native output path.
   Declare every file in both locations when finalizing the owning archive run.
4. Stop when the context, input receipt, execution copy, lifecycle, or customer
   manifest is stale or edited. Do not copy, merge, or relabel another
   customer's files to make validation pass.

Exact one-to-one bank matches are automatically verified when invoice identity,
party, entity, currency, dates, exact cents and unique allocation all agree with
the source records. Complete literal invoice references in descriptions are
resolved before semantic fallback; the latter receives only unresolved rows.
Automatic review is rederived from the same sealed sources and explicitly does
not imply human or professional approval. Other completed review rows must come
from the current run's applied review decisions.
Regenerate with those exact rows and the externally retained predecessor
checkpoint. A `PASS` row copied from an earlier run is not authority for replacement
sources, even when the invoice record ID is unchanged. Import replacement evidence
as a new controlled input and review the resulting run again; retain the earlier
source and result separately. For an explicitly requested replacement, include the
prior run ID, old and new input IDs, and the reason for re-review in the new run
`purpose`; Studio Archive preserves and exposes that sealed purpose with its input
manifest. Do not infer replacement relationships from filenames alone.

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

Load `../../references/starter-prompts.md` for beta-facing prompt examples. Keep this `SKILL.md` focused on routing, guardrails, first-run flow, dependency checks, deterministic workflow ownership, feedback, and packaging.

## Evidence Standards, Data, And Checks

Load `../../references/evidence-and-checks.md` when deciding evidence strength, canonical fields, source roles, or deterministic accounting checks.

Load `../../references/workflow-reference.md` for the exact source-decision contract,
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

The raw runner interprets CSV/XLSX only through an explicitly reviewed bounded
tabular layout, or another qualified maintained adapter. It does not infer
arbitrary spreadsheet structure. Unsupported layouts require a qualified
adapter or reviewed external preparation; do not coerce them through a
similar-looking parser.

When extracting long PDFs, enable `verbose_extraction` and set
`pdf_progress_every_pages` when the default cadence is too sparse. The runner
emits file-start, page-progress, OCR page, cache-hit, and file-done progress
messages so the reviewer can see which PDF is consuming time.

For generic runs, pass `scope_year` and `cutoff_date` through assumptions when the work is period-specific. Do not rely on a hidden default year.

Useful helper scripts include:

- `scripts/raw_input_runner.py`: client-bound input-folder orchestration; its
  CLI requires the exact Studio Archive `--client-engagement` context and
  `--assumptions-json`. Save this agent-generated configuration in the selected
  run's output directory before invoking the helper; a chat-workspace file is
  outside that run and is not an imported client source;
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

## Semantic resolution of unresolved items

The maintained raw runner automatically submits unresolved items and unused bank
evidence to bounded semantic workers after source mapping. The shared host policy
selects a suitable low-cost model from actual harness capabilities. Keep the main
chat's model; do not create visible per-case chats or ask the user to select routine
technical mappings. In Cowork or Antigravity, complete `NATIVE_WORKER_PENDING`
using `../../../journal-bank-reconciliation/skills/mparanza-journal-bank-reconciliation/references/native-host-workers.md`,
then resume the same command and deliver the regenerated result. Missing actual
host capabilities remain explicit; do not ask the user to perform the handoff.

Models interpret references, descriptions, counterparties and competing matches.
The engine verifies quoted evidence, exact amounts, accounting perimeters and no
cash reuse, then writes supported allocations and residuals into native results,
workbooks and assurance ledgers. Partial, cumulative and excess payments retain
exact open or unapplied balances. Equal amounts alone cannot close an item.
Ambiguity, contradictory evidence and missing evidence stay visible.

Inspect the returned `semantic_resolution` status and any blocks. The retained
worker packets, launch evidence and decisions are bound to the prepared population
and replayed during review/regeneration; do not edit the original source data to
make a match. No worker output constitutes professional adoption or approval.
The full packet remains local except for the selected host model submission;
its populated mapped fields include business document identifiers, descriptions,
parties, dates, amounts and opaque linkage IDs. It is not anonymized. Paths and
unmapped columns are excluded. In Claude the main chat receives status and counts.
In Cowork and Antigravity the parent reads the bounded request to dispatch its
native child, so those mapped fields enter both contexts; host transcripts may persist. A complete currency/entity perimeter is never silently
truncated to fit a worker; an oversized perimeter is explicitly deferred.

## Review, Outputs, Locales, And Wording

Load `../../references/review-and-outputs.md` when producing workpapers, reviewing deterministic classifications, or preparing operational follow-up requests.

Load `../../references/locales-and-wording.md` when choosing language settings or writing localized evidence requests.

Before delivery, Claude must review the deterministic output, preserve limitations, and avoid exposing internal status/rule labels in client-facing requests.

## Packaging

After changing this plugin source, use the repo-local `plugin-release` workflow:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py open-item-reconciliation
.venv/bin/python scripts/build_codex_plugin_zip.py open-item-reconciliation --check
.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py
```

Do not patch the downloadable ZIP manually.

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published, hash-checked dependency locks, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

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

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

---
name: audit-reconciliation
description: Use when a user wants Codex to reconcile accounting evidence across open-item lists, ledgers, journals, bank statements, payment orders, factoring or advance evidence, and compensation evidence, then produce audit-ready Excel and Word workpapers with deterministic classifications and a documented Codex review layer. This is a Codex workflow plugin, not a standalone CLI.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Audit Reconciliation

Use this skill for evidence-based accounting reconciliation. Typical work includes open-item disputes, invoice-level reconciliation, bank/ledger reconciliation, payment-batch checks, factoring or advance checks, compensation/netting support, and audit workpapers.

The plugin is a **Codex workflow plugin**. Helper scripts are deterministic support code; Codex remains responsible for inspecting the folder, asking for missing assumptions, running the workflow, reviewing the output, and explaining limitations.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Codex-native UI artifacts as part of the workflow, not as optional
narration. At minimum:

1. Start with a visible markdown run checklist. Track intake, dependency check,
   inspection, user decisions, deterministic run, Codex review, and delivery.
2. Before helper scripts, show a Run Intake table with input paths, output
   folder, working language, document language, assumptions, and notification
   choice when the skill supports user run notifications.
3. After inspection, show a compact Decision Table for missing mappings,
   filters, review choices, unsupported files, or evidence assumptions. Ask
   only unresolved decisions and update the working recipe or assumptions
   yourself.
4. Before a long-running or write-heavy step, show an execution checkpoint or
   approval checkpoint with command intent, inputs, output folder, and expected
   artifacts. Ask for approval only when the step is external, destructive,
   approval-sensitive, or still depends on an unresolved material choice.
5. During execution, update checklist statuses as steps complete.
6. End with an Artifact Card listing output path, purpose, review status,
   unresolved items, and next action. When useful, create `codex_run_review.md`
   in the output folder from generated JSON/CSV/Markdown outputs; never edit
   plugin source or generated ZIPs during a run.

## Beta Positioning

Present the plugin as one vertical professional workflow:

```text
Reconcile open items, ledgers, bank evidence, payment batches,
factoring/advance support, and compensations into reviewable Excel/Word
workpapers.
```

Do not present it as a generic accounting chatbot, a standalone app, or an MCP/API service. The user experience should feel like a guided Codex run: inspect the folder, confirm assumptions, run deterministic helpers, review exceptions, and deliver workpapers with clear limitations.

## Source Rule

For development, the repo source is the only editable source:

```text
plugins/audit-reconciliation
```

Do not edit downloaded plugin folders, ZIP contents, or Codex cache copies as source.

## Core Principle

Deterministic code is the authority for row-level classifications.

Codex/model review is a quality-control layer. It may find issues, identify missed patterns, or propose rule changes, but it must not silently override deterministic results. If review finds a material error, fix the deterministic rule, rerun, and regenerate outputs.

## Required Questions

Ask only what is needed. If not obvious, ask for:

- input folder;
- year or cut-off date;
- working language and source-document language;
- which file is the disputed/open-item population, if any;
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
- `source_pages.json`;
- `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
  `final_artifacts.json` for browser/widget review handoff;
- `artifact_card.md` as the mandatory visible handoff card for every normal
  run;
- `review_ui.html` as a standalone local fallback when the local browser server
  cannot start or the browser cannot be opened;
- Codex review rows in the workbook;
- targeted missing-evidence requests when the user needs an operational follow-up pack.

## Browser Review UI And MCP Widget

The primary review handoff is a local browser page backed by
`scripts/review_server.py`. After a run writes
`run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
`final_artifacts.json`, Codex must create and surface `artifact_card.md`, then
open the local browser review server before final delivery. This is a
completion gate for normal runs, not optional narration, and Codex must not ask
whether to open the review surface.

Required handoff sequence:

1. Read `artifact_card.md` and `final_artifacts.json` from the output folder.
2. Start the browser review server from the plugin directory:
   `python scripts/review_server.py <output-folder>`.
3. The server opens the system browser by default on `127.0.0.1`; tell the
   reviewer the exact localhost URL and the `artifact_card.md` path in chat.
4. Use the browser page to save/apply accepted, edited, rejected, unclear, or
   requested-document decisions. The local server persists `ui_decisions.json`,
   `applied_decisions.json`, and updated `final_artifacts.json`.
5. Only after the browser surface is opened and the handoff is explicit should
   Codex report the workpapers and explain review status to the user.

The MCP validate/render tools remain useful as an optional integrated Codex
surface. Load them with `tool_search` when needed, call
`validate_audit_reconciliation_review`, then
`render_audit_reconciliation_review`. When decisions are collected, call
`save_audit_reconciliation_decisions` to persist `ui_decisions.json`, then
`apply_audit_reconciliation_decisions` to write `applied_decisions.json` and
update `final_artifacts.json`. MCP render is no longer the primary normal-run
handoff when the browser review server is available.

For large runs, pass local output paths to MCP instead of inlining large JSON
objects: `run_intake_path`, `review_payload_path`, `ui_decisions_path`, and
`final_artifacts_path`. The MCP server reads those JSON files from the run
output folder, validates them, and rejects path combinations outside that run
folder.

Do not treat `review_ui.html`, Markdown summaries, file links, or `file://`
URLs as equivalent to the browser review server. Use `review_ui.html` only when
the local server cannot start or the browser cannot be opened; the static file
can show/copy/download JSON but cannot persist decisions by itself. If both the
server and static HTML are unavailable, fall back to a markdown review summary
from `review_payload.json`, the workbook review sheet, and
`codex_review_packet.json`. Do not build a separate ad hoc HTML page for
one-off setup choices; use chat or, when this conversation is in Plan mode and
the tool is available, native Plan-mode choices for small intake decisions.

## Starter Prompt Bank

Load `references/starter-prompts.md` for beta-facing prompt examples. Keep this `SKILL.md` focused on routing, guardrails, first-run flow, dependency checks, deterministic workflow ownership, feedback, and packaging.

## Evidence Standards, Data, And Checks

Load `references/evidence-and-checks.md` when deciding evidence strength, canonical fields, source roles, or deterministic accounting checks.

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

1. inventory source files;
2. extract PDF, Excel, CSV, ZIP/payment-order content where possible;
3. normalize rows to canonical fields;
4. classify open/disputed rows against evidence;
5. produce row-level output with status, rule, evidence type, source reference, and missing-evidence request;
6. produce diagnostic outputs: normalized records, checks, review packet, external evidence summary, bank allocation candidates, and ledger/journal controls where available;
7. produce deterministic roll-forward and post-cut-off candidate checks where the source data supports them.

When extracting long PDFs, enable `verbose_extraction` and set
`pdf_progress_every_pages` when the default cadence is too sparse. The runner
emits file-start, page-progress, OCR page, cache-hit, and file-done progress
messages so the reviewer can see which PDF is consuming time.

For generic runs, pass `scope_year` and `cutoff_date` through assumptions when the work is period-specific. Do not rely on a hidden default year.

Useful helper scripts include:

- `scripts/raw_input_runner.py`: input-folder orchestration where available;
- `scripts/reconciliation_helpers.py`: normalization, matching helpers, evidence typing, and diagnostics;
- `scripts/workpaper_outputs.py`: workbook and report creation helpers;
- `scripts/build_review_sample.py`: post-run selection of a small reviewer-friendly sample, with Italian operational wording and a Markdown request draft.
- `scripts/build_missing_evidence_requests.py`: post-run workbook of targeted missing-evidence requests that distinguishes evidence already acquired from the exact missing item per row, using localized operational labels instead of internal status/rule codes.

## Review, Outputs, Locales, And Wording

Load `references/review-and-outputs.md` when producing workpapers, reviewing deterministic classifications, or preparing operational follow-up requests.

Load `references/locales-and-wording.md` when choosing language settings or writing localized evidence requests.

Before delivery, Codex must review the deterministic output, preserve limitations, and avoid exposing internal status/rule labels in client-facing requests.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the
deliverables, briefly identify concrete improvements that would have made this
plugin run better. Base suggestions on the actual session, such as missing
inputs, brittle extraction, unclear assumptions, output gaps, installation
friction, or repeated manual steps.

Keep the improvement note local to chat or run artifacts.

## Packaging

After changing this plugin source, use the repo-local `plugin-release` workflow:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py audit-reconciliation
.venv/bin/python scripts/build_codex_plugin_zip.py audit-reconciliation --check
.venv/bin/python -m pytest tests/plugins/test_codex_plugin_packages.py
```

Do not patch the downloadable ZIP manually.

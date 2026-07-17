---
name: check-entries
description: Use when a user wants Codex to compare selected journal entries with supporting PDF documents, map entry columns, run deterministic amount/date/beneficiary checks, and produce reviewable CSV/XLSX/JSON outputs. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Check Entries

Use this skill when sampled journal entries must be checked against supporting
documents. The plugin is a guided Codex workflow: Codex inspects the journal
and FatturaPA XML/PDF support, asks only for unresolved mapping or review
assumptions, runs deterministic helper scripts, reviews diagnostics, and
delivers outputs.

The workflow is not Italian-only. Support the same four working locales used by the reconciliation plugin: `it`, `en`, `fr`, and `de`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

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

## Core Principle

Deterministic Python code owns journal parsing, PDF text extraction, support matching, amount/date/beneficiary comparisons, and exports. Codex may inspect files, propose mappings, explain assumptions, and review unresolved items, but the plugin scripts must not make direct OpenAI API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- a journal/sample-entry file in `.xlsx`, `.xls`, or `.csv` format;
- one support source: a FatturaPA ZIP/XML, a local export produced by an
  authorized accounting-system connector, or a supporting PDF file/folder.

Optional:

- mapping hints for movement number, date, amount/debit/credit, description, and expected beneficiary;
- amount tolerance;
- date window in days;
- working language and source-document language.

Text-PDF journals are not a v1 target for this plugin. If the source entries only exist in a PDF journal, run the Journal Sampling plugin first to normalize the journal, then run Check Entries on the normalized CSV/XLSX and support PDFs.

## First Run Workflow

1. Apply this acquisition ladder: ask first for the ZIP containing all relevant
   FatturaPA XMLs; if unavailable, offer an authorized accounting-system
   connection that materializes a local ZIP/folder export; otherwise request
   PDFs only for unresolved sampled entries. Never request credentials, tokens,
   cookies, or one-time codes. Ask for working language, source-document
   language, and mapping hints only when not inferable.
   When the user chooses connection, use a callable provider-specific connector
   only after confirming the studio/client has authorized access. Restrict the
   connector action to read/export for the selected client and period, record
   the connector name, and pass its local ZIP/folder result to Check Entries.
   If no connector for the named accounting system is callable, say so rather
   than simulating a connection; ask which provider must be integrated or move
   to the targeted-PDF fallback at the user's direction.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

3. Run inspection to produce `inspection.json` and `suggested_recipe.json`:

```bash
python scripts/inspect_entries.py <journal-file> <support-zip-xml-or-folder> --output-dir <output-dir> --language <it|en|fr|de> --document-language <auto|it|en|fr|de>
```

4. Read `inspection.json` and `suggested_recipe.json`. If required mappings are missing or confidence is low, ask the user the smallest needed decision, such as which column is movement number, debit, credit, amount, date, or beneficiary.
5. If a mapping decision is needed, edit `suggested_recipe.json` in the work folder, not plugin source.
6. Run deterministic checks:

```bash
python scripts/run_checks.py <journal-file> <support-zip-xml-or-folder> --output-dir <output-dir>/checks --recipe <output-dir>/suggested_recipe.json --language <it|en|fr|de> --document-language <auto|it|en|fr|de>
```

7. Review `check_audit.json`, `pdf_inventory.json`, `check_results.csv`, and `review_notes.md` before final delivery. Report support matching coverage, status counts, unresolved/manual-review rows, mismatches, and output paths.

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use:

- `journal.header_rows`: 1-indexed header rows for tabular files;
- `journal.mapping.movement_number`: entry or registration number used to match support PDFs;
- `journal.mapping.date`: expected entry/document date;
- `journal.mapping.amount`: signed amount column, when one exists;
- `journal.mapping.debit_amount` and `journal.mapping.credit_amount`: debit/credit columns, when signed amount is not present;
- `journal.mapping.description`: optional line description;
- `journal.mapping.beneficiary`: optional expected counterparty/payee/beneficiary.

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

## Deterministic Check Rules

- Support matching uses movement number in PDF filenames first, then movement number in extracted PDF text.
- FatturaPA matching precedes PDF matching and requires exactly one candidate
  supported by at least two independent fields among invoice number, amount,
  date, and beneficiary/party. This is deterministic because parsing and exact
  comparisons are mechanically verifiable; ambiguous semantic relevance stays
  with Codex and the professional reviewer.
- An authorized connector is an acquisition mechanism, not a matching rule.
  Record the connector name with `--connector-name` after it has produced a
  local export; the helper scripts do not authenticate or call provider APIs.
- If there is exactly one entry and one PDF, the script may match them directly.
- Amount checks compare absolute values with the configured tolerance.
- Date checks compare extracted dates within the configured day window.
- Beneficiary checks are deterministic token containment checks when an expected beneficiary column is mapped.
- Rows with missing support are `missing_support`.
- Rows with available checks and no mismatch are `ok`.
- Rows with deterministic mismatches are `mismatch`.
- Rows with no amount/date/beneficiary fields are `manual_review`.

Codex may inspect individual support PDFs and explain the review outcome, but should keep any judgment explicit in the final response rather than silently changing script outputs.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `checks/normalized_entries.csv`;
- `checks/pdf_inventory.json`;
- `checks/invoice_inventory.json`;
- `checks/check_results.csv`;
- `checks/check_results.xlsx` when XLSX dependencies are available;
- `checks/check_audit.json`;
- `checks/review_notes.md`;
- `checks/run_intake.json`;
- `checks/review_payload.json`;
- `checks/ui_decisions.json`;
- `checks/applied_decisions.json` after reviewer decisions are applied;
- `checks/final_artifacts.json`.

## MCP Review Handoff

After `scripts/run_checks.py` completes, read `checks/run_intake.json` and
`checks/review_payload.json`. Treat the review payload as the structured
contract for reviewer-facing UI: supported rows, missing support, mismatches,
manual-review rows, PDF extraction diagnostics, mapping issues, and generated
artifacts.

When the `checkEntriesWidgets` MCP server is available, call
`validate_check_entries_review` with the complete `review_payload.json` object.
If validation passes, call `render_check_entries_review` with the same payload
and optional `run_intake`, `ui_decisions`, and `final_artifacts` objects. When
the reviewer records actions in the widget or Codex collects decisions through
fallback review, call `save_check_entries_decisions` with `run_intake`,
`review_payload`, current `ui_decisions`, and the decision list so
`ui_decisions.json` is validated and persisted. When the reviewer is done, call
`apply_check_entries_decisions` with the same review payload, current
`final_artifacts`, and decision list so `applied_decisions.json` and
`final_artifacts.json` reflect the accepted, edited, unclear, skipped, or
document-requested items. Do not hand-build another HTML page for the same
review.

If MCP rendering is unavailable, continue by reading `review_payload.json` and
reviewing through Markdown/chat. Keep `ui_decisions.json` pending unless a
review step records decisions.

The UI handoff follows the OpenAI-style local MCP/widget pattern:

1. Python writes bounded review-session JSON files in the output folder.
2. The local MCP server validates the review payload schema and item types.
3. The MCP render tool returns `openai/outputTemplate` metadata for
   `ui://widget/check-entries-review.html`.
4. The reusable HTML widget renders summary metrics, type filters, search,
   rows, evidence detail, and reviewer action controls.
5. The MCP save tool validates actions against each item and writes durable
   `ui_decisions.json` when `run_intake.output_dir` is available.
6. The MCP apply tool writes `applied_decisions.json` and updates
   `final_artifacts.json` status when `run_intake.output_dir` is available.
7. Codex uses the reviewed payload and any durable decisions when writing the
   final response or `codex_run_review.md`.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, or German, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Check Entries sulla registrazione campione /percorso/entries.xlsx e sui PDF in /percorso/pdf. Lingua: it. Lingua documenti: auto. Ispeziona colonne e PDF, chiedimi solo le ambiguità essenziali e genera risultati, diagnostiche e audit trail.
EN: Use Check Entries on /path/entries.xlsx and support PDFs in /path/pdfs. Language: en. Document language: auto. Inspect columns and PDFs, ask only for essential ambiguities, then generate results, diagnostics, and audit trail.
FR: Utilise Check Entries sur /chemin/entries.xlsx et les PDF dans /chemin/pdfs. Langue: fr. Langue des documents: auto. Inspecte les colonnes et les PDF, demande uniquement les ambiguïtés essentielles, puis génère les résultats, diagnostics et l'audit trail.
DE: Verwende Check Entries für /pfad/entries.xlsx und die Beleg-PDFs in /pfad/pdfs. Sprache: de. Dokumentsprache: auto. Prüfe Spalten und PDFs, frage nur wesentliche Unklarheiten ab und erstelle Ergebnisse, Diagnostik und Audit-Trail.
```

## Failure Modes

- If support PDFs are scanned/OCR-only and no text is extracted, report that deterministic PDF text extraction is insufficient and list the affected files.
- If the movement-number mapping is missing, ask the user which column identifies each entry/support document.
- If amount mapping is missing, run inspection but ask before treating the output as a completed check.
- If a deterministic rule flags many false positives, write the gap as a plugin improvement suggestion rather than overriding the output silently.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new support-document format, a brittle PDF text extractor, a missing deterministic extraction script, a missing column-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.

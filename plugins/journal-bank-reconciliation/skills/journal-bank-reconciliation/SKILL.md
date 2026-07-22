---
name: journal-bank-reconciliation
description: Use when a user wants Codex to reconcile bank statements with journal or ledger exports, map variable customer formats, run deterministic amount/date/reference/beneficiary matching, and produce reviewable CSV/XLSX/JSON outputs. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Journal-Bank Reconciliation

Use this skill when bank statement movements must be reconciled to accounting journal or ledger rows. The plugin is a guided Codex workflow: Codex inspects the files, asks only for unresolved mapping or review assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the other accounting plugins: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, reconciliation-stage, and review-status notes live in `references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

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

Deterministic Python code owns extraction, normalization, optional sample filtering, matching, and exports. Codex may inspect files, propose recipes, explain assumptions, and review unresolved items, but the plugin scripts must not make direct OpenAI API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- a bank statement file or folder in `.xlsx`, `.xls`, `.csv`, or text `.pdf` format;
- a journal or ledger file or folder in `.xlsx`, `.xls`, `.csv`, or text `.pdf` format.

Optional:

- a sample movement file to restrict the journal/ledger side;
- mapping hints for date, signed amount or debit/credit, description, beneficiary, reference, movement number, and account;
- amount tolerance;
- date window in days;
- working language and source-document language.

OCR-only scanned PDFs are not a v1 target. If inspection returns no rows for a scanned file, explain that deterministic text extraction is insufficient and list the affected files.

## First Run Workflow

1. Ask for the bank file/folder, journal or ledger file/folder, sample file when the user wants to restrict the population, working language, source-document language, and any known mapping hints only if they are not already provided or inferable. Do not ask for output richness. Use the script defaults for amount tolerance and date window unless the user provides stricter thresholds or the data requires a different assumption.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

3. Run inspection to produce `inspection.json` and `suggested_recipe.json`:

```bash
python scripts/inspect_inputs.py <bank-file-or-folder> <journal-file-or-folder> --output-dir <output-dir> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Add `--sample <sample-file>` when a sample movement list is provided.

4. Read `inspection.json` and `suggested_recipe.json`. If required mappings are missing or confidence is low, ask the user the smallest needed decision, such as which row is the header, which column is amount, or whether the journal uses debit/credit columns.
5. If a mapping decision is needed, edit `suggested_recipe.json` in the work folder, not plugin source.
6. Run deterministic reconciliation:

```bash
python scripts/run_reconciliation.py <bank-file-or-folder> <journal-file-or-folder> --output-dir <output-dir>/reconciliation --recipe <output-dir>/suggested_recipe.json --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Use `--tolerance <amount>` and `--date-window-days <days>` when the user provides explicit thresholds.

7. Review `reconciliation_audit.json`, `reconciliation_matches.csv`, `unmatched_bank.csv`, `unmatched_journal.csv`, and `review_notes.md` before final delivery. Report matched count, unmatched bank count, unmatched journal count, stage counts, unresolved/manual-review issues, and output paths.

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use per-side recipe sections:

- `bank.files.<filename>.header_rows`: 1-indexed header rows for tabular bank files;
- `journal.files.<filename>.header_rows`: 1-indexed header rows for tabular journal/ledger files;
- `mapping.date`: transaction date;
- `mapping.amount`: signed amount column, when one exists;
- `mapping.debit` and `mapping.credit`: debit/credit columns, when signed amount is not present;
- `mapping.description`: movement or line description;
- `mapping.beneficiary`: counterparty/payee/beneficiary;
- `mapping.reference`: reference, document number, CRO, TRN, IBAN, or invoice reference;
- `mapping.movement_number`: journal movement/registration number;
- `mapping.account`: account identifier.

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

## Deterministic Matching Rules

- Candidate rows must be within amount tolerance using absolute amounts.
- Date checks use the configured date window when dates are available.
- Matching stages run in this order: `reference`, `amount_date_unique`, `beneficiary`, `description_tokens`, `amount_date_single`.
- Rows are not reused after a match is accepted.
- Sample movement files restrict only the journal/ledger side.
- Ambiguous candidates remain unmatched rather than being forced by model judgment.

Codex may inspect individual rows and explain unresolved items, but should keep review judgment explicit in the final response rather than silently changing script outputs.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `reconciliation/normalized_bank.csv`;
- `reconciliation/normalized_journal.csv`;
- `reconciliation/reconciliation_matches.csv`;
- `reconciliation/unmatched_bank.csv`;
- `reconciliation/unmatched_journal.csv`;
- `reconciliation/bank_pdf_non_movement_rows.csv`;
- `reconciliation/journal_bank_reconciliation.xlsx`;
- `reconciliation/reconciliation_audit.json`;
- `reconciliation/review_notes.md`;
- `reconciliation/run_intake.json`;
- `reconciliation/review_payload.json`;
- `reconciliation/ui_decisions.json`;
- `reconciliation/applied_decisions.json` after reviewer decisions are applied;
- `reconciliation/final_artifacts.json`.

## MCP Review UI

When the local MCP server is available, prefer the OpenAI-style review handoff:

1. Read `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` from the reconciliation output folder.
2. Call `validate_journal_bank_review` with `review_payload` before rendering.
3. If validation succeeds, call `render_journal_bank_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/journal-bank-review.html`.
4. Use the widget to inspect unmatched bank rows, unmatched journal rows,
   matched-pair evidence, diagnostics, and generated workbook/CSV/JSON outputs.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_journal_bank_decisions` so
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_journal_bank_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items before treating the review as complete.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `reconciliation_audit.json`, `review_notes.md`, and the
CSV/XLSX outputs. Do not promote ambiguous rows to matched by judgment alone;
change deterministic rules and rerun when a systematic correction is needed.
Keep review decisions pending unless they are recorded in `ui_decisions.json`
and consumed into `applied_decisions.json`. Small setup choices should stay in
chat or, when this conversation is in Plan mode and the tool is available,
native Plan-mode choices.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Journal-Bank Reconciliation sugli estratti banca in /percorso/banca e sul giornale in /percorso/giornale.xlsx. Lingua: it. Lingua documenti: auto. Ispeziona colonne e file, chiedimi solo le ambiguità essenziali e genera riconciliazione, diagnostiche e audit trail.
EN: Use Journal-Bank Reconciliation on bank statements in /path/bank and journal file /path/journal.xlsx. Language: en. Document language: auto. Inspect columns and files, ask only for essential ambiguities, then generate reconciliation, diagnostics, and audit trail.
FR: Utilise Journal-Bank Reconciliation sur les relevés bancaires dans /chemin/banque et le journal /chemin/journal.xlsx. Langue: fr. Langue des documents: auto. Inspecte les colonnes et les fichiers, demande uniquement les ambiguïtés essentielles, puis génère le rapprochement, les diagnostics et l'audit trail.
DE: Verwende Journal-Bank Reconciliation für Kontoauszüge in /pfad/bank und Journaldatei /pfad/journal.xlsx. Sprache: de. Dokumentsprache: auto. Prüfe Spalten und Dateien, frage nur wesentliche Unklarheiten ab und erstelle Abstimmung, Diagnostik und Audit-Trail.
```

## Failure Modes

- If PDFs are scanned/OCR-only and no text is extracted, report that deterministic PDF text extraction is insufficient and list affected files.
- If amount mapping is missing, run inspection but ask before treating the output as completed reconciliation.
- If dates are missing on one side, explain that matching will rely more heavily on amount/reference/description evidence.
- If deterministic rules create too many unmatched or ambiguous rows, write the gap as a plugin improvement suggestion rather than overriding the output silently.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new bank export format, a brittle PDF text extractor, a missing deterministic extraction script, a missing column-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.

---
name: report-builder
description: Use when a user wants Codex to inspect financial Excel/CSV/text-PDF inputs, map tables to report sections, write or refine the report narrative in Codex, and produce reviewable Markdown/DOCX/JSON outputs. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Build Report

Use this skill when a finance or audit report must be assembled from variable workbooks, CSV exports, readable PDFs, or ZIP folders. The plugin is a guided Codex workflow: Codex inspects the files, proposes table-to-section mapping, asks only for unresolved business choices, writes or refines narrative comments in an editable recipe, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the other accounting plugins: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output file names and JSON keys in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed input, mapping, narrative-boundary, and rendering notes live in `references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Numeric-measure currency must not be defaulted silently. Establish currency
from explicit source evidence, engagement context, or the user's answer and
record it in the reviewed numeric contract. If currency remains unresolved,
keep the candidate measure pending instead of emitting its total.

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

Deterministic Python code owns stable source-byte capture, source receipts, Excel/CSV/PDF text extraction, table inventory, section assignment suggestions, exact numeric diagnostics, source-to-prepared-to-rendered numeric replay, Markdown/DOCX rendering, and audit outputs. Codex owns judgment: interpreting ambiguous tables, deciding report structure with the user, writing the narrative, and reviewing the draft.

The plugin scripts must not make direct OpenAI API calls. The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- a report input file, folder, or ZIP containing `.xlsx`, `.xlsm`, `.csv`, or readable text `.pdf` files.

Optional:

- target report type: `management_report`, `local_government_review`, or `annual_financial_statement`;
- working language and source-document language;
- entity name, reporting period, and any context notes;
- mapping hints for table-to-section assignment;
- draft comments or conclusions the user wants included.

OCR-only scanned PDFs are not a v1 target. If inspection returns no rows for a scanned file, explain that deterministic text extraction is insufficient and list the affected files.

## First Run Workflow

1. Ask for the input file/folder/ZIP, report type, working language, source-document language, entity, period, and any context notes only when they are not already provided or inferable. If report type is not inferable, default to `management_report`. Do not ask whether to generate Markdown, DOCX, audit, diagnostics, or table packages; they are normal outputs.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

3. Run deterministic inspection to produce `inspection.json` and `suggested_recipe.json`:

```bash
python scripts/inspect_inputs.py <input-file-or-folder> --output-dir <output-dir> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es> --report-type <management_report|local_government_review|annual_financial_statement>
```

4. Read `inspection.json` and `suggested_recipe.json`. Summarize discovered tables, suggested section matches, low-confidence or unassigned tables, and extraction limitations.
5. Ask the smallest needed decision if mapping is ambiguous, such as which table belongs to cash flow, whether a PDF text block should become a section, or whether an unassigned sheet should be excluded.
6. Edit `suggested_recipe.json` in the work folder, not plugin source. Fill
   `entity`, `period`, `context_items`, `executive_summary`, each section's
   `assigned_table`, and section `codex_comment` values as appropriate. Codex
   can write the narrative directly in the recipe after confirming facts with
   the user. For the current output-closure contract, free-form entity,
   context keys and values, executive-summary, section-title, and
   section-comment text must contain no numerals; all report-value numerals
   come from reviewed measures. Use a digit-free entity display name. Periods
   may use `YYYY`, `FYYYYY`, `Qn YYYY`, an ISO date,
   `Year|Period|Quarter ended YYYY-MM-DD`, or an ISO-date `to|through` range.
7. Treat every numeric-looking column as a candidate, not a measure. For each
   column whose total should appear, confirm its business meaning from the
   source and record the source-bound review with the helper. Do not select
   account codes, invoice numbers, vendor IDs, years, or other identifiers just
   because they parse as numbers:

```bash
python scripts/review_numeric_measures.py \
  --inspection <output-dir>/inspection.json \
  --recipe <output-dir>/suggested_recipe.json \
  --output <output-dir>/reviewed_recipe.json \
  --section <section-key> \
  --header-row <detected-one-based-row|none> \
  --columns <included-column[,included-column]|none> \
  --exclude-columns <excluded-candidate[,excluded-candidate]|none> \
  --cell-disposition <column:row:include|exclude> \
  --reviewer-ref <canonical-reviewer-ref> \
  --reviewed-on <YYYY-MM-DD> \
  --numeric-locale <it|en|fr|de|es> \
  --currency <ISO-4217-code|none> \
  --unit <currency|number|count|ratio|percentage> \
  --scale <positive-canonical-decimal> \
  --parse-policy strict_all_nonblank_v1 \
  --sign-policy <as_presented_v1|invert_v1>
```

   Choose `--header-row` from `header_review_options.supported_choices` in
   `inspection.json`; use the detected one-based row only after review, or
   `none` when the source is headerless. Repeat against the updated recipe when
   more than one section has reviewed measures. Every numeric candidate column
   under the chosen header interpretation must be included or excluded, and
   every nonblank cell in an included column needs one repeated
   `--cell-disposition`. This permits explicit subtotal exclusions and a valid
   all-excluded result. Formula cells stay excluded unless a future adapter can
   prove both recalculation and exported cache identity. The helper fails
   closed on formulas, missing dispositions, unresolved syntax, mixed
   currencies, a unit/format conflict, or a report-period change after review.
   Without a valid source-and-period-bound review receipt, the build omits
   numeric totals and the numeric evidence ledger.
8. Run deterministic build:

```bash
python scripts/build_report.py <input-file-or-folder> --output-dir <output-dir>/report --recipe <output-dir>/reviewed_recipe.json --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es> --report-type <management_report|local_government_review|annual_financial_statement>
```

9. Review `report_analysis.json`, `report_audit.json`, `report_draft.md`, and the styled `report.docx` before final delivery. Report assigned sections, missing sections, pending numeric-measure reviews, tables discovered, narrative sections filled by Codex, and output paths.

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use these fields:

- `language`: working/output language for Codex;
- `document_language`: source-document language assumption;
- `report_type`: one of the supported report templates;
- `entity`: entity or client name;
- `period`: reporting period;
- `executive_summary`: Codex-written summary, reviewed against available tables;
- `context_items`: key/value notes from the user or source folder;
- `sections.<section>.title`: display title;
- `sections.<section>.assigned_table`: table id from `inspection.json`;
- `sections.<section>.codex_comment`: Codex-written narrative for that section;
- `sections.<section>.numeric_measure_columns`: exact column names explicitly
  reviewed as financial or operational measures;
- `sections.<section>.excluded_numeric_candidate_columns`: every other numeric
  candidate explicitly excluded by the reviewer;
- `sections.<section>.numeric_measure_decision`: reviewed-decision receipt bound
  to the exact report period, source artifact, table, header row, and selected
  columns;
- `render.include_table_previews`: whether deterministic table previews appear in the draft.

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `report/report_tables.json`;
- `report/report_tables.xlsx`;
- `report/report_analysis.json`;
- `report/report_draft.md`;
- `report/report.docx` with styled headings, metadata tables, section tables, and audit appendix;
- `report/report_audit.json`;
- `report/source_receipts.json` when reviewed numeric measures exist;
- `report/numeric_evidence_ledger.json` with exact source, prepared, and
  rendered values when reviewed numeric measures exist;
- `report/used_recipe.json`;
- `report/run_intake.json`;
- `report/review_payload.json`;
- `report/ui_decisions.json`;
- `report/applied_decisions.json` after reviewer decisions are applied;
- `report/final_artifacts.json`.

The run also keeps `report/source_index.json` and
`report/review_integrity.json` as private control state. Do not present either
as a deliverable. Absolute source roots occur only in the private source index.
Raw extracted ZIP members and `revisions/` backups also remain outside the
`final_artifacts.json` gallery.

## MCP Report Review UI

Use MCP/HTML for the generated report package review. Do not build HTML for
simple intake, report-type choice, section mapping, or a 2-3 option business
decision; those remain chat choices in Default mode and native Plan-mode
choices when this conversation is in Plan mode and `request_user_input` is
available.

When the local MCP server is available after `build_report.py`:

1. Read `report/run_intake.json`, `report/review_payload.json`,
   `report/ui_decisions.json`, and `report/final_artifacts.json`.
2. Call `validate_report_builder_review` with `review_payload` before
   rendering. When this is a successor review, also pass the exact
   `expected_predecessor_checkpoint` retained outside the report folder.
3. If validation succeeds, call `render_report_builder_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/report-builder-review.html`.
4. Use the widget to review section mappings, narrative gaps, table evidence,
   `report_draft.md`, `report.docx`, `report_analysis.json`,
   `report_audit.json`, `report_tables.json`, `report_tables.xlsx`,
   `source_receipts.json`, `numeric_evidence_ledger.json`, and
   `used_recipe.json`.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_report_builder_decisions` so
   `report/ui_decisions.json` is validated and persisted. When the reviewer is
   done, call `apply_report_builder_decisions` so
   `report/applied_decisions.json` and `report/final_artifacts.json` reflect
   accepted, edited, unclear, skipped, or document-requested items before
   treating the report package as reviewed.
6. Retain the returned `integrity_checkpoint` through a channel outside the
   mutable report folder. If another review round is applied, pass that exact
   value as `expected_predecessor_checkpoint`. Do not infer it from the report
   tree or silently accept a newly resealed local value.

For persisted runs, validation, rendering, save, and apply replay the sealed
source, review-payload, gallery, and output receipts. A stale receipt is a hard
stop: do not retry by resealing the old analysis. Rebuild from current sources.
After a source-mapping edit, use the regenerated `review_payload.json`; prior
numeric evidence files and references are removed when their decision no longer
binds. Never report `final_ready` while
`numeric_measure_pending_section_count` is nonzero.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `report_analysis.json`, `report_audit.json`,
`report_draft.md`, `report_tables.json`, and `used_recipe.json`. Keep review
decisions pending unless they are recorded in `report/ui_decisions.json` and
consumed into `report/applied_decisions.json`.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Build Report sui file in /percorso/report. Lingua: it. Lingua documenti: auto. Tipo report: management_report. Ispeziona tabelle e PDF, proponi la mappatura delle sezioni, chiedimi solo le ambiguita essenziali, poi aiutami a completare la narrativa e genera Markdown, DOCX e audit trail.
EN: Use Build Report on files in /path/report. Language: en. Document language: auto. Report type: management_report. Inspect tables and PDFs, propose section mapping, ask only for essential ambiguities, then help me complete the narrative and generate Markdown, DOCX, and audit trail.
FR: Utilise Build Report sur les fichiers dans /chemin/report. Langue: fr. Langue des documents: auto. Type de rapport: management_report. Inspecte les tableaux et PDF, propose le mapping des sections, demande uniquement les ambiguites essentielles, puis aide-moi a completer la narration et genere Markdown, DOCX et audit trail.
DE: Verwende Build Report fuer Dateien in /pfad/report. Sprache: de. Dokumentsprache: auto. Berichtstyp: management_report. Pruefe Tabellen und PDFs, schlage die Abschnittszuordnung vor, frage nur wesentliche Unklarheiten ab und hilf dann beim Ergaenzen der Narrative sowie beim Erstellen von Markdown, DOCX und Audit-Trail.
```

## Failure Modes

- If PDFs are scanned/OCR-only and no text is extracted, report that deterministic PDF text extraction is insufficient and list affected files.
- If Excel binary `.xls` files are provided, ask to convert them to `.xlsx` or `.csv` for this plugin version.
- If several tables map to the same section, keep the best deterministic suggestion but ask before finalizing.
- If source bytes no longer match their receipts, stop and rebuild from the
  current sources; never reseal a prior analysis against changed bytes.
- If too many sections remain unassigned, deliver inspection and a mapping checklist rather than pretending the report is complete.
- If a narrative conclusion is not supported by the deterministic evidence, keep it out of the recipe or mark it as a user-provided assertion.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new report template, a brittle PDF text extractor, a missing deterministic extraction script, a missing section-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.

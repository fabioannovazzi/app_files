# Build Report Workflow Reference

This plugin replaces the old report-builder web application with a Codex-guided workflow. The scripts are deterministic helpers; Codex provides the UI, mapping discussion, narrative drafting, and review layer.

## Deterministic Boundary

The scripts may:

- discover files in folders or ZIP archives;
- extract visible worksheets from `.xlsx` and `.xlsm` files;
- parse CSV files with dialect fallback;
- extract text lines from readable PDFs;
- inventory tables and provide previews;
- suggest section mapping using transparent keyword rules;
- compute numeric column counts, sums, minimums, and maximums;
- render Markdown, styled DOCX, JSON, and XLSX workpapers;
- record that zero model API calls were made.

The scripts must not:

- call any model API;
- decide that a narrative conclusion is true;
- silently force ambiguous table mappings;
- overwrite plugin source files during a run.

## Codex Boundary

Codex may:

- choose a working locale and infer document language;
- explain the inspection results;
- ask the user for missing mapping decisions;
- edit the generated recipe in the work folder;
- write `executive_summary` and `codex_comment` fields after checking the evidence;
- rerun the deterministic build;
- review the draft for missing sections and unsupported statements.

Codex should keep uncertainty visible. When a table or narrative claim needs user confirmation, say so in the final summary and in the recipe comments.

## Supported Report Types

- `management_report`: overview, income statement, balance sheet, cash flow, budget, debt, investments, taxes, notes.
- `local_government_review`: overview, FPV, FCDE, debt, cash, taxes, spending, investments, participations, PNRR, notes.
- `annual_financial_statement`: overview, balance sheet, income statement, cash flow, equity, ratios, segment information, debt, capital expenditure, notes.

## Recipe Editing Pattern

Use the recipe generated as `<workdir>/suggested_recipe.json`.

1. Keep the generated `version`, `language`, `document_language`, and `report_type`.
2. Fill `entity` and `period`.
3. Add known context notes under `context_items`.
4. For each section, set `assigned_table` to a `table_id` from `inspection.json`.
5. Write concise, evidence-backed prose in `codex_comment`.
6. Set `executive_summary` only after section comments are consistent.
7. Rerun `scripts/build_report.py`.

Do not ask the user to edit the JSON. Convert user answers into recipe edits yourself.

## Review Checklist

Before final delivery, inspect:

- `inspection.json`: table count, extraction errors, low-confidence suggestions;
- `suggested_recipe.json` or `used_recipe.json`: entity, period, mapped sections, comments;
- `report_analysis.json`: assigned and missing section counts;
- `report_audit.json`: `model_api_calls` must be `0`;
- `report_draft.md`: unsupported narrative and visible placeholders;
- `report.docx`: file exists, has styled headings, real Word tables, and an audit appendix.

## Escalation Examples

Suggest plugin improvements when a run exposes repeated manual work:

- a recurring customer workbook has a stable sheet layout that deserves a deterministic mapper;
- a readable PDF has tables that should be parsed into columns instead of text lines;
- a new report type needs its own section set;
- a DOCX styling requirement repeats across engagements.

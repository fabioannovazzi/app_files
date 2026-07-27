> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Build Report Workflow Reference

This plugin replaces the old report-builder web application with a Claude-guided workflow. The scripts are deterministic helpers; Claude provides the UI, mapping discussion, narrative drafting, and review layer.

## Deterministic Boundary

The scripts may:

- discover files in folders or ZIP archives;
- capture each source as stable bytes and record a path-and-content-bound
  artifact identity;
- extract visible worksheets from `.xlsx` and `.xlsm` files;
- parse CSV files with dialect fallback;
- extract text lines from readable PDFs;
- inventory tables and provide previews;
- suggest section mapping using transparent keyword rules;
- compute numeric column counts, sums, minimums, and maximums;
- keep numeric-looking columns as candidates until a source-bound reviewed
  decision identifies actual measures;
- reopen receipted sources and prove exact source-to-analysis-to-XLSX,
  Markdown, and DOCX numeric closure;
- render Markdown, styled DOCX, JSON, and XLSX workpapers;
- record that zero model API calls were made.

The scripts must not:

- call any model API;
- decide that a narrative conclusion is true;
- silently force ambiguous table mappings;
- overwrite plugin source files during a run.

## Claude Boundary

Claude may:

- choose a working locale and infer document language;
- explain the inspection results;
- ask the user for missing mapping decisions;
- edit the generated recipe in the work folder;
- write `executive_summary` and `codex_comment` fields after checking the evidence;
- rerun the deterministic build;
- review the draft for missing sections and unsupported statements.

Claude should keep uncertainty visible. When a table or narrative claim needs user confirmation, say so in the final summary and in the recipe comments.

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
5. Review candidate numeric columns and use
   `scripts/review_numeric_measures.py` to bind every candidate column and
   nonblank candidate cell to an explicit include/exclude disposition at the
   exact source receipt. Explicitly choose the detected one-based header row or
   `none` for a headerless table; the detector is only a review suggestion.
   Record locale, currency or no currency, unit, scale, sign policy, the report
   period already present in the recipe, and the strict parse policy
   explicitly. Numeric identifiers and subtotal/formula cells must remain
   explicitly excluded.
6. Write concise, evidence-backed prose in `codex_comment`.
7. Set `executive_summary` only after section comments are consistent.
8. Rerun `scripts/build_report.py`.

Do not ask the user to edit the JSON. Convert user answers into recipe edits yourself.

Interim numeric-closure rule: do not put numerals in `entity`, either side of
`context_items`, `executive_summary`, section titles, or `codex_comment`.
Report-value numerals must come from reviewed numeric measures. Use a digit-free
entity display name. `period` accepts `YYYY`, `FYYYYY`, `Qn YYYY`, an ISO date,
`Year|Period|Quarter ended YYYY-MM-DD`, or an ISO-date `to|through` range.

Example reviewed-measure command:

```bash
python scripts/review_numeric_measures.py \
  --inspection <workdir>/inspection.json \
  --recipe <workdir>/suggested_recipe.json \
  --output <workdir>/reviewed_recipe.json \
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
`inspection.json`. Repeat `--cell-disposition` for every nonblank cell in every
included column under that reviewed header choice.
The helper records all included and excluded cells, supports an all-excluded
decision, and fails closed if a candidate or cell is undisposed, a selected
cell is a formula, or a value is unresolved, mixed-currency, malformed, or
incompatible with the reviewed unit.

## Persisted Review Integrity

- `source_index.json` is private run state. It stores the absolute source roots
  needed to replay exact bytes and is never a gallery output.
- `review_integrity.json` receipts the source index, persisted review payload,
  final gallery, and each current gallery output.
- Persisted validate, render, save, and apply operations replay these receipts.
  Save and apply stop before their first write when state is stale.
- A successful persisted save or apply returns `integrity_checkpoint`. Retain
  that value outside the mutable report folder. Applying a later review round
  requires it as `expected_predecessor_checkpoint`; the successor archives the
  full predecessor integrity envelope, run intake, review payload, UI
  decisions, applied decisions, final gallery, and material-output receipts.
- Validating, rendering, or saving a successor state requires the predecessor
  checkpoint embedded by that transition. The official Python seal and
  validator expose the same boundary through
  `--expected-predecessor-checkpoint`.
- This proves continuity only when the checkpoint comes from the separately
  retained channel. Local SHA-256 values establish consistency, not reviewer
  identity, package provenance, a signature, or append-only storage.
- Source-mapping edits regenerate the review payload. Old numeric ledgers and
  references are removed when the prior numeric decision no longer binds.
- Changing the recipe period invalidates every earlier numeric-measure decision
  bound to the prior period; those totals remain withheld until re-review.
- `final_artifacts.json` contains only current allowlisted report outputs, each
  with its current byte count and SHA-256 digest. Extracted ZIP members,
  revision backups, and private control files remain outside the gallery.
- Pending numeric-measure review always keeps application status below
  `final_ready`, even if every UI item was accepted or skipped.

## Review Checklist

Before final delivery, inspect:

- `inspection.json`: table count, extraction errors, low-confidence suggestions;
- `suggested_recipe.json` or `used_recipe.json`: entity, period, mapped sections, comments;
- `report_analysis.json`: assigned and missing section counts;
- `report_analysis.json`: `numeric_measure_status` is `reviewed` or
  `not_applicable` for every reported total;
- `source_receipts.json`: every numeric source still matches the bytes used;
- `numeric_evidence_ledger.json`: each source, prepared, and rendered value is
  identical and has an exact locator;
- `report_audit.json`: `model_api_calls` must be `0`;
- `report_draft.md`: unsupported narrative and visible placeholders;
- `report.docx`: file exists, has styled headings, real Word tables, and an audit appendix.
- `final_artifacts.json`: every output is current, allowlisted, and receipted;
- `review_integrity.json`: persisted source and handoff replay closes.

## Escalation Examples

Suggest plugin improvements when a run exposes repeated manual work:

- a recurring customer workbook has a stable sheet layout that deserves a deterministic mapper;
- a readable PDF has tables that should be parsed into columns instead of text lines;
- a new report type needs its own section set;
- a DOCX styling requirement repeats across engagements.

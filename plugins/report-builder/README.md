# Build Report Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/report-builder) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Build Report is a Codex-guided reporting workflow for variable finance and audit inputs. It replaces the old web report-builder flow with deterministic local scripts plus Codex review.

Codex and Cowork use the same bounded inspection/expansion rules. A runtime
without the required helper must not substitute a raw workbook, PDF, private
inspection control, or whole connected folder as model context.

## What It Does

- Inspects `.xlsx`, `.xlsm`, `.csv`, readable `.pdf`, and ZIP inputs.
- Processes the full input population locally, writes a bounded model-visible
  `inspection.json`, keeps the complete cell inventory in private
  `inspection_control.json`, and receipts both in `model_context_receipt.json`.
- Supports repeatable, purpose-labelled expansion packets limited to one table,
  sixteen exact columns, and one hundred source rows per packet, so additional
  evidence remains available without disclosing the complete inventory by default.
- Lets Codex map tables, ask only essential questions, and write narrative fields in the recipe.
- Captures stable source bytes, disambiguates duplicate source names, and keeps
  absolute source roots in the private run-local `source_index.json`.
- Builds `report_tables.json`, `report_analysis.json`, `report_draft.md`, a styled `report.docx`, `report_audit.json`, and `used_recipe.json`.
- Reopens the receipted sources and writes
  `numeric_evidence_ledger.json`, proving exact source-to-analysis-to-rendered
  value closure for explicitly reviewed measure columns, plus a public
  relative-path `source_receipts.json`.
- Requires an explicit include/exclude disposition for every numeric candidate
  column and every nonblank cell in an included column, under an explicit
  reviewed choice of the detected header row or no header. This keeps
  identifiers and subtotals out of totals, permits a reviewed all-excluded
  result, and records sign treatment. The reviewed receipt also binds the
  report period; changing the period with an old numeric decision withholds the
  prior totals.
- Dual-reads workbook formulas and cached values. Formula cells fail closed as
  measures because this version has no verified recalculation/export adapter.
- Writes a local review handoff: `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and `final_artifacts.json` in the report output folder.
- Seals `review_integrity.json` and replays source, review-payload, gallery, and
  output receipts before any persisted review save or apply.
- Returns the current integrity checkpoint after a persisted review. A later
  review round requires that exact SHA-256 value from a separately retained
  channel, archives the full predecessor integrity envelope and review state,
  and rejects missing, replaced, or non-immediate predecessor history.
- Validates the exact 32-file executable plugin and shared-assurance tree before
  importing workflow code, and runs MCP-launched Python with isolated imports
  and bytecode disabled. Unowned files, directories, caches, links, and other
  non-regular execution paths fail closed.
- Rebuilds `final_artifacts.json` from a fixed public-output allowlist. Raw ZIP
  extraction, private source state, integrity state, and revision backups never
  enter that gallery.
- Supports working locales `it`, `en`, `fr`, `de`, and `es`.

## What It Does Not Do

- It does not expose a web application.
- It does not call OpenAI or other model APIs from helper scripts.
- Its implementation and artifact hashes prove replay consistency; they do not
  authenticate a professional reviewer or a trusted package publisher.
- The predecessor checkpoint is only as trustworthy as the separate channel
  used to retain it. It is not a signature or an append-only audit store.
- It does not OCR scanned PDFs in v1.
- It does not treat numeric-looking identifiers as measures or silently choose
  the header row, reporting period, locale, currency, unit, scale, sign
  treatment, candidate disposition, or parse policy.
- As an interim output-closure control, free-form entity, context, executive
  summary, section-title, and section-comment fields cannot contain numerals.
  All report-value numerals must come from reviewed measures. Periods may use
  `YYYY`, `FYYYYY`, `Qn YYYY`, an ISO date, `Year|Period|Quarter ended
  YYYY-MM-DD`, or an ISO-date `to|through` range. This means legal names such as
  `3M Company` need a digit-free reviewed display name until structured
  claim-basis references cover narrative numerals.

## Dependency Check

From the plugin directory:

```bash
python scripts/check_dependencies.py
```

Install only from `requirements.txt` when the environment allows it.

## Local MCP Review UI

After `scripts/build_report.py` completes, Codex can use the local MCP server to
validate and render the generated review payload:

- `validate_report_builder_review` validates `review_payload.json`.
- `render_report_builder_review` renders `ui://widget/report-builder-review.html`.
- `save_report_builder_decisions` and `apply_report_builder_decisions` reject
  stale persisted sources, review state, or output bytes before writing.
  Apply preflights exact adapters and table IDs and rolls back the whole run
  output if regeneration or its final integrity replay fails. The Python
  regeneration child must also match the exact decision and gallery digests
  handed to it by the MCP process.
- Retain the `integrity_checkpoint` returned by a successful persisted
  application outside the report folder. Pass it as
  `expected_predecessor_checkpoint` when applying the next review round. After
  a successor exists, pass the same predecessor checkpoint to validate,
  render, or save that successor state.

Use the widget for report sections, table evidence, narrative gaps, and the
generated Markdown/DOCX/JSON/XLSX artifacts. Keep simple intake and mapping
choices in Codex chat or native Plan-mode choices.

`final_ready` is unavailable while any mapped table still has candidate
numeric measures without a valid reviewed semantic decision.

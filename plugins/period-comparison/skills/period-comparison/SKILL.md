---
name: period-comparison
description: Use when a user wants Codex to inspect a sales CSV/XLSX file, compare the current period with the previous-year period, generate year-over-year charts, small multiples, source packs, and interpret the movements.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Period-over-Period Analysis

Use this skill when a sales or revenue dataset needs period comparison charts:
year-over-year column, year-over-year line, year-over-year by period, slope,
dot/dumbbell, and year-over-year waterfall. The plugin is a guided Codex workflow: Codex inspects
the file, confirms unresolved mappings, runs deterministic helper scripts,
reviews diagnostics, and explains the movement in business language.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify only material choices
that cannot be inferred from the actual inputs: ambiguous date column, amount
column, reporting dimensions, output folder, and working language. Charts, small
multiples, audit files, diagnostics, source packs, and Word reports are
default behavior; do not ask the user whether to enable them. Ask only those
unresolved choices in chat and wait for the answer. Generate choices from the
actual inputs; do not offer chart modes, output packages, or issue categories
unless the facts cue them.

Default output policy: produce the richest normal package. DOCX/Word, CSV/XLSX,
JSON audit, diagnostics, charts, source packs, and Codex-written review files
are not choices to propose when they are natural outputs of this plugin.
If a required mapping remains unresolved after inspection, ask only those unresolved choices in chat.

Default currency policy: use Euro (`EUR`) unless the user or source file
explicitly states another currency.

Use Codex-native UI artifacts as part of the workflow:

1. Start with a visible markdown checklist covering intake, dependency check, inspection, user decisions, deterministic run, Codex interpretation, and delivery.
2. Before helper scripts, show a Run Intake table with input path, output folder, working language, assumed mappings, and note that chart outputs, small multiples, source pack and client report outputs run automatically.
3. After inspection, show a compact Decision Table for missing or low-confidence mappings and ask only unresolved decisions.
4. Before a long-running or write-heavy step, show an execution checkpoint or approval checkpoint with command intent, input, output folder, and expected artifacts. Ask for approval only when the step is external, destructive, approval-sensitive, or still depends on an unresolved material choice.
5. End with an Artifact Card listing output paths, review status, unresolved caveats, and next action.
6. For every completed run, create one client-ready Word deliverable: `period_comparison_client_report.docx`. Put Codex's business interpretation into that report and, if useful, mirror the same narrative in `period_comparison_client_report.md`. Use `codex_run_review.md` only as an internal run note, not as a second client report. Never create competing Word outputs for the same run, and do not edit plugin source or generated ZIPs during a run.

## Core Principle

The vendored legacy Mparanza code owns actual-vs-previous-year preparation and
period-comparison chart semantics where available. The plugin adapter owns file
parsing, mapping user columns into legacy canonical names, headless capture and
export of the vendored legacy chart figures, CSV/XLSX/JSON/Markdown/DOCX
outputs, and source-pack generation.

Generated PNGs must follow the plugin period-comparison role contract: older previous-year
bars and totals are gray, current-period bars and totals are black, positive
movements are green, negative movements are red, and the year-over-year
waterfall is a reconciled bridge from previous year to current year. Do not
describe generic Plotly defaults as following the plugin role contract if the
audit does not record a `legacy_plotly...` renderer and source functions from
the vendored legacy chart modules.

Codex owns judgment: deciding ambiguous mappings with the user, interpreting
the largest period movements, explaining caveats, and writing business-language
commentary. The plugin scripts must not make direct model API calls.

Legacy includes both the period-comparison analysis/preparation path and the
Plotly rendering path. Codex should interpret the prepared numbers, context
JSON, tables, audits, and briefs first; chart PNG/HTML artifacts are selected
later for human communication and visual QA.

## Structured Outputs

Every successful run writes structured context, table, and audit files in the
run directory. Interpretation must use those numbers first, before looking at
PNG/HTML chart artifacts.

Every successful run also writes the local UI handoff files
`period_comparison/run_intake.json`, `period_comparison/review_payload.json`,
`period_comparison/ui_decisions.json`, and
`period_comparison/final_artifacts.json`. Treat `review_payload.json` as the
bounded OpenAI-style payload for the local MCP widget. It contains monthly
movement rows, by-period windows, chart artifacts, context artifacts, follow-up
requests, and generated report artifacts for review.

## Static HTML Examples

For plugin landing pages, chart examples must not depend on separately served
PNG assets when the hosted page needs to be self-contained. Embed the approved
legacy PNGs as `data:image/png;base64,...` in the HTML, and keep the source PNGs
under `static/shared/<plugin>/examples/` only as maintainable originals. This
avoids broken hosted pages when `/static/shared/<plugin>/examples/...` asset
requests are unavailable, while preserving the real legacy chart output.

## First Run Workflow

1. Ask for the input file and output folder only when not already clear.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the
environment allows it, or explain what dependency capability is missing.

3. Run deterministic inspection:

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <output-dir> --language <it|en|fr|de|es>
```

4. Read `inspection.json` and `suggested_recipe.json`. Summarize columns,
suggested mappings, warnings, and missing required choices.
5. If a mapping decision is needed, ask the smallest business question and update
the recipe JSON in the work folder yourself.
6. Run deterministic period comparison:

```bash
python scripts/run_period_comparison.py <input-file> --output-dir <output-dir>/period_comparison --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use the structured data-only mode:

```bash
python scripts/run_period_comparison.py <input-file> --output-dir <output-dir>/period_comparison_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

7. Review `period_comparison_context.json`, tables,
   audit, and briefs before looking at chart images. Interpret current vs previous-year movement, the
   months and panels that drive it, and whether follow-up variance analysis is
   needed. Inspect chart PNG/HTML artifacts afterward to confirm
   visual fit for the final report.
8. Review the generated structured outputs and update `period_comparison_client_report.md` / `period_comparison_client_report.docx` with Codex's business interpretation. If a separate run note is useful, write `codex_run_review.md`; it is not a client deliverable.

## MCP Review Handoff

After the deterministic run writes `period_comparison/review_payload.json`,
prefer the local MCP widget when the `periodComparisonWidgets` server is
available:

1. Read `period_comparison/run_intake.json`,
   `period_comparison/review_payload.json`,
   `period_comparison/ui_decisions.json`, and
   `period_comparison/final_artifacts.json`.
2. Call `validate_period_comparison_review` with the review payload and optional
   intake/decision/final-artifact objects.
3. If validation succeeds, call `render_period_comparison_review` with the same
   payload so Codex can show the HTML review widget.
4. Use `save_period_comparison_decisions` to persist reviewer actions to
   `ui_decisions.json`, then `apply_period_comparison_decisions` to write
   `applied_decisions.json` and update `final_artifacts.json` status.
5. If MCP rendering is unavailable, fall back to a concise Markdown/chat review
   based on `review_payload.json`; do not block the deterministic run.

Use the UI handoff to review the generated chart/report package. Continue to
write the client interpretation from structured source data and reviewed facts.

## Recipe Rules

Codex can edit `suggested_recipe.json` in the work folder. Use these fields:

- `language`: working/output language;
- `mappings.date_column`: date column used for period windows;
- `mappings.amount_column`: sales, revenue, or amount column;
- `mappings.dimensions`: reporting columns available for small multiples;
- `options.currency`: defaults to `EUR`;
- `options.charts`: all supported period-comparison charts by default;
- `options.small_multiples`: forced on when a useful dimension can be inferred;
- `options.small_multiples_dimension`: optional explicit panel dimension.

Do not ask the user to edit JSON. Ask in business terms, then Codex updates the
recipe and reruns deterministic scripts.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `period_comparison/used_recipe.json`;
- `period_comparison/period_comparison_monthly.csv`;
- `period_comparison/period_comparison_by_period.csv`;
- `period_comparison/period_comparison_canonical.csv`;
- `period_comparison/period_comparison_results.xlsx`;
- `period_comparison/period_comparison_context.json`;
- `period_comparison/period_comparison_audit.json`;
- `period_comparison/period_comparison_summary.md`;
- `period_comparison/run_intake.json`;
- `period_comparison/review_payload.json`;
- `period_comparison/ui_decisions.json`;
- `period_comparison/final_artifacts.json`;
- `period_comparison/year_over_year_column.png`;
- `period_comparison/year_over_year_line.png`;
- `period_comparison/year_over_year_by_period.png`;
- `period_comparison/year_over_year_slope.png`;
- `period_comparison/year_over_year_dot.png`;
- `period_comparison/year_over_year_waterfall.png`;
- `period_comparison/year_over_year_small_multiples.png` when a useful
  dimension exists;
- `period_comparison/period_comparison_client_report.md`;
- `period_comparison/period_comparison_client_report.docx`;
- optional `period_comparison/codex_run_review.md` for internal execution notes.

## Failure Modes

- If required mappings are missing after inspection, ask for those mappings
  before running charts.
- If the date column cannot be parsed, stop and ask for the correct date field
  or a prepared period file.
- If the amount column is non-numeric, stop and report the exact column and dtype.
- If previous-year rows are unavailable, report the blocker; do not fabricate a
  comparison period.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting
deliverables, briefly identify concrete improvements that would have made this
plugin run better. Base suggestions on the actual session, such as a missing
column-mapping heuristic, unsupported file type, unclear recipe field, output
gap, installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.

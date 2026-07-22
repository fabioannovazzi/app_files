---
name: distribution-analysis
description: Use when a user wants Codex to inspect a CSV/XLSX file, generate legacy histogram, boxplot, stripplot, ECDF, kernel-density charts, small multiples, and distribution-shape source data.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Distribution Analysis

Use this skill when a dataset needs distribution charting: histograms,
boxplots, stripplots, ECDF plots, kernel-density plots, period comparisons, and
small multiples where the legacy chart supports them.

## Codex-Native Run UX

Ask only material choices that cannot be inferred from the actual input:
ambiguous metric, distribution aggregation dimension, small-multiples dimension,
period/date column, output folder, and working language. Chart families, small
multiples, audit files, diagnostics, source packs, and artifact ZIPs are
default behavior; do not ask whether to enable them. Ask only unresolved choices
in chat and base every inferred default on the actual inputs. Ask only those unresolved choices in chat; do not introduce optional questions unless the facts cue them.

Default currency policy: use Euro (`EUR`) unless the user or source file
explicitly states another currency.

Use a compact checklist while working: intake, dependency check, inspection,
unresolved mapping decisions, deterministic run, Codex interpretation, and
delivery.

Start with a short Run Intake table when the user has not already provided the
file, language, output folder, metric, period/date fields, or key dimensions.
When a required mapping is ambiguous, use a Decision Table with the inferred
choice, source basis, and any material approval-sensitive step. Before a long or
write-heavy deterministic step, show an execution checkpoint with command
intent, input, output folder, and expected artifacts. The Default output policy
is: produce the rich package by default. Audit files, diagnostics, source
packs, chart PNG/HTML files, and generated ZIPs are not choices to propose when
they are natural outputs. End with an Artifact Card that links the source pack,
audit, context, summary, and any `codex_run_review.md` note.
Ask for explicit continuation or approval only when the next step is external,
destructive, approval-sensitive, or still depends on an unresolved material
decision. Do not ask the user to type a generic continuation word merely to
create ceremony.

## Core Principle

The vendored legacy Mparanza code owns chart preparation and chart semantics.
The adapter owns file parsing, mapping user columns into legacy chart
configuration, reusable prepared-data caching, headless capture/export of
vendored legacy Plotly figures, CSV/XLSX/JSON/Markdown outputs, and
source-pack generation.

Do not silently redraw failed legacy charts with new code. If a legacy chart
fails because of compatibility or unsupported input shape, write the failure to
the audit and report the affected chart. This plugin is a wrapper around the
legacy charting library, not a new chart implementation.

Legacy includes both the distribution preparation path and the Plotly rendering
path. Codex should interpret the prepared numbers, context JSON, tables, audits,
and briefs first; chart PNG/HTML artifacts are selected later for human
communication and visual QA.

## Structured Outputs

Every run writes structured context and audit files in the run directory.
Interpretation must use those numbers first, before looking at PNG/HTML chart
artifacts. For distribution charts, this means exposing the plotted metric,
periods, aggregation dimension, panel dimension, captured legacy chart data,
Plotly traces, draw-function invocations, and cache activity.

Every successful run also writes the local UI handoff files
`distribution/run_intake.json`, `distribution/review_payload.json`,
`distribution/ui_decisions.json`, and `distribution/final_artifacts.json`.
Treat `review_payload.json` as the bounded OpenAI-style payload for the local
MCP widget. It contains distribution summary rows, chart artifacts, context
artifacts, follow-up requests, and generated report artifacts for review.

## Legacy Inventory

The supported chart families are:

- `histogram`: `modules.charting.plot_charts.plot_histogram_charts`;
- `boxplot`: `modules.charting.plot_charts.plot_boxplot_charts`;
- `stripplot`: `modules.charting.plot_charts.plot_stripplot_charts`;
- `ecdf`: `modules.charting.plot_charts.plot_ecdf_charts`;
- `kernel_density`: `modules.charting.plot_charts.plot_kernel_density_charts`.

Small multiples use the same legacy plotter with
`chartDict[smallMultiplesColumn]`; there are no separate small-multiple
distribution plotter functions.

See `references/legacy_distribution_inventory.md` for the exact legacy chart
keys, draw functions, prep functions, and settings.

## First Run Workflow

1. Ask for the input file and output folder only when not already clear.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the
environment allows it, or explain which dependency capability is missing.

3. Run deterministic inspection:

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <output-dir> --language <it|en|fr|de|es>
```

4. Read `suggested_recipe.json`. Summarize mappings, warnings, and only
   unresolved required choices.
5. If a mapping decision is needed, ask in business terms and update the recipe
   JSON yourself.
6. Run deterministic distribution analysis:

```bash
python scripts/run_distribution.py <input-file> --output-dir <output-dir>/distribution --recipe <output-dir>/suggested_recipe.json
```

When chart images are not needed, use the structured data-only mode:

```bash
python scripts/run_distribution.py <input-file> --output-dir <output-dir>/distribution_data --recipe <output-dir>/suggested_recipe.json --artifact-mode data_only
```

7. Review `distribution_context.json`, tables, audit,
   and summary files before looking
   at chart images. Interpret shape, skew, spread, tails, outliers and
   small-multiple differences from structured source data. Inspect chart
   PNG/HTML artifacts afterward to confirm visual fit.
8. If a separate run note is useful, write `codex_run_review.md`; it is not a
   client deliverable.

## MCP Review Handoff

After the deterministic run writes `distribution/review_payload.json`, prefer
the local MCP widget when the `distributionWidgets` server is available:

1. Read `distribution/run_intake.json`, `distribution/review_payload.json`,
   `distribution/ui_decisions.json`, and `distribution/final_artifacts.json`.
2. Call `validate_distribution_review` with the review payload and optional
   intake/decision/final-artifact objects.
3. If validation succeeds, call `render_distribution_review` with the same
   payload so Codex can show the HTML review widget.
4. Use `save_distribution_decisions` to persist reviewer actions to
   `ui_decisions.json`, then `apply_distribution_decisions` to write
   `applied_decisions.json` and update `final_artifacts.json` status.
5. If MCP rendering is unavailable, fall back to a concise Markdown/chat review
   based on `review_payload.json`; do not block the deterministic run.

Use the UI handoff to review the generated chart/report package. Continue to
write the client interpretation from structured source data and reviewed facts.

## Recipe Rules

Codex can edit `suggested_recipe.json` in the work folder. Use these fields:

- `language`: working/output language;
- `mappings.metric_column`: metric to plot;
- `mappings.distribution_dimension`: optional dimension used to aggregate
  observations before plotting;
- `mappings.small_multiples_dimension`: optional panel dimension;
- `mappings.date_column`: optional date column for audit/title context;
- `mappings.period_column`: optional scenario/period column;
- `mappings.dimensions`: reporting columns to retain;
- `options.currency`: defaults to `EUR`;
- `options.charts`: complete supported chart list by default;
- `options.selected_periods`: one or two period/scenario values;
- `options.small_multiples`: on when a useful dimension can be inferred;
- `options.max_chart_items`: top items before legacy Other aggregation;
- `options.cumulative_histogram`, `options.reversed_ecdf`,
  `options.show_outliers`, `options.log_x_axis`: legacy distribution settings.

Do not ask the user to edit JSON.

## Expected Outputs

- `suggested_recipe.json`;
- `distribution/used_recipe.json`;
- `distribution/distribution_canonical.csv`;
- `distribution/distribution_summary.csv`;
- `distribution/distribution_results.xlsx`;
- `distribution/distribution_context.json`;
- `distribution/distribution_audit.json`;
- `distribution/distribution_summary.md`;
- `distribution/run_intake.json`;
- `distribution/review_payload.json`;
- `distribution/ui_decisions.json`;
- `distribution/final_artifacts.json`;
- legacy chart PNGs or Plotly HTML where legacy rendering succeeds;
- `distribution/distribution_client_report.md`;
- `distribution/distribution_artifacts.zip`.

## Failure Modes

- If no numeric metric exists, stop and ask for the correct metric field.
- If fewer than three non-null metric rows exist, report the blocker.
- If no useful dimension exists, still run standard distribution charts and
  skip small multiples.
- If a legacy chart fails, keep going with the remaining charts and record the
  failed chart, source function and error in the audit. Do not fabricate a
  replacement chart.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, briefly identify concrete
improvements that would have made this plugin run better. Base suggestions on
the actual session.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.

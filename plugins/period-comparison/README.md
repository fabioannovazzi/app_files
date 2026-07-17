# Period-over-Period Analysis

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/period-comparison) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Period-over-Period Analysis is a Codex workflow plugin for previous-year
comparison analysis. It follows the chart-family plugin pattern: legacy
preparation remains the source of truth, exported charts are captured from the
vendored legacy chart functions, chart outputs are written as reviewable
files, and Codex interprets the generated numbers.

The plugin runs the full period-comparison family by default:

- year-over-year column;
- year-over-year line;
- year-over-year by period;
- year-over-year slope;
- year-over-year dot/dumbbell;
- year-over-year waterfall;
- small multiples when a useful dimension can be inferred.

Period role colors come from the legacy charting modules: the older period is
gray, the current period is black, positive movements are green, and negative
movements are red. The year-over-year waterfall is rendered as a reconciled
bridge from previous year to current year.

The scripts do not call model APIs. Codex reads the generated context, tables,
and audits, then writes any client-facing interpretation.

The plugin also writes an OpenAI-style local review handoff for the generated
period-comparison package. `period_comparison/run_intake.json` records finalized
recipe assumptions before rendering. `period_comparison/review_payload.json`,
`period_comparison/ui_decisions.json`, and
`period_comparison/final_artifacts.json` provide the bounded payload that the
local `periodComparisonWidgets` MCP server validates and renders with the
reusable HTML widget at `ui://widget/period-comparison-review.html`. Codex
should use that MCP widget when available, and fall back to Markdown/chat review
only when MCP rendering is not available.

Typical outputs:

- `inspection.json`
- `suggested_recipe.json`
- `period_comparison/period_comparison_monthly.csv`
- `period_comparison/period_comparison_by_period.csv`
- `period_comparison/period_comparison_context.json`
- `period_comparison/run_intake.json`
- `period_comparison/review_payload.json`
- `period_comparison/ui_decisions.json`
- `period_comparison/final_artifacts.json`
- `period_comparison/year_over_year_column.png`
- `period_comparison/year_over_year_line.png`
- `period_comparison/year_over_year_by_period.png`
- `period_comparison/year_over_year_slope.png`
- `period_comparison/year_over_year_dot.png`
- `period_comparison/year_over_year_waterfall.png`
- `period_comparison/year_over_year_small_multiples.png`
- `period_comparison/period_comparison_client_report.docx`

## Commands

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <input-file> --output-dir <workdir>
python scripts/run_period_comparison.py <input-file> --output-dir <workdir>/period_comparison --recipe <workdir>/suggested_recipe.json
```

The run script also supports a data-only mode:

```bash
python scripts/run_period_comparison.py <input-file> --output-dir <workdir>/period_comparison_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

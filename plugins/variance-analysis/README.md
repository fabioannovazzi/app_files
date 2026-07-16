# Variance Analysis

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/variance-analysis) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Variance Analysis is a Codex workflow plugin for sales variance analysis with
Codex-led interpretation.

The plugin accepts a local CSV or Excel file, writes a suggested mapping recipe,
then produces auditable variance outputs. The scripts do not call model APIs.
Codex reads the generated source data and explains the drivers, caveats, and next
questions in business language.

Codex first confirms only required mappings that cannot be inferred. Scenario comparisons such as
`PL` vs `AC` can use strong defaults, while period comparisons must distinguish
calendar periods, year-to-date windows, rolling windows, or custom filters
before the results are interpreted.

Year-to-date and rolling windows are prepared before variance calculation with
the vendored legacy date helpers. The plugin derives the most recent date,
creates an auditable synthetic period bucket, then sends that bucket through the
same legacy PVM and margin calculation path.

The plugin vendors a targeted subset of the old `modules/variance`,
`modules/data`, and supporting `modules/utilities` code. Runtime calculation is routed through
the legacy period split (`rename_periods`), period pivot (`pivot_lazy_periods`),
variance formula (`calculate_variance`), sales mix formula
(`calculate_sales_mix_variance`). The plugin adapter maps CSV/XLSX columns
into the old canonical names, writes outputs, and leaves interpretation to
Codex.

The architectural pattern is deliberate: reuse legacy data preparation, reuse
legacy chart generation where possible, then add a modern Codex interpretation
and client-report layer. Future chart-family plugins should follow the same
split. Period-comparison/year-over-year charts should include legacy
`multitierColumnChart` because it is the old year-over-year column chart and
shares the period-comparison preparation path. Composition plugins should keep
legacy `multitierBarChart` separate because it is a hierarchy/composition view.
When a legacy chart family supports small multiples, the plugin should generate
them by default when a useful dimension can be inferred and include them in the
source data reviewed by Codex.

The plugin writes structured context files directly in the run directory.
Codex should use those JSON/CSV/XLSX outputs to decide what the generated
charts mean; PNGs are for communication and visual QA.
When at least two dimensions are mapped, the plugin can also write
`exploded_variance_bridge`, a one-page parent/child bridge with a native JSON
spec (`exploded_variance_bridge_spec.json`) and chart data sidecar so a later
deck builder can insert it into a PPT without interpreting chart pixels.

The plugin now also writes an OpenAI-style local review handoff for the
generated variance package. `variance/run_intake.json` records the finalized
recipe assumptions before the deterministic run. `variance/review_payload.json`,
`variance/ui_decisions.json`, and `variance/final_artifacts.json` provide the
bounded payload that the local `varianceAnalysisWidgets` MCP server validates and
renders with the reusable HTML widget at
`ui://widget/variance-analysis-review.html`. Codex should use that MCP widget
when available, and fall back to a Markdown/chat review only when MCP rendering
is not available.

Chart PNG output first tries Plotly/Kaleido. On machines where Kaleido cannot
launch Chrome, the plugin uses the built-in Pillow chart renderer instead and
records that fallback in the chart audit. This is an expected local fallback,
not a failed variance run.

Typical outputs:

- `inspection.json`
- `suggested_recipe.json`
- `variance/variance_results.csv`
- `variance/variance_results.xlsx`
- `variance/variance_audit.json`
- `variance/variance_summary.md`
- `variance/run_intake.json`
- `variance/review_payload.json`
- `variance/ui_decisions.json`
- `variance/final_artifacts.json`
- `variance/standard_variance_context.json`
- `variance/waterfall.png`
- `variance/exploded_variance_bridge.png`
- `variance/exploded_variance_bridge_spec.json`
- `variance/exploded_variance_bridge_chart_data.json`
- `variance/exploded_variance_bridge_context.json`
- `variance/root_cause_bridge.png`
- `variance/root_cause_sweep_summary.csv`
- `variance/root_cause_client_report.docx`
- `codex_business_analysis.md`

## Commands

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <input-file> --output-dir <workdir>
python scripts/run_variance.py <input-file> --output-dir <workdir>/variance --recipe <workdir>/suggested_recipe.json
```

The run script also supports a data-only mode:

```bash
python scripts/run_variance.py <input-file> --output-dir <workdir>/variance_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

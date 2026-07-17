# Distribution Analysis Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/distribution-analysis) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Distribution Analysis wraps the legacy Mparanza Plotly distribution chart code
for Codex runs. It supports histogram, boxplot, stripplot, ECDF and
kernel-density charts, including small multiples through the legacy
`smallMultiplesColumn` path.

The plugin writes canonical data, summary tables, legacy chart artifacts,
structured context, and audit metadata. Failed legacy chart
attempts are recorded in the audit; no substitute renderer is used.

The plugin also writes an OpenAI-style local review handoff for the generated
distribution package. `distribution/run_intake.json` records finalized recipe
assumptions before rendering. `distribution/review_payload.json`,
`distribution/ui_decisions.json`, and `distribution/final_artifacts.json`
provide the bounded payload that the local `distributionWidgets` MCP server
validates and renders with the reusable HTML widget at
`ui://widget/distribution-review.html`. Codex should use that MCP widget when
available, and fall back to Markdown/chat review only when MCP rendering is not
available.

## Commands

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <input-file> --output-dir <workdir>
python scripts/run_distribution.py <input-file> --output-dir <workdir>/distribution --recipe <workdir>/suggested_recipe.json
```

The run script also supports a data-only mode:

```bash
python scripts/run_distribution.py <input-file> --output-dir <workdir>/distribution_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

## Legacy Functions

See `references/legacy_distribution_inventory.md` for the exact legacy
`plot_charts.*`, draw, layout and preparation functions used by the plugin.

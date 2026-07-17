# Scatter & Bubble Analysis

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/scatter-bubble-analysis) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Codex plugin for legacy Plotly scatter and bubble charts. The plugin reads CSV
or Excel data, infers or accepts chart mappings, canonicalizes the data once,
and renders scatter/bubble chart specs through the vendored legacy
`modules.charting.plot_charts` functions with audit and context outputs.

The plugin also writes an OpenAI-style local review handoff for the generated
scatter/bubble package. `scatter_bubble/run_intake.json` records finalized
recipe assumptions before rendering. `scatter_bubble/review_payload.json`,
`scatter_bubble/ui_decisions.json`, and `scatter_bubble/final_artifacts.json`
provide the bounded payload that the local `scatterBubbleWidgets` MCP server
validates and renders with the reusable HTML widget at
`ui://widget/scatter-bubble-review.html`. Codex should use that MCP widget when
available, and fall back to Markdown/chat review only when MCP rendering is not
available.

## Commands

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <input-file> --output-dir <workdir>
python scripts/run_scatter_bubble.py <input-file> --output-dir <workdir>/scatter_bubble --recipe <workdir>/suggested_recipe.json
```

The run script also supports a data-only mode:

```bash
python scripts/run_scatter_bubble.py <input-file> --output-dir <workdir>/scatter_bubble_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

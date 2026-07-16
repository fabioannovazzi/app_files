# Mix & Contribution Analysis

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/mix-contribution-analysis) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Legacy-backed mix, composition and contribution chart workflow for sales CSV/XLSX
files.

The plugin inspects the file, builds a canonical Polars dataset, and sends chart
requests through the vendored legacy charting pipeline. If a legacy chart cannot
be produced, the failure is recorded in the audit; the plugin does not draw a
new substitute chart.

## Run

```bash
python scripts/inspect_inputs.py <input-file> --output-dir <workdir>
python scripts/run_mix_contribution.py <input-file> --output-dir <workdir>/mix_contribution --recipe <workdir>/suggested_recipe.json
```

Outputs include chart PNGs, CSV/XLSX support files, JSON audit/context files,
and `mix_contribution_client_report.docx`.

The run script also supports a data-only mode:

```bash
python scripts/run_mix_contribution.py <input-file> --output-dir <workdir>/mix_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

## Scenario Notation

The plugin uses standard scenario abbreviations in chart period labels:

| Code | Meaning |
| --- | --- |
| `AC` | Actual |
| `PY` | Previous year |
| `PM` | Previous month |
| `PQ` | Previous quarter |
| `PL` | Plan |

The plugin also writes an OpenAI-style local review handoff for the generated
mix/contribution package. `mix_contribution/run_intake.json` records finalized
recipe assumptions before rendering. `mix_contribution/review_payload.json`,
`mix_contribution/ui_decisions.json`, and
`mix_contribution/final_artifacts.json` provide the bounded payload that the
local `mixContributionWidgets` MCP server validates and renders with the
reusable HTML widget at `ui://widget/mix-contribution-review.html`. Codex should
use that MCP widget when available, and fall back to Markdown/chat review only
when MCP rendering is not available.

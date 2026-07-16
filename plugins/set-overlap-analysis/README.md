# Set Overlap Analysis

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/set-overlap-analysis) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Deterministic Venn and UpSet chart plugin for CSV and Excel datasets.

This plugin covers one chart family: set overlap. It maps an item column and a
set column, optionally maps a period column, applies explicit recipe filters,
builds deterministic membership/intersection tables, and writes chart artifacts
plus structured context for Codex interpretation.

## What It Produces

- `inspection.json`
- `suggested_recipe.json`
- `set_overlap/used_recipe.json`
- `set_overlap/set_overlap_canonical.csv`
- `set_overlap/set_overlap_ranked_canonical.csv`
- `set_overlap/set_overlap_set_summary.csv`
- `set_overlap/set_overlap_item_sets.csv`
- `set_overlap/set_overlap_intersections.csv`
- `set_overlap/set_overlap_pairs.csv`
- `set_overlap/set_overlap_context.json`
- `set_overlap/set_overlap_audit.json`
- `set_overlap/upset.html`
- `set_overlap/upset.png` when Kaleido export succeeds
- `set_overlap/upset_small_multiples.html` when `upset_small_multiples` is requested
- `set_overlap/set_overlap_small_multiples_set_summary.csv`
- `set_overlap/set_overlap_small_multiples_intersections.csv`
- `set_overlap/venn.png` only when exactly two or three sets are selected
- `set_overlap/set_overlap_artifacts.zip`
- `set_overlap/run_intake.json`
- `set_overlap/review_payload.json`
- `set_overlap/ui_decisions.json`
- `set_overlap/final_artifacts.json`

## Recipe Shape

```json
{
  "schema_version": "1.0",
  "plugin": "set-overlap-analysis",
  "mappings": {
    "item_column": "SKU",
    "set_column": "Retailer",
    "period_column": "Period",
    "dimensions": ["Brand", "Category"]
  },
  "options": {
    "charts": ["upset", "venn"],
    "selected_period": "AC",
    "set_values": ["Retailer A", "Retailer B", "Retailer C"],
    "max_sets": 5,
    "aggregate_other_sets": true,
    "include_other_rank_with_explicit_sets": false,
    "min_intersection_size": 1,
    "highlighted_sets": [],
    "small_multiples_dimension": "Category",
    "small_multiples_max_panels": 6,
    "write_html": true,
    "filters": {
      "Category": {"include": ["Hair Color"]}
    }
  }
}
```

Filters may also be placed at the recipe root as `filters` or `filter_dict`.
They are applied before the canonical membership table is built, and the filter
audit is written into the context and chart title.

When `set_values` is empty, `max_sets` ranks sets by distinct item count. If
`aggregate_other_sets` is true, lower-ranked sets are collapsed into
`Other rank >N`, where `N` is the number of ranked sets retained. Explicit
`set_values` are preserved as requested; set
`include_other_rank_with_explicit_sets` to true only when the explicit set list
should also include an aggregated lower-rank row.

Use `charts: ["upset_small_multiples"]` plus `small_multiples_dimension` to
facet UpSet charts by a category-like column. Small multiples rank sets per
panel, so each category can have its own top markets plus `Other rank >N`.

## Reporting Chart Style

Generated chart artifacts use a reporting-style typography contract: every
visible text element in a chart uses one font size. This includes the title,
axis labels, value labels, legends, and set/category labels. Visual hierarchy is
created with position, spacing, line weight, and marks instead of larger title
text. Do not describe the output as IBCS-certified.

## Legacy Mapping

The implementation keeps the legacy semantics for this chart family where they
exist:

- UpSet membership matrix: `modules.charting.upset_helpers.build_upset_matrix`
- UpSet rendering: `modules.charting.upset_plot.plot_upset`
- Venn semantics: legacy Venn supports only two or three selected sets

The plugin does not use Streamlit/UI rendering paths.

## Run

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <input-file> --output-dir <workdir> --language en
python scripts/run_set_overlap.py <input-file> --output-dir <workdir>/set_overlap --recipe <workdir>/suggested_recipe.json
```

The run script also supports a data-only mode:

```bash
python scripts/run_set_overlap.py <input-file> --output-dir <workdir>/set_overlap_data --recipe <workdir>/suggested_recipe.json --artifact-mode data_only
```

`data_only` writes chart context JSON, chart data CSV, and audits without
PNG/HTML chart render artifacts.

## Local MCP Review UI

After `scripts/run_set_overlap.py` completes, Codex can use the local MCP server
to validate and render the generated review payload:

- `validate_set_overlap_review` validates `review_payload.json`.
- `render_set_overlap_review` renders `ui://widget/set-overlap-review.html`.

Use the widget for selected sets, exact intersections, pairwise overlaps, chart
audits, structured context, and generated artifacts. Keep simple mapping and
selected-set choices in Codex chat or native Plan-mode choices.

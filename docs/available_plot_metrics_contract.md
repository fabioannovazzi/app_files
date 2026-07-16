# Available Plot Metrics Contract

Downstream consumers must not guess which metrics a plugin can plot. A plugin
should expose a machine-readable `available_plot_metrics` contract that lists
direct and derived metrics after input inspection and canonical preparation. A
consumer can then request charts by capability ID and metric ID without
reverse-engineering legacy names or dataframe columns.

This is a design contract for plugin outputs. It does not replace each plugin's
deterministic chart preparation logic.

## Contract Shape

Each available metric record should include:

```json
{
  "metric_id": "Margin in %",
  "display_name": "Margin in %",
  "kind": "derived_ratio",
  "unit_semantics": "percent",
  "additive": false,
  "source_columns": ["Sales", "Margin"],
  "requires": ["Sales", "Margin"],
  "derived_from": "Margin / Sales",
  "valid_for": ["mix.bar", "mix.related_metrics_bar", "mix.stacked_column"],
  "preferred_as_related_metric": true,
  "calculation_stage": "canonical_preparation",
  "status": "available"
}
```

Required fields:

- `metric_id`: stable internal metric name used in chart specs.
- `display_name`: user-facing metric label.
- `kind`: one of `direct`, `canonical_direct`, `derived_ratio`, `derived_growth`,
  `derived_index`, or `provided_ratio`.
- `additive`: whether values can be summed across items and periods.
- `source_columns`: raw or canonical columns required to compute the metric.
- `requires`: metric dependencies a consumer must preserve in requests.
- `valid_for`: capability IDs or capability families where the metric can be
  requested.
- `status`: `available`, `blocked_missing_dependency`, or `not_applicable`.

Recommended fields:

- `unit_semantics`: `currency`, `count`, `price`, `percent`, `rate`, `share`,
  or `index`.
- `derived_from`: readable calculation formula for audit/review.
- `preferred_as_primary_metric`: whether it is a good chart-driving metric.
- `preferred_as_related_metric`: whether it is a good marker/overlay metric.
- `calculation_stage`: `inspection`, `canonical_preparation`,
  `legacy_chart_preparation`, or `provided`.
- `blocked_reason`: required when `status` is not `available`.

## Mix Contribution Metrics

For `mix-contribution-analysis`, the canonical metric contract should be based
on the same preparation used by chart rendering.

| Metric | Availability rule | Additive | Preferred role |
| --- | --- | --- | --- |
| `Sales` | Valid amount column exists. | Yes | Primary metric. |
| `Units` | Unit/quantity/volume width column exists. | Yes | Width metric; supporting metric. |
| `Unit Price` | `Sales` and `Units` exist. | No | Related metric; BarMekko height metric. |
| `Margin` | Margin/profit column exists. | Yes | Supporting metric. |
| `Margin in %` | `Sales + Margin` exist, or a provided margin percent column exists. | No | Related metric. |
| `Sales Growth Rate` | At least two selected periods with `Sales` exist. | No | Related metric for comparison bars. |

Selection priority for default related metrics:

1. `Sales Growth Rate`, when the chart has a valid comparison period window.
2. `Unit Price`, when sales and units are available.
3. `Margin in %`, when margin percent can be derived or normalized.
4. A user-specified explicit related marker metric.
5. A remaining numeric metric only as a fallback.

Explicit user choices should override default priority when the requested metric
is available and chart-compatible.

## Dependency Rule

For derived ratio metrics, the consumer must request or preserve the
additive dependencies rather than only the final ratio column when the chart
preparation needs to aggregate first.

Examples:

- `Unit Price` requires `Sales` and `Units`; it must be computed as
  aggregated `Sales / Units`.
- `Margin in %` requires `Sales` and `Margin`; it must be computed as
  aggregated `Margin / Sales`.
- `Sales Growth Rate` requires comparable period totals for `Sales`.

This prevents invalid behavior such as summing or averaging row-level prices and
percentages when the chart needs group-level ratios.

## Output Locations

When implemented, plugins should expose `available_plot_metrics` in:

- inspection output, so consumers can ask the user only valid follow-up
  questions;
- used recipe or preparation audit, so the run is reproducible;
- structured output context, so downstream report generation can cite which
  metrics were possible and which were selected.

The contract should be generated after recipe validation and canonical
preparation, because some metrics become available only after canonical columns
are created.

## Consumer Usage

Consumers should:

1. read plugin capability catalogs for chart/table options;
2. read `available_plot_metrics` for valid metrics;
3. intersect requested chart capability with valid metric roles;
4. request charts using capability IDs, metric IDs, dimensions, and period
   windows;
5. preserve dependencies in the request where derived metrics need aggregated
   calculation.

Consumers should not:

- infer metric availability from raw column names alone;
- request raw legacy helper names;
- request non-additive metrics where a chart requires additive totals, unless
  the plugin explicitly marks the metric as compatible;
- compute derived ratios itself when the plugin owns the canonical preparation.

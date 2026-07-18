# Chart Selection Playbook: period_comparison

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `period_comparison.by_period` | `period_by_period_gap` | `axis` | `comparison_metric` | required `comparison_series` | Question asks which individual periods have the largest current-vs-baseline gaps. |
| `period_comparison.comparison_table` | `summary_exact_values` | `filter` | `comparison_metric` | required `comparison_window` | Question asks for exact summary current, baseline, delta, and percent-delta values. |
| `period_comparison.dot` | `gap_between_two_values` | `axis` | `comparison_metric` | required `comparison_item` | Question asks for low-clutter comparison of two values across items. |
| `period_comparison.horizontal_waterfall` | `additive_reconciliation` | `axis` | `comparison_metric` | required `bridge_component_period` | Question asks how period variances add from baseline total to current total. |
| `period_comparison.multitier_column` | `compact_side_by_side_period_comparison` | `axis` | `comparison_metric` | required `comparison_series` | Question asks for compact side-by-side current and baseline period columns. |
| `period_comparison.slope` | `endpoint_direction_and_relative_change` | `axis` | `comparison_metric` | required `comparison_item` | Question asks for direction and magnitude between two endpoints. |
| `period_comparison.time_series_table` | `exact_values` | `axis_or_table` | `comparison_metric` | `none` | Question asks for citeable exact period values, deltas, or percent deltas. |
| `period_comparison.trend` | `trajectory_shape` | `axis` | `comparison_metric` | required `comparison_series` | Question asks for ordered period trajectory: acceleration, reversal, narrowing, widening, or seasonality. |

## High-Overlap Pairs

- `period_comparison.by_period` <> `period_comparison.multitier_column`: `resolved` (`0` errors, `0` warnings)
- `period_comparison.by_period` <> `period_comparison.trend`: `resolved` (`0` errors, `0` warnings)
- `period_comparison.multitier_column` <> `period_comparison.trend`: `resolved` (`0` errors, `0` warnings)

## Capability Details

### `period_comparison.by_period`

- Selection emphasis: `period_by_period_gap`
- Visual grammar: `period_gap_comparison`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs to compare current and baseline period values across each month or week and see where gaps are largest.
- Avoid when: Avoid when the story is only the smooth trajectory shape or a single reconciled total movement.
- Primary decision cue: Question asks which individual periods have the largest current-vs-baseline gaps.
- Requires question focus: `period_gap`, `current_vs_baseline_by_period`
- Reject decision cues: `asks for smooth trajectory`, `asks for additive reconciliation`, `asks for exact table`
- Forbidden question focus: `trajectory_shape`, `bridge_reconciliation`, `exact_period_values`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_series`
- Close competitors: `period_comparison.trend`, `period_comparison.multitier_column`, `period_comparison.time_series_table`, `period_comparison.horizontal_waterfall`, `period_comparison.dot`
- Positive question: Which months explain the AC/PY sales gap?
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.by_period`, `period_comparison.trend`, `period_comparison.multitier_column`, `period_comparison.time_series_table`, `period_comparison.horizontal_waterfall`
- Disambiguation: Clarify whether the intended focus is `period_by_period_gap`, `trajectory_shape`, `compact_side_by_side_period_comparison`, `exact_values`, `additive_reconciliation`.
- High-overlap pair evidence:
  - `period_comparison.multitier_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `period_comparison.trend`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `period_comparison.comparison_table`

- Selection emphasis: `summary_exact_values`
- Visual grammar: `comparison_table`
- Analysis tasks: `ranking_and_comparison`, `evidence_and_reporting_tables`
- Best when: The reader needs compact exact AC/PY totals and deltas by comparison row.
- Avoid when: Avoid when the message depends on the period path or monthly sequencing.
- Primary decision cue: Question asks for exact summary current, baseline, delta, and percent-delta values.
- Requires question focus: `exact_summary_values`, `comparison_table`
- Reject decision cues: `asks for visual trend`, `asks for bridge reconciliation`, `asks for distribution`
- Forbidden question focus: `trajectory_shape`, `bridge_reconciliation`, `distribution_shape`
- Period role: `filter`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_window`
- Close competitors: `period_comparison.time_series_table`, `period_comparison.dot`
- Positive question: Give exact current, prior-year, delta, and percent-delta sales values.
- Ambiguous question: Compare categories by sales.
- Ambiguous candidates: `period_comparison.comparison_table`, `period_comparison.time_series_table`, `period_comparison.dot`, `mix.bar`, `mix.multitier_bar`
- Disambiguation: Clarify whether the intended focus is `summary_exact_values`, `exact_values`, `gap_between_two_values`, `ranked_single_metric_comparison`, `dimension_period_values_and_delta`.

### `period_comparison.dot`

- Selection emphasis: `gap_between_two_values`
- Visual grammar: `dot_gap`
- Analysis tasks: `time_and_period_movement`, `ranking_and_comparison`
- Best when: The reader needs a low-clutter comparison of two values across categories, panels, or periods.
- Avoid when: Avoid when the month-by-month path or additive reconciliation matters.
- Primary decision cue: Question asks for low-clutter comparison of two values across items.
- Requires question focus: `two_value_gap`, `low_clutter_comparison`
- Reject decision cues: `asks for monthly path`, `asks for additive bridge`, `asks for exact table`
- Forbidden question focus: `period_path`, `bridge_reconciliation`, `exact_values`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_item`
- Close competitors: `period_comparison.slope`, `period_comparison.by_period`, `period_comparison.multitier_column`, `mix.multitier_bar`, `period_comparison.comparison_table`
- Positive question: Compare AC/PY sales gaps across categories with low clutter.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.dot`, `period_comparison.slope`, `period_comparison.by_period`, `period_comparison.multitier_column`, `mix.multitier_bar`
- Disambiguation: Clarify whether the intended focus is `gap_between_two_values`, `endpoint_direction_and_relative_change`, `period_by_period_gap`, `compact_side_by_side_period_comparison`, `dimension_period_values_and_delta`.

### `period_comparison.horizontal_waterfall`

- Selection emphasis: `additive_reconciliation`
- Visual grammar: `period_bridge`
- Analysis tasks: `time_and_period_movement`, `variance_and_bridge`
- Best when: The reader needs to see how period variances add from previous total to current total.
- Avoid when: Avoid when values are non-additive or the message is trend shape rather than reconciliation.
- Primary decision cue: Question asks how period variances add from baseline total to current total.
- Requires question focus: `bridge_reconciliation`, `additive_period_variance`
- Reject decision cues: `asks for non-additive values`, `asks for line shape`, `asks for endpoint slope`
- Forbidden question focus: `non_additive_metric`, `trajectory_shape`, `endpoint_change`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `bridge_component_period`
- Close competitors: `period_comparison.trend`, `period_comparison.by_period`, `variance.scenario_bridge`, `period_comparison.slope`
- Positive question: How do period variances reconcile prior-year sales to current sales?
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.horizontal_waterfall`, `period_comparison.trend`, `period_comparison.by_period`, `variance.scenario_bridge`, `period_comparison.slope`
- Disambiguation: Clarify whether the intended focus is `additive_reconciliation`, `trajectory_shape`, `period_by_period_gap`, `scenario_reconciliation`, `endpoint_direction_and_relative_change`.

### `period_comparison.multitier_column`

- Selection emphasis: `compact_side_by_side_period_comparison`
- Visual grammar: `comparison_column`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs a compact executive AC/PY period comparison with clear column contrast.
- Avoid when: Avoid when line shape, exact values, or total bridge reconciliation is the main message.
- Primary decision cue: Question asks for compact side-by-side current and baseline period columns.
- Requires question focus: `side_by_side_periods`, `current_vs_baseline_values`
- Reject decision cues: `asks for line trajectory`, `asks for exact table`, `asks for bridge reconciliation`
- Forbidden question focus: `trajectory_shape`, `exact_period_values`, `bridge_reconciliation`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_series`
- Close competitors: `period_comparison.trend`, `period_comparison.by_period`, `period_comparison.dot`, `mix.multitier_bar`
- Positive question: Show compact AC/PY monthly sales columns.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.multitier_column`, `period_comparison.trend`, `period_comparison.by_period`, `period_comparison.dot`, `mix.multitier_bar`
- Disambiguation: Clarify whether the intended focus is `compact_side_by_side_period_comparison`, `trajectory_shape`, `period_by_period_gap`, `gap_between_two_values`, `dimension_period_values_and_delta`.
- High-overlap pair evidence:
  - `period_comparison.by_period`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `period_comparison.trend`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `period_comparison.slope`

- Selection emphasis: `endpoint_direction_and_relative_change`
- Visual grammar: `slope_endpoint_change`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs direction and magnitude of change between two endpoints, especially across multiple comparable items.
- Avoid when: Avoid when intermediate months, exact values, or additive bridge components are essential.
- Primary decision cue: Question asks for direction and magnitude between two endpoints.
- Requires question focus: `endpoint_change`, `relative_direction`
- Reject decision cues: `asks for intermediate period path`, `asks for additive bridge`, `asks for exact values`
- Forbidden question focus: `period_path`, `bridge_reconciliation`, `exact_values`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_item`
- Close competitors: `period_comparison.dot`, `period_comparison.trend`, `period_comparison.horizontal_waterfall`, `mix.multitier_bar`
- Positive question: Show endpoint direction and magnitude of category sales changes.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.slope`, `period_comparison.dot`, `period_comparison.trend`, `period_comparison.horizontal_waterfall`, `mix.multitier_bar`
- Disambiguation: Clarify whether the intended focus is `endpoint_direction_and_relative_change`, `gap_between_two_values`, `trajectory_shape`, `additive_reconciliation`, `dimension_period_values_and_delta`.

### `period_comparison.time_series_table`

- Selection emphasis: `exact_values`
- Visual grammar: `period_table`
- Analysis tasks: `time_and_period_movement`
- Best when: The report needs citeable period values, deltas, and percent deltas rather than a primarily visual reading.
- Avoid when: Avoid as the only visual when the reader must quickly perceive shape, gap, or reconciliation.
- Primary decision cue: Question asks for citeable exact period values, deltas, or percent deltas.
- Requires question focus: `exact_period_values`, `period_table`
- Reject decision cues: `asks for quick visual shape`, `asks for bridge reconciliation`, `asks for low-clutter comparison`
- Forbidden question focus: `trajectory_shape`, `bridge_reconciliation`, `two_value_gap`
- Period role: `axis_or_table`
- Metric roles: `comparison_metric`
- Dimension roles: `none`
- Close competitors: `period_comparison.trend`, `period_comparison.by_period`, `period_comparison.comparison_table`
- Positive question: Give citeable monthly AC/PY sales values and variances.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.time_series_table`, `period_comparison.trend`, `period_comparison.by_period`, `period_comparison.comparison_table`, `mix.area`
- Disambiguation: Clarify whether the intended focus is `exact_values`, `trajectory_shape`, `period_by_period_gap`, `summary_exact_values`, `trend_with_cumulative_or_share_area`.

### `period_comparison.trend`

- Selection emphasis: `trajectory_shape`
- Visual grammar: `line_time_series`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs to see the ordered period path: acceleration, reversal, narrowing, widening, or seasonality.
- Avoid when: Avoid when exact values, total reconciliation, or a two-endpoint before/after comparison is the main message.
- Primary decision cue: Question asks for ordered period trajectory: acceleration, reversal, narrowing, widening, or seasonality.
- Requires question focus: `trajectory_shape`, `current_vs_baseline_period_axis`
- Reject decision cues: `asks for exact values`, `asks for additive reconciliation`, `asks for endpoint-only comparison`
- Forbidden question focus: `exact_period_values`, `bridge_reconciliation`, `endpoint_change`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `comparison_series`
- Close competitors: `period_comparison.by_period`, `period_comparison.time_series_table`, `period_comparison.slope`, `period_comparison.horizontal_waterfall`, `mix.area`, `mix.column`, `mix.stacked_column`, `mix.timeline`, `period_comparison.multitier_column`
- Positive question: How did monthly cosmetics sales evolve versus previous year?
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `period_comparison.trend`, `period_comparison.by_period`, `period_comparison.time_series_table`, `period_comparison.slope`, `period_comparison.horizontal_waterfall`
- Disambiguation: Clarify whether the intended focus is `trajectory_shape`, `period_by_period_gap`, `exact_values`, `endpoint_direction_and_relative_change`, `additive_reconciliation`.
- High-overlap pair evidence:
  - `period_comparison.by_period`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `period_comparison.multitier_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

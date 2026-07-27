# Chart Selection Playbook: mix

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `mix.area` | `trend_with_cumulative_or_share_area` | `axis` | `primary_metric` | optional `optional_component_dimension` | Question asks for contribution or share as an area trend across ordered periods. |
| `mix.bar` | `ranked_single_metric_comparison` | `filter` | `primary_metric` | required `category` | Question asks to rank categories by one selected metric in a scope. |
| `mix.barmekko` | `width_metric_times_height_metric` | `filter` | `width_metric`, `height_metric` | required `width_category`, `height_category` | Question asks for variable-width composition where width and height are separate metrics. |
| `mix.cohort_lost_stacked_column` | `lost_cohort_contribution` | `axis` | `primary_metric` | required `lost_or_last_active_cohort` | Question asks how much contribution comes from entities by last active or lost cohort. |
| `mix.cohort_since_stacked_column` | `since_cohort_contribution` | `axis` | `primary_metric` | required `first_active_cohort` | Question asks how much contribution comes from entities by first active or since cohort. |
| `mix.column` | `total_metric_by_period_or_scope` | `axis` | `primary_metric` | `none` | Question asks for total metric columns by period or selected scope without composition. |
| `mix.column_overlay` | `total_plus_related_marker` | `axis` | `primary_metric`, `related_marker_metric` | `none` | Question asks for total columns with a secondary related metric marker. |
| `mix.like_for_like_column` | `same_population_total_change` | `axis` | `primary_metric` | required `stable_population_flag` | Question asks for total change among the same entities present in both periods. |
| `mix.like_for_like_stacked_column` | `same_population_composition_change` | `axis` | `primary_metric` | required `stable_population_flag`, `component_dimension` | Question asks for mix change among the same entities present in both periods. |
| `mix.marimekko` | `two_dimension_share_and_size` | `filter` | `primary_metric` | required `width_category`, `stack_category`; optional `optional_panel` | Question asks for composition across two categorical dimensions using segment share and size. |
| `mix.multitier_bar` | `dimension_period_values_and_delta` | `axis` | `comparison_metric` | required `dimension_member`; optional `optional_panel` | Question asks for one dimension's values in two periods and the delta, optionally by panels. |
| `mix.pareto` | `ranked_contribution_and_cumulative_share` | `filter` | `primary_metric` | required `category` | Question asks which few items explain most of the total using cumulative share. |
| `mix.stacked_bar` | `composition_within_ranked_totals` | `filter` | `primary_metric` | required `category`, `component_category` | Question asks for composition within ranked category totals. |
| `mix.stacked_bar_overlay` | `primary_rank_plus_secondary_marker` | `filter` | `primary_metric`, `related_marker_metric` | required `category` | Question asks to rank categories by a primary metric while overlaying a secondary marker. |
| `mix.stacked_column` | `composition_change_over_periods` | `axis` | `primary_metric` | required `component_dimension` | Question asks for total and component composition across periods. |
| `mix.stacked_pareto` | `concentration_with_component_breakdown` | `filter` | `primary_metric` | required `category`, `component_dimension` | Question asks for concentration and component breakdown together. |
| `mix.timeline` | `single_metric_trend_shape` | `axis` | `primary_metric` | `none` | Question asks for one metric's trend path across ordered periods without AC/PY comparison. |

## High-Overlap Pairs

- `mix.cohort_lost_stacked_column` <> `mix.cohort_since_stacked_column`: `resolved` (`0` errors, `0` warnings)
- `mix.cohort_lost_stacked_column` <> `mix.like_for_like_column`: `resolved` (`0` errors, `0` warnings)
- `mix.cohort_since_stacked_column` <> `mix.like_for_like_column`: `resolved` (`0` errors, `0` warnings)
- `mix.marimekko` <> `mix.stacked_bar`: `resolved` (`0` errors, `0` warnings)
- `mix.column` <> `mix.timeline`: `resolved` (`0` errors, `0` warnings)

## Capability Details

### `mix.area`

- Selection emphasis: `trend_with_cumulative_or_share_area`
- Visual grammar: `area_time_series`
- Analysis tasks: `time_and_period_movement`, `composition_and_mix`
- Best when: The reader needs a time-series area view for absolute contribution or share over periods.
- Avoid when: Avoid when precise line trajectory or side-by-side period gaps are clearer.
- Primary decision cue: Question asks for contribution or share as an area trend across ordered periods.
- Requires question focus: `area_trend`, `contribution_or_share_over_time`
- Reject decision cues: `asks for precise line trajectory`, `asks for AC/PY gap`, `asks for exact period table`
- Forbidden question focus: `single_line_trend`, `period_gap`, `exact_period_values`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: optional `optional_component_dimension`
- Close competitors: `mix.timeline`, `mix.stacked_column`, `period_comparison.trend`
- Positive question: Show sales contribution as an area trend across months.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `mix.area`, `mix.timeline`, `mix.stacked_column`, `period_comparison.trend`, `mix.column`
- Disambiguation: Clarify whether the intended focus is `trend_with_cumulative_or_share_area`, `single_metric_trend_shape`, `composition_change_over_periods`, `trajectory_shape`, `total_metric_by_period_or_scope`.

### `mix.bar`

- Selection emphasis: `ranked_single_metric_comparison`
- Visual grammar: `ranked_bar`
- Analysis tasks: `ranking_and_comparison`
- Best when: The reader needs a sorted comparison of one additive metric across items for one selected scope or period.
- Avoid when: Avoid when composition, hierarchy, time movement, or a second metric relationship is the point.
- Primary decision cue: Question asks to rank categories by one selected metric in a scope.
- Requires question focus: `single_metric_rank`, `category_comparison`
- Reject decision cues: `asks for composition within bars`, `asks for period delta`, `asks for cumulative Pareto share`
- Forbidden question focus: `composition`, `period_delta`, `pareto_concentration`
- Period role: `filter`
- Metric roles: `primary_metric`
- Dimension roles: required `category`
- Close competitors: `mix.stacked_bar`, `mix.stacked_bar_overlay`, `mix.multitier_bar`, `mix.pareto`, `scatter.scatter`
- Positive question: Rank categories by sales for a selected scope.
- Ambiguous question: Compare categories by sales.
- Ambiguous candidates: `mix.bar`, `mix.stacked_bar`, `mix.stacked_bar_overlay`, `mix.multitier_bar`, `mix.pareto`
- Disambiguation: Clarify whether the intended focus is `ranked_single_metric_comparison`, `composition_within_ranked_totals`, `primary_rank_plus_secondary_marker`, `dimension_period_values_and_delta`, `ranked_contribution_and_cumulative_share`.

### `mix.barmekko`

- Selection emphasis: `width_metric_times_height_metric`
- Visual grammar: `barmekko`
- Analysis tasks: `composition_and_mix`
- Best when: The reader needs a variable-width composition where width and height represent different metrics.
- Avoid when: Avoid without a meaningful width metric or when the area encoding would be hard to read.
- Primary decision cue: Question asks for variable-width composition where width and height are separate metrics.
- Requires question focus: `variable_width_composition`, `width_and_height_metrics`
- Reject decision cues: `asks for two-dimension share only`, `asks for bubble relationship`, `asks for simple ranked bars`
- Forbidden question focus: `two_dimension_share`, `metric_relationship`, `single_metric_rank`
- Period role: `filter`
- Metric roles: `width_metric`, `height_metric`
- Dimension roles: required `width_category`, `height_category`
- Close competitors: `mix.marimekko`, `scatter.bubble`, `mix.stacked_bar_overlay`
- Positive question: Show category width and retailer height as a variable-width composition.
- Ambiguous question: Show sales mix and composition.
- Ambiguous candidates: `mix.barmekko`, `mix.marimekko`, `scatter.bubble`, `mix.stacked_bar_overlay`, `mix.area`
- Disambiguation: Clarify whether the intended focus is `width_metric_times_height_metric`, `two_dimension_share_and_size`, `two_metric_relationship_plus_size`, `primary_rank_plus_secondary_marker`, `trend_with_cumulative_or_share_area`.

### `mix.cohort_lost_stacked_column`

- Selection emphasis: `lost_cohort_contribution`
- Visual grammar: `cohort_stacked_column`
- Analysis tasks: `cohort_and_population`
- Best when: The reader needs to see contribution by lost or last-active cohort.
- Avoid when: Avoid for simple time trend or non-cohort composition.
- Primary decision cue: Question asks how much contribution comes from entities by last active or lost cohort.
- Requires question focus: `lost_cohort`, `entity_population_change`
- Reject decision cues: `asks for first active cohort`, `asks for same-population change`, `asks for general composition`
- Forbidden question focus: `since_cohort`, `like_for_like_population`, `composition_only`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: required `lost_or_last_active_cohort`
- Close competitors: `mix.cohort_since_stacked_column`, `mix.like_for_like_column`, `mix.stacked_column`
- Positive question: How much sales contribution comes from products by last active month?
- Ambiguous question: How did the population change across periods?
- Ambiguous candidates: `mix.cohort_lost_stacked_column`, `mix.cohort_since_stacked_column`, `mix.like_for_like_column`, `mix.stacked_column`, `mix.like_for_like_stacked_column`
- Disambiguation: Clarify whether the intended focus is `lost_cohort_contribution`, `since_cohort_contribution`, `same_population_total_change`, `composition_change_over_periods`, `same_population_composition_change`.
- High-overlap pair evidence:
  - `mix.cohort_since_stacked_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `mix.like_for_like_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.cohort_since_stacked_column`

- Selection emphasis: `since_cohort_contribution`
- Visual grammar: `cohort_stacked_column`
- Analysis tasks: `cohort_and_population`
- Best when: The reader needs to see contribution by first-active cohort over periods.
- Avoid when: Avoid for simple time trend or non-cohort composition.
- Primary decision cue: Question asks how much contribution comes from entities by first active or since cohort.
- Requires question focus: `since_cohort`, `entity_population_change`
- Reject decision cues: `asks for lost cohort`, `asks for same-population change`, `asks for period gap`
- Forbidden question focus: `lost_cohort`, `like_for_like_population`, `period_gap`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: required `first_active_cohort`
- Close competitors: `mix.cohort_lost_stacked_column`, `mix.like_for_like_column`, `mix.stacked_column`
- Positive question: How much sales contribution comes from products by first active month?
- Ambiguous question: How did the population change across periods?
- Ambiguous candidates: `mix.cohort_since_stacked_column`, `mix.cohort_lost_stacked_column`, `mix.like_for_like_column`, `mix.stacked_column`, `mix.like_for_like_stacked_column`
- Disambiguation: Clarify whether the intended focus is `since_cohort_contribution`, `lost_cohort_contribution`, `same_population_total_change`, `composition_change_over_periods`, `same_population_composition_change`.
- High-overlap pair evidence:
  - `mix.cohort_lost_stacked_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `mix.like_for_like_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.column`

- Selection emphasis: `total_metric_by_period_or_scope`
- Visual grammar: `total_column`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs a compact total metric column view across selected periods or scopes.
- Avoid when: Avoid when component composition, relationship, or detailed period path is needed.
- Primary decision cue: Question asks for total metric columns by period or selected scope without composition.
- Requires question focus: `total_metric`, `column_summary`
- Reject decision cues: `asks for component mix`, `asks for line trajectory`, `asks for related marker metric`
- Forbidden question focus: `composition`, `single_line_trend`, `secondary_metric_marker`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: `none`
- Close competitors: `mix.column_overlay`, `period_comparison.trend`, `mix.like_for_like_column`, `mix.stacked_column`, `mix.timeline`
- Positive question: Show total sales by month as compact columns.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `mix.column`, `mix.column_overlay`, `period_comparison.trend`, `mix.like_for_like_column`, `mix.stacked_column`
- Disambiguation: Clarify whether the intended focus is `total_metric_by_period_or_scope`, `total_plus_related_marker`, `trajectory_shape`, `same_population_total_change`, `composition_change_over_periods`.
- High-overlap pair evidence:
  - `mix.timeline`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.column_overlay`

- Selection emphasis: `total_plus_related_marker`
- Visual grammar: `total_column_with_related_metric`
- Analysis tasks: `metric_relationship`
- Best when: The reader needs total metric movement with a related marker shown in the same compact view.
- Avoid when: Avoid when the relationship between metrics is the main analytical object.
- Primary decision cue: Question asks for total columns with a secondary related metric marker.
- Requires question focus: `total_metric`, `secondary_metric_marker`
- Reject decision cues: `asks for ranked categories with marker`, `asks for two-metric scatter`, `asks for plain total`
- Forbidden question focus: `rank_plus_marker`, `scatter_relationship`, `plain_total`
- Period role: `axis`
- Metric roles: `primary_metric`, `related_marker_metric`
- Dimension roles: `none`
- Close competitors: `mix.column`, `mix.stacked_bar_overlay`, `scatter.scatter`
- Positive question: Show total monthly sales with sales-share marker context.
- Ambiguous question: Show the relationship between metrics.
- Ambiguous candidates: `mix.column_overlay`, `mix.column`, `mix.stacked_bar_overlay`, `scatter.scatter`, `scatter.bubble`
- Disambiguation: Clarify whether the intended focus is `total_plus_related_marker`, `total_metric_by_period_or_scope`, `primary_rank_plus_secondary_marker`, `relationship_between_two_metrics`, `two_metric_relationship_plus_size`.

### `mix.like_for_like_column`

- Selection emphasis: `same_population_total_change`
- Visual grammar: `like_for_like_total_column`
- Analysis tasks: `cohort_and_population`
- Best when: The reader needs total change on a stable like-for-like population.
- Avoid when: Avoid when population churn or mix composition is the main finding.
- Primary decision cue: Question asks for total change among the same entities present in both periods.
- Requires question focus: `like_for_like_population`, `total_change`
- Reject decision cues: `asks for composition change`, `asks for new or lost cohorts`, `asks for all-population total`
- Forbidden question focus: `like_for_like_composition`, `cohort_change`, `all_population_total`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: required `stable_population_flag`
- Close competitors: `mix.column`, `mix.like_for_like_stacked_column`, `mix.cohort_since_stacked_column`, `mix.cohort_lost_stacked_column`
- Positive question: How did sales change for the same products active in both selected months?
- Ambiguous question: How did the population change across periods?
- Ambiguous candidates: `mix.like_for_like_column`, `mix.column`, `mix.like_for_like_stacked_column`, `mix.cohort_since_stacked_column`, `mix.cohort_lost_stacked_column`
- Disambiguation: Clarify whether the intended focus is `same_population_total_change`, `total_metric_by_period_or_scope`, `same_population_composition_change`, `since_cohort_contribution`, `lost_cohort_contribution`.
- High-overlap pair evidence:
  - `mix.cohort_lost_stacked_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `mix.cohort_since_stacked_column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.like_for_like_stacked_column`

- Selection emphasis: `same_population_composition_change`
- Visual grammar: `like_for_like_stacked_column`
- Analysis tasks: `composition_and_mix`, `cohort_and_population`
- Best when: The reader needs like-for-like total movement and composition together.
- Avoid when: Avoid when the population is not stable or exact detail is required.
- Primary decision cue: Question asks for mix change among the same entities present in both periods.
- Requires question focus: `like_for_like_population`, `composition_change`
- Reject decision cues: `asks for total-only change`, `asks for lost/since cohorts`, `asks for simple stacked composition`
- Forbidden question focus: `like_for_like_total`, `cohort_change`, `all_population_composition`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: required `stable_population_flag`, `component_dimension`
- Close competitors: `mix.like_for_like_column`, `mix.stacked_column`
- Positive question: How did same-product sales mix by category change across the selected months?
- Ambiguous question: Show sales mix and composition.
- Ambiguous candidates: `mix.like_for_like_stacked_column`, `mix.like_for_like_column`, `mix.stacked_column`, `mix.area`, `mix.barmekko`
- Disambiguation: Clarify whether the intended focus is `same_population_composition_change`, `same_population_total_change`, `composition_change_over_periods`, `trend_with_cumulative_or_share_area`, `width_metric_times_height_metric`.

### `mix.marimekko`

- Selection emphasis: `two_dimension_share_and_size`
- Visual grammar: `marimekko`
- Analysis tasks: `composition_and_mix`
- Best when: The reader needs to see composition across two categorical dimensions where both width and height carry meaning.
- Avoid when: Avoid when categories are too many, exact comparison matters, or the question is a simple ranking.
- Primary decision cue: Question asks for composition across two categorical dimensions using segment share and size.
- Requires question focus: `two_dimension_share`, `composition_size`
- Reject decision cues: `asks for separate width and height metrics`, `asks for ranked bars`, `asks for period variance`
- Forbidden question focus: `width_height_metrics`, `single_metric_rank`, `period_variance`
- Period role: `filter`
- Metric roles: `primary_metric`
- Dimension roles: required `width_category`, `stack_category`; optional `optional_panel`
- Close competitors: `mix.barmekko`, `mix.stacked_bar`, `mix.multitier_bar`
- Positive question: Show sales composition across category and retailer.
- Ambiguous question: Show sales mix and composition.
- Ambiguous candidates: `mix.marimekko`, `mix.barmekko`, `mix.stacked_bar`, `mix.multitier_bar`, `mix.area`
- Disambiguation: Clarify whether the intended focus is `two_dimension_share_and_size`, `width_metric_times_height_metric`, `composition_within_ranked_totals`, `dimension_period_values_and_delta`, `trend_with_cumulative_or_share_area`.
- High-overlap pair evidence:
  - `mix.stacked_bar`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.multitier_bar`

- Selection emphasis: `dimension_period_values_and_delta`
- Visual grammar: `period_comparison_multitier_bar`
- Analysis tasks: `time_and_period_movement`, `ranking_and_comparison`
- Best when: The reader needs one dimension split into rows, with sales for two periods and their difference visible together; if a second dimension is needed, it becomes small-multiple panels.
- Avoid when: Avoid when the question is categorical hierarchy, composition, single-period ranking, or continuous trend shape.
- Primary decision cue: Question asks for one dimension's values in two periods and the delta, optionally by panels.
- Requires question focus: `dimension_period_delta`, `current_vs_baseline_values`
- Reject decision cues: `asks for continuous trend`, `asks for composition`, `asks for root-cause bridge`
- Forbidden question focus: `single_line_trend`, `composition`, `root_cause_variance`
- Period role: `axis`
- Metric roles: `comparison_metric`
- Dimension roles: required `dimension_member`; optional `optional_panel`
- Close competitors: `period_comparison.dot`, `period_comparison.slope`, `period_comparison.multitier_column`, `mix.bar`, `mix.marimekko`, `mix.stacked_bar`
- Positive question: Show category sales in two periods and the difference, split into retailer panels.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `mix.multitier_bar`, `period_comparison.dot`, `period_comparison.slope`, `period_comparison.multitier_column`, `mix.bar`
- Disambiguation: Clarify whether the intended focus is `dimension_period_values_and_delta`, `gap_between_two_values`, `endpoint_direction_and_relative_change`, `compact_side_by_side_period_comparison`, `ranked_single_metric_comparison`.

### `mix.pareto`

- Selection emphasis: `ranked_contribution_and_cumulative_share`
- Visual grammar: `pareto`
- Analysis tasks: `ranking_and_comparison`
- Best when: The reader needs to identify the few categories that explain most of the metric.
- Avoid when: Avoid when component composition, period movement, or nested hierarchy is the main message.
- Primary decision cue: Question asks which few items explain most of the total using cumulative share.
- Requires question focus: `pareto_concentration`, `cumulative_share`
- Reject decision cues: `asks for component breakdown`, `asks for simple ranking only`, `asks for time trend`
- Forbidden question focus: `component_breakdown`, `single_metric_rank`, `time_trend`
- Period role: `filter`
- Metric roles: `primary_metric`
- Dimension roles: required `category`
- Close competitors: `mix.bar`, `mix.stacked_pareto`
- Positive question: Find the few categories that explain most sales.
- Ambiguous question: Compare categories by sales.
- Ambiguous candidates: `mix.pareto`, `mix.bar`, `mix.stacked_pareto`, `mix.multitier_bar`, `period_comparison.comparison_table`
- Disambiguation: Clarify whether the intended focus is `ranked_contribution_and_cumulative_share`, `ranked_single_metric_comparison`, `concentration_with_component_breakdown`, `dimension_period_values_and_delta`, `summary_exact_values`.

### `mix.stacked_bar`

- Selection emphasis: `composition_within_ranked_totals`
- Visual grammar: `stacked_bar`
- Analysis tasks: `composition_and_mix`
- Best when: The reader needs both total size and component composition across categories.
- Avoid when: Avoid when exact component comparison or time trend is more important than composition.
- Primary decision cue: Question asks for composition within ranked category totals.
- Requires question focus: `ranked_composition`, `stacked_total`
- Reject decision cues: `asks for simple rank only`, `asks for related marker`, `asks for two-period delta`
- Forbidden question focus: `single_metric_rank`, `secondary_metric_marker`, `period_delta`
- Period role: `filter`
- Metric roles: `primary_metric`
- Dimension roles: required `category`, `component_category`
- Close competitors: `mix.bar`, `mix.multitier_bar`, `mix.stacked_bar_overlay`, `mix.marimekko`, `mix.stacked_column`, `mix.stacked_pareto`
- Positive question: Show sales totals and composition by retailer within categories.
- Ambiguous question: Show sales mix and composition.
- Ambiguous candidates: `mix.stacked_bar`, `mix.bar`, `mix.multitier_bar`, `mix.stacked_bar_overlay`, `mix.marimekko`
- Disambiguation: Clarify whether the intended focus is `composition_within_ranked_totals`, `ranked_single_metric_comparison`, `dimension_period_values_and_delta`, `primary_rank_plus_secondary_marker`, `two_dimension_share_and_size`.
- High-overlap pair evidence:
  - `mix.marimekko`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `mix.stacked_bar_overlay`

- Selection emphasis: `primary_rank_plus_secondary_marker`
- Visual grammar: `bar_with_related_metric_marker`
- Analysis tasks: `metric_relationship`
- Best when: The reader needs ranked contribution plus a related non-additive marker such as price, margin percentage, or growth.
- Avoid when: Avoid when the secondary metric deserves a full relationship plot or when composition is the point.
- Primary decision cue: Question asks to rank categories by a primary metric while overlaying a secondary marker.
- Requires question focus: `rank_plus_marker`, `secondary_metric_marker`
- Reject decision cues: `asks for total column marker`, `asks for scatter relationship`, `asks for stacked composition`
- Forbidden question focus: `total_plus_marker`, `scatter_relationship`, `composition`
- Period role: `filter`
- Metric roles: `primary_metric`, `related_marker_metric`
- Dimension roles: required `category`
- Close competitors: `mix.bar`, `scatter.scatter`, `scatter.bubble`, `mix.barmekko`, `mix.column_overlay`, `mix.stacked_bar`
- Positive question: Rank category sales while overlaying sales-share context.
- Ambiguous question: Show the relationship between metrics.
- Ambiguous candidates: `mix.stacked_bar_overlay`, `mix.bar`, `scatter.scatter`, `scatter.bubble`, `mix.barmekko`
- Disambiguation: Clarify whether the intended focus is `primary_rank_plus_secondary_marker`, `ranked_single_metric_comparison`, `relationship_between_two_metrics`, `two_metric_relationship_plus_size`, `width_metric_times_height_metric`.

### `mix.stacked_column`

- Selection emphasis: `composition_change_over_periods`
- Visual grammar: `stacked_column`
- Analysis tasks: `time_and_period_movement`, `composition_and_mix`
- Best when: The reader needs to see total and mix composition across periods or comparable scopes.
- Avoid when: Avoid when exact values or simple trend shape matters more than composition.
- Primary decision cue: Question asks for total and component composition across periods.
- Requires question focus: `composition_over_time`, `stacked_periods`
- Reject decision cues: `asks for line trajectory`, `asks for exact values`, `asks for same-population-only mix`
- Forbidden question focus: `single_line_trend`, `exact_period_values`, `like_for_like_population`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: required `component_dimension`
- Close competitors: `period_comparison.trend`, `mix.stacked_bar`, `mix.column`, `mix.area`, `mix.cohort_lost_stacked_column`, `mix.cohort_since_stacked_column`, `mix.like_for_like_stacked_column`, `mix.timeline`
- Positive question: Show recent monthly sales mix by category.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `mix.stacked_column`, `period_comparison.trend`, `mix.stacked_bar`, `mix.column`, `mix.area`
- Disambiguation: Clarify whether the intended focus is `composition_change_over_periods`, `trajectory_shape`, `composition_within_ranked_totals`, `total_metric_by_period_or_scope`, `trend_with_cumulative_or_share_area`.

### `mix.stacked_pareto`

- Selection emphasis: `concentration_with_component_breakdown`
- Visual grammar: `stacked_pareto`
- Analysis tasks: `composition_and_mix`
- Best when: The reader needs Pareto concentration plus stacked composition by another dimension or class.
- Avoid when: Avoid when a plain Pareto or plain stacked bar would be easier to read.
- Primary decision cue: Question asks for concentration and component breakdown together.
- Requires question focus: `pareto_concentration`, `component_breakdown`
- Reject decision cues: `asks for simple Pareto only`, `asks for stacked totals only`, `asks for metric relationship`
- Forbidden question focus: `pareto_only`, `stacked_total_only`, `metric_relationship`
- Period role: `filter`
- Metric roles: `primary_metric`
- Dimension roles: required `category`, `component_dimension`
- Close competitors: `mix.pareto`, `mix.stacked_bar`
- Positive question: Show concentration and component composition together.
- Ambiguous question: Show sales mix and composition.
- Ambiguous candidates: `mix.stacked_pareto`, `mix.pareto`, `mix.stacked_bar`, `mix.area`, `mix.barmekko`
- Disambiguation: Clarify whether the intended focus is `concentration_with_component_breakdown`, `ranked_contribution_and_cumulative_share`, `composition_within_ranked_totals`, `trend_with_cumulative_or_share_area`, `width_metric_times_height_metric`.

### `mix.timeline`

- Selection emphasis: `single_metric_trend_shape`
- Visual grammar: `line_time_series`
- Analysis tasks: `time_and_period_movement`
- Best when: The reader needs the trend path of the primary mix metric across ordered periods.
- Avoid when: Avoid when composition, hierarchy, or AC/PY period comparison is the main message.
- Primary decision cue: Question asks for one metric's trend path across ordered periods without AC/PY comparison.
- Requires question focus: `single_line_trend`, `ordered_periods`
- Reject decision cues: `asks for AC/PY comparison`, `asks for composition over time`, `asks for exact period table`
- Forbidden question focus: `current_vs_baseline`, `composition_over_time`, `exact_period_values`
- Period role: `axis`
- Metric roles: `primary_metric`
- Dimension roles: `none`
- Close competitors: `period_comparison.trend`, `mix.column`, `mix.area`, `mix.stacked_column`
- Positive question: Show the single sales trend across months without AC/PY comparison.
- Ambiguous question: How did sales change over time?
- Ambiguous candidates: `mix.timeline`, `period_comparison.trend`, `mix.column`, `mix.area`, `mix.stacked_column`
- Disambiguation: Clarify whether the intended focus is `single_metric_trend_shape`, `trajectory_shape`, `total_metric_by_period_or_scope`, `trend_with_cumulative_or_share_area`, `composition_change_over_periods`.
- High-overlap pair evidence:
  - `mix.column`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

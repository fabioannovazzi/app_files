# Chart Selection Manifest Rebuild

## Counts

- `source_items`: `73`
- `artifacts`: `73`
- `capabilities`: `48`
- `analysis_tasks`: `9`
- `generated_manifest_capabilities`: `48`
- `generated_manifest_capabilities_without_gallery_examples`: `0`

## Coverage Gaps

- `generated_manifest_capabilities_without_gallery_examples`: `0`
- `gallery_capabilities_without_generated_manifest_records`: `0`

## Selector Audit

- Result: `pass`
- Capabilities checked: `48`
- Duplicate selector signatures: `0`
- Pairwise high-overlap groups: `7`
- Pairwise high-overlap pairs: `22`
- Pairwise unresolved pairs: `0`
- Generated-manifest-only capabilities: `0`

## Selection Examples

- Capabilities with examples: `48`
- Positive questions: `48`
- Negative questions: `220`
- Ambiguous questions: `48`

## Structured Decision Cues

- Capabilities with complete cue fields: `48`
- High-overlap cue collisions: `0`

## Rendering Variants

- Artifacts with rendering variant metadata: `73`
- Selector levels: `base_capability`=`45`, `capability_choice`=`6`, `rendering_variant_choice`=`22`
- Layout variants: `nested_drilldown`=`2`, `panelled`=`2`, `single`=`39`, `small_multiples`=`22`, `table`=`8`

## Role Registry And Invocation Contracts

- `chart_roles`: `58`
- `profile_roles`: `12`
- `used_chart_roles`: `54`
- `chart_roles_missing_mapping`: `0`
- Invocation contract statuses: `parameter_contract_ready`=`48`

## Period Movement Treatments

- `mix.area`: `trend_with_cumulative_or_share_area` (area_time_series)
  - Best when: The reader needs a time-series area view for absolute contribution or share over periods.
  - Avoid when: Avoid when precise line trajectory or side-by-side period gaps are clearer.
- `mix.column`: `total_metric_by_period_or_scope` (total_column)
  - Best when: The reader needs a compact total metric column view across selected periods or scopes.
  - Avoid when: Avoid when component composition, relationship, or detailed period path is needed.
- `mix.multitier_bar`: `dimension_period_values_and_delta` (period_comparison_multitier_bar)
  - Best when: The reader needs one dimension split into rows, with sales for two periods and their difference visible together; if a second dimension is needed, it becomes small-multiple panels.
  - Avoid when: Avoid when the question is categorical hierarchy, composition, single-period ranking, or continuous trend shape.
- `mix.stacked_column`: `composition_change_over_periods` (stacked_column)
  - Best when: The reader needs to see total and mix composition across periods or comparable scopes.
  - Avoid when: Avoid when exact values or simple trend shape matters more than composition.
- `mix.timeline`: `single_metric_trend_shape` (line_time_series)
  - Best when: The reader needs the trend path of the primary mix metric across ordered periods.
  - Avoid when: Avoid when composition, hierarchy, or AC/PY period comparison is the main message.
- `period_comparison.by_period`: `period_by_period_gap` (period_gap_comparison)
  - Best when: The reader needs to compare current and baseline period values across each month or week and see where gaps are largest.
  - Avoid when: Avoid when the story is only the smooth trajectory shape or a single reconciled total movement.
- `period_comparison.dot`: `gap_between_two_values` (dot_gap)
  - Best when: The reader needs a low-clutter comparison of two values across categories, panels, or periods.
  - Avoid when: Avoid when the month-by-month path or additive reconciliation matters.
- `period_comparison.horizontal_waterfall`: `additive_reconciliation` (period_bridge)
  - Best when: The reader needs to see how period variances add from previous total to current total.
  - Avoid when: Avoid when values are non-additive or the message is trend shape rather than reconciliation.
- `period_comparison.multitier_column`: `compact_side_by_side_period_comparison` (comparison_column)
  - Best when: The reader needs a compact executive AC/PY period comparison with clear column contrast.
  - Avoid when: Avoid when line shape, exact values, or total bridge reconciliation is the main message.
- `period_comparison.slope`: `endpoint_direction_and_relative_change` (slope_endpoint_change)
  - Best when: The reader needs direction and magnitude of change between two endpoints, especially across multiple comparable items.
  - Avoid when: Avoid when intermediate months, exact values, or additive bridge components are essential.
- `period_comparison.time_series_table`: `exact_values` (period_table)
  - Best when: The report needs citeable period values, deltas, and percent deltas rather than a primarily visual reading.
  - Avoid when: Avoid as the only visual when the reader must quickly perceive shape, gap, or reconciliation.
- `period_comparison.trend`: `trajectory_shape` (line_time_series)
  - Best when: The reader needs to see the ordered period path: acceleration, reversal, narrowing, widening, or seasonality.
  - Avoid when: Avoid when exact values, total reconciliation, or a two-endpoint before/after comparison is the main message.

## Validation

- No structural validation issues.

## Semantic Probes

- Probes: `16`
- Failed: `0`
- `PASS` `monthly_trend_shape` -> `time_and_period_movement`: Show how monthly sales moved over time.
- `PASS` `monthly_exact_values` -> `time_and_period_movement`: Show exact monthly values and deltas for citation.
- `PASS` `monthly_reconciliation` -> `time_and_period_movement`: Explain how monthly variances add up to the total change.
- `PASS` `one_month_rank` -> `ranking_and_comparison`: Compare brands in one selected month.
- `PASS` `two_metric_relationship` -> `metric_relationship`: Show the relationship between sales and distribution.
- `PASS` `composition_shift` -> `composition_and_mix`: Show how mix composition changed across periods.
- `PASS` `distribution_shape` -> `distribution`: Show the distribution of unit price.
- `PASS` `variance_reconciliation` -> `variance_and_bridge`: Reconcile total movement from baseline to current with a plain bridge.
- `PASS` `variance_dimension_split` -> `variance_and_bridge`: Which categories account for the total variance?
- `PASS` `variance_parent_child_drilldown` -> `variance_and_bridge`: Which categories drove variance, and which brands explain the selected category moves?
- `PASS` `variance_root_cause_total` -> `variance_and_bridge`: Which ordered root-cause path explains the total movement?
- `PASS` `variance_root_cause_exploded` -> `variance_and_bridge`: Which ordered root-cause path explains the total movement, and what explains the selected root-cause drivers?
- `PASS` `variance_root_cause_component` -> `variance_and_bridge`: Which dimension combinations explain the price component of sales movement?
- `PASS` `variance_pvm` -> `variance_and_bridge`: How much of the value movement is due to price, units, and mix?
- `PASS` `set_intersections` -> `set_overlap`: Show overlaps across several sets.
- `PASS` `product_evidence_table` -> `evidence_and_reporting_tables`: Show product-level evidence for selected attribute bundles.

## Ten Review Iterations

1. Looked for: Whether artifact entries and capability semantics were mixed. Correction: Split generated artifacts from capability records.
2. Looked for: Tautological when-to-use values. Correction: Capability records now use best_when and avoid_when; artifact fallback text is not used for selection.
3. Looked for: Whether line/trend is represented as a period-axis chart. Correction: period_comparison.trend has visual_grammar=line_time_series and period_semantics.role=axis.
4. Looked for: Scatter/bubble period leakage. Correction: scatter capabilities use period_semantics.role=filter and supports_period_axis=false.
5. Looked for: Different objectives among period charts. Correction: Added selection_emphasis values for trajectory, gap scan, exact values, endpoint change, and reconciliation.
6. Looked for: Bar-family ambiguity. Correction: Separated ranked bar, stacked composition, related metric overlay, and hierarchical multitier grammar.
7. Looked for: Distribution chart distinctions. Correction: Separated frequency shape, spread summary, individual observations, cumulative distribution, and smoothed density.
8. Looked for: Variance chart distinctions. Correction: Separated scenario bridge, dimension bridge, parent-child bridge, root-cause bridges, and PVM ladder.
9. Looked for: Whether all existing artifacts still map to a capability. Correction: Preserved every gallery item as an example under its capability.
10. Looked for: Whether the result can distinguish valid alternatives rather than choose one chart per question. Correction: Added competing_capability_ids and selection_emphasis so broad tasks can have multiple valid treatments.

# Chart Selection Playbook: scatter_bubble

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `scatter.bubble` | `two_metric_relationship_plus_size` | `filter` | `x_metric`, `y_metric`, `size_metric` | required `point_dimension`; optional `optional_panel` | Question asks for relationship between two metrics with a third metric encoded by size. |
| `scatter.scatter` | `relationship_between_two_metrics` | `filter` | `x_metric`, `y_metric` | required `point_dimension`; optional `optional_panel` | Question asks for relationship between two metrics without size encoding. |

## High-Overlap Pairs

- None

## Capability Details

### `scatter.bubble`

- Selection emphasis: `two_metric_relationship_plus_size`
- Visual grammar: `bubble_relationship`
- Analysis tasks: `metric_relationship`
- Best when: The reader needs x/y relationship plus magnitude encoded by bubble size.
- Avoid when: Avoid when bubble size would obscure the relationship or when period movement is the question.
- Primary decision cue: Question asks for relationship between two metrics with a third metric encoded by size.
- Requires question focus: `scatter_relationship`, `size_encoding`
- Reject decision cues: `asks for unweighted relationship`, `asks for ranked bars`, `asks for time trend`
- Forbidden question focus: `plain_scatter`, `single_metric_rank`, `time_trend`
- Period role: `filter`
- Metric roles: `x_metric`, `y_metric`, `size_metric`
- Dimension roles: required `point_dimension`; optional `optional_panel`
- Close competitors: `scatter.scatter`, `mix.stacked_bar_overlay`, `mix.barmekko`
- Positive question: Do units and sales share relate, weighted by sales?
- Ambiguous question: Show the relationship between metrics.
- Ambiguous candidates: `scatter.bubble`, `scatter.scatter`, `mix.stacked_bar_overlay`, `mix.barmekko`, `mix.column_overlay`
- Disambiguation: Clarify whether the intended focus is `two_metric_relationship_plus_size`, `relationship_between_two_metrics`, `primary_rank_plus_secondary_marker`, `width_metric_times_height_metric`, `total_plus_related_marker`.

### `scatter.scatter`

- Selection emphasis: `relationship_between_two_metrics`
- Visual grammar: `scatter_relationship`
- Analysis tasks: `metric_relationship`
- Best when: The reader needs to see association, clusters, quadrants, or outliers between two metrics.
- Avoid when: Avoid for time trends, one-dimensional ranking, or exact tables.
- Primary decision cue: Question asks for relationship between two metrics without size encoding.
- Requires question focus: `scatter_relationship`, `two_metrics`
- Reject decision cues: `asks for bubble size`, `asks for category ranking`, `asks for period gap`
- Forbidden question focus: `size_encoding`, `single_metric_rank`, `period_gap`
- Period role: `filter`
- Metric roles: `x_metric`, `y_metric`
- Dimension roles: required `point_dimension`; optional `optional_panel`
- Close competitors: `scatter.bubble`, `mix.stacked_bar_overlay`, `mix.bar`, `mix.column_overlay`
- Positive question: Do units and sales share relate without size encoding?
- Ambiguous question: Show the relationship between metrics.
- Ambiguous candidates: `scatter.scatter`, `scatter.bubble`, `mix.stacked_bar_overlay`, `mix.bar`, `mix.column_overlay`
- Disambiguation: Clarify whether the intended focus is `relationship_between_two_metrics`, `two_metric_relationship_plus_size`, `primary_rank_plus_secondary_marker`, `ranked_single_metric_comparison`, `total_plus_related_marker`.

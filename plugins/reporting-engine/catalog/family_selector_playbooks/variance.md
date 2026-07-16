# Chart Selection Playbook: variance

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `variance.exploded_variance_bridge` | `parent_bridge_with_child_drilldowns` | `filter` | `variance_metric` | required `parent_driver`, `child_driver` | Question asks for one fixed parent dimension variance bridge plus child drilldowns for selected rows. |
| `variance.price_volume_mix` | `pvm_decomposition_comparison` | `filter` | `value_metric`, `volume_metric`, `price_or_rate_metric` | required `period_or_scenario_pair` | Question explicitly asks how movement decomposes into price, volume, and mix effects. |
| `variance.root_cause_component_bridge` | `component_level_root_cause` | `filter` | `variance_metric` | required `variance_component`, `component_root_cause_driver` | Question asks which drivers explain a selected component-level variance. |
| `variance.root_cause_exploded_bridge` | `root_cause_path_with_nested_drilldowns` | `filter` | `variance_metric` | required `root_cause_driver_sequence`; optional `optional_nested_root_cause_driver_sequence` | Question asks for ordered root-cause path plus nested drilldown for selected drivers. |
| `variance.root_cause_total_bridge` | `root_cause_total_movement` | `filter` | `variance_metric` | required `root_cause_driver_sequence` | Question asks for ordered root-cause path explaining total movement. |
| `variance.scenario_bridge` | `scenario_reconciliation` | `filter` | `variance_metric` | required `variance_step` | Question asks for a plain reconciliation from baseline or scenario to current total. |
| `variance.total_by_dimension_bridge` | `total_delta_split_by_dimension` | `filter` | `variance_metric` | required `dimension_member` | Question asks which members of one selected dimension account for total variance. |

## High-Overlap Pairs

- `variance.root_cause_exploded_bridge` <> `variance.root_cause_total_bridge`: `resolved` (`0` errors, `0` warnings)
- `variance.exploded_variance_bridge` <> `variance.root_cause_component_bridge`: `resolved` (`0` errors, `0` warnings)

## Capability Details

### `variance.exploded_variance_bridge`

- Selection emphasis: `parent_bridge_with_child_drilldowns`
- Visual grammar: `parent_child_variance_bridge`
- Analysis tasks: `variance_and_bridge`
- Best when: Use when the question names one parent grouping dimension and one fixed second decomposition dimension to explain selected parent-row variance moves in the same visual.
- Avoid when: Avoid when only one dimension is requested, when the second dimension is not meaningful within each parent member, when the task is a variable mixed-dimension root-cause ordering, when PVM mechanics are required, or when exact tabular detail is the deliverable.
- Primary decision cue: Question asks for one fixed parent dimension variance bridge plus child drilldowns for selected rows.
- Requires question focus: `fixed_parent_child_drilldown`, `variance_bridge`
- Reject decision cues: `asks for variable root-cause sequence`, `asks for plain bridge`, `asks for PVM mechanics`
- Forbidden question focus: `root_cause_sequence`, `scenario_bridge`, `pvm_decomposition`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `parent_driver`, `child_driver`
- Close competitors: `variance.root_cause_exploded_bridge`, `variance.root_cause_component_bridge`, `variance.total_by_dimension_bridge`
- Positive question: Which categories drove variance, and which brands explain the selected category moves?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.exploded_variance_bridge`, `variance.root_cause_exploded_bridge`, `variance.root_cause_component_bridge`, `variance.total_by_dimension_bridge`, `period_comparison.horizontal_waterfall`
- Disambiguation: Clarify whether the intended focus is `parent_bridge_with_child_drilldowns`, `root_cause_path_with_nested_drilldowns`, `component_level_root_cause`, `total_delta_split_by_dimension`, `additive_reconciliation`.
- High-overlap pair evidence:
  - `variance.root_cause_component_bridge`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `variance.price_volume_mix`

- Selection emphasis: `pvm_decomposition_comparison`
- Visual grammar: `price_volume_mix_ladder`
- Analysis tasks: `variance_and_bridge`
- Best when: Use only when the business question explicitly asks how value movement decomposes into price, volume, and mix effects, and the dataset has compatible value, units/volume, and price or derived price semantics.
- Avoid when: Avoid for generic variance explanations, one-dimension splits, root-cause ordering, or any dataset without compatible value, volume, and rate semantics at the same grain.
- Primary decision cue: Question explicitly asks how movement decomposes into price, volume, and mix effects.
- Requires question focus: `pvm_decomposition`, `price_volume_mix`
- Reject decision cues: `asks for generic variance bridge`, `asks for dimension split`, `asks for root-cause ordering`
- Forbidden question focus: `scenario_bridge`, `dimension_variance`, `root_cause_sequence`
- Period role: `filter`
- Metric roles: `value_metric`, `volume_metric`, `price_or_rate_metric`
- Dimension roles: required `period_or_scenario_pair`
- Close competitors: `variance.scenario_bridge`, `variance.root_cause_total_bridge`, `variance.total_by_dimension_bridge`
- Positive question: How much of the sales movement is due to price, units, and mix?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.price_volume_mix`, `variance.scenario_bridge`, `variance.root_cause_total_bridge`, `variance.total_by_dimension_bridge`, `period_comparison.horizontal_waterfall`
- Disambiguation: Clarify whether the intended focus is `pvm_decomposition_comparison`, `scenario_reconciliation`, `root_cause_total_movement`, `total_delta_split_by_dimension`, `additive_reconciliation`.

### `variance.root_cause_component_bridge`

- Selection emphasis: `component_level_root_cause`
- Visual grammar: `root_cause_component_bridge`
- Analysis tasks: `variance_and_bridge`
- Best when: Use when the question asks why one variance component changed, not why the overall total changed; the chart drills into the drivers of that component-level variance.
- Avoid when: Avoid when the report needs the total movement root-cause sequence, a simple dimension split, the plain total bridge, or PVM mechanics.
- Primary decision cue: Question asks which drivers explain a selected component-level variance.
- Requires question focus: `component_root_cause`, `selected_variance_component`
- Reject decision cues: `asks for total root-cause path`, `asks for plain bridge`, `asks for PVM mechanics`
- Forbidden question focus: `total_root_cause`, `scenario_bridge`, `pvm_decomposition`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `variance_component`, `component_root_cause_driver`
- Close competitors: `variance.root_cause_total_bridge`, `variance.total_by_dimension_bridge`, `variance.exploded_variance_bridge`, `variance.root_cause_exploded_bridge`
- Positive question: Which drivers explain the selected root-cause component of sales movement?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.root_cause_component_bridge`, `variance.root_cause_total_bridge`, `variance.total_by_dimension_bridge`, `variance.exploded_variance_bridge`, `variance.root_cause_exploded_bridge`
- Disambiguation: Clarify whether the intended focus is `component_level_root_cause`, `root_cause_total_movement`, `total_delta_split_by_dimension`, `parent_bridge_with_child_drilldowns`, `root_cause_path_with_nested_drilldowns`.
- High-overlap pair evidence:
  - `variance.exploded_variance_bridge`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `variance.root_cause_exploded_bridge`

- Selection emphasis: `root_cause_path_with_nested_drilldowns`
- Visual grammar: `root_cause_exploded_bridge`
- Analysis tasks: `variance_and_bridge`
- Best when: Use when the question asks for a variable mixed-dimension root-cause variance path and also asks to explain selected root-cause drivers with nested root-cause bridge drilldowns.
- Avoid when: Avoid when the question names a fixed parent dimension and fixed child decomposition dimension; use variance.exploded_variance_bridge instead. Avoid when only a one-level root-cause path is needed, or when exact tabular detail is the deliverable.
- Primary decision cue: Question asks for ordered root-cause path plus nested drilldown for selected drivers.
- Requires question focus: `root_cause_sequence`, `nested_driver_drilldown`
- Reject decision cues: `asks for fixed parent-child dimensions`, `asks for total path only`, `asks for PVM mechanics`
- Forbidden question focus: `fixed_parent_child_drilldown`, `total_root_cause_only`, `pvm_decomposition`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `root_cause_driver_sequence`; optional `optional_nested_root_cause_driver_sequence`
- Close competitors: `variance.root_cause_total_bridge`, `variance.exploded_variance_bridge`, `variance.root_cause_component_bridge`
- Positive question: Which ordered root-cause path explains the total sales movement, and what explains the selected root-cause driver?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.root_cause_exploded_bridge`, `variance.root_cause_total_bridge`, `variance.exploded_variance_bridge`, `variance.root_cause_component_bridge`, `period_comparison.horizontal_waterfall`
- Disambiguation: Clarify whether the intended focus is `root_cause_path_with_nested_drilldowns`, `root_cause_total_movement`, `parent_bridge_with_child_drilldowns`, `component_level_root_cause`, `additive_reconciliation`.
- High-overlap pair evidence:
  - `variance.root_cause_total_bridge`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `variance.root_cause_total_bridge`

- Selection emphasis: `root_cause_total_movement`
- Visual grammar: `root_cause_total_bridge`
- Analysis tasks: `variance_and_bridge`
- Best when: Use when the question asks for the ordered root-cause sequence behind the total movement across available dimensions, and the output should show which driver path explains the overall delta.
- Avoid when: Avoid for a simple total bridge, a one-dimension split, a component-only root-cause question, or PVM decomposition.
- Primary decision cue: Question asks for ordered root-cause path explaining total movement.
- Requires question focus: `root_cause_sequence`, `total_movement`
- Reject decision cues: `asks for selected component`, `asks for nested drilldown`, `asks for fixed dimension split`
- Forbidden question focus: `component_root_cause`, `nested_driver_drilldown`, `dimension_variance`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `root_cause_driver_sequence`
- Close competitors: `variance.root_cause_exploded_bridge`, `variance.total_by_dimension_bridge`, `variance.root_cause_component_bridge`, `variance.scenario_bridge`, `variance.price_volume_mix`
- Positive question: Which ordered root-cause path explains the total sales movement?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.root_cause_total_bridge`, `variance.root_cause_exploded_bridge`, `variance.total_by_dimension_bridge`, `variance.root_cause_component_bridge`, `variance.scenario_bridge`
- Disambiguation: Clarify whether the intended focus is `root_cause_total_movement`, `root_cause_path_with_nested_drilldowns`, `total_delta_split_by_dimension`, `component_level_root_cause`, `scenario_reconciliation`.
- High-overlap pair evidence:
  - `variance.root_cause_exploded_bridge`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `variance.scenario_bridge`

- Selection emphasis: `scenario_reconciliation`
- Visual grammar: `variance_waterfall`
- Analysis tasks: `variance_and_bridge`
- Best when: Use for the plain bridge from one baseline total to one current total when the message is the additive reconciliation itself, not a ranked dimension split, root-cause path, or PVM mechanics.
- Avoid when: Avoid when the question names a dimension to split by, asks for nested drilldowns, asks why via root-cause ordering, asks for price/volume/mix, or when trend shape is the message.
- Primary decision cue: Question asks for a plain reconciliation from baseline or scenario to current total.
- Requires question focus: `scenario_bridge`, `baseline_to_current_total`
- Reject decision cues: `asks for dimension contributors`, `asks for root-cause ordering`, `asks for PVM mechanics`
- Forbidden question focus: `dimension_variance`, `root_cause_sequence`, `pvm_decomposition`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `variance_step`
- Close competitors: `period_comparison.horizontal_waterfall`, `variance.total_by_dimension_bridge`, `variance.root_cause_total_bridge`, `variance.price_volume_mix`
- Positive question: Reconcile total sales from baseline to current with a plain bridge.
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.scenario_bridge`, `period_comparison.horizontal_waterfall`, `variance.total_by_dimension_bridge`, `variance.root_cause_total_bridge`, `variance.price_volume_mix`
- Disambiguation: Clarify whether the intended focus is `scenario_reconciliation`, `additive_reconciliation`, `total_delta_split_by_dimension`, `root_cause_total_movement`, `pvm_decomposition_comparison`.

### `variance.total_by_dimension_bridge`

- Selection emphasis: `total_delta_split_by_dimension`
- Visual grammar: `dimension_variance_bridge`
- Analysis tasks: `variance_and_bridge`
- Best when: Use when the question explicitly asks how the total delta is distributed across members of one named dimension, such as category, retailer, region, brand, or channel.
- Avoid when: Avoid when the reader needs the generic total bridge, a nested parent/child drilldown, an ordered root-cause path across multiple dimensions, or price-volume-mix mechanics.
- Primary decision cue: Question asks which members of one selected dimension account for total variance.
- Requires question focus: `dimension_variance`, `total_delta_split`
- Reject decision cues: `asks for root-cause ordering`, `asks for child drilldowns`, `asks for plain scenario bridge`
- Forbidden question focus: `root_cause_sequence`, `fixed_parent_child_drilldown`, `scenario_bridge`
- Period role: `filter`
- Metric roles: `variance_metric`
- Dimension roles: required `dimension_member`
- Close competitors: `variance.scenario_bridge`, `variance.root_cause_total_bridge`, `variance.exploded_variance_bridge`, `variance.price_volume_mix`, `variance.root_cause_component_bridge`
- Positive question: Which categories account for the total sales variance?
- Ambiguous question: Explain the sales variance.
- Ambiguous candidates: `variance.total_by_dimension_bridge`, `variance.scenario_bridge`, `variance.root_cause_total_bridge`, `variance.exploded_variance_bridge`, `variance.price_volume_mix`
- Disambiguation: Clarify whether the intended focus is `total_delta_split_by_dimension`, `scenario_reconciliation`, `root_cause_total_movement`, `parent_bridge_with_child_drilldowns`, `pvm_decomposition_comparison`.

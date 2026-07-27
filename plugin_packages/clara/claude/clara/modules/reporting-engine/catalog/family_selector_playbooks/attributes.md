# Chart Selection Playbook: attributes

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `attributes.attribute_bridge_table` | `current_vs_emerging_signal_alignment` | `none` | `current_signal_metric`, `emerging_signal_metric`, `alignment_metric` | required `signal_bundle`, `cohort_layer` | Question asks how current attribute signals align with or differ from emerging signals. |
| `attributes.attribute_bundle_comparison_table` | `bundle_share_and_index_evidence` | `none` | `focus_share`, `baseline_share`, `delta_metric`, `index_metric` | required `attribute_bundle` | Question asks for exact attribute bundle shares, deltas, or index evidence. |
| `attributes.product_signal_evidence_table` | `product_level_grounding` | `none` | `product_signal_score`, `validation_metric` | required `product`, `signal_bundle` | Question asks which products support a selected signal or attribute bundle. |
| `attributes.rank_weighted_visibility_table` | `rank_weighted_visibility` | `none` | `gross_weight`, `incremental_weight`, `cumulative_weight`, `robustness_metric` | required `rank_or_lane` | Question asks which attributes have rank-weighted visibility evidence. |

## High-Overlap Pairs

- None

## Capability Details

### `attributes.attribute_bridge_table`

- Selection emphasis: `current_vs_emerging_signal_alignment`
- Visual grammar: `attribute_bridge_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs to compare current winners with emerging signals and see alignment or divergence.
- Avoid when: Avoid when only one cohort layer exists.
- Primary decision cue: Question asks how current attribute signals align with or differ from emerging signals.
- Requires question focus: `attribute_signal_alignment`, `current_vs_emerging`
- Reject decision cues: `asks for product rows`, `asks for simple rank visibility`, `asks for numeric time trend`
- Forbidden question focus: `product_level_evidence`, `rank_weighted_visibility`, `time_trend`
- Period role: `none`
- Metric roles: `current_signal_metric`, `emerging_signal_metric`, `alignment_metric`
- Dimension roles: required `signal_bundle`, `cohort_layer`
- Close competitors: `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`
- Positive question: How do current winning attribute bundles align or diverge from emerging signals?
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`, `funnel.stage_table`
- Disambiguation: Clarify whether the intended focus is `current_vs_emerging_signal_alignment`, `bundle_share_and_index_evidence`, `product_level_grounding`, `rank_weighted_visibility`, `stage_counts_and_conversion`.

### `attributes.attribute_bundle_comparison_table`

- Selection emphasis: `bundle_share_and_index_evidence`
- Visual grammar: `attribute_evidence_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs exact bundle evidence for current winners or emerging signals.
- Avoid when: Avoid for product-level validation or shelf visibility decomposition.
- Primary decision cue: Question asks for exact attribute bundle shares, deltas, or index evidence.
- Requires question focus: `attribute_bundle_metrics`, `share_delta_index`
- Reject decision cues: `asks for product examples`, `asks for bridge-style signal movement`, `asks for charted trend`
- Forbidden question focus: `product_level_evidence`, `attribute_bridge`, `time_trend`
- Period role: `none`
- Metric roles: `focus_share`, `baseline_share`, `delta_metric`, `index_metric`
- Dimension roles: required `attribute_bundle`
- Close competitors: `attributes.attribute_bridge_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`
- Positive question: Show exact share, delta, and index evidence for selected attribute bundles.
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `attributes.attribute_bundle_comparison_table`, `attributes.attribute_bridge_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`, `funnel.stage_table`
- Disambiguation: Clarify whether the intended focus is `bundle_share_and_index_evidence`, `current_vs_emerging_signal_alignment`, `product_level_grounding`, `rank_weighted_visibility`, `stage_counts_and_conversion`.

### `attributes.product_signal_evidence_table`

- Selection emphasis: `product_level_grounding`
- Visual grammar: `product_evidence_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs product-level support for selected bundles or standout examples.
- Avoid when: Avoid for ranking category-wide signal prevalence.
- Primary decision cue: Question asks which products support a selected signal or attribute bundle.
- Requires question focus: `product_level_evidence`, `signal_grounding`
- Reject decision cues: `asks for aggregate bundle index`, `asks for ranked visibility only`, `asks for variance bridge`
- Forbidden question focus: `aggregate_attribute_index`, `rank_weighted_visibility`, `variance_bridge`
- Period role: `none`
- Metric roles: `product_signal_score`, `validation_metric`
- Dimension roles: required `product`, `signal_bundle`
- Close competitors: `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.rank_weighted_visibility_table`
- Positive question: Which products provide evidence for the selected attribute signal?
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `attributes.product_signal_evidence_table`, `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.rank_weighted_visibility_table`, `funnel.stage_table`
- Disambiguation: Clarify whether the intended focus is `product_level_grounding`, `current_vs_emerging_signal_alignment`, `bundle_share_and_index_evidence`, `rank_weighted_visibility`, `stage_counts_and_conversion`.

### `attributes.rank_weighted_visibility_table`

- Selection emphasis: `rank_weighted_visibility`
- Visual grammar: `visibility_evidence_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs visibility, incremental lane contribution, or alpha robustness evidence.
- Avoid when: Avoid as demand, sales, or causality evidence.
- Primary decision cue: Question asks which attributes have rank-weighted visibility evidence.
- Requires question focus: `rank_weighted_visibility`, `attribute_ranking`
- Reject decision cues: `asks for product rows`, `asks for exact bundle share table`, `asks for time movement`
- Forbidden question focus: `product_level_evidence`, `bundle_share_index`, `time_trend`
- Period role: `none`
- Metric roles: `gross_weight`, `incremental_weight`, `cumulative_weight`, `robustness_metric`
- Dimension roles: required `rank_or_lane`
- Close competitors: `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`
- Positive question: Which attribute bundles have rank-weighted visibility evidence?
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `attributes.rank_weighted_visibility_table`, `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`, `funnel.stage_table`
- Disambiguation: Clarify whether the intended focus is `rank_weighted_visibility`, `current_vs_emerging_signal_alignment`, `bundle_share_and_index_evidence`, `product_level_grounding`, `stage_counts_and_conversion`.

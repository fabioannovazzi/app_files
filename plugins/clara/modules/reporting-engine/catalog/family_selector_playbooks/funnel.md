# Chart Selection Playbook: funnel

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `funnel.stage_table` | `stage_counts_and_conversion` | `none` | `stage_start_count`, `stage_pass_count` | required `ordered_stage` | Question asks for ordered funnel stage counts or conversion rates. |

## High-Overlap Pairs

- None

## Capability Details

### `funnel.stage_table`

- Selection emphasis: `stage_counts_and_conversion`
- Visual grammar: `funnel_stage_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs exact stage counts, conversion rates, and drop-offs.
- Avoid when: Avoid when a visual shape is more important than exact stage evidence.
- Primary decision cue: Question asks for ordered funnel stage counts or conversion rates.
- Requires question focus: `funnel_stages`, `conversion_rates`
- Reject decision cues: `asks for distribution`, `asks for period trend`, `asks for set overlap`
- Forbidden question focus: `distribution_shape`, `time_trend`, `set_overlap`
- Period role: `none`
- Metric roles: `stage_start_count`, `stage_pass_count`
- Dimension roles: required `ordered_stage`
- Close competitors: `none`
- Positive question: What is the stage conversion funnel?
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `funnel.stage_table`, `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`
- Disambiguation: Clarify whether the intended focus is `stage_counts_and_conversion`, `current_vs_emerging_signal_alignment`, `bundle_share_and_index_evidence`, `product_level_grounding`, `rank_weighted_visibility`.

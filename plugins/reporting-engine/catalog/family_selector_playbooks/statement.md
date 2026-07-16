# Chart Selection Playbook: statement

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `statement.pnl_table` | `structured_statement_values` | `axis_or_table` | `statement_value` | required `statement_line_item` | Question asks for structured P&L or statement line-item values. |

## High-Overlap Pairs

- None

## Capability Details

### `statement.pnl_table`

- Selection emphasis: `structured_statement_values`
- Visual grammar: `pnl_statement_table`
- Analysis tasks: `evidence_and_reporting_tables`
- Best when: The reader needs a P&L-style table with business rows and comparison columns.
- Avoid when: Avoid for exploratory charting or relationship analysis.
- Primary decision cue: Question asks for structured P&L or statement line-item values.
- Requires question focus: `statement_table`, `line_item_values`
- Reject decision cues: `asks for charted trend`, `asks for distribution`, `asks for variance bridge`
- Forbidden question focus: `time_trend`, `distribution_shape`, `variance_bridge`
- Period role: `axis_or_table`
- Metric roles: `statement_value`
- Dimension roles: required `statement_line_item`
- Close competitors: `none`
- Positive question: Build a P&L line-item table.
- Ambiguous question: Show the supporting evidence table.
- Ambiguous candidates: `statement.pnl_table`, `attributes.attribute_bridge_table`, `attributes.attribute_bundle_comparison_table`, `attributes.product_signal_evidence_table`, `attributes.rank_weighted_visibility_table`
- Disambiguation: Clarify whether the intended focus is `structured_statement_values`, `current_vs_emerging_signal_alignment`, `bundle_share_and_index_evidence`, `product_level_grounding`, `rank_weighted_visibility`.

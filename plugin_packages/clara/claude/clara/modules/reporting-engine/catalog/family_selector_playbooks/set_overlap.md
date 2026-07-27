# Chart Selection Playbook: set_overlap

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `set_overlap.upset` | `many_set_intersections` | `none` | `none` | required `set_membership_fields` | Question asks for intersection patterns across several sets. |
| `set_overlap.upset_small_multiples` | `intersection_patterns_across_panels` | `none` | `none` | required `set_membership_fields`, `panel_or_segment` | Question asks how set intersection patterns differ across panels or segments. |
| `set_overlap.venn` | `simple_two_or_three_set_overlap` | `none` | `none` | required `two_or_three_set_membership_fields` | Question asks for simple overlap among two or three sets. |

## High-Overlap Pairs

- `set_overlap.upset` <> `set_overlap.venn`: `resolved` (`0` errors, `0` warnings)

## Capability Details

### `set_overlap.upset`

- Selection emphasis: `many_set_intersections`
- Visual grammar: `upset_plot`
- Analysis tasks: `set_overlap`
- Best when: The reader needs to compare intersections across more than two sets.
- Avoid when: Avoid when only two or three simple sets need a familiar Venn view.
- Primary decision cue: Question asks for intersection patterns across several sets.
- Requires question focus: `many_set_intersections`, `set_membership`
- Reject decision cues: `asks for only two or three sets`, `asks for panel comparison`, `asks for metric distribution`
- Forbidden question focus: `simple_set_overlap`, `set_overlap_panels`, `distribution_shape`
- Period role: `none`
- Metric roles: `none`
- Dimension roles: required `set_membership_fields`
- Close competitors: `set_overlap.venn`, `set_overlap.upset_small_multiples`
- Positive question: Which brands are shared across retailers?
- Ambiguous question: Show overlap between groups.
- Ambiguous candidates: `set_overlap.upset`, `set_overlap.venn`, `set_overlap.upset_small_multiples`
- Disambiguation: Clarify whether the intended focus is `many_set_intersections`, `simple_two_or_three_set_overlap`, `intersection_patterns_across_panels`.
- High-overlap pair evidence:
  - `set_overlap.venn`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `set_overlap.upset_small_multiples`

- Selection emphasis: `intersection_patterns_across_panels`
- Visual grammar: `upset_small_multiples`
- Analysis tasks: `set_overlap`
- Best when: The reader needs to compare overlap structures across panels or segments.
- Avoid when: Avoid when one aggregate overlap view is enough.
- Primary decision cue: Question asks how set intersection patterns differ across panels or segments.
- Requires question focus: `set_overlap_panels`, `many_set_intersections`
- Reject decision cues: `asks for one global upset plot`, `asks for simple Venn`, `asks for ranking`
- Forbidden question focus: `global_set_overlap`, `simple_set_overlap`, `single_metric_rank`
- Period role: `none`
- Metric roles: `none`
- Dimension roles: required `set_membership_fields`, `panel_or_segment`
- Close competitors: `set_overlap.upset`
- Positive question: How does brand overlap across retailers differ by category?
- Ambiguous question: Show overlap between groups.
- Ambiguous candidates: `set_overlap.upset_small_multiples`, `set_overlap.upset`, `set_overlap.venn`
- Disambiguation: Clarify whether the intended focus is `intersection_patterns_across_panels`, `many_set_intersections`, `simple_two_or_three_set_overlap`.

### `set_overlap.venn`

- Selection emphasis: `simple_two_or_three_set_overlap`
- Visual grammar: `venn`
- Analysis tasks: `set_overlap`
- Best when: The reader needs an intuitive overlap picture for two or three sets.
- Avoid when: Avoid with more than three sets or many intersections.
- Primary decision cue: Question asks for simple overlap among two or three sets.
- Requires question focus: `simple_set_overlap`, `two_or_three_sets`
- Reject decision cues: `asks for many-set intersections`, `asks for panels`, `asks for metric relationship`
- Forbidden question focus: `many_set_intersections`, `set_overlap_panels`, `metric_relationship`
- Period role: `none`
- Metric roles: `none`
- Dimension roles: required `two_or_three_set_membership_fields`
- Close competitors: `set_overlap.upset`
- Positive question: Show simple brand overlap across the three retailers.
- Ambiguous question: Show overlap between groups.
- Ambiguous candidates: `set_overlap.venn`, `set_overlap.upset`, `set_overlap.upset_small_multiples`
- Disambiguation: Clarify whether the intended focus is `simple_two_or_three_set_overlap`, `many_set_intersections`, `intersection_patterns_across_panels`.
- High-overlap pair evidence:
  - `set_overlap.upset`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

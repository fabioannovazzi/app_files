# Chart Selection Playbook: distribution

Generated from `selection_manifest.json`. This is a manifest-side review document: it explains chart capability differences, not dataset-specific semantic validity.

## How To Use This Family

1. Start from the question focus and match it to `requires_question_focus`.
2. Reject charts whose `forbidden_question_focus` or reject cues match the question.
3. Check that the dataset profile can provide the required period, metric, and dimension roles.
4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.

## Capability Summary

| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |
| --- | --- | --- | --- | --- | --- |
| `distribution.boxplot` | `spread_and_outliers_summary` | `filter` | `distribution_metric` | `none` | Question asks for spread, quartiles, or outliers in numeric observations. |
| `distribution.ecdf` | `cumulative_distribution_and_percentiles` | `filter` | `distribution_metric` | `none` | Question asks for cumulative share below thresholds or percentile reading. |
| `distribution.histogram` | `frequency_shape` | `filter` | `distribution_metric` | `none` | Question asks for frequency distribution shape using binned observations. |
| `distribution.kernel_density` | `smoothed_distribution_shape` | `filter` | `distribution_metric` | `none` | Question asks for smoothed distribution shape rather than bins or points. |
| `distribution.stripplot` | `individual_observations` | `filter` | `distribution_metric` | `none` | Question asks to see individual numeric observations and point-level outliers. |

## High-Overlap Pairs

- `distribution.boxplot` <> `distribution.ecdf`: `resolved` (`0` errors, `0` warnings)
- `distribution.boxplot` <> `distribution.histogram`: `resolved` (`0` errors, `0` warnings)
- `distribution.boxplot` <> `distribution.kernel_density`: `resolved` (`0` errors, `0` warnings)
- `distribution.boxplot` <> `distribution.stripplot`: `resolved` (`0` errors, `0` warnings)
- `distribution.ecdf` <> `distribution.histogram`: `resolved` (`0` errors, `0` warnings)
- `distribution.ecdf` <> `distribution.kernel_density`: `resolved` (`0` errors, `0` warnings)
- `distribution.ecdf` <> `distribution.stripplot`: `resolved` (`0` errors, `0` warnings)
- `distribution.histogram` <> `distribution.kernel_density`: `resolved` (`0` errors, `0` warnings)
- `distribution.histogram` <> `distribution.stripplot`: `resolved` (`0` errors, `0` warnings)
- `distribution.kernel_density` <> `distribution.stripplot`: `resolved` (`0` errors, `0` warnings)

## Capability Details

### `distribution.boxplot`

- Selection emphasis: `spread_and_outliers_summary`
- Visual grammar: `boxplot`
- Analysis tasks: `distribution`
- Best when: The reader needs median, quartiles, spread, and outliers, especially across groups.
- Avoid when: Avoid when distribution shape details or individual observations matter.
- Primary decision cue: Question asks for spread, quartiles, or outliers in numeric observations.
- Requires question focus: `distribution_spread`, `outliers`
- Reject decision cues: `asks for every observation`, `asks for smoothed shape`, `asks for cumulative percentile`
- Forbidden question focus: `individual_observations`, `smoothed_density`, `cumulative_distribution`
- Period role: `filter`
- Metric roles: `distribution_metric`
- Dimension roles: `none`
- Close competitors: `distribution.stripplot`, `distribution.histogram`, `distribution.ecdf`, `distribution.kernel_density`
- Positive question: Summarize spread and outliers in monthly sales observations.
- Ambiguous question: Show how the metric is distributed.
- Ambiguous candidates: `distribution.boxplot`, `distribution.stripplot`, `distribution.histogram`, `distribution.ecdf`, `distribution.kernel_density`
- Disambiguation: Clarify whether the intended focus is `spread_and_outliers_summary`, `individual_observations`, `frequency_shape`, `cumulative_distribution_and_percentiles`, `smoothed_distribution_shape`.
- High-overlap pair evidence:
  - `distribution.ecdf`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.histogram`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.kernel_density`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.stripplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `distribution.ecdf`

- Selection emphasis: `cumulative_distribution_and_percentiles`
- Visual grammar: `ecdf`
- Analysis tasks: `distribution`
- Best when: The reader needs percentile thresholds or cumulative share below/above values.
- Avoid when: Avoid when frequency bins or individual observations are easier for the reader.
- Primary decision cue: Question asks for cumulative share below thresholds or percentile reading.
- Requires question focus: `cumulative_distribution`, `percentile_threshold`
- Reject decision cues: `asks for bins`, `asks for outlier summary`, `asks for individual observations`
- Forbidden question focus: `frequency_bins`, `spread_outliers`, `individual_observations`
- Period role: `filter`
- Metric roles: `distribution_metric`
- Dimension roles: `none`
- Close competitors: `distribution.histogram`, `distribution.boxplot`, `distribution.stripplot`, `distribution.kernel_density`
- Positive question: Show cumulative share of sales observations below each threshold.
- Ambiguous question: Show how the metric is distributed.
- Ambiguous candidates: `distribution.ecdf`, `distribution.histogram`, `distribution.boxplot`, `distribution.stripplot`, `distribution.kernel_density`
- Disambiguation: Clarify whether the intended focus is `cumulative_distribution_and_percentiles`, `frequency_shape`, `spread_and_outliers_summary`, `individual_observations`, `smoothed_distribution_shape`.
- High-overlap pair evidence:
  - `distribution.boxplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.histogram`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.kernel_density`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.stripplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `distribution.histogram`

- Selection emphasis: `frequency_shape`
- Visual grammar: `histogram`
- Analysis tasks: `distribution`
- Best when: The reader needs to see bins, skew, modal ranges, or rough frequency shape for one metric.
- Avoid when: Avoid when exact percentile comparison or individual points are needed.
- Primary decision cue: Question asks for frequency distribution shape using binned observations.
- Requires question focus: `frequency_bins`, `distribution_shape`
- Reject decision cues: `asks for exact points`, `asks for percentile threshold`, `asks for smoothed density`
- Forbidden question focus: `individual_observations`, `cumulative_distribution`, `smoothed_density`
- Period role: `filter`
- Metric roles: `distribution_metric`
- Dimension roles: `none`
- Close competitors: `distribution.boxplot`, `distribution.kernel_density`, `distribution.stripplot`, `distribution.ecdf`
- Positive question: What is the distribution of monthly sales observations?
- Ambiguous question: Show how the metric is distributed.
- Ambiguous candidates: `distribution.histogram`, `distribution.boxplot`, `distribution.kernel_density`, `distribution.stripplot`, `distribution.ecdf`
- Disambiguation: Clarify whether the intended focus is `frequency_shape`, `spread_and_outliers_summary`, `smoothed_distribution_shape`, `individual_observations`, `cumulative_distribution_and_percentiles`.
- High-overlap pair evidence:
  - `distribution.boxplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.ecdf`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.kernel_density`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.stripplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `distribution.kernel_density`

- Selection emphasis: `smoothed_distribution_shape`
- Visual grammar: `density_curve`
- Analysis tasks: `distribution`
- Best when: The reader needs a smoothed view of distribution shape across one or more groups.
- Avoid when: Avoid when sample size is small or exact bins/observations are important.
- Primary decision cue: Question asks for smoothed distribution shape rather than bins or points.
- Requires question focus: `smoothed_density`, `distribution_shape`
- Reject decision cues: `asks for exact counts by bin`, `asks for outlier markers`, `asks for cumulative thresholds`
- Forbidden question focus: `frequency_bins`, `spread_outliers`, `cumulative_distribution`
- Period role: `filter`
- Metric roles: `distribution_metric`
- Dimension roles: `none`
- Close competitors: `distribution.histogram`, `distribution.ecdf`, `distribution.boxplot`, `distribution.stripplot`
- Positive question: Show smoothed sales-distribution shape.
- Ambiguous question: Show how the metric is distributed.
- Ambiguous candidates: `distribution.kernel_density`, `distribution.histogram`, `distribution.ecdf`, `distribution.boxplot`, `distribution.stripplot`
- Disambiguation: Clarify whether the intended focus is `smoothed_distribution_shape`, `frequency_shape`, `cumulative_distribution_and_percentiles`, `spread_and_outliers_summary`, `individual_observations`.
- High-overlap pair evidence:
  - `distribution.boxplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.ecdf`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.histogram`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.stripplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

### `distribution.stripplot`

- Selection emphasis: `individual_observations`
- Visual grammar: `stripplot`
- Analysis tasks: `distribution`
- Best when: The reader needs to see individual observations, density, and outliers without summarizing them away.
- Avoid when: Avoid with too many points or when an aggregate distribution shape is enough.
- Primary decision cue: Question asks to see individual numeric observations and point-level outliers.
- Requires question focus: `individual_observations`, `point_outliers`
- Reject decision cues: `asks for binned frequency`, `asks for quartile summary`, `asks for smoothed shape`
- Forbidden question focus: `frequency_bins`, `spread_outliers`, `smoothed_density`
- Period role: `filter`
- Metric roles: `distribution_metric`
- Dimension roles: `none`
- Close competitors: `distribution.boxplot`, `distribution.histogram`, `distribution.ecdf`, `distribution.kernel_density`
- Positive question: Show individual monthly sales observations and outliers.
- Ambiguous question: Show how the metric is distributed.
- Ambiguous candidates: `distribution.stripplot`, `distribution.boxplot`, `distribution.histogram`, `distribution.ecdf`, `distribution.kernel_density`
- Disambiguation: Clarify whether the intended focus is `individual_observations`, `spread_and_outliers_summary`, `frequency_shape`, `cumulative_distribution_and_percentiles`, `smoothed_distribution_shape`.
- High-overlap pair evidence:
  - `distribution.boxplot`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.ecdf`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.histogram`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`
  - `distribution.kernel_density`: `resolved`; evidence `explicit_competitor_link`, `ambiguous_example_link`, `negative_example_link`

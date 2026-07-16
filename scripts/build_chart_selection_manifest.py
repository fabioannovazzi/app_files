from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

__all__ = ["build_chart_selection_manifest", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_chart_plugin_parameter_contract import (
    build_normalized_invocation_contract,
    build_role_registry,
)

SOURCE_MANIFEST = REPO_ROOT / "static" / "shared" / "png-gallery" / "manifest.json"
DEFAULT_OUTPUT = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_ASSESSMENT = DEFAULT_OUTPUT.with_name("assessment.md")
MAX_NEGATIVE_SELECTION_EXAMPLES = 5

ARTIFACT_CAPABILITY_OVERRIDES: dict[str, dict[str, str]] = {
    "period / year_over_year_small_multiples": {
        "capability_id": "period_comparison.trend",
        "reason": "Visual inspection: this artifact is the line small-multiple variant and should inherit the line trend capability.",
    },
}

LEGACY_STATIC_ARTIFACT_CAPABILITY_BY_STEM: dict[tuple[str, str], str] = {
    ("period-comparison", "year_over_year_small_multiples"): (
        "period_comparison.trend"
    ),
    ("set-overlap-analysis", "upset"): "set_overlap.upset",
    ("set-overlap-analysis", "upset_small_multiples"): (
        "set_overlap.upset_small_multiples"
    ),
    ("set-overlap-analysis", "venn"): "set_overlap.venn",
    ("variance-analysis", "pvm_decomposition_ladder"): "variance.price_volume_mix",
    ("variance-analysis", "waterfall"): "variance.scenario_bridge",
    ("variance-analysis", "waterfall_small_multiples"): "variance.scenario_bridge",
}

POSITIVE_SELECTION_QUESTIONS: dict[str, str] = {
    "attributes.attribute_bridge_table": "How do current winning attribute bundles align or diverge from emerging signals?",
    "attributes.attribute_bundle_comparison_table": "Show exact share, delta, and index evidence for selected attribute bundles.",
    "attributes.product_signal_evidence_table": "Which products provide evidence for the selected attribute signal?",
    "attributes.rank_weighted_visibility_table": "Which attribute bundles have rank-weighted visibility evidence?",
    "distribution.boxplot": "Summarize spread and outliers in monthly sales observations.",
    "distribution.ecdf": "Show cumulative share of sales observations below each threshold.",
    "distribution.histogram": "What is the distribution of monthly sales observations?",
    "distribution.kernel_density": "Show smoothed sales-distribution shape.",
    "distribution.stripplot": "Show individual monthly sales observations and outliers.",
    "funnel.stage_table": "What is the stage conversion funnel?",
    "mix.area": "Show sales contribution as an area trend across months.",
    "mix.bar": "Rank categories by sales for a selected scope.",
    "mix.barmekko": "Show category width and retailer height as a variable-width composition.",
    "mix.cohort_lost_stacked_column": "How much sales contribution comes from products by last active month?",
    "mix.cohort_since_stacked_column": "How much sales contribution comes from products by first active month?",
    "mix.column": "Show total sales by month as compact columns.",
    "mix.column_overlay": "Show total monthly sales with sales-share marker context.",
    "mix.like_for_like_column": "How did sales change for the same products active in both selected months?",
    "mix.like_for_like_stacked_column": "How did same-product sales mix by category change across the selected months?",
    "mix.marimekko": "Show sales composition across category and retailer.",
    "mix.multitier_bar": "Show category sales in two periods and the difference, split into retailer panels.",
    "mix.pareto": "Find the few categories that explain most sales.",
    "mix.stacked_bar": "Show sales totals and composition by retailer within categories.",
    "mix.stacked_bar_overlay": "Rank category sales while overlaying sales-share context.",
    "mix.stacked_column": "Show recent monthly sales mix by category.",
    "mix.stacked_pareto": "Show concentration and component composition together.",
    "mix.timeline": "Show the single sales trend across months without AC/PY comparison.",
    "period_comparison.by_period": "Which months explain the AC/PY sales gap?",
    "period_comparison.comparison_table": "Give exact current, prior-year, delta, and percent-delta sales values.",
    "period_comparison.dot": "Compare AC/PY sales gaps across categories with low clutter.",
    "period_comparison.horizontal_waterfall": "How do period variances reconcile prior-year sales to current sales?",
    "period_comparison.multitier_column": "Show compact AC/PY monthly sales columns.",
    "period_comparison.slope": "Show endpoint direction and magnitude of category sales changes.",
    "period_comparison.time_series_table": "Give citeable monthly AC/PY sales values and variances.",
    "period_comparison.trend": "How did monthly cosmetics sales evolve versus previous year?",
    "scatter.bubble": "Do units and sales share relate, weighted by sales?",
    "scatter.scatter": "Do units and sales share relate without size encoding?",
    "set_overlap.upset": "Which brands are shared across retailers?",
    "set_overlap.upset_small_multiples": "How does brand overlap across retailers differ by category?",
    "set_overlap.venn": "Show simple brand overlap across the three retailers.",
    "statement.pnl_table": "Build a P&L line-item table.",
    "variance.exploded_variance_bridge": "Which categories drove variance, and which brands explain the selected category moves?",
    "variance.price_volume_mix": "How much of the sales movement is due to price, units, and mix?",
    "variance.root_cause_component_bridge": "Which drivers explain the selected root-cause component of sales movement?",
    "variance.root_cause_exploded_bridge": "Which ordered root-cause path explains the total sales movement, and what explains the selected root-cause driver?",
    "variance.root_cause_total_bridge": "Which ordered root-cause path explains the total sales movement?",
    "variance.scenario_bridge": "Reconcile total sales from baseline to current with a plain bridge.",
    "variance.total_by_dimension_bridge": "Which categories account for the total sales variance?",
}

BROAD_TASK_QUESTIONS: dict[str, str] = {
    "cohort_and_population": "How did the population change across periods?",
    "composition_and_mix": "Show sales mix and composition.",
    "distribution": "Show how the metric is distributed.",
    "evidence_and_reporting_tables": "Show the supporting evidence table.",
    "metric_relationship": "Show the relationship between metrics.",
    "ranking_and_comparison": "Compare categories by sales.",
    "set_overlap": "Show overlap between groups.",
    "time_and_period_movement": "How did sales change over time?",
    "variance_and_bridge": "Explain the sales variance.",
}

DECISION_CUES_BY_EMPHASIS: dict[str, dict[str, Any]] = {
    "current_vs_emerging_signal_alignment": {
        "primary_decision_cue": "Question asks how current attribute signals align with or differ from emerging signals.",
        "requires_question_focus": [
            "attribute_signal_alignment",
            "current_vs_emerging",
        ],
        "reject_decision_cues": [
            "asks for product rows",
            "asks for simple rank visibility",
            "asks for numeric time trend",
        ],
        "forbidden_question_focus": [
            "product_level_evidence",
            "rank_weighted_visibility",
            "time_trend",
        ],
    },
    "bundle_share_and_index_evidence": {
        "primary_decision_cue": "Question asks for exact attribute bundle shares, deltas, or index evidence.",
        "requires_question_focus": ["attribute_bundle_metrics", "share_delta_index"],
        "reject_decision_cues": [
            "asks for product examples",
            "asks for bridge-style signal movement",
            "asks for charted trend",
        ],
        "forbidden_question_focus": [
            "product_level_evidence",
            "attribute_bridge",
            "time_trend",
        ],
    },
    "product_level_grounding": {
        "primary_decision_cue": "Question asks which products support a selected signal or attribute bundle.",
        "requires_question_focus": ["product_level_evidence", "signal_grounding"],
        "reject_decision_cues": [
            "asks for aggregate bundle index",
            "asks for ranked visibility only",
            "asks for variance bridge",
        ],
        "forbidden_question_focus": [
            "aggregate_attribute_index",
            "rank_weighted_visibility",
            "variance_bridge",
        ],
    },
    "rank_weighted_visibility": {
        "primary_decision_cue": "Question asks which attributes have rank-weighted visibility evidence.",
        "requires_question_focus": ["rank_weighted_visibility", "attribute_ranking"],
        "reject_decision_cues": [
            "asks for product rows",
            "asks for exact bundle share table",
            "asks for time movement",
        ],
        "forbidden_question_focus": [
            "product_level_evidence",
            "bundle_share_index",
            "time_trend",
        ],
    },
    "spread_and_outliers_summary": {
        "primary_decision_cue": "Question asks for spread, quartiles, or outliers in numeric observations.",
        "requires_question_focus": ["distribution_spread", "outliers"],
        "reject_decision_cues": [
            "asks for every observation",
            "asks for smoothed shape",
            "asks for cumulative percentile",
        ],
        "forbidden_question_focus": [
            "individual_observations",
            "smoothed_density",
            "cumulative_distribution",
        ],
    },
    "cumulative_distribution_and_percentiles": {
        "primary_decision_cue": "Question asks for cumulative share below thresholds or percentile reading.",
        "requires_question_focus": ["cumulative_distribution", "percentile_threshold"],
        "reject_decision_cues": [
            "asks for bins",
            "asks for outlier summary",
            "asks for individual observations",
        ],
        "forbidden_question_focus": [
            "frequency_bins",
            "spread_outliers",
            "individual_observations",
        ],
    },
    "frequency_shape": {
        "primary_decision_cue": "Question asks for frequency distribution shape using binned observations.",
        "requires_question_focus": ["frequency_bins", "distribution_shape"],
        "reject_decision_cues": [
            "asks for exact points",
            "asks for percentile threshold",
            "asks for smoothed density",
        ],
        "forbidden_question_focus": [
            "individual_observations",
            "cumulative_distribution",
            "smoothed_density",
        ],
    },
    "smoothed_distribution_shape": {
        "primary_decision_cue": "Question asks for smoothed distribution shape rather than bins or points.",
        "requires_question_focus": ["smoothed_density", "distribution_shape"],
        "reject_decision_cues": [
            "asks for exact counts by bin",
            "asks for outlier markers",
            "asks for cumulative thresholds",
        ],
        "forbidden_question_focus": [
            "frequency_bins",
            "spread_outliers",
            "cumulative_distribution",
        ],
    },
    "individual_observations": {
        "primary_decision_cue": "Question asks to see individual numeric observations and point-level outliers.",
        "requires_question_focus": ["individual_observations", "point_outliers"],
        "reject_decision_cues": [
            "asks for binned frequency",
            "asks for quartile summary",
            "asks for smoothed shape",
        ],
        "forbidden_question_focus": [
            "frequency_bins",
            "spread_outliers",
            "smoothed_density",
        ],
    },
    "stage_counts_and_conversion": {
        "primary_decision_cue": "Question asks for ordered funnel stage counts or conversion rates.",
        "requires_question_focus": ["funnel_stages", "conversion_rates"],
        "reject_decision_cues": [
            "asks for distribution",
            "asks for period trend",
            "asks for set overlap",
        ],
        "forbidden_question_focus": ["distribution_shape", "time_trend", "set_overlap"],
    },
    "trend_with_cumulative_or_share_area": {
        "primary_decision_cue": "Question asks for contribution or share as an area trend across ordered periods.",
        "requires_question_focus": ["area_trend", "contribution_or_share_over_time"],
        "reject_decision_cues": [
            "asks for precise line trajectory",
            "asks for AC/PY gap",
            "asks for exact period table",
        ],
        "forbidden_question_focus": [
            "single_line_trend",
            "period_gap",
            "exact_period_values",
        ],
    },
    "ranked_single_metric_comparison": {
        "primary_decision_cue": "Question asks to rank categories by one selected metric in a scope.",
        "requires_question_focus": ["single_metric_rank", "category_comparison"],
        "reject_decision_cues": [
            "asks for composition within bars",
            "asks for period delta",
            "asks for cumulative Pareto share",
        ],
        "forbidden_question_focus": [
            "composition",
            "period_delta",
            "pareto_concentration",
        ],
    },
    "width_metric_times_height_metric": {
        "primary_decision_cue": "Question asks for variable-width composition where width and height are separate metrics.",
        "requires_question_focus": [
            "variable_width_composition",
            "width_and_height_metrics",
        ],
        "reject_decision_cues": [
            "asks for two-dimension share only",
            "asks for bubble relationship",
            "asks for simple ranked bars",
        ],
        "forbidden_question_focus": [
            "two_dimension_share",
            "metric_relationship",
            "single_metric_rank",
        ],
    },
    "lost_cohort_contribution": {
        "primary_decision_cue": "Question asks how much contribution comes from entities by last active or lost cohort.",
        "requires_question_focus": ["lost_cohort", "entity_population_change"],
        "reject_decision_cues": [
            "asks for first active cohort",
            "asks for same-population change",
            "asks for general composition",
        ],
        "forbidden_question_focus": [
            "since_cohort",
            "like_for_like_population",
            "composition_only",
        ],
    },
    "since_cohort_contribution": {
        "primary_decision_cue": "Question asks how much contribution comes from entities by first active or since cohort.",
        "requires_question_focus": ["since_cohort", "entity_population_change"],
        "reject_decision_cues": [
            "asks for lost cohort",
            "asks for same-population change",
            "asks for period gap",
        ],
        "forbidden_question_focus": [
            "lost_cohort",
            "like_for_like_population",
            "period_gap",
        ],
    },
    "total_metric_by_period_or_scope": {
        "primary_decision_cue": "Question asks for total metric columns by period or selected scope without composition.",
        "requires_question_focus": ["total_metric", "column_summary"],
        "reject_decision_cues": [
            "asks for component mix",
            "asks for line trajectory",
            "asks for related marker metric",
        ],
        "forbidden_question_focus": [
            "composition",
            "single_line_trend",
            "secondary_metric_marker",
        ],
    },
    "total_plus_related_marker": {
        "primary_decision_cue": "Question asks for total columns with a secondary related metric marker.",
        "requires_question_focus": ["total_metric", "secondary_metric_marker"],
        "reject_decision_cues": [
            "asks for ranked categories with marker",
            "asks for two-metric scatter",
            "asks for plain total",
        ],
        "forbidden_question_focus": [
            "rank_plus_marker",
            "scatter_relationship",
            "plain_total",
        ],
    },
    "same_population_total_change": {
        "primary_decision_cue": "Question asks for total change among the same entities present in both periods.",
        "requires_question_focus": ["like_for_like_population", "total_change"],
        "reject_decision_cues": [
            "asks for composition change",
            "asks for new or lost cohorts",
            "asks for all-population total",
        ],
        "forbidden_question_focus": [
            "like_for_like_composition",
            "cohort_change",
            "all_population_total",
        ],
    },
    "same_population_composition_change": {
        "primary_decision_cue": "Question asks for mix change among the same entities present in both periods.",
        "requires_question_focus": ["like_for_like_population", "composition_change"],
        "reject_decision_cues": [
            "asks for total-only change",
            "asks for lost/since cohorts",
            "asks for simple stacked composition",
        ],
        "forbidden_question_focus": [
            "like_for_like_total",
            "cohort_change",
            "all_population_composition",
        ],
    },
    "two_dimension_share_and_size": {
        "primary_decision_cue": "Question asks for composition across two categorical dimensions using segment share and size.",
        "requires_question_focus": ["two_dimension_share", "composition_size"],
        "reject_decision_cues": [
            "asks for separate width and height metrics",
            "asks for ranked bars",
            "asks for period variance",
        ],
        "forbidden_question_focus": [
            "width_height_metrics",
            "single_metric_rank",
            "period_variance",
        ],
    },
    "dimension_period_values_and_delta": {
        "primary_decision_cue": "Question asks for one dimension's values in two periods and the delta, optionally by panels.",
        "requires_question_focus": [
            "dimension_period_delta",
            "current_vs_baseline_values",
        ],
        "reject_decision_cues": [
            "asks for continuous trend",
            "asks for composition",
            "asks for root-cause bridge",
        ],
        "forbidden_question_focus": [
            "single_line_trend",
            "composition",
            "root_cause_variance",
        ],
    },
    "ranked_contribution_and_cumulative_share": {
        "primary_decision_cue": "Question asks which few items explain most of the total using cumulative share.",
        "requires_question_focus": ["pareto_concentration", "cumulative_share"],
        "reject_decision_cues": [
            "asks for component breakdown",
            "asks for simple ranking only",
            "asks for time trend",
        ],
        "forbidden_question_focus": [
            "component_breakdown",
            "single_metric_rank",
            "time_trend",
        ],
    },
    "composition_within_ranked_totals": {
        "primary_decision_cue": "Question asks for composition within ranked category totals.",
        "requires_question_focus": ["ranked_composition", "stacked_total"],
        "reject_decision_cues": [
            "asks for simple rank only",
            "asks for related marker",
            "asks for two-period delta",
        ],
        "forbidden_question_focus": [
            "single_metric_rank",
            "secondary_metric_marker",
            "period_delta",
        ],
    },
    "primary_rank_plus_secondary_marker": {
        "primary_decision_cue": "Question asks to rank categories by a primary metric while overlaying a secondary marker.",
        "requires_question_focus": ["rank_plus_marker", "secondary_metric_marker"],
        "reject_decision_cues": [
            "asks for total column marker",
            "asks for scatter relationship",
            "asks for stacked composition",
        ],
        "forbidden_question_focus": [
            "total_plus_marker",
            "scatter_relationship",
            "composition",
        ],
    },
    "composition_change_over_periods": {
        "primary_decision_cue": "Question asks for total and component composition across periods.",
        "requires_question_focus": ["composition_over_time", "stacked_periods"],
        "reject_decision_cues": [
            "asks for line trajectory",
            "asks for exact values",
            "asks for same-population-only mix",
        ],
        "forbidden_question_focus": [
            "single_line_trend",
            "exact_period_values",
            "like_for_like_population",
        ],
    },
    "concentration_with_component_breakdown": {
        "primary_decision_cue": "Question asks for concentration and component breakdown together.",
        "requires_question_focus": ["pareto_concentration", "component_breakdown"],
        "reject_decision_cues": [
            "asks for simple Pareto only",
            "asks for stacked totals only",
            "asks for metric relationship",
        ],
        "forbidden_question_focus": [
            "pareto_only",
            "stacked_total_only",
            "metric_relationship",
        ],
    },
    "single_metric_trend_shape": {
        "primary_decision_cue": "Question asks for one metric's trend path across ordered periods without AC/PY comparison.",
        "requires_question_focus": ["single_line_trend", "ordered_periods"],
        "reject_decision_cues": [
            "asks for AC/PY comparison",
            "asks for composition over time",
            "asks for exact period table",
        ],
        "forbidden_question_focus": [
            "current_vs_baseline",
            "composition_over_time",
            "exact_period_values",
        ],
    },
    "period_by_period_gap": {
        "primary_decision_cue": "Question asks which individual periods have the largest current-vs-baseline gaps.",
        "requires_question_focus": ["period_gap", "current_vs_baseline_by_period"],
        "reject_decision_cues": [
            "asks for smooth trajectory",
            "asks for additive reconciliation",
            "asks for exact table",
        ],
        "forbidden_question_focus": [
            "trajectory_shape",
            "bridge_reconciliation",
            "exact_period_values",
        ],
    },
    "summary_exact_values": {
        "primary_decision_cue": "Question asks for exact summary current, baseline, delta, and percent-delta values.",
        "requires_question_focus": ["exact_summary_values", "comparison_table"],
        "reject_decision_cues": [
            "asks for visual trend",
            "asks for bridge reconciliation",
            "asks for distribution",
        ],
        "forbidden_question_focus": [
            "trajectory_shape",
            "bridge_reconciliation",
            "distribution_shape",
        ],
    },
    "gap_between_two_values": {
        "primary_decision_cue": "Question asks for low-clutter comparison of two values across items.",
        "requires_question_focus": ["two_value_gap", "low_clutter_comparison"],
        "reject_decision_cues": [
            "asks for monthly path",
            "asks for additive bridge",
            "asks for exact table",
        ],
        "forbidden_question_focus": [
            "period_path",
            "bridge_reconciliation",
            "exact_values",
        ],
    },
    "additive_reconciliation": {
        "primary_decision_cue": "Question asks how period variances add from baseline total to current total.",
        "requires_question_focus": [
            "bridge_reconciliation",
            "additive_period_variance",
        ],
        "reject_decision_cues": [
            "asks for non-additive values",
            "asks for line shape",
            "asks for endpoint slope",
        ],
        "forbidden_question_focus": [
            "non_additive_metric",
            "trajectory_shape",
            "endpoint_change",
        ],
    },
    "compact_side_by_side_period_comparison": {
        "primary_decision_cue": "Question asks for compact side-by-side current and baseline period columns.",
        "requires_question_focus": [
            "side_by_side_periods",
            "current_vs_baseline_values",
        ],
        "reject_decision_cues": [
            "asks for line trajectory",
            "asks for exact table",
            "asks for bridge reconciliation",
        ],
        "forbidden_question_focus": [
            "trajectory_shape",
            "exact_period_values",
            "bridge_reconciliation",
        ],
    },
    "endpoint_direction_and_relative_change": {
        "primary_decision_cue": "Question asks for direction and magnitude between two endpoints.",
        "requires_question_focus": ["endpoint_change", "relative_direction"],
        "reject_decision_cues": [
            "asks for intermediate period path",
            "asks for additive bridge",
            "asks for exact values",
        ],
        "forbidden_question_focus": [
            "period_path",
            "bridge_reconciliation",
            "exact_values",
        ],
    },
    "exact_values": {
        "primary_decision_cue": "Question asks for citeable exact period values, deltas, or percent deltas.",
        "requires_question_focus": ["exact_period_values", "period_table"],
        "reject_decision_cues": [
            "asks for quick visual shape",
            "asks for bridge reconciliation",
            "asks for low-clutter comparison",
        ],
        "forbidden_question_focus": [
            "trajectory_shape",
            "bridge_reconciliation",
            "two_value_gap",
        ],
    },
    "trajectory_shape": {
        "primary_decision_cue": "Question asks for ordered period trajectory: acceleration, reversal, narrowing, widening, or seasonality.",
        "requires_question_focus": [
            "trajectory_shape",
            "current_vs_baseline_period_axis",
        ],
        "reject_decision_cues": [
            "asks for exact values",
            "asks for additive reconciliation",
            "asks for endpoint-only comparison",
        ],
        "forbidden_question_focus": [
            "exact_period_values",
            "bridge_reconciliation",
            "endpoint_change",
        ],
    },
    "two_metric_relationship_plus_size": {
        "primary_decision_cue": "Question asks for relationship between two metrics with a third metric encoded by size.",
        "requires_question_focus": ["scatter_relationship", "size_encoding"],
        "reject_decision_cues": [
            "asks for unweighted relationship",
            "asks for ranked bars",
            "asks for time trend",
        ],
        "forbidden_question_focus": [
            "plain_scatter",
            "single_metric_rank",
            "time_trend",
        ],
    },
    "relationship_between_two_metrics": {
        "primary_decision_cue": "Question asks for relationship between two metrics without size encoding.",
        "requires_question_focus": ["scatter_relationship", "two_metrics"],
        "reject_decision_cues": [
            "asks for bubble size",
            "asks for category ranking",
            "asks for period gap",
        ],
        "forbidden_question_focus": [
            "size_encoding",
            "single_metric_rank",
            "period_gap",
        ],
    },
    "many_set_intersections": {
        "primary_decision_cue": "Question asks for intersection patterns across several sets.",
        "requires_question_focus": ["many_set_intersections", "set_membership"],
        "reject_decision_cues": [
            "asks for only two or three sets",
            "asks for panel comparison",
            "asks for metric distribution",
        ],
        "forbidden_question_focus": [
            "simple_set_overlap",
            "set_overlap_panels",
            "distribution_shape",
        ],
    },
    "intersection_patterns_across_panels": {
        "primary_decision_cue": "Question asks how set intersection patterns differ across panels or segments.",
        "requires_question_focus": ["set_overlap_panels", "many_set_intersections"],
        "reject_decision_cues": [
            "asks for one global upset plot",
            "asks for simple Venn",
            "asks for ranking",
        ],
        "forbidden_question_focus": [
            "global_set_overlap",
            "simple_set_overlap",
            "single_metric_rank",
        ],
    },
    "simple_two_or_three_set_overlap": {
        "primary_decision_cue": "Question asks for simple overlap among two or three sets.",
        "requires_question_focus": ["simple_set_overlap", "two_or_three_sets"],
        "reject_decision_cues": [
            "asks for many-set intersections",
            "asks for panels",
            "asks for metric relationship",
        ],
        "forbidden_question_focus": [
            "many_set_intersections",
            "set_overlap_panels",
            "metric_relationship",
        ],
    },
    "structured_statement_values": {
        "primary_decision_cue": "Question asks for structured P&L or statement line-item values.",
        "requires_question_focus": ["statement_table", "line_item_values"],
        "reject_decision_cues": [
            "asks for charted trend",
            "asks for distribution",
            "asks for variance bridge",
        ],
        "forbidden_question_focus": [
            "time_trend",
            "distribution_shape",
            "variance_bridge",
        ],
    },
    "parent_bridge_with_child_drilldowns": {
        "primary_decision_cue": "Question asks for one fixed parent dimension variance bridge plus child drilldowns for selected rows.",
        "requires_question_focus": ["fixed_parent_child_drilldown", "variance_bridge"],
        "reject_decision_cues": [
            "asks for variable root-cause sequence",
            "asks for plain bridge",
            "asks for PVM mechanics",
        ],
        "forbidden_question_focus": [
            "root_cause_sequence",
            "scenario_bridge",
            "pvm_decomposition",
        ],
    },
    "pvm_decomposition_comparison": {
        "primary_decision_cue": "Question explicitly asks how movement decomposes into price, volume, and mix effects.",
        "requires_question_focus": ["pvm_decomposition", "price_volume_mix"],
        "reject_decision_cues": [
            "asks for generic variance bridge",
            "asks for dimension split",
            "asks for root-cause ordering",
        ],
        "forbidden_question_focus": [
            "scenario_bridge",
            "dimension_variance",
            "root_cause_sequence",
        ],
    },
    "component_level_root_cause": {
        "primary_decision_cue": "Question asks which drivers explain a selected component-level variance.",
        "requires_question_focus": [
            "component_root_cause",
            "selected_variance_component",
        ],
        "reject_decision_cues": [
            "asks for total root-cause path",
            "asks for plain bridge",
            "asks for PVM mechanics",
        ],
        "forbidden_question_focus": [
            "total_root_cause",
            "scenario_bridge",
            "pvm_decomposition",
        ],
    },
    "root_cause_path_with_nested_drilldowns": {
        "primary_decision_cue": "Question asks for ordered root-cause path plus nested drilldown for selected drivers.",
        "requires_question_focus": ["root_cause_sequence", "nested_driver_drilldown"],
        "reject_decision_cues": [
            "asks for fixed parent-child dimensions",
            "asks for total path only",
            "asks for PVM mechanics",
        ],
        "forbidden_question_focus": [
            "fixed_parent_child_drilldown",
            "total_root_cause_only",
            "pvm_decomposition",
        ],
    },
    "root_cause_total_movement": {
        "primary_decision_cue": "Question asks for ordered root-cause path explaining total movement.",
        "requires_question_focus": ["root_cause_sequence", "total_movement"],
        "reject_decision_cues": [
            "asks for selected component",
            "asks for nested drilldown",
            "asks for fixed dimension split",
        ],
        "forbidden_question_focus": [
            "component_root_cause",
            "nested_driver_drilldown",
            "dimension_variance",
        ],
    },
    "scenario_reconciliation": {
        "primary_decision_cue": "Question asks for a plain reconciliation from baseline or scenario to current total.",
        "requires_question_focus": ["scenario_bridge", "baseline_to_current_total"],
        "reject_decision_cues": [
            "asks for dimension contributors",
            "asks for root-cause ordering",
            "asks for PVM mechanics",
        ],
        "forbidden_question_focus": [
            "dimension_variance",
            "root_cause_sequence",
            "pvm_decomposition",
        ],
    },
    "total_delta_split_by_dimension": {
        "primary_decision_cue": "Question asks which members of one selected dimension account for total variance.",
        "requires_question_focus": ["dimension_variance", "total_delta_split"],
        "reject_decision_cues": [
            "asks for root-cause ordering",
            "asks for child drilldowns",
            "asks for plain scenario bridge",
        ],
        "forbidden_question_focus": [
            "root_cause_sequence",
            "fixed_parent_child_drilldown",
            "scenario_bridge",
        ],
    },
}

TABLE_CAPABILITY_IDS = {
    "attributes.attribute_bridge_table",
    "attributes.attribute_bundle_comparison_table",
    "attributes.product_signal_evidence_table",
    "attributes.rank_weighted_visibility_table",
    "funnel.stage_table",
    "period_comparison.comparison_table",
    "period_comparison.time_series_table",
    "statement.pnl_table",
}

OVERLAY_CAPABILITY_IDS = {
    "mix.column_overlay",
    "mix.stacked_bar_overlay",
}

PANEL_SPECIFIC_CAPABILITY_IDS = {
    "set_overlap.upset_small_multiples",
}

NESTED_DRILLDOWN_CAPABILITY_IDS = {
    "variance.exploded_variance_bridge",
    "variance.root_cause_exploded_bridge",
}

ENCODING_VARIANT_BY_CAPABILITY_ID = {
    "distribution.boxplot": "boxplot",
    "distribution.ecdf": "ecdf",
    "distribution.histogram": "histogram",
    "distribution.kernel_density": "density",
    "distribution.stripplot": "stripplot",
    "mix.area": "area",
    "mix.bar": "bar",
    "mix.barmekko": "variable_width",
    "mix.column": "column",
    "mix.column_overlay": "overlay",
    "mix.marimekko": "variable_width",
    "mix.multitier_bar": "multitier",
    "mix.pareto": "pareto",
    "mix.stacked_bar": "stacked",
    "mix.stacked_bar_overlay": "overlay",
    "mix.stacked_column": "stacked",
    "mix.stacked_pareto": "stacked_pareto",
    "mix.timeline": "line",
    "period_comparison.by_period": "period_gap",
    "period_comparison.dot": "dot",
    "period_comparison.horizontal_waterfall": "bridge",
    "period_comparison.multitier_column": "column",
    "period_comparison.slope": "slope",
    "period_comparison.trend": "line",
    "scatter.bubble": "bubble",
    "scatter.scatter": "scatter",
    "set_overlap.upset": "upset",
    "set_overlap.upset_small_multiples": "upset",
    "set_overlap.venn": "venn",
    "variance.exploded_variance_bridge": "bridge",
    "variance.price_volume_mix": "pvm_ladder",
    "variance.root_cause_component_bridge": "bridge",
    "variance.root_cause_exploded_bridge": "bridge",
    "variance.root_cause_total_bridge": "bridge",
    "variance.scenario_bridge": "bridge",
    "variance.total_by_dimension_bridge": "bridge",
}


def _cap(
    *,
    family: str,
    grammar: str,
    task_ids: list[str],
    emphasis: str,
    best_when: str,
    avoid_when: str,
    axis_roles: dict[str, str],
    period_role: str = "none",
    metric_roles: list[str] | None = None,
    metric_requirements: dict[str, Any] | None = None,
    dimension_roles: list[str] | None = None,
    dimension_contract: dict[str, Any] | None = None,
    competitors: list[str] | None = None,
) -> dict[str, Any]:
    analysis_task_ids = _analysis_task_ids(
        family=family,
        raw_task_ids=task_ids,
        emphasis=emphasis,
    )
    resolved_metric_roles = ["primary_metric"] if metric_roles is None else metric_roles
    return {
        "family": family,
        "visual_grammar": grammar,
        "analysis_task_ids": analysis_task_ids,
        "selection_tags": task_ids,
        "selection_emphasis": emphasis,
        "best_when": best_when,
        "avoid_when": avoid_when,
        "axis_roles": axis_roles,
        "period_semantics": {
            "role": period_role,
            "supports_period_axis": period_role in {"axis", "axis_or_table"},
            "supports_period_filter": period_role
            in {"axis", "axis_or_table", "filter"},
        },
        "display_metric_roles": resolved_metric_roles,
        "metric_requirements": metric_requirements
        or _default_metric_requirements(
            family=family,
            grammar=grammar,
            metric_roles=resolved_metric_roles,
        ),
        "dimension_roles": [] if dimension_roles is None else dimension_roles,
        "dimension_contract": dimension_contract,
        "competing_capability_ids": competitors or [],
    }


def _normalize_competitor_links(capabilities: dict[str, dict[str, Any]]) -> None:
    """Make authored close-competitor links visible from both capabilities."""

    additions: defaultdict[str, list[str]] = defaultdict(list)
    for capability_id, capability in capabilities.items():
        for competitor_id in capability.get("competing_capability_ids") or []:
            if competitor_id in capabilities:
                additions[competitor_id].append(capability_id)

    for capability_id, capability in capabilities.items():
        competitors = _unique_ids(
            list(capability.get("competing_capability_ids") or [])
            + additions.get(capability_id, [])
        )
        capability["competing_capability_ids"] = [
            competitor_id
            for competitor_id in competitors
            if competitor_id in capabilities and competitor_id != capability_id
        ]


ADDITIVE_METRIC_CLASSES = [
    "additive_value",
    "additive_volume",
    "additive_count",
]
NUMERIC_METRIC_CLASSES = [
    "additive_value",
    "additive_volume",
    "additive_count",
    "rate",
    "share",
    "index",
    "score",
    "numeric_observation",
]

DIRECT_DIMENSION_ROLES = {
    "category",
    "child_driver",
    "comparison_item",
    "component_category",
    "component_dimension",
    "component_root_cause_driver",
    "dimension_member",
    "height_category",
    "mix_dimension",
    "nested_category",
    "optional_component_dimension",
    "optional_panel",
    "panel_or_segment",
    "parent_driver",
    "point_dimension",
    "product",
    "stack_category",
    "variance_component",
    "width_category",
}

DIMENSION_ROLE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "comparison_series": {
        "resolution_type": "derived_from_period_pair",
        "requires_profile_roles": ["period"],
        "output_role": "series label such as AC/PY, current/baseline, or scenario",
        "notes": "Derived after choosing the comparison periods; it is not a dataset column.",
    },
    "comparison_window": {
        "resolution_type": "derived_from_period_pair",
        "requires_profile_roles": ["period"],
        "output_role": "comparison row/window label",
        "notes": "Derived from selected current and baseline windows.",
    },
    "bridge_component_period": {
        "resolution_type": "derived_from_period_pair",
        "requires_profile_roles": ["period"],
        "output_role": "period delta bridge step",
        "notes": "Derived from ordered period deltas for an additive comparison metric.",
    },
    "stable_population_flag": {
        "resolution_type": "derived_from_entity_period",
        "requires_profile_roles": ["period", "entity_key"],
        "output_role": "boolean flag for entities present in both selected periods",
        "notes": "Requires a stable entity column plus two period windows.",
    },
    "first_active_cohort": {
        "resolution_type": "derived_from_entity_period",
        "requires_profile_roles": ["period", "entity_key"],
        "output_role": "first active period for each entity",
        "notes": "Requires a stable entity column and ordered periods.",
    },
    "lost_or_last_active_cohort": {
        "resolution_type": "derived_from_entity_period",
        "requires_profile_roles": ["period", "entity_key"],
        "output_role": "last active period or lost cohort for each entity",
        "notes": "Requires a stable entity column and ordered periods.",
    },
    "root_cause_driver_sequence": {
        "resolution_type": "derived_root_cause_sequence",
        "requires_profile_roles": ["period", "direct_dimension"],
        "output_role": "ordered mixed-dimension driver sequence",
        "notes": "The candidate driver dimensions are mechanical; ordering and business validity are selected later.",
    },
    "nested_root_cause_driver_sequence": {
        "resolution_type": "derived_root_cause_sequence",
        "requires_profile_roles": ["period", "direct_dimension"],
        "output_role": "row-specific nested root-cause driver sequence",
        "notes": "Used only for selected rows in the root-cause exploded variant.",
    },
    "set_membership_fields": {
        "resolution_type": "derived_set_membership",
        "requires_profile_roles": ["set_item", "set_dimension"],
        "output_role": "boolean membership fields for several sets",
        "notes": "Requires an item column and a low-cardinality set-defining column or equivalent membership fields.",
    },
    "two_or_three_set_membership_fields": {
        "resolution_type": "derived_set_membership",
        "requires_profile_roles": ["set_item", "set_dimension"],
        "output_role": "boolean membership fields for two or three sets",
        "notes": "Requires an item column and a set-defining column with two or three chosen set values.",
    },
    "period_or_scenario_pair": {
        "resolution_type": "derived_period_or_scenario_pair",
        "requires_profile_roles": ["period"],
        "output_role": "baseline/current period or scenario pair",
        "notes": "Can be produced from a period column; scenario dimensions can be used when present.",
    },
    "variance_step": {
        "resolution_type": "structural_variance_step",
        "requires_profile_roles": [],
        "output_role": "baseline, component deltas, and current total rows",
        "notes": "Structural rows produced by the variance renderer after baseline/current aggregation.",
    },
    "attribute_bundle": {
        "resolution_type": "semantic_or_package_role",
        "requires_profile_roles": ["attribute_evidence_package"],
        "output_role": "reviewed attribute bundle",
        "notes": "Requires a reviewed attribute/package layer, not just raw categorical columns.",
    },
    "signal_bundle": {
        "resolution_type": "semantic_or_package_role",
        "requires_profile_roles": ["attribute_evidence_package"],
        "output_role": "current or emerging signal bundle",
        "notes": "Requires a reviewed signal/package layer.",
    },
    "cohort_layer": {
        "resolution_type": "semantic_or_package_role",
        "requires_profile_roles": ["attribute_evidence_package"],
        "output_role": "current/emerging cohort layer",
        "notes": "Requires a reviewed package layer that defines the cohorts.",
    },
    "rank_or_lane": {
        "resolution_type": "direct_rank_or_lane",
        "requires_profile_roles": ["rank_or_lane"],
        "output_role": "rank, lane, bucket, class, or band",
        "notes": "Mechanically detectable candidates still require semantic review for visibility claims.",
    },
    "ordered_stage": {
        "resolution_type": "schema_role",
        "requires_profile_roles": ["ordered_stage"],
        "output_role": "ordered funnel stage",
        "notes": "Requires an explicit ordered funnel stage column or stage table.",
    },
    "statement_line_item": {
        "resolution_type": "schema_role",
        "requires_profile_roles": ["statement_line_item"],
        "output_role": "financial statement line item",
        "notes": "Requires a structured statement table, not generic dimensions.",
    },
}

for _role in DIRECT_DIMENSION_ROLES:
    DIMENSION_ROLE_REQUIREMENTS.setdefault(
        _role,
        {
            "resolution_type": "direct_dimension",
            "requires_profile_roles": ["direct_dimension"],
            "output_role": _role,
            "notes": "Resolved by choosing a concrete dataset dimension or identifier candidate.",
        },
    )


def _source_metric_role(
    role: str,
    *,
    accepted_metric_classes: list[str],
    aggregation: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "role": role,
        "required": required,
        "accepted_metric_classes": accepted_metric_classes,
        "aggregation": aggregation,
    }


def _derived_metric_role(
    role: str,
    *,
    produced_from: list[str],
    derivation: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "produced_from": produced_from,
        "derivation": derivation,
    }


def _metric_requirements(
    *,
    source_metric_roles: list[dict[str, Any]] | None = None,
    derived_metric_roles: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Describe plot-side metric requirements, not dataset-specific columns."""

    source_roles = source_metric_roles or []
    derived_roles = derived_metric_roles or []
    return {
        "source_metric_roles": source_roles,
        "derived_metric_roles": derived_roles,
        "minimum_source_metric_count": sum(
            1 for role in source_roles if role.get("required", True)
        ),
        "metric_selection_notes": notes or [],
    }


def _comparison_metric_requirements(
    *,
    additive_only: bool,
    include_percent_delta: bool = False,
) -> dict[str, Any]:
    accepted = ADDITIVE_METRIC_CLASSES if additive_only else NUMERIC_METRIC_CLASSES
    derived = [
        _derived_metric_role(
            "baseline_period_metric",
            produced_from=["comparison_metric", "baseline_period"],
            derivation="aggregate comparison_metric over the baseline period or scenario",
        ),
        _derived_metric_role(
            "current_period_metric",
            produced_from=["comparison_metric", "current_period"],
            derivation="aggregate comparison_metric over the current period or scenario",
        ),
        _derived_metric_role(
            "delta_metric",
            produced_from=["baseline_period_metric", "current_period_metric"],
            derivation="current_period_metric - baseline_period_metric",
        ),
    ]
    if include_percent_delta:
        derived.append(
            _derived_metric_role(
                "percent_delta_metric",
                produced_from=["baseline_period_metric", "current_period_metric"],
                derivation="delta_metric / baseline_period_metric when baseline is non-zero",
            )
        )
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "comparison_metric",
                accepted_metric_classes=accepted,
                aggregation="semantic_layer_defined",
            )
        ],
        derived_metric_roles=derived,
        notes=[
            "The chart needs one source metric plus two periods/scenarios; baseline/current/delta are display roles derived after period filtering."
        ],
    )


def _variance_metric_requirements() -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "variance_metric",
                accepted_metric_classes=ADDITIVE_METRIC_CLASSES,
                aggregation="sum_or_count",
            )
        ],
        derived_metric_roles=[
            _derived_metric_role(
                "baseline_metric",
                produced_from=["variance_metric", "baseline_period_or_scenario"],
                derivation="aggregate variance_metric over the baseline period or scenario",
            ),
            _derived_metric_role(
                "current_metric",
                produced_from=["variance_metric", "current_period_or_scenario"],
                derivation="aggregate variance_metric over the current period or scenario",
            ),
            _derived_metric_role(
                "delta_metric",
                produced_from=["baseline_metric", "current_metric"],
                derivation="current_metric - baseline_metric",
            ),
        ],
        notes=[
            "Variance bridges require an additive source metric; baseline/current/delta are derived display roles."
        ],
    )


def _pvm_metric_requirements() -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "value_metric",
                accepted_metric_classes=["additive_value"],
                aggregation="sum",
            ),
            _source_metric_role(
                "volume_metric",
                accepted_metric_classes=["additive_volume"],
                aggregation="sum",
            ),
            _source_metric_role(
                "price_or_rate_metric",
                accepted_metric_classes=["rate", "derived_rate"],
                aggregation="weighted_or_derived_from_value_and_volume",
            ),
        ],
        derived_metric_roles=[
            _derived_metric_role(
                "price_effect",
                produced_from=["value_metric", "volume_metric", "price_or_rate_metric"],
                derivation="plugin decomposition formula",
            ),
            _derived_metric_role(
                "volume_effect",
                produced_from=["value_metric", "volume_metric"],
                derivation="plugin decomposition formula",
            ),
            _derived_metric_role(
                "mix_effect",
                produced_from=[
                    "value_metric",
                    "volume_metric",
                    "price_or_rate_metric",
                ],
                derivation=(
                    "plugin decomposition formula at the selected analysis grain; "
                    "mix is a structural PVM component, not a required dataset "
                    "dimension parameter"
                ),
            ),
        ],
        notes=[
            "PVM is valid only when value, volume, and price/rate semantics are available for the same grain; no business dimension is required as a chart parameter."
        ],
    )


def _barmekko_metric_requirements() -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "width_metric",
                accepted_metric_classes=ADDITIVE_METRIC_CLASSES,
                aggregation="sum_or_count",
            ),
            _source_metric_role(
                "height_metric",
                accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                aggregation="semantic_layer_defined",
            ),
        ],
        derived_metric_roles=[
            _derived_metric_role(
                "area_metric",
                produced_from=["width_metric", "height_metric"],
                derivation="visual area implied by width_metric times height_metric",
            )
        ],
        notes=[
            "The area role is visual/derived; the dataset needs width and height metrics, not a precomputed area column."
        ],
    )


def _attribute_table_metric_requirements(
    *, derived_roles: list[tuple[str, list[str], str]], note: str
) -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[],
        derived_metric_roles=[
            _derived_metric_role(
                role,
                produced_from=produced_from,
                derivation=derivation,
            )
            for role, produced_from, derivation in derived_roles
        ],
        notes=[note],
    )


def _funnel_metric_requirements() -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "stage_start_count",
                accepted_metric_classes=["additive_count"],
                aggregation="sum_or_count",
            ),
            _source_metric_role(
                "stage_pass_count",
                accepted_metric_classes=["additive_count"],
                aggregation="sum_or_count",
            ),
        ],
        derived_metric_roles=[
            _derived_metric_role(
                "dropoff_count",
                produced_from=["stage_start_count", "stage_pass_count"],
                derivation="stage_start_count - stage_pass_count",
            ),
            _derived_metric_role(
                "conversion_rate",
                produced_from=["stage_start_count", "stage_pass_count"],
                derivation="stage_pass_count / stage_start_count when start is non-zero",
            ),
        ],
        notes=[
            "Funnel tables require ordered stages and stage count columns; dropoff and conversion can be derived."
        ],
    )


def _statement_metric_requirements() -> dict[str, Any]:
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                "statement_value",
                accepted_metric_classes=["additive_value"],
                aggregation="semantic_layer_defined",
            )
        ],
        notes=[
            "Statement tables require a statement line-item dimension, not just a numeric value column."
        ],
    )


def _default_metric_requirements(
    *, family: str, grammar: str, metric_roles: list[str]
) -> dict[str, Any]:
    roles = set(metric_roles)
    if not metric_roles:
        return _metric_requirements()
    if roles <= {
        "baseline_period_metric",
        "current_period_metric",
        "delta_metric",
        "percent_delta_metric",
        "baseline_metric",
        "current_metric",
    }:
        additive_only = "waterfall" in grammar or "bridge" in grammar
        return _comparison_metric_requirements(
            additive_only=additive_only,
            include_percent_delta="percent_delta_metric" in roles,
        )
    if "primary_additive_metric" in roles:
        source_roles = [
            _source_metric_role(
                "primary_metric",
                accepted_metric_classes=ADDITIVE_METRIC_CLASSES,
                aggregation="sum_or_count",
            )
        ]
        if "related_marker_metric" in roles:
            source_roles.append(
                _source_metric_role(
                    "related_marker_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="semantic_layer_defined",
                )
            )
        return _metric_requirements(source_metric_roles=source_roles)
    if family == "distribution":
        return _metric_requirements(
            source_metric_roles=[
                _source_metric_role(
                    "distribution_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="none_observation_level_or_explicit_grouping",
                )
            ]
        )
    if roles == {"x_metric", "y_metric"}:
        return _metric_requirements(
            source_metric_roles=[
                _source_metric_role(
                    "x_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="semantic_layer_defined",
                ),
                _source_metric_role(
                    "y_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="semantic_layer_defined",
                ),
            ]
        )
    if roles == {"x_metric", "y_metric", "size_metric"}:
        return _metric_requirements(
            source_metric_roles=[
                _source_metric_role(
                    "x_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="semantic_layer_defined",
                ),
                _source_metric_role(
                    "y_metric",
                    accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                    aggregation="semantic_layer_defined",
                ),
                _source_metric_role(
                    "size_metric",
                    accepted_metric_classes=ADDITIVE_METRIC_CLASSES,
                    aggregation="sum_or_count",
                ),
            ],
            notes=[
                "Bubble size should be non-negative and comparable within the plotted scope."
            ],
        )
    return _metric_requirements(
        source_metric_roles=[
            _source_metric_role(
                role,
                accepted_metric_classes=NUMERIC_METRIC_CLASSES,
                aggregation="semantic_layer_defined",
            )
            for role in metric_roles
        ]
    )


def _selection_contract(
    capability_id: str,
    capability: dict[str, Any],
    all_capabilities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build a machine-facing checklist for selector use.

    This is deterministic because it only normalizes explicit manifest fields
    into a contract the selector can validate before making semantic judgments.
    """

    display_metric_roles = list(capability.get("display_metric_roles") or [])
    metric_requirements = capability["metric_requirements"]
    dimension_roles = list(capability.get("dimension_roles") or [])
    required_dimension_roles = [
        role for role in dimension_roles if not role.startswith("optional_")
    ]
    optional_dimension_roles = [
        role for role in dimension_roles if role.startswith("optional_")
    ]
    dimension_role_requirements = {
        role: _dimension_role_requirement(role)
        for role in required_dimension_roles + optional_dimension_roles
    }
    required_column_dimension_count = sum(
        1
        for role in required_dimension_roles
        if dimension_role_requirements[role]["resolution_type"]
        in {"direct_dimension", "direct_rank_or_lane", "schema_role"}
    )
    dimension_contract = capability.get("dimension_contract")
    period_semantics = capability["period_semantics"]
    tie_breakers = []
    for competitor_id in capability.get("competing_capability_ids") or []:
        competitor = all_capabilities.get(competitor_id)
        if not competitor:
            continue
        tie_breakers.append(
            {
                "against": competitor_id,
                "choose_this_when": capability["best_when"],
                "choose_other_when": competitor["best_when"],
                "distinguishing_emphasis": {
                    "this": capability["selection_emphasis"],
                    "other": competitor["selection_emphasis"],
                },
            }
        )

    return {
        "selector_must_know": [
            "analysis_task",
            "selection_emphasis",
            "available_source_metric_roles",
            "available_dimension_roles",
            "period_role_in_question",
        ],
        "dataset_requirements": {
            "period": {
                "role": period_semantics["role"],
                "requires_period_axis": period_semantics["supports_period_axis"],
                "allows_period_filter": period_semantics["supports_period_filter"],
            },
            "metrics": {
                "minimum_source_metric_count": metric_requirements[
                    "minimum_source_metric_count"
                ],
                "source_metric_roles": metric_requirements["source_metric_roles"],
                "derived_metric_roles": metric_requirements["derived_metric_roles"],
                "display_metric_roles": display_metric_roles,
                "metric_selection_notes": metric_requirements["metric_selection_notes"],
            },
            "dimensions": {
                "minimum_count": required_column_dimension_count,
                "required_roles": required_dimension_roles,
                "optional_roles": optional_dimension_roles,
                "role_requirements": dimension_role_requirements,
                "dimension_contract": dimension_contract,
            },
            "visual_role_bindings": capability["axis_roles"],
        },
        "implementation_evidence": {
            "gallery_example_count": capability.get("example_count", 0),
            "present_in_gallery_manifest": capability.get(
                "present_in_gallery_manifest", False
            ),
            "present_in_generated_manifest": capability.get(
                "present_in_generated_manifest", False
            ),
            "evidence_status": (
                "gallery_image_reviewed"
                if capability.get("example_count", 0) > 0
                else "generated_manifest_only"
            ),
        },
        "accept_when": capability["best_when"],
        "reject_when": capability["avoid_when"],
        "tie_breakers": tie_breakers,
        "selection_boundary": (
            "This contract constrains valid chart choices and required data roles; "
            "the selector still has to match the report question to the intended "
            "selection_emphasis rather than selecting by keywords alone."
        ),
        "selection_decision": (
            f"Choose `{capability_id}` only when the task is one of "
            f"{capability['analysis_task_ids']} and the required emphasis is "
            f"`{capability['selection_emphasis']}`; otherwise compare the "
            "tie_breakers rather than selecting by chart family name."
        ),
    }


def _dimension_role_requirement(role: str) -> dict[str, Any]:
    """Normalize explicit role names into mechanical profile prerequisites."""

    lookup_role = role.removeprefix("optional_")
    requirement = dict(
        DIMENSION_ROLE_REQUIREMENTS.get(
            lookup_role,
            {
                "resolution_type": "direct_dimension",
                "requires_profile_roles": ["direct_dimension"],
                "output_role": lookup_role,
                "notes": "Fallback direct dimension role; review this role if it becomes selection-critical.",
            },
        )
    )
    requirement["role"] = role
    requirement["required"] = not role.startswith("optional_")
    return requirement


def _selection_examples(
    capability_id: str,
    capability: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    tasks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build manifest examples from authored positives plus explicit chart graph links."""

    positive_question = POSITIVE_SELECTION_QUESTIONS.get(capability_id)
    sibling_ids = _sibling_capability_ids(capability_id, capability, tasks_by_id)
    competitor_ids = [
        competitor_id
        for competitor_id in capability.get("competing_capability_ids") or []
        if competitor_id in capabilities
    ]
    negative_source_ids = _unique_ids(competitor_ids + sibling_ids)[
        :MAX_NEGATIVE_SELECTION_EXAMPLES
    ]
    if not negative_source_ids:
        negative_source_ids = [
            other_id for other_id in sorted(capabilities) if other_id != capability_id
        ][:MAX_NEGATIVE_SELECTION_EXAMPLES]
    negative_questions = [
        {
            "question": POSITIVE_SELECTION_QUESTIONS[other_id],
            "why_not": (
                f"This asks for `{capabilities[other_id]['selection_emphasis']}`, "
                f"not `{capability['selection_emphasis']}`."
            ),
            "better_capability_id": other_id,
        }
        for other_id in negative_source_ids
        if other_id in POSITIVE_SELECTION_QUESTIONS
    ]
    ambiguous_candidate_ids = _unique_ids(
        [capability_id] + competitor_ids + sibling_ids
    )[:5]
    if len(ambiguous_candidate_ids) == 1:
        ambiguous_candidate_ids = _unique_ids(
            ambiguous_candidate_ids
            + [
                other_id
                for other_id in sorted(capabilities)
                if other_id != capability_id
            ]
        )[:5]
    primary_task_id = (capability.get("analysis_task_ids") or [capability["family"]])[0]
    candidate_emphases = [
        capabilities[candidate_id]["selection_emphasis"]
        for candidate_id in ambiguous_candidate_ids
        if candidate_id in capabilities
    ]
    return {
        "positive_questions": [positive_question] if positive_question else [],
        "negative_questions": negative_questions,
        "ambiguous_questions": [
            {
                "question": BROAD_TASK_QUESTIONS.get(
                    primary_task_id, f"Show {primary_task_id.replace('_', ' ')}."
                ),
                "candidate_capability_ids": ambiguous_candidate_ids,
                "disambiguation_needed": (
                    "Clarify whether the intended focus is "
                    + ", ".join(f"`{emphasis}`" for emphasis in candidate_emphases)
                    + "."
                ),
            }
        ],
        "example_source": (
            "positive questions are authored from reviewed proof/review cases; "
            "negative and ambiguous examples are derived from explicit competitor "
            "and task-sibling links."
        ),
    }


def _sibling_capability_ids(
    capability_id: str,
    capability: dict[str, Any],
    tasks_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    sibling_ids: list[str] = []
    for task_id in capability.get("analysis_task_ids") or []:
        task = tasks_by_id.get(task_id) or {}
        for sibling_id in task.get("capability_ids") or []:
            if sibling_id != capability_id and sibling_id not in sibling_ids:
                sibling_ids.append(sibling_id)
    return sibling_ids


def _unique_ids(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _analysis_task_ids(
    *,
    family: str,
    raw_task_ids: list[str],
    emphasis: str,
) -> list[str]:
    """Map narrow chart tags to stable analytical task buckets."""

    raw = set(raw_task_ids)
    tasks: list[str] = []

    def add(task_id: str) -> None:
        if task_id not in tasks:
            tasks.append(task_id)

    if raw & {
        "period_movement",
        "period_gap_shape",
        "period_gap_scan",
        "period_reconciliation",
        "exact_period_values",
        "mix_metric_trend",
        "total_over_periods",
        "composition_over_periods",
        "two_point_change",
        "two_point_gap",
    }:
        add("time_and_period_movement")
    if raw & {
        "rank_category_values",
        "snapshot_comparison",
        "period_comparison_summary",
        "ranked_gap_comparison",
    }:
        add("ranking_and_comparison")
    if raw & {
        "composition",
        "part_to_whole_by_category",
        "hierarchical_composition",
        "nested_category_comparison",
        "two_dimension_composition",
        "composition_over_periods",
        "mix_structure",
        "mix_shift",
        "two_metric_composition",
    }:
        add("composition_and_mix")
    if raw & {
        "metric_relationship",
        "outlier_detection",
        "size_weighted_outlier_detection",
        "rank_with_secondary_metric",
        "relationship_support",
        "total_with_secondary_metric",
    }:
        add("metric_relationship")
    if family == "distribution" or raw & {
        "distribution_shape",
        "distribution_compare_groups",
        "distribution_cumulative",
        "distribution_points",
    }:
        add("distribution")
    if family == "variance" or raw & {
        "variance_bridge",
        "variance_by_dimension",
        "variance_drilldown",
        "root_cause_variance",
        "price_volume_mix",
    }:
        add("variance_and_bridge")
    if family == "set_overlap" or raw & {"set_overlap", "set_overlap_by_panel"}:
        add("set_overlap")
    if raw & {
        "cohort_contribution",
        "like_for_like_comparison",
        "retention_or_newness",
        "loss_or_churn",
    }:
        add("cohort_and_population")
    if family in {"attributes", "funnel", "statement"} or raw & {
        "attribute_bundle_evidence",
        "attribute_signal_bridge",
        "shelf_visibility_evidence",
        "product_signal_validation",
        "funnel_conversion",
        "financial_statement",
        "exact_comparison_values",
    }:
        add("evidence_and_reporting_tables")

    if not tasks:
        add(family)
    return tasks


CAPABILITY_SEMANTICS: dict[str, dict[str, Any]] = {
    "period_comparison.trend": _cap(
        family="period_comparison",
        grammar="line_time_series",
        task_ids=["period_movement", "period_gap_shape"],
        emphasis="trajectory_shape",
        best_when="The reader needs to see the ordered period path: acceleration, reversal, narrowing, widening, or seasonality.",
        avoid_when="Avoid when exact values, total reconciliation, or a two-endpoint before/after comparison is the main message.",
        axis_roles={
            "x": "ordered_period",
            "y": "metric",
            "series": "scenario_or_comparison_period",
        },
        period_role="axis",
        metric_roles=["current_period_metric", "baseline_period_metric"],
        dimension_roles=["comparison_series"],
        competitors=[
            "period_comparison.by_period",
            "period_comparison.time_series_table",
            "period_comparison.slope",
            "period_comparison.horizontal_waterfall",
        ],
    ),
    "period_comparison.by_period": _cap(
        family="period_comparison",
        grammar="period_gap_comparison",
        task_ids=["period_movement", "period_gap_scan"],
        emphasis="period_by_period_gap",
        best_when="The reader needs to compare current and baseline period values across each month or week and see where gaps are largest.",
        avoid_when="Avoid when the story is only the smooth trajectory shape or a single reconciled total movement.",
        axis_roles={
            "x": "ordered_period",
            "y": "metric",
            "series": "scenario_or_comparison_period",
        },
        period_role="axis",
        metric_roles=[
            "current_period_metric",
            "baseline_period_metric",
            "delta_metric",
        ],
        dimension_roles=["comparison_series"],
        competitors=[
            "period_comparison.trend",
            "period_comparison.multitier_column",
            "period_comparison.time_series_table",
            "period_comparison.horizontal_waterfall",
        ],
    ),
    "period_comparison.time_series_table": _cap(
        family="period_comparison",
        grammar="period_table",
        task_ids=["period_movement", "exact_period_values"],
        emphasis="exact_values",
        best_when="The report needs citeable period values, deltas, and percent deltas rather than a primarily visual reading.",
        avoid_when="Avoid as the only visual when the reader must quickly perceive shape, gap, or reconciliation.",
        axis_roles={"rows": "ordered_period", "columns": "metric_and_delta"},
        period_role="axis_or_table",
        metric_roles=[
            "current_period_metric",
            "baseline_period_metric",
            "delta_metric",
            "percent_delta_metric",
        ],
        competitors=["period_comparison.trend", "period_comparison.by_period"],
    ),
    "period_comparison.comparison_table": _cap(
        family="period_comparison",
        grammar="comparison_table",
        task_ids=["period_comparison_summary", "exact_comparison_values"],
        emphasis="summary_exact_values",
        best_when="The reader needs compact exact AC/PY totals and deltas by comparison row.",
        avoid_when="Avoid when the message depends on the period path or monthly sequencing.",
        axis_roles={"rows": "comparison_item", "columns": "baseline_current_delta"},
        period_role="filter",
        metric_roles=[
            "current_period_metric",
            "baseline_period_metric",
            "delta_metric",
            "percent_delta_metric",
        ],
        dimension_roles=["comparison_window"],
        competitors=["period_comparison.time_series_table", "period_comparison.dot"],
    ),
    "period_comparison.multitier_column": _cap(
        family="period_comparison",
        grammar="comparison_column",
        task_ids=["period_movement", "period_gap_scan"],
        emphasis="compact_side_by_side_period_comparison",
        best_when="The reader needs a compact executive AC/PY period comparison with clear column contrast.",
        avoid_when="Avoid when line shape, exact values, or total bridge reconciliation is the main message.",
        axis_roles={
            "x": "ordered_period_or_category",
            "y": "metric",
            "series": "scenario_or_comparison_period",
        },
        period_role="axis",
        metric_roles=[
            "current_period_metric",
            "baseline_period_metric",
            "delta_metric",
        ],
        dimension_roles=["comparison_series"],
        competitors=[
            "period_comparison.trend",
            "period_comparison.by_period",
            "period_comparison.dot",
        ],
    ),
    "period_comparison.dot": _cap(
        family="period_comparison",
        grammar="dot_gap",
        task_ids=["period_movement", "two_point_gap", "ranked_gap_comparison"],
        emphasis="gap_between_two_values",
        best_when="The reader needs a low-clutter comparison of two values across categories, panels, or periods.",
        avoid_when="Avoid when the month-by-month path or additive reconciliation matters.",
        axis_roles={
            "x": "metric",
            "y": "category_or_period",
            "marks": "baseline_and_current",
        },
        period_role="axis",
        metric_roles=["current_period_metric", "baseline_period_metric"],
        dimension_roles=["comparison_item"],
        competitors=[
            "period_comparison.slope",
            "period_comparison.by_period",
            "period_comparison.multitier_column",
        ],
    ),
    "period_comparison.slope": _cap(
        family="period_comparison",
        grammar="slope_endpoint_change",
        task_ids=[
            "period_movement",
            "two_point_change",
            "relative_direction_comparison",
        ],
        emphasis="endpoint_direction_and_relative_change",
        best_when="The reader needs direction and magnitude of change between two endpoints, especially across multiple comparable items.",
        avoid_when="Avoid when intermediate months, exact values, or additive bridge components are essential.",
        axis_roles={"x": "two_endpoints", "y": "metric", "series": "item_or_panel"},
        period_role="axis",
        metric_roles=["current_period_metric", "baseline_period_metric"],
        dimension_roles=["comparison_item"],
        competitors=[
            "period_comparison.dot",
            "period_comparison.trend",
            "period_comparison.horizontal_waterfall",
        ],
    ),
    "period_comparison.horizontal_waterfall": _cap(
        family="period_comparison",
        grammar="period_bridge",
        task_ids=["period_movement", "period_reconciliation", "variance_bridge"],
        emphasis="additive_reconciliation",
        best_when="The reader needs to see how period variances add from previous total to current total.",
        avoid_when="Avoid when values are non-additive or the message is trend shape rather than reconciliation.",
        axis_roles={"x": "metric_delta", "y": "bridge_component_period"},
        period_role="axis",
        metric_roles=[
            "baseline_period_metric",
            "current_period_metric",
            "delta_metric",
        ],
        dimension_roles=["bridge_component_period"],
        competitors=[
            "period_comparison.trend",
            "period_comparison.by_period",
            "variance.scenario_bridge",
        ],
    ),
    "mix.bar": _cap(
        family="mix",
        grammar="ranked_bar",
        task_ids=["rank_category_values", "snapshot_comparison"],
        emphasis="ranked_single_metric_comparison",
        best_when="The reader needs a sorted comparison of one additive metric across items for one selected scope or period.",
        avoid_when="Avoid when composition, hierarchy, time movement, or a second metric relationship is the point.",
        axis_roles={"x": "metric", "y": "category"},
        period_role="filter",
        dimension_roles=["category"],
        competitors=["mix.stacked_bar", "mix.stacked_bar_overlay", "mix.multitier_bar"],
    ),
    "mix.stacked_bar": _cap(
        family="mix",
        grammar="stacked_bar",
        task_ids=["composition", "part_to_whole_by_category"],
        emphasis="composition_within_ranked_totals",
        best_when="The reader needs both total size and component composition across categories.",
        avoid_when="Avoid when exact component comparison or time trend is more important than composition.",
        axis_roles={
            "x": "metric_total",
            "y": "category",
            "stack": "component_dimension",
        },
        period_role="filter",
        dimension_roles=["category", "component_category"],
        competitors=["mix.bar", "mix.multitier_bar", "mix.stacked_bar_overlay"],
    ),
    "mix.stacked_bar_overlay": _cap(
        family="mix",
        grammar="bar_with_related_metric_marker",
        task_ids=["rank_with_secondary_metric", "relationship_support"],
        emphasis="primary_rank_plus_secondary_marker",
        best_when="The reader needs ranked contribution plus a related non-additive marker such as price, margin percentage, or growth.",
        avoid_when="Avoid when the secondary metric deserves a full relationship plot or when composition is the point.",
        axis_roles={"x": "primary_metric", "y": "category", "marker": "related_metric"},
        period_role="filter",
        metric_roles=["primary_additive_metric", "related_marker_metric"],
        dimension_roles=["category"],
        competitors=["mix.bar", "scatter.scatter", "scatter.bubble"],
    ),
    "mix.multitier_bar": _cap(
        family="mix",
        grammar="period_comparison_multitier_bar",
        task_ids=["period_movement", "ranked_gap_comparison", "two_point_gap"],
        emphasis="dimension_period_values_and_delta",
        best_when=(
            "The reader needs one dimension split into rows, with sales for two "
            "periods and their difference visible together; if a second dimension "
            "is needed, it becomes small-multiple panels."
        ),
        avoid_when=(
            "Avoid when the question is categorical hierarchy, composition, "
            "single-period ranking, or continuous trend shape."
        ),
        axis_roles={
            "x": "baseline_current_and_delta_metrics",
            "y": "dimension_member",
            "panel": "optional_second_dimension",
        },
        period_role="axis",
        metric_roles=[
            "baseline_period_metric",
            "current_period_metric",
            "delta_metric",
        ],
        metric_requirements=_comparison_metric_requirements(additive_only=True),
        dimension_roles=["dimension_member", "optional_panel"],
        competitors=[
            "period_comparison.dot",
            "period_comparison.slope",
            "period_comparison.multitier_column",
            "mix.bar",
        ],
    ),
    "mix.column": _cap(
        family="mix",
        grammar="total_column",
        task_ids=["total_over_periods", "period_summary"],
        emphasis="total_metric_by_period_or_scope",
        best_when="The reader needs a compact total metric column view across selected periods or scopes.",
        avoid_when="Avoid when component composition, relationship, or detailed period path is needed.",
        axis_roles={"x": "period_or_total_scope", "y": "metric"},
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        competitors=["mix.column_overlay", "period_comparison.trend"],
    ),
    "mix.column_overlay": _cap(
        family="mix",
        grammar="total_column_with_related_metric",
        task_ids=["total_with_secondary_metric", "period_summary"],
        emphasis="total_plus_related_marker",
        best_when="The reader needs total metric movement with a related marker shown in the same compact view.",
        avoid_when="Avoid when the relationship between metrics is the main analytical object.",
        axis_roles={
            "x": "period_or_total_scope",
            "y": "primary_metric",
            "marker": "related_metric",
        },
        period_role="axis",
        metric_roles=["primary_additive_metric", "related_marker_metric"],
        competitors=["mix.column", "mix.stacked_bar_overlay", "scatter.scatter"],
    ),
    "mix.stacked_column": _cap(
        family="mix",
        grammar="stacked_column",
        task_ids=["composition_over_periods", "mix_shift"],
        emphasis="composition_change_over_periods",
        best_when="The reader needs to see total and mix composition across periods or comparable scopes.",
        avoid_when="Avoid when exact values or simple trend shape matters more than composition.",
        axis_roles={
            "x": "period_or_scope",
            "y": "metric_total",
            "stack": "component_dimension",
        },
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["component_dimension"],
        competitors=["period_comparison.trend", "mix.stacked_bar", "mix.column"],
    ),
    "mix.like_for_like_column": _cap(
        family="mix",
        grammar="like_for_like_total_column",
        task_ids=["like_for_like_comparison"],
        emphasis="same_population_total_change",
        best_when="The reader needs total change on a stable like-for-like population.",
        avoid_when="Avoid when population churn or mix composition is the main finding.",
        axis_roles={"x": "comparison_period", "y": "metric"},
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["stable_population_flag"],
        competitors=[
            "mix.column",
            "mix.like_for_like_stacked_column",
            "mix.cohort_since_stacked_column",
            "mix.cohort_lost_stacked_column",
        ],
    ),
    "mix.like_for_like_stacked_column": _cap(
        family="mix",
        grammar="like_for_like_stacked_column",
        task_ids=["like_for_like_comparison", "mix_shift"],
        emphasis="same_population_composition_change",
        best_when="The reader needs like-for-like total movement and composition together.",
        avoid_when="Avoid when the population is not stable or exact detail is required.",
        axis_roles={
            "x": "comparison_period",
            "y": "metric_total",
            "stack": "component_dimension",
        },
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["stable_population_flag", "component_dimension"],
        competitors=["mix.like_for_like_column", "mix.stacked_column"],
    ),
    "mix.cohort_since_stacked_column": _cap(
        family="mix",
        grammar="cohort_stacked_column",
        task_ids=["cohort_contribution", "retention_or_newness"],
        emphasis="since_cohort_contribution",
        best_when="The reader needs to see contribution by first-active cohort over periods.",
        avoid_when="Avoid for simple time trend or non-cohort composition.",
        axis_roles={"x": "period", "y": "metric_total", "stack": "first_active_cohort"},
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["first_active_cohort"],
        competitors=[
            "mix.cohort_lost_stacked_column",
            "mix.like_for_like_column",
            "mix.stacked_column",
        ],
    ),
    "mix.cohort_lost_stacked_column": _cap(
        family="mix",
        grammar="cohort_stacked_column",
        task_ids=["cohort_contribution", "loss_or_churn"],
        emphasis="lost_cohort_contribution",
        best_when="The reader needs to see contribution by lost or last-active cohort.",
        avoid_when="Avoid for simple time trend or non-cohort composition.",
        axis_roles={
            "x": "period",
            "y": "metric_total",
            "stack": "lost_or_last_active_cohort",
        },
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["lost_or_last_active_cohort"],
        competitors=[
            "mix.cohort_since_stacked_column",
            "mix.like_for_like_column",
            "mix.stacked_column",
        ],
    ),
    "mix.timeline": _cap(
        family="mix",
        grammar="line_time_series",
        task_ids=["period_movement", "mix_metric_trend"],
        emphasis="single_metric_trend_shape",
        best_when="The reader needs the trend path of the primary mix metric across ordered periods.",
        avoid_when="Avoid when composition, hierarchy, or AC/PY period comparison is the main message.",
        axis_roles={"x": "ordered_period", "y": "metric"},
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        competitors=[
            "period_comparison.trend",
            "mix.column",
            "mix.area",
            "mix.stacked_column",
        ],
    ),
    "mix.area": _cap(
        family="mix",
        grammar="area_time_series",
        task_ids=["composition_over_periods", "mix_metric_trend"],
        emphasis="trend_with_cumulative_or_share_area",
        best_when="The reader needs a time-series area view for absolute contribution or share over periods.",
        avoid_when="Avoid when precise line trajectory or side-by-side period gaps are clearer.",
        axis_roles={
            "x": "ordered_period",
            "y": "metric_or_share",
            "fill": "component_optional",
        },
        period_role="axis",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["optional_component_dimension"],
        competitors=["mix.timeline", "mix.stacked_column", "period_comparison.trend"],
    ),
    "mix.marimekko": _cap(
        family="mix",
        grammar="marimekko",
        task_ids=["two_dimension_composition", "mix_structure"],
        emphasis="two_dimension_share_and_size",
        best_when="The reader needs to see composition across two categorical dimensions where both width and height carry meaning.",
        avoid_when="Avoid when categories are too many, exact comparison matters, or the question is a simple ranking.",
        axis_roles={
            "x_width": "category_share_or_size",
            "y_stack": "second_category_share",
            "area": "metric",
        },
        period_role="filter",
        dimension_roles=["width_category", "stack_category", "optional_panel"],
        competitors=["mix.barmekko", "mix.stacked_bar", "mix.multitier_bar"],
    ),
    "mix.barmekko": _cap(
        family="mix",
        grammar="barmekko",
        task_ids=["two_metric_composition", "price_volume_mix_view"],
        emphasis="width_metric_times_height_metric",
        best_when="The reader needs a variable-width composition where width and height represent different metrics.",
        avoid_when="Avoid without a meaningful width metric or when the area encoding would be hard to read.",
        axis_roles={
            "x_width": "width_metric",
            "y_height": "height_metric",
            "area": "combined_metric",
        },
        period_role="filter",
        metric_roles=["width_metric", "height_metric", "area_metric"],
        metric_requirements=_barmekko_metric_requirements(),
        dimension_roles=["width_category", "height_category"],
        competitors=["mix.marimekko", "scatter.bubble", "mix.stacked_bar_overlay"],
    ),
    "mix.pareto": _cap(
        family="mix",
        grammar="pareto",
        task_ids=["concentration", "rank_category_values"],
        emphasis="ranked_contribution_and_cumulative_share",
        best_when="The reader needs to identify the few categories that explain most of the metric.",
        avoid_when="Avoid when component composition, period movement, or nested hierarchy is the main message.",
        axis_roles={
            "x": "ranked_category",
            "y": "metric",
            "line": "cumulative_share_optional",
        },
        period_role="filter",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["category"],
        competitors=["mix.bar", "mix.stacked_pareto"],
    ),
    "mix.stacked_pareto": _cap(
        family="mix",
        grammar="stacked_pareto",
        task_ids=["concentration", "composition"],
        emphasis="concentration_with_component_breakdown",
        best_when="The reader needs Pareto concentration plus stacked composition by another dimension or class.",
        avoid_when="Avoid when a plain Pareto or plain stacked bar would be easier to read.",
        axis_roles={
            "x": "ranked_category_or_class",
            "y": "metric",
            "stack": "component_dimension",
        },
        period_role="filter",
        metric_roles=["primary_additive_metric"],
        dimension_roles=["category", "component_dimension"],
        competitors=["mix.pareto", "mix.stacked_bar"],
    ),
    "scatter.scatter": _cap(
        family="scatter_bubble",
        grammar="scatter_relationship",
        task_ids=["metric_relationship", "outlier_detection"],
        emphasis="relationship_between_two_metrics",
        best_when="The reader needs to see association, clusters, quadrants, or outliers between two metrics.",
        avoid_when="Avoid for time trends, one-dimensional ranking, or exact tables.",
        axis_roles={"x": "metric", "y": "metric", "color_or_panel": "dimension"},
        period_role="filter",
        metric_roles=["x_metric", "y_metric"],
        dimension_roles=["point_dimension", "optional_panel"],
        competitors=["scatter.bubble", "mix.stacked_bar_overlay", "mix.bar"],
    ),
    "scatter.bubble": _cap(
        family="scatter_bubble",
        grammar="bubble_relationship",
        task_ids=["metric_relationship", "size_weighted_outlier_detection"],
        emphasis="two_metric_relationship_plus_size",
        best_when="The reader needs x/y relationship plus magnitude encoded by bubble size.",
        avoid_when="Avoid when bubble size would obscure the relationship or when period movement is the question.",
        axis_roles={
            "x": "metric",
            "y": "metric",
            "size": "metric",
            "color_or_panel": "dimension",
        },
        period_role="filter",
        metric_roles=["x_metric", "y_metric", "size_metric"],
        dimension_roles=["point_dimension", "optional_panel"],
        competitors=["scatter.scatter", "mix.stacked_bar_overlay"],
    ),
    "distribution.histogram": _cap(
        family="distribution",
        grammar="histogram",
        task_ids=["distribution_shape"],
        emphasis="frequency_shape",
        best_when="The reader needs to see bins, skew, modal ranges, or rough frequency shape for one metric.",
        avoid_when="Avoid when exact percentile comparison or individual points are needed.",
        axis_roles={"x": "metric_bins", "y": "count_or_frequency"},
        period_role="filter",
        competitors=[
            "distribution.boxplot",
            "distribution.kernel_density",
            "distribution.stripplot",
        ],
    ),
    "distribution.boxplot": _cap(
        family="distribution",
        grammar="boxplot",
        task_ids=["distribution_compare_groups"],
        emphasis="spread_and_outliers_summary",
        best_when="The reader needs median, quartiles, spread, and outliers, especially across groups.",
        avoid_when="Avoid when distribution shape details or individual observations matter.",
        axis_roles={"x": "group_optional", "y": "metric_distribution"},
        period_role="filter",
        competitors=[
            "distribution.stripplot",
            "distribution.histogram",
            "distribution.ecdf",
            "distribution.kernel_density",
        ],
    ),
    "distribution.stripplot": _cap(
        family="distribution",
        grammar="stripplot",
        task_ids=["distribution_points"],
        emphasis="individual_observations",
        best_when="The reader needs to see individual observations, density, and outliers without summarizing them away.",
        avoid_when="Avoid with too many points or when an aggregate distribution shape is enough.",
        axis_roles={"x": "group_optional", "y": "metric_points"},
        period_role="filter",
        competitors=[
            "distribution.boxplot",
            "distribution.histogram",
            "distribution.ecdf",
            "distribution.kernel_density",
        ],
    ),
    "distribution.ecdf": _cap(
        family="distribution",
        grammar="ecdf",
        task_ids=["distribution_cumulative"],
        emphasis="cumulative_distribution_and_percentiles",
        best_when="The reader needs percentile thresholds or cumulative share below/above values.",
        avoid_when="Avoid when frequency bins or individual observations are easier for the reader.",
        axis_roles={"x": "metric", "y": "cumulative_share"},
        period_role="filter",
        competitors=[
            "distribution.histogram",
            "distribution.boxplot",
            "distribution.stripplot",
        ],
    ),
    "distribution.kernel_density": _cap(
        family="distribution",
        grammar="density_curve",
        task_ids=["distribution_shape"],
        emphasis="smoothed_distribution_shape",
        best_when="The reader needs a smoothed view of distribution shape across one or more groups.",
        avoid_when="Avoid when sample size is small or exact bins/observations are important.",
        axis_roles={"x": "metric", "y": "estimated_density"},
        period_role="filter",
        competitors=[
            "distribution.histogram",
            "distribution.ecdf",
            "distribution.boxplot",
            "distribution.stripplot",
        ],
    ),
    "variance.scenario_bridge": _cap(
        family="variance",
        grammar="variance_waterfall",
        task_ids=["variance_bridge"],
        emphasis="scenario_reconciliation",
        best_when=(
            "Use for the plain bridge from one baseline total to one current total "
            "when the message is the additive reconciliation itself, not a ranked "
            "dimension split, root-cause path, or PVM mechanics."
        ),
        avoid_when=(
            "Avoid when the question names a dimension to split by, asks for nested "
            "drilldowns, asks why via root-cause ordering, asks for price/volume/mix, "
            "or when trend shape is the message."
        ),
        axis_roles={"x": "variance_step", "y": "metric_delta"},
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=["variance_step"],
        competitors=[
            "period_comparison.horizontal_waterfall",
            "variance.total_by_dimension_bridge",
            "variance.root_cause_total_bridge",
            "variance.price_volume_mix",
        ],
    ),
    "variance.total_by_dimension_bridge": _cap(
        family="variance",
        grammar="dimension_variance_bridge",
        task_ids=["variance_by_dimension"],
        emphasis="total_delta_split_by_dimension",
        best_when=(
            "Use when the question explicitly asks how the total delta is distributed "
            "across members of one named dimension, such as category, retailer, "
            "region, brand, or channel."
        ),
        avoid_when=(
            "Avoid when the reader needs the generic total bridge, a nested parent/child "
            "drilldown, an ordered root-cause path across multiple dimensions, or "
            "price-volume-mix mechanics."
        ),
        axis_roles={"x": "dimension_member", "y": "metric_delta"},
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=["dimension_member"],
        competitors=[
            "variance.scenario_bridge",
            "variance.root_cause_total_bridge",
            "variance.exploded_variance_bridge",
        ],
    ),
    "variance.exploded_variance_bridge": _cap(
        family="variance",
        grammar="parent_child_variance_bridge",
        task_ids=["variance_drilldown"],
        emphasis="parent_bridge_with_child_drilldowns",
        best_when=(
            "Use when the question names one parent grouping dimension and one fixed "
            "second decomposition dimension to explain selected parent-row variance "
            "moves in the same visual."
        ),
        avoid_when=(
            "Avoid when only one dimension is requested, when the second dimension "
            "is not meaningful within each parent member, when the task is a "
            "variable mixed-dimension root-cause ordering, when PVM mechanics are "
            "required, or when exact tabular detail is the deliverable."
        ),
        axis_roles={"x": "parent_and_child_driver", "y": "metric_delta"},
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=["parent_driver", "child_driver"],
        dimension_contract={
            "required_roles": ["parent_driver", "child_driver"],
            "distinct_dimensions_required": True,
            "parent_dimension_behavior": (
                "Left panel ranks members of one fixed parent dimension by total "
                "delta."
            ),
            "child_dimension_behavior": (
                "Right-side drilldown panels decompose selected parent members by "
                "one fixed child/decomposition dimension."
            ),
            "child_dimension_scope": "constant_across_all_drilldown_panels",
            "child_dimension_meaning": (
                "The second dimension should be a natural child of the parent or "
                "a meaningful within-parent cross-cut. This semantic validity is "
                "dataset/question-specific."
            ),
            "selector_responsibility": (
                "The selector/orchestrator must choose both dimensions from the "
                "question, dataset profile, and semantic validity layer. Plugin "
                "fallback order is mechanical and must not be treated as semantic "
                "dimension selection."
            ),
            "not_a_root_cause_path": (
                "Rows do not switch dimensional grain. Use root-cause bridge "
                "capabilities when the analysis needs a variable mixed-dimension "
                "driver path."
            ),
        },
        competitors=[
            "variance.root_cause_exploded_bridge",
            "variance.root_cause_component_bridge",
            "variance.total_by_dimension_bridge",
        ],
    ),
    "variance.root_cause_exploded_bridge": _cap(
        family="variance",
        grammar="root_cause_exploded_bridge",
        task_ids=["root_cause_variance", "variance_drilldown"],
        emphasis="root_cause_path_with_nested_drilldowns",
        best_when=(
            "Use when the question asks for a variable mixed-dimension root-cause "
            "variance path and also asks to explain selected root-cause drivers "
            "with nested root-cause bridge drilldowns."
        ),
        avoid_when=(
            "Avoid when the question names a fixed parent dimension and fixed child "
            "decomposition dimension; use variance.exploded_variance_bridge instead. "
            "Avoid when only a one-level root-cause path is needed, or when exact "
            "tabular detail is the deliverable."
        ),
        axis_roles={
            "left": "root_cause_driver_sequence",
            "right": "nested_root_cause_driver_sequence",
            "y": "metric_delta",
        },
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=[
            "root_cause_driver_sequence",
            "optional_nested_root_cause_driver_sequence",
        ],
        dimension_contract={
            "required_roles": ["root_cause_driver_sequence"],
            "optional_roles": ["nested_root_cause_driver_sequence"],
            "left_panel_behavior": (
                "Left panel shows a variable mixed-dimension root-cause bridge "
                "sequence."
            ),
            "right_panel_behavior": (
                "Right-side panels rerun or nest root-cause bridge logic inside "
                "selected left-row slices."
            ),
            "nested_dimension_scope": "row_specific",
            "selector_responsibility": (
                "Use only when the question asks for root causes plus explanation "
                "of selected drivers. Do not select a fixed child dimension for "
                "all right-side panels."
            ),
            "not_a_fixed_parent_child_bridge": (
                "Rows may switch dimensional grain. Use "
                "variance.exploded_variance_bridge for a fixed parent_dimension "
                "plus fixed child_dimension."
            ),
        },
        competitors=[
            "variance.root_cause_total_bridge",
            "variance.exploded_variance_bridge",
            "variance.root_cause_component_bridge",
        ],
    ),
    "variance.root_cause_total_bridge": _cap(
        family="variance",
        grammar="root_cause_total_bridge",
        task_ids=["root_cause_variance"],
        emphasis="root_cause_total_movement",
        best_when=(
            "Use when the question asks for the ordered root-cause sequence behind "
            "the total movement across available dimensions, and the output should "
            "show which driver path explains the overall delta."
        ),
        avoid_when=(
            "Avoid for a simple total bridge, a one-dimension split, a component-only "
            "root-cause question, or PVM decomposition."
        ),
        axis_roles={"x": "ordered_root_cause_driver", "y": "metric_delta"},
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=["root_cause_driver_sequence"],
        competitors=[
            "variance.root_cause_exploded_bridge",
            "variance.total_by_dimension_bridge",
            "variance.root_cause_component_bridge",
            "variance.scenario_bridge",
        ],
    ),
    "variance.root_cause_component_bridge": _cap(
        family="variance",
        grammar="root_cause_component_bridge",
        task_ids=["root_cause_variance"],
        emphasis="component_level_root_cause",
        best_when=(
            "Use when the question asks why one variance component changed, not why "
            "the overall total changed; the chart drills into the drivers of that "
            "component-level variance."
        ),
        avoid_when=(
            "Avoid when the report needs the total movement root-cause sequence, a "
            "simple dimension split, the plain total bridge, or PVM mechanics."
        ),
        axis_roles={"x": "component_root_cause_driver", "y": "component_delta"},
        period_role="filter",
        metric_roles=["baseline_metric", "current_metric", "delta_metric"],
        metric_requirements=_variance_metric_requirements(),
        dimension_roles=["variance_component", "component_root_cause_driver"],
        competitors=[
            "variance.root_cause_total_bridge",
            "variance.total_by_dimension_bridge",
        ],
    ),
    "variance.price_volume_mix": _cap(
        family="variance",
        grammar="price_volume_mix_ladder",
        task_ids=["price_volume_mix"],
        emphasis="pvm_decomposition_comparison",
        best_when=(
            "Use only when the business question explicitly asks how value movement "
            "decomposes into price, volume, and mix effects, and the dataset has "
            "compatible value, units/volume, and price or derived price semantics."
        ),
        avoid_when=(
            "Avoid for generic variance explanations, one-dimension splits, root-cause "
            "ordering, or any dataset without compatible value, volume, and rate "
            "semantics at the same grain."
        ),
        axis_roles={"x": "decomposition_stage", "y": "metric_delta"},
        period_role="filter",
        metric_roles=["value_metric", "volume_metric", "price_or_rate_metric"],
        metric_requirements=_pvm_metric_requirements(),
        dimension_roles=["period_or_scenario_pair"],
        competitors=[
            "variance.scenario_bridge",
            "variance.root_cause_total_bridge",
            "variance.total_by_dimension_bridge",
        ],
    ),
    "set_overlap.upset": _cap(
        family="set_overlap",
        grammar="upset_plot",
        task_ids=["set_overlap"],
        emphasis="many_set_intersections",
        best_when="The reader needs to compare intersections across more than two sets.",
        avoid_when="Avoid when only two or three simple sets need a familiar Venn view.",
        axis_roles={"x": "set_intersection", "y": "count"},
        metric_roles=[],
        dimension_roles=["set_membership_fields"],
        competitors=["set_overlap.venn", "set_overlap.upset_small_multiples"],
    ),
    "set_overlap.upset_small_multiples": _cap(
        family="set_overlap",
        grammar="upset_small_multiples",
        task_ids=["set_overlap_by_panel"],
        emphasis="intersection_patterns_across_panels",
        best_when="The reader needs to compare overlap structures across panels or segments.",
        avoid_when="Avoid when one aggregate overlap view is enough.",
        axis_roles={"x": "set_intersection", "y": "count", "panel": "segment"},
        metric_roles=[],
        dimension_roles=["set_membership_fields", "panel_or_segment"],
        competitors=["set_overlap.upset"],
    ),
    "set_overlap.venn": _cap(
        family="set_overlap",
        grammar="venn",
        task_ids=["set_overlap"],
        emphasis="simple_two_or_three_set_overlap",
        best_when="The reader needs an intuitive overlap picture for two or three sets.",
        avoid_when="Avoid with more than three sets or many intersections.",
        axis_roles={"areas": "set_counts_and_intersections"},
        metric_roles=[],
        dimension_roles=["two_or_three_set_membership_fields"],
        competitors=["set_overlap.upset"],
    ),
    "funnel.stage_table": _cap(
        family="funnel",
        grammar="funnel_stage_table",
        task_ids=["funnel_conversion"],
        emphasis="stage_counts_and_conversion",
        best_when="The reader needs exact stage counts, conversion rates, and drop-offs.",
        avoid_when="Avoid when a visual shape is more important than exact stage evidence.",
        axis_roles={"rows": "ordered_stage", "columns": "count_and_conversion"},
        period_role="none",
        metric_roles=[
            "stage_start_count",
            "stage_pass_count",
            "dropoff_count",
            "conversion_rate",
        ],
        metric_requirements=_funnel_metric_requirements(),
        dimension_roles=["ordered_stage"],
    ),
    "statement.pnl_table": _cap(
        family="statement",
        grammar="pnl_statement_table",
        task_ids=["financial_statement"],
        emphasis="structured_statement_values",
        best_when="The reader needs a P&L-style table with business rows and comparison columns.",
        avoid_when="Avoid for exploratory charting or relationship analysis.",
        axis_roles={"rows": "statement_line_item", "columns": "period_or_scenario"},
        period_role="axis_or_table",
        metric_roles=["statement_value"],
        metric_requirements=_statement_metric_requirements(),
        dimension_roles=["statement_line_item"],
    ),
    "attributes.attribute_bundle_comparison_table": _cap(
        family="attributes",
        grammar="attribute_evidence_table",
        task_ids=["attribute_bundle_evidence"],
        emphasis="bundle_share_and_index_evidence",
        best_when="The reader needs exact bundle evidence for current winners or emerging signals.",
        avoid_when="Avoid for product-level validation or shelf visibility decomposition.",
        axis_roles={
            "rows": "attribute_bundle",
            "columns": "focus_baseline_delta_index",
        },
        metric_roles=["focus_share", "baseline_share", "delta_metric", "index_metric"],
        metric_requirements=_attribute_table_metric_requirements(
            derived_roles=[
                (
                    "focus_share",
                    ["attribute_evidence_package", "focus_cohort"],
                    "package-derived share for the selected focus cohort",
                ),
                (
                    "baseline_share",
                    ["attribute_evidence_package", "baseline_cohort"],
                    "package-derived share for the baseline cohort",
                ),
                (
                    "delta_metric",
                    ["focus_share", "baseline_share"],
                    "focus_share - baseline_share",
                ),
                (
                    "index_metric",
                    ["focus_share", "baseline_share"],
                    "focus_share / baseline_share when baseline is non-zero",
                ),
            ],
            note=(
                "Attribute evidence tables are rendered from a reviewed attribute "
                "package; they do not accept arbitrary raw dataset metrics."
            ),
        ),
        dimension_roles=["attribute_bundle"],
        competitors=[
            "attributes.attribute_bridge_table",
            "attributes.product_signal_evidence_table",
            "attributes.rank_weighted_visibility_table",
        ],
    ),
    "attributes.attribute_bridge_table": _cap(
        family="attributes",
        grammar="attribute_bridge_table",
        task_ids=["attribute_signal_bridge"],
        emphasis="current_vs_emerging_signal_alignment",
        best_when="The reader needs to compare current winners with emerging signals and see alignment or divergence.",
        avoid_when="Avoid when only one cohort layer exists.",
        axis_roles={
            "rows": "signal_bundle",
            "columns": "current_and_emerging_evidence",
        },
        metric_roles=[
            "current_signal_metric",
            "emerging_signal_metric",
            "alignment_metric",
        ],
        metric_requirements=_attribute_table_metric_requirements(
            derived_roles=[
                (
                    "current_signal_metric",
                    ["attribute_evidence_package", "current_cohort"],
                    "package-derived current winner signal",
                ),
                (
                    "emerging_signal_metric",
                    ["attribute_evidence_package", "emerging_cohort"],
                    "package-derived emerging signal",
                ),
                (
                    "alignment_metric",
                    ["current_signal_metric", "emerging_signal_metric"],
                    "package-defined alignment or divergence between current and emerging signals",
                ),
            ],
            note=(
                "The bridge table requires a reviewed signal package with current "
                "and emerging cohorts; raw categorical columns are not enough."
            ),
        ),
        dimension_roles=["signal_bundle", "cohort_layer"],
        competitors=[
            "attributes.attribute_bundle_comparison_table",
            "attributes.product_signal_evidence_table",
            "attributes.rank_weighted_visibility_table",
        ],
    ),
    "attributes.rank_weighted_visibility_table": _cap(
        family="attributes",
        grammar="visibility_evidence_table",
        task_ids=["shelf_visibility_evidence"],
        emphasis="rank_weighted_visibility",
        best_when="The reader needs visibility, incremental lane contribution, or alpha robustness evidence.",
        avoid_when="Avoid as demand, sales, or causality evidence.",
        axis_roles={"rows": "rank_or_lane", "columns": "visibility_metrics"},
        metric_roles=[
            "gross_weight",
            "incremental_weight",
            "cumulative_weight",
            "robustness_metric",
        ],
        metric_requirements=_attribute_table_metric_requirements(
            derived_roles=[
                (
                    "gross_weight",
                    ["attribute_evidence_package", "rank_or_lane"],
                    "package-derived gross rank-weighted visibility",
                ),
                (
                    "incremental_weight",
                    ["attribute_evidence_package", "rank_or_lane"],
                    "package-derived incremental rank-weighted visibility",
                ),
                (
                    "cumulative_weight",
                    ["attribute_evidence_package", "rank_or_lane"],
                    "package-derived cumulative rank-weighted visibility",
                ),
                (
                    "robustness_metric",
                    ["attribute_evidence_package"],
                    "package-derived robustness across visibility assumptions",
                ),
            ],
            note=(
                "Rank-weighted visibility is a package-derived evidence table; "
                "rank/lane candidates alone do not create the visibility metrics."
            ),
        ),
        dimension_roles=["rank_or_lane"],
        competitors=[
            "attributes.attribute_bridge_table",
            "attributes.attribute_bundle_comparison_table",
            "attributes.product_signal_evidence_table",
        ],
    ),
    "attributes.product_signal_evidence_table": _cap(
        family="attributes",
        grammar="product_evidence_table",
        task_ids=["product_signal_validation"],
        emphasis="product_level_grounding",
        best_when="The reader needs product-level support for selected bundles or standout examples.",
        avoid_when="Avoid for ranking category-wide signal prevalence.",
        axis_roles={"rows": "product", "columns": "signal_and_validation_fields"},
        metric_roles=["product_signal_score", "validation_metric"],
        metric_requirements=_attribute_table_metric_requirements(
            derived_roles=[
                (
                    "product_signal_score",
                    ["attribute_evidence_package", "product"],
                    "package-derived product support score for the selected signal",
                ),
                (
                    "validation_metric",
                    ["attribute_evidence_package", "product"],
                    "package-derived validation evidence from PDP, review, or consistency fields",
                ),
            ],
            note=(
                "Product signal evidence requires a reviewed product/signal package; "
                "a raw product dimension does not produce these fields by itself."
            ),
        ),
        dimension_roles=["product", "signal_bundle"],
        competitors=[
            "attributes.attribute_bridge_table",
            "attributes.attribute_bundle_comparison_table",
            "attributes.rank_weighted_visibility_table",
        ],
    ),
}


ANALYSIS_TASKS: dict[str, dict[str, str]] = {
    "time_and_period_movement": {
        "label": "Time and period movement",
        "description": "Understand movement across ordered periods, current-vs-baseline period windows, or period-based summaries.",
    },
    "ranking_and_comparison": {
        "label": "Ranking and comparison",
        "description": "Compare categories, entities, or periods by value, gap, rank, or compact summary.",
    },
    "composition_and_mix": {
        "label": "Composition and mix",
        "description": "Show part-to-whole structure, nested categories, mix shift, or two-dimensional composition.",
    },
    "metric_relationship": {
        "label": "Metric relationship and secondary metrics",
        "description": "Show relationships, outliers, or secondary metric markers across observations.",
    },
    "distribution": {
        "label": "Distribution",
        "description": "Show shape, spread, density, cumulative share, or individual observations for a metric.",
    },
    "variance_and_bridge": {
        "label": "Variance and bridge",
        "description": "Reconcile movement through additive drivers, root-cause components, or price-volume-mix decompositions.",
    },
    "cohort_and_population": {
        "label": "Cohort and population",
        "description": "Compare stable populations, new/lost cohorts, or retention/churn-style contribution.",
    },
    "set_overlap": {
        "label": "Set overlap",
        "description": "Show intersections across sets or segments.",
    },
    "evidence_and_reporting_tables": {
        "label": "Evidence and reporting tables",
        "description": "Provide exact values, statement rows, funnel stages, attribute evidence, product support, or visibility detail.",
    },
}


ITERATIONS = [
    {
        "iteration": 1,
        "looked_for": "Whether artifact entries and capability semantics were mixed.",
        "correction": "Split generated artifacts from capability records.",
    },
    {
        "iteration": 2,
        "looked_for": "Tautological when-to-use values.",
        "correction": "Capability records now use best_when and avoid_when; artifact fallback text is not used for selection.",
    },
    {
        "iteration": 3,
        "looked_for": "Whether line/trend is represented as a period-axis chart.",
        "correction": "period_comparison.trend has visual_grammar=line_time_series and period_semantics.role=axis.",
    },
    {
        "iteration": 4,
        "looked_for": "Scatter/bubble period leakage.",
        "correction": "scatter capabilities use period_semantics.role=filter and supports_period_axis=false.",
    },
    {
        "iteration": 5,
        "looked_for": "Different objectives among period charts.",
        "correction": "Added selection_emphasis values for trajectory, gap scan, exact values, endpoint change, and reconciliation.",
    },
    {
        "iteration": 6,
        "looked_for": "Bar-family ambiguity.",
        "correction": "Separated ranked bar, stacked composition, related metric overlay, and hierarchical multitier grammar.",
    },
    {
        "iteration": 7,
        "looked_for": "Distribution chart distinctions.",
        "correction": "Separated frequency shape, spread summary, individual observations, cumulative distribution, and smoothed density.",
    },
    {
        "iteration": 8,
        "looked_for": "Variance chart distinctions.",
        "correction": "Separated scenario bridge, dimension bridge, parent-child bridge, root-cause bridges, and PVM ladder.",
    },
    {
        "iteration": 9,
        "looked_for": "Whether all existing artifacts still map to a capability.",
        "correction": "Preserved every gallery item as an example under its capability.",
    },
    {
        "iteration": 10,
        "looked_for": "Whether the result can distinguish valid alternatives rather than choose one chart per question.",
        "correction": "Added competing_capability_ids and selection_emphasis so broad tasks can have multiple valid treatments.",
    },
]

SEMANTIC_PROBES = [
    {
        "probe_id": "monthly_trend_shape",
        "question": "Show how monthly sales moved over time.",
        "task_id": "time_and_period_movement",
        "required_capability_ids": ["period_comparison.trend", "mix.timeline"],
        "forbidden_capability_ids": ["scatter.scatter", "scatter.bubble"],
        "required_emphases": ["trajectory_shape", "single_metric_trend_shape"],
    },
    {
        "probe_id": "monthly_exact_values",
        "question": "Show exact monthly values and deltas for citation.",
        "task_id": "time_and_period_movement",
        "required_capability_ids": ["period_comparison.time_series_table"],
        "forbidden_capability_ids": ["scatter.scatter", "scatter.bubble"],
        "required_emphases": ["exact_values"],
    },
    {
        "probe_id": "monthly_reconciliation",
        "question": "Explain how monthly variances add up to the total change.",
        "task_id": "time_and_period_movement",
        "required_capability_ids": ["period_comparison.horizontal_waterfall"],
        "forbidden_capability_ids": ["period_comparison.trend", "scatter.scatter"],
        "required_emphases": ["additive_reconciliation"],
    },
    {
        "probe_id": "one_month_rank",
        "question": "Compare brands in one selected month.",
        "task_id": "ranking_and_comparison",
        "required_capability_ids": ["mix.bar", "mix.pareto"],
        "forbidden_capability_ids": ["period_comparison.trend", "scatter.scatter"],
        "required_emphases": [
            "ranked_single_metric_comparison",
            "ranked_contribution_and_cumulative_share",
        ],
    },
    {
        "probe_id": "two_metric_relationship",
        "question": "Show the relationship between sales and distribution.",
        "task_id": "metric_relationship",
        "required_capability_ids": ["scatter.scatter", "scatter.bubble"],
        "forbidden_capability_ids": ["period_comparison.trend", "mix.bar"],
        "required_emphases": [
            "relationship_between_two_metrics",
            "two_metric_relationship_plus_size",
        ],
    },
    {
        "probe_id": "composition_shift",
        "question": "Show how mix composition changed across periods.",
        "task_id": "composition_and_mix",
        "required_capability_ids": ["mix.stacked_column", "mix.area"],
        "forbidden_capability_ids": ["scatter.scatter", "period_comparison.dot"],
        "required_emphases": [
            "composition_change_over_periods",
            "trend_with_cumulative_or_share_area",
        ],
    },
    {
        "probe_id": "distribution_shape",
        "question": "Show the distribution of unit price.",
        "task_id": "distribution",
        "required_capability_ids": [
            "distribution.histogram",
            "distribution.boxplot",
            "distribution.stripplot",
        ],
        "forbidden_capability_ids": ["period_comparison.trend", "mix.bar"],
        "required_emphases": [
            "frequency_shape",
            "spread_and_outliers_summary",
            "individual_observations",
        ],
    },
    {
        "probe_id": "variance_reconciliation",
        "question": "Reconcile total movement from baseline to current with a plain bridge.",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.scenario_bridge"],
        "forbidden_capability_ids": [
            "mix.barmekko",
            "scatter.scatter",
            "variance.price_volume_mix",
        ],
        "required_emphases": ["scenario_reconciliation"],
    },
    {
        "probe_id": "variance_dimension_split",
        "question": "Which categories account for the total variance?",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.total_by_dimension_bridge"],
        "forbidden_capability_ids": [
            "variance.scenario_bridge",
            "variance.root_cause_total_bridge",
        ],
        "required_emphases": ["total_delta_split_by_dimension"],
    },
    {
        "probe_id": "variance_parent_child_drilldown",
        "question": "Which categories drove variance, and which brands explain the selected category moves?",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.exploded_variance_bridge"],
        "forbidden_capability_ids": [
            "variance.total_by_dimension_bridge",
            "variance.price_volume_mix",
        ],
        "required_emphases": ["parent_bridge_with_child_drilldowns"],
    },
    {
        "probe_id": "variance_root_cause_total",
        "question": "Which ordered root-cause path explains the total movement?",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.root_cause_total_bridge"],
        "forbidden_capability_ids": [
            "variance.scenario_bridge",
            "variance.total_by_dimension_bridge",
        ],
        "required_emphases": ["root_cause_total_movement"],
    },
    {
        "probe_id": "variance_root_cause_exploded",
        "question": (
            "Which ordered root-cause path explains the total movement, and what "
            "explains the selected root-cause drivers?"
        ),
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.root_cause_exploded_bridge"],
        "forbidden_capability_ids": [
            "variance.exploded_variance_bridge",
            "variance.total_by_dimension_bridge",
        ],
        "required_emphases": ["root_cause_path_with_nested_drilldowns"],
    },
    {
        "probe_id": "variance_root_cause_component",
        "question": "Which drivers explain the selected root-cause component?",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.root_cause_component_bridge"],
        "forbidden_capability_ids": [
            "variance.root_cause_total_bridge",
            "variance.price_volume_mix",
        ],
        "required_emphases": ["component_level_root_cause"],
    },
    {
        "probe_id": "variance_pvm",
        "question": "How much of the value movement is due to price, units, and mix?",
        "task_id": "variance_and_bridge",
        "required_capability_ids": ["variance.price_volume_mix"],
        "forbidden_capability_ids": [
            "variance.scenario_bridge",
            "variance.total_by_dimension_bridge",
        ],
        "required_emphases": ["pvm_decomposition_comparison"],
    },
    {
        "probe_id": "set_intersections",
        "question": "Show overlaps across several sets.",
        "task_id": "set_overlap",
        "required_capability_ids": ["set_overlap.upset"],
        "forbidden_capability_ids": ["distribution.histogram", "mix.stacked_bar"],
        "required_emphases": ["many_set_intersections"],
    },
    {
        "probe_id": "product_evidence_table",
        "question": "Show product-level evidence for selected attribute bundles.",
        "task_id": "evidence_and_reporting_tables",
        "required_capability_ids": ["attributes.product_signal_evidence_table"],
        "forbidden_capability_ids": ["period_comparison.trend", "mix.pareto"],
        "required_emphases": ["product_level_grounding"],
    },
]


def _load_source_manifest() -> dict[str, Any]:
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Source manifest must be a JSON object.")
    return payload


def _generated_manifest_capability_ids() -> set[str]:
    """Return capability IDs evidenced by generated static artifact records.

    This is deterministic because it only extracts exact schema fields and a
    small legacy plugin/stem map for generated artifacts whose source files
    exist but whose older manifests did not carry capability IDs.
    """

    capability_ids: set[str] = set()
    for manifest_path in (REPO_ROOT / "static" / "shared").glob("**/manifest.json"):
        if manifest_path == SOURCE_MANIFEST:
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        plugin = _source_manifest_plugin(payload, manifest_path)
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            capability_id = _source_artifact_capability_id(
                artifact,
                plugin=plugin,
            )
            if _is_known_capability_id(capability_id):
                capability_ids.add(capability_id)
    capability_ids.update(_legacy_static_artifact_capability_ids())
    return capability_ids


def _source_manifest_plugin(payload: dict[str, Any], manifest_path: Path) -> str:
    plugin = payload.get("plugin")
    if isinstance(plugin, str) and plugin.strip():
        return plugin.strip()
    parts = manifest_path.relative_to(REPO_ROOT / "static" / "shared").parts
    if parts and parts[0] == "period":
        return "period-comparison"
    if parts and parts[0] == "set_overlap":
        return "set-overlap-analysis"
    if parts and parts[0] == "variance":
        return "variance-analysis"
    if parts and parts[0].startswith("mix_"):
        return "mix-contribution-analysis"
    return parts[0] if parts else ""


def _source_artifact_capability_id(
    artifact: dict[str, Any],
    *,
    plugin: str,
) -> str | None:
    stem = _source_artifact_stem(artifact)
    if stem:
        override = LEGACY_STATIC_ARTIFACT_CAPABILITY_BY_STEM.get((plugin, stem))
        if override is not None:
            return override
    capability_id = artifact.get("capability_id")
    return capability_id if isinstance(capability_id, str) else None


def _source_artifact_stem(artifact: dict[str, Any]) -> str | None:
    for key in ("artifact_id", "path", "source_path", "pack_path"):
        value = artifact.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).stem
    paths = artifact.get("paths")
    if isinstance(paths, dict):
        for value in paths.values():
            if isinstance(value, str) and Path(value).suffix.lower() in {
                ".html",
                ".png",
            }:
                return Path(value).stem
    return None


def _legacy_static_artifact_capability_ids() -> set[str]:
    capability_ids: set[str] = set()
    for artifact_path in (REPO_ROOT / "static" / "shared").glob("**/*"):
        if not artifact_path.is_file() or artifact_path == SOURCE_MANIFEST:
            continue
        if artifact_path.suffix.lower() not in {".html", ".png"}:
            continue
        if any(part == "png-gallery" for part in artifact_path.parts):
            continue
        plugin = _static_artifact_plugin(artifact_path)
        capability_id = LEGACY_STATIC_ARTIFACT_CAPABILITY_BY_STEM.get(
            (plugin, artifact_path.stem)
        )
        if _is_known_capability_id(capability_id):
            capability_ids.add(capability_id)
    return capability_ids


def _static_artifact_plugin(artifact_path: Path) -> str:
    parts = artifact_path.relative_to(REPO_ROOT / "static" / "shared").parts
    if not parts:
        return ""
    source = parts[0]
    if source == "period":
        return "period-comparison"
    if source == "set_overlap":
        return "set-overlap-analysis"
    if source == "variance":
        return "variance-analysis"
    if source.startswith("mix_"):
        return "mix-contribution-analysis"
    return source


def _is_known_capability_id(value: Any) -> bool:
    return isinstance(value, str) and value in CAPABILITY_SEMANTICS


def _decision_cues(capability_id: str, capability: dict[str, Any]) -> dict[str, Any]:
    """Return explicit selector cues for a capability.

    This is deterministic because it copies reviewed cue fields for the
    capability's explicit selection_emphasis; it does not infer intent from a
    user's question.
    """

    emphasis = capability["selection_emphasis"]
    cues = DECISION_CUES_BY_EMPHASIS.get(emphasis)
    if cues is None:
        raise ValueError(f"Missing decision cues for {capability_id}: {emphasis}")
    return {
        "primary_decision_cue": str(cues["primary_decision_cue"]),
        "requires_question_focus": list(cues["requires_question_focus"]),
        "reject_decision_cues": list(cues["reject_decision_cues"]),
        "forbidden_question_focus": list(cues["forbidden_question_focus"]),
    }


def _rendering_variant(record: dict[str, Any]) -> dict[str, Any]:
    """Return artifact-level rendering/parameter variant metadata.

    This is deterministic because it classifies generated artifact labels,
    output form, and capability IDs with explicit rules. It separates capability
    selection from rendering-variant selection without inferring user intent.
    """

    capability_id = str(record.get("capability_id") or "")
    text = " ".join(
        str(value or "")
        for value in (
            record.get("label"),
            record.get("source"),
            record.get("output"),
        )
    ).lower()
    output_form = _variant_output_form(record, capability_id)
    layout_variant = _variant_layout(record, capability_id, text)
    encoding_variant = _variant_encoding(capability_id)
    adds_parameter_roles = _variant_added_parameter_roles(
        capability_id=capability_id,
        layout_variant=layout_variant,
        encoding_variant=encoding_variant,
    )
    selector_level = _variant_selector_level(
        capability_id=capability_id,
        layout_variant=layout_variant,
        encoding_variant=encoding_variant,
    )
    return {
        "output_form": output_form,
        "layout_variant": layout_variant,
        "encoding_variant": encoding_variant,
        "selector_level": selector_level,
        "variant_changes_capability_selection": (selector_level == "capability_choice"),
        "adds_parameter_roles": adds_parameter_roles,
        "variant_selection_cues": _variant_selection_cues(
            selector_level=selector_level,
            layout_variant=layout_variant,
            encoding_variant=encoding_variant,
        ),
    }


def _variant_output_form(record: dict[str, Any], capability_id: str) -> str:
    artifact_type = str(record.get("artifact_type") or "").lower()
    source = str(record.get("source") or "").lower()
    output = str(record.get("output") or "").lower()
    if capability_id in TABLE_CAPABILITY_IDS:
        if artifact_type == "html" or source.endswith(".html"):
            return "table_html"
        if output.endswith(".png"):
            return "table_png"
        return "table"
    if artifact_type == "html" or source.endswith(".html"):
        return "chart_html"
    if artifact_type == "png" or output.endswith(".png"):
        return "chart_png"
    return artifact_type or "unknown"


def _variant_layout(
    record: dict[str, Any],
    capability_id: str,
    text: str,
) -> str:
    if capability_id in TABLE_CAPABILITY_IDS:
        return "table"
    if capability_id in NESTED_DRILLDOWN_CAPABILITY_IDS or "drilldown" in text:
        return "nested_drilldown"
    if "small_multiples" in text:
        return "small_multiples"
    if "dimension_panels" in text or "two_dimension" in text:
        return "panelled"
    return "single"


def _variant_encoding(capability_id: str) -> str:
    if capability_id in TABLE_CAPABILITY_IDS:
        return "table"
    if capability_id.startswith("mix.like_for_like"):
        return "like_for_like"
    if capability_id.startswith("mix.cohort_"):
        return "cohort"
    return ENCODING_VARIANT_BY_CAPABILITY_ID.get(capability_id, "plain")


def _variant_added_parameter_roles(
    *,
    capability_id: str,
    layout_variant: str,
    encoding_variant: str,
) -> list[str]:
    roles: list[str] = []
    if layout_variant in {"small_multiples", "panelled"}:
        roles.append("panel_dimension")
    if encoding_variant == "overlay" or capability_id in OVERLAY_CAPABILITY_IDS:
        roles.append("related_marker_metric")
    if layout_variant == "nested_drilldown":
        roles.append("drilldown_selection")
    return roles


def _variant_selector_level(
    *,
    capability_id: str,
    layout_variant: str,
    encoding_variant: str,
) -> str:
    if capability_id in OVERLAY_CAPABILITY_IDS:
        return "capability_choice"
    if capability_id in PANEL_SPECIFIC_CAPABILITY_IDS:
        return "capability_choice"
    if capability_id in NESTED_DRILLDOWN_CAPABILITY_IDS:
        return "capability_choice"
    if layout_variant in {"small_multiples", "panelled"}:
        return "rendering_variant_choice"
    return "base_capability"


def _variant_selection_cues(
    *,
    selector_level: str,
    layout_variant: str,
    encoding_variant: str,
) -> list[str]:
    cues: list[str] = []
    if layout_variant == "table":
        cues.append("table output for exact values or evidence rows")
    elif layout_variant == "small_multiples":
        cues.append("question asks to split the same chart by a panel dimension")
    elif layout_variant == "panelled":
        cues.append("question asks for side-by-side panels for the same capability")
    elif layout_variant == "nested_drilldown":
        cues.append("question asks for selected-row drilldown or nested detail")
    if encoding_variant == "overlay":
        cues.append("question asks for a primary metric plus a related marker metric")
    if selector_level == "base_capability":
        cues.append("default single-view rendering for the selected capability")
    return cues


def _artifact_record(item: dict[str, Any]) -> dict[str, Any]:
    contract = item.get("artifact_contract")
    if not isinstance(contract, dict):
        contract = {}
    label = item.get("label")
    source_capability_id = contract.get("capability_id")
    override = (
        ARTIFACT_CAPABILITY_OVERRIDES.get(label) if isinstance(label, str) else None
    )
    capability_id = (
        override["capability_id"] if override is not None else source_capability_id
    )
    record = {
        "label": label,
        "capability_id": capability_id,
        "plugin_source": item.get("plugin_source"),
        "artifact_type": item.get("artifact_type"),
        "source": item.get("source"),
        "output": item.get("output"),
        "sidecars": item.get("sidecars") or [],
        "title_context": item.get("title_context") or {},
        "context_summary": item.get("context_summary") or {},
        "original_artifact_contract": contract,
    }
    if override is not None:
        record["source_capability_id"] = source_capability_id
        record["capability_override_reason"] = override["reason"]
    record["rendering_variant"] = _rendering_variant(record)
    return {
        **record,
    }


def _validate(manifest: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    capabilities = manifest["capabilities"]
    artifacts = manifest["artifacts"]
    capability_ids = set(capabilities)
    for capability_id, capability in capabilities.items():
        for field in (
            "visual_grammar",
            "selection_emphasis",
            "best_when",
            "avoid_when",
            "axis_roles",
            "period_semantics",
            "metric_requirements",
            "selection_contract",
            "selection_examples",
            "normalized_invocation_contract",
            "primary_decision_cue",
            "requires_question_focus",
            "reject_decision_cues",
            "forbidden_question_focus",
        ):
            if capability.get(field) in (None, "", [], {}):
                issues.append(
                    {
                        "severity": "error",
                        "code": "missing_capability_field",
                        "detail": f"{capability_id}.{field}",
                    }
                )
        for field in (
            "requires_question_focus",
            "reject_decision_cues",
            "forbidden_question_focus",
        ):
            values = capability.get(field)
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                issues.append(
                    {
                        "severity": "error",
                        "code": "invalid_structured_decision_cue",
                        "detail": f"{capability_id}.{field}",
                    }
                )
        emphasis = capability.get("selection_emphasis")
        if (
            isinstance(emphasis, str)
            and emphasis in DECISION_CUES_BY_EMPHASIS
            and capability.get("primary_decision_cue")
            != DECISION_CUES_BY_EMPHASIS[emphasis]["primary_decision_cue"]
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "decision_cue_emphasis_mismatch",
                    "detail": capability_id,
                }
            )
        contract = capability.get("selection_contract")
        metric_requirements = capability.get("metric_requirements")
        if isinstance(metric_requirements, dict):
            for field in (
                "source_metric_roles",
                "derived_metric_roles",
                "minimum_source_metric_count",
                "metric_selection_notes",
            ):
                if field not in metric_requirements:
                    issues.append(
                        {
                            "severity": "error",
                            "code": "missing_metric_requirements_field",
                            "detail": f"{capability_id}.{field}",
                        }
                    )
            source_roles = metric_requirements.get("source_metric_roles")
            if isinstance(source_roles, list):
                for index, role in enumerate(source_roles):
                    if not isinstance(role, dict):
                        issues.append(
                            {
                                "severity": "error",
                                "code": "invalid_source_metric_role",
                                "detail": f"{capability_id}.{index}",
                            }
                        )
                        continue
                    for field in ("role", "accepted_metric_classes", "aggregation"):
                        if role.get(field) in (None, "", [], {}):
                            issues.append(
                                {
                                    "severity": "error",
                                    "code": "missing_source_metric_role_field",
                                    "detail": f"{capability_id}.{index}.{field}",
                                }
                            )
        if isinstance(contract, dict):
            for field in (
                "selector_must_know",
                "dataset_requirements",
                "implementation_evidence",
                "accept_when",
                "reject_when",
                "selection_boundary",
                "selection_decision",
            ):
                if contract.get(field) in (None, "", [], {}):
                    issues.append(
                        {
                            "severity": "error",
                            "code": "missing_selection_contract_field",
                            "detail": f"{capability_id}.{field}",
                        }
                    )
            if capability.get("competing_capability_ids") and not contract.get(
                "tie_breakers"
            ):
                issues.append(
                    {
                        "severity": "error",
                        "code": "missing_competitor_tie_breakers",
                        "detail": capability_id,
                    }
                )
        if capability.get("best_when") == capability_id:
            issues.append(
                {
                    "severity": "error",
                    "code": "tautological_best_when",
                    "detail": capability_id,
                }
            )
        invocation_contract = capability.get("normalized_invocation_contract")
        if not isinstance(invocation_contract, dict):
            issues.append(
                {
                    "severity": "error",
                    "code": "missing_normalized_invocation_contract",
                    "detail": capability_id,
                }
            )
        elif invocation_contract.get("status") not in {
            "parameter_contract_ready",
            "parameter_contract_gap",
            "missing_artifact_evidence",
        }:
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_normalized_invocation_contract_status",
                    "detail": capability_id,
                }
            )
        for competitor in capability.get("competing_capability_ids") or []:
            if competitor not in capability_ids:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "unknown_competitor",
                        "detail": f"{capability_id} -> {competitor}",
                    }
                )
        examples = capability.get("selection_examples")
        if not isinstance(examples, dict):
            issues.append(
                {
                    "severity": "error",
                    "code": "missing_selection_examples",
                    "detail": capability_id,
                }
            )
            continue
        positive_questions = examples.get("positive_questions")
        negative_questions = examples.get("negative_questions")
        ambiguous_questions = examples.get("ambiguous_questions")
        if not positive_questions or not all(
            isinstance(question, str) and question.strip()
            for question in positive_questions
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_positive_selection_examples",
                    "detail": capability_id,
                }
            )
        if not negative_questions or not all(
            isinstance(example, dict)
            and isinstance(example.get("question"), str)
            and example.get("question").strip()
            and example.get("better_capability_id") in capability_ids
            and example.get("better_capability_id") != capability_id
            for example in negative_questions
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_negative_selection_examples",
                    "detail": capability_id,
                }
            )
        if not ambiguous_questions or not all(
            _valid_ambiguous_selection_example(
                example, capability_id=capability_id, capability_ids=capability_ids
            )
            for example in ambiguous_questions
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_ambiguous_selection_examples",
                    "detail": capability_id,
                }
            )
    for artifact in artifacts:
        if artifact.get("capability_id") not in capability_ids:
            issues.append(
                {
                    "severity": "error",
                    "code": "artifact_without_capability",
                    "detail": str(artifact.get("label")),
                }
            )
        issues.extend(_validate_artifact_rendering_variant(artifact))
    for gap_key, gap_values in (manifest.get("coverage_gaps") or {}).items():
        if not isinstance(gap_values, list):
            continue
        for capability_id in gap_values:
            issues.append(
                {
                    "severity": "error",
                    "code": "capability_coverage_gap",
                    "detail": f"{gap_key}: {capability_id}",
                }
            )
    for task_id, task in manifest["analysis_tasks"].items():
        capability_count = len(task.get("capability_ids") or [])
        treatment_count = len(task.get("treatments") or {})
        if capability_count > 1 and treatment_count < 2:
            issues.append(
                {
                    "severity": "error",
                    "code": "ambiguous_task_without_treatments",
                    "detail": task_id,
                }
            )
    role_registry = manifest.get("role_registry")
    if not isinstance(role_registry, dict):
        issues.append(
            {
                "severity": "error",
                "code": "missing_role_registry",
                "detail": "role_registry",
            }
        )
    else:
        counts = role_registry.get("counts") or {}
        if counts.get("chart_roles_missing_mapping"):
            issues.append(
                {
                    "severity": "error",
                    "code": "role_registry_missing_parameter_mapping",
                    "detail": str(counts.get("chart_roles_missing_mapping")),
                }
            )
    selector_audit = manifest.get("selector_audit") or {}
    for duplicate in selector_audit.get("duplicate_selector_signatures") or []:
        issues.append(
            {
                "severity": "error",
                "code": "duplicate_selector_signature",
                "detail": ", ".join(duplicate),
            }
        )
    for capability_id in selector_audit.get("missing_selection_contract") or []:
        issues.append(
            {
                "severity": "error",
                "code": "missing_selection_contract",
                "detail": capability_id,
            }
        )
    pairwise_ambiguity = selector_audit.get("pairwise_ambiguity") or {}
    for pair in pairwise_ambiguity.get("unresolved_pairs") or []:
        issues.append(
            {
                "severity": "error",
                "code": "pairwise_ambiguity_without_tie_breaker",
                "detail": ", ".join(pair.get("capability_ids") or []),
            }
        )
    trend = capabilities.get("period_comparison.trend", {})
    if not trend.get("period_semantics", {}).get("supports_period_axis"):
        issues.append(
            {
                "severity": "error",
                "code": "trend_not_time_axis",
                "detail": "period_comparison.trend must support period axis.",
            }
        )
    for capability_id in ("scatter.scatter", "scatter.bubble"):
        period = capabilities.get(capability_id, {}).get("period_semantics", {})
        if period.get("supports_period_axis"):
            issues.append(
                {
                    "severity": "error",
                    "code": "scatter_time_axis_false_positive",
                    "detail": capability_id,
                }
            )
    return issues


def _validate_artifact_rendering_variant(
    artifact: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    label = str(artifact.get("label"))
    capability_id = str(artifact.get("capability_id") or "")
    variant = artifact.get("rendering_variant")
    if not isinstance(variant, dict):
        return [
            {
                "severity": "error",
                "code": "missing_rendering_variant",
                "detail": label,
            }
        ]

    for field in (
        "output_form",
        "layout_variant",
        "encoding_variant",
        "selector_level",
    ):
        if not isinstance(variant.get(field), str) or not variant.get(field):
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_rendering_variant_field",
                    "detail": f"{label}.{field}",
                }
            )
    if not isinstance(variant.get("variant_changes_capability_selection"), bool):
        issues.append(
            {
                "severity": "error",
                "code": "invalid_rendering_variant_field",
                "detail": f"{label}.variant_changes_capability_selection",
            }
        )
    for field in ("adds_parameter_roles", "variant_selection_cues"):
        values = variant.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "invalid_rendering_variant_field",
                    "detail": f"{label}.{field}",
                }
            )

    text = " ".join(
        str(value or "")
        for value in (
            artifact.get("label"),
            artifact.get("source"),
            artifact.get("output"),
        )
    ).lower()
    roles = set(variant.get("adds_parameter_roles") or [])
    layout_variant = variant.get("layout_variant")
    selector_level = variant.get("selector_level")
    encoding_variant = variant.get("encoding_variant")
    changes_capability = variant.get("variant_changes_capability_selection")

    if capability_id in TABLE_CAPABILITY_IDS:
        if not str(variant.get("output_form", "")).startswith("table"):
            issues.append(
                {
                    "severity": "error",
                    "code": "table_artifact_output_form_mismatch",
                    "detail": label,
                }
            )
        if layout_variant != "table" or encoding_variant != "table":
            issues.append(
                {
                    "severity": "error",
                    "code": "table_artifact_variant_mismatch",
                    "detail": label,
                }
            )
    if "small_multiples" in text:
        if layout_variant != "small_multiples":
            issues.append(
                {
                    "severity": "error",
                    "code": "small_multiples_layout_mismatch",
                    "detail": label,
                }
            )
        if "panel_dimension" not in roles:
            issues.append(
                {
                    "severity": "error",
                    "code": "small_multiples_missing_panel_role",
                    "detail": label,
                }
            )
        if (
            capability_id not in PANEL_SPECIFIC_CAPABILITY_IDS
            and capability_id not in OVERLAY_CAPABILITY_IDS
            and selector_level != "rendering_variant_choice"
        ):
            issues.append(
                {
                    "severity": "error",
                    "code": "ordinary_small_multiples_not_rendering_variant",
                    "detail": label,
                }
            )
    if capability_id in PANEL_SPECIFIC_CAPABILITY_IDS:
        if selector_level != "capability_choice" or changes_capability is not True:
            issues.append(
                {
                    "severity": "error",
                    "code": "panel_specific_capability_variant_mismatch",
                    "detail": label,
                }
            )
    if capability_id in OVERLAY_CAPABILITY_IDS:
        if encoding_variant != "overlay":
            issues.append(
                {
                    "severity": "error",
                    "code": "overlay_encoding_mismatch",
                    "detail": label,
                }
            )
        if selector_level != "capability_choice" or changes_capability is not True:
            issues.append(
                {
                    "severity": "error",
                    "code": "overlay_selector_level_mismatch",
                    "detail": label,
                }
            )
        if "related_marker_metric" not in roles:
            issues.append(
                {
                    "severity": "error",
                    "code": "overlay_missing_related_marker_role",
                    "detail": label,
                }
            )
    if capability_id.startswith("mix.like_for_like") and selector_level == (
        "rendering_variant_choice"
    ):
        issues.append(
            {
                "severity": "error",
                "code": "like_for_like_misclassified_as_rendering_variant",
                "detail": label,
            }
        )
    return issues


def _valid_ambiguous_selection_example(
    example: Any, *, capability_id: str, capability_ids: set[str]
) -> bool:
    if not isinstance(example, dict):
        return False
    question = example.get("question")
    candidates = example.get("candidate_capability_ids")
    if not isinstance(question, str) or not question.strip():
        return False
    if not isinstance(candidates, list) or len(candidates) < 2:
        return False
    if capability_id not in candidates:
        return False
    return all(
        isinstance(candidate, str) and candidate in capability_ids
        for candidate in candidates
    )


def _run_semantic_probes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    capabilities = manifest["capabilities"]
    tasks = manifest["analysis_tasks"]
    results: list[dict[str, Any]] = []
    for probe in SEMANTIC_PROBES:
        task = tasks.get(probe["task_id"], {})
        candidate_ids: list[str] = []
        treatments = task.get("treatments")
        if isinstance(treatments, dict):
            for emphasis in probe["required_emphases"]:
                treatment = treatments.get(emphasis)
                if not isinstance(treatment, dict):
                    continue
                for capability_id in treatment.get("capability_ids") or []:
                    if capability_id not in candidate_ids:
                        candidate_ids.append(capability_id)
        if not candidate_ids:
            candidate_ids = list(task.get("capability_ids") or [])
        candidate_set = set(candidate_ids)
        required = set(probe["required_capability_ids"])
        forbidden = set(probe["forbidden_capability_ids"])
        emphases = {
            capabilities[capability_id]["selection_emphasis"]
            for capability_id in candidate_ids
            if capability_id in capabilities
        }
        required_emphases = set(probe["required_emphases"])
        missing_required = sorted(required - candidate_set)
        present_forbidden = sorted(forbidden & candidate_set)
        missing_emphases = sorted(required_emphases - emphases)
        status = (
            "pass"
            if not missing_required and not present_forbidden and not missing_emphases
            else "fail"
        )
        results.append(
            {
                "probe_id": probe["probe_id"],
                "question": probe["question"],
                "task_id": probe["task_id"],
                "status": status,
                "required_emphases": list(probe["required_emphases"]),
                "candidate_capability_ids": candidate_ids,
                "missing_required_capability_ids": missing_required,
                "present_forbidden_capability_ids": present_forbidden,
                "missing_required_emphases": missing_emphases,
            }
        )
    return results


def _pairwise_ambiguity_audit(
    capabilities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Find mechanically similar chart pairs and require explicit tie-breakers.

    This is deterministic because it compares normalized manifest fields only:
    task buckets, period role, source metric class requirements, and dimension
    role resolution types. It does not decide which chart is semantically best.
    """

    groups: defaultdict[str, list[str]] = defaultdict(list)
    signatures_by_key: dict[str, dict[str, Any]] = {}
    for capability_id, capability in capabilities.items():
        contract = capability.get("selection_contract")
        if not isinstance(contract, dict):
            continue
        signature = _ambiguity_signature(capability)
        signature_key = json.dumps(signature, sort_keys=True)
        groups[signature_key].append(capability_id)
        signatures_by_key[signature_key] = signature

    signature_groups = []
    high_overlap_pairs = []
    unresolved_pairs = []
    for signature_key, capability_ids in sorted(groups.items()):
        if len(capability_ids) < 2:
            continue
        sorted_ids = sorted(capability_ids)
        signature = signatures_by_key[signature_key]
        signature_groups.append(
            {
                "signature": signature,
                "capability_ids": sorted_ids,
                "pair_count": len(sorted_ids) * (len(sorted_ids) - 1) // 2,
            }
        )
        for left_id, right_id in combinations(sorted_ids, 2):
            left = capabilities[left_id]
            right = capabilities[right_id]
            relationship = _pair_relationship_evidence(
                left_id=left_id,
                right_id=right_id,
                left=left,
                right=right,
            )
            issues = []
            if left["selection_emphasis"] == right["selection_emphasis"]:
                issues.append("same_selection_emphasis")
            if _decision_cue_signature(left) == _decision_cue_signature(right):
                issues.append("same_structured_decision_cues")
            if not relationship["explicit_competitor_link"]:
                issues.append("missing_explicit_pairwise_tie_breaker")
            record = {
                "capability_ids": [left_id, right_id],
                "status": "resolved" if not issues else "unresolved",
                "issues": issues,
                "signature": signature,
                "selection_emphases": {
                    left_id: left["selection_emphasis"],
                    right_id: right["selection_emphasis"],
                },
                "structured_decision_cues": {
                    left_id: _decision_cue_summary(left),
                    right_id: _decision_cue_summary(right),
                },
                "relationship_evidence": relationship,
            }
            high_overlap_pairs.append(record)
            if issues:
                unresolved_pairs.append(record)

    return {
        "signature_groups": signature_groups,
        "high_overlap_pair_count": len(high_overlap_pairs),
        "resolved_pair_count": len(high_overlap_pairs) - len(unresolved_pairs),
        "unresolved_pair_count": len(unresolved_pairs),
        "unresolved_pairs": unresolved_pairs,
        "high_overlap_pairs": high_overlap_pairs,
        "result": "pass" if not unresolved_pairs else "fail",
    }


def _decision_cue_signature(capability: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    return (
        tuple(capability.get("requires_question_focus") or []),
        tuple(capability.get("forbidden_question_focus") or []),
    )


def _decision_cue_summary(capability: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_decision_cue": capability.get("primary_decision_cue"),
        "requires_question_focus": capability.get("requires_question_focus") or [],
        "forbidden_question_focus": capability.get("forbidden_question_focus") or [],
    }


def _ambiguity_signature(capability: dict[str, Any]) -> dict[str, Any]:
    requirements = capability["selection_contract"]["dataset_requirements"]
    metrics = requirements["metrics"]
    source_metric_class_groups = []
    for role in metrics.get("source_metric_roles") or []:
        if role.get("required", True):
            source_metric_class_groups.append(
                sorted(role.get("accepted_metric_classes") or [])
            )
    dimensions = requirements["dimensions"]
    role_requirements = dimensions.get("role_requirements") or {}
    dimension_resolution_types = []
    for role in dimensions.get("required_roles") or []:
        dimension_resolution_types.append(
            (role_requirements.get(role) or {}).get(
                "resolution_type", "direct_dimension"
            )
        )
    return {
        "analysis_task_ids": sorted(capability["analysis_task_ids"]),
        "period_role": requirements["period"]["role"],
        "source_metric_count": metrics["minimum_source_metric_count"],
        "source_metric_class_groups": sorted(source_metric_class_groups),
        "dimension_count": dimensions["minimum_count"],
        "dimension_resolution_types": sorted(dimension_resolution_types),
    }


def _pair_relationship_evidence(
    *,
    left_id: str,
    right_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    left_competitors = set(left.get("competing_capability_ids") or [])
    right_competitors = set(right.get("competing_capability_ids") or [])
    return {
        "explicit_competitor_link": (
            right_id in left_competitors or left_id in right_competitors
        ),
        "negative_example_link": (
            _has_negative_example_for(left, better_capability_id=right_id)
            or _has_negative_example_for(right, better_capability_id=left_id)
        ),
        "ambiguous_example_link": (
            _has_ambiguous_example_pair(left, left_id=left_id, right_id=right_id)
            or _has_ambiguous_example_pair(right, left_id=left_id, right_id=right_id)
        ),
    }


def _has_negative_example_for(
    capability: dict[str, Any], *, better_capability_id: str
) -> bool:
    examples = capability.get("selection_examples") or {}
    return any(
        example.get("better_capability_id") == better_capability_id
        for example in examples.get("negative_questions") or []
        if isinstance(example, dict)
    )


def _has_ambiguous_example_pair(
    capability: dict[str, Any], *, left_id: str, right_id: str
) -> bool:
    examples = capability.get("selection_examples") or {}
    for example in examples.get("ambiguous_questions") or []:
        if not isinstance(example, dict):
            continue
        candidates = set(example.get("candidate_capability_ids") or [])
        if {left_id, right_id}.issubset(candidates):
            return True
    return False


def _selector_audit(manifest: dict[str, Any]) -> dict[str, Any]:
    capabilities = manifest["capabilities"]
    signatures: defaultdict[str, list[str]] = defaultdict(list)
    generated_only: list[str] = []
    missing_contract: list[str] = []
    for capability_id, capability in capabilities.items():
        contract = capability.get("selection_contract")
        if not isinstance(contract, dict):
            missing_contract.append(capability_id)
            continue
        evidence = contract.get("implementation_evidence") or {}
        if evidence.get("evidence_status") == "generated_manifest_only":
            generated_only.append(capability_id)
        requirements = contract["dataset_requirements"]
        signature = json.dumps(
            {
                "analysis_task_ids": capability["analysis_task_ids"],
                "selection_emphasis": capability["selection_emphasis"],
                "visual_grammar": capability["visual_grammar"],
                "period": requirements["period"],
                "metrics": requirements["metrics"],
                "dimensions": requirements["dimensions"],
                "visual_role_bindings": requirements["visual_role_bindings"],
            },
            sort_keys=True,
        )
        signatures[signature].append(capability_id)

    duplicate_selector_signatures = [
        capability_ids
        for capability_ids in signatures.values()
        if len(capability_ids) > 1
    ]
    pairwise_ambiguity = _pairwise_ambiguity_audit(capabilities)
    return {
        "capabilities_checked": len(capabilities),
        "missing_selection_contract": sorted(missing_contract),
        "duplicate_selector_signatures": duplicate_selector_signatures,
        "pairwise_ambiguity": pairwise_ambiguity,
        "generated_manifest_only_capabilities": sorted(generated_only),
        "result": (
            "pass"
            if not missing_contract
            and not duplicate_selector_signatures
            and pairwise_ambiguity["result"] == "pass"
            else "fail"
        ),
    }


def build_chart_selection_manifest() -> dict[str, Any]:
    source = _load_source_manifest()
    raw_items = source.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Source manifest must contain an items list.")

    artifacts = [_artifact_record(item) for item in raw_items if isinstance(item, dict)]
    artifacts_by_capability: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        capability_id = artifact.get("capability_id")
        if isinstance(capability_id, str) and capability_id:
            artifacts_by_capability[capability_id].append(artifact)

    missing_semantics = sorted(
        capability_id
        for capability_id in artifacts_by_capability
        if capability_id not in CAPABILITY_SEMANTICS
    )
    if missing_semantics:
        raise ValueError(
            "Missing capability semantics for: " + ", ".join(missing_semantics)
        )

    generated_manifest_capability_ids = _generated_manifest_capability_ids()
    all_capability_ids = (
        set(artifacts_by_capability) | generated_manifest_capability_ids
    )
    missing_semantics = sorted(
        capability_id
        for capability_id in all_capability_ids
        if capability_id not in CAPABILITY_SEMANTICS
    )
    if missing_semantics:
        raise ValueError(
            "Missing capability semantics for: " + ", ".join(missing_semantics)
        )

    capabilities: dict[str, Any] = {}
    gallery_capability_ids = set(artifacts_by_capability)
    for capability_id in sorted(all_capability_ids):
        semantics = dict(CAPABILITY_SEMANTICS[capability_id])
        semantics["capability_id"] = capability_id
        semantics["present_in_gallery_manifest"] = (
            capability_id in gallery_capability_ids
        )
        semantics["present_in_generated_manifest"] = (
            capability_id in generated_manifest_capability_ids
        )
        example_artifacts = artifacts_by_capability.get(capability_id, [])
        semantics["example_artifact_labels"] = [
            artifact["label"] for artifact in example_artifacts
        ]
        semantics["example_count"] = len(semantics["example_artifact_labels"])
        capabilities[capability_id] = semantics

    _normalize_competitor_links(capabilities)

    for capability_id, capability in capabilities.items():
        capability.update(_decision_cues(capability_id, capability))

    for capability_id, capability in capabilities.items():
        capability["selection_contract"] = _selection_contract(
            capability_id,
            capability,
            capabilities,
        )

    for capability_id, capability in capabilities.items():
        capability["normalized_invocation_contract"] = (
            build_normalized_invocation_contract(
                capability_id,
                capability,
                artifacts_by_capability.get(capability_id, []),
            )
        )

    tasks_by_id: dict[str, dict[str, Any]] = {}
    for capability_id, capability in capabilities.items():
        for task_id in capability["analysis_task_ids"]:
            if task_id in tasks_by_id:
                task = tasks_by_id[task_id]
            else:
                task = dict(
                    ANALYSIS_TASKS.get(
                        task_id,
                        {
                            "label": task_id.replace("_", " ").title(),
                            "description": "Derived from capability semantics.",
                        },
                    )
                )
                task["analysis_task_id"] = task_id
                task["capability_ids"] = []
                task["treatments"] = {}
            task["capability_ids"].append(capability_id)
            emphasis = capability["selection_emphasis"]
            treatments = task["treatments"]
            treatment = treatments.setdefault(
                emphasis,
                {
                    "selection_emphasis": emphasis,
                    "capability_ids": [],
                    "best_when": capability["best_when"],
                    "avoid_when": capability["avoid_when"],
                },
            )
            treatment["capability_ids"].append(capability_id)
            tasks_by_id[task_id] = task

    for capability_id, capability in capabilities.items():
        capability["selection_examples"] = _selection_examples(
            capability_id,
            capability,
            capabilities,
            tasks_by_id,
        )

    manifest = {
        "schema_version": "0.1",
        "source_manifest": str(SOURCE_MANIFEST.relative_to(REPO_ROOT)),
        "purpose": (
            "Selection-oriented rebuild of the PNG gallery manifest. Artifacts "
            "remain examples; capability records carry chart-selection semantics."
        ),
        "counts": {
            "source_items": len(raw_items),
            "artifacts": len(artifacts),
            "capabilities": len(capabilities),
            "analysis_tasks": len(tasks_by_id),
            "generated_manifest_capabilities": len(generated_manifest_capability_ids),
            "generated_manifest_capabilities_without_gallery_examples": len(
                generated_manifest_capability_ids - gallery_capability_ids
            ),
        },
        "coverage_gaps": {
            "generated_manifest_capabilities_without_gallery_examples": sorted(
                generated_manifest_capability_ids - gallery_capability_ids
            ),
            "gallery_capabilities_without_generated_manifest_records": sorted(
                gallery_capability_ids - generated_manifest_capability_ids
            ),
        },
        "analysis_tasks": dict(sorted(tasks_by_id.items())),
        "capabilities": capabilities,
        "artifacts": artifacts,
        "role_registry": build_role_registry(capabilities, artifacts),
        "review_iterations": ITERATIONS,
        "semantic_probes": [],
        "selector_audit": {},
    }
    manifest["semantic_probes"] = _run_semantic_probes(manifest)
    manifest["selector_audit"] = _selector_audit(manifest)
    manifest["validation_issues"] = _validate(manifest)
    return manifest


def main() -> int:
    manifest = build_chart_selection_manifest()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    DEFAULT_ASSESSMENT.write_text(_assessment_markdown(manifest), encoding="utf-8")
    print(DEFAULT_OUTPUT)
    print(DEFAULT_ASSESSMENT)
    print(json.dumps(manifest["counts"], sort_keys=True))
    print(f"validation_issues={len(manifest['validation_issues'])}")
    return 1 if manifest["validation_issues"] else 0


def _assessment_markdown(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    lines = [
        "# Chart Selection Manifest Rebuild",
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Coverage Gaps", ""])
    for key, values in manifest["coverage_gaps"].items():
        lines.append(f"- `{key}`: `{len(values)}`")
        for value in values:
            lines.append(f"  - `{value}`")
    selector_audit = manifest.get("selector_audit") or {}
    lines.extend(["", "## Selector Audit", ""])
    lines.append(f"- Result: `{selector_audit.get('result', 'unknown')}`")
    lines.append(
        "- Capabilities checked: " f"`{selector_audit.get('capabilities_checked', 0)}`"
    )
    duplicates = selector_audit.get("duplicate_selector_signatures") or []
    lines.append(f"- Duplicate selector signatures: `{len(duplicates)}`")
    for duplicate in duplicates:
        lines.append("  - " + ", ".join(f"`{item}`" for item in duplicate))
    pairwise = selector_audit.get("pairwise_ambiguity") or {}
    lines.append(
        "- Pairwise high-overlap groups: "
        f"`{len(pairwise.get('signature_groups') or [])}`"
    )
    lines.append(
        "- Pairwise high-overlap pairs: "
        f"`{pairwise.get('high_overlap_pair_count', 0)}`"
    )
    lines.append(
        "- Pairwise unresolved pairs: " f"`{pairwise.get('unresolved_pair_count', 0)}`"
    )
    for pair in pairwise.get("unresolved_pairs") or []:
        lines.append(
            "  - "
            + ", ".join(f"`{item}`" for item in pair.get("capability_ids") or [])
            + ": "
            + ", ".join(f"`{issue}`" for issue in pair.get("issues") or [])
        )
    generated_only = selector_audit.get("generated_manifest_only_capabilities") or []
    lines.append(f"- Generated-manifest-only capabilities: `{len(generated_only)}`")
    for capability_id in generated_only:
        lines.append(f"  - `{capability_id}`")
    lines.extend(["", "## Selection Examples", ""])
    capabilities_with_examples = [
        capability_id
        for capability_id, capability in manifest["capabilities"].items()
        if capability.get("selection_examples")
    ]
    lines.append(f"- Capabilities with examples: `{len(capabilities_with_examples)}`")
    positive_count = sum(
        len(capability["selection_examples"].get("positive_questions") or [])
        for capability in manifest["capabilities"].values()
        if capability.get("selection_examples")
    )
    negative_count = sum(
        len(capability["selection_examples"].get("negative_questions") or [])
        for capability in manifest["capabilities"].values()
        if capability.get("selection_examples")
    )
    ambiguous_count = sum(
        len(capability["selection_examples"].get("ambiguous_questions") or [])
        for capability in manifest["capabilities"].values()
        if capability.get("selection_examples")
    )
    lines.append(f"- Positive questions: `{positive_count}`")
    lines.append(f"- Negative questions: `{negative_count}`")
    lines.append(f"- Ambiguous questions: `{ambiguous_count}`")
    lines.extend(["", "## Structured Decision Cues", ""])
    cue_complete = [
        capability_id
        for capability_id, capability in manifest["capabilities"].items()
        if capability.get("primary_decision_cue")
        and capability.get("requires_question_focus")
        and capability.get("reject_decision_cues")
        and capability.get("forbidden_question_focus")
    ]
    cue_collision_count = sum(
        1
        for pair in pairwise.get("high_overlap_pairs") or []
        if "same_structured_decision_cues" in (pair.get("issues") or [])
    )
    lines.append(f"- Capabilities with complete cue fields: `{len(cue_complete)}`")
    lines.append(f"- High-overlap cue collisions: `{cue_collision_count}`")
    lines.extend(["", "## Rendering Variants", ""])
    artifacts_with_variant = [
        artifact
        for artifact in manifest["artifacts"]
        if isinstance(artifact.get("rendering_variant"), dict)
    ]
    selector_level_counts: defaultdict[str, int] = defaultdict(int)
    layout_counts: defaultdict[str, int] = defaultdict(int)
    for artifact in artifacts_with_variant:
        variant = artifact["rendering_variant"]
        selector_level_counts[str(variant.get("selector_level"))] += 1
        layout_counts[str(variant.get("layout_variant"))] += 1
    lines.append(
        f"- Artifacts with rendering variant metadata: `{len(artifacts_with_variant)}`"
    )
    lines.append(
        "- Selector levels: "
        + ", ".join(
            f"`{key}`=`{value}`" for key, value in sorted(selector_level_counts.items())
        )
    )
    lines.append(
        "- Layout variants: "
        + ", ".join(
            f"`{key}`=`{value}`" for key, value in sorted(layout_counts.items())
        )
    )
    role_registry = manifest.get("role_registry") or {}
    role_counts = role_registry.get("counts") or {}
    lines.extend(["", "## Role Registry And Invocation Contracts", ""])
    for key, value in role_counts.items():
        lines.append(f"- `{key}`: `{value}`")
    invocation_counts: defaultdict[str, int] = defaultdict(int)
    for capability in manifest["capabilities"].values():
        contract = capability.get("normalized_invocation_contract") or {}
        invocation_counts[str(contract.get("status", "missing"))] += 1
    lines.append(
        "- Invocation contract statuses: "
        + ", ".join(
            f"`{key}`=`{value}`" for key, value in sorted(invocation_counts.items())
        )
    )
    lines.extend(["", "## Period Movement Treatments", ""])
    period_task = manifest["analysis_tasks"].get("time_and_period_movement", {})
    for capability_id in period_task.get("capability_ids", []):
        capability = manifest["capabilities"][capability_id]
        lines.append(
            "- "
            f"`{capability_id}`: `{capability['selection_emphasis']}` "
            f"({capability['visual_grammar']})"
        )
        lines.append(f"  - Best when: {capability['best_when']}")
        lines.append(f"  - Avoid when: {capability['avoid_when']}")
    lines.extend(["", "## Validation", ""])
    issues = manifest.get("validation_issues") or []
    if not issues:
        lines.append("- No structural validation issues.")
    else:
        for issue in issues:
            lines.append(
                f"- `{issue['severity']}` `{issue['code']}`: {issue['detail']}"
            )
    lines.extend(["", "## Semantic Probes", ""])
    probes = manifest.get("semantic_probes") or []
    failed = [probe for probe in probes if probe.get("status") != "pass"]
    lines.append(f"- Probes: `{len(probes)}`")
    lines.append(f"- Failed: `{len(failed)}`")
    for probe in probes:
        marker = "PASS" if probe.get("status") == "pass" else "FAIL"
        lines.append(
            f"- `{marker}` `{probe['probe_id']}` -> `{probe['task_id']}`: "
            f"{probe['question']}"
        )
        if probe.get("status") != "pass":
            if probe.get("missing_required_capability_ids"):
                lines.append(
                    "  - Missing required capabilities: "
                    + ", ".join(
                        f"`{item}`" for item in probe["missing_required_capability_ids"]
                    )
                )
            if probe.get("present_forbidden_capability_ids"):
                lines.append(
                    "  - Forbidden capabilities present: "
                    + ", ".join(
                        f"`{item}`"
                        for item in probe["present_forbidden_capability_ids"]
                    )
                )
            if probe.get("missing_required_emphases"):
                lines.append(
                    "  - Missing required emphases: "
                    + ", ".join(
                        f"`{item}`" for item in probe["missing_required_emphases"]
                    )
                )
    lines.extend(["", "## Ten Review Iterations", ""])
    for item in manifest["review_iterations"]:
        lines.append(
            f"{item['iteration']}. Looked for: {item['looked_for']} "
            f"Correction: {item['correction']}"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

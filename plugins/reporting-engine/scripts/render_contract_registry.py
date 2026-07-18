"""Canonical capability-to-render contracts embedded in the chart manifest."""

from __future__ import annotations

from typing import Any

__all__ = ["build_render_contract"]


CHART_OPTIONS: dict[str, list[str]] = {
    "distribution.boxplot": ["boxplot"],
    "distribution.ecdf": ["ecdf"],
    "distribution.histogram": ["histogram"],
    "distribution.kernel_density": ["kernel_density"],
    "distribution.stripplot": ["stripplot"],
    "mix.area": ["area_absolute", "area_share"],
    "mix.bar": ["bar"],
    "mix.barmekko": ["barmekko"],
    "mix.cohort_lost_stacked_column": ["cohort_lost_stacked_column"],
    "mix.cohort_since_stacked_column": ["cohort_since_stacked_column"],
    "mix.column": ["column_total"],
    "mix.column_overlay": ["column_total_with_overlay"],
    "mix.like_for_like_column": ["like_for_like_column_total"],
    "mix.like_for_like_stacked_column": ["like_for_like_stacked_column"],
    "mix.marimekko": ["marimekko"],
    "mix.multitier_bar": ["multitier_bar"],
    "mix.pareto": ["pareto"],
    "mix.stacked_bar": ["stacked_bar"],
    "mix.stacked_bar_overlay": ["related_metrics_bar"],
    "mix.stacked_column": ["stacked_column"],
    "mix.stacked_pareto": ["stacked_pareto"],
    "mix.timeline": ["line"],
    "period_comparison.by_period": ["year_over_year_by_period"],
    "period_comparison.comparison_table": ["comparison_table"],
    "period_comparison.dot": ["year_over_year_dot"],
    "period_comparison.horizontal_waterfall": ["year_over_year_waterfall"],
    "period_comparison.multitier_column": ["year_over_year_column"],
    "period_comparison.slope": ["year_over_year_slope"],
    "period_comparison.time_series_table": ["time_series_table"],
    "period_comparison.trend": ["year_over_year_line"],
    "scatter.bubble": ["bubble"],
    "scatter.scatter": ["scatter"],
    "set_overlap.upset": ["upset"],
    "set_overlap.upset_small_multiples": ["upset_small_multiples"],
    "set_overlap.venn": ["venn"],
}

EXPECTED_ARTIFACT_STEMS: dict[str, list[str]] = {
    "attributes.attribute_bridge_table": ["attribute_bridge_table"],
    "attributes.attribute_bundle_comparison_table": [
        "attribute_bundle_comparison_table"
    ],
    "attributes.product_signal_evidence_table": ["product_signal_evidence_table"],
    "attributes.rank_weighted_visibility_table": ["rank_weighted_visibility_table"],
    "funnel.stage_table": ["funnel_stage_table"],
    "mix.stacked_pareto": [
        "stacked_pareto_abc",
        "stacked_pareto_by_dimension",
    ],
    "statement.pnl_table": ["pnl_statement_table"],
    "variance.exploded_variance_bridge": ["exploded_variance_bridge"],
    "variance.price_volume_mix": ["pvm_decomposition_ladder"],
    "variance.root_cause_component_bridge": ["root_cause_component_bridge"],
    "variance.root_cause_total_bridge": ["root_cause_total_bridge"],
    "variance.scenario_bridge": ["waterfall"],
    "variance.total_by_dimension_bridge": ["total_by_dimension_bridge"],
}

EXPECTED_ARTIFACT_STEM_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "variance.root_cause_exploded_bridge": [
        {
            "template": "root_cause_total_bridge_drilldown_row_{value}",
            "role": "drilldown_selection",
            "binding_key": "root_cause_bridge_drilldown_rows",
            "for_each": True,
        }
    ]
}

EXPECTED_VARIANT_ARTIFACT_STEMS: dict[str, list[str]] = {
    "distribution.boxplot": ["boxplot_small_multiples"],
    "distribution.ecdf": ["ecdf_small_multiples"],
    "distribution.histogram": ["histogram_small_multiples"],
    "distribution.kernel_density": ["kernel_density_small_multiples"],
    "distribution.stripplot": ["stripplot_small_multiples"],
}

ALLOWED_SUPPORT_ARTIFACT_STEMS: dict[str, list[str]] = {
    "scatter.bubble": ["scatter_bubble_review"],
    "scatter.scatter": ["scatter_bubble_review"],
    "variance.root_cause_component_bridge": ["root_cause_total_bridge"],
    "variance.root_cause_exploded_bridge": ["root_cause_total_bridge"],
}

VARIANT_CHART_OPTIONS: dict[str, list[str]] = {
    "mix.bar": ["bar_small_multiples"],
    "mix.barmekko": ["barmekko_small_multiples"],
    "mix.marimekko": ["marimekko_small_multiples"],
    "mix.multitier_bar": [
        "multitier_bar_dimension_panels",
        "multitier_bar_two_dimension",
    ],
    "mix.stacked_bar": ["stacked_bar_small_multiples"],
    "mix.stacked_bar_overlay": ["related_metrics_bar_small_multiples"],
    "mix.stacked_column": ["stacked_column_small_multiples"],
    "mix.timeline": ["line_small_multiples"],
    "period_comparison.by_period": ["year_over_year_by_period_small_multiples"],
    "period_comparison.dot": ["year_over_year_dot_small_multiples"],
    "period_comparison.horizontal_waterfall": [
        "year_over_year_waterfall_small_multiples"
    ],
    "period_comparison.multitier_column": ["year_over_year_column_small_multiples"],
    "period_comparison.slope": ["year_over_year_slope_small_multiples"],
    "period_comparison.trend": ["year_over_year_small_multiples"],
    "scatter.bubble": ["bubble_small_multiples"],
    "scatter.scatter": ["scatter_small_multiples"],
}

OPTION_OVERRIDES: dict[str, dict[str, Any]] = {
    "variance.exploded_variance_bridge": {
        "exploded_variance_bridge": True,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.price_volume_mix": {
        "pvm_decomposition_ladder": True,
        "exploded_variance_bridge": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_component_bridge": {
        "exploded_variance_bridge": False,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": True,
        "root_cause_bridge_alternative_sweep": False,
        "root_cause_component_bridge": True,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_exploded_bridge": {
        "exploded_variance_bridge": False,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": True,
        "root_cause_bridge_alternative_sweep": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.root_cause_total_bridge": {
        "exploded_variance_bridge": False,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": True,
        "root_cause_bridge_alternative_sweep": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
    "variance.scenario_bridge": {
        "exploded_variance_bridge": False,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": False,
        "waterfall_chart": True,
        "waterfall_small_multiples": False,
    },
    "variance.total_by_dimension_bridge": {
        "exploded_variance_bridge": False,
        "pvm_decomposition_ladder": False,
        "root_cause_bridge": False,
        "root_cause_component_bridge": False,
        "total_by_dimension_bridge": True,
        "waterfall_chart": False,
        "waterfall_small_multiples": False,
    },
}


def build_render_contract(capability_id: str) -> dict[str, Any]:
    """Return the exact renderer-managed contract for one capability."""

    chart_options = list(CHART_OPTIONS.get(capability_id, []))
    expected_stems = list(EXPECTED_ARTIFACT_STEMS.get(capability_id, chart_options))
    expected_templates = [
        dict(template)
        for template in EXPECTED_ARTIFACT_STEM_TEMPLATES.get(capability_id, [])
    ]
    return {
        "schema_version": "0.1",
        "chart_options": chart_options,
        "variant_chart_options": list(VARIANT_CHART_OPTIONS.get(capability_id, [])),
        "fixed_option_overrides": dict(OPTION_OVERRIDES.get(capability_id, {})),
        "expected_artifact_stems": expected_stems,
        "expected_artifact_stem_templates": expected_templates,
        "expected_variant_artifact_stems": list(
            EXPECTED_VARIANT_ARTIFACT_STEMS.get(
                capability_id,
                VARIANT_CHART_OPTIONS.get(capability_id, []),
            )
        ),
        "allowed_support_artifact_stems": list(
            ALLOWED_SUPPORT_ARTIFACT_STEMS.get(capability_id, [])
        ),
        "renderer_managed_parameters": [
            {"target": "source_file", "source": "request.input_file"},
            {
                "target": "options.charts",
                "source": "chart_options",
                "condition": "chart_options is non-empty",
            },
            {
                "target": "options.small_multiples",
                "source": "request.include_variants",
                "condition": "chart_options is non-empty",
            },
            {
                "target": "options.*",
                "source": "fixed_option_overrides",
                "condition": "override is registered",
            },
        ],
        "caller_parameters": {
            "required": ["capability_id", "input_file", "output_dir", "role_bindings"],
            "optional": [
                "recipe_path",
                "language",
                "currency",
                "artifact_mode",
                "include_variants",
                "options",
            ],
        },
        "exact_artifact_proof_required": bool(expected_stems or expected_templates),
        "boundary": (
            "Mechanical rendering contract. Chart options and fixed overrides are "
            "selected by capability; role bindings remain dataset-specific."
        ),
    }

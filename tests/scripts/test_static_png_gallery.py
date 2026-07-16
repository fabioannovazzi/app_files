from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GALLERY_DIR = ROOT / "static" / "shared" / "png-gallery"

EXPECTED_PUBLISHED_GALLERY_CARDS = {
    "variance / exploded_variance_bridge": (
        "variance__exploded_variance_bridge.png",
        "variance.exploded_variance_bridge",
    ),
    "variance / pvm_decomposition_ladder": (
        "variance__pvm_decomposition_ladder.png",
        "variance.price_volume_mix",
    ),
    "variance / root_cause_component_bridge": (
        "variance__root_cause_component_bridge.png",
        "variance.root_cause_component_bridge",
    ),
    "variance / root_cause_total_bridge": (
        "variance__root_cause_total_bridge.png",
        "variance.root_cause_total_bridge",
    ),
    "variance / total_by_dimension_bridge": (
        "variance__total_by_dimension_bridge.png",
        "variance.total_by_dimension_bridge",
    ),
    "variance / waterfall": ("variance__waterfall.png", "variance.scenario_bridge"),
    "variance / waterfall_small_multiples": (
        "variance__waterfall_small_multiples.png",
        "variance.scenario_bridge",
    ),
    "period / comparison_table": (
        "period__comparison_table.png",
        "period_comparison.comparison_table",
    ),
    "period / time_series_table": (
        "period__time_series_table.png",
        "period_comparison.time_series_table",
    ),
    "period / year_over_year_by_recency_window": (
        "period__year_over_year_by_period.png",
        "period_comparison.by_period",
    ),
    "period / year_over_year_by_recency_window_small_multiples": (
        "period__year_over_year_by_period_small_multiples.png",
        "period_comparison.by_period",
    ),
    "period / year_over_year_column": (
        "period__year_over_year_column.png",
        "period_comparison.multitier_column",
    ),
    "period / year_over_year_column_small_multiples": (
        "period__year_over_year_column_small_multiples.png",
        "period_comparison.multitier_column",
    ),
    "period / year_over_year_line": (
        "period__year_over_year_line.png",
        "period_comparison.trend",
    ),
    "period / year_over_year_small_multiples": (
        "period__year_over_year_small_multiples.png",
        "period_comparison.by_period",
    ),
    "period / year_over_year_waterfall": (
        "period__year_over_year_waterfall.png",
        "period_comparison.horizontal_waterfall",
    ),
    "period / year_over_year_waterfall_small_multiples": (
        "period__year_over_year_waterfall_small_multiples.png",
        "period_comparison.horizontal_waterfall",
    ),
    "period / year_over_year_dot": (
        "period__year_over_year_dot.png",
        "period_comparison.dot",
    ),
    "period / year_over_year_dot_small_multiples": (
        "period__year_over_year_dot_small_multiples.png",
        "period_comparison.dot",
    ),
    "period / year_over_year_slope": (
        "period__year_over_year_slope.png",
        "period_comparison.slope",
    ),
    "period / year_over_year_slope_small_multiples": (
        "period__year_over_year_slope_small_multiples.png",
        "period_comparison.slope",
    ),
    "mix_comparison / bar": ("mix_comparison__bar.png", "mix.bar"),
    "mix_current / stacked_bar": (
        "mix_current__mix_regular__stacked_bar.png",
        "mix.stacked_bar",
    ),
    "mix_comparison / bar_small_multiples": (
        "mix_comparison__bar_small_multiples.png",
        "mix.bar",
    ),
    "mix_current / stacked_bar_small_multiples": (
        "mix_current__mix_regular__stacked_bar_small_multiples.png",
        "mix.stacked_bar",
    ),
    "mix_comparison / related_metrics_bar": (
        "mix_comparison__related_metrics_bar.png",
        "mix.stacked_bar_overlay",
    ),
    "mix_comparison / related_metrics_bar_small_multiples": (
        "mix_comparison__related_metrics_bar_small_multiples.png",
        "mix.stacked_bar_overlay",
    ),
    "mix_comparison / multitier_bar": (
        "mix_comparison__multitier_bar.png",
        "mix.multitier_bar",
    ),
    "mix_comparison / multitier_bar_dimension_panels": (
        "mix_comparison__multitier_bar_dimension_panels.png",
        "mix.multitier_bar",
    ),
    "mix_comparison / multitier_bar_two_dimension": (
        "mix_comparison__multitier_bar_two_dimension.png",
        "mix.multitier_bar",
    ),
    "mix_like_for_like / like_for_like_column_total": (
        "mix_like_for_like__like_for_like_column_total.png",
        "mix.like_for_like_column",
    ),
    "mix_like_for_like / like_for_like_stacked_column": (
        "mix_like_for_like__like_for_like_stacked_column.png",
        "mix.like_for_like_stacked_column",
    ),
    "mix_cohort / cohort_since_stacked_column": (
        "mix_cohort__cohort_since_stacked_column.png",
        "mix.cohort_since_stacked_column",
    ),
    "mix_cohort / cohort_lost_stacked_column": (
        "mix_cohort__cohort_lost_stacked_column.png",
        "mix.cohort_lost_stacked_column",
    ),
    "mix_comparison / mix_comparison_column_total / column_total": (
        "mix_comparison__mix_comparison_column_total__column_total.png",
        "mix.column",
    ),
    "mix_comparison / mix_comparison_column_total / column_total_with_overlay": (
        "mix_comparison__mix_comparison_column_total__column_total_with_overlay.png",
        "mix.column_overlay",
    ),
    "mix_comparison / mix_regular / stacked_column": (
        "mix_comparison__mix_regular__stacked_column.png",
        "mix.stacked_column",
    ),
    "mix_comparison / mix_regular / stacked_column_small_multiples": (
        "mix_comparison__mix_regular__stacked_column_small_multiples.png",
        "mix.stacked_column",
    ),
    "mix_comparison / line": (
        "mix_comparison__mix_regular__line.png",
        "mix.timeline",
    ),
    "mix_comparison / line_small_multiples": (
        "mix_comparison__mix_regular__line_small_multiples.png",
        "mix.timeline",
    ),
    "mix_comparison / area_absolute": (
        "mix_comparison__mix_regular__area_absolute.png",
        "mix.area",
    ),
    "mix_comparison / area_share": (
        "mix_comparison__mix_regular__area_share.png",
        "mix.area",
    ),
    "mix_current / barmekko": (
        "mix_current__mix_regular__barmekko.png",
        "mix.barmekko",
    ),
    "mix_current / barmekko_small_multiples": (
        "mix_current__mix_regular__barmekko_small_multiples.png",
        "mix.barmekko",
    ),
    "mix_current / marimekko": (
        "mix_current__mix_regular__marimekko.png",
        "mix.marimekko",
    ),
    "mix_current / marimekko_small_multiples": (
        "mix_current__mix_regular__marimekko_small_multiples.png",
        "mix.marimekko",
    ),
    "mix_current / pareto": (
        "mix_current__mix_regular__pareto.png",
        "mix.pareto",
    ),
    "mix_current / stacked_pareto_abc": (
        "mix_current__mix_regular__stacked_pareto_abc.png",
        "mix.stacked_pareto",
    ),
    "mix_current / stacked_pareto_by_dimension": (
        "mix_current__mix_regular__stacked_pareto_by_dimension.png",
        "mix.stacked_pareto",
    ),
    "scatter / scatter_bubble / bubble": (
        "scatter__scatter_bubble__bubble.png",
        "scatter.bubble",
    ),
    "scatter / scatter_bubble / bubble_small_multiples": (
        "scatter__scatter_bubble__bubble_small_multiples.png",
        "scatter.bubble",
    ),
    "scatter / scatter_bubble / scatter": (
        "scatter__scatter_bubble__scatter.png",
        "scatter.scatter",
    ),
    "scatter / scatter_bubble / scatter_small_multiples": (
        "scatter__scatter_bubble__scatter_small_multiples.png",
        "scatter.scatter",
    ),
    "distribution / boxplot": ("distribution__boxplot.png", "distribution.boxplot"),
    "distribution / boxplot_small_multiples": (
        "distribution__boxplot_small_multiples.png",
        "distribution.boxplot",
    ),
    "distribution / ecdf": ("distribution__ecdf.png", "distribution.ecdf"),
    "distribution / ecdf_small_multiples": (
        "distribution__ecdf_small_multiples.png",
        "distribution.ecdf",
    ),
    "distribution / histogram": (
        "distribution__histogram.png",
        "distribution.histogram",
    ),
    "distribution / histogram_small_multiples": (
        "distribution__histogram_small_multiples.png",
        "distribution.histogram",
    ),
    "distribution / kernel_density": (
        "distribution__kernel_density.png",
        "distribution.kernel_density",
    ),
    "distribution / kernel_density_small_multiples": (
        "distribution__kernel_density_small_multiples.png",
        "distribution.kernel_density",
    ),
    "distribution / stripplot": (
        "distribution__stripplot.png",
        "distribution.stripplot",
    ),
    "distribution / stripplot_small_multiples": (
        "distribution__stripplot_small_multiples.png",
        "distribution.stripplot",
    ),
    "set_overlap / set_overlap_small_multiples / upset_small_multiples": (
        "set_overlap__set_overlap_small_multiples__upset_small_multiples.png",
        "set_overlap.upset_small_multiples",
    ),
    "set_overlap / upset": ("set_overlap__upset.png", "set_overlap.upset"),
    "set_overlap / venn": ("set_overlap__venn.png", "set_overlap.venn"),
    "funnel / funnel_stage_table": (
        "funnel__funnel_stage_table.png",
        "funnel.stage_table",
    ),
    "statement / pnl_statement_table": (
        "statement__pnl_statement_table.png",
        "statement.pnl_table",
    ),
    "attributes / attribute_bridge_table": (
        "attributes__attribute_bridge_table.png",
        "attributes.attribute_bridge_table",
    ),
    "attributes / attribute_bundle_comparison_table": (
        "attributes__attribute_bundle_comparison_table.png",
        "attributes.attribute_bundle_comparison_table",
    ),
    "attributes / product_signal_evidence_table": (
        "attributes__product_signal_evidence_table.png",
        "attributes.product_signal_evidence_table",
    ),
    "attributes / rank_weighted_visibility_table": (
        "attributes__rank_weighted_visibility_table.png",
        "attributes.rank_weighted_visibility_table",
    ),
}


def test_static_png_gallery_keeps_expected_published_cards() -> None:
    """Guard against unnoticed removals or remapped gallery cards."""

    manifest = json.loads((GALLERY_DIR / "manifest.json").read_text(encoding="utf-8"))
    items = {item["label"]: item for item in manifest["items"]}

    assert len(items) == len(manifest["items"])

    missing_labels = sorted(set(EXPECTED_PUBLISHED_GALLERY_CARDS) - set(items))
    assert missing_labels == []

    for label, (output_name, capability_id) in EXPECTED_PUBLISHED_GALLERY_CARDS.items():
        item = items[label]

        assert item["output"] == output_name
        assert item["artifact_contract"]["capability_id"] == capability_id
        assert (GALLERY_DIR / output_name).is_file()


def test_static_png_gallery_includes_first_class_table_examples() -> None:
    """Guard the published gallery cards for first-class reporting tables."""

    index_html = (GALLERY_DIR / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((GALLERY_DIR / "manifest.json").read_text(encoding="utf-8"))
    items = {item["label"]: item for item in manifest["items"]}

    assert "Report source examples" in index_html
    assert "scroll-margin-top:24px" in index_html
    assert "function scrollToHashTarget()" in index_html
    assert "window.addEventListener('hashchange',scheduleHashScroll)" in index_html
    assert "image.addEventListener('load',scheduleHashScroll,{once:true})" in index_html
    for section_id in (
        "movement-source",
        "composition-source",
        "relationship-source",
        "table-source",
        "distribution-analysis",
        "mix-contribution-analysis",
        "period-comparison",
        "funnel-analysis",
        "statement-analysis",
        "scatter-bubble-analysis",
        "set-overlap-analysis",
        "variance-analysis",
        "attribute-tables",
    ):
        assert f'id="{section_id}"' in index_html

    expected_outputs = {
        "period / comparison_table": "period__comparison_table.png",
        "period / time_series_table": "period__time_series_table.png",
        "funnel / funnel_stage_table": "funnel__funnel_stage_table.png",
        "statement / pnl_statement_table": "statement__pnl_statement_table.png",
        "attributes / attribute_bridge_table": "attributes__attribute_bridge_table.png",
        "attributes / attribute_bundle_comparison_table": (
            "attributes__attribute_bundle_comparison_table.png"
        ),
        "attributes / product_signal_evidence_table": (
            "attributes__product_signal_evidence_table.png"
        ),
        "attributes / rank_weighted_visibility_table": (
            "attributes__rank_weighted_visibility_table.png"
        ),
    }
    expected_recency_window_outputs = {
        "period / year_over_year_by_recency_window": (
            "period__year_over_year_by_period.png"
        ),
        "period / year_over_year_by_recency_window_small_multiples": (
            "period__year_over_year_by_period_small_multiples.png"
        ),
    }
    expected_variance_outputs = {
        "variance / waterfall": (
            "variance__waterfall.png",
            "variance.scenario_bridge",
        ),
        "variance / pvm_decomposition_ladder": (
            "variance__pvm_decomposition_ladder.png",
            "variance.price_volume_mix",
        ),
        "variance / waterfall_small_multiples": (
            "variance__waterfall_small_multiples.png",
            "variance.scenario_bridge",
        ),
        "variance / exploded_variance_bridge": (
            "variance__exploded_variance_bridge.png",
            "variance.exploded_variance_bridge",
        ),
        "variance / root_cause_component_bridge": (
            "variance__root_cause_component_bridge.png",
            "variance.root_cause_component_bridge",
        ),
        "variance / root_cause_total_bridge": (
            "variance__root_cause_total_bridge.png",
            "variance.root_cause_total_bridge",
        ),
        "variance / root_cause_exploded_bridge": (
            "variance__root_cause_exploded_bridge.png",
            "variance.root_cause_exploded_bridge",
        ),
        "variance / total_by_dimension_bridge": (
            "variance__total_by_dimension_bridge.png",
            "variance.total_by_dimension_bridge",
        ),
    }
    expected_mix_outputs = {
        "mix_comparison / bar": ("mix_comparison__bar.png", "mix.bar"),
        "mix_comparison / bar_small_multiples": (
            "mix_comparison__bar_small_multiples.png",
            "mix.bar",
        ),
        "mix_current / stacked_bar": (
            "mix_current__mix_regular__stacked_bar.png",
            "mix.stacked_bar",
        ),
        "mix_current / stacked_bar_small_multiples": (
            "mix_current__mix_regular__stacked_bar_small_multiples.png",
            "mix.stacked_bar",
        ),
        "mix_comparison / related_metrics_bar": (
            "mix_comparison__related_metrics_bar.png",
            "mix.stacked_bar_overlay",
        ),
        "mix_comparison / related_metrics_bar_small_multiples": (
            "mix_comparison__related_metrics_bar_small_multiples.png",
            "mix.stacked_bar_overlay",
        ),
        "mix_comparison / mix_regular / stacked_column": (
            "mix_comparison__mix_regular__stacked_column.png",
            "mix.stacked_column",
        ),
        "mix_comparison / mix_regular / stacked_column_small_multiples": (
            "mix_comparison__mix_regular__stacked_column_small_multiples.png",
            "mix.stacked_column",
        ),
        "mix_comparison / line": (
            "mix_comparison__mix_regular__line.png",
            "mix.timeline",
        ),
        "mix_comparison / line_small_multiples": (
            "mix_comparison__mix_regular__line_small_multiples.png",
            "mix.timeline",
        ),
        "mix_comparison / area_absolute": (
            "mix_comparison__mix_regular__area_absolute.png",
            "mix.area",
        ),
        "mix_comparison / area_share": (
            "mix_comparison__mix_regular__area_share.png",
            "mix.area",
        ),
        "mix_current / barmekko": (
            "mix_current__mix_regular__barmekko.png",
            "mix.barmekko",
        ),
        "mix_current / barmekko_small_multiples": (
            "mix_current__mix_regular__barmekko_small_multiples.png",
            "mix.barmekko",
        ),
        "mix_current / marimekko": (
            "mix_current__mix_regular__marimekko.png",
            "mix.marimekko",
        ),
        "mix_current / marimekko_small_multiples": (
            "mix_current__mix_regular__marimekko_small_multiples.png",
            "mix.marimekko",
        ),
        "mix_current / pareto": (
            "mix_current__mix_regular__pareto.png",
            "mix.pareto",
        ),
        "mix_current / stacked_pareto_abc": (
            "mix_current__mix_regular__stacked_pareto_abc.png",
            "mix.stacked_pareto",
        ),
        "mix_current / stacked_pareto_by_dimension": (
            "mix_current__mix_regular__stacked_pareto_by_dimension.png",
            "mix.stacked_pareto",
        ),
    }

    for label, output_name in expected_outputs.items():
        assert label in index_html
        assert output_name in index_html
        assert (GALLERY_DIR / output_name).is_file()
        assert items[label]["output"] == output_name
        assert items[label]["artifact_type"] == "table"
        assert not items[label]["quality_flags"]

    for label, output_name in expected_recency_window_outputs.items():
        assert label in index_html
        assert output_name in index_html
        assert (GALLERY_DIR / output_name).is_file()
        assert items[label]["output"] == output_name
        assert items[label]["artifact_type"] == "html"
        assert isinstance(items[label]["quality_flags"], list)

    assert "Variance Analysis <span>8 items</span>" in index_html
    variance_labels = [
        item["label"]
        for item in manifest["items"]
        if item["plugin_source"] == "variance-analysis"
    ]
    assert variance_labels[-2:] == [
        "variance / exploded_variance_bridge",
        "variance / root_cause_exploded_bridge",
    ]
    for label, (output_name, capability_id) in expected_variance_outputs.items():
        assert label in index_html
        assert output_name in index_html
        assert (GALLERY_DIR / output_name).is_file()
        assert items[label]["output"] == output_name
        assert items[label]["artifact_type"] == "png"
        assert items[label]["plugin_source_label"] == "Variance Analysis"
        assert items[label]["artifact_contract"]["capability_id"] == capability_id
        assert items[label]["artifact_readiness"]["ready"] is True
        assert not items[label]["quality_flags"]
        assert {sidecar["label"] for sidecar in items[label]["sidecars"]} >= {
            "source",
            "context",
            "data",
            "manifest",
            "recipe",
        }

    for label, (output_name, capability_id) in expected_mix_outputs.items():
        assert label in index_html
        assert output_name in index_html
        assert (GALLERY_DIR / output_name).is_file()
        assert items[label]["output"] == output_name
        assert items[label]["plugin_source_label"] == "Mix & Contribution Analysis"
        assert items[label]["artifact_contract"]["capability_id"] == capability_id
        assert {sidecar["label"] for sidecar in items[label]["sidecars"]} >= {
            "source",
            "context",
            "data",
            "manifest",
            "recipe",
        }

    assert "period / year_over_year_by_period</div>" not in index_html
    assert "period / year_over_year_by_period_small_multiples</div>" not in index_html
    assert " / index" not in index_html
    assert "__index.png" not in index_html
    assert "audit-reconciliation" not in index_html
    assert "client-intake" not in index_html
    assert "openai-data-analytics-capability-review" not in index_html

    for item in manifest["items"]:
        assert not item["label"].endswith(" / index")
        dimensions = item["dimensions"]
        image_tag = (
            f'<img src="{item["output"]}" width="{dimensions["width"]}" '
            f'height="{dimensions["height"]}" loading="lazy">'
        )
        assert image_tag in index_html

    for label in expected_outputs:
        if label.startswith("attributes / "):
            assert items[label]["plugin_source_label"] == "Attribute Tables"
            expected_limit = (
                10 if label == "attributes / product_signal_evidence_table" else 5
            )
            assert items[label]["display_row_limit"] == expected_limit
        if label.startswith("funnel / "):
            assert items[label]["plugin_source_label"] == "Funnel Analysis"
            assert items[label]["artifact_contract"]["capability_id"] == (
                "funnel.stage_table"
            )
        if label.startswith("statement / "):
            assert items[label]["plugin_source_label"] == "Statement Analysis"
            assert items[label]["artifact_contract"]["capability_id"] == (
                "statement.pnl_table"
            )

    assert index_html.index("Period Comparison") < index_html.index("Funnel Analysis")
    assert index_html.index("Funnel Analysis") < index_html.index("Statement Analysis")
    assert index_html.index("Scatter &amp; Bubble Analysis") < index_html.index(
        "Distribution Analysis"
    )
    assert index_html.index("Relationship, spread and overlap sources") < (
        index_html.index("Structured table sources")
    )
    assert index_html.index("Variance Analysis") < index_html.index("Attribute Tables")


def test_static_png_gallery_includes_set_overlap_small_multiples() -> None:
    """Guard the published Set Overlap small-multiple gallery card."""

    index_html = (GALLERY_DIR / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((GALLERY_DIR / "manifest.json").read_text(encoding="utf-8"))
    items = {item["label"]: item for item in manifest["items"]}
    label = "set_overlap / set_overlap_small_multiples / upset_small_multiples"
    output_name = "set_overlap__set_overlap_small_multiples__upset_small_multiples.png"

    assert "Set Overlap Analysis <span>3 items</span>" in index_html
    assert (
        "Relationship, spread and overlap sources <span>17 items</span>" in index_html
    )
    assert label in index_html
    assert output_name in index_html
    assert (GALLERY_DIR / output_name).is_file()
    assert items[label]["output"] == output_name
    assert items[label]["artifact_type"] == "html"
    assert items[label]["dimensions"] == {"width": 1090, "height": 1971}
    assert not items[label]["quality_flags"]


def test_static_png_gallery_exposes_three_row_title_context_for_every_card() -> None:
    """Guard the gallery manifest title wiring used by review/orchestration flows."""

    manifest = json.loads((GALLERY_DIR / "manifest.json").read_text(encoding="utf-8"))

    for item in manifest["items"]:
        title_context = item.get("title_context")
        assert isinstance(title_context, dict), item["label"]
        lines = title_context.get("lines")
        assert isinstance(lines, list), item["label"]
        assert len(lines) == 3, item["label"]
        assert lines == [
            title_context.get("who"),
            title_context.get("what"),
            title_context.get("when"),
        ]
        assert all(isinstance(line, str) and line.strip() for line in lines)
        assert "None" not in lines

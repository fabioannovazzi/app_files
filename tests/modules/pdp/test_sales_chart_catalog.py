from __future__ import annotations

from modules.pdp.sales_chart_catalog import (
    build_sales_chart_patterns,
    load_sales_chart_catalog,
    resolve_sales_chart_options,
)


def test_load_sales_chart_catalog_includes_action_metadata() -> None:
    catalog = load_sales_chart_catalog()

    assert catalog.version == 1
    assert "plotMarimekko" not in catalog.actions
    assert "plotBarMekko" not in catalog.actions
    assert catalog.actions["plotTotalCombo"].kind == "plot"
    assert catalog.actions["plotTotalCombo"].evidence_role == "primary"
    assert catalog.actions["plotTotalCombo"].lenses == (
        "growth_size",
        "price_value_capture",
    )
    assert catalog.actions["plotAreaAbsolute"].chart_type == "area"
    assert catalog.actions["plotAreaAbsolute"].request_overrides == {
        "chart_type": "area",
        "area_mode": "absolute",
    }
    assert catalog.actions["plotStackedColumn"].variants == ("standard",)
    assert catalog.actions["plotStackedColumn"].request_overrides == {
        "chart_type": "stacked_column"
    }
    assert all(
        rule.action is None or rule.action in catalog.actions for rule in catalog.rules
    )
    assert {
        "plotTotalCombo",
        "plotAreaAbsolute",
        "plotStackedColumn",
        "plotStacked100",
    }.isdisjoint({str(rule.action) for rule in catalog.rules if rule.action})


def test_load_sales_chart_catalog_includes_table_actions() -> None:
    catalog = load_sales_chart_catalog()

    expected_templates = {
        "tableAttributeBundleComparison": "attribute_bundle_comparison_table",
        "tableAttributeBridge": "attribute_bridge_table",
        "tableRankWeightedVisibility": "rank_weighted_visibility_table",
        "tableProductSignalEvidence": "product_signal_evidence_table",
    }

    for action_name, template_name in expected_templates.items():
        table_action = catalog.actions[action_name]
        assert table_action.kind == "table"
        assert table_action.rendering == "server_table"
        assert table_action.chart_type == "evidence_table"
        assert table_action.brief_enabled is False
        assert table_action.use_when
        assert table_action.avoid_when
        assert table_action.required_parameters == ("package_dir",)
        assert table_action.optional_parameters == ("output_dir", "table_keys")
        assert table_action.request_overrides["table_template"] == template_name
        assert table_action.request_overrides["source"] == (
            f"attribute_tables/{template_name}.csv"
        )


def test_load_sales_chart_catalog_requires_lens_metadata_for_all_actions() -> None:
    catalog = load_sales_chart_catalog()

    assert all(action.lenses for action in catalog.actions.values())
    assert all(action.evidence_role for action in catalog.actions.values())
    assert all(action.time_scope for action in catalog.actions.values())
    assert all(action.scope_support for action in catalog.actions.values())


def test_resolve_sales_chart_options_returns_candidate_set_for_single_month_sales() -> (
    None
):
    matched_rules, blocking_rule = resolve_sales_chart_options(
        {
            "dimsCount": 1,
            "isSingleMonthSelected": True,
            "periodMode": "single_month",
            "metrics": ["sales"],
            "isSingleNonAttributeDimension": False,
        }
    )

    assert blocking_rule is None
    assert {rule.action for rule in matched_rules} == {
        "plotVerticalWaterfall",
        "plotPareto",
        "plotSlope",
    }


def test_build_sales_chart_patterns_groups_rules_into_catalog_patterns() -> None:
    patterns = build_sales_chart_patterns()

    assert patterns
    pattern_actions = {
        action.action for pattern in patterns for action in pattern.chart_actions
    }
    assert {"plotVerticalWaterfall", "plotPareto"} <= pattern_actions

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_chart_manifest_against_dataset_profile import (
    audit_manifest_against_dataset_profile,
)
from scripts.build_chart_dataset_profile import build_dataset_profile
from scripts.build_chart_selection_manifest import build_chart_selection_manifest


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_profile(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_dataset_profile_exposes_role_candidates_without_known_false_positives(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "sales.csv"
    source_path.write_text(
        "\n".join(
            [
                "month,sales,sku,canonical_id,animal_protein_source__turkey,usage stage,retailer,brand",
                "2025-01-01,10,A,CA,yes,morning,amazon,alpha",
                "2025-02-01,15,B,CB,no,night,ulta,beta",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = build_dataset_profile(source_path, dataset_id="fixture")

    entity_columns = [
        candidate["column"] for candidate in profile["role_candidates"]["entity_key"]
    ]
    assert "sku" in entity_columns
    assert "canonical_id" in entity_columns
    assert "animal_protein_source__turkey" not in profile["roles"].get("identifier", [])
    assert "usage stage" not in [
        candidate["column"]
        for candidate in profile["role_candidates"].get("ordered_stage", [])
    ]


def test_audit_manifest_resolves_derived_entity_period_role(
    tmp_path: Path,
) -> None:
    profile_path = _write_profile(
        tmp_path / "profile.json",
        {
            "schema_version": "0.1",
            "dataset_id": "fixture",
            "roles": {
                "period": ["month"],
                "dimension": ["brand"],
                "metric": ["sales", "units"],
            },
            "metric_classes": {
                "additive_value": ["sales"],
                "additive_volume": ["units"],
            },
            "columns": {
                "month": {
                    "role": "period",
                    "period_parseability": {"is_parseable": True},
                },
                "brand": {"role": "dimension", "cardinality_class": "low"},
                "sales": {"role": "metric", "metric_class": "additive_value"},
                "units": {"role": "metric", "metric_class": "additive_volume"},
            },
            "role_candidates": {
                "entity_key": [{"column": "sku"}],
                "direct_dimension": [{"column": "brand"}],
            },
        },
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        {
            "capabilities": {
                "test.like_for_like": {
                    "capability_id": "test.like_for_like",
                    "selection_emphasis": "same_population_total_change",
                    "selection_contract": {
                        "dataset_requirements": {
                            "period": {
                                "role": "axis",
                                "requires_period_axis": True,
                                "allows_period_filter": True,
                            },
                            "metrics": {
                                "source_metric_roles": [
                                    {
                                        "role": "primary_metric",
                                        "required": True,
                                        "accepted_metric_classes": ["additive_value"],
                                        "aggregation": "sum",
                                    }
                                ],
                                "derived_metric_roles": [],
                            },
                            "dimensions": {
                                "minimum_count": 0,
                                "required_roles": ["stable_population_flag"],
                                "role_requirements": {
                                    "stable_population_flag": {
                                        "role": "stable_population_flag",
                                        "required": True,
                                        "resolution_type": "derived_from_entity_period",
                                        "requires_profile_roles": [
                                            "period",
                                            "entity_key",
                                        ],
                                    }
                                },
                            },
                        }
                    },
                }
            }
        },
    )

    audit = audit_manifest_against_dataset_profile(manifest_path, profile_path)

    result = audit["results"][0]
    assert result["status"] == "mechanically_compatible"
    assert result["role_resolutions"][0]["missing_profile_roles"] == []
    assert result["role_resolutions"][0]["prerequisite_matches"] == {
        "entity_key": ["sku"],
        "period": ["month"],
    }
    role_matches = {
        (match["kind"], match["role"]): match
        for match in result["mechanical_role_matches"]
    }
    assert role_matches[("metric", "primary_metric")]["fit_status"] == "satisfied"
    assert role_matches[("metric", "primary_metric")]["example_column"] == "sales"
    assert role_matches[("period", "period_axis")]["candidate_columns"] == ["month"]
    assert (
        role_matches[("dimension", "stable_population_flag")]["fit_status"]
        == "satisfied"
    )
    assert result["unmatched_required_roles"] == []
    metric_rejections = next(
        rejected
        for rejected in result["rejected_column_evidence"]
        if rejected["kind"] == "metric"
    )
    assert metric_rejections["rejected_count"] == 1
    assert metric_rejections["samples"][0]["column"] == "units"
    assert metric_rejections["samples"][0]["reason"] == "metric_class_not_accepted"


def test_audit_manifest_flags_period_filter_scope_before_render(
    tmp_path: Path,
) -> None:
    profile_path = _write_profile(
        tmp_path / "profile.json",
        {
            "schema_version": "0.1",
            "dataset_id": "fixture",
            "roles": {
                "period": ["date"],
                "dimension": [],
                "metric": [],
            },
            "metric_classes": {},
            "columns": {
                "date": {
                    "role": "period",
                    "period_parseability": {"is_parseable": True},
                },
            },
            "role_candidates": {},
        },
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        {
            "capabilities": {
                "test.period_filter": {
                    "capability_id": "test.period_filter",
                    "selection_emphasis": "selected_period_distribution",
                    "selection_contract": {
                        "dataset_requirements": {
                            "period": {
                                "role": "filter",
                                "requires_period_axis": False,
                                "allows_period_filter": True,
                                "scope_contract": {
                                    "role": "filter",
                                    "scope_required_for_render": True,
                                    "explicit_all_data_allowed": True,
                                    "accepted_scope_controls": [
                                        "options.selected_periods",
                                        "options.period_window",
                                    ],
                                    "unscoped_default": "all_available_records",
                                },
                            },
                            "metrics": {
                                "source_metric_roles": [],
                                "derived_metric_roles": [],
                            },
                            "dimensions": {
                                "minimum_count": 0,
                                "required_roles": [],
                                "role_requirements": {},
                            },
                        }
                    },
                }
            }
        },
    )

    audit = audit_manifest_against_dataset_profile(manifest_path, profile_path)

    result = audit["results"][0]
    assert result["status"] == "mechanically_compatible"
    assert result["issues"] == []
    assert result["period_scope"] == {
        "role": "filter",
        "status": "caller_scope_required_before_render",
        "period_column_required": True,
        "scope_required_for_render": True,
        "explicit_all_data_allowed": True,
        "accepted_scope_controls": [
            "options.selected_periods",
            "options.period_window",
        ],
        "period_candidates": ["date"],
        "unscoped_default": "all_available_records",
        "pre_render_warning": (
            "This chart has a period filter. A caller must pass a bounded "
            "analysis period or explicitly request all available data."
        ),
        "comparison_pair_required": False,
        "minimum_distinct_period_values": 0,
        "available_distinct_period_values": 0,
        "period_value_evidence": [
            {"column": "date", "distinct_count": 0, "ordered_values": []}
        ],
    }


def test_optional_period_filter_does_not_reject_cross_sectional_dataset(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "cross_section.csv"
    source_path.write_text(
        "\n".join(
            [
                "sku,category,sales,units,margin_percent",
                "A,Face,100,10,0.20",
                "B,Face,120,12,0.22",
                "C,Hair,80,8,0.18",
                "D,Hair,95,9,0.19",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    profile_path = _write_profile(
        tmp_path / "cross_section_profile.json",
        build_dataset_profile(source_path, dataset_id="cross_section"),
    )
    manifest_path = _write_json(
        tmp_path / "selection_manifest.json",
        build_chart_selection_manifest(),
    )

    audit = audit_manifest_against_dataset_profile(manifest_path, profile_path)

    results = {result["capability_id"]: result for result in audit["results"]}
    for capability_id in ("distribution.histogram", "scatter.scatter"):
        result = results[capability_id]
        assert result["status"] == "mechanically_compatible"
        period_match = next(
            match
            for match in result["mechanical_role_matches"]
            if match["kind"] == "period"
        )
        assert period_match["required"] is False
        assert period_match["fit_status"] == "optional_not_matched"
        assert result["unmatched_required_roles"] == []
        assert result["unavailable_optional_roles"] == [
            {"kind": "period", "role": "period_filter", "issue": None}
        ]
        assert result["period_scope"]["status"] == (
            "optional_filter_unavailable_all_data_only"
        )

    histogram_observations = results["distribution.histogram"]["observation_evidence"]
    assert histogram_observations["required_minimum_non_null_rows"] == 3
    assert histogram_observations["available_observation_rows"] == 4
    assert "narrower scope" in histogram_observations["scope_warning"]

    variance = results["variance.scenario_bridge"]
    assert variance["status"] == "mechanically_incomplete"
    assert "missing_required_period_column" in variance["issues"]


def test_dataset_profile_orders_numeric_years_and_exposes_dimension_relationships(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "variance.csv"
    source_path.write_text(
        "\n".join(
            [
                "year,region,subregion,product,sales,units",
                "2023,North,North,A,100,10",
                "2024,North,North,A,130,13",
                "2023,South,South,A,80,8",
                "2024,South,South,A,70,7",
                "2023,North,North,B,150,15",
                "2024,North,North,B,120,10",
                "2023,South,South,B,90,9",
                "2024,South,South,B,150,15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    profile = build_dataset_profile(source_path, dataset_id="variance")

    assert profile["columns"]["year"]["role"] == "period"
    assert profile["columns"]["year"]["ordered_values"] == [2023, 2024]
    assert profile["columns"]["year"]["period_parseability"]["inferred_grain"] == "year"
    relationships = {
        (item["left_column"], item["right_column"]): item
        for item in profile["dimension_relationships"]
    }
    assert relationships[("region", "subregion")]["relationship"] == ("bijective_alias")
    assert (
        relationships[("region", "subregion")]["supports_multidimensional_path"]
        is False
    )
    assert relationships[("region", "product")]["relationship"] == ("cross_classifying")
    assert (
        relationships[("region", "product")]["supports_multidimensional_path"] is True
    )


def test_compatibility_rejects_comparison_chart_with_one_distinct_period(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "single_period.csv"
    source_path.write_text(
        "year,category,sales\n2024,A,10\n2024,B,20\n",
        encoding="utf-8",
    )
    profile_path = _write_profile(
        tmp_path / "profile.json",
        build_dataset_profile(source_path, dataset_id="single_period"),
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        build_chart_selection_manifest(),
    )

    audit = audit_manifest_against_dataset_profile(manifest_path, profile_path)

    trend = next(
        result
        for result in audit["results"]
        if result["capability_id"] == "period_comparison.trend"
    )
    assert trend["status"] == "mechanically_incomplete"
    assert "insufficient_distinct_period_values" in trend["issues"]
    assert trend["period_scope"]["minimum_distinct_period_values"] == 2
    assert trend["period_scope"]["available_distinct_period_values"] == 1


def test_compatibility_surfaces_optional_panel_candidates_without_requiring_them(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "scatter.csv"
    source_path.write_text(
        "\n".join(
            [
                "date,brand,category,sales,units,margin_rate",
                "2025-01-01,A,Face,100,10,0.20",
                "2025-02-01,B,Face,120,12,0.22",
                "2025-03-01,A,Hair,80,8,0.18",
                "2025-04-01,B,Hair,95,9,0.19",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    profile_path = _write_profile(
        tmp_path / "profile.json",
        build_dataset_profile(source_path, dataset_id="scatter"),
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        build_chart_selection_manifest(),
    )

    audit = audit_manifest_against_dataset_profile(manifest_path, profile_path)

    scatter = next(
        result
        for result in audit["results"]
        if result["capability_id"] == "scatter.scatter"
    )
    optional_panel = next(
        match
        for match in scatter["mechanical_role_matches"]
        if match["role"] == "optional_panel"
    )
    assert scatter["status"] == "mechanically_compatible"
    assert scatter["optional_dimension_roles"] == ["optional_panel"]
    assert optional_panel["required"] is False
    assert optional_panel["fit_status"] == "satisfied"
    assert set(optional_panel["candidate_columns"]) >= {"brand", "category"}

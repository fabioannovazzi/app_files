from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_chart_manifest_against_dataset_profile import (
    audit_manifest_against_dataset_profile,
)
from scripts.build_chart_dataset_profile import build_dataset_profile


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

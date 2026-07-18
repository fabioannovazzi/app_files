from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "reporting-engine"
FIXTURE_ROOT = PLUGIN_ROOT / "fixtures" / "semantic_layer"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _modules() -> tuple[Any, Any]:
    profiler = _load_module(
        "reporting_engine_semantic_profiler_test",
        PLUGIN_ROOT / "scripts" / "profile_dataset.py",
    )
    semantic = _load_module(
        "reporting_engine_semantic_layer_test",
        PLUGIN_ROOT / "scripts" / "semantic_layer.py",
    )
    return profiler, semantic


def _fixture_profile(profiler: Any) -> dict[str, Any]:
    return profiler.profile_dataset(
        FIXTURE_ROOT / "retail_monthly.csv", dataset_id="retail_monthly"
    )


def _manifest() -> dict[str, Any]:
    return json.loads(
        (PLUGIN_ROOT / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _reviewed_layer() -> dict[str, Any]:
    return json.loads(
        (FIXTURE_ROOT / "retail_monthly.semantic.json").read_text(encoding="utf-8")
    )


def test_semantic_layer_scaffold_is_valid_but_explicitly_unreviewed() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)

    layer = semantic.build_semantic_layer_scaffold(profile)
    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "draft_unreviewed"
    assert report["counts"]["unknown_concepts"] == 9
    assert report["counts"]["analysis_policies"] == 0
    assert all(metric["status"] == "unknown" for metric in layer["metrics"])
    assert all(dimension["status"] == "unknown" for dimension in layer["dimensions"])
    assert layer["review"]["status"] == "draft"


def test_semantic_authoring_context_exposes_all_manifest_analysis_types() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)

    context = semantic.build_authoring_context(profile, _manifest())

    assert len(context["analysis_catalog"]) == 48
    assert {record["selection_emphasis"] for record in context["analysis_catalog"]} == {
        treatment_id
        for task in _manifest()["analysis_tasks"].values()
        for treatment_id in task["treatments"]
    }
    assert all(record["required_role_sets"] for record in context["analysis_catalog"])
    assert context["semantic_layer_draft"]["review"]["status"] == "draft"
    assert "not a classifier" in context["boundary"]


def test_reviewed_semantic_fixture_is_ready_and_fully_manifest_bound() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)

    report = semantic.validate_semantic_layer(_reviewed_layer(), profile, _manifest())

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "ready_as_scoped_semantic_input"
    assert report["counts"]["analysis_validities"] == {
        "conditional": 0,
        "invalid": 1,
        "unknown": 0,
        "valid": 9,
    }
    assert report["counts"]["unknown_concepts"] == 0
    assert report["errors"] == []
    assert report["warnings"] == []
    assert report["analysis_coverage"]["manifest_selection_emphasis_count"] == 48
    assert len(report["analysis_coverage"]["assessed_selection_emphases"]) == 10
    assert report["analysis_coverage"]["unlisted_policy_default"] == "unknown"
    valid_results = [
        result for result in report["policy_results"] if result["validity"] == "valid"
    ]
    assert len(valid_results) == 9
    assert all(result["has_complete_manifest_role_set"] for result in valid_results)
    rejected = next(
        result
        for result in report["policy_results"]
        if result["analysis_id"] == "analysis.structured_statement"
    )
    assert rejected["candidate_capability_ids"] == ["statement.pnl_table"]
    assert rejected["has_complete_manifest_role_set"] is False


def test_profile_fingerprint_is_path_independent_but_content_sensitive() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    relocated = copy.deepcopy(profile)
    changed = copy.deepcopy(profile)
    relocated["source"]["path"] = "/another/machine/retail_monthly.csv"
    changed["row_count"] += 1

    original_fingerprint = semantic.canonical_profile_fingerprint(profile)

    assert semantic.canonical_profile_fingerprint(relocated) == original_fingerprint
    assert semantic.canonical_profile_fingerprint(changed) != original_fingerprint


def test_validator_rejects_reviewed_semantic_claim_without_evidence() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    layer["metrics"][0]["evidence_ids"] = []

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    assert any(error["code"] == "missing_evidence" for error in report["errors"])


def test_validator_applies_packaged_json_schema() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    layer["metrics"][0].pop("unit")
    layer["unexpected"] = True

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    schema_errors = [
        error
        for error in report["errors"]
        if error["code"] == "schema_validation_error"
    ]
    assert report["status"] == "contract_invalid"
    assert {error["path"] for error in schema_errors} >= {"$", "$.metrics[0]"}


def test_validator_returns_schema_errors_for_non_object_aggregation() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    layer["metrics"][0]["aggregation"] = ["sum"]

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    assert any(
        error["code"] == "schema_validation_error"
        and error["path"] == "$.metrics[0].aggregation"
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("metrics", "compatible_dimension_ids"),
        ("metrics", "valid_period_grains"),
        ("analysis_policies", "analysis_task_ids"),
        ("analysis_policies", "selection_emphases"),
    ],
)
def test_validator_rejects_non_list_collection_without_traversing_it(
    section: str,
    field: str,
) -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    layer[section][0][field] = 42

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    assert report["semantic_readiness"] == "contract_invalid"
    assert any(
        error["code"] == "schema_validation_error"
        and error["path"] == f"$.{section}[0].{field}"
        for error in report["errors"]
    )


def test_validator_rejects_semantic_claim_supported_only_by_profile() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    layer["metrics"][0]["evidence_ids"] = ["evidence.dataset_profile"]

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    assert any(
        error["code"] == "semantic_assertion_only_mechanical_evidence"
        for error in report["errors"]
    )


def test_validator_rejects_manifest_metric_class_mismatch() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    sales = next(
        metric for metric in layer["metrics"] if metric["metric_id"] == "metric.sales"
    )
    sales["metric_class"] = "rate"

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    trajectory = next(
        result
        for result in report["policy_results"]
        if result["analysis_id"] == "analysis.monthly_sales_trajectory"
    )
    assert trajectory["has_complete_manifest_role_set"] is False
    assert trajectory["role_set_results"][0]["semantic_mismatches"][0]["code"] == (
        "metric_class_not_accepted"
    )


def test_validator_rejects_profile_content_drift() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    changed_profile = copy.deepcopy(profile)
    changed_profile["row_count"] += 1

    report = semantic.validate_semantic_layer(
        _reviewed_layer(), changed_profile, _manifest()
    )

    assert report["status"] == "contract_invalid"
    assert report["semantic_readiness"] == "contract_invalid"
    assert any(
        error["code"] == "profile_fingerprint_mismatch" for error in report["errors"]
    )


def test_validator_rejects_valid_filter_analysis_without_period_scope() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    brand_ranking = next(
        policy
        for policy in layer["analysis_policies"]
        if policy["analysis_id"] == "analysis.current_brand_sales_ranking"
    )
    brand_ranking["period_scope_id"] = None

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_invalid"
    assert any(
        error["code"] == "incomplete_manifest_role_binding"
        for error in report["errors"]
    )
    result = next(
        value
        for value in report["policy_results"]
        if value["analysis_id"] == "analysis.current_brand_sales_ranking"
    )
    assert result["role_set_results"][0]["scope_missing"] is True


def test_incomplete_conditional_policy_is_not_usable_semantic_input() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    for policy in layer["analysis_policies"]:
        policy["validity"] = "invalid"
    conditional = layer["analysis_policies"][0]
    conditional["validity"] = "conditional"
    conditional["role_bindings"].pop("primary_metric")

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "reviewed_no_usable_analysis_policies"
    assert report["policy_results"][0]["has_complete_manifest_role_set"] is False
    assert any(
        warning["code"] == "conditional_role_binding_incomplete"
        for warning in report["warnings"]
    )


def test_conditional_policy_without_conditions_is_not_usable_semantic_input() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    for policy in layer["analysis_policies"]:
        policy["validity"] = "invalid"
    conditional = layer["analysis_policies"][0]
    conditional["validity"] = "conditional"
    conditional["conditions"] = []

    report = semantic.validate_semantic_layer(layer, profile, _manifest())

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "reviewed_no_usable_analysis_policies"
    assert report["policy_results"][0]["has_complete_manifest_role_set"] is True
    assert report["policy_results"][0]["usable_as_semantic_input"] is False
    assert any(
        warning["code"] == "conditional_conditions_incomplete"
        for warning in report["warnings"]
    )


def test_semantic_schema_required_keys_match_generated_scaffold() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    schema = json.loads(
        (PLUGIN_ROOT / "catalog" / "semantic_layer.schema.json").read_text(
            encoding="utf-8"
        )
    )

    layer = semantic.build_semantic_layer_scaffold(profile)

    assert set(schema["required"]) == set(layer)
    assert schema["properties"]["schema_version"]["const"] == "0.1"
    assert (
        schema["properties"]["boundaries"]["properties"]["chart_selection_included"][
            "const"
        ]
        is False
    )


def test_packaged_semantic_acceptance_summary_matches_exact_inputs() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    manifest_path = PLUGIN_ROOT / "catalog" / "selection_manifest.json"
    schema_path = PLUGIN_ROOT / "catalog" / "semantic_layer.schema.json"
    layer_path = FIXTURE_ROOT / "retail_monthly.semantic.json"
    source_path = FIXTURE_ROOT / "retail_monthly_source_notes.md"
    stored = json.loads(
        (PLUGIN_ROOT / "catalog" / "semantic_acceptance_summary.json").read_text(
            encoding="utf-8"
        )
    )

    rebuilt = semantic.build_semantic_acceptance_summary(
        profile,
        _reviewed_layer(),
        _manifest(),
        dataset_path=FIXTURE_ROOT / "retail_monthly.csv",
        layer_path=layer_path,
        manifest_path=manifest_path,
        schema_path=schema_path,
        source_paths=[source_path],
    )

    assert rebuilt == stored
    assert rebuilt["result"] == "pass"

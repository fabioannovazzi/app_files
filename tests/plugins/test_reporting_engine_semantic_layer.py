from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "clara" / "modules" / "reporting-engine"
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


def _fixture_profile(
    profiler: Any,
    filename: str = "retail_monthly.csv",
    *,
    dataset_id: str = "retail_monthly",
) -> dict[str, Any]:
    return profiler.profile_dataset(FIXTURE_ROOT / filename, dataset_id=dataset_id)


def _snapshot_cases(profiler: Any) -> list[tuple[str, str, Path, dict[str, Any]]]:
    suite = json.loads(
        (FIXTURE_ROOT / "retail_monthly.snapshot_cases.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        (
            case["case_id"],
            case["expected_status"],
            FIXTURE_ROOT / case["dataset"],
            _fixture_profile(profiler, case["dataset"]),
        )
        for case in suite["cases"]
    ]


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
    assert layer["dataset_contract"]["dataset_contract_id"] == "retail_monthly"
    assert layer["semantic_version"] == 1
    assert "period_rules" in layer
    assert "period_scopes" not in layer


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


def test_snapshot_fingerprint_is_path_independent_but_content_sensitive() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    relocated = copy.deepcopy(profile)
    changed = copy.deepcopy(profile)
    relocated["source"]["path"] = "/another/machine/retail_monthly.csv"
    changed["row_count"] += 1

    original_fingerprint = semantic.canonical_snapshot_fingerprint(profile)

    assert semantic.canonical_snapshot_fingerprint(relocated) == original_fingerprint
    assert semantic.canonical_snapshot_fingerprint(changed) != original_fingerprint


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


def test_changed_snapshot_values_do_not_invalidate_stable_semantics() -> None:
    profiler, semantic = _modules()
    origin_profile = _fixture_profile(profiler)
    refresh_profile = _fixture_profile(profiler, "retail_monthly_refresh.csv")

    report = semantic.validate_semantic_layer(
        _reviewed_layer(), refresh_profile, _manifest()
    )

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "ready_as_scoped_semantic_input"
    assert report["snapshot"]["is_origin_snapshot"] is False
    assert report["snapshot"]["compatibility"]["status"] == "compatible"
    assert report["snapshot"]["compatibility"]["semantic_layer_reusable"] is True
    assert semantic.canonical_snapshot_fingerprint(
        origin_profile
    ) != semantic.canonical_snapshot_fingerprint(refresh_profile)


def test_validator_rejects_valid_filter_analysis_without_period_rule() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    layer = _reviewed_layer()
    brand_ranking = next(
        policy
        for policy in layer["analysis_policies"]
        if policy["analysis_id"] == "analysis.current_brand_sales_ranking"
    )
    brand_ranking["period_rule_id"] = None

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


def test_refresh_resolves_current_ytd_from_snapshot_without_changing_semantics() -> (
    None
):
    profiler, semantic = _modules()
    refresh_profile = _fixture_profile(profiler, "retail_monthly_refresh.csv")

    resolutions = semantic.resolve_period_rules(_reviewed_layer(), refresh_profile)

    current_ytd = next(
        result
        for result in resolutions["results"]
        if result["period_rule_id"] == "period_rule.current_ytd"
    )
    comparison = next(
        result
        for result in resolutions["results"]
        if result["period_rule_id"] == "period_rule.current_ytd_vs_prior_ytd"
    )
    assert current_ytd["resolved_scope"]["windows"] == [
        {
            "role": "current",
            "label": "2026-01-01 to 2026-03-31",
            "start": "2026-01-01",
            "end": "2026-03-31",
        }
    ]
    assert comparison["resolved_scope"]["windows"][1] == {
        "role": "baseline",
        "label": "2025-01-01 to 2025-03-31",
        "start": "2025-01-01",
        "end": "2025-03-31",
    }


def test_comparison_rule_is_unavailable_when_prior_period_values_are_missing() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    profile["columns"]["Date"]["ordered_values"].remove("2025-02-01")

    resolutions = semantic.resolve_period_rules(_reviewed_layer(), profile)

    comparison = next(
        result
        for result in resolutions["results"]
        if result["period_rule_id"] == "period_rule.current_ytd_vs_prior_ytd"
    )
    assert comparison["resolution_status"] == "unavailable"
    assert comparison["reason"] == "snapshot_lacks_required_period_values"
    assert comparison["coverage_check"]["missing_period_starts"] == ["2025-02-01"]


def test_new_snapshot_column_reuses_semantics_as_unclassified_extension() -> None:
    profiler, semantic = _modules()
    extension_profile = _fixture_profile(profiler, "retail_monthly_extension.csv")

    result = semantic.assess_snapshot_compatibility(
        _reviewed_layer(), extension_profile
    )

    assert result["status"] == "compatible_with_extensions"
    assert result["semantic_layer_reusable"] is True
    assert result["extension_columns"] == ["Channel"]
    assert result["available_policy_count"] == 9


def test_missing_one_bound_metric_reuses_layer_with_reduced_policy_coverage() -> None:
    profiler, semantic = _modules()
    profile = _fixture_profile(profiler)
    profile["columns"].pop("Units")

    result = semantic.assess_snapshot_compatibility(_reviewed_layer(), profile)

    assert result["status"] == "partially_compatible"
    assert result["semantic_layer_reusable"] is True
    pvm = next(
        policy
        for policy in result["policy_results"]
        if policy["analysis_id"] == "analysis.sales_price_volume_mix"
    )
    trajectory = next(
        policy
        for policy in result["policy_results"]
        if policy["analysis_id"] == "analysis.monthly_sales_trajectory"
    )
    assert pvm["availability"] == "unavailable"
    assert trajectory["availability"] == "available"


def test_same_schema_cannot_override_explicit_dataset_contract_identity() -> None:
    profiler, semantic = _modules()
    different_asset_profile = _fixture_profile(
        profiler, dataset_id="another_retail_asset"
    )

    result = semantic.assess_snapshot_compatibility(
        _reviewed_layer(), different_asset_profile
    )

    assert result["status"] == "incompatible"
    assert result["identity_matches"] is False
    assert result["semantic_layer_reusable"] is False


def test_snapshot_attachment_keeps_reviewed_semantic_version_stable() -> None:
    profiler, semantic = _modules()
    refresh_profile = _fixture_profile(profiler, "retail_monthly_refresh.csv")

    attachment = semantic.build_snapshot_attachment(_reviewed_layer(), refresh_profile)

    assert attachment["attachment_status"] == "attached"
    assert attachment["dataset_contract_id"] == "retail_monthly"
    assert attachment["semantic_layer_id"] == "retail_monthly.reporting_semantics"
    assert attachment["semantic_version"] == 1
    assert attachment["snapshot"]["snapshot_id"].startswith("snapshot.")


def test_attach_cli_writes_reusable_refresh_attachment(tmp_path: Path) -> None:
    profiler, semantic = _modules()
    profile_path = tmp_path / "refresh_profile.json"
    output_path = tmp_path / "snapshot_attachment.json"
    profile_path.write_text(
        json.dumps(_fixture_profile(profiler, "retail_monthly_refresh.csv")),
        encoding="utf-8",
    )

    return_code = semantic.main(
        [
            "attach",
            "--profile",
            str(profile_path),
            "--layer",
            str(FIXTURE_ROOT / "retail_monthly.semantic.json"),
            "--output",
            str(output_path),
        ]
    )

    attachment = json.loads(output_path.read_text(encoding="utf-8"))
    assert return_code == 0
    assert attachment["attachment_status"] == "attached"
    assert attachment["compatibility"]["status"] == "compatible"
    assert attachment["semantic_version"] == 1


def test_attach_cli_rejects_snapshot_without_bound_metrics(tmp_path: Path) -> None:
    profiler, semantic = _modules()
    profile_path = tmp_path / "incompatible_profile.json"
    output_path = tmp_path / "snapshot_attachment.json"
    profile_path.write_text(
        json.dumps(_fixture_profile(profiler, "retail_monthly_incompatible.csv")),
        encoding="utf-8",
    )

    return_code = semantic.main(
        [
            "attach",
            "--profile",
            str(profile_path),
            "--layer",
            str(FIXTURE_ROOT / "retail_monthly.semantic.json"),
            "--output",
            str(output_path),
        ]
    )

    attachment = json.loads(output_path.read_text(encoding="utf-8"))
    assert return_code == 1
    assert attachment["attachment_status"] == "rejected"
    assert attachment["compatibility"]["status"] == "incompatible"


def test_stable_period_rules_contain_no_snapshot_date_windows() -> None:
    layer = _reviewed_layer()

    assert "period_scopes" not in layer
    assert all("windows" not in rule for rule in layer["period_rules"])
    assert all("start" not in rule for rule in layer["period_rules"])
    assert all("end" not in rule for rule in layer["period_rules"])


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
    assert schema["properties"]["schema_version"]["const"] == "0.2"
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
    snapshot_suite_path = FIXTURE_ROOT / "retail_monthly.snapshot_cases.json"
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
        snapshot_cases=_snapshot_cases(profiler),
        snapshot_suite_path=snapshot_suite_path,
    )

    assert rebuilt == stored
    assert rebuilt["result"] == "pass"

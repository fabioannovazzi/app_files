from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "reporting-engine"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reporting_engine_declares_profiler_and_schema_dependencies_as_core() -> None:
    core_requirements = (
        (PLUGIN_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    )
    render_requirements = (
        (PLUGIN_ROOT / "requirements-render.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert "openpyxl" in core_requirements
    assert "jsonschema>=4.23,<5" in core_requirements
    assert "openpyxl" not in render_requirements
    assert not any(value.startswith("jsonschema") for value in render_requirements)


def test_reporting_engine_catalog_summary_matches_packaged_manifest() -> None:
    contract = _load_module(
        "reporting_engine_contract_test",
        PLUGIN_ROOT / "scripts" / "reporting_contract.py",
    )
    manifest = json.loads(
        (PLUGIN_ROOT / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    summary = contract.summarize_contract(PLUGIN_ROOT / "catalog")

    assert summary["capability_count"] == len(manifest["capabilities"])
    assert summary["artifact_count"] == len(manifest["artifacts"])
    assert summary["artifact_count"] == 73
    assert summary["role_registry_count"] == len(
        manifest["role_registry"]["chart_roles"]
    )
    assert summary["profile_role_count"] == len(
        manifest["role_registry"]["profile_roles"]
    )
    assert summary["invocation_statuses"] == {"parameter_contract_ready": 48}
    assert "period-comparison" in summary["plugin_sources"]
    assert "mix-contribution-analysis" in summary["plugin_sources"]
    assert "reporting-engine.period_comparison" in summary["clara_adapter_ids"]
    assert "reporting-engine.mix" in summary["clara_adapter_ids"]
    assert "period-comparison" in summary["clara_component_names"]
    assert summary["adapter_registry"]["owner"] == "clara.reporting-engine"
    assert summary["adapter_registry"]["adapter_count"] == 9
    assert summary["adapter_registry"]["render_api_statuses"] == {
        "unified_attribute_table_adapter": 4,
        "unified_component_cli_adapter": 44,
    }
    assert summary["mechanical_acceptance"] == {
        "result": "pass",
        "selected_capability_count": 48,
        "counts": {"component_executed": 48},
        "manifest_digest_matches": True,
    }
    assert summary["semantic_layer"]["schema_version"] == "0.1"
    assert summary["semantic_layer"]["workflow_script"] == ("scripts/semantic_layer.py")
    assert summary["semantic_layer"]["reviewed_fixture"] == (
        "fixtures/semantic_layer/retail_monthly.semantic.json"
    )
    assert summary["semantic_layer"]["judgment_owner"] == "model_or_human_review"
    assert summary["semantic_layer"]["acceptance"] == {
        "result": "pass",
        "semantic_layer_id": "retail_monthly.reporting_semantics",
        "semantic_readiness": "ready_as_scoped_semantic_input",
        "analysis_validities": {
            "conditional": 0,
            "invalid": 1,
            "unknown": 0,
            "valid": 9,
        },
        "input_digests_match": True,
    }
    assert "semantic" in summary["boundary"]


def test_reporting_engine_catalog_keeps_gallery_artifact_manifest() -> None:
    selection_manifest = json.loads(
        (PLUGIN_ROOT / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    gallery_manifest = json.loads(
        (PLUGIN_ROOT / "catalog" / "png_gallery_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert selection_manifest["counts"]["artifacts"] == 73
    assert len(selection_manifest["artifacts"]) == 73
    assert len(gallery_manifest["items"]) == 73
    assert "/Users/" not in json.dumps(selection_manifest)
    assert "/Users/" not in json.dumps(gallery_manifest)
    assert (
        selection_manifest["capabilities"]["period_comparison.trend"]["example_count"]
        == 2
    )
    assert (
        selection_manifest["capabilities"]["period_comparison.trend"][
            "present_in_gallery_manifest"
        ]
        is True
    )
    assert (
        len(
            selection_manifest["capabilities"]["period_comparison.trend"][
                "normalized_invocation_contract"
            ]["artifact_invocation_contracts"]
        )
        == 2
    )


def test_reporting_engine_runtime_contract_reconstructs_every_invocation(
    tmp_path: Path,
) -> None:
    audit = _load_module(
        "reporting_engine_parameter_audit_test",
        ROOT / "scripts" / "audit_chart_plugin_parameter_contract.py",
    )

    payload = audit.audit_chart_plugin_parameter_contract(
        selection_manifest_path=PLUGIN_ROOT / "catalog" / "selection_manifest.json",
        output_json_path=tmp_path / "parameter_audit.json",
        output_md_path=tmp_path / "parameter_audit.md",
    )

    assert payload["counts"] == {
        "capabilities": 48,
        "parameter_contract_ready": 48,
        "parameter_contract_gap": 0,
        "missing_artifact_evidence": 0,
    }
    assert payload["missing_role_counts"] == {}
    assert payload["mapping_kind_counts"]["runtime_contract"] == 32
    optional_panel = payload["normalized_invocation_contracts"]["scatter.bubble"][
        "optional_role_contracts"
    ]
    assert any(role["role"] == "optional_panel" for role in optional_panel)


def test_reporting_engine_adapter_registry_resolves_capability_contract() -> None:
    adapters = _load_module(
        "reporting_engine_adapters_test",
        PLUGIN_ROOT / "scripts" / "reporting_adapters.py",
    )

    summary = adapters.summarize_adapters(PLUGIN_ROOT)
    resolved = adapters.resolve_capability_adapter(
        "period_comparison.trend", root=PLUGIN_ROOT
    )
    plan = adapters.prepare_invocation_plan(
        "period_comparison.trend",
        dataset_profile={
            "role_candidates": {
                "period_axis": ["Month"],
                "comparison_metric": ["Sales"],
                "dimension_member": ["Brand"],
            }
        },
        root=PLUGIN_ROOT,
    )
    bubble_plan = adapters.prepare_invocation_plan(
        "scatter.bubble",
        dataset_profile={
            "roles": {
                "period": ["Date"],
                "metric": ["Sales", "MarginPercent", "Units"],
                "dimension": ["Brand"],
                "identifier": [],
            },
            "metric_classes": {
                "additive_value": ["Sales"],
                "rate": ["MarginPercent"],
                "additive_volume": ["Units"],
            },
            "columns": {
                "Date": {"role": "period"},
                "Sales": {"role": "metric", "metric_class": "additive_value"},
                "MarginPercent": {"role": "metric", "metric_class": "rate"},
                "Units": {"role": "metric", "metric_class": "additive_volume"},
                "Brand": {"role": "dimension"},
            },
            "role_candidates": {
                "period_axis": ["Date"],
                "period_filter": ["Date"],
                "x_metric": ["Sales"],
                "y_metric": ["MarginPercent"],
                "size_metric": ["Units"],
                "dimension_member": ["Brand"],
            },
        },
        root=PLUGIN_ROOT,
    )

    assert summary["adapter_count"] == 9
    assert summary["missing_registry_sources"] == []
    assert summary["capability_counts_by_legacy_source"]["period-comparison"] == 8
    assert resolved["adapter_id"] == "reporting-engine.period_comparison"
    assert resolved["component_name"] == "period-comparison"
    assert resolved["component_exists"] is True
    assert resolved["manifest_adapter_matches_registry"] is True
    assert plan["adapter_id"] == "reporting-engine.period_comparison"
    assert plan["legacy_plugin_source"] == "period-comparison"
    assert plan["dataset_checked"] is True
    assert plan["period_scope"]["role"] == "axis"
    assert bubble_plan["period_scope"]["role"] == "filter"
    assert bubble_plan["period_scope"]["scope_required_for_render"] is True
    assert {role["dataset_match_status"] for role in plan["required_roles"]} <= {
        "candidate_available",
        "missing_candidate",
    }
    bubble_period_role = next(
        role
        for role in bubble_plan["optional_roles"]
        if role["role"] == "period_filter"
    )
    assert bubble_period_role["required"] is False
    assert bubble_period_role["dataset_match_status"] == "candidate_available"
    assert bubble_period_role["scope_binding"]["status"] == "supported"
    assert "semantically valid analysis" in plan["boundary"]


def test_every_capability_has_clara_adapter_annotation() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    registry = json.loads(
        (PLUGIN_ROOT / "catalog" / "adapter_registry.json").read_text(encoding="utf-8")
    )
    adapters = registry["adapters"]

    for capability_id, capability in manifest["capabilities"].items():
        contract = capability["normalized_invocation_contract"]
        source = contract["plugin_sources"][0]
        clara_adapter = contract["clara_adapter"]

        assert clara_adapter["owner"] == "clara.reporting-engine", capability_id
        assert clara_adapter["legacy_plugin_source"] == source, capability_id
        assert clara_adapter["adapter_id"] == adapters[source]["adapter_id"]
        assert clara_adapter["component_name"] == adapters[source]["component_name"]
        assert clara_adapter["legacy_plugin_source_policy"] == "provenance_only"
        assert (
            clara_adapter["renderer"]
            == "scripts/render_capability.py:render_capability"
        )


def test_render_capability_builds_recipe_from_manifest_role_bindings(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_recipe_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="period_comparison.trend",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_axis": "Month",
            "comparison_metric": "Sales",
            "panel_dimension": "Brand",
        },
        artifact_mode="data_only",
        include_variants=True,
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    assert recipe_path == tmp_path / "render" / "render_request_recipe.json"
    assert audit["charts"] == [
        "year_over_year_line",
        "year_over_year_small_multiples",
    ]
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["source_file"] == str(tmp_path / "sales.csv")
    assert recipe["mappings"]["date_column"] == "Month"
    assert recipe["mappings"]["amount_column"] == "Sales"
    assert recipe["options"]["small_multiples_dimension"] == "Brand"
    assert recipe["options"]["small_multiples"] is True


def test_render_capability_ignores_variant_role_bindings_without_variants(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_non_variant_recipe_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="period_comparison.trend",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_axis": "Month",
            "comparison_metric": "Sales",
            "panel_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    assert recipe_path == tmp_path / "render" / "render_request_recipe.json"
    assert audit["charts"] == ["year_over_year_line"]
    assert audit["applied_roles"] == {
        "period_axis": ["mappings.date_column"],
        "comparison_metric": ["mappings.amount_column"],
    }
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["mappings"]["date_column"] == "Month"
    assert recipe["mappings"]["amount_column"] == "Sales"
    assert "small_multiples_dimension" not in recipe["options"]
    assert recipe["options"]["small_multiples"] is False


def test_render_capability_uses_base_distribution_chart_for_small_multiples(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_distribution_variant_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="distribution.boxplot",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_filter": "Date",
            "distribution_metric": "Sales",
            "panel_dimension": "Brand",
        },
        artifact_mode="data_only",
        include_variants=True,
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    assert recipe_path == tmp_path / "render" / "render_request_recipe.json"
    assert audit["charts"] == ["boxplot"]
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["options"]["charts"] == ["boxplot"]
    assert recipe["options"]["small_multiples"] is True
    assert recipe["mappings"]["small_multiples_dimension"] == "Brand"


def test_render_capability_marks_missing_required_period_scope_as_error(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_unscoped_bubble_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="scatter.bubble",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_filter": "Date",
            "x_metric": "Sales",
            "y_metric": "MarginPercent",
            "size_metric": "Units",
            "point_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["mappings"]["date_column"] == "Date"
    assert "period_type" not in recipe["options"]
    assert audit["period_scope"]["status"] == (
        "unscoped_filter_defaults_to_all_available_data"
    )
    assert audit["period_scope"]["severity"] == "error"


def test_render_capability_blocks_missing_required_period_scope(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_scope_preflight_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )
    request = renderer.RenderRequest(
        capability_id="scatter.bubble",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_filter": "Date",
            "x_metric": "Sales",
            "y_metric": "MarginPercent",
            "size_metric": "Units",
            "point_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    with pytest.raises(ValueError, match="bounded scope"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    assert calls == []


def test_render_capability_blocks_non_bounding_period_controls(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_non_bounding_scope_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )
    request = renderer.RenderRequest(
        capability_id="scatter.bubble",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_filter": {
                "date_column": "Date",
                "period_type": "calendar",
                "period_grain": "year",
            },
            "x_metric": "Sales",
            "y_metric": "MarginPercent",
            "size_metric": "Units",
            "point_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    with pytest.raises(ValueError, match="bounded scope"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    assert calls == []


def test_render_capability_blocks_missing_required_role_binding(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_role_preflight_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )
    request = renderer.RenderRequest(
        capability_id="period_comparison.trend",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_axis": {
                "date_column": "Month",
                "current_period_label": "2026",
                "previous_period_label": "2025",
            }
        },
        artifact_mode="data_only",
    )

    with pytest.raises(ValueError, match="comparison_metric"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    assert calls == []


def test_render_capability_blocks_scalar_compound_role_binding(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_compound_role_preflight_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )
    request = renderer.RenderRequest(
        capability_id="set_overlap.upset",
        input_file=tmp_path / "memberships.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "set_membership_fields": "Product",
            "period_filter": {
                "period_column": "Month",
                "selected_period": "2026-06",
            },
        },
        artifact_mode="data_only",
    )

    with pytest.raises(ValueError, match="set_membership_fields"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    assert calls == []


def test_render_capability_allows_unused_optional_period_filter(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_cross_sectional_bubble_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="scatter.bubble",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "x_metric": "Sales",
            "y_metric": "MarginPercent",
            "size_metric": "Units",
            "point_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert "date_column" not in recipe["mappings"]
    assert audit["period_scope"]["status"] == "optional_filter_not_used"
    assert audit["period_scope"]["severity"] == "none"


def test_render_capability_only_applies_runtime_supported_period_controls(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_set_overlap_scope_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="set_overlap.upset",
        input_file=tmp_path / "memberships.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "set_membership_fields": {
                "item_column": "Product",
                "set_column": "Retailer",
            },
            "period_filter": {
                "period_column": "Month",
                "selected_period": "2026-06",
                "period_type": "rolling",
            },
        },
        artifact_mode="data_only",
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["mappings"]["period_column"] == "Month"
    assert recipe["options"]["selected_period"] == "2026-06"
    assert "period_type" not in recipe["options"]
    assert audit["period_scope"]["scope_option_paths"] == ["options.selected_period"]


def test_render_proof_requires_the_selected_chart_artifact() -> None:
    renderer = _load_module(
        "reporting_engine_renderer_artifact_proof_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )

    missing = renderer.capability_render_proof(
        "set_overlap.upset_small_multiples",
        ["upset.html", "set_overlap_audit.json"],
        artifact_mode="data_and_render",
    )
    rendered = renderer.capability_render_proof(
        "set_overlap.upset_small_multiples",
        ["upset_small_multiples.html"],
        artifact_mode="data_and_render",
    )

    assert missing["status"] == "missing_expected_render"
    assert missing["missing_chart_tokens"] == ["upset_small_multiples"]
    assert rendered["status"] == "rendered"


def test_render_proof_resolves_root_cause_drilldown_from_role_binding() -> None:
    renderer = _load_module(
        "reporting_engine_renderer_dynamic_artifact_proof_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )

    proof = renderer.capability_render_proof(
        "variance.root_cause_exploded_bridge",
        [
            "root_cause_total_bridge.png",
            "root_cause_total_bridge_drilldown_row_2.png",
        ],
        artifact_mode="data_and_render",
        role_bindings={
            "drilldown_selection": {
                "root_cause_bridge_alternative_result": 4,
                "root_cause_bridge_drilldown_rows": [2],
            }
        },
    )

    assert proof["status"] == "rendered"
    assert proof["expected_chart_tokens"] == ["root_cause_total_bridge_drilldown_row_2"]


def test_render_capability_applies_structured_period_scope(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_scoped_bubble_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="scatter.bubble",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_filter": {
                "date_column": "Date",
                "period_type": "rolling",
                "period_grain": "month",
                "rolling_window_months": 12,
            },
            "x_metric": "Sales",
            "y_metric": "MarginPercent",
            "size_metric": "Units",
            "point_dimension": "Brand",
        },
        artifact_mode="data_only",
    )

    recipe_path, audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["mappings"]["date_column"] == "Date"
    assert recipe["options"]["period_type"] == "rolling"
    assert recipe["options"]["period_grain"] == "month"
    assert recipe["options"]["rolling_window_months"] == 12
    assert audit["period_scope"]["status"] == "explicit_scope"
    assert audit["period_scope"]["severity"] == "none"
    assert set(audit["period_scope"]["scope_option_paths"]) >= {
        "options.period_type",
        "options.period_grain",
        "options.rolling_window_months",
    }


def test_render_capability_preserves_fixed_capability_options(
    tmp_path: Path,
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_fixed_options_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    request = renderer.RenderRequest(
        capability_id="variance.scenario_bridge",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        options={"waterfall_chart": False},
        artifact_mode="data_only",
    )

    recipe_path, _audit = renderer.build_render_recipe(request, root=PLUGIN_ROOT)

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["options"]["waterfall_chart"] is True


def test_render_capability_dispatches_embedded_component_runner(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_dispatch_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> SimpleNamespace:
        calls.append((command, cwd, capture_output))
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "year_over_year_line_chart_data.csv").write_text(
            "month,value\n2026-01,10\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    request = renderer.RenderRequest(
        capability_id="period_comparison.trend",
        input_file=tmp_path / "sales.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "period_axis": {
                "date_column": "Month",
                "current_period_label": "2026",
                "previous_period_label": "2025",
            },
            "comparison_metric": "Sales",
        },
        artifact_mode="data_only",
    )

    manifest = renderer.render_capability(request, root=PLUGIN_ROOT)

    assert manifest["adapter_id"] == "reporting-engine.period_comparison"
    assert manifest["component_name"] == "period-comparison"
    assert manifest["runner"]["status"] == "ok"
    assert "render_manifest.json" in manifest["artifacts"]
    assert "year_over_year_line_chart_data.csv" in manifest["artifacts"]
    assert calls
    command, cwd, capture_output = calls[0]
    assert cwd == ROOT / "plugins" / "period-comparison"
    assert command[0] == sys.executable
    assert command[1].endswith("scripts/run_period_comparison.py")
    assert "--artifact-mode" in command
    assert "data_only" in command
    assert capture_output is True


def test_render_capability_fails_when_expected_render_is_missing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_proof_failure_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )

    def fake_run(
        _command: list[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
    ) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    request = renderer.RenderRequest(
        capability_id="set_overlap.upset",
        input_file=tmp_path / "memberships.csv",
        output_dir=tmp_path / "render",
        role_bindings={
            "set_membership_fields": {
                "item_column": "Product",
                "set_column": "Retailer",
            },
            "period_filter": {
                "period_column": "Month",
                "selected_period": "2026-06",
            },
        },
        artifact_mode="data_and_render",
    )

    with pytest.raises(RuntimeError, match="missing_expected_render"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    render_manifest = json.loads(
        (request.output_dir / "render_manifest.json").read_text(encoding="utf-8")
    )
    assert render_manifest["render_proof"]["status"] == "missing_expected_render"


def test_render_capability_does_not_accept_stale_expected_render(
    tmp_path: Path, monkeypatch: Any
) -> None:
    renderer = _load_module(
        "reporting_engine_renderer_stale_proof_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    output_dir = tmp_path / "render"
    output_dir.mkdir()
    (output_dir / "upset.html").write_text("stale", encoding="utf-8")
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        ),
    )
    request = renderer.RenderRequest(
        capability_id="set_overlap.upset",
        input_file=tmp_path / "memberships.csv",
        output_dir=output_dir,
        role_bindings={
            "set_membership_fields": {
                "item_column": "Product",
                "set_column": "Retailer",
            },
            "period_filter": {
                "period_column": "Month",
                "selected_period": "2026-06",
            },
        },
        artifact_mode="data_and_render",
    )

    with pytest.raises(RuntimeError, match="missing_expected_render"):
        renderer.render_capability(request, root=PLUGIN_ROOT)

    render_manifest = json.loads(
        (output_dir / "render_manifest.json").read_text(encoding="utf-8")
    )
    assert render_manifest["render_proof"]["status"] == "missing_expected_render"
    assert render_manifest["render_proof"]["rendered_artifacts"] == []


def test_render_capability_maps_all_chart_family_capabilities() -> None:
    renderer = _load_module(
        "reporting_engine_renderer_mapping_test",
        PLUGIN_ROOT / "scripts" / "render_capability.py",
    )
    manifest = json.loads(
        (PLUGIN_ROOT / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    chartless_prefixes = ("attributes.", "funnel.", "statement.", "variance.")
    chartless_capabilities = {
        "period_comparison.comparison_table",
        "period_comparison.time_series_table",
    }

    for capability_id in manifest["capabilities"]:
        if capability_id.startswith(chartless_prefixes) or (
            capability_id in chartless_capabilities
        ):
            continue
        assert renderer.capability_chart_options(capability_id), capability_id
    for capability_id in manifest["capabilities"]:
        if not capability_id.startswith("variance."):
            continue
        assert renderer.capability_option_overrides(capability_id), capability_id


def test_reporting_engine_profile_dataset_emits_chart_role_candidates(
    tmp_path: Path,
) -> None:
    profiler = _load_module(
        "reporting_engine_profile_test",
        PLUGIN_ROOT / "scripts" / "profile_dataset.py",
    )
    dataset = tmp_path / "sales.csv"
    with dataset.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["month", "brand", "sku", "sales", "share"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "month": "2026-01-01",
                    "brand": "Alpha",
                    "sku": "SKU-1",
                    "sales": "100",
                    "share": "0.4",
                },
                {
                    "month": "2026-02-01",
                    "brand": "Beta",
                    "sku": "SKU-2",
                    "sales": "120",
                    "share": "0.6",
                },
            ]
        )

    profile = profiler.profile_dataset(dataset, dataset_id="tiny_sales")

    assert profile["schema_version"] == "0.4"
    assert profile["dataset_id"] == "tiny_sales"
    assert profile["columns"]["month"]["role"] == "period"
    assert profile["columns"]["sales"]["role"] == "metric"
    assert profile["columns"]["sales"]["role_confidence"] == "high"
    assert profile["metric_classes"]["additive_value"] == ["sales"]
    assert profile["metric_classes"]["share"] == ["share"]
    assert "month" in profile["role_candidate_columns"]["period_axis"]
    assert profile["columns"]["month"]["ordered_values"] == [
        "2026-01-01",
        "2026-02-01",
    ]
    assert "sales" in profile["role_candidate_columns"]["comparison_metric"]
    assert "brand" in profile["role_candidate_columns"]["panel_dimension"]
    assert "sku" in profile["role_candidate_columns"]["identifier"]
    assert "mechanically available dataset roles" in profile["selector_boundary"]


def test_mechanical_acceptance_binds_root_cause_sequence_and_drilldown_path() -> None:
    acceptance = _load_module(
        "reporting_engine_mechanical_acceptance_binding_test",
        PLUGIN_ROOT / "scripts" / "mechanical_acceptance.py",
    )
    fixture = (
        PLUGIN_ROOT / "fixtures" / "mechanical_acceptance" / "variance_root_cause.csv"
    )
    profile = acceptance.profile_dataset(fixture, dataset_id="variance_root_cause")
    manifest = acceptance.load_manifest(PLUGIN_ROOT)
    compatibility_payload = acceptance.check_profile_compatibility(manifest, profile)
    capability = manifest["capabilities"]["variance.root_cause_exploded_bridge"]
    compatibility = next(
        result
        for result in compatibility_payload["results"]
        if result["capability_id"] == "variance.root_cause_exploded_bridge"
    )

    bindings, missing = acceptance.build_role_bindings(
        capability,
        profile,
        compatibility,
    )

    assert missing == []
    assert bindings["drilldown_selection"] == {
        "root_cause_bridge_alternative_result": 3,
        "root_cause_bridge_drilldown_rows": [1],
    }
    assert len(bindings["root_cause_driver_sequence"]["dimensions"]) >= 2


def test_packaged_mechanical_acceptance_summary_covers_every_capability() -> None:
    summary_path = PLUGIN_ROOT / "catalog" / "mechanical_acceptance_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest_path = PLUGIN_ROOT / "catalog" / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert summary["result"] == "pass"
    assert summary["selected_capability_count"] == 48
    assert summary["counts"] == {"component_executed": 48}
    assert len(summary["records"]) == 48
    assert {record["capability_id"] for record in summary["records"]} == set(
        manifest["capabilities"]
    )
    assert {record["acceptance_status"] for record in summary["records"]} == {
        "component_executed"
    }
    assert {record["render_proof_status"] for record in summary["records"]} == {
        "rendered"
    }
    assert summary["manifest"] == {
        "file_name": manifest_path.name,
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    assert "/Users/" not in summary_path.read_text(encoding="utf-8")


def test_reporting_engine_cli_writes_dataset_profile(tmp_path: Path) -> None:
    profiler = _load_module(
        "reporting_engine_profile_cli_test",
        PLUGIN_ROOT / "scripts" / "profile_dataset.py",
    )
    dataset = tmp_path / "sales.csv"
    dataset.write_text("month,category,sales\n2026-01-01,A,10\n", encoding="utf-8")
    output = tmp_path / "profile.json"

    result = profiler.main(
        [str(dataset), "--dataset-id", "cli_sales", "--output", str(output)]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["dataset_id"] == "cli_sales"
    assert payload["role_candidate_columns"]["period_axis"] == ["month"]

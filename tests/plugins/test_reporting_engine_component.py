from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "reporting-engine"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    assert "semantic" in summary["boundary"]


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
    assert {role["dataset_match_status"] for role in plan["required_roles"]} <= {
        "candidate_available",
        "missing_candidate",
    }
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
    assert "small_multiples" not in recipe["options"]


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
        role_bindings={"period_axis": "Month", "comparison_metric": "Sales"},
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

    assert profile["schema_version"] == "0.2"
    assert profile["dataset_id"] == "tiny_sales"
    assert profile["columns"]["month"]["role"] == "period"
    assert profile["columns"]["sales"]["role"] == "metric"
    assert profile["columns"]["sales"]["role_confidence"] == "high"
    assert profile["metric_classes"]["additive_value"] == ["sales"]
    assert profile["metric_classes"]["rate_or_share"] == ["share"]
    assert "month" in profile["role_candidates"]["period_axis"]
    assert "sales" in profile["role_candidates"]["comparison_metric"]
    assert "brand" in profile["role_candidates"]["panel_dimension"]
    assert "sku" in profile["role_candidates"]["identifier"]
    assert "Mechanical dataset profile only" in profile["selector_boundary"]


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
    assert payload["role_candidates"]["period_axis"] == ["month"]

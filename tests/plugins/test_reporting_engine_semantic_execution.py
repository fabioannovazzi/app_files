from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2] / "plugins/clara/modules/reporting-engine"
FIXTURES = ROOT / "fixtures/semantic_layer"


@pytest.mark.parametrize("deliver", [False, True])
def test_execution_cli_reports_and_verifies_delivery(
    reviewed: tuple[Any, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    deliver: bool,
) -> None:
    from run_capability import main, verify_reviewed_execution

    _, args = reviewed
    output = tmp_path / "cli-render"
    delivery = tmp_path / "cli-delivery"
    argv = [
        "run_capability.py",
        str(args["dataset_path"]),
        "--output-dir",
        str(output),
        "--layer",
        str(args["layer_path"]),
        "--profile",
        str(args["profile_path"]),
        "--acceptance",
        str(args["acceptance_path"]),
        "--source",
        str(args["source_paths"][0]),
        "--analysis-id",
        args["analysis_id"],
        "--capability-id",
        args["capability_id"],
        "--artifact-mode",
        "data_only",
    ]
    if deliver:
        argv.extend(["--delivery-dir", str(delivery)])
    monkeypatch.setattr(sys, "argv", argv)

    exit_code = main()

    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["delivery_required"] is (not deliver)
    assert result["verified_delivery_dir"] == (str(delivery) if deliver else None)
    assert (delivery / "reporting_delivery.json").exists() is deliver
    assert (
        verify_reviewed_execution(delivery if deliver else output)["publication"][
            "identity_verified"
        ]
        is True
    )


def test_exported_reporting_bundle_verifies_after_move_and_originals_removed(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path
) -> None:
    from reporting_delivery import export_reviewed_execution
    from run_capability import run_reviewed_capability, verify_reviewed_execution

    _, args = reviewed
    output = tmp_path / "original-render"
    run_reviewed_capability(**args, output_dir=output, artifact_mode="data_and_render")
    original_receipt = (output / "reviewed_execution.json").read_bytes()
    destination = tmp_path / "delivery"

    export_reviewed_execution(output, destination)

    moved = tmp_path / "recipient" / "moved-bundle"
    moved.parent.mkdir()
    destination.rename(moved)
    shutil.rmtree(output)
    for key in ("dataset_path", "layer_path", "profile_path", "acceptance_path"):
        args[key].unlink()
    args["source_paths"][0].unlink()
    assert (moved / "reviewed_execution.json").read_bytes() == original_receipt
    assert verify_reviewed_execution(moved)["publication"]["identity_verified"] is True
    manifest = json.loads((moved / "render_manifest.json").read_text())
    assert manifest["render_proof"]["status"] == "rendered"


def test_reporting_export_preserves_existing_delivery(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path
) -> None:
    from reporting_delivery import export_reviewed_execution
    from run_capability import run_reviewed_capability

    _, args = reviewed
    output = tmp_path / "original-render"
    run_reviewed_capability(**args, output_dir=output, artifact_mode="data_only")
    destination = tmp_path / "delivery"
    destination.mkdir()
    existing = destination / "report.md"
    existing.write_text("Reviewed prior delivery")

    with pytest.raises(ValueError, match="already exists"):
        export_reviewed_execution(output, destination)

    assert existing.read_text() == "Reviewed prior delivery"


@pytest.mark.parametrize("damage", ["input", "output", "generation", "escape"])
def test_exported_reporting_bundle_rejects_missing_or_modified_evidence(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path, damage: str
) -> None:
    from reporting_delivery import export_reviewed_execution
    from run_capability import run_reviewed_capability, verify_reviewed_execution

    _, args = reviewed
    output = tmp_path / "original-render"
    run_reviewed_capability(**args, output_dir=output, artifact_mode="data_only")
    destination = tmp_path / "delivery"
    descriptor = export_reviewed_execution(output, destination)
    targets = {
        "input": destination / descriptor["context_inputs"]["dataset_path"],
        "output": destination / "mix_contribution_summary.csv",
    }
    if damage in targets:
        targets[damage].write_text("changed")
    elif damage == "generation":
        shutil.rmtree(destination / ".reporting-generations")
    else:
        descriptor["context_inputs"]["dataset_path"] = "../outside.csv"
        (destination / "reporting_delivery.json").write_text(json.dumps(descriptor))

    with pytest.raises((ValueError, FileNotFoundError)):
        verify_reviewed_execution(destination)


@pytest.fixture
def nonfinancial_reviewed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Bind the authored duration-only fixture to its exact current source files."""
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import profile_dataset
    import semantic_layer

    fixture_root = Path(__file__).resolve().parents[1] / "fixtures/clara_response_times"
    for name in ("response_times.csv", "source.md", "semantic.json"):
        (tmp_path / name).write_bytes((fixture_root / name).read_bytes())
    dataset = tmp_path / "response_times.csv"
    layer = tmp_path / "semantic.json"
    profile = profile_dataset.profile_dataset(dataset, dataset_id="response_times")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    acceptance = semantic_layer.build_semantic_acceptance_summary(
        profile,
        json.loads(layer.read_text()),
        json.loads(semantic_layer.DEFAULT_MANIFEST.read_text()),
        dataset_path=dataset,
        layer_path=layer,
        manifest_path=semantic_layer.DEFAULT_MANIFEST,
        schema_path=semantic_layer.DEFAULT_SEMANTIC_SCHEMA,
        source_paths=[tmp_path / "source.md"],
    )
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_text(json.dumps(acceptance))
    return dict(
        dataset_path=dataset,
        layer_path=layer,
        profile_path=profile_path,
        acceptance_path=acceptance_path,
        source_paths=[tmp_path / "source.md"],
        analysis_id="analysis.response_time_distribution",
        capability_id="distribution.histogram",
    )


def test_reviewed_nonfinancial_distribution_preserves_all_observations_and_units(
    nonfinancial_reviewed: dict[str, Any], tmp_path: Path
) -> None:
    import polars as pl
    from run_capability import run_reviewed_capability, verify_reviewed_execution

    output = tmp_path / "output"

    result = run_reviewed_capability(
        **nonfinancial_reviewed, output_dir=output, artifact_mode="data_only"
    )

    assert result["status"] == "reviewed_execution_completed"
    assert result["role_bindings"] == {"distribution_metric": "LatencyMs"}
    assert result["metric_contracts"]["distribution_metric"]["unit"] == {
        "kind": "duration",
        "currency": None,
        "symbol": "ms",
    }
    assert result["resolved_scope"] == {
        "scope_type": "all_available",
        "period_column": None,
        "windows": [],
    }
    assert pl.read_csv(output / "histogram_chart_data.csv").get_column(
        "LatencyMs"
    ).to_list() == [25.0, 50.0, 75.0, 100.0, 125.0]
    assert verify_reviewed_execution(output)["status"] == "reviewed_execution_completed"
    assert pl.read_csv(output / "histogram_chart_data.csv").get_column(
        "Period"
    ).unique().to_list() == ["ALL"]
    assert (
        "No time window is inferred"
        in (output / "distribution_client_report.md").read_text()
    )


@pytest.mark.parametrize(
    "rule_type", ["current_ytd", "caller_bounded", "current_vs_prior_year"]
)
def test_period_free_scope_cannot_claim_calendar_or_comparison_rules(
    nonfinancial_reviewed: dict[str, Any], rule_type: str
) -> None:
    import semantic_layer

    layer = json.loads(nonfinancial_reviewed["layer_path"].read_text())
    layer["period_rules"][0]["rule_type"] = rule_type
    profile = json.loads(nonfinancial_reviewed["profile_path"].read_text())

    result = semantic_layer.validate_semantic_layer(
        layer, profile, json.loads(semantic_layer.DEFAULT_MANIFEST.read_text())
    )

    assert result["status"] == "contract_invalid"
    assert "unknown_period" in {issue["code"] for issue in result["errors"]}


@pytest.fixture
def reviewed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, dict[str, Any]]:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import profile_dataset
    import semantic_layer

    spec = importlib.util.spec_from_file_location(
        "semantic_execution_test", ROOT / "scripts/semantic_execution.py"
    )
    assert spec and spec.loader
    execution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(execution)
    dataset = tmp_path / "dataset.csv"
    dataset.write_bytes((FIXTURES / "retail_monthly.csv").read_bytes())
    layer_path = tmp_path / "semantic.json"
    layer_path.write_bytes((FIXTURES / "retail_monthly.semantic.json").read_bytes())
    source = tmp_path / "source.md"
    source.write_bytes((FIXTURES / "retail_monthly_source_notes.md").read_bytes())
    profile = profile_dataset.profile_dataset(dataset, dataset_id="retail_monthly")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    acceptance = semantic_layer.build_semantic_acceptance_summary(
        profile,
        json.loads(layer_path.read_text()),
        json.loads(semantic_layer.DEFAULT_MANIFEST.read_text()),
        dataset_path=dataset,
        layer_path=layer_path,
        manifest_path=semantic_layer.DEFAULT_MANIFEST,
        schema_path=semantic_layer.DEFAULT_SEMANTIC_SCHEMA,
        source_paths=[source],
    )
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_text(json.dumps(acceptance))
    return execution, dict(
        dataset_path=dataset,
        layer_path=layer_path,
        profile_path=profile_path,
        acceptance_path=acceptance_path,
        source_paths=[source],
        analysis_id="analysis.monthly_sales_trajectory",
        capability_id="mix.timeline",
    )


def test_verified_context_carries_exact_semantic_version_and_policy(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    execution, args = reviewed

    result = execution.verify_execution_context(**args)

    assert result["status"] == "reviewed_input_identity_verified"
    assert (
        result["policy"]["role_bindings"]["primary_metric"]["concept_id"]
        == "metric.sales"
    )
    assert result["parser_settings"] == {"sheet_name": None, "csv_options": None}


@pytest.mark.parametrize(
    "changed", ["dataset_path", "layer_path", "profile_path", "source"]
)
def test_changed_semantic_evidence_is_rejected(
    reviewed: tuple[Any, dict[str, Any]], changed: str
) -> None:
    execution, args = reviewed
    path = args["source_paths"][0] if changed == "source" else args[changed]
    if changed == "profile_path":
        payload = json.loads(path.read_text())
        payload["dataset_id"] = "different"
        path.write_text(json.dumps(payload))
    else:
        path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(
        ValueError, match="stale|changed|current parsed snapshot|does not bind"
    ):
        execution.verify_execution_context(**args)


def test_unreviewed_capability_cannot_use_a_valid_acceptance_receipt(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    execution, args = reviewed
    args["capability_id"] = "set_overlap.upset"

    with pytest.raises(ValueError, match="reviewed analysis policy"):
        execution.verify_execution_context(**args)


def test_compiler_derives_columns_currency_and_monthly_scope(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    from compile_execution import compile_reviewed_execution

    _, args = reviewed

    result = compile_reviewed_execution(**args)

    assert result["role_bindings"]["primary_metric"] == "Sales"
    assert result["role_bindings"]["period_axis"]["column"] == "Date"
    assert result["currency"] == "USD"
    assert result["options"]["period_grain"] == "month"
    assert result["resolved_scope"]["scope_type"] == "all_available"
    assert (
        result["metric_contracts"]["primary_metric"]["aggregation"]["default"] == "sum"
    )


def test_period_free_scope_cannot_replace_a_required_time_axis(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    import semantic_layer

    _, args = reviewed
    layer = json.loads(args["layer_path"].read_text())
    rule = next(
        item for item in layer["period_rules"] if item["rule_type"] == "all_available"
    )
    rule.update(period_id=None, parameters={})

    result = semantic_layer.validate_semantic_layer(
        layer,
        json.loads(args["profile_path"].read_text()),
        json.loads(semantic_layer.DEFAULT_MANIFEST.read_text()),
    )

    policy = next(
        item
        for item in result["policy_results"]
        if item["analysis_id"] == "analysis.monthly_sales_trajectory"
    )
    assert policy["usable_as_semantic_input"] is False


def test_reviewed_rate_is_not_summed_by_grouped_adapter(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    from compile_execution import compile_reviewed_execution

    _, args = reviewed
    args.update(
        analysis_id="analysis.brand_sales_margin_relationship",
        capability_id="scatter.scatter",
    )

    with pytest.raises(ValueError, match="aggregation preparation: weighted_mean"):
        compile_reviewed_execution(**args)


def test_observation_distribution_preserves_rate_unit_without_currency(
    reviewed: tuple[Any, dict[str, Any]],
) -> None:
    from compile_execution import compile_reviewed_execution

    _, args = reviewed
    args.update(
        analysis_id="analysis.margin_rate_distribution",
        capability_id="distribution.histogram",
    )

    result = compile_reviewed_execution(**args)

    assert result["currency"] is None
    assert result["metric_contracts"]["distribution_metric"]["unit"]["symbol"] == "%"


def test_reviewed_monthly_execution_keeps_both_years_in_actual_component_output(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path
) -> None:
    from run_capability import run_reviewed_capability

    _, args = reviewed
    output = tmp_path / "render"

    result = run_reviewed_capability(
        **args, output_dir=output, artifact_mode="data_only"
    )

    chart_context = json.loads((output / "line_chart_context.json").read_text())
    assert result["status"] == "reviewed_execution_completed"
    assert chart_context["selected_periods"] == ["’25-01", "’25-02", "’26-01", "’26-02"]
    assert result["metric_contracts"]["primary_metric"]["unit"]["currency"] == "USD"
    assert result["render_manifest_sha256"]


def test_failed_reviewed_attempt_invalidates_previous_receipt(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path
) -> None:
    from run_capability import run_reviewed_capability

    _, args = reviewed
    output = tmp_path / "output"
    output.mkdir()
    receipt = output / "reviewed_execution.json"
    receipt.write_text(json.dumps({"status": "reviewed_execution_completed"}))
    args["source_paths"][0].write_text("Changed evidence")

    with pytest.raises(ValueError, match="missing or changed"):
        run_reviewed_capability(**args, output_dir=output, artifact_mode="data_only")

    assert json.loads(receipt.read_text())["status"] == "failed_or_interrupted"


@pytest.mark.parametrize("changed", ["rendered_table", "semantic_source"])
def test_evidence_handoff_rejects_changes_after_execution(
    reviewed: tuple[Any, dict[str, Any]], tmp_path: Path, changed: str
) -> None:
    from run_capability import run_reviewed_capability, verify_reviewed_execution

    _, args = reviewed
    output = tmp_path / "output"
    run_reviewed_capability(**args, output_dir=output, artifact_mode="data_only")
    target = (
        output / "mix_contribution_summary.csv"
        if changed == "rendered_table"
        else args["source_paths"][0]
    )
    target.write_text("Changed after execution")

    with pytest.raises(ValueError, match="changed"):
        verify_reviewed_execution(output)


def test_compiler_rejects_sum_explicitly_forbidden_by_metric(
    reviewed: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import compile_execution

    execution, args = reviewed
    context = execution.verify_execution_context(**args)
    metric = next(
        item for item in context["metrics"] if item["metric_id"] == "metric.sales"
    )
    metric["aggregation"]["forbidden"] = ["sum"]
    monkeypatch.setattr(
        compile_execution, "verify_execution_context", lambda *a, **kw: context
    )

    with pytest.raises(ValueError, match="aggregation preparation"):
        compile_execution.compile_reviewed_execution(**args)


@pytest.mark.parametrize(
    ("windows", "message"),
    [
        (
            [
                {"role": "current", "start": "2026-02-01", "end": "2026-02-28"},
                {"role": "baseline", "start": "2026-01-01", "end": "2026-01-31"},
            ],
            "Same-year",
        ),
        (
            [
                {"role": "current", "start": "2026-01-01", "end": "2026-02-28"},
                {"role": "baseline", "start": "2026-01-01", "end": "2026-01-31"},
            ],
            "Overlapping",
        ),
        (
            [
                {"role": "current", "start": "2026-02-01", "end": "2026-02-28"},
                {"role": "current", "start": "2025-01-01", "end": "2025-01-31"},
            ],
            "current and baseline",
        ),
    ],
)
def test_compiler_rejects_comparison_windows_adapter_cannot_distinguish(
    reviewed: tuple[Any, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    windows: list[dict[str, str]],
    message: str,
) -> None:
    import compile_execution

    execution, args = reviewed
    context = execution.verify_execution_context(**args)
    rule_id = context["policy"]["period_rule_id"]
    resolution = next(
        item
        for item in context["snapshot_attachment"]["compatibility"][
            "period_resolution"
        ]["results"]
        if item["period_rule_id"] == rule_id
    )
    resolution["resolved_scope"]["windows"] = windows
    monkeypatch.setattr(
        compile_execution, "verify_execution_context", lambda *a, **kw: context
    )

    with pytest.raises(ValueError, match=message):
        compile_execution.compile_reviewed_execution(**args)

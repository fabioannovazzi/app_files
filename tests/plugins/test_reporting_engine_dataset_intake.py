from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from openpyxl import Workbook

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


def _intake_module() -> Any:
    return _load_module(
        "reporting_engine_dataset_intake_test",
        PLUGIN_ROOT / "scripts" / "dataset_intake.py",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("suffix", "expected_format"),
    (
        (".csv", "csv"),
        (".xlsx", "xlsx"),
        (".parquet", "parquet"),
    ),
)
def test_first_upload_profiles_each_supported_dataset_format(
    tmp_path: Path,
    suffix: str,
    expected_format: str,
) -> None:
    intake = _intake_module()
    dataset = tmp_path / f"business_metrics{suffix}"
    rows = {
        "Month": ["2026-01-01", "2026-02-01"],
        "Sales": [100, 120],
        "Discount": [5, 6],
        "COGS": [60, 72],
    }
    if suffix == ".csv":
        pl.DataFrame(rows).write_csv(dataset)
    elif suffix == ".xlsx":
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(list(rows))
        for values in zip(*rows.values(), strict=True):
            worksheet.append(list(values))
        workbook.save(dataset)
    else:
        pl.DataFrame(rows).write_parquet(dataset)

    receipt = intake.run_dataset_intake(
        dataset,
        dataset_contract_id=f"business_metrics_{expected_format}",
        output_dir=tmp_path / f"intake_{expected_format}",
    )

    profile = _read_json(
        tmp_path / f"intake_{expected_format}" / "dataset_profile.json"
    )
    assert receipt["status"] == "review_required"
    assert profile["source"]["format"] == expected_format


def test_first_upload_never_auto_maps_literal_business_metric_headers(
    tmp_path: Path,
) -> None:
    intake = _intake_module()
    dataset = tmp_path / "literal_headers.csv"
    dataset.write_text(
        "Month,Sales,Discount,COGS\n" "2026-01-01,100,5,60\n" "2026-02-01,120,6,72\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "intake"

    receipt = intake.run_dataset_intake(
        dataset,
        dataset_contract_id="literal_business_metrics",
        output_dir=output_dir,
    )

    assert receipt["status"] == "review_required"
    assert {path.name for path in output_dir.iterdir() if path.is_file()} >= {
        "dataset_profile.json",
        "semantic_layer.draft.json",
        "semantic_authoring_context.json",
        "dataset_intake.json",
    }
    layer = _read_json(output_dir / "semantic_layer.draft.json")
    assert set(layer["business_metric_mappings"]) == {"sales", "discount", "cogs"}
    assert all(
        mapping["state"] == "unknown"
        and mapping["metric_id"] is None
        and mapping["candidate_metric_ids"] == []
        for mapping in layer["business_metric_mappings"].values()
    )
    assert {
        metric["binding"]["column"]
        for metric in layer["metrics"]
        if metric["binding"]["binding_type"] == "column"
    } >= {"Sales", "Discount", "COGS"}
    assert _read_json(output_dir / "dataset_intake.json") == receipt


def test_first_upload_surfaces_ambiguous_metric_candidates_without_choosing(
    tmp_path: Path,
) -> None:
    intake = _intake_module()
    dataset = tmp_path / "ambiguous_sales.csv"
    dataset.write_text(
        "Month,Gross Sales,Net Sales,Discount Amount,Cost of Sales\n"
        "2026-01-01,120,100,20,60\n"
        "2026-02-01,150,125,25,75\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "intake"

    receipt = intake.run_dataset_intake(
        dataset,
        dataset_contract_id="ambiguous_business_metrics",
        output_dir=output_dir,
    )

    context = _read_json(output_dir / "semantic_authoring_context.json")
    review = context["business_metric_mapping_review"]
    candidate_ids = {
        candidate["metric_id"] for candidate in review["metric_candidates"]
    }
    assert receipt["status"] == "review_required"
    assert set(review["role_guidance"]) == {"sales", "discount", "cogs"}
    assert {"metric.gross_sales", "metric.net_sales"} <= candidate_ids
    assert all(
        mapping["state"] == "unknown" for mapping in review["current_mappings"].values()
    )


def test_reviewed_business_metric_mapping_is_reused_on_later_snapshot(
    tmp_path: Path,
) -> None:
    intake = _intake_module()
    reviewed_layer_path = FIXTURE_ROOT / "retail_monthly.semantic.json"
    original_layer_bytes = reviewed_layer_path.read_bytes()
    reviewed_layer = _read_json(reviewed_layer_path)
    output_dir = tmp_path / "refresh"

    receipt = intake.run_dataset_intake(
        FIXTURE_ROOT / "retail_monthly_refresh.csv",
        dataset_contract_id="retail_monthly",
        output_dir=output_dir,
        semantic_layer_path=reviewed_layer_path,
    )

    attachment = _read_json(output_dir / "snapshot_attachment.json")
    context = _read_json(output_dir / "semantic_authoring_context.json")
    assert receipt["status"] == "mapping_reused"
    assert attachment["attachment_status"] == "attached"
    assert attachment["semantic_version"] == reviewed_layer["semantic_version"] == 1
    assert (
        context["semantic_layer_draft"]["business_metric_mappings"]
        == reviewed_layer["business_metric_mappings"]
    )
    assert context["business_metric_mapping_review"]["current_mappings"] == (
        reviewed_layer["business_metric_mappings"]
    )
    assert reviewed_layer_path.read_bytes() == original_layer_bytes


def test_cli_rejects_semantic_layer_from_another_dataset_contract(
    tmp_path: Path,
) -> None:
    intake = _intake_module()
    output_dir = tmp_path / "mismatch"

    return_code = intake.main(
        [
            str(FIXTURE_ROOT / "retail_monthly_refresh.csv"),
            "--dataset-contract-id",
            "another_retail_asset",
            "--output-dir",
            str(output_dir),
            "--semantic-layer",
            str(FIXTURE_ROOT / "retail_monthly.semantic.json"),
        ]
    )

    receipt = _read_json(output_dir / "dataset_intake.json")
    assert return_code == 1
    assert receipt["status"] == "rejected"
    assert receipt["dataset_contract_id"] == "another_retail_asset"
    assert receipt["semantic_layer_dataset_contract_id"] == "retail_monthly"


def test_intake_refuses_to_overwrite_existing_run_artifacts(tmp_path: Path) -> None:
    intake = _intake_module()
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    receipt_path = output_dir / "dataset_intake.json"
    original_content = '{"status":"keep"}\n'
    receipt_path.write_text(original_content, encoding="utf-8")

    with pytest.raises(FileExistsError, match="will not overwrite"):
        intake.run_dataset_intake(
            FIXTURE_ROOT / "retail_monthly.csv",
            dataset_contract_id="retail_monthly",
            output_dir=output_dir,
        )

    assert receipt_path.read_text(encoding="utf-8") == original_content

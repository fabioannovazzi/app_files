from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "previdenza-inps"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"


def _load_script(module_name: str) -> ModuleType:
    scripts_path = str(SCRIPTS_ROOT)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    path = SCRIPTS_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"previdenza_inps_ocr_confirmation_{module_name}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_inventory(
    output_dir: Path,
    *,
    extraction_method: str | None = "paddle_ocr",
    limitations: list[str] | None = None,
) -> Path:
    text = "Il rapporto decorre dal 1 gennaio 2021."
    fragment_path = output_dir / "extracted" / "DOC-001__page-1.txt"
    fragment_path.parent.mkdir(parents=True)
    fragment_path.write_text(f"{text}\n", encoding="utf-8")
    fragment: dict[str, Any] = {
        "evidence_id": "DOC-001#page-1",
        "document_id": "DOC-001",
        "locator": {"kind": "page", "value": 1},
        "text_path": fragment_path.relative_to(output_dir).as_posix(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "character_count": len(text),
        "limitations": limitations or [],
    }
    if extraction_method is not None:
        fragment["extraction_method"] = extraction_method
    inventory = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "documents": [{"document_id": "DOC-001"}],
        "evidence_fragments": [fragment],
    }
    path = output_dir / "file_inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    run_intake = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "status": "inventory_complete",
        "run_id": "previdenza-inps-ocr-test",
        "created_at": "2026-07-16T08:00:00+00:00",
        "completed_at": "2026-07-16T08:01:00+00:00",
        "reference_date": None,
        "output_dir": output_dir.resolve().as_posix(),
        "data_posture": {
            "local_only": True,
            "network_calls_by_scripts": False,
            "network_access_allowed_for_model_weights": False,
            "acquisition_channels_used": [],
            "external_connectors_used": [],
            "ocr": {
                "enabled": True,
                "engine": "paddleocr",
                "language": "it",
                "attempt_location": "local_process",
                "attempted_page_count": 1,
                "successful_page_count": 1,
                "case_content_network_transfer": False,
                "model_download_allowed": False,
                "model_network_used": False,
                "visual_confirmation_required": True,
            },
        },
    }
    (output_dir / "run_intake.json").write_text(
        json.dumps(run_intake), encoding="utf-8"
    )
    return path


def _valid_visual_confirmation() -> dict[str, Any]:
    return {
        "confirmed": True,
        "confirmed_by_id": "REV-001",
        "confirmed_by_role": "professional_reviewer",
        "recorded_at": "2026-07-16T09:00:00+02:00",
        "basis": "Quote checked directly against page 1 of the source image.",
    }


def _write_records(
    output_dir: Path,
    *,
    review_status: str = "confirmed",
    visual_confirmation: dict[str, Any] | None = None,
) -> Path:
    evidence: dict[str, Any] = {
        "document_id": "DOC-001",
        "locator": {"kind": "page", "value": 1},
        "quote": "decorre dal 1 gennaio 2021",
    }
    if visual_confirmation is not None:
        evidence["visual_confirmation"] = visual_confirmation
    gates = (
        "professional_question_confirmed",
        "framework_confirmed",
        "period_scope_confirmed",
        "ambiguous_terms_resolved",
    )
    records = {
        "case_id": "CASE-OCR-001",
        "language": "it",
        "professional_question": "Quale trattamento risulta documentato?",
        "material_decisions": {gate: True for gate in gates},
        "decision_log": [
            {
                "decision_id": f"DEC-{index:03d}",
                "gate": gate,
                "decision": True,
                "decided_by_id": "REV-001",
                "decided_by_role": "professional_reviewer",
                "recorded_at": "2026-07-16T09:00:00+02:00",
                "basis": "Explicit reviewer instruction for the synthetic OCR case.",
            }
            for index, gate in enumerate(gates, start=1)
        ],
        "facts": [
            {
                "fact_id": "F-001",
                "statement": "Il rapporto decorre dal 1 gennaio 2021.",
                "review_label": "Decorrenza del rapporto",
                "value": "2021-01-01",
                "value_type": "date",
                "evidence": [evidence],
                "review_status": review_status,
            }
        ],
        "timeline": [],
    }
    path = output_dir / "case_records_draft.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("extraction_method", "limitations"),
    [
        ("paddle_ocr", []),
        (
            "browser_visible_text",
            [],
        ),
        (None, ["ocr_text_requires_visual_confirmation"]),
        ("embedded_text", ["embedded_text_below_ocr_quality_threshold"]),
    ],
)
def test_confirmed_fact_requires_visual_confirmation_for_ocr_fragment(
    tmp_path: Path,
    extraction_method: str | None,
    limitations: list[str],
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    inventory_path = _write_inventory(
        output_dir,
        extraction_method=extraction_method,
        limitations=limitations,
    )
    records_path = _write_records(output_dir)
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(records_path, inventory_path, output_dir)

    assert audit["status"] == "schema_error"
    assert {issue["code"] for issue in audit["issues"]} >= {
        "missing_ocr_visual_confirmation"
    }


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("confirmed", False, "unconfirmed_ocr_visual_confirmation"),
        ("confirmed_by_id", "", "missing_ocr_visual_confirmation_actor_id"),
        ("confirmed_by_role", "model", "invalid_ocr_visual_confirmation_role"),
        (
            "recorded_at",
            "2026-07-16T09:00:00",
            "invalid_ocr_visual_confirmation_timestamp",
        ),
        ("basis", "", "missing_ocr_visual_confirmation_basis"),
    ],
)
def test_confirmed_ocr_fact_rejects_invalid_human_confirmation_fields(
    tmp_path: Path,
    field: str,
    value: Any,
    expected_code: str,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    inventory_path = _write_inventory(output_dir)
    confirmation = _valid_visual_confirmation()
    confirmation[field] = value
    records_path = _write_records(
        output_dir,
        visual_confirmation=confirmation,
    )
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(records_path, inventory_path, output_dir)

    assert audit["status"] == "schema_error"
    assert expected_code in {issue["code"] for issue in audit["issues"]}


@pytest.mark.parametrize("review_status", ["pending", "disputed"])
def test_unconfirmed_fact_may_cite_ocr_without_visual_confirmation(
    tmp_path: Path,
    review_status: str,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    inventory_path = _write_inventory(output_dir)
    records_path = _write_records(output_dir, review_status=review_status)
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(records_path, inventory_path, output_dir)

    assert audit["status"] == "passed"
    assert audit["error_count"] == 0
    assert {issue["code"] for issue in audit["issues"]} == {"fact_not_confirmed"}


@pytest.mark.parametrize("extraction_method", ["paddle_ocr", "browser_visible_text"])
def test_valid_human_confirmation_allows_confirmed_extracted_fact_and_is_auditable(
    tmp_path: Path, extraction_method: str
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    inventory_path = _write_inventory(output_dir, extraction_method=extraction_method)
    records_path = _write_records(
        output_dir,
        visual_confirmation=_valid_visual_confirmation(),
    )
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(records_path, inventory_path, output_dir)

    assert audit["status"] == "passed"
    with (output_dir / "evidence_matrix.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["extraction_method"] == extraction_method
    assert row["visual_confirmation_required"] == "True"
    assert row["visual_confirmation_confirmed"] == "True"
    assert row["visual_confirmation_by_role"] == "professional_reviewer"


def test_fact_rejects_fragment_with_stripped_extraction_provenance(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(mode=0o700)
    inventory_path = _write_inventory(
        output_dir,
        extraction_method=None,
        limitations=[],
    )
    records_path = _write_records(
        output_dir,
        visual_confirmation=_valid_visual_confirmation(),
    )
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(records_path, inventory_path, output_dir)

    assert audit["status"] == "schema_error"
    assert "missing_or_invalid_extraction_provenance" in {
        issue["code"] for issue in audit["issues"]
    }


def test_case_records_schema_declares_ocr_visual_confirmation_contract() -> None:
    schema = json.loads(
        (PLUGIN_ROOT / "schemas" / "case_records.schema.json").read_text(
            encoding="utf-8"
        )
    )
    confirmation = schema["properties"]["facts"]["items"]["properties"]["evidence"][
        "items"
    ]["properties"]["visual_confirmation"]

    assert set(confirmation["required"]) == {
        "confirmed",
        "confirmed_by_id",
        "confirmed_by_role",
        "recorded_at",
        "basis",
    }
    assert confirmation["properties"]["confirmed_by_role"]["enum"] == [
        "authorized_user",
        "professional_reviewer",
    ]

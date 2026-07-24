from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import jsonschema
import pytest
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"
SCHEMA_V1_PATH = CLARA_ROOT / "contracts" / "preparation_audit_envelope.v1.schema.json"
SCHEMA_V2_PATH = CLARA_ROOT / "contracts" / "preparation_audit_envelope.v2.schema.json"
VALIDATION_DATE = "2026-07-24"
PILOT_ID = "pilot-0123456789abcdef"
SOURCE_ID = "source-0123456789abcdef"
EXECUTION_ID = "execution-0123456789abcdef"


def _load_modules() -> tuple[Any, Any, Any, Any]:
    scripts_path = str(SCRIPTS_ROOT)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        intake = importlib.import_module("validate_real_data_pilot_intake")
        semantic = importlib.import_module("validate_real_data_pilot_semantic_review")
        producer = importlib.import_module("run_real_general_ledger_pilot")
        module_name = "clara_real_general_ledger_audit_adapter_test"
        spec = importlib.util.spec_from_file_location(
            module_name,
            SCRIPTS_ROOT / "build_real_general_ledger_audit_envelope.py",
        )
        assert spec and spec.loader
        adapter = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = adapter
        spec.loader.exec_module(adapter)
        return intake, semantic, producer, adapter
    finally:
        if inserted:
            sys.path.remove(scripts_path)


INTAKE, SEMANTIC, PRODUCER, ADAPTER = _load_modules()


@dataclass
class _Fixture:
    pilot_root: Path
    case_path: Path
    intake_contract_path: Path
    intake_receipt_path: Path
    semantic_review_path: Path
    semantic_receipt_path: Path
    semantic_decisions_path: Path
    source_path: Path
    parser_layout_path: Path
    output_directory: Path
    producer_status: str


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _column_name(column: int) -> str:
    result = ""
    value = column
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _worksheet_xml(rows: dict[int, dict[int, str]]) -> str:
    row_nodes: list[str] = []
    for row_number in sorted(rows):
        cell_nodes = []
        for column, value in sorted(rows[row_number].items()):
            reference = f"{_column_name(column)}{row_number}"
            cell_nodes.append(
                f'<c r="{reference}" t="inlineStr"><is>'
                f'<t xml:space="preserve">{escape(value)}</t>'
                "</is></c>"
            )
        row_nodes.append(f'<row r="{row_number}">{"".join(cell_nodes)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        f'{"".join(row_nodes)}'
        "</sheetData></worksheet>"
    )


def _write_xlsx(path: Path) -> None:
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships"><sheets>'
        '<sheet name="Reviewed journal" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/'
        '2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    rows = {
        1: {1: "Synthetic fixture metadata"},
        2: {1: "Data registrazione"},
        3: {3: "Riga", 6: "Conto", 10: "Dare", 14: "Avere"},
        4: {1: "2023-01-31 00:00:00"},
        5: {3: "1", 6: "10 / 1 / 1", 10: "100.25"},
        6: {3: "2", 6: "20 / 1 / 1", 14: "100.25"},
        7: {1: "28/02/2023\n3 30 / 1 / 1 60,00 D\n4 40 / 1 / 1 60,00 C"},
        8: {2: "Data registrazione"},
        9: {2: "Riga", 5: "Conto", 9: "Dare", 13: "Avere"},
        10: {2: "2023-03-31 00:00:00"},
        11: {2: "5", 5: "50 / 1 / 1", 9: "50"},
        12: {2: "6", 5: "60 / 1 / 1", 13: "50"},
        13: {1: "Totale generale 210,25 210,25"},
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows))


def _parser_layout() -> dict[str, Any]:
    return {
        "contract_version": "clara.commercial_general_journal_layout.v5",
        "review_status": "reviewed",
        "sheet_name": "Reviewed journal",
        "date_header_label": "Data registrazione",
        "line_header_label": "Riga",
        "account_header_label": "Conto",
        "debit_header_label": "Dare",
        "credit_header_label": "Avere",
        "page_layouts": [
            {
                "layout_id": "layout-a",
                "date_header_column": 1,
                "line_header_column": 3,
                "account_header_column": 6,
                "debit_header_column": 10,
                "credit_header_column": 14,
                "date_columns": [1, 2, 3, 4, 5],
                "line_id_columns": [1, 2, 3, 4, 5],
                "account_columns": [6],
                "debit_amount_columns": [9, 10, 11],
                "credit_amount_columns": [13, 14, 15],
                "physical_first_line_columns": [6],
            },
            {
                "layout_id": "layout-b",
                "date_header_column": 2,
                "line_header_column": 2,
                "account_header_column": 5,
                "debit_header_column": 9,
                "credit_header_column": 13,
                "date_columns": [1, 2, 3, 4],
                "line_id_columns": [1, 2, 3, 4],
                "account_columns": [5],
                "debit_amount_columns": [8, 9, 10],
                "credit_amount_columns": [12, 13, 14],
                "physical_first_line_columns": [5],
            },
        ],
        "date_patterns": [
            {
                "pattern": (r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}) 00:00:00$"),
                "strptime_format": "%Y-%m-%d",
            },
            {
                "pattern": (r"^(?P<date>[0-9]{2}/[0-9]{2}/[0-9]{4})(?:\s|$)"),
                "strptime_format": "%d/%m/%Y",
            },
        ],
        "account_code_pattern": r"[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+",
        "logical_candidate_pattern": (
            r"^\s*[1-9][0-9]*\s+[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+"
        ),
        "logical_movement_patterns": [
            {
                "layout_ids": ["layout-a", "layout-b"],
                "pattern": (
                    r"^\s*(?P<line_id>[1-9][0-9]*)\s+"
                    r"(?P<account>[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+)"
                    r"\s+(?:(?P<debit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})\s+D|"
                    r"(?P<credit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})\s+C)\s*$"
                ),
                "amount_format": "italian_grouped_2",
            }
        ],
        "physical_embedded_amount_patterns": [],
        "reviewed_amount_pairs": [],
        "reviewed_amountless_exclusions": [],
        "physical_amount_format": "canonical_dot",
        "amount_sign_policy": "nonnegative",
        "control_pattern": (
            r"^Totale generale\s+"
            r"(?P<debit>(?:0|[1-9][0-9]{0,2}"
            r"(?:\.[0-9]{3})*),[0-9]{2})\s+"
            r"(?P<credit>(?:0|[1-9][0-9]{0,2}"
            r"(?:\.[0-9]{3})*),[0-9]{2})$"
        ),
        "control_amount_format": "italian_grouped_2",
        "reviewed_final_debit_total": "210.25",
        "reviewed_final_credit_total": "210.25",
    }


def _intake_contract(source_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "clara.real_data_pilot_intake.v2",
        "pilot_id": PILOT_ID,
        "purpose": "local_due_diligence_preparation_evaluation",
        "source": {
            "source_id": SOURCE_ID,
            "data_kind": "commercial_general_ledger",
            "data_classification": "consented_real",
            "media_type": (
                "application/vnd.openxmlformats-officedocument." "spreadsheetml.sheet"
            ),
            "byte_count": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "authorization": {
            "status": "reviewed",
            "basis": "explicit_authorized_user_instruction",
            "authority_assertion": "authorizer_has_right_to_permit_this_use",
            "evidence_reference": "Synthetic unit-test declaration.",
            "authorizing_role": "unit-test fixture",
            "authorized_on": VALIDATION_DATE,
            "valid_from": VALIDATION_DATE,
            "valid_until": None,
            "purpose": "local_due_diligence_preparation_evaluation",
            "authorized_source_sha256": _sha256(source_path),
            "permitted_actions": [
                "codex_model_processing",
                "local_deterministic_processing",
            ],
            "prohibited_actions": [
                "commit_raw_or_row_level_data",
                "package_raw_or_row_level_data",
                "publish_raw_or_row_level_data",
            ],
            "terms_summary": (
                "Synthetic unit-test declaration; no real permission is claimed."
            ),
        },
        "privacy": {
            "codex_context_acknowledged": True,
            "automatic_anonymization_claimed": False,
            "clara_external_recipient_added": False,
            "raw_and_row_level_storage": "local_run_root_only",
            "repository_recording_policy": "sanitized_summary_and_receipts_only",
        },
        "deidentification_review": {
            "status": "not_applicable",
            "basis": "Unit-test contract uses no real data.",
            "reidentification_risk_review_status": "not_applicable",
        },
        "semantic_review_plan": {
            "status": "pending",
            "required_reviews": list(INTAKE.REQUIRED_SEMANTIC_REVIEWS),
            "automatic_mapping_allowed": False,
            "unresolved_blocking_issues_block_preparation": True,
        },
        "publication_status": "withheld",
        "report_ready": False,
    }


def _semantic_review(
    pilot_root: Path,
    *,
    intake_receipt_sha256: str,
    semantic_decisions_path: Path,
) -> dict[str, Any]:
    evidence_root = pilot_root / "evidence"
    evidence_root.mkdir()
    evidence_registry: dict[str, dict[str, Any]] = {}
    for position in range(1, 9):
        evidence_id = f"evidence-{position:02d}"
        evidence_path = evidence_root / f"{evidence_id}.txt"
        evidence_path.write_text(
            f"Synthetic evidence {position}.\n",
            encoding="utf-8",
        )
        evidence_registry[evidence_id] = {
            "path": evidence_path.relative_to(pilot_root).as_posix(),
            "media_type": "text/plain",
            "byte_count": evidence_path.stat().st_size,
            "sha256": _sha256(evidence_path),
        }
    evidence_registry["evidence-09"] = {
        "path": semantic_decisions_path.relative_to(pilot_root).as_posix(),
        "media_type": "application/json",
        "byte_count": semantic_decisions_path.stat().st_size,
        "sha256": _sha256(semantic_decisions_path),
    }
    required_reviews = [
        {
            "review_id": f"topic-review-{position:02d}",
            "topic": topic,
            "status": "reviewed",
            "decision": f"Synthetic decision {position}.",
            "basis": f"Synthetic basis {position}.",
            "evidence_refs": [f"evidence-{position:02d}", "evidence-09"],
        }
        for position, topic in enumerate(
            INTAKE.REQUIRED_SEMANTIC_REVIEWS,
            start=1,
        )
    ]
    return {
        "schema_version": "clara.real_data_pilot_semantic_review.v1",
        "pilot_id": PILOT_ID,
        "review_version": "review-fedcba9876543210",
        "review_status": "reviewed",
        "reviewed_on": VALIDATION_DATE,
        "reviewer_role": "synthetic unit-test reviewer",
        "intake_receipt_sha256": intake_receipt_sha256,
        "evidence_registry": evidence_registry,
        "required_reviews": required_reviews,
        "issues": {},
        "mechanical_error_register_policy": "producer_owned_separate_artifact",
        "publication_status": "withheld",
        "report_ready": False,
    }


def _reviewed_decisions() -> dict[str, Any]:
    return {
        "account_identity": {
            "basis": "source_account_code",
            "normalization": "remove_whitespace_within_reviewed_account_code",
            "statement_mapping": "not_performed",
        },
        "period": {
            "basis": "posting_date",
            "calendar": "gregorian",
            "grain": "calendar_month",
            "date_assignment": "nondecreasing_carried_forward_posting_date",
        },
        "scope": {
            "dataset": "one_source_presented_export",
            "eliminations": "none_applied",
            "entity_basis": "export_level_source_scope_not_emitted",
            "consolidation_status": "not_assessed",
        },
        "currency_unit_fx": {
            "unit": "source_native_unit",
            "fx": "none",
            "currency": "not_asserted",
        },
        "sign_convention": "debit_positive_credit_negative",
        "control_basis": "exact_extracted_final_debit_and_credit_controls",
        "tolerance": "0",
        "output_grain": "source_account_x_calendar_month",
    }


def _reported_controls(
    *,
    debit_control: str,
    credit_control: str,
) -> dict[str, Any]:
    return {
        "debit": debit_control,
        "credit": credit_control,
        "journal_balance_required": True,
        "monthly_balance_required": True,
        "expected_calendar_months": [
            "2023-01",
            "2023-02",
            "2023-03",
        ],
    }


def _semantic_decisions(
    *,
    debit_control: str,
    credit_control: str,
) -> dict[str, Any]:
    return {
        "schema_version": "clara.real_general_ledger_semantic_decisions.v1",
        "pilot_id": PILOT_ID,
        "source_id": SOURCE_ID,
        "review_status": "reviewed",
        "reviewer_role": "synthetic unit-test reviewer",
        "reviewed_period": {"year": 2023},
        "reviewed_decisions": _reviewed_decisions(),
        "reported_controls": _reported_controls(
            debit_control=debit_control,
            credit_control=credit_control,
        ),
        "publication_status": "withheld",
        "report_ready": False,
    }


def _case(
    fixture_paths: dict[str, Path],
    *,
    debit_control: str,
    credit_control: str,
) -> dict[str, Any]:
    return {
        "schema_version": "clara.real_general_ledger_preparation_case.v1",
        "pilot_id": PILOT_ID,
        "execution_id": EXECUTION_ID,
        "case_status": "reviewed",
        "reviewer_role": "synthetic unit-test reviewer",
        "source": {
            "source_id": SOURCE_ID,
            "declared_data_kind": "commercial_general_ledger",
        },
        "bindings": {
            "source_sha256": _sha256(fixture_paths["source"]),
            "intake_receipt_sha256": _sha256(fixture_paths["intake_receipt"]),
            "semantic_review_receipt_sha256": _sha256(
                fixture_paths["semantic_receipt"]
            ),
            "semantic_decisions_sha256": _sha256(fixture_paths["semantic_decisions"]),
            "parser_layout_sha256": _sha256(fixture_paths["parser_layout"]),
            "parser_adapter_implementation_sha256": _sha256(
                fixture_paths["parser_adapter"]
            ),
            "parser_implementation_sha256": _sha256(
                fixture_paths["parser_implementation"]
            ),
        },
        "reviewed_period": {"year": 2023},
        "reviewed_decisions": _reviewed_decisions(),
        "reported_controls": _reported_controls(
            debit_control=debit_control,
            credit_control=credit_control,
        ),
        "publication_status": "withheld",
        "report_ready": False,
    }


def _fixture(
    tmp_path: Path,
    *,
    debit_control: str = "210.25",
    credit_control: str = "210.25",
) -> _Fixture:
    pilot_root = tmp_path / "pilot"
    pilot_root.mkdir(mode=0o700)
    inputs_directory = pilot_root / "inputs"
    inputs_directory.mkdir(mode=0o700)
    source_path = inputs_directory / "authorized-source.bin"
    _write_xlsx(source_path)
    source_path.chmod(0o600)

    intake_contract_path = pilot_root / "intake.json"
    _write_json(intake_contract_path, _intake_contract(source_path))
    intake_receipt = INTAKE.validate_real_data_pilot_intake_v2(
        intake_contract_path,
        source_path,
        as_of_date=VALIDATION_DATE,
        local_run_root=pilot_root,
        repository_root=ROOT,
    )
    intake_receipt_path = pilot_root / "intake-receipt.json"
    _write_json(intake_receipt_path, intake_receipt)

    semantic_decisions_path = pilot_root / "semantic-decisions.json"
    _write_json(
        semantic_decisions_path,
        _semantic_decisions(
            debit_control=debit_control,
            credit_control=credit_control,
        ),
    )
    semantic_review_path = pilot_root / "semantic-review.json"
    _write_json(
        semantic_review_path,
        _semantic_review(
            pilot_root,
            intake_receipt_sha256=_sha256(intake_receipt_path),
            semantic_decisions_path=semantic_decisions_path,
        ),
    )
    semantic_receipt = SEMANTIC.validate_real_data_pilot_semantic_review(
        semantic_review_path,
        intake_receipt_path,
        as_of_date=VALIDATION_DATE,
        local_run_root=pilot_root,
        repository_root=ROOT,
    )
    semantic_receipt_path = pilot_root / "semantic-receipt.json"
    _write_json(semantic_receipt_path, semantic_receipt)

    parser_layout_path = pilot_root / "parser-layout.json"
    _write_json(parser_layout_path, _parser_layout())
    parser_adapter_path = SCRIPTS_ROOT / "run_real_general_ledger_pilot.py"
    parser_implementation_path = SCRIPTS_ROOT / "parse_commercial_general_journal.py"
    case_path = pilot_root / "case.json"
    _write_json(
        case_path,
        _case(
            {
                "source": source_path,
                "intake_receipt": intake_receipt_path,
                "semantic_receipt": semantic_receipt_path,
                "semantic_decisions": semantic_decisions_path,
                "parser_layout": parser_layout_path,
                "parser_adapter": parser_adapter_path,
                "parser_implementation": parser_implementation_path,
            },
            debit_control=debit_control,
            credit_control=credit_control,
        ),
    )
    output_directory = pilot_root / "output"
    result = PRODUCER.run_real_general_ledger_pilot(
        case_path=case_path,
        intake_contract_path=intake_contract_path,
        intake_receipt_path=intake_receipt_path,
        semantic_review_path=semantic_review_path,
        semantic_receipt_path=semantic_receipt_path,
        semantic_decisions_path=semantic_decisions_path,
        source_path=source_path,
        parser_layout_path=parser_layout_path,
        parser_adapter_implementation_path=parser_adapter_path,
        parser_implementation_path=parser_implementation_path,
        output_directory=output_directory,
        local_run_root=pilot_root,
        repository_root=ROOT,
        as_of_date=VALIDATION_DATE,
        parser=PRODUCER.parse_reviewed_commercial_general_journal,
    )
    return _Fixture(
        pilot_root=pilot_root,
        case_path=case_path,
        intake_contract_path=intake_contract_path,
        intake_receipt_path=intake_receipt_path,
        semantic_review_path=semantic_review_path,
        semantic_receipt_path=semantic_receipt_path,
        semantic_decisions_path=semantic_decisions_path,
        source_path=source_path,
        parser_layout_path=parser_layout_path,
        output_directory=output_directory,
        producer_status=result.status,
    )


def _build(
    fixture: _Fixture,
    *,
    pilot_root: Path | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    return ADAPTER.build_real_general_ledger_audit_envelope(
        plugin_root=CLARA_ROOT,
        pilot_root=pilot_root or fixture.pilot_root,
        case_path=fixture.case_path,
        intake_contract_path=fixture.intake_contract_path,
        intake_receipt_path=fixture.intake_receipt_path,
        semantic_review_path=fixture.semantic_review_path,
        semantic_receipt_path=fixture.semantic_receipt_path,
        semantic_decisions_path=fixture.semantic_decisions_path,
        source_path=source_path or fixture.source_path,
        parser_layout_path=fixture.parser_layout_path,
        parser_adapter_implementation_path=(
            SCRIPTS_ROOT / "run_real_general_ledger_pilot.py"
        ),
        parser_implementation_path=(
            SCRIPTS_ROOT / "parse_commercial_general_journal.py"
        ),
        prepared_output_dir=fixture.output_directory,
        as_of_date=VALIDATION_DATE,
        parser=PRODUCER.parse_reviewed_commercial_general_journal,
    )


def _cli_arguments(fixture: _Fixture, output_path: Path) -> list[str]:
    return [
        "--plugin-root",
        str(CLARA_ROOT),
        "--pilot-root",
        str(fixture.pilot_root),
        "--case",
        str(fixture.case_path),
        "--intake-contract",
        str(fixture.intake_contract_path),
        "--intake-receipt",
        str(fixture.intake_receipt_path),
        "--semantic-review",
        str(fixture.semantic_review_path),
        "--semantic-receipt",
        str(fixture.semantic_receipt_path),
        "--semantic-decisions",
        str(fixture.semantic_decisions_path),
        "--source",
        str(fixture.source_path),
        "--parser-layout",
        str(fixture.parser_layout_path),
        "--parser-adapter-implementation",
        str(SCRIPTS_ROOT / "run_real_general_ledger_pilot.py"),
        "--parser-implementation",
        str(SCRIPTS_ROOT / "parse_commercial_general_journal.py"),
        "--prepared-output-dir",
        str(fixture.output_directory),
        "--as-of-date",
        VALIDATION_DATE,
        "--output",
        str(output_path),
    ]


def _schema_validator() -> jsonschema.Draft202012Validator:
    schema_v1 = json.loads(SCHEMA_V1_PATH.read_text(encoding="utf-8"))
    schema_v2 = json.loads(SCHEMA_V2_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(
        schema_v1["$id"],
        Resource.from_contents(schema_v1),
    )
    return jsonschema.Draft202012Validator(
        schema_v2,
        registry=registry,
        format_checker=jsonschema.FormatChecker(),
    )


def test_passed_real_general_ledger_run_emits_bounded_v2_envelope(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    envelope = _build(fixture)

    _schema_validator().validate(envelope)
    assert envelope["schema_version"] == "clara.preparation_audit_envelope.v2"
    assert envelope["remote_sources"] == []
    assert envelope["statuses"]["source"]["status"] == "local_receipt_only"
    assert envelope["statuses"]["semantic"]["status"] == "not_assessed"
    assert envelope["statuses"]["publication"]["status"] == "withheld"
    assert envelope["report_ready"] is False
    assert envelope["lineage"]["aggregate"]["declared"] is False
    assert envelope["lineage"]["row"]["declared"] is False
    artifacts = {
        artifact["artifact_id"]: artifact for artifact in envelope["local_artifacts"]
    }
    assert artifacts["case_contract"]["root_id"] == "pilot"
    assert artifacts["account_month_output"]["root_id"] == "pilot"
    assert artifacts["audit_adapter"]["root_id"] == "plugin"
    assert artifacts["audit_schema"]["root_id"] == "plugin"
    assert artifacts["producer"]["root_id"] == "plugin"
    assert artifacts["authorized_local_source"]["path"] == (
        "inputs/authorized-source.bin"
    )
    assert artifacts["authorized_local_source"]["media_type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    serialized = json.dumps(envelope, sort_keys=True)
    assert str(fixture.pilot_root) not in serialized
    assert "source.xlsx" not in serialized
    assert "Synthetic fixture metadata" not in serialized
    assert "Conto" not in serialized
    assert "10 / 1 / 1" not in serialized
    assert '"10/1/1"' not in serialized
    assert "100.25" not in serialized
    assert "210.25" not in serialized
    assert not list(fixture.pilot_root.glob(".clara-m6-general-ledger-audit-replay-*"))


def test_real_general_ledger_audit_envelope_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    first = json.dumps(_build(fixture), sort_keys=True).encode()
    second = json.dumps(_build(fixture), sort_keys=True).encode()

    assert first == second


def test_cli_requires_output_below_private_pilot_root(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    outside_output = tmp_path / "outside-audit-envelope.json"

    result = ADAPTER.main(_cli_arguments(fixture, outside_output))

    assert result == 2
    assert not outside_output.exists()


def test_cli_fresh_output_writer_rejects_late_symlink_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    output_path = fixture.pilot_root / "evidence" / "audit-envelope.json"
    outside_target = tmp_path / "outside-target.json"
    outside_target.write_text('{"unchanged":true}\n', encoding="utf-8")
    original_require_absent = INTAKE._PinnedPilotReceiptOutput.require_absent
    occupied = False

    def occupy_after_check(output: Any) -> None:
        nonlocal occupied
        original_require_absent(output)
        if output.output_path == output_path and not occupied:
            output_path.symlink_to(outside_target)
            occupied = True

    monkeypatch.setattr(
        INTAKE._PinnedPilotReceiptOutput,
        "require_absent",
        occupy_after_check,
    )

    result = ADAPTER.main(_cli_arguments(fixture, output_path))

    assert result == 2
    assert occupied is True
    assert output_path.is_symlink()
    assert outside_target.read_text(encoding="utf-8") == '{"unchanged":true}\n'


def test_mutated_prepared_output_is_rejected_by_exact_replay(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    account_month_path = (
        fixture.output_directory / "artifacts" / f"{PRODUCER.ACCOUNT_MONTH_ROLE}.bin"
    )
    account_month_path.write_bytes(account_month_path.read_bytes() + b"\n")

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="do not match deterministic replay",
    ):
        _build(fixture)


def test_hard_linked_authorized_source_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.source_path.with_name("source-alias.bin").hardlink_to(fixture.source_path)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="must not be hard linked",
    ):
        _build(fixture)


def test_symlinked_authorized_source_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    outside_source = tmp_path / "outside-source.csv"
    outside_source.write_bytes(fixture.source_path.read_bytes())
    fixture.source_path.unlink()
    fixture.source_path.symlink_to(outside_source)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="non-symlink regular file",
    ):
        _build(fixture)


def test_noncanonical_authorized_source_locator_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    alternate_source = fixture.pilot_root / "private-ledger.xlsx"
    alternate_source.write_bytes(fixture.source_path.read_bytes())
    alternate_source.chmod(0o600)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="fixed private staging locator",
    ):
        _build(fixture, source_path=alternate_source)


def test_non_private_authorized_source_permissions_are_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.source_path.chmod(0o640)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="authorized source must be owner-only",
    ):
        _build(fixture)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS extended ACL regression")
def test_extended_acl_on_authorized_source_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    subprocess.run(
        [
            "/bin/chmod",
            "+a",
            "everyone allow read",
            str(fixture.source_path),
        ],
        check=True,
    )

    try:
        with pytest.raises(
            ADAPTER.ContractValidationError,
            match="authorized source must not have an extended ACL",
        ):
            _build(fixture)
    finally:
        subprocess.run(
            ["/bin/chmod", "-N", str(fixture.source_path)],
            check=True,
        )


def test_authorized_source_permissions_are_rechecked_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    original_validate = ADAPTER.validate_audit_envelope_v2

    def loosen_source_after_validation(
        envelope: Any,
        *,
        artifact_roots: dict[str, Path],
    ) -> dict[str, Any]:
        validated = original_validate(
            envelope,
            artifact_roots=artifact_roots,
        )
        fixture.source_path.chmod(0o640)
        return validated

    monkeypatch.setattr(
        ADAPTER,
        "validate_audit_envelope_v2",
        loosen_source_after_validation,
    )

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="authorized source must be owner-only",
    ):
        _build(fixture)


def test_authorized_source_identity_is_rechecked_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    original_validate = ADAPTER.validate_audit_envelope_v2
    original_source = fixture.source_path.with_name("authorized-source-original.bin")
    source_bytes = fixture.source_path.read_bytes()

    def replace_source_after_validation(
        envelope: Any,
        *,
        artifact_roots: dict[str, Path],
    ) -> dict[str, Any]:
        validated = original_validate(
            envelope,
            artifact_roots=artifact_roots,
        )
        fixture.source_path.rename(original_source)
        fixture.source_path.write_bytes(source_bytes)
        fixture.source_path.chmod(0o600)
        return validated

    monkeypatch.setattr(
        ADAPTER,
        "validate_audit_envelope_v2",
        replace_source_after_validation,
    )

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="staging identity changed during audit validation",
    ):
        _build(fixture)


def test_stale_parser_layout_is_rejected_by_replay(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    layout = json.loads(fixture.parser_layout_path.read_text(encoding="utf-8"))
    layout["review_status"] = "pending"
    _write_json(fixture.parser_layout_path, layout)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="supports passed runs only",
    ):
        _build(fixture)


def test_hard_linked_prepared_output_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    account_month_path = (
        fixture.output_directory / "artifacts" / f"{PRODUCER.ACCOUNT_MONTH_ROLE}.bin"
    )
    fixture.pilot_root.joinpath("output-alias.bin").hardlink_to(account_month_path)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="must not be hard linked",
    ):
        _build(fixture)


def test_nested_named_roots_are_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="fixed private staging locator",
    ):
        _build(fixture, pilot_root=ROOT)


def test_failure_only_run_is_not_promoted_to_an_audit_envelope(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        debit_control="211",
        credit_control="211",
    )
    assert fixture.producer_status == "failed"

    with pytest.raises(
        ADAPTER.ContractValidationError,
        match="supports passed runs only",
    ):
        _build(fixture)

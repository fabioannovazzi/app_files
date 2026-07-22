from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from docx import Document
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "previdenza-inps"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"


def _load_script(module_name: str) -> ModuleType:
    scripts_path = str(SCRIPTS_ROOT)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    path = SCRIPTS_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"previdenza_inps_{module_name}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_case_records(
    path: Path, *, date_value: str = "2021-01-01", language: str = "it"
) -> Path:
    payload = {
        "case_id": "CASE-001",
        "language": language,
        "professional_question": (
            "¿Qué tratamiento de previsión social está respaldado por las evidencias?"
            if language == "es"
            else "Quale trattamento previdenziale risulta supportato?"
        ),
        "material_decisions": {
            "professional_question_confirmed": True,
            "framework_confirmed": True,
            "period_scope_confirmed": True,
            "ambiguous_terms_resolved": True,
        },
        "decision_log": [
            {
                "decision_id": f"DEC-{index:03d}",
                "gate": gate,
                "decision": True,
                "decided_by_id": "REV-001",
                "decided_by_role": "professional_reviewer",
                "recorded_at": "2026-07-16T09:00:00+02:00",
                "basis": "Explicit reviewer instruction for the synthetic test case.",
            }
            for index, gate in enumerate(
                (
                    "professional_question_confirmed",
                    "framework_confirmed",
                    "period_scope_confirmed",
                    "ambiguous_terms_resolved",
                ),
                start=1,
            )
        ],
        "facts": [
            {
                "fact_id": "F-001",
                "statement": (
                    "La relación comienza el 1 de enero de 2021."
                    if language == "es"
                    else "Il rapporto decorre dal 1 gennaio 2021."
                ),
                "review_label": (
                    "Inicio de la relación"
                    if language == "es"
                    else "Decorrenza del rapporto"
                ),
                "value": date_value,
                "value_type": "date",
                "subject_ids": ["SUB-001"],
                "evidence": [
                    {
                        "document_id": "DOC-001",
                        "locator": {"kind": "document", "value": 1},
                        "quote": "decorre dal 1 gennaio 2021",
                    }
                ],
                "review_status": "confirmed",
                "conflict_group": None,
            }
        ],
        "timeline": [
            {
                "event_id": "EV-001",
                "date": "2021-01-01",
                "date_precision": "day",
                "description": (
                    "Inicio de la relación."
                    if language == "es"
                    else "Decorrenza del rapporto."
                ),
                "source_fact_ids": ["F-001"],
                "review_status": "confirmed",
                "conflict_group": None,
            }
        ],
        "open_questions": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_claims(path: Path, *, language: str = "it") -> Path:
    payload = {
        "language": language,
        "overall_assessment": (
            "La conclusión sigue sujeta a revisión profesional."
            if language == "es"
            else "La conclusione resta soggetta a revisione professionale."
        ),
        "claims": [
            {
                "claim_id": "CL-001",
                "claim_text": (
                    "El criterio indicado se aplica durante el periodo examinado."
                    if language == "es"
                    else "Il criterio indicato si applica nel periodo esaminato."
                ),
                "review_label": (
                    "Aplicabilidad temporal del criterio"
                    if language == "es"
                    else "Applicabilità temporale del criterio"
                ),
                "claim_type": "case_application",
                "verdict": "supported",
                "sources": [
                    {
                        "source_id": "SRC-001",
                        "reference": "https://example.test/official-source",
                        "temporal_role": "period_rule",
                        "retrieved_at": "2026-07-16T09:00:00+02:00",
                        "version_note": "Synthetic official-source snapshot for testing.",
                        "support_note": "La fonte copre il criterio e il periodo.",
                        "snapshot_sha256": None,
                    }
                ],
                "source_support": (
                    "La fuente cubre el criterio y el periodo."
                    if language == "es"
                    else "La fonte copre il criterio e il periodo."
                ),
                "reasoning_review": (
                    "La relación entre la fuente y el criterio es explícita."
                    if language == "es"
                    else "Il passaggio dalla fonte al criterio è esplicito."
                ),
                "evidence_dependencies": ["F-001"],
                "period_scope": {
                    "status": "confirmed",
                    "start": "2021-01-01",
                    "end": "2021-12-31",
                    "note": "Periodo sintetico confermato.",
                },
                "research_cutoff_date": "2026-07-16",
                "professional_review_status": "pending",
            }
        ],
        "missing_evidence": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_calculation_recipe(path: Path) -> Path:
    payload = {
        "recipes": [
            {
                "recipe_id": "CALC-001",
                "description": "Synthetic approved calculation",
                "formula_basis_claim_id": "CL-001",
                "review_status": "confirmed",
                "approval": {
                    "approved_by_id": "REV-001",
                    "approved_by_role": "professional_reviewer",
                    "recorded_at": "2026-07-16T09:00:00+02:00",
                    "basis": "Synthetic recipe approved for the packaging test.",
                },
                "operands": [
                    {
                        "id": "base",
                        "value": "100.00",
                        "unit": "EUR",
                        "source_claim_ids": ["CL-001"],
                    }
                ],
                "steps": [
                    {
                        "id": "total",
                        "operation": "add",
                        "inputs": ["base", "base"],
                    }
                ],
                "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
                "result_unit": "EUR",
            }
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _inventory_case(tmp_path: Path, *, language: str = "it") -> tuple[Path, Path]:
    inventory_case = _load_script("inventory_case")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "mandato.txt").write_text(
        "Il rapporto decorre dal 1 gennaio 2021.", encoding="utf-8"
    )
    assert (
        inventory_case.main(
            [
                str(input_dir),
                "--output-dir",
                str(output_dir),
                "--no-ocr",
                "--language",
                language,
            ]
        )
        == 0
    )
    return input_dir, output_dir


def _node_or_skip() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for MCP execution tests")
    return node


def _mcp_tool_call(
    node: str, tool_name: str, arguments: dict[str, object]
) -> dict[str, object]:
    response = _mcp_raw_response(node, tool_name, arguments)
    return response["result"]["structuredContent"]


def _mcp_raw_response(
    node: str, tool_name: str, arguments: dict[str, object]
) -> dict[str, object]:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    completed = subprocess.run(
        [node, str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip())


def _review_payload(
    run_id: str, *, item_type: str = "audit_check"
) -> dict[str, object]:
    titles = {
        "artifact": "Package artifact",
        "audit_check": "Package validation audit",
    }
    summaries = {
        "artifact": "Package artifact",
        "audit_check": "Package validation audit",
    }
    data: dict[str, object] = {"summary": summaries[item_type]}
    if item_type == "audit_check":
        data["status"] = "passed"
    return {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "run_id": run_id,
        "review_type": "professional_case_review",
        "status": "ready_for_professional_review",
        "item_count": 1,
        "items": [
            {
                "id": "audit-package",
                "item_type": item_type,
                "title": titles[item_type],
                "source_path": None,
                "output_path": None,
                "allowed_actions": [
                    "accept",
                    "reject",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ],
                "recommended_action": "accept",
                "evidence": [],
                "data": data,
                "status": "needs_review",
            }
        ],
    }


def _write_run_intake(output_dir: Path, run_id: str) -> dict[str, object]:
    output_dir.mkdir(mode=0o700)
    output_dir.chmod(0o700)
    payload = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "run_id": run_id,
        "status": "inventory_complete",
        "output_dir": output_dir.resolve().as_posix(),
        "data_posture": {
            "local_only": True,
            "network_calls_by_scripts": False,
            "network_access_allowed_for_model_weights": False,
            "acquisition_channels_used": [],
            "external_connectors_used": [],
            "ocr": {
                "enabled": False,
                "engine": "disabled",
                "language": "it",
                "attempt_location": "local_codex_workspace",
                "attempted_page_count": 0,
                "successful_page_count": 0,
                "case_content_network_transfer": False,
                "model_download_allowed": False,
                "model_network_used": False,
                "visual_confirmation_required": False,
            },
        },
        "execution_trace": [
            {
                "step_id": "previdenza_inps_package",
                "kind": "deterministic_packaging",
                "status": "passed",
                "execution_location": "local_codex_workspace",
                "command": "python scripts/package_case.py",
                "inputs": [
                    "validated_case_records",
                    (output_dir / "client-name.pdf").as_posix(),
                ],
                "outputs": ["final_artifacts.json", "../secret.json"],
            }
        ],
    }
    (output_dir / "run_intake.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "file_inventory.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "plugin": "previdenza-inps",
                "run_id": run_id,
                "documents": [],
                "evidence_fragments": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_dir / "review_payload.json").write_text(
        json.dumps(_review_payload(run_id), ensure_ascii=False), encoding="utf-8"
    )
    _write_final_artifacts(output_dir, run_id)
    return payload


def _write_final_artifacts(
    output_dir: Path,
    run_id: str,
    *,
    blockers: list[dict[str, object]] | None = None,
    status: str = "ready_for_professional_review",
) -> dict[str, object]:
    acquisition_binding = _load_script("acquisition_binding").build_acquisition_binding(
        output_dir / "file_inventory.json", output_dir / "run_intake.json"
    )
    payload = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "run_id": run_id,
        "status": status,
        "professional_review_required": True,
        "review_payload_sha256": hashlib.sha256(
            (output_dir / "review_payload.json").read_bytes()
        ).hexdigest(),
        "acquisition_binding": acquisition_binding,
        "outputs": [{"path": "studio_memo.md", "kind": "md", "status": "written"}],
        "blockers": blockers or [],
    }
    (output_dir / "final_artifacts.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return payload


def _package_bound_browser_capture_case(
    tmp_path: Path,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    """Build a ready package bound to an authorized browser-capture posture."""

    _, output_dir = _inventory_case(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    posture = run_intake["data_posture"]
    posture.update(
        {
            "local_only": False,
            "network_calls_by_scripts": True,
            "acquisition_channels_used": ["inps_conditional_browser_capture"],
            "external_connectors_used": ["inps_browser_read_only"],
            "external_routes_used": [
                {
                    "route": "inps_browser_read_only",
                    "destination_or_origin": "https://www.inps.it",
                    "payload_category": (
                        "visible_page_content_received_from_selected_tab"
                    ),
                    "network_used": True,
                    "access_basis": None,
                }
            ],
            "portal_capture_receipt": {
                "manifest_sha256": "a" * 64,
                "route_selected": True,
                "approved_origin": "https://www.inps.it",
                "case_content_uploaded": False,
            },
        }
    )
    run_intake_path.write_text(
        json.dumps(run_intake, ensure_ascii=False), encoding="utf-8"
    )
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )
    assert audit["status"] == "passed"
    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )
    assert result["final_artifacts"]["status"] == "ready_for_professional_review"
    stored_run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    return output_dir, stored_run_intake, review_payload


def test_inventory_case_is_stable_and_detects_byte_identical_duplicates(
    tmp_path: Path,
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source_text = "Il rapporto decorre dal 1 gennaio 2021."
    (input_dir / "z-copy.txt").write_text(source_text, encoding="utf-8")
    (input_dir / "a-original.txt").write_text(source_text, encoding="utf-8")

    result = case_core.extract_case_documents(input_dir, output_dir)

    documents = result.inventory["documents"]
    assert [record["relative_path"] for record in documents] == [
        "a-original.txt",
        "z-copy.txt",
    ]
    assert documents[1]["duplicate_of"] == "DOC-001"


def test_output_guard_rejects_insecure_existing_directory_without_chmod(
    tmp_path: Path,
) -> None:
    case_core = _load_script("case_core")
    output_dir = tmp_path / "shared-output"
    output_dir.mkdir(mode=0o755)
    output_dir.chmod(0o755)

    with pytest.raises(PermissionError, match="owner-only"):
        case_core.ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)

    assert (output_dir.stat().st_mode & 0o777) == 0o755


def test_inventory_does_not_classify_filename_as_legal_regime(tmp_path: Path) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "gestione_commercianti.txt").write_text(
        "Documento privo di qualificazione verificata.", encoding="utf-8"
    )

    result = case_core.extract_case_documents(input_dir, output_dir)

    assert result.inventory["semantic_classification"] == "not_performed"
    assert "legal_regime" not in result.inventory["documents"][0]


def test_inventory_records_but_does_not_follow_symlink_outside_case(
    tmp_path: Path,
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("SECRET-OUTSIDE-CASE", encoding="utf-8")
    (input_dir / "linked.txt").symlink_to(outside)

    result = case_core.extract_case_documents(input_dir, output_dir)

    record = result.inventory["documents"][0]
    assert record["limitations"] == ["symlink_not_followed"]
    assert "SECRET-OUTSIDE-CASE" not in result.extracted_evidence_path.read_text(
        encoding="utf-8"
    )


def test_inventory_preserves_material_email_headers(tmp_path: Path) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "chiarimento.eml").write_text(
        "From: agency@example.test\n"
        "To: studio@example.test\n"
        "Date: Thu, 16 Jul 2026 09:00:00 +0200\n"
        "Subject: Chiarimento gruppi\n"
        "Message-ID: <case-001@example.test>\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "La dicitura necessita di conferma documentale.\n",
        encoding="utf-8",
    )

    result = case_core.extract_case_documents(input_dir, output_dir)

    record = result.inventory["documents"][0]
    assert record["email_headers"]["Message-ID"] == "<case-001@example.test>"
    assert record["email_headers"]["Subject"] == "Chiarimento gruppi"


def test_inventory_marks_mixed_readable_and_image_only_evidence_partial(
    tmp_path: Path,
) -> None:
    case_core = _load_script("case_core")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "contratto.txt").write_text("Rapporto documentato.", encoding="utf-8")
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with (input_dir / "f24_scan.pdf").open("wb") as handle:
        writer.write(handle)

    result = case_core.extract_case_documents(input_dir, output_dir)
    extraction_report = json.loads(
        result.extraction_report_path.read_text(encoding="utf-8")
    )

    assert extraction_report["status"] == "partial_evidence"
    assert "empty_text_possible_scan" in " ".join(
        result.inventory["documents"][1]["limitations"]
    )


def test_validate_case_records_accepts_exact_document_quote(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )

    assert audit["status"] == "passed"
    assert (output_dir / "case_records_validated.json").exists()
    assert (output_dir / "timeline.csv").exists()


def test_validate_case_records_rejects_ambiguous_numeric_date(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(
        output_dir / "case_records_draft.json", date_value="03/04/2021"
    )
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )

    assert audit["status"] == "schema_error"
    assert {issue["code"] for issue in audit["issues"]} >= {"ambiguous_or_invalid_date"}


def test_validate_case_records_rejects_modified_evidence_fragment(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    fragment_path = output_dir / inventory["evidence_fragments"][0]["text_path"]
    fragment_path.write_text(
        "Il rapporto decorre dal 1 gennaio 2021. Alterazione.", encoding="utf-8"
    )
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )

    assert audit["status"] == "schema_error"
    assert {issue["code"] for issue in audit["issues"]} >= {
        "evidence_fragment_integrity_mismatch"
    }


def test_validate_case_records_enforces_value_and_professional_decision_audit(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    records = json.loads(records_path.read_text(encoding="utf-8"))
    records["facts"][0].pop("value")
    records["decision_log"] = records["decision_log"][:-1]
    records["decision_log"][0]["decided_by_role"] = "model"
    records_path.write_text(json.dumps(records), encoding="utf-8")
    validator = _load_script("validate_case_records")

    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )

    assert audit["status"] == "schema_error"
    assert {issue["code"] for issue in audit["issues"]} >= {
        "missing_fact_value",
        "incomplete_decision_log",
        "missing_decision_authority",
    }


def test_reconcile_contributions_uses_explicit_decimal_recipe() -> None:
    reconciler = _load_script("reconcile_contributions")
    records = {
        "facts": [
            {
                "fact_id": "F-BASE",
                "value": "10000.00",
                "value_type": "amount",
                "review_status": "confirmed",
            }
        ]
    }
    claims = {
        "claims": [
            {
                "claim_id": "CL-RATE",
                "claim_type": "calculation_basis",
                "verdict": "supported",
            }
        ]
    }
    recipes = {
        "recipes": [
            {
                "recipe_id": "CALC-001",
                "description": "Base per aliquota confermata",
                "formula_basis_claim_id": "CL-RATE",
                "review_status": "confirmed",
                "approval": {
                    "approved_by_id": "REV-001",
                    "approved_by_role": "professional_reviewer",
                    "recorded_at": "2026-07-16T09:00:00+02:00",
                    "basis": "Synthetic recipe approved for the test.",
                },
                "operands": [
                    {
                        "id": "base",
                        "value": "10000.00",
                        "unit": "EUR",
                        "source_fact_ids": ["F-BASE"],
                    },
                    {
                        "id": "rate",
                        "value": "0.10",
                        "unit": "ratio",
                        "source_claim_ids": ["CL-RATE"],
                    },
                ],
                "steps": [
                    {
                        "id": "expected",
                        "operation": "multiply",
                        "inputs": ["base", "rate"],
                    }
                ],
                "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
                "result_unit": "EUR",
            }
        ]
    }

    result = reconciler.evaluate_recipes(recipes, records, claims)

    assert result["status"] == "passed"
    assert result["results"][0]["result"] == "1000.00"


def test_reconcile_contributions_rejects_model_as_recipe_approver() -> None:
    reconciler = _load_script("reconcile_contributions")
    records = {
        "facts": [
            {
                "fact_id": "F-BASE",
                "value": "100.00",
                "value_type": "amount",
                "review_status": "confirmed",
            }
        ]
    }
    claims = {
        "claims": [
            {
                "claim_id": "CL-RATE",
                "claim_type": "calculation_basis",
                "verdict": "supported",
            }
        ]
    }
    recipes = {
        "recipes": [
            {
                "recipe_id": "CALC-001",
                "formula_basis_claim_id": "CL-RATE",
                "review_status": "confirmed",
                "approval": {
                    "approved_by_id": "MODEL-001",
                    "approved_by_role": "model",
                    "recorded_at": "2026-07-16T09:00:00+02:00",
                    "basis": "Model self-approval is forbidden.",
                },
                "operands": [
                    {
                        "id": "base",
                        "value": "100.00",
                        "unit": "EUR",
                        "source_fact_ids": ["F-BASE"],
                    }
                ],
                "steps": [
                    {"id": "total", "operation": "add", "inputs": ["base", "base"]}
                ],
                "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
            }
        ]
    }

    result = reconciler.evaluate_recipes(recipes, records, claims)

    assert result["status"] == "calculation_not_run"
    assert "professional_reviewer" in " ".join(result["results"][0]["errors"])


def test_reconcile_contributions_blocks_unsupported_formula_basis() -> None:
    reconciler = _load_script("reconcile_contributions")
    records = {
        "facts": [
            {
                "fact_id": "F-BASE",
                "value": "100.00",
                "value_type": "amount",
                "review_status": "confirmed",
            }
        ]
    }
    claims = {
        "claims": [
            {
                "claim_id": "CL-RATE",
                "claim_type": "calculation_basis",
                "verdict": "uncertain",
            }
        ]
    }
    recipes = {
        "recipes": [
            {
                "recipe_id": "CALC-001",
                "formula_basis_claim_id": "CL-RATE",
                "review_status": "confirmed",
                "approval": {
                    "approved_by_id": "REV-001",
                    "approved_by_role": "professional_reviewer",
                    "recorded_at": "2026-07-16T09:00:00+02:00",
                    "basis": "Synthetic recipe approved for the test.",
                },
                "operands": [
                    {
                        "id": "base",
                        "value": "100.00",
                        "unit": "EUR",
                        "source_fact_ids": ["F-BASE"],
                    }
                ],
                "steps": [
                    {"id": "total", "operation": "add", "inputs": ["base", "base"]}
                ],
                "rounding": {"places": 2, "mode": "ROUND_HALF_UP"},
            }
        ]
    }

    result = reconciler.evaluate_recipes(recipes, records, claims)

    assert result["status"] == "calculation_not_run"
    assert "not fully supported" in " ".join(result["results"][0]["errors"])


def test_package_case_writes_reviewable_markdown_docx_and_handoff(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")

    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )
    assert audit["status"] == "passed"

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    assert result["final_artifacts"]["status"] == "ready_for_professional_review"
    assert "BOZZA PER REVISIONE PROFESSIONALE" in (
        output_dir / "studio_memo.md"
    ).read_text(encoding="utf-8")
    assert (output_dir / "studio_memo.docx").stat().st_size > 0
    assert (output_dir / "review_payload.json").exists()
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    fact_item = next(
        item for item in review_payload["items"] if item["item_type"] == "fact"
    )
    assert fact_item["data"]["statement"] == "Il rapporto decorre dal 1 gennaio 2021."
    assert fact_item["data"]["review_label"] == "Decorrenza del rapporto"
    assert fact_item["evidence"][0]["quote"] == "decorre dal 1 gennaio 2021"
    handoff_item = next(
        item
        for item in review_payload["items"]
        if item.get("output_path") == "review_handoff.md"
    )
    assert handoff_item["item_type"] == "artifact"
    final_artifacts = result["final_artifacts"]
    assert final_artifacts["review_status"] == "ready_for_professional_review"
    assert final_artifacts["caveats"]
    assert final_artifacts["next_actions"]
    outputs = {output["path"]: output for output in final_artifacts["outputs"]}
    assert outputs["studio_memo.md"]["required_text"] == [
        "BOZZA PER REVISIONE PROFESSIONALE"
    ]
    assert outputs["review_handoff.md"]["required_text"] == [
        "validate_previdenza_inps_review",
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ]
    handoff = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    for artifact_name in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ):
        assert f"`{artifact_name}`" in handoff
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    trace = next(
        entry
        for entry in run_intake["execution_trace"]
        if entry["step_id"] == "previdenza_inps_package"
    )
    assert trace["status"] == "passed"
    assert trace["command"] == "python scripts/package_case.py"
    assert trace["inputs"] == ["validated_case_records", "claims_review"]
    assert {
        "studio_memo.md",
        "studio_memo.docx",
        "review_payload.json",
        "final_artifacts.json",
        "review_handoff.md",
    } <= set(trace["outputs"])
    assert (output_dir.stat().st_mode & 0o077) == 0
    assert ((output_dir / "studio_memo.md").stat().st_mode & 0o077) == 0


def test_package_case_spanish_writes_localized_artifacts_and_review_payload(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path, language="es")
    records_path = _write_case_records(
        output_dir / "case_records_draft.json", language="es"
    )
    claims_path = _write_claims(output_dir / "claims_review.json", language="es")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    audit = validator.validate_case_records(
        records_path, output_dir / "file_inventory.json", output_dir
    )
    assert audit["status"] == "passed"

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    memo = (output_dir / "studio_memo.md").read_text(encoding="utf-8")
    requests = (output_dir / "document_requests.md").read_text(encoding="utf-8")
    handoff = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    docx_text = "\n".join(
        paragraph.text
        for paragraph in Document(output_dir / "studio_memo.docx").paragraphs
    )
    review = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    final_artifacts = result["final_artifacts"]
    assert "BORRADOR PARA REVISIÓN PROFESIONAL" in memo
    assert "## Límites y responsabilidades" in memo
    assert "Solicitudes de documentos y aclaraciones" in requests
    assert "Entrega para revisión de Previdenza INPS" in handoff
    assert "BORRADOR PARA REVISIÓN PROFESIONAL" in docx_text
    assert review["language"] == "es"
    assert run_intake["working_language"] == "es"
    assert final_artifacts["language"] == "es"
    assert review["items"][0]["title"].startswith("Hecho ")
    assert final_artifacts["caveats"] == [
        "El paquete es un borrador y no constituye un dictamen profesional presentado ni firmado."
    ]
    assert "Validate and render" not in " ".join(final_artifacts["next_actions"])
    required = next(
        output["required_text"]
        for output in final_artifacts["outputs"]
        if output["path"] == "studio_memo.md"
    )
    assert required == ["BORRADOR PARA REVISIÓN PROFESIONAL"]
    node = shutil.which("node") or str(
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node"
    )
    validated = _mcp_tool_call(
        node,
        "validate_previdenza_inps_review",
        {"review_payload": review},
    )
    assert validated["review_payload"]["language"] == "es"
    assert str(validated["message"]).startswith("Los datos de revisión")


def test_previdenza_widget_selects_spanish_copy_from_review_language() -> None:
    node = shutil.which("node")
    if node is None:
        fallback = (
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "node"
            / "bin"
            / "node"
        )
        if not fallback.is_file():
            pytest.skip("Node.js is required for the widget language test")
        node = str(fallback)
    widget_path = PLUGIN_ROOT / "assets" / "previdenza-inps-review-widget.html"
    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const body = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const definitions = body.split('document.getElementById("search").addEventListener')[0];
const context = {};
vm.createContext(context);
new vm.Script(`${definitions}\nglobalThis.result = { language: languageFor({ review_payload: { language: "es" } }), queue: copyFor({ review_payload: { language: "es" } }).queueTitle, save: copyFor({ review_payload: { language: "es" } }).saveButton };`).runInContext(context);
process.stdout.write(JSON.stringify(context.result));
"""
    completed = subprocess.run(
        [node, "-e", script, str(widget_path)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "language": "es",
        "queue": "Cola de revisión",
        "save": "Guardar decisiones",
    }


def test_package_case_rejects_records_that_bypassed_validator(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_validated.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    packager = _load_script("package_case")

    result = packager.package_case(records_path, claims_path, output_dir)

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert {issue["code"] for issue in result["audit"]["issues"]} >= {
        "case_records_not_validated"
    }
    assert not (output_dir / "studio_memo.md").exists()
    assert (output_dir / "blocked_case_note.md").exists()
    assert result["final_artifacts"]["review_status"] == "validation_fail"
    assert result["final_artifacts"]["next_actions"]
    blocked_output = next(
        output
        for output in result["final_artifacts"]["outputs"]
        if output["path"] == "blocked_case_note.md"
    )
    assert blocked_output["required_text"] == [
        "FASCICOLO BLOCCATO",
        "NON È UN PARERE",
    ]


def test_package_case_spanish_localizes_blocked_note_and_public_blockers(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path, language="es")
    records_path = _write_case_records(
        output_dir / "case_records_validated.json", language="es"
    )
    claims_path = _write_claims(output_dir / "claims_review.json", language="es")
    packager = _load_script("package_case")

    result = packager.package_case(records_path, claims_path, output_dir)

    blocked = (output_dir / "blocked_case_note.md").read_text(encoding="utf-8")
    assert "EXPEDIENTE BLOQUEADO — NO ES UN DICTAMEN PROFESIONAL" in blocked
    assert "## Próximos elementos necesarios" in blocked
    assert "FASCICOLO BLOCCATO" not in blocked
    assert result["final_artifacts"]["language"] == "es"
    assert all(
        blocker["message"].startswith("Este control de validación")
        for blocker in result["final_artifacts"]["blockers"]
    )


def test_package_case_blocked_rerun_clears_stale_memo_and_review_state(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_validated.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    for name in (
        "studio_memo.md",
        "studio_memo.docx",
        "applied_decisions.json",
        "revision_requirements.json",
    ):
        (output_dir / name).write_text("stale", encoding="utf-8")
    packager = _load_script("package_case")

    result = packager.package_case(records_path, claims_path, output_dir)

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert (output_dir / "blocked_case_note.md").exists()
    for name in (
        "studio_memo.md",
        "studio_memo.docx",
        "applied_decisions.json",
        "revision_requirements.json",
    ):
        assert not (output_dir / name).exists()


def test_package_case_passed_rerun_clears_stale_blocked_note(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )
    (output_dir / "blocked_case_note.md").write_text("stale", encoding="utf-8")
    for name in (
        "calculation_results.json",
        "calculation_results.csv",
        "calculation_audit.json",
    ):
        (output_dir / name).write_text("stale", encoding="utf-8")

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    assert result["final_artifacts"]["status"] == "ready_for_professional_review"
    assert not (output_dir / "blocked_case_note.md").exists()
    assert (output_dir / "studio_memo.md").exists()
    for name in (
        "calculation_results.json",
        "calculation_results.csv",
        "calculation_audit.json",
    ):
        assert not (output_dir / name).exists()


def test_package_case_blocks_unresolved_material_claim(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    claims["claims"][0]["verdict"] = "uncertain"
    claims["claims"][0]["period_scope"] = {
        "status": "unresolved",
        "start": "2021-01-01",
        "end": None,
        "note": "La data finale non è documentata.",
    }
    claims["claims"][0]["evidence_dependencies"] = []
    claims_path.write_text(json.dumps(claims), encoding="utf-8")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert {issue["code"] for issue in result["audit"]["issues"]} >= {
        "material_claim_not_fully_supported",
        "missing_case_fact_dependencies",
    }
    assert (output_dir / "blocked_case_note.md").exists()


def test_package_case_blocks_changed_acquisition_posture_after_validation(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["data_posture"]["local_only"] = False
    run_intake_path.write_text(json.dumps(run_intake), encoding="utf-8")

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert "acquisition_run_intake_acquisition_sha256_mismatch" in {
        issue["code"] for issue in result["audit"]["issues"]
    }


def test_package_case_preserves_professional_data_but_blocks_session_urls(
    tmp_path: Path,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    professional_data = "Fabio Annovazzi — TSTUSR80A01H501U — test.user@example.it"
    secret_url = "https://www.inps.it/area?token=PRIVATE-TOKEN"
    claims["claims"][0]["review_label"] = professional_data
    claims["claims"][0]["sources"][0]["reference"] = secret_url
    claims_path.write_text(json.dumps(claims), encoding="utf-8")

    result = packager.package_case(
        output_dir / "case_records_validated.json", claims_path, output_dir
    )

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert {issue["code"] for issue in result["audit"]["issues"]} >= {
        "unsafe_source_reference"
    }
    generated = "\n".join(
        (output_dir / name).read_text(encoding="utf-8")
        for name in (
            "blocked_case_note.md",
            "claims_review_normalized.json",
            "final_artifacts.json",
            "review_payload.json",
            "validation_audit.json",
        )
    )
    assert professional_data in generated
    assert secret_url not in generated


def test_package_case_rejects_unbound_calculation_results(tmp_path: Path) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    validator = _load_script("validate_case_records")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )
    calculations_path = output_dir / "calculation_results.json"
    calculations_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "results": [
                    {
                        "recipe_id": "CALC-FAKE",
                        "status": "calculated",
                        "result": "999999.99",
                        "unit": "EUR",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = packager.package_case(
        output_dir / "case_records_validated.json",
        claims_path,
        output_dir,
        calculations_path=calculations_path,
    )

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert {issue["code"] for issue in result["audit"]["issues"]} >= {
        "missing_calculation_audit"
    }
    calculation_item = next(
        item
        for item in result["review_payload"]["items"]
        if item["item_type"] == "calculation"
    )
    assert calculation_item["recommended_action"] == "mark_unclear"
    assert not (output_dir / "studio_memo.md").exists()


@pytest.mark.parametrize(
    ("scenario", "expected_issue"),
    [
        ("missing_csv", "missing_calculation_artifact"),
        ("external_directory", "calculation_artifacts_outside_package"),
        ("tampered_csv", "calculation_results_csv_hash_mismatch"),
    ],
)
def test_package_case_rejects_incomplete_or_external_calculation_package(
    tmp_path: Path,
    scenario: str,
    expected_issue: str,
) -> None:
    _, output_dir = _inventory_case(tmp_path)
    records_path = _write_case_records(output_dir / "case_records_draft.json")
    claims_path = _write_claims(output_dir / "claims_review.json")
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    claims["claims"][0]["claim_type"] = "calculation_basis"
    claims_path.write_text(json.dumps(claims), encoding="utf-8")
    recipes_path = _write_calculation_recipe(output_dir / "recipes.json")
    validator = _load_script("validate_case_records")
    reconciler = _load_script("reconcile_contributions")
    packager = _load_script("package_case")
    assert (
        validator.validate_case_records(
            records_path, output_dir / "file_inventory.json", output_dir
        )["status"]
        == "passed"
    )
    calculation_dir = (
        tmp_path / "external-calculations"
        if scenario == "external_directory"
        else output_dir
    )
    assert (
        reconciler.main(
            [
                str(recipes_path),
                str(output_dir / "case_records_validated.json"),
                str(claims_path),
                "--output-dir",
                str(calculation_dir),
            ]
        )
        == 0
    )
    if scenario == "missing_csv":
        (calculation_dir / "calculation_results.csv").unlink()
    elif scenario == "tampered_csv":
        with (calculation_dir / "calculation_results.csv").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write("tampered\n")

    result = packager.package_case(
        output_dir / "case_records_validated.json",
        claims_path,
        output_dir,
        calculations_path=calculation_dir / "calculation_results.json",
    )

    assert result["final_artifacts"]["status"] == "validation_fail"
    assert expected_issue in {issue["code"] for issue in result["audit"]["issues"]}
    calculation_outputs = {
        output["path"]: output["status"]
        for output in result["final_artifacts"]["outputs"]
        if output["path"].startswith("calculation_")
    }
    assert "written" not in calculation_outputs.values()
    calculation_item = next(
        item
        for item in result["review_payload"]["items"]
        if item["item_type"] == "calculation"
    )
    assert calculation_item["recommended_action"] == "mark_unclear"


def test_previdenza_inps_mcp_lists_exact_review_tool_contract() -> None:
    node = shutil.which("node")
    if node is None:
        source = (PLUGIN_ROOT / "mcp" / "server.cjs").read_text(encoding="utf-8")
        assert all(
            tool_name in source
            for tool_name in (
                "validate_previdenza_inps_review",
                "render_previdenza_inps_review",
                "save_previdenza_inps_decisions",
                "apply_previdenza_inps_decisions",
            )
        )
        return
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    result = subprocess.run(
        [node, str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        capture_output=True,
        check=False,
        text=True,
    )

    responses = [json.loads(line) for line in result.stdout.splitlines() if line]
    tools = responses[-1]["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "validate_previdenza_inps_review",
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    }


def test_previdenza_inps_widget_can_cancel_unsaved_changes_and_show_safe_trace() -> (
    None
):
    source = (PLUGIN_ROOT / "assets" / "previdenza-inps-review-widget.html").read_text(
        encoding="utf-8"
    )

    assert 'id="cancel"' in source
    assert "Annulla modifiche" in source
    assert "function savedDecisionMap()" in source
    assert "function clearDraft()" in source
    assert "function cancelChanges()" in source
    assert 'document.getElementById("cancel").addEventListener("click"' in source
    assert (
        'document.getElementById("cancel").disabled = state.busy || !state.dirty'
        in source
    )
    assert ".actions #copy { display: none; }" in source
    assert ".actions .button.quiet { display: none; }" not in source
    assert "entry.command" in source
    assert "entry.inputs" in source
    assert "entry.outputs" in source


def test_previdenza_inps_widget_cancel_restores_persisted_decision() -> None:
    node = _node_or_skip()
    widget_path = PLUGIN_ROOT / "assets" / "previdenza-inps-review-widget.html"
    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) throw new Error("widget script missing");
const nodes = new Map();
const document = {
  getElementById(id) {
    if (!nodes.has(id)) {
      nodes.set(id, {
        addEventListener() {},
        disabled: false,
        innerHTML: "",
        textContent: "",
        value: "",
      });
    }
    return nodes.get(id);
  },
};
const payload = {
  widget_type: "previdenza_inps_review",
  run_intake: null,
  review_payload: {
    schema_version: "1.0",
    plugin: "previdenza-inps",
    workflow: "previdenza-inps",
    run_id: "widget-cancel-test",
    item_count: 1,
    items: [{
      id: "audit-package",
      item_type: "audit_check",
      title: "Package audit",
      allowed_actions: ["accept", "reject"],
      recommended_action: "accept",
      evidence: [],
      data: { status: "passed" },
      status: "needs_review",
    }],
    status: "ready_for_professional_review",
  },
  ui_decisions: {
    decisions: [{ item_id: "audit-package", action: "accept" }],
  },
  final_artifacts: { outputs: [], blockers: [] },
  decision_policy: { can_persist: true },
};
let lastWidgetState = null;
const context = {
  console,
  document,
  window: {
    openai: {
      toolOutput: payload,
      widgetState: {
        run_id: "widget-cancel-test",
        decisions: {
          "audit-package": { item_id: "audit-package", action: "reject" },
        },
      },
      setWidgetState(value) { lastWidgetState = value; },
    },
  },
};
vm.createContext(context);
new vm.Script(`${match[1]}\nglobalThis.__widgetTest = { state, cancelChanges };`).runInContext(context);
if (!context.__widgetTest.state.dirty) throw new Error("recovered draft was not marked dirty");
if (context.__widgetTest.state.decisions["audit-package"].action !== "reject") {
  throw new Error("draft decision was not recovered");
}
context.__widgetTest.cancelChanges();
if (context.__widgetTest.state.dirty) throw new Error("cancel did not clear dirty state");
if (context.__widgetTest.state.decisions["audit-package"].action !== "accept") {
  throw new Error("cancel did not restore the persisted decision");
}
if (!lastWidgetState || Object.keys(lastWidgetState.decisions).length !== 0) {
  throw new Error("cancel did not clear persisted widget draft state");
}
"""

    completed = subprocess.run(
        [node, "-e", script, str(widget_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_previdenza_inps_mcp_save_persists_only_relative_path_disclosure(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-save"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)

    result = _mcp_tool_call(
        node,
        "save_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": _review_payload(run_id),
            "decisions": [{"item_id": "audit-package", "action": "accept"}],
        },
    )

    assert result["ok"] is True
    assert result["persisted"] is True
    assert result["ui_decisions_path"] == "ui_decisions.json"
    assert output_dir.as_posix() not in json.dumps(result)
    assert (output_dir / "ui_decisions.json").exists()


def test_previdenza_inps_mcp_render_uses_opaque_persistence_token(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-render"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    run_intake["execution_trace"].append(
        {
            "step_id": "untrusted",
            "command": f"cat {output_dir / 'secret.txt'}",
            "inputs": ["claims_review", "subject-name.pdf"],
            "outputs": ["review_handoff.md", "/tmp/private-output.json"],
        }
    )

    result = _mcp_tool_call(
        node,
        "render_previdenza_inps_review",
        {"run_intake": run_intake, "review_payload": _review_payload(run_id)},
    )

    assert result["decision_policy"]["can_persist"] is True
    assert "persistence_token" in result["run_intake"]
    assert "output_dir" not in result["run_intake"]
    assert output_dir.as_posix() not in json.dumps(result)
    trace = result["run_intake"]["execution_trace"][0]
    assert trace["command"] == "python scripts/package_case.py"
    assert trace["inputs"] == ["validated_case_records"]
    assert trace["outputs"] == ["final_artifacts.json"]
    assert "client-name.pdf" not in json.dumps(trace)
    assert "secret.json" not in json.dumps(trace)
    assert len(result["run_intake"]["execution_trace"]) == 1
    assert "untrusted" not in json.dumps(result)


def test_previdenza_inps_mcp_render_does_not_invent_connector_approval(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-connector-posture"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    run_intake["data_posture"] = {
        "local_only": False,
        "network_calls_by_scripts": True,
        "external_connectors_used": ["inps_browser_read_only"],
        "external_routes_used": [
            {
                "route": "inps_browser_read_only",
                "destination_or_origin": "https://www.inps.it",
                "payload_category": "visible_page_content_received_from_selected_tab",
                "network_used": True,
                "access_basis": "PRIVATE-ACCESS-BASIS",
            }
        ],
    }
    run_intake["execution_trace"] = [
        {
            "step_id": "previdenza_inps_portal_capture",
            "kind": "read_only_browser_capture",
            "status": "passed",
            "execution_location": "external_connector",
            "command": "python scripts/capture_portal_snapshot.py",
            "inputs": ["selected_open_browser_tab"],
            "outputs": [
                "portal_capture_manifest.json",
                "portal_full_page.png",
                "portal_visible_text.txt",
            ],
        }
    ]

    result = _mcp_tool_call(
        node,
        "render_previdenza_inps_review",
        {"run_intake": run_intake, "review_payload": _review_payload(run_id)},
    )

    posture = result["run_intake"]["data_posture"]
    assert posture["external_connectors_used"] == []
    assert posture["external_routes_used"] == []
    assert "external_execution_approval" not in posture
    assert "PRIVATE-ACCESS-BASIS" not in json.dumps(result)
    assert (
        result["run_intake"]["execution_trace"][0]["kind"] == "deterministic_packaging"
    )


def test_previdenza_inps_mcp_render_preserves_professional_case_fields() -> None:
    node = _node_or_skip()
    review = _review_payload("previdenza-inps-untrusted-fields")
    item = review["items"][0]
    assert isinstance(item, dict)
    item["title"] = "Fabio Annovazzi — test.user@example.it"
    item["data"]["case_fact"] = "TSTUSR80A01H501U"
    item["evidence"] = [{"kind": "quote", "quote": "Fabio requested review."}]

    result = _mcp_tool_call(
        node,
        "render_previdenza_inps_review",
        {"review_payload": review},
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert "Fabio Annovazzi — test.user@example.it" in serialized
    assert "TSTUSR80A01H501U" in serialized
    assert result["review_payload"]["items"][0]["evidence"] == [
        {"kind": "quote", "quote": "Fabio requested review."}
    ]


def test_previdenza_inps_mcp_render_rejects_tokenized_session_urls() -> None:
    node = _node_or_skip()
    review = _review_payload("previdenza-inps-session-url")
    review["items"][0]["evidence"] = [
        {
            "kind": "source_reference",
            "value": "https://www.inps.it/area?token=PRIVATE-TOKEN",
        }
    ]

    response = _mcp_raw_response(
        node,
        "render_previdenza_inps_review",
        {"review_payload": review},
    )

    assert response["result"]["isError"] is True
    assert (
        "private, credentialed, or tokenized URLs"
        in response["result"]["structuredContent"]["error"]
    )


def test_previdenza_inps_mcp_persistence_rejects_reduced_stored_review(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-exact-review"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    stored_review = _review_payload(run_id)
    second_item = {
        **stored_review["items"][0],
        "id": "artifact-review-handoff",
        "item_type": "artifact",
        "title": "Package artifact",
        "data": {"path": "review_handoff.md", "summary": "Package artifact"},
        "output_path": "review_handoff.md",
    }
    stored_review["items"].append(second_item)
    stored_review["item_count"] = 2
    (output_dir / "review_payload.json").write_text(
        json.dumps(stored_review), encoding="utf-8"
    )
    _write_final_artifacts(output_dir, run_id)
    reduced_review = {
        **stored_review,
        "items": stored_review["items"][:1],
        "item_count": 1,
    }

    result = _mcp_tool_call(
        node,
        "render_previdenza_inps_review",
        {"run_intake": run_intake, "review_payload": reduced_review},
    )

    assert result["ok"] is False
    assert "exactly match stored review_payload.json" in result["error"]


@pytest.mark.parametrize(
    "tool_name",
    [
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ],
)
def test_previdenza_inps_mcp_rejects_post_package_acquisition_posture_tamper(
    tmp_path: Path,
    tool_name: str,
) -> None:
    node = _node_or_skip()
    output_dir, bound_run_intake, review_payload = _package_bound_browser_capture_case(
        tmp_path
    )
    run_intake_path = output_dir / "run_intake.json"
    final_artifacts_path = output_dir / "final_artifacts.json"
    tampered_run_intake = json.loads(json.dumps(bound_run_intake))
    posture = tampered_run_intake["data_posture"]
    posture["local_only"] = True
    posture["network_calls_by_scripts"] = False
    posture["acquisition_channels_used"] = []
    posture["external_connectors_used"] = []
    posture.pop("external_routes_used", None)
    posture.pop("portal_capture_receipt", None)
    run_intake_path.write_text(
        json.dumps(tampered_run_intake, ensure_ascii=False), encoding="utf-8"
    )
    tampered_run_intake_bytes = run_intake_path.read_bytes()
    final_artifacts_bytes = final_artifacts_path.read_bytes()
    decision_artifacts = (
        output_dir / "ui_decisions.json",
        output_dir / "applied_decisions.json",
        output_dir / "revision_requirements.json",
    )
    decision_artifact_state = {
        path: path.read_bytes() if path.exists() else None
        for path in decision_artifacts
    }
    arguments = {
        "run_intake": bound_run_intake,
        "review_payload": review_payload,
    }
    if tool_name != "render_previdenza_inps_review":
        arguments["decisions"] = [
            {"item_id": item["id"], "action": "accept"}
            for item in review_payload["items"]
        ]

    result = _mcp_tool_call(node, tool_name, arguments)

    assert result["ok"] is False
    assert "acquisition" in result["error"].lower()
    for path, expected_bytes in decision_artifact_state.items():
        assert path.exists() is (expected_bytes is not None)
        if expected_bytes is not None:
            assert path.read_bytes() == expected_bytes
    assert run_intake_path.read_bytes() == tampered_run_intake_bytes
    assert final_artifacts_path.read_bytes() == final_artifacts_bytes


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        ("portal_capture_receipt", "run_intake_acquisition_sha256"),
        ("file_inventory", "file_inventory_sha256"),
    ],
)
def test_previdenza_inps_mcp_apply_rejects_bound_acquisition_artifact_tamper(
    tmp_path: Path,
    tamper_kind: str,
    expected_error: str,
) -> None:
    node = _node_or_skip()
    output_dir, bound_run_intake, review_payload = _package_bound_browser_capture_case(
        tmp_path
    )
    run_intake_path = output_dir / "run_intake.json"
    inventory_path = output_dir / "file_inventory.json"
    final_artifacts_path = output_dir / "final_artifacts.json"
    if tamper_kind == "portal_capture_receipt":
        stored_run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
        stored_run_intake["data_posture"]["portal_capture_receipt"][
            "case_content_uploaded"
        ] = True
        run_intake_path.write_text(
            json.dumps(stored_run_intake, ensure_ascii=False), encoding="utf-8"
        )
    else:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inventory["tampered_after_packaging"] = True
        inventory_path.write_text(
            json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
        )
    protected_paths = (
        run_intake_path,
        inventory_path,
        final_artifacts_path,
        output_dir / "ui_decisions.json",
        output_dir / "applied_decisions.json",
        output_dir / "revision_requirements.json",
    )
    protected_state = {
        path: path.read_bytes() if path.exists() else None for path in protected_paths
    }
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review_payload["items"]
    ]

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": bound_run_intake,
            "review_payload": review_payload,
            "decisions": decisions,
        },
    )

    assert result["ok"] is False
    assert expected_error in result["error"]
    for path, expected_bytes in protected_state.items():
        assert path.exists() is (expected_bytes is not None)
        if expected_bytes is not None:
            assert path.read_bytes() == expected_bytes


@pytest.mark.parametrize(
    "tool_name",
    [
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ],
)
@pytest.mark.parametrize(
    ("final_mutation", "expected_error"),
    [
        ("deleted", "requires final_artifacts.json"),
        ("downgraded", "requires a ready final_artifacts.json"),
    ],
)
def test_previdenza_inps_mcp_rejects_missing_or_downgraded_bound_final(
    tmp_path: Path,
    tool_name: str,
    final_mutation: str,
    expected_error: str,
) -> None:
    node = _node_or_skip()
    run_id = f"previdenza-inps-final-{final_mutation}-{tool_name}"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    review_payload = _review_payload(run_id)
    final_path = output_dir / "final_artifacts.json"
    if final_mutation == "deleted":
        final_path.unlink()
    else:
        final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
        final_artifacts["status"] = "validation_fail"
        final_artifacts.pop("acquisition_binding")
        final_path.write_text(
            json.dumps(final_artifacts, ensure_ascii=False), encoding="utf-8"
        )
    protected_paths = (
        output_dir / "run_intake.json",
        final_path,
        output_dir / "ui_decisions.json",
        output_dir / "applied_decisions.json",
        output_dir / "revision_requirements.json",
    )
    protected_state = {
        path: path.read_bytes() if path.exists() else None for path in protected_paths
    }
    arguments = {"run_intake": run_intake, "review_payload": review_payload}
    if tool_name != "render_previdenza_inps_review":
        arguments["decisions"] = [{"item_id": "audit-package", "action": "accept"}]

    result = _mcp_tool_call(node, tool_name, arguments)

    assert result["ok"] is False
    assert expected_error in result["error"]
    for path, expected_bytes in protected_state.items():
        assert path.exists() is (expected_bytes is not None)
        if expected_bytes is not None:
            assert path.read_bytes() == expected_bytes


@pytest.mark.parametrize(
    "tool_name",
    [
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ],
)
@pytest.mark.parametrize(
    ("identity_field", "invalid_value", "expected_error"),
    [
        ("plugin", "other-plugin", "stored final_artifacts.plugin"),
        ("workflow", "other-workflow", "stored final_artifacts.workflow"),
        ("run_id", "other-run", "stored final_artifacts.run_id"),
    ],
)
def test_previdenza_inps_mcp_rejects_bound_final_identity_mismatch(
    tmp_path: Path,
    tool_name: str,
    identity_field: str,
    invalid_value: str,
    expected_error: str,
) -> None:
    node = _node_or_skip()
    run_id = f"previdenza-inps-final-identity-{identity_field}-{tool_name}"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    review_payload = _review_payload(run_id)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts[identity_field] = invalid_value
    final_path.write_text(
        json.dumps(final_artifacts, ensure_ascii=False), encoding="utf-8"
    )
    protected_paths = (
        output_dir / "run_intake.json",
        final_path,
        output_dir / "ui_decisions.json",
        output_dir / "applied_decisions.json",
        output_dir / "revision_requirements.json",
    )
    protected_state = {
        path: path.read_bytes() if path.exists() else None for path in protected_paths
    }
    arguments = {"run_intake": run_intake, "review_payload": review_payload}
    if tool_name != "render_previdenza_inps_review":
        arguments["decisions"] = [{"item_id": "audit-package", "action": "accept"}]

    result = _mcp_tool_call(node, tool_name, arguments)

    assert result["ok"] is False
    assert expected_error in result["error"]
    for path, expected_bytes in protected_state.items():
        assert path.exists() is (expected_bytes is not None)
        if expected_bytes is not None:
            assert path.read_bytes() == expected_bytes


def test_previdenza_inps_mcp_render_token_can_persist_in_same_session(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-token-session"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    process = subprocess.Popen(
        [node, str(PLUGIN_ROOT / "mcp" / "server.cjs"), "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    render_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "render_previdenza_inps_review",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": _review_payload(run_id),
            },
        },
    }
    process.stdin.write(json.dumps(render_request) + "\n")
    process.stdin.flush()
    rendered = json.loads(process.stdout.readline())["result"]["structuredContent"]

    save_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "save_previdenza_inps_decisions",
            "arguments": {
                "run_intake": rendered["run_intake"],
                "review_payload": rendered["review_payload"],
                "decisions": [{"item_id": "audit-package", "action": "accept"}],
            },
        },
    }
    process.stdin.write(json.dumps(save_request) + "\n")
    process.stdin.flush()
    saved = json.loads(process.stdout.readline())["result"]["structuredContent"]
    process.stdin.close()
    assert process.wait(timeout=5) == 0

    assert saved["ok"] is True
    assert saved["ui_decisions_path"] == "ui_decisions.json"
    assert (output_dir / "ui_decisions.json").exists()


def test_previdenza_inps_mcp_save_rejects_git_workspace_output() -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-unsafe"
    unsafe_run_intake = {
        "schema_version": "1.0",
        "plugin": "previdenza-inps",
        "workflow": "previdenza-inps",
        "run_id": run_id,
        "output_dir": PLUGIN_ROOT.resolve().as_posix(),
    }

    result = _mcp_tool_call(
        node,
        "save_previdenza_inps_decisions",
        {
            "run_intake": unsafe_run_intake,
            "review_payload": _review_payload(run_id),
            "decisions": [{"item_id": "audit-package", "action": "accept"}],
        },
    )

    assert result["ok"] is False
    assert "outside the plugin Git workspace" in result["error"]


def test_previdenza_inps_mcp_save_rejects_mismatched_stored_run(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    output_dir = tmp_path / "output"
    stored = _write_run_intake(output_dir, "stored-run")
    provided = {**stored, "run_id": "provided-run"}

    result = _mcp_tool_call(
        node,
        "save_previdenza_inps_decisions",
        {
            "run_intake": provided,
            "review_payload": _review_payload("provided-run"),
            "decisions": [{"item_id": "audit-package", "action": "accept"}],
        },
    )

    assert result["ok"] is False
    assert "stored run_intake.run_id must match" in result["error"]


def test_previdenza_inps_mcp_apply_reject_preserves_existing_blockers(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-reject"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    existing_blocker = {
        "code": "missing_source",
        "message": "An existing package blocker must remain visible.",
    }
    _write_final_artifacts(output_dir, run_id, blockers=[existing_blocker])

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": _review_payload(run_id),
            "decisions": [{"item_id": "audit-package", "action": "reject"}],
        },
    )

    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert result["application_status"] == "blocked"
    assert result["final_artifacts_path"] == "final_artifacts.json"
    assert existing_blocker in final_artifacts["blockers"]
    assert any(
        blocker.get("item_id") == "audit-package" and blocker.get("action") == "reject"
        for blocker in final_artifacts["blockers"]
    )
    assert "final_ready" not in json.dumps(result)


def test_previdenza_inps_mcp_apply_edit_records_revision_without_editing_memo(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-edit"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    artifact_review = _review_payload(run_id, item_type="artifact")
    (output_dir / "review_payload.json").write_text(
        json.dumps(artifact_review), encoding="utf-8"
    )
    _write_final_artifacts(output_dir, run_id)
    memo_path = output_dir / "studio_memo.md"
    original_memo = "# BOZZA\n\nTesto originale.\n"
    memo_path.write_text(original_memo, encoding="utf-8")

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": artifact_review,
            "decisions": [
                {
                    "item_id": "audit-package",
                    "action": "edit",
                    "edit_value": "Correggere il periodo nel memo.",
                }
            ],
        },
    )

    revisions = json.loads(
        (output_dir / "revision_requirements.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert result["application_status"] == "blocked"
    assert result["revision_requirements_path"] == "revision_requirements.json"
    assert revisions["source_artifacts_modified"] is False
    assert revisions["revisions"][0]["status"] == "revision_required_not_applied"
    assert memo_path.read_text(encoding="utf-8") == original_memo
    assert any(
        output["path"] == "revision_requirements.json"
        and output["status"] == "revision_required_not_applied"
        for output in final_artifacts["outputs"]
    )


@pytest.mark.parametrize(
    "action",
    ["reject", "skip", "edit", "mark_unclear", "request_more_documents"],
)
def test_previdenza_inps_mcp_non_accept_actions_remain_blocking(
    tmp_path: Path,
    action: str,
) -> None:
    node = _node_or_skip()
    run_id = f"previdenza-inps-block-{action}"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    _write_final_artifacts(output_dir, run_id)
    decision = {"item_id": "audit-package", "action": action}
    if action == "edit":
        decision["edit_value"] = "Revision required."

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": _review_payload(run_id),
            "decisions": [decision],
        },
    )

    assert result["application_status"] == "blocked"
    assert result["blocker_count"] >= 1


def test_previdenza_inps_mcp_apply_all_accepts_keeps_professional_review_ceiling(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-accept"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    _write_final_artifacts(output_dir, run_id)

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": _review_payload(run_id),
            "decisions": [{"item_id": "audit-package", "action": "accept"}],
        },
    )

    assert result["application_status"] == "ready_for_professional_review"
    assert result["final_artifacts"]["status"] == "ready_for_professional_review"
    assert result["run_intake_path"] == "run_intake.json"
    stored_run = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    application_trace = next(
        entry
        for entry in stored_run["execution_trace"]
        if entry["step_id"] == "previdenza_inps_review_application"
    )
    assert application_trace == {
        "step_id": "previdenza_inps_review_application",
        "kind": "professional_review_application",
        "status": "ready_for_professional_review",
        "execution_location": "local_mcp_server",
        "command": "apply_previdenza_inps_decisions",
        "inputs": ["review_payload", "ui_decisions"],
        "outputs": [
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
        "applied_at": application_trace["applied_at"],
    }
    assert "final_ready" not in json.dumps(result)


def test_previdenza_inps_mcp_apply_accept_cannot_upgrade_invalid_package(
    tmp_path: Path,
) -> None:
    node = _node_or_skip()
    run_id = "previdenza-inps-invalid-package"
    output_dir = tmp_path / "output"
    run_intake = _write_run_intake(output_dir, run_id)
    invalid_review = _review_payload(run_id)
    invalid_review["status"] = "validation_fail"
    (output_dir / "review_payload.json").write_text(
        json.dumps(invalid_review), encoding="utf-8"
    )
    _write_final_artifacts(output_dir, run_id, status="validation_fail")

    result = _mcp_tool_call(
        node,
        "apply_previdenza_inps_decisions",
        {
            "run_intake": run_intake,
            "review_payload": invalid_review,
            "decisions": [{"item_id": "audit-package", "action": "accept"}],
        },
    )

    assert result["application_status"] == "blocked"
    assert result["final_artifacts"]["blockers"] == [{"status": "blocked"}]

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from openpyxl import Workbook

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "audit-reconciliation"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
REVIEW_SESSION_PATH = SCRIPT_DIR / "review_session.py"
REVIEW_SERVER_PATH = SCRIPT_DIR / "review_server.py"
RAW_INPUT_RUNNER_PATH = SCRIPT_DIR / "raw_input_runner.py"
CHECK_DEPENDENCIES_PATH = SCRIPT_DIR / "check_dependencies.py"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


def load_review_session() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "audit_reconciliation_review_session", REVIEW_SESSION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_raw_input_runner() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "audit_reconciliation_raw_input_runner", RAW_INPUT_RUNNER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_review_server() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "audit_reconciliation_review_server", REVIEW_SERVER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_check_dependencies() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "audit_reconciliation_check_dependencies", CHECK_DEPENDENCIES_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js is required to exercise the Audit Reconciliation MCP server."
        )
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_workbook(
    path: Path,
    sheet_names: list[str],
    *,
    headers_by_sheet: dict[str, list[str]] | None = None,
    rows_by_sheet: dict[str, list[list[object]]] | None = None,
) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in sheet_names:
        sheet = workbook.create_sheet(sheet_name)
        headers = (headers_by_sheet or {}).get(sheet_name, ["Campo", "Valore"])
        sheet.append(headers)
        rows = (rows_by_sheet or {}).get(sheet_name)
        if rows is None:
            rows = [["fixture" for _header in headers]]
        for row in rows:
            sheet.append(row)
    workbook.save(path)


def _write_docx(path: Path, title: str, required_text: list[str] | None = None) -> None:
    document = Document()
    document.add_heading(title, level=1)
    document.add_paragraph("Fixture document for native artifact validation.")
    for fragment in required_text or []:
        document.add_paragraph(fragment)
    document.save(path)


def test_review_session_writes_audit_reconciliation_contract(tmp_path: Path) -> None:
    review_session = load_review_session()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    audit_workbook = output_dir / "riconciliazione_audit.xlsx"
    accountant_workbook = output_dir / "scheda_operativa_commercialista.xlsx"
    word_report = output_dir / "relazione_riconciliazione_audit.docx"
    missing_requests = output_dir / "richieste_mirate_evidenze.xlsx"
    _write_workbook(
        audit_workbook,
        [
            "Indice",
            "Assunzioni",
            "Dettaglio riconciliazione",
            "Sintesi",
            "Controlli",
            "Revisione Codex",
        ],
        headers_by_sheet={
            "Indice": ["Foglio", "Righe"],
            "Assunzioni": ["Campo", "Valore"],
            "Dettaglio riconciliazione": [
                "Documento",
                "Esito riconciliazione",
                "ID riga",
            ],
        },
        rows_by_sheet={
            "Indice": [
                ["Assunzioni", 1],
                ["Inventario fonti", 1],
                ["Righe normalizzate", 0],
                ["Dettaglio riconciliazione", 3],
            ],
            "Assunzioni": [["Currency", "EUR"]],
            "Dettaglio riconciliazione": [["INV-1", "closed", "row-1"]],
        },
    )
    _write_workbook(
        accountant_workbook,
        ["Legenda", "Scheda operativa", "Dettaglio riscontri"],
        headers_by_sheet={
            "Legenda": ["campo", "valore"],
            "Scheda operativa": [
                "id dettaglio",
                "partita",
                "stato riscontro",
                "azione richiesta",
            ],
            "Dettaglio riscontri": [
                "id dettaglio",
                "partita",
                "tipo evidenza",
                "riferimento fonte",
            ],
        },
        rows_by_sheet={
            "Legenda": [
                [
                    "Scopo",
                    (
                        "Scheda operativa riga-per-riga: data pagamento/incasso, "
                        "fonte, modalita, compensazione, stato, confidenza e "
                        "azione richiesta."
                    ),
                ],
                ["Righe", 3],
            ],
            "Scheda operativa": [
                ["R0001", "INV-1", "Chiuso", "Verificare fonte"],
            ],
        },
    )
    required_word_text = [
        "Sintesi esecutiva",
        "Perimetro e metodo",
        "Come leggere gli esiti",
        "Controlli automatici",
        "Revisione manuale Codex",
        "Limiti della procedura",
        "Rinvio al file Excel",
    ]
    _write_docx(word_report, "Relazione riconciliazione", required_word_text)
    _write_workbook(missing_requests, ["Richieste"])

    run_intake = review_session.write_run_intake(
        output_dir,
        assumptions={
            "scope_year": 2025,
            "cutoff_date": "2025-12-31",
            "currency": "EUR",
            "report_language": "it",
            "document_language": "it",
            "factoring_pro_soluto_closes_item": True,
        },
        source_inventory=[{"source_file": "open_items.xlsx"}],
        language="it",
        source_hint="open_items.xlsx",
    )
    result = {
        "excel_path": str(audit_workbook),
        "accountant_report_path": str(accountant_workbook),
        "word_path": str(word_report),
        "assumptions": {"currency": "EUR"},
        "reconciliation_rows": [
            {
                "record_id": "row-1",
                "document_no": "INV-1",
                "reconciliation_status": "closed",
            },
            {
                "record_id": "row-2",
                "document_no": "INV-2",
                "reconciliation_status": "needs_evidence",
            },
            {
                "record_id": "row-3",
                "document_no": "INV-3",
                "reconciliation_status": "unresolved",
            },
        ],
        "review_rows": [
            {
                "review_id": "review:closed",
                "record_id": "row-1",
                "document_no": "INV-1",
                "amount": "120.50",
                "deterministic_status": "closed",
                "deterministic_rule": "external_bank_match",
                "review_status": "PENDING",
                "review_selection_reason": "mandatory_closure_evidence",
                "review_instruction": "Verify source evidence.",
                "review_notes": "",
                "source_file": "open_items.xlsx",
                "source_row": "2",
            },
            {
                "review_id": "review:missing",
                "record_id": "row-2",
                "document_no": "INV-2",
                "amount": "88.00",
                "deterministic_status": "needs_evidence",
                "deterministic_rule": "payment_order_only",
                "review_status": "PENDING",
                "review_selection_reason": "risk_flag",
                "review_instruction": "Request missing evidence.",
                "review_notes": "",
            },
        ],
        "checks": [
            {"check": "row_count", "status": "PASS", "actual": 3, "expected": 3},
            {
                "check": "codex_review_complete",
                "status": "FAIL",
                "actual": "PENDING",
                "expected": "PASS",
            },
        ],
        "checks_pass": False,
        "bank_allocation_candidates": [{"record_id": "candidate-1"}],
        "account_rollforward_check": [
            {
                "account": "TOTAL",
                "account_name": "Conti confrontati",
                "status": "Difference",
                "opening_difference_journal_minus_ledger": "0.00",
                "closing_difference_journal_minus_ledger": "2236.67",
                "review_note": "Journal and ledger closing balances differ.",
            }
        ],
    }
    (output_dir / "codex_review_packet.json").write_text(
        json.dumps(result["review_rows"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    run_intake_payload = json.loads(run_intake.path.read_text(encoding="utf-8"))
    dependency_check = run_intake_payload["dependency_check"]

    session = review_session.write_review_session_artifacts(
        output_dir,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        result=result,
        source_inventory=[{"source_file": "open_items.xlsx"}],
        missing_evidence_requests_path=missing_requests,
        language="it",
    )

    review_payload = json.loads(session.review_payload_path.read_text(encoding="utf-8"))
    ui_decisions = json.loads(session.ui_decisions_path.read_text(encoding="utf-8"))
    final_artifacts = json.loads(
        session.final_artifacts_path.read_text(encoding="utf-8")
    )
    review_html = session.review_html_path.read_text(encoding="utf-8")
    artifact_card = session.artifact_card_path.read_text(encoding="utf-8")

    assert review_payload["plugin"] == "audit-reconciliation"
    assert review_payload["run_id"] == run_intake.run_id
    assert review_payload["review_type"] == "audit_reconciliation_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {
        "closure_evidence_review",
        "missing_evidence_review",
        "check_exception",
        "workpaper_artifact",
        "report_artifact",
        "evidence_request_artifact",
    } <= item_types
    assert review_payload["summary"]["reconciliation_row_count"] == 3
    assert review_payload["summary"]["failed_check_count"] == 1
    assert review_payload["summary"]["checks_pass"] is False
    assert review_payload["summary"]["rollforward_exception_count"] == 1
    assert review_payload["summary"]["rollforward_exceptions"][0] == {
        "account": "TOTAL",
        "account_name": "Conti confrontati",
        "status": "Difference",
        "opening_difference": "0.00",
        "closing_difference": "2236.67",
        "review_note": "Journal and ledger closing balances differ.",
    }
    closed_item = next(
        item for item in review_payload["items"] if item["id"] == "review:closed"
    )
    assert closed_item["data"]["target_artifact"] == "codex_review_packet.json"
    assert closed_item["data"]["target_id_field"] == "review_id"
    assert closed_item["data"]["target_record_id"] == "review:closed"
    assert closed_item["data"]["target_field"] == "review_notes"
    assert dependency_check["status"] != "not_run_by_script"
    assert "checked_at" in dependency_check
    assert "requirement_files" in dependency_check or "note" in dependency_check
    assert ui_decisions["status"] == "pending_review"
    assert session.review_html_path.name == "review_ui.html"
    assert session.artifact_card_path.name == "artifact_card.md"
    assert "window.openai = { toolOutput:" in review_html
    assert run_intake.run_id in review_html
    assert '"item_count": 7' in review_html
    assert "Review safeguards" in review_html
    assert "review-safeguards" in review_html
    assert "renderReviewSafeguards" in review_html
    assert "Execution provenance" in review_html
    assert "execution-provenance" in review_html
    assert "local_codex_workspace" in review_html
    assert "scripts/review_server.py" in artifact_card
    assert "ui_decisions.json" in artifact_card
    assert "final_artifacts.json" in artifact_card
    assert final_artifacts["status"] == "written_pending_review"
    assert any(
        "Account roll-forward has exception rows" in caveat
        for caveat in final_artifacts["caveats"]
    )
    assert any(
        output["path"] == "richieste_mirate_evidenze.xlsx"
        for output in final_artifacts["outputs"]
    )
    packet_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "codex_review_packet.json"
    )
    assert packet_output["required_columns"] == ["review_id", "review_notes"]
    audit_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "riconciliazione_audit.xlsx"
    )
    accountant_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "scheda_operativa_commercialista.xlsx"
    )
    word_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "relazione_riconciliazione_audit.docx"
    )
    assert audit_output["artifact_role"] == "audit_workpaper"
    assert audit_output["required_sheets"] == [
        "Indice",
        "Assunzioni",
        "Dettaglio riconciliazione",
        "Sintesi",
        "Controlli",
        "Revisione Codex",
    ]
    assert "required_sheets" in audit_output["qa_checks"]
    assert audit_output["required_sheet_headers"] == {
        "Indice": ["Foglio", "Righe"],
        "Assunzioni": ["Campo", "Valore"],
    }
    assert audit_output["required_cells"] == {
        "Indice": {
            "A1": "Foglio",
            "B1": "Righe",
            "A2": "Assunzioni",
            "A5": "Dettaglio riconciliazione",
        },
        "Assunzioni": {
            "A1": "Campo",
            "B1": "Valore",
            "A2": "Currency",
            "B2": "EUR",
        },
        "Dettaglio riconciliazione": {
            "A1": "Documento",
            "A2": "INV-1",
            "C1": "ID riga",
            "C2": "row-1",
        },
    }
    assert "required_sheet_headers" in audit_output["qa_checks"]
    assert "required_cells" in audit_output["qa_checks"]
    assert accountant_output["artifact_role"] == "accountant_workbook"
    assert accountant_output["required_sheets"] == [
        "Legenda",
        "Scheda operativa",
        "Dettaglio riscontri",
    ]
    assert accountant_output["required_sheet_headers"] == {
        "Legenda": ["campo", "valore"],
        "Scheda operativa": [
            "id dettaglio",
            "partita",
            "stato riscontro",
            "azione richiesta",
        ],
        "Dettaglio riscontri": [
            "id dettaglio",
            "partita",
            "tipo evidenza",
            "riferimento fonte",
        ],
    }
    assert accountant_output["required_cells"] == {
        "Legenda": {
            "A1": "campo",
            "B1": "valore",
            "A3": "Righe",
            "B3": "3",
        },
        "Scheda operativa": {
            "A1": "id dettaglio",
            "B1": "partita",
            "A2": "R0001",
            "B2": "INV-1",
        },
        "Dettaglio riscontri": {"A1": "id dettaglio", "B1": "partita"},
    }
    assert "required_cells" in accountant_output["qa_checks"]
    assert word_output["artifact_role"] == "word_report"
    assert word_output["required_text"] == required_word_text
    assert "word_document_xml" in word_output["qa_checks"]
    assert "required_text" in word_output["qa_checks"]
    assert any(
        output["path"] == "review_ui.html" for output in final_artifacts["outputs"]
    )
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()
    assert any(
        output["path"] == "artifact_card.md" for output in final_artifacts["outputs"]
    )
    review_handoff = final_artifacts["review_handoff"]
    assert review_handoff["primary"] == "local_browser_server"
    assert review_handoff["status"] == "browser_review_required"
    assert review_handoff["required_before_final_delivery"] is True
    assert review_handoff["server"]["script"] == "scripts/review_server.py"
    assert review_handoff["server"]["host"] == "127.0.0.1"
    assert review_handoff["server"]["port"] == "auto"
    assert review_handoff["server"]["opens"] == "system_browser"
    assert review_handoff["server"]["required"] is True
    assert "scripts/review_server.py" in review_handoff["server"]["command"]
    assert review_handoff["server"]["writes"] == [
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert review_handoff["artifact_card"] == {
        "path": "artifact_card.md",
        "required": True,
        "announce_to_user": True,
    }
    assert review_handoff["mcp"]["status"] == "optional_integrated_surface"
    assert review_handoff["mcp"]["tool_sequence"] == [
        "validate_audit_reconciliation_review",
        "render_audit_reconciliation_review",
    ]
    assert review_handoff["fallback"]["artifact"] == "review_ui.html"
    assert review_handoff["fallback"]["persistence"] == "copy_or_download_json"
    assert (
        "Open the browser review server with scripts/review_server.py"
        in final_artifacts["next_actions"][0]
    )
    assert (
        "Use the browser page to save or apply decisions"
        in final_artifacts["next_actions"][1]
    )


def _write_review_server_fixture(output_dir: Path) -> None:
    output_dir.mkdir()
    (output_dir / "codex_review_packet.json").write_text(
        json.dumps(
            [
                {
                    "review_id": "review:closed",
                    "record_id": "row-1",
                    "document_no": "INV-1",
                    "review_notes": "",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    review_payload = {
        "schema_version": "1.0",
        "plugin": "audit-reconciliation",
        "workflow": "audit-reconciliation",
        "run_id": "audit-reconciliation-test-run",
        "review_type": "audit_reconciliation_review",
        "source_paths": ["open_items.xlsx"],
        "items": [
            {
                "id": "review:closed",
                "item_type": "closure_evidence_review",
                "title": "INV-1 | 120.50 | closed",
                "source_path": "open_items.xlsx; row 2",
                "output_path": "codex_review_packet.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [],
                "data": {
                    "target_artifact": "codex_review_packet.json",
                    "target_id_field": "review_id",
                    "target_record_id": "review:closed",
                    "target_field": "review_notes",
                },
                "status": "needs_review",
            },
            {
                "id": "review:missing",
                "item_type": "missing_evidence_review",
                "title": "INV-2 | 88.00 | needs evidence",
                "source_path": "open_items.xlsx; row 3",
                "output_path": "richieste_mirate_evidenze.xlsx",
                "allowed_actions": ["accept", "request_more_documents", "skip"],
                "recommended_action": "request_more_documents",
                "evidence": [],
                "data": {"target_artifact": "richieste_mirate_evidenze.xlsx"},
                "status": "needs_review",
            },
        ],
        "item_count": 2,
        "columns": [],
        "evidence": {},
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {"review_item_count": 2},
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "audit-reconciliation",
        "workflow": "audit-reconciliation",
        "run_id": "audit-reconciliation-test-run",
        "created_at": "2026-01-01T00:00:00Z",
        "language": "it",
        "input_paths": ["open_items.xlsx"],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "audit_reconciliation_review",
        "assumptions": {},
        "unresolved_questions": [],
        "dependency_check": {"status": "not_run"},
        "data_posture": {
            "local_files_read": ["open_items.xlsx"],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
        "execution_trace": [
            {
                "step_id": "audit_reconciliation_run",
                "kind": "deterministic_review_session",
                "status": "passed",
                "execution_location": "local_codex_workspace",
                "command": [
                    "python",
                    "plugins/audit-reconciliation/scripts/raw_input_runner.py",
                ],
                "inputs": ["open_items.xlsx"],
                "outputs": [
                    "review_payload.json",
                    "artifact_card.md",
                    "codex_review_packet.json",
                    "final_artifacts.json",
                ],
            }
        ],
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "audit-reconciliation",
        "workflow": "audit-reconciliation",
        "run_id": "audit-reconciliation-test-run",
        "decided_at": None,
        "decision_source": "not_collected",
        "review_payload_path": "review_payload.json",
        "decisions": [],
        "decision_count": 0,
        "status": "pending_review",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "audit-reconciliation",
        "workflow": "audit-reconciliation",
        "run_id": "audit-reconciliation-test-run",
        "outputs": [{"path": "artifact_card.md", "kind": "md", "status": "written"}],
        "review_handoff": {
            "primary": "local_browser_server",
            "artifact_card": {"path": "artifact_card.md", "required": True},
        },
        "caveats": [],
        "next_actions": [],
        "status": "written_pending_review",
    }
    (output_dir / "artifact_card.md").write_text(
        "# Audit Reconciliation Review\n",
        encoding="utf-8",
    )
    for name, payload in {
        "run_intake.json": run_intake,
        "review_payload.json": review_payload,
        "ui_decisions.json": ui_decisions,
        "final_artifacts.json": final_artifacts,
    }.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def test_review_server_saves_local_browser_decisions(tmp_path: Path) -> None:
    review_server = load_review_server()
    output_dir = tmp_path / "out"
    _write_review_server_fixture(output_dir)

    result = review_server.save_decisions(
        output_dir,
        {
            "decisions": [
                {
                    "item_id": "review:closed",
                    "action": "accept",
                    "reviewer_note": "Evidence checked.",
                }
            ],
            "decision_source": "mcp_widget",
        },
    )

    saved = json.loads((output_dir / "ui_decisions.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["persisted"] is True
    assert saved["decision_source"] == "local_review_server"
    assert saved["decision_count"] == 1
    assert saved["item_count"] == 2
    assert saved["status"] == "partial_review"
    assert saved["decisions"][0]["status"] == "accepted"


def test_review_server_renders_local_browser_bridge(tmp_path: Path) -> None:
    review_server = load_review_server()
    output_dir = tmp_path / "out"
    _write_review_server_fixture(output_dir)

    html = review_server.render_review_html(output_dir)

    assert "/api/call-tool" in html
    assert "async callTool" in html
    assert '"can_persist": true' in html
    assert '"fallback": "local_review_server"' in html
    assert "audit_reconciliation_review" in html
    assert "Review safeguards" in html
    assert "review-safeguards" in html
    assert "renderReviewSafeguards" in html
    assert "safeguardLocalExecution" in html
    assert "safeguardExternalApproval" in html
    assert "safeguardBoundedPayload" in html
    assert "safeguardDecisionPersistence" in html
    assert "safeguardFinalArtifacts" in html
    assert "Execution provenance" in html
    assert "execution-provenance" in html
    assert '"execution_location": "local_codex_workspace"' in html


def test_review_server_applies_local_browser_decisions(tmp_path: Path) -> None:
    review_server = load_review_server()
    output_dir = tmp_path / "out"
    _write_review_server_fixture(output_dir)

    result = review_server.apply_decisions(
        output_dir,
        {
            "decisions": [
                {
                    "item_id": "review:closed",
                    "action": "edit",
                    "edit_value": "Reviewer confirmed external bank support.",
                },
                {"item_id": "review:missing", "action": "accept"},
            ],
        },
    )

    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert result["ok"] is True
    assert result["application_status"] == "final_ready"
    assert result["run_intake_path"] == (output_dir / "run_intake.json").as_posix()
    assert applied["decision_source"] == "local_review_server"
    assert applied["decision_count"] == 2
    assert applied["blocker_count"] == 0
    assert applied["structured_update_count"] == 1
    assert applied["structured_update_paths"] == ["codex_review_packet.json"]
    assert applied["effects"][0]["structured_update"] == {
        "id_field": "review_id",
        "record_id": "review:closed",
        "target_field": "review_notes",
        "records_key": "",
        "updated_rows": 1,
    }
    packet = json.loads(
        (output_dir / "codex_review_packet.json").read_text(encoding="utf-8")
    )
    assert packet[0]["review_notes"] == "Reviewer confirmed external bank support."
    assert final_artifacts["status"] == "final_ready"
    assert final_artifacts["review_handoff"]["primary"] == "local_browser_server"
    assert final_artifacts["review_application"]["decision_count"] == 2
    assert final_artifacts["review_application"]["structured_update_count"] == 1
    packet_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "codex_review_packet.json"
    )
    assert packet_output["status"] == "updated_from_review"
    assert packet_output["required_columns"] == ["review_id", "review_notes"]
    assert any(
        output["path"] == "applied_decisions.json"
        for output in final_artifacts["outputs"]
    )
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_apply_steps = [
        step
        for step in run_intake["execution_trace"]
        if step["kind"] == "deterministic_review_apply"
    ]
    assert len(review_apply_steps) == 1
    assert {
        "applied_decisions.json",
        "codex_review_packet.json",
        "final_artifacts.json",
        "ui_decisions.json",
    } <= set(review_apply_steps[0]["outputs"])
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_check_dependencies_builds_run_intake_contract() -> None:
    check_dependencies = load_check_dependencies()

    result = check_dependencies.build_dependency_check(
        explicit_files=["requirements.txt"]
    )

    assert result["status"] in {"ok", "missing_dependencies"}
    assert result["command"] == (
        "python scripts/check_dependencies.py --requirements requirements.txt"
    )
    assert result["requirement_files"] == ["requirements.txt"]
    assert "checked_at" in result
    assert result["checked_count"] == len(result["checked"])
    assert result["missing_count"] == len(result["missing"])


def test_raw_input_runner_rejects_git_workspace_output_dir(tmp_path: Path) -> None:
    raw_input_runner = load_raw_input_runner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    blocked_output_dir = ROOT / "out" / "audit-reconciliation-test"

    with pytest.raises(ValueError, match="outside the Git workspace"):
        raw_input_runner.extract_normalized_records(
            input_dir,
            output_dir=blocked_output_dir,
        )


def test_audit_reconciliation_mcp_server_validates_and_renders_review_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "audit-reconciliation",
        "workflow": "audit-reconciliation",
        "run_id": "audit-reconciliation-test-run",
        "review_type": "audit_reconciliation_review",
        "items": [
            {
                "id": "review:closed",
                "item_type": "closure_evidence_review",
                "title": "INV-1 | 120.50 | closed",
                "source_path": "open_items.xlsx; row 2",
                "output_path": "codex_review_packet.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [
                    {
                        "kind": "deterministic_classification",
                        "status": "closed",
                        "rule": "external_bank_match",
                    }
                ],
                "data": {"review_status": "PENDING"},
                "status": "needs_review",
            },
            {
                "id": "check-1",
                "item_type": "check_exception",
                "title": "codex_review_complete",
                "output_path": "run_manifest.json",
                "allowed_actions": ["accept", "reject", "mark_unclear", "skip"],
                "recommended_action": "reject",
                "evidence": [{"kind": "deterministic_check", "status": "FAIL"}],
                "data": {"status": "FAIL"},
                "status": "needs_review",
            },
        ],
        "item_count": 2,
        "columns": [],
        "evidence": {},
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "reconciliation_row_count": 3,
            "review_row_count": 1,
            "failed_check_count": 1,
            "reconciliation_status_counts": {"closed": 1, "unresolved": 2},
        },
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "validate_audit_reconciliation_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "render_audit_reconciliation_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "ui://widget/audit-reconciliation-review.html"},
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    instructions = responses[1]["result"]["instructions"]
    assert "primary visible handoff is the local browser review server" in instructions
    assert "scripts/review_server.py" in instructions
    assert "artifact_card.md" in instructions
    assert "optional integrated Codex review surface" in instructions
    assert "review_payload_path" in instructions
    assert "openai/outputTemplate" in instructions
    assert "static fallback" in instructions
    tool_names = {tool["name"] for tool in responses[2]["result"]["tools"]}
    assert {
        "validate_audit_reconciliation_review",
        "render_audit_reconciliation_review",
    } <= tool_names
    validate_result = responses[3]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    assert "scripts/review_server.py" in validate_result["message"]
    assert "artifact_card.md" in validate_result["message"]
    render_result = responses[4]["result"]
    assert render_result["structuredContent"]["widget_type"] == (
        "audit_reconciliation_review"
    )
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/audit-reconciliation-review.html"
    )
    assert render_result["_meta"]["openai/widgetAccessible"] is True
    assert render_result["_meta"]["ui"] == {
        "resourceUri": "ui://widget/audit-reconciliation-review.html",
        "visibility": ["model"],
    }
    resource_uris = {
        resource["uri"] for resource in responses[5]["result"]["resources"]
    }
    assert "ui://widget/audit-reconciliation-review.html" in resource_uris
    widget_html = responses[6]["result"]["contents"][0]["text"]
    assert "Audit Reconciliation Review" in widget_html


def test_audit_reconciliation_mcp_server_accepts_local_review_paths(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    _write_review_server_fixture(output_dir)
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_audit_reconciliation_review",
                "arguments": {
                    "review_payload_path": str(output_dir / "review_payload.json")
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_audit_reconciliation_review",
                "arguments": {
                    "run_intake_path": str(output_dir / "run_intake.json"),
                    "review_payload_path": str(output_dir / "review_payload.json"),
                    "ui_decisions_path": str(output_dir / "ui_decisions.json"),
                    "final_artifacts_path": str(output_dir / "final_artifacts.json"),
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "save_audit_reconciliation_decisions",
                "arguments": {
                    "run_intake_path": str(output_dir / "run_intake.json"),
                    "review_payload_path": str(output_dir / "review_payload.json"),
                    "decisions": [
                        {"item_id": "review:closed", "action": "accept"},
                    ],
                },
            },
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    assert "review_payload_path" in validate_result["message"]
    render_result = responses[3]["result"]["structuredContent"]
    assert render_result["review_payload"]["run_id"] == "audit-reconciliation-test-run"
    assert render_result["decision_policy"]["can_persist"] is True
    save_result = responses[4]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    saved = json.loads((output_dir / "ui_decisions.json").read_text(encoding="utf-8"))
    assert saved["decision_count"] == 1
    assert saved["decisions"][0]["item_id"] == "review:closed"


def test_skill_mentions_browser_review_and_mcp_tools() -> None:
    skill_text = (
        PLUGIN_ROOT / "skills" / "audit-reconciliation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["apps"] == "./.app.json"
    assert "scripts/review_server.py" in skill_text
    assert "artifact_card.md" in skill_text
    assert "local browser review server" in skill_text
    assert "review surface" in skill_text
    assert "validate_audit_reconciliation_review" in skill_text
    assert "render_audit_reconciliation_review" in skill_text
    assert "review_payload_path" in skill_text
    assert "MCP render is no longer the primary" in skill_text
    assert "Do not treat `review_ui.html`, Markdown summaries" in skill_text
    assert "ui_decisions.json" in skill_text

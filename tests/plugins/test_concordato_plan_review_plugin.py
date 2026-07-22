from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from docx import Document

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "plugins" / "concordato-plan-review" / "scripts"
CORE_PATH = SCRIPT_DIR / "concordato_plan_core.py"
MCP_SERVER_PATH = ROOT / "plugins" / "concordato-plan-review" / "mcp" / "server.cjs"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("concordato_plan_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _save_workbook(path: Path, rows: list[list[Any]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Dati"
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Concordato MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def _docx_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_parse_amount_token_handles_italian_amounts_and_dates() -> None:
    core = load_core()

    assert core.parse_amount_token("1.234.567,89") == 1234567.89
    assert core.parse_amount_token("(2.500,00)") == -2500
    assert core.parse_amount_token("31.03.2026") is None


def test_run_concordato_review_writes_candidate_workpapers(tmp_path: Path) -> None:
    core = load_core()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _save_workbook(
        input_dir / "ExampleCo piano CP_2026.05.25.xlsx",
        [
            ["Voce", "Importo"],
            ["Debiti tributari entro 12 mesi", 4124413.15],
            ["Assunzione prospettica non storica", 999999.99],
        ],
    )
    _save_workbook(
        input_dir / "DB_31.03.2026_21052026.xlsx",
        [
            ["Voce", "Saldo rettificato"],
            ["Debiti tributari entro 12 mesi", 4124413.15],
        ],
    )

    run = core.run_concordato_review(
        input_dir,
        output_dir,
        reference_date="2026-03-31",
        language="it",
        document_language="it",
        tolerance=0.01,
    )

    audit = json.loads((output_dir / "run_audit.json").read_text(encoding="utf-8"))
    matches = (output_dir / "exact_amount_matches.csv").read_text(encoding="utf-8")

    assert run.audit["candidate_match_count"] == 1
    assert audit["deterministic_boundary"].startswith("Inventory, extraction")
    assert "candidate_amount_match" in matches
    assert (output_dir / "concordato_tie_out_workpaper.xlsx").exists()
    assert (output_dir / "concordato_review_summary.docx").exists()
    assert (output_dir / "review_packet.md").exists()
    assert (output_dir / "run_intake.json").exists()
    assert (output_dir / "review_payload.json").exists()
    assert (output_dir / "ui_decisions.json").exists()
    assert (output_dir / "final_artifacts.json").exists()

    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert review_payload["plugin"] == "concordato-plan-review"
    assert review_payload["review_type"] == "concordato_plan_support_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {
        "source_inventory",
        "candidate_amount_match",
        "unmatched_plan_amount",
        "review_artifact",
        "codex_review_memo",
    } <= item_types
    assert review_payload["summary"]["candidate_match_count"] == 1
    assert review_payload["summary"]["unmatched_plan_amount_count"] == 1
    unmatched_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "unmatched_plan_amount"
    )
    assert unmatched_item["recommended_action"] == "request_more_documents"
    assert unmatched_item["data"]["requested_document"].startswith(
        "Support document or explanatory schedule for concordato plan amount "
    )
    assert (
        unmatched_item["data"]["required_document"]
        == unmatched_item["data"]["requested_document"]
    )
    assert unmatched_item["data"]["reason"] == (
        "No deterministic support amount matched this plan amount within tolerance."
    )
    assert unmatched_item["data"]["source_file"] == "ExampleCo piano CP_2026.05.25.xlsx"
    assert unmatched_item["data"]["amount"] == "999,999.99"
    assert (
        unmatched_item["evidence"][0]["requested_document"]
        == unmatched_item["data"]["requested_document"]
    )

    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    assert ui_decisions["decision_source"] == "not_collected"
    assert ui_decisions["status"] == "pending_review"

    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final_artifacts["run_id"] == review_payload["run_id"]
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_concordato_plan_review" in handoff_text
    assert "apply_concordato_plan_decisions" in handoff_text
    review_packet_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_packet.md"
    )
    assert review_packet_output["required_text"] == [
        "# Concordato plan review packet",
        "## Deterministic counts",
        "## Codex review required",
    ]
    workpaper_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "concordato_tie_out_workpaper.xlsx"
    )
    assert workpaper_output["required_sheets"] == [
        "Inventory",
        "Amount candidates",
        "Candidate matches",
    ]
    assert workpaper_output["required_sheet_headers"] == {
        "Inventory": [
            "path",
            "relative_path",
            "name",
            "suffix",
            "size_bytes",
            "supported",
            "suggested_role",
        ],
        "Amount candidates": [
            "source_file",
            "source_role",
            "location",
            "amount",
            "token",
            "context",
        ],
        "Candidate matches": [
            "plan_source_file",
            "plan_location",
            "plan_amount",
            "plan_context",
            "support_source_file",
            "support_role",
            "support_location",
            "support_amount",
            "support_context",
            "difference",
            "abs_difference",
            "context_token_overlap",
            "match_status",
        ],
    }
    assert workpaper_output["required_cells"] == {
        "Inventory": {
            "B1": "relative_path",
            "B2": "DB_31.03.2026_21052026.xlsx",
            "C1": "name",
            "C2": "DB_31.03.2026_21052026.xlsx",
            "G1": "suggested_role",
            "G2": "adjusted_db",
        },
        "Amount candidates": {
            "A1": "source_file",
            "A2": "DB_31.03.2026_21052026.xlsx",
            "B1": "source_role",
            "B2": "adjusted_db",
            "C1": "location",
            "C2": "Dati!B2",
            "D1": "amount",
            "D2": "4124413.15",
        },
        "Candidate matches": {
            "A1": "plan_source_file",
            "A2": "ExampleCo piano CP_2026.05.25.xlsx",
            "C1": "plan_amount",
            "C2": "4124413.15",
            "E1": "support_source_file",
            "E2": "DB_31.03.2026_21052026.xlsx",
            "H1": "support_amount",
            "H2": "4124413.15",
            "M1": "match_status",
            "M2": "candidate_amount_match",
        },
    }
    assert "required_sheet_headers" in workpaper_output["qa_checks"]
    assert "required_cells" in workpaper_output["qa_checks"]
    exact_matches_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "exact_amount_matches.csv"
    )
    assert exact_matches_output["row_count"] == run.audit["candidate_match_count"]
    assert exact_matches_output["required_columns"] == [
        "plan_amount",
        "support_amount",
        "difference",
        "match_status",
    ]
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()

    document = Document(output_dir / "concordato_review_summary.docx")
    document_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "battono per importo" in document_text
    assert "non battono" in document_text


def test_concordato_request_more_documents_prefills_blocker_context(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _save_workbook(
        input_dir / "ExampleCo piano CP_2026.05.25.xlsx",
        [
            ["Voce", "Importo"],
            ["Debiti tributari entro 12 mesi", 4124413.15],
            ["Assunzione prospettica non storica", 999999.99],
        ],
    )
    _save_workbook(
        input_dir / "DB_31.03.2026_21052026.xlsx",
        [
            ["Voce", "Saldo rettificato"],
            ["Debiti tributari entro 12 mesi", 4124413.15],
        ],
    )

    core.run_concordato_review(
        input_dir,
        output_dir,
        reference_date="2026-03-31",
        language="it",
        document_language="it",
        tolerance=0.01,
    )
    run_intake = json.loads((output_dir / "run_intake.json").read_text())
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    final_artifacts = json.loads((output_dir / "final_artifacts.json").read_text())
    unmatched_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "unmatched_plan_amount"
    )

    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "apply_concordato_plan_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": unmatched_item["id"],
                            "action": "request_more_documents",
                            "reviewer_note": "Ask for support of the unmatched plan amount.",
                        }
                    ],
                    "decision_source": "pytest_unmatched_plan_request",
                    "reviewer": "pytest",
                },
            },
        }
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}
    payload = responses[1]["result"]["structuredContent"]
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    updated_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    expected_document = unmatched_item["data"]["requested_document"]

    assert payload["ok"] is True
    assert payload["application_status"] == "blocked"
    assert applied["effects"][0]["requested_documents"] == [expected_document]
    assert applied["effects"][0]["followup_context"]["source_file"] == (
        unmatched_item["data"]["source_file"]
    )
    assert applied["effects"][0]["followup_context"]["source_table"] == (
        unmatched_item["data"]["source_table"]
    )
    assert applied["effects"][0]["followup_context"]["amount"] == "999,999.99"
    assert updated_final["blockers"][0]["requested_documents"] == [expected_document]
    assert updated_final["blockers"][0]["followup_context"]["reason"] == (
        "No deterministic support amount matched this plan amount within tolerance."
    )


def test_skill_and_scripts_keep_report_builder_out_of_the_workflow() -> None:
    skill_text = (
        ROOT
        / "plugins"
        / "concordato-plan-review"
        / "skills"
        / "concordato-plan-review"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DIR.glob("*.py")
    )

    assert "This is not a general report builder" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "requirements" in skill_text.lower()
    assert "generated ZIPs" in skill_text
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "validate_concordato_plan_review" in skill_text
    assert "render_concordato_plan_review" in skill_text
    assert "report-builder" not in script_text
    assert "modules.llm" not in script_text
    assert "model_router" not in script_text


def test_static_page_exposes_concordato_specific_outputs() -> None:
    page = (
        ROOT / "static" / "shared" / "concordato-plan-review" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Revisione numeri di piano",
        "Controlla i numeri del piano",
        "exact_amount_matches.csv",
        "concordato_tie_out_workpaper.xlsx",
        "concordato_review_summary.docx",
        "codex_run_review.md",
        "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d",
        "Concordato Plan Review",
        "Révision du plan de concordat",
        "Concordato-Plan prüfen",
        "Installa Vera dal marketplace",
        "Install Vera from the marketplace",
    ):
        assert snippet in page


def test_concordato_mcp_server_validates_and_renders_review_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "concordato-plan-review",
        "workflow": "concordato-plan-review",
        "run_id": "concordato-test-run",
        "review_type": "concordato_plan_support_review",
        "items": [
            {
                "id": "source-1",
                "item_type": "source_inventory",
                "title": "piano.xlsx",
                "source_path": "/tmp/piano.xlsx",
                "output_path": None,
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [],
                "data": {"suggested_role": "concordato_plan"},
                "status": "needs_review",
            },
            {
                "id": "unmatched-plan-amount-1",
                "item_type": "unmatched_plan_amount",
                "title": "piano.xlsx Dati!B3 999,999.99",
                "source_path": "piano.xlsx",
                "output_path": "amount_candidates.csv",
                "allowed_actions": [
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ],
                "recommended_action": "request_more_documents",
                "evidence": [{"kind": "plan_context", "text": "Assunzione"}],
                "data": {
                    "amount": 999999.99,
                    "match_status": "no_candidate_amount_match",
                },
                "status": "needs_review",
            },
        ],
        "item_count": 2,
        "columns": [],
        "evidence": {},
        "allowed_actions": [
            "accept",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "file_count": 1,
            "plan_amount_candidate_count": 1,
            "unmatched_plan_amount_count": 1,
        },
    }
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_concordato_plan_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_concordato_plan_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/concordato-plan-review.html"},
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert render_result["structuredContent"]["widget_type"] == "concordato_plan_review"
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/concordato-plan-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/concordato-plan-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "Concordato Plan Review" in widget_html


def test_concordato_mcp_apply_creates_codex_review_memo_from_edit(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "concordato"
    output_dir.mkdir()
    run_intake = {
        "schema_version": "1.0",
        "plugin": "concordato-plan-review",
        "workflow": "concordato-plan-review",
        "run_id": "concordato-apply-test-run",
        "created_at": "2026-01-01T00:00:00Z",
        "language": "it",
        "input_paths": [tmp_path.as_posix()],
        "output_dir": output_dir.as_posix(),
        "inferred_task": "concordato_plan_support_review",
        "assumptions": {},
        "unresolved_questions": [],
        "dependency_check": {"status": "not_run"},
        "data_posture": {
            "local_files_read": [tmp_path.as_posix()],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
    }
    review_payload = {
        "schema_version": "1.0",
        "plugin": "concordato-plan-review",
        "workflow": "concordato-plan-review",
        "run_id": "concordato-apply-test-run",
        "review_type": "concordato_plan_support_review",
        "source_paths": [tmp_path.as_posix()],
        "items": [
            {
                "id": "codex-review-memo",
                "item_type": "codex_review_memo",
                "title": "Codex auditor review memo",
                "source_path": None,
                "output_path": "codex_run_review.md",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "mark_unclear",
                "evidence": [],
                "data": {
                    "path": "codex_run_review.md",
                    "exists": False,
                    "review_note": "Codex writes this memo after review.",
                },
                "status": "needs_review",
            }
        ],
        "item_count": 1,
        "columns": [],
        "evidence": {"codex_review_memo": "codex_run_review.md"},
        "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
        "status": "ready_for_review",
        "summary": {"file_count": 1},
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "concordato-plan-review",
        "workflow": "concordato-plan-review",
        "run_id": "concordato-apply-test-run",
        "outputs": [
            {
                "path": "concordato_review_summary.docx",
                "kind": "docx",
                "status": "written",
            }
        ],
        "caveats": [],
        "next_actions": [],
        "status": "written_pending_review",
    }
    _write_docx(
        output_dir / "concordato_review_summary.docx",
        [
            "Revisione piano concordato - sintesi tie-out",
            "Conclusione operativa",
            "Da spiegare nel memo del revisore",
        ],
    )
    (output_dir / "run_intake.json").write_text(
        json.dumps(run_intake, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "review_payload.json").write_text(
        json.dumps(review_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "final_artifacts.json").write_text(
        json.dumps(final_artifacts, indent=2) + "\n",
        encoding="utf-8",
    )
    memo_text = (
        "# Codex review memo\n\n"
        "Il piano batte per importo su una voce e richiede evidenza per "
        "l'assunzione prospettica."
    )
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "apply_concordato_plan_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "codex-review-memo",
                            "action": "edit",
                            "edit_value": memo_text,
                            "reviewer_note": "Use this memo for handoff.",
                        }
                    ],
                },
            },
        }
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    payload = responses[1]["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["application_status"] == "final_ready"
    assert payload["target_update_count"] == 1
    assert payload["native_regeneration_count"] == 0
    assert payload["native_regenerated_count"] == 1
    assert payload["run_intake_path"] == str(output_dir / "run_intake.json")
    assert (output_dir / "codex_run_review.md").read_text(encoding="utf-8") == memo_text
    updated_docx_text = _docx_text(output_dir / "concordato_review_summary.docx")
    assert "Memo revisore Codex" in updated_docx_text
    assert "Il piano batte per importo su una voce" in updated_docx_text
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["target_update_paths"] == ["codex_run_review.md"]
    assert applied["effects"][0]["artifact_update"] == "target_artifact_created"
    assert applied["effects"][0]["promoted_from_revision"].startswith(
        "revisions/codex_run_review__codex-review-memo"
    )
    assert applied["effects"][0]["native_regeneration_status"] == "regenerated"
    assert applied["native_regenerated_paths"] == ["concordato_review_summary.docx"]
    updated_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert updated_final["review_application"]["target_update_paths"] == [
        "codex_run_review.md"
    ]
    memo_output = next(
        output
        for output in updated_final["outputs"]
        if output["path"] == "codex_run_review.md"
    )
    assert memo_output["status"] == "updated_from_review"
    summary_output = next(
        output
        for output in updated_final["outputs"]
        if output["path"] == "concordato_review_summary.docx"
    )
    assert summary_output["status"] == "updated_from_review"
    assert summary_output["native_regenerated"] is True
    assert "Memo revisore Codex" in summary_output["required_text"]
    assert (
        "Il piano batte per importo su una voce" in summary_output["required_text"][2]
    )
    assert updated_final["review_application"]["native_regenerated_paths"] == [
        "concordato_review_summary.docx"
    ]
    updated_run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_apply_steps = [
        step
        for step in updated_run_intake["execution_trace"]
        if step["kind"] == "deterministic_review_apply"
    ]
    assert len(review_apply_steps) == 1
    assert {
        "applied_decisions.json",
        "codex_run_review.md",
        "concordato_review_summary.docx",
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

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "plugins" / "check-entries" / "scripts"
CORE_PATH = SCRIPT_DIR / "check_entries_core.py"
MCP_SERVER_PATH = ROOT / "plugins" / "check-entries" / "mcp" / "server.cjs"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_entries_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _save_workbook(path: Path, rows: list[list[Any]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row_idx, row in enumerate(rows, start=1):
        for col_idx, value in enumerate(row, start=1):
            sheet.cell(row=row_idx, column=col_idx, value=value)
    workbook.save(path)


def _fatturapa_xml(
    *,
    number: str = "INV-42",
    invoice_date: str = "2025-01-02",
    amount: str = "123.45",
    supplier: str = "ACME SPA",
) -> bytes:
    """Return the smallest representative FatturaPA invoice fixture."""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>{supplier}</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>09876543210</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>CLIENTE SRL</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{invoice_date}</Data><Numero>{number}</Numero><ImportoTotaleDocumento>{amount}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody>
</FatturaElettronica>
""".encode()


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Check Entries MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_plugin_inspects_entries_and_runs_deterministic_checks(
    monkeypatch: Any, tmp_path: Path
) -> None:
    core = load_core()
    journal_path = tmp_path / "entries.xlsx"
    pdf_dir = tmp_path / "pdfs"
    output_dir = tmp_path / "out"
    checks_dir = output_dir / "checks"
    pdf_dir.mkdir()
    support_pdf = pdf_dir / "support_1001.pdf"
    support_pdf.write_bytes(b"%PDF placeholder")
    _save_workbook(
        journal_path,
        [
            ["Nr. Reg", "Data", "Beneficiario", "Importo", "Descrizione"],
            ["1001", "2025-01-02", "ACME Spa", 123.45, "Invoice payment"],
        ],
    )

    def fake_extract_text(path: Path) -> str:
        assert path == support_pdf
        return "Pagamento fattura ACME Spa 02/01/2025 EUR 123,45"

    monkeypatch.setattr(core, "_extract_pdf_text", fake_extract_text)

    inspection = core.inspect_entries(
        journal_path, pdf_dir, output_dir, language="it", document_language="it"
    )
    result = core.run_entry_checks(
        journal_path,
        pdf_dir,
        checks_dir,
        output_dir / "suggested_recipe.json",
        language="it",
        document_language="it",
    )

    inspection_payload = json.loads((output_dir / "inspection.json").read_text())
    recipe_payload = json.loads((output_dir / "suggested_recipe.json").read_text())
    audit_payload = json.loads((checks_dir / "check_audit.json").read_text())
    run_intake = json.loads((checks_dir / "run_intake.json").read_text())
    review_payload = json.loads((checks_dir / "review_payload.json").read_text())
    ui_decisions = json.loads((checks_dir / "ui_decisions.json").read_text())
    final_artifacts = json.loads((checks_dir / "final_artifacts.json").read_text())
    row = result.frame.to_dicts()[0]

    assert inspection.journal["row_count"] == 1
    assert inspection_payload["language"] == "it"
    assert recipe_payload["journal"]["mapping"]["movement_number"] == "Nr. Reg"
    assert row["status"] == "ok"
    assert row["matched_pdf"] == "support_1001.pdf"
    assert row["checks_run"] == "amount,date,beneficiary"
    assert audit_payload["status_counts"] == {"ok": 1}
    assert (checks_dir / "normalized_entries.csv").exists()
    assert (checks_dir / "pdf_inventory.json").exists()
    assert (checks_dir / "check_results.csv").exists()
    assert (checks_dir / "review_notes.md").exists()
    assert run_intake["plugin"] == "check-entries"
    assert run_intake["workflow"] == "check-entries"
    assert run_intake["dependency_check"]["status"] == "not_run"
    assert journal_path.as_posix() in run_intake["data_posture"]["local_files_read"]
    assert pdf_dir.as_posix() in run_intake["data_posture"]["local_files_read"]
    assert run_intake["data_posture"]["external_connectors_used"] == []
    assert run_intake["data_posture"]["upload_paths_used"] == []
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "journal_entry_support_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {"supported_entry", "pdf_inventory", "review_artifact"} <= item_types
    supported_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "supported_entry"
    )
    assert supported_item["data"]["target_artifact"] == "check_results.csv"
    assert supported_item["data"]["target_id_field"] == "source_row"
    assert supported_item["data"]["target_record_id"] == "1"
    assert supported_item["data"]["target_field"] == "review_notes"
    assert review_payload["summary"]["ok_count"] == 1
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decision_source"] == "not_collected"
    assert final_artifacts["run_id"] == run_intake["run_id"]
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (checks_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_check_entries_review" in handoff_text
    assert "apply_check_entries_decisions" in handoff_text
    review_notes_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_notes.md"
    )
    assert review_notes_output["required_text"] == [
        "# Check Entries Review Notes",
        "## Status Counts",
        "## Review Policy",
    ]
    check_results_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "check_results.csv"
    )
    check_results_xlsx_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "check_results.xlsx"
    )
    assert check_results_output["row_count"] == audit_payload["result_row_count"]
    assert check_results_output["required_columns"] == [
        "movement_number",
        "status",
        "matched_pdf",
    ]
    assert (
        check_results_xlsx_output["source_row_count"]
        == audit_payload["result_row_count"]
    )
    assert check_results_xlsx_output["required_sheets"] == ["Sheet1"]
    assert check_results_xlsx_output["required_sheet_headers"] == {
        "Sheet1": [
            "movement_number",
            "source_row",
            "status",
            "matched_pdf",
            "checks_run",
        ]
    }
    assert check_results_xlsx_output["required_cells"] == {
        "Sheet1": {
            "A1": "movement_number",
            "A2": "1001",
            "H1": "source_row",
            "H2": "1",
            "I1": "status",
            "I2": "ok",
            "J1": "matched_pdf",
            "J2": "support_1001.pdf",
            "K1": "checks_run",
            "K2": "amount,date,beneficiary",
        }
    }
    assert "required_cells" in check_results_xlsx_output["qa_checks"]
    contract_report = validate_contract(
        checks_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_spanish_run_localizes_review_notes_and_strict_contract(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "entries.xlsx"
    support_dir = tmp_path / "support"
    output_dir = tmp_path / "output"
    support_dir.mkdir()
    _save_workbook(
        journal_path,
        [
            ["Movement", "Date", "Amount"],
            ["ES-1", "2026-01-15", 75.25],
        ],
    )

    core.run_entry_checks(
        journal_path,
        support_dir,
        output_dir,
        language="es-ES",
        document_language="en",
    )

    review_notes = (output_dir / "review_notes.md").read_text(encoding="utf-8")
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    review_notes_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_notes.md"
    )

    assert review_notes.startswith(
        "# Notas de revisión de la comprobación de asientos\n"
    )
    assert "- Idioma: es" in review_notes
    assert "## Recuento por estado" in review_notes
    assert "## Política de revisión" in review_notes
    assert review_notes_output["required_text"] == [
        "# Notas de revisión de la comprobación de asientos",
        "## Recuento por estado",
        "## Política de revisión",
    ]
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_plugin_marks_missing_support_without_model_calls(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "entries.xlsx"
    pdf_dir = tmp_path / "pdfs"
    output_dir = tmp_path / "out"
    pdf_dir.mkdir()
    _save_workbook(
        journal_path,
        [
            ["Movement", "Date", "Amount"],
            ["2001", "2025-03-10", 80],
        ],
    )

    result = core.run_entry_checks(journal_path, pdf_dir, output_dir, language="en")
    row = result.frame.to_dicts()[0]
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    missing_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "missing_support"
    )

    assert row["status"] == "missing_support"
    assert row["mismatches"] == "support_pdf"
    assert missing_item["recommended_action"] == "request_more_documents"
    assert missing_item["data"]["requested_document"] == (
        "Supporting PDF for movement 2001"
    )
    assert missing_item["data"]["reason"] == (
        "No supporting PDF matched the movement number."
    )
    assert any(
        evidence.get("kind") == "missing_document_request"
        and evidence.get("requested_document") == "Supporting PDF for movement 2001"
        for evidence in missing_item["evidence"]
    )


def test_plugin_matches_sampled_entry_from_fatturapa_zip(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "entries.xlsx"
    invoice_zip = tmp_path / "all_invoices.zip"
    output_dir = tmp_path / "out"
    _save_workbook(
        journal_path,
        [
            ["Movement", "Date", "Beneficiary", "Amount", "Description"],
            ["3001", "2025-01-02", "ACME SPA", 123.45, "Invoice INV-42"],
        ],
    )
    with zipfile.ZipFile(invoice_zip, "w") as archive:
        archive.writestr("IT01234567890_INV42.xml", _fatturapa_xml())

    inspection = core.inspect_entries(journal_path, invoice_zip, tmp_path / "inspect")
    result = core.run_entry_checks(journal_path, invoice_zip, output_dir)

    row = result.frame.to_dicts()[0]
    inventory = json.loads((output_dir / "invoice_inventory.json").read_text())
    assert len(inspection.invoices) == 1
    assert inspection.suggested_recipe["acquisition_ladder"] == [
        "fatturapa_zip",
        "authorized_connector_export",
        "targeted_pdf_fallback",
    ]
    assert row["status"] == "ok"
    assert row["support_type"] == "fatturapa_xml"
    assert row["matched_support"] == "IT01234567890_INV42.xml"
    assert row["matched_pdf"] is None
    assert set(row["checks_run"].split(",")) == {
        "invoice_number",
        "amount",
        "date",
        "beneficiary",
    }
    assert inventory["invoice_count"] == 1
    assert inventory["errors"] == []


def test_plugin_records_authorized_connector_and_requests_targeted_fallback(
    tmp_path: Path,
) -> None:
    core = load_core()
    journal_path = tmp_path / "entries.xlsx"
    connector_export = tmp_path / "connector_export"
    output_dir = tmp_path / "out"
    connector_export.mkdir()
    _save_workbook(
        journal_path,
        [
            ["Movement", "Date", "Beneficiary", "Amount", "Description"],
            ["4001", "2025-01-02", "ACME SPA", 123.45, "Supplier invoice"],
        ],
    )
    (connector_export / "invoice_a.xml").write_bytes(_fatturapa_xml(number="A"))
    (connector_export / "invoice_b.xml").write_bytes(_fatturapa_xml(number="B"))

    result = core.run_entry_checks(
        journal_path,
        connector_export,
        output_dir,
        connector_name="authorized-accounting-system",
    )

    row = result.frame.to_dicts()[0]
    run_intake = json.loads((output_dir / "run_intake.json").read_text())
    assert row["status"] == "missing_support"
    assert row["mismatches"] == "ambiguous_invoice_support"
    assert "targeted support" in row["review_notes"]
    assert run_intake["data_posture"]["external_connectors_used"] == [
        "authorized-accounting-system"
    ]
    assert run_intake["data_posture"]["external_routes_used"] == [
        {
            "route": "authorized-accounting-system",
            "destination_or_origin": "authorized-accounting-system",
            "payload_category": (
                "accounting_system_export_materialized_as_local_support"
            ),
            "network_used": True,
            "access_basis": None,
        }
    ]
    assert run_intake["assumptions"]["invoice_count"] == 2


def test_skill_and_scripts_keep_codex_as_the_review_layer() -> None:
    skill_text = (
        ROOT / "plugins" / "check-entries" / "skills" / "check-entries" / "SKILL.md"
    ).read_text(encoding="utf-8")
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DIR.glob("*.py")
    )

    assert "The user should not interact directly with CLI scripts" in skill_text
    assert "must not make direct OpenAI API calls" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "`it`, `en`, `fr`, `de`, and `es`" in skill_text
    assert "missing deterministic extraction script" in skill_text
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "validate_check_entries_review" in skill_text
    assert "render_check_entries_review" in skill_text
    assert "save_check_entries_decisions" in skill_text
    assert "apply_check_entries_decisions" in skill_text
    assert "modules.llm" not in script_text
    assert "model_router" not in script_text


def test_static_page_exposes_five_language_switch() -> None:
    page = (ROOT / "static" / "shared" / "check-entries" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        'data-lang="it"',
        'data-lang="en"',
        'data-lang="fr"',
        'data-lang="de"',
        'data-lang="es"',
        "Dalla scrittura campionata al supporto che la spiega.",
        "From a sampled entry to the document that explains it.",
        "De l'écriture échantillonnée au document qui l'explique.",
        "Von der ausgewählten Buchung zum erklärenden Beleg.",
        "Del asiento muestreado al documento que lo explica.",
        "authorized_connector_export",
        "invoice_inventory.json",
    ):
        assert snippet in page


def test_check_entries_mcp_server_validates_renders_and_saves_review_payload(
    tmp_path: Path,
) -> None:
    check_results_path = tmp_path / "check_results.csv"
    check_results_xlsx_path = tmp_path / "check_results.xlsx"
    check_results_path.write_text(
        "\n".join(
            [
                "source_row,review_notes,status,matched_pdf",
                "1,Original deterministic note,ok,support_1001.pdf",
                "2,Missing support,missing_support,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _save_workbook(
        check_results_xlsx_path,
        [
            ["source_row", "review_notes", "status", "matched_pdf"],
            [1, "Original deterministic note", "ok", "support_1001.pdf"],
            [2, "Missing support", "missing_support", None],
        ],
    )
    review_payload = {
        "schema_version": "1.0",
        "plugin": "check-entries",
        "workflow": "check-entries",
        "run_id": "check-entries-test-run",
        "source_paths": ["entries.xlsx", "support_1001.pdf"],
        "review_type": "journal_entry_support_review",
        "items": [
            {
                "id": "entry-1",
                "item_type": "supported_entry",
                "title": "1001 | 123.45 | 2025-01-02",
                "source_path": "entries.xlsx",
                "output_path": "check_results.csv",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "deterministic_checks", "checks_run": "amount"}],
                "data": {
                    "status": "ok",
                    "matched_pdf": "support_1001.pdf",
                    "target_artifact": "check_results.csv",
                    "target_id_field": "source_row",
                    "target_record_id": "1",
                    "target_field": "review_notes",
                },
                "status": "needs_review",
            },
            {
                "id": "entry-2",
                "item_type": "missing_support",
                "title": "1002 | 88.0",
                "source_path": "entries.xlsx",
                "output_path": "check_results.csv",
                "allowed_actions": [
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ],
                "recommended_action": "request_more_documents",
                "evidence": [
                    {
                        "kind": "deterministic_checks",
                        "mismatches": "support_pdf",
                        "requested_document": "support_1002.pdf",
                    }
                ],
                "data": {
                    "status": "missing_support",
                    "requested_document": "support_1002.pdf",
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
            "result_row_count": 2,
            "ok_count": 1,
            "missing_support_count": 1,
            "pdf_count": 1,
        },
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "check-entries",
        "workflow": "check-entries",
        "run_id": "check-entries-test-run",
        "created_at": "2026-01-01T00:00:00Z",
        "language": "en",
        "document_language": "en",
        "input_paths": ["entries.xlsx", "support_1001.pdf"],
        "output_dir": tmp_path.as_posix(),
        "inferred_task": "journal_entry_support_check",
        "assumptions": {},
        "unresolved_questions": [],
        "dependency_check": {"status": "not_run"},
        "data_posture": {
            "local_files_read": ["entries.xlsx", "support_1001.pdf"],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
        "execution_trace": [
            {
                "step_id": "check_entries_run",
                "kind": "deterministic_review_session",
                "status": "passed",
                "execution_location": "local_codex_workspace",
                "command": [
                    "python",
                    "plugins/check-entries/scripts/run_check_entries.py",
                ],
                "inputs": ["entries.xlsx", "support_1001.pdf"],
                "outputs": [
                    "review_payload.json",
                    "check_results.xlsx",
                    "final_artifacts.json",
                ],
            }
        ],
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "check-entries",
        "workflow": "check-entries",
        "run_id": "check-entries-test-run",
        "review_payload_path": "review_payload.json",
        "decisions": [],
        "decision_count": 0,
        "status": "pending_review",
    }
    (tmp_path / "run_intake.json").write_text(
        json.dumps(run_intake, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "review_payload.json").write_text(
        json.dumps(review_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_check_entries_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_check_entries_review",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                },
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/check-entries-review.html"},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "save_check_entries_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "decisions": [
                        {
                            "item_id": "entry-1",
                            "action": "edit",
                            "edit_value": "Reviewer confirmed support evidence.",
                        },
                        {
                            "item_id": "entry-2",
                            "action": "request_more_documents",
                            "reviewer_note": "Support file is still missing.",
                        },
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "apply_check_entries_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": {
                        "schema_version": "1.0",
                        "plugin": "check-entries",
                        "workflow": "check-entries",
                        "run_id": "check-entries-test-run",
                        "outputs": [
                            {
                                "path": "review_payload.json",
                                "kind": "json",
                                "status": "written",
                            },
                            {
                                "path": "check_results.xlsx",
                                "kind": "xlsx",
                                "status": "written",
                            },
                        ],
                        "status": "written_pending_review",
                    },
                    "decisions": [
                        {
                            "item_id": "entry-1",
                            "action": "edit",
                            "edit_value": "Reviewer confirmed support evidence.",
                        },
                        {
                            "item_id": "entry-2",
                            "action": "request_more_documents",
                            "reviewer_note": "Support file is still missing.",
                        },
                    ],
                },
            },
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_check_entries_review",
        "render_check_entries_review",
        "save_check_entries_decisions",
        "apply_check_entries_decisions",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert render_result["structuredContent"]["widget_type"] == "check_entries_review"
    assert render_result["structuredContent"]["decision_policy"]["can_persist"] is True
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/check-entries-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/check-entries-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "Check Entries Review" in widget_html
    assert "Save decisions" in widget_html
    assert "Apply decisions" in widget_html
    assert "Applica decisioni" in widget_html
    assert "Preview sample review" in widget_html
    assert "Final outputs" in widget_html
    save_result = responses[6]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 2
    assert save_result["status"] == "reviewed"
    written_decisions = json.loads((tmp_path / "ui_decisions.json").read_text())
    assert written_decisions["decision_source"] == "mcp_widget"
    assert written_decisions["status"] == "reviewed"
    assert written_decisions["decision_count"] == 2
    assert written_decisions["decisions"][0]["edit_value"] == (
        "Reviewer confirmed support evidence."
    )
    assert written_decisions["decisions"][1]["requested_documents"] == [
        "support_1002.pdf"
    ]
    assert written_decisions["decisions"][1]["followup_context"] == {
        "reason": "support_pdf"
    }
    apply_result = responses[7]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["persisted"] is True
    assert apply_result["run_intake_path"] == str(tmp_path / "run_intake.json")
    assert apply_result["decision_count"] == 2
    assert apply_result["blocker_count"] == 1
    assert apply_result["structured_update_count"] == 1
    assert apply_result["native_regeneration_count"] == 0
    assert apply_result["native_regenerated_count"] == 1
    assert apply_result["application_status"] == "blocked"
    applied = json.loads((tmp_path / "applied_decisions.json").read_text())
    assert applied["plugin"] == "check-entries"
    assert applied["effects"][0]["structured_update"] == {
        "id_field": "source_row",
        "record_id": "1",
        "target_field": "review_notes",
        "records_key": None,
        "updated_rows": 1,
    }
    assert applied["effects"][0]["derived_native_regeneration_paths"] == [
        "check_results.xlsx"
    ]
    assert applied["effects"][0]["requires_native_regeneration"] is False
    assert applied["effects"][0]["native_regeneration_status"] == "regenerated"
    assert applied["native_regeneration_paths"] == []
    assert applied["native_regenerated_paths"] == ["check_results.xlsx"]
    assert applied["effects"][1]["requires_followup"] is True
    assert applied["effects"][1]["followup_context"] == {"reason": "support_pdf"}
    assert "Reviewer confirmed support evidence." in check_results_path.read_text(
        encoding="utf-8"
    )
    workbook = openpyxl.load_workbook(check_results_xlsx_path)
    assert workbook.active["B2"].value == "Reviewer confirmed support evidence."
    final_artifacts = json.loads((tmp_path / "final_artifacts.json").read_text())
    assert final_artifacts["status"] == "blocked"
    assert final_artifacts["review_application"]["structured_update_count"] == 1
    assert final_artifacts["review_application"]["structured_update_paths"] == [
        "check_results.csv"
    ]
    assert final_artifacts["review_application"]["native_regeneration_paths"] == []
    assert final_artifacts["review_application"]["native_regenerated_paths"] == [
        "check_results.xlsx"
    ]
    outputs_by_path = {output["path"]: output for output in final_artifacts["outputs"]}
    assert outputs_by_path["check_results.xlsx"]["status"] == "updated_from_review"
    assert outputs_by_path["check_results.xlsx"]["native_regenerated"] is True
    assert outputs_by_path["check_results.xlsx"]["source_artifact"] == (
        "check_results.csv"
    )
    assert outputs_by_path["check_results.xlsx"]["source_row_count"] == 2
    assert outputs_by_path["check_results.xlsx"]["required_sheets"] == ["check_results"]
    assert outputs_by_path["check_results.xlsx"]["required_cells"] == {
        "check_results": {"B2": "Reviewer confirmed support evidence."}
    }
    assert {"ui_decisions.json", "applied_decisions.json"} <= {
        output["path"] for output in final_artifacts["outputs"]
    }
    assert {
        "check_results.csv",
        "revisions/originals/check_results__entry-1.csv",
        "revisions/originals/check_results__entry-1.xlsx",
    } <= {output["path"] for output in final_artifacts["outputs"]}
    run_intake = json.loads((tmp_path / "run_intake.json").read_text())
    review_apply_steps = [
        step
        for step in run_intake["execution_trace"]
        if step["kind"] == "deterministic_review_apply"
    ]
    assert len(review_apply_steps) == 1
    assert {
        "applied_decisions.json",
        "check_results.csv",
        "check_results.xlsx",
        "final_artifacts.json",
        "revisions/originals/check_results__entry-1.csv",
        "revisions/originals/check_results__entry-1.xlsx",
        "ui_decisions.json",
    } <= set(review_apply_steps[0]["outputs"])
    contract = validate_contract(
        tmp_path,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract.ok is True, contract.errors


@pytest.mark.parametrize(
    ("decisions", "expected_error"),
    [
        (
            [{"item_id": "missing-item", "action": "accept"}],
            "item_id is not in review_payload.items",
        ),
        (
            [{"item_id": "entry-1", "action": "edit"}],
            "edit_value is required",
        ),
        (
            [{"item_id": "entry-1", "action": "request_more_documents"}],
            "action is not allowed",
        ),
    ],
)
def test_check_entries_mcp_server_rejects_invalid_review_decisions(
    tmp_path: Path,
    decisions: list[dict[str, object]],
    expected_error: str,
) -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "check-entries",
        "workflow": "check-entries",
        "run_id": "check-entries-test-run",
        "items": [
            {
                "id": "entry-1",
                "item_type": "supported_entry",
                "title": "1001 | 123.45",
                "allowed_actions": ["accept", "edit", "skip"],
                "recommended_action": "accept",
            },
        ],
        "item_count": 1,
        "status": "ready_for_review",
    }
    run_intake = {
        "plugin": "check-entries",
        "workflow": "check-entries",
        "run_id": "check-entries-test-run",
        "output_dir": tmp_path.as_posix(),
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "save_check_entries_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": decisions,
                },
            },
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    result = responses[1]["result"]
    assert result["isError"] is True
    assert expected_error in result["structuredContent"]["error"]
    assert not (tmp_path / "ui_decisions.json").exists()

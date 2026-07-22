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
PLUGIN_ROOT = ROOT / "plugins" / "report-builder"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
CORE_PATH = SCRIPT_DIR / "report_builder_core.py"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("report_builder_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_mcp_server(
    method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    if shutil.which("node") is None:
        pytest.skip("node is required for MCP server checks")
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    completed = subprocess.run(
        ["node", str(MCP_SERVER_PATH)],
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=True,
        text=True,
    )
    responses = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip().startswith("{")
    ]
    assert responses
    response = responses[-1]
    assert "error" not in response
    return response["result"]


def test_spanish_docx_output_record_uses_spanish_required_text(
    tmp_path: Path,
) -> None:
    load_core()
    review_session = sys.modules["mparanza_report_builder_review_session"]
    (tmp_path / "report.docx").write_bytes(b"docx-placeholder")
    (tmp_path / "report_draft.md").write_text(
        "# Informe de gestión\n",
        encoding="utf-8",
    )
    analysis = {
        "language": "es",
        "sections": [{"title": "Resultados del periodo", "status": "assigned"}],
    }
    audit = {"missing_section_count": 1}

    outputs = review_session.build_output_records(tmp_path, audit, analysis)

    report = next(output for output in outputs if output["path"] == "report.docx")
    draft = next(output for output in outputs if output["path"] == "report_draft.md")
    assert report["required_text"] == [
        "Resumen ejecutivo",
        "Anexo de auditoría",
        "Estado del informe",
        "Llamadas a la API del modelo desde los scripts",
        "Secciones asignadas",
        "Secciones pendientes",
        "Resultados del periodo",
    ]
    assert draft["required_text"] == [
        "## Resumen ejecutivo",
        "## Resultados del periodo",
        "Fuente:",
        "Filas:",
    ]


def test_render_markdown_localizes_all_spanish_wrapper_copy() -> None:
    core = load_core()
    recipe = {
        "language": "es",
        "report_type": "management_report",
        "context_items": {"Moneda": "EUR"},
        "render": {"include_table_previews": False},
    }
    analysis = {
        "sections": [
            {
                "title": "Resultados",
                "status": "assigned",
                "source_file": "informe.xlsx",
                "sheet_name": "Resultados",
                "row_count": 3,
                "column_count": 2,
                "numeric_columns": [
                    {"column": "Importe", "numeric_count": 3, "sum": "250.00"}
                ],
                "preview_rows": [],
            },
            {
                "title": "Tesorería",
                "status": "unassigned",
                "numeric_columns": [],
                "preview_rows": [],
            },
        ]
    }

    markdown = core.render_markdown(recipe, analysis)

    assert markdown.startswith("# Informe de gestión")
    assert "**Entidad:** Entidad pendiente" in markdown
    assert "**Periodo:** Periodo pendiente" in markdown
    assert "## Resumen ejecutivo" in markdown
    assert "Resumen ejecutivo de Codex pendiente." in markdown
    assert "## Contexto" in markdown
    assert "La revisión de Codex está pendiente para esta sección." in markdown
    assert "Fuente: informe.xlsx / Resultados" in markdown
    assert "Filas: 3 | Columnas: 2" in markdown
    assert "Totales numéricos deterministas:" in markdown
    assert "Importe: recuento 3, suma 250.00" in markdown
    assert "Todavía no hay una tabla asignada." in markdown
    assert "Executive summary" not in markdown
    assert "Source:" not in markdown
    assert "Rows:" not in markdown


def _save_workbook(path: Path) -> None:
    workbook = openpyxl.Workbook()
    income = workbook.active
    income.title = "Income Statement"
    income.append(["Line", "Actual", "Budget"])
    income.append(["Revenue", 1000, 950])
    income.append(["Costs", -620, -600])
    income.append(["Result", 380, 350])

    balance = workbook.create_sheet("Balance Sheet")
    balance.append(["Line", "Amount"])
    balance.append(["Assets", 2000])
    balance.append(["Equity", 900])
    balance.append(["Debt", 1100])

    cash = workbook.create_sheet("Cash Flow")
    cash.append(["Line", "Amount"])
    cash.append(["Operating cash", 250])
    cash.append(["Investing cash", -50])
    workbook.save(path)


def test_plugin_inspects_and_builds_report_without_model_calls(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "report.xlsx"
    output_dir = tmp_path / "out"
    report_dir = output_dir / "report"
    _save_workbook(input_path)

    inspection = core.inspect_inputs(
        input_path,
        output_dir,
        language="en",
        document_language="auto",
        report_type="management_report",
    )
    recipe_path = output_dir / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["entity"] = "Example Ltd"
    recipe["period"] = "2025"
    recipe["executive_summary"] = "Codex reviewed the mapped tables."
    recipe["sections"]["income_statement"][
        "codex_comment"
    ] = "Revenue and result were reviewed against the income statement table."
    recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")

    result = core.build_report(
        input_path,
        report_dir,
        recipe_path=recipe_path,
        language="en",
        document_language="auto",
        report_type="management_report",
    )

    inspection_payload = json.loads((output_dir / "inspection.json").read_text())
    analysis_payload = json.loads((report_dir / "report_analysis.json").read_text())
    audit_payload = json.loads((report_dir / "report_audit.json").read_text())
    run_intake = json.loads((report_dir / "run_intake.json").read_text())
    review_payload = json.loads((report_dir / "review_payload.json").read_text())
    ui_decisions = json.loads((report_dir / "ui_decisions.json").read_text())
    final_artifacts = json.loads((report_dir / "final_artifacts.json").read_text())
    draft = (report_dir / "report_draft.md").read_text(encoding="utf-8")
    document = Document(result.docx_path)
    paragraph_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    table_text = "\n".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )

    assert inspection.inspection["table_count"] == 3
    assert inspection_payload["language"] == "en"
    assert recipe["sections"]["income_statement"]["assigned_table"]
    assert analysis_payload["assigned_section_count"] >= 3
    assert audit_payload["model_api_calls"] == 0
    assert "Revenue and result were reviewed" in draft
    assert result.docx_path.exists()
    assert "Management report" in paragraph_text
    assert "Executive summary" in paragraph_text
    assert "Audit appendix" in paragraph_text
    assert "Revenue" in table_text
    assert len(document.tables) >= 4
    assert (report_dir / "report_tables.json").exists()
    assert (report_dir / "report_tables.xlsx").exists()
    assert (report_dir / "used_recipe.json").exists()
    assert result.review_session == audit_payload["review_session"]
    assert audit_payload["review_session"]["run_id"] == run_intake["run_id"]
    assert review_payload["plugin"] == "report-builder"
    assert review_payload["workflow"] == "report-builder"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "report_builder_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert "report_section" in item_types
    assert "table_evidence" in item_types
    assert "report_artifact" in item_types
    assert review_payload["summary"]["assigned_section_count"] >= 3
    assert review_payload["summary"]["table_count"] == 3
    income_section_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "report_section"
        and item["data"]["section"] == "income_statement"
    )
    assert income_section_item["data"]["target_artifact"] == "report.docx"
    assert (
        income_section_item["data"]["target_path"]
        == "sections.income_statement.codex_comment"
    )
    assert income_section_item["data"]["target_field"] == "codex_comment"
    income_table_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "table_evidence"
        and item["data"]["section"] == "income_statement"
    )
    assert income_table_item["data"]["target_artifact"] == "report.docx"
    assert (
        income_table_item["data"]["target_path"]
        == "sections.income_statement.assigned_table"
    )
    assert income_table_item["data"]["target_field"] == "assigned_table"
    assert "report.xlsx::Cash Flow" in income_table_item["data"]["available_table_ids"]
    assert income_table_item["data"]["preview_rows"][0]["Line"] == "Revenue"
    assert income_table_item["evidence"][0]["preview_rows"][0]["Line"] == "Revenue"
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decision_count"] == 0
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (report_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_report_builder_review" in handoff_text
    assert "apply_report_builder_decisions" in handoff_text
    report_draft_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "report_draft.md"
    )
    first_section_title = analysis_payload["sections"][0]["title"]
    assert "## Executive summary" in report_draft_output["required_text"]
    assert f"## {first_section_title}" in report_draft_output["required_text"]
    assert "Source:" in report_draft_output["required_text"]
    assert "Rows:" in report_draft_output["required_text"]
    assert "required_text" in report_draft_output["qa_checks"]
    report_docx_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "report.docx"
    )
    assert "Executive summary" in report_docx_output["required_text"]
    assert "Audit appendix" in report_docx_output["required_text"]
    assert "Report status" in report_docx_output["required_text"]
    assert "Model API calls from scripts" in report_docx_output["required_text"]
    assert first_section_title in report_docx_output["required_text"]
    assert "required_text" in report_docx_output["qa_checks"]
    report_tables_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "report_tables.xlsx"
    )
    first_section_row, first_section = next(
        (
            (index, section)
            for index, section in enumerate(analysis_payload["sections"], start=2)
            if section["assigned_table"]
        )
    )
    preview_sheet = first_section["section"]
    assert report_tables_output["required_sheets"] == ["summary", preview_sheet]
    assert report_tables_output["required_sheet_headers"] == {
        "summary": ["section", "status", "assigned_table", "rows", "columns"],
        preview_sheet: ["Line", "Actual", "Budget"],
    }
    assert report_tables_output["required_cells"] == {
        "summary": {
            f"A{first_section_row}": str(first_section["section"]),
            f"B{first_section_row}": str(first_section["status"]),
            f"C{first_section_row}": str(first_section["assigned_table"]),
            f"D{first_section_row}": str(first_section["row_count"]),
            f"E{first_section_row}": str(first_section["column_count"]),
        },
        preview_sheet: {
            "A1": "Line",
            "A2": "Revenue",
            "B1": "Actual",
            "B2": "1000",
            "C1": "Budget",
            "C2": "950",
        },
    }
    assert "required_sheet_headers" in report_tables_output["qa_checks"]
    assert "required_cells" in report_tables_output["qa_checks"]
    report_tables_json_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "report_tables.json"
    )
    assert report_tables_json_output["records_key"] == "tables"
    assert report_tables_json_output["row_count"] == audit_payload["table_count"]
    assert report_tables_json_output["required_columns"] == [
        "table_id",
        "source_file",
        "row_count",
        "column_count",
    ]
    contract_report = validate_contract(
        report_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_plugin_marks_unassigned_sections_for_codex_review(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "report.xlsx"
    output_dir = tmp_path / "out"
    _save_workbook(input_path)

    result = core.build_report(
        input_path,
        output_dir,
        language="en",
        report_type="annual_financial_statement",
    )
    draft = result.markdown_path.read_text(encoding="utf-8")
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    missing_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "review_issue"
        and item["id"].startswith("missing-section-")
    )

    assert result.audit["missing_section_count"] > 0
    assert "Codex review pending for this section." in draft
    assert "request_more_documents" in missing_item["allowed_actions"]
    assert missing_item["data"]["requested_document"].startswith(
        "Source table or narrative support for report section "
    )
    assert (
        missing_item["data"]["required_document"]
        == missing_item["data"]["requested_document"]
    )
    assert missing_item["data"]["reason"] == (
        "No deterministic source table is mapped to this report section."
    )
    assert missing_item["data"]["source_table"] == "unassigned"
    assert missing_item["data"]["record_id"] == missing_item["data"]["section"]
    assert (
        missing_item["evidence"][0]["requested_document"]
        == missing_item["data"]["requested_document"]
    )


def test_report_builder_request_more_documents_prefills_blocker_context(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "report.xlsx"
    output_dir = tmp_path / "out"
    _save_workbook(input_path)

    core.build_report(
        input_path,
        output_dir,
        language="en",
        report_type="annual_financial_statement",
    )
    run_intake = json.loads((output_dir / "run_intake.json").read_text())
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    final_artifacts = json.loads((output_dir / "final_artifacts.json").read_text())
    missing_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "review_issue"
        and item["id"].startswith("missing-section-")
    )

    apply_result = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_report_builder_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": [
                    {
                        "item_id": missing_item["id"],
                        "action": "request_more_documents",
                        "reviewer_note": "Ask the client for the missing schedule.",
                    }
                ],
                "decision_source": "pytest_missing_section_request",
                "reviewer": "pytest",
            },
        },
    )

    payload = apply_result["structuredContent"]
    applied = json.loads((output_dir / "applied_decisions.json").read_text())
    updated_final = json.loads((output_dir / "final_artifacts.json").read_text())
    expected_document = missing_item["data"]["requested_document"]

    assert payload["ok"] is True
    assert payload["application_status"] == "blocked"
    assert applied["effects"][0]["requested_documents"] == [expected_document]
    assert (
        applied["effects"][0]["followup_context"]["record_id"]
        == missing_item["data"]["section"]
    )
    assert applied["effects"][0]["followup_context"]["source_table"] == "unassigned"
    assert updated_final["blockers"][0]["requested_documents"] == [expected_document]
    assert updated_final["blockers"][0]["followup_context"]["reason"] == (
        "No deterministic source table is mapped to this report section."
    )


def test_report_builder_apply_decisions_regenerates_docx_for_section_edit(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "report.xlsx"
    output_dir = tmp_path / "out"
    report_dir = output_dir / "report"
    _save_workbook(input_path)

    inspection = core.inspect_inputs(
        input_path,
        output_dir,
        language="en",
        document_language="auto",
        report_type="management_report",
    )
    recipe_path = output_dir / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["entity"] = "Example Ltd"
    recipe["period"] = "2025"
    recipe["executive_summary"] = "Codex reviewed the mapped tables."
    recipe["sections"]["income_statement"][
        "codex_comment"
    ] = "Original income statement narrative."
    recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    result = core.build_report(
        input_path,
        report_dir,
        recipe_path=recipe_path,
        language="en",
        document_language="auto",
        report_type="management_report",
    )
    assert inspection.inspection["table_count"] == 3
    review_payload = json.loads((report_dir / "review_payload.json").read_text())
    run_intake = json.loads((report_dir / "run_intake.json").read_text())
    final_artifacts = json.loads((report_dir / "final_artifacts.json").read_text())
    section_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "report_section"
        and item["data"]["section"] == "income_statement"
    )
    revised_text = "Reviewer-approved income statement narrative."
    assert revised_text not in "\n".join(
        paragraph.text for paragraph in Document(result.docx_path).paragraphs
    )

    apply_result = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_report_builder_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": [
                    {
                        "item_id": section_item["id"],
                        "action": "edit",
                        "edit_value": revised_text,
                        "reviewer_note": "Replace section narrative in native report.",
                    }
                ],
                "decision_source": "pytest_docx_regeneration",
                "reviewer": "pytest",
            },
        },
    )

    payload = apply_result["structuredContent"]
    assert payload["ok"] is True
    assert payload["application_status"] == "partial_review_applied"
    assert payload["native_regeneration_count"] == 0
    assert payload["native_regenerated_count"] == 1
    assert set(payload["applied_decisions"]["native_regenerated_paths"]) >= {
        "report.docx",
        "report_draft.md",
        "used_recipe.json",
        "report_analysis.json",
    }

    updated_recipe = json.loads((report_dir / "used_recipe.json").read_text())
    updated_analysis = json.loads((report_dir / "report_analysis.json").read_text())
    updated_draft = (report_dir / "report_draft.md").read_text(encoding="utf-8")
    updated_docx_text = "\n".join(
        paragraph.text for paragraph in Document(report_dir / "report.docx").paragraphs
    )
    applied = json.loads((report_dir / "applied_decisions.json").read_text())
    updated_final = json.loads((report_dir / "final_artifacts.json").read_text())

    assert (
        updated_recipe["sections"]["income_statement"]["codex_comment"] == revised_text
    )
    assert (
        next(
            section
            for section in updated_analysis["sections"]
            if section["section"] == "income_statement"
        )["codex_comment"]
        == revised_text
    )
    assert revised_text in updated_draft
    assert revised_text in updated_docx_text
    assert applied["effects"][0]["artifact_update"] == "native_artifact_regenerated"
    assert applied["effects"][0]["native_regeneration_status"] == "regenerated"
    assert applied["native_regeneration_count"] == 0
    assert applied["native_regenerated_count"] == 1
    assert applied["application_status"] == "partial_review_applied"
    assert updated_final["status"] == "partial_review_applied"
    report_output = next(
        output for output in updated_final["outputs"] if output["path"] == "report.docx"
    )
    assert report_output["status"] == "updated_from_review"
    assert report_output["native_regenerated"] is True
    assert "Regenerate native DOCX/XLSX/PDF outputs before final handoff." not in (
        updated_final["next_actions"]
    )
    assert (
        "Complete remaining review decisions before final handoff."
        in updated_final["next_actions"]
    )
    assert (report_dir / "revisions/originals").exists()


def test_report_builder_apply_decisions_regenerates_outputs_for_source_mapping_edit(
    tmp_path: Path,
) -> None:
    core = load_core()
    input_path = tmp_path / "report.xlsx"
    output_dir = tmp_path / "out"
    report_dir = output_dir / "report"
    _save_workbook(input_path)

    inspection = core.inspect_inputs(
        input_path,
        output_dir,
        language="en",
        document_language="auto",
        report_type="management_report",
    )
    recipe_path = output_dir / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["entity"] = "Example Ltd"
    recipe["period"] = "2025"
    recipe["executive_summary"] = "Codex reviewed the mapped tables."
    recipe["sections"]["income_statement"][
        "codex_comment"
    ] = "Income statement narrative follows the mapped source."
    recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    core.build_report(
        input_path,
        report_dir,
        recipe_path=recipe_path,
        language="en",
        document_language="auto",
        report_type="management_report",
    )
    assert inspection.inspection["table_count"] == 3

    review_payload = json.loads((report_dir / "review_payload.json").read_text())
    run_intake = json.loads((report_dir / "run_intake.json").read_text())
    final_artifacts = json.loads((report_dir / "final_artifacts.json").read_text())
    table_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "table_evidence"
        and item["data"]["section"] == "income_statement"
    )
    revised_table_id = "report.xlsx::Cash Flow"
    assert revised_table_id in table_item["data"]["available_table_ids"]

    apply_result = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_report_builder_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": [
                    {
                        "item_id": table_item["id"],
                        "action": "edit",
                        "edit_value": revised_table_id,
                        "reviewer_note": "Use the cash flow table for this section.",
                    }
                ],
                "decision_source": "pytest_source_mapping_regeneration",
                "reviewer": "pytest",
            },
        },
    )

    payload = apply_result["structuredContent"]
    updated_recipe = json.loads((report_dir / "used_recipe.json").read_text())
    updated_analysis = json.loads((report_dir / "report_analysis.json").read_text())
    updated_audit = json.loads((report_dir / "report_audit.json").read_text())
    updated_final = json.loads((report_dir / "final_artifacts.json").read_text())
    updated_draft = (report_dir / "report_draft.md").read_text(encoding="utf-8")
    workbook = openpyxl.load_workbook(report_dir / "report_tables.xlsx", data_only=True)
    income_section = next(
        section
        for section in updated_analysis["sections"]
        if section["section"] == "income_statement"
    )
    outputs_by_path = {
        output["path"]: output
        for output in updated_final["outputs"]
        if isinstance(output, dict)
    }

    assert payload["ok"] is True
    assert payload["application_status"] == "partial_review_applied"
    assert (
        updated_recipe["sections"]["income_statement"]["assigned_table"]
        == revised_table_id
    )
    assert income_section["assigned_table"] == revised_table_id
    assert income_section["sheet_name"] == "Cash Flow"
    assert income_section["row_count"] == 3
    assert "Source: report.xlsx / Cash Flow" in updated_draft
    assert updated_audit["review_native_regeneration"]["status"] == "regenerated"
    assert (
        "report_tables.xlsx" in payload["applied_decisions"]["native_regenerated_paths"]
    )
    assert workbook["summary"]["C3"].value == revised_table_id
    assert workbook["income_statement"]["A2"].value == "Operating cash"
    assert workbook["income_statement"]["B2"].value == "250"
    assert outputs_by_path["report_tables.xlsx"]["status"] == "updated_from_review"
    assert outputs_by_path["report_tables.xlsx"]["native_regenerated"] is True
    assert outputs_by_path["report_tables.xlsx"]["required_sheets"] == [
        "summary",
        "income_statement",
    ]
    assert outputs_by_path["report_tables.xlsx"]["required_sheet_headers"] == {
        "summary": ["section", "status", "assigned_table", "rows", "columns"],
        "income_statement": ["Line", "Amount"],
    }
    assert outputs_by_path["report_tables.xlsx"]["required_cells"] == {
        "summary": {
            "A3": "income_statement",
            "B3": "assigned",
            "C3": revised_table_id,
            "D3": "3",
            "E3": "2",
        },
        "income_statement": {
            "A1": "Line",
            "A2": "Operating cash",
            "B1": "Amount",
            "B2": "250",
        },
    }
    assert outputs_by_path["report_tables.json"]["row_count"] == 3
    assert (
        "report_tables.xlsx"
        in updated_final["review_application"]["native_regenerated_paths"]
    )
    contract_report = validate_contract(
        report_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_skill_and_scripts_keep_codex_as_the_narrative_layer() -> None:
    skill_text = (
        ROOT / "plugins" / "report-builder" / "skills" / "report-builder" / "SKILL.md"
    ).read_text(encoding="utf-8")
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DIR.glob("*.py")
    )

    assert "The user should not interact directly with CLI scripts" in skill_text
    assert "must not make direct OpenAI API calls" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "it`, `en`, `fr`, `de`, and `es`" in skill_text
    assert "missing deterministic extraction script" in skill_text
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "validate_report_builder_review" in skill_text
    assert "render_report_builder_review" in skill_text
    assert "ui://widget/report-builder-review.html" in skill_text
    assert "native Plan-mode" in skill_text
    assert "modules.llm" not in script_text
    assert "model_router" not in script_text
    assert "get_openai_client" not in script_text


def test_static_page_exposes_five_language_switch_and_prompts() -> None:
    page = (ROOT / "static" / "shared" / "report-builder" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        'data-lang="it"',
        'data-lang="en"',
        'data-lang="fr"',
        'data-lang="de"',
        'data-lang="es"',
        "Turn source tables into a reviewable Word report.",
        "Da tabelle sorgente a un report Word rivedibile.",
        "Transformer les tableaux source en rapport Word révisable.",
        "Quelltabellen in einen prüfbaren Word-Bericht verwandeln.",
        "Convierta tablas fuente en un informe Word revisable.",
        "Prepara una bozza DOCX da Excel, CSV e PDF leggibili.",
        "Ready prompts",
        "Prompt pronti",
        "File prodotti rivedibili",
        "Usa Genera report sui file in /percorso/report.",
        '"download.button": "Installa Vera"',
    ):
        assert snippet in page


def test_mcp_review_server_validates_and_renders_report_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "report-builder",
        "workflow": "report-builder",
        "run_id": "report-builder-test-run",
        "review_type": "report_builder_review",
        "item_count": 3,
        "items": [
            {
                "id": "report-section-1",
                "item_type": "report_section",
                "title": "Income statement (assigned)",
                "source_path": "report.xlsx::Income Statement",
                "output_path": "report_draft.md",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "section_status", "status": "assigned"}],
                "data": {},
                "status": "needs_review",
            },
            {
                "id": "table-evidence-1",
                "item_type": "table_evidence",
                "title": "Evidence table for Income statement",
                "source_path": "report.xlsx::Income Statement",
                "output_path": "report_tables.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "table_evidence"}],
                "data": {},
                "status": "needs_review",
            },
            {
                "id": "artifact-1",
                "item_type": "report_artifact",
                "title": "Word report",
                "output_path": "report.docx",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "artifact_status", "exists": True}],
                "data": {},
                "status": "needs_review",
            },
        ],
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "report-builder",
        "workflow": "report-builder",
        "run_id": "report-builder-test-run",
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "report-builder",
        "workflow": "report-builder",
        "run_id": "report-builder-test-run",
        "decisions": [],
        "status": "pending_review",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "report-builder",
        "workflow": "report-builder",
        "run_id": "report-builder-test-run",
        "outputs": [],
        "status": "written_pending_review",
    }

    tools = _call_mcp_server("tools/list")
    tool_names = {tool["name"] for tool in tools["tools"]}
    assert "validate_report_builder_review" in tool_names
    assert "render_report_builder_review" in tool_names

    validate_result = _call_mcp_server(
        "tools/call",
        {
            "name": "validate_report_builder_review",
            "arguments": {
                "review_payload": review_payload,
                "run_intake": run_intake,
                "ui_decisions": ui_decisions,
                "final_artifacts": final_artifacts,
            },
        },
    )
    validation = json.loads(validate_result["content"][0]["text"])
    assert validation["ok"] is True
    assert validation["item_count"] == 3

    render_result = _call_mcp_server(
        "tools/call",
        {
            "name": "render_report_builder_review",
            "arguments": {
                "review_payload": review_payload,
                "run_intake": run_intake,
                "ui_decisions": ui_decisions,
                "final_artifacts": final_artifacts,
            },
        },
    )
    rendered = json.loads(render_result["content"][0]["text"])
    assert rendered["widget_type"] == "report_builder_review"
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/report-builder-review.html"
    )

    resources = _call_mcp_server("resources/list")
    assert any(
        resource["uri"] == "ui://widget/report-builder-review.html"
        for resource in resources["resources"]
    )
    widget = _call_mcp_server(
        "resources/read", {"uri": "ui://widget/report-builder-review.html"}
    )
    assert "Build Report Review" in widget["contents"][0]["text"]

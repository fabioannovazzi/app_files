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

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "plugins" / "journal-sampling" / "scripts"
CORE_PATH = SCRIPT_DIR / "journal_sampling_core.py"
MCP_SERVER_PATH = ROOT / "plugins" / "journal-sampling" / "mcp" / "server.cjs"


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("journal_sampling_core", CORE_PATH)
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


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Journal Sampling MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_plugin_workflow_normalizes_excel_and_samples(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "journal.xlsx"
    output_dir = tmp_path / "out"
    sample_dir = output_dir / "sample"
    _save_workbook(
        journal_path,
        [
            ["Data", "Conto", "Descrizione conto", "Descrizione", "Dare", "Avere"],
            ["2025-01-01", "1000", "Cash", "Opening", 100, None],
            ["2025-01-02", "2000", "Revenue", "Sale", None, 100],
            ["2025-01-03", "3000", "Expense", "Cost", 50, None],
        ],
    )

    inspection = core.inspect_path(
        journal_path, output_dir, language="fr", document_language="it"
    )
    normalized = core.normalize_path(
        journal_path, output_dir, output_dir / "suggested_recipe.json"
    )
    sample = core.run_sample(
        output_dir / "normalized_journal.csv",
        sample_dir,
        method="random",
        size=2,
    )

    assert inspection.total_rows == 3
    inspection_payload = json.loads((output_dir / "inspection.json").read_text())
    recipe_payload = json.loads((output_dir / "suggested_recipe.json").read_text())
    assert inspection_payload["language"] == "fr"
    assert inspection_payload["document_language"] == "it"
    assert recipe_payload["language"] == "fr"
    assert recipe_payload["document_language"] == "it"
    assert normalized.frame.height == 3
    assert sample.frame.height == 2
    first_sample_row = sample.frame.to_dicts()[0]
    sampling_audit = json.loads((sample_dir / "sampling_audit.json").read_text())
    run_intake = json.loads((sample_dir / "run_intake.json").read_text())
    review_payload = json.loads((sample_dir / "review_payload.json").read_text())
    ui_decisions = json.loads((sample_dir / "ui_decisions.json").read_text())
    final_artifacts = json.loads((sample_dir / "final_artifacts.json").read_text())

    assert (output_dir / "inspection.json").exists()
    assert (output_dir / "normalized_journal.csv").exists()
    assert (sample_dir / "journal_sample.csv").exists()
    assert (sample_dir / "sampling_audit.json").exists()
    assert (sample_dir / "run_intake.json").exists()
    assert (sample_dir / "review_payload.json").exists()
    assert (sample_dir / "ui_decisions.json").exists()
    assert (sample_dir / "final_artifacts.json").exists()
    assert sampling_audit["review_session"]["run_id"] == run_intake["run_id"]
    assert review_payload["plugin"] == "journal-sampling"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "journal_sampling_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {"sampling_control", "sampled_entry", "sample_artifact"} <= item_types
    assert review_payload["summary"]["sample_size"] == 2
    assert ui_decisions["status"] == "pending_review"
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (sample_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_journal_sampling_review" in handoff_text
    assert "apply_journal_sampling_decisions" in handoff_text
    sample_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "journal_sample.csv"
    )
    sample_xlsx_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "journal_sample.xlsx"
    )
    assert sample_output["row_count"] == sampling_audit["sample_size"]
    assert sample_output["required_columns"] == [
        "entry_date",
        "account",
        "account_desc",
        "line_desc",
        "amount_abs",
        "source_file",
        "source_row",
    ]
    assert {
        "entry_date",
        "account",
        "account_desc",
        "line_desc",
        "amount_abs",
        "source_file",
        "source_row",
        first_sample_row["entry_date"],
        str(first_sample_row["account"]),
        first_sample_row["account_desc"],
        first_sample_row["line_desc"],
        first_sample_row["source_file"],
    } <= set(sample_output["required_text"])
    assert "required_text" in sample_output["qa_checks"]
    assert sample_xlsx_output["source_row_count"] == sampling_audit["sample_size"]
    assert sample_xlsx_output["required_sheets"] == ["Sheet1"]
    assert sample_xlsx_output["required_sheet_headers"] == {
        "Sheet1": [
            "entry_date",
            "account",
            "account_desc",
            "line_desc",
            "amount_abs",
            "source_file",
            "source_row",
        ]
    }
    assert sample_xlsx_output["required_cells"] == {
        "Sheet1": {
            "A1": "entry_date",
            "A2": first_sample_row["entry_date"],
            "D1": "account",
            "D2": str(first_sample_row["account"]),
            "E1": "account_desc",
            "E2": first_sample_row["account_desc"],
            "F1": "line_desc",
            "F2": first_sample_row["line_desc"],
            "K1": "source_file",
            "K2": first_sample_row["source_file"],
            "N1": "source_row",
            "N2": str(first_sample_row["source_row"]),
        }
    }
    assert "required_cells" in sample_xlsx_output["qa_checks"]
    contract_report = validate_contract(
        sample_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_plugin_print_friendly_excel_extracts_detail_rows(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "print_friendly.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    header_row = 7
    headers = {
        1: "Nr. Prog",
        2: "Data Reg.",
        5: "Descrizione",
        6: "Conto",
        7: "Descrizione Conto",
        8: "Dare (EUR)",
        11: "Avere (EUR)",
        14: "Nr. Reg",
    }
    for col_idx, value in headers.items():
        sheet.cell(row=header_row, column=col_idx, value=value)
    sheet.cell(row=8, column=2, value="01/10/2025")
    sheet.cell(row=8, column=5, value="PAGAMENTO FORNITORE")
    sheet.cell(row=8, column=14, value=93551)
    sheet.cell(row=9, column=6, value="F 21360")
    sheet.cell(row=9, column=7, value="FORNITORE")
    sheet.cell(row=9, column=9, value=1857)
    sheet.cell(row=10, column=6, value="G 514")
    sheet.cell(row=10, column=7, value="BANCA")
    sheet.cell(row=10, column=12, value=1857)
    workbook.save(journal_path)

    normalized = core.normalize_path(journal_path, tmp_path / "out")

    assert normalized.frame.height == 2
    assert normalized.frame.get_column("account").to_list() == ["F 21360", "G 514"]
    assert normalized.frame.get_column("entry_date").to_list() == [
        "2025-10-01",
        "2025-10-01",
    ]


def test_plugin_text_pdf_path_uses_extracted_text(
    monkeypatch: Any, tmp_path: Path
) -> None:
    core = load_core()
    pdf_path = tmp_path / "journal.pdf"
    pdf_path.write_bytes(b"%PDF placeholder")

    def fake_extract_text(path: Path) -> list[tuple[int, str]]:
        assert path == pdf_path
        return [(1, "01/02/2025 1000 Cash debit 100,00")]

    monkeypatch.setattr(core, "_extract_pdf_text", fake_extract_text)

    normalized = core.normalize_path(pdf_path, tmp_path / "out")

    assert normalized.frame.height == 1
    assert normalized.frame.get_column("account").to_list() == ["1000"]
    assert normalized.frame.get_column("entry_date").to_list() == ["2025-02-01"]


def test_plugin_supports_french_and_german_header_labels(tmp_path: Path) -> None:
    core = load_core()
    journal_path = tmp_path / "journal_de.xlsx"
    output_dir = tmp_path / "out"
    _save_workbook(
        journal_path,
        [
            ["Datum", "Konto", "Beschreibung", "Soll", "Haben"],
            ["2025-03-01", "1000", "Start", 80, None],
            ["2025-03-02", "2000", "Umsatz", None, 80],
        ],
    )

    normalized = core.normalize_path(
        journal_path,
        output_dir,
        language="de",
        document_language="de",
    )

    assert normalized.frame.height == 2
    assert normalized.diagnostics["language"] == "de"
    assert normalized.diagnostics["document_language"] == "de"
    assert normalized.frame.get_column("account").to_list() == ["1000", "2000"]


def test_skill_tells_codex_user_does_not_run_cli_directly() -> None:
    skill_text = (
        ROOT
        / "plugins"
        / "journal-sampling"
        / "skills"
        / "journal-sampling"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "The user should not interact directly with CLI scripts" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "it`, `en`, `fr`, `de`, and `es`" in skill_text
    assert "missing deterministic extraction script" in skill_text
    assert "suggested next engineering action" in skill_text
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "validate_journal_sampling_review" in skill_text
    assert "render_journal_sampling_review" in skill_text


def test_static_page_exposes_four_language_switch() -> None:
    page = (ROOT / "static" / "shared" / "journal-sampling" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        'data-lang="it"',
        'data-lang="en"',
        'data-lang="fr"',
        'data-lang="de"',
        "Crea un campione riproducibile da un giornale disordinato.",
        "Create a reproducible sample from a messy journal export.",
        "Créer un échantillon reproductible depuis un journal désordonné.",
        "Eine reproduzierbare Stichprobe aus einem uneinheitlichen Journal erstellen.",
    ):
        assert snippet in page


def test_journal_sampling_mcp_server_validates_and_renders_review_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "journal-sampling",
        "workflow": "journal-sampling",
        "run_id": "journal-sampling-test-run",
        "review_type": "journal_sampling_review",
        "items": [
            {
                "id": "sampling-control",
                "item_type": "sampling_control",
                "title": "random sample: 2 of 3",
                "output_path": "sampling_audit.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "sampling_parameters", "method": "random"}],
                "data": {"method": "random", "sample_size": 2},
                "status": "needs_review",
            },
            {
                "id": "sampled-entry-1",
                "item_type": "sampled_entry",
                "title": "2025-01-02 | 2000 | 100",
                "source_path": "journal.xlsx; row 2",
                "output_path": "journal_sample.csv",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [{"kind": "sampled_entry", "account": "2000"}],
                "data": {"account": "2000", "amount_abs": 100},
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
            "method": "random",
            "requested_size": 2,
            "population_size_after_filters": 3,
            "sample_size": 2,
        },
    }
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_journal_sampling_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_journal_sampling_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/journal-sampling-review.html"},
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert render_result["structuredContent"]["widget_type"] == (
        "journal_sampling_review"
    )
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/journal-sampling-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/journal-sampling-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "Journal Sampling Review" in widget_html

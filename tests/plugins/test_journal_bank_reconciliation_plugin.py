from __future__ import annotations

import csv
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
SCRIPT_DIR = ROOT / "plugins" / "journal-bank-reconciliation" / "scripts"
CORE_PATH = SCRIPT_DIR / "journal_bank_core.py"
APPLY_REVIEW_EDITS_PATH = SCRIPT_DIR / "apply_review_edits.py"
MCP_SERVER_PATH = (
    ROOT / "plugins" / "journal-bank-reconciliation" / "mcp" / "server.cjs"
)


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("journal_bank_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_apply_review_edits() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "journal_bank_apply_review_edits", APPLY_REVIEW_EDITS_PATH
    )
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


def _save_csv(path: Path, rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js is required to exercise the Journal-Bank Reconciliation MCP server."
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


def test_plugin_inspects_and_runs_deterministic_journal_bank_reconciliation(
    tmp_path: Path,
) -> None:
    core = load_core()
    bank_path = tmp_path / "bank.xlsx"
    journal_path = tmp_path / "journal.xlsx"
    output_dir = tmp_path / "out"
    reconciliation_dir = output_dir / "reconciliation"
    _save_workbook(
        bank_path,
        [
            ["Date", "Description", "Amount", "Reference", "Beneficiary"],
            ["2025-01-02", "Payment invoice INV100 ACME", 123.45, "INV100", "ACME"],
            ["2025-01-05", "Unmatched fee", 9.99, "FEE9", "Bank"],
        ],
    )
    _save_workbook(
        journal_path,
        [
            ["Data", "Descrizione", "Dare", "Avere", "Riferimento", "Beneficiario"],
            ["2025-01-01", "Invoice INV100 ACME", 123.45, None, "INV100", "ACME"],
            ["2025-01-07", "Unmatched supplier", 77.0, None, "SUP77", "Supplier"],
        ],
    )

    inspection = core.inspect_inputs(
        bank_path,
        journal_path,
        output_dir,
        language="it",
        document_language="it",
    )
    result = core.run_reconciliation(
        bank_path,
        journal_path,
        reconciliation_dir,
        output_dir / "suggested_recipe.json",
        language="it",
        document_language="it",
    )

    inspection_payload = json.loads((output_dir / "inspection.json").read_text())
    recipe_payload = json.loads((output_dir / "suggested_recipe.json").read_text())
    audit_payload = json.loads(
        (reconciliation_dir / "reconciliation_audit.json").read_text()
    )
    run_intake = json.loads((reconciliation_dir / "run_intake.json").read_text())
    review_payload = json.loads(
        (reconciliation_dir / "review_payload.json").read_text()
    )
    ui_decisions = json.loads((reconciliation_dir / "ui_decisions.json").read_text())
    final_artifacts = json.loads(
        (reconciliation_dir / "final_artifacts.json").read_text()
    )
    match = result.matches.to_dicts()[0]
    unmatched_bank = result.unmatched_bank.to_dicts()[0]
    unmatched_journal = result.unmatched_journal.to_dicts()[0]

    assert inspection.bank["row_count"] == 2
    assert inspection_payload["language"] == "it"
    assert recipe_payload["bank"]["files"]["bank.xlsx"]["mapping"]["date"] == "Date"
    assert match["status"] == "matched"
    assert match["stage"] == "reference"
    assert "inv100" in match["shared_references"].split(",")
    assert result.unmatched_bank.height == 1
    assert result.unmatched_journal.height == 1
    assert audit_payload["matched_count"] == 1
    assert audit_payload["unmatched_bank_count"] == 1
    assert audit_payload["unmatched_journal_count"] == 1
    assert audit_payload["review_session"]["run_id"] == run_intake["run_id"]
    assert (reconciliation_dir / "normalized_bank.csv").exists()
    assert (reconciliation_dir / "normalized_journal.csv").exists()
    assert (reconciliation_dir / "reconciliation_matches.csv").exists()
    assert (reconciliation_dir / "unmatched_bank.csv").exists()
    assert (reconciliation_dir / "unmatched_journal.csv").exists()
    assert (reconciliation_dir / "bank_pdf_non_movement_rows.csv").exists()
    assert (reconciliation_dir / "journal_bank_reconciliation.xlsx").exists()
    assert (reconciliation_dir / "review_notes.md").exists()
    assert (reconciliation_dir / "run_intake.json").exists()
    assert (reconciliation_dir / "review_payload.json").exists()
    assert (reconciliation_dir / "ui_decisions.json").exists()
    assert (reconciliation_dir / "final_artifacts.json").exists()
    assert run_intake["plugin"] == "journal-bank-reconciliation"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "journal_bank_reconciliation_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {"matched_pair", "unmatched_bank", "unmatched_journal"} <= item_types
    matched_item = next(
        item for item in review_payload["items"] if item["item_type"] == "matched_pair"
    )
    unmatched_bank_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "unmatched_bank"
    )
    unmatched_journal_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "unmatched_journal"
    )
    assert matched_item["data"]["target_artifact"] == "reconciliation_matches.csv"
    assert matched_item["data"]["target_id_field"] == "bank_transaction_id"
    assert matched_item["data"]["target_record_id"] == match["bank_transaction_id"]
    assert matched_item["data"]["target_field"] == "review_note"
    assert unmatched_bank_item["recommended_action"] == "request_more_documents"
    assert unmatched_bank_item["data"]["requested_document"] == (
        "Journal or ledger support for bank transaction FEE9"
    )
    assert unmatched_bank_item["data"]["reason"] == (
        "Bank transaction has no deterministic journal match."
    )
    assert any(
        evidence.get("kind") == "missing_reconciliation_evidence"
        and evidence.get("requested_document")
        == "Journal or ledger support for bank transaction FEE9"
        for evidence in unmatched_bank_item["evidence"]
    )
    assert unmatched_journal_item["recommended_action"] == "request_more_documents"
    assert unmatched_journal_item["data"]["requested_document"] == (
        "Bank statement or payment evidence for journal transaction SUP77"
    )
    assert unmatched_journal_item["data"]["reason"] == (
        "Journal transaction has no deterministic bank match."
    )
    assert review_payload["summary"]["matched_count"] == 1
    assert review_payload["summary"]["unmatched_bank_count"] == 1
    assert review_payload["summary"]["unmatched_journal_count"] == 1
    assert ui_decisions["status"] == "pending_review"
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (reconciliation_dir / "review_handoff.md").read_text(
        encoding="utf-8"
    )
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_journal_bank_review" in handoff_text
    assert "apply_journal_bank_decisions" in handoff_text
    review_notes_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_notes.md"
    )
    assert review_notes_output["required_text"] == [
        "# Journal-Bank Reconciliation Review Notes",
        "## Stage Counts",
        "## Review Policy",
    ]
    workbook_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "journal_bank_reconciliation.xlsx"
    )
    assert workbook_output["required_sheets"] == [
        "matches",
        "unmatched_bank",
        "unmatched_journal",
        "bank_pdf_non_movements",
    ]
    assert workbook_output["source_row_counts"] == {
        "matches": audit_payload["matched_count"],
        "unmatched_bank": audit_payload["unmatched_bank_count"],
        "unmatched_journal": audit_payload["unmatched_journal_count"],
        "bank_pdf_non_movements": audit_payload["bank_pdf_non_movement_row_count"],
    }
    assert workbook_output["required_sheet_headers"] == {
        "matches": [
            "status",
            "stage",
            "bank_transaction_id",
            "journal_transaction_id",
            "amount_delta",
            "shared_references",
        ],
        "unmatched_bank": [
            "side",
            "transaction_id",
            "transaction_date",
            "amount_abs",
            "reference",
        ],
        "unmatched_journal": [
            "side",
            "transaction_id",
            "transaction_date",
            "amount_abs",
            "reference",
        ],
        "bank_pdf_non_movements": [
            "source_file",
            "source_row",
            "classification",
            "description",
            "amount_abs",
        ],
    }
    assert workbook_output["required_cells"] == {
        "matches": {
            "A1": "status",
            "A2": "matched",
            "B1": "stage",
            "B2": "reference",
            "C1": "bank_transaction_id",
            "C2": match["bank_transaction_id"],
            "D1": "journal_transaction_id",
            "D2": match["journal_transaction_id"],
            "M1": "shared_references",
            "M2": match["shared_references"],
        },
        "unmatched_bank": {
            "A1": "side",
            "A2": "bank",
            "B1": "transaction_id",
            "B2": unmatched_bank["transaction_id"],
            "C1": "transaction_date",
            "C2": unmatched_bank["transaction_date"],
            "H1": "reference",
            "H2": "FEE9",
        },
        "unmatched_journal": {
            "A1": "side",
            "A2": "journal",
            "B1": "transaction_id",
            "B2": unmatched_journal["transaction_id"],
            "C1": "transaction_date",
            "C2": unmatched_journal["transaction_date"],
            "H1": "reference",
            "H2": "SUP77",
        },
        "bank_pdf_non_movements": {
            "B1": "source_file",
            "C1": "source_row",
            "D1": "classification",
            "I1": "description",
            "H1": "amount_abs",
        },
    }
    assert "required_cells" in workbook_output["qa_checks"]
    matches_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "reconciliation_matches.csv"
    )
    assert matches_output["row_count"] == audit_payload["matched_count"]
    assert matches_output["required_columns"] == [
        "status",
        "bank_transaction_id",
        "journal_transaction_id",
        "amount_delta",
    ]
    contract_report = validate_contract(
        reconciliation_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_plugin_keeps_ambiguous_rows_unmatched(tmp_path: Path) -> None:
    core = load_core()
    bank_path = tmp_path / "bank.xlsx"
    journal_path = tmp_path / "journal.xlsx"
    output_dir = tmp_path / "out"
    _save_workbook(
        bank_path,
        [
            ["Date", "Description", "Amount"],
            ["2025-03-10", "Payment", 80],
        ],
    )
    _save_workbook(
        journal_path,
        [
            ["Date", "Description", "Amount"],
            ["2025-03-10", "Payment A", 80],
            ["2025-03-10", "Payment B", 80],
        ],
    )

    result = core.run_reconciliation(bank_path, journal_path, output_dir, language="en")

    assert result.matches.height == 0
    assert result.unmatched_bank.height == 1
    assert result.unmatched_journal.height == 2


def test_run_reconciliation_sanitizes_illegal_excel_characters_before_workbook_export(
    tmp_path: Path,
) -> None:
    core = load_core()
    bank_path = tmp_path / "bank.csv"
    journal_path = tmp_path / "journal.csv"
    output_dir = tmp_path / "out"
    raw_bank_description = "Saldo iniziale al 31.03.2025 +133\x19 318, 47 EUR"
    excel_bank_description = "Saldo iniziale al 31.03.2025 +133 318, 47 EUR"
    _save_csv(
        bank_path,
        [
            ["Date", "Description", "Amount", "Reference"],
            ["2025-03-31", raw_bank_description, "47.00", "CTRL19"],
        ],
    )
    _save_csv(
        journal_path,
        [
            ["Date", "Description", "Amount", "Reference"],
            ["2025-03-31", "Journal movement CTRL19", "47.00", "CTRL19"],
        ],
    )

    result = core.run_reconciliation(bank_path, journal_path, output_dir, language="en")

    match = result.matches.to_dicts()[0]
    workbook = openpyxl.load_workbook(output_dir / "journal_bank_reconciliation.xlsx")
    assert match["bank_description"] == raw_bank_description
    assert workbook["matches"]["K2"].value == excel_bank_description
    assert workbook["normalized_bank"]["F2"].value == excel_bank_description
    assert "\x19" not in workbook["matches"]["K2"].value


def test_bank_pdf_non_movement_rows_are_excluded_with_multilingual_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = load_core()
    bank_path = tmp_path / "bank.pdf"
    journal_path = tmp_path / "journal.csv"
    output_dir = tmp_path / "out"
    bank_path.write_text("stub pdf content", encoding="utf-8")
    bank_pdf_text = "\n".join(
        [
            "Saldo iniziale al 31.03.2025 +133 318,47 EUR",
            "Totale accrediti 1.000,00 EUR",
            "Riassunto scalare interessi 12,34 EUR",
            "Condizioni economiche canone 5,00 EUR",
            "Opening balance at 31/03/2025 133,318.47 EUR",
            "Total fees 12.00 EUR",
            "Account conditions 5.00 EUR",
            "Solde initial au 31/03/2025 133 318,47 EUR",
            "Total des credits 1 000,00 EUR",
            "Conditions economiques 5,00 EUR",
            "Anfangssaldo zum 31.03.2025 133.318,47 EUR",
            "Summe der Gutschriften 1.000,00 EUR",
            "Kontokonditionen 5,00 EUR",
            "31/03/2025 Bonifico cliente ACME INV100 1.000,00 EUR",
            "01/04/2025 Commissione bonifico FEEIT 3,00 EUR",
            "02/04/2025 Bank transfer fee FEEEN 4.00 EUR",
            "03/04/2025 Frais de virement FEEFR 5,00 EUR",
            "04/04/2025 Ueberweisungsgebuehr FEEDE 6,00 EUR",
        ]
    )
    _save_csv(
        journal_path,
        [
            ["Date", "Description", "Amount", "Reference"],
            ["2025-03-31", "Invoice INV100 ACME", "1000.00", "INV100"],
            ["2025-04-01", "Commissione bonifico FEEIT", "3.00", "FEEIT"],
            ["2025-04-02", "Bank transfer fee FEEEN", "4.00", "FEEEN"],
            ["2025-04-03", "Frais de virement FEEFR", "5.00", "FEEFR"],
            ["2025-04-04", "Ueberweisungsgebuehr FEEDE", "6.00", "FEEDE"],
        ],
    )

    def fake_extract_pdf_text(path: Path) -> str:
        return bank_pdf_text if path == bank_path else ""

    monkeypatch.setattr(core, "_extract_pdf_text", fake_extract_pdf_text)

    inspection = core.inspect_inputs(
        bank_path,
        journal_path,
        tmp_path / "inspection",
        language="en",
        document_language="auto",
    )
    result = core.run_reconciliation(bank_path, journal_path, output_dir, language="en")

    non_movement_rows = _read_csv_dicts(output_dir / "bank_pdf_non_movement_rows.csv")
    normalized_bank_rows = _read_csv_dicts(output_dir / "normalized_bank.csv")
    final_artifacts = json.loads((output_dir / "final_artifacts.json").read_text())
    review_payload = json.loads((output_dir / "review_payload.json").read_text())
    workbook = openpyxl.load_workbook(output_dir / "journal_bank_reconciliation.xlsx")
    workbook_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "journal_bank_reconciliation.xlsx"
    )
    non_movement_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "bank_pdf_non_movement_rows.csv"
    )
    classifications = [row["classification"] for row in non_movement_rows]
    normalized_descriptions = {row["description"] for row in normalized_bank_rows}

    assert inspection.bank["row_count"] == 5
    assert (
        json.loads((tmp_path / "inspection" / "inspection.json").read_text())[
            "bank_pdf_non_movement_row_count"
        ]
        == 13
    )
    assert result.matches.height == 5
    assert result.unmatched_bank.height == 0
    assert result.audit["bank_row_count"] == 5
    assert result.audit["bank_pdf_non_movement_row_count"] == 13
    assert result.audit["bank_pdf_non_movement_classifications"] == {
        "balance": 4,
        "conditions": 4,
        "scalare": 1,
        "total": 4,
    }
    assert len(non_movement_rows) == 13
    assert {"balance", "conditions", "scalare", "total"} <= set(classifications)
    assert any("Saldo iniziale" in row["description"] for row in non_movement_rows)
    assert any("Opening balance" in row["description"] for row in non_movement_rows)
    assert any("Solde initial" in row["description"] for row in non_movement_rows)
    assert any("Anfangssaldo" in row["description"] for row in non_movement_rows)
    assert any("Commissione bonifico" in text for text in normalized_descriptions)
    assert any("Bank transfer fee" in text for text in normalized_descriptions)
    assert any("Frais de virement" in text for text in normalized_descriptions)
    assert any("Ueberweisungsgebuehr" in text for text in normalized_descriptions)
    assert workbook["bank_pdf_non_movements"]["D2"].value == "balance"
    assert workbook["bank_pdf_non_movements"]["I2"].value.startswith("Saldo iniziale")
    assert workbook_output["source_row_counts"]["bank_pdf_non_movements"] == 13
    assert non_movement_output["row_count"] == 13
    assert review_payload["summary"]["bank_pdf_non_movement_row_count"] == 13


def test_apply_review_edits_sanitizes_illegal_excel_characters_during_regeneration(
    tmp_path: Path,
) -> None:
    apply_review_edits_module = load_apply_review_edits()
    raw_review_note = "Reviewer accepted\x19 reference match."
    excel_review_note = "Reviewer accepted reference match."
    _save_csv(
        tmp_path / "reconciliation_matches.csv",
        [
            [
                "status",
                "stage",
                "bank_transaction_id",
                "journal_transaction_id",
                "review_note",
            ],
            ["matched", "reference", "bank:1", "journal:1", raw_review_note],
        ],
    )
    for filename in (
        "unmatched_bank.csv",
        "unmatched_journal.csv",
        "normalized_bank.csv",
        "normalized_journal.csv",
    ):
        _save_csv(tmp_path / filename, [["transaction_id"], []])
    _save_workbook(
        tmp_path / "journal_bank_reconciliation.xlsx",
        [
            ["status", "review_note"],
            ["matched", "original"],
        ],
    )
    applied_decisions = {
        "effects": [
            {
                "action": "edit",
                "artifact_update": "structured_artifact_updated",
                "target_artifact": "reconciliation_matches.csv",
                "derived_native_regeneration_paths": [
                    "journal_bank_reconciliation.xlsx"
                ],
                "edit_value": raw_review_note,
                "item_id": "matched-pair-1",
                "target_id_field": "bank_transaction_id",
                "target_record_id": "bank:1",
                "target_field": "review_note",
                "structured_update": {
                    "id_field": "bank_transaction_id",
                    "record_id": "bank:1",
                    "target_field": "review_note",
                },
            }
        ],
        "blocker_count": 0,
        "decision_count": 1,
        "item_count": 1,
    }
    final_artifacts = {
        "outputs": [{"path": "journal_bank_reconciliation.xlsx"}],
        "next_actions": [],
    }
    applied_path = tmp_path / "applied_decisions.json"
    final_artifacts_path = tmp_path / "final_artifacts.json"
    applied_path.write_text(json.dumps(applied_decisions) + "\n", encoding="utf-8")
    final_artifacts_path.write_text(
        json.dumps(final_artifacts) + "\n", encoding="utf-8"
    )

    result = apply_review_edits_module.apply_review_edits(
        tmp_path,
        applied_path,
        final_artifacts_path,
    )

    workbook = openpyxl.load_workbook(tmp_path / "journal_bank_reconciliation.xlsx")
    written_final_artifacts = json.loads(final_artifacts_path.read_text())
    workbook_output = next(
        output
        for output in written_final_artifacts["outputs"]
        if output["path"] == "journal_bank_reconciliation.xlsx"
    )
    assert result["ok"] is True
    assert workbook["matches"]["E2"].value == excel_review_note
    assert workbook_output["required_cells"] == {"matches": {"E2": excel_review_note}}


def test_skill_and_scripts_keep_codex_as_the_review_layer() -> None:
    skill_text = (
        ROOT
        / "plugins"
        / "journal-bank-reconciliation"
        / "skills"
        / "journal-bank-reconciliation"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in SCRIPT_DIR.glob("*.py")
    )

    assert "The user should not interact directly with CLI scripts" in skill_text
    assert "must not make direct OpenAI API calls" in skill_text
    assert "scripts/check_dependencies.py" in skill_text
    assert "it`, `en`, `fr`, and `de`" in skill_text
    assert "missing deterministic extraction script" in skill_text
    assert "Keep the improvement note local to chat or run artifacts." in skill_text
    assert "validate_journal_bank_review" in skill_text
    assert "render_journal_bank_review" in skill_text
    assert "modules.llm" not in script_text
    assert "model_router" not in script_text
    assert "openai" not in script_text.lower()


def test_static_page_exposes_four_language_switch() -> None:
    page = (
        ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        'data-lang="it"',
        'data-lang="en"',
        'data-lang="fr"',
        'data-lang="de"',
        "Abbina banca e contabilità senza nascondere le eccezioni",
        "Match bank rows to accounting rows without burying exceptions.",
        "Rapprocher banque et comptabilité sans masquer les exceptions",
        "Bank- und Buchhaltungszeilen abgleichen, ohne Ausnahmen zu verstecken",
    ):
        assert snippet in page


def test_journal_bank_mcp_server_validates_renders_and_applies_review_payload(
    tmp_path: Path,
) -> None:
    matches_path = tmp_path / "reconciliation_matches.csv"
    workbook_path = tmp_path / "journal_bank_reconciliation.xlsx"
    matches_path.write_text(
        "\n".join(
            [
                "status,stage,bank_transaction_id,journal_transaction_id,review_note",
                "matched,reference,bank:1,journal:1,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _save_workbook(
        workbook_path,
        [
            ["status", "stage", "bank_transaction_id", "journal_transaction_id"],
            ["matched", "reference", "bank:1", "journal:1"],
        ],
    )
    review_payload = {
        "schema_version": "1.0",
        "plugin": "journal-bank-reconciliation",
        "workflow": "journal-bank-reconciliation",
        "run_id": "journal-bank-test-run",
        "source_paths": ["bank.xlsx", "journal.xlsx"],
        "review_type": "journal_bank_reconciliation_review",
        "items": [
            {
                "id": "matched-pair-1",
                "item_type": "matched_pair",
                "title": "123.45 | inv100 | reference",
                "output_path": "reconciliation_matches.csv",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [
                    {
                        "kind": "deterministic_match",
                        "stage": "reference",
                        "shared_references": "inv100",
                    }
                ],
                "data": {
                    "status": "matched",
                    "target_artifact": "reconciliation_matches.csv",
                    "target_id_field": "bank_transaction_id",
                    "target_record_id": "bank:1",
                    "target_field": "review_note",
                },
                "status": "needs_review",
            },
            {
                "id": "unmatched-bank-1",
                "item_type": "unmatched_bank",
                "title": "2025-01-05 | 9.99 | FEE9",
                "source_path": "bank.xlsx; row 2",
                "output_path": "unmatched_bank.csv",
                "allowed_actions": [
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ],
                "recommended_action": "mark_unclear",
                "evidence": [{"kind": "unmatched_transaction", "side": "bank"}],
                "data": {"transaction_id": "bank:1"},
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
            "bank_row_count": 2,
            "journal_row_count": 2,
            "matched_count": 1,
            "unmatched_bank_count": 1,
            "unmatched_journal_count": 1,
        },
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "journal-bank-reconciliation",
        "workflow": "journal-bank-reconciliation",
        "run_id": "journal-bank-test-run",
        "created_at": "2026-01-01T00:00:00Z",
        "language": "en",
        "document_language": "en",
        "input_paths": ["bank.xlsx", "journal.xlsx"],
        "output_dir": tmp_path.as_posix(),
        "inferred_task": "journal_bank_reconciliation",
        "assumptions": {},
        "unresolved_questions": [],
        "dependency_check": {"status": "not_run"},
        "data_posture": {
            "local_files_read": ["bank.xlsx", "journal.xlsx"],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "journal-bank-reconciliation",
        "workflow": "journal-bank-reconciliation",
        "run_id": "journal-bank-test-run",
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
                "name": "validate_journal_bank_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_journal_bank_review",
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
            "params": {"uri": "ui://widget/journal-bank-review.html"},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "save_journal_bank_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "decisions": [
                        {
                            "item_id": "matched-pair-1",
                            "action": "edit",
                            "edit_value": "Reviewer accepted reference match.",
                        },
                        {
                            "item_id": "unmatched-bank-1",
                            "action": "request_more_documents",
                            "reviewer_note": "Need accounting support for FEE9.",
                            "requested_documents": ["ledger_support_FEE9.pdf"],
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
                "name": "apply_journal_bank_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": {
                        "schema_version": "1.0",
                        "plugin": "journal-bank-reconciliation",
                        "workflow": "journal-bank-reconciliation",
                        "run_id": "journal-bank-test-run",
                        "outputs": [
                            {
                                "path": "reconciliation_matches.csv",
                                "kind": "csv",
                                "status": "written",
                            },
                            {
                                "path": "journal_bank_reconciliation.xlsx",
                                "kind": "xlsx",
                                "status": "written",
                            },
                        ],
                        "status": "written_pending_review",
                    },
                    "decisions": [
                        {
                            "item_id": "matched-pair-1",
                            "action": "edit",
                            "edit_value": "Reviewer accepted reference match.",
                        },
                        {
                            "item_id": "unmatched-bank-1",
                            "action": "request_more_documents",
                            "reviewer_note": "Need accounting support for FEE9.",
                            "requested_documents": ["ledger_support_FEE9.pdf"],
                        },
                    ],
                },
            },
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_journal_bank_review",
        "render_journal_bank_review",
        "save_journal_bank_decisions",
        "apply_journal_bank_decisions",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert render_result["structuredContent"]["widget_type"] == "journal_bank_review"
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/journal-bank-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/journal-bank-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "Journal-Bank Review" in widget_html
    save_result = responses[6]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 2
    written_decisions = json.loads((tmp_path / "ui_decisions.json").read_text())
    assert written_decisions["decisions"][0]["edit_value"] == (
        "Reviewer accepted reference match."
    )
    assert written_decisions["decisions"][1]["requested_documents"] == [
        "ledger_support_FEE9.pdf"
    ]
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
    assert "Reviewer accepted reference match." in matches_path.read_text(
        encoding="utf-8"
    )
    applied = json.loads((tmp_path / "applied_decisions.json").read_text())
    assert applied["effects"][0]["structured_update"] == {
        "id_field": "bank_transaction_id",
        "record_id": "bank:1",
        "target_field": "review_note",
        "records_key": None,
        "updated_rows": 1,
    }
    assert applied["effects"][0]["derived_native_regeneration_paths"] == [
        "journal_bank_reconciliation.xlsx"
    ]
    assert applied["effects"][0]["requires_native_regeneration"] is False
    assert applied["effects"][0]["native_regeneration_status"] == "regenerated"
    assert applied["structured_update_paths"] == ["reconciliation_matches.csv"]
    assert applied["native_regeneration_paths"] == []
    assert applied["native_regenerated_paths"] == ["journal_bank_reconciliation.xlsx"]
    workbook = openpyxl.load_workbook(workbook_path)
    assert workbook["matches"]["E2"].value == "Reviewer accepted reference match."
    final_artifacts = json.loads((tmp_path / "final_artifacts.json").read_text())
    assert final_artifacts["review_application"]["structured_update_count"] == 1
    assert final_artifacts["review_application"]["structured_update_paths"] == [
        "reconciliation_matches.csv"
    ]
    assert final_artifacts["review_application"]["native_regeneration_paths"] == []
    assert final_artifacts["review_application"]["native_regenerated_paths"] == [
        "journal_bank_reconciliation.xlsx"
    ]
    outputs_by_path = {output["path"]: output for output in final_artifacts["outputs"]}
    assert outputs_by_path["journal_bank_reconciliation.xlsx"]["status"] == (
        "updated_from_review"
    )
    assert (
        outputs_by_path["journal_bank_reconciliation.xlsx"]["native_regenerated"]
        is True
    )
    assert outputs_by_path["journal_bank_reconciliation.xlsx"]["source_artifact"] == (
        "reconciliation_matches.csv"
    )
    assert outputs_by_path["journal_bank_reconciliation.xlsx"]["source_row_count"] == 1
    assert outputs_by_path["journal_bank_reconciliation.xlsx"][
        "required_sheet_headers"
    ] == {
        "matches": [
            "status",
            "stage",
            "bank_transaction_id",
            "journal_transaction_id",
            "review_note",
        ]
    }
    assert outputs_by_path["journal_bank_reconciliation.xlsx"]["required_cells"] == {
        "matches": {"E2": "Reviewer accepted reference match."}
    }
    assert {
        "reconciliation_matches.csv",
        "revisions/originals/reconciliation_matches__matched-pair-1.csv",
        "revisions/originals/journal_bank_reconciliation__matched-pair-1.xlsx",
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
        "final_artifacts.json",
        "journal_bank_reconciliation.xlsx",
        "reconciliation_matches.csv",
        "revisions/originals/journal_bank_reconciliation__matched-pair-1.xlsx",
        "revisions/originals/reconciliation_matches__matched-pair-1.csv",
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

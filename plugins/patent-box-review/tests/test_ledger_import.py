"""Selected-source parsing and reviewed normalization; no professional UAT claim."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from patent_box.contracts import ContractError, file_hash
from patent_box.ledger_import import (
    inspect_table,
    normalization_markdown,
    normalize_population,
)


def selection(fmt: str = "CSV", *, last: int = 3) -> dict[str, Any]:
    return {
        "format": fmt,
        "sheet": "Selected" if fmt == "XLSX" else None,
        "header_row": 1,
        "first_row": 2,
        "last_row": last,
        "delimiter": "," if fmt == "CSV" else None,
        "encoding": "utf-8" if fmt == "CSV" else None,
        "pdf_extraction": None,
    }


def csv_table(
    tmp_path: Path,
    body: str = "L1,I1,100.00,EUR\nL2,I2,40.00,EUR\n",
    *,
    delimiter: str = ",",
) -> dict[str, Any]:
    path = tmp_path / "selected.csv"
    path.write_text(
        delimiter.join(["ledger", "invoice", "amount", "currency"]) + "\n" + body
    )
    options = selection(last=1 + len(body.splitlines()))
    options["delimiter"] = delimiter
    return inspect_table(
        path, {"evidence_id": "LEDGER", "sha256": file_hash(path)}, options
    )


def normalization_plan(
    table: dict[str, Any],
    total: str = "140.00",
    amounts: tuple[str, ...] = ("100.00", "40.00"),
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "purpose": "Synthetic normalization acceptance",
        "mappings": [
            {
                "table_id": table["table_id"],
                "amount_column": "C",
                "currency_column": "D",
                "currency_constant": None,
                "row_key_column": "A",
                "decimal_separator": ".",
                "thousands_separator": None,
                "parentheses_negative": False,
                "economic_key_columns": ["B"],
                "mapping_rationale": "Explicit fixture columns",
            }
        ],
        "non_data_rows": [],
        "control_totals": [
            {
                "table_id": table["table_id"],
                "currency": "EUR",
                "value": total,
                "evidence_id": "LEDGER",
                "locator": "Reviewed fixture control",
                "source_cell": None,
            }
        ],
        "fx_rates": [],
        "costs": [
            {
                "cost_id": f"C{i}",
                "period_id": "P2025",
                "account": "Fixture",
                "category": "PERSONNEL",
                "components": [{"row_ref": row["row_ref"], "fx_rate_id": None}],
                "income_max": amount,
                "irap_max": amount,
                "rationale": "Explicit fixture fiscal basis",
                "evidence_ids": ["LEDGER"],
            }
            for i, (row, amount) in enumerate(zip(table["rows"], amounts), 1)
        ],
        "excluded_rows": [],
        "duplicate_reviews": [],
        "population_duplicate_review": {
            "assessment": "Fixture population reviewed with invoice identities",
            "evidence_ids": ["LEDGER"],
        },
        "rounding_policy": "HALF_UP_AT_NORMALIZED_COST_TOTAL",
    }


def test_normalize_preserves_original_rows_and_does_not_approve(tmp_path: Path) -> None:
    table = csv_table(tmp_path)
    plan = normalization_plan(table)

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["ledger_control_total"] == "140.00"
    assert result["professional_approval"] is False
    assert result["blocked_cost_ids"] == []
    assert result["trace"][0]["components"][0]["original_ledger_key"] == "L1"
    assert result["trace"][0]["components"][0]["locator"] == "CSV, source row 2"
    assert "PROPOSTA DA RIVEDERE" in normalization_markdown(result)


def test_normalize_locale_credit_note_netting_retains_negative_component(
    tmp_path: Path,
) -> None:
    table = csv_table(
        tmp_path, "L1;I1;1.200,50;EUR\nL2;CN1;(200,50);EUR\n", delimiter=";"
    )
    plan = normalization_plan(table, "1000.00", ("1000.00",))
    plan["mappings"][0].update(
        decimal_separator=",", thousands_separator=".", parentheses_negative=True
    )
    plan["costs"][0]["components"].append(
        {"row_ref": table["rows"][1]["row_ref"], "fx_rate_id": None}
    )

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["costs"][0]["book_amount"] == "1000.00"
    assert result["trace"][0]["components"][1]["source_amount"] == "-200.50"


def test_normalize_fx_payroll_group_rounds_only_final_cost(tmp_path: Path) -> None:
    table = csv_table(tmp_path, "L1,PAY1,0.10,USD\nL2,PAY2,0.10,USD\n")
    plan = normalization_plan(table, "0.20", ("0.07",))
    plan["control_totals"][0]["currency"] = "USD"
    plan["costs"][0]["components"] = [
        {"row_ref": r["row_ref"], "fx_rate_id": "FX"} for r in table["rows"]
    ]
    plan["fx_rates"] = [
        {
            "rate_id": "FX",
            "from_currency": "USD",
            "eur_per_unit": "0.33333333",
            "rate_date": "2025-12-31",
            "evidence_id": "RATE",
            "locator": "Rate statement page 1",
            "rationale": "Explicit fixture conversion rate",
        }
    ]

    result = normalize_population([table], plan, {"LEDGER", "RATE"})

    assert result["costs"][0]["book_amount"] == "0.07"
    assert result["trace"][0]["unrounded_eur"] == "0.0666666660"
    assert result["trace"][0]["rounding_delta"] == "0.0033333340"
    assert result["trace"][0]["components"][0]["fx_rate_id"] == "FX"


def duplicate_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    table = csv_table(
        tmp_path, "L1,SAME,100.00,EUR\nL2,SAME,100.00,EUR\nL3,OTHER,40.00,EUR\n"
    )
    return table, normalization_plan(table, "240.00", ("100.00", "100.00", "40.00"))


def duplicate_review(table: dict[str, Any], decision: str) -> dict[str, Any]:
    return {
        "row_refs": [table["rows"][0]["row_ref"], table["rows"][1]["row_ref"]],
        "decision": decision,
        "retained_row_ref": (
            table["rows"][0]["row_ref"] if decision == "DUPLICATE" else None
        ),
        "reason": "Reviewed fixture documents",
        "evidence_ids": ["LEDGER"],
    }


def test_duplicate_economic_entries_with_distinct_ids_block_only_affected_costs(
    tmp_path: Path,
) -> None:
    table, plan = duplicate_fixture(tmp_path)

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["blocked_cost_ids"] == ["C1", "C2"]
    assert result["costs"][2]["cost_id"] == "C3"
    assert len(result["costs"]) == 3
    assert result["duplicate_findings"][0]["automatic_exclusion"] is False


def test_duplicate_distinct_decision_retains_all_costs(tmp_path: Path) -> None:
    table, plan = duplicate_fixture(tmp_path)
    plan["duplicate_reviews"] = [duplicate_review(table, "DISTINCT")]

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["blocked_cost_ids"] == []
    assert result["ledger_control_total"] == "240.00"


def test_confirmed_duplicate_requires_explicit_exclusion_and_keeps_raw_total(
    tmp_path: Path,
) -> None:
    table, plan = duplicate_fixture(tmp_path)
    plan["duplicate_reviews"] = [duplicate_review(table, "DUPLICATE")]
    plan["costs"].pop(1)
    plan["excluded_rows"] = [
        {
            "row_ref": table["rows"][1]["row_ref"],
            "reason": "Duplicate of first source row",
            "evidence_ids": ["LEDGER"],
        }
    ]

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["ledger_control_total"] == "140.00"
    assert result["source_control_totals"][0]["amount"] == "240.00"
    assert result["excluded_rows"][0]["source_amount"] == "100.00"
    assert result["blocked_cost_ids"] == []


def test_same_ledger_id_with_different_amounts_still_requires_review(
    tmp_path: Path,
) -> None:
    table = csv_table(tmp_path, "L1,I1,100.00,EUR\nL1,I2,40.00,EUR\n")

    result = normalize_population([table], normalization_plan(table), {"LEDGER"})

    assert result["blocked_cost_ids"] == ["C1", "C2"]


def test_source_control_total_row_is_retained_as_explicit_non_data(
    tmp_path: Path,
) -> None:
    table = csv_table(
        tmp_path, "L1,I1,100.00,EUR\nL2,I2,40.00,EUR\nTOTAL,,140.00,EUR\n"
    )
    plan = normalization_plan(table)
    total_row = table["rows"][2]["row_ref"]
    plan["non_data_rows"] = [{"row_ref": total_row, "reason": "Source control total"}]
    plan["control_totals"][0]["source_cell"] = {"row_ref": total_row, "column_id": "C"}

    result = normalize_population([table], plan, {"LEDGER"})

    assert result["ledger_control_total"] == "140.00"
    assert result["non_data_rows"] == [
        {"row_ref": total_row, "reason": "Source control total"}
    ]


@pytest.mark.parametrize(
    "scenario,match",
    [
        ("omitted_row", "Closed population"),
        ("wrong_total", "control totals"),
        ("over_basis", "fiscal basis"),
        ("reuse_row", "already consumed"),
        ("unproven_fx", "conversion rate"),
        ("outside_evidence", "selected evidence"),
        ("duplicate_without_exclusion", "explicit exclusions"),
    ],
)
def test_normalize_rejects_unclosed_or_unsupported_proposals(
    tmp_path: Path, scenario: str, match: str
) -> None:
    table = csv_table(tmp_path)
    plan = normalization_plan(table)
    if scenario == "omitted_row":
        plan["costs"].pop()
    elif scenario == "wrong_total":
        plan["control_totals"][0]["value"] = "150.00"
    elif scenario == "over_basis":
        plan["costs"][0]["income_max"] = "101.00"
    elif scenario == "reuse_row":
        plan["costs"][1]["components"] = copy.deepcopy(plan["costs"][0]["components"])
    elif scenario == "unproven_fx":
        plan["mappings"][0].update(currency_column=None, currency_constant="USD")
        plan["control_totals"][0]["currency"] = "USD"
    elif scenario == "outside_evidence":
        plan["costs"][0]["evidence_ids"] = ["OTHER_CLIENT"]
    elif scenario == "duplicate_without_exclusion":
        plan["duplicate_reviews"] = [duplicate_review(table, "DUPLICATE")]

    with pytest.raises(ContractError, match=match):
        normalize_population([table], plan, {"LEDGER"})


def test_normalize_rejects_edited_table_cells(tmp_path: Path) -> None:
    table = csv_table(tmp_path)
    plan = normalization_plan(table)
    table["rows"][0]["cells"]["C"]["value"] = "200.00"

    with pytest.raises(ContractError, match="snapshot changed"):
        normalize_population([table], plan, {"LEDGER"})


def xlsx_source(tmp_path: Path, amount: str | float = 100.25) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Selected"
    sheet.append(["ledger", "invoice", "amount", "currency"])
    sheet.append(["L1", "I1", amount, "EUR"])
    other = workbook.create_sheet("Not selected")
    other.append(["OTHER CLIENT SECRET"])
    target = tmp_path / "selected.xlsx"
    workbook.save(target)
    return target


def test_xlsx_reads_only_selected_sheet_and_retains_numeric_strings(
    tmp_path: Path,
) -> None:
    source = xlsx_source(tmp_path)

    table = inspect_table(
        source,
        {"evidence_id": "LEDGER", "sha256": file_hash(source)},
        selection("XLSX", last=2),
    )

    assert table["rows"][0]["cells"]["C"] == {"value": "100.25", "kind": "NUMBER"}
    assert "OTHER CLIENT SECRET" not in str(table)
    assert table["rows"][0]["locator"] == "Selected, source row 2"


def test_xlsx_formula_is_not_evaluated_or_accepted_as_amount(tmp_path: Path) -> None:
    source = xlsx_source(tmp_path, "=100+40")
    table = inspect_table(
        source,
        {"evidence_id": "LEDGER", "sha256": file_hash(source)},
        selection("XLSX", last=2),
    )
    plan = normalization_plan(table, "140.00", ("140.00",))

    with pytest.raises(ContractError, match="values-only"):
        normalize_population([table], plan, {"LEDGER"})


def pdf_source(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "selected.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(40, 780, "L1 Invoice1 100.00 EUR")
    canvas.showPage()
    canvas.drawString(40, 780, "Unselected page")
    canvas.save()
    options = selection("PDF")
    options.update(
        header_row=None,
        first_row=None,
        last_row=None,
        pdf_extraction={
            "columns": [
                {"column_id": c, "label": l}
                for c, l in [
                    ("A", "ledger"),
                    ("B", "invoice"),
                    ("C", "amount"),
                    ("D", "currency"),
                ]
            ],
            "rows": [
                {
                    "page": 1,
                    "quote": "L1 Invoice1 100.00 EUR",
                    "cells": {"A": "L1", "B": "Invoice1", "C": "100.00", "D": "EUR"},
                }
            ],
            "rationale": "Model-proposed literal fixture row",
        },
    )
    return source, options


def test_pdf_keeps_literal_page_quote_and_model_proposal_assurance(
    tmp_path: Path,
) -> None:
    source, options = pdf_source(tmp_path)

    table = inspect_table(
        source, {"evidence_id": "LEDGER", "sha256": file_hash(source)}, options
    )

    assert table["rows"][0]["locator"] == "page 1: L1 Invoice1 100.00 EUR"
    assert (
        table["extraction_assurance"]
        == "MODEL_TABLE_PROPOSAL_WITH_LITERAL_PAGE_REFERENCES"
    )
    assert "Unselected page" not in str(table)


@pytest.mark.parametrize(
    "scenario", ["wrong_page", "invented_amount", "invented_quote"]
)
def test_pdf_rejects_unsupported_model_cells_or_passages(
    tmp_path: Path, scenario: str
) -> None:
    source, options = pdf_source(tmp_path)
    row = options["pdf_extraction"]["rows"][0]
    if scenario == "wrong_page":
        row["page"] = 2
    elif scenario == "invented_amount":
        row["cells"]["C"] = "200.00"
    else:
        row["quote"] = "A row never present in this file"

    with pytest.raises(ContractError, match="cited page passage|cited passage"):
        inspect_table(
            source, {"evidence_id": "LEDGER", "sha256": file_hash(source)}, options
        )


def test_inspection_rejects_changed_selected_source(tmp_path: Path) -> None:
    source = tmp_path / "selected.csv"
    source.write_text("id,amount\n1,100\n")
    evidence = {"evidence_id": "LEDGER", "sha256": file_hash(source)}
    source.write_text("id,amount\n1,200\n")

    with pytest.raises(ContractError, match="bytes changed"):
        inspect_table(source, evidence, selection(last=2))

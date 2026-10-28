"""Declared source lists produce arithmetic drafts without bank provenance."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.open_item_reconciliation.test_audit_assurance import (
    SCRIPTS,
    load_assurance,
    load_script_module,
)
from tests.open_item_reconciliation.test_reviewed_tabular_adapter import spec


def case(tmp_path):
    source = tmp_path / "inputs"
    source.mkdir()
    population = source / "partite.csv"
    population.write_text(
        "invoice_id,customer,currency,invoice_date,amount\nINV-001,A,EUR,2026-09-01,100.00\nINV-002,B,EUR,2026-09-02,200.00\n"
    )
    invoice = source / "fatture.csv"
    invoice.write_text(population.read_text() + "\n")
    payment = source / "pagamenti.csv"
    payment.write_text(
        "payment_id,invoice_id,currency,payment_date,amount\nPAY-001,INV-001,EUR,2026-10-10,100.00\nPAY-002,INV-002,EUR,2026-10-15,50.00\n"
    )
    decisions = {}
    for path, role in (
        (population, "open_items"),
        (invoice, "invoice_list"),
        (payment, "payment_list"),
    ):
        choice = spec(path)
        choice["role"] = role
        choice["perimeter"]["party_ref"] = None
        choice["tabular"].update(
            delimiter=",",
            default_evidence_type={
                "open_items": "open_item",
                "invoice_list": "invoice_record",
                "payment_list": "declared_payment",
            }[role],
        )
        columns = {
            "document_no": "invoice_id",
            "amount": "amount",
            "currency": "currency",
        }
        if role == "payment_list":
            columns.update(payment_date="payment_date", source_record_id="payment_id")
        else:
            columns.update(document_date="invoice_date", party_ref="customer")
        choice["tabular"]["columns"] = columns
        decisions[path.name] = choice
    return source, {
        "scope_year": 2026,
        "cutoff_date": "2026-10-31",
        "amount_tolerance": "0",
        "post_cutoff_events_excluded": True,
        "reviewed_source_decisions": decisions,
    }


def extract(tmp_path):
    source, assumptions = case(tmp_path)
    raw = load_script_module("declared_raw", SCRIPTS / "raw_input_runner.py")
    extracted = raw.extract_normalized_records(
        source, assumptions, output_dir=tmp_path / "extracted"
    )
    assert extracted["extraction_errors"] == []
    return source, assumptions, extracted


def test_declared_lists_deliver_replayable_draft_with_honest_provenance(tmp_path):
    source, assumptions, extracted = extract(tmp_path)
    workflow = load_script_module(
        "declared_workflow", SCRIPTS / "reconciliation_workflow.py"
    )
    result = workflow.build_reconciliation_artifacts(
        output_dir=tmp_path / "workpapers",
        open_items=extracted["open_items"],
        evidence_rows=extracted["evidence_rows"],
        assumptions=assumptions,
        source_inventory=extracted["source_inventory"],
        source_qualifications=extracted["source_qualifications"],
        source_artifact_root=source,
        source_artifact_receipts=extracted["source_artifact_receipts"],
        reviewed_source_decision_receipts=extracted[
            "reviewed_source_decision_receipts"
        ],
        normalized_records=extracted["normalized_records"],
        require_completed_review=False,
        language="it",
    )
    rows = result["reconciliation_rows"]
    assert [r["allocated_amount"] for r in rows] == ["100.00", "50.00"]
    assert [r["residual_amount"] for r in rows] == ["0.00", "150.00"]
    assert {r["reconciliation_status"] for r in rows} == {"needs_evidence"}
    assert {r["matched_evidence_type"] for r in rows} == {"declared_payment"}
    payments = [
        r for r in extracted["evidence_rows"] if r["source_role"] == "payment_list"
    ]
    assert payments[0]["party_ref"] is None
    assert "document_date" not in payments[0]
    assert "posting_date" not in payments[0]
    assert payments[0]["payment_date"] == "2026-10-10"
    assert Path(result["excel_path"]).is_file()
    assert Path(result["word_path"]).is_file()
    assert (
        load_assurance().validate_assurance_run(tmp_path / "workpapers")[
            "content_sha256"
        ]
        == result["assurance"]["content_sha256"]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_invoice",
        "duplicate_payment",
        "wrong_currency",
        "wrong_party",
        "invoice_amount",
        "after_cutoff",
        "overpayment",
    ],
)
def test_ambiguous_or_inconsistent_declarations_do_not_calculate_residual(
    tmp_path, fault
):
    _, assumptions, extracted = extract(tmp_path)
    workflow = load_script_module(
        "declared_fault_workflow", SCRIPTS / "reconciliation_workflow.py"
    )
    items = copy.deepcopy(extracted["open_items"])
    evidence = copy.deepcopy(extracted["evidence_rows"])
    payment = next(e for e in evidence if e["source_role"] == "payment_list")
    invoice = next(e for e in evidence if e["source_role"] == "invoice_list")
    if fault == "duplicate_invoice":
        items.append(
            {**items[0], "record_id": "duplicate", "document_date": "2025-09-01"}
        )
    elif fault == "duplicate_payment":
        evidence.append({**payment, "record_id": "duplicate"})
    elif fault == "wrong_currency":
        payment["currency"] = "USD"
    elif fault == "wrong_party":
        payment["party_ref"] = "other"
    elif fault == "invoice_amount":
        invoice["amount"] = "99"
    elif fault == "after_cutoff":
        payment["payment_date"] = "2026-11-01"
    elif fault == "overpayment":
        payment["amount"] = "101"
    rows = workflow.reconcile_open_items(items, evidence, assumptions)
    assert rows[0]["rule_applied"] == "declared_payment_unresolved"
    assert "residual_amount" not in rows[0]

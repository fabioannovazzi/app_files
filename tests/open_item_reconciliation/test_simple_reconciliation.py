"""Normal exact matches need one calculation; ambiguity still requires review."""

from __future__ import annotations

import copy

import pytest

from tests.open_item_reconciliation.test_reconciliation_helpers import load_helpers
from tests.open_item_reconciliation.test_reviewed_tabular_adapter import (
    load_assurance,
    reviewed,
    spec,
    write_source,
)


def exact_case():
    perimeter = {
        "entity_ref": "company",
        "party_ref": "Rossi Srl",
        "currency": "EUR",
        "unit": "EUR",
        "direction_policy": "receivable",
        "allocation_policy": "one_to_one",
    }
    invoice = {
        **perimeter,
        "record_id": "invoice",
        "document_no": "FT-2026-0102",
        "document_date": "2026-07-01",
        "amount": "1220.00",
        "source_role": "open_items",
        "evidence_type": "open_item",
    }
    bank = {
        **perimeter,
        "record_id": "bank",
        "description": "Saldo FT-2026-0102",
        "posting_date": "2026-07-11",
        "amount": "1220.00",
        "source_role": "bank_statement",
        "evidence_type": "external_bank",
    }
    scope = {
        "cutoff_date": "2026-07-01",
        "post_cutoff_events_excluded": False,
        "assurance_run_date": "2026-10-22",
    }
    return invoice, bank, scope


def test_literal_invoice_reference_closes_without_semantics_or_an_accept_click():
    h = load_helpers()
    invoice, bank, scope = exact_case()
    original = copy.deepcopy(bank)

    rows = h.reconcile_open_items([invoice], [bank], scope)
    review = h.automatically_review_exact_matches(
        h.build_codex_review_packet(rows), rows, [bank], scope
    )

    assert rows[0]["rule_applied"] == "external_bank_match"
    assert rows[0]["reconciliation_status"] == "closed"
    assert rows[0]["supporting_bank_date"] == "2026-07-11"
    assert review[0]["review_status"] == "PASS"
    assert review[0]["reviewer_ref"] == "system-exact-match"
    assert "no human or professional approval" in review[0]["review_notes"]
    assert bank == original


@pytest.mark.parametrize(
    "patch",
    [
        {"party_ref": "Different payer"},
        {"currency": "USD"},
        {"entity_ref": "another-company"},
        {"amount": "1219.99"},
        {"amount": "-1220.00"},
        {"posting_date": "2026-06-30"},
        {"posting_date": "invalid"},
        {"description": "Saldo FT-2026-01020"},
        {"description": "Saldo XFT-2026-0102"},
        {"document_no": "DIFFERENT-INVOICE"},
        {"party_ref": ""},
    ],
)
def test_incompatible_or_inexact_evidence_does_not_receive_automatic_review(patch):
    h = load_helpers()
    invoice, bank, scope = exact_case()
    bank.update(patch)

    rows = h.reconcile_open_items([invoice], [bank], scope)
    review = h.automatically_review_exact_matches(
        h.build_codex_review_packet(rows), rows, [bank], scope
    )

    assert review[0]["review_status"] == "PENDING"


@pytest.mark.parametrize("duplicate", ["invoice", "payment"])
def test_duplicate_identity_or_payment_keeps_review_required(duplicate):
    h = load_helpers()
    invoice, bank, scope = exact_case()
    invoices = (
        [invoice, {**invoice, "record_id": "duplicate"}]
        if duplicate == "invoice"
        else [invoice]
    )
    payments = (
        [bank, {**bank, "record_id": "duplicate"}] if duplicate == "payment" else [bank]
    )

    rows = h.reconcile_open_items(invoices, payments, scope)
    review = h.automatically_review_exact_matches(
        h.build_codex_review_packet(rows), rows, payments, scope
    )

    assert {row["review_status"] for row in review} == {"PENDING"}


@pytest.mark.parametrize("label", ["agent:codex-sol", "", None, 123, " reviewer.test"])
def test_mapping_intake_generates_valid_technical_reviewer_metadata(tmp_path, label):
    a = load_assurance()
    path = tmp_path / "source.csv"
    write_source(path)
    mapping = spec(path)
    mapping["reviewer_ref"] = label
    del mapping["reviewed_on"]

    _, decision = reviewed(a, path, mapping)

    assert decision["reviewer_ref"].startswith("agent-")
    assert decision["reviewed_on"] == "2026-10-18"
    assert decision["content"]["tabular"] == mapping["tabular"]

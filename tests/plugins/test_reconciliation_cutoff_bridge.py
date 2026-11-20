"""Synthetic near-amount and cutoff controls, without customer data."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import openpyxl
import pytest
from reportlab.pdfgen import canvas

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1] / "_shared/vendor/modules"))
import bank_first as bf
from balance_bridge import build_balance_bridge, read_balance_evidence
from grouped_review import _summary
from grouped_workbook import export_final_workbook
from local_cash_links import review_population

POLICY = dict(
    default_currency="EUR",
    default_entity_ref="test",
    default_unit="money",
    direction_policy="same_sign",
)


def row(i, amount, day="2027-03-31", **extra):
    return dict(
        transaction_id=i,
        amount_signed=amount,
        transaction_date=day,
        description="Generic posting",
        source_file="source.pdf",
        source_sheet="PDF page 1",
        source_row="1",
        **extra,
    )


@pytest.mark.parametrize("extra", [{}, {"reference": "different"}])
def test_unsupported_near_amount_is_visible_unreserved_and_in_semantic_population(
    extra,
):
    b = [row("bank", "-24.00", reference="bank-only")]
    j = [row("ledger", "-23.77", "2027-04-02", **extra)]
    admitted = bf.admission(
        b,
        j,
        POLICY,
        local_matches=[
            dict(bank_transaction_id="bank", journal_transaction_id="ledger")
        ],
    )
    assert admitted["sure"] == []
    candidate = admitted["probable_candidates"][0]
    assert candidate["difference"] == "-0.23"
    assert candidate["journal_ids"] == ["ledger"]
    assert review_population(b, j, admitted) == (b, j)


def test_shared_reference_retains_difference_and_duplicate_reference_is_not_unique():
    b = [row("b", "-24.00", reference="payment-AB123")]
    j = [row("j", "-23.77", reference="payment-AB123")]
    pair = [dict(bank_transaction_id="b", journal_transaction_id="j")]
    admitted = bf.admission(b, j, POLICY, local_matches=pair)
    group = bf._deterministic(admitted["sure"][0])
    assert group["difference"] == "-0.23"
    assert group["confirmed_discrepancy"]
    assert review_population(b, j, admitted) == ([], [])
    ambiguous = bf.admission(
        b,
        j + [row("alternative", "-23.78", reference="payment-AB123")],
        POLICY,
        local_matches=pair,
    )
    assert not ambiguous["sure"]


def case():
    b = [row("matched", "100"), row("open1", "-20"), row("open2", "-10")]
    j = [row("posted", "100"), row("later", "-19.85", "2027-04-02")]
    relations = [
        dict(
            id="R1",
            bank_ids=["matched"],
            journal_ids=["posted"],
            allocation_state="reserved",
            bank_resolution={"status": "resolved"},
            status="concordant",
        )
    ]
    for side, ids in (("bank", ["open1", "open2"]), ("journal", ["later"])):
        for i in ids:
            relations.append(
                dict(
                    id="R" + str(len(relations) + 1),
                    bank_ids=[i] if side == "bank" else [],
                    journal_ids=[i] if side == "journal" else [],
                    status="unmatched",
                )
            )
    for g in relations:
        g.update(
            title="Synthetic relation",
            rationale="Source review",
            required_documents=[],
            evidence=[],
            bank_sum=str(
                sum(
                    int(r["amount_signed"])
                    for r in b
                    if r["transaction_id"] in g["bank_ids"]
                )
            ),
            journal_sum=str(
                sum(
                    float(r["amount_signed"])
                    for r in j
                    if r["transaction_id"] in g["journal_ids"]
                )
            ),
        )
        from decimal import Decimal

        g["difference"] = str(Decimal(g["bank_sum"]) - Decimal(g["journal_sum"]))
    snapshots = {
        side: dict(
            date="2027-03-31",
            amount=amount,
            currency="EUR",
            entity_ref="test",
            evidence=dict(
                source_file="source.pdf", page=1, quote="Synthetic closing balance"
            ),
        )
        for side, amount in (("bank", "500"), ("journal", "530"))
    }
    return b, j, relations, snapshots


def test_cutoff_bridge_zero_does_not_close_items_and_workbook_separates_later_rows(
    tmp_path,
):
    b, j, relations, evidence = case()
    before = copy.deepcopy(relations)
    bridge = build_balance_bridge(b, j, relations, evidence, POLICY)
    assert bridge["unexplained_difference"] == "0.00"
    assert bridge["bank_open_ids"] == ["open1", "open2"]
    assert bridge["journal_open_ids"] == []
    assert bridge["subsequent_journal_ids"] == ["later"]
    assert bridge["subsequent_journal_net"] == "-19.85"
    assert bridge["balance_gap"] == "-30.00"
    assert relations == before
    summary = _summary(relations, b, j)
    summary.update(currency="EUR", strict_match_count=1)
    path = tmp_path / "bridge.xlsx"
    export_final_workbook(
        path, dict(summary=summary, relations=relations, balance_bridge=bridge), b, j
    )
    book = openpyxl.load_workbook(path, data_only=True)
    values = {r[0]: r[1] for r in book["Sintesi"].values if r[0]}
    assert values["Differenza non spiegata"] == 0
    assert values["Saldo partitario alla stessa data"] == 530
    assert values["Aperti banca alla chiusura (netto)"] == -30
    assert any("Scritture successive" in str(r[0]) for r in book["Sintesi"].values)
    assert book["Banca"]["H7"].value == "Non rilevato nella fonte opposta"
    book.close()


def test_missing_or_incomparable_balance_never_invents_zero():
    b, j, r, e = case()
    for invalid in (
        {},
        {**e, "journal": {**e["journal"], "date": "2027-04-02"}},
        {**e, "bank": {**e["bank"], "currency": "USD"}},
    ):
        bridge = build_balance_bridge(b, j, r, invalid, POLICY)
        assert bridge["status"] == "unavailable"
        assert bridge["missing"]
        assert "unexplained_difference" not in bridge


def test_supported_cross_cutoff_link_is_still_open_at_cutoff():
    b, j, r, e = case()
    r[1].update(
        journal_ids=["later"],
        allocation_state="reserved",
        bank_resolution={"status": "resolved"},
    )
    bridge = build_balance_bridge(b, j, r[:-1], e, POLICY)
    assert bridge["bank_open_ids"] == ["open1", "open2"]
    assert bridge["unexplained_difference"] == "0.00"


def test_supported_difference_is_a_separate_bridge_component():
    b, j, r, e = case()
    j[0]["amount_signed"] = "100.23"
    e["journal"]["amount"] = "530.23"
    bridge = build_balance_bridge(b, j, r, e, POLICY)
    assert bridge["supported_difference"] == "-0.23"
    assert bridge["unexplained_difference"] == "0.00"


def test_pdf_balance_mapping_replays_source_quotes_and_rejects_changed_bytes(tmp_path):
    source = tmp_path / "source.pdf"
    doc = canvas.Canvas(str(source))
    doc.drawString(30, 700, "31/03/2027 Closing balance 500.00")
    doc.save()
    item = dict(
        role="closing_balance",
        reviewed_by="agent",
        source_file=source.name,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        page=1,
        quote="31/03/2027 Closing balance 500.00",
        amount_text="500.00",
        date_text="31/03/2027",
        date_format="%d/%m/%Y",
        cash_sign=1,
        currency="EUR",
        entity_ref="test",
    )
    mapping = tmp_path / "balances.json"
    mapping.write_text(
        json.dumps(
            dict(
                schema_version="journal_bank.balance_evidence.v1",
                bank=item,
                journal=item,
            )
        )
    )
    roots = dict(source_bank=tmp_path, source_journal=tmp_path)
    rows = dict(bank=[row("b", "1")], journal=[row("j", "1")])
    evidence = read_balance_evidence(mapping, roots, rows)
    assert evidence["bank"]["amount"] == "500.00"
    assert evidence["bank"]["date"] == "2027-03-31"
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="changed"):
        read_balance_evidence(mapping, roots, rows)


@pytest.mark.parametrize(
    "mapping",
    [
        [],
        {"schema_version": "journal_bank.balance_evidence.v1", "bank": ["invalid"]},
        {"schema_version": "journal_bank.balance_evidence.v1", "bank": {"quote": 7}},
    ],
)
def test_malformed_balance_mapping_is_a_clear_evidence_error(tmp_path, mapping):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(mapping))
    with pytest.raises(ValueError, match="[Bb]alance"):
        read_balance_evidence(path, {}, {})


def test_available_bank_balance_is_shown_when_ledger_balance_is_missing():
    b, j, r, e = case()
    bridge = build_balance_bridge(b, j, r, {"bank": e["bank"]}, POLICY)
    assert bridge["bank_closing"] == "500.00"
    assert bridge["status"] == "unavailable"
    assert "journal_closing" not in bridge
    assert "unexplained_difference" not in bridge

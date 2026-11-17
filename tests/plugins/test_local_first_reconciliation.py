"""Restore local results without losing grouped semantic investigation."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "plugins/journal-bank-reconciliation/scripts"
    ),
)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bank_first as bf
from test_evidence_retrieval import execute, request
from test_vera_bank_first import REL, NativeFixture, answer, row


@pytest.fixture(autouse=True)
def scoped_imports(monkeypatch):
    monkeypatch.syspath_prepend(
        str(
            Path(__file__).resolve().parents[2]
            / "plugins/journal-bank-reconciliation/scripts"
        )
    )


def pair(bank="b1", journal="j1"):
    return {"bank_transaction_id": bank, "journal_transaction_id": journal}


def attach(group, journal_rows):
    group["journal_ids"] = [r["transaction_id"] for r in journal_rows]
    group["accounting_resolution"]["evidence"].extend(
        {
            "side": "journal",
            "transaction_id": r["transaction_id"],
            "field": "description",
            "quote": r["description"],
        }
        for r in journal_rows
    )


def test_replayed_generic_local_match_finishes_without_a_model_or_invoice_claim(
    tmp_path,
):
    bank = [row("b1", "Bank transfer", "-610")]
    journal = [row("j1", "PAGATA FATTURA", "-610")]
    native = NativeFixture({})
    result = execute(tmp_path, native, bank, journal, local_matches=[pair()])
    assert native.calls == []
    assert result["summary"]["primary_counts"]["deterministic"] == 1
    group = result["groups"][0]
    assert group["journal_ids"] == ["j1"]
    assert group["accounting_resolution"]["scope"] == "cash_reconciliation_only"
    assert group["allocations"] == []
    assert group["proposed_account_codes"] == []
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_local_source_rows_are_not_returned_by_residual_searches(tmp_path):
    bank = [row("b1", "Local payment", "-610"), row("b2", "Residual payment", "-610")]
    journal = [
        row("j1", "Local ledger entry", "-610"),
        row("j2", "Other posting", "-10"),
    ]
    native = NativeFixture({})

    def respond(packet, **_):
        assert "b1" not in {r["transaction_id"] for r in packet["bank_records"]}
        assert "j1" not in {r["transaction_id"] for r in packet["journal_records"]}
        if packet["retrieval"]["round"] == 0:
            return request(
                packet, {"side": "journal", "amount_min": "-610", "amount_max": "-610"}
            )
        assert packet["retrieval"]["pages"][0]["total_candidates"] == 0
        return answer(packet)

    native.respond = respond
    result = execute(tmp_path, native, bank, journal, local_matches=[pair()])
    assert not result["errors"]
    assert [p["stage"] for p in native.calls] == ["luna", "luna", "sol", "sol"]
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


@pytest.mark.parametrize("purpose", ["bookkeeping_check", "audit_reconciliation"])
def test_accounting_mandate_keeps_local_cash_link_and_still_reviews_treatment(
    tmp_path, purpose
):
    bank = [row("b1")]
    journal = [row("j1", "Recorded accounting treatment")]
    native = NativeFixture({"luna": {"complete": False}})
    result = execute(
        tmp_path, native, bank, journal, local_matches=[pair()], purpose=purpose
    )
    assert not result["errors"]
    assert [p["stage"] for p in native.calls] == ["luna", "sol"]
    assert all(
        p["focus"] == [{"bank_ids": ["b1"], "question_scope": "accounting"}]
        for p in native.calls
    )
    assert result["groups"][0]["journal_ids"] == ["j1"]
    assert result["groups"][0]["resolved_at"] == "deterministic"
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_every_focused_small_candidate_set_is_available_without_rediscovery(tmp_path):
    bank = [row(f"b{i}", "Payment", str(-10 - i)) for i in range(5)]
    journal = [row(f"j{i}", "Recorded payment", str(-10 - i)) for i in range(5)]
    native = NativeFixture({})

    def respond(packet, **_):
        assert {r["transaction_id"] for r in packet["journal_records"]} == {
            f"j{i}" for i in range(5)
        }
        assert len(packet["probable_candidates"]) == 5
        assert all(c["preview_complete"] for c in packet["probable_candidates"])
        result = answer(packet)
        for group in result["groups"]:
            identifier = "j" + group["bank_ids"][0][1:]
            attach(group, [r for r in journal if r["transaction_id"] == identifier])
        return result

    native.respond = respond
    result = execute(tmp_path, native, bank, journal, local_matches=[])
    assert not result["errors"]
    assert len(native.calls) == 1
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_sol_adds_missing_link_even_after_first_stage_claims_accounting_complete(
    tmp_path,
):
    bank = [row("b1", "Payment")]
    journal = [row("j1", "Recorded payment")]
    native = NativeFixture({})

    def respond(packet, **_):
        result = answer(packet)
        if packet["stage"] == "sol":
            attach(result["groups"][0], journal)
        return result

    native.respond = respond
    result = execute(tmp_path, native, bank, journal, local_matches=[])
    assert not result["errors"]
    assert [p["stage"] for p in native.calls] == ["luna", "sol"]
    group = result["groups"][0]
    assert group["journal_ids"] == ["j1"]
    assert group["bank_resolution"] == group["history"][0]["bank_resolution"]
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_sol_can_join_explained_unlinked_payments_after_iterative_group_search(
    tmp_path,
):
    bank = [row("b1", "Salary A", "-60"), row("b2", "Salary B", "-40")]
    journal = [
        row(
            "j1",
            "Salary total",
            "-100",
            transaction_date="2026-01-30",
            reference="payroll",
        )
    ]
    native = NativeFixture({})

    def respond(packet, **_):
        if packet["stage"] == "luna":
            return answer(packet, complete=False)
        if packet["retrieval"]["round"] == 0:
            return request(
                packet, {"side": "journal", "field": "reference", "value": "payroll"}
            )
        result = answer(packet)
        group = result["groups"][0]
        group["bank_ids"] = ["b1", "b2"]
        attach(group, journal)
        result["groups"] = [group]
        return result

    native.respond = respond
    result = execute(tmp_path, native, bank, journal, local_matches=[])
    assert not result["errors"]
    assert [p["stage"] for p in native.calls] == ["luna", "sol", "sol"]
    group = result["groups"][0]
    assert group["bank_ids"] == ["b1", "b2"]
    assert group["journal_ids"] == ["j1"]
    assert group["difference"] == "0.00"
    assert len(group["history"]) == 2
    assert {e["transaction_id"] for e in group["bank_resolution"]["evidence"]} == {
        "b1",
        "b2",
    }
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_sol_cannot_reassign_a_reserved_local_link(tmp_path):
    bank = [row("b1")]
    journal = [row("j1", "First posting"), row("j2", "Other posting")]
    native = NativeFixture({})

    def respond(packet, **_):
        result = answer(packet, complete=False)
        if packet["stage"] == "sol":
            attach(result["groups"][0], [journal[1]])
        return result

    native.respond = respond
    result = execute(
        tmp_path,
        native,
        bank,
        journal,
        local_matches=[pair()],
        purpose="bookkeeping_check",
    )
    assert result["errors"]
    assert "cannot reassign" in result["errors"][0]["reason"]
    assert result["groups"][0]["journal_ids"] == ["j1"]


def test_old_saved_admission_is_not_reinterpreted_when_local_matches_are_supplied(
    tmp_path,
):
    bank, journal = [row("b1")], [row("j1")]
    native = NativeFixture({"luna": {"linked": True}})
    first = execute(tmp_path, native, bank, journal)
    before = copy.deepcopy(first["groups"])
    resumed = execute(tmp_path, native, bank, journal, local_matches=[pair()])
    assert len(native.calls) == 1
    assert resumed["groups"] == before
    assert resumed["local_matches"] is None


def test_repeated_fee_pool_is_preserved_as_group_without_inventing_pairs(tmp_path):
    bank = [row("b1", "Transfer fee", "-1.50"), row("b2", "Transfer fee", "-1.50")]
    journal = [row("j1", "Bank charges", "-1.50"), row("j2", "Bank charges", "-1.50")]
    native = NativeFixture({})

    def respond(packet, **_):
        result = answer(packet)
        group = result["groups"][0]
        group["bank_ids"] = ["b1", "b2"]
        group["bank_resolution"]["evidence"].extend(
            result["groups"][1]["bank_resolution"]["evidence"]
        )
        attach(group, journal)
        result["groups"] = [group]
        return result

    native.respond = respond
    result = execute(tmp_path, native, bank, journal, local_matches=[])
    assert not result["errors"]
    assert len(result["groups"]) == 1
    assert result["groups"][0]["allocations"] == []
    assert result["groups"][0]["difference"] == "0.00"
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


@pytest.mark.parametrize("local", [True, False])
def test_opposite_sign_cash_link_keeps_signed_sources_without_false_discrepancy(
    tmp_path, local
):
    bank, journal = [row("b1", amount="-80")], [row("j1", amount="80")]
    relationship = {**REL, "direction_policy": "opposite_sign"}
    native = NativeFixture({"luna": {"linked": True}})

    def respond(packet, **_):
        if not packet["journal_records"]:
            return request(
                packet, {"side": "journal", "amount_min": "80", "amount_max": "80"}
            )
        return answer(packet, linked=True)

    native.respond = respond
    result = bf.run_bank_first(
        bank,
        journal,
        tmp_path,
        source_binding={"client": "synthetic"},
        relationship=relationship,
        invoke=native.invoke,
        select=native.select,
        local_matches=[pair()] if local else [],
    )
    assert not result["errors"]
    group = result["groups"][0]
    assert (group["bank_sum"], group["journal_sum"], group["difference"]) == (
        "-80.00",
        "80.00",
        "0.00",
    )
    assert not group["confirmed_discrepancy"]
    assert len(native.calls) == (0 if local else 2)
    assert bf.replay_retained(result, bank, journal, relationship) == result["groups"]


def test_local_match_retains_reviewed_tolerance_difference(tmp_path):
    bank, journal = [row("b1", amount="-80")], [row("j1", amount="-79.99")]
    result = execute(tmp_path, NativeFixture({}), bank, journal, local_matches=[pair()])
    assert result["groups"][0]["difference"] == "-0.01"
    assert result["groups"][0]["confirmed_discrepancy"]
    assert result["attempts"] == []


@pytest.mark.parametrize("matches", [[pair("missing", "j1")], [pair(), pair()]])
def test_invalid_local_source_edges_are_not_accepted(tmp_path, matches):
    native = NativeFixture({})
    with pytest.raises(
        ValueError, match="outside its source population|Duplicate local match"
    ):
        execute(tmp_path, native, [row("b1")], [row("j1")], local_matches=matches)
    assert not native.calls

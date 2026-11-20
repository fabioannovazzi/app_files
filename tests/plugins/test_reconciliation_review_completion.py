"""Fresh controller regressions use synthetic rows and receipted fixture workers."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "plugins/journal-bank-reconciliation/scripts"
    ),
)
import bank_first as bf
import reconciliation_orchestrator as orch
from test_reconciliation_orchestrator import BANK, JOURNAL, REL, Worker, action


def response(packet, kind):
    return {
        **action(packet, kind),
        "open_reviews": [],
        "accounting_notes": [],
        "reviewed_group_ids": [],
    }


def open_review(packet):
    result = response(packet, "review_open")
    result["open_reviews"] = [
        dict(
            bank_id=r["transaction_id"],
            explanation="Nessuna registrazione supportata dalle fonti disponibili.",
            evidence_fields=["description"],
            document_request="Richiedere la ricevuta del commerciante indicato e la registrazione del pagamento.",
        )
        for r in packet["bank_records"]
    ]
    return result


def notes(packet):
    result = response(packet, "review_notes")
    result["reviewed_group_ids"] = [g["bank_ids"][0] for g in packet["linked_groups"]]
    records = {s: bf._records(packet[s + "_records"]) for s in ("bank", "journal")}
    result["accounting_notes"] = [
        dict(
            group_id=g["bank_ids"][0],
            explanation="Verificare identità del commerciante; collegamento monetario conservato.",
            questions=[
                "Richiedere fattura e ricevuta del commerciante per spiegare i nomi differenti."
            ],
            evidence=[
                dict(
                    side=s,
                    transaction_id=i,
                    field="description",
                    quote=records[s][i]["description"],
                )
                for s in records
                for i in g[s + "_ids"]
            ],
        )
        for g in packet["linked_groups"]
    ]
    return result


def run(path, worker, bank=None, journal=None, **kwargs):
    return orch.run_orchestrator(
        bank or BANK,
        journal or JOURNAL,
        path,
        source_binding={"workflow": "journal-bank-reconciliation", "hash": "synthetic"},
        relationship=REL,
        local_matches=[],
        invoke=worker.invoke,
        select=worker.select,
        **kwargs,
    )


def approve(packet):
    result = response(packet, "decide_candidates")
    result.update(
        candidate_indices=[0],
        evidence_fields={"bank": ["description"], "journal": ["description"]},
    )
    return result


def test_local_searches_precede_model_and_notes_cannot_change_link(tmp_path):
    worker = Worker([approve, notes])
    result = run(tmp_path, worker)
    assert len(worker.calls) == 2
    assert len(worker.calls[0]["search_history"]) == 3
    assert worker.calls[0]["probable_candidates"][0]["journal_ids"] == ["j"]
    group = result["groups"][0]
    assert group["allocation_state"] == "reserved"
    assert group["bank_ids"] == ["b"] and group["journal_ids"] == ["j"]
    assert group["bank_resolution"]["status"] == "resolved"
    assert group["accounting_resolution"]["status"] == "partial"
    assert result["questions"]["accounting"][0]["questions"]
    assert result["summary"]["review_complete"]
    assert orch.replay_result(result, BANK, JOURNAL, REL) == result["groups"]


def test_unsupported_near_amount_gets_reviewed_open_without_search_calls(tmp_path):
    journal = [
        {
            **JOURNAL[0],
            "amount_signed": "-33.96",
            "description": "Generic invoice posting",
        }
    ]
    worker = Worker([open_review])
    result = run(tmp_path, worker, journal=journal)
    assert worker.calls[0]["review_phase"] == "investigation"
    assert result["groups"][0]["allocation_state"] != "reserved"
    assert result["summary"]["primary_counts"]["unprocessed"] == 0
    assert result["summary"]["review_complete"]
    assert result["questions"]["bank"][0]["questions"]


def test_cache_survives_retry_and_replay_without_rerunning_discovery(
    tmp_path, monkeypatch
):
    def repeated(packet):
        result = response(packet, "run")
        result["routine"] = "date_window"
        result["bank_ids"] = ["b"]  # Same scope as empty arrays, canonical key.
        result["journal_ids"] = ["j"]
        return result

    worker = Worker([repeated, open_review])
    partial = run(tmp_path, worker, limits={"calls": 1})
    assert partial["attempts"][0]["result"]["cache_hit"]

    def forbidden(*args, **kwargs):
        raise AssertionError("A completed local search ran again")

    monkeypatch.setattr(orch, "discover", forbidden)
    result = run(tmp_path, worker, resume_checkpoint=True)
    assert worker.calls[1]["review_phase"] == "final_review"
    assert result["summary"]["review_complete"]
    assert len(result["orchestrator_state"]["preflight"]) == 3
    assert orch.replay_result(result, BANK, JOURNAL, REL) == result["groups"]


def test_finish_cannot_silently_leave_unreviewed_rows(tmp_path):
    worker = Worker([lambda p: response(p, "finish")])
    result = run(tmp_path, worker, limits={"calls": 1})
    assert not result["summary"]["review_complete"]
    assert result["summary"]["primary_counts"]["unprocessed"] == 1
    assert "explicit disposition" in result["attempts"][0]["error"]


def test_notes_reject_unrelated_source_quote_without_changing_cash(tmp_path):
    def invented(packet):
        result = notes(packet)
        result["accounting_notes"][0]["evidence"][0]["quote"] = "invented merchant"
        return result

    worker = Worker([approve, invented])
    result = run(tmp_path, worker, limits={"calls": 2})
    assert result["groups"][0]["allocation_state"] == "reserved"
    assert result["attempts"][1]["status"] == "rejected"
    assert not result["summary"]["review_complete"]


def test_changed_population_has_different_search_identity():
    action1 = dict(action="run", routine="date_window", window_days=7, expression="")
    before = orch._search_key(action1, BANK, JOURNAL)
    changed = copy.deepcopy(JOURNAL)
    changed[0]["amount_signed"] = "-1.00"
    assert before != orch._search_key(action1, BANK, changed)
    assert before == orch._search_key(
        action1, list(reversed(BANK)), list(reversed(JOURNAL))
    )


def test_clean_group_acknowledgement_does_not_invent_invoice_approval(tmp_path):
    def clean(packet):
        result = response(packet, "review_notes")
        result["reviewed_group_ids"] = [
            g["bank_ids"][0] for g in packet["linked_groups"]
        ]
        return result

    worker = Worker([approve, clean])
    result = run(tmp_path, worker)
    assert result["summary"]["accounting_notes_complete"]
    assert result["summary"]["cash_review_complete"]
    assert (
        result["groups"][0]["accounting_resolution"]["scope"]
        == "document_questions_only_not_expense_approval"
    )
    assert result["questions"]["accounting"] == []


def test_more_than_one_packet_gets_individual_open_dispositions(tmp_path):
    bank = [
        {**BANK[0], "transaction_id": f"b{i}", "amount_signed": str(-1000 - i)}
        for i in range(26)
    ]
    worker = Worker([open_review, open_review])
    result = run(tmp_path, worker, bank=bank)
    assert [len(p["bank_records"]) for p in worker.calls] == [25, 1]
    assert len(result["groups"]) == 26
    assert result["summary"]["primary_counts"]["unprocessed"] == 0
    assert result["summary"]["review_complete"]
    assert len(result["orchestrator_state"]["preflight"]) == 3


def test_notes_must_acknowledge_all_groups_before_completion(tmp_path):
    worker = Worker([approve, lambda p: response(p, "review_notes")])
    result = run(tmp_path, worker, limits={"calls": 2})
    assert result["summary"]["cash_review_complete"]
    assert not result["summary"]["accounting_notes_complete"]
    assert not result["summary"]["review_complete"]
    assert result["groups"][0]["journal_ids"] == ["j"]


def test_empty_standard_searches_still_allow_a_model_proposed_net_alternative(tmp_path):
    bank = [
        {**BANK[0], "transaction_id": "b1", "amount_signed": "-60"},
        {**BANK[0], "transaction_id": "b2", "amount_signed": "-40"},
    ]
    journal = [
        {**JOURNAL[0], "transaction_id": "j1", "amount_signed": "-70"},
        {**JOURNAL[0], "transaction_id": "j2", "amount_signed": "-30"},
    ]

    def generated(packet):
        assert packet["review_phase"] == "investigation"
        assert not packet["probable_candidates"]
        result = response(packet, "generate")
        result["expression"] = (
            "[{'bank_ids':[r['transaction_id'] for r in bank], 'journal_ids':[r['transaction_id'] for r in journal]}]"
        )
        return result

    worker = Worker([generated, approve, notes])
    result = run(tmp_path, worker, bank=bank, journal=journal)
    assert result["summary"]["review_complete"]
    assert result["groups"][0]["bank_ids"] == ["b1", "b2"]
    assert result["groups"][0]["journal_ids"] == ["j1", "j2"]


def test_empty_text_search_is_retained_across_native_retry(tmp_path, monkeypatch):
    from evidence_retrieval import EvidenceIndex, query_schema

    def inspect(packet):
        result = response(packet, "inspect")
        result["query"] = {key: None for key in query_schema()["properties"]}
        result["query"].update(side="journal", text="Missing document")
        return result

    worker = Worker([inspect, open_review])
    first = run(tmp_path, worker, limits={"calls": 1})
    assert first["attempts"][0]["status"] == "accepted"

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed text search ran again")

    monkeypatch.setattr(EvidenceIndex, "search", forbidden)
    final = run(tmp_path, worker, resume_checkpoint=True)
    assert final["summary"]["review_complete"]
    assert len(worker.calls[1]["search_history"]) == 4
    assert worker.calls[1]["review_phase"] == "final_review"


def test_timed_out_notes_shrink_and_resume_without_repeating_cash_work(
    tmp_path, monkeypatch
):
    bank = [
        {**BANK[0], "transaction_id": f"b{i}", "amount_signed": str(-100 - i)}
        for i in range(2)
    ]
    journal = [
        {**JOURNAL[0], "transaction_id": f"j{i}", "amount_signed": str(-100 - i)}
        for i in range(2)
    ]

    def approve_all(packet):
        result = approve(packet)
        result["candidate_indices"] = list(range(len(packet["probable_candidates"])))
        return result

    def timeout(packet):
        assert len(packet["linked_groups"]) == 2
        raise RuntimeError("Worker process exceeded its time limit")

    worker = Worker([approve_all, timeout, notes, notes])
    partial = run(tmp_path, worker, bank=bank, journal=journal, limits={"calls": 2})
    assert partial["summary"]["cash_review_complete"]
    assert not partial["summary"]["accounting_notes_complete"]
    assert partial["attempts"][-1]["next_notes_group_limit"] == 1

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed search ran again after notes timeout")

    monkeypatch.setattr(orch, "discover", forbidden)
    final = run(tmp_path, worker, bank=bank, journal=journal, resume_checkpoint=True)
    assert final["summary"]["review_complete"]
    assert [len(p["linked_groups"]) for p in worker.calls[2:]] == [1, 1]
    assert orch.replay_result(final, bank, journal, REL) == final["groups"]

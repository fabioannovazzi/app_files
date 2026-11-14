"""Synthetic retrieval correctness and common-controller regressions."""

from __future__ import annotations

import copy
import json
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
from evidence_retrieval import EvidenceIndex
from test_vera_bank_first import REL, NativeFixture, answer, row


@pytest.fixture(autouse=True)
def scoped_imports(monkeypatch):
    monkeypatch.syspath_prepend(
        str(
            Path(__file__).resolve().parents[2]
            / "plugins/journal-bank-reconciliation/scripts"
        )
    )


def test_retrieval_preserves_unicode_in_native_prompt_and_saved_replay(
    tmp_path, monkeypatch
):
    import io

    original_text_encoding = io.text_encoding
    monkeypatch.setattr(
        io,
        "text_encoding",
        lambda encoding, stacklevel=2: original_text_encoding(encoding or "cp1252"),
    )
    bank = [row("b1", "Caffè 東京 ↳")]
    native = NativeFixture({})

    result = execute(tmp_path, native, bank=bank)

    assert result["errors"] == []
    assert native.calls[0]["bank_records"][0]["description"] == "Caffè 東京 ↳"
    assert bf.replay_retained(result, bank, [], REL) == result["groups"]
    assert "Caffè 東京 ↳" in (
        tmp_path / "bank-first-attempts/00001-luna/prompt.md"
    ).read_text(encoding="utf-8")


def test_index_pages_keep_alternatives_and_delayed_records():
    rows = [
        row(f"j{i}", reference="invoice-7", transaction_date="2024-01-01")
        for i in range(40)
    ]
    index = EvidenceIndex([], rows, {"client": "one"}, REL, 16)
    first = index.search(
        {"side": "journal", "field": "reference", "value": "invoice-7"}
    )
    second = index.search({**first["query"], "cursor": first["next_cursor"]})
    third = index.search({**first["query"], "cursor": second["next_cursor"]})
    assert (
        first["total_candidates"],
        first["remaining_unread"],
        third["returned"],
    ) == (40, 24, 8)
    assert third["records"][-1]["transaction_id"] == "j39"
    assert third["coverage"] == "complete_for_predicates"
    assert first["absence_is_global"] is False
    assert index.get("journal", ["j39"])[0]["transaction_date"] == "2024-01-01"


def test_alias_requires_provenance_and_does_not_invent_identity():
    index = EvidenceIndex(
        [],
        [row("j1", counterparty="Legal Name")],
        {},
        {
            **REL,
            "documented_aliases": [
                {
                    "canonical": "Legal Name",
                    "alias": "Trading Name",
                    "source_ref": "contract:page2",
                }
            ],
        },
    )
    result = index.search(
        {"side": "journal", "field": "counterparty", "value": "Trading Name"}
    )
    assert result["records"][0]["reason"] == "documented alias: contract:page2"
    assert (
        index.search({"side": "journal", "text": "nonexistent"})["total_candidates"]
        == 0
    )
    with pytest.raises(ValueError, match="provenance"):
        EvidenceIndex(
            [],
            [row("j1")],
            {},
            {**REL, "documented_aliases": [{"canonical": "x", "alias": "y"}]},
        )


def test_cursor_cannot_cross_query_client_or_source():
    index = EvidenceIndex([], [row("j1"), row("j2")], {"client": "one"}, REL, 1)
    cursor = index.search({"side": "journal"})["next_cursor"]
    other = EvidenceIndex([], [row("j1"), row("j2")], {"client": "two"}, REL, 1)
    with pytest.raises(ValueError, match="another"):
        other.search({"side": "journal", "cursor": cursor})
    with pytest.raises(ValueError, match="another"):
        index.search({"side": "bank", "cursor": cursor})
    with pytest.raises(ValueError, match="Unknown"):
        index.search({"side": "journal", "sql": "DROP TABLE records"})
    with pytest.raises(ValueError, match="outside"):
        index.get("journal", ["foreign-id"])


def test_group_members_amount_ranges_and_text_are_independent_filters():
    index = EvidenceIndex(
        [],
        [
            row("a", "Payroll January", amount="-45.00", group_id="payroll"),
            row(
                "b",
                "Payroll late",
                amount="-55.00",
                group_id="payroll",
                transaction_date="2026-04-30",
            ),
            row("c", "Other", amount="-45.00"),
        ],
        {},
        REL,
        1,
    )
    result = index.search({"side": "journal", "field": "group_id", "value": "payroll"})
    assert result["total_candidates"] == 2
    assert (
        index.search({"side": "journal", "text": "late"})["records"][0][
            "transaction_id"
        ]
        == "b"
    )
    assert (
        index.search(
            {"side": "journal", "amount_min": "-50.00", "amount_max": "-40.00"}
        )["total_candidates"]
        == 2
    )


def request(packet, query, retain=None):
    return {
        "packet_sha256": packet["packet_sha256"],
        "groups": [],
        "evidence_requests": [query],
        "retain": retain or {"bank": [], "journal": []},
        "working_note": "Investigating alternatives; no accounting conclusion yet.",
    }


def execute(tmp_path, native, bank=None, journal=None, **kwargs):
    return bf.run_bank_first(
        bank or [row("b1")],
        journal or [],
        tmp_path,
        source_binding={"client": "synthetic"},
        relationship=REL,
        invoke=native.invoke,
        select=native.select,
        **kwargs,
    )


def test_model_finds_initially_excluded_record_and_replays_without_calls(tmp_path):
    bank = [row("b1", "Payment title-X", reference="title-X")]
    journal = [row(f"j{i}", "Payment title-X", reference="title-X") for i in range(20)]
    native = NativeFixture({})

    def respond(packet, **_):
        page = packet["retrieval"]["pages"][0]
        if page["next_cursor"]:
            return request(packet, {**page["query"], "cursor": page["next_cursor"]})
        result = answer(packet, linked=True)
        return result

    native.respond = respond
    result = execute(tmp_path, native, bank, journal)
    assert not result["errors"]
    assert len(native.calls) == 2
    assert len(native.calls[0]["journal_records"]) == 16
    assert len(native.calls[1]["journal_records"]) == 4
    assert result["groups"][0]["journal_ids"] == [
        "j16"
    ]  # indexed page order is stable input order
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]
    execute(tmp_path, native, bank, journal)
    assert len(native.calls) == 2


def test_source_projections_follow_each_submitted_page(tmp_path):
    bank = [row("b1", reference="title-X")]
    journal = [row(f"j{i}", reference="title-X") for i in range(20)]
    projections = [
        {"record_id": record["transaction_id"], "fields": ["original_amount"]}
        for record in bank + journal
    ]
    submissions = []
    native = NativeFixture({})
    invoke = native.invoke

    def capture(**kwargs):
        submissions.append(kwargs["source_records"])
        return invoke(**kwargs)

    def respond(packet, **_):
        page = packet["retrieval"]["pages"][0]
        if page["next_cursor"]:
            return request(packet, {**page["query"], "cursor": page["next_cursor"]})
        return answer(packet, linked=True)

    native.invoke = capture
    native.respond = respond
    result = execute(tmp_path, native, bank, journal, source_records=projections)

    assert not result["errors"]
    assert submissions == [
        [projections[0], *sorted(projections[1:17], key=lambda r: r["record_id"])],
        [projections[0], *projections[17:]],
    ]


def test_sol_can_search_outside_initial_context(tmp_path):
    native = NativeFixture({})

    def respond(packet, **_):
        if packet["stage"] == "luna":
            return answer(packet, resolved=False, complete=False)
        if packet["retrieval"]["round"] == 0:
            return request(packet, {"side": "journal", "text": "late evidence"})
        return answer(packet, linked=True)

    native.respond = respond
    bank = [row("b1")]
    journal = [row("delayed", "late evidence", "-81.00", transaction_date="2025-01-01")]
    result = execute(tmp_path, native, bank, journal)
    assert not result["errors"]
    assert result["summary"]["primary_counts"]["sol"] == 1
    assert result["groups"][0]["journal_ids"] == ["delayed"]
    assert native.calls[1]["journal_records"] == []
    assert len(native.calls[1]["prior_conclusions"]) == 1
    assert native.calls[1]["retrieval"]["prior_investigations"] == []
    prior_search = result["retained_native_evidence"][0]["packet"]["retrieval"]
    assert prior_search["search_count"] == 1
    assert prior_search["recent_searches"][0]["total_candidates"] == 0
    assert "retrieval_context" not in native.calls[1]["prior_conclusions"][0]
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


def test_budget_is_technical_and_denial_can_resume(tmp_path):
    native = NativeFixture({})
    original = native.invoke

    def denied(**kwargs):
        raise RuntimeError("host refused")

    native.invoke = denied
    result = execute(tmp_path, native)
    assert result["summary"]["primary_counts"]["error"] == 1
    assert result["questions"]["bank"] == []
    native.invoke = original
    resumed = execute(tmp_path, native)
    assert not resumed["errors"]
    assert resumed["summary"]["primary_counts"]["luna"] == 1
    limited = execute(
        tmp_path / "small", native, retrieval_budget={"context_bytes": 100}
    )
    assert (
        "technical" in limited["errors"][0]["reason"]
        or "budget" in limited["errors"][0]["reason"]
    )
    assert limited["questions"]["bank"] == []


def test_query_chain_tampering_cannot_replay(tmp_path):
    native = NativeFixture({})
    result = execute(tmp_path, native)
    result["retained_native_evidence"][0]["packet"]["retrieval"]["not_in_context"][
        "journal"
    ] = 99
    result["content_sha256"] = bf.digest(
        {k: v for k, v in result.items() if k != "content_sha256"}
    )
    with pytest.raises(ValueError, match="Retained (evidence|serialization)"):
        bf.replay_retained(result, [row("b1")], [], REL)


def test_global_reservation_rejects_reuse_across_focus_batches(tmp_path):
    native = NativeFixture({})

    def respond(packet, **_):
        first = answer({**packet, "focus": packet["focus"][:1]}, linked=True)
        rest = answer({**packet, "focus": packet["focus"][1:]})
        return {
            "packet_sha256": packet["packet_sha256"],
            "groups": first["groups"] + rest["groups"],
        }

    native.respond = respond
    result = execute(
        tmp_path, native, [row(f"b{i}") for i in range(26)], [row("journal")]
    )
    assert result["errors"]
    assert "ownership conflict" in result["errors"][0]["reason"]
    assert result["summary"]["primary_counts"]["luna"] == 25
    assert result["questions"]["bank"] == []


def test_concurrent_controller_cannot_allocate_stale_state(tmp_path):
    from retrieval_review import _run_lock

    native = NativeFixture({})
    with _run_lock(tmp_path):
        with pytest.raises(RuntimeError, match="Another controller"):
            execute(tmp_path, native)
    assert native.calls == []


def test_source_change_during_worker_is_rejected_before_acceptance(tmp_path):
    native = NativeFixture({})
    calls = []

    def check():
        calls.append(True)
        if len(calls) > 1:
            raise RuntimeError("source changed")

    result = execute(tmp_path, native, source_check=check)
    assert result["groups"] == []
    assert "source changed" in result["errors"][0]["reason"]


def test_round_budget_does_not_invent_human_question(tmp_path):
    native = NativeFixture({})
    native.respond = lambda packet, **_: request(
        packet, {"side": "journal", "text": f"unseen{packet['retrieval']['round']}"}
    )
    result = execute(tmp_path, native, retrieval_budget={"max_rounds": 1})
    assert "technical deferral" in result["errors"][0]["reason"]
    assert result["questions"]["bank"] == []
    assert result["summary"]["primary_counts"]["human"] == 0


def test_search_handoff_is_bounded_and_marks_omitted_history():
    from retrieval_review import _advance, _initial, _packet

    bank = [row("b1")]
    index = EvidenceIndex(bank, [], {}, REL)
    admitted = bf.admission(bank, [], REL)
    focus = [{"bank_ids": ["b1"], "question_scope": "bank"}]
    session = _initial(index, focus, [])
    from evidence_retrieval import DEFAULT_BUDGET

    for n in range(12):
        packet = _packet(
            index,
            session,
            focus,
            [],
            admitted,
            {},
            REL,
            "luna",
            "bank_open_items",
            DEFAULT_BUDGET,
        )
        session = _advance(
            index,
            session,
            packet,
            request(packet, {"side": "journal", "text": f"query{n}"}),
        )
    packet = _packet(
        index,
        session,
        focus,
        [],
        admitted,
        {},
        REL,
        "luna",
        "bank_open_items",
        DEFAULT_BUDGET,
    )
    assert packet["retrieval"]["search_count"] == 13
    assert len(packet["retrieval"]["recent_searches"]) == 8
    assert packet["retrieval"]["omitted_search_count"] == 5
    assert all("records" not in item for item in packet["retrieval"]["recent_searches"])


def test_historical_checkpoint_retains_citation_outside_group_and_resumes_only_sol(
    tmp_path, monkeypatch
):
    """The 0.1.625 packet drops cited rows after a retrieval page is replaced."""
    import retrieval_review as rr

    bank = [row("bank", reference="initial")]
    journal = [
        row("initial-row", reference="initial"),
        row("cited-only", "Supporting posting", reference="other"),
    ]
    native = NativeFixture({})

    def respond(packet, **_):
        if packet["stage"] == "luna" and packet["retrieval"]["round"] == 0:
            return request(
                packet,
                {"side": "journal", "field": "transaction_id", "value": "cited-only"},
            )
        response = answer(packet, complete=packet["stage"] == "sol")
        if packet["stage"] == "luna":
            response["groups"][0]["accounting_resolution"]["evidence"].append(
                {
                    "side": "journal",
                    "transaction_id": "cited-only",
                    "field": "description",
                    "quote": "Supporting posting",
                }
            )
        return response

    native.respond = respond
    original_packet = rr._packet

    def legacy_packet(*args, **kwargs):
        return original_packet(*args, **{**kwargs, "projection": 1})

    with monkeypatch.context() as old:
        old.setattr(rr, "_packet", legacy_packet)
        old.setattr(rr, "_implementation_digest", lambda: rr.LEGACY_IMPLEMENTATION)
        with pytest.raises(ValueError, match="Unknown journal row reference"):
            execute(tmp_path, native, bank, journal)
    retained = {
        p: p.read_bytes()
        for p in (tmp_path / "bank-first-attempts").rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="explicit resume_checkpoint"):
        execute(tmp_path, native, bank, journal)
    native.calls.clear()

    result = execute(tmp_path, native, bank, journal, resume_checkpoint=True)

    assert [call["stage"] for call in native.calls] == ["sol"]
    assert [r["transaction_id"] for r in native.calls[0]["journal_records"]] == [
        "cited-only",
        "initial-row",
    ]
    assert result["groups"][0]["journal_ids"] == []
    assert not result["errors"]
    assert result["implementation_transitions"][0]["retained_attempt_count"] == 2
    assert {p: p.read_bytes() for p in retained} == retained
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]
    native.calls.clear()
    assert execute(tmp_path, native, bank, journal)["groups"] == result["groups"]
    assert native.calls == []


def test_utf8_upgrade_keeps_completed_0627_checkpoint_without_model_replay(
    tmp_path, monkeypatch
):
    import retrieval_review as rr

    native = NativeFixture({})
    with monkeypatch.context() as old:
        old.setattr(rr, "_implementation_digest", lambda: rr.UTF8_PREDECESSOR)
        previous = execute(tmp_path, native)
    retained = {
        p: p.read_bytes()
        for p in (tmp_path / "bank-first-attempts").rglob("*")
        if p.is_file()
    }
    assert bf.replay_retained(previous, [row("b1")], [], REL) == previous["groups"]
    native.calls.clear()

    resumed = execute(tmp_path, native, resume_checkpoint=True)

    assert native.calls == []
    assert resumed["groups"] == previous["groups"]
    assert {p: p.read_bytes() for p in retained} == retained
    assert (
        resumed["implementation_transitions"][0]["from_implementation_sha256"]
        == rr.UTF8_PREDECESSOR
    )


def test_reference_closure_visits_nested_allocations_and_citations():
    assert bf.referenced_rows(
        {
            "bank_ids": ["b1"],
            "journal_ids": [],
            "accounting_resolution": {
                "evidence": [{"side": "journal", "transaction_id": "j-evidence"}]
            },
            "allocations": [{"source_id": "b2", "target_id": "j-allocation"}],
        }
    ) == {"bank": {"b1", "b2"}, "journal": {"j-evidence", "j-allocation"}}


@pytest.mark.parametrize(
    "implementation", ["LEGACY_IMPLEMENTATION", "UTF8_PREDECESSOR"]
)
@pytest.mark.parametrize("damage", ["source", "binding", "receipt"])
def test_checkpoint_upgrade_rejects_changed_evidence_without_launch(
    tmp_path, monkeypatch, damage, implementation
):
    import retrieval_review as rr

    native = NativeFixture({})
    original_packet = rr._packet
    with monkeypatch.context() as old:
        old.setattr(rr, "_implementation_digest", lambda: getattr(rr, implementation))
        old.setattr(
            rr,
            "_packet",
            lambda *a, **kw: original_packet(*a, **{**kw, "projection": 1}),
        )
        result = execute(tmp_path, native)
    assert bf.replay_retained(result, [row("b1")], [], REL) == result["groups"]
    if damage == "binding":
        state_path = tmp_path / "bank_first_state.json"
        state = json.loads(state_path.read_text())
        state["binding_sha256"] = "0" * 64
        bf._save(state_path, state)
    elif damage == "receipt":
        (tmp_path / "bank-first-attempts/00001-luna/receipt.json").write_text("{}")
    native.calls.clear()
    before = (tmp_path / "bank_first_state.json").read_bytes()

    with pytest.raises(ValueError, match="different source|evidence changed"):
        execute(
            tmp_path,
            native,
            bank=[row("b1", "changed")] if damage == "source" else None,
            resume_checkpoint=True,
        )

    assert native.calls == []
    assert (tmp_path / "bank_first_state.json").read_bytes() == before


def test_explicit_recovery_cannot_start_an_empty_run(tmp_path):
    native = NativeFixture({})

    with pytest.raises(ValueError, match="existing saved state"):
        execute(tmp_path, native, resume_checkpoint=True)

    assert native.calls == []
    assert not (tmp_path / "bank_first_state.json").exists()


def test_checkpoint_upgrade_keeps_pending_native_request_without_duplicate_launch(
    tmp_path, monkeypatch
):
    import retrieval_review as rr
    from native_host_worker import NativeWorkerPending

    native = NativeFixture({})

    def pending(**kwargs):
        raise NativeWorkerPending("Synthetic native worker remains pending")

    native.invoke = pending
    with monkeypatch.context() as old:
        old.setattr(rr, "_implementation_digest", lambda: rr.LEGACY_IMPLEMENTATION)
        with pytest.raises(NativeWorkerPending):
            execute(tmp_path, native)
    before = (tmp_path / "bank_first_state.json").read_bytes()

    with pytest.raises(ValueError, match="pending native worker"):
        execute(tmp_path, native, resume_checkpoint=True)

    assert native.calls == []
    assert (tmp_path / "bank_first_state.json").read_bytes() == before


def test_context_budget_batches_whole_focus_without_dropping_bank_work(tmp_path):
    bank = [row(f"b{i:02d}", "Causale documentata " + "x" * 700) for i in range(25)]
    native = NativeFixture({"luna": {"complete": False}})
    budget = {"context_bytes": 24000}

    result = execute(tmp_path, native, bank=bank, retrieval_budget=budget)

    assert not result["errors"]
    assert result["summary"]["secondary_counts"]["complete"] == 25
    assert len([p for p in native.calls if p["stage"] == "sol"]) > 1
    assert all(
        a["context_bytes"] <= budget["context_bytes"] for a in result["attempts"]
    )
    assert sorted(i for g in result["groups"] for i in g["bank_ids"]) == [
        f"b{i:02d}" for i in range(25)
    ]
    assert bf.replay_retained(result, bank, [], REL) == result["groups"]
    native.calls.clear()
    assert (
        execute(tmp_path, native, bank=bank, retrieval_budget=budget)["groups"]
        == result["groups"]
    )
    assert native.calls == []


def test_sol_timeout_resume_splits_focus_and_replays_completed_work(tmp_path):
    bank = [row(f"b{i}") for i in range(7)]
    native = NativeFixture({"luna": {"complete": False}})
    original = native.invoke

    def time_out_sol(**kwargs):
        if kwargs["worker_selection"]["model"] == "fixture-sol":
            raise ValueError("Worker process exceeded its time limit")
        return original(**kwargs)

    native.invoke = time_out_sol
    interrupted = execute(tmp_path, native, bank=bank)
    assert interrupted["attempts"][-1]["status"] == "technical_error"

    native.calls.clear()
    native.invoke = original
    resumed = execute(tmp_path, native, bank=bank, resume_checkpoint=True)

    assert resumed["errors"] == []
    assert [packet["stage"] for packet in native.calls] == ["sol", "sol"]
    assert [len(packet["focus"]) for packet in native.calls] == [5, 2]
    assert bf.replay_retained(resumed, bank, [], REL) == resumed["groups"]

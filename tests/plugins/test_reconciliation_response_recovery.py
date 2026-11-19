"""Source-backed cash evidence and bounded answer recovery; synthetic workers only."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bank_first as bf
from test_evidence_retrieval import execute, request
from test_vera_bank_first import REL, NativeFixture, answer, row


@pytest.fixture(autouse=True)
def source_imports(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))


def reference_answer(packet, **_):
    # The reusable fixture constructs its answer from descriptions. Substitute
    # only in its scaffold, then quote the real packet's explicit references.
    scaffold = copy.deepcopy(packet)
    for side in ("bank", "journal"):
        for record in scaffold[side + "_records"]:
            record.setdefault("description", record["reference"])
    response = answer(scaffold)
    citations = [
        {
            "side": side,
            "transaction_id": record["transaction_id"],
            "field": "reference",
            "quote": record["reference"],
        }
        for side in ("bank", "journal")
        for record in packet[side + "_records"]
    ]
    for group in response["groups"]:
        group["bank_resolution"]["evidence"] = citations
        group["accounting_resolution"]["evidence"] = citations
    return response


@pytest.mark.parametrize("purpose", ["bookkeeping_check", "audit_reconciliation"])
def test_qualified_reference_only_csv_match_completes_accounting_review(
    tmp_path, purpose
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _prepare_reviewed_recipe,
        _read_csv_dicts,
        _save_csv,
        load_core,
    )

    core = load_core()
    bank_path, journal_path = tmp_path / "bank.csv", tmp_path / "journal.csv"
    for path in (bank_path, journal_path):
        _save_csv(
            path, [["Date", "Amount", "Reference"], ["2026-11-17", "-80", "PAY123"]]
        )
    recipe = _prepare_reviewed_recipe(
        core,
        bank_path,
        journal_path,
        tmp_path / "inspection",
        tolerance="0",
        policy_updates={"direction_policy": "same_sign"},
    )
    local = core.run_reconciliation(
        bank_path, journal_path, tmp_path / "local", recipe_path=recipe
    )
    policy = json.loads(recipe.read_text())["relationship"]["policy"]
    native = NativeFixture({})
    native.respond = reference_answer
    bank = _read_csv_dicts(tmp_path / "local/normalized_bank.csv")
    journal = _read_csv_dicts(tmp_path / "local/normalized_journal.csv")
    pairs = local.matches.select(
        "bank_transaction_id", "journal_transaction_id"
    ).to_dicts()

    result = bf.run_bank_first(
        bank,
        journal,
        tmp_path / "review",
        source_binding={"client": "synthetic"},
        relationship=policy,
        purpose=purpose,
        local_matches=pairs,
        invoke=native.invoke,
        select=native.select,
    )

    assert len(pairs) == 1
    assert result["errors"] == []
    assert len(native.calls) == 1
    assert result["groups"][0]["resolved_at"] == "deterministic"
    assert result["groups"][0]["accounting_resolution"]["status"] == "complete"
    assert result["groups"][0]["allocations"] == []
    assert bf.replay_retained(result, bank, journal, policy) == result["groups"]


def bad_answer(packet, **_):
    response = answer(packet, linked=bool(packet["journal_records"]))
    response["groups"][0]["bank_resolution"]["evidence"][0][
        "quote"
    ] = "fabricated quote"
    return response


def test_invalid_first_stage_answers_escalate_without_accepting_or_replaying_them(
    tmp_path,
):
    bank, journal = [row("b1")], [row("j1", transaction_date="2026-01-09")]
    native = NativeFixture({})
    native.respond = lambda packet, **_: (
        bad_answer(packet) if packet["stage"] == "luna" else answer(packet, linked=True)
    )

    result = execute(tmp_path, native, bank, journal, local_matches=[])

    assert [p["stage"] for p in native.calls] == ["luna", "luna", "luna", "sol"]
    assert result["errors"] == []
    assert result["groups"][0]["resolved_at"] == "sol"
    assert result["groups"][0]["history"] == []
    assert result["attempts"][2]["status"] == "escalated_response"
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]
    native.calls.clear()
    assert (
        execute(tmp_path, native, bank, journal, local_matches=[])["groups"]
        == result["groups"]
    )
    assert native.calls == []


def test_stronger_stage_failures_remain_bounded_and_do_not_become_matches(tmp_path):
    native = NativeFixture({})
    native.respond = bad_answer

    result = execute(
        tmp_path,
        native,
        [row("b1")],
        [row("j1", transaction_date="2026-01-09")],
        local_matches=[],
    )

    assert [p["stage"] for p in native.calls] == ["luna"] * 3 + ["sol"] * 3
    assert result["errors"][0]["stage"] == "sol"
    assert result["groups"] == []
    assert result["questions"]["bank"] == []


def test_escalation_preserves_later_first_stage_work_and_replay(tmp_path):
    bank = [row(f"b{i:02}") for i in range(30)]
    native = NativeFixture({})
    native.respond = lambda packet, **_: (
        bad_answer(packet)
        if packet["stage"] == "luna" and "b00" in packet["focus"][0]["bank_ids"]
        else answer(packet)
    )

    result = execute(tmp_path, native, bank, local_matches=[])

    assert [p["stage"] for p in native.calls] == ["luna"] * 4 + ["sol"]
    assert result["errors"] == []
    assert result["summary"]["primary_counts"]["sol"] == 25
    assert result["summary"]["primary_counts"]["luna"] == 5
    assert bf.replay_retained(result, bank, [], REL) == result["groups"]


def test_recovery_after_evidence_search_preserves_valid_search_replay(tmp_path):
    native = NativeFixture({})

    def respond(packet, **_):
        if packet["stage"] == "sol":
            return answer(packet, linked=True)
        if packet["retrieval"]["round"] == 0:
            return request(
                packet, {"side": "journal", "field": "transaction_id", "value": "j1"}
            )
        return bad_answer(packet)

    native.respond = respond
    bank, journal = [row("b1")], [row("j1", transaction_date="2026-01-09")]
    result = execute(tmp_path, native, bank, journal, local_matches=[])

    assert result["errors"] == []
    assert result["attempts"][0]["status"] == "evidence_requested"
    assert [p["stage"] for p in native.calls] == ["luna"] * 4 + ["sol"]
    assert bf.replay_retained(result, bank, journal, REL) == result["groups"]


@pytest.mark.parametrize("failure", ["receipt", "isolation", "host", "source"])
def test_boundary_failures_stop_without_retry_or_escalation(tmp_path, failure):
    native = NativeFixture({})
    original = native.invoke
    called = []

    def invoke(**kwargs):
        called.append(kwargs["worker_selection"]["cost_class"])
        if failure == "host":
            raise RuntimeError("host denied execution")
        call = original(**kwargs)
        if failure in {"receipt", "isolation"}:
            path = Path(call["launch_receipt"])
            receipt = json.loads(path.read_text())
            if failure == "receipt":
                receipt["packet_sha256"] = "changed"
            else:
                receipt["boundary"]["canaries"]["outside_capsule_read_denied"] = False
            receipt["content_sha256"] = bf.digest(
                {k: v for k, v in receipt.items() if k != "content_sha256"}
            )
            path.write_text(json.dumps(receipt))
        return call

    def source_check():
        if failure == "source" and called:
            raise ValueError("source changed during execution")

    native.invoke = invoke
    result = execute(tmp_path, native, source_check=source_check, local_matches=[])

    assert called == ["low"]
    assert result["attempts"][0]["status"] == "technical_error"
    assert result["errors"]
    assert result["groups"] == []


def test_verified_response_format_failures_escalate_then_resume(tmp_path):
    import semantic_review as semantic

    native = NativeFixture({})
    original = native.invoke
    calls = []

    def invoke(**kwargs):
        stage = kwargs["worker_selection"]["cost_class"]
        calls.append(stage)
        if stage == "low":
            raise semantic.WorkerResponseFormatError(
                "Worker emitted multiple completed messages",
                usage={"input_tokens": 1, "output_tokens": 1},
            )
        return original(**kwargs)

    native.invoke = invoke
    result = execute(tmp_path, native, local_matches=[])

    assert calls == ["low"] * 3 + ["escalation"]
    assert result["errors"] == []
    assert bf.replay_retained(result, [row("b1")], [], REL) == result["groups"]
    calls.clear()
    assert execute(tmp_path, native, local_matches=[])["groups"] == result["groups"]
    assert calls == []


@pytest.mark.parametrize("version", [1, 2])
def test_historical_local_evidence_projection_replays_unchanged(
    tmp_path, monkeypatch, version
):
    import retrieval_review as rr

    bank, journal = [row("b1", reference="PAY123")], [row("j1", reference="PAY123")]
    pair = {"bank_transaction_id": "b1", "journal_transaction_id": "j1"}
    original = rr.bf.admission

    def legacy(*args, **kwargs):
        return original(*args, **{**kwargs, "local_evidence_version": version})

    with monkeypatch.context() as old:
        old.setattr(rr.bf, "admission", legacy)
        old.setattr(rr, "_implementation_digest", lambda: rr.REPLAY_IMPLEMENTATIONS[0])
        retained = execute(
            tmp_path, NativeFixture({}), bank, journal, local_matches=[pair]
        )
    # The released 0.1.653 result/state predate the version field.
    retained["local_evidence_version"] = version
    if version == 1:
        retained.pop("local_evidence_version")
    retained["content_sha256"] = bf.digest(
        {k: v for k, v in retained.items() if k != "content_sha256"}
    )
    state = bf._read(tmp_path / "bank_first_state.json")
    state["local_evidence_version"] = version
    if version == 1:
        state.pop("local_evidence_version")
    bf._save(tmp_path / "bank_first_state.json", state)
    native = NativeFixture({})

    resumed = execute(
        tmp_path, native, bank, journal, local_matches=[pair], resume_checkpoint=True
    )

    assert bf.replay_retained(retained, bank, journal, REL) == retained["groups"]
    assert resumed["groups"] == retained["groups"]
    assert native.calls == []


def test_stronger_host_denial_resumes_only_the_pending_stronger_stage(tmp_path):
    native = NativeFixture({})
    original = native.invoke

    def deny_sol(**kwargs):
        if kwargs["worker_selection"]["cost_class"] == "escalation":
            raise RuntimeError("host temporarily unavailable")
        return original(**kwargs)

    native.invoke = deny_sol
    native.respond = bad_answer
    first = execute(tmp_path, native, local_matches=[])
    assert first["errors"][0]["stage"] == "sol"
    native.calls.clear()
    native.invoke = original
    native.respond = answer

    resumed = execute(tmp_path, native, local_matches=[])

    assert [p["stage"] for p in native.calls] == ["sol"]
    assert resumed["errors"] == []
    assert bf.replay_retained(resumed, [row("b1")], [], REL) == resumed["groups"]


@pytest.mark.parametrize("change", [{"format_attempt": 1}, {"bank_ids": ["outside"]}])
def test_recovery_marker_cannot_change_the_failed_focus_or_retry_bound(
    tmp_path, change
):
    native = NativeFixture({})
    native.respond = lambda packet, **_: (
        bad_answer(packet) if packet["stage"] == "luna" else answer(packet)
    )
    result = execute(tmp_path, native, local_matches=[])
    retained = copy.deepcopy(result)
    transition = next(
        e
        for e in retained["retained_native_evidence"]
        if e["attempt"]["status"] == "escalated_response"
    )
    transition["attempt"].update(change)
    retained["content_sha256"] = bf.digest(
        {k: v for k, v in retained.items() if k != "content_sha256"}
    )

    with pytest.raises(ValueError, match="Invalid stronger-stage recovery transition"):
        bf.replay_retained(retained, [row("b1")], [], REL)

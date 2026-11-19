"""Native-receipted action sequences exercise the pilot's control decisions."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
import bank_first as bf
import reconciliation_orchestrator as orch

REL = dict(
    relationship_shape="many_to_many",
    default_currency="EUR",
    default_unit="money",
    default_entity_ref="fixture",
    direction_policy="same_sign",
)
BANK = [
    dict(
        transaction_id="b",
        amount_signed="-34.12",
        transaction_date="2026-07-01",
        description="Card ACME shop",
    )
]
JOURNAL = [
    dict(
        transaction_id="j",
        amount_signed="-34.12",
        transaction_date="2026-07-02",
        description="Purchase ACME",
    )
]


@pytest.fixture(autouse=True)
def imports(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))


def action(packet, kind, **extra):
    return dict(
        packet_sha256=packet["packet_sha256"],
        action=kind,
        bank_ids=[],
        journal_ids=[],
        routine="",
        window_days=7,
        expression="",
        query=None,
        groups=[],
        rationale="Inspect useful evidence",
        working_note="",
        **extra,
    )


def decision(packet, *, status="resolved"):
    evidence = [
        dict(
            side=side,
            transaction_id=r["transaction_id"],
            field="description",
            quote=r["description"],
        )
        for side in ("bank", "journal")
        for r in packet[side + "_records"]
    ]
    resolution = dict(
        status=status,
        scope="bank cash link",
        explanation="Compatible amount, posting delay and merchant descriptions support the link without a reference code.",
        evidence=evidence,
        questions=[] if status == "resolved" else ["Confirm the merchant receipt."],
    )
    return dict(
        bank_ids=["b"],
        journal_ids=["j"],
        bank_resolution=resolution,
        accounting_resolution=dict(
            status="complete",
            scope="cash only",
            explanation="No assertion about expense treatment.",
            evidence=evidence,
            questions=[],
        ),
        allocations=[],
        proposed_account_codes=[],
        account_codes_are_alternatives=False,
        change_basis="additional_analysis_of_supplied_evidence",
    )


class Worker:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def select(self, **kw):
        return dict(
            model="fixture",
            reasoning_effort="high",
            cost_class="standard" if kw["stage"] == "luna" else "escalation",
        )

    def invoke(self, **kw):
        packet = json.loads((kw["output_dir"] / "packet.json").read_text())
        self.calls.append(packet)
        response = next(self.responses)(packet)
        serial = lambda x: (
            json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode()
        receipt = dict(
            workflow_id=kw["workflow_id"],
            packet_sha256=kw["packet_sha256"],
            packet=dict(
                prompt_sha256=hashlib.sha256(kw["prompt"].encode()).hexdigest(),
                output_schema_sha256=hashlib.sha256(
                    serial(kw["output_schema"])
                ).hexdigest(),
            ),
            requested_worker_configuration=dict(
                **kw["worker_selection"], direct_model_api=False, ephemeral=True
            ),
            process=dict(
                return_code=0,
                response_sha256=hashlib.sha256(serial(response)).hexdigest(),
            ),
            boundary=dict(
                canaries=dict(
                    exact_schema_read_succeeded=True,
                    outside_capsule_read_denied=True,
                    required_cli_capabilities_available=True,
                )
            ),
        )
        receipt["content_sha256"] = bf.digest(receipt)
        path = kw["output_dir"] / "receipt.json"
        path.write_text(json.dumps(receipt))
        return dict(
            response_payload=response,
            launch_receipt=path,
            usage=dict(input_tokens=10, output_tokens=5),
            duration_ms=1,
        )


def run(path, worker, **kw):
    return orch.run_orchestrator(
        BANK,
        JOURNAL,
        path,
        source_binding={"workflow": "journal-bank-reconciliation", "hash": "synthetic"},
        relationship=REL,
        local_matches=[],
        invoke=worker.invoke,
        select=worker.select,
        **kw,
    )


def search(packet):
    a = action(packet, "run")
    a["routine"] = "date_window"
    return a


def decide(packet):
    a = action(packet, "decide")
    a["groups"] = [decision(packet)]
    return a


def test_model_selects_tool_then_semantic_link_without_codes_and_replays(tmp_path):
    worker = Worker([search, decide])
    result = run(tmp_path, worker)
    assert len(worker.calls) == 2
    assert result["groups"][0]["journal_ids"] == ["j"]
    assert result["summary"]["review_complete"] is True
    assert orch.replay_result(result, BANK, JOURNAL, REL) == result["groups"]
    assert run(tmp_path, worker) == result
    assert len(worker.calls) == 2


def test_budget_returns_partial_and_explicit_resume_preserves_tool_work(tmp_path):
    worker = Worker([search, decide])
    partial = run(tmp_path, worker, limits={"calls": 1})
    assert partial["stop_reason"] == "budget_exhausted"
    assert partial["summary"]["review_complete"] is False
    assert run(tmp_path, worker, limits={"calls": 1}) == partial
    resumed = run(tmp_path, worker, resume_checkpoint=True)
    assert len(worker.calls) == 2
    assert resumed["groups"][0]["journal_ids"] == ["j"]


def test_tentative_link_does_not_reserve_ledger(tmp_path):
    def tentative(p):
        a = action(p, "decide")
        a["groups"] = [decision(p, status="doubtful")]
        return a

    worker = Worker([search, tentative, lambda p: action(p, "finish")])
    result = run(tmp_path, worker)
    assert result["groups"][0]["journal_ids"] == []
    assert result["groups"][0]["candidate_journal_ids"] == ["j"]
    assert result["summary"]["primary_counts"]["human"] == 1


def test_changed_source_is_not_resumed(tmp_path):
    worker = Worker([search])
    run(tmp_path, worker, limits={"calls": 1})
    with pytest.raises(ValueError, match="different sources"):
        orch.run_orchestrator(
            BANK,
            [],
            tmp_path,
            source_binding={
                "workflow": "journal-bank-reconciliation",
                "hash": "synthetic",
            },
            relationship=REL,
            local_matches=[],
            invoke=worker.invoke,
            select=worker.select,
        )


def test_failed_worker_retains_partial_result(tmp_path):
    worker = Worker([])

    def fail(**kw):
        raise OSError("worker unavailable")

    worker.invoke = fail
    result = run(tmp_path, worker)
    assert result["stop_reason"] == "technical_error"
    assert (tmp_path / "orchestrator_result.json").is_file()
    assert orch.replay_result(result, BANK, JOURNAL, REL) == []


def test_generated_rule_then_model_judgment(tmp_path):
    def generated(p):
        a = action(p, "generate")
        a["expression"] = (
            "[{'bank_ids':[b['transaction_id']], 'journal_ids':[j['transaction_id']]} for b in bank for j in journal if b['cents']==j['cents']]"
        )
        return a

    worker = Worker([generated, decide])
    result = run(tmp_path, worker)
    assert result["groups"][0]["journal_ids"] == ["j"]
    assert result["attempts"][0]["result"]["accepted_matches"] == 0


def test_model_discovery_failure_still_produces_partial(tmp_path):
    worker = Worker([])

    def unavailable(**kw):
        raise RuntimeError("Model discovery unavailable")

    worker.select = unavailable
    result = run(tmp_path, worker)
    assert result["stop_reason"] == "technical_error"
    assert result["groups"] == []
    assert (tmp_path / "orchestrator_result.json").is_file()


def test_nonzero_supported_link_is_not_silently_accepted(tmp_path):
    worker = Worker([search, decide])
    wrong = [{**JOURNAL[0], "amount_signed": "-35.12"}]

    # Inspect the candidate explicitly; equal-amount search cannot find it.
    def inspect(p):
        a = action(p, "inspect")
        a["journal_ids"] = ["j"]
        return a

    worker = Worker([inspect, decide])
    result = orch.run_orchestrator(
        BANK,
        wrong,
        tmp_path,
        source_binding={"workflow": "journal-bank-reconciliation", "hash": "mismatch"},
        relationship=REL,
        local_matches=[],
        invoke=worker.invoke,
        select=worker.select,
        limits={"calls": 2},
    )
    assert result["groups"] == []
    assert result["attempts"][-1]["status"] == "rejected"
    assert "Nonzero difference" in result["attempts"][-1]["error"]


def test_changed_checkpoint_is_rejected(tmp_path):
    worker = Worker([search])
    run(tmp_path, worker, limits={"calls": 1})
    path = tmp_path / "orchestrator_state.json"
    state = json.loads(path.read_text())
    state["elapsed_seconds"] = 0
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="checkpoint changed"):
        run(tmp_path, worker, resume_checkpoint=True)


def test_partial_decision_must_not_reuse_a_reserved_journal_row(tmp_path):
    extra_bank = [
        *BANK,
        {**BANK[0], "transaction_id": "other-bank", "transaction_date": "2026-07-03"},
    ]

    def first(p):
        a = action(p, "decide")
        a["groups"] = [decision(p)]
        return a

    def second(p):
        a = action(p, "inspect")
        a["journal_ids"] = ["j"]
        return a

    worker = Worker([search, first, second])
    result = orch.run_orchestrator(
        extra_bank,
        JOURNAL,
        tmp_path,
        source_binding={"workflow": "journal-bank-reconciliation", "hash": "duplicate"},
        relationship=REL,
        local_matches=[],
        invoke=worker.invoke,
        select=worker.select,
        limits={"calls": 3},
    )
    assert len(result["groups"]) == 1
    assert result["groups"][0]["journal_ids"] == ["j"]
    assert result["attempts"][-1]["status"] == "rejected"
    assert "already reserved" in result["attempts"][-1]["error"]


def test_semantic_net_settlement_can_link_receipts_less_fee(tmp_path):
    bank = [
        {
            **BANK[0],
            "amount_signed": "97.50",
            "description": "Processor weekly net settlement",
        }
    ]
    journal = [
        {
            **JOURNAL[0],
            "transaction_id": "gross",
            "amount_signed": "100",
            "description": "Processor gross receipts",
        },
        {
            **JOURNAL[0],
            "transaction_id": "fee",
            "amount_signed": "-2.50",
            "description": "Processor settlement fee",
        },
    ]

    def find(p):
        a = action(p, "run")
        a["routine"] = "subset_sum"
        return a

    def resolve(p):
        a = action(p, "decide")
        g = decision(p)
        g["journal_ids"] = ["gross", "fee"]
        g["bank_resolution"][
            "explanation"
        ] = "The processor net settlement equals gross receipts less the documented fee."
        a["groups"] = [g]
        return a

    worker = Worker([find, resolve])
    result = orch.run_orchestrator(
        bank,
        journal,
        tmp_path,
        source_binding={"workflow": "journal-bank-reconciliation", "hash": "net"},
        relationship=REL,
        local_matches=[],
        invoke=worker.invoke,
        select=worker.select,
    )
    assert result["groups"][0]["difference"] == "0.00"
    assert result["groups"][0]["journal_ids"] == ["gross", "fee"]
    assert orch.replay_result(result, bank, journal, REL) == result["groups"]


def test_explained_bank_name_without_ledger_link_is_not_a_match(tmp_path):
    def explain(p):
        a = action(p, "decide")
        g = decision(p)
        g["journal_ids"] = []
        a["groups"] = [g]
        return a

    worker = Worker([search, explain])
    result = run(tmp_path, worker, limits={"calls": 2})
    assert result["groups"] == []
    assert "not a ledger match" in result["attempts"][-1]["error"]


def test_model_can_search_evidence_then_decide_without_running_all_routines(tmp_path):
    def inspect(p):
        from evidence_retrieval import query_schema

        a = action(p, "inspect")
        a["query"] = {k: None for k in query_schema()["properties"]}
        a["query"].update(side="journal", text="ACME")
        return a

    worker = Worker([inspect, decide])
    result = run(tmp_path, worker)
    assert result["groups"][0]["journal_ids"] == ["j"]
    assert result["attempts"][0]["result"]["total_candidates"] == 1
    assert orch.replay_result(result, BANK, JOURNAL, REL) == result["groups"]


def test_pending_native_host_returns_partial_and_reuses_same_packet(tmp_path):
    from native_host_worker import NativeWorkerPending

    class PendingWorker(Worker):
        pending = True
        packet_hash = None

        def invoke(self, **kw):
            if self.pending:
                self.pending = False
                self.packet_hash = kw["packet_sha256"]
                raise NativeWorkerPending("Dispatch retained host request")
            assert kw["packet_sha256"] == self.packet_hash
            return super().invoke(**kw)

    worker = PendingWorker([lambda p: action(p, "finish")])
    first = run(tmp_path, worker)
    assert first["stop_reason"] == "awaiting_native_host"
    assert first["summary"]["review_complete"] is False
    second = run(tmp_path, worker)
    assert second["stop_reason"] == "finished"
    assert len(second["attempts"]) == 1


def test_changed_native_diagnostics_reject_reopen_without_new_calls(tmp_path):
    worker = Worker([search, decide])
    run(tmp_path, worker)
    (tmp_path / "orchestrator-attempts/00001/receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="attempt evidence changed"):
        run(tmp_path, worker)
    assert len(worker.calls) == 2


def test_symlink_attempt_directory_rejected_before_writes_or_dispatch(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "run"
    output.mkdir()
    (output / "orchestrator-attempts").symlink_to(outside, target_is_directory=True)
    worker = Worker([search])
    with pytest.raises(ValueError, match="symbolic links"):
        run(output, worker)
    assert list(outside.iterdir()) == []
    assert worker.calls == []


def test_rejected_format_cost_is_retained_in_partial_result(tmp_path):
    import semantic_review as semantic

    class FailedWorker(Worker):
        def invoke(self, **kw):
            path = kw["output_dir"] / "luna_process_receipt.json"
            path.write_text(
                json.dumps(
                    dict(
                        jsonl_observation=dict(
                            usage=dict(input_tokens=19, output_tokens=8)
                        ),
                        process=dict(duration_ms=27),
                    )
                )
            )
            error = semantic.WorkerResponseFormatError(
                "Ambiguous answer", usage=dict(input_tokens=19, output_tokens=8)
            )
            error.process_receipt = path
            raise error

    result = run(tmp_path, FailedWorker([]))
    assert result["stop_reason"] == "technical_error"
    assert result["attempts"][0]["usage"]["input_tokens"] == 19
    assert result["attempts"][0]["duration_ms"] == 27
    assert result["groups"] == []


def test_small_context_budget_delivers_partial_without_model_call(tmp_path):
    worker = Worker([])
    result = run(tmp_path, worker, limits={"context_bytes": 100})
    assert result["stop_reason"] == "context_limit"
    assert worker.calls == []


def test_public_run_all_logs_pilot_attempts_and_delivers_without_key_error(
    tmp_path, monkeypatch
):
    import semantic_review as semantic

    worker = Worker([search, decide])
    canonical = run(tmp_path / "controller", worker)
    logs = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "semantic_review.py",
            "run-all",
            str(tmp_path / "reconciliation"),
            "--output-dir",
            str(tmp_path / "controller"),
            "--client-engagement",
            str(tmp_path / "context.json"),
            "--review-strategy",
            "orchestrator",
        ],
    )
    monkeypatch.setattr(semantic, "_load_cli_client_engagement", lambda args: {})

    def completed(*args, **kwargs):
        assert kwargs["review_strategy"] == "orchestrator"
        return dict(
            batch_count=1,
            batches=canonical["attempts"],
            reviewed_bank_count=1,
            human_review_count=0,
            exhaustive=True,
            workbook=tmp_path / "result.xlsx",
            model_tokens=None,
        )

    monkeypatch.setattr(semantic, "run_semantic_resolution_pipeline", completed)
    monkeypatch.setattr(
        semantic, "log_execution_status", lambda *args: logs.append(args)
    )
    assert semantic.main() == 0
    assert any("orchestrator-attempts" in str(line) for line in logs)
    assert any("final reconciliation workbook" in str(line) for line in logs)

"""Synthetic contract tests; no real client population or native model runs."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
sys.path.insert(0, str(SCRIPTS))
import bank_first as bf


@pytest.fixture(autouse=True)
def source_imports(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))


REL = {
    "relationship_shape": "many_to_many",
    "require_same_currency": True,
    "require_same_unit": True,
    "require_same_entity": True,
    "default_currency": "EUR",
    "default_unit": "money",
    "default_entity_ref": "fixture",
}


def row(identifier, description="Prelievo ATM", amount="-80.00", **extra):
    return {
        "transaction_id": identifier,
        "transaction_date": "2026-01-08",
        "amount_signed": amount,
        "description": description,
        **extra,
    }


def answer(packet, *, resolved=True, complete=True, linked=False):
    groups = []
    prior = {i: g for g in packet["prior_conclusions"] for i in g["bank_ids"]}
    for entry in packet["focus"]:
        ids = entry["bank_ids"]
        source = next(
            r for r in packet["bank_records"] if r["transaction_id"] == ids[0]
        )
        citations = [
            {
                "side": "bank",
                "transaction_id": i,
                "field": "description",
                "quote": next(
                    r["description"]
                    for r in packet["bank_records"]
                    if r["transaction_id"] == i
                ),
            }
            for i in ids
        ]
        journal_ids = (
            list(prior[ids[0]]["journal_ids"])
            if entry["question_scope"] == "accounting"
            else ([packet["journal_records"][0]["transaction_id"]] if linked else [])
        )
        citations += [
            {
                "side": "journal",
                "transaction_id": i,
                "field": "description",
                "quote": next(
                    r["description"]
                    for r in packet["journal_records"]
                    if r["transaction_id"] == i
                ),
            }
            for i in journal_ids
        ]
        resolution = lambda status, scope: {
            "status": status,
            "scope": scope,
            "explanation": "Causale esaminata nel perimetro dichiarato.",
            "evidence": citations,
            "questions": (
                []
                if status in {"resolved", "complete", "carry_forward"}
                else [
                    "Quale titolo o destinatario specifico giustifica questo movimento?"
                ]
            ),
        }
        groups.append(
            {
                "bank_ids": ids,
                "journal_ids": journal_ids,
                "bank_resolution": resolution(
                    (
                        "carry_forward"
                        if entry["question_scope"] == "accounting"
                        else "resolved" if resolved else "doubtful"
                    ),
                    "bank_cash_only",
                ),
                "accounting_resolution": resolution(
                    "complete" if complete else "partial", "account_level_only"
                ),
                "allocations": [],
                "proposed_account_codes": [],
                "account_codes_are_alternatives": True,
                "change_basis": (
                    "scope_clarification" if packet["stage"] == "sol" else "unresolved"
                ),
            }
        )
    return {"packet_sha256": packet["packet_sha256"], "groups": groups}


class NativeFixture:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []
        self.respond = answer

    def select(self, *, workflow_id, stage):
        return {
            "model": "fixture-luna" if stage == "luna" else "fixture-sol",
            "reasoning_effort": "high",
            "cost_class": "low" if stage == "luna" else "escalation",
        }

    def invoke(self, **kwargs):
        directory = kwargs["output_dir"]
        packet = json.loads((directory / "packet.json").read_text(encoding="utf-8"))
        self.calls.append(packet)
        response = self.respond(packet, **self.outcomes.get(packet["stage"], {}))
        from bank_first import _translate, reference_map

        response = _translate(
            response,
            {
                side: {identifier: ref for ref, identifier in mapping.items()}
                for side, mapping in reference_map(packet).items()
            },
        )
        serialized = lambda value: (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode()
        receipt = {
            "schema_version": "vera.luna_launch_receipt.v1",
            "workflow_id": kwargs["workflow_id"],
            "packet_sha256": kwargs["packet_sha256"],
            "packet": {
                "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode()).hexdigest(),
                "output_schema_sha256": hashlib.sha256(
                    serialized(kwargs["output_schema"])
                ).hexdigest(),
            },
            "requested_worker_configuration": {
                **kwargs["worker_selection"],
                "direct_model_api": False,
                "ephemeral": True,
            },
            "process": {
                "return_code": 0,
                "response_sha256": hashlib.sha256(serialized(response)).hexdigest(),
            },
            "boundary": {
                "canaries": {
                    key: True
                    for key in (
                        "exact_schema_read_succeeded",
                        "outside_capsule_read_denied",
                        "required_cli_capabilities_available",
                    )
                }
            },
            "runtime_attestation": {
                "model_self_reported_by_pinned_cli": kwargs["worker_selection"]["model"]
            },
        }
        receipt["content_sha256"] = bf.digest(receipt)
        path = directory / "luna_launch_receipt.json"
        path.write_bytes(serialized(receipt))
        (directory / "luna_response.json").write_bytes(serialized(response))
        return {
            "launch_receipt": path,
            "response_payload": response,
            "usage": None,
            "duration_ms": 1,
        }


def run(tmp_path, native, bank=None, journal=None):
    return bf.run_bank_first(
        bank or [row("cash-1")],
        journal or [],
        tmp_path,
        source_binding={"fixture": "synthetic"},
        relationship=REL,
        invoke=native.invoke,
        select=native.select,
    )


def test_amount_date_is_candidate_not_reserved():
    result = bf.admission([row("b")], [row("j")], REL)
    assert not result["sure"]
    assert result["unresolved_bank_ids"] == ["b"]
    assert result["unreserved_journal_ids"] == ["j"]
    assert (
        result["probable_candidates"][0]["rule_id"] == "amount_date_candidate_only.v1"
    )


def test_explicit_unique_identity_is_strong_and_decimal_sources_work():
    result = bf.admission(
        [row("b", amount=Decimal("-80"), reference="F-1", party_ref="party-1")],
        [row("j", reference="F-1", party_ref="party-1")],
        REL,
    )
    assert len(result["sure"]) == 1
    assert result["sure"][0]["evidence_sha256"]


@pytest.mark.parametrize(
    "change",
    [
        {"party_ref": "other"},
        {"currency": "USD"},
        {"amount_signed": "-79.99"},
        {"transaction_date": "2025-01-08"},
    ],
)
def test_conflicting_identity_scope_amount_or_date_is_not_sure(change):
    bank = row("b", reference="F-1", party_ref="p")
    journal = row("j", reference="F-1", party_ref="p")
    journal.update(change)
    assert not bf.admission([bank], [journal], REL)["sure"]


def test_duplicate_sources_are_not_sure():
    b = row("b", reference="F-1", party_ref="p")
    assert not bf.admission(
        [b, {**b, "transaction_id": "b2"}],
        [row("j", amount="-160", reference="F-1", party_ref="p")],
        REL,
    )["sure"]


def test_resolved_luna_does_not_call_sol_and_resume_does_not_call_models(tmp_path):
    native = NativeFixture({})
    result = run(tmp_path, native)
    assert [p["stage"] for p in native.calls] == ["luna"]
    assert result["summary"]["primary_counts"]["luna"] == 1
    assert result["questions"] == {"bank": [], "accounting": []}
    assert run(tmp_path, native) == result
    assert len(native.calls) == 1


def test_all_luna_doubts_reach_sol_including_missing_documents(tmp_path):
    native = NativeFixture(
        {
            "luna": {"resolved": False, "complete": False},
            "sol": {"resolved": False, "complete": False},
        }
    )
    result = run(tmp_path, native)
    assert [p["stage"] for p in native.calls] == ["luna", "sol"]
    assert result["summary"]["primary_counts"]["human"] == 1
    assert result["groups"][0]["resolved_at"] is None
    assert (
        len(result["questions"]["bank"]) == len(result["questions"]["accounting"]) == 1
    )
    assert sum(result["summary"]["primary_counts"].values()) == 1


def test_accounting_doubt_does_not_reopen_luna_bank_fact(tmp_path):
    native = NativeFixture({"luna": {"complete": False}, "sol": {"complete": False}})
    result = run(tmp_path, native)
    assert native.calls[1]["focus"][0]["question_scope"] == "accounting"
    assert result["summary"]["primary_counts"]["luna"] == 1
    assert result["summary"]["primary_counts"]["human"] == 0
    assert not result["questions"]["bank"]
    assert result["questions"]["accounting"]
    assert result["summary"]["secondary_open_count"] == 1


def test_atm_scope_clarification_can_resolve_primary_without_cash_destination(tmp_path):
    native = NativeFixture(
        {
            "luna": {"resolved": False, "complete": False},
            "sol": {"resolved": True, "complete": False},
        }
    )
    result = run(tmp_path, native)
    assert result["summary"]["primary_counts"]["sol"] == 1
    assert result["groups"][0]["change_basis"] == "scope_clarification"
    assert result["groups"][0]["invoice_closure"] is False


def test_doubtful_candidates_do_not_reserve_journal(tmp_path):
    native = NativeFixture(
        {
            "luna": {"resolved": False, "complete": False, "linked": True},
            "sol": {"resolved": False, "complete": False, "linked": True},
        }
    )
    result = run(tmp_path, native, journal=[row("j")])
    assert result["groups"][0]["journal_ids"] == []
    assert result["groups"][0]["candidate_journal_ids"] == ["j"]
    assert native.calls[1]["reserved_journal_owners"] == {}


def test_host_failure_is_error_not_human_document_question(tmp_path):
    native = NativeFixture({})

    def fail(**kwargs):
        raise RuntimeError("Native host unavailable")

    native.invoke = fail
    result = run(tmp_path, native)
    assert result["summary"]["primary_counts"]["error"] == 1
    assert result["summary"]["primary_counts"]["human"] == 0
    assert not result["summary"]["review_complete"]
    assert not result["questions"]["bank"]


def test_changed_source_cannot_resume(tmp_path):
    native = NativeFixture({})
    run(tmp_path, native)
    with pytest.raises(ValueError, match="different source"):
        run(tmp_path, native, bank=[row("cash-1", amount="-81.00")])


def test_saved_human_files_are_byte_preserved(tmp_path):
    for name in ("posting_decisions.json", "ui_decisions.json", "private-draft.json"):
        (tmp_path / name).write_bytes(b' {"saved":"human"} \n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    run(tmp_path, NativeFixture({}))
    assert all((tmp_path / name).read_bytes() == data for name, data in before.items())


def test_native_parent_handoff_resumes_the_same_attempt(tmp_path):
    from native_host_worker import NativeWorkerPending

    native = NativeFixture({})
    directories = []

    def pending(**kwargs):
        directories.append(kwargs["output_dir"])
        raise NativeWorkerPending("Dispatch native child and resume")

    original = native.invoke
    native.invoke = pending
    with pytest.raises(NativeWorkerPending):
        run(tmp_path, native)
    state = json.loads((tmp_path / "bank_first_state.json").read_text())
    assert state["attempts"][0]["status"] == "awaiting_native_host"
    assert not state["errors"]
    native.invoke = original
    result = run(tmp_path, native)
    assert len(result["attempts"]) == 1
    assert directories[0].name == result["attempts"][0]["directory"]
    assert result["summary"]["primary_counts"]["luna"] == 1


def test_attempt_directory_link_is_rejected_before_model_or_writes(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "review"
    output.mkdir()
    (output / "bank-first-attempts").symlink_to(outside, target_is_directory=True)
    native = NativeFixture({})
    with pytest.raises(ValueError, match="symbolic links"):
        run(output, native)
    assert not native.calls
    assert list(outside.iterdir()) == []


def test_resume_uses_validated_receipts_after_completion_marker_interruption(tmp_path):
    native = NativeFixture(
        {
            "luna": {"resolved": False, "complete": False},
            "sol": {"resolved": False, "complete": False},
        }
    )
    result = run(tmp_path, native)
    path = tmp_path / "bank_first_state.json"
    state = json.loads(path.read_text())
    state["stage_completed"] = {"luna": [], "sol": []}
    state["content_sha256"] = bf.digest(
        {k: v for k, v in state.items() if k != "content_sha256"}
    )
    path.write_text(json.dumps(state))
    calls = len(native.calls)
    assert run(tmp_path, native) == result
    assert len(native.calls) == calls


@pytest.mark.parametrize("stage", ["luna", "sol"])
@pytest.mark.parametrize("direction", ["absolute_amount", "opposite_sign"])
def test_semantic_links_respect_reviewed_direction_policy(stage, direction):
    bank = [row("b", amount="-80")]
    journal = [row("j", amount="80")]
    relationship = {**REL, "direction_policy": direction}
    packet = bf.build_packet(
        bank,
        journal,
        [{"bank_ids": ["b"], "question_scope": "bank"}],
        stage=stage,
        source_binding={},
        relationship=relationship,
        admission_result=bf.admission(bank, journal, relationship),
        previous=[],
        purpose="bank_open_items",
        reserved={},
    )
    response = answer(packet, linked=True)
    groups = bf.validate_response(packet, response)
    assert groups[0]["bank_resolution"]["status"] == "resolved"
    assert groups[0]["difference"] == "-160.00"  # Preserve the signed source totals.
    packet["relationship_policy"]["direction_policy"] = "same_sign"
    packet["packet_sha256"] = bf.digest(
        {k: v for k, v in packet.items() if k != "packet_sha256"}
    )
    response["packet_sha256"] = packet["packet_sha256"]
    with pytest.raises(ValueError, match="signed direction"):
        bf.validate_response(packet, response)


@pytest.mark.parametrize("stage", ["luna", "sol"])
def test_semantic_links_cannot_override_required_party_identity(stage):
    bank = [row("b", party_ref="party-a")]
    journal = [row("j", party_ref="party-b")]
    relationship = {**REL, "require_same_party": True}
    packet = bf.build_packet(
        bank,
        journal,
        [{"bank_ids": ["b"], "question_scope": "bank"}],
        stage=stage,
        source_binding={},
        relationship=relationship,
        admission_result=bf.admission(bank, journal, relationship),
        previous=[],
        purpose="bank_open_items",
        reserved={},
    )
    with pytest.raises(ValueError, match="party perimeter"):
        bf.validate_response(packet, answer(packet, linked=True))


def test_exact_admission_cannot_bypass_reviewed_opposite_direction():
    bank = [row("b", reference="F-1", party_ref="p")]
    journal = [row("j", reference="F-1", party_ref="p")]
    admitted = bf.admission(bank, journal, {**REL, "direction_policy": "opposite_sign"})
    assert admitted["sure"] == []
    assert admitted["unresolved_bank_ids"] == ["b"]


def test_secondary_analysis_retains_established_partial_allocation():
    bank = [row("b", amount="-80")]
    journal = [row("j", amount="-100")]
    relationship = {**REL, "open_item_allocation_authorized": True}
    admitted = bf.admission(bank, journal, relationship)
    packet = bf.build_packet(
        bank,
        journal,
        [{"bank_ids": ["b"], "question_scope": "bank"}],
        stage="luna",
        source_binding={},
        relationship=relationship,
        admission_result=admitted,
        previous=[],
        purpose="bank_open_items",
        reserved={},
    )
    response = answer(packet, linked=True, complete=False)
    response["groups"][0]["allocations"] = [
        {"source_id": "b", "target_id": "j", "amount": "40"}
    ]
    prior = bf.validate_response(packet, response)
    sol = bf.build_packet(
        bank,
        journal,
        [{"bank_ids": ["b"], "question_scope": "accounting"}],
        stage="sol",
        source_binding={},
        relationship=relationship,
        admission_result=admitted,
        previous=prior,
        purpose="bank_open_items",
        reserved={"j": "b"},
    )
    reply = answer(sol, complete=False)
    with pytest.raises(ValueError, match="established partial allocation"):
        bf.validate_response(sol, reply)
    reply["groups"][0]["allocations"] = [
        {"source_id": "b", "target_id": "j", "amount": "40"}
    ]
    assert bf.validate_response(sol, reply)[0]["resolved_at"] == "luna"


def test_saved_native_result_is_utf8_and_replays_accented_source_text(tmp_path):
    native = NativeFixture({})
    bank = [row("cash-1", description="Prova sintetica: società Città – €")]
    result = run(tmp_path, native, bank=bank)
    restored = json.loads((tmp_path / "bank_first_result.json").read_bytes())
    assert (
        restored["groups"][0]["bank_resolution"]["evidence"][0]["quote"]
        == bank[0]["description"]
    )
    assert run(tmp_path, native, bank=bank) == result
    assert len(native.calls) == 1


def test_short_references_roundtrip_and_retained_map_tampering(tmp_path):
    native = NativeFixture({"luna": {"linked": True}})
    result = run(
        tmp_path,
        native,
        bank=[row("bank:source:99")],
        journal=[row("journal:PDF_page_2:39")],
    )
    directory = tmp_path / "bank-first-attempts/00001-luna"
    wire = json.loads((directory / "worker_packet.json").read_text())
    response = json.loads((directory / "response.json").read_text())
    assert wire["bank_records"][0]["transaction_id"] == "B001"
    assert wire["journal_records"][0]["transaction_id"] == "J001"
    assert response["groups"][0]["journal_ids"] == ["J001"]
    assert result["groups"][0]["journal_ids"] == ["journal:PDF_page_2:39"]
    assert wire["journal_records"][0]["description"] == "Prelievo ATM"
    (directory / "row_reference_map.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        run(
            tmp_path,
            native,
            bank=[row("bank:source:99")],
            journal=[row("journal:PDF_page_2:39")],
        )


@pytest.mark.parametrize("bad", ["J999", "B001", "journal:PDF_page_3:39"])
def test_unknown_cross_side_and_full_source_ids_rejected(tmp_path, bad):
    import jsonschema

    native = NativeFixture({"luna": {"linked": True}})
    run(
        tmp_path,
        native,
        bank=[row("bank:source:99")],
        journal=[row("journal:PDF_page_2:39")],
    )
    directory = tmp_path / "bank-first-attempts/00001-luna"
    packet = json.loads((directory / "packet.json").read_text())
    response = json.loads((directory / "response.json").read_text())
    response["groups"][0]["journal_ids"] = [bad]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(response, bf.output_schema(packet))
    with pytest.raises(ValueError, match="Unknown journal row reference"):
        bf.validate_worker_response(packet, response)


def test_short_ids_do_not_weaken_exact_citation_check(tmp_path):
    native = NativeFixture({})
    run(tmp_path, native)
    directory = tmp_path / "bank-first-attempts/00001-luna"
    packet = json.loads((directory / "packet.json").read_text())
    response = json.loads((directory / "response.json").read_text())
    response["groups"][0]["bank_resolution"]["evidence"][0]["quote"] = "absent"
    with pytest.raises(ValueError):
        bf.validate_worker_response(packet, response)


def test_focus_projection_bounds_history_without_dropping_sources_or_ownership(
    tmp_path,
):
    run(tmp_path, NativeFixture({}))
    packet = json.loads(
        (tmp_path / "bank-first-attempts/00001-luna/packet.json").read_text()
    )
    first = answer(packet)["groups"][0]
    packet["bank_records"] = [row(f"b{i}") for i in range(200)]
    packet["focus"] = [{"bank_ids": ["b199"], "kind": "accounting"}]
    packet["eligible_bank_ids"] = ["b199"]
    packet["prior_conclusions"] = []
    for i in range(200):
        group = copy.deepcopy(first)
        group["bank_ids"] = [f"b{i}"]
        group["bank_resolution"]["evidence"][0]["transaction_id"] = f"b{i}"
        group["history"] = [{"explanation": "retained audit history " * 1000}]
        packet["prior_conclusions"].append(group)
    before = copy.deepcopy(packet)
    wire = bf.worker_packet(packet)
    assert packet == before
    assert len(wire["bank_records"]) == 200
    assert len(wire["prior_conclusion_index"]) == 200
    assert len(wire["prior_conclusions"]) == 1
    assert wire["prior_conclusions"][0]["bank_ids"] == ["B200"]
    assert "history" not in wire["prior_conclusions"][0]
    assert len(bf.prompt(packet).encode()) < 262144
    assert all(
        a["description"] == b["description"]
        for a, b in zip(packet["bank_records"], wire["bank_records"])
    )


def test_run_all_cli_reports_bank_first_attempts_without_legacy_fields(
    monkeypatch, tmp_path, caplog
):
    """Successful exports must not crash, or label a rejected attempt validated."""
    import semantic_review as semantic

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "semantic_review",
            "run-all",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "semantic-review"),
            "--client-engagement",
            str(tmp_path / "context.json"),
        ],
    )
    monkeypatch.setattr(semantic, "_load_cli_client_engagement", lambda args: {})
    monkeypatch.setattr(semantic, "_load_cli_worker_selection", lambda args: None)
    monkeypatch.setattr(
        semantic,
        "run_semantic_resolution_pipeline",
        lambda *a, **kw: {
            "batch_count": 1,
            "reviewed_bank_count": 1,
            "human_review_count": 0,
            "exhaustive": True,
            "batches": [
                {"directory": "00001-sol", "status": "rejected_format"},
                {"directory": "00002-sol", "status": "validated"},
            ],
            "workbook": tmp_path / "final.xlsx",
            "model_tokens": {},
        },
    )
    messages = []
    monkeypatch.setattr(
        semantic,
        "log_execution_status",
        lambda out, message, *args: messages.append(message % args),
    )
    assert semantic.main() == 0
    assert any('"status": "rejected_format"' in message for message in messages)
    assert any("final reconciliation workbook" in message for message in messages)

"""The final review must preserve grouped evidence and deliver the client workbook."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import polars as pl
import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "plugins/journal-bank-reconciliation/scripts"
)
SPEC = importlib.util.spec_from_file_location(
    "grouped_review_cases", SCRIPTS / "grouped_review.py"
)
assert SPEC and SPEC.loader
grouped = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grouped)
POLICY = {
    "relationship_shape": "many_to_many",
    "default_currency": "EUR",
    "default_unit": "currency",
    "default_entity_ref": "case",
    "require_same_currency": True,
    "require_same_unit": True,
    "require_same_entity": True,
    "direction_policy": "same_sign",
    "amount_tolerance": "0",
    "date_window_days": 0,
}


def row(
    identifier: str,
    amount: str,
    description: str = "Pagamento Alfa",
    day: str = "2026-10-01",
) -> dict:
    return {
        "transaction_id": identifier,
        "amount_signed": amount,
        "description": description,
        "transaction_date": day,
        "source_file": "source.csv",
        "source_sheet": "CSV",
        "source_row": "2",
    }


def decision(
    bank_ids: list[str],
    journal_ids: list[str],
    status: str = "concordant",
    name: str = "Alfa",
) -> dict:
    return {
        "bank_ids": bank_ids,
        "journal_ids": journal_ids,
        "status": status,
        "title": name,
        "rationale": "Movimento e contropartite esaminati insieme.",
        "required_documents": [],
        "evidence": (
            [
                {
                    "side": side,
                    "transaction_id": identifier,
                    "field": "description",
                    "quote": name,
                }
                for side, identifiers in (("bank", bank_ids), ("journal", journal_ids))
                for identifier in identifiers
            ]
            if bank_ids and journal_ids
            else []
        ),
    }


def packet(bank: list[dict], journal: list[dict]) -> dict:
    return grouped.build_grouped_packet(
        bank, journal, source_binding={"hash": "current"}, policy=POLICY
    )


def test_grouped_packet_preserves_split_postings_and_shifted_dates_without_exact_edge_filter() -> (
    None
):
    original = packet(
        [row("b", "-159.31")],
        [row("principal", "-158.60", day="2026-10-02"), row("fee", "-0.71")],
    )

    result = grouped.validate_grouped_response(
        original,
        {
            "packet_sha256": original["packet_sha256"],
            "groups": [decision(["b"], ["principal", "fee"])],
        },
    )

    assert len(original["journal_records"]) == 2
    assert result[0]["difference"] == "0.00"


def test_grouped_packet_retains_all_43_counterparts_while_focusing_25_bank_rows() -> (
    None
):
    original = packet(
        [row(f"b{i}", "-100") for i in range(40)],
        [row(f"j{i}", "-0.71") for i in range(43)],
    )

    assert len(original["focus_ids"]) == 25
    assert len(original["bank_records"]) == 40
    assert len(original["journal_records"]) == 43


def test_grouped_review_accepts_salary_total_without_reusing_single_journal_as_multiple_matches() -> (
    None
):
    original = packet(
        [row("b1", "-60", "Stipendi"), row("b2", "-40", "Stipendi")],
        [row("j", "-100", "Stipendi")],
    )

    result = grouped.validate_grouped_response(
        original,
        {
            "packet_sha256": original["packet_sha256"],
            "groups": [decision(["b1", "b2"], ["j"], name="Stipendi")],
        },
    )

    assert result[0]["bank_sum"] == "-100"
    assert result[0]["journal_ids"] == ["j"]


def test_grouped_review_rejects_same_amount_link_without_source_purpose_evidence() -> (
    None
):
    original = packet([row("b", "-100")], [row("j", "-100")])
    unsupported = decision(["b"], ["j"])
    unsupported["evidence"] = []

    with pytest.raises(ValueError, match="non-monetary evidence"):
        grouped.validate_grouped_response(
            original,
            {"packet_sha256": original["packet_sha256"], "groups": [unsupported]},
        )


@pytest.mark.parametrize(
    "change,error",
    [
        ("wrong_sum", "conserve exact"),
        ("invented_quote", "not present"),
        ("omitted_bank", "omitted"),
        ("reuse", "reused"),
        ("currency", "currency perimeter"),
    ],
)
def test_grouped_review_rejects_incomplete_or_unsupported_relationships(
    change: str, error: str
) -> None:
    bank = [row("b1", "-100"), row("b2", "-100")]
    journal = [row("j1", "-100"), row("j2", "-100")]
    if change == "currency":
        bank[0]["currency"] = "CHF"
    original = packet(bank, journal)
    groups = [decision(["b1"], ["j1"]), decision(["b2"], ["j2"])]
    if change == "wrong_sum":
        original = packet(bank, [row("j1", "-99.99"), journal[1]])
    elif change == "invented_quote":
        groups[0]["evidence"][0]["quote"] = "not in source"
    elif change == "omitted_bank":
        groups.pop()
    elif change == "reuse":
        groups[1] = decision(["b2"], ["j1"])

    with pytest.raises(ValueError, match=error):
        grouped.validate_grouped_response(
            original, {"packet_sha256": original["packet_sha256"], "groups": groups}
        )


def _write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    bank: list[dict] | None = None,
    journal: list[dict] | None = None,
    reject_first: bool = False,
    denied: bool = False,
    protocol_first: bool = False,
) -> tuple[Path, Path, list[dict]]:
    reconciliation = tmp_path / "reconciliation"
    output = tmp_path / "semantic-review"
    reconciliation.mkdir()
    output.mkdir()
    bank = (
        bank
        if bank is not None
        else [row("b1", "-159.31"), row("b2", "-100", "Pagamento Beta")]
    )
    journal = (
        journal
        if journal is not None
        else [
            row("j1", "-158.60"),
            row("j2", "-0.71", "Oneri"),
            row("j3", "-100", "Pagamento Beta"),
        ]
    )
    _write_csv(reconciliation / "normalized_bank.csv", bank, fields=list(row("b", "1")))
    _write_csv(
        reconciliation / "normalized_journal.csv", journal, fields=list(row("j", "1"))
    )
    _write_csv(
        reconciliation / "reconciliation_matches.csv",
        [],
        fields=["bank_transaction_id", "journal_transaction_id"],
    )
    (reconciliation / "run_intake.json").write_text("{}")
    calls = []
    rejection_sent = [False]

    class FormatError(ValueError):
        pass

    def worker(**kwargs):
        if denied:
            raise OSError("host denied execution")
        directory = kwargs["output_dir"]
        p = json.loads((directory / "packet.json").read_text())
        assert kwargs["source_records"] == [
            {"record_id": record["transaction_id"], "fields": list(record)}
            for record in [*p["bank_records"], *p["journal_records"]]
        ]
        calls.append(p)
        if protocol_first and len(calls) == 1:
            events = b"rejected multi-message turn"
            stderr = b"worker banner"
            (directory / "luna_process_events.jsonl").write_bytes(events)
            (directory / "luna_process_stderr.log").write_bytes(stderr)
            content = {
                "packet_sha256": p["packet_sha256"],
                "process": {
                    "duration_ms": 50,
                    "events_sha256": hashlib.sha256(events).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                },
                "jsonl_observation": {"usage": {"input_tokens": 7, "output_tokens": 3}},
            }
            path = directory / "luna_process_receipt.json"
            path.write_text(
                json.dumps({**content, "content_sha256": grouped._digest(content)})
            )
            exc = FormatError("Worker emitted multiple completed messages")
            exc.process_receipt = path
            raise exc
        # Simulated worker follows the read-only protocol for missing evidence.
        # Broad search is intentional in this tiny exporter fixture.
        if p.get("retrieval") and p["retrieval"]["not_in_context"]["journal"]:
            from bank_first import reference_map

            pages = p["retrieval"]["pages"]
            last = pages[-1] if pages else {}
            query = {"side": "journal"}
            if last.get("query", {}) == {"side": "journal"} or last.get(
                "query", {}
            ).get("cursor"):
                query["cursor"] = last.get("next_cursor")
            response = {
                "packet_sha256": p["packet_sha256"],
                "groups": [],
                "evidence_requests": [query],
                "retain": {side: list(refs) for side, refs in reference_map(p).items()},
                "working_note": "Retrieve remaining fixture evidence before deciding.",
            }
            return finish(response, kwargs, p, directory)
        if {r["transaction_id"] for r in p["journal_records"]} == {"j1", "j2", "j3"}:
            groups = [
                decision(["b1"], ["j1", "j2"]),
                decision(["b2"], ["j3"], name="Beta"),
            ]
        elif p["journal_records"]:
            groups = [
                decision(
                    [entry["bank_ids"][0]],
                    [
                        next(
                            (
                                record["transaction_id"]
                                for record in p["journal_records"]
                                if record.get("reference")
                                and record.get("reference")
                                == next(
                                    row.get("reference")
                                    for row in p["bank_records"]
                                    if row["transaction_id"] == entry["bank_ids"][0]
                                )
                            ),
                            p["journal_records"][index]["transaction_id"],
                        )
                    ],
                )
                for index, entry in enumerate(p["focus"])
            ]
        else:
            groups = [
                decision([i], [], status="unmatched")
                for entry in p["focus"]
                for i in entry["bank_ids"]
            ]
        for item in groups:
            for citation in item["evidence"]:
                record = next(
                    r
                    for r in p[citation["side"] + "_records"]
                    if r["transaction_id"] == citation["transaction_id"]
                )
                citation["quote"] = record["description"]
        if p["focus"] and all(
            entry["question_scope"] == "accounting" for entry in p["focus"]
        ):
            groups = [
                decision(previous["bank_ids"], previous["journal_ids"])
                for previous in p["prior_conclusions"]
                if any(
                    set(previous["bank_ids"]) == set(entry["bank_ids"])
                    for entry in p["focus"]
                )
            ]
            for item in groups:
                for citation in item["evidence"]:
                    citation["quote"] = next(
                        r["description"]
                        for r in p[citation["side"] + "_records"]
                        if r["transaction_id"] == citation["transaction_id"]
                    )
        # The normal producer now has separate bank/accounting conclusions.
        typed = []
        for item in groups:
            citations = item["evidence"] or [
                {
                    "side": "bank",
                    "transaction_id": i,
                    "field": "description",
                    "quote": next(
                        r["description"]
                        for r in p["bank_records"]
                        if r["transaction_id"] == i
                    ),
                }
                for i in item["bank_ids"]
            ]
            resolution = lambda status, scope: {
                "status": status,
                "scope": scope,
                "explanation": item["rationale"],
                "evidence": citations,
                "questions": [],
            }
            typed.append(
                {
                    "bank_ids": item["bank_ids"],
                    "journal_ids": item["journal_ids"],
                    "bank_resolution": resolution(
                        (
                            "carry_forward"
                            if all(
                                entry["question_scope"] == "accounting"
                                for entry in p["focus"]
                            )
                            else "resolved"
                        ),
                        "bank_cash",
                    ),
                    "accounting_resolution": resolution("complete", "account_level"),
                    "proposed_account_codes": [],
                    "account_codes_are_alternatives": True,
                    "allocations": [],
                    "change_basis": "additional_analysis_of_supplied_evidence",
                }
            )
        groups = typed
        if reject_first and not rejection_sent[0]:
            rejection_sent[0] = True
            groups[0]["bank_resolution"]["evidence"][0]["quote"] = "invented evidence"
        response = {"packet_sha256": p["packet_sha256"], "groups": groups}
        return finish(response, kwargs, p, directory)

    def finish(response, kwargs, p, directory):
        from bank_first import _translate, reference_map

        response = _translate(
            response,
            {
                side: {identifier: ref for ref, identifier in mapping.items()}
                for side, mapping in reference_map(p).items()
            },
        )
        response_bytes = (
            json.dumps(response, indent=2, ensure_ascii=False) + "\n"
        ).encode()
        response_path = directory / "luna_response.json"
        response_path.write_bytes(response_bytes)
        receipt_content = {
            "schema_version": "vera.luna_launch_receipt.v1",
            "workflow_id": kwargs["workflow_id"],
            "packet_sha256": p["packet_sha256"],
            "packet": {
                "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode()).hexdigest(),
                "output_schema_sha256": hashlib.sha256(
                    (
                        json.dumps(
                            kwargs["output_schema"], ensure_ascii=False, indent=2
                        )
                        + "\n"
                    ).encode()
                ).hexdigest(),
            },
            "requested_worker_configuration": {
                **kwargs["worker_selection"],
                "direct_model_api": False,
                "ephemeral": True,
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
            "process": {
                "return_code": 0,
                "duration_ms": 100,
                "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            },
            "jsonl_observation": {"usage": {"input_tokens": 10, "output_tokens": 4}},
        }
        digest = hashlib.sha256(
            json.dumps(
                receipt_content,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        receipt = {**receipt_content, "content_sha256": digest}
        receipt_path = directory / "luna_launch_receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        return {
            "launch_receipt": receipt_path,
            "response_payload": response,
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "duration_ms": 100,
        }

    monkeypatch.setitem(
        sys.modules,
        "semantic_review",
        SimpleNamespace(
            _resolved_reconciliation_dir=lambda p: p,
            _semantic_output_dir=lambda r, p: p,
            _validated_source_replay=lambda *args, **kwargs: {
                "source_binding": {"hash": "current"},
                "bank": pl.DataFrame(bank),
                "journal": pl.DataFrame(journal),
                "relationship_policy": POLICY,
                "audit": {"matched_count": 0},
            },
            _artifact_roots_from_intake=lambda *args, **kwargs: {},
            discover_worker_selection=lambda **kwargs: {
                "host": "codex",
                "model": (
                    "fixture-luna" if kwargs.get("stage") == "luna" else "fixture-sol"
                ),
                "reasoning_effort": "high",
                "cost_class": "low" if kwargs.get("stage") == "luna" else "escalation",
            },
            run_isolated_native_worker=worker,
            WorkerResponseFormatError=FormatError,
            PROCESS_RECEIPT_NAME="luna_process_receipt.json",
            PROCESS_EVENTS_NAME="luna_process_events.jsonl",
            PROCESS_STDERR_NAME="luna_process_stderr.log",
            MAX_PROMPT_BYTES=256 * 1024,
        ),
    )
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return reconciliation, output, calls


def test_complete_review_retains_rejected_call_tokens_then_exports_same_four_sheet_final_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(
        tmp_path, monkeypatch, reject_first=True
    )
    baseline = (reconciliation / "normalized_bank.csv").read_bytes()

    result = grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 3
    assert result["model_tokens"] == {
        "input_tokens": 30,
        "output_tokens": 12,
        "total_tokens": 42,
    }
    assert [a["status"] for a in result["batches"]] == [
        "evidence_requested",
        "rejected_format",
        "validated",
    ]
    assert (output / "bank-first-attempts/00001-luna/luna_response.json").exists()
    assert result["summary"]["concordant_bank_count"] == 2
    assert (reconciliation / "normalized_bank.csv").read_bytes() == baseline
    book = openpyxl.load_workbook(result["workbook"], data_only=True)
    assert book.sheetnames == ["Sintesi", "Relazioni", "Banca", "Partitario"]
    assert book["Relazioni"]["D6"].value == -159.31
    assert book["Relazioni"]["E6"].value == -159.31
    assert book["Relazioni"]["F6"].value == 0
    assert book["Relazioni"]["B6"].value == "B001"
    assert book["Relazioni"]["C6"].value == "C001\nC002"
    assert book["Banca"]["A6"].value == "B001"
    assert book["Partitario"]["A6"].value == "C001"
    assert book["Sintesi"]["B16"].value == 2
    assert book["Banca"].max_row == 7
    assert book["Partitario"].max_row == 8


def test_final_workbook_preserves_strict_split_reference_group_without_reusing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(
        tmp_path, monkeypatch, bank=[], journal=[]
    )
    _write_csv(
        reconciliation / "normalized_bank.csv",
        [{**row("b", "-100"), "reference": "settlement-1", "party_ref": "party-1"}],
    )
    _write_csv(
        reconciliation / "normalized_journal.csv",
        [
            {**row("j1", "-99"), "reference": "settlement-1", "party_ref": "party-1"},
            {**row("j2", "-1"), "reference": "settlement-1", "party_ref": "party-1"},
        ],
    )
    _write_csv(
        reconciliation / "reconciliation_matches.csv",
        [
            {"bank_transaction_id": "b", "journal_transaction_id": "j1"},
            {"bank_transaction_id": "b", "journal_transaction_id": "j2"},
        ],
    )

    result = grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 1
    assert calls[0]["focus"][0]["question_scope"] == "accounting"
    assert result["summary"]["strict_match_count"] == 1
    retained = json.loads(result["result"].read_text())
    assert len(retained["relations"]) == 1
    assert retained["relations"][0]["journal_ids"] == ["j1", "j2"]
    assert retained["relations"][0]["difference"] == "0"
    assert result["model_tokens"]["total_tokens"] == 14


def test_complete_review_batches_35_rows_without_dropping_context_or_reusing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(
        tmp_path, monkeypatch, bank=[row(f"b{i}", "-1") for i in range(35)], journal=[]
    )

    result = grouped.complete_grouped_review(reconciliation, output)

    assert [
        len([i for entry in p["focus"] for i in entry["bank_ids"]]) for p in calls
    ] == [25, 10]
    assert len(calls[0]["bank_records"]) == 25
    assert calls[0]["retrieval"]["not_in_context"]["bank"] == 10
    assert not {i for entry in calls[0]["focus"] for i in entry["bank_ids"]} & {
        i for entry in calls[1]["focus"] for i in entry["bank_ids"]
    }
    assert result["exhaustive"] is True
    assert result["summary"]["bank_status_counts"] == {"bank_explained": 35}


def test_final_workbook_keeps_source_references_and_counterparties_for_equal_amounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, _ = _environment(tmp_path, monkeypatch, bank=[], journal=[])
    _write_csv(
        reconciliation / "normalized_bank.csv",
        [
            {
                **row("b1", "-610"),
                "reference": "OUT-005",
                "beneficiary": "Fornitore Olmo",
            },
            {
                **row("b2", "-610"),
                "reference": "OUT-006",
                "beneficiary": "Fornitore Pino",
            },
        ],
    )
    _write_csv(
        reconciliation / "normalized_journal.csv",
        [
            {**row("j2", "-610"), "reference": "OUT-006", "beneficiary": "Pino Srl"},
            {**row("j1", "-610"), "reference": "OUT-005", "beneficiary": "Olmo Srl"},
        ],
    )
    _write_csv(
        reconciliation / "reconciliation_matches.csv",
        [
            {"bank_transaction_id": "b1", "journal_transaction_id": "j1"},
            {"bank_transaction_id": "b2", "journal_transaction_id": "j2"},
        ],
    )

    result = grouped.complete_grouped_review(reconciliation, output)

    book = openpyxl.load_workbook(result["workbook"], data_only=True)
    assert list(
        book["Banca"].iter_rows(
            min_row=5, max_row=7, min_col=4, max_col=5, values_only=True
        )
    ) == [
        ("Riferimento originale", "Controparte"),
        ("OUT-005", "Fornitore Olmo"),
        ("OUT-006", "Fornitore Pino"),
    ]
    assert list(
        book["Partitario"].iter_rows(
            min_row=6, max_row=7, min_col=4, max_col=5, values_only=True
        )
    ) == [
        ("OUT-006", "Pino Srl"),
        ("OUT-005", "Olmo Srl"),
    ]
    assert book["Relazioni"]["B6"].value == "B001 · OUT-005\nFornitore Olmo"
    assert book["Relazioni"]["C6"].value == "C002 · OUT-005\nOlmo Srl"
    assert book["Relazioni"]["B7"].value == "B002 · OUT-006\nFornitore Pino"
    assert book["Relazioni"]["C7"].value == "C001 · OUT-006\nPino Srl"
    assert book["Relazioni"]["D6"].value == -610
    assert book["Relazioni"]["E6"].value == -610
    assert book["Sintesi"]["B8"].value == -1220
    assert book["Sintesi"]["D8"].value == 0
    assert book["Sintesi"]["B16"].value == 2
    formulas = openpyxl.load_workbook(result["workbook"], data_only=False)
    assert (
        formulas["Relazioni"]["D6"].value
        == "=SUMIF(Banca!$B$6:$B$7,A6,Banca!$G$6:$G$7)"
    )
    assert formulas["Sintesi"]["B16"].value == '=COUNTIF(Banca!$H$6:$H$7,"Concorde")'


def test_complete_review_resumes_from_validated_decisions_without_another_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(tmp_path, monkeypatch)
    first = grouped.complete_grouped_review(reconciliation, output)
    original_bytes = first["result"].read_bytes()

    second = grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 2
    assert second["summary"] == first["summary"]
    assert second["model_tokens"] == first["model_tokens"]
    assert second["result"].read_bytes() == original_bytes


def test_complete_review_does_not_deliver_intermediate_workbook_after_host_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(tmp_path, monkeypatch, denied=True)

    with pytest.raises(ValueError, match="host denied"):
        grouped.complete_grouped_review(reconciliation, output)

    assert calls == []
    assert not (output / "Riconciliazione_banca_partitario.xlsx").exists()


def test_native_packet_byte_overflow_retains_indivisible_focus_without_a_false_final_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(tmp_path, monkeypatch)
    monkeypatch.setattr(sys.modules["semantic_review"], "MAX_PROMPT_BYTES", 1)

    with pytest.raises(ValueError, match="Working context"):
        grouped.complete_grouped_review(reconciliation, output)

    retained = json.loads(
        (output / "bank-first-attempts/00001-luna/packet.json").read_text()
    )
    assert retained["focus"] == [{"bank_ids": ["b1"], "question_scope": "bank"}]
    assert len(retained["bank_records"]) == 1
    assert retained["journal_records"] == []
    assert retained["retrieval"]["not_in_context"] == {"bank": 1, "journal": 3}
    assert calls == []
    assert not (output / "Riconciliazione_banca_partitario.xlsx").exists()
    assert (
        json.loads((output / "grouped_review_status.json").read_text())["status"]
        == "incomplete"
    )


def test_normal_api_and_run_all_cli_use_the_same_final_review_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        load_semantic_review,
    )

    semantic = load_semantic_review()
    calls = []
    result = {
        "batch_count": 0,
        "batches": [],
        "reviewed_bank_count": 0,
        "human_review_count": 0,
        "exhaustive": True,
        "workbook": tmp_path / "final.xlsx",
        "model_tokens": None,
    }

    def complete(*args, **kwargs):
        calls.append((args, kwargs))
        return dict(result)

    monkeypatch.setitem(
        sys.modules, "grouped_review", SimpleNamespace(complete_grouped_review=complete)
    )
    monkeypatch.setattr(semantic, "_load_cli_client_engagement", lambda _: {})
    monkeypatch.setattr(semantic, "log_execution_status", lambda *args: None)
    direct = semantic.run_semantic_resolution_pipeline(tmp_path, tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "semantic_review.py",
            "run-all",
            str(tmp_path),
            "--output-dir",
            str(tmp_path),
            "--client-engagement",
            str(tmp_path / "context.json"),
        ],
    )

    cli_status = semantic.main()

    assert direct["workbook"] == result["workbook"]
    assert cli_status == 0
    assert len(calls) == 2


def _bank_preparation_case(tmp_path: Path) -> tuple[object, dict, dict]:
    spec = importlib.util.spec_from_file_location(
        "bank_working_case", SCRIPTS / "bank_working_copy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Account heading", None, None])
    sheet.append(["Date", "Description", "EUR"])
    sheet.append(["01/10/2026", "Supplier Alfa", -159.31])
    sheet.append([None, None, -159.31])
    book.save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    decisions = {
        "reviewer_ref": "agent.test",
        "reviewed_on": "2026-11-06",
        "files": [
            {
                "source_path": str(source),
                "source_sha256": digest,
                "sheet": 0,
                "date_column": 0,
                "description_column": 1,
                "amount_column": 2,
                "date_convention": "day_first",
                "excluded_rows": [1, 2, 4],
            }
        ],
    }
    context = {"input_bindings": [{"path": str(source), "sha256": digest}]}
    return module, decisions, context


def test_reviewed_bank_preparation_preserves_excluded_cells_and_is_replayable(
    tmp_path: Path,
) -> None:
    module, decisions, context = _bank_preparation_case(tmp_path)
    first = module.prepare_reviewed_bank_copies(
        decisions, tmp_path / "out", context=context
    )

    second = module.prepare_reviewed_bank_copies(
        decisions, tmp_path / "out", context=context
    )

    assert first["movement_count"] == second["movement_count"] == 1
    evidence = json.loads(first["evidence"].read_text())
    assert evidence[0]["row_links"] == [{"csv_row": 2, "source_excel_row": 3}]
    assert evidence[0]["excluded_rows"][-1] == {
        "excel_row": 4,
        "cells": [None, None, "-159.31"],
    }
    assert evidence[0]["net_amount"] == "-159.31"


def test_bank_preparation_never_silently_drops_unreviewed_undated_amounts(
    tmp_path: Path,
) -> None:
    module, decisions, context = _bank_preparation_case(tmp_path)
    decisions["files"][0]["excluded_rows"] = [1, 2]

    with pytest.raises(ValueError, match="parseable date"):
        module.prepare_reviewed_bank_copies(
            decisions, tmp_path / "out", context=context
        )

    assert not list((tmp_path / "out/bank-prepared").glob("*.csv"))


def test_grouped_source_evidence_keeps_next_page_counterparty_without_the_next_posting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.plugins.test_journal_bank_reconciliation_plugin import _write_pdf_table

    monkeypatch.syspath_prepend(str(SCRIPTS))
    source = tmp_path / "ledger.pdf"
    header = ["Data reg.", "N.Reg.", "Descrizione", "D A R E", "A V E R E"]
    _write_pdf_table(
        source,
        [
            [header, ["01/10/26", "1", "PAG FATTURA", "", "159,31"]],
            [
                header,
                ["", "", "FORNITORE ALFA", "", ""],
                ["02/10/26", "2", "ALTRO PAGAMENTO", "", "20,00"],
            ],
        ],
    )
    record = {
        **row("j1", "-159.31"),
        "source_file": "ledger.pdf",
        "source_sheet": "PDF page 1 table 1",
        "source_row": "2",
    }

    evidence = grouped.extract_grouped_source_evidence(
        [record], {"source_journal": tmp_path}
    )

    assert "FORNITORE ALFA" in evidence["j1"]
    assert "ALTRO PAGAMENTO" not in evidence["j1"]


def test_source_change_after_a_returned_call_stops_without_retry_and_keeps_its_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(tmp_path, monkeypatch)
    semantic = sys.modules["semantic_review"]
    original = semantic._validated_source_replay
    replay_count = 0

    def replay(*args, **kwargs):
        nonlocal replay_count
        replay_count += 1
        result = original(*args, **kwargs)
        if replay_count > 2:
            result["source_binding"] = {"hash": "changed"}
        return result

    monkeypatch.setattr(semantic, "_validated_source_replay", replay)

    with pytest.raises(ValueError, match="Source bindings changed"):
        grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 1
    state = json.loads((output / "bank_first_state.json").read_text())
    assert state["attempts"][0]["usage"] == {"input_tokens": 10, "output_tokens": 4}
    assert state["attempts"][0]["status"] == "technical_error"
    assert state["groups"] == []
    assert not (output / "Riconciliazione_banca_partitario.xlsx").exists()


def test_resume_preserves_user_changed_final_workbook_instead_of_overwriting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(tmp_path, monkeypatch)
    first = grouped.complete_grouped_review(reconciliation, output)
    first["workbook"].write_bytes(b"user changed workbook")

    with pytest.raises(ValueError, match="Existing final workbook changed"):
        grouped.complete_grouped_review(reconciliation, output)

    assert first["workbook"].read_bytes() == b"user changed workbook"
    assert len(calls) == 2


def test_grouped_review_retries_tool_free_protocol_rejection_retains_cost_and_replays_without_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(
        tmp_path, monkeypatch, protocol_first=True
    )

    result = grouped.complete_grouped_review(reconciliation, output)
    replayed = grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 3
    assert [a["status"] for a in result["batches"]] == [
        "rejected_format",
        "evidence_requested",
        "validated",
    ]
    assert result["model_tokens"] == {
        "input_tokens": 27,
        "output_tokens": 11,
        "total_tokens": 38,
    }
    assert replayed["model_tokens"] == result["model_tokens"]
    assert result["batches"][0]["duration_ms"] == 50
    assert Path(result["workbook"]).is_file()


def test_grouped_review_rejects_changed_retained_protocol_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, output, calls = _environment(
        tmp_path, monkeypatch, protocol_first=True
    )
    grouped.complete_grouped_review(reconciliation, output)
    (output / "bank-first-attempts/00001-luna/luna_process_events.jsonl").write_text(
        "changed"
    )

    with pytest.raises(ValueError, match="attempt evidence changed"):
        grouped.complete_grouped_review(reconciliation, output)

    assert len(calls) == 3

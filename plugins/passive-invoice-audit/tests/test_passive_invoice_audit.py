from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_core  # noqa: E402
import luna_worker  # noqa: E402


def _write_invoice(
    path: Path,
    *,
    number: str = "INV-1",
    supplier_vat: str = "01234567890",
    supplier_name: str = "TIM S.p.A.",
    description: str = "Servizi di telefonia mobile",
    taxable: str = "100.00",
    vat_rate: str = "22.00",
    vat: str = "22.00",
    gross: str = "122.00",
    document_type: str = "TD01",
) -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="urn:test">
 <FatturaElettronicaHeader>
  <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{supplier_vat}</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>{supplier_name}</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
  <CessionarioCommittente><DatiAnagrafici><CodiceFiscale>99999999999</CodiceFiscale><Anagrafica><Denominazione>Cliente S.r.l.</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
 </FatturaElettronicaHeader>
 <FatturaElettronicaBody>
  <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>{document_type}</TipoDocumento><Divisa>EUR</Divisa><Data>2026-01-31</Data><Numero>{number}</Numero><ImportoTotaleDocumento>{gross}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
  <DatiBeniServizi>
   <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>{description}</Descrizione><Quantita>1</Quantita><PrezzoUnitario>{taxable}</PrezzoUnitario><PrezzoTotale>{taxable}</PrezzoTotale><AliquotaIVA>{vat_rate}</AliquotaIVA></DettaglioLinee>
   <DatiRiepilogo><AliquotaIVA>{vat_rate}</AliquotaIVA><ImponibileImporto>{taxable}</ImponibileImporto><Imposta>{vat}</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
  </DatiBeniServizi>
  <DatiPagamento><CondizioniPagamento>TP02</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><DataScadenzaPagamento>2026-02-28</DataScadenzaPagamento><ImportoPagamento>{gross}</ImportoPagamento></DettaglioPagamento></DatiPagamento>
 </FatturaElettronicaBody>
</p:FatturaElettronica>""",
        encoding="utf-8",
    )


def _ledger_rows(
    *,
    movement_id: str = "M1",
    number: str = "INV-1",
    supplier_vat: str = "01234567890",
    account_code: str = "625010",
    account_description: str = "Spese telefoniche",
    gross: str = "122.00",
    taxable: str = "100.00",
    vat: str = "22.00",
    payable: str = "-122.00",
) -> list[dict[str, str]]:
    common = {
        "movement_id": movement_id,
        "entry_date": "2026-01-31",
        "document_date": "2026-01-31",
        "supplier_tax_id": supplier_vat,
        "supplier_name": "TIM S.p.A.",
        "invoice_number": number,
        "document_reference": number,
        "currency": "EUR",
        "gross_amount": gross,
        "taxable_amount": taxable,
        "vat_amount": vat,
    }
    return [
        common
        | {
            "line_number": "1",
            "account_code": account_code,
            "account_description": account_description,
            "account_type": "expense",
            "line_description": "Costo",
            "amount_signed": taxable,
        },
        common
        | {
            "line_number": "2",
            "account_code": "IVA22",
            "account_description": "IVA a credito",
            "account_type": "input_vat",
            "line_description": "IVA",
            "amount_signed": vat,
        },
        common
        | {
            "line_number": "3",
            "account_code": "FORN",
            "account_description": "Debiti fornitori",
            "account_type": "supplier_payable",
            "line_description": "Fornitore",
            "amount_signed": payable,
        },
    ]


def _write_ledger(path: Path, rows: list[dict[str, str]]) -> Path:
    headers = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_mapping(path: Path) -> Path:
    fields = list(_ledger_rows()[0])
    path.write_text(json.dumps({field: field for field in fields}), encoding="utf-8")
    return path


def _parsed_item(
    tmp_path: Path,
    *,
    invoice_kwargs: Mapping[str, str] | None = None,
    rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    invoices_dir = tmp_path / "invoices"
    invoices_dir.mkdir()
    _write_invoice(invoices_dir / "invoice.xml", **dict(invoice_kwargs or {}))
    invoices = audit_core.parse_invoice_population(invoices_dir, tmp_path / "stage")
    items, _ = audit_core.match_population(
        invoices, rows or _ledger_rows(), audit_core.CENT
    )
    return items[0]


def _semantic_payload(
    invoice_id: str, *, status: str, issue_type: str = "none", reason: str = ""
) -> dict[str, Any]:
    exception = status != "no_issue_detected"
    return {
        "schema_version": "vera.passive_invoice_luna.v1",
        "results": [
            {
                "invoice_id": invoice_id,
                "status": status,
                "short_reason": reason,
                "suspected_issue_type": issue_type,
                "invoice_evidence": ["Invoice line evidence"] if exception else [],
                "booked_account_evidence": (
                    ["Booked account evidence"] if exception else []
                ),
                "professional_should_inspect": (
                    "Inspect classification" if exception else ""
                ),
            }
        ],
    }


class FixtureRunner:
    def __init__(
        self, decisions: Mapping[str, tuple[str, str]], *, fail: bool = False
    ) -> None:
        self.decisions = decisions
        self.fail = fail
        self.calls = 0

    def __call__(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        output_dir: Path,
        workflow_id: str,
        packet_sha256: str,
        reasoning_effort: str,
    ) -> Mapping[str, Any]:
        self.calls += 1
        if self.fail:
            raise ValueError("controlled interruption")
        packets = json.loads(prompt.partition("PACKETS_JSON:\n")[2])
        results = []
        for packet in packets:
            status, issue_type = self.decisions.get(
                packet["invoice_id"], ("no_issue_detected", "none")
            )
            results.extend(
                _semantic_payload(
                    packet["invoice_id"],
                    status=status,
                    issue_type=issue_type,
                    reason="Fixture decision",
                )["results"]
            )
        return {
            "response_payload": {
                "schema_version": "vera.passive_invoice_luna.v1",
                "results": results,
            },
            "usage": {"input_tokens": 100, "output_tokens": 20},
            "duration_ms": 10,
            "model": "gpt-5.6-luna",
            "reasoning_effort": reasoning_effort,
        }


def _run_fixture_audit(
    tmp_path: Path, runner: FixtureRunner
) -> tuple[dict[str, Any], Path]:
    invoices = tmp_path / "invoices"
    invoices.mkdir(exist_ok=True)
    _write_invoice(invoices / "invoice.xml")
    ledger = _write_ledger(tmp_path / "ledger.csv", _ledger_rows())
    mapping = _write_mapping(tmp_path / "mapping.json")
    output = tmp_path / "output"
    summary = audit_core.run_audit(
        invoice_source=invoices,
        ledger_path=ledger,
        mapping_path=mapping,
        output_dir=output,
        runner=runner,
        config=audit_core.AuditConfig(chunk_size=1, concurrency=1),
    )
    return summary, output


def test_fatturapa_parsing_extracts_accounting_fields(tmp_path: Path) -> None:
    invoice_path = tmp_path / "invoice.xml"
    _write_invoice(invoice_path)

    records = audit_core.parse_invoice_population(invoice_path, tmp_path / "stage")

    assert records[0]["lines"][0]["description"] == "Servizi di telefonia mobile"
    assert records[0]["vat_summaries"][0]["vat_amount"] == "22.00"
    assert records[0]["payments"][0]["method"] == "MP05"


def test_exact_invoice_ledger_matching_records_evidence(tmp_path: Path) -> None:
    item = _parsed_item(tmp_path)

    assert item["match_state"] == "matched"
    assert {"supplier_tax_id_exact", "invoice_number_exact"} <= set(
        item["match_evidence"]
    )


def test_population_matching_uses_exact_candidate_indices() -> None:
    population_size = 200
    invoices = [
        {
            "invoice_id": f"invoice-{index}",
            "xml_valid": True,
            "supplier_vat": f"{index:011d}",
            "invoice_number": f"INV-{index}",
            "invoice_date": "2026-01-31",
            "gross_amount": "122.00",
            "currency": "EUR",
            "lines": [],
            "vat_summaries": [
                {
                    "taxable_amount": "100.00",
                    "vat_amount": "22.00",
                    "vat_rate": "22.00",
                    "vat_nature": "",
                }
            ],
        }
        for index in range(population_size)
    ]
    ledger_rows = [
        {
            "movement_id": f"movement-{index}",
            "entry_date": "2026-01-31",
            "document_date": "2026-01-31",
            "supplier_tax_id": f"{index:011d}",
            "supplier_name": f"Supplier {index}",
            "invoice_number": f"INV-{index}",
            "document_reference": f"INV-{index}",
            "account_code": "625010",
            "account_description": "Spese telefoniche",
            "account_type": "expense",
            "line_description": "Costo",
            "amount_signed": "0.00",
            "currency": "EUR",
            "gross_amount": "122.00",
            "taxable_amount": "100.00",
            "vat_amount": "22.00",
            "source_file": "ledger.csv",
        }
        for index in range(population_size)
    ]
    metrics: dict[str, float] = {}

    items, orphans = audit_core.match_population(
        invoices, ledger_rows, audit_core.CENT, metrics
    )

    assert len(items) == population_size
    assert {item["match_state"] for item in items} == {"matched"}
    assert orphans == []
    assert metrics["matching_candidate_comparisons"] == population_size


def test_ambiguous_matching_is_not_forced(tmp_path: Path) -> None:
    rows = _ledger_rows(movement_id="M1") + _ledger_rows(movement_id="M2")

    item = _parsed_item(tmp_path, rows=rows)

    assert item["match_state"] == "ambiguous_match"
    assert item["matched_movement"] is None


def test_missing_ledger_entry_is_an_exception(tmp_path: Path) -> None:
    item = _parsed_item(
        tmp_path,
        rows=_ledger_rows(number="DIFFERENT", supplier_vat="99999999999"),
    )

    assert item["match_state"] == "invoice_not_found_in_ledger"
    assert "invoice_not_found_in_ledger" in {
        finding["code"] for finding in item["deterministic_findings"]
    }


def test_duplicate_invoice_candidates_are_explicit(tmp_path: Path) -> None:
    invoices_dir = tmp_path / "invoices"
    invoices_dir.mkdir()
    _write_invoice(invoices_dir / "one.xml")
    _write_invoice(invoices_dir / "two.xml")
    invoices = audit_core.parse_invoice_population(invoices_dir, tmp_path / "stage")

    items, _ = audit_core.match_population(invoices, _ledger_rows(), audit_core.CENT)

    assert {item["match_state"] for item in items} == {"duplicate_candidate"}


def test_invoice_total_arithmetic_mismatch_is_detected(tmp_path: Path) -> None:
    item = _parsed_item(
        tmp_path,
        invoice_kwargs={"gross": "130.00"},
        rows=_ledger_rows(gross="130.00", payable="-130.00"),
    )

    assert "xml_total_arithmetic_mismatch" in {
        finding["code"] for finding in item["deterministic_findings"]
    }


def test_vat_mismatch_with_mapped_ledger_vat_is_detected(tmp_path: Path) -> None:
    item = _parsed_item(
        tmp_path, rows=_ledger_rows(vat="20.00", payable="-120.00", gross="122.00")
    )

    assert "vat_amount_mismatch" in {
        finding["code"] for finding in item["deterministic_findings"]
    }


@pytest.mark.parametrize(
    ("payable", "expected_balanced"),
    [("-122.00", True), ("-120.00", False)],
)
def test_balanced_and_unbalanced_posting(
    tmp_path: Path, payable: str, expected_balanced: bool
) -> None:
    item = _parsed_item(tmp_path, rows=_ledger_rows(payable=payable))

    assert item["matched_movement"]["balanced"] is expected_balanced


@pytest.mark.parametrize(
    ("invoice_description", "account_description", "status", "issue_type"),
    [
        (
            "Servizi di telefonia mobile",
            "Spese telefoniche",
            "no_issue_detected",
            "none",
        ),
        (
            "Servizi di telefonia mobile",
            "Cancelleria",
            "review_required",
            "economic_substance_account_mismatch",
        ),
        (
            "Adobe Creative Cloud annuale",
            "Abbonamenti software",
            "no_issue_detected",
            "none",
        ),
        (
            "Otto computer portatili",
            "Materiale di consumo",
            "review_required",
            "possible_fixed_asset",
        ),
        (
            "Amazon articoli misti",
            "Costi generali",
            "insufficient_evidence",
            "invoice_contains_multiple_economic_categories",
        ),
        ("Servizio corriere DHL", "Spese di trasporto", "no_issue_detected", "none"),
    ],
)
def test_semantic_fixture_cases_preserve_packet_evidence(
    tmp_path: Path,
    invoice_description: str,
    account_description: str,
    status: str,
    issue_type: str,
) -> None:
    item = _parsed_item(
        tmp_path,
        invoice_kwargs={"description": invoice_description},
        rows=_ledger_rows(account_description=account_description),
    )
    packet = audit_core.build_packet(item)
    payload = _semantic_payload(
        packet["invoice_id"],
        status=status,
        issue_type=issue_type,
        reason="Fixture judgment",
    )

    result = audit_core.validate_luna_result(payload, [packet["invoice_id"]])

    assert result[packet["invoice_id"]]["status"] == status
    assert invoice_description in packet["invoice_lines"][0]["description"]
    assert (
        account_description
        in packet["actual_accounting_treatment"][0]["account_description"]
    )


def test_semantic_chunking_honours_item_and_prompt_byte_limits() -> None:
    first = {
        "invoice_id": "one",
        "invoice_lines": [{"description": "A" * 2_000}],
    }
    second = {
        "invoice_id": "two",
        "invoice_lines": [{"description": "B" * 2_000}],
    }
    one_packet_bytes = len(audit_core.build_luna_prompt([first]).encode("utf-8"))

    chunks = audit_core.chunk_semantic_packets(
        [first, second], max_items=25, max_prompt_bytes=one_packet_bytes + 100
    )

    assert chunks == [[first], [second]]


@pytest.mark.parametrize(
    ("history_state", "status"),
    [
        ("supports_current", "no_issue_detected"),
        ("contradicts_current", "review_required"),
    ],
)
def test_historical_evidence_is_bounded_and_available(
    tmp_path: Path, history_state: str, status: str
) -> None:
    item = _parsed_item(tmp_path)
    history = [
        {
            "supplier_tax_id": "01234567890",
            "invoice_description": "Mobile service",
            "account_code": "625010",
            "account_description": "Spese telefoniche",
            "treatment_state": history_state,
        }
    ]

    packet = audit_core.build_packet(item, history)

    assert packet["relevant_history"][0]["treatment_state"] == history_state
    assert status in audit_core.SEMANTIC_STATUSES


def test_strict_luna_output_parser_rejects_extra_invoice(tmp_path: Path) -> None:
    item = _parsed_item(tmp_path)
    invoice_id = item["invoice"]["invoice_id"]
    payload = _semantic_payload(invoice_id, status="no_issue_detected")
    payload["results"].append(
        _semantic_payload("extra", status="no_issue_detected")["results"][0]
    )

    with pytest.raises(audit_core.AuditError, match="exactly once"):
        audit_core.validate_luna_result(payload, [invoice_id])


def test_interrupted_run_resumes_failed_chunk(tmp_path: Path) -> None:
    invoices = tmp_path / "invoices"
    invoices.mkdir()
    _write_invoice(invoices / "invoice.xml")
    ledger = _write_ledger(tmp_path / "ledger.csv", _ledger_rows())
    mapping = _write_mapping(tmp_path / "mapping.json")
    output = tmp_path / "output"
    with pytest.raises(audit_core.AuditError, match="resume"):
        audit_core.run_audit(
            invoice_source=invoices,
            ledger_path=ledger,
            mapping_path=mapping,
            output_dir=output,
            runner=FixtureRunner({}, fail=True),
            config=audit_core.AuditConfig(chunk_size=1, concurrency=1, max_retries=0),
        )
    runner = FixtureRunner({})

    summary = audit_core.run_audit(
        invoice_source=invoices,
        ledger_path=ledger,
        mapping_path=mapping,
        output_dir=output,
        runner=runner,
        config=audit_core.AuditConfig(chunk_size=1, concurrency=1, max_retries=0),
    )

    assert summary["luna_chunks_completed"] == 1
    assert runner.calls == 1


def test_idempotent_rerun_does_not_repeat_luna_or_duplicate_results(
    tmp_path: Path,
) -> None:
    runner = FixtureRunner({})
    _, output = _run_fixture_audit(tmp_path, runner)

    summary, _ = _run_fixture_audit(tmp_path, runner)

    assert runner.calls == 1
    assert summary["population"] == 1
    assert (
        len((output / "full_population.jsonl").read_text(encoding="utf-8").splitlines())
        == 1
    )


def test_rerun_rejects_changed_semantic_context(tmp_path: Path) -> None:
    invoices = tmp_path / "invoices"
    invoices.mkdir()
    _write_invoice(invoices / "invoice.xml")
    ledger = _write_ledger(tmp_path / "ledger.csv", _ledger_rows())
    mapping = _write_mapping(tmp_path / "mapping.json")
    output = tmp_path / "output"
    runner = FixtureRunner({})
    audit_core.run_audit(
        invoice_source=invoices,
        ledger_path=ledger,
        mapping_path=mapping,
        output_dir=output,
        runner=runner,
        chart_of_accounts={"625010": "Telefonia"},
    )

    with pytest.raises(audit_core.AuditError, match="different inputs or controls"):
        audit_core.run_audit(
            invoice_source=invoices,
            ledger_path=ledger,
            mapping_path=mapping,
            output_dir=output,
            runner=runner,
            chart_of_accounts={"625010": "Cancelleria"},
        )


def test_synthetic_error_mode_keeps_original_and_labels_copy(tmp_path: Path) -> None:
    _, output = _run_fixture_audit(tmp_path, FixtureRunner({}))
    row = json.loads((output / "full_population.jsonl").read_text(encoding="utf-8"))
    plan = tmp_path / "mutations.json"
    plan.write_text(
        json.dumps(
            [
                {
                    "invoice_id": row["invoice"]["invoice_id"],
                    "replacement_account_code": "CANC",
                    "replacement_account_description": "Cancelleria",
                    "label": "telecom_to_stationery",
                }
            ]
        ),
        encoding="utf-8",
    )
    synthetic_path = output / "synthetic" / "packets.jsonl"

    generated = audit_core.create_synthetic_population(
        output / "full_population.jsonl", plan, synthetic_path
    )

    assert generated[0]["synthetic"] is True
    assert generated[0]["packet"]["invoice_id"].startswith("synthetic:")
    assert (
        generated[0]["original_treatment"]
        != generated[0]["packet"]["actual_accounting_treatment"]
    )

    synthetic_id = generated[0]["packet"]["invoice_id"]
    report = audit_core.evaluate_synthetic_population(
        output / "full_population.jsonl",
        plan,
        output / "synthetic-evaluation",
        FixtureRunner(
            {
                synthetic_id: (
                    "review_required",
                    "economic_substance_account_mismatch",
                )
            }
        ),
        audit_core.AuditConfig(chunk_size=1, concurrency=1),
    )

    assert report["exception_recall"] == 1.0
    assert report["missed_material_issues"] == []


def test_evaluation_reports_recall_false_positive_review_rate_and_misses(
    tmp_path: Path,
) -> None:
    _, output = _run_fixture_audit(tmp_path, FixtureRunner({}))
    row = json.loads((output / "full_population.jsonl").read_text(encoding="utf-8"))
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        json.dumps(
            {
                "invoice_id": row["invoice"]["invoice_id"],
                "label": "problematic",
                "known_issue": "fixture issue",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = audit_core.evaluate_results(output / "full_population.jsonl", labels)

    assert report["exception_recall"] == 0.0
    assert report["missed_material_issues"][0]["known_issue"] == "fixture issue"
    assert "false_positive_rate" in report
    assert "human_review_rate" in report


def test_scripts_contain_no_direct_model_api_or_api_key_contract() -> None:
    script_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SCRIPTS.glob("*.py"))
    )

    assert "OPENAI_API_KEY" not in script_text
    assert "from openai" not in script_text
    assert "import openai" not in script_text
    assert "api.openai.com" not in script_text


def test_native_worker_fails_closed_if_shared_capsule_reports_wrong_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class WrongModelCapsule:
        @staticmethod
        def run_isolated_luna_worker(**kwargs: Any) -> dict[str, Any]:
            return {"model": "gpt-5.6-terra", "reasoning_effort": "low"}

    monkeypatch.setattr(
        luna_worker, "_load_shared_capsule", lambda: WrongModelCapsule()
    )

    with pytest.raises(ValueError, match="gpt-5.6-luna"):
        luna_worker.run_luna_chunk("prompt", {}, tmp_path, "workflow", "0" * 64, "low")


def test_shared_capsule_is_pinned_to_intended_luna_model() -> None:
    source = (
        PLUGIN_ROOT.parent
        / "journal-bank-reconciliation"
        / "scripts"
        / "semantic_review.py"
    ).read_text(encoding="utf-8")

    assert 'model = "gpt-5.6-luna"' in source
    assert "run_isolated_luna_worker" in source


def test_real_luna_integration_is_opt_in() -> None:
    if not os.environ.get("VERA_RUN_REAL_LUNA_INTEGRATION"):
        pytest.skip(
            "Set VERA_RUN_REAL_LUNA_INTEGRATION=1 for the native Codex/Luna test"
        )
    output_dir = Path(os.environ["VERA_REAL_LUNA_OUTPUT_DIR"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "invoice_id": "real-luna-smoke-1",
        "supplier": {"name": "TIM S.p.A.", "tax_id": "01234567890"},
        "invoice_lines": [
            {"description": "Servizi di telefonia mobile", "line_total": "100.00"}
        ],
        "actual_accounting_treatment": [
            {
                "account_code": "625010",
                "account_description": "Spese telefoniche",
                "amount_signed": "100.00",
            }
        ],
        "deterministic_findings": [],
    }
    prompt = audit_core.build_luna_prompt([packet])
    schema = audit_core.luna_output_schema([packet["invoice_id"]])

    result = luna_worker.run_luna_chunk(
        prompt,
        schema,
        output_dir,
        audit_core.WORKFLOW_ID,
        audit_core._sha256_json([packet]),
        "low",
    )

    assert result["model"] == "gpt-5.6-luna"
    assert audit_core.validate_luna_result(
        result["response_payload"], [packet["invoice_id"]]
    )

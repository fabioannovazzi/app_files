"""Synthetic acceptance cases for preparation, review and ordinary XML export."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from invoice_checks import check_invoice
from invoice_schema import InvoiceSchema, flatten_fields
from invoice_workflow import (
    DECISIONS,
    FOREIGN_DECISIONS,
    digest,
    export_invoice,
    prepare_draft,
)
from source_evidence import prepare_source_evidence


def _proposal(tmp_path: Path, document_type: str = "TD01") -> tuple[dict, Path]:
    root = tmp_path / "inputs"
    root.mkdir(exist_ok=True)
    source = root / "synthetic-invoice.txt"
    source.write_text(
        "Synthetic approved test data: service 100.00 EUR, VAT 22.00 EUR, total 122.00 EUR."
    )
    foreign = document_type in {"TD17", "TD18", "TD19"}
    invoice = {
        "FatturaElettronicaHeader": {
            "DatiTrasmissione": {
                "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
                "ProgressivoInvio": "00001",
                "FormatoTrasmissione": "FPR12",
                "CodiceDestinatario": "0000000",
            },
            "CedentePrestatore": {
                "DatiAnagrafici": {
                    "IdFiscaleIVA": {
                        "IdPaese": "DE" if foreign else "IT",
                        "IdCodice": "123456789" if foreign else "01234567897",
                    },
                    "Anagrafica": {"Denominazione": "Synthetic supplier & services"},
                    "RegimeFiscale": "RF01",
                },
                "Sede": {
                    "Indirizzo": "Via Esempio 1",
                    "CAP": "00000" if foreign else "00100",
                    "Comune": "Berlino" if foreign else "Roma",
                    "Nazione": "DE" if foreign else "IT",
                },
            },
            "CessionarioCommittente": {
                "DatiAnagrafici": {
                    "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "09876543217"},
                    "Anagrafica": {"Denominazione": "Synthetic customer"},
                },
                "Sede": {
                    "Indirizzo": "Via Esempio 2",
                    "CAP": "20100",
                    "Comune": "Milano",
                    "Nazione": "IT",
                },
            },
        },
        "FatturaElettronicaBody": [
            {
                "DatiGenerali": {
                    "DatiGeneraliDocumento": {
                        "TipoDocumento": document_type,
                        "Divisa": "EUR",
                        "Data": "2026-09-01",
                        "Numero": "TEST-1",
                        "ImportoTotaleDocumento": "122.00",
                    }
                },
                "DatiBeniServizi": {
                    "DettaglioLinee": [
                        {
                            "NumeroLinea": "1",
                            "Descrizione": "Synthetic service <review>",
                            "Quantita": "1.00",
                            "PrezzoUnitario": "100.00",
                            "PrezzoTotale": "100.00",
                            "AliquotaIVA": "22.00",
                        }
                    ],
                    "DatiRiepilogo": [
                        {
                            "AliquotaIVA": "22.00",
                            "ImponibileImporto": "100.00",
                            "Imposta": "22.00",
                        }
                    ],
                },
            }
        ],
    }
    if foreign:
        invoice["FatturaElettronicaBody"][0]["DatiGenerali"]["DatiFattureCollegate"] = [
            {"IdDocumento": "FOREIGN-1", "Data": "2026-08-31"}
        ]
    proposal = {
        "schema_version": 2,
        "draft_id": "synthetic-1",
        "route": "foreign_integration" if foreign else "domestic",
        "transmission_mode": "intermediary" if foreign else "supplier_direct",
        "invoice": invoice,
        "sources": [
            {
                "id": "source-1",
                "path": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "title": "Synthetic fixture",
                "role": "invoice",
                "evidence_group": "invoice-1",
            }
        ],
        "field_evidence": {},
        "decisions": {},
        "questions": [],
    }
    _refresh_evidence(proposal)
    return proposal, root


def _refresh_evidence(proposal: dict) -> None:
    ref = [{"source_id": "source-1", "locator": "synthetic fixture"}]
    proposal["field_evidence"] = {
        pointer: {"kind": "source", "basis": "Synthetic test value", "references": ref}
        for pointer in flatten_fields(proposal["invoice"])
    }
    names = DECISIONS + (
        FOREIGN_DECISIONS if proposal["route"] == "foreign_integration" else ()
    )
    proposal["decisions"] = {
        name: {
            "assessment": "Explicit synthetic test decision; not professional advice",
            "references": ref,
        }
        for name in names
    }


def _review(proposal: dict) -> dict:
    return {
        "schema_version": 1,
        "proposal_sha256": digest(proposal),
        "status": "approved_for_export",
        "reviewer": "Synthetic reviewer",
        "reviewed_at": "2026-09-14T12:00:00+02:00",
        "approval_basis": "Synthetic test authorization",
    }


@pytest.mark.parametrize("document_type", ["TD01", "TD04", "TD17", "TD18", "TD19"])
def test_reviewed_invoice_exports_schema_valid_xml(
    tmp_path: Path, document_type: str
) -> None:
    proposal, inputs = _proposal(tmp_path, document_type)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    result = export_invoice(revision, _review(proposal), input_root=inputs)

    xml = (revision / "export" / result["xml_path"]).read_bytes()
    assert result["status"] == "exported_for_operator"
    assert result["sdi_acceptance"] == "not_tested"
    assert InvoiceSchema().errors(xml) == []
    assert etree.fromstring(xml).findtext(".//TipoDocumento") == document_type
    assert b"&amp;" in xml


def test_preparation_never_writes_invoice_xml(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    assert list(revision.rglob("*.xml")) == []
    assert (
        json.loads((revision / "validation.json").read_text())["status"]
        == "awaiting_professional_review"
    )
    assert "&lt;review&gt;" in (revision / "preview.html").read_text()


@pytest.mark.parametrize("missing", ["field", "decision", "question"])
def test_missing_or_uncertain_evidence_preserves_blocked_draft(
    tmp_path: Path, missing: str
) -> None:
    proposal, inputs = _proposal(tmp_path)
    if missing == "field":
        proposal["invoice"]["FatturaElettronicaHeader"]["CedentePrestatore"][
            "DatiAnagrafici"
        ]["RegimeFiscale"] = None
    elif missing == "decision":
        del proposal["decisions"]["tax_treatment"]
    else:
        proposal["questions"] = ["Two photos disagree on the invoice date"]
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    with pytest.raises(ValueError, match="export blocked"):
        export_invoice(revision, _review(proposal), input_root=inputs)

    assert json.loads((revision / "validation.json").read_text())["status"] == "blocked"
    assert list(revision.rglob("*.xml")) == []


def test_schema_orders_fields_and_preserves_optional_payment(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    body["DatiPagamento"] = [
        {
            "DettaglioPagamento": [
                {"ImportoPagamento": "122.00", "ModalitaPagamento": "MP05"}
            ],
            "CondizioniPagamento": "TP02",
        }
    ]

    payload = InvoiceSchema().serialize(proposal["invoice"])

    assert InvoiceSchema().errors(payload) == []
    assert etree.fromstring(payload).findtext(".//ImportoPagamento") == "122.00"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("PrezzoTotale", "99.00", "line total"),
        ("AliquotaIVA", "0.00", "Natura"),
    ],
)
def test_line_inconsistency_blocks_export(
    tmp_path: Path, field: str, value: str, reason: str
) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["invoice"]["FatturaElettronicaBody"][0]["DatiBeniServizi"][
        "DettaglioLinee"
    ][0][field] = value
    _refresh_evidence(proposal)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    with pytest.raises(ValueError, match=reason):
        export_invoice(revision, _review(proposal), input_root=inputs)


def test_changed_source_invalidates_approved_draft(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )
    (inputs / "synthetic-invoice.txt").write_text("Changed source")

    with pytest.raises(ValueError, match="Source changed"):
        export_invoice(revision, _review(proposal), input_root=inputs)


def test_changed_proposal_requires_new_review(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    review = _review(proposal)
    proposal["invoice"]["FatturaElettronicaBody"][0]["DatiGenerali"][
        "DatiGeneraliDocumento"
    ]["Numero"] = "TEST-2"
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    with pytest.raises(ValueError, match="exact proposal"):
        export_invoice(revision, review, input_root=inputs)


def test_identical_export_retry_reuses_bytes(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )
    expected = export_invoice(revision, _review(proposal), input_root=inputs)

    result = export_invoice(revision, _review(proposal), input_root=inputs)

    assert result == expected
    assert len(list((revision / "export").glob("*.xml"))) == 1


def test_foreign_supplier_not_swapped_with_italian_customer(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path, "TD17")
    header = proposal["invoice"]["FatturaElettronicaHeader"]
    header["CedentePrestatore"]["DatiAnagrafici"]["IdFiscaleIVA"]["IdPaese"] = "IT"

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert any("supplier's foreign identifier" in issue for issue in issues)


def test_multiple_photos_form_one_invoice_evidence_group(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    second = inputs / "other-view.txt"
    second.write_text("Different view of the same synthetic invoice")
    proposal["sources"].append(
        dict(
            proposal["sources"][0],
            id="source-2",
            path=second.name,
            sha256=hashlib.sha256(second.read_bytes()).hexdigest(),
        )
    )

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["source_file_count"] == 2
    assert len(proposal["invoice"]["FatturaElettronicaBody"]) == 1


def test_duplicate_bodies_are_blocked(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path)
    bodies = proposal["invoice"]["FatturaElettronicaBody"]
    bodies.append(copy.deepcopy(bodies[0]))

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert any("duplicate invoice identity" in issue for issue in issues)


def test_exempt_invoice_requires_consistent_nature_and_zero_tax(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    body["DatiGenerali"]["DatiGeneraliDocumento"]["ImportoTotaleDocumento"] = "100.00"
    body["DatiBeniServizi"]["DettaglioLinee"][0].update(AliquotaIVA="0.00", Natura="N4")
    body["DatiBeniServizi"]["DatiRiepilogo"][0].update(
        AliquotaIVA="0.00", Natura="N4", Imposta="0.00"
    )

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert issues == []


def test_export_blocks_invalid_supplier_fiscal_code_control_character(
    tmp_path: Path,
) -> None:
    proposal, inputs = _proposal(tmp_path)
    supplier = proposal["invoice"]["FatturaElettronicaHeader"]["CedentePrestatore"][
        "DatiAnagrafici"
    ]
    supplier["CodiceFiscale"] = "RSSMRA80A01H501X"
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any("fiscal code" in issue for issue in report["mechanical_errors"])


def test_valid_personal_fiscal_code_passes_fixed_control_character_check(
    tmp_path: Path,
) -> None:
    proposal, _ = _proposal(tmp_path)
    supplier = proposal["invoice"]["FatturaElettronicaHeader"]["CedentePrestatore"][
        "DatiAnagrafici"
    ]
    supplier["CodiceFiscale"] = "RSSMRA80A01H501U"

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert not any("fiscal code" in issue for issue in issues)


def test_export_blocks_invalid_italian_vat_check_digit(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["invoice"]["FatturaElettronicaHeader"]["CedentePrestatore"][
        "DatiAnagrafici"
    ]["IdFiscaleIVA"]["IdCodice"] = "01234567898"
    proposal["invoice"]["FatturaElettronicaHeader"]["DatiTrasmissione"][
        "IdTrasmittente"
    ]["IdCodice"] = "01234567898"
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any("VAT number" in issue for issue in report["mechanical_errors"])


def test_export_blocks_truncated_customer_fiscal_code_from_latest_rejection(
    tmp_path: Path,
) -> None:
    proposal, inputs = _proposal(tmp_path)
    customer = proposal["invoice"]["FatturaElettronicaHeader"][
        "CessionarioCommittente"
    ]["DatiAnagrafici"]
    customer["CodiceFiscale"] = "RSSMRA80A01H501"
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any("fiscal code" in issue for issue in report["mechanical_errors"])


def test_export_allows_distinct_valid_italian_vat_and_numeric_fiscal_code(
    tmp_path: Path,
) -> None:
    proposal, inputs = _proposal(tmp_path)
    customer = proposal["invoice"]["FatturaElettronicaHeader"][
        "CessionarioCommittente"
    ]["DatiAnagrafici"]
    customer["CodiceFiscale"] = "01234567897"
    _refresh_evidence(proposal)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    result = export_invoice(revision, _review(proposal), input_root=inputs)

    assert result["sdi_acceptance"] == "not_tested"


@pytest.mark.parametrize("transmission_mode", ["supplier_direct", "intermediary"])
def test_export_accepts_personal_transmitter_fiscal_code(
    tmp_path: Path, transmission_mode: str
) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["transmission_mode"] = transmission_mode
    header = proposal["invoice"]["FatturaElettronicaHeader"]
    header["DatiTrasmissione"]["IdTrasmittente"]["IdCodice"] = "RSSMRA80A01H501U"
    if transmission_mode == "supplier_direct":
        header["CedentePrestatore"]["DatiAnagrafici"][
            "CodiceFiscale"
        ] = "RSSMRA80A01H501U"
    _refresh_evidence(proposal)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    result = export_invoice(revision, _review(proposal), input_root=inputs)

    assert result["xml_path"] == "ITRSSMRA80A01H501U_00001.xml"


@pytest.mark.parametrize("code", ["RSSMRA80A01H501X", "RSSMRA80A01H501", "01234567898"])
def test_invalid_transmitter_identifier_blocks_draft(tmp_path: Path, code: str) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["transmission_mode"] = "intermediary"
    proposal["invoice"]["FatturaElettronicaHeader"]["DatiTrasmissione"][
        "IdTrasmittente"
    ]["IdCodice"] = code
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any("Transmitter:" in issue for issue in report["mechanical_errors"])


def test_direct_transmission_requires_supplier_as_transmitter(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["invoice"]["FatturaElettronicaHeader"]["DatiTrasmissione"][
        "IdTrasmittente"
    ]["IdCodice"] = "09876543217"
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any("Direct transmission" in issue for issue in report["mechanical_errors"])


def test_uncertain_fiscal_identity_blocks_export(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    pointer = "/FatturaElettronicaHeader/CedentePrestatore/DatiAnagrafici/IdFiscaleIVA/IdCodice"
    proposal["field_evidence"][pointer]["uncertain"] = True

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert report["status"] == "blocked"
    assert any(pointer in issue for issue in report["issues"])


def test_export_uses_sdi_transmitter_and_progressive_filename(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    result = export_invoice(revision, _review(proposal), input_root=inputs)

    assert result["xml_path"] == "IT01234567897_00001.xml"


def test_workflow_requires_latest_gateway_evidence_review() -> None:
    skill = (
        Path(__file__).resolve().parents[1] / "skills/invoice-xml/SKILL.md"
    ).read_text()
    normalized = " ".join(skill.split())

    assert "inspect the newest supplied notification or screenshot" in normalized
    assert "every currently visible error code and message" in normalized
    assert "exact latest control passes" in normalized


def test_unsupported_optional_block_is_retained_and_blocks_export(
    tmp_path: Path,
) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["invoice"]["FatturaElettronicaBody"][0]["DatiGenerali"][
        "DatiGeneraliDocumento"
    ]["DatiBollo"] = {"BolloVirtuale": "SI", "ImportoBollo": "2.00"}
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    report = json.loads((revision / "validation.json").read_text())
    assert any("DatiBollo" in issue for issue in report["issues"])
    assert "DatiBollo" in (revision / "proposal.json").read_text()


def test_source_path_escape_is_rejected(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["sources"][0]["path"] = "../unbound.txt"

    with pytest.raises(ValueError, match="relative"):
        prepare_draft(proposal, input_root=inputs, output_dir=tmp_path / "output")


def test_unknown_invoice_fields_are_not_silently_discarded(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["invoice"]["Unexpected"] = "meaningful information"
    _refresh_evidence(proposal)

    revision = prepare_draft(
        proposal, input_root=inputs, output_dir=tmp_path / "output"
    )

    assert "Unknown or unsupported" in (revision / "validation.json").read_text()


def test_pdf_intake_retains_text_and_render_for_every_page(tmp_path: Path) -> None:
    import fitz

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    source = inputs / "synthetic.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((40, 60), "Synthetic invoice: 100.00 EUR")
        document.new_page().insert_text((40, 60), "VAT 22.00 EUR; total 122.00 EUR")
        document.save(source)
    selection = [
        {
            "id": "invoice",
            "path": source.name,
            "title": "Synthetic invoice",
            "role": "invoice",
            "evidence_group": "one-invoice",
        }
    ]

    folder = prepare_source_evidence(
        selection, input_root=inputs, output_dir=tmp_path / "output"
    )

    material = json.loads((folder / "source_evidence.json").read_text())["material"][0]
    assert len(material["views"]) == 2
    assert "100.00" in (folder / material["views"][0]["text"]).read_text()
    assert "122.00" in (folder / material["views"][1]["text"]).read_text()
    assert (folder / material["views"][1]["image"]).read_bytes().startswith(b"\x89PNG")


def test_managed_run_prepares_and_exports_bound_invoice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    import invoice_workflow
    import source_evidence

    repository = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(repository / "plugins/studio-archive/scripts"))
    spec = importlib.util.spec_from_file_location(
        "invoice_test_ledger",
        repository / "plugins/studio-archive/scripts/client_ledger.py",
    )
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    client = tmp_path / "synthetic-client"
    client.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(
        client, client_id, "Synthetic invoice workflow"
    )
    proposal, inputs = _proposal(tmp_path)
    imported = ledger.import_document(
        client,
        client_id,
        engagement["engagement_id"],
        (inputs / "synthetic-invoice.txt").resolve(),
        "source",
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "invoice-xml",
        "0.1.0",
        input_ids=[imported["receipt"]["input_id"]],
        idempotency_key="invoice-test",
    )
    running = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    output = Path(running["output_dir"])
    bound_inputs = Path(running["context"]["input_dir"])
    bound_source = next(path for path in bound_inputs.rglob("*.txt"))
    proposal["sources"][0]["path"] = bound_source.relative_to(bound_inputs).as_posix()
    proposal_path = output / "proposal.json"
    proposal_path.write_text(json.dumps(proposal))
    common = ["--client-engagement", running["context_path"], "--output", str(output)]
    selection = output / "source_selection.json"
    selection.write_text(json.dumps(proposal["sources"]))
    source_evidence.main(["--selection", str(selection), *common])
    invoice_workflow.main(["prepare", "--proposal", str(proposal_path), *common])
    revision = output / f"draft-{digest(proposal)}"
    review_path = output / "approval.json"
    review_path.write_text(json.dumps(_review(proposal)))

    result = invoice_workflow.main(
        ["export", "--revision", str(revision), "--review", str(review_path), *common]
    )

    assert result == 0
    assert (
        json.loads((revision / "export/export_report.json").read_text())["status"]
        == "exported_for_operator"
    )

    from tests.model_data_helpers import write_no_model_report

    run_id = prepared["run"]["run_id"]
    declarations = write_no_model_report(output, "invoice-xml", run_id)
    mime_types = {
        ".json": "application/json",
        ".html": "text/html",
        ".txt": "text/plain",
        ".xml": "application/xml",
    }
    declarations += [
        {
            "artifact_id": f"invoice.{index}",
            "path": path.relative_to(output).as_posix(),
            "purpose": "Retain synthetic invoice preparation and export evidence.",
            "audience": "review",
            "media_type": mime_types[path.suffix],
        }
        for index, path in enumerate(sorted(output.rglob("*")))
        if path.is_file() and not path.name.startswith("model_data_report.")
    ]
    sealed = ledger.finalize_run(
        client, engagement["engagement_id"], run_id, declarations
    )

    completed = ledger.complete_run(client, engagement["engagement_id"], run_id)

    assert sealed["run"]["status"] == "ready_for_review"
    assert completed["run"]["status"] == "completed"
    assert ledger.validate_run_artifacts(client, engagement["engagement_id"], run_id)
    disclosure = json.loads((output / "model_data_report.json").read_text())
    assert disclosure["workflow_id"] == "invoice-xml"
    assert disclosure["run_id"] == run_id
    assert disclosure["phases"][0]["outcome"] == "no_case_data"


def test_multirate_invoice_reconciles_separate_vat_groups(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    body["DatiBeniServizi"]["DettaglioLinee"].append(
        {
            "NumeroLinea": "2",
            "Descrizione": "Second synthetic service",
            "Quantita": "2.00",
            "PrezzoUnitario": "25.00",
            "PrezzoTotale": "50.00",
            "AliquotaIVA": "10.00",
        }
    )
    body["DatiBeniServizi"]["DatiRiepilogo"].append(
        {"AliquotaIVA": "10.00", "ImponibileImporto": "50.00", "Imposta": "5.00"}
    )
    body["DatiGenerali"]["DatiGeneraliDocumento"]["ImportoTotaleDocumento"] = "177.00"

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert issues == []


def test_line_discount_applies_before_quantity(tmp_path: Path) -> None:
    proposal, _ = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    line = body["DatiBeniServizi"]["DettaglioLinee"][0]
    line.update(
        Quantita="2.00",
        ScontoMaggiorazione=[{"Tipo": "SC", "Percentuale": "10.00"}],
        PrezzoTotale="180.00",
    )
    body["DatiBeniServizi"]["DatiRiepilogo"][0].update(
        ImponibileImporto="180.00", Imposta="39.60"
    )
    body["DatiGenerali"]["DatiGeneraliDocumento"]["ImportoTotaleDocumento"] = "219.60"

    issues = check_invoice(
        proposal["invoice"], proposal["route"], proposal["transmission_mode"]
    )

    assert issues == []


def test_dependency_preflight_reports_missing_xml_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import check_dependencies

    monkeypatch.setattr(
        check_dependencies.importlib.util,
        "find_spec",
        lambda name: None if name == "lxml" else object(),
    )

    result = check_dependencies.main([])

    assert result == 1


def test_explicit_rounding_reconciles_summary_and_document(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    line = body["DatiBeniServizi"]["DettaglioLinee"][0]
    line.update(PrezzoUnitario="100.004", PrezzoTotale="100.004")
    body["DatiBeniServizi"]["DatiRiepilogo"][0]["Arrotondamento"] = "-0.004"
    body["DatiGenerali"]["DatiGeneraliDocumento"].update(
        Arrotondamento="0.01", ImportoTotaleDocumento="122.01"
    )
    _refresh_evidence(proposal)

    revision = prepare_draft(proposal, input_root=inputs, output_dir=tmp_path / "out")

    assert json.loads((revision / "validation.json").read_text())["issues"] == []


def test_context_screenshot_cannot_be_the_only_invoice_basis(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    proposal["sources"][0]["role"] = "context"

    with pytest.raises(ValueError, match="Context images alone"):
        prepare_draft(proposal, input_root=inputs, output_dir=tmp_path / "out")


def test_oversized_pdf_page_is_rejected_before_rendering(tmp_path: Path) -> None:
    import fitz

    source = tmp_path / "oversized.pdf"
    with fitz.open() as document:
        document.new_page(width=20000, height=20000)
        document.save(source)

    with pytest.raises(ValueError, match="Oversized PDF page"):
        prepare_source_evidence(
            [{"id": "page", "path": source.name}],
            input_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_export_conflict_preserves_existing_file(tmp_path: Path) -> None:
    proposal, inputs = _proposal(tmp_path)
    revision = prepare_draft(proposal, input_root=inputs, output_dir=tmp_path / "out")
    export_folder = revision / "export"
    export_folder.mkdir()
    conflicting = export_folder / "IT01234567897_00001.xml"
    conflicting.write_bytes(b"Existing operator document")

    with pytest.raises(ValueError, match="Export already exists"):
        export_invoice(revision, _review(proposal), input_root=inputs)

    assert conflicting.read_bytes() == b"Existing operator document"
    assert not (export_folder / "export_report.json").exists()


def test_retired_generic_nature_is_blocked_despite_schema_acceptance(
    tmp_path: Path,
) -> None:
    proposal, inputs = _proposal(tmp_path)
    body = proposal["invoice"]["FatturaElettronicaBody"][0]
    body["DatiBeniServizi"]["DettaglioLinee"][0].update(AliquotaIVA="0.00", Natura="N2")
    body["DatiBeniServizi"]["DatiRiepilogo"][0].update(
        AliquotaIVA="0.00", Natura="N2", Imposta="0.00"
    )
    body["DatiGenerali"]["DatiGeneraliDocumento"]["ImportoTotaleDocumento"] = "100.00"
    _refresh_evidence(proposal)

    revision = prepare_draft(proposal, input_root=inputs, output_dir=tmp_path / "out")

    report = json.loads((revision / "validation.json").read_text())
    assert report["schema_valid"] is True
    assert report["status"] == "blocked"
    assert any("retired from 2021" in issue for issue in report["issues"])


@pytest.mark.parametrize(
    "schema_root",
    [
        "plugins/invoice-xml/references/xsd",
        "plugin_packages/vera/claude/vera/modules/invoice-xml/references/xsd",
    ],
)
def test_git_preserves_original_pinned_schema_bytes(schema_root: str) -> None:
    repository = Path(__file__).resolve().parents[3]
    relative = f"{schema_root}/Schema_VFPR12_v1.2.3.xsd"
    original = subprocess.check_output(
        ["git", "hash-object", "--no-filters", relative], cwd=repository
    )

    stored = subprocess.check_output(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "hash-object",
            f"--path={relative}",
            relative,
        ],
        cwd=repository,
    )

    assert stored == original

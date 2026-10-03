"""Approved export and supplied-file comparisons using fictional evidence only."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from lxml import etree

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
import lipe_export
from lipe import save_result
from lipe_approval import accept_review, prepare_review
from lipe_authorization import load_export_registry, request_bytes
from lipe_core import ContractError, calculate, read_json
from lipe_export import compare_files, export_xml, main
from lipe_xml import build_test_xml
from lipe_xml_compare import compare_ivp, read_ivp
from test_lipe import amounts, case_data, monthly_quarter, prepare, quarterly
from test_lipe_approval import (
    AFTER,
    AT,
    BEFORE,
    archive_example,
    crypto,
    example,
    frontpage,
    sign,
)

IVP = "urn:www.agenziaentrate.gov.it:specificheTecniche:sco:ivp"
INTERMEDIARY = {
    "CFIntermediario": "11111111115",
    "ImpegnoPresentazione": "2",
    "DataImpegno": "2026-10-01",
    "FirmaIntermediario": "1",
}


def signed_approval(
    root,
    crypto,
    *,
    real=False,
    intermediary=True,
    representative=False,
    case_override=None,
    at=AT,
):
    """Create actual test signatures without asserting real professional acceptance."""
    options = copy.deepcopy(INTERMEDIARY) if intermediary else {}
    if representative:
        options.update(
            CodiceFiscale="12345678903",
            CFDichiarante="RSSMRA80A01H501U",
            CodiceCaricaDichiarante="1",
        )
    if real:
        case, front, draft, sources, output, context, paths, report = archive_example(
            root, front_overrides=options
        )
        run_id = read_json(context)["run_id"]
    else:
        if case_override is None:
            case, _, draft = example(root)
        else:
            case = copy.deepcopy(case_override)
            prepare(case, root)
            draft = save_result(case, calculate(case, root), root / "drafts")
        front = frontpage(case, root, **options)
        sources, output, context, paths, report, run_id = (
            root,
            root,
            None,
            {},
            None,
            None,
        )
    if representative:
        front["taxpayer_kind"] = "OTHER"
    authority = copy.deepcopy(crypto["authority"])
    authority["policy"]["data_origin"] = case["data_origin"]
    packet = prepare_review(
        case,
        front,
        draft,
        sources,
        output / "request",
        at=at,
        model_data_report=report,
        run_id=run_id,
    )
    request = read_json(packet / "request.json")
    mandate = {
        "schema_version": "lipe.mandate.v1",
        "policy_id": "fictional-policy",
        "mandate_id": "fictional-mandate",
        "scope": request["scope"],
        "reviewer_name": "FICTIONAL EXPORT REVIEWER",
        "professional_reference": "SYNTHETIC ONLY",
        "reviewer_certificate_sha256": crypto["certs"]["reviewer"]
        .fingerprint(hashes.SHA256())
        .hex(),
        "actions": ["APPROVE_LIPE_EXPORT"],
        "valid_from": BEFORE.isoformat(),
        "valid_until": AFTER.isoformat(),
        "powers_evidence": [
            {"reference": "FICTIONAL AUTHORITY ONLY", "sha256": "1" * 64}
        ],
    }
    mandate_path = root / "mandate.json"
    mandate_path.write_bytes(request_bytes(mandate))
    signature = sign(
        (packet / "request.json").read_bytes(),
        root / "decision.p7s",
        crypto,
        "reviewer",
    )
    mandate_signature = sign(
        mandate_path.read_bytes(), root / "mandate.p7s", crypto, "admin"
    )
    approved = accept_review(
        case,
        front,
        draft,
        sources,
        packet / "request.json",
        output / "approved",
        signature=signature,
        mandate=mandate_path,
        mandate_signature=mandate_signature,
        authority=authority,
        at=at,
        model_data_report=report,
        run_id=run_id,
    )
    return (
        {
            "case": case,
            "front": front,
            "draft_folder": draft,
            "source_root": sources,
            "approval_folder": approved,
            "authority": authority,
            "at": at,
            "model_data_report": report,
            "run_id": run_id,
        },
        output,
        context,
        paths,
    )


def export_options(tmp_path, crypto, **kwargs):
    inputs, output, _, _ = signed_approval(tmp_path, crypto, **kwargs)
    return {
        **inputs,
        "output": output / "export",
        "registry": tmp_path / "exports.sqlite3",
        "progressive": 7,
    }


def synthetic_xml() -> bytes:
    return build_test_xml(
        read_json(PLUGIN / "examples/synthetic-case.json"), PLUGIN / "examples"
    )


def change_xml(raw, xpath, value):
    root = etree.fromstring(raw)
    root.find(xpath, {"iv": IVP}).text = value
    return etree.tostring(root)


def test_approved_export_preserves_originals_and_emits_checked_unsigned_import_xml(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto, representative=True)

    folder = export_xml(**options)

    filename = "IT11111111115_LI_00007.xml"
    parsed = read_ivp((folder / filename).read_bytes())
    assert parsed["header"] == {
        "CodiceFornitura": "IVP18",
        "CodiceFiscaleDichiarante": "RSSMRA80A01H501U",
        "CodiceCarica": "1",
    }
    assert parsed["frontpage"] == {
        "CodiceFiscale": "12345678903",
        "AnnoImposta": "2026",
        "PartitaIVA": "12345678903",
        "CFDichiarante": "RSSMRA80A01H501U",
        "CodiceCaricaDichiarante": "1",
        "FirmaDichiarazione": "1",
        "CFIntermediario": "11111111115",
        "ImpegnoPresentazione": "2",
        "DataImpegno": "01102026",
        "FirmaIntermediario": "1",
    }
    assert parsed["modules"][0]["fields"] == {
        "NumeroModulo": "1",
        "Mese": "4",
        "TotaleOperazioniAttive": "1000,00",
        "TotaleOperazioniPassive": "500,00",
        "IvaEsigibile": "220,00",
        "IvaDetratta": "110,00",
        "IvaDovuta": "110,00",
        "ImportoDaVersare": "110,00",
    }
    assert parsed["signature_present"] is False
    assert (folder / "approved-summary.pdf").read_bytes() == (
        options["draft_folder"] / "summary.pdf"
    ).read_bytes()
    assert (folder / "approval/decision.p7s").read_bytes() == (
        options["approval_folder"] / "decision.p7s"
    ).read_bytes()
    receipt = read_json(folder / "export.json")
    assert receipt["status"] == "APPROVED_VERSION_XML_UNSIGNED"
    assert receipt["filing_status"] == "NOT_SIGNED_OR_TRANSMITTED"
    assert receipt["professional_and_importer_acceptance"] == "NOT_ESTABLISHED"
    assert receipt["roundtrip"] == {
        "schema_validation": "PASS",
        "frontpage_and_header": "PASS",
        "periods_and_all_vp_values": "PASS",
        "zero_omission": "PASS",
        "unsigned": True,
    }


def test_editable_approval_status_is_ignored_and_original_signatures_are_rechecked(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto)
    (options["approval_folder"] / "approval.json").write_text(
        '{"forged_status":"APPROVED_WITHOUT_CHECKS"}', encoding="utf-8"
    )

    folder = export_xml(**options)

    proof = read_json(folder / "approval/approval.json")
    assert proof["review_verification"]["signature_integrity"]["status"] == "PASS"
    assert "forged_status" not in proof


def test_q4_option_export_uses_period_five_and_omits_inapplicable_rows(
    tmp_path, crypto
):
    case = quarterly(4)
    case["modules"][0].update(vp13="103.29", vp13_method=1)
    options = export_options(
        tmp_path,
        crypto,
        case_override=case,
        at=datetime(2027, 1, 10, 10, tzinfo=timezone.utc),
    )

    folder = export_xml(**options)

    parsed = read_ivp((folder / "IT11111111115_LI_00007.xml").read_bytes())
    assert parsed["modules"][0]["fields"] == {
        "NumeroModulo": "1",
        "Trimestre": "5",
        "TotaleOperazioniAttive": "1000,00",
        "TotaleOperazioniPassive": "500,00",
        "IvaEsigibile": "220,00",
        "IvaDetratta": "110,00",
        "IvaDovuta": "110,00",
        "Metodo": "1",
        "Acconto": "103,29",
    }


def test_quarterly_interest_export_preserves_independent_expected_cents(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto, case_override=quarterly())

    folder = export_xml(**options)

    module = read_ivp((folder / "IT11111111115_LI_00007.xml").read_bytes())["modules"][
        0
    ]
    assert module["fields"]["Trimestre"] == "2"
    assert module["fields"]["InteressiDovuti"] == "1,10"
    assert module["fields"]["ImportoDaVersare"] == "111,10"


def test_approved_monthly_credit_export_preserves_each_carry_and_final_debit(
    tmp_path, crypto
):
    case = case_data()
    amounts(case, 4, "SALES", "-100.00", "-22.00", "0.00")
    options = export_options(tmp_path, crypto, case_override=case)

    folder = export_xml(**options)

    parsed = read_ivp((folder / "IT11111111115_LI_00007.xml").read_bytes())
    assert parsed["modules"][0]["fields"] == {
        "NumeroModulo": "1",
        "Mese": "4",
        "TotaleOperazioniAttive": "-100,00",
        "TotaleOperazioniPassive": "500,00",
        "IvaEsigibile": "-22,00",
        "IvaDetratta": "110,00",
        "IvaCredito": "132,00",
        "ImportoACredito": "132,00",
    }
    assert parsed["modules"][1]["fields"] == {
        "NumeroModulo": "2",
        "Mese": "5",
        "TotaleOperazioniAttive": "1000,00",
        "TotaleOperazioniPassive": "500,00",
        "IvaEsigibile": "220,00",
        "IvaDetratta": "110,00",
        "IvaDovuta": "110,00",
        "CreditoPeriodoPrecedente": "132,00",
        "ImportoACredito": "22,00",
    }
    assert parsed["modules"][2]["fields"] == {
        "NumeroModulo": "3",
        "Mese": "6",
        "TotaleOperazioniAttive": "1000,00",
        "TotaleOperazioniPassive": "500,00",
        "IvaEsigibile": "220,00",
        "IvaDetratta": "110,00",
        "IvaDovuta": "110,00",
        "CreditoPeriodoPrecedente": "22,00",
        "ImportoDaVersare": "88,00",
    }


@pytest.mark.parametrize(
    "regime,method,period_field,period,expected_due",
    [
        ("MONTHLY", 4, "Mese", "12", "6,71"),
        ("QUARTERLY_SPECIAL", 2, "Trimestre", "4", "6,71"),
        ("QUARTERLY_OPTION", 3, "Trimestre", "5", None),
    ],
)
def test_final_period_export_preserves_reviewed_advance_and_method(
    tmp_path, crypto, regime, method, period_field, period, expected_due
):
    case = monthly_quarter(4) if regime == "MONTHLY" else quarterly(4, regime)
    case["modules"][-1].update(vp13="103.29", vp13_method=method)
    options = export_options(
        tmp_path,
        crypto,
        case_override=case,
        at=datetime(2027, 1, 10, 10, tzinfo=timezone.utc),
    )

    folder = export_xml(**options)

    module = read_ivp((folder / "IT11111111115_LI_00007.xml").read_bytes())["modules"][
        -1
    ]
    assert module["fields"][period_field] == period
    assert module["fields"]["Metodo"] == str(method)
    assert module["fields"]["Acconto"] == "103,29"
    assert module["fields"].get("ImportoDaVersare") == expected_due
    assert "InteressiDovuti" not in module["fields"]
    assert "DebitoPrecedente" not in module["fields"]


def test_vp10_export_uses_the_actual_schema_tag_and_preserves_amount(tmp_path, crypto):
    case = case_data()
    case["modules"][0]["vp10"] = "12.34"
    options = export_options(tmp_path, crypto, case_override=case)

    folder = export_xml(**options)

    module = read_ivp((folder / "IT11111111115_LI_00007.xml").read_bytes())["modules"][
        0
    ]
    assert module["fields"]["VersamentiAutoUE"] == "12,34"
    assert module["fields"]["ImportoDaVersare"] == "97,66"
    assert "VersamentiAuto" not in module["fields"]


@pytest.mark.parametrize(
    "changed",
    [
        "workpaper",
        "source",
        "signature",
        "request",
        "mandate",
        "expired",
        "revoked_mandate",
        "revoked_certificate",
    ],
)
def test_changed_or_no_longer_authorized_evidence_prevents_export(
    tmp_path, crypto, changed
):
    options = export_options(tmp_path, crypto)
    approved = options["approval_folder"]
    if changed == "workpaper":
        (options["draft_folder"] / "workpaper.md").write_bytes(b"changed")
    elif changed == "source":
        (tmp_path / "synthetic-registers.txt").write_bytes(b"changed")
    elif changed == "signature":
        sign(
            (approved / "request.json").read_bytes(),
            approved / "decision.p7s",
            crypto,
            "admin",
        )
    elif changed in {"request", "mandate"}:
        (approved / (changed + ".json")).write_bytes(b"{}")
    elif changed == "expired":
        options["at"] = AT + timedelta(hours=25)
    elif changed == "revoked_mandate":
        options["authority"]["policy"]["revoked_mandate_ids"] = ["fictional-mandate"]
    else:
        options["authority"]["crls"] = crypto["revoked"]

    with pytest.raises(ContractError):
        export_xml(**options)

    assert not options["output"].exists()
    assert not options["registry"].exists()


def test_valid_approval_without_intermediary_cannot_invent_import_filename(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto, intermediary=False)

    with pytest.raises(ContractError, match="intermediary fiscal code"):
        export_xml(**options)

    assert not options["output"].exists()


def test_signed_earlier_statement_does_not_authorize_the_current_export_contract(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto)
    approved = options["approval_folder"]
    request = read_json(approved / "request.json")
    request["statement"] = (
        "Approvo dati, fonti, frontespizio, decisioni e righi VP della versione "
        "indicata per la preparazione del file XML non firmato, subordinata alle "
        "qualificazioni richieste. Firma telematica e trasmissione restano atti separati."
    )
    raw = request_bytes(request)
    (approved / "request.json").write_bytes(raw)
    sign(raw, approved / "decision.p7s", crypto, "reviewer")

    with pytest.raises(ContractError, match="statement"):
        export_xml(**options)

    assert not options["output"].exists()
    assert not options["registry"].exists()


@pytest.mark.parametrize("value", [0, -1, 100000, True, "7"])
def test_invalid_progressive_is_rejected_before_any_artifact_write(
    tmp_path, crypto, value
):
    options = export_options(tmp_path, crypto)
    options["progressive"] = value

    with pytest.raises(ContractError, match="integer from 1"):
        export_xml(**options)

    assert not options["output"].exists()


def test_same_intermediary_filename_is_not_reused_for_a_second_export(tmp_path, crypto):
    options = export_options(tmp_path, crypto)
    original = export_xml(**options)
    original_xml = (original / "IT11111111115_LI_00007.xml").read_bytes()
    options["output"] = tmp_path / "second"

    with pytest.raises(ContractError, match="already reserved"):
        export_xml(**options)

    assert not options["output"].exists()
    assert (original / "IT11111111115_LI_00007.xml").read_bytes() == original_xml


def test_an_unused_progressive_produces_a_new_file_without_rewriting_prior_export(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto)
    original = export_xml(**options)
    options.update(output=tmp_path / "second", progressive=8)

    second = export_xml(**options)

    assert (second / "IT11111111115_LI_00008.xml").read_bytes() == (
        original / "IT11111111115_LI_00007.xml"
    ).read_bytes()


def test_concurrent_exports_cannot_reserve_the_same_filename(tmp_path, crypto):
    options = export_options(tmp_path, crypto)

    def attempt(name):
        try:
            export_xml(**{**options, "output": tmp_path / name})
            return "EXPORTED"
        except ContractError as exc:
            if "already reserved" not in str(exc):
                raise
            return "DUPLICATE"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("first", "second")))

    assert sorted(results) == ["DUPLICATE", "EXPORTED"]


def test_unrelated_database_is_not_repurposed_as_an_export_registry(tmp_path, crypto):
    options = export_options(tmp_path, crypto)
    with sqlite3.connect(options["registry"]) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('preserve')")

    with pytest.raises(ContractError, match="not a LIPE export registry"):
        export_xml(**options)

    with sqlite3.connect(options["registry"]) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchall() == [
            ("preserve",)
        ]
    assert not options["output"].exists()


def test_registry_cannot_mix_studios_or_real_and_synthetic_data(tmp_path, crypto):
    options = export_options(tmp_path, crypto)
    export_xml(**options)
    options.update(output=tmp_path / "second", progressive=8)
    options["authority"]["policy"]["studio_id"] = "another-studio"

    with pytest.raises(ContractError, match="different studio or data origin"):
        export_xml(**options)

    assert not options["output"].exists()


def test_failed_output_write_consumes_the_reserved_name(tmp_path, crypto, monkeypatch):
    options = export_options(tmp_path, crypto)
    original_writer = lipe_export._write

    def fail_write(path, raw):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(lipe_export, "_write", fail_write)
    with pytest.raises(OSError, match="synthetic disk failure"):
        export_xml(**options)
    with sqlite3.connect(options["registry"]) as registry:
        reservation = json.loads(
            registry.execute("SELECT record FROM exports").fetchone()[0]
        )
    assert reservation["status"] == "RESERVED"
    assert "filing_status" not in reservation
    monkeypatch.setattr(lipe_export, "_write", original_writer)
    options["output"] = tmp_path / "retry"

    with pytest.raises(ContractError, match="already reserved"):
        export_xml(**options)

    assert not options["output"].exists()


def test_serializer_amount_error_is_detected_by_readback_before_reservation(
    tmp_path, crypto, monkeypatch
):
    options = export_options(tmp_path, crypto)
    serialize = lipe_export._serialize

    def changed(*args):
        return change_xml(
            serialize(*args),
            "iv:Comunicazione/iv:DatiContabili/iv:Modulo/iv:ImportoDaVersare",
            "111,00",
        )

    monkeypatch.setattr(lipe_export, "_serialize", changed)

    with pytest.raises(ContractError, match="Serialized VP values"):
        export_xml(**options)

    assert not options["registry"].exists()


def test_artifact_change_during_serialization_invalidates_export(
    tmp_path, crypto, monkeypatch
):
    options = export_options(tmp_path, crypto)
    serialize = lipe_export._serialize

    def changed(*args):
        payload = serialize(*args)
        (options["draft_folder"] / "workpaper.md").write_bytes(
            b"changed during serialization"
        )
        return payload

    monkeypatch.setattr(lipe_export, "_serialize", changed)

    with pytest.raises(ContractError, match="changed during XML serialization"):
        export_xml(**options)

    assert not options["registry"].exists()


@pytest.mark.parametrize("target", ["draft_folder", "approval_folder"])
def test_export_cannot_be_nested_in_existing_evidence(tmp_path, crypto, target):
    options = export_options(tmp_path, crypto)
    options["output"] = options[target] / "new-export"

    with pytest.raises(ContractError, match="separate from the evidence"):
        export_xml(**options)

    assert not options["output"].exists()


def test_identical_xml_fields_do_not_imply_signature_or_filing_acceptance():
    raw = synthetic_xml()

    result = compare_ivp(raw, raw)

    assert result["status"] == "FIELDS_MATCH"
    assert result["amounts_match"] is True
    assert result["bytes_equal"] is True
    assert result["signature_authenticity"] == "NOT_TESTED"
    assert result["filing_acceptance"] == "NOT_ESTABLISHED"
    assert result["reference_authorization"] == "NOT_ESTABLISHED_BY_COMPARISON"


def test_per_period_comparison_detects_offsetting_errors_with_unchanged_quarter_total():
    raw = synthetic_xml()
    root = etree.fromstring(raw)
    modules = root.findall(
        f"{{{IVP}}}Comunicazione/{{{IVP}}}DatiContabili/{{{IVP}}}Modulo"
    )
    modules[0].find(f"{{{IVP}}}IvaEsigibile").text = "221,00"
    modules[1].find(f"{{{IVP}}}IvaEsigibile").text = "219,00"

    result = compare_ivp(raw, etree.tostring(root))

    assert result["status"] == "AMOUNTS_DIFFER"
    assert result["amount_differences"] == [
        {
            "location": "Mese 4",
            "field": "vp4",
            "reference": "220.00",
            "supplied": "221.00",
        },
        {
            "location": "Mese 5",
            "field": "vp4",
            "reference": "220.00",
            "supplied": "219.00",
        },
    ]


def test_explicit_zero_is_numerically_equal_but_its_presence_remains_visible():
    raw = synthetic_xml()
    root = etree.fromstring(raw)
    module = root.find(f"{{{IVP}}}Comunicazione/{{{IVP}}}DatiContabili/{{{IVP}}}Modulo")
    credit = etree.Element(f"{{{IVP}}}IvaCredito")
    credit.text = "0,00"
    module.insert(7, credit)

    result = compare_ivp(raw, etree.tostring(root))

    assert result["status"] == "AMOUNTS_MATCH_REPRESENTATION_DIFFERS"
    assert result["amounts_match"] is True
    assert result["amount_representation_differences"] == [
        {
            "location": "Mese 4",
            "field": "IvaCredito",
            "reference": None,
            "supplied": "0,00",
        }
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("CodiceFiscale", "11111111115"),
        ("AnnoImposta", "2025"),
        ("PartitaIVA", "11111111115"),
    ],
)
def test_different_taxpayer_or_year_prevents_cross_case_amount_comparison(field, value):
    raw = synthetic_xml()
    changed = change_xml(raw, "iv:Comunicazione/iv:Frontespizio/iv:" + field, value)

    result = compare_ivp(raw, changed)

    assert result["status"] == "DIFFERENT_TAXPAYER_OR_YEAR"
    assert result["amounts_match"] is None
    assert result["amount_differences"] == []


def test_different_periods_are_not_compared_by_module_position():
    raw = synthetic_xml()
    changed = change_xml(
        raw, "iv:Comunicazione/iv:DatiContabili/iv:Modulo/iv:Mese", "3"
    )

    result = compare_ivp(raw, changed)

    assert result["status"] == "DIFFERENT_PERIODS"
    assert result["amounts_match"] is None


@pytest.mark.parametrize(
    "mutation", ["duplicate_period", "both_period_kinds", "no_period", "wrong_number"]
)
def test_ambiguous_module_identity_is_rejected_even_when_xsd_allows_it(mutation):
    root = etree.fromstring(synthetic_xml())
    module = root.find(f"{{{IVP}}}Comunicazione/{{{IVP}}}DatiContabili/{{{IVP}}}Modulo")
    if mutation == "duplicate_period":
        module.find(f"{{{IVP}}}Mese").text = "5"
    elif mutation == "both_period_kinds":
        quarter = etree.Element(f"{{{IVP}}}Trimestre")
        quarter.text = "2"
        module.insert(2, quarter)
    elif mutation == "no_period":
        module.remove(module.find(f"{{{IVP}}}Mese"))
    else:
        module.find(f"{{{IVP}}}NumeroModulo").text = "2"

    with pytest.raises(ContractError):
        read_ivp(etree.tostring(root))


def test_software_added_metadata_remains_visible_despite_identical_amounts():
    raw = synthetic_xml()
    root = etree.fromstring(raw)
    front = root.find(f"{{{IVP}}}Comunicazione/{{{IVP}}}Frontespizio")
    etree.SubElement(front, f"{{{IVP}}}IdentificativoProdSoftware").text = (
        "SYNTHETIC SOFTWARE"
    )

    result = compare_ivp(raw, etree.tostring(root))

    assert result["status"] == "AMOUNTS_MATCH_REVIEW_OTHER_FIELDS"
    assert result["other_field_differences"] == [
        {
            "location": "Frontespizio",
            "field": "IdentificativoProdSoftware",
            "reference": None,
            "supplied": "SYNTHETIC SOFTWARE",
        }
    ]


def test_changed_commitment_date_is_not_silently_approved_by_equal_vp_amounts(
    tmp_path, crypto
):
    options = export_options(tmp_path, crypto)
    folder = export_xml(**options)
    raw = (folder / "IT11111111115_LI_00007.xml").read_bytes()
    supplied = change_xml(
        raw, "iv:Comunicazione/iv:Frontespizio/iv:DataImpegno", "02102026"
    )

    result = compare_ivp(raw, supplied)

    assert result["amounts_match"] is True
    assert result["status"] == "AMOUNTS_MATCH_REVIEW_OTHER_FIELDS"
    assert result["other_field_differences"] == [
        {
            "location": "Frontespizio",
            "field": "DataImpegno",
            "reference": "01102026",
            "supplied": "02102026",
        }
    ]


def test_xml_signature_presence_does_not_establish_signature_authenticity():
    from test_lipe_receipt import receipt_tree

    raw = synthetic_xml()
    root = etree.fromstring(raw)
    root.append(
        copy.deepcopy(
            receipt_tree().find("{http://www.w3.org/2000/09/xmldsig#}Signature")
        )
    )

    result = compare_ivp(raw, etree.tostring(root))

    assert result["status"] == "AMOUNTS_MATCH_REVIEW_OTHER_FIELDS"
    assert result["signature_authenticity"] == "NOT_TESTED"
    assert result["other_field_differences"] == [
        {
            "location": "Fornitura",
            "field": "signature_present",
            "reference": False,
            "supplied": True,
        }
    ]


def test_nested_schema_valid_communication_cannot_substitute_signed_object_content():
    from test_lipe_receipt import receipt_tree

    root = etree.fromstring(synthetic_xml())
    signature = copy.deepcopy(
        receipt_tree().find("{http://www.w3.org/2000/09/xmldsig#}Signature")
    )
    obj = etree.SubElement(signature, "{http://www.w3.org/2000/09/xmldsig#}Object")
    obj.append(copy.deepcopy(root))
    root.append(signature)

    with pytest.raises(ContractError, match="Ambiguous nested"):
        read_ivp(etree.tostring(root))


def test_untrusted_software_label_is_escaped_in_readable_comparison(tmp_path):
    case = case_data()
    reference, supplied = tmp_path / "reference.xml", tmp_path / "supplied.xml"
    raw = synthetic_xml()
    root = etree.fromstring(raw)
    front = root.find(f"{{{IVP}}}Comunicazione/{{{IVP}}}Frontespizio")
    etree.SubElement(front, f"{{{IVP}}}IdentificativoProdSoftware").text = (
        "<script> [click](https://example.invalid)"
    )
    reference.write_bytes(raw)
    supplied.write_bytes(etree.tostring(root))

    folder = compare_files(case, reference, supplied, tmp_path / "comparison")

    text = (folder / "comparison.md").read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "[click](https://example.invalid)" not in text
    assert "&lt;script&gt;" in text
    assert (folder / "reference.original").read_bytes() == raw


@pytest.mark.parametrize("match,exit_code", [(True, 0), (False, 2)])
def test_compare_cli_returns_nonzero_for_changed_cents_and_preserves_both_files(
    tmp_path, match, exit_code
):
    reference, supplied = tmp_path / "reference.xml", tmp_path / "supplied.xml"
    raw = synthetic_xml()
    reference.write_bytes(raw)
    supplied.write_bytes(
        raw
        if match
        else change_xml(
            raw, "iv:Comunicazione/iv:DatiContabili/iv:Modulo/iv:IvaEsigibile", "220,01"
        )
    )

    status = main(
        [
            "compare",
            "--case",
            str(PLUGIN / "examples/synthetic-case.json"),
            "--reference",
            str(reference),
            "--supplied",
            str(supplied),
            "--output",
            str(tmp_path / "comparison"),
        ]
    )

    assert status == exit_code
    assert (tmp_path / "comparison/reference.original").read_bytes() == raw
    assert (
        read_json(tmp_path / "comparison/comparison.json")["filing_acceptance"]
        == "NOT_ESTABLISHED"
    )


def test_blocked_supplied_file_is_preserved_with_readable_reason(tmp_path):
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    reference, supplied = tmp_path / "original.xml", tmp_path / "transmitted.p7m"
    reference.write_bytes(synthetic_xml())
    supplied.write_bytes(b"opaque signed container - not XML")

    folder = compare_files(case, reference, supplied, tmp_path / "comparison")

    assert read_json(folder / "comparison.json")["status"] == "BLOCKED"
    assert (
        folder / "supplied.original"
    ).read_bytes() == b"opaque signed container - not XML"
    assert "Lettura bloccata" in (folder / "comparison.md").read_text(encoding="utf-8")


def host_config(tmp_path, options, monkeypatch):
    config = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in options["authority"].items()
    }
    config["export_registry"] = str(tmp_path / "host-export.sqlite3")
    path = tmp_path / "host-policy.json"
    path.write_bytes(request_bytes(config))
    monkeypatch.setenv("VERA_LIPE_AUTHORITY_CONFIG", str(path))
    return path


def test_registry_location_must_come_from_independent_host_configuration(
    tmp_path, crypto, monkeypatch
):
    config = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in crypto["authority"].items()
    }
    path = tmp_path / "host-policy.json"
    config["export_registry"] = str(tmp_path / "client/registry.sqlite3")
    (tmp_path / "client").mkdir()
    path.write_bytes(request_bytes(config))
    monkeypatch.setenv("VERA_LIPE_AUTHORITY_CONFIG", str(path))

    with pytest.raises(ContractError, match="outside client runs"):
        load_export_registry(excluded_roots=[tmp_path / "client"])


def test_missing_registry_configuration_does_not_create_an_arbitrary_new_ledger(
    tmp_path, crypto, monkeypatch
):
    config = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in crypto["authority"].items()
    }
    path = tmp_path / "host-policy.json"
    path.write_bytes(request_bytes(config))
    monkeypatch.setenv("VERA_LIPE_AUTHORITY_CONFIG", str(path))

    with pytest.raises(ContractError, match="has not configured"):
        load_export_registry(excluded_roots=[])


def test_real_cli_exports_from_actual_archive_binding_with_fictional_authority(
    tmp_path, crypto, monkeypatch
):
    case_root = tmp_path / "case"
    case_root.mkdir()
    options, output, context, paths = signed_approval(case_root, crypto, real=True)
    host_config(tmp_path, options, monkeypatch)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT

    monkeypatch.setattr(lipe_export, "datetime", FixedClock)

    status = main(
        [
            "export",
            "--case",
            str(paths["case.json"]),
            "--frontpage",
            str(paths["frontpage.json"]),
            "--draft",
            str(options["draft_folder"]),
            "--approval",
            str(options["approval_folder"]),
            "--client-engagement",
            str(context),
            "--output",
            str(output / "xml"),
            "--progressive",
            "21",
        ]
    )

    assert status == 0
    assert (output / "xml/IT11111111115_LI_00021.xml").is_file()
    report = read_json(output / "xml/export.json")
    assert report["scope"]["data_origin"] == "REAL"
    assert report["filing_status"] == "NOT_SIGNED_OR_TRANSMITTED"


def test_real_cli_rejects_external_export_destination(tmp_path, crypto):
    options, _, context, paths = signed_approval(tmp_path, crypto, real=True)

    with pytest.raises(ContractError, match="selected Archive output"):
        main(
            [
                "export",
                "--case",
                str(paths["case.json"]),
                "--frontpage",
                str(paths["frontpage.json"]),
                "--draft",
                str(options["draft_folder"]),
                "--approval",
                str(options["approval_folder"]),
                "--client-engagement",
                str(context),
                "--output",
                str(tmp_path / "external"),
                "--progressive",
                "21",
            ]
        )

    assert not (tmp_path / "external").exists()

"""Supplied-receipt parsing tests; every receipt and signature here is fictional."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from lxml import etree

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
import lipe_xml
from lipe_core import ContractError, read_json
from lipe_receipt import inspect_receipt, main, preserve_receipt
from lipe_xml import load_official_schema, parse_xml

RECEIPT_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/file/v2.0"
DS = "http://www.w3.org/2000/09/xmldsig#"
SUBMITTED_NAME = "IT12345678903_LI_00001.xml"


def receipt_tree(outcome: str = "ES01"):
    """Create an XSD-shaped receipt with deliberately invalid signature values."""
    root = etree.Element(
        f"{{{RECEIPT_NS}}}EsitoFile", nsmap={"r": RECEIPT_NS, "ds": DS}, versione="2.0"
    )
    for name, value in (
        ("TipoFile", "LI"),
        ("IDFile", "123456789"),
        ("NomeFile", SUBMITTED_NAME),
        ("DataOraRicezione", "2026-10-03T12:00:00+02:00"),
        ("Esito", outcome),
        ("MessageID", "SYNTHETIC-NOT-A-TRANSMISSION"),
    ):
        etree.SubElement(root, name).text = value
    signature = etree.SubElement(root, f"{{{DS}}}Signature")
    signed = etree.SubElement(signature, f"{{{DS}}}SignedInfo")
    etree.SubElement(
        signed,
        f"{{{DS}}}CanonicalizationMethod",
        Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    etree.SubElement(
        signed,
        f"{{{DS}}}SignatureMethod",
        Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
    )
    ref = etree.SubElement(signed, f"{{{DS}}}Reference", URI="")
    etree.SubElement(
        ref,
        f"{{{DS}}}DigestMethod",
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256",
    )
    etree.SubElement(ref, f"{{{DS}}}DigestValue").text = "AA=="
    etree.SubElement(signature, f"{{{DS}}}SignatureValue").text = "AA=="
    return root


def receipt_bytes(outcome: str = "ES01") -> bytes:
    return etree.tostring(receipt_tree(outcome), encoding="UTF-8", xml_declaration=True)


def supplied(tmp_path: Path) -> tuple[dict, Path]:
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    receipt = tmp_path / "synthetic_EL_001.xml"
    receipt.write_bytes(receipt_bytes())
    return case, receipt


@pytest.mark.parametrize(
    "code,label",
    [
        ("ES01", "File validato"),
        ("ES02", "File validato con segnalazione"),
        ("ES03", "File scartato"),
    ],
)
def test_declared_status_never_establishes_filing_or_signature_acceptance(code, label):
    result = inspect_receipt(receipt_bytes(code))

    assert result["schema_validation"] == "PASS"
    assert result["inspection_status"] == "STRUCTURALLY_VALID_UNAUTHENTICATED"
    assert result["declared"]["Esito"] == code
    assert result["declared"]["EsitoDescription"] == label
    assert result["filing_acceptance"] == "NOT_ESTABLISHED"
    assert result["signature"] == {
        "schema_presence": "PASS_STRUCTURE_ONLY",
        "xades_profile": "NOT_TESTED",
        "cryptographic_integrity": "NOT_TESTED",
        "signer_trust_and_revocation": "NOT_TESTED",
    }
    assert result["network_calls"] is False


def test_optional_archive_all_errors_notes_and_local_timestamp_are_preserved():
    root = receipt_tree("ES03")
    root.find("DataOraRicezione").text = "2026-10-03T12:00:00"
    archive = etree.Element("RifArchivio")
    etree.SubElement(archive, "IDArchivio").text = "987654321"
    etree.SubElement(archive, "NomeArchivio").text = "synthetic_archive.zip"
    root.insert(4, archive)
    errors = etree.Element("ListaErrori")
    first, second = etree.SubElement(errors, "Errore"), etree.SubElement(
        errors, "Errore"
    )
    etree.SubElement(first, "Codice").text = "00001"
    etree.SubElement(first, "Descrizione").text = "Errore sintetico uno"
    etree.SubElement(second, "Codice").text = "00002"
    etree.SubElement(second, "Descrizione").text = "Errore sintetico due"
    root.insert(6, errors)
    pec, note = etree.Element("PECMessageID"), etree.Element("Note")
    pec.text, note.text = "synthetic@example.invalid", "Riga uno\nRiga due"
    root.insert(-1, pec)
    root.insert(-1, note)

    result = inspect_receipt(etree.tostring(root))

    assert result["declared"]["RifArchivio"] == {
        "IDArchivio": "987654321",
        "NomeArchivio": "synthetic_archive.zip",
    }
    assert result["declared"]["ListaErrori"] == [
        {"Codice": "00001", "Descrizione": "Errore sintetico uno"},
        {"Codice": "00002", "Descrizione": "Errore sintetico due"},
    ]
    assert result["declared"]["DataOraRicezione"] == "2026-10-03T12:00:00"
    assert result["declared"]["PECMessageID"] == "synthetic@example.invalid"
    assert result["declared"]["Note"] == "Riga uno\nRiga due"


@pytest.mark.parametrize(
    "field,value",
    [
        ("IDFile", "0"),
        ("IDFile", "1000000000000000"),
        ("Esito", "ES00"),
        ("NomeFile", "../other.xml"),
        ("NomeFile", "synthetic_é.xml"),
        ("DataOraRicezione", "yesterday"),
    ],
)
def test_fields_outside_official_contract_block_without_exposing_declared_success(
    field, value
):
    root = receipt_tree()
    root.find(field).text = value

    result = inspect_receipt(etree.tostring(root))

    assert result["inspection_status"] == "BLOCKED"
    assert result["schema_validation"] == "NOT_PASSED"
    assert result["declared"] is None
    assert result["diagnostics"]


@pytest.mark.parametrize("field", ["IDFile", "Esito", f"{{{DS}}}Signature"])
def test_missing_required_field_or_signature_is_rejected(field):
    root = receipt_tree()
    root.remove(root.find(field))

    result = inspect_receipt(etree.tostring(root))

    assert result["inspection_status"] == "BLOCKED"
    assert result["declared"] is None


def test_other_receipt_type_does_not_become_a_lipe_receipt():
    root = receipt_tree()
    root.find("TipoFile").text = "DF"

    result = inspect_receipt(etree.tostring(root))

    assert result["schema_validation"] == "PASS"
    assert result["inspection_status"] == "BLOCKED"
    assert result["declared"] is None


@pytest.mark.parametrize(
    "mutation", ["root_namespace", "qualified_child", "duplicate", "version"]
)
def test_namespace_duplicate_and_version_confusion_is_rejected(mutation):
    root = receipt_tree()
    if mutation == "root_namespace":
        root.tag = "{urn:untrusted}EsitoFile"
    elif mutation == "qualified_child":
        root.find("Esito").tag = f"{{{RECEIPT_NS}}}Esito"
    elif mutation == "duplicate":
        root.insert(5, copy.deepcopy(root.find("Esito")))
    else:
        root.set("versione", "1.0")

    result = inspect_receipt(etree.tostring(root))

    assert result["inspection_status"] == "BLOCKED"
    assert result["declared"] is None


def test_nested_schema_valid_receipt_does_not_select_an_alternative_outcome():
    root = receipt_tree("ES03")
    obj = etree.SubElement(root.find(f"{{{DS}}}Signature"), f"{{{DS}}}Object")
    obj.append(receipt_tree("ES01"))

    result = inspect_receipt(etree.tostring(root))

    assert result["schema_validation"] == "PASS"
    assert result["declared"] is None
    assert result["diagnostics"] == ["Ambiguous nested receipt or signature"]


@pytest.mark.parametrize(
    "doctype",
    [
        '<!DOCTYPE r:EsitoFile SYSTEM "https://example.invalid/never-load.dtd">',
        '<!DOCTYPE r:EsitoFile [<!ENTITY secret SYSTEM "file:///never-read-this-file">]>',
    ],
)
def test_document_types_are_blocked_even_when_no_entity_is_expanded(doctype):
    raw = doctype.encode() + etree.tostring(receipt_tree())

    result = inspect_receipt(raw)

    assert result["declared"] is None
    assert result["diagnostics"] == ["XML document types are not permitted"]


@pytest.mark.parametrize(
    "raw",
    [b"", b"not XML", b"<root>", b"x" * (8 * 1024 * 1024 + 1)],
    ids=["empty", "non-xml-text", "truncated-xml", "over-8-mib"],
)
def test_malformed_empty_and_oversized_xml_cannot_produce_a_status(raw):
    result = inspect_receipt(raw)

    assert result["inspection_status"] == "BLOCKED"
    assert result["declared"] is None


@pytest.mark.parametrize(
    "raw",
    [b"<x>" * 65 + b"</x>" * 65, b"<x>" + b"<y/>" * 10000 + b"</x>"],
    ids=["depth-65", "over-10000-elements"],
)
def test_xml_inspection_limits_bound_depth_and_element_count(raw):
    with pytest.raises(ContractError, match="element or depth"):
        parse_xml(raw)


def test_official_receipt_schema_resolves_its_remote_import_offline_from_escaped_path(
    tmp_path, monkeypatch
):
    install = tmp_path / "install with spaces é #"
    shutil.copytree(PLUGIN / "references/xsd", install / "references/xsd")
    monkeypatch.setattr(lipe_xml, "ROOT", install)

    result = inspect_receipt(receipt_bytes())

    assert result["schema_validation"] == "PASS"


def test_altered_official_receipt_schema_blocks_inspection(tmp_path, monkeypatch):
    shutil.copytree(PLUGIN / "references/xsd", tmp_path / "references/xsd")
    (tmp_path / "references/xsd/receipts/DatiFatturaMessaggi_v2.0.xsd").write_text(
        "untrusted schema", encoding="utf-8"
    )
    monkeypatch.setattr(lipe_xml, "ROOT", tmp_path)

    with pytest.raises(ContractError, match="schema bundle changed"):
        inspect_receipt(receipt_bytes())


def test_unknown_schema_name_is_not_a_path_or_network_request():
    with pytest.raises(ContractError, match="Unknown official"):
        load_official_schema("https://example.invalid/arbitrary.xsd")


@pytest.mark.parametrize(
    "uri",
    ["https://example.invalid/untrusted.xsd", "file://remote-host/share/schema.xsd"],
)
def test_schema_loader_rejects_every_unlisted_dependency_uri(
    tmp_path, monkeypatch, uri
):
    bundle = tmp_path / "references/xsd"
    shutil.copytree(PLUGIN / "references/xsd", bundle)
    path = bundle / "receipts/DatiFatturaMessaggi_v2.0.xsd"
    changed = path.read_bytes().replace(
        lipe_xml.SIGNATURE_SCHEMA_URI.encode(), uri.encode()
    )
    path.write_bytes(changed)
    manifest = read_json(bundle / "manifest.json")
    entry = next(
        item for item in manifest["files"] if item["path"].startswith("receipts/")
    )
    entry["sha256"] = hashlib.sha256(changed).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(lipe_xml, "ROOT", tmp_path)

    # libxml2 may wrap a denied resolver dependency in XMLSchemaParseError.
    with pytest.raises(
        (ContractError, etree.XMLSchemaParseError),
        match="Unexpected XML schema dependency|Failed to parse the XML resource",
    ):
        load_official_schema("RECEIPT")


def test_original_bytes_and_status_survive_later_source_changes(tmp_path):
    case, receipt = supplied(tmp_path)
    original = receipt.read_bytes()

    folder = preserve_receipt(case, receipt, tmp_path / "saved")

    receipt.write_bytes(b"changed after inspection")
    report = read_json(folder / "receipt-inspection.json")
    assert (folder / "receipt.original").read_bytes() == original
    assert report["receipt"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert report["case_association"] == "OPERATOR_SELECTION_NOT_ESTABLISHED_BY_RECEIPT"
    assert (
        report["submitted_file_association"]["filename_check"]
        == "NOT_CHECKED_NO_SUBMITTED_FILE"
    )


@pytest.mark.parametrize(
    "filename,expected",
    [
        (SUBMITTED_NAME, "FILENAME_MATCH_ONLY"),
        ("different.xml", "FILENAME_MISMATCH"),
    ],
)
def test_supplied_file_name_is_compared_without_claiming_content_or_vp_binding(
    tmp_path, filename, expected
):
    case, receipt = supplied(tmp_path)
    submitted = tmp_path / filename
    original = b"An opaque binary or different XML can use exactly the same name."
    submitted.write_bytes(original)

    folder = preserve_receipt(
        case, receipt, tmp_path / "saved", submitted_file=submitted
    )

    report = read_json(folder / "receipt-inspection.json")
    assert report["submitted_file_association"] == {
        "filename_check": expected,
        "content_binding": "NOT_ESTABLISHED",
        "vp_and_frontpage_comparison": "NOT_TESTED",
        "submitted_file_signature": "NOT_TESTED",
    }
    assert (folder / "submitted-file.original").read_bytes() == original
    assert report["submitted_file"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert report["filing_acceptance"] == "NOT_ESTABLISHED"


def test_blocked_receipt_is_preserved_with_reason_and_no_filename_match(tmp_path):
    case, receipt = supplied(tmp_path)
    receipt.write_bytes(b"malformed supplied receipt")
    submitted = tmp_path / SUBMITTED_NAME
    submitted.write_bytes(b"submitted bytes")

    folder = preserve_receipt(
        case, receipt, tmp_path / "saved", submitted_file=submitted
    )

    report = read_json(folder / "receipt-inspection.json")
    assert (folder / "receipt.original").read_bytes() == b"malformed supplied receipt"
    assert report["inspection_status"] == "BLOCKED"
    assert (
        report["submitted_file_association"]["filename_check"]
        == "NOT_CHECKED_BLOCKED_RECEIPT"
    )
    assert "Lettura bloccata" in (folder / "receipt-inspection.md").read_text(
        encoding="utf-8"
    )


def test_receipt_folder_is_never_overwritten(tmp_path):
    case, receipt = supplied(tmp_path)
    output = tmp_path / "saved"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"original evidence")

    with pytest.raises(FileExistsError):
        preserve_receipt(case, receipt, output)

    assert sentinel.read_bytes() == b"original evidence"
    assert not (output / "receipt.original").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not Windows ACLs")
def test_saved_receipt_bytes_and_reports_have_private_posix_modes(tmp_path):
    case, receipt = supplied(tmp_path)

    folder = preserve_receipt(case, receipt, tmp_path / "saved")

    assert folder.stat().st_mode & 0o777 == 0o700
    assert (folder / "receipt.original").stat().st_mode & 0o777 == 0o600
    assert (folder / "receipt-inspection.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "value", [b"", b"x" * (16 * 1024 * 1024 + 1)], ids=["empty", "over-16-mib"]
)
def test_empty_or_excessive_evidence_is_rejected_before_writing(tmp_path, value):
    case, receipt = supplied(tmp_path)
    receipt.write_bytes(value)

    with pytest.raises(ContractError, match="empty or exceeds"):
        preserve_receipt(case, receipt, tmp_path / "saved")

    assert not (tmp_path / "saved").exists()


def test_nonfile_receipt_is_rejected_before_writing(tmp_path):
    case, _ = supplied(tmp_path)

    with pytest.raises(ContractError, match="regular, non-symlink"):
        preserve_receipt(case, tmp_path / "missing.xml", tmp_path / "saved")

    assert not (tmp_path / "saved").exists()


def test_untrusted_note_is_readable_data_not_a_markdown_link_or_html(tmp_path):
    case, receipt = supplied(tmp_path)
    root = receipt_tree()
    note = etree.Element("Note")
    note.text = "L'esito dichiarato: <script>alert(1)</script>\n[approve](https://example.invalid) | # Heading"
    root.insert(-1, note)
    receipt.write_bytes(etree.tostring(root))

    folder = preserve_receipt(case, receipt, tmp_path / "saved")

    text = (folder / "receipt-inspection.md").read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "[approve](https://example.invalid)" not in text
    assert "&lt;script&gt;" in text
    assert "L'esito dichiarato:" in text
    assert (
        read_json(folder / "receipt-inspection.json")["declared"]["Note"] == note.text
    )


@pytest.mark.parametrize(
    "raw,expected",
    [(receipt_bytes("ES03"), 0), (b"malformed", 2)],
    ids=["declared-rejection-is-inspected", "malformed-xml-is-blocked"],
)
def test_cli_exit_code_means_inspection_not_filing_acceptance(tmp_path, raw, expected):
    _, receipt = supplied(tmp_path)
    receipt.write_bytes(raw)
    output = tmp_path / "saved"

    code = main(
        [
            "--case",
            str(PLUGIN / "examples/synthetic-case.json"),
            "--receipt",
            str(receipt),
            "--output",
            str(output),
        ]
    )

    assert code == expected
    assert (
        read_json(output / "receipt-inspection.json")["filing_acceptance"]
        == "NOT_ESTABLISHED"
    )


def test_real_cli_preserves_late_receipt_in_existing_archive_run(tmp_path):
    from test_lipe import archive_case

    context, case_path, output = archive_case(tmp_path)
    receipt = tmp_path / "returned-after-run-start.xml"
    receipt.write_bytes(receipt_bytes())

    code = main(
        [
            "--case",
            str(case_path),
            "--receipt",
            str(receipt),
            "--client-engagement",
            str(context),
            "--output",
            str(output / "receipt-01"),
        ]
    )

    assert code == 0
    report = read_json(output / "receipt-01/receipt-inspection.json")
    assert report["scope"]["data_origin"] == "REAL"
    assert report["scope"]["client_id"] == read_json(case_path)["client_id"]


def test_real_cli_cannot_write_receipt_outside_selected_archive(tmp_path):
    from test_lipe import archive_case

    context, case_path, _ = archive_case(tmp_path)
    receipt = tmp_path / "returned.xml"
    receipt.write_bytes(receipt_bytes())

    with pytest.raises(ContractError, match="selected Archive output"):
        main(
            [
                "--case",
                str(case_path),
                "--receipt",
                str(receipt),
                "--client-engagement",
                str(context),
                "--output",
                str(tmp_path / "external"),
            ]
        )

    assert not (tmp_path / "external").exists()


def test_real_cli_cannot_bypass_missing_archive_context(tmp_path):
    from test_lipe import archive_case

    _, case_path, _ = archive_case(tmp_path)
    receipt = tmp_path / "returned.xml"
    receipt.write_bytes(receipt_bytes())

    with pytest.raises(ContractError, match="Studio Archive"):
        main(
            [
                "--case",
                str(case_path),
                "--receipt",
                str(receipt),
                "--output",
                str(tmp_path / "external"),
            ]
        )

    assert not (tmp_path / "external").exists()

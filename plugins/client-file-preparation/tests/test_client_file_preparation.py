from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.validate_plugin_review_contract import validate_contract

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"

import extract_documents as extraction_module

build_module = importlib.import_module("build_file_preparation_outputs")
scan_module = importlib.import_module("scan_folder")
from build_file_preparation_outputs import build_file_preparation_outputs
from parse_fatturapa_xml import parse_fatturapa_file
from parse_fiscal_forms import FiscalField, write_fiscal_fields_summary
from scan_folder import (
    CATEGORY_CH_GE_TAX,
    CATEGORY_CH_ZH_TAX,
    CATEGORY_CU,
    CATEGORY_F24,
    CATEGORY_FATTURE_XML,
    CATEGORY_UK_HMRC_NOTICE,
    CATEGORY_UK_SELF_ASSESSMENT,
    CATEGORY_UK_YEAR_END_PAYROLL,
    scan_folder,
)

CU_TEXT = (
    "Certificazione Unica 2025. Codice fiscale TSTUSR80A01H501U. "
    "Sostituto d'imposta Fornitore Test SRL. Redditi lavoro dipendente 24.000,00."
)
F24_TEXT = (
    "Modello F24 sezione erario. Codice tributo 4001. Anno riferimento 2025. "
    "Importo a debito versato € 1.234,00."
)
MUTUO_TEXT = (
    "Contratto di mutuo ipotecario stipulato nel 2025 per abitazione principale. "
    "Non contiene una certificazione separata degli oneri."
)
MEDICAL_TEXT = (
    "Ricevuta spese sanitarie farmacia. Codice fiscale TSTUSR80A01H501U. "
    "Importo € 45,90 pagato con carta."
)
NOTICE_TEXT = (
    "Agenzia delle Entrate. Avviso bonario. Protocollo ABC12345. "
    "Data 15/09/2025. Importo richiesto € 200,00."
)
MODEL_730_TEXT = (
    "Modello 730 2025 dichiarazione precompilata. "
    "Codice fiscale TSTUSR80A01H501U. "
    "Importo da rimborsare 850,00. "
    "RC1 redditi lavoro dipendente 24.000,00. "
    "E1 spese sanitarie 450,00."
)
REDDITI_PF_TEXT = (
    "Modello Redditi Persone Fisiche 2025. "
    "Codice fiscale TSTUSR80A01H501U. "
    "Reddito complessivo 30.000,00. Imposta netta 5.000,00. "
    "RN1 30.000,00 RN5 5.000,00 RX1 100,00."
)
GENEVA_TEXT = (
    "Certificat de salaire 2025. Numero AVS 756.1234.5678.97. "
    "Salaire brut CHF 120000.00. Impot anticipe CHF 1500.00."
)
ZURICH_TEXT = (
    "Steuererklarung 2025 Kanton Zurich. "
    "Steuerbares Einkommen CHF 95000.00. Steuerbares Vermogen CHF 250000.00."
)
UK_P60_TEXT = (
    "P60 2025. National Insurance number AB123456C. "
    "Total pay £45,000.00. Tax deducted £8,000.00."
)
UK_SELF_ASSESSMENT_TEXT = (
    "HMRC Self Assessment 2025. UTR 1234567890. Amount due £1,250.00."
)


def _write_invoice_xml(path: Path, date: str = "2025-06-15") -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>Fornitore Test SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <CodiceFiscale>TSTUSR80A01H501U</CodiceFiscale>
        <Anagrafica><Nome>Example</Nome><Cognome>Client</Cognome></Anagrafica>
      </DatiAnagrafici>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
      <DatiGenerali>
        <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{date}</Data><Numero>1</Numero><ImportoTotaleDocumento>122.00</ImportoTotaleDocumento>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Servizio test</Descrizione><PrezzoTotale>100.00</PrezzoTotale></DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>100.00</ImponibileImporto><Imposta>22.00</Imposta></DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</FatturaElettronica>
""",
        encoding="utf-8",
    )


def _write_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                f"{text}"
                "</w:t></w:r></w:p></w:body></w:document>"
            ),
        )


def _write_xlsx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheetData><row r="1">'
                '<c r="A1" t="inlineStr"><is><t>'
                f"{text}"
                "</t></is></c></row></sheetData></worksheet>"
            ),
        )


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js is required to exercise the Client File Preparation MCP server."
        )
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _expected_package_hash(outputs: list[dict[str, object]]) -> str:
    canonical_outputs = sorted(
        (
            {
                "path": output["path"],
                "sha256": output["sha256"],
                "size_bytes": output["size_bytes"],
            }
            for output in outputs
        ),
        key=lambda output: str(output["path"]).encode("utf-8"),
    )
    canonical_bytes = json.dumps(
        canonical_outputs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _load_review_run(
    output_dir: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        json.loads((output_dir / "run_intake.json").read_text(encoding="utf-8")),
        json.loads((output_dir / "review_payload.json").read_text(encoding="utf-8")),
        json.loads((output_dir / "final_artifacts.json").read_text(encoding="utf-8")),
    )


def _call_review_decision_tool(
    tool_name: str,
    *,
    run_intake: dict[str, object],
    review_payload: dict[str, object],
    final_artifacts: dict[str, object],
    decisions: list[dict[str, object]],
    reviewer: str | None = None,
) -> dict[str, object]:
    arguments: dict[str, object] = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "final_artifacts": final_artifacts,
        "decisions": decisions,
    }
    if reviewer is not None:
        arguments["reviewer"] = reviewer
    response = _call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ]
    )[0]
    return response["result"]["structuredContent"]


def _reseal_review_run(output_dir: Path) -> dict[str, object]:
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    for output in final_artifacts["outputs"]:
        output_path = output_dir / output["path"]
        output["size_bytes"] = output_path.stat().st_size
        output["sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
    final_artifacts["integrity"] = {
        "algorithm": "sha256",
        "package_hash_basis": "sorted_outputs_path_size_sha256_canonical_json_v1",
        "package_hash": _expected_package_hash(final_artifacts["outputs"]),
    }
    final_path.write_text(
        json.dumps(final_artifacts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    final_path.chmod(0o600)
    return final_artifacts


def _run_tree_bytes(output_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_scan_folder_classifies_core_document_types(tmp_path: Path) -> None:
    customer = tmp_path / "Example Client" / "2025"
    fatture = customer / "fatture"
    fatture.mkdir(parents=True)
    (customer / "CU_Example_2025.pdf").write_text(CU_TEXT, encoding="utf-8")
    (customer / "F24_giugno.pdf").write_text(F24_TEXT, encoding="utf-8")
    _write_invoice_xml(fatture / "IT01234567890_001.xml")

    records = scan_folder(customer, target_year=2025)

    categories = {record.file_name: record.category for record in records}
    assert categories["CU_Example_2025.pdf"] == CATEGORY_CU
    assert categories["F24_giugno.pdf"] == CATEGORY_F24
    assert categories["IT01234567890_001.xml"] == CATEGORY_FATTURE_XML


def test_scan_folder_classifies_geneva_zurich_and_uk_documents(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "International Client" / "2025"
    customer.mkdir(parents=True)
    (customer / "Geneva_certificat_de_salaire_2025.pdf").write_text(
        GENEVA_TEXT, encoding="utf-8"
    )
    (customer / "Zurich_Steuererklarung_2025.pdf").write_text(
        ZURICH_TEXT, encoding="utf-8"
    )
    (customer / "UK_P60_2025.pdf").write_text(UK_P60_TEXT, encoding="utf-8")
    (customer / "HMRC_Self_Assessment_2025.pdf").write_text(
        UK_SELF_ASSESSMENT_TEXT, encoding="utf-8"
    )
    (customer / "HMRC_tax_code_notice_2025.pdf").write_text(
        "HMRC tax code notice 2025.", encoding="utf-8"
    )

    records = scan_folder(customer, target_year=2025)

    categories = {record.file_name: record.category for record in records}
    assert categories["Geneva_certificat_de_salaire_2025.pdf"] == CATEGORY_CH_GE_TAX
    assert categories["Zurich_Steuererklarung_2025.pdf"] == CATEGORY_CH_ZH_TAX
    assert categories["UK_P60_2025.pdf"] == CATEGORY_UK_YEAR_END_PAYROLL
    assert categories["HMRC_Self_Assessment_2025.pdf"] == CATEGORY_UK_SELF_ASSESSMENT
    assert categories["HMRC_tax_code_notice_2025.pdf"] == CATEGORY_UK_HMRC_NOTICE


def test_parse_fatturapa_file_extracts_formal_invoice_fields(tmp_path: Path) -> None:
    xml_path = tmp_path / "invoice.xml"
    _write_invoice_xml(xml_path)

    record = parse_fatturapa_file(xml_path, base_dir=tmp_path, target_year=2025)

    assert record.supplier_vat == "01234567890"
    assert record.customer_tax_id == "TSTUSR80A01H501U"
    assert record.invoice_date == "2025-06-15"
    assert record.invoice_number == "1"
    assert record.document_type == "TD01"
    assert record.total_amount == "122.00"
    assert record.vat_summary == "aliquota=22.00, imponibile=100.00, imposta=22.00"
    assert record.line_count == 1
    assert record.anomalies == ()


def test_parse_fatturapa_file_rejects_entity_declarations(tmp_path: Path) -> None:
    xml_path = tmp_path / "unsafe-invoice.xml"
    xml_path.write_text(
        "<!DOCTYPE invoice [<!ENTITY payload 'unsafe'>]><invoice>&payload;</invoice>",
        encoding="utf-8",
    )

    record = parse_fatturapa_file(xml_path, base_dir=tmp_path, target_year=2025)

    assert record.malformed is True
    assert record.anomalies == (
        "XML non leggibile: DTD and entity declarations are not allowed",
    )


def test_build_file_preparation_outputs_extracts_geneva_zurich_and_uk_fields(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "Clienti" / "International Client" / "2025"
    customer.mkdir(parents=True)
    (customer / "Geneva_certificat_de_salaire_2025.pdf").write_text(
        GENEVA_TEXT, encoding="utf-8"
    )
    (customer / "Zurich_Steuererklarung_2025.pdf").write_text(
        ZURICH_TEXT, encoding="utf-8"
    )
    (customer / "UK_P60_2025.pdf").write_text(UK_P60_TEXT, encoding="utf-8")
    (customer / "HMRC_Self_Assessment_2025.pdf").write_text(
        UK_SELF_ASSESSMENT_TEXT, encoding="utf-8"
    )

    result = build_file_preparation_outputs(customer, target_year=2025)

    assert result.file_count == 4
    assert result.structured_field_count >= 10
    fiscal_csv = (
        result.output_dir / "extracted" / "structured_fiscal_fields.csv"
    ).read_text(encoding="utf-8")
    assert "salary_gross" in fiscal_csv
    assert "taxable_income" in fiscal_csv
    assert "national_insurance_number_1" in fiscal_csv
    assert "total_pay" in fiscal_csv
    assert "amount_due" in fiscal_csv


def test_build_file_preparation_outputs_writes_expected_files(tmp_path: Path) -> None:
    customer = tmp_path / "Clienti" / "Example Client" / "2025"
    fatture = customer / "fatture"
    fatture.mkdir(parents=True)
    (customer / "CU_Example_2025.pdf").write_text(CU_TEXT, encoding="utf-8")
    (customer / "F24_giugno.pdf").write_text(F24_TEXT, encoding="utf-8")
    (customer / "mutuo_contratto.pdf").write_text(MUTUO_TEXT, encoding="utf-8")
    (customer / "spese_mediche_1.pdf").write_text(MEDICAL_TEXT, encoding="utf-8")
    (customer / "avviso_agenzia.pdf").write_text(NOTICE_TEXT, encoding="utf-8")
    (customer / "Precompilata_730.pdf").write_text(MODEL_730_TEXT, encoding="utf-8")
    (customer / "Redditi_PF_2025.pdf").write_text(REDDITI_PF_TEXT, encoding="utf-8")
    _write_invoice_xml(fatture / "IT01234567890_001.xml")
    _write_invoice_xml(fatture / "IT01234567890_002.xml")

    result = build_file_preparation_outputs(customer, target_year=2025)

    assert result.file_count == 9
    assert result.extracted_count >= 7
    assert result.structured_field_count >= 18
    assert (result.output_dir / "00_fascicolo_index.md").exists()
    assert (result.output_dir / "01_document_inventory.csv").exists()
    assert (result.output_dir / "00_environment_check.md").exists()
    assert (result.output_dir / "extracted" / "documents.jsonl").exists()
    assert (result.output_dir / "03_domande_interne_studio.md").exists()
    assert (result.output_dir / "04_bozza_email_cliente.md").exists()
    assert (result.output_dir / "06_memo_istruttoria.md").exists()
    assert (result.output_dir / "07_scheda_codex_per_studio.md").exists()
    assert (result.output_dir / "08_dati_fiscali_strutturati.md").exists()
    assert (result.output_dir / "run_intake.json").exists()
    assert (result.output_dir / "review_payload.json").exists()
    assert (result.output_dir / "ui_decisions.json").exists()
    assert (result.output_dir / "final_artifacts.json").exists()
    assert (result.output_dir / "extracted" / "structured_fiscal_fields.csv").exists()
    assert (result.output_dir / "extracted" / "structured_fiscal_fields.jsonl").exists()
    assert (result.output_dir / "fatture" / "duplicate_candidates.csv").exists()
    deadlines = (result.output_dir / "avviso" / "deadlines_and_amounts.csv").read_text(
        encoding="utf-8"
    )
    assert "ABC12345" in deadlines
    assert "15/09/2025" in deadlines
    extraction_report = (
        result.output_dir / "extracted" / "extraction_report.md"
    ).read_text(encoding="utf-8")
    assert "CU_Example_2025.pdf" in extraction_report
    memo = (result.output_dir / "06_memo_istruttoria.md").read_text(encoding="utf-8")
    assert "certificazione interessi passivi" in memo
    fiscal_csv = (
        result.output_dir / "extracted" / "structured_fiscal_fields.csv"
    ).read_text(encoding="utf-8")
    assert "importo_debito" in fiscal_csv
    assert "redditi_lavoro_dipendente" in fiscal_csv
    assert "importo_da_rimborsare" in fiscal_csv
    assert "reddito_complessivo" in fiscal_csv
    fiscal_summary = (result.output_dir / "08_dati_fiscali_strutturati.md").read_text(
        encoding="utf-8"
    )
    assert "F24" in fiscal_summary
    assert "CU" in fiscal_summary
    assert "730" in fiscal_summary
    assert "Redditi PF" in fiscal_summary
    email = (result.output_dir / "04_bozza_email_cliente.md").read_text(
        encoding="utf-8"
    )
    assert "Oggetto: Documenti e chiarimenti per completare l'istruttoria" in email
    assert "certificazione degli interessi passivi del mutuo" in email
    assert "spese sanitarie inviate sono complete" in email
    assert "F24 mancanti" in email
    assert "documenti non classificati" not in email

    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    assert run_intake["schema_version"] == "1.0"
    assert run_intake["plugin"] == "client-file-preparation"
    assert run_intake["workflow"] == "client-file-preparation"
    assert run_intake["assumptions"]["target_year"] == 2025
    assert run_intake["assumptions"]["file_count"] == result.file_count
    assert run_intake["data_posture"]["local_files_read"] == [customer.as_posix()]
    assert run_intake["data_posture"]["external_connectors_used"] == []
    assert run_intake["data_posture"]["upload_paths_used"] == []
    source_snapshot = run_intake["source_snapshot"]
    assert source_snapshot["algorithm"] == "sha256"
    assert len(source_snapshot["files"]) == result.file_count
    assert source_snapshot["observed"]["file_count"] == result.file_count
    assert source_snapshot["observed"]["regular_file_count"] == result.file_count
    assert source_snapshot["observed"]["symlink_count"] == 0
    assert source_snapshot["observed"]["total_regular_bytes"] == sum(
        source["size_bytes"] for source in source_snapshot["files"]
    )
    assert source_snapshot["limits"] == {
        "max_entry_count": scan_module.MAX_SOURCE_ENTRIES,
        "max_file_count": scan_module.MAX_SOURCE_FILES,
        "max_file_bytes": scan_module.MAX_SOURCE_FILE_BYTES,
        "max_total_bytes": scan_module.MAX_SOURCE_TOTAL_BYTES,
    }
    assert all(
        source["entry_type"] == "regular_file" and len(source["sha256"]) == 64
        for source in source_snapshot["files"]
    )

    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "client_file_preparation_folder_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {
        "document_inventory",
        "uncertain_file",
        "missing_document_request",
        "extracted_fiscal_field",
        "draft_memo_section",
        "draft_client_email",
    } <= item_types
    assert review_payload["summary"]["file_count"] == result.file_count
    assert review_payload["summary"]["structured_field_count"] == (
        result.structured_field_count
    )
    draft_email_items = [
        item
        for item in review_payload["items"]
        if item["item_type"] == "draft_client_email"
    ]
    assert draft_email_items
    assert "preview" not in draft_email_items[0]["data"]
    studio_brief = next(
        item for item in review_payload["items"] if item["id"] == "draft-studio-brief"
    )
    assert studio_brief["output_path"] == "07_scheda_codex_per_studio.md"
    assert "edit" in studio_brief["allowed_actions"]
    for item in review_payload["items"]:
        if item["item_type"] not in {"draft_memo_section", "draft_client_email"}:
            assert "edit" not in item["allowed_actions"]
    fiscal_items = [
        item
        for item in review_payload["items"]
        if item["item_type"] == "extracted_fiscal_field"
    ]
    assert all("evidence" not in item["data"] for item in fiscal_items)
    assert all(
        evidence.get("kind") != "snippet"
        for item in fiscal_items
        for evidence in item["evidence"]
    )
    assert review_payload["source_paths"] == []
    assert review_payload["preview_policy"] == {
        "mode": "explicit_opt_in",
        "previews_included": False,
    }

    ui_decisions = json.loads(
        (result.output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    assert ui_decisions["decision_source"] == "not_collected"
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decisions"] == []

    final_artifacts = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final_artifacts["run_id"] == run_intake["run_id"]
    assert final_artifacts["status"] == "written_pending_review"
    assert final_artifacts["integrity"]["algorithm"] == "sha256"
    assert all(
        output["size_bytes"] == (result.output_dir / output["path"]).stat().st_size
        and output["sha256"]
        == hashlib.sha256((result.output_dir / output["path"]).read_bytes()).hexdigest()
        for output in final_artifacts["outputs"]
    )
    assert final_artifacts["integrity"]["package_hash"] == _expected_package_hash(
        final_artifacts["outputs"]
    )
    output_paths = {item["path"] for item in final_artifacts["outputs"]}
    assert "review_handoff.md" in output_paths
    assert "04_bozza_email_cliente.md" in output_paths
    assert "06_memo_istruttoria.md" in output_paths
    handoff_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "review_handoff.md"
    )
    handoff_text = (result.output_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "Passaggio alla revisione",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_client_file_preparation_review" in handoff_text
    assert "apply_client_file_preparation_decisions" in handoff_text
    index_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "00_fascicolo_index.md"
    )
    assert "# Indice fascicolo" in index_output["required_text"]
    assert "Anno target: 2025" in index_output["required_text"]
    assert "File analizzati: 9" in index_output["required_text"]
    assert "CU_Example_2025.pdf" in index_output["required_text"]
    inventory_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "01_document_inventory.csv"
    )
    assert inventory_output["row_count"] == result.file_count
    assert inventory_output["required_columns"] == [
        "relative_path",
        "file_name",
        "extension",
        "size_bytes",
        "modified_iso",
        "sha256",
        "category",
        "confidence",
        "years",
        "notes",
    ]
    missing_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "02_documenti_mancanti_o_incerti.md"
    )
    assert "Presente una CU. Confermare con il cliente" in (
        missing_output["required_text"][1]
    )
    email_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "04_bozza_email_cliente.md"
    )
    assert email_output["required_text"] == [
        "Oggetto: Documenti e chiarimenti per completare l'istruttoria",
        "Example Client",
        (
            "confermare che non vi siano altre CU o ulteriori documenti "
            "reddituali non ancora trasmessi;"
        ),
    ]
    memo_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "06_memo_istruttoria.md"
    )
    assert memo_output["required_text"][:6] == [
        "# Memo di istruttoria clienti",
        "Cliente Example Client",
        "Anno 2025",
        "File analizzati: 9.",
        "## Documenti ricevuti",
        "## Elementi mancanti o incerti",
    ]
    assert "Presente una CU. Confermare con il cliente" in (
        memo_output["required_text"][6]
    )
    assert "Il perimetro reddituale del cliente" in memo_output["required_text"][7]
    assert "confermare che non vi siano altre CU" in memo_output["required_text"][8]
    studio_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "07_scheda_codex_per_studio.md"
    )
    assert studio_output["required_text"][:7] == [
        "# Scheda per lo studio",
        "Example Client",
        "2025",
        "## Sintesi del fascicolo",
        "File analizzati: 9",
        f"Campi fiscali strutturati estratti: {result.structured_field_count}",
        "## Punti mancanti o incerti",
    ]
    assert "Presente una CU. Confermare con il cliente" in (
        studio_output["required_text"][7]
    )
    assert "Il perimetro reddituale del cliente" in studio_output["required_text"][8]
    fiscal_fields_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "extracted/structured_fiscal_fields.csv"
    )
    assert fiscal_fields_output["row_count"] == result.structured_field_count
    assert fiscal_fields_output["required_columns"] == [
        "relative_path",
        "file_name",
        "document_kind",
        "field_code",
        "label",
        "value",
        "confidence",
    ]
    fiscal_summary_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "08_dati_fiscali_strutturati.md"
    )
    assert "# Dati fiscali strutturati" in fiscal_summary_output["required_text"]
    assert (
        f"Campi estratti: {result.structured_field_count}"
        in fiscal_summary_output["required_text"]
    )
    assert any(
        fragment.startswith("codice_fiscale")
        for fragment in fiscal_summary_output["required_text"]
    )
    xml_summary_output = next(
        item
        for item in final_artifacts["outputs"]
        if item["path"] == "fatture/fatture_summary.csv"
    )
    assert xml_summary_output["row_count"] == result.xml_count
    assert "invoice_number" in xml_summary_output["required_columns"]
    contract_report = validate_contract(
        result.output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_build_rejects_missing_or_empty_folder_without_creating_output(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "mistyped-client"

    with pytest.raises(NotADirectoryError, match="Cartella non valida"):
        build_file_preparation_outputs(missing)

    assert not missing.exists()

    empty = tmp_path / "empty-client"
    empty.mkdir()

    with pytest.raises(ValueError, match="non contiene file"):
        build_file_preparation_outputs(empty)

    assert not (empty / "out").exists()


def test_build_rejects_nonempty_output_without_mutating_prior_run(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "fresh-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    output_dir = tmp_path / "existing-output"
    output_dir.mkdir()
    stale_path = output_dir / "applied_decisions.json"
    stale_bytes = b'{"run_id":"prior-client"}\n'
    stale_path.write_bytes(stale_bytes)

    with pytest.raises(FileExistsError, match="nuova o vuota"):
        build_file_preparation_outputs(customer, output_dir=output_dir)

    assert stale_path.read_bytes() == stale_bytes
    assert list(output_dir.iterdir()) == [stale_path]


def test_build_rejects_symlinked_output_without_touching_target(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "symlink-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    target_dir = tmp_path / "external-target"
    target_dir.mkdir()
    victim = target_dir / "04_bozza_email_cliente.md"
    victim_bytes = b"external content must remain unchanged\n"
    victim.write_bytes(victim_bytes)
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="link simbolici"):
        build_file_preparation_outputs(customer, output_dir=output_link)

    assert victim.read_bytes() == victim_bytes


def test_build_rejects_output_inside_source_repository(tmp_path: Path) -> None:
    customer = tmp_path / "repository-output-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    protected_output = PLUGIN_ROOT / ".test-client-output-must-not-be-created"

    with pytest.raises(ValueError, match="esterna al repository"):
        build_file_preparation_outputs(
            customer,
            output_dir=protected_output,
        )

    assert not protected_output.exists()


def test_build_rejects_source_file_above_hashing_limit_before_output_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = tmp_path / "oversized-source-client"
    customer.mkdir()
    (customer / "support.txt").write_bytes(b"0123456789")
    output_dir = tmp_path / "oversized-output"
    monkeypatch.setattr(scan_module, "MAX_SOURCE_FILE_BYTES", 8)

    with pytest.raises(ValueError, match="supera il limite di dimensione"):
        build_file_preparation_outputs(customer, output_dir=output_dir)

    assert not output_dir.exists()


def test_build_fails_when_source_changes_after_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = tmp_path / "changing-client"
    customer.mkdir()
    source = customer / "support.txt"
    source.write_text(CU_TEXT, encoding="utf-8")
    output_dir = tmp_path / "changing-output"
    original_writer = build_module._write_studio_synthesis

    def write_then_change_source(*args: object, **kwargs: object) -> object:
        result = original_writer(*args, **kwargs)
        source.write_text(CU_TEXT + " changed", encoding="utf-8")
        return result

    monkeypatch.setattr(
        build_module,
        "_write_studio_synthesis",
        write_then_change_source,
    )

    with pytest.raises(RuntimeError, match="file sorgente è cambiato"):
        build_module.build_file_preparation_outputs(
            customer,
            output_dir=output_dir,
        )

    assert not (output_dir / "final_artifacts.json").exists()


def test_run_id_is_opaque_and_does_not_expose_customer_folder_name(
    tmp_path: Path,
) -> None:
    private_folder_name = "Francesco Giraldo Private Client"
    customer = tmp_path / private_folder_name
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")

    result = build_file_preparation_outputs(customer)

    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert review_payload["run_id"] == run_intake["run_id"]
    assert private_folder_name.casefold() not in review_payload["run_id"].casefold()
    assert "francesco" not in review_payload["run_id"].casefold()


def test_unsupported_high_confidence_file_is_inventory_evidence_but_never_accepted(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "Sensitive Client"
    customer.mkdir()
    (customer / "CU_2025.msg").write_bytes(b"Outlook message placeholder")

    result = build_file_preparation_outputs(customer, target_year=2025)

    evidence = [
        json.loads(line)
        for line in (result.output_dir / "extracted" / "documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(evidence) == 1
    assert evidence[0]["relative_path"] == "CU_2025.msg"
    assert evidence[0]["extraction_method"] == "unsupported_msg"
    assert evidence[0]["readable"] is False
    review_payload_path = result.output_dir / "review_payload.json"
    review_payload = json.loads(review_payload_path.read_text(encoding="utf-8"))
    document_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "document_inventory"
    )
    assert document_item["recommended_action"] == "mark_unclear"
    assert document_item["source_path"] == "CU_2025.msg"
    assert customer.as_posix() not in review_payload_path.read_text(encoding="utf-8")


def test_docx_xlsx_and_eml_are_extracted_locally(tmp_path: Path) -> None:
    customer = tmp_path / "office-files"
    customer.mkdir()
    _write_docx(customer / "CU_2025.docx", CU_TEXT)
    _write_xlsx(customer / "F24_2025.xlsx", F24_TEXT)
    (customer / "documenti_2025.eml").write_text(
        "From: cliente@example.test\n"
        "To: studio@example.test\n"
        "Subject: Documenti fiscali 2025\n"
        "MIME-Version: 1.0\n"
        'Content-Type: multipart/mixed; boundary="boundary-test"\n\n'
        "--boundary-test\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        f"{MEDICAL_TEXT}\n"
        "--boundary-test\n"
        "Content-Type: application/pdf\n"
        'Content-Disposition: attachment; filename="ricevuta.pdf"\n'
        "Content-Transfer-Encoding: base64\n\n"
        "cGRm\n"
        "--boundary-test--\n",
        encoding="utf-8",
    )

    result = build_file_preparation_outputs(customer, target_year=2025)

    evidence = {
        item["file_name"]: item
        for item in (
            json.loads(line)
            for line in (result.output_dir / "extracted" / "documents.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    assert evidence["CU_2025.docx"]["extraction_method"] == "docx_ooxml"
    assert evidence["F24_2025.xlsx"]["extraction_method"] == "xlsx_ooxml"
    assert evidence["documenti_2025.eml"]["extraction_method"] == "eml_stdlib"
    assert evidence["documenti_2025.eml"]["notes"] == ["allegati EML non estratti: 1"]
    assert all(item["readable"] for item in evidence.values())
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    eml_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "document_inventory"
        and item["title"] == "documenti_2025.eml"
    )
    assert eml_item["recommended_action"] == "mark_unclear"


def test_ocr_page_limit_is_recorded_as_a_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = tmp_path / "ocr-client"
    customer.mkdir()
    (customer / "CU_scan_2025.pdf").write_bytes(b"not a text PDF")
    records = scan_folder(customer, target_year=2025)
    monkeypatch.setattr(
        extraction_module,
        "_extract_with_pdfplumber",
        lambda _path, _max_pages: ("", 5, ""),
    )
    monkeypatch.setattr(
        extraction_module,
        "_extract_with_fitz",
        lambda _path, _max_pages: ("", 5, ""),
    )
    monkeypatch.setattr(
        extraction_module,
        "_plain_text_fallback",
        lambda _path: ("", "testo assente"),
    )
    monkeypatch.setattr(
        extraction_module,
        "_render_pdf_pages",
        lambda _path, max_pages: ([object()] * max_pages, 5, ""),
    )
    monkeypatch.setattr(
        extraction_module._PaddleOcrSession,
        "extract",
        lambda _self, _image: (CU_TEXT, ""),
    )

    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "extracted",
        max_pages=2,
    )

    assert evidence[0].readable is True
    assert evidence[0].extraction_method == "paddle_ocr"
    assert "OCR limitato alle prime 2 di 5 pagine" in evidence[0].notes


def test_extraction_never_follows_symbolic_links_outside_customer_folder(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text(
        "External secret that must never enter the customer evidence extraction.",
        encoding="utf-8",
    )
    customer = tmp_path / "customer"
    customer.mkdir()
    (customer / "linked-secret.txt").symlink_to(outside)
    (customer / "linked-secret-copy.txt").symlink_to(outside)

    records = scan_folder(customer, target_year=2025)
    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "extracted",
        enable_ocr=False,
        language="de",
    )

    assert len(records) == 2
    assert all(
        "collegamento simbolico non seguito" in record.notes for record in records
    )
    assert all(record.extraction_method == "unsafe_source_path" for record in evidence)
    assert all(record.readable is False for record in evidence)
    assert all(record.text_path == "" for record in evidence)
    assert "External secret that must never enter" not in (
        tmp_path / "extracted" / "documents.jsonl"
    ).read_text(encoding="utf-8")
    assert "External secret that must never enter" not in (
        tmp_path / "extracted" / "extraction_report.md"
    ).read_text(encoding="utf-8")

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        enable_ocr=False,
    )
    assert (
        len(
            (result.output_dir / "duplicate_candidates.csv")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        == 1
    )


def test_symlink_snapshot_rejects_regular_file_replacement(tmp_path: Path) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("Original external secret.", encoding="utf-8")
    customer = tmp_path / "customer-replacement"
    customer.mkdir()
    source = customer / "linked-secret.txt"
    source.symlink_to(outside)
    records = scan_folder(customer, target_year=2025)

    source.unlink()
    source.write_text("Replacement content must not be extracted.", encoding="utf-8")
    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "replacement-extracted",
        enable_ocr=False,
    )

    assert evidence[0].extraction_method == "unsafe_source_path"
    assert evidence[0].readable is False
    assert "Replacement content must not be extracted" not in (
        tmp_path / "replacement-extracted" / "documents.jsonl"
    ).read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="cambiato tipo"):
        scan_module.verify_source_snapshot(records, customer)


def test_extracted_text_paths_do_not_collide_after_filename_sanitization(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "customer"
    nested = customer / "a"
    nested.mkdir(parents=True)
    first_text = "First document marker. " * 4
    second_text = "Second document marker. " * 4
    (nested / "b.txt").write_text(first_text, encoding="utf-8")
    (customer / "a_b.txt").write_text(second_text, encoding="utf-8")

    records = scan_folder(customer, target_year=2025)
    output_dir = tmp_path / "extracted"
    evidence = extraction_module.extract_documents(
        records,
        customer,
        output_dir,
        enable_ocr=False,
    )

    paths = {record.relative_path: record.text_path for record in evidence}
    assert paths["a/b.txt"] != paths["a_b.txt"]
    assert "First document marker" in (output_dir / paths["a/b.txt"]).read_text(
        encoding="utf-8"
    )
    assert "Second document marker" in (output_dir / paths["a_b.txt"]).read_text(
        encoding="utf-8"
    )


def test_ooxml_rejects_entity_declaration_after_large_leading_prefix(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "customer"
    customer.mkdir()
    path = customer / "unsafe.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            b" " * 5_000
            + b"<!DOCTYPE w:document [<!ENTITY unsafe 'payload'>]>"
            + b"<w:document xmlns:w='urn:test'><w:body><w:p><w:r>"
            + b"<w:t>&unsafe;</w:t></w:r></w:p></w:body></w:document>",
        )

    records = scan_folder(customer)
    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "extracted",
        enable_ocr=False,
        language="de",
    )

    assert evidence[0].extraction_method == "docx_unreadable"
    assert evidence[0].readable is False
    assert any(
        "DTD-/Entity-Deklarationen sind nicht zulässig" in note
        for note in evidence[0].notes
    )


def test_ooxml_rejects_archives_over_the_member_count_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = tmp_path / "customer"
    customer.mkdir()
    path = customer / "oversized-structure.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            "<w:document xmlns:w='urn:test'><w:body/></w:document>",
        )
        archive.writestr("custom/one.xml", "<one/>")
        archive.writestr("custom/two.xml", "<two/>")
    monkeypatch.setattr(extraction_module, "MAX_ARCHIVE_MEMBERS", 2)

    records = scan_folder(customer)
    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "extracted",
        enable_ocr=False,
    )

    assert evidence[0].extraction_method == "docx_unreadable"
    assert any("troppi membri" in note for note in evidence[0].notes)


def test_text_extraction_rejects_files_over_the_configured_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = tmp_path / "customer"
    customer.mkdir()
    (customer / "oversized.txt").write_text("A" * 256, encoding="utf-8")
    monkeypatch.setattr(extraction_module, "MAX_TEXT_BYTES", 64)

    records = scan_folder(customer)
    evidence = extraction_module.extract_documents(
        records,
        customer,
        tmp_path / "extracted",
        enable_ocr=False,
        language="fr",
    )

    assert evidence[0].readable is False
    assert any("dépasse la limite de" in note for note in evidence[0].notes)


def test_short_text_diagnostic_uses_working_language(tmp_path: Path) -> None:
    customer = tmp_path / "short-text-customer"
    customer.mkdir()
    (customer / "short.txt").write_text("x", encoding="utf-8")

    evidence = extraction_module.extract_documents(
        scan_folder(customer),
        customer,
        tmp_path / "short-text-extracted",
        enable_ocr=False,
        language="de",
    )

    assert evidence[0].notes == ("Text fehlt oder ist zu kurz",)


def test_non_italian_generic_xml_is_not_processed_as_fatturapa(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "uk-client"
    customer.mkdir()
    (customer / "generic.xml").write_text(
        "<records><record>UK supporting data</record></records>",
        encoding="utf-8",
    )

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction="uk",
        language="en",
        enable_ocr=False,
    )

    records = scan_folder(customer, jurisdiction="uk")
    assert records[0].category != CATEGORY_FATTURE_XML
    assert (result.output_dir / "extracted" / "fatture_xml.jsonl").read_text(
        encoding="utf-8"
    ) == ""
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert all(
        item["item_type"] != "formal_xml_anomaly" for item in review_payload["items"]
    )


def test_mixed_generic_xml_is_not_misclassified_as_fatturapa(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "mixed-client"
    customer.mkdir()
    (customer / "swiss_export.xml").write_text(
        "<records><record>Geneva supporting data</record></records>",
        encoding="utf-8",
    )

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction="mixed",
        language="fr",
        enable_ocr=False,
    )

    records = scan_folder(customer, jurisdiction="mixed", language="fr")
    assert records[0].category != CATEGORY_FATTURE_XML
    assert "XML generico: struttura FatturaPA non individuata" in records[0].notes
    assert (result.output_dir / "extracted" / "fatture_xml.jsonl").read_text(
        encoding="utf-8"
    ) == ""
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert all(
        item["item_type"] != "formal_xml_anomaly" for item in review_payload["items"]
    )
    anomaly_text = (result.output_dir / "05_anomalie_formali.md").read_text(
        encoding="utf-8"
    )
    assert "structure FatturaPA non identifiée" in anomaly_text


def test_run_scope_records_supported_jurisdiction_language_and_opt_in_previews(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "geneva-client"
    customer.mkdir()
    (customer / "Geneva_tax_2025.txt").write_text(GENEVA_TEXT, encoding="utf-8")

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction="geneva",
        language="fr",
        include_review_previews=True,
    )

    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert run_intake["jurisdiction"] == "geneva"
    assert run_intake["language"] == "fr"
    assert run_intake["assumptions"]["ocr_language"] == "fr"
    assert review_payload["jurisdiction"] == "geneva"
    assert review_payload["language"] == "fr"
    assert review_payload["preview_policy"]["previews_included"] is True
    inventory_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "document_inventory"
    )
    assert inventory_item["data"]["category"] == "documents fiscaux genevois"
    assert any(
        evidence.get("preview")
        for item in review_payload["items"]
        for evidence in item.get("evidence", [])
    )
    assert any(
        evidence.get("kind") == "snippet"
        for item in review_payload["items"]
        if item["item_type"] == "extracted_fiscal_field"
        for evidence in item.get("evidence", [])
    )
    for draft_id in ("draft-studio-brief", "draft-memo", "draft-client-email"):
        draft = next(item for item in review_payload["items"] if item["id"] == draft_id)
        assert draft["data"]["preview"]


@pytest.mark.parametrize(
    ("language", "jurisdiction", "expected"),
    [
        (
            "it",
            "italy",
            {
                "index": "# Indice fascicolo",
                "memo": "# Memo di istruttoria clienti",
                "email": "Oggetto: Documenti e chiarimenti per completare l'istruttoria",
                "limits": "## Limiti della lettura",
                "handoff": "Passaggio alla revisione",
                "column": "Azione suggerita",
                "fiscal_title": "# Dati fiscali strutturati",
                "fiscal_count": "- Campi estratti: 0",
                "fiscal_limit": "Ogni valore va verificato sul documento originale",
                "fiscal_empty": "Nessun campo fiscale strutturato estratto",
                "anomalies": "# Anomalie formali",
                "xml_anomalies": "# Anomalie formali e-fattura XML",
                "confidence": "bassa",
                "posture_note": "Gli script esaminano localmente",
            },
        ),
        (
            "en",
            "uk",
            {
                "index": "# Client file index",
                "memo": "# Client file-preparation memo",
                "email": "Subject: Documents and clarifications needed to complete file preparation",
                "limits": "## Reading limitations",
                "handoff": "Review handoff",
                "column": "Suggested action",
                "fiscal_title": "# Structured fiscal data",
                "fiscal_count": "- Extracted fields: 0",
                "fiscal_limit": "Verify every value against the original document",
                "fiscal_empty": "No structured fiscal fields were extracted",
                "anomalies": "# Formal anomalies",
                "xml_anomalies": "# Formal electronic-invoice XML anomalies",
                "confidence": "low",
                "posture_note": "Scripts inspect local customer-folder files",
            },
        ),
        (
            "fr",
            "geneva",
            {
                "index": "# Index du dossier client",
                "memo": "# Note de préparation du dossier client",
                "email": "Objet : Documents et précisions nécessaires pour compléter le dossier",
                "limits": "## Limites de lecture",
                "handoff": "Passage à la revue",
                "column": "Action suggérée",
                "fiscal_title": "# Données fiscales structurées",
                "fiscal_count": "- Champs extraits: 0",
                "fiscal_limit": "Chaque valeur doit être vérifiée",
                "fiscal_empty": "Aucun champ fiscal structuré n’a été extrait",
                "anomalies": "# Anomalies formelles",
                "xml_anomalies": "# Anomalies formelles des factures électroniques XML",
                "confidence": "faible",
                "posture_note": "Les scripts examinent localement",
            },
        ),
        (
            "de",
            "zurich",
            {
                "index": "# Index der Mandantenakte",
                "memo": "# Arbeitsvermerk zur Mandantenakte",
                "email": "Betreff: Unterlagen und Angaben zur Vervollständigung der Akte",
                "limits": "## Grenzen der Auslesung",
                "handoff": "Übergabe zur Prüfung",
                "column": "Empfohlene Aktion",
                "fiscal_title": "# Strukturierte Steuerdaten",
                "fiscal_count": "- Extrahierte Felder: 0",
                "fiscal_limit": "Jeder Wert muss vor der operativen Verwendung",
                "fiscal_empty": "keine strukturierten Steuerfelder extrahiert",
                "anomalies": "# Formale Anomalien",
                "xml_anomalies": "# Formale Anomalien in E-Rechnungs-XML",
                "confidence": "niedrig",
                "posture_note": "Die Skripte prüfen die Dateien",
            },
        ),
    ],
)
def test_language_controls_user_facing_run_outputs(
    tmp_path: Path,
    language: str,
    jurisdiction: str,
    expected: dict[str, str],
) -> None:
    customer = tmp_path / f"client-{language}"
    customer.mkdir()
    (customer / "supporting_document_2025.txt").write_text(
        "General supporting document for the 2025 client file. "
        "This content is intentionally long enough for local extraction.",
        encoding="utf-8",
    )

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction=jurisdiction,
        language=language,
    )

    assert expected["index"] in (result.output_dir / "00_fascicolo_index.md").read_text(
        encoding="utf-8"
    )
    assert expected["memo"] in (result.output_dir / "06_memo_istruttoria.md").read_text(
        encoding="utf-8"
    )
    email_text = (result.output_dir / "04_bozza_email_cliente.md").read_text(
        encoding="utf-8"
    )
    assert expected["email"] in email_text
    if language != "it":
        assert "Bozza email cliente" not in email_text
        assert "Nessuna richiesta cliente generata automaticamente" not in email_text
    assert expected["limits"] in (
        result.output_dir / "07_scheda_codex_per_studio.md"
    ).read_text(encoding="utf-8")
    assert expected["anomalies"] in (
        result.output_dir / "05_anomalie_formali.md"
    ).read_text(encoding="utf-8")
    assert expected["xml_anomalies"] in (
        result.output_dir / "fatture" / "formal_anomalies.md"
    ).read_text(encoding="utf-8")
    assert expected["handoff"] in (result.output_dir / "review_handoff.md").read_text(
        encoding="utf-8"
    )
    fiscal_summary = (result.output_dir / "08_dati_fiscali_strutturati.md").read_text(
        encoding="utf-8"
    )
    assert expected["fiscal_title"] in fiscal_summary
    assert expected["fiscal_count"] in fiscal_summary
    assert expected["fiscal_limit"] in fiscal_summary
    assert expected["fiscal_empty"] in fiscal_summary
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    assert expected["column"] in {
        column["label"] for column in review_payload["columns"]
    }
    assert review_payload["language"] == language
    uncertain_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "uncertain_file"
    )
    assert uncertain_item["data"]["confidence"] == expected["confidence"]
    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    assert any(
        expected["posture_note"] in note for note in run_intake["data_posture"]["notes"]
    )
    final_artifacts = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    fiscal_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "08_dati_fiscali_strutturati.md"
    )
    assert expected["fiscal_title"] in fiscal_output["required_text"]
    assert expected["fiscal_count"].removeprefix("- ") in fiscal_output["required_text"]


@pytest.mark.parametrize(
    ("language", "expected_title", "expected_dates"),
    [
        (
            "it",
            "# Avviso / comunicazione - scheda di prima lettura",
            "Date individuate",
        ),
        ("en", "# Notice / communication - initial reading sheet", "Dates identified"),
        ("fr", "# Avis / communication - fiche de première lecture", "Dates relevées"),
        ("de", "# Bescheid / Mitteilung - Erstprüfungsblatt", "Erkannte Daten"),
    ],
)
def test_notice_artifact_follows_working_language(
    tmp_path: Path,
    language: str,
    expected_title: str,
    expected_dates: str,
) -> None:
    customer = tmp_path / f"notice-{language}"
    customer.mkdir()
    (customer / "Agenzia_avviso_2025.txt").write_text(
        NOTICE_TEXT,
        encoding="utf-8",
    )

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction="italy",
        language=language,
    )

    notice = (result.output_dir / "avviso" / "avviso_intake_memo.md").read_text(
        encoding="utf-8"
    )
    assert expected_title in notice
    assert expected_dates in notice


@pytest.mark.parametrize(
    ("language", "label", "confidence", "warning"),
    [
        (
            "it",
            "Codice fiscale individuato",
            "alta",
            "campo da verificare su layout originale",
        ),
        (
            "en",
            "Tax code identified",
            "high",
            "field to verify against the original layout",
        ),
        (
            "fr",
            "Code fiscal identifié",
            "élevée",
            "champ à vérifier dans la mise en page originale",
        ),
        (
            "de",
            "Ermittelte italienische Steuernummer",
            "hoch",
            "Feld anhand des Originallayouts prüfen",
        ),
    ],
)
def test_fiscal_summary_localizes_display_text_without_changing_structured_data(
    tmp_path: Path,
    language: str,
    label: str,
    confidence: str,
    warning: str,
) -> None:
    field = FiscalField(
        relative_path="CU_2025.pdf",
        file_name="CU_2025.pdf",
        document_kind="CU",
        section="identificativi",
        field_code="codice_fiscale_1",
        label="Codice fiscale individuato",
        value="TSTUSR80A01H501U",
        normalized_value="TSTUSR80A01H501U",
        value_type="text",
        confidence="alta",
        evidence="Codice fiscale TSTUSR80A01H501U",
        warnings=("campo da verificare su layout originale",),
    )
    output_path = tmp_path / f"fiscal-summary-{language}.md"

    write_fiscal_fields_summary([field], output_path, language=language)

    summary = output_path.read_text(encoding="utf-8")
    assert f"- {label} (`codice_fiscale_1`): TSTUSR80A01H501U [{confidence}]" in summary
    assert warning in summary
    assert field.field_code == "codice_fiscale_1"
    assert field.normalized_value == "TSTUSR80A01H501U"


def test_selected_jurisdiction_gates_italian_completeness_requests(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "uk-client"
    customer.mkdir()
    (customer / "CU_2025.txt").write_text(CU_TEXT, encoding="utf-8")

    result = build_file_preparation_outputs(
        customer,
        target_year=2025,
        jurisdiction="uk",
        language="en",
    )

    missing_text = (result.output_dir / "02_documenti_mancanti_o_incerti.md").read_text(
        encoding="utf-8"
    )
    email_text = (result.output_dir / "04_bozza_email_cliente.md").read_text(
        encoding="utf-8"
    )
    assert "Check document completeness against the jurisdiction" in missing_text
    assert "confirm that there are no other CUs" not in email_text
    assert "confermare che non vi siano altre CU" not in email_text


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("jurisdiction", "canada", "Giurisdizione non supportata"),
        ("language", "es", "Lingua non supportata"),
    ],
)
def test_build_rejects_unsupported_scope_values(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    customer = tmp_path / f"client-{field}"
    customer.mkdir()
    (customer / "document.txt").write_text(CU_TEXT, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_file_preparation_outputs(customer, **{field: value})


def test_client_file_preparation_mcp_server_validates_and_renders_review_payload() -> (
    None
):
    run_intake = {
        "run_id": "client-file-preparation-test-run",
        "output_dir": "/private/customer/output",
        "input_paths": ["/private/customer"],
        "data_posture": {"local_files_read": ["/private/customer"]},
        "assumptions": {"client_name": "Private Client", "file_count": 1},
        "execution_trace": [
            {
                "command": ["python", "/private/customer/run.py"],
                "inputs": ["/private/customer/document.pdf"],
            }
        ],
    }
    review_payload = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": "client-file-preparation-test-run",
        "review_type": "client_file_preparation_folder_review",
        "items": [
            {
                "id": "document-1",
                "item_type": "document_inventory",
                "title": "CU_Example_2025.pdf",
                "source_path": "/tmp/CU_Example_2025.pdf",
                "output_path": None,
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [],
                "data": {"category": "CU", "confidence": "alta"},
                "status": "needs_review",
            },
            {
                "id": "draft-client-email",
                "item_type": "draft_client_email",
                "title": "Bozza email cliente",
                "source_path": None,
                "output_path": "04_bozza_email_cliente.md",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [],
                "data": {"preview": "Gentile cliente, inviare la CU mancante."},
                "status": "needs_review",
            },
        ],
        "item_count": 2,
        "columns": [],
        "evidence": {},
        "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
        "status": "ready_for_review",
        "summary": {"file_count": 1, "missing_document_count": 1},
    }
    private_required_text = "Private Client must send the confidential source"
    final_artifacts = {
        "outputs": [
            {
                "path": "04_bozza_email_cliente.md",
                "size_bytes": 123,
                "sha256": "0" * 64,
                "qa_checks": ["nonempty_text", "required_text"],
                "required_text": [private_required_text],
            }
        ]
    }
    nonpersistent_render_intake = dict(run_intake)
    nonpersistent_render_intake.pop("output_dir")
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_client_file_preparation_review",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_client_file_preparation_review",
                "arguments": {
                    "run_intake": nonpersistent_render_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                },
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/client-file-preparation-review.html"},
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert (
        render_result["structuredContent"]["widget_type"]
        == "client_file_preparation_review"
    )
    assert "output_dir" not in render_result["structuredContent"]["run_intake"]
    assert render_result["structuredContent"]["run_intake"]["input_paths"] == []
    assert (
        render_result["structuredContent"]["run_intake"]["data_posture"][
            "local_files_read"
        ]
        == []
    )
    sanitized_intake = render_result["structuredContent"]["run_intake"]
    assert "client_name" not in sanitized_intake["assumptions"]
    assert sanitized_intake["execution_trace"][0]["inputs"] == ["<local-path>"]
    assert sanitized_intake["execution_trace"][0]["command"] == [
        "python",
        "<local-path>",
    ]
    rendered_artifacts = render_result["structuredContent"]["final_artifacts"]
    assert rendered_artifacts["outputs"][0]["qa_checks"] == [
        "nonempty_text",
        "required_text",
    ]
    assert "required_text" not in rendered_artifacts["outputs"][0]
    assert private_required_text not in json.dumps(render_result)
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/client-file-preparation-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/client-file-preparation-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "New Client · File Preparation" in widget_html


def test_client_file_preparation_hosted_mcp_render_save_apply_is_path_private(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "hosted-path-private-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    private_required_text = [
        text
        for output in final_artifacts["outputs"]
        for text in output.get("required_text", [])
    ]
    assert private_required_text
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review_payload["items"]
    ]
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js is required to exercise the Client File Preparation MCP server."
        )
    process = subprocess.Popen(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def call_tool(
        request_id: int,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                }
            )
            + "\n"
        )
        process.stdin.flush()
        response_line = process.stdout.readline()
        assert response_line, "Client File Preparation MCP server closed unexpectedly"
        return json.loads(response_line)

    try:
        render_response = call_tool(
            1,
            "render_client_file_preparation_review",
            {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
            },
        )
        rendered = render_response["result"]["structuredContent"]
        persistence_token = rendered["decision_policy"]["persistence_token"]
        assert rendered["decision_policy"]["can_persist"] is True
        assert len(persistence_token) == 43
        assert "output_dir" not in rendered["run_intake"]
        assert result.output_dir.as_posix() not in json.dumps(render_response)
        assert customer.as_posix() not in json.dumps(render_response)

        initial_ui_bytes = (result.output_dir / "ui_decisions.json").read_bytes()
        rejected_response = call_tool(
            2,
            "save_client_file_preparation_decisions",
            {
                "run_intake": rendered["run_intake"],
                "persistence_token": "x" * 43,
                "review_payload": rendered["review_payload"],
                "decisions": [],
            },
        )
        rejected = rejected_response["result"]["structuredContent"]
        assert rejected["ok"] is False
        assert "unknown or expired" in rejected["error"]
        assert (
            result.output_dir / "ui_decisions.json"
        ).read_bytes() == initial_ui_bytes

        save_response = call_tool(
            3,
            "save_client_file_preparation_decisions",
            {
                "run_intake": rendered["run_intake"],
                "persistence_token": persistence_token,
                "review_payload": rendered["review_payload"],
                "ui_decisions": rendered["ui_decisions"],
                "decisions": decisions,
                "decision_source": "hosted_mcp_test",
                "reviewer": "reviewer-hosted-01",
            },
        )
        saved = save_response["result"]["structuredContent"]
        assert saved["ok"] is True
        assert saved["persisted"] is True
        assert saved["ui_decisions_path"] == "ui_decisions.json"
        assert "final_artifacts" not in saved

        apply_response = call_tool(
            4,
            "apply_client_file_preparation_decisions",
            {
                "run_intake": rendered["run_intake"],
                "persistence_token": persistence_token,
                "review_payload": rendered["review_payload"],
                "ui_decisions": saved["ui_decisions"],
                "decisions": decisions,
                "decision_source": "hosted_mcp_test",
                "reviewer": "reviewer-hosted-01",
            },
        )
        applied = apply_response["result"]["structuredContent"]
        assert applied["ok"] is True
        assert applied["persisted"] is True
        assert applied["application_status"] == "final_ready"
        assert applied["ui_decisions_path"] == "ui_decisions.json"
        assert applied["applied_decisions_path"] == "applied_decisions.json"
        assert applied["final_artifacts_path"] == "final_artifacts.json"
        assert applied["run_intake_path"] == "run_intake.json"
        assert all(
            "required_text" not in output
            for output in applied["final_artifacts"]["outputs"]
        )
        browser_results = json.dumps(
            [render_response, save_response, apply_response],
            ensure_ascii=False,
        )
        assert result.output_dir.as_posix() not in browser_results
        assert customer.as_posix() not in browser_results
        assert "Hosted Path Private Client" not in browser_results
        persisted_final_artifacts = json.loads(
            (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
        )
        assert any(
            output.get("required_text")
            for output in persisted_final_artifacts["outputs"]
        )
    finally:
        if process.stdin is not None:
            process.stdin.close()
        return_code = process.wait(timeout=10)
        stderr = process.stderr.read() if process.stderr is not None else ""
        assert return_code == 0, stderr

    written_ui = json.loads(
        (result.output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    written_applied = json.loads(
        (result.output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    written_final = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert written_ui["status"] == "reviewed"
    assert written_applied["application_status"] == "final_ready"
    assert written_final["review_status"] == "final_ready"


def test_client_file_preparation_mcp_apply_updates_draft_email_artifact(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "apply-email-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    output_dir = result.output_dir
    draft_email_path = output_dir / "04_bozza_email_cliente.md"
    original_email = draft_email_path.read_text(encoding="utf-8")
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    edited_email = (
        original_email.rstrip()
        + "\n\nNota di revisione: verificare anche la certificazione del mutuo.\n"
    )
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "apply_client_file_preparation_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "reviewer": "reviewer-email-01",
                    "decisions": [
                        (
                            {
                                "item_id": item["id"],
                                "action": "edit",
                                "edit_value": edited_email,
                                "reviewer_note": "Rewrite the client request.",
                            }
                            if item["id"] == "draft-client-email"
                            else {"item_id": item["id"], "action": "accept"}
                        )
                        for item in review_payload["items"]
                    ],
                },
            },
        }
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    payload = responses[1]["result"]["structuredContent"]
    assert payload["ok"] is True
    assert payload["target_update_count"] == 1
    assert payload["application_status"] == "final_ready"
    assert draft_email_path.read_text(encoding="utf-8") == edited_email.rstrip()
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    email_effect = next(
        effect
        for effect in applied["effects"]
        if effect["item_id"] == "draft-client-email"
    )
    assert email_effect["artifact_update"] == "target_artifact_updated"
    assert email_effect["target_artifact"] == "04_bozza_email_cliente.md"
    assert applied["target_update_paths"] == ["04_bozza_email_cliente.md"]
    backup_path = output_dir / applied["original_backup_paths"][0]
    assert backup_path.read_text(encoding="utf-8") == original_email
    updated_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert updated_final["review_status"] == "final_ready"
    assert updated_final["review_application"]["target_update_paths"] == [
        "04_bozza_email_cliente.md"
    ]
    assert any(
        "galleria verificata" in action for action in updated_final["next_actions"]
    )
    email_output = next(
        output
        for output in updated_final["outputs"]
        if output["path"] == "04_bozza_email_cliente.md"
    )
    assert email_output["status"] == "updated_from_review"


def test_client_file_preparation_mcp_rejects_edit_that_breaks_declared_qa(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "invalid-email-edit-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    before = _run_tree_bytes(result.output_dir)
    decisions = [
        (
            {
                "item_id": item["id"],
                "action": "edit",
                "edit_value": "This replacement omits the required document structure.",
            }
            if item["id"] == "draft-client-email"
            else {"item_id": item["id"], "action": "accept"}
        )
        for item in review_payload["items"]
    ]

    payload = _call_review_decision_tool(
        "apply_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=decisions,
        reviewer="reviewer-qa-01",
    )

    assert payload["ok"] is False
    assert "artifact QA failed required_text" in payload["error"]
    assert _run_tree_bytes(result.output_dir) == before


def test_client_file_preparation_mcp_save_reseals_generated_package(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "save-reseal-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )

    responses = _call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "save_client_file_preparation_decisions",
                    "arguments": {
                        "run_intake": run_intake,
                        "review_payload": review_payload,
                        "final_artifacts": final_artifacts,
                        "decisions": [
                            {
                                "item_id": review_payload["items"][0]["id"],
                                "action": "accept",
                            }
                        ],
                    },
                },
            }
        ]
    )

    assert responses[0]["result"]["structuredContent"]["ok"] is True
    updated = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    ui_output = next(
        output for output in updated["outputs"] if output["path"] == "ui_decisions.json"
    )
    ui_path = result.output_dir / "ui_decisions.json"
    assert ui_output["sha256"] == hashlib.sha256(ui_path.read_bytes()).hexdigest()
    assert updated["integrity"]["package_hash"] == _expected_package_hash(
        updated["outputs"]
    )


def test_client_file_preparation_mcp_apply_rejects_tampered_generated_artifact(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "tamper-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    email_path = result.output_dir / "04_bozza_email_cliente.md"
    original_email = email_path.read_text(encoding="utf-8")
    email_path.write_text(f"X{original_email[1:]}", encoding="utf-8")

    responses = _call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "apply_client_file_preparation_decisions",
                    "arguments": {
                        "run_intake": run_intake,
                        "review_payload": review_payload,
                        "final_artifacts": final_artifacts,
                        "decisions": [
                            {
                                "item_id": review_payload["items"][0]["id"],
                                "action": "accept",
                            }
                        ],
                    },
                },
            }
        ]
    )

    payload = responses[0]["result"]["structuredContent"]
    assert payload["ok"] is False
    assert "sha256 mismatch: 04_bozza_email_cliente.md" in payload["error"]
    assert not (result.output_dir / "applied_decisions.json").exists()


def test_client_file_preparation_mcp_apply_reseals_generated_package(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "reseal-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake = json.loads(
        (result.output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (result.output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    decisions = [
        {"item_id": item["id"], "action": "accept"}
        for item in review_payload["items"]
        if "accept" in item["allowed_actions"]
    ]

    responses = _call_mcp_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "apply_client_file_preparation_decisions",
                    "arguments": {
                        "run_intake": run_intake,
                        "review_payload": review_payload,
                        "final_artifacts": final_artifacts,
                        "reviewer": "reviewer-reseal-01",
                        "decisions": decisions,
                    },
                },
            }
        ]
    )

    payload = responses[0]["result"]["structuredContent"]
    assert payload["ok"] is True
    updated = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    output_paths = {output["path"] for output in updated["outputs"]}
    assert {"run_intake.json", "ui_decisions.json", "applied_decisions.json"} <= (
        output_paths
    )
    for output in updated["outputs"]:
        output_path = result.output_dir / output["path"]
        assert output["size_bytes"] == output_path.stat().st_size
        assert output["sha256"] == hashlib.sha256(output_path.read_bytes()).hexdigest()
    assert updated["integrity"]["package_hash"] == _expected_package_hash(
        updated["outputs"]
    )


def test_generated_review_run_is_owner_only(tmp_path: Path) -> None:
    customer = tmp_path / "private-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")

    result = build_file_preparation_outputs(customer, target_year=2025)

    assert result.output_dir.stat().st_mode & 0o777 == 0o700
    for path in result.output_dir.rglob("*"):
        expected_mode = 0o700 if path.is_dir() else 0o600
        assert path.stat().st_mode & 0o777 == expected_mode


def test_mcp_save_rejects_missing_integrity_without_writing(tmp_path: Path) -> None:
    customer = tmp_path / "missing-integrity-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    before = _run_tree_bytes(result.output_dir)
    final_artifacts.pop("integrity")
    final_path = result.output_dir / "final_artifacts.json"
    final_path.write_text(
        json.dumps(final_artifacts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    expected_after_fixture_change = _run_tree_bytes(result.output_dir)

    payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=[],
    )

    assert payload["ok"] is False
    assert "final_artifacts.integrity is required" in payload["error"]
    assert _run_tree_bytes(result.output_dir) == expected_after_fixture_change
    assert (
        before["ui_decisions.json"]
        == expected_after_fixture_change["ui_decisions.json"]
    )


def test_mcp_save_rejects_stale_manifest_argument(tmp_path: Path) -> None:
    customer = tmp_path / "stale-manifest-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, stale_final = _load_review_run(result.output_dir)
    current_final = json.loads(json.dumps(stale_final))
    current_final["next_actions"].append("A newer local manifest state.")
    final_path = result.output_dir / "final_artifacts.json"
    final_path.write_text(
        json.dumps(current_final, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    before = _run_tree_bytes(result.output_dir)

    payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=stale_final,
        decisions=[],
    )

    assert payload["ok"] is False
    assert "stale" in payload["error"]
    assert _run_tree_bytes(result.output_dir) == before


def test_mcp_persistence_rejects_protected_and_non_owner_only_output_dirs(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "unsafe-output-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)

    protected_intake = dict(run_intake)
    protected_intake["output_dir"] = PLUGIN_ROOT.as_posix()
    protected_payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=protected_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=[],
    )
    assert protected_payload["ok"] is False
    assert (
        "outside the plugin package and source repository" in protected_payload["error"]
    )

    result.output_dir.chmod(0o755)
    non_owner_payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=[],
    )
    assert non_owner_payload["ok"] is False
    assert "owner-only (mode 0700)" in non_owner_payload["error"]


def test_mcp_save_rejects_symlinked_run_output(tmp_path: Path) -> None:
    customer = tmp_path / "symlink-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    email_path = result.output_dir / "04_bozza_email_cliente.md"
    real_email_path = result.output_dir / "email-bytes.md"
    email_path.rename(real_email_path)
    email_path.symlink_to(real_email_path.name)

    payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=[],
    )

    assert payload["ok"] is False
    assert "symbolic links" in payload["error"]
    assert email_path.is_symlink()


def test_mcp_save_binds_caller_review_to_sealed_run_payload(tmp_path: Path) -> None:
    customer = tmp_path / "review-binding-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    changed_review = json.loads(json.dumps(review_payload))
    changed_review["items"][0]["title"] = "Different caller-provided item title"
    before = _run_tree_bytes(result.output_dir)

    payload = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=changed_review,
        final_artifacts=final_artifacts,
        decisions=[],
    )

    assert payload["ok"] is False
    assert "canonical hash" in payload["error"]
    assert _run_tree_bytes(result.output_dir) == before


def test_mcp_final_ready_requires_stable_pseudonymous_reviewer(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "reviewer-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    decisions = [
        {"item_id": item["id"], "action": "accept"} for item in review_payload["items"]
    ]
    before = _run_tree_bytes(result.output_dir)

    missing_reviewer = _call_review_decision_tool(
        "apply_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=decisions,
    )

    assert missing_reviewer["ok"] is False
    assert "stable pseudonymous alias" in missing_reviewer["error"]
    assert _run_tree_bytes(result.output_dir) == before

    saved = _call_review_decision_tool(
        "save_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=decisions[:1],
        reviewer="reviewer-stable-01",
    )
    assert saved["ok"] is True
    current_final = json.loads(
        (result.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    changed_reviewer = _call_review_decision_tool(
        "apply_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=current_final,
        decisions=decisions,
        reviewer="reviewer-other-02",
    )
    assert changed_reviewer["ok"] is False
    assert "must remain stable" in changed_reviewer["error"]


def test_mcp_skip_is_blocked_not_final_ready(tmp_path: Path) -> None:
    customer = tmp_path / "skip-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, final_artifacts = _load_review_run(result.output_dir)
    skipped_id = next(
        item["id"]
        for item in review_payload["items"]
        if "skip" in item["allowed_actions"]
    )
    decisions = [
        {
            "item_id": item["id"],
            "action": "skip" if item["id"] == skipped_id else "accept",
        }
        for item in review_payload["items"]
    ]

    payload = _call_review_decision_tool(
        "apply_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=decisions,
        reviewer="reviewer-skip-01",
    )

    assert payload["ok"] is True
    assert payload["application_status"] == "blocked"
    applied = json.loads(
        (result.output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["application_status"] == "blocked"
    assert applied["reviewer"] == "reviewer-skip-01"


def test_mcp_apply_is_transactional_when_later_effect_is_invalid(
    tmp_path: Path,
) -> None:
    customer = tmp_path / "transaction-client"
    customer.mkdir()
    (customer / "support.txt").write_text(CU_TEXT, encoding="utf-8")
    result = build_file_preparation_outputs(customer, target_year=2025)
    run_intake, review_payload, _ = _load_review_run(result.output_dir)
    email_item = next(
        item for item in review_payload["items"] if item["id"] == "draft-client-email"
    )
    email_item["output_path"] = "missing-later-target.md"
    review_path = result.output_dir / "review_payload.json"
    review_path.write_text(
        json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    review_path.chmod(0o600)
    final_artifacts = _reseal_review_run(result.output_dir)
    before = _run_tree_bytes(result.output_dir)

    payload = _call_review_decision_tool(
        "apply_client_file_preparation_decisions",
        run_intake=run_intake,
        review_payload=review_payload,
        final_artifacts=final_artifacts,
        decisions=[
            {
                "item_id": "draft-memo",
                "action": "edit",
                "edit_value": "A valid first edit that must be rolled back.",
            },
            {
                "item_id": "draft-client-email",
                "action": "edit",
                "edit_value": "The later invalid target must fail the batch.",
            },
        ],
        reviewer="reviewer-transaction-01",
    )

    assert payload["ok"] is False
    assert "not a sealed output" in payload["error"]
    assert _run_tree_bytes(result.output_dir) == before

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validate_plugin_review_contract import validate_contract

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"

from build_file_preparation_outputs import build_file_preparation_outputs
from parse_fatturapa_xml import parse_fatturapa_file
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
    assert "certificazione degli interessi passivi del mutuo" in (
        draft_email_items[0]["data"]["preview"]
    )

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


def test_client_file_preparation_mcp_server_validates_and_renders_review_payload() -> (
    None
):
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
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_client_file_preparation_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_client_file_preparation_review",
                "arguments": {"review_payload": review_payload},
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


def test_client_file_preparation_mcp_apply_updates_draft_email_artifact(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "intake"
    output_dir.mkdir()
    draft_email_path = output_dir / "04_bozza_email_cliente.md"
    draft_email_path.write_text(
        "Gentile cliente,\n\ninviare la CU mancante.\n",
        encoding="utf-8",
    )
    run_intake = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": "client-file-preparation-apply-test-run",
        "output_dir": output_dir.as_posix(),
        "data_posture": {
            "local_files_read": [tmp_path.as_posix()],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
    }
    review_payload = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": "client-file-preparation-apply-test-run",
        "review_type": "client_file_preparation_folder_review",
        "items": [
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
            }
        ],
        "item_count": 1,
        "columns": [],
        "evidence": {"client_email": "04_bozza_email_cliente.md"},
        "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
        "status": "ready_for_review",
        "summary": {"file_count": 1, "missing_document_count": 1},
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "client-file-preparation",
        "workflow": "client-file-preparation",
        "run_id": "client-file-preparation-apply-test-run",
        "outputs": [
            {
                "path": "04_bozza_email_cliente.md",
                "kind": "md",
                "status": "written",
            }
        ],
        "caveats": [],
        "next_actions": [],
        "status": "written_pending_review",
    }
    (output_dir / "run_intake.json").write_text(
        json.dumps(run_intake, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "review_payload.json").write_text(
        json.dumps(review_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "final_artifacts.json").write_text(
        json.dumps(final_artifacts, indent=2) + "\n",
        encoding="utf-8",
    )
    edited_email = (
        "Gentile cliente,\n\n"
        "per completare l'istruttoria servono CU 2025 e certificazione mutuo."
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
                    "decisions": [
                        {
                            "item_id": "draft-client-email",
                            "action": "edit",
                            "edit_value": edited_email,
                            "reviewer_note": "Rewrite the client request.",
                        }
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
    assert draft_email_path.read_text(encoding="utf-8") == edited_email
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["effects"][0]["artifact_update"] == "target_artifact_updated"
    assert applied["effects"][0]["target_artifact"] == "04_bozza_email_cliente.md"
    assert applied["target_update_paths"] == ["04_bozza_email_cliente.md"]
    backup_path = output_dir / applied["original_backup_paths"][0]
    assert backup_path.read_text(encoding="utf-8") == (
        "Gentile cliente,\n\ninviare la CU mancante.\n"
    )
    updated_final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert updated_final["review_status"] == "final_ready"
    assert updated_final["review_application"]["target_update_paths"] == [
        "04_bozza_email_cliente.md"
    ]
    email_output = next(
        output
        for output in updated_final["outputs"]
        if output["path"] == "04_bozza_email_cliente.md"
    )
    assert email_output["status"] == "updated_from_review"

from __future__ import annotations

import argparse
import csv
import json
import logging

# XML is parsed only through _safe_xml_root, which rejects declarations.
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "InvoiceXmlRecord",
    "localize_formal_anomaly",
    "parse_fatturapa_file",
    "parse_xml_files",
    "write_duplicate_candidates_csv",
    "write_formal_anomalies_markdown",
    "write_summary_csv",
    "write_summary_jsonl",
]

LOGGER = logging.getLogger(__name__)
MAX_XML_BYTES = 20 * 1024 * 1024
FORBIDDEN_XML_DECLARATIONS = (b"<!doctype", b"<!entity")
SUPPORTED_LANGUAGES = ("it", "en", "fr", "de", "es")

ANOMALY_COPY = {
    "tipo documento mancante": {
        "en": "document type missing",
        "fr": "type de document manquant",
        "de": "Dokumenttyp fehlt",
        "es": "falta el tipo de documento",
    },
    "data fattura mancante": {
        "en": "invoice date missing",
        "fr": "date de facture manquante",
        "de": "Rechnungsdatum fehlt",
        "es": "falta la fecha de la factura",
    },
    "numero fattura mancante": {
        "en": "invoice number missing",
        "fr": "numéro de facture manquant",
        "de": "Rechnungsnummer fehlt",
        "es": "falta el número de la factura",
    },
    "importo totale documento mancante": {
        "en": "document total missing",
        "fr": "total du document manquant",
        "de": "Dokumentgesamtbetrag fehlt",
        "es": "falta el total del documento",
    },
    "partita IVA / codice fiscale cedente mancante": {
        "en": "supplier VAT/tax identifier missing",
        "fr": "identifiant TVA/fiscal du fournisseur manquant",
        "de": "USt-/Steuer-ID des Lieferanten fehlt",
        "es": "falta el identificador fiscal o de IVA del proveedor",
    },
    "sezione DatiRiepilogo non individuata": {
        "en": "DatiRiepilogo section not found",
        "fr": "section DatiRiepilogo introuvable",
        "de": "Abschnitt DatiRiepilogo nicht gefunden",
        "es": "no se encuentra la sección DatiRiepilogo",
    },
}


def localize_formal_anomaly(value: str, language: str) -> str:
    """Return a human-facing FatturaPA anomaly in the working language."""

    if language == "it":
        return value
    direct = ANOMALY_COPY.get(value, {}).get(language)
    if direct:
        return direct
    if value.startswith("data fuori anno target "):
        year = value.removeprefix("data fuori anno target ")
        return {
            "en": f"date outside target year {year}",
            "fr": f"date hors de l’année cible {year}",
            "de": f"Datum außerhalb des Zieljahres {year}",
            "es": f"fecha fuera del año objetivo {year}",
        }[language]
    if value.startswith("XML non leggibile:"):
        detail = value.partition(":")[2].strip()
        prefix = {
            "en": "Unreadable XML",
            "fr": "XML illisible",
            "de": "XML nicht lesbar",
            "es": "XML no legible",
        }[language]
        return f"{prefix}: {detail}"
    return value


@dataclass(frozen=True)
class InvoiceXmlRecord:
    """Formal data extracted from one FatturaPA XML file."""

    relative_path: str
    file_name: str
    supplier_vat: str
    supplier_name: str
    customer_tax_id: str
    customer_name: str
    invoice_date: str
    invoice_number: str
    document_type: str
    total_amount: str
    currency: str
    vat_summary: str
    natura_codes: str
    withholding_summary: str
    stamp_duty: str
    payment_methods: str
    line_count: int
    malformed: bool
    anomalies: tuple[str, ...]

    @property
    def duplicate_key(self) -> str:
        return "|".join(
            [
                self.supplier_vat,
                self.invoice_number,
                self.invoice_date,
                self.total_amount,
            ]
        )

    def as_row(self) -> dict[str, str | bool]:
        return {
            "relative_path": self.relative_path,
            "file_name": self.file_name,
            "supplier_vat": self.supplier_vat,
            "supplier_name": self.supplier_name,
            "customer_tax_id": self.customer_tax_id,
            "customer_name": self.customer_name,
            "invoice_date": self.invoice_date,
            "invoice_number": self.invoice_number,
            "document_type": self.document_type,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "vat_summary": self.vat_summary,
            "natura_codes": self.natura_codes,
            "withholding_summary": self.withholding_summary,
            "stamp_duty": self.stamp_duty,
            "payment_methods": self.payment_methods,
            "line_count": self.line_count,
            "malformed": self.malformed,
            "anomalies": " | ".join(self.anomalies),
            "duplicate_key": self.duplicate_key,
        }

    def as_json(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self) | {"duplicate_key": self.duplicate_key}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_first(node: ET.Element | None, local_name: str) -> ET.Element | None:
    if node is None:
        return None
    for child in node.iter():
        if _local_name(child.tag) == local_name:
            return child
    return None


def _find_all(node: ET.Element | None, local_name: str) -> list[ET.Element]:
    if node is None:
        return []
    return [child for child in node.iter() if _local_name(child.tag) == local_name]


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


def _first_text(node: ET.Element | None, local_names: Sequence[str]) -> str:
    if node is None:
        return ""
    for local_name in local_names:
        value = _text(_find_first(node, local_name))
        if value:
            return value
    return ""


def _party_vat(party: ET.Element | None) -> str:
    dati_anagrafici = (
        _find_first(party, "DatiAnagrafici") if party is not None else None
    )
    id_fiscale_iva = (
        _find_first(dati_anagrafici, "IdFiscaleIVA")
        if dati_anagrafici is not None
        else None
    )
    return _first_text(id_fiscale_iva, ["IdCodice"]) or _first_text(
        dati_anagrafici,
        ["CodiceFiscale"],
    )


def _party_name(party: ET.Element | None) -> str:
    dati_anagrafici = (
        _find_first(party, "DatiAnagrafici") if party is not None else None
    )
    anagrafica = _find_first(dati_anagrafici, "Anagrafica")
    denominazione = _first_text(anagrafica, ["Denominazione"])
    if denominazione:
        return denominazione
    nome = _first_text(anagrafica, ["Nome"])
    cognome = _first_text(anagrafica, ["Cognome"])
    return " ".join(part for part in [nome, cognome] if part)


def _normalize_amount(value: str) -> str:
    if not value:
        return ""
    normalized = value.replace(".", "").replace(",", ".") if "," in value else value
    try:
        return str(Decimal(normalized).quantize(Decimal("0.01")))
    except InvalidOperation:
        return value


def _join_unique(values: Iterable[str]) -> str:
    return "; ".join(sorted({value for value in values if value}))


def _build_vat_summary(root: ET.Element) -> tuple[str, str]:
    rows: list[str] = []
    natura_codes: list[str] = []
    for riepilogo in _find_all(root, "DatiRiepilogo"):
        aliquota = _normalize_amount(_first_text(riepilogo, ["AliquotaIVA"]))
        natura = _first_text(riepilogo, ["Natura"])
        imponibile = _normalize_amount(_first_text(riepilogo, ["ImponibileImporto"]))
        imposta = _normalize_amount(_first_text(riepilogo, ["Imposta"]))
        if natura:
            natura_codes.append(natura)
        parts = [
            f"aliquota={aliquota}" if aliquota else "",
            f"natura={natura}" if natura else "",
            f"imponibile={imponibile}" if imponibile else "",
            f"imposta={imposta}" if imposta else "",
        ]
        row = ", ".join(part for part in parts if part)
        if row:
            rows.append(row)
    return " | ".join(rows), _join_unique(natura_codes)


def _build_withholding_summary(root: ET.Element) -> str:
    rows: list[str] = []
    for ritenuta in _find_all(root, "DatiRitenuta"):
        tipo = _first_text(ritenuta, ["TipoRitenuta"])
        importo = _normalize_amount(_first_text(ritenuta, ["ImportoRitenuta"]))
        aliquota = _normalize_amount(_first_text(ritenuta, ["AliquotaRitenuta"]))
        causale = _first_text(ritenuta, ["CausalePagamento"])
        parts = [
            f"tipo={tipo}" if tipo else "",
            f"importo={importo}" if importo else "",
            f"aliquota={aliquota}" if aliquota else "",
            f"causale={causale}" if causale else "",
        ]
        row = ", ".join(part for part in parts if part)
        if row:
            rows.append(row)
    return " | ".join(rows)


def _build_stamp_duty(root: ET.Element) -> str:
    rows: list[str] = []
    for bollo in _find_all(root, "DatiBollo"):
        virtuale = _first_text(bollo, ["BolloVirtuale"])
        importo = _normalize_amount(_first_text(bollo, ["ImportoBollo"]))
        parts = [
            f"bollo_virtuale={virtuale}" if virtuale else "",
            f"importo={importo}" if importo else "",
        ]
        row = ", ".join(part for part in parts if part)
        if row:
            rows.append(row)
    return " | ".join(rows)


def _build_payment_methods(root: ET.Element) -> str:
    return _join_unique(
        _first_text(payment, ["ModalitaPagamento"])
        for payment in _find_all(root, "DettaglioPagamento")
    )


def _safe_xml_root(xml_path: Path) -> ET.Element:
    """Parse bounded XML after rejecting DTD and entity declarations."""

    payload = xml_path.read_bytes()
    if len(payload) > MAX_XML_BYTES:
        raise ET.ParseError(f"XML exceeds the {MAX_XML_BYTES}-byte safety limit")
    if b"\x00" in payload:
        raise ET.ParseError("XML encoding with null bytes is not supported")
    lowered = payload.lower()
    if any(marker in lowered for marker in FORBIDDEN_XML_DECLARATIONS):
        raise ET.ParseError("DTD and entity declarations are not allowed")
    # The bounded payload cannot contain DTD or entity declarations.
    return ET.fromstring(payload)  # nosec B314


def parse_fatturapa_file(
    path: Path | str,
    base_dir: Path | str | None = None,
    target_year: int | None = None,
) -> InvoiceXmlRecord:
    """Parse one XML file and return formal invoice metadata."""

    xml_path = Path(path)
    base_path = Path(base_dir).resolve() if base_dir else xml_path.parent.resolve()
    relative = xml_path.resolve().relative_to(base_path).as_posix()

    try:
        root = _safe_xml_root(xml_path)
    except (ET.ParseError, OSError) as exc:
        return InvoiceXmlRecord(
            relative_path=relative,
            file_name=xml_path.name,
            supplier_vat="",
            supplier_name="",
            customer_tax_id="",
            customer_name="",
            invoice_date="",
            invoice_number="",
            document_type="",
            total_amount="",
            currency="",
            vat_summary="",
            natura_codes="",
            withholding_summary="",
            stamp_duty="",
            payment_methods="",
            line_count=0,
            malformed=True,
            anomalies=(f"XML non leggibile: {exc}",),
        )

    header = _find_first(root, "FatturaElettronicaHeader")
    body = _find_first(root, "FatturaElettronicaBody")
    general_data = _find_first(body, "DatiGeneraliDocumento")
    supplier = _find_first(header, "CedentePrestatore")
    customer = _find_first(header, "CessionarioCommittente")

    invoice_date = _first_text(general_data, ["Data"])
    invoice_number = _first_text(general_data, ["Numero"])
    document_type = _first_text(general_data, ["TipoDocumento"])
    total_amount = _normalize_amount(
        _first_text(general_data, ["ImportoTotaleDocumento"])
    )
    currency = _first_text(general_data, ["Divisa"])
    vat_summary, natura_codes = _build_vat_summary(root)
    withholding_summary = _build_withholding_summary(root)
    stamp_duty = _build_stamp_duty(root)
    payment_methods = _build_payment_methods(root)
    line_count = len(_find_all(root, "DettaglioLinee"))

    anomalies: list[str] = []
    if not document_type:
        anomalies.append("tipo documento mancante")
    if not invoice_date:
        anomalies.append("data fattura mancante")
    if not invoice_number:
        anomalies.append("numero fattura mancante")
    if not total_amount:
        anomalies.append("importo totale documento mancante")
    if not _party_vat(supplier):
        anomalies.append("partita IVA / codice fiscale cedente mancante")
    if target_year is not None and invoice_date:
        if not invoice_date.startswith(str(target_year)):
            anomalies.append(f"data fuori anno target {target_year}")

    riepiloghi = _find_all(root, "DatiRiepilogo")
    if not riepiloghi:
        anomalies.append("sezione DatiRiepilogo non individuata")

    return InvoiceXmlRecord(
        relative_path=relative,
        file_name=xml_path.name,
        supplier_vat=_party_vat(supplier),
        supplier_name=_party_name(supplier),
        customer_tax_id=_party_vat(customer),
        customer_name=_party_name(customer),
        invoice_date=invoice_date,
        invoice_number=invoice_number,
        document_type=document_type,
        total_amount=total_amount,
        currency=currency,
        vat_summary=vat_summary,
        natura_codes=natura_codes,
        withholding_summary=withholding_summary,
        stamp_duty=stamp_duty,
        payment_methods=payment_methods,
        line_count=line_count,
        malformed=False,
        anomalies=tuple(anomalies),
    )


def parse_xml_files(
    paths: Iterable[Path],
    base_dir: Path | str,
    target_year: int | None = None,
) -> list[InvoiceXmlRecord]:
    """Parse all XML files in a customer folder."""

    base_path = Path(base_dir)
    return [
        parse_fatturapa_file(path, base_dir=base_path, target_year=target_year)
        for path in sorted(paths)
        if path.is_file()
    ]


def write_summary_csv(
    records: Iterable[InvoiceXmlRecord],
    output_path: Path | str,
) -> Path:
    """Write parsed XML invoice data to CSV."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relative_path",
        "file_name",
        "supplier_vat",
        "supplier_name",
        "customer_tax_id",
        "customer_name",
        "invoice_date",
        "invoice_number",
        "document_type",
        "total_amount",
        "currency",
        "vat_summary",
        "natura_codes",
        "withholding_summary",
        "stamp_duty",
        "payment_methods",
        "line_count",
        "malformed",
        "anomalies",
        "duplicate_key",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_row())
    return path


def write_summary_jsonl(
    records: Iterable[InvoiceXmlRecord],
    output_path: Path | str,
) -> Path:
    """Write parsed XML invoice data as one JSON object per line."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.as_json(), ensure_ascii=False) + "\n")
    return path


def _duplicate_groups(
    records: Sequence[InvoiceXmlRecord],
) -> dict[str, list[InvoiceXmlRecord]]:
    groups: dict[str, list[InvoiceXmlRecord]] = {}
    for record in records:
        if record.malformed or not record.duplicate_key.strip("|"):
            continue
        groups.setdefault(record.duplicate_key, []).append(record)
    return {key: value for key, value in groups.items() if len(value) > 1}


def write_duplicate_candidates_csv(
    records: Sequence[InvoiceXmlRecord],
    output_path: Path | str,
) -> Path:
    """Write likely duplicate invoice XML rows to CSV."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "duplicate_key",
        "relative_path",
        "supplier_vat",
        "invoice_date",
        "invoice_number",
        "total_amount",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for key, group in sorted(_duplicate_groups(records).items()):
            for record in sorted(group, key=lambda item: item.relative_path):
                writer.writerow(
                    {
                        "duplicate_key": key,
                        "relative_path": record.relative_path,
                        "supplier_vat": record.supplier_vat,
                        "invoice_date": record.invoice_date,
                        "invoice_number": record.invoice_number,
                        "total_amount": record.total_amount,
                    }
                )
    return path


def write_formal_anomalies_markdown(
    records: Sequence[InvoiceXmlRecord],
    output_path: Path | str,
    *,
    language: str = "it",
) -> Path:
    """Write formal XML anomalies to markdown."""

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    copy = {
        "it": {
            "title": "Anomalie formali e-fattura XML",
            "intro": "Questo controllo riepiloga campi XML, date, importi, natura, IVA e anomalie formali.",
            "duplicates": "Duplicati potenziali",
            "by_file": "Anomalie per file",
            "empty": "Nessuna anomalia formale individuata nei file XML analizzati.",
        },
        "en": {
            "title": "Formal electronic-invoice XML anomalies",
            "intro": "This check summarizes XML fields, dates, amounts, VAT nature codes, VAT, and formal anomalies.",
            "duplicates": "Potential duplicates",
            "by_file": "Anomalies by file",
            "empty": "No formal anomaly was identified in the XML files reviewed.",
        },
        "fr": {
            "title": "Anomalies formelles des factures électroniques XML",
            "intro": "Ce contrôle récapitule les champs XML, dates, montants, codes nature TVA, TVA et anomalies formelles.",
            "duplicates": "Doublons potentiels",
            "by_file": "Anomalies par fichier",
            "empty": "Aucune anomalie formelle n’a été relevée dans les fichiers XML examinés.",
        },
        "de": {
            "title": "Formale Anomalien in E-Rechnungs-XML",
            "intro": "Diese Prüfung fasst XML-Felder, Daten, Beträge, Mehrwertsteuer-Naturcodes, Mehrwertsteuer und formale Anomalien zusammen.",
            "duplicates": "Mögliche Duplikate",
            "by_file": "Anomalien nach Datei",
            "empty": "In den geprüften XML-Dateien wurden keine formalen Anomalien festgestellt.",
        },
        "es": {
            "title": "Anomalías formales en XML de factura electrónica",
            "intro": "Este control resume los campos XML, las fechas, los importes, los códigos de naturaleza del IVA, el IVA y las anomalías formales.",
            "duplicates": "Posibles duplicados",
            "by_file": "Anomalías por archivo",
            "empty": "No se detectaron anomalías formales en los archivos XML revisados.",
        },
    }[language]
    lines = [f"# {copy['title']}", "", copy["intro"], ""]

    duplicate_groups = _duplicate_groups(records)
    if duplicate_groups:
        lines.extend([f"## {copy['duplicates']}", ""])
        for key, group in sorted(duplicate_groups.items()):
            files = ", ".join(f"`{record.relative_path}`" for record in group)
            lines.append(f"- {key}: {files}")
        lines.append("")

    anomaly_records = [record for record in records if record.anomalies]
    if anomaly_records:
        lines.extend([f"## {copy['by_file']}", ""])
        for record in anomaly_records:
            lines.append(f"- `{record.relative_path}`")
            for anomaly in record.anomalies:
                lines.append(f"  - {localize_formal_anomaly(anomaly, language)}")
    else:
        lines.append(copy["empty"])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analizza formalmente file FatturaPA XML e produce CSV."
    )
    parser.add_argument("folder", type=Path, help="Cartella contenente XML.")
    parser.add_argument("--year", type=int, default=None, help="Anno fiscale target.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Cartella output. Default: <folder>/out/fatture",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    out_dir = args.out or args.folder / "out" / "fatture"
    records = parse_xml_files(args.folder.rglob("*.xml"), args.folder, args.year)
    write_summary_csv(records, out_dir / "fatture_summary.csv")
    write_summary_jsonl(records, out_dir / "fatture_summary.jsonl")
    write_duplicate_candidates_csv(records, out_dir / "duplicate_candidates.csv")
    write_formal_anomalies_markdown(records, out_dir / "formal_anomalies.md")
    LOGGER.info("Analizzati %s XML. Output in %s", len(records), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

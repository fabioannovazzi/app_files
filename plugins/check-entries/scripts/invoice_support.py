"""Load and match Italian FatturaPA support from ZIPs or connector exports."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

# Payload size and DTD/entity checks are enforced before this parser is called.
from xml.etree import ElementTree  # nosec B405

__all__ = [
    "InvoiceRecord",
    "load_invoice_records",
    "match_invoice",
]

MAX_XML_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000


@dataclass(frozen=True)
class InvoiceRecord:
    """Mechanically parsed fields from one FatturaPA XML document."""

    source_name: str
    invoice_number: str
    invoice_date: str | None
    total_amount: float | None
    supplier_name: str
    supplier_tax_id: str
    customer_name: str
    customer_tax_id: str

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable representation."""

        return {
            "source_name": self.source_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "total_amount": self.total_amount,
            "supplier_name": self.supplier_name,
            "supplier_tax_id": self.supplier_tax_id,
            "customer_name": self.customer_name,
            "customer_tax_id": self.customer_tax_id,
        }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(root: ElementTree.Element, path: tuple[str, ...]) -> str:
    nodes = [root]
    for wanted in path:
        nodes = [
            child
            for node in nodes
            for child in node
            if _local_name(child.tag) == wanted
        ]
        if not nodes:
            return ""
    return (nodes[0].text or "").strip()


def _party_name(root: ElementTree.Element, party_tag: str) -> str:
    party = next(
        (node for node in root.iter() if _local_name(node.tag) == party_tag), None
    )
    if party is None:
        return ""
    denomination = _first_text(party, ("DatiAnagrafici", "Anagrafica", "Denominazione"))
    if denomination:
        return denomination
    first_name = _first_text(party, ("DatiAnagrafici", "Anagrafica", "Nome"))
    last_name = _first_text(party, ("DatiAnagrafici", "Anagrafica", "Cognome"))
    return " ".join(part for part in (first_name, last_name) if part)


def _party_tax_id(root: ElementTree.Element, party_tag: str) -> str:
    party = next(
        (node for node in root.iter() if _local_name(node.tag) == party_tag), None
    )
    if party is None:
        return ""
    vat = _first_text(party, ("DatiAnagrafici", "IdFiscaleIVA", "IdCodice"))
    return vat or _first_text(party, ("DatiAnagrafici", "CodiceFiscale"))


def _parse_amount(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_invoice_xml(source_name: str, payload: bytes) -> InvoiceRecord:
    if len(payload) > MAX_XML_BYTES:
        raise ValueError(f"FatturaPA XML exceeds {MAX_XML_BYTES} bytes: {source_name}")
    upper_payload = payload.upper()
    if b"<!DOCTYPE" in upper_payload or b"<!ENTITY" in upper_payload:
        raise ValueError(f"DTD/entity declarations are not allowed: {source_name}")
    # ElementTree is safe here because payload size is bounded and DTD/entities
    # are rejected before parsing; fixed parsing is required for audit replay.
    root = ElementTree.fromstring(payload)  # nosec B314
    body = next(
        (
            node
            for node in root.iter()
            if _local_name(node.tag) == "FatturaElettronicaBody"
        ),
        None,
    )
    if body is None:
        raise ValueError(f"Not a FatturaPA invoice: {source_name}")
    general = next(
        (
            node
            for node in body.iter()
            if _local_name(node.tag) == "DatiGeneraliDocumento"
        ),
        None,
    )
    if general is None:
        raise ValueError(f"Missing DatiGeneraliDocumento: {source_name}")
    return InvoiceRecord(
        source_name=source_name,
        invoice_number=_first_text(general, ("Numero",)),
        invoice_date=_first_text(general, ("Data",)) or None,
        total_amount=_parse_amount(_first_text(general, ("ImportoTotaleDocumento",))),
        supplier_name=_party_name(root, "CedentePrestatore"),
        supplier_tax_id=_party_tax_id(root, "CedentePrestatore"),
        customer_name=_party_name(root, "CessionarioCommittente"),
        customer_tax_id=_party_tax_id(root, "CessionarioCommittente"),
    )


def _xml_payloads(path: Path) -> Iterable[tuple[str, bytes]]:
    if path.is_dir():
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in {".xml", ".p7m"}:
                yield candidate.name, candidate.read_bytes()
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise ValueError(
                    f"Invoice archive exceeds {MAX_ARCHIVE_FILES} members: {path}"
                )
            for member in sorted(members, key=lambda item: item.filename):
                if member.is_dir() or Path(member.filename).suffix.lower() not in {
                    ".xml",
                    ".p7m",
                }:
                    continue
                if member.flag_bits & 0x1:
                    raise ValueError(
                        f"Encrypted ZIP member is unsupported: {member.filename}"
                    )
                if member.file_size > MAX_XML_BYTES:
                    raise ValueError(
                        f"Invoice XML exceeds {MAX_XML_BYTES} bytes: {member.filename}"
                    )
                yield member.filename, archive.read(member)
        return
    if path.suffix.lower() in {".xml", ".p7m"}:
        yield path.name, path.read_bytes()
        return
    raise ValueError(f"Invoice source must be an XML, ZIP, or folder: {path}")


def load_invoice_records(
    path: Path,
) -> tuple[list[InvoiceRecord], list[dict[str, str]]]:
    """Parse readable FatturaPA XMLs without extracting ZIP contents to disk."""

    records: list[InvoiceRecord] = []
    errors: list[dict[str, str]] = []
    for source_name, payload in _xml_payloads(path.expanduser()):
        try:
            # Signed .p7m envelopes are reported for review unless they contain plain XML.
            records.append(_parse_invoice_xml(source_name, payload))
        except (ElementTree.ParseError, ValueError, UnicodeError) as exc:
            errors.append({"source_name": source_name, "error": str(exc)})
    return records, errors


def _norm(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _contains_party(expected: object, record: InvoiceRecord) -> bool:
    expected_norm = _norm(expected)
    if not expected_norm:
        return False
    parties = " ".join(
        _norm(value)
        for value in (
            record.supplier_name,
            record.supplier_tax_id,
            record.customer_name,
            record.customer_tax_id,
        )
    )
    tokens = [token for token in expected_norm.split() if len(token) > 2]
    return bool(tokens) and all(token in parties for token in tokens)


def match_invoice(
    entry: dict[str, Any],
    invoices: list[InvoiceRecord],
    *,
    amount_tolerance: float,
    date_window_days: int,
) -> tuple[InvoiceRecord | None, list[str], str | None]:
    """Return a unique invoice match based on mechanically verifiable signals.

    At least two independent signals are required. This fixed boundary prevents a
    common amount alone from silently selecting the wrong accounting evidence.
    """

    candidates: list[tuple[InvoiceRecord, list[str]]] = []
    description = _norm(entry.get("description"))
    expected_amount = entry.get("amount_abs")
    expected_date = _parse_date(entry.get("entry_date"))
    for invoice in invoices:
        signals: list[str] = []
        if invoice.invoice_number and _norm(invoice.invoice_number) in description:
            signals.append("invoice_number")
        if expected_amount is not None and invoice.total_amount is not None:
            if (
                abs(abs(float(expected_amount)) - abs(invoice.total_amount))
                <= amount_tolerance
            ):
                signals.append("amount")
        invoice_date = _parse_date(invoice.invoice_date)
        if expected_date is not None and invoice_date is not None:
            if abs((expected_date - invoice_date).days) <= date_window_days:
                signals.append("date")
        if _contains_party(entry.get("beneficiary_expected"), invoice):
            signals.append("beneficiary")
        if len(signals) >= 2:
            candidates.append((invoice, signals))
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], None
    if len(candidates) > 1:
        return None, [], "multiple_invoice_candidates"
    return None, [], None

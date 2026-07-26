"""Load and match Italian FatturaPA support from ZIPs or connector exports."""

from __future__ import annotations

import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

# Payload size and DTD/entity checks are enforced before this parser is called.
from xml.etree import ElementTree  # nosec B405

_COMPONENT_ROOT = Path(__file__).resolve().parents[1]
_VENDOR_CANDIDATES = (
    _COMPONENT_ROOT / "vendor" / "modules",
    _COMPONENT_ROOT.parent.parent / "vendor" / "modules",
    _COMPONENT_ROOT.parent / "_shared" / "vendor" / "modules",
)
if "vera_assurance" not in sys.modules:
    for _vendor_candidate in _VENDOR_CANDIDATES:
        if (_vendor_candidate / "vera_assurance").is_dir():
            if str(_vendor_candidate) not in sys.path:
                sys.path.insert(0, str(_vendor_candidate))
            break

from vera_assurance import (  # noqa: E402
    MoneyValidationError,
    decimal_text,
    difference_within_tolerance,
    parse_canonical_decimal,
    parse_localized_decimal,
)

__all__ = [
    "InvoiceRecord",
    "fatturapa_document_polarity",
    "load_invoice_payloads",
    "load_invoice_records",
    "match_invoice",
]

MAX_XML_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_FILES = 10_000
FATTURAPA_POSITIVE_DOCUMENT_TYPES = frozenset(
    {"TD01", "TD02", "TD03", "TD05", "TD06", "TD09"}
)
FATTURAPA_NEGATIVE_DOCUMENT_TYPES = frozenset({"TD04", "TD08"})


def fatturapa_document_polarity(document_type: object) -> str | None:
    """Return bounded document polarity without inferring a journal side.

    ``TipoDocumento`` is mechanically parsed source metadata, but it does not
    identify which account line is under test. Therefore this diagnostic fact
    must never promote a debit/credit conclusion for the journal entry.
    """

    normalized = str(document_type or "").strip().upper()
    if normalized in FATTURAPA_POSITIVE_DOCUMENT_TYPES:
        return "positive_document"
    if normalized in FATTURAPA_NEGATIVE_DOCUMENT_TYPES:
        return "negative_document"
    return None


@dataclass(frozen=True)
class InvoiceRecord:
    """Mechanically parsed fields from one FatturaPA XML document."""

    source_name: str
    document_type: str
    invoice_number: str
    invoice_date: str | None
    total_amount: str | None
    currency: str | None
    supplier_name: str
    supplier_tax_id: str
    customer_name: str
    customer_tax_id: str

    def as_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable representation."""

        return {
            "source_name": self.source_name,
            "document_type": self.document_type,
            "document_polarity": fatturapa_document_polarity(self.document_type),
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "total_amount": self.total_amount,
            "currency": self.currency,
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


def _parse_amount(value: str) -> str | None:
    if not value:
        return None
    try:
        number = parse_localized_decimal(
            value,
            label="FatturaPA ImportoTotaleDocumento",
            decimal_separator=".",
        )
    except MoneyValidationError as exc:
        raise ValueError(str(exc)) from exc
    return decimal_text(number)


def _parse_invoice_xml(source_name: str, payload: bytes) -> InvoiceRecord:
    if len(payload) > MAX_XML_BYTES:
        raise ValueError(f"FatturaPA XML exceeds {MAX_XML_BYTES} bytes: {source_name}")
    upper_payload = payload.upper()
    if b"<!DOCTYPE" in upper_payload or b"<!ENTITY" in upper_payload:
        raise ValueError(f"DTD/entity declarations are not allowed: {source_name}")
    # ElementTree is safe here because payload size is bounded and DTD/entities
    # are rejected before parsing; fixed parsing is required for audit replay.
    root = ElementTree.fromstring(payload)  # nosec B314
    if _local_name(root.tag) != "FatturaElettronica":
        raise ValueError(f"Not a FatturaPA invoice: {source_name}")
    bodies = [
        node
        for node in root.iter()
        if _local_name(node.tag) == "FatturaElettronicaBody"
    ]
    if len(bodies) != 1:
        raise ValueError(f"Expected exactly one FatturaElettronicaBody: {source_name}")
    generals = [
        node
        for node in bodies[0].iter()
        if _local_name(node.tag) == "DatiGeneraliDocumento"
    ]
    if len(generals) != 1:
        raise ValueError(f"Missing DatiGeneraliDocumento: {source_name}")
    general = generals[0]
    document_type = _first_text(general, ("TipoDocumento",))
    invoice_number = _first_text(general, ("Numero",))
    invoice_date = _first_text(general, ("Data",))
    currency = _first_text(general, ("Divisa",)).upper()
    if not document_type or not invoice_number or not invoice_date:
        raise ValueError(
            f"FatturaPA document type, number, and date are required: {source_name}"
        )
    try:
        date.fromisoformat(invoice_date)
    except ValueError as exc:
        raise ValueError(f"Invalid FatturaPA invoice date: {source_name}") from exc
    if re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError(f"Invalid FatturaPA currency: {source_name}")
    return InvoiceRecord(
        source_name=source_name,
        document_type=document_type,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        total_amount=_parse_amount(_first_text(general, ("ImportoTotaleDocumento",))),
        currency=currency,
        supplier_name=_party_name(root, "CedentePrestatore"),
        supplier_tax_id=_party_tax_id(root, "CedentePrestatore"),
        customer_name=_party_name(root, "CessionarioCommittente"),
        customer_tax_id=_party_tax_id(root, "CessionarioCommittente"),
    )


def _xml_payloads(path: Path) -> Iterable[tuple[str, bytes]]:
    if path.is_dir():
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in {".xml", ".p7m"}:
                yield candidate.relative_to(path).as_posix(), candidate.read_bytes()
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
                yield f"{path.name}!/{member.filename}", archive.read(member)
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
        if Path(source_name).suffix.lower() == ".p7m":
            errors.append(
                {
                    "source_name": source_name,
                    "error": (
                        "P7M support is unsupported without a bounded decoder "
                        "and signature-validation policy."
                    ),
                }
            )
            continue
        try:
            records.append(_parse_invoice_xml(source_name, payload))
        except (ElementTree.ParseError, ValueError, UnicodeError) as exc:
            errors.append({"source_name": source_name, "error": str(exc)})
    return records, errors


def load_invoice_payloads(
    payloads: Iterable[tuple[str, bytes]],
) -> tuple[list[InvoiceRecord], list[dict[str, str]]]:
    """Parse already-captured XML bytes without reopening live source files."""

    records: list[InvoiceRecord] = []
    errors: list[dict[str, str]] = []
    for source_name, payload in payloads:
        if Path(source_name).suffix.lower() == ".p7m":
            errors.append(
                {
                    "source_name": source_name,
                    "error": (
                        "P7M support is unsupported without a bounded decoder "
                        "and signature-validation policy."
                    ),
                }
            )
            continue
        try:
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


def _contains_labeled_invoice_identifier(
    container: object,
    identifier: object,
) -> bool:
    """Match only explicit labelled, distinctive invoice references.

    A fixed syntax is justified here because identity is an audit control:
    accepting an unlabeled number, year, or single-letter token creates
    mechanically demonstrable false positives.
    """

    parts = re.findall(r"[a-z0-9]+", str(identifier or "").lower())
    if not parts:
        return False
    compact = "".join(parts)
    if compact.isdigit() or (len(compact) == 1 and compact.isalpha()):
        return False
    text = str(container or "").lower()
    invoice_identifier = r"[^a-z0-9]+".join(re.escape(part) for part in parts)
    label = r"(?:invoice|fattura|facture|rechnung|factura)"
    return (
        re.search(
            rf"(?<![a-z0-9]){label}(?:[^a-z0-9]+(?:n|no|nr|numero|number))?"
            rf"[^a-z0-9]+{invoice_identifier}(?![a-z0-9])",
            text,
        )
        is not None
    )


def match_invoice(
    entry: dict[str, Any],
    invoices: list[InvoiceRecord],
    *,
    amount_tolerance: Decimal,
    date_window_days: int,
) -> tuple[InvoiceRecord | None, list[str], str | None]:
    """Return a unique invoice match based on mechanically verifiable signals.

    An explicit invoice-number relationship plus at least one corroborating
    signal is required. Amount/date/currency coincidence without an identity key
    remains a review candidate rather than silently selecting evidence.
    """

    candidates: list[tuple[InvoiceRecord, list[str]]] = []
    weak_candidates: list[tuple[InvoiceRecord, list[str]]] = []
    description = _norm(entry.get("description"))
    expected_amount = entry.get("amount_abs")
    expected_amount_value = (
        None
        if expected_amount in (None, "")
        else parse_canonical_decimal(expected_amount, label="entry amount_abs")
    )
    expected_currency = str(entry.get("currency") or "").strip().upper()
    expected_date = _parse_date(entry.get("entry_date"))
    for invoice in invoices:
        signals: list[str] = []
        if invoice.invoice_number and _contains_labeled_invoice_identifier(
            description, invoice.invoice_number
        ):
            signals.append("invoice_number")
        if expected_amount_value is not None and invoice.total_amount is not None:
            invoice_amount = parse_canonical_decimal(
                invoice.total_amount,
                label=f"{invoice.source_name} total_amount",
            )
            invoice_currency = str(invoice.currency or "").strip().upper()
            if expected_currency and invoice_currency == expected_currency:
                _, within = difference_within_tolerance(
                    abs(invoice_amount), abs(expected_amount_value), amount_tolerance
                )
                if within:
                    signals.append("amount")
        invoice_date = _parse_date(invoice.invoice_date)
        if expected_date is not None and invoice_date is not None:
            if abs((expected_date - invoice_date).days) <= date_window_days:
                signals.append("date")
        if "invoice_number" in signals and len(signals) >= 2:
            candidates.append((invoice, signals))
        elif len(signals) >= 2:
            weak_candidates.append((invoice, signals))
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], None
    if len(candidates) > 1:
        return None, [], "multiple_invoice_candidates"
    if weak_candidates:
        return None, [], "invoice_relationship_requires_review"
    return None, [], None

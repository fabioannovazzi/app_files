"""Deterministic engine for Vera's passive-invoice audit workflow."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import logging
import sqlite3
import sys
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from openpyxl import load_workbook
from xlsxwriter import Workbook

__all__ = [
    "AuditConfig",
    "AuditError",
    "LunaRunner",
    "chunk_semantic_packets",
    "create_synthetic_population",
    "evaluate_results",
    "evaluate_synthetic_population",
    "load_ledger",
    "parse_invoice_population",
    "run_audit",
    "validate_luna_result",
]

LOGGER = logging.getLogger(__name__)
WORKFLOW_ID = "passive-invoice-audit"
WORKFLOW_VERSION = "0.1.0"
SCHEMA_VERSION = "vera.passive_invoice_audit.v1"
CENT = Decimal("0.01")
MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_INVOICE_XML_BYTES = 20 * 1024 * 1024
MAX_PACKET_LINES = 80
MAX_PACKET_DESCRIPTION_CHARS = 12_000
MAX_LUNA_PROMPT_BYTES = 240 * 1024
SEMANTIC_STATUSES = {
    "no_issue_detected",
    "review_required",
    "insufficient_evidence",
}
ISSUE_TYPES = {
    "none",
    "economic_substance_account_mismatch",
    "possible_fixed_asset",
    "possible_capitalisation_issue",
    "ambiguous_expense_classification",
    "unusual_vat_treatment",
    "historical_treatment_inconsistency",
    "invoice_contains_multiple_economic_categories",
    "insufficient_description",
    "possible_period_cutoff_issue",
    "other_material_accounting_issue",
}
REQUIRED_LEDGER_FIELDS = {
    "movement_id",
    "entry_date",
    "account_code",
    "account_description",
}
OPTIONAL_LEDGER_FIELDS = {
    "line_number",
    "line_description",
    "amount_signed",
    "debit",
    "credit",
    "currency",
    "supplier_tax_id",
    "supplier_name",
    "invoice_number",
    "document_reference",
    "document_date",
    "gross_amount",
    "taxable_amount",
    "vat_amount",
    "account_type",
}


class AuditError(ValueError):
    """Raised when the controlled audit contract cannot be satisfied."""


LunaRunner = Callable[[str, Mapping[str, Any], Path, str, str, str], Mapping[str, Any]]


@dataclass(frozen=True)
class AuditConfig:
    """Bounded controls for one restartable invoice audit."""

    chunk_size: int = 25
    concurrency: int = 2
    max_retries: int = 2
    reasoning_effort: str = "low"
    amount_tolerance: Decimal = CENT

    def validate(self) -> None:
        """Reject unsafe or unsupported execution settings."""

        if not 1 <= self.chunk_size <= 50:
            raise AuditError("chunk_size must be between 1 and 50")
        if not 1 <= self.concurrency <= 4:
            raise AuditError("concurrency must be between 1 and 4")
        if not 0 <= self.max_retries <= 3:
            raise AuditError("max_retries must be between 0 and 3")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise AuditError("Unsupported Luna reasoning effort")
        if self.amount_tolerance < 0:
            raise AuditError("amount_tolerance cannot be negative")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalized_identifier(value: Any) -> str:
    return "".join(
        character for character in _text(value).upper() if character.isalnum()
    )


def _normalized_invoice_number(value: Any) -> str:
    return _normalized_identifier(value).lstrip("0") or "0"


def _decimal(value: Any, *, allow_blank: bool = True) -> Decimal | None:
    text = _text(value)
    if not text and allow_blank:
        return None
    if not text:
        raise AuditError("Required decimal value is blank")
    normalized = text.replace(" ", "")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise AuditError(f"Invalid decimal value: {text}") from exc


def _money(value: Decimal | None) -> str:
    return "" if value is None else str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _load_fatturapa_module() -> Any:
    roots = [
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3] / "modules",
    ]
    candidates = [
        root / "client-file-preparation" / "scripts" / "parse_fatturapa_xml.py"
        for root in roots
    ]
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise AuditError(
            "Vera's client-file-preparation FatturaPA parser is unavailable"
        )
    spec = importlib.util.spec_from_file_location("vera_fatturapa_parser", source)
    if spec is None or spec.loader is None:
        raise AuditError("Unable to load Vera's FatturaPA parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_archive_members(source: Path, staging_dir: Path) -> list[Path]:
    staging_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    total = 0
    with zipfile.ZipFile(source) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise AuditError("Invoice archive exceeds the member-count limit")
        for member in members:
            total += member.file_size
            if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise AuditError("Invoice archive exceeds the uncompressed-size limit")
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise AuditError("Invoice archive contains an unsafe member path")
            if member_path.suffix.lower() != ".xml":
                continue
            if member.file_size > MAX_INVOICE_XML_BYTES:
                raise AuditError("Invoice archive contains an oversized XML member")
            payload = archive.read(member)
            digest = _sha256_bytes(payload)
            target = staging_dir / f"{len(paths):08d}-{digest[:16]}.xml"
            if target.exists() and target.read_bytes() != payload:
                raise AuditError("Staged invoice hash collision")
            if not target.exists():
                target.write_bytes(payload)
            paths.append(target)
    return paths


def parse_invoice_population(source: Path, staging_dir: Path) -> list[dict[str, Any]]:
    """Parse a directory, XML file, or ZIP into one record per invoice body."""

    started = time.perf_counter()
    source = source.expanduser().resolve()
    if source.is_dir():
        paths = sorted(
            path for path in source.rglob("*") if path.suffix.lower() == ".xml"
        )
        base_dir = source
        source_names = {path: path.relative_to(source).as_posix() for path in paths}
    elif source.is_file() and source.suffix.lower() == ".zip":
        paths = _safe_archive_members(source, staging_dir)
        base_dir = staging_dir
        source_names = {path: f"{source.name}!{path.name}" for path in paths}
    elif source.is_file() and source.suffix.lower() == ".xml":
        paths = [source]
        base_dir = source.parent
        source_names = {source: source.name}
    else:
        raise AuditError(
            "Invoice source must be an XML file, directory, or ZIP archive"
        )
    parser = _load_fatturapa_module()
    invoices: list[dict[str, Any]] = []
    for path in paths:
        source_hash = _sha256_file(path)
        try:
            bodies = parser.parse_fatturapa_audit_file(path, base_dir=base_dir)
        except (OSError, ValueError, parser.ET.ParseError) as exc:
            invoice_id = _sha256_json([source_names[path], source_hash, 0])[:24]
            invoices.append(
                {
                    "invoice_id": invoice_id,
                    "source_identifier": source_names[path],
                    "source_sha256": source_hash,
                    "body_index": 0,
                    "xml_valid": False,
                    "parse_error": str(exc),
                    "lines": [],
                    "vat_summaries": [],
                }
            )
            continue
        for body in bodies:
            record = dict(body)
            record["source_identifier"] = source_names[path]
            record["source_sha256"] = source_hash
            record["xml_valid"] = True
            record["parse_error"] = ""
            record["invoice_id"] = _sha256_json(
                [source_names[path], source_hash, record["body_index"]]
            )[:24]
            invoices.append(record)
    elapsed = max(time.perf_counter() - started, 0.000001)
    LOGGER.info(
        "Parsed %d invoice bodies at %.1f/s", len(invoices), len(invoices) / elapsed
    )
    return invoices


def _read_tabular(
    path: Path, sheet: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), [dict(row) for row in reader]
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet = workbook[sheet] if sheet else workbook[workbook.sheetnames[0]]
            rows = worksheet.iter_rows(values_only=True)
            try:
                headers = [_text(value) for value in next(rows)]
            except StopIteration:
                return [], []
            return headers, [dict(zip(headers, row, strict=True)) for row in rows]
        finally:
            workbook.close()
    raise AuditError("Ledger must be CSV, XLSX, or XLSM")


def load_ledger(
    path: Path,
    mapping_path: Path,
    *,
    sheet: str | None = None,
) -> list[dict[str, Any]]:
    """Load ledger rows through an explicit reviewed source-to-canonical map."""

    path = path.expanduser().resolve()
    mapping = json.loads(
        mapping_path.expanduser().resolve().read_text(encoding="utf-8")
    )
    if not isinstance(mapping, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in mapping.items()
    ):
        raise AuditError(
            "Ledger mapping must be a JSON object of canonical to source headers"
        )
    unknown = set(mapping) - REQUIRED_LEDGER_FIELDS - OPTIONAL_LEDGER_FIELDS
    missing = REQUIRED_LEDGER_FIELDS - set(mapping)
    if unknown:
        raise AuditError(f"Unknown canonical ledger fields: {sorted(unknown)}")
    if missing:
        raise AuditError(f"Missing required ledger mappings: {sorted(missing)}")
    if "amount_signed" not in mapping and not {"debit", "credit"} <= set(mapping):
        raise AuditError("Map amount_signed or both debit and credit")
    headers, rows = _read_tabular(path, sheet)
    absent = {source for source in mapping.values() if source not in headers}
    if absent:
        raise AuditError(f"Mapped ledger headers are absent: {sorted(absent)}")
    normalized: list[dict[str, Any]] = []
    for source_row_number, source_row in enumerate(rows, start=2):
        row = {canonical: source_row[source] for canonical, source in mapping.items()}
        movement_id = _text(row.get("movement_id"))
        if not movement_id:
            raise AuditError(f"Ledger row {source_row_number} has no movement_id")
        debit = _decimal(row.get("debit")) or Decimal("0")
        credit = _decimal(row.get("credit")) or Decimal("0")
        signed = _decimal(row.get("amount_signed"))
        if signed is None:
            signed = debit - credit
        normalized.append(
            {
                canonical: _text(value)
                for canonical, value in row.items()
                if canonical not in {"amount_signed", "debit", "credit"}
            }
            | {
                "movement_id": movement_id,
                "source_row": source_row_number,
                "amount_signed": _money(signed),
                "debit": _money(debit),
                "credit": _money(credit),
                "source_file": path.name,
            }
        )
    return normalized


def _first_consistent(rows: Sequence[Mapping[str, Any]], key: str) -> str:
    values = {_text(row.get(key)) for row in rows if _text(row.get(key))}
    return next(iter(values)) if len(values) == 1 else ""


def _movement_groups(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_text(row["movement_id"])].append(row)
    movements: dict[str, dict[str, Any]] = {}
    for movement_id, lines in grouped.items():
        signed_total = sum(
            (
                _decimal(line.get("amount_signed"), allow_blank=False) or Decimal("0")
                for line in lines
            ),
            Decimal("0"),
        )
        explicit_gross = _decimal(_first_consistent(lines, "gross_amount"))
        fallback_gross = max(
            (
                abs(
                    _decimal(line.get("amount_signed"), allow_blank=False)
                    or Decimal("0")
                )
                for line in lines
            ),
            default=Decimal("0"),
        )
        movements[movement_id] = {
            "movement_id": movement_id,
            "entry_date": _first_consistent(lines, "entry_date"),
            "document_date": _first_consistent(lines, "document_date"),
            "supplier_tax_id": _first_consistent(lines, "supplier_tax_id"),
            "supplier_name": _first_consistent(lines, "supplier_name"),
            "invoice_number": _first_consistent(lines, "invoice_number"),
            "document_reference": _first_consistent(lines, "document_reference"),
            "currency": _first_consistent(lines, "currency"),
            "gross_amount": _money(explicit_gross),
            "gross_amount_comparison_basis": (
                "mapped_gross_amount"
                if explicit_gross is not None
                else "largest_absolute_line"
            ),
            "comparison_gross_amount": _money(explicit_gross or fallback_gross),
            "taxable_amount": _money(
                _decimal(_first_consistent(lines, "taxable_amount"))
            ),
            "vat_amount": _money(_decimal(_first_consistent(lines, "vat_amount"))),
            "signed_total": _money(signed_total),
            "balanced": abs(signed_total) <= CENT,
            "lines": [dict(line) for line in lines],
            "ledger_reference": f"{lines[0].get('source_file', '')}:movement={movement_id}",
        }
    return movements


def _invoice_amounts(
    invoice: Mapping[str, Any],
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    summaries = invoice.get("vat_summaries", [])
    taxable = sum(
        (_decimal(row.get("taxable_amount")) or Decimal("0") for row in summaries),
        Decimal("0"),
    )
    vat = sum(
        (_decimal(row.get("vat_amount")) or Decimal("0") for row in summaries),
        Decimal("0"),
    )
    return (
        _decimal(invoice.get("gross_amount")),
        taxable if summaries else None,
        vat if summaries else None,
    )


def _candidate_evidence(
    invoice: Mapping[str, Any],
    movement: Mapping[str, Any],
    tolerance: Decimal,
) -> list[str]:
    evidence: list[str] = []
    invoice_supplier = _normalized_identifier(invoice.get("supplier_vat"))
    movement_supplier = _normalized_identifier(movement.get("supplier_tax_id"))
    if invoice_supplier and movement_supplier and invoice_supplier == movement_supplier:
        evidence.append("supplier_tax_id_exact")
    invoice_number = _normalized_invoice_number(invoice.get("invoice_number"))
    references = {
        _normalized_invoice_number(movement.get("invoice_number")),
        _normalized_invoice_number(movement.get("document_reference")),
    } - {"0"}
    if invoice_number != "0" and invoice_number in references:
        evidence.append("invoice_number_exact")
    invoice_date = _text(invoice.get("invoice_date"))
    movement_dates = {
        _text(movement.get("document_date")),
        _text(movement.get("entry_date")),
    } - {""}
    if invoice_date and invoice_date in movement_dates:
        evidence.append("date_exact")
    gross, _, _ = _invoice_amounts(invoice)
    ledger_gross = _decimal(movement.get("comparison_gross_amount"))
    if (
        gross is not None
        and ledger_gross is not None
        and abs(abs(gross) - abs(ledger_gross)) <= tolerance
    ):
        evidence.append("gross_amount_exact")
    currency = _text(invoice.get("currency")).upper()
    ledger_currency = _text(movement.get("currency")).upper()
    if currency and ledger_currency and currency == ledger_currency:
        evidence.append("currency_exact")
    return evidence


def _qualifies_match(evidence: Sequence[str]) -> bool:
    evidence_set = set(evidence)
    if {"supplier_tax_id_exact", "invoice_number_exact"} <= evidence_set:
        return True
    if (
        "invoice_number_exact" in evidence_set
        and len(
            evidence_set & {"supplier_tax_id_exact", "date_exact", "gross_amount_exact"}
        )
        >= 1
    ):
        return True
    return {"supplier_tax_id_exact", "date_exact", "gross_amount_exact"} <= evidence_set


def _finding(
    code: str, severity: str, detail: str, evidence: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "detail": detail,
        "evidence": dict(evidence),
    }


def _deterministic_findings(
    invoice: Mapping[str, Any],
    movement: Mapping[str, Any] | None,
    match_state: str,
    duplicate: bool,
    tolerance: Decimal,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not invoice.get("xml_valid"):
        findings.append(
            _finding("xml_invalid", "exception", _text(invoice.get("parse_error")), {})
        )
    if duplicate:
        findings.append(
            _finding(
                "duplicate_invoice_candidate",
                "exception",
                "Same supplier, number, date and gross amount appear more than once",
                {},
            )
        )
    if match_state == "invoice_not_found_in_ledger":
        findings.append(
            _finding(
                "invoice_not_found_in_ledger",
                "exception",
                "No ledger movement met the reviewed exact-match rule",
                {},
            )
        )
    elif match_state == "ambiguous_match":
        findings.append(
            _finding(
                "ambiguous_ledger_match",
                "exception",
                "More than one ledger movement met the reviewed exact-match rule",
                {},
            )
        )
    gross, taxable, vat = _invoice_amounts(invoice)
    for summary in invoice.get("vat_summaries", []):
        rate = _decimal(summary.get("vat_rate"))
        base = _decimal(summary.get("taxable_amount"))
        tax = _decimal(summary.get("vat_amount"))
        nature = _text(summary.get("vat_nature"))
        if rate is not None and base is not None and tax is not None and not nature:
            expected = (base * rate / Decimal("100")).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            if abs(expected - tax) > tolerance:
                findings.append(
                    _finding(
                        "xml_vat_arithmetic_mismatch",
                        "exception",
                        "VAT summary does not reconcile mechanically",
                        {
                            "taxable_amount": _money(base),
                            "vat_rate": _money(rate),
                            "reported_vat": _money(tax),
                            "expected_vat": _money(expected),
                        },
                    )
                )
    if (
        gross is not None
        and taxable is not None
        and vat is not None
        and not invoice.get("withholdings")
    ):
        stamp = _decimal((invoice.get("stamp_duty") or {}).get("amount")) or Decimal(
            "0"
        )
        expected_gross = taxable + vat + stamp
        if abs(abs(gross) - abs(expected_gross)) > tolerance:
            findings.append(
                _finding(
                    "xml_total_arithmetic_mismatch",
                    "exception",
                    "Document total does not reconcile to taxable, VAT and stamp fields",
                    {
                        "reported_gross": _money(gross),
                        "computed_gross": _money(expected_gross),
                    },
                )
            )
    elif invoice.get("withholdings"):
        findings.append(
            _finding(
                "xml_total_not_mechanically_comparable",
                "information",
                "Withholding is present, so the document total is not forced through the ordinary gross arithmetic rule",
                {},
            )
        )
    if movement is None:
        return findings
    if not movement.get("balanced"):
        findings.append(
            _finding(
                "unbalanced_journal_entry",
                "exception",
                "Ledger movement debit and credit do not balance",
                {"signed_total": movement.get("signed_total")},
            )
        )
    ledger_gross = _decimal(movement.get("comparison_gross_amount"))
    if (
        gross is not None
        and ledger_gross is not None
        and abs(abs(gross) - abs(ledger_gross)) > tolerance
    ):
        findings.append(
            _finding(
                "invoice_booked_total_mismatch",
                "exception",
                "Invoice total differs from the ledger comparison amount",
                {
                    "invoice_gross": _money(gross),
                    "ledger_gross": _money(ledger_gross),
                    "basis": movement.get("gross_amount_comparison_basis"),
                },
            )
        )
    ledger_taxable = _decimal(movement.get("taxable_amount"))
    if (
        taxable is not None
        and ledger_taxable is not None
        and abs(abs(taxable) - abs(ledger_taxable)) > tolerance
    ):
        findings.append(
            _finding(
                "taxable_amount_mismatch",
                "exception",
                "Invoice taxable amount differs from the mapped ledger taxable amount",
                {
                    "invoice_taxable": _money(taxable),
                    "ledger_taxable": _money(ledger_taxable),
                },
            )
        )
    ledger_vat = _decimal(movement.get("vat_amount"))
    if (
        vat is not None
        and ledger_vat is not None
        and abs(abs(vat) - abs(ledger_vat)) > tolerance
    ):
        findings.append(
            _finding(
                "vat_amount_mismatch",
                "exception",
                "Invoice VAT differs from the mapped ledger VAT amount",
                {"invoice_vat": _money(vat), "ledger_vat": _money(ledger_vat)},
            )
        )
    invoice_currency = _text(invoice.get("currency")).upper()
    ledger_currency = _text(movement.get("currency")).upper()
    if invoice_currency and ledger_currency and invoice_currency != ledger_currency:
        findings.append(
            _finding(
                "currency_mismatch",
                "exception",
                "Invoice and ledger currencies differ",
                {
                    "invoice_currency": invoice_currency,
                    "ledger_currency": ledger_currency,
                },
            )
        )
    invoice_supplier = _normalized_identifier(invoice.get("supplier_vat"))
    ledger_supplier = _normalized_identifier(movement.get("supplier_tax_id"))
    if invoice_supplier and ledger_supplier and invoice_supplier != ledger_supplier:
        findings.append(
            _finding(
                "supplier_identifier_mismatch",
                "exception",
                "Supplier tax identifiers differ",
                {
                    "invoice_supplier": invoice_supplier,
                    "ledger_supplier": ledger_supplier,
                },
            )
        )
    invoice_number = _normalized_invoice_number(invoice.get("invoice_number"))
    ledger_number = _normalized_invoice_number(movement.get("invoice_number"))
    if (
        invoice_number != "0"
        and ledger_number != "0"
        and invoice_number != ledger_number
    ):
        findings.append(
            _finding(
                "document_reference_mismatch",
                "exception",
                "Invoice numbers differ",
                {
                    "invoice_number": invoice.get("invoice_number"),
                    "ledger_number": movement.get("invoice_number"),
                },
            )
        )
    if invoice.get("credit_note") and gross is not None:
        signs = {
            _decimal(line.get("amount_signed"), allow_blank=False).compare(Decimal("0"))
            for line in movement["lines"]
            if _decimal(line.get("amount_signed"), allow_blank=False) != 0
        }
        if len(signs) < 2:
            findings.append(
                _finding(
                    "credit_note_sign_unusual",
                    "exception",
                    "Credit-note posting does not contain both debit and credit directions",
                    {},
                )
            )
    return findings


def match_population(
    invoices: Sequence[Mapping[str, Any]],
    ledger_rows: Sequence[Mapping[str, Any]],
    tolerance: Decimal,
    metrics: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match invoice bodies to movements without forcing uncertain candidates."""

    matching_started = time.perf_counter()
    movements = _movement_groups(ledger_rows)
    duplicate_counts = Counter(
        (
            _normalized_identifier(invoice.get("supplier_vat")),
            _normalized_invoice_number(invoice.get("invoice_number")),
            _text(invoice.get("invoice_date")),
            _money(_decimal(invoice.get("gross_amount"))),
        )
        for invoice in invoices
        if invoice.get("xml_valid")
    )
    invoice_number_index: dict[str, set[str]] = defaultdict(set)
    supplier_date_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for movement_id, movement in movements.items():
        references = {
            _normalized_invoice_number(movement.get("invoice_number")),
            _normalized_invoice_number(movement.get("document_reference")),
        } - {"0"}
        for reference in references:
            invoice_number_index[reference].add(movement_id)
        supplier_id = _normalized_identifier(movement.get("supplier_tax_id"))
        dates = {
            _text(movement.get("document_date")),
            _text(movement.get("entry_date")),
        } - {""}
        if supplier_id:
            for movement_date in dates:
                supplier_date_index[(supplier_id, movement_date)].add(movement_id)
    candidate_sets: list[list[dict[str, Any]]] = []
    movement_candidate_counts: Counter[str] = Counter()
    candidate_comparisons = 0
    for invoice in invoices:
        candidates: list[dict[str, Any]] = []
        if invoice.get("xml_valid"):
            invoice_number = _normalized_invoice_number(invoice.get("invoice_number"))
            supplier_id = _normalized_identifier(invoice.get("supplier_vat"))
            invoice_date = _text(invoice.get("invoice_date"))
            possible_movement_ids: set[str] = set()
            if invoice_number != "0":
                possible_movement_ids.update(invoice_number_index[invoice_number])
            if supplier_id and invoice_date:
                possible_movement_ids.update(
                    supplier_date_index[(supplier_id, invoice_date)]
                )
            for movement_id in sorted(possible_movement_ids):
                movement = movements[movement_id]
                candidate_comparisons += 1
                evidence = _candidate_evidence(invoice, movement, tolerance)
                if _qualifies_match(evidence):
                    candidates.append({"movement": movement, "evidence": evidence})
                    movement_candidate_counts[str(movement["movement_id"])] += 1
        candidate_sets.append(candidates)
    matching_seconds = time.perf_counter() - matching_started
    deterministic_started = time.perf_counter()
    matched_ids: set[str] = set()
    items: list[dict[str, Any]] = []
    for invoice, candidates in zip(invoices, candidate_sets, strict=True):
        key = (
            _normalized_identifier(invoice.get("supplier_vat")),
            _normalized_invoice_number(invoice.get("invoice_number")),
            _text(invoice.get("invoice_date")),
            _money(_decimal(invoice.get("gross_amount"))),
        )
        duplicate = duplicate_counts[key] > 1 if invoice.get("xml_valid") else False
        uniquely_owned = (
            len(candidates) == 1
            and movement_candidate_counts[str(candidates[0]["movement"]["movement_id"])]
            == 1
        )
        if uniquely_owned and not duplicate:
            match_state = "matched"
            movement = candidates[0]["movement"]
            match_evidence = candidates[0]["evidence"]
            matched_ids.add(str(movement["movement_id"]))
        elif candidates and not duplicate:
            match_state = "ambiguous_match"
            movement = None
            match_evidence = [
                {
                    "movement_id": candidate["movement"]["movement_id"],
                    "evidence": candidate["evidence"],
                }
                for candidate in candidates
            ]
        elif duplicate:
            match_state = "duplicate_candidate"
            movement = candidates[0]["movement"] if len(candidates) == 1 else None
            match_evidence = candidates[0]["evidence"] if len(candidates) == 1 else []
        else:
            match_state = "invoice_not_found_in_ledger"
            movement = None
            match_evidence = []
        findings = _deterministic_findings(
            invoice, movement, match_state, duplicate, tolerance
        )
        items.append(
            {
                "invoice": dict(invoice),
                "match_state": match_state,
                "matched_movement": movement,
                "match_evidence": match_evidence,
                "deterministic_findings": findings,
            }
        )
    orphans = [
        dict(movement) | {"match_state": "ledger_entry_without_invoice"}
        for movement_id, movement in movements.items()
        if movement_id not in matched_ids
    ]
    if metrics is not None:
        metrics["matching_seconds"] = matching_seconds
        metrics["matching_candidate_comparisons"] = candidate_comparisons
        metrics["deterministic_check_seconds"] = (
            time.perf_counter() - deterministic_started
        )
    return items, orphans


def _expense_lines(movement: Mapping[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for line in movement.get("lines", []):
        account_type = _text(line.get("account_type")).lower()
        if account_type in {"supplier_payable", "input_vat", "vat", "payable"}:
            continue
        lines.append(
            {
                "account_code": _text(line.get("account_code")),
                "account_description": _text(line.get("account_description")),
                "line_description": _text(line.get("line_description")),
                "amount_signed": _text(line.get("amount_signed")),
            }
        )
    return lines or [
        {
            "account_code": _text(line.get("account_code")),
            "account_description": _text(line.get("account_description")),
            "line_description": _text(line.get("line_description")),
            "amount_signed": _text(line.get("amount_signed")),
        }
        for line in movement.get("lines", [])
    ]


def build_packet(
    item: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] = (),
    chart_of_accounts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the compact, source-backed semantic packet for one invoice."""

    invoice = item["invoice"]
    movement = item.get("matched_movement")
    if item.get("match_state") != "matched" or not movement:
        raise AuditError("Only matched invoices can form Luna packets")
    line_rows = []
    used_chars = 0
    truncated = False
    for line in invoice.get("lines", [])[:MAX_PACKET_LINES]:
        description = _text(line.get("description"))
        if used_chars + len(description) > MAX_PACKET_DESCRIPTION_CHARS:
            truncated = True
            break
        used_chars += len(description)
        line_rows.append(
            {
                "description": description,
                "quantity": _text(line.get("quantity")),
                "line_total": _text(line.get("line_total")),
                "vat_rate": _text(line.get("vat_rate")),
                "vat_nature": _text(line.get("vat_nature")),
            }
        )
    invoice_id = _text(invoice.get("invoice_id"))
    supplier_id = _normalized_identifier(invoice.get("supplier_vat"))
    selected_history = [
        row
        for row in history
        if invoice_id in row.get("relevant_to_invoice_ids", [])
        or (
            supplier_id
            and supplier_id == _normalized_identifier(row.get("supplier_tax_id"))
        )
    ]
    relevant_history = [
        {
            "invoice_description": _text(row.get("invoice_description")),
            "account_code": _text(row.get("account_code")),
            "account_description": _text(row.get("account_description")),
            "treatment_state": _text(row.get("treatment_state")),
        }
        for row in selected_history[:5]
    ]
    booked_treatment = _expense_lines(movement)
    chart = chart_of_accounts or {}
    return {
        "invoice_id": invoice["invoice_id"],
        "source_reference": invoice.get("source_identifier"),
        "supplier": {
            "name": invoice.get("supplier_name", ""),
            "tax_id": invoice.get("supplier_vat", ""),
        },
        "invoice_number": invoice.get("invoice_number", ""),
        "invoice_date": invoice.get("invoice_date", ""),
        "document_type": invoice.get("document_type", ""),
        "currency": invoice.get("currency", ""),
        "gross_amount": invoice.get("gross_amount", ""),
        "invoice_lines": line_rows,
        "invoice_lines_truncated": truncated
        or len(invoice.get("lines", [])) > len(line_rows),
        "vat_summaries": invoice.get("vat_summaries", []),
        "flags": {
            "credit_note": invoice.get("credit_note", False),
            "split_payment": invoice.get("split_payment", False),
            "reverse_charge": invoice.get("reverse_charge", False),
        },
        "actual_accounting_treatment": [
            line
            | {"client_chart_description": _text(chart.get(line["account_code"], ""))}
            for line in booked_treatment
        ],
        "ledger_reference": movement.get("ledger_reference"),
        "deterministic_findings": item.get("deterministic_findings", []),
        "relevant_history": relevant_history,
        "history_is_supporting_evidence_not_a_prerequisite": True,
    }


def luna_output_schema(invoice_ids: Sequence[str]) -> dict[str, Any]:
    """Return the strict structured-output schema for one Luna chunk."""

    return {
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": ["vera.passive_invoice_luna.v1"],
            },
            "results": {
                "type": "array",
                "minItems": len(invoice_ids),
                "maxItems": len(invoice_ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "enum": list(invoice_ids)},
                        "status": {"type": "string", "enum": sorted(SEMANTIC_STATUSES)},
                        "short_reason": {"type": "string", "maxLength": 600},
                        "suspected_issue_type": {
                            "type": "string",
                            "enum": sorted(ISSUE_TYPES),
                        },
                        "invoice_evidence": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 400},
                            "maxItems": 6,
                        },
                        "booked_account_evidence": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 400},
                            "maxItems": 6,
                        },
                        "professional_should_inspect": {
                            "type": "string",
                            "maxLength": 600,
                        },
                    },
                    "required": [
                        "invoice_id",
                        "status",
                        "short_reason",
                        "suspected_issue_type",
                        "invoice_evidence",
                        "booked_account_evidence",
                        "professional_should_inspect",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["schema_version", "results"],
        "additionalProperties": False,
    }


def build_luna_prompt(packets: Sequence[Mapping[str, Any]]) -> str:
    """Build a bounded batch prompt that preserves invoice-level independence."""

    return """You are the semantic second reviewer in Vera's Intelligent Passive-Invoice Audit.

Review each packet independently. Never let another packet determine this invoice's result. Use the invoice lines as primary evidence, the actual booked expense/asset accounts, normal economic/world knowledge, and only then relevant history as additional evidence.

Narrow question: given the invoice's economic substance and the accounting treatment actually recorded, is there a material reason this invoice deserves professional review?

Return no_issue_detected only when no concrete material review reason is visible. This does not mean correct, approved, verified, or audit passed. Return review_required for a concrete accounting/economic inconsistency or material judgment issue. Return insufficient_evidence when the packet itself lacks evidence needed for this narrow screen. Do not recreate the complete booking. Do not redo arithmetic or override deterministic findings. Supplier identity alone is never enough where the lines may change the substance. First-ever suppliers can still be semantically clear. Do not invent percentages or confidence scores.

For no_issue_detected, suspected_issue_type must be none and the inspection field may be empty. For either exception status, cite specific invoice and booked-account evidence and state what the professional should inspect. Return exactly one result for each invoice_id and no additional invoices.

PACKETS_JSON:
""" + json.dumps(
        list(packets), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def chunk_semantic_packets(
    packets: Sequence[Mapping[str, Any]],
    max_items: int,
    max_prompt_bytes: int = MAX_LUNA_PROMPT_BYTES,
) -> list[list[Mapping[str, Any]]]:
    """Build bounded chunks without splitting or merging invoice decisions."""

    if max_items < 1 or max_prompt_bytes < 1:
        raise AuditError("Semantic chunk limits must be positive")
    chunks: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for packet in packets:
        tentative = [*current, packet]
        prompt_too_large = (
            len(build_luna_prompt(tentative).encode("utf-8")) > max_prompt_bytes
        )
        if current and (len(tentative) > max_items or prompt_too_large):
            chunks.append(current)
            current = [packet]
        else:
            current = tentative
        if len(build_luna_prompt(current).encode("utf-8")) > max_prompt_bytes:
            raise AuditError(
                f"Semantic packet exceeds the {max_prompt_bytes}-byte prompt limit"
            )
    if current:
        chunks.append(current)
    return chunks


def validate_luna_result(
    payload: Mapping[str, Any], invoice_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Strictly validate Luna output beyond JSON-schema enforcement."""

    if set(payload) != {"schema_version", "results"}:
        raise AuditError("Luna response has unexpected top-level fields")
    if payload.get("schema_version") != "vera.passive_invoice_luna.v1":
        raise AuditError("Luna response schema version is invalid")
    results = payload.get("results")
    if not isinstance(results, list):
        raise AuditError("Luna results must be an array")
    expected = list(invoice_ids)
    actual = [
        _text(result.get("invoice_id"))
        for result in results
        if isinstance(result, dict)
    ]
    if (
        len(results) != len(expected)
        or sorted(actual) != sorted(expected)
        or len(set(actual)) != len(actual)
    ):
        raise AuditError(
            "Luna response must contain each requested invoice exactly once"
        )
    validated: dict[str, dict[str, Any]] = {}
    required = {
        "invoice_id",
        "status",
        "short_reason",
        "suspected_issue_type",
        "invoice_evidence",
        "booked_account_evidence",
        "professional_should_inspect",
    }
    for result in results:
        if not isinstance(result, dict) or set(result) != required:
            raise AuditError("Luna invoice result has unexpected fields")
        status = result["status"]
        issue_type = result["suspected_issue_type"]
        if status not in SEMANTIC_STATUSES or issue_type not in ISSUE_TYPES:
            raise AuditError("Luna invoice result has an invalid enum")
        if status == "no_issue_detected" and issue_type != "none":
            raise AuditError("no_issue_detected must use suspected_issue_type=none")
        if status != "no_issue_detected" and issue_type == "none":
            raise AuditError("Exception result must identify an issue type")
        for key in ("invoice_evidence", "booked_account_evidence"):
            if not isinstance(result[key], list) or any(
                not isinstance(value, str) for value in result[key]
            ):
                raise AuditError(f"Luna {key} must be a string array")
        if status != "no_issue_detected" and (
            not result["short_reason"].strip()
            or not result["invoice_evidence"]
            or not result["booked_account_evidence"]
            or not result["professional_should_inspect"].strip()
        ):
            raise AuditError("Luna exception result lacks specific review evidence")
        validated[result["invoice_id"]] = dict(result)
    return validated


def _open_database(path: Path, fingerprint: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_items (
            invoice_id TEXT PRIMARY KEY,
            packet_sha256 TEXT,
            item_json TEXT NOT NULL,
            packet_json TEXT,
            semantic_json TEXT,
            semantic_model TEXT,
            semantic_effort TEXT,
            chunk_id TEXT,
            final_state TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            packet_sha256 TEXT NOT NULL,
            invoice_ids_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL,
            error TEXT,
            usage_json TEXT,
            duration_ms INTEGER,
            completed_at TEXT
        );
        """)
    existing = connection.execute(
        "SELECT value FROM metadata WHERE key='run_fingerprint'"
    ).fetchone()
    if existing and existing[0] != fingerprint:
        connection.close()
        raise AuditError(
            "Existing audit database belongs to different inputs or controls"
        )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES('run_fingerprint',?)",
        (fingerprint,),
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)",
        (SCHEMA_VERSION,),
    )
    connection.execute(
        "UPDATE chunks SET status='pending', error='interrupted before completion' WHERE status='running'"
    )
    connection.commit()
    return connection


def _input_fingerprint(
    invoice_source: Path,
    ledger_path: Path,
    mapping_path: Path,
    config: AuditConfig,
    *,
    ledger_sheet: str | None,
    history: Sequence[Mapping[str, Any]],
    chart_of_accounts: Mapping[str, str] | None,
) -> str:
    if invoice_source.is_dir():
        invoice_manifest = [
            [
                path.relative_to(invoice_source).as_posix(),
                _sha256_file(path),
            ]
            for path in sorted(invoice_source.rglob("*"))
            if path.is_file() and path.suffix.lower() == ".xml"
        ]
    else:
        invoice_manifest = [[invoice_source.name, _sha256_file(invoice_source)]]
    return _sha256_json(
        {
            "workflow_version": WORKFLOW_VERSION,
            "invoice_manifest": invoice_manifest,
            "ledger_sha256": _sha256_file(ledger_path),
            "mapping_sha256": _sha256_file(mapping_path),
            "ledger_sheet": ledger_sheet,
            "history_sha256": _sha256_json(list(history)),
            "chart_of_accounts_sha256": _sha256_json(chart_of_accounts or {}),
            "controls": {
                "chunk_size": config.chunk_size,
                "reasoning_effort": config.reasoning_effort,
                "amount_tolerance": str(config.amount_tolerance),
            },
        }
    )


def _execute_chunk(
    chunk_id: str,
    packets: Sequence[Mapping[str, Any]],
    output_dir: Path,
    config: AuditConfig,
    runner: LunaRunner,
) -> dict[str, Any]:
    invoice_ids = [str(packet["invoice_id"]) for packet in packets]
    packet_sha256 = _sha256_json(packets)
    chunk_dir = output_dir / "luna_chunks" / chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_luna_prompt(packets)
    schema = luna_output_schema(invoice_ids)
    (chunk_dir / "audit_packets.json").write_bytes(_json_bytes(list(packets)))
    (chunk_dir / "luna_prompt.md").write_text(prompt, encoding="utf-8")
    (chunk_dir / "luna_output_schema.json").write_bytes(_json_bytes(schema))
    result = runner(
        prompt, schema, chunk_dir, WORKFLOW_ID, packet_sha256, config.reasoning_effort
    )
    payload = result.get("response_payload")
    if not isinstance(payload, Mapping):
        raise AuditError("Luna runner did not return a structured payload")
    validated = validate_luna_result(payload, invoice_ids)
    return {
        "chunk_id": chunk_id,
        "packet_sha256": packet_sha256,
        "invoice_ids": invoice_ids,
        "results": validated,
        "usage": result.get("usage", {}),
        "duration_ms": int(result.get("duration_ms", 0)),
        "model": result.get("model"),
        "reasoning_effort": result.get("reasoning_effort"),
    }


def _finalize_item(
    item: Mapping[str, Any], semantic: Mapping[str, Any] | None
) -> tuple[str, list[str]]:
    reasons = [
        finding["code"]
        for finding in item.get("deterministic_findings", [])
        if finding.get("severity") == "exception"
    ]
    if semantic and semantic.get("status") != "no_issue_detected":
        reasons.append(_text(semantic.get("suspected_issue_type")))
    if reasons:
        return "professional_review_required", sorted(set(reasons))
    if semantic is None:
        return "professional_review_required", ["semantic_review_not_completed"]
    return "no_issue_detected", []


def _write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(_json_bytes(value).decode("utf-8"))


def _write_exception_workpaper(
    path: Path,
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    orphans: Sequence[Mapping[str, Any]],
) -> None:
    workbook = Workbook(
        path,
        {"strings_to_formulas": False, "strings_to_urls": False},
    )
    title_format = workbook.add_format(
        {"bold": True, "font_size": 16, "font_color": "#173F67"}
    )
    header_format = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#173F67", "border": 1}
    )
    wrap_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    summary_sheet = workbook.add_worksheet("Summary")
    summary_sheet.write("A1", "Vera — Intelligent Passive-Invoice Audit", title_format)
    summary_sheet.write("A3", "Metric", header_format)
    summary_sheet.write("B3", "Value", header_format)
    for row_number, (key, value) in enumerate(summary.items(), start=3):
        summary_sheet.write(row_number, 0, key)
        summary_sheet.write(
            row_number, 1, value if isinstance(value, (int, float)) else _text(value)
        )
    summary_sheet.set_column("A:A", 38)
    summary_sheet.set_column("B:B", 24)
    exception_sheet = workbook.add_worksheet("Exceptions")
    columns = [
        "invoice_id",
        "source_reference",
        "supplier",
        "invoice_number",
        "invoice_date",
        "gross_amount",
        "booked_accounts",
        "match_state",
        "final_exception_reasons",
        "luna_status",
        "luna_reason",
        "invoice_evidence",
        "booked_account_evidence",
        "professional_should_inspect",
        "ledger_reference",
    ]
    for index, column in enumerate(columns):
        exception_sheet.write(0, index, column, header_format)
    for row_number, row in enumerate(rows, start=1):
        invoice = row["invoice"]
        movement = row.get("matched_movement") or {}
        semantic = row.get("semantic_result") or {}
        values = [
            invoice.get("invoice_id"),
            invoice.get("source_identifier"),
            invoice.get("supplier_name"),
            invoice.get("invoice_number"),
            invoice.get("invoice_date"),
            invoice.get("gross_amount"),
            " | ".join(
                f"{line.get('account_code')} — {line.get('account_description')}"
                for line in _expense_lines(movement)
            ),
            row.get("match_state"),
            " | ".join(row.get("final_exception_reasons", [])),
            semantic.get("status", "not_run"),
            semantic.get("short_reason", ""),
            " | ".join(semantic.get("invoice_evidence", [])),
            " | ".join(semantic.get("booked_account_evidence", [])),
            semantic.get("professional_should_inspect", ""),
            movement.get("ledger_reference", ""),
        ]
        for column_number, value in enumerate(values):
            exception_sheet.write(row_number, column_number, value, wrap_format)
    exception_sheet.freeze_panes(1, 0)
    exception_sheet.autofilter(0, 0, max(len(rows), 1), len(columns) - 1)
    exception_sheet.set_column(0, 5, 18)
    exception_sheet.set_column(6, 14, 32)
    orphan_sheet = workbook.add_worksheet("Ledger Orphans")
    orphan_columns = [
        "movement_id",
        "entry_date",
        "supplier_tax_id",
        "supplier_name",
        "invoice_number",
        "comparison_gross_amount",
        "currency",
        "ledger_reference",
    ]
    for index, column in enumerate(orphan_columns):
        orphan_sheet.write(0, index, column, header_format)
    for row_number, orphan in enumerate(orphans, start=1):
        for column_number, column in enumerate(orphan_columns):
            orphan_sheet.write(
                row_number, column_number, orphan.get(column, ""), wrap_format
            )
    orphan_sheet.freeze_panes(1, 0)
    orphan_sheet.autofilter(0, 0, max(len(orphans), 1), len(orphan_columns) - 1)
    orphan_sheet.set_column(0, len(orphan_columns) - 1, 22)
    workbook.close()


def run_audit(
    *,
    invoice_source: Path,
    ledger_path: Path,
    mapping_path: Path,
    output_dir: Path,
    runner: LunaRunner,
    config: AuditConfig = AuditConfig(),
    ledger_sheet: str | None = None,
    history: Sequence[Mapping[str, Any]] = (),
    chart_of_accounts: Mapping[str, str] | None = None,
    client_run_id: str | None = None,
    client_run_root: Path | None = None,
) -> dict[str, Any]:
    """Run or resume the complete local audit and write exception-focused outputs."""

    config.validate()
    if (client_run_id is None) != (client_run_root is None):
        raise AuditError("client_run_id and client_run_root must be supplied together")
    started = time.perf_counter()
    output_dir = output_dir.expanduser().resolve()
    if client_run_root is not None:
        managed_run_root = client_run_root.expanduser().resolve()
        if not output_dir.is_relative_to(managed_run_root):
            raise AuditError("Audit output leaves the managed customer run")
    output_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = _input_fingerprint(
        invoice_source,
        ledger_path,
        mapping_path,
        config,
        ledger_sheet=ledger_sheet,
        history=history,
        chart_of_accounts=chart_of_accounts,
    )
    connection = _open_database(output_dir / "audit.sqlite3", fingerprint)
    parse_started = time.perf_counter()
    invoices = parse_invoice_population(invoice_source, output_dir / ".invoice_staging")
    parse_seconds = time.perf_counter() - parse_started
    ledger_rows = load_ledger(ledger_path, mapping_path, sheet=ledger_sheet)
    timing: dict[str, float] = {}
    items, orphans = match_population(
        invoices, ledger_rows, config.amount_tolerance, metrics=timing
    )
    packets: list[dict[str, Any]] = []
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        invoice_id = str(item["invoice"]["invoice_id"])
        packet = (
            build_packet(item, history, chart_of_accounts)
            if item["match_state"] == "matched"
            else None
        )
        packet_sha256 = _sha256_json(packet) if packet else None
        existing = connection.execute(
            "SELECT packet_sha256, semantic_json FROM audit_items WHERE invoice_id=?",
            (invoice_id,),
        ).fetchone()
        if existing and existing[0] != packet_sha256:
            connection.close()
            raise AuditError(f"Stored packet changed for invoice {invoice_id}")
        connection.execute(
            "INSERT INTO audit_items(invoice_id,packet_sha256,item_json,packet_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(invoice_id) DO UPDATE SET item_json=excluded.item_json, packet_json=excluded.packet_json, updated_at=excluded.updated_at",
            (
                invoice_id,
                packet_sha256,
                _json_bytes(item).decode("utf-8"),
                _json_bytes(packet).decode("utf-8") if packet else None,
                _now(),
            ),
        )
        item_by_id[invoice_id] = item
        if packet and not (existing and existing[1]):
            packets.append(packet)
    connection.commit()
    chunks = chunk_semantic_packets(packets, config.chunk_size)
    pending: list[tuple[str, list[dict[str, Any]]]] = []
    for chunk in chunks:
        digest = _sha256_json(chunk)
        chunk_id = f"chunk-{digest[:16]}"
        row = connection.execute(
            "SELECT status,packet_sha256 FROM chunks WHERE chunk_id=?", (chunk_id,)
        ).fetchone()
        if row and row[0] == "completed" and row[1] == digest:
            continue
        connection.execute(
            "INSERT INTO chunks(chunk_id,packet_sha256,invoice_ids_json,status,attempt_count) VALUES(?,?,?,?,0) ON CONFLICT(chunk_id) DO UPDATE SET status='pending', error=NULL",
            (
                chunk_id,
                digest,
                json.dumps([packet["invoice_id"] for packet in chunk]),
                "pending",
            ),
        )
        pending.append((chunk_id, chunk))
    connection.commit()
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        future_map = {}
        for chunk_id, chunk in pending:
            connection.execute(
                "UPDATE chunks SET status='running', attempt_count=attempt_count+1 WHERE chunk_id=?",
                (chunk_id,),
            )
            future_map[
                executor.submit(
                    _execute_chunk, chunk_id, chunk, output_dir, config, runner
                )
            ] = (chunk_id, chunk)
        connection.commit()
        for future in as_completed(future_map):
            chunk_id, chunk = future_map[future]
            attempt = 0
            while True:
                try:
                    result = (
                        future.result()
                        if attempt == 0
                        else _execute_chunk(chunk_id, chunk, output_dir, config, runner)
                    )
                    break
                except (AuditError, OSError, ValueError) as exc:
                    attempt += 1
                    if attempt > config.max_retries:
                        failures[chunk_id] = str(exc)
                        connection.execute(
                            "UPDATE chunks SET status='failed', error=? WHERE chunk_id=?",
                            (str(exc), chunk_id),
                        )
                        result = None
                        break
                    connection.execute(
                        "UPDATE chunks SET attempt_count=attempt_count+1, error=? WHERE chunk_id=?",
                        (str(exc), chunk_id),
                    )
                    connection.commit()
            if result is None:
                continue
            for invoice_id, semantic in result["results"].items():
                connection.execute(
                    "UPDATE audit_items SET semantic_json=?,semantic_model=?,semantic_effort=?,chunk_id=?,updated_at=? WHERE invoice_id=?",
                    (
                        _json_bytes(semantic).decode("utf-8"),
                        result["model"],
                        result["reasoning_effort"],
                        chunk_id,
                        _now(),
                        invoice_id,
                    ),
                )
            connection.execute(
                "UPDATE chunks SET status='completed',error=NULL,usage_json=?,duration_ms=?,completed_at=? WHERE chunk_id=?",
                (
                    _json_bytes(result["usage"]).decode("utf-8"),
                    result["duration_ms"],
                    _now(),
                    chunk_id,
                ),
            )
            connection.commit()
    complete_rows: list[dict[str, Any]] = []
    for invoice_id, item in item_by_id.items():
        stored = connection.execute(
            "SELECT semantic_json,semantic_model,semantic_effort,chunk_id FROM audit_items WHERE invoice_id=?",
            (invoice_id,),
        ).fetchone()
        semantic = json.loads(stored[0]) if stored and stored[0] else None
        final_state, final_reasons = _finalize_item(item, semantic)
        final_item = dict(item) | {
            "schema_version": SCHEMA_VERSION,
            "semantic_packet": (
                build_packet(item, history, chart_of_accounts)
                if item["match_state"] == "matched"
                else None
            ),
            "semantic_model": stored[1] if stored else None,
            "semantic_reasoning_effort": stored[2] if stored else None,
            "semantic_chunk_id": stored[3] if stored else None,
            "semantic_result": semantic,
            "final_state": final_state,
            "final_exception_reasons": final_reasons,
            "processed_at": _now(),
            "workflow_version": WORKFLOW_VERSION,
            "client_run_id": client_run_id,
        }
        complete_rows.append(final_item)
        connection.execute(
            "UPDATE audit_items SET final_state=?,updated_at=? WHERE invoice_id=?",
            (final_state, _now(), invoice_id),
        )
    connection.commit()
    chunk_rows = connection.execute(
        "SELECT status,attempt_count,usage_json,duration_ms FROM chunks"
    ).fetchall()
    semantic_counts = Counter(
        (row.get("semantic_result") or {}).get("status", "not_run")
        for row in complete_rows
    )
    match_counts = Counter(row["match_state"] for row in complete_rows)
    deterministic_exception_count = sum(
        any(
            finding.get("severity") == "exception"
            for finding in row["deterministic_findings"]
        )
        for row in complete_rows
    )
    review_rows = [
        row
        for row in complete_rows
        if row["final_state"] == "professional_review_required"
    ]
    total_seconds = time.perf_counter() - started
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_fingerprint": fingerprint,
        "client_run_id": client_run_id,
        "population": len(complete_rows),
        "matched": match_counts["matched"],
        "ambiguous_match": match_counts["ambiguous_match"],
        "invoice_not_found_in_ledger": match_counts["invoice_not_found_in_ledger"],
        "duplicate_candidate": match_counts["duplicate_candidate"],
        "ledger_entry_without_invoice": len(orphans),
        "deterministic_exceptions": deterministic_exception_count,
        "luna_no_issue_detected": semantic_counts["no_issue_detected"],
        "luna_review_required": semantic_counts["review_required"],
        "luna_insufficient_evidence": semantic_counts["insufficient_evidence"],
        "luna_not_run_or_failed": semantic_counts["not_run"],
        "invoices_requiring_professional_attention": len(review_rows),
        "exception_rate": (
            round(len(review_rows) / len(complete_rows), 6) if complete_rows else 0
        ),
        "invoices_parsed_per_second": round(
            len(invoices) / max(parse_seconds, 0.000001), 2
        ),
        "parse_seconds": round(parse_seconds, 4),
        "matching_seconds": round(timing["matching_seconds"], 4),
        "matching_candidate_comparisons": int(timing["matching_candidate_comparisons"]),
        "deterministic_check_seconds": round(timing["deterministic_check_seconds"], 4),
        "luna_invoices_sent": sum(
            len(json.loads(row[2]))
            for row in connection.execute(
                "SELECT chunk_id,packet_sha256,invoice_ids_json FROM chunks WHERE status='completed'"
            )
        ),
        "luna_chunks_total": len(chunk_rows),
        "luna_chunks_completed": sum(row[0] == "completed" for row in chunk_rows),
        "luna_chunks_failed": sum(row[0] == "failed" for row in chunk_rows),
        "luna_processing_failures_retries": sum(
            max(row[1] - 1, 0) for row in chunk_rows
        ),
        "luna_usage": [json.loads(row[2]) for row in chunk_rows if row[2]],
        "luna_duration_ms": sum(row[3] or 0 for row in chunk_rows),
        "total_wall_clock_seconds": round(total_seconds, 4),
        "completed_at": _now(),
        "limitations": [
            "no_issue_detected is a screening result, not proof of correct accounting treatment",
            "ledger matching quality depends on the reviewed column map and source references",
            "largest_absolute_line is only a fallback gross-comparison basis when no mapped gross amount is supplied",
        ],
    }
    _write_jsonl(output_dir / "full_population.jsonl", complete_rows)
    _write_jsonl(output_dir / "ledger_entries_without_invoice.jsonl", orphans)
    (output_dir / "run_summary.json").write_bytes(_json_bytes(summary))
    (output_dir / "run_summary.md").write_text(
        "# Vera — Intelligent Passive-Invoice Audit\n\n"
        + "\n".join(
            f"- {key}: {value}"
            for key, value in summary.items()
            if key not in {"limitations", "luna_usage"}
        )
        + "\n\n`no_issue_detected` is a screening result, not proof that accounting treatment is correct.\n",
        encoding="utf-8",
    )
    _write_exception_workpaper(
        output_dir / "exception_workpaper.xlsx", summary, review_rows, orphans
    )
    connection.close()
    if failures:
        raise AuditError(
            f"Luna chunks failed after retries; resume the same job: {failures}"
        )
    return summary


def evaluate_results(
    results_path: Path, labels_path: Path, output_path: Path | None = None
) -> dict[str, Any]:
    """Measure material-issue recall, false positives, and human review rate."""

    results = {
        row["invoice"]["invoice_id"]: row
        for row in (
            json.loads(line)
            for line in results_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    labels = [
        json.loads(line)
        for line in labels_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    valid_labels = {"problematic", "acceptable", "ambiguous"}
    if any(label.get("label") not in valid_labels for label in labels):
        raise AuditError(
            "Evaluation labels must be problematic, acceptable, or ambiguous"
        )
    missing = [
        label["invoice_id"] for label in labels if label["invoice_id"] not in results
    ]
    if missing:
        raise AuditError(f"Labelled invoices are missing from results: {missing}")
    problematic = [label for label in labels if label["label"] == "problematic"]
    acceptable = [label for label in labels if label["label"] == "acceptable"]
    flagged = (
        lambda invoice_id: results[invoice_id]["final_state"]
        == "professional_review_required"
    )
    missed = [
        {
            "invoice_id": label["invoice_id"],
            "known_issue": label.get("known_issue", ""),
            "observed_semantic_status": (
                results[label["invoice_id"]].get("semantic_result") or {}
            ).get("status", "not_run"),
        }
        for label in problematic
        if not flagged(label["invoice_id"])
    ]
    report = {
        "schema_version": "vera.passive_invoice_evaluation.v1",
        "labelled_population": len(labels),
        "problematic_population": len(problematic),
        "acceptable_population": len(acceptable),
        "exception_recall": (
            sum(flagged(label["invoice_id"]) for label in problematic)
            / len(problematic)
            if problematic
            else None
        ),
        "false_positive_rate": (
            sum(flagged(label["invoice_id"]) for label in acceptable) / len(acceptable)
            if acceptable
            else None
        ),
        "human_review_rate": (
            sum(flagged(label["invoice_id"]) for label in labels) / len(labels)
            if labels
            else None
        ),
        "missed_material_issues": missed,
        "evaluated_at": _now(),
    }
    if output_path:
        output_path.write_bytes(_json_bytes(report))
    return report


def create_synthetic_population(
    full_population_path: Path,
    mutation_plan_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    """Create clearly labelled packet copies with controlled wrong accounts."""

    rows = [
        json.loads(line)
        for line in full_population_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {row["invoice"]["invoice_id"]: row for row in rows}
    plan = json.loads(mutation_plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, list):
        raise AuditError("Synthetic mutation plan must be an array")
    generated: list[dict[str, Any]] = []
    for mutation in plan:
        invoice_id = _text(mutation.get("invoice_id"))
        replacement_code = _text(mutation.get("replacement_account_code"))
        replacement_description = _text(mutation.get("replacement_account_description"))
        if (
            invoice_id not in by_id
            or not replacement_code
            or not replacement_description
        ):
            raise AuditError(
                "Synthetic mutation must identify an existing invoice and replacement account"
            )
        source_packet = by_id[invoice_id].get("semantic_packet")
        if not source_packet:
            raise AuditError(f"Invoice {invoice_id} has no semantic packet to corrupt")
        packet = json.loads(json.dumps(source_packet))
        original = packet["actual_accounting_treatment"]
        packet["invoice_id"] = f"synthetic:{invoice_id}:{len(generated) + 1}"
        packet["actual_accounting_treatment"] = [
            {
                "account_code": replacement_code,
                "account_description": replacement_description,
                "line_description": "CONTROLLED SYNTHETIC CORRUPTION",
                "amount_signed": line.get("amount_signed", ""),
            }
            for line in original
        ]
        generated.append(
            {
                "schema_version": "vera.passive_invoice_synthetic.v1",
                "synthetic": True,
                "source_invoice_id": invoice_id,
                "mutation_label": _text(mutation.get("label"))
                or "materially_wrong_account_substitution",
                "original_treatment": original,
                "packet": packet,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_path, generated)
    return generated


def evaluate_synthetic_population(
    full_population_path: Path,
    mutation_plan_path: Path,
    output_dir: Path,
    runner: LunaRunner,
    config: AuditConfig = AuditConfig(),
) -> dict[str, Any]:
    """Run controlled corruptions through Luna and report detection recall."""

    config.validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = create_synthetic_population(
        full_population_path,
        mutation_plan_path,
        output_dir / "synthetic_packets.jsonl",
    )
    packets = [row["packet"] for row in generated]
    chunks = chunk_semantic_packets(packets, config.chunk_size)

    def execute_with_retry(
        chunk_id: str, chunk: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        last_error = ""
        for _attempt in range(config.max_retries + 1):
            try:
                return _execute_chunk(chunk_id, chunk, output_dir, config, runner)
            except (AuditError, OSError, ValueError) as exc:
                last_error = str(exc)
        raise AuditError(
            f"Synthetic Luna chunk failed after retries: {chunk_id}: {last_error}"
        )

    results: dict[str, dict[str, Any]] = {}
    usage: list[Mapping[str, Any]] = []
    duration_ms = 0
    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {}
        for chunk in chunks:
            digest = _sha256_json(chunk)
            chunk_id = f"synthetic-chunk-{digest[:16]}"
            futures[executor.submit(execute_with_retry, chunk_id, chunk)] = chunk_id
        for future in as_completed(futures):
            chunk_result = future.result()
            results.update(chunk_result["results"])
            usage.append(chunk_result["usage"])
            duration_ms += chunk_result["duration_ms"]

    result_rows = [
        row | {"semantic_result": results[row["packet"]["invoice_id"]]}
        for row in generated
    ]
    _write_jsonl(output_dir / "synthetic_results.jsonl", result_rows)
    missed = [
        {
            "invoice_id": row["packet"]["invoice_id"],
            "source_invoice_id": row["source_invoice_id"],
            "mutation_label": row["mutation_label"],
        }
        for row in result_rows
        if row["semantic_result"]["status"] == "no_issue_detected"
    ]
    flagged = len(result_rows) - len(missed)
    report = {
        "schema_version": "vera.passive_invoice_synthetic_evaluation.v1",
        "synthetic_population": len(result_rows),
        "exception_recall": (flagged / len(result_rows) if result_rows else None),
        "human_review_rate": (flagged / len(result_rows) if result_rows else None),
        "missed_material_issues": missed,
        "luna_chunks": len(chunks),
        "luna_usage": usage,
        "luna_duration_ms": duration_ms,
        "evaluated_at": _now(),
        "limitation": (
            "Synthetic substitutions are regression evidence and do not replace "
            "labelled real-world validation."
        ),
    }
    (output_dir / "synthetic_evaluation.json").write_bytes(_json_bytes(report))
    return report

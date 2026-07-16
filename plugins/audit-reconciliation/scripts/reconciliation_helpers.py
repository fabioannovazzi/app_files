"""Reusable helper functions for Codex audit reconciliation workflows.

These helpers are intentionally not a standalone product CLI. A Codex skill can
import or copy them into a case-specific workpaper script when deterministic
parsing, matching, or reporting logic is needed.
"""

from __future__ import annotations

import html
import hashlib
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

try:
    from .locale_support import (
        any_keyword_in,
        configured_language,
        keyword_tuple,
        language_candidates,
        missing_evidence_messages,
    )
except ImportError:  # pragma: no cover - direct import support
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from locale_support import any_keyword_in, configured_language, keyword_tuple, language_candidates, missing_evidence_messages  # type: ignore


CANONICAL_FIELDS = [
    "record_id",
    "source_file",
    "source_sheet",
    "source_page",
    "source_row",
    "source_role",
    "party",
    "counterparty",
    "account",
    "document_no",
    "document_date",
    "posting_date",
    "amount",
    "currency",
    "direction",
    "description",
    "evidence_type",
    "document_key",
]


DEFAULT_ASSUMPTIONS = {
    "scope_year": None,
    "cutoff_date": None,
    "report_language": "it",
    "document_language": "auto",
    "payment_orders_are_bank_evidence": False,
    "compensation_requires_bank": False,
    "factoring_pro_soluto_closes_item": True,
    "factoring_operator_keywords": [],
    "post_cutoff_events_excluded": True,
    "promote_probable_bank_payments": False,
    "probable_bank_exact_matches_close": False,
    "amount_tolerance": "0.01",
    "document_date_tolerance_days": "7",
}


ROLE_KEYWORDS = {
    role: sorted(
        {
            keyword
            for language in language_candidates("auto")
            for keyword in keyword_tuple(language, "role_keywords", role)
        }
    )
    for role in (
        "bank_statement",
        "factoring_statement",
        "payment_order",
        "journal",
        "ledger",
        "open_items",
    )
}

FACTOR_KEYWORDS = tuple(
    sorted(
        {
            keyword
            for language in language_candidates("auto")
            for keyword in keyword_tuple(language, "evidence_keywords", "factoring")
        }
    )
)

BANK_KEYWORDS = tuple(
    sorted(
        {
            keyword
            for language in language_candidates("auto")
            for keyword in keyword_tuple(language, "evidence_keywords", "bank")
        }
    )
)
COMPENSATION_KEYWORDS = tuple(
    sorted(
        {
            keyword
            for language in language_candidates("auto")
            for keyword in (
                keyword_tuple(language, "evidence_keywords", "compensation")
                + keyword_tuple(language, "evidence_keywords", "netting")
            )
        }
    )
)
BATCH_KEYWORDS = tuple(
    sorted(
        {
            keyword
            for language in language_candidates("auto")
            for keyword in keyword_tuple(language, "evidence_keywords", "batch")
        }
    )
)

DEFAULT_SIDE_AMOUNT_FIELDS = {
    "receivable": ("receivable_amount", "customer_amount", "debit_amount", "debit"),
    "customer": ("customer_amount", "receivable_amount", "debit_amount", "debit"),
    "payable": ("payable_amount", "supplier_amount", "credit_amount", "credit"),
    "supplier": ("supplier_amount", "payable_amount", "credit_amount", "credit"),
    "debit": ("debit_amount", "debit"),
    "credit": ("credit_amount", "credit"),
}

OPPOSITE_SIDE = {
    "receivable": "payable",
    "customer": "supplier",
    "payable": "receivable",
    "supplier": "customer",
    "debit": "credit",
    "credit": "debit",
}

DEFAULT_EXTERNAL_AMOUNT_FIELDS = (
    "bank_amount",
    "external_bank_amount",
    "factoring_amount",
    "factor_amount",
    "advance_amount",
    "operator_amount",
)

CLOSED_EVIDENCE_LEVELS = {
    "strong_external",
    "documented_compensation",
    "configured_strong",
}
DATE_FIELDS = (
    "value_date",
    "transaction_date",
    "posting_date",
    "document_date",
    "date",
)
PAYMENT_ORDER_TYPES = {"payment_order", "payment_order_bridge"}
FACTORING_BRIDGE_TYPES = {"factoring_bridge", "operator_factoring_bridge"}
UNALLOCATED_EXTERNAL_TYPES = {
    "unallocated_external_bank",
    "grouped_bank_unallocated",
    "unallocated_bank",
}
INTERNAL_TYPES = {"internal_accounting"}
INTERNAL_CLOSURE_TYPES = {
    "internal_closure",
    "internal_bank_closure",
    "closure_without_external",
}
OPEN_SUPPORT_TYPES = {"internal_booking", "ledger_open_item", "open_balance"}
EXTERNAL_TYPES = {"external_bank", "external_factoring"}
PROBABLE_BANK_PAYMENT_STATUS = "probable_payment"
NON_CLOSING_STATUSES = {
    "needs_evidence",
    "unresolved",
    "open_supported",
    PROBABLE_BANK_PAYMENT_STATUS,
}
INVOICE_REFERENCE_TERMS = (
    "fattura",
    "fatture",
    "fatt.",
    "fatt",
    "ftt.",
    "ftt",
    "ft.",
    "ft",
    "invoice",
    "inv.",
    "inv",
    "facture",
    "factura",
)
REVERSAL_OR_SETTLEMENT_TERMS = COMPENSATION_KEYWORDS + (
    "storno",
    "storni",
    "giroconto",
    "giroconti",
    "rettifica",
    "rettifiche",
    "nota credito",
    "note credito",
    "abbuono",
    "abbuoni",
    "write off",
    "write-off",
    "reversal",
    "credit note",
    "adjustment",
)
AGING_BUCKETS = (
    ("not_due_or_future", None, -1),
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("91-180", 91, 180),
    ("181-365", 181, 365),
    ("over_365", 366, None),
)


def clean_text(value: object) -> str:
    text = html.unescape(str(value if value is not None else "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_decimal(value: object) -> Decimal | None:
    text = clean_text(value)
    if not text:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    matches = re.findall(r"-?\d[\d.,]*", text)
    if not matches:
        return None
    raw = matches[-1]
    if "," in raw and "." in raw:
        raw = (
            raw.replace(".", "").replace(",", ".")
            if raw.rfind(",") > raw.rfind(".")
            else raw.replace(",", "")
        )
    elif "," in raw:
        tail = raw.split(",")[-1]
        raw = raw.replace(",", ".") if len(tail) <= 2 else raw.replace(",", "")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            raw = raw.replace(".", "")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value)
    if not text:
        return ""
    for pattern, order in [
        (r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", "ymd"),
        (r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", "dmy"),
    ]:
        match = re.search(pattern, text)
        if not match:
            continue
        a, b, c = match.groups()
        try:
            return (
                date(int(a), int(b), int(c)).isoformat()
                if order == "ymd"
                else date(int(c), int(b), int(a)).isoformat()
            )
        except ValueError:
            continue
    return ""


def merged_assumptions(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    assumptions = dict(DEFAULT_ASSUMPTIONS)
    if overrides:
        assumptions.update(overrides)
    return assumptions


def infer_source_role(path: str | Path) -> str:
    name = Path(path).name.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return role
    return "unknown"


def extract_document_no(text: object) -> str:
    value = clean_text(text)
    explicit = re.search(
        r"(?:invoice|fattura|document|doc|n\.?|no\.?|num(?:ero)?)\s*[:#.]?\s*([A-Z0-9][A-Z0-9./_-]{1,30})",
        value,
        flags=re.I,
    )
    if explicit:
        return explicit.group(1).strip(" .,-_/")
    candidates = re.findall(
        r"\b(?:\d{1,7}[/-][A-Z0-9]{1,8}|[A-Z]{1,5}\d{2,8}|\d{2,7}-[A-Z]{1,5})\b",
        value,
        flags=re.I,
    )
    return candidates[0].strip(" .,-_/") if candidates else ""


def document_key(document_no: object, document_date: object = "") -> str:
    raw_doc = clean_text(document_no).upper()
    suffix_year = re.fullmatch(r"0*(\d{1,7})[-/](\d{2}|20\d{2})", raw_doc)
    if suffix_year:
        year = suffix_year.group(2)
        return f"{int(suffix_year.group(1))}|{f'20{year}' if len(year) == 2 else year}"
    doc = re.sub(r"[^A-Z0-9]", "", raw_doc).lstrip("0")
    if not doc:
        return ""
    parsed_date = parse_date(document_date)
    year = parsed_date[:4] if parsed_date else ""
    if not year:
        year_match = re.search(r"(20\d{2}|\d{2})$", doc)
        if year_match:
            year = year_match.group(1)
            year = f"20{year}" if len(year) == 2 else year
    return f"{doc}|{year}"


def classify_evidence_type(source_role: str, description: object) -> str:
    text = clean_text(description).lower()
    if source_role == "bank_statement":
        return "external_bank"
    if source_role == "factoring_statement":
        return "external_factoring"
    if source_role == "payment_order":
        return "payment_order_bridge"
    if any_keyword_in(text, COMPENSATION_KEYWORDS):
        return "compensation"
    if source_role in {"ledger", "journal"}:
        return "internal_accounting"
    if source_role == "open_items":
        return "open_item"
    return "unknown"


def normalized_evidence_type(row: dict[str, Any]) -> str:
    explicit = clean_text(row.get("evidence_type")).lower()
    if explicit:
        return explicit
    return classify_evidence_type(clean_text(row.get("source_role")), row_text(row))


def text_contains_any(value: object, keywords: tuple[str, ...] | list[str]) -> bool:
    text = clean_text(value).lower()
    return any(keyword.lower() in text for keyword in keywords)


def row_text(
    row: dict[str, Any], fields: tuple[str, ...] | list[str] | None = None
) -> str:
    selected = fields or tuple(row.keys())
    return " ".join(clean_text(row.get(field)) for field in selected)


def has_factor_reference(
    *values: object,
    extra_keywords: tuple[str, ...] | list[str] | None = None,
) -> bool:
    keywords = FACTOR_KEYWORDS + tuple(extra_keywords or ())
    return text_contains_any(" ".join(clean_text(value) for value in values), keywords)


def has_bank_reference(*values: object) -> bool:
    return text_contains_any(
        " ".join(clean_text(value) for value in values), BANK_KEYWORDS
    )


def parse_bool(value: object) -> bool:
    text = clean_text(value).lower()
    return text in {"1", "true", "yes", "y", "si", "sì", "x"}


def assumption_enabled(assumptions: dict[str, Any], key: str) -> bool:
    value = assumptions.get(key)
    if isinstance(value, bool):
        return value
    return parse_bool(value)


def amounts_equal(left: object, right: object, tolerance: object = "0.01") -> bool:
    left_amount = parse_decimal(left)
    right_amount = parse_decimal(right)
    allowed = parse_decimal(tolerance) or Decimal("0.01")
    if left_amount is None or right_amount is None:
        return False
    return abs(left_amount - right_amount) <= allowed


def sum_amounts(values: list[object] | tuple[object, ...]) -> Decimal:
    total = Decimal("0.00")
    for value in values:
        parsed = parse_decimal(value)
        if parsed is not None:
            total += parsed
    return total.quantize(Decimal("0.01"))


def resolved_document_key(row: dict[str, Any]) -> str:
    explicit = clean_text(row.get("document_key"))
    if explicit:
        return explicit
    return document_key(row.get("document_no"), row.get("document_date"))


def split_tokens(value: object) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"[;,\n]+", clean_text(value))
        if token.strip()
    ]


def document_key_aliases(key: str) -> set[str]:
    """Return conservative aliases for common accounting invoice formats.

    Example: an Italian ledger may show ``23FE01/001524`` while a payment
    schedule shows ``1524-23``. The canonical keys are different, but both carry
    invoice number 1524 and year 2023. The alias is only numeric+year; it does
    not collapse different years or arbitrary text identifiers.
    """

    value = clean_text(key).upper()
    if "|" not in value:
        return set()
    doc, year = value.split("|", 1)
    if not re.fullmatch(r"20\d{2}", year):
        return set()
    aliases: set[str] = set()
    match = re.fullmatch(r"0*(\d{1,7})([A-Z][A-Z0-9]{0,5})", doc)
    if match:
        aliases.add(f"{int(match.group(1))}|{year}")
    match = re.fullmatch(r"0*(\d{1,7})(\d{2})", doc)
    if match and f"20{match.group(2)}" == year:
        aliases.add(f"{int(match.group(1))}|{year}")
    return aliases


def record_document_keys(row: dict[str, Any]) -> set[str]:
    keys = {resolved_document_key(row)}
    for field in (
        "document_keys",
        "allocated_document_keys",
        "invoice_keys",
        "matched_document_keys",
    ):
        for token in split_tokens(row.get(field)):
            keys.add(token)
    keys.discard("")
    for key in list(keys):
        keys.update(document_key_aliases(key))
    return keys


def _fallback_year_from_date(
    value: object, assumptions: dict[str, Any] | None = None
) -> str:
    parsed = parse_date(value)
    if parsed:
        return parsed[:4]
    active = merged_assumptions(assumptions)
    scope_year = clean_text(active.get("scope_year"))
    return scope_year if re.fullmatch(r"20\d{2}", scope_year) else ""


def _document_key_from_reference(ref: str, fallback_year: str) -> str:
    value = clean_text(ref).strip(" .,-_/")
    if not value:
        return ""
    if fallback_year and re.fullmatch(r"0*\d{1,7}", value):
        return f"{int(value)}|{fallback_year}"
    return document_key(value, f"{fallback_year}-01-01" if fallback_year else "")


def _split_invoice_reference_fragment(fragment: str, fallback_year: str) -> list[str]:
    """Split invoice-reference lists without treating arbitrary numbers as docs."""

    text = clean_text(fragment).upper()
    if not text:
        return []
    stop = re.search(
        r"\b(?:EUR|EURO|USD|GBP|SPESE|RIF\.?|ABI|CAB|BIC|IBAN|A\s+FAVORE|DA\s+VOSTRO)\b",
        text,
    )
    if stop:
        text = text[: stop.start()]
    text = re.sub(r"\b(?:N\.?|NO\.?|NR\.?|NUM(?:ERO)?)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,-_/")
    if not text:
        return []

    refs: list[str] = []
    year_suffix = fallback_year[-2:] if fallback_year else ""
    for raw in re.findall(
        r"\d{1,7}(?:[-/](?:(?:20\d{2}|\d{2})(?!\d)|FE|NE|FF|V\d+))?|\d{1,7}",
        text,
        flags=re.I,
    ):
        token = raw.strip(" .,-_/")
        if not token:
            continue
        year_match = re.fullmatch(r"0*(\d{1,7})[-/](\d{2}|20\d{2})", token)
        if year_match and year_suffix:
            year_part = year_match.group(2)
            normalized_year = year_part[-2:] if len(year_part) == 4 else year_part
            if normalized_year == year_suffix:
                refs.append(token)
                continue
        typed_match = re.fullmatch(r"\d{1,7}[-/](?:FE|NE|FF|V\d+)", token, flags=re.I)
        if typed_match:
            refs.append(token)
            continue
        if re.fullmatch(r"\d{1,7}", token):
            refs.append(token)

    keys: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        key = _document_key_from_reference(ref, fallback_year)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def invoice_reference_keys_from_text(
    text: object,
    *,
    fallback_date: object = "",
    assumptions: dict[str, Any] | None = None,
) -> list[str]:
    """Extract conservative invoice keys from descriptions.

    The parser only reads numbers tied to invoice terms. It intentionally avoids
    generic numbers such as bank identifiers, SEPA ids, customer ids, or amounts.
    """

    value = clean_text(text)
    if not value:
        return []
    fallback_year = _fallback_year_from_date(fallback_date, assumptions)
    term_pattern = (
        r"(?:FATT(?:URA|URE|\.?)|FTT\.?|FT\.?|INV(?:OICE)?\.?|FACTURE|FACTURA)"
    )
    fragment_pattern = re.compile(
        rf"\b{term_pattern}\s*(?:N\.?|NO\.?|NR\.?|NUM(?:ERO)?)?\s*"
        r"(?P<refs>\d{1,7}(?:\s*[-/]\s*(?:\d{1,7}|20\d{2}|FE|NE|FF|V\d+)){0,40})",
        re.I,
    )
    seen: set[str] = set()
    keys: list[str] = []
    for match in fragment_pattern.finditer(value):
        for key in _split_invoice_reference_fragment(
            match.group("refs"), fallback_year
        ):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    typed_pattern = re.compile(r"\b(?P<doc>\d{1,7}[-/](?:FE|NE|FF|V\d+))\b", re.I)
    for match in typed_pattern.finditer(value):
        key = _document_key_from_reference(match.group("doc"), fallback_year)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def record_contains_document_key(row: dict[str, Any], key: str) -> bool:
    return bool(key and key in record_document_keys(row))


def build_evidence_document_index(
    evidence_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Index evidence rows by normalized document key.

    Reconciliation is invoice-level work. Rows with no invoice/document key are
    intentionally not indexed because they cannot close a specific open item
    without allocation evidence.
    """

    index: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        for key in record_document_keys(row):
            index.setdefault(key, []).append(row)
    return index


def evidence_candidates_for_open_item(
    open_item: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    evidence_index: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    keys = record_document_keys(open_item)
    if not keys:
        return evidence_rows
    active_index = (
        evidence_index
        if evidence_index is not None
        else build_evidence_document_index(evidence_rows)
    )
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in keys:
        for row in active_index.get(key, []):
            marker = id(row)
            if marker not in seen:
                seen.add(marker)
                candidates.append(row)
    return candidates


def document_keys_match(
    left: dict[str, Any], right: dict[str, Any], require_both: bool = True
) -> bool:
    left_keys = record_document_keys(left)
    right_keys = record_document_keys(right)
    if not left_keys or not right_keys:
        return not require_both
    return bool(left_keys & right_keys)


def _parse_iso_date(value: object) -> date | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    try:
        return datetime.strptime(parsed, "%Y-%m-%d").date()
    except ValueError:
        return None


def document_dates_compatible(
    left: dict[str, Any],
    right: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> bool:
    """Return whether two document dates can support the same invoice match.

    The comparison uses explicit document dates only. Posting, value, or bank
    movement dates are settlement dates and must not invalidate a bank/factor
    match by themselves.
    """

    left_date = _parse_iso_date(left.get("document_date"))
    right_date = _parse_iso_date(right.get("document_date"))
    if left_date is None or right_date is None:
        return True
    active = merged_assumptions(assumptions)
    tolerance = parse_decimal(
        active.get("document_date_tolerance_days", "7")
    ) or Decimal("7")
    return abs((left_date - right_date).days) <= int(tolerance)


def requires_document_date_compatibility(evidence: dict[str, Any]) -> bool:
    evidence_type = normalized_evidence_type(evidence)
    source_role = clean_text(evidence.get("source_role")).lower()
    if evidence_type in EXTERNAL_TYPES or source_role in {
        "bank_statement",
        "factoring_statement",
    }:
        return False
    return (
        evidence_type in PAYMENT_ORDER_TYPES
        or evidence_type in FACTORING_BRIDGE_TYPES
        or evidence_type in INTERNAL_TYPES
        or evidence_type in INTERNAL_CLOSURE_TYPES
        or evidence_type in OPEN_SUPPORT_TYPES
        or source_role in {"payment_order", "ledger", "journal"}
    )


def document_key_match_rejected_by_date(
    open_item: dict[str, Any],
    evidence: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> bool:
    return (
        document_keys_match(open_item, evidence, require_both=True)
        and requires_document_date_compatibility(evidence)
        and not document_dates_compatible(open_item, evidence, assumptions)
    )


def record_date(
    row: dict[str, Any], date_fields: tuple[str, ...] | list[str] = DATE_FIELDS
) -> str:
    for field in date_fields:
        parsed = parse_date(row.get(field))
        if parsed:
            return parsed
    return ""


def is_after_cutoff(
    row: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> bool:
    active = merged_assumptions(assumptions)
    cutoff = parse_date(active.get("cutoff_date"))
    if not cutoff:
        return False
    row_date = record_date(row)
    return bool(row_date and row_date > cutoff)


def post_cutoff_evidence_candidates(
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List after-cut-off evidence that may explain in-scope open items.

    These rows are diagnostic only. They must not close a cut-off reconciliation
    when post-cut-off events are excluded, but they help reviewers distinguish
    true open balances from later settlements.
    """

    active = merged_assumptions(assumptions)
    cutoff = parse_date(active.get("cutoff_date"))
    if not cutoff:
        return []

    after_cutoff = [
        row
        for row in evidence_rows
        if is_after_cutoff(row, active) and record_document_keys(row)
    ]
    evidence_index = build_evidence_document_index(after_cutoff)
    rows: list[dict[str, Any]] = []
    tolerance = active.get("amount_tolerance", "0.01")
    for open_item in open_items:
        if not is_open_item_in_scope(open_item, active):
            continue
        open_amount = amount_for_matching(open_item) or Decimal("0.00")
        for evidence in evidence_candidates_for_open_item(
            open_item, after_cutoff, evidence_index
        ):
            if not document_keys_match(open_item, evidence, require_both=True):
                continue
            evidence_amount = amount_for_matching(evidence) or external_amount_total(
                evidence
            )
            exact_amount = amounts_equal(open_amount, evidence_amount, tolerance)
            description = clean_text(evidence.get("description"))
            if len(description) > 500:
                description = f"{description[:500]}..."
            rows.append(
                {
                    "candidate_id": f"post_cutoff:{clean_text(open_item.get('record_id'))}:{clean_text(evidence.get('record_id'))}",
                    "open_record_id": clean_text(open_item.get("record_id")),
                    "open_source_file": clean_text(open_item.get("source_file")),
                    "open_source_page": clean_text(open_item.get("source_page")),
                    "open_source_row": clean_text(open_item.get("source_row")),
                    "document_key": "; ".join(
                        sorted(
                            record_document_keys(open_item)
                            & record_document_keys(evidence)
                        )
                    ),
                    "document_no": clean_text(open_item.get("document_no")),
                    "document_date": record_date(
                        open_item, ("document_date", "posting_date", "date")
                    ),
                    "open_amount": f"{open_amount:.2f}",
                    "evidence_record_id": clean_text(evidence.get("record_id")),
                    "evidence_source_file": clean_text(evidence.get("source_file")),
                    "evidence_source_page": clean_text(evidence.get("source_page")),
                    "evidence_source_row": clean_text(evidence.get("source_row")),
                    "evidence_source_role": clean_text(evidence.get("source_role")),
                    "evidence_type": normalized_evidence_type(evidence),
                    "evidence_date": record_date(evidence),
                    "evidence_amount": f"{evidence_amount:.2f}",
                    "exact_amount_match": "YES" if exact_amount else "NO",
                    "review_use": (
                        "Candidato successivo al cut-off: usare per spiegare una chiusura successiva, "
                        "non per chiudere la riga al cut-off."
                    ),
                    "description": description,
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row.get("document_key", ""),
            row.get("evidence_date", ""),
            row.get("evidence_record_id", ""),
        ),
    )


def analysis_reference_date(assumptions: dict[str, Any] | None = None) -> str:
    """Return the deterministic reporting date for aging-style analyses."""

    active = merged_assumptions(assumptions)
    cutoff = parse_date(active.get("cutoff_date"))
    if cutoff:
        return cutoff
    scope_year = clean_text(active.get("scope_year"))
    if re.fullmatch(r"20\d{2}", scope_year):
        return f"{scope_year}-12-31"
    return ""


def aging_bucket(age_days: int | None) -> str:
    if age_days is None:
        return "no_date"
    for label, minimum, maximum in AGING_BUCKETS:
        if minimum is None and age_days <= (maximum or age_days):
            return label
        if maximum is None and age_days >= (minimum or age_days):
            return label
        if (
            minimum is not None
            and maximum is not None
            and minimum <= age_days <= maximum
        ):
            return label
    return "no_date"


def age_days_at_reference(row: dict[str, Any], reference_date: str) -> int | None:
    row_date = _parse_iso_date(
        record_date(row, ("document_date", "posting_date", "date"))
    )
    reference = _parse_iso_date(reference_date)
    if row_date is None or reference is None:
        return None
    return (reference - row_date).days


def open_item_aging_summary(
    reconciliation_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Summarize in-scope reconciliation rows by deterministic aging bucket."""

    reference_date = analysis_reference_date(assumptions)
    if not reference_date:
        return []
    buckets: dict[str, dict[str, Any]] = {}
    for row in reconciliation_rows:
        if clean_text(row.get("reconciliation_status")) == "out_of_scope":
            continue
        amount = amount_for_matching(row) or Decimal("0.00")
        status = clean_text(row.get("reconciliation_status")) or "unknown"
        age_days = age_days_at_reference(row, reference_date)
        bucket_key = aging_bucket(age_days)
        bucket = buckets.setdefault(
            bucket_key,
            {
                "aging_bucket": bucket_key,
                "reference_date": reference_date,
                "rows": 0,
                "amount_total": Decimal("0.00"),
                "amount_abs_total": Decimal("0.00"),
                "closed_amount": Decimal("0.00"),
                "probable_payment_amount": Decimal("0.00"),
                "open_supported_amount": Decimal("0.00"),
                "needs_evidence_amount": Decimal("0.00"),
                "unresolved_amount": Decimal("0.00"),
                "min_age_days": age_days,
                "max_age_days": age_days,
            },
        )
        bucket["rows"] += 1
        bucket["amount_total"] += amount
        bucket["amount_abs_total"] += abs(amount)
        if status == "closed":
            bucket["closed_amount"] += amount
        elif status == PROBABLE_BANK_PAYMENT_STATUS:
            bucket["probable_payment_amount"] += amount
        elif status == "open_supported":
            bucket["open_supported_amount"] += amount
        elif status == "needs_evidence":
            bucket["needs_evidence_amount"] += amount
        elif status == "unresolved":
            bucket["unresolved_amount"] += amount
        if age_days is not None:
            bucket["min_age_days"] = (
                age_days
                if bucket["min_age_days"] is None
                else min(bucket["min_age_days"], age_days)
            )
            bucket["max_age_days"] = (
                age_days
                if bucket["max_age_days"] is None
                else max(bucket["max_age_days"], age_days)
            )

    order = {label: idx for idx, (label, _, _) in enumerate(AGING_BUCKETS)}
    order["no_date"] = len(order)
    return [
        {
            "aging_bucket": row["aging_bucket"],
            "reference_date": row["reference_date"],
            "rows": row["rows"],
            "amount_total": f"{row['amount_total']:.2f}",
            "amount_abs_total": f"{row['amount_abs_total']:.2f}",
            "closed_amount": f"{row['closed_amount']:.2f}",
            "probable_payment_amount": f"{row['probable_payment_amount']:.2f}",
            "open_supported_amount": f"{row['open_supported_amount']:.2f}",
            "needs_evidence_amount": f"{row['needs_evidence_amount']:.2f}",
            "unresolved_amount": f"{row['unresolved_amount']:.2f}",
            "min_age_days": "" if row["min_age_days"] is None else row["min_age_days"],
            "max_age_days": "" if row["max_age_days"] is None else row["max_age_days"],
        }
        for row in sorted(
            buckets.values(), key=lambda item: order.get(item["aging_bucket"], 99)
        )
    ]


def review_signal_rows(
    reconciliation_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank rows that deserve attention by amount, age, and evidence weakness."""

    active = merged_assumptions(assumptions)
    reference_date = analysis_reference_date(active)
    high_value_threshold = parse_decimal(
        active.get("review_high_value_threshold", "100000")
    ) or Decimal("100000.00")
    old_age_threshold = int(
        parse_decimal(active.get("review_old_age_days", "180")) or Decimal("180")
    )
    signals: list[dict[str, Any]] = []
    for row in reconciliation_rows:
        status = clean_text(row.get("reconciliation_status"))
        if status == "out_of_scope":
            continue
        amount = amount_for_matching(row) or Decimal("0.00")
        amount_abs = abs(amount)
        age_days = (
            age_days_at_reference(row, reference_date) if reference_date else None
        )
        evidence_level_value = clean_text(row.get("evidence_level"))
        row_signals: list[str] = []
        if amount_abs >= high_value_threshold:
            row_signals.append("high_value")
        if age_days is not None and age_days >= old_age_threshold:
            row_signals.append("old_open_item")
        if status in {"needs_evidence", "unresolved", PROBABLE_BANK_PAYMENT_STATUS}:
            row_signals.append(status)
        if evidence_level_value in {"none", "weak_internal", "bridge_only"}:
            row_signals.append(f"evidence_{evidence_level_value}")
        if clean_text(row.get("matched_evidence_type")) in PAYMENT_ORDER_TYPES:
            row_signals.append("payment_order_bridge")
        if not row_signals:
            continue
        signals.append(
            {
                "record_id": clean_text(row.get("record_id")),
                "document_key": clean_text(row.get("document_key")),
                "document_no": clean_text(row.get("document_no")),
                "document_date": record_date(
                    row, ("document_date", "posting_date", "date")
                ),
                "amount": f"{amount:.2f}",
                "amount_abs": f"{amount_abs:.2f}",
                "age_days_at_reference": "" if age_days is None else age_days,
                "reconciliation_status": status,
                "rule_applied": clean_text(row.get("rule_applied")),
                "evidence_level": evidence_level_value,
                "matched_evidence_type": clean_text(row.get("matched_evidence_type")),
                "review_signals": "; ".join(row_signals),
                "source_reference": evidence_reference(row),
            }
        )
    ranked = sorted(
        signals,
        key=lambda row: (
            -len(split_tokens(row.get("review_signals"))),
            -(parse_decimal(row.get("amount_abs")) or Decimal("0.00")),
            -(int(row.get("age_days_at_reference") or 0)),
            row.get("record_id"),
        ),
    )
    for idx, row in enumerate(ranked, start=1):
        row["review_signal_rank"] = idx
    return ranked


def evidence_support_bucket(row: dict[str, Any]) -> str:
    status = clean_text(row.get("reconciliation_status"))
    evidence_type = clean_text(
        row.get("matched_evidence_type") or row.get("evidence_type")
    ).lower()
    evidence_level_value = clean_text(row.get("evidence_level")).lower()
    rule = clean_text(row.get("rule_applied")).lower()
    if status == "unresolved" or evidence_level_value == "none":
        return "no_evidence"
    if status == PROBABLE_BANK_PAYMENT_STATUS:
        return "bank_probable"
    if evidence_type in {"external_bank", "probable_external_bank"}:
        return "bank"
    if (
        evidence_type == "external_factoring"
        or evidence_type in FACTORING_BRIDGE_TYPES
        or "factoring" in rule
    ):
        return "factor_or_advance"
    if evidence_type in PAYMENT_ORDER_TYPES:
        return "payment_order"
    if evidence_type == "compensation" or "compensation" in rule:
        return "compensation"
    if (
        evidence_type in INTERNAL_TYPES
        or evidence_type in INTERNAL_CLOSURE_TYPES
        or evidence_type in OPEN_SUPPORT_TYPES
    ):
        return "internal_accounting"
    if evidence_level_value == "bridge_only":
        return "bridge_only"
    return evidence_type or "unknown"


def evidence_concentration_summary(
    reconciliation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize the open-item population by the strongest evidence bucket."""

    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    total_abs = Decimal("0.00")
    for row in reconciliation_rows:
        if clean_text(row.get("reconciliation_status")) == "out_of_scope":
            continue
        amount = amount_for_matching(row) or Decimal("0.00")
        amount_abs = abs(amount)
        total_abs += amount_abs
        bucket_key = evidence_support_bucket(row)
        status = clean_text(row.get("reconciliation_status")) or "unknown"
        key = (bucket_key, status)
        bucket = buckets.setdefault(
            key,
            {
                "support_bucket": bucket_key,
                "reconciliation_status": status,
                "rows": 0,
                "amount_total": Decimal("0.00"),
                "amount_abs_total": Decimal("0.00"),
            },
        )
        bucket["rows"] += 1
        bucket["amount_total"] += amount
        bucket["amount_abs_total"] += amount_abs
    rows = []
    for bucket in sorted(
        buckets.values(),
        key=lambda item: (
            -item["amount_abs_total"],
            item["support_bucket"],
            item["reconciliation_status"],
        ),
    ):
        share = (
            Decimal("0.00")
            if total_abs == Decimal("0.00")
            else (bucket["amount_abs_total"] / total_abs * Decimal("100")).quantize(
                Decimal("0.01")
            )
        )
        rows.append(
            {
                "support_bucket": bucket["support_bucket"],
                "reconciliation_status": bucket["reconciliation_status"],
                "rows": bucket["rows"],
                "amount_total": f"{bucket['amount_total']:.2f}",
                "amount_abs_total": f"{bucket['amount_abs_total']:.2f}",
                "share_of_abs_amount_percent": f"{share:.2f}",
            }
        )
    return rows


def source_map_bucket(row: dict[str, Any]) -> str:
    source_role = clean_text(row.get("source_role")).lower()
    evidence_type = normalized_evidence_type(row)
    if source_role == "open_items" or evidence_type == "open_item":
        return "open_items"
    if source_role == "bank_statement" or evidence_type == "external_bank":
        return "bank"
    if (
        source_role == "factoring_statement"
        or evidence_type == "external_factoring"
        or evidence_type in FACTORING_BRIDGE_TYPES
    ):
        return "factoring"
    if source_role == "payment_order" or evidence_type in PAYMENT_ORDER_TYPES:
        return "payment_order"
    if evidence_type == "compensation" or source_role == "compensation_support":
        return "compensation"
    if source_role == "ledger" or evidence_type in OPEN_SUPPORT_TYPES:
        return "ledger"
    if (
        source_role == "journal"
        or evidence_type in INTERNAL_TYPES
        or evidence_type in INTERNAL_CLOSURE_TYPES
    ):
        return "journal"
    return "other"


def document_source_map(
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    reconciliation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map each document key to the source families where it appears."""

    rows = [*open_items, *evidence_rows]
    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    row_keys: list[tuple[dict[str, Any], set[str]]] = []
    for row in rows:
        keys = record_document_keys(row)
        if not keys:
            continue
        sorted_keys = sorted(keys)
        for key in sorted_keys:
            find(key)
        for key in sorted_keys[1:]:
            union(sorted_keys[0], key)
        row_keys.append((row, keys))

    groups: dict[str, set[str]] = {}
    for key in parent:
        groups.setdefault(find(key), set()).add(key)

    def representative(keys: set[str]) -> str:
        return sorted(
            keys,
            key=lambda value: (
                not re.fullmatch(r"\d+\|20\d{2}", value),
                len(value),
                value,
            ),
        )[0]

    root_to_representative = {
        root: representative(keys) for root, keys in groups.items()
    }
    key_to_representative = {key: root_to_representative[find(key)] for key in parent}

    reconciliation_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in reconciliation_rows:
        for key in record_document_keys(row):
            mapped = key_to_representative.get(key, key)
            reconciliation_by_key.setdefault(mapped, []).append(row)

    mapped_rows: dict[str, dict[str, Any]] = {}
    for row, keys in row_keys:
        mapped = key_to_representative.get(sorted(keys)[0], sorted(keys)[0])
        bucket_name = source_map_bucket(row)
        amount = (
            amount_for_matching(row) or external_amount_total(row) or Decimal("0.00")
        )
        target = mapped_rows.setdefault(
            mapped,
            {
                "document_key": mapped,
                "document_aliases": "; ".join(
                    sorted(groups.get(find(mapped), {mapped}))
                ),
                "document_no_examples": set(),
                "document_dates": set(),
                "source_files": set(),
                "evidence_types_present": set(),
                "source_roles_present": set(),
                "open_item_rows": 0,
                "open_amount_total": Decimal("0.00"),
                "ledger_rows": 0,
                "journal_rows": 0,
                "bank_rows": 0,
                "payment_order_rows": 0,
                "factoring_rows": 0,
                "compensation_rows": 0,
                "other_rows": 0,
                "evidence_amount_total": Decimal("0.00"),
            },
        )
        if clean_text(row.get("document_no")):
            target["document_no_examples"].add(clean_text(row.get("document_no")))
        row_date = record_date(row, ("document_date", "posting_date", "date"))
        if row_date:
            target["document_dates"].add(row_date)
        if clean_text(row.get("source_file")):
            target["source_files"].add(clean_text(row.get("source_file")))
        if clean_text(row.get("source_role")):
            target["source_roles_present"].add(clean_text(row.get("source_role")))
        if normalized_evidence_type(row):
            target["evidence_types_present"].add(normalized_evidence_type(row))
        if bucket_name == "open_items":
            target["open_item_rows"] += 1
            target["open_amount_total"] += amount
        elif bucket_name == "ledger":
            target["ledger_rows"] += 1
            target["evidence_amount_total"] += amount
        elif bucket_name == "journal":
            target["journal_rows"] += 1
            target["evidence_amount_total"] += amount
        elif bucket_name == "bank":
            target["bank_rows"] += 1
            target["evidence_amount_total"] += amount
        elif bucket_name == "payment_order":
            target["payment_order_rows"] += 1
            target["evidence_amount_total"] += amount
        elif bucket_name == "factoring":
            target["factoring_rows"] += 1
            target["evidence_amount_total"] += amount
        elif bucket_name == "compensation":
            target["compensation_rows"] += 1
            target["evidence_amount_total"] += amount
        else:
            target["other_rows"] += 1
            target["evidence_amount_total"] += amount

    output_rows: list[dict[str, Any]] = []
    for key, row in mapped_rows.items():
        related_reconciliation = reconciliation_by_key.get(key, [])
        status_counts: dict[str, int] = {}
        for reconciliation in related_reconciliation:
            status = (
                clean_text(reconciliation.get("reconciliation_status")) or "unknown"
            )
            status_counts[status] = status_counts.get(status, 0) + 1
        has_external = bool(row["bank_rows"] or row["factoring_rows"])
        has_bridge = bool(row["payment_order_rows"] or row["compensation_rows"])
        has_internal = bool(row["ledger_rows"] or row["journal_rows"])
        if row["open_item_rows"] and has_external:
            review_note = "Documento presente anche in evidenza esterna."
        elif row["open_item_rows"] and has_bridge:
            review_note = "Documento presente in distinta/compensazione: verificare supporto di chiusura."
        elif row["open_item_rows"] and has_internal:
            review_note = "Documento presente solo in evidenza interna."
        elif row["open_item_rows"]:
            review_note = (
                "Documento presente nelle partite aperte senza evidenza collegata."
            )
        else:
            review_note = (
                "Documento presente solo nelle evidenze, non nella popolazione aperta."
            )
        output_rows.append(
            {
                "document_key": row["document_key"],
                "document_aliases": row["document_aliases"],
                "document_no_examples": "; ".join(
                    sorted(row["document_no_examples"])[:5]
                ),
                "document_dates": "; ".join(sorted(row["document_dates"])[:5]),
                "open_item_rows": row["open_item_rows"],
                "open_amount_total": f"{row['open_amount_total']:.2f}",
                "reconciliation_status_counts": "; ".join(
                    f"{status}:{count}"
                    for status, count in sorted(status_counts.items())
                ),
                "ledger_rows": row["ledger_rows"],
                "journal_rows": row["journal_rows"],
                "bank_rows": row["bank_rows"],
                "payment_order_rows": row["payment_order_rows"],
                "factoring_rows": row["factoring_rows"],
                "compensation_rows": row["compensation_rows"],
                "other_rows": row["other_rows"],
                "evidence_amount_total": f"{row['evidence_amount_total']:.2f}",
                "source_roles_present": "; ".join(sorted(row["source_roles_present"])),
                "evidence_types_present": "; ".join(
                    sorted(row["evidence_types_present"])
                ),
                "source_files": "; ".join(sorted(row["source_files"])[:10]),
                "review_note": review_note,
            }
        )
    return sorted(
        output_rows,
        key=lambda item: (
            item["open_item_rows"] == 0,
            -(parse_decimal(item["open_amount_total"]) or Decimal("0.00")),
            item["document_key"],
        ),
    )


def reversal_or_compensation_candidates(
    reconciliation_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Find same-document storno/giroconto/compensation candidates."""

    active = merged_assumptions(assumptions)
    tolerance = active.get("amount_tolerance", "0.01")
    evidence_index = build_evidence_document_index(evidence_rows)
    candidates: list[dict[str, Any]] = []
    seen_candidates: set[tuple[str, str]] = set()
    for open_row in reconciliation_rows:
        status = clean_text(open_row.get("reconciliation_status"))
        if status in {"closed", "out_of_scope"}:
            continue
        open_amount = amount_for_matching(open_row) or Decimal("0.00")
        if open_amount == Decimal("0.00"):
            continue
        for evidence in evidence_candidates_for_open_item(
            open_row, evidence_rows, evidence_index
        ):
            if active.get("post_cutoff_events_excluded") and is_after_cutoff(
                evidence, active
            ):
                continue
            evidence_type = normalized_evidence_type(evidence)
            source_role = clean_text(evidence.get("source_role")).lower()
            text = row_text(evidence).lower()
            evidence_amount = amount_for_matching(evidence) or external_amount_total(
                evidence
            )
            exact_abs_match = amounts_equal(
                abs(open_amount), abs(evidence_amount), tolerance
            )
            opposite_sign_match = amounts_equal(
                open_amount, -evidence_amount, tolerance
            )
            keyword_match = any_keyword_in(text, REVERSAL_OR_SETTLEMENT_TERMS)
            closure_type = (
                evidence_type in ({"compensation"} | INTERNAL_CLOSURE_TYPES)
                or source_role == "compensation_support"
            )
            if not (
                opposite_sign_match
                or keyword_match
                or (exact_abs_match and closure_type)
            ):
                continue
            reasons = []
            if exact_abs_match:
                reasons.append("same_document_same_absolute_amount")
            if opposite_sign_match:
                reasons.append("opposite_sign_amount")
            if keyword_match:
                reasons.append("reversal_or_compensation_keyword")
            if closure_type:
                reasons.append("closure_or_compensation_type")
            shared_keys = sorted(
                record_document_keys(open_row) & record_document_keys(evidence)
            )
            candidate_key = (_row_identity(open_row), _row_identity(evidence))
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            candidates.append(
                {
                    "candidate_id": f"reversal:{_row_identity(open_row)}:{_row_identity(evidence)}",
                    "open_record_id": clean_text(open_row.get("record_id")),
                    "open_status": status,
                    "document_key": "; ".join(shared_keys),
                    "document_no": clean_text(open_row.get("document_no")),
                    "document_date": record_date(
                        open_row, ("document_date", "posting_date", "date")
                    ),
                    "open_amount": f"{open_amount:.2f}",
                    "evidence_record_id": clean_text(evidence.get("record_id")),
                    "evidence_source_file": clean_text(evidence.get("source_file")),
                    "evidence_source_page": clean_text(evidence.get("source_page")),
                    "evidence_source_row": clean_text(evidence.get("source_row")),
                    "evidence_date": record_date(evidence),
                    "evidence_type": evidence_type,
                    "evidence_amount": f"{evidence_amount:.2f}",
                    "candidate_reasons": "; ".join(reasons),
                    "review_use": "Verificare se si tratta di storno, giroconto, compensazione o rettifica; non cambia lo stato da solo.",
                    "description": clean_text(evidence.get("description")),
                }
            )
    return sorted(
        candidates,
        key=lambda row: (
            row.get("open_status"),
            -(abs(parse_decimal(row.get("open_amount")) or Decimal("0.00"))),
            row.get("document_key"),
            row.get("evidence_record_id"),
        ),
    )


def cutoff_window_movements(
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List source rows dated near the cut-off date."""

    active = merged_assumptions(assumptions)
    cutoff = _parse_iso_date(active.get("cutoff_date"))
    if cutoff is None:
        return []
    window_days = int(
        parse_decimal(active.get("cutoff_window_days", "30")) or Decimal("30")
    )
    rows: list[dict[str, Any]] = []
    for row in [*open_items, *evidence_rows]:
        row_date_text = record_date(row)
        row_date = _parse_iso_date(row_date_text)
        if row_date is None:
            continue
        days_from_cutoff = (row_date - cutoff).days
        if abs(days_from_cutoff) > window_days:
            continue
        if days_from_cutoff < 0:
            timing = "before_cutoff"
        elif days_from_cutoff > 0:
            timing = "after_cutoff"
        else:
            timing = "cutoff_date"
        amount = (
            amount_for_matching(row) or external_amount_total(row) or Decimal("0.00")
        )
        rows.append(
            {
                "record_id": clean_text(row.get("record_id")),
                "source_file": clean_text(row.get("source_file")),
                "source_page": clean_text(row.get("source_page")),
                "source_row": clean_text(row.get("source_row")),
                "source_role": clean_text(row.get("source_role")),
                "evidence_type": normalized_evidence_type(row),
                "document_key": "; ".join(sorted(record_document_keys(row))),
                "document_no": clean_text(row.get("document_no")),
                "movement_date": row_date_text,
                "days_from_cutoff": days_from_cutoff,
                "cutoff_window_timing": timing,
                "amount": f"{amount:.2f}",
                "description": clean_text(row.get("description")),
                "source_reference": evidence_reference(row),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            abs(int(row["days_from_cutoff"])),
            row.get("movement_date"),
            row.get("source_file"),
            row.get("source_row"),
            row.get("record_id"),
        ),
    )


def is_open_item_in_scope(
    open_item: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> bool:
    active = merged_assumptions(assumptions)
    scope_year = clean_text(active.get("scope_year"))
    cutoff = parse_date(active.get("cutoff_date"))
    item_date = record_date(open_item, ("document_date", "posting_date", "date"))
    if scope_year and item_date and not item_date.startswith(scope_year):
        return False
    if cutoff and item_date and item_date > cutoff:
        return False
    return True


def first_amount(
    row: dict[str, Any], fields: tuple[str, ...] | list[str]
) -> Decimal | None:
    for field in fields:
        parsed = parse_decimal(row.get(field))
        if parsed is not None:
            return parsed
    return None


def side_amount(
    row: dict[str, Any],
    expected_side: str,
    side_amount_fields: dict[str, tuple[str, ...] | list[str]] | None = None,
) -> Decimal | None:
    fields_by_side = side_amount_fields or DEFAULT_SIDE_AMOUNT_FIELDS
    fields = fields_by_side.get(clean_text(expected_side).lower(), ())
    return first_amount(row, fields)


def external_amount_total(
    row: dict[str, Any],
    external_amount_fields: (
        tuple[str, ...] | list[str]
    ) = DEFAULT_EXTERNAL_AMOUNT_FIELDS,
) -> Decimal:
    return sum_amounts([row.get(field) for field in external_amount_fields])


def amount_for_matching(
    row: dict[str, Any], amount_field: str = "amount"
) -> Decimal | None:
    fields = (
        amount_field,
        "balance",
        "open_amount",
        "matched_amount",
        "allocated_amount",
    )
    return first_amount(row, fields)


def side_aware_closure_match(
    open_item: dict[str, Any],
    closure: dict[str, Any],
    expected_side: str,
    *,
    amount_field: str = "amount",
    tolerance: object = "0.01",
    require_document_key: bool = True,
    side_amount_fields: dict[str, tuple[str, ...] | list[str]] | None = None,
    external_amount_fields: (
        tuple[str, ...] | list[str]
    ) = DEFAULT_EXTERNAL_AMOUNT_FIELDS,
) -> bool:
    """Match an open item to a closure without confusing opposite account sides.

    Use this for journal/ledger closures where the same invoice number can appear
    on both receivable and payable sides. The expected side amount wins. As a
    fallback, grouped bank/factor evidence can match by external total, but only
    after document-key checks pass.
    """

    expected_side_clean = clean_text(expected_side).lower()
    if not expected_side_clean:
        return False
    if require_document_key and not document_keys_match(
        open_item, closure, require_both=True
    ):
        return False
    if require_document_key and document_key_match_rejected_by_date(
        open_item, closure, {"amount_tolerance": tolerance}
    ):
        return False

    closure_side = clean_text(
        closure.get("side")
        or closure.get("account_side")
        or closure.get("expected_side")
        or closure.get("account_role")
    ).lower()
    if closure_side and closure_side != expected_side_clean:
        return False

    open_amount = open_item.get(amount_field)
    matched_side_amount = side_amount(closure, expected_side_clean, side_amount_fields)
    if matched_side_amount is not None and amounts_equal(
        matched_side_amount, open_amount, tolerance
    ):
        return True
    opposite_side = OPPOSITE_SIDE.get(expected_side_clean, "")
    opposite_amount = (
        side_amount(closure, opposite_side, side_amount_fields)
        if opposite_side
        else None
    )
    if opposite_amount is not None and amounts_equal(
        opposite_amount, open_amount, tolerance
    ):
        return False
    if closure_side == expected_side_clean and amounts_equal(
        amount_for_matching(closure), open_amount, tolerance
    ):
        return True

    text = row_text(closure)
    closure_evidence_type = normalized_evidence_type(closure)
    closure_source_role = clean_text(closure.get("source_role")).lower()
    if (
        closure_evidence_type in EXTERNAL_TYPES
        or closure_source_role in {"bank_statement", "factoring_statement"}
        or has_factor_reference(text)
        or has_bank_reference(text)
    ):
        return amounts_equal(
            external_amount_total(closure, external_amount_fields),
            open_amount,
            tolerance,
        )

    return False


def evidence_has_external_support(row: dict[str, Any]) -> bool:
    evidence_type = normalized_evidence_type(row)
    source_role = clean_text(row.get("source_role")).lower()
    text = row_text(row)
    return (
        evidence_type in EXTERNAL_TYPES
        or source_role in {"bank_statement", "factoring_statement"}
        or parse_bool(row.get("external_support_found"))
        or parse_bool(row.get("bank_statement_found"))
        or parse_bool(row.get("factor_statement_found"))
        or has_bank_reference(text)
        or has_factor_reference(text)
    )


def is_factoring_evidence(
    row: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> bool:
    active = merged_assumptions(assumptions)
    evidence_type = normalized_evidence_type(row)
    source_role = clean_text(row.get("source_role")).lower()
    text = row_text(row)
    return (
        evidence_type == "external_factoring"
        or evidence_type in FACTORING_BRIDGE_TYPES
        or source_role == "factoring_statement"
        or has_factor_reference(
            text, extra_keywords=active.get("factoring_operator_keywords", ())
        )
    )


def side_conflicts_with_expected(
    open_item: dict[str, Any],
    evidence: dict[str, Any],
    expected_side: str,
    assumptions: dict[str, Any] | None = None,
) -> bool:
    active = merged_assumptions(assumptions)
    expected_side_clean = clean_text(expected_side).lower()
    if not expected_side_clean:
        return False

    evidence_side = clean_text(
        evidence.get("side")
        or evidence.get("account_side")
        or evidence.get("expected_side")
        or evidence.get("account_role")
    ).lower()
    if evidence_side and evidence_side != expected_side_clean:
        return True

    opposite_side = OPPOSITE_SIDE.get(expected_side_clean, "")
    opposite_amount = side_amount(evidence, opposite_side) if opposite_side else None
    expected_amount = side_amount(evidence, expected_side_clean)
    open_amount = amount_for_matching(open_item)
    return bool(
        expected_amount is None
        and opposite_amount is not None
        and amounts_equal(
            opposite_amount, open_amount, active.get("amount_tolerance", "0.01")
        )
    )


def pro_soluto_factoring_document_match(
    open_item: dict[str, Any],
    evidence: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
    expected_side: str = "",
) -> bool:
    """Allow document-specific pro-soluto factoring evidence to close the item.

    A factoring/advance statement may show the financed amount rather than the
    invoice face value. When the configured assumption treats pro-soluto
    factoring as closing the item, a document-specific external factoring row is
    enough even if its cash amount differs from the invoice balance.
    """

    active = merged_assumptions(assumptions)
    if not active.get("factoring_pro_soluto_closes_item"):
        return False
    if not document_keys_match(open_item, evidence, require_both=True):
        return False
    if not is_factoring_evidence(evidence, active):
        return False
    if expected_side and side_conflicts_with_expected(
        open_item, evidence, expected_side, active
    ):
        return False
    return True


def evidence_level(
    row: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> str:
    active = merged_assumptions(assumptions)
    source_role = clean_text(row.get("source_role")).lower()
    evidence_type = normalized_evidence_type(row)
    text = row_text(row)

    if active.get("post_cutoff_events_excluded") and is_after_cutoff(row, active):
        return "out_of_scope"
    if evidence_type in UNALLOCATED_EXTERNAL_TYPES:
        return "bridge_only"
    if evidence_type == "external_bank" or source_role == "bank_statement":
        return "strong_external"
    if evidence_type in FACTORING_BRIDGE_TYPES:
        return "bridge_only"
    if is_factoring_evidence(row, active):
        return (
            "configured_strong"
            if active.get("factoring_pro_soluto_closes_item")
            else "bridge_only"
        )
    keyword_compensation = (
        source_role not in {"ledger", "journal"}
        and evidence_type not in OPEN_SUPPORT_TYPES
        and any_keyword_in(text, COMPENSATION_KEYWORDS)
    )
    if (
        evidence_type == "compensation"
        or source_role == "compensation_support"
        or keyword_compensation
    ):
        if active.get(
            "compensation_requires_bank"
        ) and not evidence_has_external_support(row):
            return "bridge_only"
        return "documented_compensation"
    if evidence_type in PAYMENT_ORDER_TYPES or source_role == "payment_order":
        return (
            "configured_strong"
            if active.get("payment_orders_are_bank_evidence")
            else "bridge_only"
        )
    if (
        evidence_type in INTERNAL_TYPES
        or evidence_type in INTERNAL_CLOSURE_TYPES
        or evidence_type in OPEN_SUPPORT_TYPES
        or source_role in {"ledger", "journal"}
    ):
        return "weak_internal"
    return "none"


def evidence_reference(row: dict[str, Any]) -> str:
    bits = []
    for label, field in (
        ("file", "source_file"),
        ("sheet", "source_sheet"),
        ("page", "source_page"),
        ("row", "source_row"),
        ("id", "record_id"),
    ):
        value = clean_text(row.get(field))
        if value:
            bits.append(f"{label}={value}")
    return "; ".join(bits)


def closed_rule_for_evidence(
    evidence: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> str:
    evidence_type = normalized_evidence_type(evidence)
    if is_factoring_evidence(evidence, assumptions):
        if evidence_has_external_support(evidence) or external_amount_total(
            evidence
        ) != Decimal("0.00"):
            return "factoring_with_bank_or_external_support"
        return "factoring_or_advance_match"
    if (
        evidence_type == "external_bank"
        or clean_text(evidence.get("source_role")).lower() == "bank_statement"
    ):
        return "external_bank_match"
    if (
        evidence_type == "compensation"
        or clean_text(evidence.get("source_role")).lower() == "compensation_support"
    ):
        return "documented_compensation"
    if evidence_type in PAYMENT_ORDER_TYPES:
        return "configured_payment_order"
    return "configured_strong_evidence"


def evidence_amount_summary(evidence: dict[str, Any]) -> str:
    bits = []
    for label, field in (
        ("amount", "amount"),
        ("bank_amount", "bank_amount"),
        ("external_bank_amount", "external_bank_amount"),
        ("factor_amount", "factor_amount"),
        ("factoring_amount", "factoring_amount"),
        ("advance_amount", "advance_amount"),
    ):
        value = parse_decimal(evidence.get(field))
        if value is not None:
            bits.append(f"{label}={value:.2f}")
    return "; ".join(bits)


def evidence_matches_open_item(
    open_item: dict[str, Any],
    evidence: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> bool:
    active = merged_assumptions(assumptions)
    if active.get("post_cutoff_events_excluded") and is_after_cutoff(evidence, active):
        return False
    if document_key_match_rejected_by_date(open_item, evidence, active):
        return False

    expected_side = clean_text(
        open_item.get("expected_side") or open_item.get("account_side")
    )
    evidence_type = normalized_evidence_type(evidence)
    if (
        document_keys_match(open_item, evidence, require_both=True)
        and evidence_type in OPEN_SUPPORT_TYPES
    ):
        if expected_side and side_conflicts_with_expected(
            open_item, evidence, expected_side, active
        ):
            return False
        evidence_side = clean_text(
            evidence.get("side")
            or evidence.get("account_side")
            or evidence.get("expected_side")
            or evidence.get("account_role")
        ).lower()
        if expected_side and evidence_side == expected_side.lower():
            return True
        return amounts_equal(
            amount_for_matching(open_item),
            amount_for_matching(evidence),
            active.get("amount_tolerance", "0.01"),
        )

    if expected_side and document_keys_match(open_item, evidence, require_both=True):
        opposite_side = OPPOSITE_SIDE.get(expected_side.lower(), "")
        has_side_data = bool(
            side_amount(evidence, expected_side)
            or (opposite_side and side_amount(evidence, opposite_side))
            or external_amount_total(evidence)
            or clean_text(
                evidence.get("side")
                or evidence.get("account_side")
                or evidence.get("expected_side")
                or evidence.get("account_role")
            )
        )
        if has_side_data:
            return side_aware_closure_match(
                open_item,
                evidence,
                expected_side,
                tolerance=active.get("amount_tolerance", "0.01"),
            ) or pro_soluto_factoring_document_match(
                open_item, evidence, active, expected_side
            )

    if document_keys_match(open_item, evidence, require_both=True):
        if (
            evidence_type in PAYMENT_ORDER_TYPES
            or evidence_type in FACTORING_BRIDGE_TYPES
        ):
            return True
        if evidence_type in UNALLOCATED_EXTERNAL_TYPES:
            return True
        if evidence_type in OPEN_SUPPORT_TYPES:
            return True
        open_amount = amount_for_matching(open_item)
        evidence_amount = amount_for_matching(evidence)
        if evidence_amount is None:
            return pro_soluto_factoring_document_match(
                open_item, evidence, active, expected_side
            )
        if pro_soluto_factoring_document_match(
            open_item, evidence, active, expected_side
        ):
            return True
        return amounts_equal(
            evidence_amount, open_amount, active.get("amount_tolerance", "0.01")
        )

    if expected_side:
        return side_aware_closure_match(
            open_item,
            evidence,
            expected_side,
            tolerance=active.get("amount_tolerance", "0.01"),
        ) or pro_soluto_factoring_document_match(
            open_item, evidence, active, expected_side
        )

    if not document_keys_match(open_item, evidence, require_both=True):
        return False
    return amounts_equal(
        amount_for_matching(open_item),
        amount_for_matching(evidence),
        active.get("amount_tolerance", "0.01"),
    )


def grouped_external_support(
    bridge_evidence: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = merged_assumptions(assumptions)
    batch_ids = set()
    for field in ("batch_id", "group_id", "batch_ids", "group_ids"):
        batch_ids.update(split_tokens(bridge_evidence.get(field)))
    batch_total = first_amount(
        bridge_evidence, ("batch_total", "group_total", "amount")
    )
    if batch_total is None:
        return {}
    bridge_date = record_date(
        bridge_evidence, ("value_date", "posting_date", "document_date", "date")
    )

    for evidence in evidence_rows:
        if evidence is bridge_evidence:
            continue
        if active.get("post_cutoff_events_excluded") and is_after_cutoff(
            evidence, active
        ):
            continue
        evidence_type = normalized_evidence_type(evidence)
        source_role = clean_text(evidence.get("source_role")).lower()
        external_bank_support = (
            evidence_type in UNALLOCATED_EXTERNAL_TYPES
            and source_role == "bank_statement"
        )
        if (
            evidence_level(evidence, active) not in CLOSED_EVIDENCE_LEVELS
            and not external_bank_support
        ):
            continue
        evidence_amount = amount_for_matching(evidence)
        if not amounts_equal(
            evidence_amount, batch_total, active.get("amount_tolerance", "0.01")
        ):
            continue
        evidence_batches = set()
        for field in ("batch_id", "group_id", "batch_ids", "group_ids"):
            evidence_batches.update(split_tokens(evidence.get(field)))
        if batch_ids and evidence_batches and batch_ids & evidence_batches:
            return evidence
        bridge_keys = record_document_keys(bridge_evidence)
        evidence_keys = record_document_keys(evidence)
        if evidence_keys and bridge_keys and not (evidence_keys & bridge_keys):
            continue
        evidence_date = record_date(
            evidence, ("value_date", "posting_date", "document_date", "date")
        )
        if bridge_date and evidence_date and bridge_date == evidence_date:
            return evidence
    return {}


def _row_identity(row: dict[str, Any]) -> str:
    return (
        clean_text(row.get("record_id"))
        or clean_text(row.get("document_key"))
        or row_text(row)
    )


def _candidate_id(candidate_type: str, bank_row: dict[str, Any], extra: str) -> str:
    raw = "|".join([candidate_type, _row_identity(bank_row), extra])
    return f"candidate:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _row_amount(row: dict[str, Any]) -> Decimal:
    return amount_for_matching(row) or Decimal("0.00")


def _batch_ids(row: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for field in ("batch_id", "group_id", "batch_ids", "group_ids"):
        ids.update(split_tokens(row.get(field)))
    return ids


def _is_bank_allocation_source(
    row: dict[str, Any], assumptions: dict[str, Any]
) -> bool:
    if assumptions.get("post_cutoff_events_excluded") and is_after_cutoff(
        row, assumptions
    ):
        return False
    source_role = clean_text(row.get("source_role")).lower()
    return source_role == "bank_statement"


def _is_unallocated_bank_pool_source(row: dict[str, Any]) -> bool:
    return normalized_evidence_type(
        row
    ) in UNALLOCATED_EXTERNAL_TYPES or not record_document_keys(row)


def _non_closed_reconciliation_rows(
    reconciliation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in reconciliation_rows
        if clean_text(row.get("reconciliation_status"))
        not in {"closed", "out_of_scope"}
    ]


def _reconciliation_document_index(
    reconciliation_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in _non_closed_reconciliation_rows(reconciliation_rows):
        for key in record_document_keys(row):
            index.setdefault(key, []).append(row)
    return index


def _rows_for_document_keys(
    keys: list[str] | tuple[str, ...] | set[str],
    index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for key in keys:
        for row in index.get(key, []):
            identity = _row_identity(row)
            if identity not in seen:
                seen.add(identity)
                rows.append(row)
    return rows


def _candidate_row(
    *,
    candidate_type: str,
    confidence: str,
    bank_row: dict[str, Any],
    open_rows: list[dict[str, Any]],
    document_keys: list[str],
    evidence_basis: str,
    required_follow_up: str,
    match_details: dict[str, Any] | None = None,
    changes_status: bool = False,
) -> dict[str, Any]:
    bank_amount = _row_amount(bank_row)
    open_total = sum_amounts([_row_amount(row) for row in open_rows])
    amount_difference = (bank_amount - open_total).quantize(Decimal("0.01"))
    open_ids = [_row_identity(row) for row in open_rows]
    status_counts: dict[str, int] = {}
    for row in open_rows:
        status = clean_text(row.get("reconciliation_status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    details = match_details or {}
    return {
        "candidate_id": _candidate_id(
            candidate_type, bank_row, ";".join(document_keys + open_ids)
        ),
        "candidate_type": candidate_type,
        "candidate_confidence": confidence,
        "does_not_change_status": "NO" if changes_status else "YES",
        "candidate_reconciliation_effect": (
            "promotes_to_probable_payment" if changes_status else "advisory_only"
        ),
        "bank_record_id": clean_text(bank_row.get("record_id")),
        "bank_source_file": clean_text(bank_row.get("source_file")),
        "bank_source_page": clean_text(bank_row.get("source_page")),
        "bank_source_row": clean_text(bank_row.get("source_row")),
        "bank_date": record_date(bank_row),
        "bank_amount": f"{bank_amount:.2f}",
        "bank_description": clean_text(bank_row.get("description")),
        "candidate_open_record_ids": "; ".join(open_ids),
        "candidate_document_keys": "; ".join(document_keys),
        "candidate_open_row_count": len(open_rows),
        "candidate_open_amount_total": f"{open_total:.2f}",
        "amount_difference_bank_minus_open": f"{amount_difference:.2f}",
        "candidate_open_status_counts": "; ".join(
            f"{key}:{value}" for key, value in sorted(status_counts.items())
        ),
        "evidence_basis": evidence_basis,
        "required_follow_up": required_follow_up,
        **details,
    }


def bank_allocation_candidates(
    reconciliation_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return advisory candidate allocations for otherwise unallocated bank rows.

    This layer is intentionally non-closing. It highlights possible false
    negatives where bank money exists but deterministic row-level allocation is
    not yet strong enough to change the reconciliation status.
    """

    active = merged_assumptions(assumptions)
    tolerance = active.get("amount_tolerance", "0.01")
    promote_probable = assumption_enabled(active, "promote_probable_bank_payments")
    document_index = _reconciliation_document_index(reconciliation_rows)
    bank_rows = [
        row for row in evidence_rows if _is_bank_allocation_source(row, active)
    ]

    payment_rows_by_batch: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        if normalized_evidence_type(row) not in PAYMENT_ORDER_TYPES:
            continue
        if active.get("post_cutoff_events_excluded") and is_after_cutoff(row, active):
            continue
        for batch_id in _batch_ids(row):
            payment_rows_by_batch.setdefault(batch_id, []).append(row)

    candidates: list[dict[str, Any]] = []
    bank_rows_with_specific_candidate: set[str] = set()

    for bank_row in bank_rows:
        bank_identity = _row_identity(bank_row)
        bank_date = record_date(bank_row)
        bank_amount = _row_amount(bank_row)
        reference_keys = invoice_reference_keys_from_text(
            row_text(bank_row, ("document_no", "description")),
            fallback_date=bank_date,
            assumptions=active,
        )
        if reference_keys:
            open_rows = _rows_for_document_keys(reference_keys, document_index)
            if open_rows:
                open_total = sum_amounts([_row_amount(row) for row in open_rows])
                unmatched = sorted(
                    set(reference_keys)
                    - {key for row in open_rows for key in record_document_keys(row)}
                )
                exact_amount = amounts_equal(bank_amount, open_total, tolerance)
                confidence = "high" if exact_amount and not unmatched else "medium"
                candidates.append(
                    _candidate_row(
                        candidate_type="invoice_refs_in_bank_description",
                        confidence=confidence,
                        bank_row=bank_row,
                        open_rows=open_rows,
                        document_keys=reference_keys,
                        evidence_basis="Bank description contains invoice references that map to non-closed reconciliation rows.",
                        required_follow_up=(
                            "Verify the bank description and allocation support. Promote only if the engagement accepts the "
                            "bank document list as allocation evidence or if a receipt/allocation schedule confirms the rows."
                        ),
                        match_details={
                            "bank_reference_keys_found": "; ".join(reference_keys),
                            "unmatched_reference_keys": "; ".join(unmatched),
                            "candidate_amount_match": "YES" if exact_amount else "NO",
                        },
                        changes_status=promote_probable
                        and confidence in {"high", "medium"},
                    )
                )
                bank_rows_with_specific_candidate.add(bank_identity)

        shared_batches = sorted(_batch_ids(bank_row) & set(payment_rows_by_batch))
        for batch_id in shared_batches:
            payment_rows = payment_rows_by_batch[batch_id]
            payment_keys = sorted(
                {key for row in payment_rows for key in record_document_keys(row)}
            )
            open_rows = _rows_for_document_keys(payment_keys, document_index)
            if not open_rows:
                continue
            payment_total = sum_amounts([_row_amount(row) for row in payment_rows])
            open_total = sum_amounts([_row_amount(row) for row in open_rows])
            exact_bank_to_payment = amounts_equal(bank_amount, payment_total, tolerance)
            exact_bank_to_open = amounts_equal(bank_amount, open_total, tolerance)
            confidence = (
                "high" if exact_bank_to_payment and exact_bank_to_open else "medium"
            )
            candidates.append(
                _candidate_row(
                    candidate_type="batch_id_candidate",
                    confidence=confidence,
                    bank_row=bank_row,
                    open_rows=open_rows,
                    document_keys=payment_keys,
                    evidence_basis="Bank row and payment-order evidence share the same batch/distinta identifier.",
                    required_follow_up=(
                        "Verify the payment-order batch against bank execution and any offset/compensation lines. "
                        "Promote only if the batch allocation explains the specific open rows."
                    ),
                    match_details={
                        "batch_id": batch_id,
                        "payment_order_row_count": len(payment_rows),
                        "payment_order_amount_total": f"{payment_total:.2f}",
                        "candidate_bank_matches_payment_order_total": (
                            "YES" if exact_bank_to_payment else "NO"
                        ),
                        "candidate_bank_matches_nonclosed_open_total": (
                            "YES" if exact_bank_to_open else "NO"
                        ),
                    },
                    changes_status=promote_probable
                    and confidence in {"high", "medium"},
                )
            )
            bank_rows_with_specific_candidate.add(bank_identity)

    for bank_row in bank_rows:
        bank_identity = _row_identity(bank_row)
        if (
            bank_identity in bank_rows_with_specific_candidate
            or not _is_unallocated_bank_pool_source(bank_row)
        ):
            continue
        candidates.append(
            _candidate_row(
                candidate_type="unallocated_counterparty_bank_pool",
                confidence="low",
                bank_row=bank_row,
                open_rows=[],
                document_keys=[],
                evidence_basis="Bank movement with relevant counterparty/operator text but no deterministic invoice or batch allocation.",
                required_follow_up=(
                    "Obtain bank receipts, cash application detail, payment schedules, or operator ledger that allocate this "
                    "movement to invoice-level rows."
                ),
            )
        )

    return sorted(
        candidates,
        key=lambda row: (
            row.get("candidate_confidence") != "high",
            row.get("candidate_confidence") != "medium",
            row.get("bank_date"),
            row.get("bank_source_file"),
            row.get("bank_source_page"),
            row.get("bank_source_row"),
            row.get("candidate_id"),
        ),
    )


def bank_candidate_reference(candidate: dict[str, Any]) -> str:
    bits = []
    for label, field in (
        ("file", "bank_source_file"),
        ("page", "bank_source_page"),
        ("row", "bank_source_row"),
        ("id", "bank_record_id"),
    ):
        value = clean_text(candidate.get(field))
        if value:
            bits.append(f"{label}={value}")
    return "; ".join(bits)


def bank_candidate_amount_summary(candidate: dict[str, Any]) -> str:
    fields = (
        ("bank_amount", "bank_amount"),
        ("candidate_open_amount_total", "candidate_open_amount_total"),
        ("amount_difference_bank_minus_open", "amount_difference_bank_minus_open"),
        ("payment_order_amount_total", "payment_order_amount_total"),
    )
    return "; ".join(
        f"{label}={clean_text(candidate.get(field))}"
        for label, field in fields
        if clean_text(candidate.get(field))
    )


def bank_candidate_match_basis(candidate: dict[str, Any]) -> str:
    fields = (
        "candidate_type",
        "evidence_basis",
        "bank_reference_keys_found",
        "batch_id",
        "candidate_amount_match",
        "candidate_bank_matches_payment_order_total",
        "candidate_bank_matches_nonclosed_open_total",
    )
    return "; ".join(
        f"{field}={clean_text(candidate.get(field))}"
        for field in fields
        if clean_text(candidate.get(field))
    )


def bank_candidate_is_exact_closure(
    candidate: dict[str, Any], assumptions: dict[str, Any]
) -> bool:
    if not assumption_enabled(assumptions, "probable_bank_exact_matches_close"):
        return False
    if clean_text(candidate.get("candidate_confidence")) != "high":
        return False
    if clean_text(candidate.get("candidate_amount_match")).upper() == "YES":
        return True
    return (
        clean_text(candidate.get("candidate_bank_matches_payment_order_total")).upper()
        == "YES"
        and clean_text(
            candidate.get("candidate_bank_matches_nonclosed_open_total")
        ).upper()
        == "YES"
    )


def bank_candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, Decimal, str]:
    confidence_rank = {"high": 0, "medium": 1}.get(
        clean_text(candidate.get("candidate_confidence")),
        9,
    )
    exact = (
        clean_text(candidate.get("candidate_amount_match")).upper() == "YES"
        or clean_text(
            candidate.get("candidate_bank_matches_payment_order_total")
        ).upper()
        == "YES"
    )
    amount_difference = abs(
        parse_decimal(candidate.get("amount_difference_bank_minus_open"))
        or Decimal("999999999999.99")
    )
    return (
        confidence_rank,
        0 if exact else 1,
        amount_difference,
        clean_text(candidate.get("candidate_id")),
    )


def promote_probable_bank_payments(
    reconciliation_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> list[dict[str, Any]]:
    if not assumption_enabled(assumptions, "promote_probable_bank_payments"):
        return reconciliation_rows

    candidates = bank_allocation_candidates(
        reconciliation_rows, evidence_rows, assumptions
    )
    candidates_by_open_id: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if clean_text(candidate.get("candidate_confidence")) not in {"high", "medium"}:
            continue
        for open_id in split_tokens(candidate.get("candidate_open_record_ids")):
            candidates_by_open_id.setdefault(open_id, []).append(candidate)

    promoted_rows: list[dict[str, Any]] = []
    for row in reconciliation_rows:
        status = clean_text(row.get("reconciliation_status"))
        if status in {"closed", "out_of_scope"}:
            promoted_rows.append(row)
            continue
        row_id = _row_identity(row)
        candidate_list = candidates_by_open_id.get(row_id, [])
        if not candidate_list:
            promoted_rows.append(row)
            continue

        candidate = sorted(candidate_list, key=bank_candidate_sort_key)[0]
        bank_reference = bank_candidate_reference(candidate)
        exact_closure = bank_candidate_is_exact_closure(candidate, assumptions)
        promoted = dict(row)
        for field in (
            "reconciliation_status",
            "evidence_level",
            "rule_applied",
            "matched_evidence_type",
            "matched_evidence_amounts",
            "matched_evidence_id",
            "matched_evidence_reference",
            "missing_evidence",
        ):
            prior_field = f"prior_{field}"
            if clean_text(row.get(field)) and not clean_text(promoted.get(prior_field)):
                promoted[prior_field] = row.get(field)

        promoted.update(
            {
                "reconciliation_status": (
                    "closed" if exact_closure else PROBABLE_BANK_PAYMENT_STATUS
                ),
                "evidence_level": (
                    "strong_external" if exact_closure else "probable_external"
                ),
                "rule_applied": (
                    "external_bank_exact_allocation_match"
                    if exact_closure
                    else "probable_bank_payment_candidate"
                ),
                "matched_evidence_type": (
                    "external_bank" if exact_closure else "probable_external_bank"
                ),
                "matched_evidence_amounts": bank_candidate_amount_summary(candidate),
                "matched_evidence_id": clean_text(candidate.get("bank_record_id")),
                "matched_evidence_reference": bank_reference,
                "missing_evidence": (
                    ""
                    if exact_closure
                    else missing_evidence_message(
                        "probable_bank_payment_candidate", assumptions
                    )
                ),
                "probable_bank_candidate_id": clean_text(candidate.get("candidate_id")),
                "probable_bank_confidence": clean_text(
                    candidate.get("candidate_confidence")
                ),
                "probable_bank_reference": bank_reference,
                "probable_bank_record_id": clean_text(candidate.get("bank_record_id")),
                "probable_bank_date": clean_text(candidate.get("bank_date")),
                "probable_bank_amount": clean_text(candidate.get("bank_amount")),
                "probable_bank_description": clean_text(
                    candidate.get("bank_description")
                ),
                "probable_bank_match_basis": bank_candidate_match_basis(candidate),
                "probable_bank_amount_difference": clean_text(
                    candidate.get("amount_difference_bank_minus_open")
                ),
                "probable_bank_required_follow_up": clean_text(
                    candidate.get("required_follow_up")
                ),
            }
        )
        promoted_rows.append(promoted)
    return promoted_rows


def direct_supporting_bank_by_key(
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    support_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        if assumptions.get("post_cutoff_events_excluded") and is_after_cutoff(
            row, assumptions
        ):
            continue
        source_role = clean_text(row.get("source_role")).lower()
        evidence_type = normalized_evidence_type(row)
        if source_role != "bank_statement" and evidence_type != "external_bank":
            continue
        for key in record_document_keys(row):
            support_by_key.setdefault(key, []).append(row)
    return support_by_key


def add_supporting_bank_references(
    reconciliation_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> list[dict[str, Any]]:
    support_by_key = direct_supporting_bank_by_key(evidence_rows, assumptions)
    if not support_by_key:
        return reconciliation_rows

    enriched_rows: list[dict[str, Any]] = []
    tolerance = assumptions.get("amount_tolerance", "0.01")
    for row in reconciliation_rows:
        shared_bank_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in record_document_keys(row):
            for bank_row in support_by_key.get(key, []):
                identity = _row_identity(bank_row)
                if identity not in seen:
                    seen.add(identity)
                    shared_bank_rows.append(bank_row)
        if not shared_bank_rows:
            enriched_rows.append(row)
            continue

        row_amount = amount_for_matching(row)
        best = sorted(
            shared_bank_rows,
            key=lambda bank_row: (
                not amounts_equal(
                    _external_cash_amount(bank_row), row_amount, tolerance
                ),
                clean_text(bank_row.get("source_role")).lower() != "bank_statement",
                evidence_reference(bank_row),
                _row_identity(bank_row),
            ),
        )[0]
        enriched = dict(row)
        enriched.update(
            {
                "supporting_bank_reference": evidence_reference(best),
                "supporting_bank_record_id": clean_text(best.get("record_id")),
                "supporting_bank_date": record_date(best),
                "supporting_bank_amount": f"{_external_cash_amount(best):.2f}",
                "supporting_bank_description": clean_text(best.get("description")),
                "supporting_bank_rule": "same_document_bank_reference",
            }
        )
        enriched_rows.append(enriched)
    return enriched_rows


def _configured_keywords(assumptions: dict[str, Any], key: str) -> list[str]:
    return [
        clean_text(value).lower()
        for value in assumptions.get(key, [])
        if clean_text(value)
    ]


def _contains_configured_keyword(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _favours_keyword(text: str, keywords: list[str]) -> bool:
    return any(
        keyword
        and (
            f"a favore di {keyword}" in text
            or f"favore di {keyword}" in text
            or f"beneficiario {keyword}" in text
            or f"beneficiary {keyword}" in text
        )
        for keyword in keywords
    )


def _external_cash_amount(row: dict[str, Any]) -> Decimal:
    return amount_for_matching(row) or external_amount_total(row) or Decimal("0.00")


def external_evidence_classification(
    row: dict[str, Any], assumptions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Classify external cash/factor evidence without using internal accounting as proof."""

    active = merged_assumptions(assumptions)
    text = row_text(row).lower()
    counterparty_keywords = _configured_keywords(active, "counterparty_keywords")
    factor_keywords = _configured_keywords(active, "factoring_operator_keywords")
    own_party_keywords = _configured_keywords(active, "own_party_keywords")
    has_counterparty = _contains_configured_keyword(text, counterparty_keywords)
    has_factor = is_factoring_evidence(row, active) or _contains_configured_keyword(
        text, factor_keywords
    )
    incoming_to_own = (
        _favours_keyword(text, own_party_keywords) if own_party_keywords else False
    )
    outgoing_to_counterparty = (
        _favours_keyword(text, counterparty_keywords) and not incoming_to_own
    )
    amount = _external_cash_amount(row)

    category = "other_external"
    cash_flow_signed = Decimal("0.00")
    settlement_signed = Decimal("0.00")
    treatment = "External row kept separate; no configured settlement effect."
    direction_confidence = "low"

    if "addebito" in text and has_factor:
        category = "factor_or_operator_debit_fee"
        cash_flow_signed = -amount
        treatment = "Operator/bank debit or fee; not treated as invoice settlement."
        direction_confidence = "medium"
    elif "rientro anticipo" in text or "repayment of advance" in text:
        category = "bank_advance_repayment"
        cash_flow_signed = -amount
        treatment = "Repayment of bank advance/financing; not treated as customer payment by itself."
        direction_confidence = "medium"
    elif (
        "anticipo su documenti" in text
        or "anticipo fatture" in text
        or "advance on invoices" in text
    ):
        category = "bank_advance_credit"
        cash_flow_signed = amount
        treatment = "Bank advance/financing cash inflow; not treated as customer settlement unless separately configured/documented."
        direction_confidence = "medium"
    elif has_factor and (incoming_to_own or ("bonifico" in text or "wire" in text)):
        category = "factor_operator_cash_inflow"
        cash_flow_signed = amount
        if active.get("factoring_pro_soluto_closes_item"):
            settlement_signed = -amount
            treatment = "Factor/operator cash inflow treated as settlement under configured pro-soluto assumption."
        else:
            treatment = "Factor/operator cash inflow; settlement effect disabled by assumptions."
        direction_confidence = "high" if incoming_to_own else "medium"
    elif has_counterparty and incoming_to_own:
        category = "direct_counterparty_bank_receipt"
        cash_flow_signed = amount
        settlement_signed = -amount
        treatment = "Direct bank receipt from counterparty reduces receivable/exposure."
        direction_confidence = "high"
    elif has_counterparty and outgoing_to_counterparty:
        category = "direct_counterparty_bank_payment"
        cash_flow_signed = -amount
        settlement_signed = amount
        treatment = "Direct bank payment to counterparty reduces payable and increases net receivable position."
        direction_confidence = "high"
    elif has_counterparty:
        category = "counterparty_bank_other"
        treatment = "Counterparty bank movement with unclear direction/allocation; not netted into settlement effect."
        direction_confidence = "low"
    elif has_factor:
        category = "factor_operator_other"
        treatment = "Factor/operator external movement with unclear direction/allocation; not netted into settlement effect."
        direction_confidence = "low"

    return {
        "external_category": category,
        "cash_flow_signed": cash_flow_signed.quantize(Decimal("0.01")),
        "settlement_effect_signed_net_debit_minus_credit": settlement_signed.quantize(
            Decimal("0.01")
        ),
        "direction_confidence": direction_confidence,
        "external_treatment": treatment,
    }


def external_evidence_detail_rows(
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a deterministic external-evidence schedule from bank/factor rows.

    Positive settlement effect increases net receivable debit-minus-credit;
    negative settlement effect reduces it. Financing advances are shown as cash
    flows but have zero settlement effect unless separately supported.
    """

    active = merged_assumptions(assumptions)
    detail: list[dict[str, Any]] = []
    for row in evidence_rows:
        if active.get("post_cutoff_events_excluded") and is_after_cutoff(row, active):
            continue
        source_role = clean_text(row.get("source_role")).lower()
        evidence_type = normalized_evidence_type(row)
        if (
            source_role not in {"bank_statement", "factoring_statement"}
            and evidence_type not in EXTERNAL_TYPES
        ):
            continue
        amount = _external_cash_amount(row)
        if amount == Decimal("0.00"):
            continue
        classification = external_evidence_classification(row, active)
        detail.append(
            {
                "record_id": clean_text(row.get("record_id")),
                "source_file": clean_text(row.get("source_file")),
                "source_page": clean_text(row.get("source_page")),
                "source_row": clean_text(row.get("source_row")),
                "source_role": source_role,
                "evidence_type": evidence_type,
                "posting_date": record_date(row),
                "document_key": "; ".join(sorted(record_document_keys(row))),
                "amount": f"{amount:.2f}",
                "external_category": classification["external_category"],
                "cash_flow_signed": f"{classification['cash_flow_signed']:.2f}",
                "settlement_effect_signed_net_debit_minus_credit": f"{classification['settlement_effect_signed_net_debit_minus_credit']:.2f}",
                "direction_confidence": classification["direction_confidence"],
                "external_treatment": classification["external_treatment"],
                "description": clean_text(row.get("description")),
                "source_reference": evidence_reference(row),
            }
        )
    return sorted(
        detail,
        key=lambda row: (
            row.get("posting_date"),
            row.get("source_file"),
            row.get("source_page"),
            row.get("source_row"),
            row.get("record_id"),
        ),
    )


def external_evidence_summary(
    detail_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in detail_rows:
        category = clean_text(row.get("external_category")) or "unknown"
        bucket = buckets.setdefault(
            category,
            {
                "external_category": category,
                "rows": 0,
                "amount_total": Decimal("0.00"),
                "cash_flow_signed_total": Decimal("0.00"),
                "settlement_effect_signed_net_debit_minus_credit": Decimal("0.00"),
            },
        )
        bucket["rows"] += 1
        bucket["amount_total"] += parse_decimal(row.get("amount")) or Decimal("0.00")
        bucket["cash_flow_signed_total"] += parse_decimal(
            row.get("cash_flow_signed")
        ) or Decimal("0.00")
        bucket["settlement_effect_signed_net_debit_minus_credit"] += parse_decimal(
            row.get("settlement_effect_signed_net_debit_minus_credit")
        ) or Decimal("0.00")

    rows = [
        {
            "external_category": bucket["external_category"],
            "rows": bucket["rows"],
            "amount_total": f"{bucket['amount_total']:.2f}",
            "cash_flow_signed_total": f"{bucket['cash_flow_signed_total']:.2f}",
            "settlement_effect_signed_net_debit_minus_credit": f"{bucket['settlement_effect_signed_net_debit_minus_credit']:.2f}",
        }
        for bucket in sorted(
            buckets.values(), key=lambda item: item["external_category"]
        )
    ]
    if rows:
        rows.insert(
            0,
            {
                "external_category": "TOTAL",
                "rows": sum(int(row["rows"]) for row in rows),
                "amount_total": f"{sum((parse_decimal(row['amount_total']) or Decimal('0.00')) for row in rows):.2f}",
                "cash_flow_signed_total": f"{sum((parse_decimal(row['cash_flow_signed_total']) or Decimal('0.00')) for row in rows):.2f}",
                "settlement_effect_signed_net_debit_minus_credit": f"{sum((parse_decimal(row['settlement_effect_signed_net_debit_minus_credit']) or Decimal('0.00')) for row in rows):.2f}",
            },
        )
    return rows


def missing_evidence_message(
    rule: str, assumptions: dict[str, Any] | None = None
) -> str:
    active = merged_assumptions(assumptions)
    language = configured_language(active, purpose="report")
    messages = missing_evidence_messages(language)
    return (
        messages.get(rule)
        or messages.get("default")
        or missing_evidence_messages("en")["default"]
    )


def grouped_open_amount_support_by_row(
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Find same-document open-item splits supported by one aggregate booking.

    Some open-item schedules split one document across multiple rows while the
    ledger carries one aggregate invoice booking. This is open support, not a
    closing event. The rule is deliberately narrow: same source file, same side,
    same document alias/year, same document date, and exact group amount match.
    """

    active = merged_assumptions(assumptions)

    def group_document_key(row: dict[str, Any]) -> str:
        numeric_keys = sorted(
            key
            for key in record_document_keys(row)
            if re.fullmatch(r"\d+\|20\d{2}", key)
        )
        return numeric_keys[0] if numeric_keys else resolved_document_key(row)

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in open_items:
        if not is_open_item_in_scope(row, active):
            continue
        key = group_document_key(row)
        row_date = record_date(row, ("document_date", "posting_date", "date"))
        if not key or not row_date:
            continue
        group_key = (
            clean_text(row.get("source_file")),
            clean_text(row.get("source_side") or row.get("expected_side")),
            key,
            row_date,
        )
        groups.setdefault(group_key, []).append(row)

    support_by_row: dict[str, dict[str, Any]] = {}
    for (source_file, source_side, key, row_date), group_rows in groups.items():
        if len(group_rows) <= 1:
            continue
        group_total = sum_amounts([amount_for_matching(row) for row in group_rows])
        if group_total == Decimal("0.00"):
            continue
        candidates: list[dict[str, Any]] = []
        for evidence in evidence_rows:
            if active.get("post_cutoff_events_excluded") and is_after_cutoff(
                evidence, active
            ):
                continue
            if normalized_evidence_type(evidence) not in OPEN_SUPPORT_TYPES:
                continue
            evidence_date = record_date(
                evidence, ("document_date", "posting_date", "date")
            )
            if evidence_date and evidence_date != row_date:
                continue
            if key not in record_document_keys(evidence):
                continue
            if source_side and side_conflicts_with_expected(
                group_rows[0], evidence, source_side, active
            ):
                continue
            if amounts_equal(
                amount_for_matching(evidence),
                group_total,
                active.get("amount_tolerance", "0.01"),
            ):
                candidates.append(evidence)
        if not candidates:
            continue
        evidence = sorted(
            candidates,
            key=lambda item: (
                clean_text(item.get("source_role")) != "ledger",
                clean_text(item.get("source_role")) != "journal",
                evidence_reference(item),
                _row_identity(item),
            ),
        )[0]
        for row in group_rows:
            identity = _row_identity(row)
            if identity:
                support_by_row[identity] = {
                    "evidence": evidence,
                    "group_source_file": source_file,
                    "group_source_side": source_side,
                    "group_document_key": key,
                    "group_document_date": row_date,
                    "group_row_count": len(group_rows),
                    "group_open_amount_total": f"{group_total:.2f}",
                }
    return support_by_row


def classify_open_item(
    open_item: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
    candidate_evidence_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active = merged_assumptions(assumptions)
    result = dict(open_item)
    result.setdefault("record_id", clean_text(open_item.get("record_id")))
    result["document_key"] = resolved_document_key(open_item)

    if not is_open_item_in_scope(open_item, active):
        result.update(
            {
                "reconciliation_status": "out_of_scope",
                "evidence_level": "out_of_scope",
                "rule_applied": "out_of_scope",
                "matched_evidence_type": "",
                "matched_evidence_amounts": "",
                "matched_evidence_id": "",
                "matched_evidence_reference": "",
                "missing_evidence": "",
            }
        )
        return result

    match_pool = (
        candidate_evidence_rows
        if candidate_evidence_rows is not None
        else evidence_rows
    )
    matches = [
        row for row in match_pool if evidence_matches_open_item(open_item, row, active)
    ]
    ranked: list[tuple[int, dict[str, Any], str, str]] = []
    for evidence in matches:
        level = evidence_level(evidence, active)
        evidence_type = normalized_evidence_type(evidence)
        if level in CLOSED_EVIDENCE_LEVELS:
            ranked.append(
                (0, evidence, level, closed_rule_for_evidence(evidence, active))
            )
        elif level == "bridge_only" and (
            evidence_type in PAYMENT_ORDER_TYPES
            or evidence_type in FACTORING_BRIDGE_TYPES
        ):
            if evidence_type in PAYMENT_ORDER_TYPES:
                allocated_amount = amount_for_matching(evidence)
                open_amount = amount_for_matching(open_item)
                if allocated_amount is None or not amounts_equal(
                    allocated_amount,
                    open_amount,
                    active.get("amount_tolerance", "0.01"),
                ):
                    ranked.append((6, evidence, level, "payment_order_amount_mismatch"))
                    continue
            support = grouped_external_support(evidence, evidence_rows, active)
            if support:
                ranked.append(
                    (0, support, "strong_external", "grouped_payment_external_match")
                )
            else:
                ranked.append(
                    (
                        2,
                        evidence,
                        level,
                        (
                            "factoring_bridge_only"
                            if evidence_type in FACTORING_BRIDGE_TYPES
                            else "payment_order_only"
                        ),
                    )
                )
        elif level == "bridge_only" and evidence_type in UNALLOCATED_EXTERNAL_TYPES:
            ranked.append(
                (2, evidence, level, "unallocated_external_bank_requires_allocation")
            )
        elif level == "bridge_only" and (
            evidence_type == "compensation"
            or any_keyword_in(row_text(evidence), COMPENSATION_KEYWORDS)
        ):
            ranked.append((2, evidence, level, "compensation_needs_external_support"))
        elif level == "weak_internal" and evidence_type in INTERNAL_CLOSURE_TYPES:
            ranked.append((2, evidence, level, "internal_closure_without_external"))
        elif level == "weak_internal" and evidence_type in OPEN_SUPPORT_TYPES:
            ranked.append((3, evidence, level, "internal_booking_open_support"))
        elif level == "weak_internal":
            ranked.append((3, evidence, level, "internal_accounting_only"))

    if ranked:
        _, evidence, level, rule = sorted(
            ranked,
            key=lambda item: (
                item[0],
                clean_text(item[1].get("record_id")),
                evidence_reference(item[1]),
            ),
        )[0]
        closed = level in CLOSED_EVIDENCE_LEVELS
        open_supported = rule == "internal_booking_open_support"
        result.update(
            {
                "reconciliation_status": (
                    "closed"
                    if closed
                    else ("open_supported" if open_supported else "needs_evidence")
                ),
                "evidence_level": level,
                "rule_applied": rule,
                "matched_evidence_type": normalized_evidence_type(evidence),
                "matched_evidence_amounts": evidence_amount_summary(evidence),
                "matched_evidence_id": clean_text(evidence.get("record_id")),
                "matched_evidence_reference": evidence_reference(evidence),
                "missing_evidence": (
                    "" if closed else missing_evidence_message(rule, active)
                ),
            }
        )
        return result

    result.update(
        {
            "reconciliation_status": "unresolved",
            "evidence_level": "none",
            "rule_applied": "unresolved",
            "matched_evidence_type": "",
            "matched_evidence_amounts": "",
            "matched_evidence_id": "",
            "matched_evidence_reference": "",
            "missing_evidence": missing_evidence_message("unresolved", active),
        }
    )
    return result


def reconcile_open_items(
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    active = merged_assumptions(assumptions)
    evidence_index = build_evidence_document_index(evidence_rows)
    grouped_support = grouped_open_amount_support_by_row(
        open_items, evidence_rows, active
    )
    reconciliation_rows: list[dict[str, Any]] = []
    for row in open_items:
        classified = classify_open_item(
            row,
            evidence_rows,
            active,
            candidate_evidence_rows=evidence_candidates_for_open_item(
                row, evidence_rows, evidence_index
            ),
        )
        support = grouped_support.get(_row_identity(row))
        if support and clean_text(classified.get("rule_applied")) in {
            "unresolved",
            "payment_order_amount_mismatch",
            "internal_booking_open_support",
        }:
            evidence = support["evidence"]
            amount_summary = evidence_amount_summary(evidence)
            group_summary = (
                f"group_open_amount_total={support['group_open_amount_total']}; "
                f"group_rows={support['group_row_count']}"
            )
            classified.update(
                {
                    "reconciliation_status": "open_supported",
                    "evidence_level": evidence_level(evidence, active),
                    "rule_applied": "grouped_open_amount_internal_booking_support",
                    "matched_evidence_type": normalized_evidence_type(evidence),
                    "matched_evidence_amounts": "; ".join(
                        filter(None, [amount_summary, group_summary])
                    ),
                    "matched_evidence_id": clean_text(evidence.get("record_id")),
                    "matched_evidence_reference": evidence_reference(evidence),
                    "missing_evidence": missing_evidence_message(
                        "grouped_open_amount_internal_booking_support", active
                    ),
                }
            )
        reconciliation_rows.append(classified)
    reconciliation_rows = promote_probable_bank_payments(
        reconciliation_rows, evidence_rows, active
    )
    return add_supporting_bank_references(reconciliation_rows, evidence_rows, active)


def reconciliation_checks(
    open_items: list[dict[str, Any]],
    reconciliation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic completeness gates for a reconciliation run."""

    valid_statuses = {
        "closed",
        PROBABLE_BANK_PAYMENT_STATUS,
        "open_supported",
        "needs_evidence",
        "unresolved",
        "out_of_scope",
    }
    checks: list[dict[str, Any]] = []

    def add(
        name: str, passed: bool, actual: object, expected: object, note: str = ""
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": "PASS" if passed else "FAIL",
                "actual": actual,
                "expected": expected,
                "note": note,
            }
        )

    add(
        "open_item_count_matches_detail",
        len(open_items) == len(reconciliation_rows),
        len(reconciliation_rows),
        len(open_items),
    )

    invalid_statuses = sorted(
        {
            clean_text(row.get("reconciliation_status"))
            for row in reconciliation_rows
            if clean_text(row.get("reconciliation_status")) not in valid_statuses
        }
    )
    add(
        "classification_statuses_valid",
        not invalid_statuses,
        "; ".join(invalid_statuses),
        "none",
    )

    closed_without_evidence = [
        clean_text(row.get("record_id")) or clean_text(row.get("document_key"))
        for row in reconciliation_rows
        if row.get("reconciliation_status") == "closed"
        and not clean_text(row.get("matched_evidence_reference"))
    ]
    add(
        "closed_rows_have_evidence_reference",
        not closed_without_evidence,
        len(closed_without_evidence),
        0,
        "; ".join(closed_without_evidence[:10]),
    )

    unresolved_without_next_step = [
        clean_text(row.get("record_id")) or clean_text(row.get("document_key"))
        for row in reconciliation_rows
        if row.get("reconciliation_status")
        in {"needs_evidence", "unresolved", PROBABLE_BANK_PAYMENT_STATUS}
        and not clean_text(row.get("missing_evidence"))
    ]
    add(
        "open_rows_have_missing_evidence_request",
        not unresolved_without_next_step,
        len(unresolved_without_next_step),
        0,
        "; ".join(unresolved_without_next_step[:10]),
    )

    payment_order_closed = [
        clean_text(row.get("record_id")) or clean_text(row.get("document_key"))
        for row in reconciliation_rows
        if row.get("reconciliation_status") == "closed"
        and row.get("rule_applied") == "payment_order_only"
    ]
    add(
        "payment_order_only_not_closed",
        not payment_order_closed,
        len(payment_order_closed),
        0,
        "; ".join(payment_order_closed[:10]),
    )

    return checks


def checks_pass(checks: list[dict[str, Any]]) -> bool:
    return all(row.get("status") == "PASS" for row in checks)


def codex_review_sample(
    rows: list[dict[str, Any]],
    sample_size: int = 30,
    seed: str = "audit-reconciliation-review",
    high_value_count: int = 10,
) -> list[dict[str, Any]]:
    """Build a reproducible advisory review sample from deterministic results."""

    if not rows:
        return []

    def amount_abs(row: dict[str, Any]) -> Decimal:
        values = [
            parse_decimal(row.get(field))
            for field in (
                "amount",
                "all_a_balance",
                "balance",
                "open_amount",
                "matched_amount",
            )
        ]
        return max(
            (abs(value) for value in values if value is not None),
            default=Decimal("0.00"),
        )

    selected: dict[str, dict[str, Any]] = {}
    selected_priority: dict[str, int] = {}

    def identity(row: dict[str, Any]) -> str:
        return (
            clean_text(row.get("record_id"))
            or clean_text(row.get("document_key"))
            or row_text(row)
        )

    def add(row: dict[str, Any], reason: str, priority: int) -> None:
        key = identity(row)
        enriched = dict(row)
        existing = clean_text(enriched.get("review_reason"))
        enriched["review_reason"] = "; ".join(filter(None, [existing, reason]))
        if key in selected:
            prior = clean_text(selected[key].get("review_reason"))
            selected[key]["review_reason"] = "; ".join(filter(None, [prior, reason]))
            selected_priority[key] = min(selected_priority[key], priority)
        else:
            selected[key] = enriched
            selected_priority[key] = priority

    for row in sorted(rows, key=lambda item: -amount_abs(item))[:high_value_count]:
        add(row, "high_value", 0)
    for row in rows:
        if row.get("rule_applied") in {
            "grouped_payment_external_match",
            "payment_order_only",
            "compensation_needs_external_support",
            "internal_accounting_only",
        }:
            add(row, "audit_rule_risk", 1)
    for row in rows:
        if codex_review_flags(row):
            add(row, "risk_flag", 2)

    remaining_slots = max(0, sample_size - len(selected))
    if remaining_slots:
        remaining = [row for row in rows if identity(row) not in selected]
        for row in stable_review_sample(
            remaining,
            sample_size=remaining_slots,
            seed=seed,
            include_top_amount=0,
        ):
            add(row, "stable_random", 3)

    return [
        row
        for _, row in sorted(
            selected.items(),
            key=lambda item: (selected_priority[item[0]], identity(item[1])),
        )
    ][:sample_size]


def review_identity(row: dict[str, Any]) -> str:
    return (
        clean_text(row.get("record_id"))
        or clean_text(row.get("document_key"))
        or row_text(row)
    )


def review_amount_abs(row: dict[str, Any]) -> Decimal:
    values = [
        parse_decimal(row.get(field))
        for field in (
            "amount",
            "all_a_balance",
            "balance",
            "open_amount",
            "matched_amount",
        )
    ]
    return max(
        (abs(value) for value in values if value is not None), default=Decimal("0.00")
    )


def review_reason_tokens(row: dict[str, Any]) -> set[str]:
    return {
        token.strip()
        for token in clean_text(
            row.get("review_selection_reason") or row.get("review_reason")
        ).split(";")
        if token.strip()
    }


def row_matches_challenge(
    row: dict[str, Any], challenged_rows: list[str] | tuple[str, ...] | set[str]
) -> bool:
    if not challenged_rows:
        return False
    challenged = {
        clean_text(value).lower() for value in challenged_rows if clean_text(value)
    }
    if not challenged:
        return False
    row_values = {
        clean_text(row.get(field)).lower()
        for field in (
            "record_id",
            "document_key",
            "document_no",
            "source_file",
            "matched_evidence_id",
        )
        if clean_text(row.get(field))
    }
    return bool(challenged & row_values)


def is_reviewable_row(row: dict[str, Any]) -> bool:
    return clean_text(row.get("reconciliation_status")) != "out_of_scope"


def is_mandatory_evidence_review_row(row: dict[str, Any]) -> bool:
    """Rows where a wrong promotion would be material enough to require review."""

    if clean_text(row.get("reconciliation_status")) != "closed":
        return False
    text = " ".join(
        clean_text(row.get(field)).lower()
        for field in (
            "rule_applied",
            "matched_evidence_type",
            "evidence_level",
            "description",
            "matched_evidence_reference",
        )
    )
    return (
        any_keyword_in(text, BANK_KEYWORDS)
        or any_keyword_in(text, FACTOR_KEYWORDS)
        or any_keyword_in(text, COMPENSATION_KEYWORDS)
        or "grouped_payment_external_match" in text
        or "external_bank_match" in text
        or "factoring" in text
        or "compensation" in text
    )


def review_instruction_for_row(row: dict[str, Any]) -> str:
    status = clean_text(row.get("reconciliation_status"))
    rule = clean_text(row.get("rule_applied"))
    if status == "closed":
        return "Verify that the cited evidence really ties this row to document number, date/year, amount or configured strong evidence, and source reference."
    if status == "needs_evidence":
        return "Verify that the row was not promoted to closed without sufficient external/operator/compensation evidence, and that missing evidence is specific."
    if status == PROBABLE_BANK_PAYMENT_STATUS:
        return "Verify that the probable bank movement really allocates to this open item and that no batch, fee, advance or partial-settlement detail is missing."
    if status == "unresolved":
        return "Verify whether any source reference or extracted evidence appears to have been missed; if yes, propose a deterministic rule."
    if rule in {
        "internal_booking_open_support",
        "grouped_open_amount_internal_booking_support",
    }:
        return "Verify that open support is only internal/open-balance support and does not hide a closing evidence item."
    return "Review deterministic classification against matched evidence fields and source reference."


def enrich_review_row(
    row: dict[str, Any], reasons: set[str], seed: str
) -> dict[str, Any]:
    identity = review_identity(row)
    review_id = hashlib.sha256(f"{seed}|{identity}".encode("utf-8")).hexdigest()[:16]
    enriched = dict(row)
    enriched.update(
        {
            "review_id": f"review:{review_id}",
            "review_status": clean_text(enriched.get("review_status")) or "PENDING",
            "review_selection_reason": "; ".join(sorted(reasons)),
            "review_required": "YES",
            "review_instruction": clean_text(enriched.get("review_instruction"))
            or review_instruction_for_row(row),
            "review_notes": clean_text(enriched.get("review_notes")),
            "suggested_rule_change": clean_text(enriched.get("suggested_rule_change")),
            "deterministic_status": clean_text(row.get("reconciliation_status")),
            "deterministic_rule": clean_text(row.get("rule_applied")),
            "deterministic_evidence_level": clean_text(row.get("evidence_level")),
        }
    )
    flags = codex_review_flags(row)
    if flags:
        enriched["review_flags"] = "; ".join(flags)
    return enriched


def build_codex_review_packet(
    reconciliation_rows: list[dict[str, Any]],
    *,
    seed: str = "audit-reconciliation-review",
    high_value_count: int = 10,
    random_count: int = 20,
    challenged_rows: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the mandatory Codex review packet for the deterministic result.

    The packet is advisory control data. It never changes the deterministic row
    classification by itself.
    """

    reviewable = [row for row in reconciliation_rows if is_reviewable_row(row)]
    selected: dict[str, dict[str, Any]] = {}
    reasons_by_id: dict[str, set[str]] = {}

    def add(row: dict[str, Any], reason: str) -> None:
        identity = review_identity(row)
        if not identity:
            return
        selected.setdefault(identity, row)
        reasons_by_id.setdefault(identity, set()).add(reason)

    for row in sorted(
        reviewable, key=lambda item: (-review_amount_abs(item), review_identity(item))
    )[:high_value_count]:
        add(row, "high_value")

    for row in reviewable:
        if is_mandatory_evidence_review_row(row):
            add(row, "mandatory_closure_evidence")
        flags = codex_review_flags(row)
        if flags:
            add(row, "risk_flag")

    for row in reviewable:
        if row_matches_challenge(row, challenged_rows or []):
            add(row, "user_challenged")

    remaining = [row for row in reviewable if review_identity(row) not in selected]
    for row in stable_review_sample(
        remaining,
        sample_size=min(random_count, len(remaining)),
        seed=seed,
        include_top_amount=0,
    ):
        add(row, "stable_random")

    return [
        enrich_review_row(row, reasons_by_id[identity], seed)
        for identity, row in sorted(
            selected.items(),
            key=lambda item: (sorted(reasons_by_id[item[0]])[0], item[0]),
        )
    ]


def codex_review_checks(
    reconciliation_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    *,
    require_completed_review: bool = False,
    high_value_count: int = 10,
    random_count: int = 20,
    challenged_rows: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(
        name: str, passed: bool, actual: object, expected: object, note: str = ""
    ) -> None:
        checks.append(
            {
                "check": name,
                "status": "PASS" if passed else "FAIL",
                "actual": actual,
                "expected": expected,
                "note": note,
            }
        )

    reviewable = [row for row in reconciliation_rows if is_reviewable_row(row)]
    review_ids = {review_identity(row) for row in review_rows if review_identity(row)}
    high_value_ids = {
        review_identity(row)
        for row in sorted(
            reviewable,
            key=lambda item: (-review_amount_abs(item), review_identity(item)),
        )[:high_value_count]
    }
    mandatory_ids = {
        review_identity(row)
        for row in reviewable
        if is_mandatory_evidence_review_row(row)
    }
    challenged_ids = {
        review_identity(row)
        for row in reviewable
        if row_matches_challenge(row, challenged_rows or [])
    }
    risk_ids = {review_identity(row) for row in reviewable if codex_review_flags(row)}
    random_rows = [
        row for row in review_rows if "stable_random" in review_reason_tokens(row)
    ]
    expected_random = min(
        random_count,
        max(
            0,
            len(reviewable)
            - len(high_value_ids | mandatory_ids | challenged_ids | risk_ids),
        ),
    )
    valid_statuses = {"PENDING", "PASS", "FAIL", "UNRESOLVED"}
    statuses = [clean_text(row.get("review_status")).upper() for row in review_rows]
    invalid_statuses = sorted(
        {status for status in statuses if status and status not in valid_statuses}
    )
    failed_rows = [
        review_identity(row)
        for row in review_rows
        if clean_text(row.get("review_status")).upper() == "FAIL"
    ]
    incomplete_rows = [
        review_identity(row)
        for row in review_rows
        if clean_text(row.get("review_status")).upper() in {"", "PENDING"}
    ]

    add(
        "codex_review_packet_present",
        bool(review_rows) or not reviewable,
        len(review_rows),
        ">0 when population is reviewable",
    )
    add(
        "codex_review_high_value_coverage",
        high_value_ids.issubset(review_ids),
        len(high_value_ids & review_ids),
        len(high_value_ids),
        "; ".join(sorted(high_value_ids - review_ids)[:10]),
    )
    add(
        "codex_review_mandatory_closure_coverage",
        mandatory_ids.issubset(review_ids),
        len(mandatory_ids & review_ids),
        len(mandatory_ids),
        "; ".join(sorted(mandatory_ids - review_ids)[:10]),
    )
    add(
        "codex_review_challenged_row_coverage",
        challenged_ids.issubset(review_ids),
        len(challenged_ids & review_ids),
        len(challenged_ids),
        "; ".join(sorted(challenged_ids - review_ids)[:10]),
    )
    add(
        "codex_review_stable_random_minimum",
        len(random_rows) >= expected_random,
        len(random_rows),
        expected_random,
    )
    add(
        "codex_review_statuses_valid",
        not invalid_statuses,
        "; ".join(invalid_statuses),
        "PENDING/PASS/FAIL/UNRESOLVED",
    )
    add(
        "codex_review_no_failed_rows",
        not failed_rows,
        len(failed_rows),
        0,
        "; ".join(failed_rows[:10]),
    )
    if require_completed_review:
        add(
            "codex_review_completed",
            not incomplete_rows,
            len(incomplete_rows),
            0,
            "; ".join(incomplete_rows[:10]),
        )
    return checks


def money_label(value: object, currency: str = "EUR", decimals: bool = False) -> str:
    parsed = parse_decimal(value) or Decimal("0.00")
    quant = Decimal("0.01") if decimals else Decimal("1")
    number = parsed.quantize(quant, rounding=ROUND_HALF_UP)
    sign = "-" if number < 0 else ""
    whole, _, cents = f"{abs(number):f}".partition(".")
    parts: list[str] = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    rendered = f"{sign}{','.join(reversed(parts))}"
    if decimals:
        rendered = f"{rendered}.{(cents + '00')[:2]}"
    return f"{currency} {rendered}".strip()


def codex_review_flags(
    row: dict[str, Any], high_value_threshold: object = "100000"
) -> list[str]:
    """Return advisory flags for rows that deserve Codex/human review.

    These flags are not classification evidence. They are quality-control prompts
    for reviewing the deterministic result.
    """
    evidence_text = " ".join(
        clean_text(row.get(field)).lower()
        for field in (
            "rule_applied",
            "matched_evidence_type",
            "matched_evidence_amounts",
            "matched_evidence_id",
            "matched_evidence_reference",
            "evidence_level",
            "description",
            "source_file",
            "source_role",
            "evidence_type",
        )
    )
    flags: list[str] = []
    amount_values = [
        parse_decimal(row.get(field))
        for field in (
            "amount",
            "all_a_balance",
            "balance",
            "matched_amount",
            "bank_amount",
        )
    ]
    max_amount = max(
        (abs(value) for value in amount_values if value is not None),
        default=Decimal("0.00"),
    )
    threshold = parse_decimal(high_value_threshold) or Decimal("100000.00")
    if max_amount >= threshold:
        flags.append("high_value")
    if any_keyword_in(
        evidence_text, ("group", "bulk", "blocco", "payment_order") + BATCH_KEYWORDS
    ):
        flags.append("grouped_or_batch_payment")
    if any_keyword_in(evidence_text, COMPENSATION_KEYWORDS):
        flags.append("compensation_or_netting")
    if has_factor_reference(evidence_text):
        flags.append("factoring_or_advance")
    if any(
        token in evidence_text
        for token in ("near match", "approx", "similar", "fuzzy", "probable")
    ):
        flags.append("non_exact_match_language")
    if any_keyword_in(
        evidence_text,
        (
            "without bank",
            "no bank",
            "senza estratto",
            "senza banca",
            "sans banque",
            "sin banco",
        ),
    ):
        flags.append("internal_without_external_evidence")
    if not clean_text(row.get("document_no")) and not clean_text(
        row.get("document_key")
    ):
        flags.append("missing_document_key")
    return flags


def stable_review_sample(
    rows: list[dict[str, Any]],
    sample_size: int = 25,
    seed: str = "audit-reconciliation",
    id_fields: tuple[str, ...] = (
        "record_id",
        "id",
        "document_key",
        "document_no",
        "source_file",
        "source_row",
    ),
    amount_fields: tuple[str, ...] = (
        "amount",
        "all_a_balance",
        "balance",
        "matched_amount",
    ),
    include_top_amount: int = 5,
) -> list[dict[str, Any]]:
    """Select a reproducible spot-check sample.

    The sample includes the largest rows first, then a stable hash sample. Record
    the seed, population size, and returned row ids in the workpaper.
    """
    if sample_size <= 0 or not rows:
        return []

    def amount_abs(row: dict[str, Any]) -> Decimal:
        values = [parse_decimal(row.get(field)) for field in amount_fields]
        return max(
            (abs(value) for value in values if value is not None),
            default=Decimal("0.00"),
        )

    def identity(row: dict[str, Any]) -> str:
        parts = [
            clean_text(row.get(field))
            for field in id_fields
            if clean_text(row.get(field))
        ]
        if not parts:
            parts = [clean_text(value) for value in row.values()]
        return "|".join(parts)

    def hash_key(row: dict[str, Any]) -> str:
        return hashlib.sha256(f"{seed}|{identity(row)}".encode("utf-8")).hexdigest()

    ranked = sorted(enumerate(rows), key=lambda item: (-amount_abs(item[1]), item[0]))
    selected_indexes: set[int] = set(
        index for index, _ in ranked[: max(0, min(include_top_amount, sample_size))]
    )
    remaining_slots = sample_size - len(selected_indexes)
    if remaining_slots > 0:
        remaining = [
            (index, row)
            for index, row in enumerate(rows)
            if index not in selected_indexes
        ]
        for index, _ in sorted(remaining, key=lambda item: hash_key(item[1]))[
            :remaining_slots
        ]:
            selected_indexes.add(index)
    return [row for index, row in enumerate(rows) if index in selected_indexes]

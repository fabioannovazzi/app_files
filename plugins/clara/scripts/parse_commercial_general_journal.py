#!/usr/bin/env python3
"""Parse one explicitly reviewed paginated commercial general journal.

This parser is deterministic because byte binding, OpenXML extraction, fixed
layout matching, exact arithmetic, line-ID uniqueness, date ordering, and
control-total reconciliation are mechanically verifiable. It does not decide
that a workbook is a general journal, choose an entity, currency, unit, account
mapping, sign convention, or accounting interpretation. The caller must review
and supply those decisions outside this parser.

The parser writes nothing. Raw descriptions and entity labels are deliberately
excluded from the returned in-memory model.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import (
    Decimal,
    DecimalException,
    Inexact,
    InvalidOperation,
    Rounded,
    localcontext,
)
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn, Pattern

# Every XML payload is bounded and screened by _safe_xml_member_bytes first.
from xml.etree import ElementTree  # nosec B405

__all__ = [
    "DatePattern",
    "GeneralJournalLayoutContract",
    "GeneralJournalParseError",
    "JournalMovement",
    "LogicalMovementPattern",
    "PageLayout",
    "ParsedGeneralJournal",
    "PhysicalEmbeddedAmountPattern",
    "ReviewedAmountLocator",
    "ReviewedAmountlessExclusion",
    "ReviewedAmountPair",
    "ReviewedAmountPairMember",
    "canonical_general_journal_row_sha256",
    "general_journal_layout_contract_from_mapping",
    "load_general_journal_layout_contract",
    "parse_commercial_general_journal",
]

CONTRACT_VERSION = "clara.commercial_general_journal_layout.v5"
REVIEW_STATUS = "reviewed"
REVIEWED_ROW_SHA256_DOMAIN = "clara.general_journal_reviewed_row.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ACCOUNTING_AMOUNT_FORMATS = frozenset(
    {
        "canonical_dot",
        "italian_grouped_2",
    }
)
AMOUNT_SIGN_POLICIES = frozenset({"nonnegative", "signed"})
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_CONTRACT_BYTES = 1024 * 1024
MAX_PATTERN_LENGTH = 2_048
MAX_CELL_TEXT_LENGTH = 1_000_000
MAX_XLSX_MEMBERS = 2_048
MAX_XLSX_MEMBER_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 200
MAX_WORKSHEET_ROWS = 1_000_000
MAX_WORKSHEET_CELLS = 10_000_000
MAX_ROW_CELLS = 20_000
MAX_SHARED_STRINGS = 2_000_000
MAX_SHARED_STRING_CHARACTERS = 128 * 1024 * 1024
MAX_XLSX_COLUMN = 16_384

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_RELATIONSHIP_ID = f"{{{_DOCUMENT_REL_NS}}}id"
_CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_CANONICAL_DOT_DECIMAL = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_ITALIAN_GROUPED_2_DECIMAL = re.compile(
    r"^[+-]?(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3})*),[0-9]{2}$"
)
_XML_DECLARATION = re.compile(
    rb"\A(?:\xef\xbb\xbf)?[ \t\r\n]*<\?xml\b.*?\?>",
    re.IGNORECASE | re.DOTALL,
)
_XML_ENCODING = re.compile(
    rb"\bencoding\s*=\s*(['\"])(?P<encoding>[A-Za-z0-9._-]+)\1",
    re.IGNORECASE,
)
_SUPPORTED_XML_ENCODINGS = frozenset({"ascii", "us-ascii", "utf-8"})
_CONTRACT_FIELDS = frozenset(
    {
        "contract_version",
        "review_status",
        "sheet_name",
        "date_header_label",
        "line_header_label",
        "account_header_label",
        "debit_header_label",
        "credit_header_label",
        "page_layouts",
        "date_patterns",
        "account_code_pattern",
        "logical_candidate_pattern",
        "logical_movement_patterns",
        "physical_embedded_amount_patterns",
        "reviewed_amount_pairs",
        "reviewed_amountless_exclusions",
        "physical_amount_format",
        "amount_sign_policy",
        "control_pattern",
        "control_amount_format",
        "reviewed_final_debit_total",
        "reviewed_final_credit_total",
    }
)
_PAGE_LAYOUT_FIELDS = frozenset(
    {
        "layout_id",
        "date_header_column",
        "line_header_column",
        "account_header_column",
        "debit_header_column",
        "credit_header_column",
        "date_columns",
        "line_id_columns",
        "account_columns",
        "debit_amount_columns",
        "credit_amount_columns",
        "physical_first_line_columns",
    }
)
_DATE_PATTERN_FIELDS = frozenset({"pattern", "strptime_format"})
_LOGICAL_PATTERN_FIELDS = frozenset({"layout_ids", "pattern", "amount_format"})
_PHYSICAL_EMBEDDED_AMOUNT_PATTERN_FIELDS = frozenset(
    {"layout_ids", "column", "pattern", "amount_format"}
)
_REVIEWED_AMOUNT_LOCATOR_FIELDS = frozenset(
    {
        "layout_id",
        "row_number",
        "column",
        "line_index",
        "pattern",
        "amount_format",
    }
)
_REVIEWED_AMOUNT_PAIR_MEMBER_FIELDS = frozenset(
    {
        "movement_layout_id",
        "movement_row_number",
        "movement_line_id",
        "amount_locator",
    }
)
_REVIEWED_AMOUNT_PAIR_FIELDS = frozenset({"debit", "credit"})
_REVIEWED_AMOUNTLESS_EXCLUSION_FIELDS = frozenset(
    {
        "layout_id",
        "row_number",
        "line_id",
        "nonempty_columns",
        "residual_columns",
        "canonical_row_sha256",
    }
)


class GeneralJournalParseError(ValueError):
    """Raised when an exact parser or reviewed-contract invariant fails."""


@dataclass(frozen=True)
class DatePattern:
    """One caller-reviewed registration-date syntax."""

    pattern: str
    strptime_format: str


@dataclass(frozen=True)
class LogicalMovementPattern:
    """One caller-reviewed fixed-width logical movement-line syntax."""

    layout_ids: tuple[str, ...]
    pattern: str
    amount_format: str


@dataclass(frozen=True)
class PhysicalEmbeddedAmountPattern:
    """One reviewed amount embedded in a physical text cell."""

    layout_ids: tuple[str, ...]
    column: int
    pattern: str
    amount_format: str


@dataclass(frozen=True)
class ReviewedAmountLocator:
    """One exact source line containing a reviewer-owned pair amount."""

    layout_id: str
    row_number: int
    column: int
    line_index: int
    pattern: str
    amount_format: str


@dataclass(frozen=True)
class ReviewedAmountPairMember:
    """One exact movement row bound to one exact amount locator."""

    movement_layout_id: str
    movement_row_number: int
    movement_line_id: int
    amount_locator: ReviewedAmountLocator


@dataclass(frozen=True)
class ReviewedAmountPair:
    """One reviewer-owned equal debit/credit pair."""

    debit: ReviewedAmountPairMember
    credit: ReviewedAmountPairMember


@dataclass(frozen=True)
class ReviewedAmountlessExclusion:
    """One exact row with no reviewed physical amount signal."""

    layout_id: str
    row_number: int
    line_id: int
    nonempty_columns: tuple[int, ...]
    residual_columns: tuple[int, ...]
    canonical_row_sha256: str


@dataclass(frozen=True)
class PageLayout:
    """One exact page-header signature and its physical extraction columns."""

    layout_id: str
    date_header_column: int
    line_header_column: int
    account_header_column: int
    debit_header_column: int
    credit_header_column: int
    date_columns: tuple[int, ...]
    line_id_columns: tuple[int, ...]
    account_columns: tuple[int, ...]
    debit_amount_columns: tuple[int, ...]
    credit_amount_columns: tuple[int, ...]
    physical_first_line_columns: tuple[int, ...]


@dataclass(frozen=True)
class GeneralJournalLayoutContract:
    """Caller-reviewed mechanics; no semantic source decisions are inferred."""

    contract_version: str
    review_status: str
    sheet_name: str
    date_header_label: str
    line_header_label: str
    account_header_label: str
    debit_header_label: str
    credit_header_label: str
    page_layouts: tuple[PageLayout, ...]
    date_patterns: tuple[DatePattern, ...]
    account_code_pattern: str
    logical_candidate_pattern: str
    logical_movement_patterns: tuple[LogicalMovementPattern, ...]
    physical_embedded_amount_patterns: tuple[
        PhysicalEmbeddedAmountPattern,
        ...,
    ]
    reviewed_amount_pairs: tuple[ReviewedAmountPair, ...]
    reviewed_amountless_exclusions: tuple[
        ReviewedAmountlessExclusion,
        ...,
    ]
    physical_amount_format: str
    amount_sign_policy: str
    control_pattern: str
    control_amount_format: str
    reviewed_final_debit_total: str
    reviewed_final_credit_total: str


@dataclass(frozen=True)
class JournalMovement:
    """One mechanically parsed movement without descriptions or entity data."""

    line_id: int
    posting_date: date
    account_code: str
    debit: Decimal
    credit: Decimal
    source_form: str


@dataclass(frozen=True)
class ParsedGeneralJournal:
    """Deterministic numeric model; row-level completeness is not established."""

    source_sha256: str
    movements: tuple[JournalMovement, ...]
    debit_total: Decimal
    credit_total: Decimal
    source_control_debit_total: Decimal
    source_control_credit_total: Decimal
    first_posting_date: date
    last_posting_date: date
    page_header_count: int
    physical_movement_count: int
    logical_movement_count: int
    excluded_amountless_count: int
    line_id_gap_count: int
    layout_page_counts: Mapping[str, int]

    def sanitized_counts(self) -> dict[str, int | str]:
        """Return aggregate mechanics only; no row-level or identifying values."""

        return {
            "movement_count": len(self.movements),
            "physical_movement_count": self.physical_movement_count,
            "logical_movement_count": self.logical_movement_count,
            "excluded_amountless_count": self.excluded_amountless_count,
            "page_header_count": self.page_header_count,
            "line_id_gap_count": self.line_id_gap_count,
            "layout_variant_count": len(self.layout_page_counts),
            "first_posting_date": self.first_posting_date.isoformat(),
            "last_posting_date": self.last_posting_date.isoformat(),
        }


@dataclass(frozen=True)
class _SheetRow:
    row_number: int
    cells: Mapping[int, str]


@dataclass(frozen=True)
class _CompiledDatePattern:
    pattern: Pattern[str]
    strptime_format: str


@dataclass(frozen=True)
class _CompiledLogicalMovementPattern:
    layout_ids: frozenset[str]
    pattern: Pattern[str]
    amount_format: str


@dataclass(frozen=True)
class _CompiledPhysicalEmbeddedAmountPattern:
    layout_ids: frozenset[str]
    column: int
    pattern: Pattern[str]
    amount_format: str


@dataclass(frozen=True)
class _CompiledReviewedAmountLocator:
    value: ReviewedAmountLocator
    pattern: Pattern[str]


@dataclass(frozen=True)
class _CompiledReviewedAmountPairMember:
    value: ReviewedAmountPairMember
    role: str
    amount_locator: _CompiledReviewedAmountLocator


@dataclass(frozen=True)
class _CompiledReviewedAmountPair:
    debit: _CompiledReviewedAmountPairMember
    credit: _CompiledReviewedAmountPairMember


@dataclass(frozen=True)
class _CompiledContract:
    value: GeneralJournalLayoutContract
    account_code_pattern: Pattern[str]
    logical_candidate_pattern: Pattern[str]
    logical_movement_patterns: tuple[_CompiledLogicalMovementPattern, ...]
    physical_embedded_amount_patterns: tuple[
        _CompiledPhysicalEmbeddedAmountPattern,
        ...,
    ]
    reviewed_amount_pairs: tuple[_CompiledReviewedAmountPair, ...]
    reviewed_amountless_exclusions: tuple[
        ReviewedAmountlessExclusion,
        ...,
    ]
    date_patterns: tuple[_CompiledDatePattern, ...]
    control_pattern: Pattern[str]
    reviewed_debit_total: Decimal
    reviewed_credit_total: Decimal


@dataclass(frozen=True)
class _LogicalLine:
    row_number: int
    column: int
    line_index: int
    text: str


@dataclass(frozen=True)
class _ResolvedReviewedAmountPairMember:
    value: ReviewedAmountPairMember
    role: str
    amount: Decimal


@dataclass(frozen=True)
class _ResolvedReviewedAmountPairs:
    members_by_row: Mapping[int, _ResolvedReviewedAmountPairMember]
    movement_rows_by_line_id: Mapping[int, int]
    locator_keys: frozenset[tuple[int, int, int]]


@dataclass(frozen=True)
class _ResolvedReviewedAmountlessExclusions:
    by_row: Mapping[int, ReviewedAmountlessExclusion]
    rows_by_line_id: Mapping[int, int]


def _fail(message: str) -> NoReturn:
    raise GeneralJournalParseError(message)


def canonical_general_journal_row_sha256(cells: Mapping[int, str]) -> str:
    """Hash one exact row with a domain-separated canonical payload."""

    if not isinstance(cells, Mapping) or not cells:
        _fail("canonical reviewed row cells must be a non-empty mapping")
    if any(
        type(column) is not int or column <= 0 or column > MAX_XLSX_COLUMN
        for column in cells
    ):
        _fail("canonical reviewed row columns must be positive XLSX integers")
    ordered_cells: list[list[int | str]] = []
    for column in sorted(cells):
        text = cells[column]
        if not isinstance(text, str) or not text:
            _fail("canonical reviewed row cell text must be exact non-empty text")
        ordered_cells.append([column, text])
    payload = json.dumps(
        [REVIEWED_ROW_SHA256_DOMAIN, ordered_cells],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{label} must be canonical non-empty text")
    return value


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        _fail(f"{label} keys must be strings")
    return value


def _exact_fields(
    value: Mapping[str, object],
    *,
    expected: frozenset[str],
    label: str,
) -> None:
    fields = set(value)
    missing = sorted(expected - fields)
    unexpected = sorted(fields - expected)
    if missing:
        _fail(f"{label} is missing fields: {missing}")
    if unexpected:
        _fail(f"{label} contains unexpected fields: {unexpected}")


def _json_list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        _fail(f"{label} must be a JSON array")
    return value


def _json_integer(value: object, *, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    return value


def _json_integer_tuple(value: object, *, label: str) -> tuple[int, ...]:
    items = _json_list(value, label=label)
    return tuple(
        _json_integer(item, label=f"{label}[{index}]")
        for index, item in enumerate(items)
    )


def _json_text_tuple(value: object, *, label: str) -> tuple[str, ...]:
    items = _json_list(value, label=label)
    return tuple(
        _canonical_text(item, label=f"{label}[{index}]")
        for index, item in enumerate(items)
    )


def _normalized_label(value: str) -> str:
    return " ".join(value.casefold().split())


def _positive_columns(values: tuple[int, ...], *, label: str) -> tuple[int, ...]:
    if (
        not values
        or any(type(value) is not int or value <= 0 for value in values)
        or tuple(sorted(set(values))) != values
    ):
        _fail(f"{label} must be sorted unique positive integer columns")
    return values


def _compile_pattern(value: str, *, label: str) -> Pattern[str]:
    text = _canonical_text(value, label=label)
    if len(text) > MAX_PATTERN_LENGTH:
        _fail(f"{label} is too long")
    try:
        return re.compile(text)
    except re.error as exc:
        raise GeneralJournalParseError(f"{label} must be a valid regex") from exc


def _decimal(
    text: str,
    *,
    decimal_format: str,
    sign_policy: str,
    label: str,
) -> Decimal:
    if decimal_format not in ACCOUNTING_AMOUNT_FORMATS:
        _fail(f"{label} uses an unsupported declared decimal format")
    if sign_policy not in AMOUNT_SIGN_POLICIES:
        _fail("amount_sign_policy is unsupported")
    raw = _canonical_text(text, label=label)
    if decimal_format == "canonical_dot":
        if _CANONICAL_DOT_DECIMAL.fullmatch(raw) is None:
            _fail(f"{label} is not an exact canonical-dot Decimal")
        normalized = raw
    else:
        if _ITALIAN_GROUPED_2_DECIMAL.fullmatch(raw) is None:
            _fail(f"{label} is not an exact Italian-grouped Decimal")
        normalized = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise GeneralJournalParseError(f"{label} is not a finite Decimal") from exc
    if not result.is_finite():
        _fail(f"{label} is not a finite Decimal")
    if sign_policy == "nonnegative" and result < 0:
        _fail(f"{label} violates the reviewed nonnegative amount policy")
    return result


def _decimal_pattern(decimal_format: str) -> Pattern[str]:
    if decimal_format == "canonical_dot":
        return _CANONICAL_DOT_DECIMAL
    if decimal_format == "italian_grouped_2":
        return _ITALIAN_GROUPED_2_DECIMAL
    _fail("declared decimal format is unsupported")


def _validate_registered_amount_cell_occupancy(
    row: _SheetRow,
    *,
    layout: PageLayout,
    contract: _CompiledContract,
) -> None:
    """Fail unless every occupied registered amount cell is contract-valid."""

    occupied = [
        ("debit", column, row.cells[column])
        for column in layout.debit_amount_columns
        if column in row.cells
    ] + [
        ("credit", column, row.cells[column])
        for column in layout.credit_amount_columns
        if column in row.cells
    ]
    if not occupied:
        return
    exact_control_columns = {
        column
        for column, text in row.cells.items()
        if contract.control_pattern.fullmatch(text) is not None
    }
    contains_control_line = any(
        contract.control_pattern.fullmatch(line) is not None
        for text in row.cells.values()
        for line in text.splitlines()
    )
    if contains_control_line:
        if any(column not in exact_control_columns for _, column, _ in occupied):
            _fail("physical control row also contains a movement signal")
        return
    # Exact source-format validation is mechanically verifiable and prevents
    # occupied amount cells from disappearing before movement extraction.
    for role, _, text in occupied:
        _decimal(
            text,
            decimal_format=contract.value.physical_amount_format,
            sign_policy=contract.value.amount_sign_policy,
            label=f"physical registered {role} amount at row {row.row_number}",
        )


def _line_has_registered_movement_signal(
    text: str,
    *,
    column: int,
    layout: PageLayout,
    contract: _CompiledContract,
) -> bool:
    """Return whether one exact cell line reaches a movement-candidate path."""

    if contract.logical_candidate_pattern.search(text) is not None:
        return True
    if (
        column in layout.line_id_columns
        and re.fullmatch(r"[1-9][0-9]*", text) is not None
    ):
        return True
    if (
        column in layout.account_columns
        and contract.account_code_pattern.search(text) is not None
    ):
        return True
    if column in (
        *layout.debit_amount_columns,
        *layout.credit_amount_columns,
    ):
        return True
    return any(
        item.pattern.fullmatch(text) is not None
        for item in contract.physical_embedded_amount_patterns
        if layout.layout_id in item.layout_ids and item.column == column
    )


def _exact_decimal_sum(
    values: tuple[Decimal, ...],
    *,
    label: str,
) -> Decimal:
    """Sum finite Decimals exactly, independent of ambient precision."""

    nonzero_values = tuple(value for value in values if not value.is_zero())
    if not nonzero_values:
        return Decimal(0)
    exponents: list[int] = []
    for value in nonzero_values:
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or not value.is_finite():
            _fail(f"{label} contains a non-finite Decimal")
        exponents.append(exponent)
    minimum_exponent = min(exponents)
    maximum_adjusted = max(value.adjusted() for value in nonzero_values)
    carry_digits = len(str(len(nonzero_values)))
    exact_precision = max(
        1,
        maximum_adjusted - minimum_exponent + 1 + carry_digits,
    )
    try:
        with localcontext() as context:
            context.prec = exact_precision
            context.Emax = max(
                context.Emax,
                maximum_adjusted + carry_digits,
            )
            context.Emin = min(
                context.Emin,
                minimum_exponent - carry_digits,
            )
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            return sum(nonzero_values, Decimal(0))
    except DecimalException as exc:
        raise GeneralJournalParseError(
            f"{label} could not be accumulated exactly"
        ) from exc


def _validate_layout(layout: PageLayout) -> None:
    _canonical_text(layout.layout_id, label="page layout ID")
    header_columns = (
        layout.date_header_column,
        layout.line_header_column,
        layout.account_header_column,
        layout.debit_header_column,
        layout.credit_header_column,
    )
    if any(type(column) is not int or column <= 0 for column in header_columns):
        _fail("page layout header columns must be positive integers")
    if not (
        layout.date_header_column < layout.account_header_column
        and layout.line_header_column < layout.account_header_column
        and layout.account_header_column < layout.debit_header_column
        and layout.debit_header_column < layout.credit_header_column
    ):
        _fail("page layout header columns are not ordered")
    date_columns = _positive_columns(
        layout.date_columns,
        label=f"{layout.layout_id} date_columns",
    )
    line_columns = _positive_columns(
        layout.line_id_columns,
        label=f"{layout.layout_id} line_id_columns",
    )
    account_columns = _positive_columns(
        layout.account_columns,
        label=f"{layout.layout_id} account_columns",
    )
    debit_columns = _positive_columns(
        layout.debit_amount_columns,
        label=f"{layout.layout_id} debit_amount_columns",
    )
    credit_columns = _positive_columns(
        layout.credit_amount_columns,
        label=f"{layout.layout_id} credit_amount_columns",
    )
    physical_first_line_columns = (
        _positive_columns(
            layout.physical_first_line_columns,
            label=f"{layout.layout_id} physical_first_line_columns",
        )
        if layout.physical_first_line_columns
        else ()
    )
    if any(column >= layout.account_header_column for column in date_columns):
        _fail("date extraction columns must precede the account header")
    if any(column >= layout.account_header_column for column in line_columns):
        _fail("line-ID extraction columns must precede the account header")
    if layout.account_header_column not in account_columns:
        _fail("account extraction columns must include the account header column")
    if set(debit_columns) & set(credit_columns):
        _fail("debit and credit extraction columns must be disjoint")
    if any(column <= layout.account_header_column for column in debit_columns):
        _fail("debit extraction columns must follow the account header")
    if any(column <= layout.account_header_column for column in credit_columns):
        _fail("credit extraction columns must follow the account header")
    extraction_columns = (
        set(date_columns)
        | set(line_columns)
        | set(account_columns)
        | set(debit_columns)
        | set(credit_columns)
    )
    if not set(physical_first_line_columns).issubset(extraction_columns):
        _fail("physical-first-line columns must be reviewed extraction columns")


def _reviewed_amount_locator_key(
    locator: ReviewedAmountLocator,
) -> tuple[int, int, int]:
    return (locator.row_number, locator.column, locator.line_index)


def _reviewed_amount_pair_order_key(
    pair: ReviewedAmountPair,
) -> tuple[int, int, int, int]:
    return (
        min(
            pair.debit.movement_row_number,
            pair.credit.movement_row_number,
        ),
        pair.debit.movement_row_number,
        pair.credit.movement_row_number,
        pair.debit.movement_line_id,
    )


def _reviewed_amountless_exclusion_order_key(
    exclusion: ReviewedAmountlessExclusion,
) -> tuple[int, int, str, tuple[int, ...], tuple[int, ...], str]:
    return (
        exclusion.row_number,
        exclusion.line_id,
        exclusion.layout_id,
        exclusion.nonempty_columns,
        exclusion.residual_columns,
        exclusion.canonical_row_sha256,
    )


def _compile_contract(
    contract: GeneralJournalLayoutContract,
) -> _CompiledContract:
    if not isinstance(contract, GeneralJournalLayoutContract):
        _fail("layout_contract must be a GeneralJournalLayoutContract")
    if contract.contract_version != CONTRACT_VERSION:
        _fail("layout contract version is not supported")
    if contract.review_status != REVIEW_STATUS:
        _fail("layout contract must be explicitly reviewed")
    _canonical_text(contract.sheet_name, label="sheet_name")
    for label, value in (
        ("date_header_label", contract.date_header_label),
        ("line_header_label", contract.line_header_label),
        ("account_header_label", contract.account_header_label),
        ("debit_header_label", contract.debit_header_label),
        ("credit_header_label", contract.credit_header_label),
    ):
        _canonical_text(value, label=label)
    if not contract.page_layouts:
        _fail("layout contract must declare page layouts")
    for layout in contract.page_layouts:
        _validate_layout(layout)
    layout_ids = [layout.layout_id for layout in contract.page_layouts]
    if len(layout_ids) != len(set(layout_ids)):
        _fail("page layout IDs must be unique")
    layout_id_set = frozenset(layout_ids)
    header_signatures = [
        (
            layout.date_header_column,
            layout.line_header_column,
            layout.account_header_column,
            layout.debit_header_column,
            layout.credit_header_column,
        )
        for layout in contract.page_layouts
    ]
    if len(header_signatures) != len(set(header_signatures)):
        _fail("page layout header signatures must be unique")

    date_patterns: list[_CompiledDatePattern] = []
    if not contract.date_patterns:
        _fail("layout contract must declare date patterns")
    for index, item in enumerate(contract.date_patterns):
        compiled = _compile_pattern(
            item.pattern,
            label=f"date_patterns[{index}].pattern",
        )
        if "date" not in compiled.groupindex:
            _fail("each date pattern must provide a named date group")
        if item.strptime_format not in {"%Y-%m-%d", "%d/%m/%Y"}:
            _fail("date pattern uses an unsupported reviewed date format")
        date_patterns.append(
            _CompiledDatePattern(
                pattern=compiled,
                strptime_format=item.strptime_format,
            )
        )

    account_code_pattern = _compile_pattern(
        contract.account_code_pattern,
        label="account_code_pattern",
    )
    logical_candidate_pattern = _compile_pattern(
        contract.logical_candidate_pattern,
        label="logical_candidate_pattern",
    )
    if not contract.logical_movement_patterns:
        _fail("layout contract must declare logical movement patterns")
    logical_patterns: list[_CompiledLogicalMovementPattern] = []
    for index, item in enumerate(contract.logical_movement_patterns):
        if (
            not item.layout_ids
            or tuple(sorted(set(item.layout_ids))) != item.layout_ids
            or any(
                not isinstance(layout_id, str)
                or not layout_id
                or layout_id != layout_id.strip()
                for layout_id in item.layout_ids
            )
        ):
            _fail(
                "logical movement pattern layout IDs must be sorted unique "
                "canonical text"
            )
        if not set(item.layout_ids).issubset(layout_id_set):
            _fail("logical movement pattern references an unknown layout ID")
        compiled = _compile_pattern(
            item.pattern,
            label=f"logical_movement_patterns[{index}].pattern",
        )
        if not {"line_id", "account", "debit", "credit"}.issubset(compiled.groupindex):
            _fail(
                "each logical movement pattern must provide named line_id, "
                "account, debit, and credit groups"
            )
        if item.amount_format not in ACCOUNTING_AMOUNT_FORMATS:
            _fail("logical movement pattern has an unsupported amount format")
        logical_patterns.append(
            _CompiledLogicalMovementPattern(
                layout_ids=frozenset(item.layout_ids),
                pattern=compiled,
                amount_format=item.amount_format,
            )
        )
    physical_embedded_patterns: list[_CompiledPhysicalEmbeddedAmountPattern] = []
    for index, item in enumerate(contract.physical_embedded_amount_patterns):
        if (
            not item.layout_ids
            or tuple(sorted(set(item.layout_ids))) != item.layout_ids
            or any(
                not isinstance(layout_id, str)
                or not layout_id
                or layout_id != layout_id.strip()
                for layout_id in item.layout_ids
            )
        ):
            _fail(
                "physical embedded amount pattern layout IDs must be "
                "sorted unique canonical text"
            )
        if not set(item.layout_ids).issubset(layout_id_set):
            _fail("physical embedded amount pattern references an unknown " "layout ID")
        if type(item.column) is not int or item.column <= 0:
            _fail("physical embedded amount pattern column must be positive")
        compiled = _compile_pattern(
            item.pattern,
            label=f"physical_embedded_amount_patterns[{index}].pattern",
        )
        if not {"debit", "credit"}.issubset(compiled.groupindex):
            _fail(
                "each physical embedded amount pattern must provide named "
                "debit and credit groups"
            )
        if item.amount_format not in ACCOUNTING_AMOUNT_FORMATS:
            _fail(
                "physical embedded amount pattern has an unsupported " "amount format"
            )
        physical_embedded_patterns.append(
            _CompiledPhysicalEmbeddedAmountPattern(
                layout_ids=frozenset(item.layout_ids),
                column=item.column,
                pattern=compiled,
                amount_format=item.amount_format,
            )
        )
    if not isinstance(contract.reviewed_amount_pairs, tuple):
        _fail("reviewed_amount_pairs must be a tuple")
    if any(
        not isinstance(pair, ReviewedAmountPair)
        for pair in contract.reviewed_amount_pairs
    ):
        _fail("reviewed amount pair must use the reviewed pair type")
    if (
        tuple(
            sorted(
                contract.reviewed_amount_pairs,
                key=_reviewed_amount_pair_order_key,
            )
        )
        != contract.reviewed_amount_pairs
    ):
        _fail("reviewed amount pairs must be in canonical movement-row order")
    reviewed_amount_pairs: list[_CompiledReviewedAmountPair] = []
    reviewed_movement_rows: set[int] = set()
    reviewed_movement_line_ids: set[int] = set()
    reviewed_locator_keys: set[tuple[int, int, int]] = set()
    reviewed_locator_rows: set[int] = set()
    for pair_index, pair in enumerate(contract.reviewed_amount_pairs):
        if (
            pair.debit.movement_row_number == pair.credit.movement_row_number
            or pair.debit.movement_line_id == pair.credit.movement_line_id
        ):
            _fail("reviewed amount pair members must be distinct")
        compiled_members: list[_CompiledReviewedAmountPairMember] = []
        for role, member in (("debit", pair.debit), ("credit", pair.credit)):
            if not isinstance(member, ReviewedAmountPairMember):
                _fail("reviewed amount pair member has an invalid type")
            if member.movement_layout_id not in layout_id_set:
                _fail(
                    "reviewed amount pair member references an unknown "
                    "movement layout"
                )
            if (
                type(member.movement_row_number) is not int
                or member.movement_row_number <= 0
                or type(member.movement_line_id) is not int
                or member.movement_line_id <= 0
            ):
                _fail(
                    "reviewed amount pair movement row and line ID must be "
                    "positive integers"
                )
            if member.movement_row_number in reviewed_movement_rows:
                _fail("reviewed amount pair movement rows must be unique")
            if member.movement_line_id in reviewed_movement_line_ids:
                _fail("reviewed amount pair movement line IDs must be unique")
            reviewed_movement_rows.add(member.movement_row_number)
            reviewed_movement_line_ids.add(member.movement_line_id)
            locator = member.amount_locator
            if not isinstance(locator, ReviewedAmountLocator):
                _fail("reviewed amount locator has an invalid type")
            if locator.layout_id not in layout_id_set:
                _fail("reviewed amount locator references an unknown layout ID")
            if (
                type(locator.row_number) is not int
                or locator.row_number <= 0
                or type(locator.column) is not int
                or locator.column <= 0
                or type(locator.line_index) is not int
                or locator.line_index < 0
            ):
                _fail(
                    "reviewed amount locator coordinates must be positive "
                    "rows/columns and a nonnegative line index"
                )
            locator_key = _reviewed_amount_locator_key(locator)
            if locator_key in reviewed_locator_keys:
                _fail("reviewed amount locators must be globally unique")
            reviewed_locator_keys.add(locator_key)
            reviewed_locator_rows.add(locator.row_number)
            compiled_pattern = _compile_pattern(
                locator.pattern,
                label=(
                    f"reviewed_amount_pairs[{pair_index}].{role}."
                    "amount_locator.pattern"
                ),
            )
            if "amount" not in compiled_pattern.groupindex:
                _fail(
                    "reviewed amount locator pattern must provide a named "
                    "amount group"
                )
            if locator.amount_format not in ACCOUNTING_AMOUNT_FORMATS:
                _fail("reviewed amount locator has an unsupported amount format")
            compiled_members.append(
                _CompiledReviewedAmountPairMember(
                    value=member,
                    role=role,
                    amount_locator=_CompiledReviewedAmountLocator(
                        value=locator,
                        pattern=compiled_pattern,
                    ),
                )
            )
        reviewed_amount_pairs.append(
            _CompiledReviewedAmountPair(
                debit=compiled_members[0],
                credit=compiled_members[1],
            )
        )
    if not isinstance(contract.reviewed_amountless_exclusions, tuple):
        _fail("reviewed_amountless_exclusions must be a tuple")
    if any(
        not isinstance(exclusion, ReviewedAmountlessExclusion)
        for exclusion in contract.reviewed_amountless_exclusions
    ):
        _fail("reviewed amountless exclusion must use the reviewed exclusion type")
    if (
        tuple(
            sorted(
                contract.reviewed_amountless_exclusions,
                key=_reviewed_amountless_exclusion_order_key,
            )
        )
        != contract.reviewed_amountless_exclusions
    ):
        _fail("reviewed amountless exclusions must be in canonical row order")
    reviewed_exclusion_rows: set[int] = set()
    reviewed_exclusion_line_ids: set[int] = set()
    for exclusion in contract.reviewed_amountless_exclusions:
        _canonical_text(
            exclusion.layout_id,
            label="reviewed amountless exclusion layout ID",
        )
        if exclusion.layout_id not in layout_id_set:
            _fail("reviewed amountless exclusion references an unknown layout")
        if (
            type(exclusion.row_number) is not int
            or exclusion.row_number <= 0
            or type(exclusion.line_id) is not int
            or exclusion.line_id <= 0
        ):
            _fail(
                "reviewed amountless exclusion row and line ID must be "
                "positive integers"
            )
        if exclusion.row_number in reviewed_exclusion_rows:
            _fail("reviewed amountless exclusion rows must be unique")
        if exclusion.line_id in reviewed_exclusion_line_ids:
            _fail("reviewed amountless exclusion line IDs must be unique")
        if exclusion.row_number in reviewed_movement_rows:
            _fail(
                "reviewed amountless exclusion rows must not overlap "
                "reviewed amount pair rows"
            )
        if exclusion.row_number in reviewed_locator_rows:
            _fail(
                "reviewed amountless exclusion rows must not overlap "
                "reviewed amount locator rows"
            )
        if exclusion.line_id in reviewed_movement_line_ids:
            _fail(
                "reviewed amountless exclusion line IDs must not overlap "
                "reviewed amount pair line IDs"
            )
        if not isinstance(exclusion.nonempty_columns, tuple):
            _fail("reviewed amountless exclusion nonempty columns must be a tuple")
        _positive_columns(
            exclusion.nonempty_columns,
            label="reviewed amountless exclusion nonempty columns",
        )
        if any(column > MAX_XLSX_COLUMN for column in exclusion.nonempty_columns):
            _fail(
                "reviewed amountless exclusion nonempty columns exceed XLSX " "limits"
            )
        if not isinstance(exclusion.residual_columns, tuple):
            _fail("reviewed amountless exclusion residual columns must be a tuple")
        if (
            any(
                type(column) is not int or column <= 0 or column > MAX_XLSX_COLUMN
                for column in exclusion.residual_columns
            )
            or tuple(sorted(set(exclusion.residual_columns)))
            != exclusion.residual_columns
        ):
            _fail(
                "reviewed amountless exclusion residual columns must be "
                "sorted unique positive XLSX columns"
            )
        if not set(exclusion.residual_columns).issubset(exclusion.nonempty_columns):
            _fail(
                "reviewed amountless exclusion residual columns must be a "
                "subset of nonempty columns"
            )
        if len(set(exclusion.nonempty_columns) - set(exclusion.residual_columns)) != 2:
            _fail(
                "reviewed amountless exclusion must reserve exactly two "
                "line/account signal columns"
            )
        if (
            not isinstance(exclusion.canonical_row_sha256, str)
            or SHA256_PATTERN.fullmatch(exclusion.canonical_row_sha256) is None
        ):
            _fail(
                "reviewed amountless exclusion canonical row SHA-256 must be "
                "lowercase hexadecimal"
            )
        reviewed_exclusion_rows.add(exclusion.row_number)
        reviewed_exclusion_line_ids.add(exclusion.line_id)
    if contract.physical_amount_format not in ACCOUNTING_AMOUNT_FORMATS:
        _fail("physical_amount_format is unsupported")
    if contract.control_amount_format not in ACCOUNTING_AMOUNT_FORMATS:
        _fail("control_amount_format is unsupported")
    if contract.amount_sign_policy not in AMOUNT_SIGN_POLICIES:
        _fail("amount_sign_policy is unsupported")

    control_pattern = _compile_pattern(
        contract.control_pattern,
        label="control_pattern",
    )
    if not {"debit", "credit"}.issubset(control_pattern.groupindex):
        _fail("control_pattern must provide named debit and credit groups")
    reviewed_debit = _decimal(
        contract.reviewed_final_debit_total,
        decimal_format="canonical_dot",
        sign_policy=contract.amount_sign_policy,
        label="reviewed_final_debit_total",
    )
    reviewed_credit = _decimal(
        contract.reviewed_final_credit_total,
        decimal_format="canonical_dot",
        sign_policy=contract.amount_sign_policy,
        label="reviewed_final_credit_total",
    )
    return _CompiledContract(
        value=contract,
        account_code_pattern=account_code_pattern,
        logical_candidate_pattern=logical_candidate_pattern,
        logical_movement_patterns=tuple(logical_patterns),
        physical_embedded_amount_patterns=tuple(physical_embedded_patterns),
        reviewed_amount_pairs=tuple(reviewed_amount_pairs),
        reviewed_amountless_exclusions=(contract.reviewed_amountless_exclusions),
        date_patterns=tuple(date_patterns),
        control_pattern=control_pattern,
        reviewed_debit_total=reviewed_debit,
        reviewed_credit_total=reviewed_credit,
    )


def general_journal_layout_contract_from_mapping(
    value: Mapping[str, object],
) -> GeneralJournalLayoutContract:
    """Build and validate a contract from an exact JSON-compatible object."""

    source = _mapping(value, label="layout contract")
    _exact_fields(source, expected=_CONTRACT_FIELDS, label="layout contract")

    layouts: list[PageLayout] = []
    for index, raw_layout in enumerate(
        _json_list(source["page_layouts"], label="page_layouts")
    ):
        layout = _mapping(raw_layout, label=f"page_layouts[{index}]")
        _exact_fields(
            layout,
            expected=_PAGE_LAYOUT_FIELDS,
            label=f"page_layouts[{index}]",
        )
        layouts.append(
            PageLayout(
                layout_id=_canonical_text(
                    layout["layout_id"],
                    label=f"page_layouts[{index}].layout_id",
                ),
                date_header_column=_json_integer(
                    layout["date_header_column"],
                    label=f"page_layouts[{index}].date_header_column",
                ),
                line_header_column=_json_integer(
                    layout["line_header_column"],
                    label=f"page_layouts[{index}].line_header_column",
                ),
                account_header_column=_json_integer(
                    layout["account_header_column"],
                    label=f"page_layouts[{index}].account_header_column",
                ),
                debit_header_column=_json_integer(
                    layout["debit_header_column"],
                    label=f"page_layouts[{index}].debit_header_column",
                ),
                credit_header_column=_json_integer(
                    layout["credit_header_column"],
                    label=f"page_layouts[{index}].credit_header_column",
                ),
                date_columns=_json_integer_tuple(
                    layout["date_columns"],
                    label=f"page_layouts[{index}].date_columns",
                ),
                line_id_columns=_json_integer_tuple(
                    layout["line_id_columns"],
                    label=f"page_layouts[{index}].line_id_columns",
                ),
                account_columns=_json_integer_tuple(
                    layout["account_columns"],
                    label=f"page_layouts[{index}].account_columns",
                ),
                debit_amount_columns=_json_integer_tuple(
                    layout["debit_amount_columns"],
                    label=f"page_layouts[{index}].debit_amount_columns",
                ),
                credit_amount_columns=_json_integer_tuple(
                    layout["credit_amount_columns"],
                    label=f"page_layouts[{index}].credit_amount_columns",
                ),
                physical_first_line_columns=_json_integer_tuple(
                    layout["physical_first_line_columns"],
                    label=(f"page_layouts[{index}].physical_first_line_columns"),
                ),
            )
        )

    dates: list[DatePattern] = []
    for index, raw_date in enumerate(
        _json_list(source["date_patterns"], label="date_patterns")
    ):
        item = _mapping(raw_date, label=f"date_patterns[{index}]")
        _exact_fields(
            item,
            expected=_DATE_PATTERN_FIELDS,
            label=f"date_patterns[{index}]",
        )
        dates.append(
            DatePattern(
                pattern=_canonical_text(
                    item["pattern"],
                    label=f"date_patterns[{index}].pattern",
                ),
                strptime_format=_canonical_text(
                    item["strptime_format"],
                    label=f"date_patterns[{index}].strptime_format",
                ),
            )
        )

    logical_patterns: list[LogicalMovementPattern] = []
    for index, raw_pattern in enumerate(
        _json_list(
            source["logical_movement_patterns"],
            label="logical_movement_patterns",
        )
    ):
        item = _mapping(
            raw_pattern,
            label=f"logical_movement_patterns[{index}]",
        )
        _exact_fields(
            item,
            expected=_LOGICAL_PATTERN_FIELDS,
            label=f"logical_movement_patterns[{index}]",
        )
        logical_patterns.append(
            LogicalMovementPattern(
                layout_ids=_json_text_tuple(
                    item["layout_ids"],
                    label=f"logical_movement_patterns[{index}].layout_ids",
                ),
                pattern=_canonical_text(
                    item["pattern"],
                    label=f"logical_movement_patterns[{index}].pattern",
                ),
                amount_format=_canonical_text(
                    item["amount_format"],
                    label=f"logical_movement_patterns[{index}].amount_format",
                ),
            )
        )

    physical_embedded_patterns: list[PhysicalEmbeddedAmountPattern] = []
    for index, raw_pattern in enumerate(
        _json_list(
            source["physical_embedded_amount_patterns"],
            label="physical_embedded_amount_patterns",
        )
    ):
        item = _mapping(
            raw_pattern,
            label=f"physical_embedded_amount_patterns[{index}]",
        )
        _exact_fields(
            item,
            expected=_PHYSICAL_EMBEDDED_AMOUNT_PATTERN_FIELDS,
            label=f"physical_embedded_amount_patterns[{index}]",
        )
        physical_embedded_patterns.append(
            PhysicalEmbeddedAmountPattern(
                layout_ids=_json_text_tuple(
                    item["layout_ids"],
                    label=(f"physical_embedded_amount_patterns[{index}]" ".layout_ids"),
                ),
                column=_json_integer(
                    item["column"],
                    label=(f"physical_embedded_amount_patterns[{index}].column"),
                ),
                pattern=_canonical_text(
                    item["pattern"],
                    label=(f"physical_embedded_amount_patterns[{index}].pattern"),
                ),
                amount_format=_canonical_text(
                    item["amount_format"],
                    label=(
                        f"physical_embedded_amount_patterns[{index}]" ".amount_format"
                    ),
                ),
            )
        )

    reviewed_amount_pairs: list[ReviewedAmountPair] = []
    for pair_index, raw_pair in enumerate(
        _json_list(
            source["reviewed_amount_pairs"],
            label="reviewed_amount_pairs",
        )
    ):
        pair = _mapping(
            raw_pair,
            label=f"reviewed_amount_pairs[{pair_index}]",
        )
        _exact_fields(
            pair,
            expected=_REVIEWED_AMOUNT_PAIR_FIELDS,
            label=f"reviewed_amount_pairs[{pair_index}]",
        )
        members: dict[str, ReviewedAmountPairMember] = {}
        for role in ("debit", "credit"):
            member_label = f"reviewed_amount_pairs[{pair_index}].{role}"
            member = _mapping(pair[role], label=member_label)
            _exact_fields(
                member,
                expected=_REVIEWED_AMOUNT_PAIR_MEMBER_FIELDS,
                label=member_label,
            )
            locator_label = f"{member_label}.amount_locator"
            locator = _mapping(
                member["amount_locator"],
                label=locator_label,
            )
            _exact_fields(
                locator,
                expected=_REVIEWED_AMOUNT_LOCATOR_FIELDS,
                label=locator_label,
            )
            members[role] = ReviewedAmountPairMember(
                movement_layout_id=_canonical_text(
                    member["movement_layout_id"],
                    label=f"{member_label}.movement_layout_id",
                ),
                movement_row_number=_json_integer(
                    member["movement_row_number"],
                    label=f"{member_label}.movement_row_number",
                ),
                movement_line_id=_json_integer(
                    member["movement_line_id"],
                    label=f"{member_label}.movement_line_id",
                ),
                amount_locator=ReviewedAmountLocator(
                    layout_id=_canonical_text(
                        locator["layout_id"],
                        label=f"{locator_label}.layout_id",
                    ),
                    row_number=_json_integer(
                        locator["row_number"],
                        label=f"{locator_label}.row_number",
                    ),
                    column=_json_integer(
                        locator["column"],
                        label=f"{locator_label}.column",
                    ),
                    line_index=_json_integer(
                        locator["line_index"],
                        label=f"{locator_label}.line_index",
                    ),
                    pattern=_canonical_text(
                        locator["pattern"],
                        label=f"{locator_label}.pattern",
                    ),
                    amount_format=_canonical_text(
                        locator["amount_format"],
                        label=f"{locator_label}.amount_format",
                    ),
                ),
            )
        reviewed_amount_pairs.append(
            ReviewedAmountPair(
                debit=members["debit"],
                credit=members["credit"],
            )
        )

    reviewed_amountless_exclusions: list[ReviewedAmountlessExclusion] = []
    for exclusion_index, raw_exclusion in enumerate(
        _json_list(
            source["reviewed_amountless_exclusions"],
            label="reviewed_amountless_exclusions",
        )
    ):
        exclusion_label = f"reviewed_amountless_exclusions[{exclusion_index}]"
        exclusion = _mapping(raw_exclusion, label=exclusion_label)
        _exact_fields(
            exclusion,
            expected=_REVIEWED_AMOUNTLESS_EXCLUSION_FIELDS,
            label=exclusion_label,
        )
        reviewed_amountless_exclusions.append(
            ReviewedAmountlessExclusion(
                layout_id=_canonical_text(
                    exclusion["layout_id"],
                    label=f"{exclusion_label}.layout_id",
                ),
                row_number=_json_integer(
                    exclusion["row_number"],
                    label=f"{exclusion_label}.row_number",
                ),
                line_id=_json_integer(
                    exclusion["line_id"],
                    label=f"{exclusion_label}.line_id",
                ),
                nonempty_columns=_json_integer_tuple(
                    exclusion["nonempty_columns"],
                    label=f"{exclusion_label}.nonempty_columns",
                ),
                residual_columns=_json_integer_tuple(
                    exclusion["residual_columns"],
                    label=f"{exclusion_label}.residual_columns",
                ),
                canonical_row_sha256=_canonical_text(
                    exclusion["canonical_row_sha256"],
                    label=f"{exclusion_label}.canonical_row_sha256",
                ),
            )
        )

    contract = GeneralJournalLayoutContract(
        contract_version=_canonical_text(
            source["contract_version"],
            label="contract_version",
        ),
        review_status=_canonical_text(
            source["review_status"],
            label="review_status",
        ),
        sheet_name=_canonical_text(source["sheet_name"], label="sheet_name"),
        date_header_label=_canonical_text(
            source["date_header_label"],
            label="date_header_label",
        ),
        line_header_label=_canonical_text(
            source["line_header_label"],
            label="line_header_label",
        ),
        account_header_label=_canonical_text(
            source["account_header_label"],
            label="account_header_label",
        ),
        debit_header_label=_canonical_text(
            source["debit_header_label"],
            label="debit_header_label",
        ),
        credit_header_label=_canonical_text(
            source["credit_header_label"],
            label="credit_header_label",
        ),
        page_layouts=tuple(layouts),
        date_patterns=tuple(dates),
        account_code_pattern=_canonical_text(
            source["account_code_pattern"],
            label="account_code_pattern",
        ),
        logical_candidate_pattern=_canonical_text(
            source["logical_candidate_pattern"],
            label="logical_candidate_pattern",
        ),
        logical_movement_patterns=tuple(logical_patterns),
        physical_embedded_amount_patterns=tuple(physical_embedded_patterns),
        reviewed_amount_pairs=tuple(reviewed_amount_pairs),
        reviewed_amountless_exclusions=tuple(reviewed_amountless_exclusions),
        physical_amount_format=_canonical_text(
            source["physical_amount_format"],
            label="physical_amount_format",
        ),
        amount_sign_policy=_canonical_text(
            source["amount_sign_policy"],
            label="amount_sign_policy",
        ),
        control_pattern=_canonical_text(
            source["control_pattern"],
            label="control_pattern",
        ),
        control_amount_format=_canonical_text(
            source["control_amount_format"],
            label="control_amount_format",
        ),
        reviewed_final_debit_total=_canonical_text(
            source["reviewed_final_debit_total"],
            label="reviewed_final_debit_total",
        ),
        reviewed_final_credit_total=_canonical_text(
            source["reviewed_final_credit_total"],
            label="reviewed_final_credit_total",
        ),
    )
    _compile_contract(contract)
    return contract


def _strict_object_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            _fail(f"layout contract JSON contains duplicate field: {key}")
        result[key] = item
    return result


def _reject_json_constant(value: str) -> None:
    _fail(f"layout contract JSON contains unsupported constant: {value}")


def load_general_journal_layout_contract(
    path: Path,
    *,
    expected_contract_sha256: str,
) -> GeneralJournalLayoutContract:
    """Load one exact, duplicate-key-safe, digest-bound private contract."""

    payload = _stable_file_bytes(
        Path(path),
        expected_sha256=expected_contract_sha256,
        max_bytes=MAX_CONTRACT_BYTES,
        label="layout contract",
    )
    if payload.startswith(b"\xef\xbb\xbf"):
        _fail("layout contract JSON must not contain a UTF-8 BOM")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GeneralJournalParseError("layout contract JSON must be UTF-8") from exc
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise GeneralJournalParseError("layout contract JSON is invalid") from exc
    return general_journal_layout_contract_from_mapping(
        _mapping(raw, label="layout contract")
    )


def _stable_file_bytes(
    path: Path,
    *,
    expected_sha256: str,
    max_bytes: int,
    label: str,
) -> bytes:
    if SHA256_PATTERN.fullmatch(expected_sha256) is None:
        _fail(f"expected {label} SHA-256 must be a lowercase digest")
    file_path = Path(path)
    try:
        lexical_status = file_path.lstat()
        if stat.S_ISLNK(lexical_status.st_mode):
            _fail(f"{label} path must not be a symlink")
        if not stat.S_ISREG(lexical_status.st_mode):
            _fail(f"{label} path must identify one regular file")
        if lexical_status.st_nlink != 1:
            _fail(f"{label} file must not be hard linked")
        with file_path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                _fail(f"{label} path must identify one regular file")
            if before.st_nlink != 1:
                _fail(f"{label} file must not be hard linked")
            if before.st_size > max_bytes:
                _fail(f"{label} exceeds the parser byte limit")
            payload = handle.read()
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise GeneralJournalParseError(f"{label} could not be read") from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_lexical = (
        lexical_status.st_dev,
        lexical_status.st_ino,
        lexical_status.st_size,
        lexical_status.st_mtime_ns,
        lexical_status.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        identity_lexical != identity_before
        or identity_before != identity_after
        or len(payload) != after.st_size
    ):
        _fail(f"{label} changed while it was read")
    try:
        current = file_path.lstat()
    except OSError as exc:
        raise GeneralJournalParseError(
            f"{label} path changed while it was read"
        ) from exc
    if stat.S_ISLNK(current.st_mode):
        _fail(f"{label} path changed to a symlink while it was read")
    if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
        _fail(f"{label} path changed while it was read")
    identity_current = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
    )
    if identity_after != identity_current:
        _fail(f"{label} path changed while it was read")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        _fail(f"{label} does not match the exact reviewed digest")
    return payload


def _stable_source_bytes(path: Path, *, expected_sha256: str) -> bytes:
    return _stable_file_bytes(
        path,
        expected_sha256=expected_sha256,
        max_bytes=MAX_SOURCE_BYTES,
        label="source workbook",
    )


def _safe_zip_member(target: str, *, base: str) -> str:
    if (
        not target
        or "\\" in target
        or "\x00" in target
        or "?" in target
        or "#" in target
        or ":" in target
    ):
        _fail("workbook relationship target is unsafe")
    package_absolute = target.startswith("/")
    relative_target = target[1:] if package_absolute else target
    parts = relative_target.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _fail("workbook relationship target is unsafe")
    resolved = posixpath.normpath(
        relative_target if package_absolute else posixpath.join(base, target)
    )
    if (
        not resolved
        or resolved == ".."
        or resolved.startswith("../")
        or resolved.startswith("/")
    ):
        _fail("workbook relationship target escapes the package")
    return resolved


def _validate_archive_limits(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_XLSX_MEMBERS:
        _fail("XLSX package contains too many members")
    names: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        if (
            not name
            or "\\" in name
            or name.startswith("/")
            or posixpath.normpath(name) != name.rstrip("/")
            or name == ".."
            or name.startswith("../")
        ):
            _fail("XLSX package contains an unsafe member path")
        if name in names:
            _fail("XLSX package contains duplicate member names")
        names.add(name)
        if info.flag_bits & 0x1:
            _fail("XLSX package must not contain encrypted members")
        if info.file_size > MAX_XLSX_MEMBER_UNCOMPRESSED_BYTES:
            _fail("XLSX package member exceeds the decompressed byte limit")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES:
            _fail("XLSX package exceeds the total decompressed byte limit")
        if (
            info.file_size
            and info.file_size / max(info.compress_size, 1) > MAX_XLSX_COMPRESSION_RATIO
        ):
            _fail("XLSX package member exceeds the compression-ratio limit")


def _safe_xml_member_bytes(
    archive: zipfile.ZipFile,
    path: str,
    *,
    label: str,
) -> bytes:
    """Read bounded package XML after rejecting entity-capable syntax."""

    try:
        payload = archive.read(path)
    except (KeyError, OSError) as exc:
        raise GeneralJournalParseError(f"{label} is missing or unreadable") from exc
    if len(payload) > MAX_XLSX_MEMBER_UNCOMPRESSED_BYTES:
        _fail(f"{label} exceeds the decompressed byte limit")
    if b"\x00" in payload:
        _fail(f"{label} uses an unsupported XML encoding")
    declaration = _XML_DECLARATION.match(payload)
    if declaration is not None:
        encoding = _XML_ENCODING.search(declaration.group(0))
        if (
            encoding is not None
            and encoding.group("encoding").decode("ascii").casefold()
            not in _SUPPORTED_XML_ENCODINGS
        ):
            _fail(f"{label} uses an unsupported XML encoding")
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        _fail(f"{label} contains a forbidden DTD or entity declaration")
    return payload


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return ()
    payload = _safe_xml_member_bytes(
        archive,
        path,
        label="shared strings XML",
    )
    try:
        # DTDs and entity declarations were rejected above.
        root = ElementTree.fromstring(payload)  # nosec B314
    except ElementTree.ParseError as exc:
        raise GeneralJournalParseError("shared strings XML is invalid") from exc
    values: list[str] = []
    character_count = 0
    for item in root.findall(f"{{{_MAIN_NS}}}si"):
        if len(values) >= MAX_SHARED_STRINGS:
            _fail("shared-string table exceeds the item-count limit")
        value = "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
        character_count += len(value)
        if character_count > MAX_SHARED_STRING_CHARACTERS:
            _fail("shared-string table exceeds the character-count limit")
        values.append(value)
    return tuple(values)


def _worksheet_path(archive: zipfile.ZipFile, *, sheet_name: str) -> str:
    workbook_payload = _safe_xml_member_bytes(
        archive,
        "xl/workbook.xml",
        label="workbook XML",
    )
    relationships_payload = _safe_xml_member_bytes(
        archive,
        "xl/_rels/workbook.xml.rels",
        label="workbook relationships XML",
    )
    try:
        # DTDs and entity declarations were rejected above.
        workbook = ElementTree.fromstring(workbook_payload)  # nosec B314
        relationships = ElementTree.fromstring(relationships_payload)  # nosec B314
    except ElementTree.ParseError as exc:
        raise GeneralJournalParseError("workbook metadata XML is invalid") from exc
    relationship_targets: dict[str, str] = {}
    for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")
        if relationship.get("TargetMode") == "External":
            continue
        if relationship_id and target:
            relationship_targets[relationship_id] = target
    matches = []
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relationship_id = sheet.get(_RELATIONSHIP_ID)
            if not relationship_id or relationship_id not in relationship_targets:
                _fail("reviewed sheet has no internal worksheet relationship")
            matches.append(
                _safe_zip_member(
                    relationship_targets[relationship_id],
                    base="xl",
                )
            )
    if len(matches) != 1:
        _fail("reviewed sheet name must resolve to exactly one worksheet")
    if matches[0] not in archive.namelist():
        _fail("reviewed worksheet part is missing")
    return matches[0]


def _column_number(cell_reference: str, *, row_number: int) -> int:
    match = _CELL_REFERENCE.fullmatch(cell_reference)
    if match is None or int(match.group(2)) != row_number:
        _fail("worksheet contains an invalid cell reference")
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - ord("A") + 1
    if result > MAX_XLSX_COLUMN:
        _fail("worksheet cell exceeds the XLSX column limit")
    return result


def _cell_text(
    cell: ElementTree.Element,
    *,
    row_number: int,
    shared_strings: tuple[str, ...],
) -> tuple[int, str] | None:
    reference = cell.get("r")
    if reference is None:
        _fail("worksheet cell is missing its reference")
    column = _column_number(reference, row_number=row_number)
    if cell.find(f"{{{_MAIN_NS}}}f") is not None:
        _fail("reviewed worksheet must not contain formulas")
    cell_type = cell.get("t")
    if cell_type == "e":
        _fail("reviewed worksheet must not contain error cells")
    if cell_type == "inlineStr":
        value = "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
    else:
        value_node = cell.find(f"{{{_MAIN_NS}}}v")
        if value_node is None:
            return None
        raw = value_node.text or ""
        if cell_type == "s":
            try:
                index = int(raw)
                value = shared_strings[index]
            except (ValueError, IndexError) as exc:
                raise GeneralJournalParseError(
                    "worksheet shared-string reference is invalid"
                ) from exc
        else:
            value = raw
    if len(value) > MAX_CELL_TEXT_LENGTH:
        _fail("worksheet cell exceeds the parser text limit")
    if value == "":
        return None
    return column, value


def _worksheet_rows(
    archive: zipfile.ZipFile,
    *,
    worksheet_path: str,
    shared_strings: tuple[str, ...],
) -> tuple[_SheetRow, ...]:
    rows: list[_SheetRow] = []
    previous_row_number = 0
    parsed_row_count = 0
    parsed_cell_count = 0
    payload = _safe_xml_member_bytes(
        archive,
        worksheet_path,
        label="worksheet XML",
    )
    try:
        with io.BytesIO(payload) as handle:
            # DTDs and entity declarations were rejected above.
            for _, element in ElementTree.iterparse(  # nosec B314
                handle,
                events=("end",),
            ):
                if element.tag != f"{{{_MAIN_NS}}}row":
                    continue
                parsed_row_count += 1
                if parsed_row_count > MAX_WORKSHEET_ROWS:
                    _fail("worksheet exceeds the row-count limit")
                raw_row_number = element.get("r")
                try:
                    row_number = int(raw_row_number or "")
                except ValueError as exc:
                    raise GeneralJournalParseError(
                        "worksheet row number is invalid"
                    ) from exc
                if row_number <= previous_row_number:
                    _fail("worksheet row numbers must be strictly increasing")
                previous_row_number = row_number
                cells: dict[int, str] = {}
                cell_elements = element.findall(f"{{{_MAIN_NS}}}c")
                if len(cell_elements) > MAX_ROW_CELLS:
                    _fail("worksheet row exceeds the cell-count limit")
                parsed_cell_count += len(cell_elements)
                if parsed_cell_count > MAX_WORKSHEET_CELLS:
                    _fail("worksheet exceeds the total cell-count limit")
                for cell in cell_elements:
                    parsed = _cell_text(
                        cell,
                        row_number=row_number,
                        shared_strings=shared_strings,
                    )
                    if parsed is None:
                        continue
                    column, value = parsed
                    if column in cells:
                        _fail("worksheet row contains duplicate cell columns")
                    cells[column] = value
                if cells:
                    rows.append(
                        _SheetRow(
                            row_number=row_number,
                            cells=MappingProxyType(cells),
                        )
                    )
                element.clear()
    except (ElementTree.ParseError, KeyError, OSError) as exc:
        raise GeneralJournalParseError("worksheet XML is invalid") from exc
    return tuple(rows)


def _read_rows(payload: bytes, *, sheet_name: str) -> tuple[_SheetRow, ...]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            _validate_archive_limits(archive)
            worksheet_path = _worksheet_path(archive, sheet_name=sheet_name)
            strings = _shared_strings(archive)
            return _worksheet_rows(
                archive,
                worksheet_path=worksheet_path,
                shared_strings=strings,
            )
    except zipfile.BadZipFile as exc:
        raise GeneralJournalParseError(
            "source workbook is not a valid XLSX package"
        ) from exc


def _match_layout(
    row: _SheetRow,
    next_row: _SheetRow | None,
    *,
    contract: GeneralJournalLayoutContract,
) -> PageLayout | None:
    date_label = _normalized_label(contract.date_header_label)
    if not any(_normalized_label(value) == date_label for value in row.cells.values()):
        return None
    if next_row is None or next_row.row_number != row.row_number + 1:
        _fail("page header is missing its consecutive second header row")
    matches: list[PageLayout] = []
    labels = {
        "line": _normalized_label(contract.line_header_label),
        "account": _normalized_label(contract.account_header_label),
        "debit": _normalized_label(contract.debit_header_label),
        "credit": _normalized_label(contract.credit_header_label),
    }
    for layout in contract.page_layouts:
        if (
            _normalized_label(row.cells.get(layout.date_header_column, ""))
            == date_label
            and _normalized_label(next_row.cells.get(layout.line_header_column, ""))
            == labels["line"]
            and _normalized_label(next_row.cells.get(layout.account_header_column, ""))
            == labels["account"]
            and _normalized_label(next_row.cells.get(layout.debit_header_column, ""))
            == labels["debit"]
            and _normalized_label(next_row.cells.get(layout.credit_header_column, ""))
            == labels["credit"]
        ):
            matches.append(layout)
    if len(matches) != 1:
        _fail("page header does not match exactly one reviewed layout")
    return matches[0]


def _date_from_text(
    text: str,
    *,
    patterns: tuple[_CompiledDatePattern, ...],
    label: str,
) -> date | None:
    matches: list[date] = []
    for item in patterns:
        match = item.pattern.match(text)
        if match is None:
            continue
        try:
            parsed = datetime.strptime(
                match.group("date"),
                item.strptime_format,
            ).date()
        except (ValueError, IndexError) as exc:
            raise GeneralJournalParseError(f"{label} is invalid") from exc
        matches.append(parsed)
    if len(matches) > 1:
        _fail(f"{label} matches more than one reviewed date pattern")
    return matches[0] if matches else None


def _line_id(text: str, *, label: str) -> int:
    if re.fullmatch(r"[1-9][0-9]*", text) is None:
        _fail(f"{label} must be a positive base-10 integer")
    return int(text)


def _account_code(
    text: str,
    *,
    pattern: Pattern[str],
    label: str,
) -> str:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        _fail(f"{label} must contain exactly one reviewed account code")
    return re.sub(r"\s+", "", matches[0].group(0))


def _active_layout_ids_by_row(
    rows: tuple[_SheetRow, ...],
    *,
    contract: GeneralJournalLayoutContract,
) -> Mapping[int, str]:
    current_layout: PageLayout | None = None
    skip_row_number: int | None = None
    result: dict[int, str] = {}
    for index, row in enumerate(rows):
        if skip_row_number == row.row_number:
            skip_row_number = None
            continue
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        layout = _match_layout(row, next_row, contract=contract)
        if layout is not None:
            current_layout = layout
            if next_row is None:
                _fail("page header is missing its second header row")
            skip_row_number = next_row.row_number
            continue
        if current_layout is not None:
            result[row.row_number] = current_layout.layout_id
    return MappingProxyType(result)


def _resolve_reviewed_amount_pairs(
    rows: tuple[_SheetRow, ...],
    *,
    contract: _CompiledContract,
) -> _ResolvedReviewedAmountPairs:
    rows_by_number = {row.row_number: row for row in rows}
    active_layouts = _active_layout_ids_by_row(
        rows,
        contract=contract.value,
    )
    members_by_row: dict[int, _ResolvedReviewedAmountPairMember] = {}
    movement_rows_by_line_id: dict[int, int] = {}
    locator_keys: set[tuple[int, int, int]] = set()
    for pair in contract.reviewed_amount_pairs:
        resolved_members: list[_ResolvedReviewedAmountPairMember] = []
        for member in (pair.debit, pair.credit):
            value = member.value
            movement_layout = active_layouts.get(value.movement_row_number)
            if movement_layout is None:
                _fail("reviewed amount pair movement row is missing")
            if movement_layout != value.movement_layout_id:
                _fail("reviewed amount pair movement layout does not match")
            locator = member.amount_locator
            locator_value = locator.value
            locator_layout = active_layouts.get(locator_value.row_number)
            if locator_layout is None:
                _fail("reviewed amount locator row is missing")
            if locator_layout != locator_value.layout_id:
                _fail("reviewed amount locator layout does not match")
            locator_row = rows_by_number.get(locator_value.row_number)
            if locator_row is None:
                _fail("reviewed amount locator row is missing")
            cell = locator_row.cells.get(locator_value.column)
            if cell is None:
                _fail("reviewed amount locator column is missing")
            lines = cell.splitlines()
            if locator_value.line_index >= len(lines):
                _fail("reviewed amount locator line is missing")
            line = lines[locator_value.line_index]
            match = locator.pattern.fullmatch(line)
            if match is None:
                _fail("reviewed amount locator content changed")
            if (
                contract.logical_candidate_pattern.search(line) is not None
                or contract.control_pattern.fullmatch(line) is not None
            ):
                _fail("reviewed amount locator collides with ordinary extraction")
            amount = _decimal(
                match.group("amount"),
                decimal_format=locator_value.amount_format,
                sign_policy=contract.value.amount_sign_policy,
                label="reviewed amount locator",
            )
            resolved = _ResolvedReviewedAmountPairMember(
                value=value,
                role=member.role,
                amount=amount,
            )
            members_by_row[value.movement_row_number] = resolved
            movement_rows_by_line_id[value.movement_line_id] = value.movement_row_number
            locator_keys.add(_reviewed_amount_locator_key(locator_value))
            resolved_members.append(resolved)
        if resolved_members[0].amount != resolved_members[1].amount:
            _fail("reviewed amount pair values must be exactly equal")
    return _ResolvedReviewedAmountPairs(
        members_by_row=MappingProxyType(members_by_row),
        movement_rows_by_line_id=MappingProxyType(movement_rows_by_line_id),
        locator_keys=frozenset(locator_keys),
    )


def _resolve_reviewed_amountless_exclusions(
    rows: tuple[_SheetRow, ...],
    *,
    contract: _CompiledContract,
) -> _ResolvedReviewedAmountlessExclusions:
    rows_by_number = {row.row_number: row for row in rows}
    active_layouts = _active_layout_ids_by_row(
        rows,
        contract=contract.value,
    )
    by_row: dict[int, ReviewedAmountlessExclusion] = {}
    rows_by_line_id: dict[int, int] = {}
    for exclusion in contract.reviewed_amountless_exclusions:
        row = rows_by_number.get(exclusion.row_number)
        if row is None:
            _fail("reviewed amountless exclusion row is missing")
        layout_id = active_layouts.get(exclusion.row_number)
        if layout_id is None:
            _fail("reviewed amountless exclusion row has no active layout")
        if layout_id != exclusion.layout_id:
            _fail("reviewed amountless exclusion layout does not match")
        if tuple(sorted(row.cells)) != exclusion.nonempty_columns or any(
            not value.strip() for value in row.cells.values()
        ):
            _fail("reviewed amountless exclusion nonempty columns changed")
        if (
            canonical_general_journal_row_sha256(row.cells)
            != exclusion.canonical_row_sha256
        ):
            _fail("reviewed amountless exclusion canonical row fingerprint changed")
        if any("\n" in value or "\r" in value for value in row.cells.values()):
            _fail("reviewed amountless exclusion contains multiline text")
        by_row[exclusion.row_number] = exclusion
        rows_by_line_id[exclusion.line_id] = exclusion.row_number
    return _ResolvedReviewedAmountlessExclusions(
        by_row=MappingProxyType(by_row),
        rows_by_line_id=MappingProxyType(rows_by_line_id),
    )


class _ParserState:
    def __init__(
        self,
        contract: _CompiledContract,
        reviewed_amount_pairs: _ResolvedReviewedAmountPairs,
        reviewed_amountless_exclusions: _ResolvedReviewedAmountlessExclusions,
    ) -> None:
        self.contract = contract
        self.reviewed_amount_pairs = reviewed_amount_pairs
        self.reviewed_amountless_exclusions = reviewed_amountless_exclusions
        self.current_layout: PageLayout | None = None
        self.current_date: date | None = None
        self.movements: list[JournalMovement] = []
        self.line_ids: set[int] = set()
        self.last_line_id: int | None = None
        self.line_id_gap_count = 0
        self.page_header_count = 0
        self.physical_movement_count = 0
        self.logical_movement_count = 0
        self.reviewed_amountless_exclusion_rows_seen: set[int] = set()
        self.reviewed_amount_pair_rows_seen: set[int] = set()
        self.reviewed_amount_locator_keys_consumed: set[tuple[int, int, int]] = set()
        self.layout_page_counts: dict[str, int] = {}
        self.control_totals: tuple[Decimal, Decimal] | None = None
        self.control_seen = False

    def update_date(self, value: date) -> None:
        if self.current_date is not None and value < self.current_date:
            _fail("posting dates must be nondecreasing")
        self.current_date = value

    def add_movement(
        self,
        *,
        line_id: int,
        account_code: str,
        debit: Decimal,
        credit: Decimal,
        source_form: str,
    ) -> None:
        # A journal movement has mechanically verifiable one-sided provenance.
        if debit.is_zero() == credit.is_zero():
            _fail("movement must contain exactly one nonzero debit or credit amount")
        if self.current_date is None:
            _fail("movement appears before a parseable carried posting date")
        self.observe_line_id(line_id)
        self.movements.append(
            JournalMovement(
                line_id=line_id,
                posting_date=self.current_date,
                account_code=account_code,
                debit=debit,
                credit=credit,
                source_form=source_form,
            )
        )
        if source_form == "physical_row":
            self.physical_movement_count += 1
        else:
            self.logical_movement_count += 1

    def observe_line_id(self, line_id: int) -> None:
        if self.control_seen:
            _fail("movement appears after the reviewed final control line")
        if self.current_layout is None:
            _fail("movement appears before a reviewed page layout")
        if line_id in self.line_ids:
            _fail("duplicate global line ID")
        if self.last_line_id is not None:
            if line_id < self.last_line_id:
                _fail("global line IDs must be strictly increasing")
            self.line_id_gap_count += line_id - self.last_line_id - 1
        self.line_ids.add(line_id)
        self.last_line_id = line_id

    def exclude_reviewed_amountless_row(
        self,
        *,
        row_number: int,
        line_id: int,
    ) -> None:
        if row_number not in self.reviewed_amountless_exclusions.by_row:
            _fail("amountless exclusion is not explicitly reviewed")
        if row_number in self.reviewed_amountless_exclusion_rows_seen:
            _fail("reviewed amountless exclusion row was consumed twice")
        self.observe_line_id(line_id)
        self.reviewed_amountless_exclusion_rows_seen.add(row_number)

    def record_control(self, *, debit: Decimal, credit: Decimal) -> None:
        if self.control_totals is not None:
            _fail("reviewed final control line must occur exactly once")
        self.control_totals = (debit, credit)
        self.control_seen = True


def _record_control_line(
    line: str,
    *,
    state: _ParserState,
) -> bool:
    match = state.contract.control_pattern.fullmatch(line)
    if match is None:
        return False
    debit = _decimal(
        match.group("debit"),
        decimal_format=state.contract.value.control_amount_format,
        sign_policy=state.contract.value.amount_sign_policy,
        label="source final debit control",
    )
    credit = _decimal(
        match.group("credit"),
        decimal_format=state.contract.value.control_amount_format,
        sign_policy=state.contract.value.amount_sign_policy,
        label="source final credit control",
    )
    state.record_control(debit=debit, credit=credit)
    return True


def _parse_logical_line(line: _LogicalLine, *, state: _ParserState) -> None:
    locator_key = (line.row_number, line.column, line.line_index)
    if locator_key in state.reviewed_amount_pairs.locator_keys:
        return
    text = line.text
    if not text.strip():
        return
    if _record_control_line(text, state=state):
        return
    parsed_date = _date_from_text(
        text,
        patterns=state.contract.date_patterns,
        label="logical-line posting date",
    )
    if parsed_date is not None:
        state.update_date(parsed_date)
    if state.contract.logical_candidate_pattern.search(text) is None:
        return
    if state.current_layout is None:
        _fail("logical movement candidate appears before a reviewed page layout")
    matches = [
        (item, item.pattern.fullmatch(text))
        for item in state.contract.logical_movement_patterns
        if state.current_layout.layout_id in item.layout_ids
    ]
    matched = [(item, match) for item, match in matches if match is not None]
    if len(matched) != 1:
        _fail("logical movement candidate does not match exactly one reviewed pattern")
    item, match = matched[0]
    if match is None:
        _fail("logical movement pattern selection is internally inconsistent")
    line_id = _line_id(
        match.group("line_id"),
        label="logical movement line ID",
    )
    if line_id in state.reviewed_amount_pairs.movement_rows_by_line_id:
        _fail("reviewed amount pair line ID appeared in a logical line")
    if line_id in state.reviewed_amountless_exclusions.rows_by_line_id:
        _fail("reviewed amountless exclusion line ID appeared in a logical line")
    account = _account_code(
        match.group("account"),
        pattern=state.contract.account_code_pattern,
        label="logical movement account code",
    )
    debit_text = match.group("debit")
    credit_text = match.group("credit")
    if (debit_text is None) == (credit_text is None):
        _fail("logical movement must contain exactly one debit or credit amount")
    zero = Decimal(0)
    if debit_text is not None:
        debit = _decimal(
            debit_text,
            decimal_format=item.amount_format,
            sign_policy=state.contract.value.amount_sign_policy,
            label="logical movement debit",
        )
        credit = zero
    else:
        debit = zero
        credit = _decimal(
            credit_text,
            decimal_format=item.amount_format,
            sign_policy=state.contract.value.amount_sign_policy,
            label="logical movement credit",
        )
    state.add_movement(
        line_id=line_id,
        account_code=account,
        debit=debit,
        credit=credit,
        source_form="logical_line",
    )


def _partition_multiline_cells(
    row: _SheetRow,
    *,
    state: _ParserState,
) -> tuple[
    _SheetRow | None,
    tuple[_LogicalLine, ...],
    tuple[_LogicalLine, ...],
]:
    multiline_cells = [
        (column, value)
        for column, value in row.cells.items()
        if "\n" in value or "\r" in value
    ]
    if not multiline_cells:
        return row, (), ()
    candidate_cell_count = sum(
        any(
            state.contract.logical_candidate_pattern.search(line) is not None
            for line in value.splitlines()
        )
        for _, value in multiline_cells
    )
    if candidate_cell_count > 1:
        _fail("multiple multiline cells contain movement candidates in one row")
    physical_first_columns = (
        set(state.current_layout.physical_first_line_columns)
        if state.current_layout is not None
        else set()
    )
    remaining = {
        column: value
        for column, value in row.cells.items()
        if "\n" not in value and "\r" not in value
    }
    before_physical: list[_LogicalLine] = []
    after_physical: list[_LogicalLine] = []
    for column, value in sorted(multiline_cells):
        lines = value.splitlines()
        if column in physical_first_columns:
            if not lines or not lines[0].strip():
                _fail("reviewed physical-first multiline cell has no first line")
            remaining[column] = lines[0]
            after_physical.extend(
                _LogicalLine(
                    row_number=row.row_number,
                    column=column,
                    line_index=line_index,
                    text=line,
                )
                for line_index, line in enumerate(lines[1:], start=1)
            )
        else:
            before_physical.extend(
                _LogicalLine(
                    row_number=row.row_number,
                    column=column,
                    line_index=line_index,
                    text=line,
                )
                for line_index, line in enumerate(lines)
            )
    if not remaining:
        physical_row = None
    else:
        physical_row = _SheetRow(
            row_number=row.row_number,
            cells=MappingProxyType(remaining),
        )
    return physical_row, tuple(before_physical), tuple(after_physical)


def _physical_date(row: _SheetRow, *, state: _ParserState) -> date | None:
    layout = state.current_layout
    if layout is None:
        return None
    matches: list[date] = []
    for column in layout.date_columns:
        value = row.cells.get(column)
        if value is None:
            continue
        parsed = _date_from_text(
            value,
            patterns=state.contract.date_patterns,
            label=f"physical posting date at row {row.row_number}",
        )
        if parsed is not None:
            matches.append(parsed)
    if len(matches) > 1:
        _fail("physical row contains multiple parseable posting dates")
    return matches[0] if matches else None


def _physical_movement(row: _SheetRow, *, state: _ParserState) -> None:
    layout = state.current_layout
    if layout is None:
        return
    account_signals = [
        (column, row.cells[column])
        for column in layout.account_columns
        if column in row.cells
        and state.contract.account_code_pattern.search(row.cells[column]) is not None
    ]
    line_id_signals = [
        (column, row.cells[column])
        for column in layout.line_id_columns
        if column in row.cells
        and re.fullmatch(r"[1-9][0-9]*", row.cells[column]) is not None
    ]
    debit_signals = [
        (column, row.cells[column])
        for column in layout.debit_amount_columns
        if column in row.cells
    ]
    credit_signals = [
        (column, row.cells[column])
        for column in layout.credit_amount_columns
        if column in row.cells
    ]
    embedded_matches = []
    for item in state.contract.physical_embedded_amount_patterns:
        if layout.layout_id not in item.layout_ids or item.column not in row.cells:
            continue
        match = item.pattern.fullmatch(row.cells[item.column])
        if match is not None:
            embedded_matches.append((item, match))
    amount_signal_count = (
        len(debit_signals) + len(credit_signals) + len(embedded_matches)
    )
    ordinary_amount_locator_keys = [
        (row.row_number, column, 0) for column, _ in (*debit_signals, *credit_signals)
    ] + [(row.row_number, item.column, 0) for item, _ in embedded_matches]
    reviewed_member = state.reviewed_amount_pairs.members_by_row.get(row.row_number)
    reviewed_exclusion = state.reviewed_amountless_exclusions.by_row.get(row.row_number)
    for _, line_id_text in line_id_signals:
        signaled_line_id = int(line_id_text)
        expected_row = state.reviewed_amount_pairs.movement_rows_by_line_id.get(
            signaled_line_id
        )
        if expected_row is not None and expected_row != row.row_number:
            _fail("reviewed amount pair line ID appeared on the wrong row")
        expected_exclusion_row = (
            state.reviewed_amountless_exclusions.rows_by_line_id.get(signaled_line_id)
        )
        if (
            expected_exclusion_row is not None
            and expected_exclusion_row != row.row_number
        ):
            _fail("reviewed amountless exclusion line ID appeared on the " "wrong row")
    if reviewed_member is not None:
        if layout.layout_id != reviewed_member.value.movement_layout_id:
            _fail("reviewed amount pair movement layout does not match")
        if len(line_id_signals) != 1:
            _fail("reviewed amount pair movement line ID is missing")
        line_id = _line_id(
            line_id_signals[0][1],
            label="reviewed amount pair movement line ID",
        )
        if line_id != reviewed_member.value.movement_line_id:
            _fail("reviewed amount pair movement line ID changed")
        if len(account_signals) != 1:
            _fail("reviewed amount pair movement account is ambiguous or missing")
        if amount_signal_count > 1:
            _fail("reviewed amount pair movement has ordinary amount ambiguity")
        locator_key = _reviewed_amount_locator_key(reviewed_member.value.amount_locator)
        if ordinary_amount_locator_keys and ordinary_amount_locator_keys != [
            locator_key
        ]:
            _fail("reviewed amount pair movement has an undeclared ordinary " "amount")
        if row.row_number in state.reviewed_amount_pair_rows_seen:
            _fail("reviewed amount pair movement row was consumed twice")
        if locator_key in state.reviewed_amount_locator_keys_consumed:
            _fail("reviewed amount locator was consumed twice")
        account = _account_code(
            account_signals[0][1],
            pattern=state.contract.account_code_pattern,
            label="reviewed amount pair movement account code",
        )
        zero = Decimal(0)
        state.reviewed_amount_pair_rows_seen.add(row.row_number)
        state.reviewed_amount_locator_keys_consumed.add(locator_key)
        state.add_movement(
            line_id=line_id,
            account_code=account,
            debit=reviewed_member.amount if reviewed_member.role == "debit" else zero,
            credit=(
                reviewed_member.amount if reviewed_member.role == "credit" else zero
            ),
            source_form="physical_row",
        )
        return
    if reviewed_exclusion is not None:
        if layout.layout_id != reviewed_exclusion.layout_id:
            _fail("reviewed amountless exclusion layout does not match")
        if tuple(sorted(row.cells)) != reviewed_exclusion.nonempty_columns:
            _fail("reviewed amountless exclusion nonempty columns changed")
        if any("\n" in value or "\r" in value for value in row.cells.values()):
            _fail("reviewed amountless exclusion contains multiline text")
        if len(line_id_signals) != 1:
            _fail("reviewed amountless exclusion line ID is ambiguous or missing")
        line_id = _line_id(
            line_id_signals[0][1],
            label="reviewed amountless exclusion line ID",
        )
        if line_id != reviewed_exclusion.line_id:
            _fail("reviewed amountless exclusion line ID changed")
        if len(account_signals) != 1:
            _fail("reviewed amountless exclusion account is ambiguous or missing")
        if amount_signal_count != 0:
            _fail("reviewed amountless exclusion contains an amount")
        if any(
            state.contract.logical_candidate_pattern.search(value) is not None
            for value in row.cells.values()
        ):
            _fail("reviewed amountless exclusion contains a logical amount")
        signal_columns = {
            line_id_signals[0][0],
            account_signals[0][0],
        }
        expected_signal_columns = set(reviewed_exclusion.nonempty_columns) - set(
            reviewed_exclusion.residual_columns
        )
        if signal_columns != expected_signal_columns:
            _fail("reviewed amountless exclusion residual columns changed")
        _account_code(
            account_signals[0][1],
            pattern=state.contract.account_code_pattern,
            label="reviewed amountless exclusion account code",
        )
        state.exclude_reviewed_amountless_row(
            row_number=row.row_number,
            line_id=line_id,
        )
        return
    if any(
        key in state.reviewed_amount_pairs.locator_keys
        for key in ordinary_amount_locator_keys
    ):
        _fail("reviewed amount locator reached ordinary physical extraction")
    is_candidate = bool(
        line_id_signals
        or account_signals
        or debit_signals
        or credit_signals
        or embedded_matches
    )
    if not is_candidate:
        return
    if len(line_id_signals) != 1:
        _fail(
            "physical movement candidate has an ambiguous or missing line ID "
            f"at row {row.row_number}"
        )
    line_id = _line_id(
        line_id_signals[0][1],
        label=f"physical movement line ID at row {row.row_number}",
    )
    if len(account_signals) != 1:
        _fail(
            "physical movement candidate has an ambiguous or missing account "
            f"at row {row.row_number}"
        )
    account_column, account_text = account_signals[0]
    if account_column not in layout.account_columns:
        _fail("physical movement account lies outside the reviewed columns")
    account = _account_code(
        account_text,
        pattern=state.contract.account_code_pattern,
        label=f"physical movement account code at row {row.row_number}",
    )
    if amount_signal_count != 1:
        _fail(
            "physical movement candidate has an ambiguous or missing amount "
            f"at row {row.row_number}"
        )
    zero = Decimal(0)
    if embedded_matches:
        item, match = embedded_matches[0]
        debit_text = match.group("debit")
        credit_text = match.group("credit")
        if (debit_text is None) == (credit_text is None):
            _fail(
                "reviewed physical embedded amount must contain exactly one "
                "debit or credit amount"
            )
        if debit_text is not None:
            debit = _decimal(
                debit_text,
                decimal_format=item.amount_format,
                sign_policy=state.contract.value.amount_sign_policy,
                label=("physical embedded debit amount at row " f"{row.row_number}"),
            )
            credit = zero
        else:
            debit = zero
            credit = _decimal(
                credit_text,
                decimal_format=item.amount_format,
                sign_policy=state.contract.value.amount_sign_policy,
                label=("physical embedded credit amount at row " f"{row.row_number}"),
            )
    else:
        amount_text = debit_signals[0][1] if debit_signals else credit_signals[0][1]
        amount = _decimal(
            amount_text,
            decimal_format=state.contract.value.physical_amount_format,
            sign_policy=state.contract.value.amount_sign_policy,
            label=f"physical movement amount at row {row.row_number}",
        )
        if debit_signals:
            debit = amount
            credit = zero
        else:
            debit = zero
            credit = amount
    state.add_movement(
        line_id=line_id,
        account_code=account,
        debit=debit,
        credit=credit,
        source_form="physical_row",
    )


def _parse_rows(
    rows: tuple[_SheetRow, ...],
    *,
    contract: _CompiledContract,
) -> _ParserState:
    reviewed_amount_pairs = _resolve_reviewed_amount_pairs(
        rows,
        contract=contract,
    )
    reviewed_amountless_exclusions = _resolve_reviewed_amountless_exclusions(
        rows,
        contract=contract,
    )
    state = _ParserState(
        contract,
        reviewed_amount_pairs,
        reviewed_amountless_exclusions,
    )
    skip_row_number: int | None = None
    for index, row in enumerate(rows):
        if skip_row_number == row.row_number:
            skip_row_number = None
            continue
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        layout = _match_layout(
            row,
            next_row,
            contract=contract.value,
        )
        if layout is not None:
            state.current_layout = layout
            state.page_header_count += 1
            state.layout_page_counts[layout.layout_id] = (
                state.layout_page_counts.get(layout.layout_id, 0) + 1
            )
            if next_row is None:
                _fail("page header is missing its second header row")
            skip_row_number = next_row.row_number
            continue
        if state.current_layout is not None:
            _validate_registered_amount_cell_occupancy(
                row,
                layout=state.current_layout,
                contract=state.contract,
            )
        physical_row, before_physical, after_physical = _partition_multiline_cells(
            row, state=state
        )
        for line in before_physical:
            _parse_logical_line(line, state=state)
        if physical_row is not None:
            control_items = [
                (column, line)
                for column, line in physical_row.cells.items()
                if state.contract.control_pattern.fullmatch(line) is not None
            ]
            if len(control_items) > 1:
                _fail("physical row contains multiple reviewed control lines")
            if control_items:
                if state.current_layout is None:
                    _fail("reviewed control appears before a reviewed page layout")
                control_column, control_line = control_items[0]
                if any(
                    _line_has_registered_movement_signal(
                        line,
                        column=column,
                        layout=state.current_layout,
                        contract=state.contract,
                    )
                    for column, line in physical_row.cells.items()
                    if column != control_column
                ):
                    _fail("physical control row also contains a movement signal")
                if not _record_control_line(control_line, state=state):
                    _fail("reviewed control-line detection is inconsistent")
            else:
                parsed_date = _physical_date(physical_row, state=state)
                if parsed_date is not None:
                    state.update_date(parsed_date)
                _physical_movement(physical_row, state=state)
        for line in after_physical:
            _parse_logical_line(line, state=state)
    return state


def _finish(
    state: _ParserState,
    *,
    source_sha256: str,
) -> ParsedGeneralJournal:
    if state.page_header_count == 0:
        _fail("reviewed worksheet contains no recognized page headers")
    if not state.movements:
        _fail("reviewed worksheet contains no parsed movements")
    if state.current_date is None:
        _fail("reviewed worksheet contains no parsed posting date")
    if state.control_totals is None:
        _fail("reviewed final control line was not found")
    if (
        state.reviewed_amount_locator_keys_consumed
        != state.reviewed_amount_pairs.locator_keys
    ):
        _fail("reviewed amount locators were not consumed exactly once")
    if state.reviewed_amount_pair_rows_seen != set(
        state.reviewed_amount_pairs.members_by_row
    ):
        _fail("reviewed amount pair movement rows were not consumed exactly once")
    if state.reviewed_amountless_exclusion_rows_seen != set(
        state.reviewed_amountless_exclusions.by_row
    ):
        _fail("reviewed amountless exclusion rows were not consumed exactly once")
    source_debit, source_credit = state.control_totals
    if (
        source_debit != state.contract.reviewed_debit_total
        or source_credit != state.contract.reviewed_credit_total
    ):
        _fail("source final controls do not match the exact reviewed controls")
    debit_total = _exact_decimal_sum(
        tuple(movement.debit for movement in state.movements),
        label="parsed debit total",
    )
    credit_total = _exact_decimal_sum(
        tuple(movement.credit for movement in state.movements),
        label="parsed credit total",
    )
    if (
        debit_total != state.contract.reviewed_debit_total
        or credit_total != state.contract.reviewed_credit_total
    ):
        _fail("parsed movements do not reconcile to the exact reviewed controls")
    dates = [movement.posting_date for movement in state.movements]
    return ParsedGeneralJournal(
        source_sha256=source_sha256,
        movements=tuple(state.movements),
        debit_total=debit_total,
        credit_total=credit_total,
        source_control_debit_total=source_debit,
        source_control_credit_total=source_credit,
        first_posting_date=min(dates),
        last_posting_date=max(dates),
        page_header_count=state.page_header_count,
        physical_movement_count=state.physical_movement_count,
        logical_movement_count=state.logical_movement_count,
        excluded_amountless_count=len(state.reviewed_amountless_exclusion_rows_seen),
        line_id_gap_count=state.line_id_gap_count,
        layout_page_counts=MappingProxyType(dict(state.layout_page_counts)),
    )


def parse_commercial_general_journal(
    source_path: Path,
    *,
    expected_source_sha256: str,
    layout_contract: GeneralJournalLayoutContract,
) -> ParsedGeneralJournal:
    """Parse one digest-bound workbook under an explicit reviewed layout.

    No source kind, entity, currency, unit, sign convention, or account mapping
    is selected here. A successful result proves only the declared parser
    mechanics and exact control reconciliation.
    """

    compiled = _compile_contract(layout_contract)
    payload = _stable_source_bytes(
        Path(source_path),
        expected_sha256=expected_source_sha256,
    )
    rows = _read_rows(payload, sheet_name=compiled.value.sheet_name)
    state = _parse_rows(rows, contract=compiled)
    return _finish(state, source_sha256=expected_source_sha256)

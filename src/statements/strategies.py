"""Extraction strategies for bank statements."""

from __future__ import annotations

import logging
from typing import Iterable, List

from modules.utilities.utils import get_schema_and_column_names

from .header_map import map_headers
from .ingest import Document
from .locale_utils import parse_date, parse_number
from .page_classifier import AMOUNT_RE, DATE_RE
from .row_filters import filter_rows
from .schema import Transaction

logger = logging.getLogger(__name__)


def strategy_table_layout(document: Document, locale: str) -> List[Transaction]:
    """Parse transactions when tabular layout is available."""
    if not document.tables:
        return []
    df = document.tables[0]
    columns, _ = get_schema_and_column_names(df)
    columns = [str(c) for c in columns]
    mapping = map_headers(columns, locale)
    transactions: List[Transaction] = []
    for row in df.iter_rows(named=True):
        try:
            booking = parse_date(str(row[columns[mapping["booking_date"]]]), locale)
            amount = parse_number(str(row[columns[mapping["amount"]]]), locale)
        except (KeyError, ValueError):
            continue
        description = (
            str(row[columns[mapping["description"]]])
            if "description" in mapping
            else ""
        )
        currency = (
            str(row[columns[mapping["currency"]]]) if "currency" in mapping else ""
        )
        transactions.append(
            Transaction(
                booking_date=booking,
                value_date=None,
                description=description,
                amount=amount,
                currency=currency,
                raw_source=document.kind,
            )
        )
    return transactions


def strategy_line_heuristics(document: Document, locale: str) -> List[Transaction]:
    """Parse lines using date and amount heuristics with row filtering."""
    transactions: List[Transaction] = []
    for page_no, text in enumerate(document.pages, start=1):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        filtered = filter_rows(lines, lang_hint=locale)
        kept, dropped = len(filtered), len(lines) - len(filtered)
        diag = document.metadata.get("page_diagnostics")
        if isinstance(diag, list) and page_no - 1 < len(diag):
            diag[page_no - 1]["kept_rows"] = kept
            diag[page_no - 1]["dropped_rows"] = dropped
        logger.info("page %s heuristic kept %s dropped %s", page_no, kept, dropped)
        for line in filtered:
            date_match = DATE_RE.search(line)
            amount_match = None
            for m in AMOUNT_RE.finditer(line):
                amount_match = m
            if not date_match or not amount_match:
                continue
            date_str = date_match.group()
            amount_str = amount_match.group()
            desc = line[date_match.end() : amount_match.start()].strip()
            try:
                booking = parse_date(date_str, locale)
                amount = parse_number(amount_str, locale)
            except ValueError:
                continue
            transactions.append(
                Transaction(
                    booking_date=booking,
                    value_date=None,
                    description=desc,
                    amount=amount,
                    currency="",
                    raw_page=page_no,
                    raw_source=document.kind,
                    confidence=0.8,
                )
            )
    return transactions


def strategy_llm_blocks(document: Document, locale: str) -> List[Transaction]:
    """Fallback LLM extraction for difficult layouts."""
    try:
        from .llm import extract_transactions_llm
    except Exception as e:  # pragma: no cover - optional
        logging.exception(e)
        return []
    transactions: List[Transaction] = []
    for text in document.pages:
        transactions.extend(extract_transactions_llm(text, locale))
    return transactions

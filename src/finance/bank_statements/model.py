"""Data models used by the agentic bank statement parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class BankTransaction:
    """Normalised transaction record.

    Amounts are always signed: positive for credits, negative for debits.
    """

    posted_date: Optional[date]
    value_date: Optional[date]
    description: str
    amount: Decimal
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    raw: Dict[str, str] = field(default_factory=dict)
    source_page: int = 0
    line_no: Optional[int] = None
    confidence: float = 1.0


@dataclass
class PageDecision:
    """Decision taken for a single page."""

    page_number: int
    strategy: str
    transactions: List[BankTransaction] = field(default_factory=list)


@dataclass
class ParseReport:
    """Aggregate report returned by the parser."""

    pages_total: int = 0
    pages_parsed: int = 0
    transactions_extracted: int = 0
    by_strategy: Dict[str, int] = field(default_factory=dict)
    excluded_sections: int = 0
    decisions: List[PageDecision] = field(default_factory=list)

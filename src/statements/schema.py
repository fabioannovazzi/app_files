"""Canonical transaction schema used across statement extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass
class Transaction:
    """Represents a single bank transaction.

    ``counterparty`` and ``reference`` are deprecated; use ``beneficiary``
    and ``reference_ids`` instead.  Older fields are preserved for backward
    compatibility.
    """

    booking_date: date
    value_date: Optional[date]
    description: str
    amount: Decimal
    currency: str
    balance_after: Optional[Decimal] = None
    reference: Optional[str] = None
    counterparty: Optional[str] = None
    reference_ids: List[str] = field(default_factory=list)
    beneficiary: Optional[str] = None
    raw_page: int = 0
    raw_source: str = ""
    confidence: float = 1.0


def normalise_whitespace(value: str) -> str:
    """Collapse repeated whitespace and strip."""
    return " ".join(value.split())


def normalise_transaction(tx: Transaction) -> Transaction:
    """Return a copy with whitespace trimmed and signs normalised."""
    tx.description = normalise_whitespace(tx.description)
    if tx.reference:
        tx.reference = normalise_whitespace(tx.reference)
    if tx.reference_ids:
        tx.reference_ids = [normalise_whitespace(r) for r in tx.reference_ids]
    if tx.counterparty:
        tx.counterparty = normalise_whitespace(tx.counterparty)
    if tx.beneficiary:
        tx.beneficiary = normalise_whitespace(tx.beneficiary)
    return tx

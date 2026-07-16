"""Simple duplicate detection and reconciliation for transactions."""

from __future__ import annotations

import logging
from typing import Iterable, List

from .model import BankTransaction

try:  # optional dependency
    from rapidfuzz import fuzz
except Exception as e:  # pragma: no cover
    logging.exception(e)
    fuzz = None  # type: ignore


def _hashable(tx: BankTransaction) -> tuple:
    return (
        tx.posted_date,
        tx.value_date,
        round(tx.amount, 2),
    )


def dedupe_transactions(rows: Iterable[BankTransaction]) -> List[BankTransaction]:
    """Remove duplicate transactions keeping the one with highest confidence."""
    by_key: dict[tuple, BankTransaction] = {}
    for tx in rows:
        key = _hashable(tx)
        existing = by_key.get(key)
        if not existing:
            by_key[key] = tx
            continue
        if existing.description != tx.description:
            similar = False
            if (
                existing.description in tx.description
                or tx.description in existing.description
            ):
                similar = True
            elif (
                fuzz is not None
                and fuzz.ratio(existing.description, tx.description) >= 70
            ):
                similar = True
            if not similar:
                by_key[key + (tx.description,)] = tx
                continue
        if tx.confidence > existing.confidence or len(tx.description) > len(
            existing.description
        ):
            by_key[key] = tx
    return list(by_key.values())

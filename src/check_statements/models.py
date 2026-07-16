from __future__ import annotations

"""Transaction data models and related helpers."""

from dataclasses import dataclass, field
import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    """Represents a single financial transaction.

    Attributes:
        date: The transaction date.
        amount: The signed amount (positive for incoming, negative for outgoing).
        description: A textual description of the transaction.
        reference_ids: Unique reference numbers or identifiers.
        beneficiary: An optional field indicating the counterparty (payer or payee).
        metadata: Arbitrary metadata (e.g. source file, row number) preserved
                  through processing.
    """

    date: date
    amount: float
    description: str
    reference_ids: List[str] = field(default_factory=list)
    beneficiary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalised_description(self, llm_wrapper: Any | None = None) -> str:
        """Return a cached or locally cleaned description for fuzzy matching."""
        desc = self.description or ""
        # Resolve cache/function via public facade so tests can monkeypatch
        try:
            from src import check_statements as _facade  # type: ignore
        except Exception:  # pragma: no cover
            _facade = None  # type: ignore
        cache = (
            getattr(_facade, "_DESCRIPTION_CACHE", None) if _facade is not None else None
        )
        if not isinstance(cache, dict):
            # fallback to internal cache maintained by facade
            from src.check_statements_logic import _DESCRIPTION_CACHE  # type: ignore

            cache = _DESCRIPTION_CACHE
        cached = cache.get(desc)
        if cached:
            return cached
        # fallback to local cleaner via facade
        cleaner = getattr(_facade, "_clean_description_local", None) if _facade else None
        if cleaner is None:
            from src.check_statements.normalisation import _clean_description_local  # type: ignore

            cleaner = _clean_description_local
        return cleaner(desc)

    def normalised_beneficiary(self) -> str:
        """Return upper‑case beneficiary for fuzzy matching."""
        return (self.beneficiary or "").upper()


# Keep public API limited here; helpers are imported in package __init__
__all__ = ("Transaction",)

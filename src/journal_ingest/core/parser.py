from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Mapping


class BaseJournalParser(ABC):
    """Contract for journal parsers."""

    @abstractmethod
    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        """Return confidence score between 0.0 and 1.0."""

    @abstractmethod
    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        """Yield canonical journal line dictionaries."""

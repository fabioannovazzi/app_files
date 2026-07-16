from __future__ import annotations

"""Scaffolding to hold Stage 1 candidates (no runtime integration yet)."""

from dataclasses import dataclass, field
from typing import Dict, List

__all__ = ("CandidateEdge", "CandidateGraph")


@dataclass(slots=True)
class CandidateEdge:
    bank_index: int
    ledger_index: int
    amount_delta: float
    date_diff_days: int
    labels: List[str] = field(default_factory=list)


class CandidateGraph:
    def __init__(self, bank_size: int) -> None:
        self._edges_by_bank: Dict[int, List[CandidateEdge]] = {i: [] for i in range(bank_size)}

    def add_edge(self, edge: CandidateEdge) -> None:
        self._edges_by_bank[edge.bank_index].append(edge)

    def edges_for_bank(self, bank_index: int) -> List[CandidateEdge]:
        return self._edges_by_bank.get(bank_index, [])


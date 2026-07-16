"""Data schemas for bank statement checking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class RowCandidate:
    """Possible transaction row on a page."""

    page_index: int
    y_top: float
    y_bottom: float
    x_spans: List[Tuple[float, float]]
    raw_text: str
    lang: Optional[str]
    features: Dict[str, float]
    reason_flags: List[str]
    score: float


@dataclass
class ExtractionReport:
    """Telemetry about extraction run."""

    file_path: str
    total_pages: int
    strategies_tried: List[str]
    chosen_strategy: str
    per_page_candidates: List[int]
    per_page_rows_extracted: List[int]
    coverage_by_page: List[float]
    global_coverage: float
    dropped_candidates_sample: List[RowCandidate]
    notes: List[str]

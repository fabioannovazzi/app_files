"""Telemetry helpers for statement extraction."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from modules.utilities.cache import get_cache_dir

from .schemas import ExtractionReport, RowCandidate

_CACHE_DIR = get_cache_dir("bank_ingestion")


def collect_extraction_report(
    file_path: str,
    total_pages: int,
    strategies_tried: List[str],
    chosen_strategy: str,
    per_page_candidates: List[int],
    per_page_rows_extracted: List[int],
    dropped_candidates_sample: Optional[List[RowCandidate]] = None,
    notes: Optional[List[str]] = None,
) -> ExtractionReport:
    """Create and persist :class:`ExtractionReport`."""

    coverage_by_page = [
        rows / max(1, cand)
        for cand, rows in zip(per_page_candidates, per_page_rows_extracted)
    ]
    global_coverage = sum(per_page_rows_extracted) / max(1, sum(per_page_candidates))

    report = ExtractionReport(
        file_path=file_path,
        total_pages=total_pages,
        strategies_tried=strategies_tried,
        chosen_strategy=chosen_strategy,
        per_page_candidates=per_page_candidates,
        per_page_rows_extracted=per_page_rows_extracted,
        coverage_by_page=coverage_by_page,
        global_coverage=global_coverage,
        dropped_candidates_sample=dropped_candidates_sample or [],
        notes=notes or [],
    )

    out_dir = _CACHE_DIR / "bank_extract_reports"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{Path(file_path).stem}.report.json"
    with out_file.open("w", encoding="utf-8") as fh:
        json.dump(asdict(report), fh, ensure_ascii=False, indent=2)
    return report

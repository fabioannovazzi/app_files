import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

# Prefer canonical import; fall back to src-layout if needed
try:  # pragma: no cover - import resolution
    from bank_ingestion.check_statements import telemetry as telemetry_mod
    from bank_ingestion.check_statements.schemas import ExtractionReport
    from bank_ingestion.check_statements.telemetry import collect_extraction_report
except Exception:  # pragma: no cover
    from src.bank_ingestion.check_statements import (
        telemetry as telemetry_mod,  # type: ignore
    )
    from src.bank_ingestion.check_statements.schemas import (
        ExtractionReport,  # type: ignore
    )
    from src.bank_ingestion.check_statements.telemetry import (
        collect_extraction_report,  # type: ignore
    )

@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    cache_root = tmp_path / "bank_ingestion"
    cache_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(telemetry_mod, "_CACHE_DIR", cache_root)
    return cache_root


def test_collect_extraction_report_writes_json_and_returns_report(cache_dir):
    # Arrange
    file_path = "subdir/myfile.pdf"  # only stem is used for output naming
    total_pages = 5
    strategies_tried = ["heuristic_a", "heuristic_b"]
    chosen_strategy = "heuristic_b"
    per_page_candidates = [10, 5, 0]
    per_page_rows_extracted = [7, 3, 0]

    # Act
    report = collect_extraction_report(
        file_path=file_path,
        total_pages=total_pages,
        strategies_tried=strategies_tried,
        chosen_strategy=chosen_strategy,
        per_page_candidates=per_page_candidates,
        per_page_rows_extracted=per_page_rows_extracted,
        dropped_candidates_sample=None,
        notes=None,
    )

    # Assert
    assert isinstance(report, ExtractionReport)
    assert report.file_path == file_path
    assert report.total_pages == total_pages
    assert report.strategies_tried == strategies_tried
    assert report.chosen_strategy == chosen_strategy
    assert report.per_page_candidates == per_page_candidates
    assert report.per_page_rows_extracted == per_page_rows_extracted
    assert report.dropped_candidates_sample == []  # defaults to empty list
    assert report.notes == []  # defaults to empty list

    # Coverage calculations
    assert report.coverage_by_page == pytest.approx([0.7, 0.6, 0.0])
    assert report.global_coverage == pytest.approx((7 + 3 + 0) / (10 + 5 + 0))

    # Output file is written alongside matching JSON content
    out_file = cache_dir / "bank_extract_reports" / "myfile.report.json"
    assert out_file.exists()
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved == asdict(report)


def test_collect_extraction_report_zero_candidates_safeguard(cache_dir):
    # Arrange
    file_path = "zero.pdf"

    # Act
    report = collect_extraction_report(
        file_path=file_path,
        total_pages=2,
        strategies_tried=["s1"],
        chosen_strategy="s1",
        per_page_candidates=[0, 0],
        per_page_rows_extracted=[3, 2],
    )

    # Assert: division-by-zero protected via max(1, candidates)
    assert report.coverage_by_page == pytest.approx([3.0, 2.0])
    assert report.global_coverage == pytest.approx(5.0)


def test_collect_extraction_report_mismatched_lengths_truncates_coverage(cache_dir):
    # Arrange

    # Act
    report = collect_extraction_report(
        file_path="mismatch.pdf",
        total_pages=3,
        strategies_tried=["s1", "s2"],
        chosen_strategy="s2",
        per_page_candidates=[2, 2, 2],  # longer than rows list
        per_page_rows_extracted=[1, 2],
    )

    # Assert: coverage is computed for zipped pairs only; global uses full sums
    assert report.coverage_by_page == pytest.approx([0.5, 1.0])
    assert len(report.coverage_by_page) == 2
    assert report.global_coverage == pytest.approx((1 + 2) / (2 + 2 + 2))

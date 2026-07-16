import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

try:  # pragma: no cover - import resolution
    from bank_ingestion.check_statements import telemetry as telemetry_mod
    from bank_ingestion.check_statements.debug_report import (
        build_markdown,
        write_debug_report,
    )
    from bank_ingestion.check_statements.schemas import (
        ExtractionReport,
        RowCandidate,
    )
except Exception:  # pragma: no cover
    from src.bank_ingestion.check_statements import (
        telemetry as telemetry_mod,  # type: ignore
    )
    from src.bank_ingestion.check_statements.debug_report import (  # type: ignore
        build_markdown,
        write_debug_report,
    )
    from src.bank_ingestion.check_statements.schemas import (  # type: ignore
        ExtractionReport,
        RowCandidate,
    )

def _sample_candidate(text: str, reasons: list[str]) -> RowCandidate:
    return RowCandidate(
        page_index=0,
        y_top=0.0,
        y_bottom=10.0,
        x_spans=[(0.0, 100.0)],
        raw_text=text,
        lang="eng",
        features={},
        reason_flags=reasons,
        score=0.1,
    )


def test_build_markdown_golden_path():
    # Arrange
    report = ExtractionReport(
        file_path="/path/to/statement.pdf",
        total_pages=2,
        strategies_tried=["A", "B"],
        chosen_strategy="B",
        per_page_candidates=[3, 1],
        per_page_rows_extracted=[2, 1],
        coverage_by_page=[0.5, 1.0],
        global_coverage=0.75,
        dropped_candidates_sample=[
            _sample_candidate("raw row", ["overlap", "low_confidence"])
        ],
        notes=["check rows", "done"],
    )

    # Act
    md = build_markdown(report)

    # Assert
    assert md.startswith("# Debug report for statement.pdf")
    assert "Total pages: 2" in md
    assert "Strategies tried: A, B (chosen: B)" in md
    assert "Global coverage: 75.00%" in md
    # table header and rows
    assert "| Page | Candidates | Extracted | Coverage |" in md
    assert "| --- | --- | --- | --- |" in md
    assert "| 0 | 3 | 2 | 50% |" in md
    assert "| 1 | 1 | 1 | 100% |" in md
    # extras
    assert "## Dropped candidate samples" in md
    assert "`raw row`" in md and "overlap, low_confidence" in md
    assert "## Notes" in md and "- check rows" in md


def test_build_markdown_empty_edge_case():
    # Arrange
    report = ExtractionReport(
        file_path="/tmp/a/b/bank.pdf",
        total_pages=0,
        strategies_tried=[],
        chosen_strategy="none",
        per_page_candidates=[],
        per_page_rows_extracted=[],
        coverage_by_page=[],
        global_coverage=0.0,
        dropped_candidates_sample=[],
        notes=[],
    )

    # Act
    md = build_markdown(report)

    # Assert
    lines = md.splitlines()
    assert lines[0] == "# Debug report for bank.pdf"
    assert "Global coverage: 0.00%" in md
    assert "Strategies tried:" in md and "(chosen: none)" in md
    # Table exists but contains no page rows
    assert "| --- | --- | --- | --- |" in md
    assert "| 0 |" not in md
    # No optional sections
    assert "## Dropped candidate samples" not in md
    assert "## Notes" not in md


def test_write_debug_report_creates_file_and_contents(tmp_path, monkeypatch):
    # Arrange
    cache_root = tmp_path / "bank_ingestion"
    cache_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(telemetry_mod, "_CACHE_DIR", cache_root)
    report = ExtractionReport(
        file_path="dir/stmt.pdf",
        total_pages=1,
        strategies_tried=["only"],
        chosen_strategy="only",
        per_page_candidates=[1],
        per_page_rows_extracted=[1],
        coverage_by_page=[1.0],
        global_coverage=1.0,
        dropped_candidates_sample=[],
        notes=[],
    )
    expected_md = build_markdown(report)

    # Act
    out_path_str = write_debug_report(report)

    # Assert
    out_path = Path(out_path_str)
    assert out_path.exists()
    assert out_path.parent == cache_root / "bank_extract_reports"
    assert out_path.name == "stmt.debug.md"
    assert out_path.read_text(encoding="utf-8") == expected_md

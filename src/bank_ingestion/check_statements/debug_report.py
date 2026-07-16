"""Build human friendly debug reports."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import telemetry
from .schemas import ExtractionReport, RowCandidate


def build_markdown(report: ExtractionReport) -> str:
    """Return a Markdown representation of the report."""
    lines = [f"# Debug report for {Path(report.file_path).name}", ""]
    lines.append(f"Total pages: {report.total_pages}")
    lines.append(
        f"Strategies tried: {', '.join(report.strategies_tried)} (chosen: {report.chosen_strategy})"
    )
    lines.append(f"Global coverage: {report.global_coverage:.2%}")
    lines.append("")
    lines.append("| Page | Candidates | Extracted | Coverage |")
    lines.append("| --- | --- | --- | --- |")
    for idx, (cand, rows, cov) in enumerate(
        zip(
            report.per_page_candidates,
            report.per_page_rows_extracted,
            report.coverage_by_page,
        )
    ):
        lines.append(f"| {idx} | {cand} | {rows} | {cov:.0%} |")
    if report.dropped_candidates_sample:
        lines.append("\n## Dropped candidate samples")
        for cand in report.dropped_candidates_sample:
            lines.append(
                f"- `{cand.raw_text}` → {', '.join(cand.reason_flags) or 'n/a'}"
            )
    if report.notes:
        lines.append("\n## Notes")
        for n in report.notes:
            lines.append(f"- {n}")
    return "\n".join(lines)


def write_debug_report(report: ExtractionReport) -> str:
    """Persist Markdown report to file and return path."""
    out_dir = telemetry._CACHE_DIR / "bank_extract_reports"
    out_dir.mkdir(exist_ok=True)
    md_path = out_dir / f"{Path(report.file_path).stem}.debug.md"
    md_content = build_markdown(report)
    md_path.write_text(md_content, encoding="utf-8")
    return str(md_path)

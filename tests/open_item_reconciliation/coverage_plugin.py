"""Report the bootstrap's virtual Python filenames against their exact sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coverage import CoveragePlugin, FileTracer

__all__ = ["coverage_init"]

SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "open-item-reconciliation"
    / "scripts"
)


class RetainedSourceTracer(FileTracer):
    """The bootstrap compiles retained bytes unchanged, preserving line numbers."""

    def __init__(self, source: Path) -> None:
        self.source = source

    def source_filename(self) -> str:
        return str(self.source)


class RetainedSourceCoverage(CoveragePlugin):
    def file_tracer(self, filename: str) -> FileTracer | None:
        path = Path(filename)
        source = SCRIPTS / "retained_sources" / f"{path.stem}.source"
        if path.parent == SCRIPTS and path.suffix == ".py" and source.is_file():
            return RetainedSourceTracer(source)
        return None

    def file_reporter(self, filename: str) -> str:
        return "python"


def coverage_init(reg: Any, options: dict[str, str]) -> None:
    """Register a test-only filename mapping without changing product execution."""
    reg.add_file_tracer(RetainedSourceCoverage())

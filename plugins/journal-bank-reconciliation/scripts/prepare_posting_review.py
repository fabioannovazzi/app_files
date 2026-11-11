"""Prepare Vera's native accounting-proposal review without running a matcher."""

from __future__ import annotations

import runpy
from pathlib import Path

__all__: list[str] = []

if __name__ == "__main__":
    source = Path(__file__).resolve()
    candidates = (
        source.parents[3] / "scripts/native_posting_review.py",
        source.parents[2] / "vera/scripts/native_posting_review.py",
    )
    helper = next((path for path in candidates if path.is_file()), None)
    if helper is None:
        raise ValueError(
            "Accounting-proposal review requires the Vera product installation"
        )
    runpy.run_path(str(helper), run_name="__main__")

#!/usr/bin/env python3
"""Build or validate local run disclosures using the canonical report helper."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["main"]

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    COMPONENT_ROOT / "vendor" / "modules",
    COMPONENT_ROOT.parent / "vera" / "scripts",
):
    if (candidate / "model_data_report.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from model_data_report import main as report_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Keep generic lifecycle reports local; server stamping belongs to its host."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    return report_main(arguments, server_attestation=False)


if __name__ == "__main__":
    raise SystemExit(main())

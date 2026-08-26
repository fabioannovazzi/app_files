#!/usr/bin/env python3
"""Evaluate Centrale Rischi parser coverage without producing a client analysis."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from centrale_rischi_pdf import evaluate_pdf_corpus  # noqa: E402

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def _page_selection(value: str) -> tuple[str, tuple[int, ...]]:
    """Parse one explicit NAME=1,3-5 corpus case."""

    name, separator, selection = value.partition("=")
    if not separator or not name.strip() or not selection.strip():
        raise argparse.ArgumentTypeError("Expected NAME=1,3-5.")
    pages: set[int] = set()
    for part in selection.split(","):
        start_text, range_separator, end_text = part.strip().partition("-")
        try:
            start = int(start_text)
            end = int(end_text) if range_separator else start
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Page numbers must be integers.") from exc
        if start < 1 or end < start:
            raise argparse.ArgumentTypeError(
                "Page ranges must be positive and ordered."
            )
        pages.update(range(start, end + 1))
    return name.strip(), tuple(sorted(pages))


def main(argv: list[str] | None = None) -> int:
    """Write a page- or case-level parser coverage receipt."""

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        type=_page_selection,
        help="Optional explicit case such as example-a=4-6,8; defaults to one case per page.",
    )
    args = parser.parse_args(argv)
    cases: dict[str, tuple[int, ...]] | None = None
    if args.case:
        cases = {}
        for name, pages in args.case:
            if name in cases:
                parser.error(f"Duplicate corpus case ID: {name}")
            cases[name] = pages
    try:
        evaluation = evaluate_pdf_corpus(args.input, cases=cases)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info(
        "Evaluated %s separate corpus cases; no client analysis was generated.",
        evaluation["case_count"],
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())

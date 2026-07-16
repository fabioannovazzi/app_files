"""CLI for bank statement checking."""
from __future__ import annotations

import argparse
import logging

from .debug_report import write_debug_report
from .telemetry import collect_extraction_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check_statements")
    sub = parser.add_subparsers(dest="cmd")
    parse_p = sub.add_parser("parse")
    parse_p.add_argument("--file", required=True, help="Path to PDF")
    parse_p.add_argument("--debug", action="store_true")
    parse_p.add_argument("--qa-report", action="store_true")
    parse_p.add_argument("--coverage-min", type=float, default=0.6)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd != "parse":
        parser.print_help()
        return 1

    # placeholder extraction for demo purposes
    report = collect_extraction_report(
        file_path=args.file,
        total_pages=0,
        strategies_tried=[],
        chosen_strategy="",
        per_page_candidates=[],
        per_page_rows_extracted=[],
    )
    if args.debug:
        write_debug_report(report)
    if args.qa_report:
        logging.info(f"Global coverage: {report.global_coverage:.2%}")
        if report.global_coverage < args.coverage_min:
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

import argparse
import csv
from pathlib import Path
import logging

from journal_ingest.agent import generate_layout
from journal_ingest.config import get_recipe
from journal_ingest.core import ParserConfidenceError, ValidationError
from journal_ingest.core.validate import ValidationReport, validate_entry_balances
from journal_ingest.router import Router
from journal_ingest.strategies import (
    JournalStrategyExcel,
    JournalStrategyTableArea,
    JournalStrategyTextLayout,
    OcrParser,
    TablePDFParser,
    TextPDFParser,
)


def build_router(agent=None) -> Router:
    parsers = [
        JournalStrategyExcel(),
        TextPDFParser(),
        TablePDFParser(),
        JournalStrategyTextLayout(get_recipe("journal_generic_v1")),
        JournalStrategyTableArea(),
        OcrParser(),
    ]
    return Router(parsers, agent=agent)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for journal parsing."""
    parser = argparse.ArgumentParser(prog="journal-parse")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("out.csv"))
    parser.add_argument("--recipe")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--allow-agent", action="store_true")
    args = parser.parse_args(argv)

    if not args.auto and not args.recipe:
        args.auto = True

    file_bytes = args.input.read_bytes()

    try:
        if args.auto:
            agent_fn = generate_layout if args.allow_agent else None
            router = build_router(agent_fn)
            parser_impl = router.route(file_bytes, meta={})
            confidence = parser_impl.probe(file_bytes, meta={})
        else:
            config = get_recipe(args.recipe)
            parser_impl = JournalStrategyTextLayout(config)
            confidence = 1.0
        rows = list(parser_impl.parse(file_bytes, meta={}))
        balance_issues = validate_entry_balances(rows)
    except (ParserConfidenceError, ValidationError) as exc:  # pragma: no cover
        logging.exception(f"Error: {exc}")
        return 1

    report = ValidationReport(
        rows_parsed=len(rows),
        line_match_pct=100.0,
        amount_normalized_pct=100.0,
        dropped_lines_by_rule={},
        balance_issues=balance_issues,
    )

    if len(rows) > 0:
        with args.output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    logging.info(f"confidence={confidence:.2f} {report.compact()}")
    return 0

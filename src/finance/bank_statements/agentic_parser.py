"""Agentic parser that selects extraction strategies per page."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pdfplumber

from .bank_statement_strategies import choose_strategy
from .dedupe import dedupe_transactions
from .lexicon import Lexicon
from .model import BankTransaction, PageDecision, ParseReport

logger = logging.getLogger(__name__)


@dataclass
class ParserConfig:
    enable_ocr: bool = True
    language_hint: str | None = None
    debug_dump_dir: str | None = None


class AgenticStatementParser:
    """Orchestrates strategy selection and normalisation."""

    def __init__(
        self, config: ParserConfig | None = None, lexicon: Lexicon | None = None
    ):
        self.config = config or ParserConfig()
        self.lexicon = lexicon or Lexicon()

    def parse(self, path: str | Path) -> Tuple[List[BankTransaction], ParseReport]:
        """Parse the given file and return transactions with a report."""
        p = Path(path)
        report = ParseReport()
        if p.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported")
        with pdfplumber.open(p) as pdf:
            report.pages_total = len(pdf.pages)
            strategy = choose_strategy(pdf)
            rows = strategy.parse(pdf)
            transactions = dedupe_transactions(rows)
            report.transactions_extracted = len(transactions)
            report.pages_parsed = report.pages_total if len(rows) > 0 else 0
            report.by_strategy[strategy.name] = len(transactions)
            for page in pdf.pages:
                page_rows = [
                    r for r in transactions if r.source_page == page.page_number
                ]
                report.decisions.append(
                    PageDecision(
                        page_number=page.page_number,
                        strategy=strategy.name,
                        transactions=page_rows,
                    )
                )
            logger.info(
                "parsed %s pages, %s transactions via %s",
                report.pages_total,
                len(transactions),
                strategy.name,
            )
            if self.config.debug_dump_dir:
                dump_dir = Path(self.config.debug_dump_dir)
                dump_dir.mkdir(parents=True, exist_ok=True)
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    (dump_dir / f"page-{page.page_number:03d}.txt").write_text(text)
                if getattr(strategy, "debug_rows", None):
                    with open(dump_dir / "rows.jsonl", "w") as fh:
                        for item in strategy.debug_rows:  # type: ignore[attr-defined]
                            fh.write(json.dumps(item) + "\n")
                with open(dump_dir / "transactions.json", "w") as fh:
                    json.dump([t.__dict__ for t in transactions], fh, default=str)
        return transactions, report


def _cli_preview(path: str) -> None:  # pragma: no cover - simple manual tool
    parser = AgenticStatementParser()
    rows, rep = parser.parse(path)
    logging.info(
        f"pages: {rep.pages_total}, parsed: {rep.pages_parsed}, rows: {len(rows)}"
    )
    for strat, count in rep.by_strategy.items():
        logging.info(f"  {strat}: {count}")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Preview parsed transactions")
    ap.add_argument("pdf")
    args = ap.parse_args()
    _cli_preview(args.pdf)

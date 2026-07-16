"""CLI for extracting transactions from bank statements."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

import polars as pl

from .orchestrator import StatementExtractor
from .schema import Transaction


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract bank statement transactions")
    parser.add_argument("--file", required=True, help="Path to statement file")
    parser.add_argument("--out", help="Optional output CSV path")
    parser.add_argument("--diagnostics", help="Optional diagnostics JSON path")
    args = parser.parse_args(argv)

    extractor = StatementExtractor()
    rows, diag = extractor.orchestrate(args.file, {})

    if args.out:
        df = pl.DataFrame([asdict(r) for r in rows]).drop(
            ["reference_ids", "beneficiary"], strict=False
        )
        df.write_csv(args.out)
    if args.diagnostics:
        with open(args.diagnostics, "w", encoding="utf-8") as f:
            json.dump(asdict(diag), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":  # pragma: no cover
    main()

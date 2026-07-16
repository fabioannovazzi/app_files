#!/usr/bin/env python3
from __future__ import annotations

"""Utility to inspect how bank and ledger files are parsed.

Run from the project root:

    python scripts/inspect_parsed_transactions.py \
        --bank /path/to/bank1.pdf \
        --bank /path/to/bank2.pdf \
        --ledger /path/to/ledger.xlsx

Only rows whose description (or extra description) contains one of the
keywords ``PRELIEVO`` or ``PRELEVAMENTO`` are printed to keep the output
focused on cash withdrawals.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.check_statements.loaders import load_bank_rows, load_ledger_rows


KEYWORDS = ("PRELIEVO", "PRELEVAMENTO")


def _contains_keyword(value: str | None) -> bool:
    if not value:
        return False
    upper = value.upper()
    return any(token in upper for token in KEYWORDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bank",
        dest="bank_files",
        action="append",
        required=True,
        help="Bank statement file (PDF/XLSX/CSV). Repeat for multiple files.",
    )
    parser.add_argument(
        "--ledger",
        dest="ledger_file",
        required=True,
        help="Ledger file (XLSX/CSV).",
    )
    parser.add_argument(
        "--language",
        default="it",
        help="Language hint passed to the loaders (default: it).",
    )
    args = parser.parse_args()

    bank_rows = []
    for name in args.bank_files:
        path = Path(name).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Bank file not found: {path}")
        bank_rows.extend(
            load_bank_rows([(path.name, path.read_bytes())], language=args.language)
        )

    ledger_path = Path(args.ledger_file).expanduser().resolve()
    if not ledger_path.is_file():
        raise FileNotFoundError(f"Ledger file not found: {ledger_path}")
    ledger_rows = load_ledger_rows(
        [(ledger_path.name, ledger_path.read_bytes())],
        language=args.language,
    )

    print("Bank rows with withdrawal keywords:")
    for idx, row in enumerate(bank_rows):
        desc = row.get("description", "")
        if _contains_keyword(desc):
            print(
                f"{idx}: date={row['date']} amount={row['amount']} "
                f"desc={desc}"
            )

    print("\nLedger rows with withdrawal keywords:")
    for idx, row in enumerate(ledger_rows):
        desc = row.get("description", "")
        meta = row.get("metadata") or {}
        extra = meta.get("extra_desc")
        if _contains_keyword(desc) or _contains_keyword(extra):
            print(
                f"{idx}: date={row['date']} amount={row['amount']} "
                f"desc={desc} extra_desc={extra}"
            )


if __name__ == "__main__":
    main()

Inspect Parsed Transactions
==========================

Script: `python scripts/inspect_parsed_transactions.py`

Purpose
- Diagnostic helper to inspect how bank and ledger files are parsed, focusing on cash withdrawals.

What it does
- Loads bank statements and a ledger file via the check_statements loaders.
- Filters rows whose description (or extra description) contains the keywords `PRELIEVO` or `PRELEVAMENTO`.
- Prints matching rows (date, amount, descriptions) to stdout.

Usage
```bash
python scripts/inspect_parsed_transactions.py \
  --bank /path/to/bank1.pdf \
  --bank /path/to/bank2.pdf \
  --ledger /path/to/ledger.xlsx \
  --language it
```
- `--bank` (repeatable): Bank statement file(s) (PDF/XLSX/CSV).
- `--ledger`: Ledger file (XLSX/CSV).
- `--language`: Language hint passed to loaders (default: `it`).

Notes
- Run from the repo root with `PYTHONPATH=$PWD` if needed.
- Errors if files are missing. Output is printed to stdout for quick inspection.***

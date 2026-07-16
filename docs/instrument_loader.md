Instrument Loader (ledger header detection)
===========================================

Script: `python scripts/instrument_loader.py path/to/ledger.xlsx`

Purpose
- Diagnostic helper to inspect ledger header detection and column mapping for statement parsing.

What it does
- Loads the Excel ledger file supplied on the command line.
- Runs `_detect_excel_header_polars`, rebuilds the DataFrame with the detected header, infers column mapping using ledger keywords, and prints the results.

Usage
- Run from repo root (or adjust `PYTHONPATH`):
```bash
python scripts/instrument_loader.py path/to/ledger.xlsx
```

Output
- Prints detected header row index, DataFrame shape, column names, inferred mapping, and the first few rows to stdout.

Notes
- This is a diagnostics tool; pass the path to the file you want to inspect.

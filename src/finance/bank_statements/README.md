# Bank Statement Agentic Parser

This package provides a modular parser that extracts transaction lines from
bank statements.  Each page is inspected and one of several strategies is
selected:

- **layout** – uses detected table headers and column positions.
- **stream** – falls back to heuristics over text lines.
- **ocr** – as a last resort when pages are rasterised.

The top level entry point is `AgenticStatementParser.parse(path)` which
returns a list of `BankTransaction` objects and a `ParseReport` describing
what happened.

A small CLI is available:

```bash
python -m finance.bank_statements.agentic_parser my.pdf
```

Dependencies such as `paddleocr` and `rapidfuzz` are optional and the parser
will degrade gracefully if they are missing.

# Journal Sampling Workflow Reference

## Deterministic Boundary

The helper scripts perform deterministic work: file inspection, parser selection, column mapping suggestions, row normalization, filtering, sample selection, and audit metadata. Codex can inspect outputs, update the recipe in the work folder, and explain assumptions, but it should not rewrite extracted rows or sampled rows as if they came from deterministic evidence.

## Mapping Fields

- `date`: journal entry date.
- `movement_number`: movement, registration, or document number when available.
- `account`: account code or account identifier.
- `account_desc`: account description.
- `line_desc`: entry description or causale.
- `debit` and `credit`: separate amount columns.
- `amount`: signed amount column when debit/credit are not separate.

## Supported Parsers

- tabular Excel/CSV with header rows;
- print-friendly Excel exports with repeated headers and wide columns;
- text PDFs where journal lines are extractable without OCR.

OCR-only scanned PDFs are outside v1. If a run exposes a repeatable OCR-only use case, report it through the plugin improvement feedback policy.

## Sampling Methods

- `random`: deterministic seed 42.
- `systematic`: interval-based population traversal.
- `stratified`: deterministic group allocation by account or another mapped column.
- `mus`: deterministic cumulative monetary-unit thresholds.

## Review Policy

The final response should report parser confidence, missing fields, filters, population size, sample size, and output paths. If Codex had to adjust the recipe or ask the user a mapping question, include that assumption explicitly.

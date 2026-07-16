# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Changed
- Polars `collect` calls now use `engine="streaming"` instead of the deprecated `streaming=True` flag.
- Helper functions `collect_tail`, `n_unique_lazy`, `extract_top_categories`, `convert_df_csv`, and `convert_df_parquet` now accept an `engine` parameter to control collection.
- Entry checking can now be cancelled mid-run, returning partial results.
- Introduced multilingual bank statement extraction with locale-aware parsing, multiple strategies and an orchestrator fallback.
- Journal PDF parser now guards against ambiguous boolean evaluation errors
  **case-insensitively**, logs per-strategy failures, wraps parsing in a
  catch-all that returns an empty frame when ambiguity bubbles up, and uses
  ``df.height > 0`` instead of ``df.is_empty()`` in acceptance checks.
- Repository-wide removal of ``df.is_empty()`` and other implicit boolean
  evaluations on Polars objects; helpers like ``validate_entry_balances`` and
  ``validate_page_totals`` now use explicit ``height``/``len`` checks to avoid
  "truth value of a Series is ambiguous" errors across modules.
- Journal PDF parser now falls back to a group-lines strategy when table,
  text, OCR and text heuristics fail to extract any rows.

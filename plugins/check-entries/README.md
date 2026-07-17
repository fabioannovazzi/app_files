# Check Entries Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/check-entries) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Check Entries is a Codex workflow plugin for comparing selected journal entries with supporting PDF documents.

The plugin keeps extraction and comparison deterministic:

- `scripts/inspect_entries.py` inspects the journal columns and PDF support folder, then writes `inspection.json` and `suggested_recipe.json`.
- `scripts/run_checks.py` normalizes entries, matches PDFs by movement number, compares amount/date/beneficiary evidence when available, and writes CSV/XLSX/JSON review outputs.
- `scripts/run_checks.py` also writes `run_intake.json`, `review_payload.json`,
  `ui_decisions.json`, and `final_artifacts.json` so Codex can render an MCP
  HTML review surface for supported entries, missing support, mismatches,
  manual-review rows, PDF extraction diagnostics, and generated artifacts.
- Codex handles ambiguity, mapping decisions, review explanation, and final language, without direct OpenAI API calls from the plugin scripts.

Run `python scripts/check_dependencies.py` from the plugin directory before using the helper scripts.

Working locales: `it`, `en`, `fr`, `de`.

## UI review MCP

The review UI follows the local OpenAI-style MCP/widget pattern:

- the Python workflow writes bounded review-session JSON files in the run
  output folder;
- the local MCP server declared in `.mcp.json` exposes
  `validate_check_entries_review`, `render_check_entries_review`, and
  `save_check_entries_decisions`;
- `assets/check-entries-review-widget.html` renders summary counts, searchable
  rows, type filters, evidence details, and reviewer action controls;
- saved reviewer actions are validated against the review payload and persisted
  to `ui_decisions.json` when the render call includes `run_intake.output_dir`;
- if MCP is unavailable, Codex reads `review_payload.json` and continues with
  Markdown/chat review without blocking the workflow.

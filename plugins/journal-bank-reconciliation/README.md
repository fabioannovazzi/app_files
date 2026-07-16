# Journal-Bank Reconciliation Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/journal-bank-reconciliation) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Guided Codex workflow for deterministic reconciliation between bank statements and journal or ledger exports.

The plugin is multilingual (`it`, `en`, `fr`, `de`) and keeps helper scripts deterministic. Codex handles inspection, mapping decisions, review explanation, and improvement suggestions; scripts perform extraction, normalization, matching, and exports without direct model API calls.

## Internal Scripts

- `scripts/check_dependencies.py`
- `scripts/inspect_inputs.py`
- `scripts/run_reconciliation.py`
- `scripts/journal_bank_core.py`

Users should invoke the plugin from Codex rather than running the scripts directly.

## Local MCP Review UI

Deterministic runs now emit `run_intake.json`, `review_payload.json`,
`ui_decisions.json`, and `final_artifacts.json` in the reconciliation output
folder.

- `validate_journal_bank_review` validates the review payload.
- `render_journal_bank_review` renders the local widget
  `ui://widget/journal-bank-review.html`.
- The widget focuses on unmatched bank rows, unmatched journal rows, matched
  pair evidence, diagnostics, and generated artifacts.

If MCP rendering is unavailable, Codex should use the JSON payloads plus
`review_notes.md`, CSVs, and workbook as the fallback review surface.

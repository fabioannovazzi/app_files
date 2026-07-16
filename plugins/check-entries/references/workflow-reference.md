# Check Entries Workflow Reference

## Deterministic Boundary

The helper scripts perform only deterministic work: journal parsing, PDF text extraction, support matching, and rule-based comparisons. Codex can inspect outputs and explain professional review conclusions, but it should not rewrite script outputs as if they were extracted evidence.

## Mapping Fields

- `movement_number`: required for support matching.
- `date`: optional expected date for date checks.
- `amount`: optional signed amount column.
- `debit_amount` and `credit_amount`: optional debit/credit pair used when `amount` is absent.
- `description`: optional context for review.
- `beneficiary`: optional expected payee/counterparty/beneficiary.

## Review Statuses

- `ok`: all available deterministic checks passed.
- `mismatch`: one or more deterministic checks failed.
- `missing_support`: no matching support PDF was found.
- `manual_review`: no deterministic amount/date/beneficiary field was available.

## Review UI Contract

After the deterministic run, use `checks/review_payload.json` as the
structured review contract for the MCP widget or Markdown fallback. The payload
is bounded and selected for review; it does not replace `check_results.csv`,
`check_results.xlsx`, `pdf_inventory.json`, `check_audit.json`, or
`review_notes.md` as the full evidence set.

## Improvement Policy

When a run exposes a missing parser, brittle matching rule, or repetitive manual step, Codex should offer to draft a concise GitHub issue for the repository. Creating the issue still requires the user's confirmation.

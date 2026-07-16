# Concordato Plan Review Methodology

## Scope

The workflow reviews the numerical section of an Italian concordato plan against accounting evidence. It is not a generic report generator and it is not a legal attestation engine.

## Review UI contract

After the deterministic run, use `review_payload.json` as the structured review
contract for the MCP widget or Markdown fallback. The payload is bounded and
selected for review: it does not replace `amount_candidates.csv`,
`exact_amount_matches.csv`, `concordato_tie_out_workpaper.xlsx`, or
`concordato_review_summary.docx` as the full evidence set.

## Evidence Categories

- `historical_accounting_data`: amount expected to agree to bilancio, mastrino, ledger, or DB.
- `rectification`: adjustment to a historical amount, expected to agree to DB support or a named detail schedule.
- `reclassification`: movement between financial statement lines, expected to be neutral in aggregate and documented.
- `prospective_assumption`: forward-looking value or plan assumption; it must be explained, not mechanically tied to historical balances.
- `unsupported_or_unclear`: number or statement not yet tied to a source, assumption, or explicit calculation.

## Deterministic Boundary

Use deterministic code for file inventory, text extraction, workbook sheet inspection, number parsing, exact arithmetic, and candidate amount matching. These tasks are mechanically verifiable and require auditability.

Use Codex/reviewer judgment for semantic mapping, relevance of a source to a plan assertion, going-concern implications, legal/tax framing, materiality, omission assessment, and final criticality.

## Output Standard

For each material number in the plan, the final review should identify:

- plan location and text context;
- amount in the plan;
- source file, sheet/page, row/cell, and source context;
- source amount;
- difference;
- category from the evidence categories above;
- reviewer comment and missing evidence request when needed.

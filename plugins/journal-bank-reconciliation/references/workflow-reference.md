# Journal-Bank Reconciliation Reference

This reference documents the deterministic boundary for the plugin. Codex reads it only when a run needs more detail than the main skill.

## Stable Columns

Normalized bank and journal outputs use these canonical columns:

- `side`
- `transaction_id`
- `transaction_date`
- `amount_signed`
- `amount_abs`
- `description`
- `beneficiary`
- `reference`
- `movement_number`
- `account`
- `source_file`
- `source_row`

Match outputs use:

- `status`
- `stage`
- `bank_transaction_id`
- `journal_transaction_id`
- `bank_date`
- `journal_date`
- `date_diff_days`
- `bank_amount`
- `journal_amount`
- `amount_delta`
- `bank_description`
- `journal_description`
- `shared_references`
- `review_note`

## Header Detection

The inspection script scores the first rows of tabular files using multilingual accounting labels. It prefers rows containing date, amount, debit/credit, description, beneficiary, reference, movement, or account labels. Codex can override with `header_rows` in `suggested_recipe.json` when the detected row is wrong.

## Mapping Fields

Use `amount` when the file has a single signed amount column. Use `debit` and `credit` when the file splits debit and credit. The script calculates signed amount as debit minus credit.

Reference fields can contain document numbers, CRO/TRN, invoice references, IBAN fragments, or other stable identifiers. They are used before weaker description-token matching.

## Matching Stages

1. `reference`: exact shared reference token among amount/date candidates.
2. `amount_date_unique`: exactly one amount/date candidate.
3. `beneficiary`: deterministic counterparty token containment among candidates.
4. `description_tokens`: deterministic description token overlap among candidates.
5. `amount_date_single`: exactly one amount candidate when date is absent or not useful.

Rows are not reused. Ambiguity stays unmatched.

## Codex Review Boundary

Codex may:

- decide whether a generated mapping is credible;
- ask a targeted mapping question;
- inspect source rows;
- explain why unmatched rows need manual review;
- propose deterministic improvements.

Codex must not:

- alter a match solely because it "looks right";
- hide unresolved ambiguity;
- make direct OpenAI API calls from helper scripts;
- ask the user to operate CLI scripts directly.

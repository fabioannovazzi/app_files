# Evidence And Checks

Load this reference when deciding evidence strength, source roles, canonical fields, or deterministic accounting checks for the audit reconciliation workflow.

## Evidence Standards

Use deterministic evidence levels:

- `strong_external`: official bank statement, factoring/operator statement, or other independent external evidence.
- `documented_compensation`: compensation/netting supported under the configured rule.
- `configured_strong`: evidence explicitly treated as strong under case assumptions.
- `bridge_only`: payment order, remittance batch, or internal bridge without external settlement.
- `weak_internal`: ledger or journal evidence only.
- `none`: no evidence found.
- `out_of_scope`: outside the configured period.

Candidate allocations are not row-level conclusions. A bank transfer that mentions a batch or document number but lacks row-level allocation is candidate evidence, not proof of a specific invoice unless a deterministic rule connects it.

Aggregate roll-forward checks support ledger-level coherence only. They must not close individual rows without row-level evidence.

## Canonical Data

Normalize available evidence into fields such as `record_id`, `source_file`, `source_sheet`, `source_page`, `source_row`, `source_role`, `party`, `counterparty`, `account`, `document_no`, `document_date`, `posting_date`, `value_date`, `amount`, `currency`, `direction`, `description`, `reference`, `beneficiary`, `iban`, `evidence_type`, and `document_key`.

Preserve source references in outputs wherever available.

## Source Roles

Use these roles unless the case requires an extension:

- `open_items`;
- `counterparty_open_items`;
- `ledger`;
- `journal`;
- `bank_statement`;
- `payment_order`;
- `factoring_statement`;
- `compensation_support`;
- `unknown`.

## Deterministic Accounting Checks

When mastrini and journal exports are available, include an `Account rollforward check` sheet with opening balance from ledger, opening balance from journal, net period movement from journal, recalculated closing balance, closing balance from ledger, differences, status, and review note.

When a cut-off date is configured, include `Post-cutoff candidates` where after-cut-off evidence shares a document key with an in-scope open item. These rows are explanatory only and must not close cut-off rows when post-cut-off events are excluded.

When inputs support them, include additional exception-finding controls:

- `Open item aging`;
- `Evidence concentration`;
- `Review signals`;
- `Document source map`;
- `Reversal candidates`;
- `Cutoff window movements`.

These checks guide reviewer attention and must not silently change row-level reconciliation status.

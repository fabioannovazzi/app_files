> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Evidence And Checks

Load this reference when deciding evidence strength, source roles, canonical fields, or deterministic accounting checks for the open-item reconciliation workflow.

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

External evidence may close a row only when its reviewed entity, party,
currency, unit, and allocation policy are compatible with the open item.
One-to-one evidence cannot be reused. One-to-many/many-to-one use must be
declared, and every allocation must conserve source and target amounts exactly
within the reviewed tolerance. Preserve non-zero residuals; never force them to
zero to obtain a passing result.

## Canonical Data

Normalize available evidence into fields such as `record_id`, `source_file`, `source_sheet`, `source_page`, `source_row`, `source_role`, `party`, `counterparty`, `account`, `document_no`, `document_date`, `posting_date`, `value_date`, `amount`, `currency`, `direction`, `description`, `reference`, `beneficiary`, `iban`, `evidence_type`, and `document_key`.

Preserve source references in outputs wherever available. Normalize monetary
values to exact `Decimal` text only after applying the reviewed separators,
reported unit, and the currently supported exact increment `0.01`. Binary floats are not
authoritative. Punctuation that is ambiguous without a reviewed convention
must abstain, any other reported increment must stop before preparation, and a
value that is not a cent multiple must
not enter the prepared population.

Every source decision also declares `date.order` as `day_first` or
`month_first`. ISO/native dates remain unambiguous. A populated critical date
that is invalid under the reviewed order makes the source unqualified and
emits zero rows.

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

Role, adapter, perimeter, and money convention are semantic intake decisions.
Record them in a reviewed decision receipt bound to the full current bytes of
the source. Filename/text matches may populate a suggestion list but never
select a role or unlock a parser.

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

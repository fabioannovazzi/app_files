> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Reviewed CSV/XLSX source layout

Use `reviewed_tabular_accounting_v1` for an ordinary rectangular header-based
CSV or XLSX source with role `open_items`, `bank_statement` or `journal`.
This is an additive adapter; existing PDF, print-journal and payment-order
adapters keep their existing contracts.

Review source meaning in the current host. Do not classify source roles or
evidence strength from filename patterns, header guesses or description
keywords. For synthetic tests retain `sample_kind=agent_test`, an actual AI
reviewer label, `human_confirmation=false` and `professional_approval=false`.
Reviewed receipts remain unsigned and do not authenticate that label.

## Inspection and explicit decisions

1. Inspect the actual sheet names, headers, data rows, typed dates and monetary
   cells with the managed environment. Limit model previews to what is useful;
   exact local parsing still covers the complete reviewed table. Review the
   beginning and end of the table and keep notes/totals outside the selected
   population only when that scope is justified. Do not omit difficult rows.
2. Record the existing source decision fields: role, adapter, reviewer/date,
   accounting perimeter, cent-only money convention and date order. Add the
   `tabular` object below. Use exact current source paths as decision keys.
3. For each canonical field choose the exact source header. Do not infer
   missing values, silently discard relevant columns or overwrite source party,
   entity, currency or units to agree with a desired result. Mapped perimeter
   cells must equal the reviewed source perimeter. This version retains the
   existing single reviewed perimeter per source; do not claim unrestricted
   multi-party/multi-entity intake.
4. Use the normal `raw_input_runner.py` entrypoint, with its actual started
   Archive context and `--output-subdirectory reconciliation`. It builds and
   replays current-byte source decisions/qualifications before parsing.
5. Review all emitted rows and source diagnostics. Any invalid mapped row
   rejects that source as a whole; no partly parsed source is promoted.
   Assurance freshly rederives every tabular prepared row, including evidence
   rows, from the exact source and reviewed layout. Changed or invented
   amounts, document identity, dates, evidence meaning, missing/added rows or
   perimeter values fail replay. Workpapers retain the usual review gates.

## Layout object

The source decision has exactly its normal fields plus `tabular`. That object
has exactly these fields:

```json
{
  "sheet": "Receivables",
  "header_row": 1,
  "first_data_row": 2,
  "last_data_row": 3,
  "delimiter": null,
  "columns": {
    "source_record_id": "Item ID",
    "document_no": "Invoice",
    "document_date": "Invoice date",
    "amount": "Amount",
    "balance": "Reported balance",
    "currency": "Currency",
    "party_ref": "Counterparty"
  },
  "evidence_type_map": {},
  "default_evidence_type": "open_item"
}
```

These labels and bounds are an example, not defaults. XLSX requires one exact
sheet and `delimiter=null`. CSV requires `sheet=null` and an explicit delimiter
from comma, semicolon, tab or vertical bar. Header names are exact strings;
missing/duplicate mapped headers and reuse of one column for two canonical
fields are rejected. Bounds are explicit positive worksheet/physical CSV row
numbers, with `header_row < first_data_row <= last_data_row`.

Supported columns are `source_record_id`, `document_no`, `document_date`,
`posting_date`, `value_date`, `due_date`, `amount`, `balance`, `description`,
`entity_ref`, `party_ref`, `currency`, `unit`, `evidence_type` and
`support_document_no`. Open items require document number/date and amount;
evidence sources require posting date and amount. Each nonblank source row must
have a source or document identity. A mapped critical date cannot be invalid;
an amount or mapped balance cannot be blank, invalid or more precise than a
cent. No exchange rate or amount rounding is inferred.

Open-item sources use explicit `default_evidence_type="open_item"`; bank
sources use `"external_bank"`. Journal sources require an explicit reviewed
choice among `internal_accounting`, `internal_closure`, `compensation` and
`factoring_bridge`. A homogeneous journal may declare one default. Otherwise
map its evidence-type column, set the default to null, and provide a complete
`evidence_type_map`, for example:

```json
{
  "evidence_type_map": {
    "Documented credit note": "compensation",
    "Internal annotation": "internal_accounting"
  },
  "default_evidence_type": null
}
```

That mapping is the reviewer's accounting judgment. The parser only applies
the exact selected values and rejects unmapped values; a description containing
“paid” does not become external banking proof.

## Exact reading and boundaries

CSV text amounts follow the reviewed decimal/thousands convention and UTF-8
encoding, optionally with a BOM. Native numeric XLSX amounts are read from the
source XML number, independent of display format or Python binary floats.
Mapped formulas and spreadsheet error cells are unsupported; do not use cached
formula results as authority. Native Excel dates and reviewed day/month text
dates are accepted. XLSM/XLS/ODS and ambiguous mapped headers are not admitted. The adapter
reads explicit flat cells; it does not reconstruct merged/pivot layouts or infer
their row-level accounting meaning.

The adapter is bounded to 100,000 selected row numbers, 256 source columns and
1,000,000 table cells; CSV also bounds its read population. Workbook expanded
XML is bounded to 50 MB. Monetary XML numbers have at most 28 significant
digits and exponent magnitude 28. Exceeding a bound fails explicitly rather
than truncating source records.

All source originals, receipts, table selections and reviewed meanings remain
available for replay. Preparation, numeric locators and final assurance use
the same reader. The source, preparation, reconciliation, semantic review,
reporting and publication gates retain their distinct meanings.

Worksheet dimensions are optional cached metadata. The reader derives bounded physical row and column extents from actual XML cells and ignores missing or stale dimensions; source bytes and reviewed row/header selectors remain authoritative.

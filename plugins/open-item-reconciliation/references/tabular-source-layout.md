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
   For CSV, Archive's normal read returns `data.source_format.delimiter`, the
   separator actually used for the displayed columns and rows. Retain that value
   in the reviewed layout instead of assuming a comma from the `.csv` extension.
   `delimiter_basis=sniffed` identifies the reader's sample-based detection;
   `default` means detection was inconclusive and the reader used its fallback.
   Check the physical source when the preview or fallback leaves the layout
   uncertain. This is an agent technical check, not a human approval step.
2. Record the existing source decision fields: role, adapter, reviewer/date,
   accounting perimeter, cent-only money convention and date order. Add the
   `tabular` object below. Key each decision by its complete path relative to
   the context's `input_dir` (including `imports/<input_id>/`) or by that exact
   current file's absolute path. Both identify the same byte-bound source.
   A basename alone is insufficient for nested imports. Do not reuse another
   run's absolute paths or supply conflicting reviews under both path forms.
3. For each canonical field choose the exact source header. Do not infer
   missing values, silently discard relevant columns or overwrite source party,
   entity, currency or units to agree with a desired result. For a source with
   multiple counterparties, map `columns.party_ref` to the exact counterparty
   header and set `perimeter.party_ref=null`: each nonblank source party cell
   then supplies that row's identity. Do not split an ordinary export per party
   or substitute a common fictitious party. A non-null `perimeter.party_ref`
   still declares one common party and any mapped party cells must equal it.
   Entity, currency and units remain source-wide; their mapped cells must equal
   the reviewed perimeter. Blank mapped party cells reject the source rather
   than becoming a shared unknown identity. Deterministic matching requires
   exact cross-source party values. For unresolved items, the semantic worker
   may establish that different names identify the same customer, citing both
   complete source names and settlement evidence. Preserve both original
   names; do not rewrite source mappings to make them equal. Conflicting
   explicit party IDs, entities, currencies, units and payment directions
   remain incompatible.
4. Use the normal `raw_input_runner.py` entrypoint, with its actual started
   Archive context and `--output-subdirectory reconciliation`. It builds and
   replays current-byte source decisions/qualifications before parsing.
   Save agent-generated `--assumptions-json` inside that run's output directory;
   a configuration file in the chat workspace is outside the selected run.
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

A bank export may identify the invoice without repeating its issue date. The
reconciliation joins that exact reviewed invoice number to a single source
invoice with the same counterparty, entity, currency and unit. Repeated numbers
within that perimeter remain unresolved, including repetitions across years;
the payment amount does not choose the year. Source dates and references stay
unchanged. Undelimited trailing digits such as `F001` never supply an invoice
year. An explicit number/year reference retains its stated year.

When the request includes settlements after the opening-population cutoff, set
`post_cutoff_events_excluded=false` in the reviewed assumptions and retain the
original cutoff. This applies to partial as well as full bank payments; the
unpaid residual remains open. Inspect the supplied evidence period rather than
changing the population cutoff to force a match.

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

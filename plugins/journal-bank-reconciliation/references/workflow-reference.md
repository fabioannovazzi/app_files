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
- `currency`
- `unit`
- `entity_ref`
- `party_ref`
- `direction`
- `source_file`
- `source_sheet`
- `source_row`

`amount_signed`, `amount_abs`, `bank_amount`, `journal_amount`, and
`amount_delta` are canonical non-exponent Decimal text. Binary floats are not
used for reconciliation comparisons.

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

Relationship-residual outputs use `side`, `record_ref`, `transaction_id`,
`record_amount`, `allocated_amount`, `residual`, `currency`, `unit`,
`entity_ref`, and `party_ref`. These are an exact projection of the allocation
ledger; they do not classify, allocate, or force residuals to zero.

## Header and Mapping Authority

Automatic qualification is deliberately narrow: exactly one row in the first
30 rows must contain an unambiguous set of exact, supported headers for date
and either signed amount or debit/credit. A value-profiled date, fuzzy label,
or numeric column position may be proposed in `suggested_recipe.json`, but it
has no qualification authority and emits zero movements.

For CSVs, `csv_field_delimiter` is transport syntax and is distinct from
`decimal_separator` and `thousands_separator`. The bounded profile tests only
comma, semicolon, tab, and pipe over at most 128 KiB and 100 non-empty records.
A candidate is unique only when exactly one strict parse produces at least two
constant-width records with more than one field. Only the uniquely profiled
comma default may participate in the exact automatic contract. A non-default
delimiter or an explicit delimiter that does not uniquely match the profile
requires a current reviewed mapping receipt. Ambiguous delimiters return
`needs_review`; unsupported delimiters return `unsupported_source_layout`.
Both emit zero rows.

LF, CRLF, and CR record terminators are mechanically normalized to LF through
a chunked private transport copy before the full parse. A record terminator is
not a mapping field and is distinct from both field and numeric separators.
The full CSV parse is strict: errors are not ignored and ragged rows are not
truncated, including malformed rows beyond the bounded profile.

When the exact contract does not apply, Codex must review the physical header
row, mapping, CSV field delimiter, and numeric separator convention. It then uses
`build_mapping_review_receipt` to seal that content against the current
content-addressed source artifact reference and adapter version. Hand-editing
the mapping without a valid receipt does not qualify it. A changed source,
mapping, header row, separator convention, or adapter makes the receipt stale.

The v6 mapping receipt also binds `date_convention`. Native date/datetime
cells, valid compact `YYYYMMDD`, valid year-first text, and integral
spreadsheet serial dates in the bounded Excel range are mechanical.
Day/month text is evaluated under both supported interpretations. If both are
valid, the source emits zero rows until the reviewer seals exactly
`day_first` or `month_first`; parser-list order has no authority. A populated
invalid date fails the complete source even if the row has a stable reference.
Only a truly blank date with a stable reference can be emitted as
`emitted_reference_only`.

The additive v7 mapping contract supports full Italian textual-month dates
only after the reviewer seals `date_locale: it` against the current source.
It accepts the exact full-month vocabulary and valid Gregorian dates; unknown,
abbreviated, mixed-language, embedded, or invalid forms fail closed. A v7
mapping receipt may also bind `non_movement_summary_labels`. An exact reviewed
label excludes a monetary row only when its mapped date is blank and its
explicit reference and movement-number fields contain no stable token. Labels
never override an actual date or stable reference.

Every reviewed path must declare `potential_monetary_columns` exactly as
derived from the current parsed source and must provide
`excluded_monetary_columns`, even when it is empty. Each potential monetary
column must be mapped to `amount`, `debit`, or `credit`, or explicitly
excluded. Incomplete, extra, or stale dispositions have no review authority
and emit zero rows.

## Mapping Fields

Use `amount` when the file has a single signed amount column. Use `debit` and `credit` when the file splits debit and credit. The script calculates signed amount as debit minus credit.

Reference fields can contain document numbers, CRO/TRN, invoice references,
IBAN fragments, or other stable identifiers. Only explicit `reference` and
`movement_number` fields participate in the reference stage. Descriptions and
beneficiary names remain review context. Generic words such as `invoice`,
`payment`, `document`, or `transfer` are not stable identifiers; reference
tokens must contain a non-generic identifier with digits.

`currency`, `unit`, `entity_ref`, `party_ref`, and `direction` define the
relationship perimeter. Missing required values may be supplied only through a
reviewed policy default.

An explicit direction column may contain canonical `positive`, `negative`, and
`zero` values directly. Other categorical values require a reviewed,
source-bound `direction_value_mapping` that exactly covers the observed
non-canonical vocabulary. The mapping translates each source label to one
canonical direction and is sealed in the mapping receipt. No universal
debit/credit polarity is assumed. A missing label mapping, an extra unobserved
label, or disagreement between the mapped direction and exact signed amount
withholds the complete source.

## Reviewed Relationship Policy

Every run requires a `journal_bank_relationship` reviewed decision receipt,
sealed with `build_relationship_review_receipt` against the current bank and
journal source artifact references. The supported relationship shape is
`one_to_one`, evidence reuse is disabled, and currency and unit equality are
mandatory. The policy also records:

- whether entity and party must agree;
- `absolute_amount`, `same_sign`, or `opposite_sign` direction treatment;
- any currency, unit, entity, or party defaults;
- exact amount tolerance;
- date window in calendar days.

Execution arguments must equal the reviewed tolerance and date window.
Relationship tolerance accepts canonical decimal text, `Decimal`, or integer
values and is persisted as canonical Decimal text. Floats, booleans,
localized/noncanonical text, non-finite values, and negative values are
rejected rather than guessed.
The relationship adapter is `journal_bank.relationship.v2`, version `2`.
Version 2 seals the batch-safe, order-independent singleton allocation
semantics below. Receipts from relationship adapter v1 are stale and must be
reviewed again.

## Matching Stages

Each wave is computed from a snapshot of all currently unmatched rows. Only
bank rows with exactly one eligible candidate whose target journal row is not
also the singleton target of another bank row enter the batch. The complete
batch is accepted together; source row order never breaks target collisions.

1. `reference`: conflict-free singleton candidates with an explicit shared
   reference or movement token and amount inside the exact tolerance. Date
   evidence is optional for this explicit-identifier stage. Conflict-free
   reference waves repeat until no further safe reference singleton remains.
2. `amount_date_unique`: the first conflict-free singleton amount/date batch
   after reference matching is exhausted. Both rows require actual dates inside
   the configured date window.
3. `amount_date_single`: later conflict-free singleton waves containing only
   candidates that became singleton after an earlier amount/date batch removed
   other candidates. Later waves repeat until no safe singleton remains.

Rows are not reused. Ambiguity stays unmatched.
Multiple singleton bank rows targeting the same journal row remain ambiguous;
none receives a row-order preference.
Candidates outside the reviewed currency, unit, entity, party, or direction
perimeter are never matched.

## Source Qualification

- Tabular files emit rows only after date and amount or debit/credit fields are
  mapped and every populated mapped monetary cell parses exactly.
- CSV field delimiter and date authority follow the bounded v6 contract above.
  Non-default choices, profile mismatches, and full potential-monetary-column
  dispositions are sealed in `journal_bank.tabular.v6` mapping receipts;
  receipts from adapter v5 and earlier are stale.
- Italian textual-month dates and exact reviewed blank-date summary labels use
  the additive `journal_bank.tabular.v7` receipt. Adapter selection is explicit;
  existing numeric-date v6 sources are not silently upgraded.
- The strict full-file CSV parse follows bounded delimiter profiling. A
  malformed or ragged record anywhere in the population is a parser failure
  and emits zero rows; LF, CRLF, and CR differ only as transport syntax.
- Dates accept the mechanical forms described above. Ambiguous day/month
  values require reviewed source-bound authority; invalid populated values
  fail the source and emit zero rows.
- Non-canonical direction labels emit rows only after complete reviewed
  source-value mapping.
- Every monetary candidate receives a row disposition. An invalid monetary
  value or a missing date without an explicit reference blocks the source and
  emits zero rows. A missing date with a stable explicit identifier is emitted
  as `emitted_reference_only` and can participate only in the reference stage.
  A blank-date/no-reference row may instead be
  `excluded_reviewed_summary` only through an exact receipt-bound v7 summary
  label.
- Ambiguous separator syntax such as `1.000` is rejected unless the recipe
  explicitly declares the separator convention.
- Generic text-PDF movement extraction emits zero rows with
  `unsupported_source_layout`. Narrow balance, total, scalare, and conditions
  classifications may still be retained as non-movement review evidence.
- A future PDF adapter must be source-family-specific and tested; a free-form
  recipe label does not qualify an adapter.
- A supplied sample must contain movement identifiers and select journal rows.
  Empty, invalid, or nonmatching samples block instead of falling back to the
  full journal.
- Parser failure is reported separately from a readable but unsupported layout;
  available receipts, qualifications, gates, lineage, diagnostics, and audit
  are still written before the run returns a block.

## Assurance Artifacts

Inspection and reconciliation bind source bytes to content-addressed
`input_receipts.json` records and `source_qualifications.json`. Reviewed mapping
and relationship decisions are collected in `reviewed_decisions.json`.
`lineage.json` points every emitted transaction to the physical workbook sheet
and row (or physical CSV row). `relationship_ledger.json` records the exact
one-to-one allocations and residuals. `relationship_residuals.csv` projects
the record, allocated, and residual components for every bank and journal row.
`material_value_ledger.json` freshly replays matching and the relationship
ledger, then binds every declared match and residual field to the exact
prepared row, CSV row/column, and XLSX cell. A blocked run still writes the
complete reviewable native package, including an empty
`relationship_residuals.csv` and an explicit blocked relationship ledger.
Only `material_value_ledger.json` is absent when source qualification or
relationship authority blocks, because material reconciliation never ran.

The execution boundary closes an exact 23-file contract covering launcher
configuration, UI assets, Python/Node code, and the shared assurance kernel.
Supported Python entries validate the physical tree before local imports; MCP
does so before manifest parsing and invokes Python with `-I -B`. Unowned
bytecode caches and other physical entries therefore fail before execution.
Those receipts establish consistency, not package-publisher or reviewer
authentication.

The assurance gates are independent:

- source qualification;
- preparation and sample perimeter;
- exact reconciliation closure;
- professional semantic review;
- reporting integrity;
- publication, which remains outside this component.

Unmatched rows or residuals set reconciliation to `withheld`, even if a reviewer
accepts every review item. Reporting becomes passed only after source,
preparation, reconciliation, and semantic review are passed and artifact
receipts validate. Authorized review edits are resealed; an unexpected changed
output keeps its old failing receipt and blocks readiness.

Blocked runs still write the available receipts, qualifications, lineage,
gates, audit, and narrow PDF non-movement evidence before returning an error.

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

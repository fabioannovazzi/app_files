> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Journal Sampling Workflow Reference

## Deterministic Boundary

The helper scripts perform deterministic work: file inspection, parser selection, column mapping suggestions, row normalization, filtering, sample selection, and audit metadata. Claude can inspect outputs, update the recipe in the work folder, and explain assumptions, but it should not rewrite extracted rows or sampled rows as if they came from deterministic evidence.

## Mapping Fields

- `date`: journal entry date.
- `movement_number`: movement, registration, or document number when available.
- `line_number`: source-owned posting-line number when available.
- `account`: account code or account identifier.
- `account_desc`: account description.
- `line_desc`: entry description or causale.
- `debit` and `credit`: separate amount columns.
- `amount`: signed amount column when debit/credit are not separate.
- `posting_identity`: source-owned fields that define the posting grain.
- `carry_forward_fields`: reviewed fields that may inherit a preceding value;
  print layouts can bind date, movement number, and line description.
- `excluded_monetary_columns`: explicitly reviewed non-posting numeric or
  monetary-labelled fields.
- `currency` and `unit`: monetary context for every emitted row.

## Supported Parsers

- reviewed tabular Excel/CSV journals with explicit header and field mappings;
- reviewed print-friendly Excel exports using the bounded debit/credit-column
  adapter.

Generic text PDFs and OCR-only scanned PDFs abstain with
`unsupported_source_layout`; trailing-number position is not evidence of amount
side. A repeatable PDF family needs its own explicit, tested adapter before rows
may enter a population.

Multi-worksheet workbooks currently abstain as a whole. The adapter must account
for every worksheet before the workbook can qualify.

Unreadable or corrupt containers also emit no rows. Their qualification remains
fail-closed, while `failure_class=parser_failure` and `parser_error` distinguish
an execution failure from an otherwise readable but unsupported layout.

For Excel sources, canonical rows retain the exact worksheet name and physical
workbook row. Canonical values retain exact Decimal text, explicit currency and
unit, and the source-reported monetary increment. Account-only metadata rows are
excluded from the monetary candidate population and counted separately.
Additional monetary-labelled or numeric fields must be mapped or explicitly
excluded in the reviewed contract. Native XLSX numeric cells retain a fixed
display scale such as `0.00` when it is consistent with the stored value.
Normalization parses captured source bytes and reconciles them to the source
receipt; changing or swapping the source during or after normalization cannot
change the prepared values.

A complete normalization also copies the exact reviewed recipe bytes to
`normalization_recipe.json`, receipts the retained copy and original recipe
source, and binds the retained receipt into the normalization envelope.
`replay_normalization.py` starts through the same pre-import implementation
boundary, reruns the raw input with that retained recipe, and requires exact
reproduction of the canonical CSV, material diagnostics projection, reviewed
decisions, gates, envelope, and qualification-review payload. Sampling invokes
this replay before using the population. A locally resealed but stale prepared
CSV therefore cannot substitute for re-performance.

## Sampling Methods

- `random`: deterministic seed 42.
- `systematic`: interval-based population traversal.
- `stratified`: deterministic group allocation by account or another mapped column.
- `mus`: deterministic cumulative monetary-unit thresholds.

## Sample-Stage Assurance And Closure

`run_sample.py` accepts only an absent or empty output folder. It writes the
entire sample in a private sibling staging directory and promotes that directory
only after final replay succeeds. A failed upstream replay, sample selection,
required XLSX write, native-value comparison, assurance-envelope replay, or
physical output-set check leaves no success-shaped sample package at the target.

The stage writes:

- `sample_reproducibility.json`: a run-independent recipe/result surface bound
  to normalized CSV bytes, implementation bytes, canonical filters, selected
  prepared row numbers, canonical sampled rows, and sample CSV bytes;
- `sample_material_value_ledger.json`: one address record for every canonical
  field in every sampled row, including the normalized prepared CSV row, sample
  CSV row, native XLSX cell, exact value kind and text, currency, unit, and
  positive canonical reported increment;
- `sample_assurance_gates.json` and `sample_assurance_envelope.json`: current
  source, normalized preparation, implementation, CSV, XLSX, reproducibility,
  material-ledger, audit, and gate receipts;
- `sample_output_receipts.json`: the exact physical file and directory
  allowlists, file/directory/root modes, stage/predecessor binding, and current
  byte count and SHA-256 receipt for every payload file.

The output-set manifest is the fixed bootstrap member of its own physical set;
it seals its own canonical content digest and receipts every other member,
avoiding an impossible self-hash. Its boundary is
`sample_stage_finalization_pre_review` at stage zero. A real MCP save or apply
first replays that stage, archives only its exact operational members beneath
`assurance_history/<index>_<kind>`, freshly rederives the post-review material
state, reseals a `save` or `apply` successor, and replays the full chain before
the transaction commits. The chain rejects missing or rogue files, empty or
nested rogue directories, symlinks, hard links, special files, mode changes,
stale predecessor bindings, and changed archived bytes.

Sample source and preparation gates pass only after all mechanical closure
checks pass. Semantic review stays `not_assessed`, reporting stays `blocked`,
publication stays `withheld`, and `report_ready` remains false. A fully accepted
apply successor is `review_applied_with_assurance_limits`, never `final_ready`.
Fixed rules govern only mechanically verifiable bytes, addresses, schema,
arithmetic, and membership; they do not infer audit sufficiency, materiality,
or conclusions.

## Review Policy

The final response should report source-qualification status, withheld or
rejected rows, monetary-field dispositions, filters, population size, sample
size, and output paths. The mapping review must be a validated
`vera.reviewed_decision_receipt.v1` bound to the exact source, adapter, version,
and mapping contract. If Claude adjusted the recipe or asked the user a mapping
question, include that reviewed assumption explicitly.

Normalization emits `reviewed_decisions.json`, `assurance_gates.json`, and a
replayable `assurance_envelope.json`. Sampling validates these artifacts,
source and prepared receipts, and implementation receipts before selecting
rows, and repeats the replay at finalization. The sample envelope records source
and preparation as passed only for a closed sample package while semantic
review remains `not_assessed`, reporting remains `blocked`, and publication
remains `withheld`. The implementation receipt set is exact and ordered across
the plugin CLIs/core, review successor, MCP server, widget/adapter/discovery
configuration, and every imported shared Vera assurance Python/CJS module.
The exact current set contains 16 plugin files plus 8 shared assurance files;
the replay CLI and implementation bootstrap are inside that set. Physical tree
closure rejects unowned caches, files, directories, links, and special entries
before public Python or MCP paths import local implementation code. Receipts
and self-hashes establish internal consistency only; reviewer authority and
package authenticity remain external trust requirements.

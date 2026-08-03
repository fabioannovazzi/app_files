# Journal-Bank Reconciliation Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/journal-bank-reconciliation) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Guided Codex workflow for bounded, reviewable reconciliation between bank
statements and journal or ledger exports.

The plugin is multilingual (`it`, `en`, `fr`, `de`, `es`). Codex handles
mapping and review judgment; helper scripts own mechanically verifiable source
qualification, exact-decimal normalization, explicit-reference and
amount/date matching, receipts, lineage, and exports without direct model API
calls.

Only one unambiguous, exact supported header contract qualifies automatically.
Profiled dates, numeric positions, and fuzzy labels remain proposals and emit
zero rows until a reviewer seals the chosen mapping against the content-addressed
source receipt. Every run also requires a reviewed one-to-one relationship
policy covering evidence reuse, currency, unit, entity/party perimeter,
direction, amount tolerance, date window, and any defaults.
Non-canonical source direction labels require a complete, source-bound value
mapping to `positive`, `negative`, or `zero`; the plugin does not assume a
universal debit/credit polarity.

CSV transport and the base date contract use adapter
`journal_bank.tabular.v6`.
The field delimiter is a
separate reviewed input from decimal and thousands separators. A bounded,
strict profile considers only comma, semicolon, tab, and pipe. Only a uniquely
profiled comma source with the exact header contract can qualify without a
mapping receipt; a non-default delimiter or an explicit/profile mismatch needs
a current v6 receipt. Ambiguous or unsupported delimiters emit zero rows.
LF, CRLF, and CR record terminators are normalized mechanically in a streamed
private copy before a strict full-file parse; malformed or ragged records fail
as parser errors rather than yielding a partial population.

Native date/datetime cells, valid compact `YYYYMMDD`, valid year-first text,
and integral spreadsheet serial dates are mechanical. Ambiguous day/month
text emits zero rows until `day_first` or `month_first` is sealed in the
source-bound v6 mapping receipt. An invalid populated date fails the complete
source even when the row has a stable reference; only a truly blank date with
a stable explicit identifier may enter reference-only matching.

Adapter `journal_bank.tabular.v7` is an explicit additive extension. A
source-bound `date_locale: it` mapping receipt admits only full Italian
textual-month dates under the frozen vocabulary and Gregorian calendar rules.
Without that receipt, textual-month dates emit zero rows and require review;
unknown, abbreviated, embedded, or invalid dates fail the complete source.
The same v7 receipt may bind a sorted exact
`non_movement_summary_labels` list. A reviewed label excludes a row only when
its mapped date is truly blank and it has no stable reference; an actual date,
stable reference, substring, or fuzzy similarity prevents exclusion.

Every reviewed mapping also binds the current complete list of potential
monetary columns and an explicit excluded list, including an empty list. Each
potential column must be mapped to amount/debit/credit or explicitly excluded;
an incomplete or stale disposition emits zero rows.

Relationship receipts use `journal_bank.relationship.v2`. Matching evaluates
conflict-free singleton batches rather than choosing row-by-row: reference
waves run first, `amount_date_unique` labels the first amount/date singleton
batch, and `amount_date_single` labels only later singleton waves created by
earlier amount/date allocations. Competing singleton bank rows targeting the
same journal row remain ambiguous regardless of source order.

Generic text-PDF movement extraction is deliberately disabled. PDF inspection
can still retain narrowly classified balance, total, scalare, and conditions
lines for review, but reconciliation remains blocked with
`unsupported_source_layout` until a tested source-family adapter exists. A
supplied sample that is empty, invalid, or selects no journal movements also
blocks the run instead of silently falling back to the full journal.

Every completed or blocked run adds `input_receipts.json`,
`source_qualifications.json`,
`reviewed_decisions.json`, `lineage.json`, `relationship_ledger.json`,
`relationship_residuals.csv`,
`assurance_gates.json`, and `artifact_receipts.json` to the existing review
package. Qualified runs with current relationship authority also add
`material_value_ledger.json`; blocked runs deliberately omit it. Monetary
values and tolerance differences are stored as canonical Decimal text. The
material-value ledger freshly replays matching and residual
preparation and binds every declared match and residual value to its exact CSV
row/column and XLSX cell. Lineage uses the physical sheet and row from the
source, even across preambles and blank rows.

Reconciliation is passed only when the one-to-one ledger is exactly closed and
no bank or journal rows remain unmatched. Reviewer acceptance cannot override a
withheld reconciliation gate. Authorized review edits regenerate native output
when needed and reseal artifact receipts; unexpected output changes block final
readiness. Generated reconciliation workbooks normalize only mechanical OOXML
timestamps and ZIP ordering so identical inputs produce byte-identical XLSX
receipts; duplicate package member names are rejected.

Before importing local workflow code, every public Python command validates an
exact 24-file implementation/configuration/UI/shared-assurance tree and
disables local bytecode. The MCP server closes the same physical tree before
reading the manifest and launches Python with isolated imports and bytecode
disabled. Unowned files, directories, caches, links, or special files block
execution. The resulting hashes prove replay consistency; they do not
authenticate the package publisher or a professional reviewer.

The row-free machine-readable repository contract is
`../../docs/specs/vera_audit_assurance/journal-bank-evaluation-contract.v5.json`.
It binds adapter IDs, schemas, stage semantics, native outputs, workbook
closure, gates, threats, and cross-run equality scope without oracle rows or
hidden expected matches. The v2, v3, and v4 contracts remain immutable
historical evaluation evidence and are not the current prospective contract.
The additive v7 rules are separately frozen in
`../../docs/specs/vera_audit_assurance/journal-bank-tabular-v7-extension-contract.v1.json`;
they do not rewrite or promote v5.

## Internal Scripts

- `scripts/check_dependencies.py`
- `scripts/inspect_inputs.py`
- `scripts/run_reconciliation.py`
- `scripts/semantic_review.py`
- `scripts/journal_bank_core.py`

Users should invoke the plugin from Codex rather than running the scripts directly.

The optional Codex-only residual review keeps the main reconciliation chat on
its existing model. After deterministic qualification and matching, Codex may
use `semantic_review.py prepare` and the pinned `run-worker` launcher to send
one bounded unresolved candidate packet to a separate Luna Max process. The
launcher is qualified only on its pinned macOS/Codex/Seatbelt environment,
fails closed when those pins or its filesystem canaries do not match, and
records a content-bound launch receipt. The bounded packet is transmitted to
the OpenAI Codex service. Validated results remain advisory in a sibling
directory and cannot change canonical matches, ledgers, receipts, gates,
review decisions, or report readiness.

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

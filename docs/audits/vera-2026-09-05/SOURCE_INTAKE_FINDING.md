# Open Item source-intake acceptance finding

## Current correction — 5 September 2026

Nested source enumeration is implemented. Inventory, reviewed adapter selection,
PDF page/cache identity, journal/payment records, qualifications and receipt
lookup use the full relative path. A basename-only decision cannot authorize
multiple imported files. Linked and non-regular source entries reject before
read. Existing flat input behavior is retained.

Source-value replay now checks the exact three-line document/date/amount span
for the declared open-item PDF adapter, while locating the amount on its exact
line. A full invoice-series reference no longer emits an additional bare-number
bank row. Missing-evidence section totals are rederived from the actual shared
section classification, and report identity lookup recognizes exact semicolon-
separated document keys. No material-value control was bypassed.

The fresh uninstrumented run at
`/private/tmp/vera-remediation-01a07083/source-acceptance-a01-final/result.json`
retains actual Studio Archive imports, source receipts, normalized rows,
allocation ledger and final Word/Excel artifacts. It reports original 1220,
allocated 488.00 and residual 732.00. `checks_pass` remains false solely because
`codex_review_completed` is pending; do not describe this as full professional
acceptance. The earlier diagnostic runs below remain historical failures.

Module suite: 263 passes (`nested-source-suite.xml`). The added real-PDF test
also passes with the two nested inventory tests, proving that identical
basenames in distinct import folders retain separate rows and receipts.

## Historical observation — 5 September 2026

A01 was exercised through actual Studio Archive client creation, engagement,
document import, run preparation/start and `run_raw_input_reconciliation`.
Two real text PDFs were generated from the approved synthetic case: an open
item of EUR 1220.00 and a bank payment of EUR 488.00. Adapter-compatible invoice
identifiers were used (`26FE01/000001` and `1-FE`), representing the original
`INV-1`; these PDFs are a synthetic derivative, not the original CSV bytes.
The code-generated mapping declaration records the user-approved expected
case and an unsigned reviewer label; the user did not independently inspect
this PDF layout or mapping. No independent source-mapping review is claimed.

Evidence is retained in
`/private/tmp/vera-remediation-01a07083/source-acceptance-a01/`.
`run_source_acceptance.py` and `diagnose_source_acceptance.py` in the parent
folder record the actual calls and diagnostic-only observation wrapper.
No parser output, control result or final acceptance was mocked into success.

The first failure was a DOCX material-figure rejection. The Word assumption
section dumped `reviewed_source_decisions` JSON into prose, including the
`reported_increment: 0.01` convention. Excel also dumped the same control
object into a value cell. The report builder now leaves these technical
control receipts in canonical audit JSON rather than rendering them as
financial claims. Professional scalar assumptions remain visible. The
material-value validator has not been bypassed.

The next failure is `source_root is not allowed without source receipts`.
Studio Archive stages sources under `inputs/imports/<input_id>/<filename>`.
Both `source_inventory` and `extract_normalized_records` currently enumerate
only `root.iterdir()` regular files, so this valid prepared layout yields zero
source receipts and zero parsed rows. This is a real integration defect;
normalized-input tests and successful standalone PDF parsing do not cover it.
The finalization failure prevents a successful run claim.

## Required correction

Support the authorized nested input tree without flattening or altering
Studio Archive's staged sources. Preserve relative source paths consistently
through decisions, adapter lookup, inventory, page caches, parsed record IDs,
qualification, source locators and final receipt replay. Distinct imports may
share a basename; basename aliases must never silently merge or select them.
Reject linked or special source entries before reading. Preserve exact
source-set and changed-byte checks. Then rerun A01 from the prepared context,
inspect the 488/732 result, complete its normal review, and extend the cases.

The nested-source defect is corrected as described above. T15 remains incomplete pending final review and the other approved source cases.

## A04 grouped-payment source case — 6 September 2026

The real bank PDF lists two invoice references on one physical line. The old
parser emitted two independent bank records, each with the whole EUR 1830.00.
The parser now emits one movement with an explicit set of document keys, so
allocation controls enforce one EUR 1830.00 source capacity.

The approved A04 expectation is exercised with explicit engagement assumptions
`promote_probable_bank_payments: true` and
`probable_bank_exact_matches_close: true`, and a reviewed `one_to_many` perimeter.
Those declarations are retained in the mapping artifact. The default remains
advisory; exact closure is not enabled globally by this change.

The source run produces two closed items (EUR 1220 and EUR 610), one bank source,
one balanced allocation ledger, and allocations of 1220 and 610. The only
outstanding check is `codex_review_completed`. This proves the source/extraction/
mechanical-output path, not completed professional review.

Follow-up report fixes retain the bank amount as the matched evidence amount
rather than summing bank amount, group total and difference in one cell. The
operational per-invoice difference now compares the bank amount with that
invoice, while the candidate schedule retains the group difference separately.
Both advisory and explicitly approved exact-closure workflow regressions pass.
The latest uninstrumented output is retained at
`/private/tmp/vera-remediation-01a07083/source-acceptance-a04-current/result.json`.

## A05 subsequent payment source case — 6 September 2026

The fresh Studio Archive/PDF run in
`/private/tmp/vera-remediation-01a07083/source-acceptance-a05-final/result.json`
retains an unresolved EUR 1000 invoice at 30 September and one separately
reported payment dated 2 October. It has no allocation at the cutoff. All
mechanical checks pass; the remaining check is `codex_review_completed`.

The operational workbook previously inferred "non pagata: NO" merely from
having an evidence detail, even for an unresolved invoice. It now derives this
presentation from the reconciliation outcome: only a closed row is shown as
settled; a partial row displays its outstanding residual; other rows state that
closure at the cutoff is not demonstrated. This does not assert that payment
never occurred. Its actual evidence date remains visible.

The rendered per-row difference is replayed from the explicitly referenced
invoice and evidence amounts with equal currency/unit/entity/party. This
arithmetic check does not grant matching or cutoff authority. The focused
accountant-report/public-workflow suite passes all 15 tests
(`cutoff-report-tests.xml`). The original fake-flat-input regression was
corrected to supply the same explicit open-item source role/type used by the
real raw pipeline; no production parser was altered to accommodate that fixture.

## A06 currency and A07 review-to-final acceptance — 6 September 2026

The actual A06 Studio Archive/PDF run preserves the EUR 100 invoice and USD 100
bank movement as different currencies. It emits no allocation and retains the
expected failing relationship control; it does not invent an exchange rate.
Evidence: `/private/tmp/vera-remediation-01a07083/source-acceptance-a06/result.json`.

The A07 managed source case now completes the local review and successor
regeneration path. The first real application exposed a missing customer-context
lookup for predecessor snapshots. The corrected lookup applies only to an
externally anchored snapshot below the same managed run, reloads the live
Studio Archive context, and exact-compares its portable identity. Missing
context remains a rejection; a snapshot does not create new run authority.

Fresh evidence is retained under
`/private/tmp/vera-remediation-01a07083/source-acceptance-a07-reviewed-v2/`:
`codex-review-request.json`, `codex-review-response.json`,
`retained-predecessor-checkpoint.json`, and `successor-result.json`.
All seven review decisions were persisted through the public local API. As
expected, saving decisions alone stayed blocked pending regeneration. The
normal raw runner then regenerated the reports using the recorded review rows
and externally retained predecessor checkpoint. All checks pass, both EUR 100
invoices remain unresolved, the allocation ledger is empty, and final artifacts
are `final_ready`. Source, preparation, reconciliation, semantic-review and
reporting gates pass; publication is withheld.

Reviewer `reviewer.codex_acceptance` identifies Codex's verification against the
user-approved synthetic case. It is not an independent professional credential,
user interaction with the review UI, or native visual acceptance. The generated
PDF mapping is an engineering fixture. This evidence closes the local A07
synthetic review-to-final path, not the whole professional acceptance matrix.

The isolated CLI replay (`isolated-successor-replay.json`) rejects both missing
and wrong predecessor checkpoints and accepts the matching external checkpoint.
The complete Open Item suite passes 271 tests with no failures or skips
(`managed-successor-suite.xml`, 64.772 seconds). Two new managed-run regressions
cover successful successor replay and rejection when the live customer context
is missing. Vera Codex and Cowork packages were rebuilt; both drift checks pass,
and all 18 packaged MCP servers initialize and list tools. Seven other privacy
records remain stale after concurrent work; no complete-register pass is claimed.

## A03 duplicate source intake — 6 September 2026

Actual content-addressed Studio Archive import recognizes the second
byte-identical PDF as `already_imported` and returns the same input ID. Selecting
that same ID twice is rejected (`Workflow input selections contain duplicates.`),
so the corrected acceptance driver selects each imported ID once. The normal
raw runner emits exactly one EUR 1220 unresolved invoice, not EUR 2440.
Evidence: `/private/tmp/vera-remediation-01a07083/source-acceptance-a03-current/`
contains `result.json` and `import-observations.json`, with both original PDFs
preserved under `synthetic-source/`.

A03 is not fully closed: the workflow source inventory contains only the one
canonical imported name. The acceptance driver retains both original names and
the duplicate response, but that external observation file is not yet durable
pipeline/report lineage. The production intake needs to preserve the duplicate
occurrence and expose it to the report without creating a second accounting
obligation. Final review is also pending. Do not count driver-retained evidence
as a completed product fix.

## A03 duplicate lineage correction — 6 September 2026

The gap above is corrected. Studio Archive stores additional imported basenames
in a separate sealed `import_names.json` register bound to the canonical input
ID and byte digest. The immutable input receipt and canonical bytes are not
rewritten. A prepared run snapshots the sorted names in its sealed input
manifest; a later import cannot silently alter that prior run. Same-content,
same-role imports still select one input; different content receives a separate
input and is not treated as a duplicate from its amount or meaning. This is
filename provenance, not a reconstruction of every original folder location.

The shared v2 context validator accepts this bounded optional imported-name
metadata only for import bindings. The Open Item raw runner carries the
context-bound names to its source inventory. The normal Word report now shows
the canonical source and imported names for identical copies; the Excel source
inventory includes the same names, with localized Italian/Spanish labels.

Fresh real intake/review/successor evidence is under
`/private/tmp/vera-remediation-01a07083/source-acceptance-a03-lineage-final/`.
The filenames `A03-copy.pdf` and `A03-source.pdf` both appear in the generated Word
and Excel reports. The final result has one EUR 1220 unresolved invoice, all
checks passing and `final_ready`; no payment was inferred. The final assurance
SHA-256 is `3ad1e8fa5478ad1551b34cf8123cc29dc4224bcea305308584ea7594690a4a2e`.
`duplicate-report-verification.json` records the native document-content checks.
Codex performed the recorded review against the approved synthetic expectation;
this remains distinct from independent professional or native visual acceptance.

Regression evidence: 396 archive/reconciliation tests and 93 shared-assurance
core tests pass. New tests verify additional-name persistence, unchanged prior
runs and receipts, and separation of different-content documents. The final
localized header was subsequently verified in the fresh actual Word/Excel run.
The shared context change invalidates privacy fingerprints across its consuming
workstreams; Studio Archive and Open Item records were updated and refreshed.
The remaining records require reconciliation and are not reported as current.

## A02 reversal and unexplained payment correction — 6 September 2026

The grouped-format source run exposed an economic defect: the positive EUR 1220
invoice closed against the bank payment while its same-document -1220 entry
remained unresolved. The correction now withholds bank settlement when opposing
signed entries share a document and accounting perimeter at the cutoff. It
retains the signed records and bank payment, clears settlement allocation, and
asks for evidence of the reversal's validity and payment purpose. It does not
infer that an adjustment is valid or classify the payment as an advance/refund.
Different documents, different parties and subsequent reversals do not trigger
that guard. The rule uses exact identities and arithmetic, not a semantic
classifier for the meaning of reversals.

The reversal candidate table also omitted evidence record references. It now
retains both invoice and evidence references, preventing a same-number invoice
from standing in for the bank amount during report formula validation.

Fresh actual PDF intake, public review and successor regeneration evidence is
in `/private/tmp/vera-remediation-01a07083/source-acceptance-a02-final-v2/`.
`reversal-verification.json` confirms signed +1220/-1220, net zero, no bank
allocation, both entries `needs_evidence`, all checks passing and `final_ready`.
Codex accepted the appropriateness of the evidence requests; it did not mark
missing documents as received or certify the reversal as valid. Native visual
and independent professional acceptance remain separate.

All 276 Open Item tests pass (`reversal-suite.xml`), including five new positive
and negative guard cases. The first bank-text fixture with ungrouped `1220.00`
was unsupported by the current adapter; the qualified derivative uses
`1,220.00`. This case does not establish support for every numeric source format.
The intermediate review-driver attempts are retained: an unknown review item
kind was rejected before any decisions were applied. The final fresh driver
explicitly handles `missing_evidence_review` and completes the normal successor.

## A08 replacement evidence and review invalidation — 6 September 2026

A real initial EUR 100 invoice/payment run was reviewed through the local API
and regenerated successfully. Replacing the sealed execution-copy bytes with
the EUR 110 PDF is rejected as `run execution input no longer matches its
receipt`; the synthetic tamper test restores the exact original bytes afterward.
A legitimate new import preserves the original EUR 100 snapshot and creates a
new input receipt and run for EUR 110. The new accounting result leaves the
EUR 100 invoice unresolved, with a candidate payment EUR 110 and difference EUR
10 in the normal operating workbook, and no allocation.

The first reuse test found that copying prior PASS rows into this new managed
run incorrectly passed the semantic-review gate. Final UI review still remained
pending, so this was not an unauthorized `final_ready` result, but the passed
review gate was incorrect. Record IDs remain stable for the unchanged invoice
and therefore cannot alone authorize revised evidence.

Preparation, finalization and assurance replay now require completed review
rows in a managed run to match that run's persisted applied decisions. Existing
transition replay enforces the independently retained predecessor checkpoint.
Unbound prior PASS rows are rejected before prepared/final report records are
written. A fresh review of the new run remains supported and was verified.

Current evidence directories:
- `/private/tmp/vera-remediation-01a07083/source-acceptance-a08-bound-initial/`
  retains the initial source, review and final result.
- `/private/tmp/vera-remediation-01a07083/source-acceptance-a08-bound-changed/`
  retains tamper/reuse rejection, baseline inputs and reports, new review and
  successor, and `changed-source-verification.json`.

The newly reviewed successor is `final_ready`, with all checks passing and no
allocation. The EUR 10 remains unexplained. Isolated replay rejects missing and
wrong checkpoints and accepts the matching checkpoint. All 277 Open Item tests
pass (`source-review-binding-suite.xml`), including a regression rejecting copied
completed review rows before output records are created.

This validates approval invalidation and a fresh local review. The acceptance
evidence explicitly links old/new input IDs; both controlled snapshots and runs
are retained. A dedicated product-level replacement relationship in the normal
history has not yet been established by this test. Independent professional and
native visual acceptance remain separate. Direct review rows in standalone
developer fixtures are outside the managed customer-run authority boundary.

## A08 explicit replacement history — 6 September

The existing sealed run `purpose` now records the old run ID, old input ID, new
input ID and reason for re-review. The normal `list_runs` result retains this
purpose and both runs have valid exact input manifests. The workflow guidance
requires this information for an explicitly requested replacement and prohibits
inferring replacement relationships from filenames. No new relationship schema
was introduced.

A fresh linked-history run completed six Codex acceptance decisions and normal
successor regeneration with `checks_pass: true` and `final_ready`. Isolated CLI
replay rejected missing and wrong predecessor checkpoints and accepted the
retained correct checkpoint. This is technical acceptance of the unresolved
EUR 100 invoice / EUR 110 candidate payment, not an independent professional
judgment or an explanation of the EUR 10 difference.

Evidence directory: `/private/tmp/vera-remediation-01a07083/source-acceptance-a08-linked-history/`.
Key files: `history-verification.json`, `codex-review-request.json`,
`codex-review-response.json`, `successor-result.json`,
`isolated-successor-replay.json` and `final-verification.json`.

## Limited privacy reconciliation — 6 September

Reviewed AML, Archive Organization and Business Planning workflow instructions,
context consumers, privacy declarations and public model-data copy against the
optional shared `imported_names` field. The inspected change adds no model call
or external destination. Refreshed those three records and the separately
reviewed Open Item record. The overall register still reports other stale
records; these refreshes do not establish a complete-register pass.

Archive Organization public copy now states in all five languages that only
SHA-256 establishes the implemented exact-duplicate match; other checksums alone
do not. This matches `_exact_duplicate_key` for local and Drive inputs. The two
existing archive-page/model-data-contract checks pass (`archive-page-review.xml`).
Package rebuilding and full-register reconciliation remain outstanding.

## Fresh A01 exposes omitted residual request

Current source run `source-acceptance-a01-reviewed-current/result.json` reproduces
invoice EUR 1220, allocated payment EUR 488 and residual EUR 732. Source PDF text
and the operational workbook were inspected. The generated targeted-evidence
workbook contains only headers in every request section: the partially paid row
is missing. `section_for_row` in `build_missing_evidence_requests.py` has no
`partially_paid` branch and returns an empty section, dropping that row.

Do not accept this output package yet. Add an explicit partial-payment request
that preserves the known payment reference and asks only for evidence concerning
the EUR 732 residual, verify the actual workbook, then perform the fresh Codex
review and successor regeneration. No review decisions were applied to this run.

Partial-payment request correction implemented: `partially_paid` now enters the
missing-evidence section, with localized wording for all five languages that
preserves the documented allocated payment and bank reference and asks only for
settlement evidence or open-balance confirmation of the residual. The request
amount and section summary now use the residual rather than the original invoice.
Five language-parametrized regressions failed before the fix (missing row), then
passed after the fix, including saved XLSX inspection. The complete request-pack
test file passes all 10 tests. Fresh managed A01 regeneration/review and package
fingerprint reconciliation remain required; this test result is not final run
acceptance.

Fresh source regeneration exposed and corrected a dependent lineage issue: the
missing-evidence section total previously summed original invoice amounts only.
The rendered-value formula now records the partially-paid status override to
`residual_amount`. The first run failed closed on the unsupported 732 total;
the subsequent actual PDF-source run completed and saved both operational and
assurance-final workbooks with one request for 732.00, documented payment488.00,
and the precise imported bank source reference. Evidence is under
`/private/tmp/vera-remediation-01a07083/source-acceptance-a01-residual-lineage`,
run `run_b06bdb5bc305bac7e121c5da`. Workbook cells were inspected with openpyxl.
The result still reports checks_pass=false pending review; this is not accepted
as completion of A01. Review, focused assurance regression and package refresh
remain next actions.

A01 successor review is now recorded through `review_server.apply_decisions`
with the retained predecessor checkpoint. Source PDFs, request XLSX rows and
DOCX paragraphs/tables were inspected. Reviewer identity is explicitly
`reviewer.codex_acceptance`, not an independent qualified professional. The
successor result passes all 17 checks and retains `partially_paid`, allocation
488.00 and residual 732.00. Review request/response, checkpoint and successor
result are retained in the same source-acceptance-a01-residual-lineage directory.
Native application rendering was not attested by this review.

## A04 reviewed successor and A05 current-source finding

A04 current-source review inspected the allocation ledger, DOCX tables and
request workbook. One source payment1830 funds targets1220 and610, balanced with
zero source/target residuals and no capacity reuse. The checkpoint-bound Codex
review successor passes checks. Evidence: source-acceptance-a04-reviewed-current,
a04-review.log and a04-successor.log. This remains technical synthetic acceptance.

A05 fresh source run correctly leaves the invoice unresolved at September30 and
creates no allocation ledger for the October2 payment. The operational sheet
retains the October2 date and states closure is not demonstrated at cut-off.
However, the targeted-request workbook only cites the original invoice and asks
for missing closure evidence without mentioning the already held later payment.
This is incomplete professional guidance: preserve the later bank reference and
explicitly distinguish payment after cut-off from proof of settlement at cut-off.
Do not accept the A05 request artifact yet. Evidence:
source-acceptance-a05-reviewed-current/result.json and its generated workbooks.

A05 request builder now accepts the existing post-cutoff candidate population
and joins it by exact open_record_id, preserving date/file/page/row/id in the
request. Five localized messages distinguish later candidate evidence from
settlement at cut-off and request only missing support for any claimed earlier
settlement. Both raw intake and workbook CLI pass this existing population;
no new matching/classification rule is introduced. All 15 request-builder tests
pass, including five localized later-candidate cases. Full current-source
regeneration, assurance checks and package/privacy refresh remain required.

A05 actual corrected-source run and checkpoint-bound reviewed successor now pass
all pipeline checks. Inspected request workbook retains October2 bank reference,
asks for balance confirmation at September30, and requests only missing support
for any claimed earlier closure. DOCX separates later evidence; allocation
ledger remains empty. Evidence: source-acceptance-a05-request-fixed, a05-review.log,
a05-successor.log. Reviewer is Codex technical acceptance, not independent
professional or native-rendering qualification. Regression suite launched in
this batch; its outcome must be checked separately.

A06 fresh source case rejects EUR100 versus USD100 and creates no allocation.
Request fix retains supporting-bank reference/description and adds five-language
perimeter-conflict follow-up. Regeneration confirms those fields. The operational
sheet still selected a separate advisory candidate detail, which displayed zero
difference and high confidence despite rejected perimeter. Corrected that path
too: failed-perimeter candidates use unavailable difference, low confidence and
require perimeter clarification before allocation. The direct normalized-evidence
path also withholds arithmetic across different currencies. Subsequent complete
regeneration/tests/privacy/package updates remain required. Evidence:
source-acceptance-a06-current and source-acceptance-a06-output-fixed (the latter
predates the advisory-candidate correction and must not be accepted as final).

A06 corrected candidate-source regeneration completed at
source-acceptance-a06-candidate-fixed. Operational and evidence-detail workbook
cells now show low confidence and `N/A - perimetro non coerente` instead of a
numeric zero. No allocation is created; bank_relationship_controls_pass remains
FAIL as expected for incompatible currencies. This negative acceptance must not
be forced to a globally green settlement result. All 24 accountant-report and
request-builder tests pass, including the rejected-candidate regression and five
localized request-reference cases. Broader assurance regression and package/
privacy reconciliation remain outstanding for these edits.

Clarification from the saved XLSX inspection: the builder regression retains the
full unavailable-reason string, but the final workbook serializes the main-sheet
difference as `N/A` and the detail numeric difference as an empty cell. Both
saved rows show `Bassa` confidence. The preceding paragraph's exact reason-string
claim applies to the builder result, not the final serialized cells. The reason
remains in the candidate follow-up/request wording; inspect that final wording
before accepting the artifact. This distinction must be retained in acceptance.

A06 negative acceptance now has executable assertions and a retained result:
source-acceptance-a06-candidate-fixed/negative-acceptance.json. The invoice stays
needs_evidence; currency mismatch is explicit, allocation ledger empty and bank
relationship control fails as expected. Main XLSX difference is unavailable,
confidence low, and final request retains the bank reference and asks to clarify
the reviewed perimeter. Final detail-sheet actions were also inspected. This is
a passing rejection test, not a settled case or an all-green professional run.
No review decision was used to override the failed currency control.

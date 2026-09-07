# Accounting outcome cases and acceptance evidence

Prepared for T15. Every case is synthetic. The user approved all A01–A08
expected proposals in `REVISIONE_PROFESSIONALE_IT.md`; the approval and original
source hashes are retained in
`/private/tmp/vera-remediation-01a07083/professional-proposals-user-approval.json`.
No further approval of those expectations is pending. The CSVs remain source
fixtures, not approved mappings for every workflow. Runtime and independent
professional acceptance are distinct requirements. See `SOURCE_INTAKE_FINDING.md`
for actual PDF/Studio Archive execution evidence, including A07's completed
Codex review and successor regeneration.

Cutoff: 30 September 2026. Amounts use explicit decimal points; dates are ISO.
An invoice amount is its stated obligation. A payment amount is its stated
settlement amount; these are not implicitly signed ledger postings. Before any
workflow adapter runs, approve debit/credit direction, source mapping, currency,
cutoff policy and evidence adequacy. Preserve original source files and hashes.

| Case | Evidence | Proposed review question and expectation |
| --- | --- | --- |
| A01 — partial-payment | A01/source.csv | 488 paid; 732 residual at 2026-09-30. Reviewer confirms allocation and required support. |
| A02 — reversal | A02/source.csv | Original plus reversal net to zero. Do not silently present the payment as settlement of an open 1220 balance; reviewer determines disposition. |
| A03 — duplicate-evidence | A03/source.csv; A03/source-copy.csv | The byte-identical source copy does not by itself establish a second economic obligation. Reviewer approves deduplication rule and lineage. |
| A04 — grouped-payment | A04/source.csv | 1220 + 610 = 1830. Reviewer approves group membership; allocation cannot consume either invoice twice. |
| A05 — cutoff | A05/source.csv | The payment is after the stated 2026-09-30 cutoff. Reviewer approves open-item treatment and subsequent-event presentation. |
| A06 — currency-conflict | A06/source.csv | Equal nominal numbers do not establish currency equivalence. No exchange rate or reviewed currency conversion is supplied. |
| A07 — missing-support | A07/source.csv | No remittance reference distinguishes the two invoices. Reviewer specifies permitted abstention and requested supporting evidence. |
| A08 — changed-source | A08/source.csv; A08/source-replacement.csv | A replacement source changes the payment to 110. Old source-bound review must not silently authorize the replacement; reviewer assesses the additional 10. |

Apply A01–A08 to Open Item and Journal–Bank where their accepted input contracts
support the case. Use duplicate/currency/missing-support/changed-evidence cases
for Check Entries and Passive Invoice with actual supporting FatturaPA or
reviewed documents added before execution; these CSVs alone do not qualify XML
extraction or expense/VAT judgment. Journal Sampling additionally needs reviewed
population, strata and sample-size cases; allocation arithmetic tests do not
establish inferential validity. No whole-pipeline coverage is implied by this pack.

For each applicable workflow, the independent reviewer must approve expected
links, forbidden links, required abstentions and visible report claims before
examining candidate outputs. Preserve disagreements and corrections. After
approval, run the existing workflow from mapped source intake through review and
normal final artifacts. Record input/mapping/source hashes, code/package/model
identity, normalized rows, proposed and final decisions, report and model-data
artifacts, and any unsupported host or missing-document outcome.

Count false matches against approved forbidden links, missed matches against
approved required links, abstentions against the approved eligible population,
and reviewer corrections against initial candidate decisions. State denominator
and unlabelled coverage for every rate. Do not count an unexecuted, unlabelled or
unsupported case as correct, or treat proposed labels as independent truth.

The local pack and blank reviewer worksheet are at
`/private/tmp/vera-remediation-01a07083/accounting-review-cases/`.
The manifest preserves exact source bytes and hashes. A03 has byte-identical
copies; A08 has different original/replacement hashes. The complete pack remains
local and has not been sent to a reviewer or model service.

## Journal-Bank source acceptance started

Managed synthetic A04 inspection is retained at
`/private/tmp/vera-remediation-01a07083/journal-bank-a04-current`.
The CSV bank population contains one positive receipt1830 with two invoice
references; the journal population contains the corresponding posted receipt
lines1220 and610 on the same date. These are bank-account receipt postings,
not invoice issuance entries or implicitly signed obligations. This preserves
the A04 grouping/capacity question while respecting Journal-Bank's input meaning.
Both imported sources qualify through the exact-header CSV adapter (1 bank row,
2 journal rows). No rows or full source tables were opened as model context;
the synthetic source was authored for this test and qualification inspected.
Current recipe mappings are proposals; relationship authority still needs to be
sealed for one-to-many, same currency/entity/party and no reuse before running.
The managed run is active, not complete. No residual worker has launched.

Journal-Bank A04 relationship policy sealed against current source hashes using
the public receipt builder: one_to_many, no reuse, same currency/unit/entity/
party and same sign (both inputs represent receipts). The public managed CLI
completed. Source and preparation gates pass, but 0 matches, 1 unmatched bank,
2 unmatched journal remain and report_ready=false.

Inspected `_unconflicted_reference_group_batch`: grouping currently requires one
shared token present on all group members. A bank reference listing INV-1 INV-2
with separate journal references INV-1 and INV-2 therefore does not form the
expected explicit-reference group. Preserve this original case and its failure;
do not rewrite the sources to a common batch ID merely to obtain a pass.
Next assess token handling and implement bounded explicit-reference-list grouping
with exact conservation, perimeter and non-reuse checks, including competing/
ambiguous reference-list cases. No semantic worker was launched and no unmatched
row was promoted by review. Evidence run stays active pending correction or
explicit retained blocked completion.

A04 grouping regression added through public run_reconciliation and current
review-receipt helper: test_explicit_invoice_list_allocates_one_bank_payment_without_shared_batch.
It fails as expected (0 matches versus2); exact failure retained in
journal-bank-a04-red.log. Additional root cause: `_reference_tokens` discards
short invoice identifiers and generic-prefixed compact identifiers, so simply
unioning current tokens will not repair INV-1/INV-2. The next implementation
must preserve exact mapped identifiers and bounded explicit list membership,
withhold incomplete/competing groups, and retain currency/direction/date and
capacity checks. Do not broaden description matching or remove generic-period
protections to make this test green. The new test is intentionally failing
until that implementation is complete.

Explicit-reference-list grouping implemented without changing global fuzzy/token
matching. It preserves punctuation in mapped reference identifiers, requires a
bounded complete distinct list, exactly one counterpart per identifier, and
passes the same shape/perimeter/date/amount checks and overlapping-membership
rejection as existing shared-reference groups. No description/name inference or
subset-sum search is added. Mechanical justification: authored explicit list
membership plus exact capacity conservation, not inferred invoice relevance.
Nine focused tests pass, including the original red regression, existing group
cases and missing/duplicate/competing list cases.

Fresh managed source run `journal-bank-a04-list-fixed` uses identical source
contents to the retained failing case, with fresh source-bound relationship
review. Actual CLI output now has 2 reference_group matches, 0 unmatched bank
and 0 unmatched journal. Source/preparation/reconciliation gates pass. Reporting
is still withheld pending review, so report_ready remains false. Review, final
artifact replay, broader regression and privacy/package reconciliation remain
required before acceptance. No worker launched or review bypassed.

A04 MCP validation succeeded with the current client_engagement context. The
bounded index exposes two matched cases plus artifact-review cases; only the two
matched cases were requested with exact identifiers, needed to verify explicit
list membership. Projection shows 1830 bank population versus allocations1220
and610, reference_group, zero group delta and exact explicit list inv-1|inv-2.
Saved bounded-review-index.json and bounded-matched-context.json under the fixed
case. No private full payload was opened or review decision applied. The first
validation attempt omitted required client context and failed closed; corrected
call succeeded.

Full Journal-Bank test file started with bundled Node and JUnit output
journal-bank-list-full.xml/log. Live exec handle54904 remained running at the
last observation, with at least one reported failure. Poll this same handle;
do not restart or claim the full suite passes before its terminal result.

During full-suite observation, collected test ordering locates the visible
failure at test_mcp_rejects_unowned_implementation_path_before_stdio. Inspected
fixture creates only an empty __pycache__, which the current implementation
boundary intentionally permits. Replaced that stale fixture with unowned.py;
focused retry passes and preserves the actual unowned-code rejection contract.
No production behavior was changed for this test. Evidence:
journal-bank-unowned-retry.xml. Full run54904 remains live at last poll; wait
for its terminal failure summary to confirm no other failures before reporting
combined results. Original suite was already loaded before this test edit.

A04 fresh validate_material_value_ledger replay succeeds for 52 material entries
covering 2 match rows and 3 bank/journal residual rows across CSV and XLSX.
Retained material-replay-result.json. The bounded artifact-context request
returns nine generic artifact_status items with no distinguishing artifact
identity or outcome information. This projection is insufficient to approve
artifacts on its own; do not accept blindly. Continue through the local manifest
and exact declared artifacts (or improve bounded artifact metadata) while
preserving the no-full-private-payload model boundary. Full test handle54904
still live at last poll, progressed beyond89 percent with the one visible
failure whose corrected fixture has a passing focused retry.

Journal-Bank full suite is terminal:403 tests,402 passed,1 failed,0 skipped,
238.052 seconds. The only failure is the stale empty-cache fixture already
corrected and passed in journal-bank-unowned-retry.xml. Together the full run and
focused retry provide passing evidence for all403 cases; they are not a single
all-green full rerun. Handle54904 is closed and must not be polled again.

A04 final manifest20 outputs all exist at declared sizes. Every output receipt
was checked against physical SHA256 and byte count, retained in
artifact-integrity-review.json. This supplements successful52-entry material
replay; it does not establish native rendering or independent professional
review. Review decisions and managed run finalization still remain open.

A04 normal save/apply MCP decisions completed for12 review items. Decisions
explicitly record synthetic Codex technical review, exact group allocation,
source/preparation/reconciliation gates, receipt verification and material
replay; native visual and independent professional acceptance are excluded.
Application reports final_ready, assurance_report_ready=true, no blockers and
no native regeneration. Evidence: save_journal_bank_decisions.json,
apply_journal_bank_decisions.json and journal-bank-a04-apply.log.

Studio Archive completion is still open. It requires model_data_report.json/md
through the existing generic local report helper, followed by declarations for
every physical output and finalize_run/complete_run. Do not treat the component
final_ready status as completion of the managed run. No worker was invoked.

A04 managed run now completed through Studio Archive finalize_run and complete_run.
All36 physical outputs declared and sealed; final declaration inspected.
Model-data JSON/Markdown disclose synthetic authoring, mapping inspection and
bounded review/material-replay context, using host-attested not_measurable
extent rather than falsely claiming source data never reached the model.
No server attestation or worker launch is claimed. Saved finalize-result.json,
complete-result.json, model-data-request.json and output-declarations.json under
the fixed-case evidence directory. This completes this synthetic managed A04
execution; remaining workflow cases, independent/native qualification and
privacy/package refresh still apply to the overall objective.

Journal-Bank A01 bounded review confirms same explicit reference, same date and
currency, bank488 versus journal1220. Unlike Open Item's invoice obligation,
this is a posted-receipt discrepancy: source evidence alone does not establish
that732 is a remaining receivable or authorize journal correction. Retain both
unmatched rows and request explanation/support; do not force partial settlement.

Residual preparation executed with perfect_match as this exact-reconciliation
acceptance threshold: selected1 bank movement, deferred0, worker_required=true.
The qualified public run-worker launcher then failed before launch with:
`SEMANTIC_WORKER_LAUNCH_FAILED: The macOS build has not been qualified for Luna isolation`.
Exit2 and exact logs retained in journal-bank-a01-current/semantic-worker-attempt.log.
No pins were weakened and no alternative worker was substituted. This is a
verified host limitation for the actual synthetic packet, not completed semantic
acceptance. Inspect saved status/queue and complete a disclosed blocked run
through normal review and Studio Archive next; other task work can continue.

Journal-Bank A01 worker failure verified in saved state: worker_failed,
deterministic_baseline, one movement488 retained in human queue, no semantic
decision hash, report_ready=false. Created local model-data JSON/Markdown with
host-attested limitations and recorded the managed run as failed using fail_run,
retaining all outputs and exact launch failure. Evidence: failed-run-result.json.
This closes the attempted run lifecycle without claiming acceptance or altering
the current platform qualification pins. Further supported-host semantic
qualification remains outstanding; other workflow acceptance can continue.

Journal-Bank A06 actual managed CSV source case executed: bankUSD100 versus
journalEUR100, same explicit reference/date and reviewed same-currency policy.
No matches; one unmatched each side. Residual graph has selected_bank_count1,
selected_journal_count0 and selected_edge_count0, proving the incompatible
journal cannot become a semantic match candidate. Worker_required remains true
for bank-only classification; no worker was launched because the unchanged host
qualification failure was already verified in A01. This is not a claim that all
semantic processing is skipped for currency conflicts.

Negative-acceptance.json records the passing currency-edge rejection and
unexecuted classification. Local model-data disclosure created. Managed run
recorded failed with outputs retained and reporting withheld, not accepted or
settled. Evidence: journal-bank-a06-current. Other Journal-Bank cases and
Check Entries/Passive Invoice/Sampling source acceptance remain outstanding.

Check Entries acceptance setup now has an actual managed Journal Sampling
inspection at sampling-check-entries-current. Synthetic journal has3 entries
with distinctive movement/invoice IDs and exact EUR amounts; planned sample is
all3 entries, explicitly not an inferential sampling design. Inspection withheld
the source as unsupported_source_layout. Suggested mapping maps account to date
because the authored test source omitted an account field; that proposal must
not be approved. Add an explicit account column to a new synthetic source import
and rerun inspection with reviewed mapping, preserving this rejected initial
attempt. Check Entries remains unstarted until all9 upstream artifacts are
sealed by Journal Sampling. No source file was silently repaired in place.

Corrected synthetic journal imported into a separate managed run at
sampling-check-entries-accounted, preserving the rejected initial source. Added
explicit account120100 to all3 authored debit-positive EUR entries. Inspection
now maps account to account and requires review. Sealed the exact mapping
contract using the public reviewed-decision builder against source qualification
refs, with reviewer.codex_synthetic_acceptance. Public normalization CLI emits3
rows; public run_sample CLI random size3 emits3 rows. This is a complete tiny
population for handoff acceptance, not statistical inference. Exact scripts/logs:
normalize_sampling_accounted.py and sampling-accounted-run.log.

Run run_7c8be8b315fd96c822649eaa remains active pending review, model-data report
and declarations with the exact upstream semantic artifact IDs required by Check
Entries. Do not use arbitrary hashed IDs for those9 handoff artifacts. Next
review normalization/sample gates and seal the managed sample before importing
support and invoking start_check_entries_from_sample.

### A07 Journal–Bank actual missing-support case — 2026-09-06

Executed a fresh managed synthetic CSV intake and source-bound one-to-one,
same-sign relationship review at
`/private/tmp/vera-remediation-01a07083/journal-bank-a07-current`.
The bank receipt is EUR100 without a reference; the journal has two EUR100
receipt postings, INV-1 and INV-2, on the same date and with the same explicitly
mapped entity and party. These are posted bank-account movements, not invoice
obligations. Neither candidate has distinguishing settlement evidence.

The public reconciliation CLI and native MCP validation/selected-case retrieval
succeed. All three entries remain unmatched and request supporting documents;
neither journal candidate is silently selected. The actual bounded MCP output
also confirms the latest Italian request/reason wording, including the bank
amount fallback when its reference is absent. Evidence:
`bounded-review-index.json`, `bounded-residual-context.json`, and the sibling
`journal-bank-a07-inspect.log`, `journal-bank-a07-run.log`, and
`journal-bank-a07-review.log`.

This establishes deterministic abstention for this authored ambiguous case.
No semantic worker was invoked and no professional acceptance or completed
managed-run lifecycle is claimed. Review decisions, model-data disclosure and
managed-run disposition remain outstanding.

A07 normal MCP save/apply now persists 13 explicit technical review decisions:
three unmatched entries request documents; ten artifact items remain unclear
pending content/native review. Apply succeeds while correctly preserving
`application_status=blocked`, `assurance_report_ready=false`, 13 blockers and
zero target updates. No candidate was accepted or allocation introduced.

Created Italian model-data JSON/Markdown with honest host-attested,
not-measurable context disclosure. Studio Archive `finalize_run` seals all 35
physical outputs and puts run `run_697ced1df246b7bf8d4443ba` in
`ready_for_review`. This is a retained unresolved review package, not completed
professional acceptance. Evidence: `save_journal_bank_decisions.json`,
`apply_journal_bank_decisions.json`, `model-data-request.json`,
`output-declarations.json` and `finalize-result.json` in the A07 directory.

### A08 Journal–Bank managed source replacement — 2026-09-06

Executed separate managed synthetic original/replacement fixtures (separate test
clients, not a claim of same-engagement successor lineage). Original bank100 and
journal100 produce one match and zero unmatched rows, with audit
completed_pending_review. Replacement bank110 with byte-identical journal100,
using the exact original relationship receipt, fails with
`relationship_review_required`: `decision source binding is stale`. Its retained
blocked artifact package has zero matches and one unmatched row on each side.
No stale decision authorizes the additional10. Exact original/replacement source
hashes, run IDs and row counts are retained in
`/private/tmp/vera-remediation-01a07083/journal-bank-a08-source-binding-evidence.json`.
The CLI failure is in `journal-bank-a08-stale-review.log`; managed fixtures are
`journal-bank-a08-original-postings` and `journal-bank-a08-replacement-postings`.

The initial fixture accidentally made bank/journal files byte-identical.
Studio Archive deduplicated the imports and rejected repeated selected input IDs
before run creation (`Workflow input selections contain duplicates`). That
attempt remains in `journal-bank-a08-original`; it is not a completed A08 run.
Distinct new fixtures identify bank versus journal postings in a description
column while retaining the intended amounts/date/reference and perimeter.
Original files were not overwritten. This observation is not full A03 acceptance.

Remaining A08 work: same-engagement replacement handoff, explicit fresh review of
the EUR10 discrepancy, bounded output review, model-data disclosure and managed
lifecycle disposition. The verified stale-receipt rejection does not establish
those remaining outcomes or independent professional acceptance.

A08 same-engagement replacement is now executed under the original engagement.
Replacement run `run_0d90f78b95206af4ac8a06f1` retains the original journal bytes
and imports bank110 without modifying the original bank100. The old relationship
receipt is rejected with relationship_review_required/source binding stale.
`journal-bank-a08-same-engagement/source-binding-result.json` records identities
and unchanged-source checks. The failed attempt's artifacts remain in stale-review.

A fresh source-bound synthetic relationship review then executes to a separate
reconciliation output directory. Native MCP selected context confirms bank110
and journal100 remain unmatched despite identical reference/date/currency.
Normal save/apply decisions request evidence explaining EUR10 on both sides;
artifact review remains unclear. Application is blocked, report_ready=false and
no target changes are made. Evidence: bounded-residual-context.json and
apply_journal_bank_decisions.json. This closes the previously missing
same-engagement execution and explicit discrepancy review, but model-data report,
managed finalization and independent/native qualification still remain.

A08 same-engagement replacement package now finalized to ready_for_review with
59 sealed outputs. This includes the retained stale-review rejection package,
fresh reconciliation and review decisions, and Italian model-data disclosure.
A separate physical audit confirms all 59 SHA256/byte counts, with no missing or
undeclared output files. Evidence: finalize-result.json and
final-integrity-result.json under journal-bank-a08-same-engagement.
The managed finalization and disclosure listed above are now done; report
readiness remains withheld for the EUR10 discrepancy and incomplete artifact
review. Native/professional qualification is not implied.

### A03 Journal–Bank duplicate evidence — 2026-09-06

Actual managed case at journal-bank-a03-current imports journal.csv and its
byte-identical journal-copy.csv. Studio Archive returns the same input ID for
both and retains both imported names in the receipt. The run explicitly selects
that input once, alongside the distinct bank source. Public inspection and
reconciliation produce exactly one EUR100-to-EUR100 match and zero unmatched
rows; the copy does not create a second journal movement. Native MCP validation
and bounded selected-case review confirm a single amount_date_unique match,
zero amount delta and zero date difference.

Evidence under `/private/tmp/vera-remediation-01a07083/journal-bank-a03-current`:
duplicate-import-result.json (including current receipt/names),
duplicate-reconciliation-result.json, bounded-review-index.json and
bounded-residual-context.json. This verifies byte-identical evidence handling
and explicit unique input selection, not semantic deduplication of differently
encoded documents or true duplicate economic postings. Review/application,
model-data disclosure, native/professional checks and finalization remain open.

A03 duplicate case now has normal MCP save/apply: the single EUR100 match is
accepted as synthetic technical evidence; artifact items remain unclear rather
than receiving unperformed native/professional approval. Application succeeds
and correctly retains blocked report status. Italian model-data disclosure and
all35 physical outputs are sealed by Studio Archive to ready_for_review.
Separate SHA256/size verification passes35/35. Evidence: apply_journal_bank_decisions.json,
model-data-request.json, finalize-result.json and final-integrity-result.json
under journal-bank-a03-current. Finalization/disclosure listed above are done;
remaining qualification limits still apply.

### A05 applicability review for Journal–Bank — 2026-09-06

The approved A05 question is whether a September invoice is settled at September30
by an October2 payment. Inspected Journal–Bank's workflow definition, CLI and
`RELATIONSHIP_POLICY_FIELDS`: this engine reconciles posted bank/journal
movements; it exposes amount tolerance and a symmetric date-distance window,
but no as-of cutoff or subsequent-settlement policy. `_date_diff_days` computes
absolute date distance. The skill's generic instruction to resolve a cutoff
choice does not implement a cutoff in this engine.

Therefore the original invoice-settlement A05 expectation is outside the current
Journal–Bank input/decision contract; retain the existing Open Item A05 execution
as the applicable evidence. Do not turn an invoice into a bank-account posting,
claim date-window matching proves settlement at cutoff, or label an unexecuted
Journal–Bank cutoff test as passing. A separate test of posting-date differences
could verify date-window behavior, but would not answer A05. This follows the
pack's explicit “where their accepted input contracts support the case” scope;
it does not close other Journal–Bank acceptance requirements.

Source anchors: plugins/journal-bank-reconciliation/scripts/run_reconciliation.py
CLI arguments; journal_bank_core.py RELATIONSHIP_POLICY_FIELDS and
_date_diff_days; skills/journal-bank-reconciliation/SKILL.md workflow definition.


### A04 measured before/after outcome — 2026-09-06

Re-read the original and corrected managed input bytes and actual match/unmatched
CSV outputs. Both runs use identical bank and journal source bytes. The approved
1830 = 1220 + 610 proposal maps to the two explicit journal source rows; this
row-level mapping is Codex technical analysis, not a new independent review.

| Measurement | Before fix | Corrected retained run |
| --- | ---: | ---: |
| Required source links found | 0/2 | 2/2 |
| Missed required source links | 2/2 | 0/2 |
| Unexpected links / predicted links | 0/0 (rate unavailable) | 0/2 |
| Unresolved bank rows | 1 | 0 |
| Unresolved journal rows | 2 | 0 |
| Corrections to proposed links by technical reviewer | unavailable | 0/2 |

The corrected allocation totals EUR1830 exactly, with two distinct links and
no duplicate link row. The repeated bank amount in each match row is not summed
as two separate payments. These counts measure the retained synthetic fix;
they are not population accuracy or independent professional acceptance.
Unmatched-row counts are not labelled semantic abstentions. Independent false-match,
abstention and reviewer-correction rates remain unavailable where independent
link/eligibility labels are absent. User approval of the case expectation remains
valid and does not need to be repeated.

Exact input/output/review hashes and denominators are recorded in
`/private/tmp/vera-remediation-01a07083/journal-bank-a04-outcome-metrics.json`.
This comparison reuses retained normal runtime outputs; it is not a new execution
of today's source or a replacement for final unchanged-source qualification.


### Passive Invoice missing-support managed acceptance — 2026-09-06

Executed the public run_audit.py CLI with a Studio Archive engagement, one
synthetic FatturaPA XML invoice (INV-1, EUR122, supplier Alfa), a booked movement
for a different supplier and invoice (UNRELATED-2, EUR122, supplier Beta), and
an explicit canonical numeric/header mapping. Chunk size25, concurrency2; no
semantic packets are eligible because no invoice matches. The dependency check
still reports the native Luna worker unqualified; no worker boundary was bypassed.

Initial runtime correctly produced one unmatched invoice, one ledger orphan and
professional_review_required, but left the XLSX professional_should_inspect
cell blank. That acceptance is recorded failed, with all original files retained
under passive-missing-support-current in the private evidence directory.

Corrected source retains an operational missing-support request in both JSONL
and XLSX: inspect the supplied scope and mapping, request the corresponding
movement or an explanation of its absence from the extract, and do not create
a booking from the screening result. This explains the exact no-match outcome;
it does not decide that a booking was omitted or alter semantic judgments.

A fresh managed CLI run, run_60db21717bfa72c383951469, uses byte-identical sources.
Direct output checks verify 1 unmatched invoice, 1 orphan, 0 matches, 0 semantic
chunks and identical request text in JSONL/XLSX. Eight output artifacts, including
SQLite and an Italian model-data disclosure, are sealed to ready_for_review.
Evidence: passive-missing-support-fixed/source-output-verification.json,
execution-result.json, finalize-result.json and model-data-request.json beneath
/private/tmp/vera-remediation-01a07083. The main model saw synthetic source and
output excerpts; zero worker chunks does not mean wholly local model processing.

Component regression: 89 passed, 1 opt-in native test skipped, 0 failed/errors
(passive-source-request.xml). No independent professional, native visual or
semantic-worker qualification is claimed. This case adds actual missing-support
runtime evidence; it does not cover matched-invoice account-treatment judgment.


### Passive Invoice ambiguous candidates — 2026-09-06

Public managed CLI run with one invoice and two independently identified booked
movements M1/M2 correctly withheld matching and semantic review. Its normal XLSX
failed technical acceptance: candidate IDs were only in JSONL and the reviewer
next-action cell was blank. Original outputs remain under passive-ambiguous-current,
with a failed acceptance lifecycle record.

The output now retains candidate movement IDs, source ledger references and exact
supporting match fields in both JSONL and XLSX. Ambiguous and duplicate-candidate
states receive explicit evidence requests; these instructions do not select a
movement, infer an omitted booking or treat a copied XML as a second obligation.
The ambiguous finding now describes nonunique allocation rather than incorrectly
requiring multiple candidates (one movement can be contested by multiple invoices).
No worker prompt or match-selection rule changed.

Fresh managed run run_1d648d60925264560ce61143 uses byte-identical input files.
Direct verification confirms both M1/M2 references visible, one unresolved
ambiguous invoice, zero selected matches, zero ledger orphans, zero worker chunks,
and identical action text in JSONL/XLSX. Eight artifacts, including Italian
model-data disclosure, are sealed for review. Exact hashes and assertions:
/private/tmp/vera-remediation-01a07083/passive-ambiguous-fixed/source-output-verification.json.
This is technical source/output evidence; independent professional, native visual
and worker-host acceptance remain unqualified.

Component regressions: 91 passed, 1 opt-in native skip, zero failures/errors
(passive-candidates.xml). The new normal-output regression also verifies that two
ledger candidates remain visible for duplicated XML documents. Duplicate-source
managed CLI acceptance is not inferred from that regression. All three Vera ZIPs
rebuilt and passed parity with 18 packaged MCP startups; exact package hashes
are in passive-candidates-package-hashes.json. Privacy register passes; the local
candidate evidence adds no worker/model destination. No publication occurred.

Selected Vera/privacy/Cowork integrity tests: 35 tests, 0 failures, 0 errors, 0 skips (passive-candidates-integrity.xml).


### Passive Invoice duplicate XML managed execution — 2026-09-06

Executed the actual public CLI under Studio Archive with a ZIP containing two
byte-identical XML members (one.xml and two.xml), one three-line booked movement
M1, and the explicit canonical header/number mapping. No fixture runner or model
substitute was supplied to the command. Both XML members retain distinct source
references and invoice identities; both are duplicate_candidate with M1 shown
only as a candidate. Results: 2 duplicate flags, 0 selected matches, 0 orphans,
0 semantic chunks. Both workpaper rows include the evidence request and M1's
source ledger reference. No second obligation or allocation is inferred.

Managed run run_64ca19420c29876307961d47 is sealed for review with 10 outputs,
including staged XML, SQLite, JSONL, normal XLSX and Italian model-data disclosure.
Evidence: /private/tmp/vera-remediation-01a07083/passive-duplicate-current/
source-output-verification.json, execution-result.json and finalize-result.json.
This closes the managed duplicate-source execution missing from the earlier
regression-only checkpoint. Independent professional and native visual review,
matched-invoice semantic review and unsupported-host qualification remain open.

### 2026-09-06 — Measured retained negative-case outcomes

Inspected the actual final reconciliation JSON and source-qualification records
for A05 (`source-acceptance-a05-final`), A06
(`source-acceptance-a06-candidate-fixed`, superseding the earlier output-fixed
candidate), and A07 (`source-acceptance-a07-reviewed-current`). The three runs
contain four open-item rows: all four abstain from settlement, all retain an
evidence request, none has a matched-evidence ID and all allocation ledgers are
empty. A06 retains the expected failed bank relationship control; this is a
correctly withheld settlement, not an all-green professional run.

Recorded exact output hashes, mapped source refs, row/page IDs, status counts
and failed controls in `/private/tmp/vera-remediation-01a07083/open-item-negative-outcome-metrics.json`.
The executable measurement script is `measure_open_item_abstentions.py` in the
same root. This measures retained runtime evidence; it does not claim a fresh
execution or current-source replay. User-approved qualitative expectations are
retained, but no independent complete edge-label/candidate-decision dataset is
available for these runs. Accordingly independent false-match, missed-match and
reviewer-correction rates remain null, not fabricated zeroes. These measurements
complement the earlier A04 required-link and conservation measurements.

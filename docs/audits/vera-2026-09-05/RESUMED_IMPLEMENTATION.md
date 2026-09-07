> Historical remediation record. See [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md) for the resumed release tests and current coverage. Earlier temporary logs were unavailable at restart; their historical claims are not substituted for fresh evidence.

# Vera — resumed implementation, 6 September 2026

The user authorized fresh Astra Medium subagents and requested restart. The
goal is active. Earlier approval of the Italian synthetic expectations remains
valid. Missing historical Centrale Rischi PDFs constrain their own benchmark
cases, not the rest of implementation. No deployment or publication is included.

## Newly reproduced defects and corrections

| Workflow | Reproduced behavior | Correction and evidence |
| --- | --- | --- |
| Variance Analysis 0.1.98 | An `Infinity` tolerance passed source differences of 900 and 1800 and a bridge difference of 900. | Require finite numeric controls and a finite non-negative tolerance. Invalid tolerance remains an unresolved item. A normal synthetic engine run now rejects source differences of 290 and 310. New message has localized review translations and Italian report wording. |
| Open Item 0.1.52 | Two aliases of one document doubled the status count in the document-source map, despite correct obligation amounts. | Resolve aliases to distinct groups before counting each reconciliation row. Two separate records still count twice. Two regressions fail before and pass after; 94 focused tests pass. |
| Business Planning 0.2.7 | A plan blocked by stale numeric claims still showed accepted prose asserting losses and funding needs when the sensitivity had positive base EBITDA and no funding gap. | Clear accepted conclusions for blocked plans; retain original case and source/calculation/issue evidence. HTML withholds assessment. Normal partial scenarios remain available. Blocked presentation references remain validated against preserved input without accepting or rendering its conclusions; invalid reference/amount bindings still reject. |

Evidence root: `/private/tmp/vera-remediation-01a07083/`.

- Variance: `variance-nonfinite-before.json`,
  `variance-nonfinite-normal/verification.json`,
  `variance-nonfinite-final-targeted.xml` (11 passes).
  Full suite: 74 passes plus one managed dependency-network failure; the exact
  drilldown case separately passed with approved network access
  (`variance-nonfinite-drilldown.xml`). Do not describe the restricted full run
  as green or keep repeating the same network failure.
- Open Item: `resumed-retained-accounting-review/REPORT.md` and
  `source-acceptance-a03-status-counts/REPORT.md`. The fresh managed A03 run
  `run_bf29cea4a392342e7d2f332c` has one unresolved EUR 1220 obligation, count 1,
  both imported filenames in DOCX/XLSX, 67 sealed artifacts, and a completed
  technical lifecycle. All 65 earlier output files remain unchanged. It used
  the corrected code with pre-bump manifest 0.1.51; this is not execution proof
  of a downloaded 0.1.52 package or professional approval.
- Business Planning: `resumed-business-output-review.md`,
  `resumed-business-current/`, `resumed-business-after/`.
  Three before and three after managed runs are sealed and terminal. Independent
  Decimal calculations pass 150 comparisons per set. Thin-margin base EBITDA
  is 15, margin 1.5%, and funding/residual gap zero. The deliberately stale
  assessment remains blocked; baseline and incomplete-scenario behavior is
  preserved. Final shared/decision/presentation suite: 95 passes
  (`resumed-business-final.xml`, 1.23 seconds). A blocked case with a
  source-bound presentation also produces a diagnostic HTML/JSON package;
  the added caption/action/amount regressions preserve strict validation.

## Independent output acceptance

Sales Plan's two retained missing-discount and sparse-period cases pass 424
independent numeric/blank comparisons. All source rows and mapped Plan rows,
assumption-ledger effects, group totals, percentages and hashes reconcile.
Its natural outputs are CSV/JSON, so absent HTML/PDF/XLSX is not a product
defect. See `resumed-financial-output-review.md` and its independent checks.

A01/A02/A03/A08 normal reports were inspected independently: seven source hashes
and sixteen DOCX/XLSX report copies agree with retained evidence. The source-map
count defect above is separated from the preserved partial-payment, reversal,
duplicate-source and replacement-evidence outcomes. No model agreement is
reported as independent professional certification.

## Bandi fresh-session evidence

Fresh source-only contributions are now recorded as `MODEL_SUGGESTED`, with
exact retained excerpts and locally attested actual agent identities. Source
review and contribution acceptance remain separate from client eligibility.

- INTEL-000001: decree; `bandi-fresh-review/`.
- INTEL-000002: financing notice; `bandi-fresh-notice-review/`.
- INTEL-000003: FAQ; `bandi-fresh-faq-review/`.
- INTEL-000004: retained operational scope error. Its record command omitted
  explicit subject scope and reconstructed a four-source packet. It must not
  be treated as proof of the original single-source packet or accepted for
  this evaluation. Original evidence remains in `bandi-fresh-circular-review/`;
  INTEL-000005 was then produced in a genuinely fresh session with explicit
  single-source scope and matching packet/record hash. Evidence is in
  `bandi-fresh-circular-exact-review/`.

The four valid contributions are summarized with exact proposal hashes and
locators in `BANDI_CONTRIBUTI_RIPRESA_IT.md`.

No professional decision has been fabricated or copied onto these contributions.
They do not require stopping other engineering work.

## Integration

The configured unsuppressed Mypy check now includes the Variance numeric
controls: 22 source files pass. The seven changed implementation files have no
Bandit findings or scan errors. Vera privacy fingerprints are current after
review. Two stale service fingerprints were traced exactly to the Vera manifest
version change: substituting only the prior manifest reproduces their recorded
fingerprints (`resumed-service-privacy-differential.json`). No new service data
path was inferred or introduced.

After the presentation correction, Vera Codex/Cowork/Platform-upload packages
were rebuilt again and all three source checks passed. Eighteen packaged MCP
servers started and listed tools (`resumed-final-packages.log`). Exact source
and ZIP hashes/versions are in `resumed-final-identities.json`. The nine checked
Python/test files pass Black/Isort; the complete Vera privacy register and
workflow-registry check pass. These are local candidate artifacts, not publication.

The broader package/update run completed: 377 passed, 13 failed. Failures include
Clara source/ZIP drift after shared component changes, nine explicit managed
dependency-network failures, two missing Clara output artifacts, and the public
Clara version manifest lag. The two missing-artifact failures were subsequently
reproduced with the exit-code assertion moved before artifact reads: both report
`MPARANZA_NETWORK_PERMISSION_REQUIRED`. The approved network retry passed all
13 selected tests (`resumed-clara-network-retry.xml`). The original run is not a green
global gate. No public version manifest or unrelated Clara package was changed
to manufacture closure. Final Vera-only source/package checks above pass.

Observed repository lifecycle: 3 local branches, 3 remote branches, 3 worktrees,
0 stashes. This resumption created none and preserved the other tasks' work.

Remaining acceptance is tracked per task in
`resumed-acceptance-checklist.md` outside the checkout. T13's implemented
nine-workflow extraction already has local differential and package evidence;
unspecified further refactoring is not a mandatory open item.

## Further boundary checks — 6 September 2026

Two additional reproduced production defects are corrected:

- Bandi 0.3.7 requires the supplied packet SHA-256 when recording a model
  contribution. Reconstructed task/source scope must match before any register
  mutation. All 83 focused tests pass. A fresh managed source-only run rejected
  omitted subject scope with register and workbench byte-identical, then recorded
  exactly one contribution with explicit matching scope: INTEL-000006 remains
  MODEL_SUGGESTED. Packet and recorded hash both equal
  `33924c06753fa0fa16e6c924dc74bc9da3a76937609c9aee875f295d47707c59`.
  Evidence: `bandi-packet-binding/managed-acceptance/acceptance-summary.json`.
  This proves packet identity, not provider-authenticated execution or professional
  acceptance. The earlier mismatched INTEL-000004 remains excluded.
- Deep Research Validator 0.1.42 uses HTMLParser for extracted HTML text.
  Quoted attributes containing `>` no longer leak into captured source text;
  scripts, styles, comments and attributes remain excluded. All 72 module tests
  pass. Independent encrypted-PDF and UTF-16-HTML probes correctly remain
  unreadable; no unsupported decoding is claimed. Evidence:
  `intake-remaining-boundaries/ACCEPTANCE.md` and `full.xml`.

Three additional managed Business Planning runs passed 108 independent
arithmetic comparisons. Startup input legitimately has no opening financial
statements; zero-revenue undefined ratios stay unavailable; an explicitly
unsupported sector benchmark is withheld. These do not prove detection of
disguised semantic claims or browser/PDF layout. See
`business-remaining-boundaries/review.md`.

Configured Mypy now passes all 23 source files, including the Bandi recorder.
Bandit found no medium/high issues in the two new production changes (one low
B101 finding). Vera privacy fingerprints were reviewed and refreshed.
Vera and Lucia Codex, Cowork and upload ZIPs were rebuilt locally and source
checks passed; all 18 Vera and 4 Lucia packaged MCP servers initialized and
listed tools. See `boundary-pass-packages.log`; Lucia upload was additionally
built and checked successfully. These artifacts have not been published.

Clara package drift remains: shared Business Planning/Variance changes plus two
unrelated deck edits. This task has not rebuilt that unrelated package or changed
its public version manifest. Current host CLI is 0.153.4; the pinned native
worker qualification remains unsupported. The Mac reported locked, affecting
only live browser checks; an unlock request is pending. Neither constraint
stops independent implementation and verification. Goal remains active.

### Current candidate identity and decomposition ledger

`boundary-pass-identities.json` captures current HEAD, exact hashes of all six
locally rebuilt Vera/Lucia ZIPs and the changed implementation files, component
versions, sizes, and the 1,681-entry tracked/untracked dirty inventory. It supersedes
`resumed-final-identities.json` for current package identity; earlier run receipts
retain their original identities. The dirty inventory includes other tasks and
is not a claim that this task owns every change.

The retained trace measurements were re-read: nine callers decrease from 234
lines to 136 including the 19-line helper, a net reduction of 98. All 112 retained
production differential comparisons report identical payload/error behavior;
all 90 retained file-operation comparisons report equality. These are scoped
historical verification receipts, not fresh execution after unrelated edits.
Current Vera ZIP sizes are 5,475,249 bytes (Codex), 5,157,466 (Cowork), and
5,292,714 (upload). Size includes packaging and metadata changes and must not be
presented as a pure decomposition saving. No additional speculative pruning is
needed to preserve this completed extraction; remaining T13 acceptance must be
assessed against its original explicit requirements.

### Established-company opening balances and lifecycle mapping

One additional normal managed Business Planning run with ten explicitly absent
opening positions passed 12 independent checks. Commercial revenue EUR 1,000,
unit contribution EUR 4, operating result EUR -100 and break-even 125 units
reconcile independently; cash/funding outputs remain unavailable and the plan
partial. Physical artifacts/disclosure are sealed and the technical run completed.
Evidence: `business-missing-opening/review.md` and `independent-checks.json`.
The linked financial model is still entirely suppressed, including schedule-only
EBITDA; the retained separate commercial calculations do not prove dependency-aware
preservation of that linked model.

That report exposed two formula descriptions calling pending inputs “Accepted”.
Business Planning 0.2.8 now says “Supplied volume assumption” and “Supplied net
realized price”. Four existing commercial calculation tests pass; no arithmetic
or review status changes. The complete Vera privacy register passes after the
reviewed fingerprint refresh. All three Vera package builds/source checks and
18 packaged MCP startups pass in `business-wording-packages.log`. Current hashes
are in `business-wording-identities.json`; the earlier hashes precede this wording change.

`LIFECYCLE_ACCEPTANCE_MAP.md` now maps T11 to inspected implementation, retained
tests and current managed disclosures. It explicitly distinguishes injected
receipt-service tests from live server/provider evidence and retains the
deployed-page comparison requirement.

### T03 original sampling boundary observations

`SAMPLING_ACCEPTANCE_MAP.md` records five completed managed public runs and one
explicit failed normalization run. The original strata 1/1/20 case selects six
rows as 1/1/4; request1 selects one; request30 selects all 22 and explains the
shortfall of eight. Repeated MUS hits select one unique row from three eligible
rows and explain the shortfall of two; the negative input remains a credit.
An explicit zero row rejects normalization with its row number and reason;
the population is withheld rather than silently reduced. This is the observed
deliberate parser boundary, not an allocation defect.

Two nontrivial stratified runs have byte-identical selected CSV and equal complete
reproducibility JSON (`sampling-t03-seed-replay-comparison.json`). All six named
T03 acceptance cases now have managed observations. This does not establish
statistical inference, professional sample sufficiency, or every optional method
variant. No source changes were needed for these cases.

### Management Control and XML consumer boundary evidence

Ten Management Control cases ran through Studio Archive-bound public inspect/run
CLIs. Missing, empty, uncached formula, NaN and infinity reject before producing a
pack. Baseline, zero-revenue, both competing bank-row orders and 51-service cases
preserve independently checked totals and explicit unavailable sections. All 51
service identities occur in JSON/HTML/Markdown/XLSX. See
`management-acceptance-current/REVIEW.md`. These are retained draft-output checks;
successful fixture lifecycles were cancelled, not delivered as completed client
runs. Native visual inspection and complete delivery qualification remain distinct.

Six XML cases cover one/two invoice bodies across unqualified, default and fully
prefixed namespaces. Public XML/passive/Check Entries consumers preserve distinct
amounts, dates, numbers, multiple payments, withholding, VAT and source/body
identity. Check Entries intentionally rejects two bodies with an explicit error.
See `xml-consumer-acceptance/REVIEW.md`. This is public parser/consumer execution,
not a complete managed professional workflow.

The XML guide incorrectly described one summary row per file. Client File
Preparation 0.1.38 now documents one row per invoice body with source hash and
body index, distinguishing file count from body count. No parser changed. The
reviewed Vera privacy register passes. Local package build/check evidence is
`xml-guide-packages.log`: all three Vera source checks and 18 packaged MCP starts
pass. `xml-guide-identities.json` records the refreshed package hashes and dirty
inventory; prior package hashes predate this documentation change.

Management acceptance follow-up: cancellation was a reviewer scope decision,
not a technical requirement or a prerequisite to avoid professional approval.
The five cancelled and five failed fixture runs lack run-level model-data reports
and artifact manifests. Their output/hash evidence remains valid for bounded
builder assertions, but does not establish complete canonical delivery. An honest
external `management-acceptance-current/ACCEPTANCE_REVIEW_DISCLOSURE.md` records
the reviewer's access without modifying terminal run trees or inventing finalized
disclosures. This distinction remains an explicit acceptance limit.

### INPS L01/L02 and SARI host correction

L01/L02 now have one actual INPS source-workflow run with four imported inputs,
26 readable official PDF pages and no OCR. The normal packager retains two
`material_claim_not_fully_supported` issues, no contribution calculation and no
conclusive memo. A 54-artifact blocked evidence package was physically finalized
and technically completed; professional acceptance was not asserted. The candidate
asks for missing applicability facts and preserves the supplied 2024 memo as
historical. See `inps-l01-l02-current/REVIEW.md`. The memo contains no numeric
contribution, so numerical conflict reconciliation is not claimed.

Fresh L05 execution reproduced rejection of the approved official Registro
Imprese assistance URL. SARI 0.1.10 adds only `www.registroimprese.it` to the exact
HTTPS host set; metadata registration and network-route permissions remain distinct.
The positive registration test and five HTTP/lookalike/userinfo/port rejection
cases pass within the 53-test full module (`sari-host-fix-final.xml`). Mypy for
the changed source, Black/Isort and Bandit pass. The initial test-only assertion
placement mistake is retained in `sari-host-fix.log`; it was fixed in the test,
not production. The fresh normal L05 run passed source registration and completed
21-artifact physical delivery with zero validation errors, 13 unresolved blockers,
`partial_review` and `ready_to_file=false`. No municipality, chamber, form, fee
or filing sequence was invented. See `sari-l05-current/REVIEW.md`.

The L08 mixed-PDF run separately reproduced incomplete page coverage being
presented as fully readable. Client File Preparation 0.1.39 now records embedded
text coverage per page, propagates it into review/handoff/CSV, and explains missing
pages in the Italian report. Old coverage-less extraction checkpoints are invalidated.
The fresh managed case identifies text on page1 and no text on page2, sets
needs_ocr=true with medium confidence, and emits no deadline. Physical delivery
and honest disclosure are retained. The component batch passes66 with16 Node
skips; those exact16 subsequently passed with bundled Node. All82 cases therefore
have passing evidence across the two runs, not one unskipped suite. Two pre-existing
XML/EML type errors were corrected with an optional-value annotation and an identity
cast after tests terminated. Reversing only those changes reproduces the exact
managed-run source hash (`notice-l08-current/type-only-integration.json`). The
unsuppressed gate now includes extraction and passes 24 source files. The complete
Vera privacy register passes after reviewed coverage metadata refresh. Package
refresh passes all three Vera checks plus Lucia Codex/Cowork parity and packaged
MCP startup in `l08-sari-packages.log`; hashes are in `l08-sari-identities.json`.
Expanded extraction Bandit review reports one low B405 and one medium B314 at
the pre-existing OOXML parser. Its raw-byte DTD guard is now under a bounded
UTF-16 investigation; no security-clean or final package claim is made while
that concrete encoding question remains unresolved.

L06/L07 now have a bounded Concordato source-inspection execution with 37 finalized
artifacts (`concordato-l06-l07-current/REVIEW.md`). The exact40% ratio is verified;
no legal adequacy or feasibility conclusion follows. Historical11Feb2021 source
selection is preserved; the retrieved current-date index/preamble does not establish
the complete current article chain. Eight official PDF pages were extracted, but
current legal applicability remains unresolved and the candidate abstains. This
is a technical boundary check, not an independent legal correctness certification.

### OOXML encoding security and frozen integration

The suspected encoding bypass was reproduced with a tiny inert UTF-16 DOCX:
its internal entity expanded despite the byte-level DTD guard. Client File
Preparation 0.1.40 now parses OOXML using explicitly declared defusedxml with DTD,
entity and external-reference prohibitions. Nine new public regression cases
cover UTF-16 BOM/LE/BE rejection and ordinary document acceptance; all 12 selected
OOXML tests pass, as do unsuppressed Mypy, Black and Isort. Bandit B314 medium
is eliminated; the remaining B405 low concerns the stdlib import used for type
annotations/ParseError, not actual parsing. No suppression was added.

A fresh normal managed run verifies the new declared dependency runtime,
preserves 82 characters from the ordinary UTF-16 DOCX, rejects the inert entity
DOCX with zero characters, and retains both source hashes. Disclosure, physical
finalization and technical completion are recorded under
`ooxml-encoding-guard/managed`. No professional approval was invented.

One fresh Management Control run with 51 services now closes the earlier delivery gap:
20 artifacts sealed, validated disclosure, technically completed, with exact
prior metrics/sections preserved. See `management-delivery-current/REVIEW.md`.
All prior output hashes remain unchanged. Draft professional status persists;
file-URL browser policy blocked visual inspection, and no alternate route was used.

A temporary detached worktree at
`/private/tmp/vera-remediation-01a07083/final-integration-checkout` contains a
frozen copy of 5,873 files and five tracked deletions. Exact file hashes and the
absence of concurrent source drift are recorded in `final-integration-snapshot.json`.
It reuses the existing .venv only as runtime; ignored .env and caches were not
copied. The first copy attempt detected another task's changing review log and
stopped before starting tests; the second copy had no drift.

The complete pytest/80% coverage run is active in session 43263. Separate frozen
Black, Isort, unsuppressed 24-file Mypy and src Bandit checks have completed;
results are recorded below and in `final-gates.json`. Do not restart the live
pytest process or treat earlier checks as its outcome. This task created one
detached worktree and no branch; it remains needed while integration is active.

### Frozen gate results and remaining numeric review

Frozen Mypy passes 24 source files. The src Bandit command returns 1 for 30 low
findings, with zero scan errors and no medium/high findings; this satisfies its
stated severity threshold but is not a zero-finding result. Repository-wide
Black reports 312 files and Isort 220 files. Of those, 257 and 208 respectively are
byte-identical to HEAD; others include unrelated changes and generated copies.
`final-format-classification.json` records exact paths and HEAD comparisons.
No broad reformatting or legacy UI edits were performed. The full test/coverage
run remains active; no final global pass is established.

Four additional public source-inventory cases pass bounded capture assertions:
over 1 MB truncation, readable login/subscription guidance, and two challenge
interstitials. Capture availability is distinct from access to the underlying
document. `source-capture-current/REVIEW.md` records exact bytes/hashes and model
interpretation limits. These use BytesIO socket-layer doubles, not live TCP;
the earlier source-acquisition table was corrected accordingly.

The T02 numeric run found a confirmed optional-amount locale reparse defect and
a parentheses-format rejection requiring contract reconciliation. Those fixes
are being prepared in the primary checkout; the running frozen suite remains
unchanged and cannot be claimed to cover subsequent fixes without their own
verification and an explicit final source reconciliation.

### Passive Invoice Audit 0.1.4: three reproduced numeric fixes

All 16 fresh managed CLI cases now meet their explicit expected outcomes: nine
successful runs with sealed reports/disclosures, and seven expected input
rejections. The complete component test module reports 103 passed, one skipped,
zero errors/failures (`passive-014-full.xml`). The unsuppressed 24-file Mypy gate
and focused Bandit check also pass.

The fixes normalize every mapped monetary column under the reviewed number
convention, accept a single accounting-parentheses negative while rejecting
conflicting signs, and preserve explicit mapped gross zero rather than replacing
it with a fallback. Original failures remain preserved. The public output checks
include immutable source lineage, JSONL values and XLSX comparison amounts;
rendered workbook appearance and matched semantic-worker qualification are not
claimed. See `passive-numeric-current/REVIEW.md` and its exact 16-case matrix.

README and skill clarification followed the managed executions without changing
the algorithm. The reviewed privacy manifest was refreshed against final source.
Three Vera package builds and parity checks passed, including initialization
and tool listing for all 18 packaged MCP servers (`passive-014-packages.log`).
Exact source/package hashes and dirty inventory are in `passive-014-identities.json`. The frozen repository-wide suite predates these
Passive changes; its result must be reconciled with this explicit tested delta.

### Original case index and package-test follow-up

`CASE_OUTPUT_INDEX.md` now maps every approved A01–A08/L01–L08 case to retained
source and normal output evidence. It identifies actual missing L03/L04 case
reports despite valid source contributions, and stale A05/A07 metric pointers
that refer to older outputs instead of reviewed successors. These corrections
are in progress; prior evidence remains preserved. A01/A02/A08 still contain
the old alias-count defect in historical report bytes; narrowly corrected
successors are being prepared rather than claiming those files changed.

The post-Passive package/update suites completed: 378 passed, 12 failed, no
skips/errors (`passive-014-package-tests.xml`). Eleven failures show blocked
PyPI DNS during declared managed dependency setup. Exactly those eleven nodes
passed on retry with approved network access (`passive-014-package-network-retry.xml`).
Combined coverage of the two runs is 389 passing nodes and the single public
Clara notification-manifest failure; the original failures remain retained.
The twelfth is Clara public manifest 0.1.177 versus installed marketplace
0.1.180. No public version promotion or deployment was performed here.

Read-only inspection of the active task “Audit Clara pipelines and code” confirms
its owner is addressing the shared Variance test-import isolation and Clara
privacy assertion. This task does not duplicate those edits. Our frozen suite
precedes those owner changes; reconciliation must identify that delta too.

The native-host diagnostic investigation inspected CLI 0.153.4 help and offline
protocol documentation. No supported complete native tool-registration/dispatch
proof was found; prompt, MCP and feature metadata are insufficient substitutes.
`host-profile-review/diagnostic-options.md` records the precise limitation.
The supported-host claim remains unchanged; no bypass was introduced.

### Accounting corrected deliveries and financial report index

A01/A02/A08 now have fresh corrected Open Item 0.1.52 successors: counts1/2/1,
exact prior amounts and allocations preserved, assurance replay passed, 69
physical artifacts sealed per run, technical lifecycle completed. All 67
predecessor outputs per case retain exact hashes. A05/A07 metric references
are corrected in a new file; old metrics remain intact. `CASE_OUTPUT_INDEX.md`
contains the current overlay, with detailed receipts in
`accounting-report-corrections-current/REVIEW.md`.

`FINANCIAL_REPORT_OUTPUT_INDEX.md` maps 26 retained cases across six workflows.
It identifies a concrete Report Builder numeric-role review gap: a readable
draft still withholds all numbers. A new normal managed numeric-review/report
run is being prepared. Sales Plan needs its reader-facing explanation of sparse
months and unavailable amounts; normal CSV/JSON remains its correct format.
`ARCHIVE_FAULT_ACCEPTANCE_MAP.md` maps the retained 52 before/after boundary
cases to writes, flushes, file fsyncs, unlinks and journal writes precisely.

### Completed ON and numeric Report Builder deliveries

L03/L04 now each have a completed 19-artifact normal pending dossier plus a
fresh, source-linked candidate response. Six approved expected claims matched;
37 source/excerpt checks passed. No workbench/source professional acceptance
was fabricated. `bandi-l03-l04-case-output/REVIEW.md` records exact run identities
and preserved old hashes. The case index has a current overlay.

Report Builder's fresh controlled numeric review now seals 28 artifacts,
verifies eleven source literals and four aggregates across DOCX/Markdown/XLSX,
and preserves 19 old draft files. Totals are 380/350/2000/200 without double
counting. The six missing sections remain draft/pending, and preview tables
remain redacted; no full unredacted-table rendering is claimed. See
`report-builder-numeric-current/REVIEW.md` and the financial index.

The remaining original L02 numerical-year trap, general Quesito/planner/validator
normal workflow gap and AML technical lifecycle checks are now in progress.
These are specific missing evidence steps, not requests for renewed approval.

### L02 numeric-year trap and package scope clarified

L02's new managed successor preserves an explicit synthetic/unverified 2024
EUR999 memo and leaves the 2026 amount/difference null; no calculation runs.
Its normal blocked package and useful candidate comparison are sealed among
55 artifacts; old output hashes remain unchanged. Six bounded expectations
pass field/hash and authored-text technical review, not an independent
professional certification. See `inps-l02-numeric-history-current/REVIEW.md`.

Inspection of `test_configured_plugin_zips_match_repo_source` confirms the
passing package check compares every configured Codex ZIP name and byte entry
against its source-derived expected contents, including Clara. Thus the earlier
shared-source ZIP drift is not an unresolved result at that test snapshot.
Subsequent owner changes still require explicit delta reconciliation; published
manifest mismatch remains separate from source-package parity.

### General Q&A and AML delivery closure

The original general-Q&A scope now has a bounded actual planner→validator
execution on the approved historical-source reuse question: Prompt Optimizer
21 artifacts and Deep Research Validator 20 artifacts, each sealed/completed,
normal Markdown/DOCX and three claims linked to two unchanged native-text
sources. No current-law or numerical-conflict qualification is inferred.
`general-legal-communications-current/REVIEW.md` records exact contracts and
limits. The separate professional-communications assessor procedure is being
inspected for a supported local qualification path; missing retained evidence
is not automatically treated as a demand for user credentials.

The original AML and first successor now complete technically through the
normal API, preserving their five artifacts each and draft_for_review records.
A new successor `run_1712118c97371444f6af4f09` corrects the stale “two evidences”
scope to three original synthetic documents plus historical prior-review
context. Six artifacts sealed/completed, no professional decision or calculation,
substantive findings unchanged and all prior outputs preserved. This is an
authored case-output correction, not a newly inferred production defect.
See `aml-delivery-current/REVIEW.md` and `scope-correction/` receipts.

The root's fresh CUA inventory still reported the Mac locked. Earlier subagent
AX tab observations are retained only for their exact rendered review pages;
they do not prove the entire host is unlocked. A public canonical Vera-page
read returned a non-retryable web-tool safety refusal, captured in
`public-page-current/read-attempt.json`; no alternate fetch bypass was attempted.
The full frozen test/coverage process remains live, with at least one failure
marker now visible; final traces are still pending.

### Latest declared input/source correctness CI gate

Ran the exact current input-and-source-correctness job's four test files with
its committed coverage configuration: 295 passed, one opt-in skip, 84.52%
statement coverage against 80%. This includes Passive 0.1.4 after the frozen
full-suite snapshot. It covers the four declared kernels, not all Vera code.
XML parser individually reports 79%; the committed gate is aggregate.
`passive-014-correctness.xml`, coverage JSON/log and exact source/config hashes
in `passive-014-correctness-identities.json` retain this current delta evidence.
No tests or production controls were changed to obtain the result.

### Communications phases completed; concrete review presented

The canonical editorial qualification passed7/7 fixed product-reviewed cases
with zero false-ready. Actual separate qualification, generation, claim and
editorial sessions produced and recorded a source-limited no_publish candidate.
This is no longer a missing-runtime-operation blocker. Normal packaging
correctly refuses absent fresh acceptance for recommendation, editorial_value,
source_basis and studio_profile. No review event or final-ready claim is invented.

`general-legal-communications-current/communications-qualification-followup.md`
and `communication-review-matrix-it.md` retain exact evidence and the four
proposed decisions for digest71ab9db34dba37b8f237bf82eb11afde4be063c72742a0756c84bff6bc2c529f.
Root presented that exact matrix asynchronously and quoted canonical skill405.
The request is pending; accepted delivery of a question is not approval.
No prior user authorization was withdrawn. Full tests and the bounded T08
profile-mechanism audit continue independently.

### T08 remaining local mechanism identified and implementation authorized

Inspection distinguishes existing versioned boundary ID/model selection from
the absent selected-profile mechanism: launch, argv, canaries and replay still
consume global pins. `host-profile-review/IMPLEMENTATION_AUDIT.md` records exact
consumers and the bounded plan. Root authorized one immutable retained-legacy
profile in canonical semantic_review.py, strict shared resolution, independent
legacy envelope comparisons and tamper/unsupported-profile tests. No new current
host, feature change, runtime config override, canary or qualification claim is
authorized by this refactor. Version/privacy/package integration waits for the
source diff and tests. Thus another concrete local implementation step remains;
the overall goal is not at an external-only impasse.


## Restart: T08 profile integration

The existing goal remains active. Reviewed the actual before/after source diff and
independent host-profile-implementation/REVIEW.md: a single immutable retained-legacy
profile drives enforcement; no new host qualification or capability expansion.
All 13 captured legacy envelope fields and receipt shapes remain identical.
35 focused tests pass. Journal–Bank manifest is now 0.1.49; Journal–Bank and Passive
privacy records refreshed successfully. Broader current integration tests and all
three Vera package builds/checks are running. The older frozen full suite remains
live and has progressed beyond 48%; it has failure markers and is not green.
Its snapshot predates this change; current checks cannot be attributed to it.

Current T08 integration:430 passed/92 skipped. Skip inventory found91 Node-dependent
cases because that command omitted bundled Node from PATH; exact skipped nodes
are being rerun with Node (session54172). The one native Luna opt-in case remains
separate. All three Vera package builds and parity checks passed, with18 packaged
MCP servers initialized/listed. Exact hashes are in
host-profile-implementation/integrated-identities.json. Package/update suite
session47480 is running; full frozen suite43263 is beyond50%. Neither is claimed
green. No new approval, host qualification, merge or deployment was recorded.

T08 package/update integration finished:377 initial passes;11 DNS-dependent
failures retried with approved network and all11 passed. The remaining transient
source/ZIP byte mismatch passed its exact test rerun after current all-package
byte comparison returned no drift. Thus389 of390 nodes now pass across these
runs; the sole unresolved node is the previously identified Clara published
manifest versus installed marketplace version check. No release manifest was
altered to conceal it. Logs/XML remain in host-profile-implementation.

All91 exact Node-dependent retries passed (191.91s). Combined current
Journal–Bank/Passive integration:521 passed, one opt-in native skip. Both
current integration and package suites are terminal. Only the earlier frozen
full repository suite43263 remains running, last observed beyond52%. The goal
remains active; no broad user reauthorization is required to inspect its result.


## Current gates and frozen-suite delta after T08

Current configured Mypy passes all24 source files. Current Bandit severity gate
passes with0 medium/high,6 low,0 scan errors; workflow-registry generation check
and full Vera privacy validation pass. Exact output is
host-profile-implementation/current-gates.log.

The read-only integration-delta-post-t08.json records51 changed files,0 missing
and52 new files relative to the full-suite snapshot. All52 new files are docs.
Vera production deltas are Passive0.1.4 and Journal–Bank0.1.49 plus their privacy
records and generated bundles; current521-test integration covers these.
Clara owner changes include source/skills/privacy and a deck interpretation
script. Shared builder delta adds Clara to source-preserving ChatGPT packages;
current package tests cover the resulting source-to-ZIP behavior. Inspected
changed package tests now require actual Clara workflow/catalog/script bytes
rather than flattened card-only copy; Vera preservation remains tested.
Other-owner source acceptance must not be inferred from Vera tests.

The frozen full suite remains live; its failure traces are not available yet.
This delta records observed identities, not retrospective full-suite coverage
or a freeze of other active work.


## Post-profile packaged integrity verification

Both complete declared package-startup and Vera bytecode-integrity modules pass:
102 tests, zero skips/failures (27.93s), retained in
host-profile-implementation/packaged-boundary-tests.xml and .log. Inspected
coverage includes normal registered-server startup/tools listing, missing
runtime/configuration rejection, tools-list failure, unresponsive server,
inert bytecode acceptance, ambient import, unsafe entries and bytecode-named
symlink rejection. This verifies the current rebuilt implementation after T08;
it is separate from the still-live frozen full-suite session43263.


## Frozen full integration finished

Session43263 terminated with exit1. JUnit:9953 tests,9894 passed,29 failed,
30 skipped,0 errors;10109.624 seconds. src coverage79.50%, below required80%.
Final evidence:final-integration.xml,final-integration-coverage.json,
final-integration-failures.json and full log. This is the retained frozen
snapshot, not current-source evidence. Exact29 failed nodes are now being
rechecked against the primary checkout before assigning remaining fixes.
No full-suite green or goal completion claim is supported.

## Restart: completed full-run diagnosis and current package check

The frozen full suite is terminal, not running:9894 passed,29 failed,30 skipped,
9953 total,79.50290510006455% src coverage (80% gate fails). Its rounded display
must not be used as a passing result. Existing frozen source predates later work.

Five test files were corrected for existing source contracts: removed unused
UI write monkeypatch, current removed-theme wording, state-only select behavior,
shared assurance import path available during lazy calls, and exact packaged
serialization ownership after T13. No production UI was restored. The focused
corrected group passed17 tests. Evidence:test-contract-corrections-v2.xml/log.

The expanded current check has {'tests': 48, 'failures': 8, 'errors': 0, 'skipped': 0}; exact failures are retained
in resumed-current-recheck.xml/log. Seven failures concern Lucia or Clara; one
shared catalogue failure was subsequently addressed by regenerating the local
catalogue with build_catalog from canonical manifests. No publication manifest
was changed and no deploy was performed. Concurrent Clara edits prevent claiming
a stable all-product package snapshot.

With bundled Node on PATH, resumed-cowork-parity-with-node.log records Vera
source/directory/ZIP parity and18MCP startups passing; Lucia parity and4MCP starts
also pass. Clara manifest changed concurrently and fails package parity. The
local catalogue passes its canonical check. The initial no-Node check is retained
and is an environment failure, not a Vera runtime defect.

Coverage inspection shows global src omissions are dominated by slide modules
and old check_statements paths. No direct check_statements/period_aggregators
reference was found in the inspected Vera, Journal-Bank, Check Entries or Passive
source roots. This is a bounded search, not exhaustive reachability proof. The
original T09 explicitly distinguishes global src coverage from Vera plugin
coverage. Do not add arbitrary legacy tests or alter exclusions to manufacture
a passing total; retain79.50% as an unresolved global gate alongside the actual
84.52% four-kernel plugin result.

The subsequent exact configured-Cowork-source test passed (1 test,0 failures):
resumed-catalog-recheck.xml/log. The expanded48-test check therefore has an
exact passing successor for its shared catalogue failure; seven other-product
failures remain from that snapshot, subject to concurrent owner changes.

## Reviewed current privacy deltas integrated into Vera packages

Current public/privacy checks found two new stale fingerprints caused by shared
owner changes. Full delta review and precise disclosure correction are recorded
in PRIVACY_RECONCILIATION.md. The successor privacy/runtime suite passes72/72;
the current Variance layout export test passes1/1. All three Vera packages were
rebuilt and pass source parity, including18 packagedMCP startup/tool-list checks.
No deployment or publication occurred. Exact source and package hashes:
current-privacy-routing-identities.json. Logs:current-reviewed-vera-packages.log,
current-variance-layout.xml, current-privacy-runtime.xml.

Routing evidence was re-bound, not rerun: the current router and catalogue
SHA256s exactly match the ten-case evaluated inputs in ROUTING_EVALUATION.md.
The reviewed-results raw hash also matches; all ten completed cases retain
expected routing and clarification decisions and no invented completed action.
The existing limited R11 planning-usefulness observation remains. This removes
source-staleness doubt for these routing results; browser execution remains
a separate requirement.

## Shared-source projection reconciled after the frozen test run

Current-frozen-source-delta.json records112 changed existing files by exact
before/current hashes. This is a delta inventory, not an attribution of all
changes to Vera or a substitute for test coverage.

Inspected three changed shared chart modules. Vera's actual ZIP contains the
Variance-specific overlay of draw_waterfall, draw_charts_utils and
multidimensional_charts_prep. Exact packaged bytes match plugins/_shared/variance,
not plugins/_shared/vendor. Thus concurrent average/population/zero-value changes
in the latter two generic modules are not incorporated into Vera's Variance
module. No unrelated source was reverted or altered.

The relevant dedicated-overlay change forwards the existing selected font size
to fallback waterfall panels. It changes presentation, not amounts or data
selection. Existing targeted public chart tests pass11/11: waterfall, small
multiples, fallback and bottom-up mix cases. This does not prove native browser
layout. The package/source comparison is recorded in
current-variance-shared-projection.json; regression evidence is
current-variance-vendor-regression.xml/log.

The frozen worktree remains an exact source reference for the original global
run. No test process remains live there; it is not a reason to wait. All new
checks above ran against current primary source.

## Current sparse Sales Plan source reconciliation

Recovered prepare_sales_plan_case.py with the exact engine SHA256 in the old
sparse-period receipt (7dbf2ad57ea649f1726302a48033dc0f65d5b30f449466786e17e0ba7e7ae4a3).
The delta is the separately verified missing-metric correction: unavailable
discount no longer becomes zero; dependent totals stay unavailable and warnings
identify missing source metrics.

Executed the current public prepare_sales_plan_case API on the retained
synthetic source case into a new external output directory. Status is passed.
The sales_plan_scenario.csv, scenario_summary.csv and assumption_application_ledger.csv
are each byte-identical to their retained sparse-run versions. This preserves
the six scenario rows, sparse-month mapping and prior independently checked
amounts through the current engine. It is preparation API evidence, not a new
managed lifecycle or professional forecast approval. Original inputs and sealed
outputs are unchanged.

Evidence: sales-sparse-current-source.diff and
sales-sparse-current-replay/retained-comparison.json under
/private/tmp/vera-remediation-01a07083. The separate missing-discount managed run
already exercises the new unavailable-value behavior; no duplicate rerun was
needed for that unchanged current source.

## Blocked audit after completed current-source reconciliation

Three consecutive continuation checks found the same unresolved prerequisites
after the Sales/Business source replays and current privacy/package/chart checks:
no user confirmation of the exact communications matrix (review_log.events is
still empty), no newly qualified native host, no new browser-unlock evidence or
missing benchmark originals. No live test process is being awaited. Repeating
passing checks cannot close these requirements.

The goal is blocked, not complete. The immediate user action is review of
general-legal-communications-current/communication-review-matrix-it.md in the
external evidence directory. This confirms a synthetic no_publish decision and
its four exact scopes; no professional credential is requested. Prior approvals
for implementation and original case expectations remain valid. The complete
T01-T20 ledger, global gate failures and external-host/visual limitations remain
unchanged; approving this matrix alone will not establish all of them.

No deployment, merge or publication occurred. Current source changes, outputs
and the frozen diagnostic reference remain retained while the task awaits its
external prerequisites. Resume dependent communications packaging only after
a real user answer, using the existing exact contribution digest.

## User approval of synthetic communications test recorded

After the plain explanation of the Italian matrix, the user replied “Ok fine”.
Recorded four digest-bound decisions for the original contribution
71ab9db34dba37b8f237bf82eb11afde4be063c72742a0756c84bff6bc2c529f, limited to this
synthetic no_publish exercise. Reviewer label explicitly does not assert
credentials or adopt the proposed style as a real studio standard.

Normal package_communications produced six actual local artifacts, no reader
communication draft and no external action. The first manifest misleadingly
instructed retaining a completed outcome while validation remained pending.
Corrected that sentence in canonical package_communications.py to condition
completion on exact-package review and successful validation. Communication
component is0.1.9; Vera is0.1.209. Repackaged the unfinalized test package.
The contribution and prior semantic approval bindings remain unchanged.

Validation was executed and reports exactly: Fresh accepted review required
for: packaged_output. That acceptance was not fabricated. The former missing
four-scope approval is resolved; final package review is distinct.

Reviewed concurrent Business Planning undated operating-period changes: null
periods allowed only without a dated financial model, source-bound assumptions
retain their existing data classes, presentation displays undated and scrolls
actions. No new external/model-data path. Refreshed its privacy record and the
communications wording fingerprint. Shared update/receipt records changed only
with the new Vera manifest version and were refreshed without boundary changes.
Evidence:communication-approved-package-tests.xml, communication-approved-validation.log,
communication-integration-privacy.xml and communication-approved-integration.log.

### 6 September — Official Centrale Rischi corpus and empty-run correction

The user explicitly replaced the old-third-party-PDF recovery requirement with
correct documents from Banca d’Italia. Downloaded both official guides directly
from the source URLs recorded in `cr-official-current/acquisition.json`. The
new default `plugins/centrale-rischi-review/evals/gold_official_cases.json` covers
14 extraction cases, one negative control and 10 analysis cases; all 25 passed
on the downloaded documents. Numerical expectations are retained from the
reviewed official examples, not derived from this run's outputs. Three optional
commentary-review cases remain separately identified by the normal receipt;
this run establishes extraction and numerical behavior. The original extended
manifest is retained but no longer required for the official-document check.

Reproduced an independent code defect: an empty manifest returned
`deterministic_passed: true` with zero tests. The runner now rejects empty source
sets and corpora without cases before producing a success receipt. Added two
regression cases; corrected the existing missing-semantic-review fixture to
contain an actual extraction case. All 32 Centrale Rischi tests pass. The preceding
current-source batch passed 90 CR/Business/Privacy tests; the updated privacy
suite passed 28. Black and Isort pass on the two edited Python files.

Centrale Rischi version 0.1.8 / Vera 0.1.211. The privacy review confirms these
changes add no external data path: only manifest validation and selection,
source-document provenance, and benchmark instructions changed. Refreshed the
CR fingerprint and version-bound service fingerprints. No deployment occurred.

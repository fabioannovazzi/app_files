# Shared context privacy reconciliation — 6 September

This is an incremental engineering review of the optional `imported_names`
Studio Archive input binding. It is not a complete privacy-register pass or
professional certification. The full workflow skills, affected context consumers,
existing manifests and public model-data disclosures were inspected for the
records below. Neither component has local source changes relative to HEAD;
their shared assurance dependency changed.

| Workflow | Inspected behavior | Result |
| --- | --- | --- |
| Financial Analysis | `run_pack.py` and preparation writers use the hydrated context for path and run validation. `model_use.py:build_manifest` separately constructs source identities from artifact IDs and hashes; it does not copy imported names or the full context. Evidence reopening checks the named source bytes and records the reason. The public page describes prepared results followed by specific source reopening. | Existing disclosure remains applicable; fingerprint refreshed. All 24 financial-analysis tests pass. |
| Centrale Rischi Review | Inspector, runner and finalizer validate the managed context without projecting it into output. `centrale_rischi_core.py:build_model_context` separately selects calculated fields and bounded review populations. The public page documents the corresponding preview and post-calculation populations. | Existing disclosure remains applicable; fingerprint refreshed. The regression suite passes, including PDF intake and bounded-context checks. |

Neither inspected change adds a model call, network destination or connector.
The selected Codex/Cowork account boundary still applies when the model reads
the declared professional material; local calculation does not imply local-only
model processing or automatic anonymization.

Evidence under `/private/tmp/vera-remediation-01a07083/`:

- `privacy-reconcile-financial-analysis.log`
- `financial-privacy-regression.xml`
- `privacy-reconcile-centrale-rischi-review.log`
- `centrale-privacy-regression.xml`

The final validator output still identifies 18 stale records: bandi-agevolazioni,
check-entries, client-file-preparation, concordato-plan-review,
deep-research-validator, journal-bank-reconciliation, journal-sampling,
management-control-pack, new-client, passive-invoice-audit, previdenza-inps,
prompt-optimizer, registro-imprese-sari, report-builder, sales-plan,
variance-analysis, plugin-update-check and run-receipt-stamping. Their reviews
remain outstanding; the nonzero validator exit is preserved in the logs.

Earlier reviewed AML, Archive Organization, Business Planning and Open Item
changes are recorded in `SOURCE_INTAKE_FINDING.md`. Package rebuilding remains
outstanding until the remaining changes and privacy reviews are reconciled.

## Sales Plan and Variance Analysis follow-up

Both full workflow skills, context consumers, model-use builders, existing
privacy records and public disclosures were reviewed. Sales Plan constructs
its default model-use manifest separately from the managed context. Variance
Analysis uses a portable context projection for intake and review: it retains
the manifest filename and hash, not the hydrated `input_bindings` entries.
Consequently the new imported-name aliases do not enter that projection.

An initial reading confused the manifest reference with embedded entries.
The corresponding proposed disclosure additions were removed after checking
the shared contract and a real context file. No new external boundary or
alias disclosure is claimed. A strengthened existing intake regression now
supplies a hydrated binding with an alternate imported name and verifies that
neither the binding nor the alternate name appears in the persisted intake.

Both privacy fingerprints were refreshed. The selected Sales Plan and Variance
regression batch passed 28 tests, followed by the strengthened intake check.
Evidence: `plan-variance-privacy-regression.xml`,
`variance-import-alias-boundary.xml`, and the two corresponding
`privacy-reconcile-*.log` files in the retained evidence directory. The remaining
stale count is now 16; Sales Plan and Variance Analysis are removed from the
18-record checkpoint above. The complete register is still not current.

## Management Control Pack follow-up

Reviewed the complete workflow, all three managed CLI entry points, the current
numeric-input and report changes, model projection and receipt builders, and
the public model-data paragraphs in all five languages. The shared context is
validated but not copied into the calculated context. The numeric changes retain
missing/uncached values as unavailable, reject conflicting latest balances,
preserve all service detail locally and display undefined ratios explicitly.

The privacy record incorrectly described service rows as capped at 20. The
actual projection caps each section's `rows` at 60, `top_parties` at 20, and
customer rows additionally at the reviewed setting of 1–50. Corrected the record
to those observed bounds. The public page already describes bounded calculated
rows without the incorrect number and required no change. No new external
destination is introduced.

Refreshed the fingerprint. All 33 Management Control Pack tests pass, including
managed CLI execution, missing values, uncached formulas, conflicting balances,
undefined ratios and context-receipt validation. Evidence:
`management-privacy-regression.xml` and
`privacy-reconcile-management-control-pack.log` in the retained evidence
directory. Fifteen records remain stale after this checkpoint.

## New Client follow-up

Reviewed the complete New Client workflow, its changed inventory validator,
managed initialization, promotion, packaging and delivery entry points, the
existing privacy record and public model-data section. Promotion uses exact
validated input paths and upstream workflow identities; optional imported names
do not change its evidence authority. Packaging separately constructs portable
evidence references rather than exporting the hydrated binding population.

The current inventory validator accepts the candidate-aware column format only
when `category_status=candidate` and `category_basis=lexical_hint`. Updated the
upstream-integrity control to record that implemented boundary. The existing
case-data and public-source-research disclosures still apply. This engineering
review does not verify current legal sources or professional AML outcomes.

Refreshed the New Client fingerprint. The New Client domain and managed
phase-one handoff suites passed 123 tests. Evidence:
`new-client-privacy-regression.xml` and `privacy-reconcile-new-client.log` in
the retained evidence directory. Fourteen privacy records remain stale.
Client File Preparation has separate parser and handoff changes; its review
has started but is not complete and its fingerprint was not refreshed here.

## Client File Preparation follow-up

Completed the incremental review of the main workflow, changed fiscal and XML
parsers, inventory metadata, model-handoff projection, review payload builder
and managed entry point. The existing privacy record already describes candidate
classification status, extraction dispositions, reviewed text-hash-bound adapter
selection and bounded fiscal citations. XML bodies now retain separate local
positions and exact source-byte hashes; the model's XML anomaly projection still
selects opaque document references and anomaly details, excluding invoice-party
fields. The default handoff does not copy hydrated Studio Archive bindings.
The public New Client page covers the internal engine's model-data path.

Refreshed the fingerprint without inventing another destination or control.
The first suite run passed 60 tests but skipped 16 MCP tests because Node was
absent from PATH. Repeated with the existing bundled Node runtime: all 76 tests
passed, with no skips. No dependency was installed. The latter run exercises
review rendering, persistence, hash drift, transaction failure, reviewer
attribution and path protections as well as extraction and handoff behavior.
It does not establish native Cowork acceptance or real-client professional
qualification.

Evidence: `file-preparation-privacy-regression.xml` (initial skips),
`file-preparation-privacy-node-regression.xml` (76 passes), and
`privacy-reconcile-client-file-preparation.log` in the retained evidence
directory. Thirteen privacy records remain stale after this checkpoint.

## Answer Planner follow-up

Reviewed the complete Prompt Optimizer skill, question inspection, validation,
managed intake builder, existing privacy manifest and public model-data section.
The intake extracts the run ID and relative selected paths rather than copying
the hydrated context or imported-name bindings. The other current code change
uses `timezone.utc` in the benchmark timestamp helper with the same UTC output
semantics. No additional data class or external route is introduced by these
changes; the existing public-source research and selected generation-route
disclosures remain applicable.

Refreshed the fingerprint. All 48 Prompt Optimizer and FiscalPrompt benchmark
tests pass with the existing bundled Node runtime enabled. These are automated
contract/runtime checks, not fresh legal-source verification or model benchmark
executions. Evidence: `prompt-privacy-regression.xml` and
`privacy-reconcile-prompt-optimizer.log` in the retained evidence directory.
Twelve privacy records remain stale. Deep Research Validator has separate
source-fetching changes and remains pending its completed review.

## Answer Validator: DNS rebinding correction

Reviewed the current source extraction changes, managed context consumers,
source-fetching transport and existing disclosures. PDF page coverage and exact
byte/text hashes were already described by the record. The shared imported-name
field does not change the selected source inputs or review projection.

The network inspection found a security gap: URL preflight checked resolved
addresses, but urllib's later connection resolved the hostname again without
checking that second answer. Added dedicated HTTP/S connection handlers that
validate all connection-time candidates and connect to a checked numeric socket
address. HTTPS retains the original hostname through the standard TLS connection
implementation. Initial and redirected URL/port checks remain in place.
Environment proxies are disabled for this direct public-source route; the skill
documents research-tool or local-source acquisition for proxy-only networks.
This fixed address rule is justified by mechanically verifiable network access
control, not source-relevance or legal judgment.

Regression cases exercise the public `inspect_sources` path with public-to-
loopback DNS changes for HTTP and HTTPS, asserting no socket is created. A
positive HTTP case exercises the actual urllib handler and HTTP connection with
a simulated socket, verifies the numeric destination and original Host header,
and checks that an environment proxy cannot change the destination. These are
isolated transport tests, not live-network or certificate-server acceptance.

All 63 Answer Validator tests pass, with no skips. Updated the privacy control
and refreshed its fingerprint after the workflow note. Evidence:
`deep-research-transport-regression.xml` and
`privacy-reconcile-deep-research-validator.log` in the retained evidence
directory. Eleven privacy records remain stale; package rebuilds and the broader
integrated gates remain outstanding.

## INPS follow-up

Reviewed the complete INPS workflow, all managed context consumers, initial
intake construction, privacy record and public model-data explanation. The
component has no local source diff; its shared assurance dependency changed.
The entry points validate the selected input paths and output scope. Reporting
uses run identity and relative references without copying `input_bindings` or
the new imported-name aliases. The declared official research, optional
authenticated-tab capture and optional OCR-model download routes remain
unchanged. The public explanation still states that the full private case and
derived data may reach the selected model.

Refreshed the fingerprint. The case, portal export, portal capture, OCR and
download-confirmation suites pass with bundled Node available. These tests use
controlled evidence and simulated external boundaries; they do not establish
current portal permission, an actual INPS session, live OCR download acceptance,
or professional legal-source qualification. Evidence:
`inps-privacy-regression.xml` and `privacy-reconcile-previdenza-inps.log` in the
retained evidence directory. Ten privacy records remain stale.

## Registro Imprese/SARI follow-up

Reviewed the complete skill, shared managed-context helper, its stage consumers,
initialization, connector arguments, selected-field review projection, privacy
record and public model-data explanation. There is no local component source
diff. The shared binding change is used for input validation but is not copied
into connector arguments or the selected case review context. The existing
private-case, public topical research, conditional connector and optional OCR
download disclosures remain applicable.

Refreshed the fingerprint. All 47 component tests pass with bundled Node
available and no skips. Evidence: `sari-privacy-regression.xml` and
`privacy-reconcile-registro-imprese-sari.log` in the retained evidence directory.
No live connector call, rights-holder authorization assessment or current legal
source qualification was performed by this engineering review. Nine privacy
records remain stale.

## Bandi e Agevolazioni follow-up

Reviewed the workflow, changed radar code and issue-inventory schemas, application
packet projection, managed-context consumers, privacy record and public data
explanation. Gazette issue inventories are included in source-check snapshots,
review hashes and the readable report. Their public URLs, dates and inspection
notes are already described by the existing privacy controls. The application
packet selects application/project fields and reference-closed workbench data;
it does not copy the Studio Archive input bindings or imported-name aliases.
The Python 3.10 enum fallback introduces no additional data destination.

Refreshed the fingerprint after review. All three Bandi component test files
pass with bundled Node available; exact counts are retained in
`bandi-privacy-regression.xml`. The refresh log is
`privacy-reconcile-bandi-agevolazioni.log` in the retained evidence directory.
These checks do not establish live official-source coverage, actual model-session
isolation, or professional eligibility acceptance. Eight privacy records remain
stale; packaging and the broader qualification work remain outstanding.

## Shared-service review in progress

Reviewed the complete update-check client and hook, including its separate
feedback-status polling call. Version retrieval sends a fixed-URL GET and a
generic User-Agent; it does not include case content or installed version.
Feedback polling sends stored request IDs and status tokens and is separately
disclosed in the existing plugin-feedback service record. Refreshed only the
plugin-update-check fingerprint. Seven records remain stale.

The update, local report, receipt client and receipt API test batch passes;
see `shared-services-privacy-regression.xml`. Receipt review is not complete:
the client validates the initial endpoint but uses urllib's redirect-following
opener, which does not establish the stated fixed-destination control for every
request. Fix and test redirects before refreshing this record. Also clarify
that the generic Studio Archive report helper deliberately requests no server
attestation, while the Vera command retains automatic stamping. Existing tests
passing do not close these identified review findings.

## Receipt destination correction

The default receipt transport now installs a redirect-rejecting urllib handler
for both stamping and verification. Endpoint URLs containing credentials are
also rejected. Existing injected transports remain available for isolated tests.
Public-API regressions exercise the real urllib opener with a simulated HTTPS
transport for 301, 302, 303, 307 and 308 responses on both operations; each
asserts exactly one initial Mparanza request and no redirected request. A further
case verifies credential-bearing URLs are rejected before transport. Existing
API, report, retry and immutable-output tests remain green. Exact results:
`receipt-redirect-regression.xml` in the retained evidence directory.

Clarified the service record: automatic stamping belongs to Vera's command;
the generic Studio Archive helper intentionally creates local reports without
requesting attestation. Updated the fixed-destination control and refreshed the
receipt service fingerprint. Six workflow privacy records remain stale. These
isolated checks are not live-server deployment evidence; packages still need
rebuilding after the source changes.

## Check Entries review and regression in progress

Reviewed the workflow skill, changed bootstrap/core/MCP code, adapter, portable
context projection, case-context routing and public model-data explanation.
The portable projection retains run identity and manifest references rather
than copying input bindings or imported-name aliases. The cache changes are
already described by the inert-bytecode control; disabling local-server
injection does not add an external route.

Corrected contradictory skill instructions: pass the private review payload by
path rather than reading it into model context, use selected-case context for
the final response, and describe generated caches as inert instead of claiming
they are rejected. Refreshed Check Entries after these corrections. Five
workflow fingerprints remain stale.

The full Check Entries component regression is still running under exec session
63274, with results targeted to `check-entries-privacy-regression.xml`. No final
test count or pass claim is made yet. Resume observation of that same session;
do not restart merely because it is slow. Concordato review has begun: its
complete skill, current manifest, changed MCP/adapter, run-context consumer and
Italian public data section have been read, but its fingerprint is not yet
refreshed and its regression has not started.

## Concordato boundary review completed; tests pending

Completed the changed bootstrap/MCP/adapter and managed-context review. Context
loading validates the run and selected files; the runner passes run identity and
relative paths, not imported-name bindings, into the review. Existing inert-cache
and selected-review disclosures remain applicable. Clarified a contradictory
fallback sentence so it follows the existing instruction to use the delivered
semantic review and exact files needed for the question rather than suggesting
another complete payload read. Refreshed the Concordato fingerprint; four
workflow records remain stale.

The component and semantic regression suite is running under exec session 61908
and has reported a failure; inspect its final traceback and
`concordato-privacy-regression.xml` before claiming verification. Check Entries
session 63274 also remains live. Neither suite has been restarted. Journal–Bank
review has begun with its manifest and current semantic-review diff; its complete
workflow and remaining changed paths still need inspection before refresh.

## Concordato regression failure resolved

The completed Concordato run produced 124 passes and one failure, with no
skips. The failing test treated an empty `__pycache__` directory as an unowned
executable entry, contradicting the current inert-cache contract. Changed that
negative fixture to an unowned Python source file and added a separate public
MCP startup case accepting invalid, unused cache bytes. Both focused tests pass
in `concordato-cache-regression.xml`; no production behavior was changed to
satisfy this test. The original full-suite result remains retained as
`concordato-privacy-regression.xml`, not relabelled as a wholly green rerun.

Check Entries session 63274 continues to run. Journal–Bank's complete skill and
main semantic-selection/host-inspection diff have now been read; bootstrap,
projection and public-disclosure reconciliation still require completion.

## Journal–Bank boundary review completed

Reviewed the complete workflow, semantic worker selection and host inspection,
bootstrap, packaged shared-assurance path selection, context consumer and public
data explanation. The execution entrypoint passes run identity/root, not the
hydrated input bindings. The worker prompt contains the graph digest, matching
policy and selected candidate components; reviewer identity and benchmark digest
remain in the parent-side selection record. Current records already describe
the reviewed alternative-model and inert-bytecode controls. No new case-data
class or external destination is introduced by these changes.

Refreshed the fingerprint. All 18 focused generic-worker, host prerequisite,
selection-preservation and authorized-selection-input tests pass without skips:
`journal-bank-privacy-regression.xml`. This is not a complete Journal–Bank suite
or a fresh native worker qualification. The default host pins and canary checks
remain enforced. Three workflow privacy records remain stale: Journal Sampling,
Passive Invoice Audit and Report Builder. Check Entries session 63274 remains
live and has passed the 70-percent progress marker without a reported failure.

## Journal Sampling privacy review

Reviewed the full skill, sampling/core changes, bootstrap and MCP cache handling,
portable context projection, model-review builder, manifest and public model-data
section. The shared imported-name bindings are not copied into the persisted
portable context. The model-review builder preserves semantic sample evidence
while removing the declared technical controls. Stratified allocation now fills
the requested size up to population capacity and records its fixed seed; this
changes selected rows, not the declared data classes or external routes. Moved
its existing methodological explanation into Sampling Rules, where it belongs.

Refreshed the fingerprint. Focused stratified, cache and caller-context tests
pass; exact counts are in `journal-sampling-privacy-regression.xml`. Two privacy
records remain stale: Passive Invoice Audit and Report Builder. These checks do
not establish professional sampling sufficiency or full workflow acceptance.

Separate product-copy finding remains open: the public Journal Sampling page
still advertises text PDFs in input lists and examples, although the current
skill/parser refuses generic PDFs as movement sources. Correct those localized
descriptions before considering the public journey reconciled. The reviewed
model-data block itself describes the observed mapping/sample data path.

## Journal Sampling public input claims corrected

Corrected the page's static markup and all five localized input, preparation and
workflow descriptions to request Excel or CSV. The PDF rows now explicitly say
that text extraction does not make a PDF supported for normalization/sampling;
the input explanation requires an Excel/CSV export with reviewed mapping.
Retained print-style Excel examples because that bounded workbook adapter is
supported. Replaced the sample `.pdf` input filename with a CSV example.

The extracted inline JavaScript passes Node syntax validation and all seven
public-model-data copy tests pass (`sampling-page-copy-regression.xml`). This
closes the identified PDF input-copy contradiction in repository source; no
deployment or fresh browser layout acceptance is claimed. Check Entries session
63274 remains live without a reported failure at the latest observation.

## Passive Invoice Audit privacy review

Reviewed the full workflow, ledger parsing/evaluation and restart changes,
native selection adapter, audit/evaluation entrypoints, complete Cowork file
handoff, packaged agent and Cowork instructions, privacy manifest and public
data explanation. Runtime/model/review identity is bound to recovery; pending
Cowork requests remain incomplete. Model-selection evidence is not added to
the subordinate invoice prompt. Existing records describe the host-reported
identity limitation and bounded packet contents. Added the exact reviewed
decimal-format and missing-amount requirements to the main workflow instructions.

Refreshed the fingerprint. The complete component test file passes except its
explicitly opt-in real Luna integration test, which was not enabled; exact
counts are in `passive-invoice-privacy-regression.xml`. This does not close
native Luna or actual Cowork Haiku acceptance. Report Builder is the only
remaining stale privacy record. Check Entries session 63274 remains live.

## Complete privacy register reconciled

Check Entries finished with 204 passes and no failures or skips
(`check-entries-privacy-regression.xml`); session 63274 is now terminal.

Reviewed Report Builder's full workflow, layout-specific implementation contract,
bootstrap/MCP cache handling, workbook presentation changes, run-intake context
consumer, privacy manifest and public data explanation. The context supplies
run identity and relative output containment; imported-name bindings are not
copied into report intake. The existing manifest describes both full and
projected layouts and the bounded inspection/expansion path. Workbook styling
adds no model data or external destination.

The focused test batch found the same stale empty-cache rejection expectation
as Concordato. Changed its negative fixture to unowned executable source;
retained the existing real-Python inert-bytecode acceptance test. All 11 selected
implementation, workbook and model-context tests now pass without skips
(`report-builder-privacy-regression.xml`). Refreshed Report Builder after review;
the complete Vera privacy validator passes with no stale records.

This closes this register-reconciliation batch, not T01–T20. Generated packages
must still be rebuilt and checked; broader integration, professional source
acceptance and native-runtime requirements remain open.

## Rebuilt package verification in progress

Rebuilt Vera and Lucia Codex/Cowork packages from current source; Lucia shares
the corrected Deep Research Validator transport. All four builder drift checks
pass. Cowork checks initialize and list tools for Vera's 18 and Lucia's four
MCP servers. The complete Vera privacy register also passes after rebuilding.
Exact ZIP identities are in `reconciled-package-hashes.json`; build/check logs
use the `reconciled-codex-*` and `reconciled-cowork-*` names in the evidence
directory. An initial build lacked Node in PATH and stopped; the successful
builds used the existing bundled Node runtime, without installing dependencies.

The package/update/assurance integration suite is live under exec session 98203
and has reported a failure. Inspect its final traceback and
`reconciled-package-tests.xml` before claiming package integration completion.
Do not restart while that handle remains live. Nothing was deployed or published.

The suite is now terminal: 391 passes and two failures. Both failures are
extracted-Clara rendering tests whose fresh managed runtime could not resolve
pypi.org under the network sandbox. The exact two tests are rerunning with
approved host network access under exec session 95432, installing only declared
dependencies. Results target `reconciled-package-network-retry.xml`; do not
report those two paths as passed until the rerun completes.

Session 95432 completed successfully: both extracted-package rendering tests
pass with declared dependency setup available. Thus all 393 package tests have
passing evidence across the retained initial run and the two-test network retry.
No test or production code was modified to bypass the network failure.

A01 residual-request change review: inspected the two production edits in
build_missing_evidence_requests.py and audit_assurance.py. They select the
existing residual field for a generated request row/summary and record its
formula, retaining the existing bank reference. They add no source ingestion,
model-context route, endpoint, or transmission. The existing Open Item disclosure
continues to apply. Refreshed only that workstream fingerprint; validator reports
all Vera privacy surfaces complete and current. Log: a01-privacy-refresh.log.

A05 reviewed delta carries existing post-cutoff candidates into the targeted
request workbook through an exact record-id join. Date and source references
already present in the reconciliation review are retained in that generated
artifact; no additional source is read or endpoint contacted. Existing model
review of generated request artifacts remains the same disclosed path. Inspected
builder and raw runner wiring; refreshed only Open Item. Validator passes.

A06 reviewed delta preserves already generated supporting-bank references and
candidate descriptions in request output and suppresses invalid arithmetic in
accountant output. It uses the existing reviewed perimeter status; no new data
read, model-context expansion beyond existing review artifacts, or transmission
is introduced. Inspected both changed production modules and final XLSX action
text. Open Item fingerprint refreshed; validator passes (a06-privacy-refresh.log).

Journal-Bank explicit-list change reviewed: local matching reads the existing
mapped reference field and preserves source identifiers in the existing
shared_references output. It adds no source read, endpoint or model request.
The existing selected-case exact-identifier opt-in remains unchanged and was
used for A04 membership review. Both workflow skill/reference now describe the
list bounds and complete-membership requirement. Refreshed only Journal-Bank;
all Vera privacy records validate current. This is workflow-boundary evidence,
not a provider transmission attestation.

## Current shared-owner integration review

Compared current canonical source with the retained frozen integration tree.
Variance changed only its plugin version and legacy_plotting.py within that
component: extra right margin for outside labels and waterfall font-size metadata.
The complete workflow and prior bounded model projection remain applicable;
no input selection, context population, source reopening or external boundary
changed. Refreshed the Variance fingerprint after this review.

The managed-runtime delta adds CODEX_THREAD_ID presence alongside CODEX_SANDBOX
when selecting the existing private temporary cache. It does not use the ID value
in the directory or network request. Published dependency selection, private
write probe, generation lock and atomic activation remain unchanged. Updated
the service retention description to cover approved and sandboxed commands
resolving the same cache, then refreshed its fingerprint. No credentials or
client materials are introduced to this setup path.

Current public/privacy suite:208 passed,1 stale-register failure. Its exact
successor privacy/runtime suite passes72 tests after review. Evidence:
current-public-contracts.xml, current-privacy-runtime.xml,
current-privacy-routing-identities.json and current-*-privacy-refresh.log in
/private/tmp/vera-remediation-01a07083. This is local source-contract evidence,
not live-site deployment or rendered browser acceptance.

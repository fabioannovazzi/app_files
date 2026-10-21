# Studio Archive layer interaction audit

Date: 2026-10-21. Scope: the current working tree, before restarting Test 1.
The initial inspection and isolated fault-injection exercise were not normal-chat
acceptance and changed no production code, customer records or installed plugins.
Subsequent authorized source repairs are recorded below. Disposable archives were created under `/private/tmp`
and removed when each probe ended. No model or server request was made.

The four original requirements remain the criteria: selected-work execution,
durable identity across sessions, discovery independent of indexing, and fault
isolation. Earlier acceptance on an older version does not establish the new
Codex-and-Cowork campaign's acceptance.

## Observed: remaining boundary violations

### L01: selected preparation still depends on unrelated folder metadata

`archive_core.prepare_studio_client_workflow` loads configuration, obtains a
current view of all top-level scopes, synchronizes identities and searches
across clients for the engagement. `_discover_top_level_scopes` inspects every
top-level entry. Its `is_symlink()` call can raise before its subsequent
`lstat()` error handler; the latter also aborts the whole discovery on failure.

Probe: create a valid selected client, engagement, imported CSV and prepared run;
then inject EACCES only for metadata reads of a different top-level folder.
Repeat preparation of the same selected engagement and input.

Observed output:

```json
{
  "baseline_status": "prepared",
  "selected_preparation_blocked": true,
  "error_type": "PermissionError",
  "selected_run_still_readable_directly": true
}
```

This violates the original execution/discovery/fault-isolation boundary even
though the content-index refresh dependency has been removed. It establishes
the behavior under an injected filesystem failure, not the frequency of that
failure on users' computers.

### L02: reporting failure obscures an already committed lifecycle transition

`client_ledger._write_run_status_locked` writes terminal `run.json`, then calls
`finish_report`. A local reporting exception propagates after the durable write.
This differs from `_readable_after_write`, which explicitly returns a successful
mutation alongside an unavailable navigation status.

Probe: use the real ledger to create and start a disposable run; inject an
`OSError` from the reporting finish operation; call public `fail_run`.

Observed: the call raises `OSError`, but independent ledger readback returns
`status=failed`. Reproduced with two distinct runs. This proves ambiguous
operation outcome at the reporting handoff. It does not show a failed server
stamp blocks calculation: `stamp_report` already returns `pending` for expected
network/receipt failures.

### L03: one report recovery failure prevents independent recovery work

`client_ledger.retry_reporting` processes terminal transitions in a loop without
per-run exception isolation. Only afterward does it call `retry_pending`.
The caller catches failures around the entire recovery pass, protecting the
selected operation but skipping the rest of the report recovery work.

Probe: register two real, terminal disposable runs as awaiting recovery; inject
a reporting failure on the first finish call and provide a successful second
response. Replace network receipt retry with a recording mock.

Observed output:

```json
{
  "eligible_terminal_runs": 2,
  "terminal_reports_attempted": 1,
  "pending_receipt_retry_called": false
}
```

This extends the original invalid-run isolation problem into the reporting
layer. Recurrence can prevent later recovery attempts while the first failure
persists; no live receipt queue was changed or exercised.

## Observed: incomplete cross-layer contracts

- Intake: `check_studio_import_sources` explicitly returns
  `direct_chat_attachment_import_supported=false`. It checks reachability and
  optional source hashes on the importer host; it does not transfer cloud
  attachments. The ordering before client/engagement creation is expressed in
  instructions and tool descriptions; creation and checking remain independent
  APIs. A usable folder-transfer path still depends on host capabilities.
- Host instructions: the Cowork build rewrites the Codex client-workflow section
  in `scripts/build_claude_plugin_zip.py::_project_main_cowork_scope` and also
  supplies a separate `COWORK_EXECUTION_CONTRACT`. Workflow ordering therefore
  has multiple maintained definitions. This is an inspected drift risk, not a
  claim that every current generated instruction is wrong.
- Report delivery: `archive_reporting.snapshot_run` creates files and returns
  `display_markdown`. Vera's skill separately tells the agent to display that
  text in its final response. File creation and final chat display are distinct
  handoffs. This audit did not establish reliable visible delivery in both hosts.
- Tool responses: `archive_emission_mcp.cjs` records before forwarding a request
  and again after the child returns. A failed outgoing recording substitutes a
  generic withheld-response error after the child has executed. The inspected
  bridge does not include a committed-operation result in that error. This is a
  further outcome-ambiguity risk; no mutating MCP case was reproduced here.
- Identity verification: `archive_report_receipt.stamp_report` compares current
  credentials with the report's userID, and `verify_report` accepts an expected
  userID and checks the exact server proof. Their presence is not acceptance
  evidence for the deleted Test 1 run or either host's replacement run.

## Observed: repairs that remain supported

Three existing regressions passed in this audit:

- `test_new_session_recovers_root_identity_and_engagement_without_setup`
- `test_approved_root_change_keeps_existing_session_pinned_and_aliases_separate`
- `test_other_sessions_can_create_and_resume_without_full_index_refresh`

They were run from the repository's activated `.venv`, using the adoption and
concurrency test files. Exit status was zero, with all three passing. These are
fresh-process/source checks, not Codex or Cowork UI acceptance.

Source inspection also confirms independent ledger collection inspection and
separate navigation failure reporting. Those repairs do not automatically cover
top-level discovery or report-recovery loops.

## Diagnostic interruptions retained

- The first reporting probe omitted a selected input and was rejected with
  `Every workflow run must select at least one exact input.` The fixture was
  corrected by importing one synthetic CSV. Production validation was unchanged.
- The first folder probe caught `ArchiveError` only. The injected metadata
  failure propagated as `PermissionError` from `Path.is_symlink`; its traceback
  already demonstrated the selected-operation failure. The repeated probe also
  caught `OSError` so it could report direct ledger readback afterward.

## Inference and limits

The original diagnosis remains supported: some selected operations still depend
on unrelated state, and failures cross boundaries inconsistently. Several
repairs work, but the four architectural requirements have not been applied
through every layer. This does not establish that Studio Archive is beyond
repair, nor that every observed host denial was a Vera defect.

No replacement Test 1 was started during this audit. The latest retained failed
Test 1 report documents successful deterministic reconciliation followed by host
approval rejection of the semantic-worker launch. The user subsequently granted
the scoped synthetic-data authorization and deleted that chat. Those facts are
separate from L01-L03. Both-host automatic report delivery and independent
correct-user server verification remain required and unproven for a replacement
run. The overall goal remains incomplete.

## Authorized repair phase

The active goal authorized continuing from the reproduced failures. Existing
archives and installed plugins remain unchanged. Source changes now implement:

- L01: scope inventory catches each entry's metadata failure, reports it as an
  unavailable scope, and continues through healthy siblings. Case-insensitive
  name collisions are likewise isolated to the affected scopes. Fresh-session
  configuration and discovery preserve the incomplete-inventory indication.
- Already selected folder access and engagement preparation now obtain stable
  IDs from the portable client manifests. They no longer synchronize or require
  the entire private alias registry. Two regressions retain a malformed unrelated
  alias record byte-for-byte while selection and preparation succeed. Duplicate
  portable identities remain unavailable, and selected manifests are validated.
- L02: terminal lifecycle acknowledgements distinguish saved run status from an
  unavailable privacy report. Failure before snapshot generation retains the
  previous report bytes; an interrupted multi-file generation remains pending
  and must not be claimed as a final report. Repeating the
  terminal operation recovers reporting without repeating calculation or adding
  another lifecycle transition. A changed sealed professional output still
  prevents initial completion.
- L02/L03: local report generation and resealing now finish before the run is
  removed from the unfinished-collection queue. Previously a failure after queue
  closure could leave receipt retry unable to finish the local report.
- L03: each recovery attempt isolates its own expected failure. A small auxiliary
  SQLite table orders attempts so persistent failures do not monopolize the
  three-entry batch. The existing queue and report bytes are retained. Selection
  is restricted to the relevant client before applying that batch size, and
  unreadable transition metadata does not hide other eligible transitions.
- CI now includes `test_archive_reporting_recovery.py` in the existing automatic
  reporting job, retaining its coverage threshold and source-quality checks.

Focused results: 12 reporting recovery checks initially passed; 24 Archive fault
isolation checks subsequently passed, including the private-registry independence
cases. A broader 198-case run found one obsolete text assertion in the existing
symlink import regression. The import was correctly rejected with the new typed
`source_path_is_symlink` error. The test now checks that code, the retained
engagement ID and the preserved link; the corrected test passes. No import
behavior was changed to satisfy that assertion.

The first recovery test run used stale generated reporting copies under
`plugins/vera/scripts` before shared-source synchronization and reported five
failures. Running the existing `sync_reporting_runtime.py` build step synchronized
the source copies; the 12-case rerun passed. This build-order mistake is retained
as a diagnostic block, not attributed to deployed Vera.

The expanded combined regression run passed **238 checks**, with five existing
SWIG deprecation warnings, in 54.31 seconds. Its output is retained at
`/private/tmp/vera-layer-boundaries-regressions-final.log`. Black and Isort checks
passed for all seven changed Python source/test files; Mypy passed the four
changed source modules; Bandit reported no medium/high findings there.

### L04: a withheld response previously obscured whether a tool had run

The bridge risk described above was converted into two executable regressions.
One recording failure happens before forwarding to a child; the other occurs
after a child saves a disposable file and returns its response. Both initially
failed the required transport-state acknowledgement, recorded in
`/private/tmp/vera-response-handoff-before.log`.

`plugins/vera/scripts/archive_emission_mcp.cjs` now distinguishes
`before_tool_start` from `after_tool_return`. It returns the operation name and,
when available, the validated opaque run ID, with separate recovery directions.
A returned tool response does not prove every requested mutation committed, so
the message says work may already be saved and directs inspection of the
existing result before repetition. It does not claim a completed background job.
The case response remains withheld when recording fails.

The complete emission-boundary suite passed **24 checks**, with the same five
SWIG warnings, in 4.49 seconds. The regressions verify the child saves once in
the post-return case, does not run in the pre-start case, and neither response
reveals the unrecorded case content. Output is retained at
`/private/tmp/vera-response-handoff-after.log`. Node syntax, test formatting,
import ordering and shared-reporting source synchronization checks passed.

This repair pass therefore has **262 passing checks** across the two suites.
Package rebuilding and installed-host verification remain pending. Remaining
audit work includes private alias discovery under damaged state, whole-root
discovery availability, host instruction consistency and visible report delivery.
These source checks do not establish native chat acceptance.

The acceptance ledger now records the deleted 0.1.469 chat as a retained failed
attempt, with the later user authorization and outstanding independent server
verification. It no longer falsely labels that chat as running. No replacement
test was created. The Cowork replacement-dialog timeout remains an unverified
installation state, not a passed native workflow.

## Second repair pass: discovery, recovery and delivery contracts

### L05: private alias discovery still treated one bad record as a global failure

The original selected-ID repair did not repair ordinary client listing or name
resolution. Four fault probes initially failed in
`/private/tmp/vera-discovery-boundaries-before.log`. Private alias reads now
isolate malformed records, preserve all original bytes and expose
`identity_registry_complete: false` with issue metadata. Whole malformed files
likewise leave portable client identities discoverable. Conflicting opaque
identities are excluded; readable exact aliases remain available. No-match
results with unreadable aliases explicitly return `resolution_status: incomplete`,
not evidence that a new client must be created.

Ordinary discovery joins valid aliases with portable identities without taking
the identity write lock or rewriting the registry. Explicit identity changes
and recovery retain validated, serialized writes. Legacy session aliases can
still migrate once to the approved private profile. A metadata permission error
before the partial reader was a further reproduced defect; it is now handled by
that reader rather than mistaken for a missing registry to overwrite.

### L06: fresh-session recovery still required whole-root enumeration

Known selected work now survives a root-listing permission error. A complete
observed directory is cached in root-specific private profile storage; incomplete
observations never replace it. Its cache write is optional and does not wait for
an alias mutation. New sessions can reuse these previously observed locations
while reporting `directory_complete: false` and `known_scopes_only: true`.
Selected manifests, input receipts and run dependencies still validate against
the actual filesystem. Cached locations cannot authorize a changed client ID or
escape the approved root.

Regressions cover current and fresh sessions, changed portable identity, an
invalid cached parent-relative path, a failed optional cache write, and a read
that must not acquire the identity write lock. Existing archives were not used
as fixtures. No cached folder hint is treated as an input receipt or current
complete inventory.

### L07: the final-answer instruction named a nonexistent report field

The selective-reporting reference instructed the agent to display
`vera_reporting.display_markdown`. The actual terminal lifecycle response returns
`reporting.display_markdown`; `vera_reporting` is active collection metadata.
Three public lifecycle probes (completed, failed and cancelled) followed the
documented field and failed. The reference now points to the actual response.
The probes compare that exact delivered field with the saved Markdown and same
run ID. A Cowork package-projection regression checks that the host build retains
this same instruction. This mismatch is established from source and executable
probes; it is not proof of the cause of the deleted native chat's final answer.

Instructions now distinguish saved work from a pending local report, prescribe
retrying that same report/run, and prohibit describing an older draft as the
missing final report. They also explain partial client discovery so agents do
not create duplicates after incomplete lookups.

### L08: Gmail identity operations still depended on document-index refresh

Both Gmail query planning and exact header matching rejected any change to the
top-level scope set until a document-index refresh. An unrelated new folder
reproduced both failures. They now use current folder identities without opening
the document index. A renamed client retains its identity and aliases and can
be planned immediately through its new scope. An obsolete scope still cannot
select another client. Header matching reports unavailable identity evidence
instead of claiming automatic routing or failing with a missing-scope lookup.
No Gmail connector was called in these tests.

Incomplete alias evidence still prevents automatic email assignment because
unique ownership cannot then be established; healthy candidate evidence remains
visible. This is a specific cross-client attribution constraint, not an index or
maintenance gate. Separate regressions preserve this behavior for unreadable
aliases and a removed client folder.

Index refresh itself also committed its index before attempting mandatory global
alias synchronization. A damaged alias therefore made a successful index write
appear failed. Refresh now returns its committed result alongside partial alias
discovery. Explicit pointer repair remains an independent operation.

### Verification and blocks during the second pass

- Initial discovery probes failed as expected. The first expanded run found a
  genuine regression: read-only alias access had bypassed the private-profile
  separation check. That check was restored before profile access; the original
  regression now passes.
- Two existing whole-result expectations needed the new diagnostic fields:
  optional cache status and identity/directory completeness. Only those test
  expectations changed; permission and preservation assertions remain.
- `/private/tmp/vera-discovery-delivery-contract-before.log`: four failed, two
  passed. Failures were the three incorrect report-field lookups and alias
  metadata access. After repair, the full recovery/fault suites passed 52 checks.
- `/private/tmp/vera-gmail-index-boundary-before.log`: three reproduced failures
  (planning, matching and post-index alias synchronization). After repair, the
  fault-isolation and Gmail suites passed 62 checks. An existing rename test
  now verifies successful planning before refresh instead of requiring the
  defective refresh gate.
- `/private/tmp/vera-architecture-boundaries-source-final.log`: **330 passed**,
  five SWIG deprecation warnings, 26.67 seconds. Includes automatic reporting,
  terminal recovery, finalization, fault isolation, adoption, concurrent sessions,
  customer ledgers, readable navigation, Gmail, emission boundaries and report
  display/reopening tests. Mypy passed all four changed core/reporting modules;
  Isort, Bandit and both changed JavaScript syntax checks passed.
- Remote comparison initially returned 404 for a local-only commit. Fetching
  `origin/main` established the merged runtime release at `a5fa6d4b4`. Its runtime
  sources are retained; the clean, previously unchanged packaged-preflight test
  was updated from that revision to expect scoped temporary-copy cleanup.
- The first package preparation stopped at Black formatting of the new Cowork
  projection test. Formatting was applied before restarting the build. Icon
  generation changed zero files; all three icon checks passed.

The new source candidate is Vera **0.1.470**, Clara **0.1.336**, Lucia **0.1.161**,
with Studio Archive **0.1.65**. The shared reporting/Archive changes require
rebuilding all affected host packages. Build, package checks and installation
results are recorded separately below when completed. No normal-chat workflow
was restarted during these repairs, and no installed host was updated.

### Candidate build review and additional interruption probe

The first 0.1.470 build stopped on stale source-privacy fingerprints. The
privacy-surface-review process inspected the changed local cache, discovery,
report recovery and delivery paths. The Archive inventory descriptions now
cover partial alias metadata and known-folder recovery. The reporting service
record distinguishes committed lifecycle state from pending or partially written
report files. No new hosted recipient or receipt payload field was introduced.
Twenty affected source review records were refreshed individually; all three
product registers then validated.

The next build stopped on stale generated course bindings. The maintained course
builder regenerated 58 workflow kits and 258 localized kits, with no missing
translations. A structural JSON comparison established that the generated course
changes were source SHA-256 bindings and index SHA-256 values, not teaching
content. This made four course/onboarding review fingerprints stale; those four
metadata-only updates were reviewed and refreshed. The third build failure is
retained separately from a product execution failure. No new tutorial was run.

Two review-scope inspection commands incorrectly assumed Clara used the same
Archive/onboarding record names as Vera and returned FileNotFoundError. The
inspection was corrected to use each product's actual registry. A process-list
inspection was denied by the sandbox; the build was followed through its own
execution session and output log instead. These are audit-harness stops, not
customer workflow outcomes.

An additional public lifecycle probe interrupts the Markdown write after the
terminal JSON is saved. The saved lifecycle remains acknowledged and reporting
returns unavailable. Retrying restores Markdown and seals the same JSON bytes
without recalculating or altering the professional artifact. This probe passed.
It establishes the tested partial-write recovery; it is not a multi-file atomic
write guarantee.

### Final source and build verification

A follow-up migration probe found that an inaccessible legacy alias file was
incorrectly reported as a complete alias inventory. The shared-file branch was
already handled, but the legacy-file metadata check was not. Both branches now
return an unavailable-identity issue while retaining healthy portable clients.
The before/after evidence is in
`/private/tmp/vera-legacy-alias-metadata-before.log` and
`/private/tmp/vera-architecture-boundaries-final-additions.log`: the final focused
set passed **102 checks** with five SWIG warnings in 9.03 seconds. The Gmail
regression module is now included in the existing Archive session CI job.

The automatic-reporting CI selection passed **293 checks**, with five warnings,
in 149.65 seconds and **84.88% coverage** against the 80% threshold. Its log is
`/private/tmp/vera-architecture-470-reporting-coverage.log`. Source formatting,
import ordering, Mypy, Bandit and JavaScript syntax checks passed. These are local
checks, not evidence that hosted CI or the installed applications passed.

The final all-host build passed at 0.1.470 / 0.1.336 / 0.1.161, followed by the
complete all-host source-parity check. Logs:
`/private/tmp/vera-architecture-470-build-final-reviewed.log` and
`/private/tmp/vera-architecture-470-parity.log`. The Vera Codex ZIP SHA-256 is
`f318924b5aad34bea08899629d43778007b6dcfd489b994c16a7e433158ddcb1`.
The prepared local distribution has the same 2,187-file inventory; installation
has not yet occurred. The live local enabled inventory still reports Vera
0.1.469. Its remote-catalog lookup was unavailable in the sandbox, so that
inventory observation is scoped to the local installation.

The broad package test command mistakenly used `--confcutdir=tests/plugins`,
excluding `vera_workflow_workspace` from `tests/conftest.py`. The affected Cowork
artifact-emission test passed when rerun without that exclusion (1 passed in
21.96 seconds). No production edit was made for this test-harness error. The
remaining broad suite was still running when this entry was written.

The authorized coordination message could not be delivered because the other
release chat was archived. It was not unarchived or otherwise changed. Version
reservation is recorded here and in this campaign's acceptance ledger.

The broad package suite finished with **638 passed, 2 skipped, 1 setup error**
in 819.03 seconds. The only error was the excluded shared fixture described
above; its corrected rerun passed. The two skips concern absent local curated
Marketplace installations, not a native workflow acceptance result. The full
package log is `/private/tmp/vera-architecture-470-package-checks.log`; the
corrected case is `/private/tmp/vera-architecture-470-package-fixture-recheck.log`.

The verified 2,187-file local distribution was installed with the supported
`codex plugin add vera@mp-vera --json` command. A subsequent inventory check
confirms Vera 0.1.470 enabled as `vera@mp-vera`; no duplicate installation error
was reported. Inventory evidence is
`/private/tmp/vera-architecture-installed-470.json`. This parent chat's older
exposed catalog is not evidence of fresh-session acceptance.

A new projectless GPT-6.1 Sol chat was created for Test 1:
`01a15ebd-6900-7952-93cf-604632959234` on host `local`. Its prepared prompt is
`/private/tmp/vera-cross-host-test01-codex-470-prompt.txt`. The first status snapshot
confirms the chat is actively checking the exposed installation and Archive
identities. It must stop at the first new failure. No previous deleted test chat
was resumed, and Cowork remains pending. The available chat tool creates a
separate chat; a separate native window was not verified.

Automatic visible delivery, reopening without recalculation, accounting output
correctness and independent live correct-user server verification are still
pending for this replacement run. The overall 13-pipeline goal remains active.

## Follow-up after the combined implementation merged

The user stopped the replacement test and paused this review while the other
implementation finished. PRs #887 and #888 were then merged. The subsequent
instruction authorizes repairs and deployment, explicitly stopping before any
Codex or Cowork acceptance test is restarted. This phase begins from clean main
`3957f0003406c8bcf7795dc8ccfcea3fb1c16df6`; production was independently observed
at that same revision. The 13-pipeline acceptance goal is not complete.

Four remaining source defects were confirmed:

- Ordinary selected operations synchronously recovered unrelated runs belonging
  to the same client, taking their engagement/report locks and making server
  calls before the requested work. Recovery now selects the exact client,
  engagement and run path before applying either recovery queue's batch limit.
  Operations without a selected run do not initiate unrelated recovery. Explicit
  maintenance can still process the independent bounded queue.
- Failure and cancellation used the execution loader, so missing or changed input
  bytes prevented recording the failure itself and generating its final report.
  A shared metadata reader now validates the sealed client/engagement/run/input
  manifest and context identities without opening execution input bytes. Only
  failure, cancellation and already-terminal reporting recovery use that reader
  alone. Execution and completion retain complete input and artifact checks.
  Run ownership now also compares the requested run ID with its manifest.
- JSON arrays or objects in a run status raised an uncaught TypeError outside
  per-record isolation. Mechanical type validation now returns the existing
  invalid-record result. Equivalent enum fields and artifact-record shapes have
  explicit type checks; damaged records remain unchanged and healthy siblings
  remain visible.
- Exact alias lookup could label a damaged portable client as registered and
  the result complete. It now carries the same blocked-record and directory
  completeness evidence as client listing, retaining a known alias as evidence
  without representing the folder as usable.

The initial focused regressions reproduced eight failures, with one already
passing null-status case (`/private/tmp/vera-recovery-boundaries-before.log`).
The first repaired two-suite selection passed 68 checks. Expanded regressions
include sibling receipt isolation, exact engagement/run recovery, retained report
recovery after input loss, and rejection of completion with damaged inputs.
The expanded Archive selection passed **189 checks**, five SWIG warnings,
in 14.96 seconds (`/private/tmp/vera-recovery-boundaries-regressions.log`).

One wider command named nonexistent adoption/concurrency test files and collected
no tests. It was corrected to the repository's actual test names; production code
was not changed for this harness mistake. The source type and security checks
passed for the four changed implementation modules.

Candidate versions are Vera **0.1.473**, Clara **0.1.338**, Lucia **0.1.163** and
Studio Archive **0.1.66**. The privacy-surface review inspected the changed recovery
selection, identity-only lifecycle reader, error projection and unchanged server
transport. There is no additional recipient, server payload field, document
transmission, model call or professional approval. Twenty-three affected source
review fingerprints were individually refreshed after inspecting their governed
paths; course changes regenerate source bindings without changing teaching
content. The three product privacy registers validate. Build, broader coverage,
hosted CI and deployment evidence are recorded separately when complete.

No normal-chat test, installation acceptance, Marketplace publication or live
test receipt verification is performed by this follow-up phase.

The first automatic-reporting coverage run passed 302 checks but found one test
still invoking the private client-level lookup to retry unrelated reports. That
expectation conflicts with the repaired recovery boundary. The test now resumes
the exact completed run through the public completion API. It passes while
retaining authenticated server proof, unchanged report/professional-output bytes,
signature verification, wrong-user rejection and altered-report rejection. No
production behavior was changed to satisfy the old assertion. Reporting coverage
was 84.67%; the complete selection is being repeated with the corrected test.

All three product builds completed with matching Codex, Cowork and Antigravity
versions. The generated course changes were checked to affect source bindings
and their indexes only. The public OpenAI published-version manifest is unchanged.
Final package validation, hosted CI and production verification remain merge and
deployment requirements, not substitutes for the stopped acceptance campaign.

# Vera workflow continuity audit

The requested outcome covers every Vera workflow, with Studio Archive as the
shared persistence boundary. Resolve prerequisites before dependent work,
retain passed startup choices, and recover operational failures without losing
work or restarting the user's job. An archive destination may be a general
folder such as Vari; its internal ID is software-managed, not a professional
identity or an automatic request for client onboarding.

Current status: the 55-route source audit, corrected local regressions and final
all-host package parity checks are complete. Draft PR #924 is under CI review.
Its first CI run exposed three implementation defects and several test setup/
expectation issues, repaired in `42b853a66`. The second run confirmed the Windows
Treasury recovery repair and exposed Windows newline expectations in CLI tests.
Earlier pending
lists below are chronological findings, superseded by the later results.
Source/package checks do not establish all-workflow live professional or
installed-host acceptance.

## Inspected defects

| Boundary | Observed behavior | Required result | Status |
| --- | --- | --- | --- |
| Prepared inputs | Both the shared worker context loader and Archive ledger reread original sources and receipts after copying verified inputs into a run. Losing an original interrupts a still-valid execution copy. | Consume the admitted copies and retained provenance; verify current execution bytes without reopening settled source admission. | Reproduced before repair; focused regression passes |
| Reporting at start | Archive saves running status and then lets report initialization/status-write exceptions escape. | Acknowledge the running job, expose reporting as a separate recoverable issue, retain the same run. | Reproduced before repair; focused regression passes |
| Archive destination | Creating a folder always returns a new-client onboarding handoff. | Allow an explicitly selected general destination without starting professional onboarding. | Implemented in Python/CLI/MCP; general-folder regressions pass |
| Selected run lookup | Lifecycle APIs rediscover the archive/client for each operation. | Persist and recover the established job binding across helpers and service sessions. | Owner-private exact run binding implemented; lost-session-configuration regression passes. Cross-process coverage pending. |
| Storage interruption | All execution copies and progress resided under the destination's client folder. | Preserve recoverable progress independently and support verified continuation/delivery to an available authorized location. | Independent private checkpoints, exact input repair and resumable restore implemented; eight targeted recovery checks pass. Engine relocation review remains incomplete. |
| Agent instructions | Several paths say stop, block or create a fresh run without distinguishing retained work and recoverable operations. | Audit each workflow and its owning component; specify exact resume behavior without repeated settled setup. | Pending |

The MCP adapter invokes the same Python CLI and passes explicit IDs. The observed
input/readmission and reporting defects are below that transport boundary.
MCP process/session continuity still needs separate verification. The adapter's
five-minute worker-killing timeout has now been removed; this does not establish
durable outcomes after a host/process disconnect.

## Completion evidence still required

- Account for every exposed Vera skill and owning component, including direct
  and studio-wide workflows, Codex and Cowork instruction projections.
- Verify the repaired public APIs and ordinary helper routes with failures
  between successful stages, retained source/output bytes and unchanged job IDs.
- Verify source, receipt and output isolation under recovery; preserve changed
  evidence instead of discarding it or falsely accepting it as the original.
- Exercise lost destination/reconnect, alternate delivery, interrupted write,
  uncertain mutation outcome, native process reconnect and changed originals.
- Record pipeline and privacy-report outcomes separately.
- Complete source quality gates and product package parity; retain explicit
  installed-host and deployment limits until directly verified.

## Verification through the first repair set

- Five initial fault-injection regressions failed on the unmodified product:
  original removal, original receipt removal, original change, report start
  failure, and reporting-status write failure. All five pass after repair.
- Prepared runs now retain source-receipt snapshots and use their sealed input
  manifest and execution copies after intake. Current execution-byte checks
  remain enabled. Recovery of damaged execution copies still needs work.
- General destinations support both creation and registration without invented
  identity values or automatic onboarding. The existing client creation API
  now reports relationship setup as not requested.
- The exact selected run survives loss of the session configuration. Its
  retained pointer is checked against the run's immutable identity; it does not
  authorize another client or infer the most recent run.
- The current combined Archive fault-isolation, assurance, component, adoption
  and concurrency selection passed **326 tests** (five existing SWIG warnings),
  in 44.84 seconds. Log: `/private/tmp/vera-continuity-bindings-tests.log`.
- Every one of the 55 exposed Vera skill entry points now references the shared
  work-continuity contract. This is instruction coverage, not evidence that
  every engine or installed host satisfies it. Per-workflow implementation
  review, storage recovery, packaging and installed acceptance remain open.
- MCP-specific observation: `server.cjs::callTool` uses synchronous CLI
  execution and imposes a 300-second timeout on every operation except index
  refresh. This can terminate a long operation independently of the shared
  Python defects. No evidence ties that timeout to the reported client-ID error.
  Durable operation/reconnect behavior needs review before completion.

## Remaining implementation work

1. Extend verified relocation/continuation coverage to the owning engines.
   Independent checkpoints and restore are implemented, with managed-runtime
   integration. Some formats retain absolute paths; byte recovery alone is not
   proof the next engine step can run. Do not promise an unsaved checkpoint.
2. Extend corruption, concurrent recovery and storage-failure coverage. Exact
   admitted input recovery retains changed copies as separate evidence. Keep
   receipt and package integrity checks and verify all transitive file inventories.
3. Verify upfront prerequisite admission and continuation in each engine and
   direct workflow, including multi-company merger, synthetic transformation,
   studio-wide workflows and connected-service routes. Update contradictory
   stop/restart instructions and source behavior, not just the shared wording.
4. Verify Archive MCP disconnect/reconnect behavior through durable outcomes;
   never retry a possibly committed mutation under a new identity.
5. Review privacy source/data-path changes, update component/product versions
   without colliding with the active tolerance release, rebuild all affected
   host packages, and run the required quality/package checks. Marketplace
   remains untouched.

## Reporting isolation and recovery verification

The second repair set reproduces and removes eight delivery failures: CLI and
preview output withholding, missing report-start records, native job output
withholding and MCP pre/post-delivery reporting failures. Finalization also
reproduced two failures after a useful result existed: report closure and report
status-sidecar writing. Those are separate reporting outcomes now. Invalid
source mappings still cannot claim provenance; the professional output remains
available and a content-free measurement-gap record is retained when possible.
Late delivery retains the sealed report and records any gap separately.

The combined source run completed **483 tests**, with five existing SWIG warnings,
in 90.77 seconds (`/private/tmp/vera-continuity-core-current.log`). This includes
storage restore to an alternate destination after loss of the original archive,
repaired execution copies with changed evidence retained, interrupted restore
resumption, managed-helper output checkpoints, replay without rolling back new
work, and a fresh CLI process restoring after archive/configuration loss. Sealed
output completion and delivery no longer reopen input admission. Genuine output
byte/identity verification remains required.

Checkpoint files are owner-private local copies outside the selected archive,
deduplicated by exact content hash. A committed running/terminal state is never
hidden by checkpoint failure. Restoration retains the same IDs and refuses to
overwrite an unrelated destination. The store has no external upload or
automatic deletion. Losing optional checkpoint storage does not invalidate
unchanged available execution inputs.

Three additional adapter/CLI regressions failed before repair
(`/private/tmp/vera-continuity-mcp-before.log`): a simulated six-minute valid
operation was killed by the adapter deadline, and secondary error-reporting
failure hid the original operation error in both MCP and CLI. These now pass.
The elapsed-time test injects a worker result, not a six-minute host session;
host timeout/reconnect behavior remains unverified.

Representative open-item/report-builder producer tests passed after registering
the new shared recovery module in their implementation inventories. The same
test run found an additional bank-reconciliation receipt inventory omission;
both its bootstrap list and receipt specification now include recovery.py.
The larger earlier projection run (334 passes, 11 failures, 67 setup errors)
predated those inventory repairs and must be rerun; it is not a passing result.

Treasury relocation was independently reproduced through its actual CLI: a
renamed archive and a restored archive both failed with a missing-source error
despite intact admitted inputs and forecast versions. Its reader now resolves
the retained source references using the exact same portable run, relative input
path and admitted hash, without rewriting sealed session/forecast bytes. Both
CLI cases pass. The broader Treasury/adapter/bank selection passed 63 checks;
two local HTTP tests were blocked by this execution sandbox and one test lost
its shared import path after another fixture's cleanup. The test fixture has
been corrected; the affected checks are being rerun with local socket access.

Pipeline and privacy outcomes are separate throughout these tests. Fault cases
explicitly retain reporting-unavailable/incomplete status; successful delivery
does not count as successful privacy measurement or server receipt verification.
No installed-host, Marketplace or deployed-release acceptance is established.

Work is isolated at `/private/tmp/vera-work-continuity` on
`codex/vera-work-continuity`. The primary checkout's unrelated changes remain
untouched. Main advanced through #922 (Archive owned artifact/verification tools)
and #923 (reviewed tolerance preservation), to Vera 0.1.512. Integrate those
changes before release and rebuild; do not replace either intervening repair.

## Integration checkpoint

The source repair was committed on the isolated branch and rebased onto
`ea8e5fe4a` (#923), preserving #922 and #923. Current task commit:
`9324cd125`. This is an intermediate local commit, not a release. The two merge
conflicts retained the report-verification CLI command and authored-text stdin
transport while adding checkpoint/restore and removing the worker deadline.

The integrated selection passed **494 checks** and found six fixture setup
failures: imported ledger helpers lost their shared module path after another
test's cleanup. The test helpers now restore their own source import roots.
The three formerly sandbox/import-blocked Treasury checks passed with local
socket access, and the three native Treasury checks passed after fixture repair.

Three new integration regressions then reproduced gaps in #922's new routes:
the authored-save and report-verification APIs rediscovered session configuration
after run admission, and authored-save results were absent from the independent
checkpoint. Both APIs now select the retained exact run, and successful authored
saves checkpoint that stage. All three regressions pass. The accompanying
selection passed 20 checks and identified the sampling receipt inventory's
missing recovery-module entry. The six assured producers' Python and Node
inventory declarations have now been inspected and synchronized; broader
producer/projection checks are running.

Privacy review now describes the independent local copies and separate reporting
failure in the Vera/Lucia Archive manifests and the Vera reporting service. The
five localized Archive data-path explanations include these actual changes.
Fingerprints and generated contracts remain stale pending the complete review
and final source/version choices. An initial validation found 66 stale Vera,
21 stale Clara and 25 stale Lucia reviews; one new service control needed its
explicit executable paths and failure behavior, now supplied. No generated
contracts or packages have been claimed current.

## Workflow inventory and unresolved boundaries

The 55 exposed wrappers all reference the continuity contract. Source inventory
finds the shared context loader in 32 component script groups: adeguati-assetti,
aml-review, archive-organization, bandi-agevolazioni, business-planning,
business-valuation, centrale-rischi-review, check-entries,
client-file-preparation, composizione-negoziata, concordato-plan-review,
deep-research-validator, esg-reporting-assurance, financial-analysis, invoice-xml,
journal-bank-reconciliation, journal-sampling, lipe, management-control-pack,
new-client, open-item-reconciliation, passive-invoice-audit, patent-box-review,
previdenza-inps, prompt-optimizer, rating-legalita, registro-imprese-sari,
report-builder, sales-plan, scissione-guidata, treasury-forecast and
variance-analysis. This establishes the shared repair's call sites, not acceptance
of each engine's remaining internal checks or relocation behavior.

Additional routes still need owning-source review: legal/tax vendor workflows,
multi-company fusione, bilancio adapters, browser acquisition, synthetic
trasformazione, studio-wide communications/formatting, calendars and tutorials.
The ordinary calendar instructions already retain a proposal when external
access is unavailable, without inventing connector success. The course file-access
reference currently requires pausing later teaching when a save fails and reconnecting
the same location. Its `OnboardingStore.status` rejects a changed lesson directory;
`recover` restores only a matching enrollment profile at its existing root. That
is an unresolved course relocation restriction, not evidence of universal recovery.

MCP reconnect remains an explicit open item: removing the adapter timeout does
not establish durable outgoing responses or prevent duplicate engagement creation
after an uncertain response. Native jobs already have retained IDs/status routes;
the generic Archive mutation boundary still needs exact-outcome verification.

The expanded public recovery selection passed **14 tests** in 3.09 seconds
(`/private/tmp/vera-continuity-recovery-expanded.log`), including a full checkpoint
disk after successful authored saving, a foreign run's checkpoint and a linked
destination. The existing result remains available in the storage-failure case;
the two rejected restores leave unrelated destinations untouched. Mypy found no
issues in the two new Python runtime modules, and Bandit reported no findings in
those modules. Black, Isort and changed Node source syntax checks passed. These
are selected checks, not the repository-wide quality/coverage gates.

The producer/projection run remains active in
`/private/tmp/vera-continuity-projections-current.log`; it is running real producer
subprocesses, not waiting on a user response. Its final result must be collected.
After the reporting-control schema correction, Vera privacy validation reports
67 stale fingerprints and no other schema/control errors. No fingerprint refresh
or package generation has occurred yet.

## Creation, handoff, acquisition and course recovery

The previously pending producer/projection run completed **198 tests** in
1019.54 seconds (five existing SWIG warnings). Its log is
`/private/tmp/vera-continuity-projections-current.log`. This verifies the authored
artifact routes and open-item, bank, report-builder and native projections after
the implementation-inventory fixes. Intermediate local commit `e77f10809`
retains those inventory and authored-save changes.

Engagement creation now accepts a software-generated, retained request key. Its
sealed creation intent precedes directory creation; exact retries keep the same
ID and creation time, while a different label under the same key cannot replace
the prior matter. Run preparation recognizes an explicit retained request before
rereading original intake receipts, preserving the admitted version and current
run state. Normalized labels, purposes and upstream roles compare consistently.
The component, Vera and Cowork instructions require generating and saving these
internal keys before the first call; the professional never supplies them.
Unkeyed explicit-new requests still intentionally allocate separate runs.

Actual subprocess exits after engagement/run commit and before response delivery
were followed by fresh CLI retries. The same identities and bytes were returned;
the committed run remained usable even after its original receipt was removed.
A separate reproduced handoff failure required a completed producer's old input
copies even though its selected result and sealed artifact receipt were intact.
Handoff now verifies that exact result without reopening the producer's input
gate. The current creation/concurrency/ledger/recovery selection passes
**74 tests** (`/private/tmp/vera-continuity-archive-retry-final.log`).

Owning-source inspection of Agenzia acquisition found three additional failures,
all reproduced before repair: identity rediscovery on resume, CLI status delivery
withheld by reporting storage failure, and a saved acquisition event interrupted
by source-measurement failure. The adapter now retains its selected Archive run,
uses immutable identity for report/output access, and reports measurement gaps
separately. The MCP delivery bridge also preserves status when its reporting call
fails. A foreign pipeline binding receives no measurements; other valid bindings
still receive explicit gap records. The native panel's resume now carries the
same Archive bindings as CLI resume. A new worker attempt may have another worker
ID; it continues the same professional Archive runs and verified originals.
Acquisition recovery checks passed 27 tests after panel repair, and the additional
mixed-binding gap selection passed nine tests.

Course recovery now has an explicit `local_onboarding.py relocate` operation for
an authorized alternate folder. It preserves enrollment/session IDs, profile,
progress and exact evidence bytes; resumes partial copies; refuses symlinks and
unrelated destinations; and does not overwrite newer destination progress on
replay. Retained absolute receipt paths resolve through the completed local
relocation record, with exact current-byte checks. Original folders and receipt
bytes are unchanged. No automatic upload, deletion or new permission is implied.
An inaccessible source requires an available retained copy; the code does not
promise recovery of unreadable bytes. A saved phase now retains its admitted
procedure version across a plugin update, while receipt or evidence changes still
prevent a false completion. The combined course/acquisition run passed **121
tests** (`/private/tmp/vera-continuity-course-agenzia.log`). New recovery module
Mypy and Bandit checks passed. Privacy controls and five localized course data
explanations describe the actual additional local copies and path records.

The broader course run initially had 162 passes and 35 failures: 30 stale prepared
course fingerprints, two absent package ZIPs and three test-fixture lazy-import
failures. The fixture restores its shared import root; the current catalog build
regenerated 58 kits / 258 localized kits with no missing translations. The
post-build runtime selection passed **199 tests**, with the two package-dependent
checks deselected, in 181.29 seconds
(`/private/tmp/vera-continuity-courses-rebuilt.log`). Those package-dependent
checks still need built ZIPs.

The native executor now checks an existing exact request before current-package
admission. The previous implementation rejected a committed result after a valid
newer package removed that component; the repaired fresh-service retry returns
the saved result and rejects different arguments under the same job ID. The
reproduction and passing target are recorded in `vera-continuity-native-retry-
reproduced.log` and `vera-continuity-native-retry-final.log` under `/private/tmp`.
The full native selection passed 45 checks with appropriate local process/sandbox
permissions; its remaining failure was the new test fixture retaining empty
directories outside its digest index. After correcting that fixture, the target
passed separately. Earlier nested-sandbox failures in cancellation and OS sandbox
probes passed with the required permissions. No installed Windows acceptance is
inferred from these local processes.

Additional owning-route findings: fusione imports Archive receipts once into
SQLite blobs, and later `_base_issues` verifies retained blob hashes instead of
reopening original folders. Legal document/matter helpers retain relative
original snapshots, revision histories and output identities. Bilancio's
jurisdiction adapter uses the repaired shared context loader; its case service
has durable job/idempotency records and a separate controlled-input intake.
Studio calendar instructions retain uncertain external outcomes and verify the
specific event before retry. Studio document formatting has an upfront separate
workspace and retains previous standard versions. The synthetic transformation
route remains separate from Archive and keeps its bounded case/consent scope.
These are inspected source boundaries, not full engine or host acceptance.

The branch includes fetched `origin/main` at `ea8e5fe4a`; the primary checkout's
local `main` is older (`e42c5d4a8`), so it must not replace the integrated #922/#923
changes. The current repair set is local commit `f997fb4c2`. The worktree is clean.
There are two local branches, one actual remote branch (excluding the symbolic
`origin/HEAD`), two registered worktrees and zero stashes.

Release work remains: finish the owning-route audit, verify the current remote,
review/refresh the changed privacy fingerprints, generate contracts,
reserve noncolliding versions, rebuild all affected host packages and complete
the relevant full quality/package checks. No deployment, Marketplace publication
or installed-host fix is claimed. The active task branch/worktree is retained.

## Owning-route audit closure and final preparation

The 55 wrapper inventory is accounted for as follows. This is a source audit,
with executable acceptance limited to the recorded regression suites; it is not
55 independent live professional tasks.

| Exposed route(s) | Owning continuation boundary inspected |
| --- | --- |
| adeguati-assetti, aml-review, archive-organization, bandi-agevolazioni, business-planning, business-valuation, centrale-rischi-review, composizione-negoziata, concordato-plan-review, esg-reporting-assurance, financial-analysis, journal-bank-reconciliation, journal-sampling, lipe, management-control-pack, new-client, patent-box-review, rating-legalita, registro-imprese-sari, sales-plan, scissione-guidata, variance-analysis | Corresponding component scripts consume the shared retained Archive context and exact execution copies. Changed evidence remains distinguishable from the admitted copies. |
| avviso-intake, dati-fiscali-strutturati, email-cliente, fatture-xml-check | client-file-preparation and shared Archive context. |
| adversarial-opinion, deep-research, legal-tax-answer-review, quesito-legale-fiscale | deep-research-validator; standalone task workspace remains available without invented client registration. |
| legal-tax-answer-planner | prompt-optimizer and deep-research-validator. |
| financial-report-builder, purchase-invoice-review, vouching | report-builder, passive-invoice-audit and check-entries respectively. Producer inventories include recovery implementation. |
| open-item-reconciliation | Ordinary Archive reconciliation and assured component; retained producer result is verified independently of its old inputs. |
| treasury-forecast | Session-relative references resolve against exact restored run bytes, without rewriting sealed forecast provenance. |
| invoice-xml | Shared admitted context; prepare persists partial revisions and preview without professional approval. Later export checks exact proposal/source bytes and its declared approval record, without recreating intake. |
| previdenza-inps | Shared context and persisted facts; routine source-image transcription now accepts honest agent review while preserving attribution and missing-check failures. Material decision and arithmetic confirmations are separate. |
| bilancio-oic | bilancio-xbrl-it jurisdiction adapter and durable case jobs. |
| fusione-guidata | SQLite retains imported source blobs; later validation verifies retained hashes. |
| contenzioso-tributario, posizioni-negoziali | Shared italian_tax_litigation/deal_redux and legal document/matter helpers retain snapshots, versions and relative outputs. |
| agenzia-acquisition, browser-automation, datev-invoice-start | Browser acquisition adapter retains professional Archive bindings; a resumed worker attempt is not a new professional task. |
| trasformazione | Separate synthetic case store with retained case/consent scope. |
| comunicazione-professionale, presenza-digitale-studio | Saved drafts and selected task workspace; external communication/publication remains a distinct requested action. |
| organizzazione-lavoro | Studio calendar retains uncertain external outcomes and verifies the exact event before retry. |
| studio-document-format | Separate upfront workspace and retained standard versions; adoption distinct from preparation. |
| learn-with-vera | Explicit verified relocation retains enrollment, sessions, phase receipts and completed progress. |
| research-subscriptions | Missing local register or subscription capability preserves current-task choices and permits available unsubscribed research. |
| studio-archive | Persistent client/run bindings, exact request retries, independent checkpoints, restore and completed-result delivery. |
| vera, privacy-surface-review | Routing/governance instructions inherit continuity; reporting outcomes stay separate from professional result delivery. |

The execution-recovery reference now stops only an unverified launch, preserves
existing job IDs/results and directs recovery of the affected operation.
Acquisition wording distinguishes a worker attempt from its existing Archive run.
The INPS visual-check validator accepts `agent_reviewer` only as an attributed
source-image check, never fabricated human approval. Missing evidence checks,
unknown roles and invalid timestamps remain rejected. The associated suite passed
109 tests (five existing SWIG warnings). An initial invocation omitted the parent
fixture; a second exposed its cached-ledger import-path defect. The fixture now
restores the shared import root. No production import behavior was changed to
satisfy that fixture.

Deterministic checks here establish exact identifiers, bytes, source ownership,
request equality and replay outcomes. These are mechanical invariants. They do
not select legal relevance, resolve ambiguous professional facts or replace
semantic judgment.

Privacy review of the changed routes distinguishes additional private recovery
copies and request records from existing model-visible inputs. Report failures
record content-free gap metadata; they do not establish zero exposure. Course
relocation retains a local path/file inventory and does not upload it. The new
visual reviewer role changes attribution, not recipients or payload routing.
Unchanged external-service boundaries are retained; their changed fingerprints
reflect shared execution/reporting code and course source references. The
selected stale records will be refreshed only after these source edits, then
contract generation and package validation will run.

Remote main was checked before reserving versions: Vera 0.1.512, Clara 0.1.359,
Lucia 0.1.185, with no open release PRs. Local candidates are respectively
0.1.513, 0.1.360 and 0.1.186. Nothing has been uploaded or published.

### Current verification results

- Black and Isort passed all 74 changed Python files at the first final check;
  subsequent test-only edits are checked separately. Node syntax passed all 21
  changed JavaScript files. Mypy passed the 11 reporting/native files and both
  new recovery modules; Bandit found no medium/high issue in that selection.
- The focused recovery set passed 142 tests, with 86.08% combined coverage
  (Archive recovery 85%, course relocation 88%). Its first combined run exposed
  a cached-module test import path; the owning fixture now restores its roots.
- The current privacy selection passed 108 tests with 89.05% coverage using its
  own coverage file. A prior premature package run lacked the still-building
  Cowork ZIPs; no product failure was inferred from those missing artifacts.
- Native emission tests passed eight tests with the repository's normal import
  isolation. Combining them with the older `--confcutdir` reporting selection
  had mixed identically named standalone component modules. CI now runs this
  native selection separately with the repository fixture enabled.
- The broad reporting selection initially had 324 passes, seven failures and
  one setup error. Three failures were obsolete assertions expecting a reporting
  error to hide the operation error or a missing report to block a result; one
  required a downstream run to reread an altered original upstream receipt.
  Those now assert preserved results and explicit reporting gaps. The acquisition
  fixture now records the actual client/engagement/run identity fields written
  by the producer. The remaining native failures were the import isolation
  issue above. The complete reporting selection is being rerun independently.
- All three product builds completed, including Codex, ChatGPT upload, Cowork
  and Antigravity projections and their MCP startup checks. The package selection
  passed 454 checks, with two existing skips; its remaining failure identified
  missing patch bumps for changed embedded components. Those versions must be
  advanced and the final packages regenerated before claiming release parity.

These results are local source/package evidence. No merge, deployment,
Marketplace action, installed-host replacement or professional acceptance has
occurred. The goal remains active while final release checks are incomplete.

The isolated final reporting run passed **324 tests**, with **85.08%** coverage.
The full native execution selection passed **46 tests** with the required local
process/sandbox permissions. Updated test formatting and changed CI YAML checks
passed. New continuity tests and coverage are included in the existing Archive,
reporting and teaching CI jobs; native emission tests use normal component import
isolation in their own step.

All 13 affected product/component versions differ from integrated main. Embedded
candidates are browser-automation 0.5.32, check-entries 0.1.57,
concordato-plan-review 0.1.43, journal-bank-reconciliation 0.1.80,
journal-sampling 0.1.57, open-item-reconciliation 0.1.83,
previdenza-inps 0.2.13, report-builder 0.1.46, studio-archive 0.1.70 and
treasury-forecast 0.1.5. The failing version-check target now passes. The first
parity run completed the Codex, ChatGPT-upload and Cowork checks; it was superseded
by these required component version changes during its Antigravity stage and
therefore is not final release parity. Catalogs and affected privacy fingerprints
were regenerated, and the final all-host rebuild is running.

### Final local candidate and CI handoff

Local commits `46a4571af` (source/metadata) and `1b472e344` (generated packages)
are pushed in draft PR https://github.com/fabioannovazzi/app_files/pull/924.
Remote main remains `ea8e5fe4a`; no intervening release was dropped.
The final package selection passed **436 tests**, with two skips and four
existing warnings; the separate alignment selection passed **19 tests**.
The final `build_product_release.py vera clara lucia --check` passed every
product/host, including startup checks and exact package/source parity.

CI initially failed LIPE on both Linux and Windows because its direct ledger
fixtures omitted the shared module search path. Two local tests reproduced the
same missing import. The fixture setup is corrected without modifying production
LIPE or Archive imports. The complete LIPE selection now passes **377 tests**
with **90.99%** coverage, and its formatting checks pass. CI remains outstanding
on the corrected commit; this does not establish installed-host acceptance.
The GitHub connector could read the repository but refused PR creation with
integration permission 403; the authenticated GitHub CLI created the draft.

The active task retains two local branches, two actual remote branches, two
registered worktrees and zero stashes. The primary checkout's unrelated work
remains untouched. No merge, deployment, Marketplace publication or enabled
installation update has occurred.

### Corrections from the first cross-platform CI run

- The reporting subprocess wrapper rejected the valid `env=None` option.
  A real child-process regression reproduced this; `None` now inherits the
  environment, while an explicitly empty mapping remains empty. All three
  environment cases pass. The operational-incident selection passes **551
  tests**, with **83.43%** coverage. Its initial local run hit the nested sandbox's
  loopback-socket restriction; the permitted rerun completed successfully.
- Windows CI could not flush read-only checkpoint handles, so it retained no
  recovery snapshot. A focused writable-descriptor regression reproduced this
  locally; retained copies are now opened read/write for `fsync`. The combined
  Archive recovery/Treasury selection passed **208 tests**, with three existing
  skips and **85.43%** recovery coverage. Two local HTTP tests initially met the
  same sandbox socket restriction; both passed when rerun with socket access.
  Real Windows confirmation remains pending on the corrected candidate.
- The document-format CLI and packaged dated-case acceptance called the ledger
  directly, without Archive core's shared-module bootstrap. This showed that the
  earlier LIPE import diagnosis also affected actual callers. The ledger now
  resolves its owned source/packaged recovery dependency itself. The real
  document-format CLI regression failed before and its complete **19-test**
  selection passes after repair. The rebuilt Vera ZIP also passes the dated-case
  reconciliation through reinstall, simulated upgrade and MCP reconnect while
  retaining its run. The later CI vouching failure had the same ledger import
  cause; its focused cross-page PDF regression passes with this fix.
- Cross-process creation fixtures now declare their synthetic session identity
  instead of inheriting an incidental desktop host session absent in CI. The
  reporting CI job installs the acquisition component's declared requirements
  for its real MCP status test. The browser package test uses the current source
  ZIP inventory API.
- CNC, ESG, Patent Box and Archive isolation assertions now verify retained
  admitted inputs and saved decisions, including preservation of changed bytes;
  current execution symlinks and altered state/artifacts remain rejected.
  The planning comparison excludes the explicit Vera continuity instruction
  block while still comparing the shared analytical contract. The combined
  CNC/ESG/planning/creation selection passes **131 tests**; Patent Box passes
  **278 tests** with **82.84%** coverage, and invoice XML passes **49 tests**.
- The three implementation corrections add no model-context fields, recipients
  or network destinations. Affected source fingerprints and generated catalogs
  are refreshed after reviewing these changes. Release versions remain the
  same unpublished draft candidates. All host packages have been rebuilt and
  their startup/version-alignment checks pass; the independent parity and
  package regression checks are running.

The corrected full reporting selection passes **327 tests**, with **85.09%**
coverage. The separate native-emission selection passes **eight tests**.

The correction candidate's package and release-alignment selection passes
**455 tests**, with two existing skips and four warnings. The final all-host
build and independent `build_product_release.py vera clara lucia --check` both
pass, including exact source/package parity and MCP startup checks.

The second CI run confirms Windows Treasury checkpoints, readable Archive on
all three platforms, LIPE on Linux/Windows, invoice XML on Linux/Windows,
operational incidents, the document-format CLI, and native boundaries on all
three platforms. Windows reporting found five assertions expecting LF where
child processes correctly emitted CRLF; the tests now compare native line
endings/exact source bytes. Its full nine-test CLI selection passes locally.
No production source or package changes were required for that correction.
A Linux service-lock job timed out fetching the repository before tests ran;
that job was retried independently rather than counted as a product failure.

The final-head Windows browser job hit its five-minute CI limit twice while
passing tests: 245 Python tests, 38 lifecycle tests and the first Node suite
completed, but the second Node suite was still advancing when CI cancelled it.
The lifecycle selection alone took 185 seconds on that runner. Its job budget
is raised to ten minutes, retaining every test and assertion. This changes only
CI scheduling, not any product timeout or gate.

On `d6d22fb16`, Windows reporting completes **312 tests**, with 15 platform skips
and no failures, in 831.54 seconds. The fifteen-minute job limit then cancels
the separate native-emission step before quality checks. That reporting job now
allows thirty minutes so all existing steps can finish. The corrected Windows
browser job passes with its ten-minute budget. These are CI limits only; the
production source and packages remain unchanged from `42b853a66`.

CI is still outstanding. These results do not establish deployment, installed
acceptance or live professional acceptance of every workflow.

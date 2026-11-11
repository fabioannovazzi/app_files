# Studio Archive graceful failure — implementation plan

Goal: an Archive infrastructure failure must not, by itself, stop otherwise
possible processing or delivery. This applies across Vera, not only accounting.
Professional source validation and real missing inputs remain separate.

## Follow-up outage audit (2026-11-11, in progress)

Latest verification supplement: the active installed Vera service reports the
candidate package digest `f79a25e3fb0abde729baec9037f3ab14f90d830639914c040b341bc8622a892d`.
Its maintained work-folder status operation reopened the exact synthetic run
with its saved result and unchanged inventory hash. Current exposed skills and
the sole enabled installation both match 0.1.615. This resolves the earlier
obsolete-skill mismatch; it does not establish rendered native-panel acceptance.

Three additional healthy/outage producer pairs now cover AML first record
creation, Assetti first case/questionnaire, and Scissione first proposal/review
from admitted inputs. All six cases and their three full test files pass.
They supplement the earlier native continuation cases; professional judgments
remain synthetic supplied inputs, not independently accepted advice.

Teaching CI run `43063905137`, job `130679947033`, passed 1,752 tests with three
explicit skips, then rejected stale editorial course digests. All 55 affected
review digests were located in exact historical Git snapshots. Every compiled
field except `sources` matches its own reviewed baseline. Historical editorial
judgments, reviewer identities, dates and artifact hashes were preserved, with
a separate agent-attributed compatibility record. Ten XML teaching test names
also gained the healthy/outage parameter; their release references now select
the actual successful healthy controls with matching kit/locale/phase/digest.
The unchanged release verifier passes all 58 kits and 258 locales against the
downloaded real CI JUnit. Release-review regressions pass. This is not new
visual, learner, professional or native-panel acceptance. Fresh final-head CI
remains required; no failing assertion or execution gate was removed.

The follow-up starts from `450a84806`. The requirement above is unchanged;
the earlier shared-route coverage did not establish every pipeline end to end.

Reproduced blockers and repairs:

| Failure injected | Observed effect before repair | Implemented recovery |
| --- | --- | --- |
| Busy or unwritable pending-work lock | `finish_work` raised before returning saved outputs | Validate and enumerate the existing outputs without writing the pending-work record; return finalization and archival as pending |
| Inaccessible Archive metadata during shared CLI checkpoint discovery | Child command never started | Record a reporting gap and run the requested command, preserving its exit code |
| Unavailable first or second temporary reporting capture file | Child command never started | Close any opened capture file, record a reporting gap, and launch once using the original output destinations |
| Archive state/profile unavailable for an existing native job | Patent Box could not resolve its admitted job before calculation | Store exact run bindings in owner-private `.vera-work-continuity/work-bindings` beside session storage; resolve and verify the run without opening Archive configuration |
| Archive state/profile unavailable for direct result writing/listing | Configuration wrapper rejected the request before reaching intact work storage | Use the state location for serialization; retained-job identity validation remains mandatory and configuration users still validate/lease actual Archive state |
| Reporting runtime import fails while listing saved outputs | Declaration preview raised instead of returning existing result files | Enumerate owned outputs first; return a separate unavailable-reporting status |
| Archive configuration fails after admitting an engagement | Start, completion, import, input verification and preparation rejected before reading intact job storage | Resolve the exact retained engagement/run first; keep source receipts, input membership and lifecycle validation in the portable ledger |
| Archive configuration fails while recording failure/cancellation/closure or requesting a checkpoint | These operations raised an unrelated state-directory error | Retain the actual lifecycle outcome; return checkpoint unavailability separately |
| Report JSON is malformed or carries another product/workflow/run identity | Python and Node professional output validators rejected valid work because of the reporting payload | Establish ownership from the execution context; keep reserved ordinary report files outside the professional output seal and emit an unverified-reporting warning without rewriting the report |

Every repair has a regression that failed before the production change. The
shared CLI implementation is synchronized into Vera, Clara and Lucia sources.
No runtime integrity check or professional input check was removed.

Coverage added:

- All 38 registered workflows exercise portable preparation and ordinary context
  validation with unavailable Archive configuration; all exercise finalization,
  completion, status-record, busy-lock and permission-failure delivery paths.
- All 39 bundled component names exercise shared launcher discovery failure with
  a real child that saves and prints a result, including nonzero exit-code
  preservation. This is launcher coverage, not 39 professional engine runs.
- Capture-storage failures exercise both acquisition points and verify private
  stderr stays in its original destination.
- A real journal-bank engine run uses two synthetic spreadsheets imported into
  the portable context. It calculates one reference match and one unmatched row
  on each side, then delivers the saved workbook during finalization failure.
  Output bytes are checked unchanged. The initial test used an invalid import
  role (`bank`); the test was corrected to the supported `source` role, without
  changing production validation.

The bank fixture isolates external reporting: it does not establish a successful
privacy report or server receipt. Launcher failure tests assert the reporting
measurement gap remains visible. Package rebuilds, required repository gates,
installed acceptance and complete per-engine outage coverage remain outstanding.
No publication or installed-plugin change has been made by this follow-up.

Current source/package checkpoint: both full Archive gates passed (483 reporting
tests at 86.42% coverage; 519 recovery/continuity tests at 89.08%, plus three
Windows-only skips on macOS). All host builds and exact source-to-package checks
passed. The package/update group has 416 passes and the separately recorded
pre-existing Clara public-notice failure below. Installed fresh-chat acceptance
and remote CI are not yet established.

Further retained-work regression: unavailable session settings still rejected
`list_studio_client_engagements` and `retain_studio_run_binding` before accessing
the independent pointer. Both new tests reproduced the error. These operations
now resolve the state location without requiring optional configuration storage;
the complete tutorial-binding suite passes (18 tests), including foreign-client,
altered-context, unsafe-pointer and multiple-live-copy rejection.

### Incremental privacy review of this change

The changed launcher continues the same child command and original output sinks
when checkpoint discovery or capture-file allocation fails. The existing
reporting-failure helper records component, stage, exception class, measurement
gap and persistence status; it does not record exception text or source content.
Unavailable capture leaves measurement incomplete; it does not claim a successful
report. The Python and Node output validators preserve malformed/foreign report
bytes and warn without treating those bytes as professional ownership evidence.
Source payload builders, external recipients and receipt request fields are not
changed. Existing product-specific service declarations remain applicable.

The new retained pointer stores only the working root, client/engagement/run IDs
and static context hash in owner-private storage beside the session directory.
It has no network path or automatic deletion. Reopening still validates the
actual ledger and rejects unsafe or ambiguous bindings. Vera and Lucia Archive
manifests now record this local persistence boundary. Shared source fingerprints
also affect Clara's embedded assurance consumers; they do not establish that
Clara gained an Archive workflow. This is a review of the changed paths, not a
claim of fresh host-session or server-receipt acceptance.

The incremental review refreshed 37 Vera, six Clara and seven Lucia source
records; all three registers validated before versioning. Candidate versions are
Vera 0.1.615, Clara 0.1.410, Lucia 0.1.233 and Studio Archive 0.1.78. GitHub's
open PR inventory showed the separate Vera 0.1.614 candidate in PR #982; it is
not included in this worktree. The fetched main remains `450a84806`.

The first package attempts exposed stale generated catalogue/course records.
The Vera catalogue comparison proved all 55 skill entrypoint IDs and bytes
unchanged; only the canonical version binding changed. Its existing jurisdiction
judgments were retained. Course regeneration covered 58 workflow kits and 258
localized kits with no missing translations; the course source hashes changed
with the shared assurance repair. The corresponding onboarding/prepared-course
privacy fingerprints were refreshed. The subsequent build passed privacy,
runtime-policy revision and 1,122 remote-course-attachment checks. All three
Codex product ZIPs were built and their packaged launcher bytes compared exactly
with source. Other host builds and the broad reporting/coverage test gate are
still in progress at this checkpoint; no installation or release acceptance is
claimed. Black/Isort passed for all 46 changed Python files; targeted Mypy and
Bandit checks passed.

The broad automatic-reporting CI command completed with 480 passed, three
failed and 86.42% coverage. All three failures came from acquisition test
fixtures monkeypatching `_state_dir` instead of selecting temporary state via
the supported environment. The new location resolver bypassed that mock;
fallback inspected a host profile, then the incomplete mock rejected the
`create` keyword before configuration could be written. The tests now select
both temporary state and profile paths; production code was not changed to
accommodate the harness. Both affected test files subsequently passed all 38
tests. A fresh execution of the complete CI reporting command is in progress.
The component packaging command for Studio Archive correctly targets its Vera
and Lucia containers; it does not create a standalone Archive package.

The complete reporting CI command rerun passed: **483 tests, 86.42% coverage**.
The Archive adoption/recovery CI command also passed: **519 tests, three skips,
89.08% coverage**. The helper itself has 92% coverage in that gate. All product
builds completed with the candidate versions aligned across Codex, ChatGPT
upload, Cowork and Antigravity. Local MCP startup checks passed for the projected
packages. These are package/runtime checks, not real-host conversation acceptance.
Source-to-package checking and the package/update-notification test group are
still running; five plugin-icon tests and the assurance Python/Node source
quality checks passed. The shared vendor dependency inventory identifies only
Vera, Clara and Lucia as downloadable targets affected by the assurance change.
The three skips are Windows-only PowerShell launcher cases on this macOS host;
the CI adoption matrix retains Windows, macOS and Linux execution. The latest
remote fetch still reports main at `450a84806`. Product checking has verified
all three Codex and ChatGPT-upload archives and continues through the remaining
host checks. The full package/update-notification suite is still live; it has
not yet produced a final result.

Finished package verification: `build_product_release.py vera clara lucia --check`
passed for every host and exact candidate version. Package/update tests finished
with **416 passed, one skipped, one failed**. The only failure is the existing
Clara public update notice (0.1.248) being behind the locally cached curated
version (0.1.390). `static/shared/codex-plugin-versions.json` is identical to
origin/main; this change has not modified Marketplace publication metadata.
The skipped case is Vera's curated-cache check because that distribution is not
installed locally. Do not treat this combined test group as wholly green or a
cached version as independent proof of current Marketplace Published status.

The final producer expansion passed **130 cases**: packaged Vera/Lucia
tax-litigation preparation, document rendering and resumption across five
languages and four host formats; negotiation HTML/CSV/XLSX plus immutable source
and output receipts; Bilancio Alfa service calculation/review states and its
comparison report; actual invoice-XML parser totals and anomaly artifacts; and
ESG case creation, evidence binding, source registration and deliverable creation
with exact retries. Healthy and unavailable-Archive controls run the existing
professional assertions. These use fictional inputs and do not claim filing,
live portal acquisition, professional approval or fresh host-chat acceptance.

### Native outage scenarios

`tests/plugins/archive_outage.py` makes optional configuration/profile/reporting
locations unusable without changing the admitted input copies or output folder.
For an explicitly configured location inside the synthetic test, it preserves
the original directory under a test-only name and substitutes an ordinary file
at the same path. It does not redirect an existing job to another Archive.
Inherited locations outside the test directory are never modified.

The existing public-engine assertions now run with and without this outage for:

| Native route | Professional behavior checked |
| --- | --- |
| LIPE | Monthly and quarterly calculations, workbook/PDF and idempotent retry |
| Sales plan | Scenario calculation, execution receipt, reopening and retry |
| Variance analysis | Numeric totals, report/chart files, complete artifact list and retry |
| Business valuation | Method results, report/workbook/PDF, ready/partial/blocked statuses and retry |
| Business planning | Calculations and complete reports for ready/partial/blocked/idea cases |
| Rating legalita | Public assessment status, exact dossier download and retry |
| Adeguati assetti | Append reviewed decision, retain proposal/history and deliver files |
| AML | Append exact decision, retain findings/history and deliver files |
| ESG | Read complete version/dependency records and deliver exact existing draft bytes |
| Patent Box | Public proposal/review/calculation, expected deductions, Word/PDF delivery and retry |
| Scissione | Append exact reviewed record, retain prior version and deliver seven artifacts |
| Financial analysis | All eight reviewed packs, exact copied case/source bytes and normal prepared outputs |
| Management control | Reporting and costing calculations, ready/partial/blocked statuses and eight artifact hashes |
| Treasury preparation | Selected source inspection, cash forecast, first version, reopening and retry |
| Invoice XML | Six supported proposal variants, exact public XML/export artifacts, retry and no transmission |
| Journal-bank native preparation | Input inspection, mapping review, real match and result view |
| Purchase-invoice native supervisor | Fresh and existing jobs, real producer completion, same-key retry and exact population |
| Open-item native intake | Five languages, complete workbook/assurance package and exact retry |
| CNC | Retain complete public snapshot/memo and exact retry without professional approval |
| Bandi | Public validation, complete HTML dossier, byte hash and exact retry |
| INPS | Six explicit review choices, unchanged memo, persisted decisions and exact retry |
| Registro Imprese SARI | Five language/jurisdiction combinations, actual source inventory and intake drafts, exact retry |

ESG here verifies existing-result delivery; AML, Assetti and Scissione begin with
prepared proposals and verify continuation. They are not claims of complete
first-intake outage acceptance. These tests do not turn failed/missing privacy
reporting into a successful receipt. Direct result-listing regressions separately
assert the unavailable-reporting status and unavailable recovery checkpoint.

The native Patent Box outage initially failed on Archive state validation. It
passed after independent binding storage and lookup were implemented. The
selected direct write/list test also failed before its fix. The first broader
Scissione selection accidentally included two package tests; both correctly
stopped on stale privacy fingerprints after the source changes. Those package
checks remain pending the required semantic review and regeneration, not waived.

Latest follow-up results: 58 native cases passed across the eleven routes above
(including healthy controls); 371 shared delivery, independent-work, optional
service and retained-binding cases passed; the earlier focused concurrency and
fault-isolation run passed 101 cases. Black, selected Isort checks and
`git diff --check` passed. These are source checks, not a released build.

Remaining scope includes first-intake coverage for the other professional
engines, auditing other direct bound-job lifecycle operations for premature
Archive-state validation, missing-report acceptance evidence, the privacy
source review/refresh, complete release gates, rebuilt host packages and actual
installed-session acceptance. Do not mark the goal complete from this matrix.

The next follow-up also added 76 shared lifecycle scenarios: each of the 38
registered IDs both resumes a prepared job and imports/verifies new selected
evidence into the retained engagement before preparing, starting, saving,
finalizing and completing another job with Archive configuration unavailable.
This is lifecycle coverage, not a claim of 76 professional calculations.
Both start/completion and the new-source path failed before their respective
repairs. Two test-harness assumptions were corrected from inspected public
responses: import returns `input_id`, and checkpoint status is under `recovery`.
No production response schema was changed to accommodate those tests.

Additional native source checks passed 38 cases across financial analysis,
management control, treasury preparation and invoice XML, followed by six bank
and purchase-invoice cases. Another 36 outage/healthy-control cases passed for
open-item intake, CNC continuation, Bandi packaging, INPS review application and
SARI first intake. The final focused lifecycle/fault-isolation/concurrency/binding
run passed 184 cases after the new-source verification fix.

### Further producer and reporting-boundary checks

Twelve healthy/outage cases passed for actual journal sampling, vouching,
report building, concordato workpapers, archive organization and the two-stage
client-file-preparation/new-client pipeline. These start the standalone or
portable producers with configuration/profile/reporting service paths made
unusable. Ten further healthy/outage cases passed for the complete Centrale
Rischi producer, standalone transformation authoring/calculation/export and
merger P1 workpaper export. The standalone case stores remain available.

Inspection then found a distinct reporting-content dependency in shared Python
and Node output closure. An interrupted report JSON or wrong reporting identity
stopped validation of otherwise valid professional outputs. The regression
failed before repair. Twenty cases now cover the four report faults across
open-item reconciliation, vouching, journal sampling, report-builder and
report-enti-locali. The damaged report bytes remain unchanged and both runtimes
emit an explicit unverified-reporting warning. This does not verify or repair
the report or its receipt. Wrong professional workflow context, symbolic links
and changed transaction-owned report bytes remain rejected. The report-builder
alias case also verifies that ownership does not depend on a usable report.

The combined reporting-output-boundary, independent-work and optional-service
run passed 390 cases after this repair. Source checks remain distinct from
package/installed acceptance; the shared contract change adds privacy fingerprints
and host packages to refresh before release.

## Inspected starting point

- Reporting startup/finalization and checkpoint writes already have partial
  failure isolation. Source tests cover these individual boundaries.
- `work-continuity.md` still requires a retained recovery checkpoint before
  dependent work. Most component instructions require Archive setup before
  inspection. These instructions can turn secondary storage failures into
  processing prerequisites.
- The shared engine context validates exact inputs and output ownership without
  an index or an Archive service connection. The portable local ledger can
  supply those contracts independently of Archive discovery/configuration.
- The current standalone helper supports only three engines. Simply using it
  for all workflows would break engines that need the richer portable context.
- Indexing, semantic tidying, checkpointing and recovery are distinct operations.
  Failure of one must not imply failure of unrelated professional work.

## Implementation sequence

1. Add a maintained independent working-folder route using the existing
   portable execution contracts. It must need no configured Archive, index,
   profile, network or registration. A software-managed general workspace is
   explicitly unregistered; it does not assert a professional client identity.
   Preserve an explicitly supplied known client identity when available.
   Retain exact inputs, an idempotent request, run identity and outputs.
2. Keep processing/delivery status separate from Archive status. Provide local
   completion and explicit retryable registration of retained work without
   recalculation. Never overwrite another client/run, duplicate a committed
   retry, infer missing client ownership, or announce successful archiving before
   byte verification. Use existing restore support for already-started runs.
3. Repair remaining optional-service exceptions and instructions. A failed
   index, private pointer, checkpoint or readable index must not block work
   whose actual source/output contracts remain usable. A failed filing operation
   stops that operation, not unrelated work. Report reduced recovery coverage.
4. Test failure before preparation, during work and after useful output exists;
   verify unchanged bytes, repeatable retries and distinct result/archive
   outcomes. Exercise several real engine entrypoints and audit every exposed
   route, distinguishing source coverage from installed acceptance.
5. Refresh affected privacy evidence and generated packages; run focused source
   checks, package integrity and required repository gates. Report any source,
   package or installed-host gaps explicitly. Do not touch Marketplace state.

## Acceptance criteria

- With selected readable inputs and a writable authorized task folder, an
  unavailable Archive does not require another setup conversation or prevent
  calculation/drafting and delivery.
- A useful saved output remains available when optional finalization, reporting,
  indexing, registration or checkpoint services fail.
- Failure status is durable when storage permits, visible independently of the
  professional result, and never falsely marked complete.
- An exact retry retains the same job and saved outputs. Recovery never accepts
  altered evidence as the original or repeats already completed professional work.
- Missing required evidence, damaged sole execution copies, unavailable actual
  output storage, or ambiguous authorization remain specific affected-step
  failures; no blanket catch converts them into success.

## Implementation and evidence (2026-11-10)

The plan was recorded before implementation. Work is isolated from the primary
checkout's existing changes and based on released `origin/main` at `3ae9b2d107`.

- `work_folder.py` implements preparation, reopening, delivery and exact-byte
  archival retry using the existing portable ledger. It does not import
  `archive_core` or require its profile, configuration or index.
- The normal context and ledger loaders now verify intact execution copies when
  optional recovery is unavailable. Changed or missing copies still fail.
- Checkpoint profile failures and unavailable reporting/declaration modules are
  isolated. Processing, archiving and privacy-report outcomes remain separate.
- Interrupted exclusive copies retain their partial bytes and resume the same
  selected job. Foreign identities, different committed bytes, sibling jobs and
  modified completed artifacts are not silently adopted or overwritten.
- No model judgment was replaced. Exact identity/hash/ownership checks are
  appropriate here because their correctness is mechanically verifiable.

### Route audit

All 55 exposed Vera entrypoints in the Geneva catalogue were inspected: each
already requires `work-continuity.md`. Their entrypoint bytes are unchanged; the
updated shared reference now explicitly overrides generic Archive prerequisites.
The detailed fallback reference is loaded only after an observed Archive failure.

The portable route covers the 38 registered client-workflow IDs. Twelve distinct
professional routes have direct context-compatibility regressions; real Treasury
calculation and the legal-question/document inspection entrypoints exercise the
fallback through ordinary engine contracts. Existing tests also cover normal
Archive recovery, concurrency, MCP continuity and standalone legal routes.
This is shared-route coverage, not an assertion that all 55 professional engines
were independently accepted end to end.

Fusione retains its own case storage and selected-file `import_evidence` route;
its existing Archive adapter still validates actual selected evidence.
Trasformazione explicitly uses its own local prototype folder without an Archive
adapter. Studio-wide and chat-only routes retain ordinary task storage. Actual
missing upstream evidence remains an affected-step limitation.

The four Archive functions remain distinct: indexing may be pending while selected
files remain usable; restart uses the admitted context without repeating intake;
tidying stops its failed file operation; recovery uses verified surviving copies
or existing restore support without claiming missing progress was recovered.

### Release validation

Source candidates: Vera 0.1.608, Clara 0.1.408, Lucia 0.1.231 and Archive 0.1.77.
The shared contract change requires rebuilding dependent host packages. No Clara
workflow was used as a comparator. Marketplace state is outside this change.

The shared privacy-surface-review process reviewed the new local copies,
metadata returned to the model, separate reporting outcome, retained partial
copies and explicit later archival transfer. The Archive workstream's five
localized data disclosures were updated; dependent fingerprints are regenerated
from this reviewed source. This does not claim reporting passed in an unavailable
service environment.

Package build, broader test results and installed acceptance are recorded below
when actually observed; source tests alone do not establish an installed fix.

- 50 focused failure/CLI tests pass, including all six helper commands and the
  exact documented managed-launcher examples. Black, Isort, Mypy and Bandit pass
  for the new helper; changed legacy helper formatting also passes.
- 316 wider Archive identity, output, finalization, recovery, component and
  readable-index regressions pass. The adoption run reached 89.07% coverage
  (new helper 92%); two initial failures were missing, not-yet-built Cowork ZIPs.
- All three product builds completed. A final Vera-only rebuild incorporates
  the corrected launcher examples; parity and final package results follow.
- The selected local `vera@mp-vera` installation was updated through supported
  commands to 0.1.608. Its actual managed CLI prepared, inspected, delivered,
  reopened and archived the same synthetic job with Archive state/profile
  pointing at a file instead of a usable folder. A failed destination copy
  returned `archive.pending`; retry returned `saved`, one run and two outputs.
  Search indexing remained explicitly `not_refreshed`.
- Installed acceptance caught a wrong option order in the new documentation
  (`run --module` instead of `--module ... run`). The examples and their new
  launcher regression were corrected before the final candidate. The sandbox
  initially denied the shared runtime lock; authorized access recovered it.
- The installed inspection route returned privacy `not_applicable` with reason
  `pipeline_not_selected`; this is not a passed reporting test. The actual
  Treasury calculation is covered by source acceptance with isolated reporting.
- This conversation still exposes Vera 0.1.607 skills. Installed CLI acceptance
  does not establish that these old conversation instructions changed; a fresh
  model conversation remains an explicit acceptance limit.
- The final adoption/recovery suite passes: **225 passed, 3 skipped**, with
  **89.07%** combined coverage. Final Vera host builds pass after the command
  correction. The installed final helper and reference were byte-compared with
  source. The active-session check correctly reports the obsolete exposed path.

### CI follow-up (2026-11-11)

PR #979 initially passed 102/106 checks. The three native-boundary OS jobs all
rejected a symlink correctly but failed an assertion against the earlier recovery
error wording. The test now asserts the execution validator's real-directory
error and still verifies no run-state mutation. All 11 isolation tests pass.
The remaining failure was a stale generated workflow registry: regeneration adds
the new helper entrypoint. No production validation was weakened for CI.

The final local package/update suite passes **416 tests, 2 skipped**. Source and
generated package parity were checked; the registry change triggers a final Vera
rebuild. The resumed host now exposes the actual 0.1.608 skill path, and the live
installed-product check passes for exactly one enabled `vera@mp-vera` installation.
This supersedes the earlier stale-catalog observation. The managed CLI acceptance
remains the evidenced runtime boundary; it is not a claim about all 55 workflows.

### Follow-up CI browser setup repair (PR #983)

At commit `baa35b1dd`, the Ubuntu `one-review` and `agenzia-acquisition`
jobs failed twice before executing tests: Playwright's unconditional system
package installation could not resolve Ubuntu mirrors. Logs confirmed Chromium's
core shared libraries were already installed; the failed downloads were font/X11
packages. The two jobs now install Chromium, attempt an actual headless launch,
and install system dependencies only if that launch fails. A failed dependency
installation or a second failed launch still fails the job. Test commands,
assertions and coverage thresholds are unchanged.

Both workflow blocks passed YAML/shell validation and four simulated cases:
available browser, missing dependencies recovered by installation, failed
installation, and persistent launch failure. The exact capability probe also
launched and closed the locally installed Chromium successfully. Remote execution
of the revised setup remains required; this local result does not prove Linux
runner compatibility.

The exact local browser review suite passed 26 tests. The offline acquisition
suite passed 79 tests at 80.84% coverage. Initial restricted browser launches
produced 22 UI failures and seven acquisition setup errors; unchanged suites
passed after authorized browser access. No live tax portal or client data was
used. The original follow-up CI had 90 passes, two setup failures and 27 pending
jobs when the setup failures were diagnosed; those results do not establish a
passing final candidate.

The revised Ubuntu acquisition and browser-review jobs both passed remotely.
The Windows acquisition job exposed a CI repair defect: the multiline Bash
block inherited PowerShell and failed parsing the here-document before running.
Both setup steps now explicitly select Bash. YAML inspection verifies that shell
selection and Bash syntax validation passes for both blocks; the Windows rerun
remains the authoritative cross-platform check. No product code or test assertion
was changed for this correction.

### Clean-environment CI follow-up

The macOS and Linux Archive recovery jobs on `d43c1513e` each passed 518 tests
and Windows passed 520 tests, but all three failed the added real bank-engine
outage test at import: the job installed
Archive dependencies but omitted journal-bank-reconciliation requirements,
including `fastexcel`. The workflow now installs that component's declared
requirements. An isolated temporary environment installed the exact amended CI
dependency command and passed the complete recovery suite: 519 passed, three
Windows-only skips, 89.08% coverage. No production import, dependency validation
or test assertion was weakened.

The managed-runtime job separately found stale generated workflow metadata.
Regeneration adds the existing `prepare_posting_review.py` command to the bank
component inventory. This metadata correction does not change executable data
paths, recipients or reporting payloads. The affected Vera workstream fingerprint
was reviewed/refreshed and its generated contract projections regenerated.
The local managed-runtime suite passed 358 tests (eight platform skips) at 81.95%
coverage; Cowork session coverage passed nine tests (three Windows-only skips)
at 94.87%; Mypy reported no issues in 30 source files. Vera host packages are
rebuilt from the corrected registry before the next CI candidate.

The teaching-kits job separately failed before tests on the same Ubuntu mirror
DNS outage during unconditional Chromium system-dependency installation. Its
setup now uses the exact capability probe already passed remotely by the UI and
acquisition jobs, with explicit Bash. YAML inspection confirms byte-identical
probe code and Bash syntax validation passes; all teaching assertions remain.

Final local follow-up verification: all Vera host builds and source-to-package
checks passed at 0.1.615. Package/update tests completed with 415 passed, one
skipped and two failures. One is the pre-existing Clara public update notice
(0.1.248 versus the now-observed local curated 0.1.407). The other is the
working-tree version assertion comparing the corrected registry with `HEAD`,
which already contains this unreleased 0.1.615 candidate. Inspection confirms
origin/main remains Vera 0.1.613 and the only other open release PR is #982 at
0.1.614; the candidate has not been installed or published. The release version
increase is retained without changing production version metadata just to satisfy
that intermediate working-tree comparison. Rerun that check on the committed
candidate; preserve this failure record. No Marketplace metadata was changed.

# Vera workflow continuity audit

The requested outcome covers every Vera workflow, with Studio Archive as the
shared persistence boundary. Resolve prerequisites before dependent work,
retain passed startup choices, and recover operational failures without losing
work or restarting the user's job. An archive destination may be a general
folder such as Vari; its internal ID is software-managed, not a professional
identity or an automatic request for client onboarding.

This audit is in progress. Source changes and narrow regressions do not establish
all-workflow or installed-host acceptance.

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

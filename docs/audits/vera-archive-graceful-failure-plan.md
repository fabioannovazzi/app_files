# Studio Archive graceful failure — implementation plan

Goal: an Archive infrastructure failure must not, by itself, stop otherwise
possible processing or delivery. This applies across Vera, not only accounting.
Professional source validation and real missing inputs remain separate.

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

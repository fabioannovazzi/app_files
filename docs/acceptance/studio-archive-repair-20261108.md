# Studio Archive repair — 8 November 2026

## Scope

Repair of four real course-acceptance failures with fictional inputs: isolated
case inventory/import, unavailable tutorial binding, mismatched artifact ID
constraints, and missing retry progress. These were not customer-data outages.
PR959 covered run-bound writes, not every engagement-only operation.

## Changes

- Engagement inventory/import, client reopen and continuation resolve verified
  retained run bindings. Exact client/engagement IDs and sealed run identity are
  checked. Conflicting live locations are rejected rather than guessed. Session
  archive selection is unchanged. Imports still reject another archive's scope.
- A prepared tutorial exposes whether native Archive addressing is ready. Its
  binding can be retried through the official helper without recreating the job.
  Host filesystem permission may still be required; its actual denial is not
  silently bypassed. Prepared files survive failed bookkeeping.
- Native artifact schemas expose the existing lowercase ID pattern. File names
  remain independent and can include uppercase characters.
- Native retries can carry the retained original incident report UUID through
  the managed launcher. Exact-operation progress is durable before a status poll
  or report acknowledgement. Different episodes get different event IDs. This
  records execution evidence; original-task verification still owns closure.
- Privacy-error recording and the readable Archive projection use retained case
  routing. Reporting failure remains separate from the pipeline result.

## Evidence and validation

The installed Vera 0.1.597 reproduction was rerun before editing: run lookup
succeeded while inventory/import failed with another archive selected; both
succeeded with the tutorial archive selected.

The focused regression batch passed 152 tests; added ambiguity and foreign-source
tests also passed. The incident CI-equivalent suite passed 562 tests, skipped 8,
and measured 83.23% coverage. Black, Isort, Mypy and Bandit checks passed for
the changed checked helpers.

Focused regressions cover cross-session writes, fresh-process inventory,
engagement import/reopen/continuation, denied binding retry, altered binding
hashes, conflicting copies, foreign source scopes, native ID schema and incident
retry identity, delayed report delivery and separate failure episodes.

A built Vera 0.1.601 package was exercised through its native JSON-RPC server and
actual managed runtime. Inventory, import, reopen, continuation, start, authored
save, finalization and completion succeeded without changing the selected
archive. This is package/native-transport acceptance, not proof that an already
open Codex chat has updated. Enabled Vera in the inspected host was 0.1.597.

The native acceptance initially encountered a host sandbox denial opening the
shared runtime code lock. Its prepared case was retained; the same case passed
after the authorized filesystem-permission retry. The separate incident test
suite initially hit loopback socket restrictions and was rerun with local test
server permission. A package-dependent onboarding test was initially run before
its generated ZIP existed; its isolated rerun uses the completed build.

The native continuation used client-file-preparation; automatic privacy reporting
returned `not_applicable` / `pipeline_not_selected`. That is not a passed privacy
report or evidence that no data reached the model. Selected-pipeline reporting
has separate regression coverage. No original case was rerun or modified.

## Original incidents and rollout limits

Retained original transcripts establish recovery of the save and finalization
operations. The import workaround did not recover the failed native import.
Neither source tests nor deployment establish recovery of a customer's original
operation. Windows incidents remain open pending affected-machine testing.

Two proposed historical recovery supplements were blocked by automatic approval
review because they would transmit operation identifiers and recovery history to
Vera's incident service. They remain local, pending explicit transmission approval.
No incident closure, customer communication or monitor schedule change was made.
No Marketplace upload, submission or publication is part of this release.

The first CI run found an old assertion requiring the readable view to remain
unavailable after session loss. It now verifies the repaired ready view and its
actual index file, while still requiring the lost session configuration to stay
absent. The recovery suite then passed 150 tests, skipped 3, with 85.43% coverage.
A separate Clara Linux job failed before product execution because GitHub's
Python download returned HTTP 504; it is an infrastructure failure, not package
acceptance evidence.

The next CI teaching stage passed 1,742 tests with 3 skips and 85.05% coverage,
then failed its editorial source-fingerprint check. Eighteen reviewed courses
changed only in their source records; complete lesson content and execution
contracts are identical to origin/main. Their source-binding reviews now record
the Archive/incident repairs without replacing historical editorial judgments.
The downloaded native JUnit evidence validates all 58 kits and 258 locales
against the exact current course hashes. Final-head CI remains required.

Refreshing those review records also required refreshing their owning Vera
local-onboarding and Clara teaching privacy fingerprints. The next package build
reported that stale dependency before execution. Reviewed changes add only
source-review evidence, with no changed model payload, transport or recipient.
The affected privacy contracts and all host packages were regenerated; the
course hashes still validate against the retained native JUnit evidence.

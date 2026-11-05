# Windows execution snapshot repair

Observed: the production reconciliation incident
`cc4baa5e-47d7-4889-89ab-6c6dd41d8afd` contains a November 4 Vera 0.1.560
installation-preparation `FileNotFoundError` report
`9356790c-6021-4d2e-9381-055b8f95b4a2`. It has no traceback or missing filename.
An older report in that grouped incident has a reviewed Windows error 3 for
`modules/presenza-digitale-studio/skills/presenza-digitale-studio/references/website-quality-standard.md`
in its runtime snapshot. That file exists in the source-built ZIP. Shared
snapshot publication replaces a short staging directory name with a 64-character
digest while retaining nested package filenames.

Inferred: a Windows path-length failure is a supported failure mode of that
snapshot implementation. It is a candidate explanation for the customer symptom,
not a diagnosis established by grouping the reports.

Unknown: the November 4 report's exact failing path, source line and Windows
error number; whether this change restores the customer's installation and
original reconciliation. The screenshot's matching time and workflow do not
independently establish machine ownership. No customer files were accessed.

The subsequently supplied error also names `review_output_transaction.cjs` and
a separate file-access service failure to locate Python. Source inspection found
that the Archive MCP resolver ignored the existing shared managed interpreter,
used POSIX-only virtual-environment paths, and returned `python3` without testing
whether it could execute. Two real MCP file-access regressions with a working
Python but no `python3` alias fail with `ENOENT` against the original server and
pass against the repair: one uses the existing managed environment with empty
PATH, and one uses an available `python` launcher. No client or engagement is
created by these selected-file checks.

Archive now checks the configured interpreter, the same existing managed runtime
used by native execution, platform-correct environment paths and available
launchers. A fixed isolated standard-library probe establishes executable
capability; it downloads nothing, reads no selected document and sends nothing
to a model or network. A missing/broken alias cannot hide a working interpreter.
The probe deadline bounds only interpreter discovery, not professional work.
If none can execute, the caller retains its actual spawn-error/reporting path.

The shared verifier now uses Win32 extended paths when reading the installed
package as well as for its private code store and temporary execution copies.
Clean, uncopied roots retain their original return path. It retains the same storage location, exact inventory,
digest checks, link checks, kernel leases and collection rules. It changes no
machine policy or permissions. Path normalization is a mechanical filesystem
operation; it makes no semantic decision about professional inputs.

Preparation reporting additionally retains source coordinates from the
independently verified verifier, a numeric Windows error when available and the
failed pathname's character count. It excludes the actual pathname, exception
message/values, locals and document contents. Capture completeness does not mean
that the cause is diagnosed or the operation recovered. Existing reporting failure
fallback remains visible. Privacy service descriptions record these exact fields.

The native Windows regression uses both reported package-relative filenames,
including the reconciliation module's vendored `review_output_transaction.cjs`,
a long runtime parent, short and long installed-package roots, both ordinary
and already extended configuration paths,
and a simulated legacy Win32 path limit even on CI images with long paths enabled.
It checks successful verification/read and collection of the complete snapshot.
An independent Windows CI job runs this regression without waiting for package
builds. Existing tamper, link and lifetime tests remain applicable.

Validation preparation encountered these recoverable blocks:

| Block | Effect and recovery |
| --- | --- |
| Stale privacy source fingerprints | Packaging stopped. Reviewed the changed runtime/report payload and unchanged recipients, updated its service descriptions, then refreshed the affected source reviews and generated contracts. This is agent engineering review, not professional or legal approval. |
| Version-bound localization catalogue | The release check rejected the changed manifest. Verified exact skill entrypoint bytes and IDs were unchanged, then rebound the existing catalogue/assessment without changing jurisdiction judgments. |
| Course implementation hashes | Prepared kits referenced the previous verifier bytes. Regenerated the kits and refreshed affected onboarding/prepared-course reviews. Lesson content and professional acceptance were not inferred from hash refreshes. |
| Package tests started before archive generation finished | The premature run had 20 missing-archive failures and 79.23% coverage. It is not a product result; package verification must be repeated after all archives exist. |
| Incorrect initial coverage selector | A filesystem filename was supplied as a coverage module selector, producing no data. Use the repository's `tests/plugin_runtime.coveragerc` instead. |
| Partial vendored regression fixture | Adding only the reported CJS file made the component validator correctly require its companion PDF vendor. Fixed the test to copy the complete existing vendor tree; production validation was preserved. |
| Invalid negative-test tool arguments | The initial no-interpreter test supplied a run ID to an input-verification tool that does not accept it. Used the supported checkpoint operation with all three retained IDs; the test then verified the original spawn error and separate reporting gap. |

Local source checks passed with 112 tests, two native Windows cases skipped on
macOS, and Black, Isort, Mypy and Bandit checks. The final managed-runtime suite
passed 326 tests with two native Windows skips and 81.90% coverage after archive
generation. Final package checks and native Windows CI are recorded with the repair PR. Local
CLI evidence does not establish an installed customer or fresh-chat acceptance.
No reconciliation or its run-level privacy report was produced in this repair.
The original pipeline outcome remains failed/unexecuted; its incomplete diagnostic
capture and lack of recovery remain explicit. No Marketplace action is authorized
by this repair.

After the additional failure was specified, the expanded local source suite
passed 268 tests with four native Windows path cases skipped on macOS. A subsequent
extension applies the same namespace handling to the original installation,
retaining the return-path behavior of clean uncopied roots; its local verifier,
reporting and Archive suite passed 260 tests with eight native Windows skips. Obsolete
CI runs for the first candidate were cancelled, retaining their evidence, so a
fresh candidate must pass all CI including eight native snapshot cases and both
actual file-access interpreter routes. The first candidate's two Windows path
passes alone do not validate this expanded release.

The complete `c5f034961` candidate subsequently passed all 103 CI checks,
including eight native Windows snapshot cases and both real file-access routes.
The accounting job first stopped at an official-taxonomy download timeout; its
retry downloaded the checksum-verified package and passed. GitHub cancelled the
unstarted final macOS helper job for hosted ARM runner capacity; that job passed
on retry. Neither recovered infrastructure block was counted as a product pass.

Before merge, main advanced to `dcbd84fe9` through PR #951 and deployed Vera
0.1.567, Clara 0.1.379 and Lucia 0.1.205. This repair integrates those Archive,
incident-outbox and native dependency changes without reverting them. Production
source merged without conflicts; release metadata and generated packages require
rebuilding. The combined candidate is Vera 0.1.570, Clara 0.1.380, Lucia 0.1.206
and Studio Archive 0.1.72, above current main and all inspected open candidates.
Reviewed privacy descriptions retain both the main outbox behavior and the
Windows preparation fields. Course objects are identical to integrated main
apart from source inventories; existing localized judgments remain historical,
with fresh current-digest native CI required. Skill entrypoint bytes match main,
so the localization refresh changes manifest binding only. The old candidate's
ZIPs are not deployable for this combined source; fresh CI and exact new artifacts
must pass before merge, deployment and the authorized customer email.

Combined-source validation first ran inside the agent filesystem/process sandbox:
323 focused tests passed, eight Windows cases skipped on macOS, and three native
process tests failed. The macOS nested sandbox probe could not apply its profile;
the two descendant-cancellation checks retained a running result. Repeating only
those three tests outside the nested agent sandbox passed all three (5.75 s).
No production or test assertion was weakened. Managed-runtime validation passed
326 tests, with eight Windows skips and 81.91% coverage. Fresh CI remains required.

The next candidate `2578c5cbd` again passed the eight native Windows snapshot
cases and both real MCP file-access routes. While its remaining CI was running,
PR #952 advanced main to `6ddb10c44`, adding direct bank CSV downloads in Vera
0.1.568. This repair also integrates that source, package-builder update,
localization assessment and privacy/workflow declarations. Its 212 conflicts
were confined to generated artifacts and release metadata; the Windows verifier,
Archive interpreter fix and earlier incident/native fixes remain unchanged.
Only this repair's five unfinished obsolete workflows were cancelled; completed
evidence remains historical. No unrelated branch/run was cancelled. The combined
release stays at 0.1.570/0.1.380/0.1.206, above the inspected open candidates,
and requires fresh package checks and CI. Existing authored course objects still
match main exactly apart from source inventories; no course review changed in
this integration. Old candidate ZIPs remain ineligible for deployment.

The bank-main integration passed 350 focused source tests with eight Windows
skips on macOS, including all native process checks and the preserved bank CSV
workflow. Its runtime suite passed 326 tests with eight Windows skips and
81.91% coverage. All 12 distributions rebuilt with local MCP startup checks.
These are combined-source checks, not customer-machine acceptance.

The first combined package run passed 431 tests but failed its release-version
check: newly integrated bank code reused the earlier 0.1.570 candidate identity.
That check prevents Codex from reusing same-version cached code. Vera is therefore
rebuilt as 0.1.571, above main and every inspected open candidate; Clara and Lucia
retain 0.1.380 and 0.1.206 because their source did not change in this integration.
No release check or product integrity rule was weakened. Final package checks and
fresh current-head CI remain required.

The bank-main candidate `ece61a1fd` passed its native Windows eight-plus-two
regressions, 432 local package checks, and 108 CI checks before main advanced
again through PR #949 to `2c3669d45` (Vera course-completion status, version
0.1.569). Only this repair's two unfinished obsolete workflows were cancelled;
neither a product failure nor customer recovery was inferred. This integration
retains main's course-completion/onboarding implementation and its common course
projection/catalogue changes. Generated and release-metadata conflicts are
regenerated; the actual Windows verifier and Archive selector remain unchanged.
The new candidate uses distinct cache identities Vera 0.1.572, Clara 0.1.381 and
Lucia 0.1.207. Fresh current-head CI and artifacts are required again. The
authorised customer email remains unsent until deployment and public ZIP
verification; no inter-chat coordination message has been authorised or sent.

This combined source passed 435 focused tests (eight native Windows cases
skipped on macOS), including course completion, product scope, teaching, bank
downloads, incident/native execution and both startup repairs. The runtime suite
passed 326 tests with eight Windows skips and 81.91% coverage. All 12 host
distributions rebuilt with local MCP startup checks at 0.1.572/0.1.381/0.1.207.
Customer-machine recovery remains unverified.

Final package/update/index checks passed 432 tests with two environment skips;
all three Codex ZIP/source drift checks passed after the complete rebuild.

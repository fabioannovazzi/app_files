# Studio Archive isolation and Windows pipeline repair

The Windows bug report covered Bilancio's Unix-only lock import, financial
analysis and sales planning's descriptor-relative filesystem operations, and
Journal–Bank's Unix pipe selector/process-group operations. The Archive incident
reports separately showed `Run input manifest shape is invalid` during listing
and recovery. The invalid original manifest contents have not been received.

This release integrates PR #864 at `5f356f1a2191` (Bilancio locking) and PR #866
at `4370e78cf321` (Archive JSON output encoding), preserving their source history.
Main commit `28623647c7a3` (PR #865, per-run Cowork reporting and native binding)
is also retained. The combined release versions are Vera 0.1.417, Clara 0.1.304
and Lucia 0.1.128.

## Behavior

- Archive inventory, recovery and native navigation isolate an invalid run and
  keep healthy runs usable. An incomplete recovery explicitly reports blocked
  records. Invalid records cannot supply execution context, upstream artifacts
  or closure actions and are never rewritten, resealed or replaced. A retry
  with the same request identity still fails on the original invalid run.
  Unrelated preparation can proceed only when all immutable run headers remain
  valid, so an unreadable idempotency identity cannot conceal a duplicate.
- The native Archive list retains its sortable date-string contract for blocked
  rows. A regression exercises the actual workspace JavaScript and confirms
  blocked rows have no action buttons while healthy runs remain startable.
- Native workspace review saves use an exclusive Windows handle with deletion
  on close, including process exit. A legacy lock left by the old open-stream
  deletion failure is recoverable only after exclusive acquisition proves it is
  one empty regular non-reparse file with one link. Active writers and foreign
  file content remain untouched. No file age or PID guess authorizes cleanup.
  The mechanism follows the native sharing and deletion contracts documented in
  [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
- Financial analysis and sales planning use native Windows directory handles,
  handle-relative file opens, identity and byte checks, exclusive output
  creation, and exact-handle cleanup. Reparse points and multiple hard links
  are rejected. Directory list access makes Windows sharing restrictions
  effective; attributes-only access did not prevent rename in the first test.
  The existing POSIX route remains in place. Errors raised inside a protected
  operation retain their identity rather than being misreported as failure to
  acquire the directory.
- Journal–Bank has bounded Windows pipe capture and a kill-on-close Job Object.
  A fixed gate prevents command execution before successful job assignment.
  Timeout, excessive output and ordinary exit terminate descendants. The new
  helper is included in Python and JavaScript implementation receipts.

The deterministic choice here is limited to mechanically verifiable integrity,
file identity, lifecycle and receipt controls. It does not replace semantic or
professional judgment.

## Privacy review

The new Windows helpers operate locally and add no network destination or model
payload. Archive blocked rows expose an existing ordinary directory identifier
and a fixed status, never values from the invalid manifest. Existing execution,
handoff, source minimization, professional approval and receipt validation remain
in force. Source registers record those controls; product and course dependency
fingerprints are regenerated from reviewed source.

All non-source fields of the six affected compiled courses were compared with
main at `9361a54e9`: content, languages, inputs, exercises, checkpoints and timing
were identical. Existing editorial judgments and historical artifact reviews
are preserved. Current native execution remains an independent CI requirement. The final
combined catalogue retains all 55 unchanged skill entrypoints and prior Geneva
judgments; only its release version binding changes.

## Evidence and limits

Native Windows run `39171312432` on `3af718c2f` passed all 142 tests:
22 file/process boundary tests at 88.74% helper coverage, six Archive isolation,
12 readable/encoding, 39 native navigation/save/legacy-lock recovery,
24 financial-analysis, ten FDD hardening and 29 sales-plan tests. The recovery
cases preserve active legacy writers, nonempty files, hard links and symbolic
links, and verify cleanup after process exit. All three product formats matched
source; package/update tests passed 406 tests with two explicit skips.

Local combined Archive regressions passed 232 tests, Bilancio passed 43 and
Journal–Bank passed all 473 tests together. PR #865 integration preserved the
Windows/Archive implementation bytes and the incoming reporting implementation.
All non-source course fields match both parents, and all 55 catalogue skill
entrypoints remain unchanged. Full CI on the final combined head remains the
merge and deployment gate.

The isolated semantic worker remains qualified only for its pinned macOS host
profiles. Windows process lifecycle tests do **not** qualify its filesystem
sandbox or enable an unrestricted worker. A Windows/Codex host qualification and
the affected user's original-run acceptance are separate outstanding checks.
The original damaged Archive manifests are preserved and are not claimed repaired.
No Marketplace action is part of this release.

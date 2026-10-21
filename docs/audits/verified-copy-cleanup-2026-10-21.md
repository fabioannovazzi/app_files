# Verified execution code-copy lifecycle

Observed: repeated fresh `vera-verified-*` materializations accumulated in OS
temporary storage. The verifier removed partial copies only for selected
preparation errors. Successful API calls returned a Path without an owner that
released it. Shell preflight guidance explicitly relied on OS cleanup.

The shared implementation now records only its own freshly created directory's
PID/device/inode identity. Managed commands and dependency checks release their
copies in finally blocks; process-exit cleanup retries remaining owned copies.
Cancellation during preparation also releases partially written code. Cleanup
failure is logged without replacing a helper's result or original exception.
Borrowed roots, installations, replaced directories and symlink targets are not
removed. Existing file inventory, digest and single-link validation remains.

The native service bootstrap now verifies and serves in one owning Python
process. After transport closure that process waits for its own persistent
workers before releasing the snapshot; jobs and their retained results survive
connection restart. A separate bootstrap copy lives until that owner closes.

Standalone preflight releases its verification copy before returning the
installed root. Execution guidance requires the managed launcher, which prepares
its own verified execution copy for the duration of the helper. Callers must keep
professional inputs and outputs outside code roots, as already required.

## Privacy review

The reviewed change is local lifetime management of verified program bytes.
There is no new model-context payload, connector, recipient, network operation,
client-data processing or reporting phase. Case records, source files, professional
outputs, diagnostics and signed receipts retain their existing retention rules.
Technical stderr may contain a cleanup warning with a temporary code path; the
existing incident transport and semantic review boundaries still apply.

Managed-runtime retention records now describe explicit cleanup and its limits.
Affected workflow/service fingerprints were refreshed after reviewing this diff.
Canonical version changes and regenerated course version/digest references cause
additional mechanical fingerprint changes without altering lesson content or
model-data contracts. Shared source was synchronized into all three products.

## Verification and limits

Regression coverage includes clean and hardlinked installations, intact digest
validation, success, nonzero exits, raised errors, cooperative cancellation,
preparation interruption, process-exit cleanup, borrowed roots, directory
replacement and Windows-style locked-file refusal/retry. The existing cross-OS
launcher CI job runs these tests on Linux, macOS and Windows.

Hard termination, power loss, or files still locked at process exit can leave an
orphan. No historical-copy sweeper was added: filename/age alone does not prove
ownership or that another process has finished. This change does not remove old
copies, edit the installed host cache, or update an already-open conversation.
Source/package/CI evidence is separate from native-host acceptance and actual
user-workflow privacy-report delivery. No native Windows session or fresh-host
professional run is claimed by this source review. Marketplace is untouched.

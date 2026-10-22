# Verified code lifetime after native and CLI termination

## Observed defect and scope

Installed Vera 0.1.474 removed a verified code snapshot after normal stdin EOF,
but left it and its bootstrap behind after SIGTERM. On this Mac, 1,202 surviving
verified copies occupied 58.160 GiB. The previous repair covered finally/atexit
cleanup and did not establish ownership for orphan recovery.

This repair changes temporary program-code lifetime. It does not alter client
inputs, retained results, professional decisions or the model-data boundary.
The final product versions are Vera 0.1.479, Clara 0.1.342 and Lucia 0.1.167.

## Implementation

The native Node launcher forwards SIGTERM/SIGINT and keeps the Python owner
alive until accepted detached jobs finish. The service stops intake without
cancelling jobs, including when stdin remains open or contains a partial line.
Signal handlers set a plain flag: repeated signals can reenter and deadlock a
threading.Event/Condition mutex. Stress testing exposed that race in an early
candidate and the plain flag removed it.

On POSIX, freshly owned snapshots and bootstraps have private sidecar
schema/device/inode records and shared kernel flock leases. Detached native
workers inherit the snapshot descriptor. CLI command boundaries independently
acquire and pass a shared descriptor to their child before launch. This covers
a killed managed launcher whose helper is still running, even if another native
service starts. The lease is closed only after the child completes or at its
actual process exit. It is not a PID/age heuristic.

Owner cleanup first closes its descriptor, then tries an exclusive lock through
a new open-file description. Upgrading the inherited shared description would
incorrectly upgrade the worker's same flock lock. A later verified startup scans
only explicit lease records and removes an orphan only after exclusive
nonblocking acquisition and matching real-directory identity/ownership. Live
holders, replaced roots, symlinks, malformed records and unmarked historical
copies are retained. Automatic collection requires protocol 2, which includes
native and CLI handoff. Protocol-1 records are retained even without a holder,
because their earlier owners did not guarantee that every CLI child inherited
a lease. Current commands can still borrow those older leases. A regression
failed before this guard and passes after it. Windows retains process-owned cleanup; automatic orphan
recovery is POSIX-only.

## Verification

- 109 native/CLI, verified-copy and automatic-reporting tests passed.
- 290 shared-runtime tests passed with 82.79% coverage; Mypy passed 29 files.
- Real launchers cover normal EOF, bursts of 100 SIGTERM/SIGINT signals sent to
  the launcher/group, idle/busy services, partial stdin and SIGKILL followed by
  startup recovery. Accepted jobs complete once and retain durable results.
- The direct-CLI regression failed before the handoff repair: the reaper deleted
  a surviving helper's code. After repair, the helper reads its code after its
  launcher is killed, completes, and only then becomes eligible for recovery.
- Borrowed CLI leases outlive owner cleanup. Invalid lease records, live code,
  replaced identities, borrowed directories and symlink targets remain safe.
- Source/package parity, full product builds and installed-launcher probes are
  recorded separately from fresh professional host-conversation acceptance.

The release catalogue check caught a stale localization snapshot. The final
manifest binding preserves all 55 professional skill entrypoint byte hashes and
every existing jurisdiction assessment row. No jurisdiction capability is added.

## Privacy and space recovery

Sidecar records contain technical directory identity and stay outside indexed
code and client folders. No new model payload, network operation or recipient
is introduced. Shared service descriptions and source/contract fingerprints are
reviewed for the actual source changes.

Historical recovery is separate from the new sweeper. It verifies every file
against the complete build inventory and SHA-256, rejects unexpected contents
and filesystem objects, and rechecks live process/open-file references plus
directory identity immediately before removal. The overnight pass retains all
copies as new as any live bootstrap, with a conservative 09:00 CEST ceiling.
Running services and workers are never signalled for space recovery.

The two passes removed 1,152 verified unused copies: 60,097,245,184 allocated
bytes (55.970 GiB / 60.097 decimal GB). Five observed detached workers retained
their original start times, and all explicitly protected code directories
remained intact. Recent, live and unverified copies were retained. Exact local
removal and post-recovery evidence is recorded by the recovery operation.

The supported local installation updates retain older caches and services.
Already-running work keeps its code; new sessions use the selected final
installation. No Marketplace operation, native Windows acceptance or fresh
professional workflow acceptance is claimed by these local developer probes.

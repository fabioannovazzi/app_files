# Verified code lifetime after transport termination

## Observed defect

The installed Vera 0.1.474 native launcher left both a full verified code
snapshot and its bootstrap behind when its process group received SIGTERM.
Closing stdin normally removed them. An isolated reproduction initialized the
actual installed launcher without running a client helper. On this Mac, 1,202
surviving verified copies used 58.160 GiB allocated. The previous cleanup repair
covered normal/process-exit paths but not default signal termination, and had
no ownership proof for recovering abandoned snapshots.

## Repair

The Node launcher forwards SIGTERM/SIGINT without exiting before its service.
The Python owner records termination as a stop-intake event, finishes accepted
requests and waits for detached workers. Signal handlers set a plain flag; they
never acquire an Event/Condition mutex, which repeated signals can reenter and
deadlock on the interrupted main thread. A repeated-signal stress run exposed
this failure in the first candidate; it was repaired before installation. A transport reader permits termination
even when stdin remains open or holds a partial message. Signals do not cancel
professional jobs. User-requested job cancellation keeps its existing semantics.

On POSIX, every new snapshot and bootstrap has a private sidecar record of its
device/inode and a shared kernel flock lease. Native workers inherit the
snapshot descriptor across detachment. Closing the owner's descriptor does not
release a worker's inherited lease. Removal obtains an exclusive lock through a
new open-file description, never by upgrading that shared descriptor. This
prevents owner cleanup from deleting live worker code.

A later verified startup scans only these explicit lease records. It removes
an orphan only after exclusive nonblocking acquisition and matching real
directory identity/ownership. Live holders, replaced roots, symlinks, malformed
records and unmarked historical directories are retained. It never discovers
client files by a name/age rule. Forced termination can leave a directory until
the next verified startup; it does not require pretending SIGKILL is catchable.
Windows retains process-owned cleanup; automatic orphan recovery depends on
POSIX kernel leases and is not claimed for Windows.

## Verification

The local runtime/ownership/reporting/index suite passed 111 tests. After
integrating PR #892, the runtime/reporting suite passed 99 tests and the
index/privacy suite passed 85 tests. The shared-runtime suite passed 285 tests
with 82.62% coverage. Three repeated termination batches passed all 24 cases,
each sending bursts of 100 signals. The package/privacy suite passed 479 tests
with two skips before integration; current combined package checks are repeated
for the release. Real
launcher processes cover SIGTERM and SIGINT sent to the Node launcher and its
whole process group, idle and with an accepted persistent job, repeated signals
with stdin still open, and SIGKILL followed by automatic startup recovery.
Detached jobs complete once, retain their durable result and keep their code
until completion. Safety cases preserve live leases, borrowed directories,
replaced directory identities and symlink targets. Formatting, import sorting,
Mypy and medium/high Bandit checks are part of release verification.

## Privacy and recovery boundaries

Lease records hold technical directory identity, not documents, credentials or
professional output. They stay beside OS temporary code storage, outside the
indexed product and client folders. No model-visible payload, hosted recipient,
network operation or reporting authorization is added. Managed-runtime service
records and generated contracts are refreshed for this inspected change.

The one-time historical cleanup is separate from the product sweeper: inspect
live process command/open-file references, fully verify the build index and every
file digest, reject unexpected contents or filesystem objects, and recheck live
references before each removal. The second pass admits overnight copies before 09:00 CEST, reduces that
cutoff to the oldest observed live bootstrap when necessary, and rechecks the
cutoff immediately before deletion. Newer or otherwise uncertain copies are
retained. Running services and workers are never signalled for this recovery.
Exact deletions and reclaimed allocation are recorded locally by the recovery
operation. Package/source checks do not establish a fresh professional
host-conversation acceptance run or replace an already running service.


## Local recovery and installation evidence

The two recovery passes removed 1,152 fully verified unused copies, reclaiming
60,097,245,184 allocated bytes (55.970 GiB / 60.097 decimal GB). Five previously
observed detached workers retained their original process start times after
recovery and installation, and every explicitly protected code directory still
existed. No existing worker was signalled for the recovery or local update.

The supported local catalog/installation commands selected one enabled
`vera@mp-vera` 0.1.476, retaining old caches and source folders. The first combined 0.1.476
Codex ZIP SHA-256 was
`6385c2a41c3f3fdbcc6e906f461b6e46d98c1b594d965b847b1e44611fba5675`.
The actual installed launcher independently passed normal EOF, 100-signal
SIGTERM/SIGINT bursts, and SIGKILL followed by startup recovery. These tests
initialize isolated native services, not client workflows. Active conversations
and their existing services retain their old code; the selected installation is
for new sessions. This is local termination acceptance, not a claim of a fresh
professional workflow, native Windows acceptance or Marketplace publication.


The release CI later detected a stale localization catalogue bound to 0.1.475.
The final Vera patch is 0.1.477, avoiding replacement of code in the already
running 0.1.476 cache. Its recorded catalogue is rebound to the canonical
manifest; exact equality checks preserve all 55 skill entrypoints and every
existing jurisdiction assessment row. No jurisdiction adaptation is inferred
from this local runtime repair. Executable lifecycle bytes are unchanged from
the tested 0.1.476 candidate. Final archive/install hashes and CI outcomes are
recorded by the release validation evidence.

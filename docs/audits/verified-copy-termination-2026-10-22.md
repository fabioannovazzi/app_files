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

The local runtime/ownership/reporting/index suite passed 111 tests. Real
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
references before each removal. Current-day or otherwise uncertain copies are
retained. Running services and workers are never signalled for this recovery.
Exact deletions and reclaimed allocation are recorded locally by the recovery
operation. Package/source checks do not establish a fresh professional
host-conversation acceptance run or replace an already running service.

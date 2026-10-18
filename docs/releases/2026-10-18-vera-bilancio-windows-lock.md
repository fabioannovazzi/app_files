# Bilancio case and job locks on Windows

The Windows worker reported `ModuleNotFoundError` at `case_service.py:12`,
imported by `service_bridge.py:14`. That source location imports the POSIX-only
`fcntl` module before any case operation can start. A controlled regression
reproduces this exact import failure without inspecting customer files.

The service now chooses the native locking module for the actual host:
`flock` on POSIX and a stable one-byte `msvcrt` lock on Windows. Both case
mutations and job execution retain exclusive cross-process locking. Windows
contention is retried; other errors propagate, and the lock is released when
the protected operation raises. This mechanical synchronization is deterministic
to preserve mutual exclusion and prevent concurrent case/job writes.

The change reads no new customer data and adds no network destination, model
context, reporting field or permission. The existing lock file receives one
sentinel byte on Windows. Windows case mutex files stay in the tenant's
`.case-locks` directory, outside the case folder, so the retention-controlled
quarantine rename does not fail on an open CRT handle. These mutex files are
never unlinked, keeping waiting writers on the same lock across deletion.
POSIX retains its existing lock location. Tenant authorization, symlink checks, idempotency,
professional decisions and original-task verification remain in force.

Source tests, CI and downloadable packages do not establish recovery of the
reported task. Its exact report, owner, operation and applicable remedy still
require a successful host retry and original-task verification. No Marketplace
publication is part of this fix.

# T06 archive fault-boundary acceptance map

Inspected retained `archive-current.xml`: 71 passes, no failures/errors/skips,
including 52 file-boundary cases. This is an index of prior actual temporary
filesystem tests, not a new execution or a live cloud/Windows claim.

| Phase | Before and after each occurrence | Case count |
| --- | --- | --- |
| Apply | writes 1–2, flushes 1–2, file fsyncs 1–2, unlinks 1–2, journal writes 1–6 | 28 |
| Rollback | writes 1–2, flushes 1–2, file fsyncs 1–2, unlinks 1–2, journal writes 1–4 | 24 |

Current test source lines 706 onward identify exact parameterization and hooks.
The interruption is an injected KeyboardInterrupt before/after a real operation.
A before-write empty destination is retained for manual review: recovery must
refuse an incomplete copy without changing any bytes, and every original content
remains present. An interruption before the first apply journal leaves the
original paths unchanged and permits a new approved apply. Other covered
boundaries recover original paths/bytes through rollback, and repeated rollback
is idempotent.

Separate retained tests cover competing public apply/rollback calls, refusing to
overwrite a destination changed after apply while preserving its journal, and
interruption after a complete physical move with hash-based recovery. Explicit
approval records are synthetic test fixtures. Google Drive uses a fake gateway;
thread contention and injected exceptions are not hard-power-loss, cross-process
lock or Windows execution evidence.

Exact 52 JUnit node names, XML hash and currently inspected test-source hash are
in `/private/tmp/vera-remediation-01a07083/archive-fault-matrix-index.json`.
The hash of today's test file is an inspection identity, not a claim that the
older JUnit recorded its source hash. The full frozen integration run supplies
separate current-baseline evidence when it completes.

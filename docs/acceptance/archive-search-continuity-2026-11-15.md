# Studio Archive search continuity

A fresh chat previously recovered the approved archive root but selected an empty
session-local SQLite index. Searching therefore required extracting the same
sources again. The root configuration also unconditionally reported that a refresh
was required, even when a compatible index was available.

The fix stores the derived index under the product's private profile and canonical
archive-root key. Session configuration, selected work and credentials remain
separate. On first use it atomically backs up one compatible legacy index from the
same product's default sessions, preserving its timestamp and source IDs. Explicit
state directories without a profile retain their isolated behavior. Concurrent
refresh writers use an OS lock; source opening still verifies the live file hash.
No source files are changed and no new external recipient is introduced.

Validation:

- 8 subprocess regressions: new-chat reuse, legacy migration for Vera and Lucia,
  concurrent migration, archive-root isolation, changed-source rejection and
  concurrent refresh.
- 181 existing archive/component/concurrency/product-default tests passed.
- New cache module coverage: 86% (subprocess coverage).
- Enabled local Vera distribution updated through the supported installer to 0.1.644.
- Real fresh-chat acceptance: pending final transcript verification.

Release checks also exposed stale generated course/package artifacts. These are
reported independently from archive retrieval acceptance; no failed check is
represented as a pass.

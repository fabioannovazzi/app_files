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
- Real fresh-chat acceptance passed in chat `01a1de66-5cf8-78b2-b9a1-19038b7e3e53`:
  all three original Eutekne questions returned the pertinent PDF first and opened
  with `source_verified=true`. Before and after: 20 documents, 88 chunks,
  `last_refresh_at=2026-11-15T08:31:10+00:00`, `index_requires_refresh=false`.
  No refresh/rebuild/configuration/extraction call occurred. Donation retrieval
  ranked the rates page first; adjacent opened pages supplied the direct context.
  The CLI could not query the remote catalogue or create PATH aliases, but local
  enabled-version inspection and Archive MCP operations succeeded.

Release checks also exposed stale generated course/package artifacts. These are
reported independently from archive retrieval acceptance; no failed check is
represented as a pass.

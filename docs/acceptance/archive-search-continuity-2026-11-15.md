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
- Enabled local Vera distribution updated through the supported installer to 0.1.645.
- Real fresh-chat acceptance passed in final chat `01a1de76-0ec1-7c42-8162-49512616d2f2`:
  all three original Eutekne questions returned the pertinent PDF first and opened
  with `source_verified=true`. Before and after: 20 documents, 88 chunks,
  `last_refresh_at=2026-11-15T08:31:10+00:00`, `index_requires_refresh=false`.
  No refresh/rebuild/configuration/extraction call occurred. Donation retrieval
  ranked the rates page first; adjacent opened pages supplied the direct context.
  The CLI could not query the remote catalogue or create PATH aliases, but local
  enabled-version inspection and Archive MCP operations succeeded.

Release checks initially exposed stale generated course/package artifacts and
missing local upload ZIPs. The maintained generators rebuilt these. The complete
product release builder then passed Codex, Cowork and Antigravity version alignment
for Vera, Clara and Lucia, including packaged MCP startup checks. Focused ZIP/source
parity and notification tests passed (19 passed, two environment-dependent skips),
and four upload-instruction/helper preservation tests passed. The initial broad
package run was interrupted after stale/missing-artifact failures; it is not claimed
as a full-suite pass. Search implementation and instructions in the enabled Vera
installation match the source fix byte-for-byte. No Marketplace publication occurred.

The expanded recovery run initially found four failures: a newly selected private
profile inherited broad parent-directory creation permissions. Version 0.1.645
creates each private profile level explicitly with owner-only permissions. The
corrected run passed 477 tests (three optional skips), including those four cases
and the eight cross-process search regressions. The final fresh-chat acceptance
above exercised the installed 0.1.645 independently of the earlier 0.1.644 test.
Final package parity, upload-preservation and notification checks: 23 passed, two
environment-dependent skips. The complete release build passed again for 0.1.645.

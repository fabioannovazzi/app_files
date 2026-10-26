# Course-file deduplication

The publication compiler stores byte-identical attachments, rendered document
images and passive supporting files once under
`static/shared/courses/<product>/_files/<sha256>/<filename>`. SHA-256 comparison
is appropriate here because identity is mechanically verifiable; no document
meaning or professional judgment is inferred. Authored attachment bytes and
the pins in the course manifests are unchanged.

`file-aliases.json` preserves published language paths and previous hash paths.
The application mounts `CourseFiles` before the general static handler and
rewrites exact aliases internally. Identical files shared by products or named
differently also use this mapping. Packages retain their product-scoped base URL
and use `_files/<sha256>/<filename>` paths, so the existing client download and
hash-verification code is unchanged. GET, HEAD, conditional responses and range
requests retain the standard static-file behavior. Rebuilds retain historical
hash files and reject altered historical bytes before publication.

Generated HTML views link to stored inputs on the same site. Original HTML
attachments remain unchanged. The current original HTML attachments have no
relative resource links requiring a separate resource bundle. Future attachment
layouts must continue to pass the complete public-link tests.

The 230 MiB compressed Git-archive guard already ran in the product-artifact CI
workflow. `build_product_release.py --check` now runs the same guard against
`HEAD`, with the Claude directory's 256 MiB limit in its diagnostic. Public
catalogue rendering remains an explicit compiler step, independently checked by
the teaching workflow; building ZIPs does not require document-rendering tools.

## Source and privacy review

The only hosted application change adds the public course-file mount. The new
handler loads a repository-generated URL mapping and delegates file responses to
Starlette. It makes no outbound request, accepts no upload and calls no model.
Existing authentication and non-course endpoints retain their implementation.
The build helpers consume repository-owned fictional course material only.
Client download boundaries, recipients, input bytes and hash pins are unchanged.
Normal public HTTP request metadata remains subject to existing hosted logging.

The agent inspected this change and refreshed affected privacy source bindings;
hash refreshes themselves do not constitute human approval. Course-publication
and serving source files are now included in the Vera local-onboarding and
Clara/Lucia prepared-course-file records. Other affected records cover the shared
application entry point or product version metadata; their transmitted payloads
and controls have not changed. No user-host installation, professional workflow,
model-data report delivery or Marketplace publication is established by this
source review.

## Verification

- Before deduplication, the initial checkout archive measured 207,324,417 bytes.
  Implementation was subsequently based on main commit `a37a4f9c6` (PR #910).
- The staged implementation tree measured 124,884,684 compressed bytes
  (119.10 MiB), below the requested 120 MiB target. The committed `HEAD` is
  measured separately before merge.
- Product builds completed for Vera 0.1.493, Lucia 0.1.177 and Clara 0.1.349,
  including Codex, ChatGPT upload, Cowork and Antigravity archives.
- The public tree changed from 4,761 to 2,860 files, retaining all 258 localized
  workflow lessons and the five Vera introductions.
- All 1,072 remote-file pins from the previously released Cowork package trees
  on that main commit resolve with unchanged hashes: Vera 778, Lucia 141,
  Clara 153.
- Regressions cover cross-product and cross-filename sharing, retained old
  inputs after source changes, reproducible rebuilds, corrupted historical
  files, GET/HEAD/range behavior, missing URLs, alias targets, duplicate files
  at or above 4 KiB, and the release command's archive guard.
- The focused publication/release suite passed 28 tests with 90.74% coverage
  on the new code. The archive-guard/prerequisite suite passed 15 tests with
  96.43% guard coverage. Full public-link verification passed, as did the
  public compiler's reproducibility check.
- The first build stopped on stale privacy fingerprints after the hosted-route
  change. Selected records were refreshed after inspecting the source delta.
  A later formatting change and the historical-file integrity check required
  refreshing their corresponding bindings again. These were build-preparation
  failures, not lesson-execution failures.

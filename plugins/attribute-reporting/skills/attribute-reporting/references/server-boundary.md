# Attribute Reporting Server Boundary

## Implemented Clara-installed boundary

The installed Clara component uses a narrow first-party HTTP bridge under `/case-notes/api/attribute-reporting`. Every route uses the existing Mparanza session and requires Clara site permission. Persist that session between client commands only with the client's `--session-file` cookie jar in a private local auth directory outside the run directory, Git workspaces, and plugin caches; the client writes the jar as a private `0600` file. Artifacts are owner-scoped; another authenticated user receives no information about whether an artifact exists. The plugin never receives database credentials and the bridge never depends on a model-provider API key.

The bridge currently provides:

1. `GET /taxonomies/{category_key}` returns the one published central category taxonomy, active leaves, version, and canonical checksum.
2. `POST /evidence-packs` creates an immutable background job from the current server database for a retailer/category and pinned taxonomy. Polling a `pending` or abandoned `running` job safely reschedules it after a worker restart; a cross-worker file lock makes each build attempt single-writer and a ready job is idempotent. The worker rechecks the central taxonomy immediately before and again after package construction, so a queued job fails rather than becoming ready if its taxonomy pin changes. Poll and download routes expose job status and a checksum-verified ZIP only to the requesting user.
3. `POST /mapping-worksets` normally creates a complete unresolved product/parent workset from a ready evidence job. `mapping_mode: correction` is accepted only with an explicit, non-empty audit reason. The server regenerates the complete include-resolved candidate scope and selects every resolved cell that is both effective as `codex` in the evidence matrix and present in the pinned accepted Codex mapping state. Unresolved and higher-authority retailer-filter or deterministic cells are excluded; callers must not infer correction intent or represent the remaining complete correction-eligible scope as a targeted patch. The server retains the private source-bound tasks. The public copy replaces its absolute source package with an opaque evidence-job locator and carries no local images. A complete unresolved workset with zero tasks is returned with `status: no_work`; the client must skip submission and the rebuilt job rather than manufacture an empty mapping operation.
4. `POST /mapping-worksets/{id}/submissions` accepts the public task artifact enriched only with package-relative local-image hashes, complete Codex decisions, validated mappings, and an independent mapping review. The server verifies ownership, workset hash, source rows, taxonomy freshness, complete task coverage, local-image field shape, decision validation, reviewer independence, review coverage, and the combined idempotency key before one transactional database write of values and audit lineage. Before that transaction it durably writes the validated repair inputs to the private bridge root. The transaction itself records compact operation evidence and the committed timestamp in the database marker, so a retry after a filesystem interruption reconstructs the same receipt rather than inventing a later state.
5. A second evidence job can name the accepted mapping operation id. Before building, the server revalidates that submission against the current taxonomy and exact retailer/category scope. Poll, checksum-download, and safely extract this distinct job. The rebuilt URL-only package contains the four mapping artifacts plus the server submission, mapping-review-validation, and sanitization receipts. Report preparation recomputes their hashes and operation binding before recording `server_accepted`. Hydrate this rebuilt package locally again because the preliminary image manifest is bound to another package directory and source-row hashes.

The server package builder deliberately removes image files, server filesystem paths, database paths, and private local-image fields. It preserves structured evidence and public image URLs, checks package integrity, writes a sanitization receipt, and emits a deterministically ordered ZIP. The local client verifies the download checksum and safely extracts only ordinary bounded files; it rejects traversal, absolute or duplicate paths, links, unsafe file types, oversized members, suspicious compression ratios, and an existing symlink in any component of either the ZIP path or extraction destination. Keep the downloaded ZIP plus both generated receipts until correctness is complete. Production `prepare_run.py` receives both receipt paths, verifies the unchanged archive and the full extracted-file ledger against the package, allows only manifest-pinned local image hydration additions, and copies the receipts into the private report output for later correctness revalidation.

For `status: no_work`, the preliminary ZIP is also the report's structured evidence package. `prepare_run.py` receives its preliminary download and extraction receipts together with `--no-work-workset`, verifies that the envelope and task scope name the same evidence job and retailer/category, and pins the zero-task coverage locally. Mapping authoring, review, submission, and rebuild are `not_applicable`; the final correctness record visibly distinguishes trusted pre-existing central-package values from mappings reviewed in this run.

## Retention and resource bounds

The bridge opportunistically prunes expired artifacts before creating server work: evidence jobs expire after 30 days, worksets after 7 days, and submissions after 180 days. A live workset keeps its source evidence job; a live pending submission keeps both its workset and source evidence so crash recovery remains possible. A single actor may retain at most 25 evidence jobs, 25 worksets, and 100 submissions; a full quota blocks new work until retention cleanup removes eligible artifacts. Aggregate retained data is also capped at 8 GiB per actor and 64 GiB for the bridge root. At most one evidence build per actor and two builds globally may run concurrently.

An evidence-package tree is limited to 20,000 ordinary files and 512 MiB. A mapping workset or submission is limited to 10,000 tasks. Each submitted mapping JSON artifact is limited to 32 MiB and the four-artifact submission to 64 MiB total; JSON is also bounded to 16 levels, 500,000 values, and 16,000 characters per string. Ordinary POST bodies are limited to 64 KiB before JSON parsing; only the mapping-submission route receives the 65 MiB transport envelope. The production reverse proxy must enforce authentication-aware rate/concurrency limits and allow that 65 MiB route while retaining the smaller limits elsewhere. These are hard rejection limits, not targets for agent context size.

The bridge root and its POSIX file locks are a deployment invariant. Every worker serving these routes must see the same filesystem; on the current single-host deployment that means one private, backed-up and disk-monitored root. Do not load-balance the routes across hosts with independent local disks. A future multi-host deployment requires shared artifact storage plus distributed locking/quota coordination before these routes may be enabled.

## Current-view consistency

`snapshot_mode: current_database` means the builder reads the current central database; it is not a single repeatable-read transaction across every discovery, product, price, filter, and attribute table. The bridge does mechanically pin the taxonomy and the complete accepted Codex mapping state before and after construction, and it fails if either changes. For a point-in-time operational run, scrape ingestion, price refresh, and filter materialization must be quiescent while the evidence job builds. The present rollout intentionally uses the user's accepted assumption that the current stored product data is sufficiently up to date; it must not be described as a transactional historical snapshot.

Local image hydration treats URLs as untrusted. For every initial request and redirect it rejects non-public targets, resolves and vets the numeric addresses, connects directly to one vetted address, and preserves the original hostname for the HTTP `Host` value and TLS SNI/certificate verification. This prevents a second unvetted DNS resolution between validation and connection.

## Files and artifacts kept local

The installed workflow keeps all of the following on the user's machine:

- authentication input files;
- downloaded ZIPs and extraction receipts;
- image bytes hydrated from package URLs;
- `local_image_manifest.json` and package-relative image bindings;
- report model, claim ledger, semantic review, browser-QA screenshots, correctness artifacts, and final HTML report;
- the resumable run ledger and stage receipts.

Only the enriched mapping task JSON, decisions, normalized validation, and independent mapping review cross back to the authenticated bridge. Local image paths are relative `images/...` locators with hashes; image bytes and absolute workspace paths are never uploaded. Reports are never uploaded.

Local file storage is not local model processing. Report inputs, mapping tasks,
claims, and review evidence that Codex reads may enter model context through the
user's existing ChatGPT plan. The helper scripts make no separate model API call.

## Development-only fresh scrape path

The `app_files` development runtime can additionally:

- scrape retailer listing/filter surfaces through attached local Chrome;
- fetch and parse PDPs locally;
- persist listing and PDP rows to the server-backed store;
- download product images into a supplied local workspace;
- compute deterministic-only attributes; and
- build the established retailer/category evidence package.

`project_pipeline.py` constrains those stages and blocks the legacy model-backed mapping modes. It uses the repository runtime, existing retailer profiles, local browser state, and the configured database connection/tunnel.

## Remaining transport gap

Fresh scrape ingestion is not implemented for an installed Clara plugin. There is no installed endpoint that accepts a newly captured local listing/PDP bundle. Therefore:

- do not describe a current-database evidence job as a fresh scrape;
- do not give the plugin Postgres credentials;
- do not upload local scrape or image bundles through another route;
- do not silently fall back from a requested fresh scrape to the current snapshot.

When a user explicitly needs fresh data, run the development adapter when that environment is available. Otherwise mark fresh ingestion as blocked while offering the honest current-database snapshot as a separate option. Once an integrity-checked package exists, both modes use the same local image hydration, Codex mapping, independent mapping review, provenance, report review, browser QA, and correctness contracts.

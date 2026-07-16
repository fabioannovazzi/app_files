---
name: attribute-reporting
description: Use when a user wants Codex to run or continue the local retail scrape and central attribute-mapping pipeline, compare retailer-defined new products or best sellers with the remaining assortment, author a private local HTML report, or answer whether that report is correct. This workflow uses Codex agents for semantic mapping, narrative, and independent review; helper scripts never call a model API.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. Put each user run in a private local output directory outside every Git repository. Product images remain on the local machine. Reports, claim ledgers, report semantic reviews, browser QA, and correctness verdicts remain local and are never uploaded to the server. The four explicitly approved mapping artifacts, including the independent mapping review, may cross the authenticated mapping boundary described below.

# Attribute Reporting

Use this workflow to preserve the existing scrape → map → compare → report logic while moving model judgment into Codex. The central server remains authoritative for structured scraped records, the single published taxonomy for each category, accepted mappings, and image URLs. Clara's installed workflow can now authenticate to Mparanza, build an immutable package from the current database, retrieve a public mapping workset, submit independently reviewed mappings, and rebuild the package with provenance. Image bytes and report artifacts remain local. Fresh local scrape ingestion is still available only in the `app_files` development runtime; do not imply that an installed plugin can upload a fresh scrape.

The existing analytical cohorts remain authoritative:

- `recent` means the retailer-defined newest or new-arrivals cohort already encoded by the pipeline;
- `rest` means every other discovered product in that retailer/category snapshot;
- `top_seller` means the existing retailer-ranked top-seller cohort;
- comparisons use normalized cohort shares, recurring attribute pairs/triples, brand breadth, and the package's current best-seller-versus-other, new-versus-rest, sale-pressure, and rank logic.

Do not replace those definitions with a model-invented definition of newness. Do not rewrite the package arithmetic in prose or in new ad hoc scripts.

Read `references/workflow-reference.md` when authoring claims, constructing a mapping workset, filling `report_model.json`, or reviewing correctness. Read `references/server-boundary.md` before any installed Clara current-database run or any request for a fresh scrape.

## Judgment Boundary

Deterministic code owns:

- authenticated current-database snapshot jobs, ownership checks, checksummed downloads, and safe extraction;
- invoking the existing local scrape and server-persistence stages only in the development runtime;
- exact cohort membership and comparison arithmetic;
- package integrity and source hashes;
- taxonomy-version and allowed-value validation;
- claim-token resolution from exact CSV/JSON rows;
- the four existing attribute-table templates;
- local URL-image hydration and hash binding, HTML rendering, artifact hashes, browser QA, resumable stage receipts, and final verdict combination.

Codex agents own:

- ambiguous product-to-taxonomy mapping from product text and local images;
- an independent semantic review of every new mapping by an agent other than the mapping author;
- choosing which already-computed signals matter to the report;
- the report structure and narrative within the fixed section roles;
- semantic calibration, brand-effect interpretation, product-example relevance, and caveat wording;
- an independent review of every report claim and the final HTML's readability.

Use lower-cost Codex agents for bounded mapping tasks and first-pass claim review. Escalate only ambiguous or materially consequential cases to a stronger Codex agent. Plugin scripts must not call OpenAI or another model API, and the user does not need an API key.

## Codex-Native Run UX

Before helper scripts or write-heavy work, identify material choices that would change execution: retailer, category, whether the user wants a fresh scrape or the current database snapshot, local workspace, report audience, and any explicit report emphasis. Ask only those unresolved choices in chat. Generate choices from the actual inputs; do not offer named frameworks, new cohort definitions, report formats, or taxonomies unless the facts cue them or the user must supply a missing custom value.

Default output policy: a normal completed run produces the richest natural local package—resumable run and stage receipts, `run_intake.json`, evidence catalog, four deterministic attribute tables, Codex-authored report model, claim ledger, HTML draft, independent semantic review, desktop/mobile browser QA, final `report.html`, direct correctness verdict, `codex_run_review.md`, and `final_artifacts.json`. These are not choices to propose. HTML is the production report format. Do not generate PDF, OCR recovery, PPTX, NotebookLM, ChatGPT Pro, or legacy slide-validator artifacts for this workflow.

Use these visible artifacts in chat:

1. Start with a checklist covering dependency check, intake, authenticated data snapshot, local image hydration, Codex mapping, independent mapping review, authenticated submission, rebuilt evidence package, report authoring, render, independent report review, browser QA, correctness verdict, and delivery.
2. Show a Run Intake table with retailer, category, data snapshot choice, local workspace, output directory, taxonomy posture, image posture, and report audience.
3. Show a compact Decision Table only for unresolved mappings, stale taxonomy, missing source data, unsupported server access, or report-angle choices. Resolve inferable items yourself.
4. Before a long or write-heavy step, show an execution checkpoint with the intended command, inputs, output folder, and expected artifacts. Explicit approval or continuation is only needed when the step is external, destructive, approval-sensitive, or still depends on a material unresolved decision.
5. Update checklist statuses as stages complete. Do not use staged continuation ceremony.
6. End with an Artifact Card listing local paths, purpose, direct correctness verdict, review status, unresolved items, and next action. `codex_run_review.md` is the durable local card. Never edit plugin source or generated ZIPs during a user run.

## Dependency Check

From the plugin directory, run:

```bash
python scripts/check_dependencies.py
```

The checker reads `requirements.txt` and only reports missing packages. It never installs packages at runtime. If a requirement is missing, use the declared requirements file only when the environment allows installation; otherwise explain the missing capability.

## Resumable Run Ledger

Create the run outside every Git repository before fetching data. `run_state.py` fixes the stage order, writes a hash-bound receipt for each stage, and invalidates downstream receipts if an earlier artifact changes. Use `status` before continuing an interrupted run. Record `partial`, `blocked`, or `failed` honestly; never turn missing evidence into a completed receipt.

```bash
python scripts/run_state.py init <private-run-dir> --retailer <retailer> --category <category> --author-agent-id <author-agent-id> --server-origin https://mparanza.com
python scripts/run_state.py status <private-run-dir>
python scripts/run_state.py record <private-run-dir> <stage> --status complete --artifact <run-relative-artifact>
```

The fixed stages are intake, server snapshot, image hydration, mapping tasks, mapping decisions, mapping review, mapping apply, rebuilt package, report preparation, report authoring, report render, semantic review, browser QA, and correctness. Receipts and their artifacts must remain inside the private run directory. Authentication material is never a run artifact.

## Run Modes

### Clara-installed current-database workflow

This is the default production path when current database data is acceptable.

1. Authenticate with a current Mparanza session using `server_bridge_client.py`. Keep the private magic-link input, cookie-header input, and persistent `--session-file` cookie jar in a separate `0700` local auth directory outside the run directory, every Git repository, and every plugin cache. Bootstrap the jar once with `--magic-link-file`; subsequent bridge invocations use only the same `--session-file`. A cookie header is an alternative that must be supplied on each authenticated invocation and is attached only to the exact approved Mparanza origin. Never copy authentication material into logs, receipts, mapping artifacts, or report artifacts.
2. Download the published central taxonomy snapshot for the category. Its version and checksum pin every package and workset operation.
3. Create and poll a preliminary evidence job from the current database. The queued builder rechecks the pinned central taxonomy immediately before and again after package construction; a change fails the job and requires a fresh snapshot and job. Download its checksum-verified ZIP, then use `extract-evidence`; do not use a generic unzip command. The safe extractor rejects traversal, links, duplicate paths, oversized members, suspicious compression, and any existing symlink component in the ZIP or destination path. The portable package contains structured data and image URLs, not server paths or image bytes.
4. Run `hydrate_images.py` on the extracted package. It downloads supported public raster URLs into `images/local`, verifies byte limits and hashes, writes `local_image_manifest.json`, and never uploads image bytes or changes analytical CSVs. Its SSRF guard resolves and vets public numeric addresses, connects to a vetted address while retaining the original hostname for HTTP and TLS verification, and repeats that process for every redirect. A partial manifest is a visible partial image-evidence state.
5. Create the public mapping workset from the preliminary evidence job. The default `unresolved` mode covers only unresolved eligible cells. Use `correction` mode only after the user explicitly asks to correct accepted mappings and supplies a non-empty audit reason. The server regenerates the complete include-resolved candidate scope, then admits every resolved cell whose value is both effective in `product_filter_matrix.csv` and backed by the pinned accepted `codex` mapping identity. It excludes unresolved cells (which remain the normal mode) and values whose effective source is higher-authority retailer-filter or deterministic evidence. This is the complete correction-eligible scope, not a selected-cell patch. Preserve the entire workset envelope as `workset.json`, and write its exact nested `mapping_tasks` object beside it as `mapping_tasks.public.json`. The public task artifact has an opaque evidence-job locator and empty `product.local_images`; it exposes no server filesystem path.
   - If the unresolved workset has `status: no_work`, an empty `tasks` list, and coverage with `task_count: 0`, `task_count_before_limit: 0`, `unresolved_attribute_cells: 0`, `include_resolved: false`, and `truncated: false`, take the explicit no-work branch. Do not author decisions, create or run a mapping review, submit an empty operation, or request a rebuilt package. The already hydrated preliminary current-database package becomes the report package. Record mapping decisions, mapping review, mapping apply, and rebuilt-package ledger stages as `skipped`; their semantic status is `not_applicable`, not `approved`.
6. Run `bind_mapping_images.py` to create `mapping_tasks.json`. This may change only `product.local_images`, using package-relative `images/...` paths and verified SHA-256 values. Never place an absolute local path in a mapping artifact.
7. Have bounded lower-cost Codex mapping agents author decisions for every task. Apply the status semantics in the workflow reference: `no_value` means no coherent value was observed for that attribute, while a positively observed value absent from the active taxonomy is an `oov_candidate`; do not use `no_value` merely because no active leaf matched, and do not move evidence from another attribute into an OOV. Check parallel products for the same boundary before review. For a small workset, one agent may author `mapping_decisions.json` directly. For a workset too large for one bounded context, use `mapping_shards.py shard-tasks`, delegate each exact slice, then use `merge-decisions`; the mechanical merge rejects missing, duplicate, stale, or out-of-slice work and preserves contributor provenance. Validate the complete merged artifact. Inspect `coverage`; skipped variant-scoped cells are a disclosed boundary, not complete coverage.
8. Prepare `mapping_review.json`. A different Codex agent reviews every task against its pinned text, taxonomy values, source-row hash, decision, normalized mapping, and local-image hashes. For a large review, use `mapping_shards.py shard-review` and `merge-review`; every task reviewer must differ from that task's mapping contributor and the mapping coordinator, while the review coordinator must differ from every mapping author and every review-shard contributor. The merge and final validator enforce those per-task author pins. Validate the complete merged review. Only `approved` or `approved_with_caveats` proceeds.
9. At an explicit server-write checkpoint, submit the complete enriched tasks, decisions, validated mappings, and independent review through the authenticated bridge. The server removes the permitted local-image enrichment to compare the original public workset, re-verifies its private source workset and current taxonomy, recomputes validation and review checksums, and applies value/audit pairs transactionally under the combined idempotency key. Do not use direct database credentials.
10. Create a second evidence job using the returned mapping submission operation id. This rebuilds comparisons from accepted mappings and places the four mapping artifacts, server submission receipt, and mapping-review validation in the portable package. Poll this distinct job until it is `ready`, then checksum-download and safely extract it into a new rebuilt-package directory.
11. Run `hydrate_images.py` again on the extracted rebuilt package before report preparation. The preliminary manifest is bound to its own package directory and source-row hashes and cannot be reused for the rebuilt package. Preserve a partial rebuilt manifest honestly.
12. Run `prepare_run.py` on the hydrated rebuilt package with `--download-receipt`, `--extraction-receipt`, and `--require-browser-qa`. It validates that both receipts identify the same still-present archive, verifies its hash and size, checks every extracted file against the current package, and permits only manifest-pinned `local_image_manifest.json` and `images/local/**` hydration additions. It then copies and hash-pins both receipts in the report output. It also automatically detects, validates, and copies the four mapping artifacts plus the server submission, mapping-review-validation, and sanitization receipts. Server provenance cannot proceed without the matching transport receipts. The run intake records `server_accepted` only when the operation id, actor, database write, taxonomy, scope, review hashes, portable-package provenance hashes, and local transport lineage agree. Those hashes establish internal integrity after an authenticated download; they are not server signatures and cannot prove authenticity against a maliciously fabricated local package. Four locally reviewed artifacts without those receipts remain usable only as `local_review_only` and force a visible correctness caveat. Pass `--mapping-provenance-dir` only when the complete provenance set lives in another local directory; incomplete, stale, rejected, or unable provenance blocks preparation. In the explicit no-work branch, instead run preparation on the hydrated preliminary package with its preliminary download and extraction receipts plus `--no-work-workset <run>/mapping/workset.json`; preparation verifies the zero-task envelope against the same evidence job and records mapping review as `not_applicable`.
13. Author `report_model.json`, render the draft, and delegate `semantic_review.json` to a different Codex agent. The report reviewer must cover every claim, all six required dimensions, and every selected local image against the exact render-manifest hashes.
14. Run `browser_qa.py` after render and semantic review. It inspects the exact draft at desktop and mobile sizes for overflow, broken local images, unsafe/external assets, table containment, links, and browser errors. A required missing, blocked, failed, or stale `browser_qa.json` prevents a clean verdict.
15. Run `check_report.py`. Deliver `report.html`, its direct correctness verdict, `codex_run_review.md`, `final_artifacts.json`, and the completed run ledger locally. Never upload the report.

Representative commands follow. Global authentication flags precede the bridge subcommand. Create `<private-auth-dir>` outside `<run>`, every Git repository, and every plugin cache with directory mode `0700`. The first authenticated command below consumes a private magic link and writes a `0600` session jar; reuse that jar without the magic-link flag for all later commands. If a current jar already exists, omit `--magic-link-file` from the first command too.

```bash
python scripts/server_bridge_client.py --magic-link-file <private-auth-dir>/magic-link.txt --session-file <private-auth-dir>/mparanza-session.cookies taxonomy <category> --output <run>/server/taxonomy.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies create-evidence --retailer <retailer> --category <category> --taxonomy <run>/server/taxonomy.json --output <run>/server/preliminary-job.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies poll-evidence <preliminary-job-id> --output <run>/server/preliminary-status.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies download-evidence <preliminary-job-id> --output <run>/server/preliminary.zip --receipt <run>/server/preliminary-download.json
python scripts/server_bridge_client.py extract-evidence --archive <run>/server/preliminary.zip --output <run>/preliminary-package --receipt <run>/server/preliminary-extraction.json
python scripts/hydrate_images.py <run>/preliminary-package
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies create-workset --evidence-job-id <preliminary-job-id> --taxonomy <run>/server/taxonomy.json --output <run>/mapping/workset.json --tasks-output <run>/mapping/mapping_tasks.public.json
# Explicit correction only: append --mapping-mode correction --correction-reason "<user-supplied audit reason>".
# If workset.status is no_work and its complete unresolved coverage is zero, stop the mapping branch here:
# python scripts/prepare_run.py <run>/preliminary-package --output-dir <run>/report --author-agent-id <codex-agent-id> --download-receipt <run>/server/preliminary-download.json --extraction-receipt <run>/server/preliminary-extraction.json --no-work-workset <run>/mapping/workset.json --require-browser-qa
# Do not run bind, decision, review, submit, rebuilt-job, or rebuilt-package commands in that branch.
python scripts/bind_mapping_images.py <run>/mapping/mapping_tasks.public.json --image-manifest <run>/preliminary-package/local_image_manifest.json --output <run>/mapping/mapping_tasks.json
# For a large workset, shard before delegation, then merge every completed decision shard.
python scripts/mapping_shards.py shard-tasks <run>/mapping/mapping_tasks.json --output-dir <run>/mapping/task-shards --max-tasks-per-shard 40
python scripts/mapping_shards.py merge-decisions <run>/mapping/mapping_tasks.json <run>/mapping/task-shards/mapping_task_shards.json <decision-shard>... --coordinator-agent-id <mapping-coordinator-id> --output <run>/mapping/mapping_decisions.json
python scripts/validate_mapping_decisions.py <run>/mapping/mapping_tasks.json <run>/mapping/mapping_decisions.json --output <run>/mapping/validated_mappings.json
python scripts/prepare_mapping_review.py <run>/mapping/mapping_tasks.json <run>/mapping/mapping_decisions.json <run>/mapping/validated_mappings.json --reviewer-agent-id <different-codex-agent-id> --output <run>/mapping/mapping_review.json
# For a large review, shard the untouched template, delegate every slice, then merge all reviewed slices.
python scripts/mapping_shards.py shard-review <run>/mapping/mapping_review.json --output-dir <run>/mapping/review-shards --max-reviews-per-shard 40
python scripts/mapping_shards.py merge-review <run>/mapping/mapping_review.json <run>/mapping/review-shards/mapping_review_shards.json <review-shard>... --coordinator-agent-id <independent-review-coordinator-id> --summary <coordinator-summary> --output <run>/mapping/mapping_review.json
python scripts/validate_mapping_review.py <run>/mapping/mapping_tasks.json <run>/mapping/mapping_decisions.json <run>/mapping/validated_mappings.json <run>/mapping/mapping_review.json --output <run>/mapping/mapping_review_validation.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies submit --workset <run>/mapping/workset.json --mapping-tasks <run>/mapping/mapping_tasks.json --decisions <run>/mapping/mapping_decisions.json --validated <run>/mapping/validated_mappings.json --mapping-review <run>/mapping/mapping_review.json --mapping-review-validation <run>/mapping/mapping_review_validation.json --output <run>/server/mapping-submission.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies create-evidence --retailer <retailer> --category <category> --taxonomy <run>/server/taxonomy.json --mapping-submission-id <operation-id> --output <run>/server/rebuilt-job.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies poll-evidence <rebuilt-job-id> --output <run>/server/rebuilt-status.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies download-evidence <rebuilt-job-id> --output <run>/server/rebuilt.zip --receipt <run>/server/rebuilt-download.json
python scripts/server_bridge_client.py extract-evidence --archive <run>/server/rebuilt.zip --output <run>/rebuilt-package --receipt <run>/server/rebuilt-extraction.json
python scripts/hydrate_images.py <run>/rebuilt-package
python scripts/prepare_run.py <run>/rebuilt-package --output-dir <run>/report --author-agent-id <codex-agent-id> --download-receipt <run>/server/rebuilt-download.json --extraction-receipt <run>/server/rebuilt-extraction.json --require-browser-qa
python scripts/render_report.py <run>/report
python scripts/browser_qa.py <run>/report
python scripts/check_report.py <run>/report
```

The sharding commands are conditional: skip them for a genuinely bounded single-agent workset. When review sharding is used, replace `mapping_review.json` with the mechanically merged artifact before validation and submission. Repeat each poll command until its status artifact says `ready`; polling also reschedules a `pending` or abandoned `running` build after a server-worker restart. Do not download a pending, running, or failed job. Record every stage and receipt in `run_state.py` as it completes. Treat the rebuilt extraction receipt and rebuilt `local_image_manifest.json` as rebuilt-package evidence; authentication files remain outside the run ledger.

### Existing package to report

For development, testing, or a user-supplied integrity-checked package, skip the authenticated mapping stages only when no new mappings are being applied. Confirm `package_integrity.json` is `pass`; hydrate URL images locally if needed; run `prepare_run.py` with `--require-browser-qa`; author and render the report; delegate semantic review; run browser QA; then run correctness. If all four mapping provenance artifacts are absent, correctness records mapping review as `not_applicable`. If any one is present, all four must be present and valid.

### Fresh local scrape in development

Inside `app_files`, `project_pipeline.py` remains the adapter for browser-backed discovery, PDP capture, local image download, deterministic-only mapping, server persistence, and evidence-package building. Use it only when the user explicitly asks for fresh data. `discover` and `fetch-pdps` run locally and write structured records to the server-backed database; `deterministic-map` must invoke `export_pdp_attributes.py --deterministic-only`; `build-package` preserves the established cohorts and comparisons. Never use `--run-vlm` or the legacy vision/web model runners.

An installed Clara plugin cannot yet ingest a newly scraped local listing/PDP bundle. Do not route a fresh-scrape request through the current-database bridge, do not distribute direct Postgres credentials, and do not claim that the current snapshot is fresh. Run the development adapter when available or report the fresh-ingestion stage as blocked. After a development package exists, use the same local image, mapping-review, report-review, browser-QA, and correctness contracts described above.

## Correctness Verdict

The question “Is this report correct?” is mandatory and must be answered directly with exactly one of:

- `Correct`
- `Correct with caveats`
- `Incorrect`
- `Unable to determine`

The deterministic checker verifies source/package hashes, package integrity, table hashes, bound values, preserved signal thresholds, product/image references, warning disclosure, mapping-review integrity, required browser-QA hashes/findings, and HTML parity. It cannot decide whether a mapping or report interpretation is sensible. One independent Codex reviewer evaluates every new mapping; a different report reviewer evaluates meaning, coherence, importance calibration, caveat handling, brand/product interpretation, and HTML readability.

Mechanical failure makes the report `Incorrect`. Missing, stale, or invalid mapping review for a run that carries mapping provenance makes it `Unable to determine`; a rejected mapping makes it `Incorrect`. Missing or invalid independent report review makes it `Unable to determine`. Required browser QA that is missing, blocked, stale, or invalid makes it `Unable to determine`; a failed browser finding makes it `Incorrect`. An unsupported semantic claim makes it `Incorrect`. Supported mappings or claims with a semantic caveat, or an active disclosed package warning, make it `Correct with caveats`. Only a clean mechanical pass plus complete supporting mapping and report reviews, passing browser QA, and no active caveats makes it `Correct`. A report made from an already accepted package with no new mapping artifacts records mapping review as `not_applicable`.

An unresolved workset is incremental: its independent review covers the new unresolved tasks, not every pre-existing resolved cell in the central package. When `coverage.include_resolved` is false and `resolved_attribute_cells` is positive, correctness must visibly report that exact count as trusted central-package input that was not re-reviewed in this run; the verdict is at best `Correct with caveats`. A validated `no_work` run makes the same boundary visible, keeps mapping review `not_applicable`, and never turns zero tasks into an implicit approval of historical mappings.

A correction workset is also scoped: its `correction_selection` records unresolved cells and non-Codex-effective resolved cells excluded from the accepted-Codex remap. Final correctness validates those counts and visibly discloses every nonzero exclusion bucket; unresolved exclusions remain unmapped, while non-Codex-effective exclusions remain trusted package input that was not re-reviewed. A positive `excluded_not_pinned_count` is a package/database-state conflict, not a caveat, and blocks the correction path.

Do not replace this verdict with “ready,” a slide score, a PDF/OCR pass, or a general reassurance.

## Expected Outputs

- preliminary and rebuilt evidence packages for a current-database mapping run
- checksum download/extraction receipts, `local_image_manifest.json`, and local `images/`
- `mapping_tasks.json`, `mapping_decisions.json`, `validated_mappings.json`, `mapping_review.json`, `mapping_review_validation.json`, `mapping_submission_receipt.json`, `server_sanitization_receipt.json`, and a transactional submission/apply receipt when semantic mapping runs
- task/review shard manifests and contributor artifacts when bounded multi-agent sharding is needed
- `run_state.json`, `run_intake.json`, and hash-bound stage receipts
- `evidence_catalog.json`
- `evidence/attribute_tables/manifest.json`
- four deterministic attribute table CSV/HTML pairs
- `report_model.json`
- `claim_ledger.json`
- `report_draft.html`
- `render_manifest.json`
- `semantic_review.json`
- `browser_qa.json` and desktop/mobile screenshots
- `correctness_verdict.json`
- `report.html`
- `codex_run_review.md`
- `final_artifacts.json`
- selected local product images under `assets/products/`

## Failure Modes

- If package integrity is not `pass`, stop before authoring. Do not infer around a failed source package.
- If a download checksum or safe extraction fails, discard that local package and do not continue from a generic extraction.
- If local image hydration is partial, preserve the manifest status and do not claim that every mapped or featured product was visually reviewed.
- If the pinned source package or taxonomy changes after mapping tasks are issued, reject the write and rebuild the workset.
- If the mapping reviewer is the mapping author, misses a task, rejects a mapping, cannot determine it, or targets stale content, do not apply the mappings.
- If the mapping workset is truncated or excludes unresolved variant-scoped attributes, disclose that boundary and do not describe the whole category as completely mapped.
- If a claim selector matches zero or multiple rows, fix the selector; do not paste the value manually.
- If a report warning is not visibly disclosed, rendering or correctness checking must fail.
- If product evidence has no local image, render an explicit local-image-unavailable placeholder. Do not download an image during report rendering.
- If review evidence is absent, say it is unavailable. Do not treat absence as negative consumer evidence.
- If the independent reviewer is the report author, the verdict is `Unable to determine` until a different agent reviews it.
- If browser QA is missing, blocked, stale, or failed, do not issue a clean correctness verdict. Revise any faulty draft, then rerun semantic review and browser QA because the draft hash changed.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as the missing fresh-scrape ingestion adapter, stale taxonomy snapshot, brittle retailer capture, ambiguous mapping task, missing source field, weak image evidence, report-model friction, visual overflow, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.

# Attribute Reporting Workflow Reference

## Report model contract

`report_model.json` uses schema `attribute_reporting.report_model.v1`. It keeps authored meaning separate from exact values.

Required top-level fields:

- `report_id`: copied from `evidence_catalog.json`;
- `author`: a Codex agent identity with role `report_author`;
- `title`, `subtitle`, and `audience`;
- `acknowledged_warning_codes`: exactly the active warning codes in the evidence catalog;
- seven sections in this exact order: `executive_summary`, `winning_now`, `brand_context`, `emerging_signal`, `winner_emerging_bridge`, `product_evidence`, `method_and_caveats`;
- `claims`;
- up to eight `featured_products`;
- `limitations`, including every active package warning;
- `authoring_status: codex_complete`.

Each deterministic claim has:

```json
{
  "claim_id": "win-black-cardigan",
  "kind": "deterministic",
  "checker": "bundle_signal_winning_now",
  "headline": "Black cardigans are a visible winning bundle",
  "text_template": "The bundle appears in {{focus_share}} of top sellers versus {{baseline_share}} of the remaining assortment.",
  "evidence_refs": [
    {
      "ref_id": "focus_share",
      "source": "top_seller_pairs.csv",
      "selector": {
        "match": {
          "bundle_key": "color=black + garment type=cardigan"
        },
        "field": "pct_top_seller"
      },
      "format": "percent_1"
    },
    {
      "ref_id": "baseline_share",
      "source": "top_seller_pairs.csv",
      "selector": {
        "match": {
          "bundle_key": "color=black + garment type=cardigan"
        },
        "field": "pct_other"
      },
      "format": "percent_1"
    }
  ],
  "supporting_claim_ids": [],
  "interpretation": "The bundle repeats across brands rather than appearing as a single-product exception.",
  "caveat": "This describes the captured retailer rank surface, not market-wide sales.",
  "confidence": "high",
  "product_ids": []
}
```

The renderer requires evidence tokens and `ref_id` values to match exactly. It rejects numeric literals in authored prose. Available formats are `text`, `integer`, `decimal_1`, `decimal_2`, `percent_1`, `percentage_point_1`, `ratio_2`, and `currency_0`.

Supported deterministic checkers:

- `cohort_summary`
- `bundle_signal_winning_now`
- `bundle_signal_emerging`
- `bundle_bridge`
- `brand_fact`
- `review_availability`
- `source_fact`

`bundle_signal_winning_now` preserves the existing thresholds: at least three focus products, at least two brands, and top-seller share above other-product share. `bundle_signal_emerging` preserves the equivalent recent-versus-rest thresholds. Every displayed focus and baseline share in one layer must bind to one exact source filename and source-row hash, the row must have a non-empty `bundle_key`, and every numeric threshold input must be finite. `bundle_bridge` requires matching pair-or-triple source layers and the same canonical `bundle_key` to pass both layers.

A semantic synthesis claim has no fresh evidence reference or number. It cites passed deterministic support; the validator rejects semantic claims that try to introduce evidence refs directly:

```json
{
  "claim_id": "synthesis-category-direction",
  "kind": "semantic",
  "headline": "Cardigan structure connects current winners and emerging detail",
  "text_template": "The evidence points to continuity in garment structure, with newer products adding more specific knit expression.",
  "evidence_refs": [],
  "supporting_claim_ids": [
    "win-black-cardigan",
    "emerge-cable-cardigan"
  ],
  "interpretation": "This is a bounded synthesis of two supported package signals.",
  "caveat": "It should not be read as a causal forecast.",
  "confidence": "medium",
  "product_ids": []
}
```

## Deterministic tables

The author may reference only the existing four registered table keys in section `table_keys`:

- `attribute_bundle_comparison_table`
- `attribute_bridge_table`
- `rank_weighted_visibility_table`
- `product_signal_evidence_table`

The writer never supplies table rows. `prepare_run.py` calls the existing table-template module, records source files, row counts, columns, and hashes, and the HTML renderer reads those artifacts unchanged.

## Featured products and images

Each featured product supplies `product_id`, `role`, `rationale`, and `supporting_claim_ids`. Before mapping or reporting, `hydrate_images.py` may resolve the package's public image URLs into `images/local` and write `local_image_manifest.json`. The hydrator vets public numeric addresses and connects to a vetted address while preserving the original hostname for HTTP and TLS verification; every redirect is independently revalidated and repinned. The manifest pins every image to the exact package directory and relevant source-row hashes and records its byte hash. Hydrate the preliminary package for mapping, then hydrate the rebuilt post-mapping package again for reporting; never copy or reuse a manifest across those package directories. The renderer finds the exact product in `recent_products.csv` or `top_seller_products.csv`, verifies an existing pack/scrape/sidecar image, copies it into `assets/products`, records its hash, and links the product name to the source PDP URL. It never downloads an image during rendering or sends an image to the server.

Use local product images in two different ways:

- mapping: show relevant local images to a Codex mapping agent when the allowed taxonomy attribute is visually inferable;
- reporting/review: show only selected exemplar images tied to supported claims and inspect those images during semantic review when the report makes a visual-expression claim.

Do not ask the model to compare every old and new image as an unstructured visual dump. The attribute matrix remains the analytical backbone; images validate mappings and selected product examples.

## Semantic review contract

`semantic_review.json` must target the exact report id, evidence-catalog hash, report-model hash, and draft-HTML hash in `render_manifest.json`. The reviewer must be a different Codex agent from the author.

Required dimensions:

- `claim_coverage`
- `story_coherence`
- `importance_calibration`
- `caveat_handling`
- `brand_and_example_interpretation`
- `html_readability`

Each dimension has `status` (`pass`, `caveat`, `fail`, or `unable_to_determine`) and a reason. Every claim receives exactly one verdict: `supported`, `supported_with_caveat`, `unsupported`, or `unable_to_determine`.

`report_level_findings` is always a list. Each finding has a unique `code`, `status` (`caveat`, `fail`, or `unable_to_determine`), and non-empty `finding`. A `fail` finding makes the report incorrect even if the reviewer accidentally marks the overall verdict correct. `images_reviewed` must cover every rendered local product image with the exact product id, relative image path, image hash, status, and observation.

The reviewer identity fields are an orchestration contract: Codex must actually delegate to a different agent, while the checker verifies that the recorded identities differ. The local JSON alone is not cryptographic proof of agent identity.

The overall semantic verdict uses the same four report-level values: `correct`, `correct_with_caveats`, `incorrect`, or `unable_to_determine`. Semantic review cannot override a deterministic failure.

## Mapping task contract

Mapping tasks are pinned to one published taxonomy snapshot:

```json
{
  "schema_version": "attribute_reporting.mapping_tasks.v1",
  "taxonomy_snapshot": {
    "version": "published-version",
    "sha256": "canonical-json-sha256"
  },
  "tasks": [
    {
      "task_id": "product-attribute-stable-id",
      "product": {
        "retailer": "retailer-key",
        "row_type": "parent",
        "parent_product_id": "product-id",
        "variant_id": "",
        "category_key": "category-key",
        "source_row_sha256": "source-row-sha256",
        "title": "Product title",
        "description": "Bounded product text",
        "local_images": [
          {"path": "images/local/product-image.avif", "sha256": "image-sha256"}
        ]
      },
      "attribute": {
        "id": "attribute-id",
        "label": "Attribute label",
        "selection": "single",
        "allowed_values": [
          {"id": "value-id", "label": "Value label"}
        ]
      }
    }
  ]
}
```

For the installed Clara path, the server first issues this task object inside a `mapping_workset` envelope. Its `scope.source_package` is an opaque `evidence-job:<id>` locator and every `product.local_images` list is empty. The local client writes the complete response envelope to `workset.json` and requires `--tasks-output` to write its exact nested task object separately as `mapping_tasks.public.json`. `bind_mapping_images.py` may then create an enriched copy by adding only verified package-relative `images/...` paths and SHA-256 values from `local_image_manifest.json`. Absolute paths, extra image fields, unsupported extensions, duplicates, more than twelve images per task, and any other task edit are rejected on submission. Image bytes never cross the server boundary.

Codex decisions cover every task exactly once and use `mapped`, `no_value`, `oov_candidate`, or `unable_to_determine`. A mapped single-select decision may use `value_id` and `value_label`. A mapped multi-select decision uses `value_ids` and the exactly corresponding `value_labels`; the validator canonicalizes their order to active leaves in the pinned taxonomy. An OOV result records a candidate for governance; it does not edit taxonomy JSON.

These statuses describe observed attribute evidence, not merely whether an active leaf matched. Use `mapped` when the bounded evidence supports one or more active values. Use `no_value` only when the evidence supports no coherent value for this attribute after assigning pattern, knit, construction, neckline, sleeve, and other signals to their proper dimensions. Use `oov_candidate` when a coherent value for this attribute is positively supported but absent from the active taxonomy; for example, an explicitly stated fitted, cropped, straight, or relaxed silhouette in a sparse style taxonomy is OOV rather than `no_value`. Do not turn an allover color or knit pattern into a style OOV unless the evidence supports it as a distinct product-level style treatment. Use `unable_to_determine` when the available text and images cannot support a responsible choice, including a material source-identity conflict that the remaining evidence cannot resolve. Apply the same boundary to parallel products and record one reusable atomic OOV candidate where possible. The v1 decision shape cannot simultaneously preserve an active multi-select leaf and an OOV candidate; when both are materially supported, choose the result that best preserves the report's analytical use, disclose the unrecorded signal in the reason, and require an independent-review caveat.

The normal installed mode generates unresolved tasks only. Correction mode must follow an explicit user request and carry a non-empty audit reason. It regenerates the complete product/parent candidate set with `include_resolved: true`, then deterministically selects the complete correction-eligible subset: resolved cells whose effective matrix source is `codex` and whose exact identity exists in the pinned accepted Codex mapping state. Unresolved cells remain in normal mode, while retailer-filter, deterministic-explicit, and other non-Codex-effective values are excluded because changing the Codex row would not change the rebuilt report. The result is a full remap of the correction-eligible subset rather than a selected-cell patch. In the development path, apply regenerates the full workset and compares exact task content and coverage. In the installed path, the server strips the one permitted local-image enrichment, compares the original public workset, verifies its separately retained private workset against the unchanged source package, confirms the current central taxonomy, and recomputes decision and review validation. Both paths bind source-row and local-image hashes before database application.

The generated workset is product/parent-scoped because the current evidence package exposes the complete parent comparison matrix but not a complete variant workset. Its `coverage` object reports every skipped variant-scoped attribute cell. That is a visible partial-coverage boundary, not silent success.

An unresolved workset with no eligible product/parent cells is a first-class steady state. The server marks its envelope `status: no_work`; its task artifact must have an empty `tasks` list plus `task_count: 0`, `task_count_before_limit: 0`, `unresolved_attribute_cells: 0`, `include_resolved: false`, and `truncated: false`. The local workflow keeps the workset as evidence, skips decision authoring, independent mapping review, submission, and the rebuilt evidence job, and prepares the already hydrated preliminary package with the preliminary download and extraction receipts plus `--no-work-workset`. `prepare_run.py` binds the workset to that receipt's evidence job and package scope, copies it as `mapping_no_work_workset.json`, and records mapping review as `not_applicable`. Empty submissions are never used as a substitute for this branch.

The incremental unresolved review does not attest to historical mappings. If its coverage reports `include_resolved: false` and a positive `resolved_attribute_cells` count, final correctness visibly identifies that exact number of pre-existing resolved central-package cells as trusted input that was not re-reviewed in the run. The same disclosure is emitted for a no-work branch when resolved cells are present; even with zero resolved cells, the report states that it used the preliminary current-database package as-is. These boundaries force a caveated verdict rather than allowing `Correct` to imply a full remap or historical semantic audit.

### Bounded low-cost-agent sharding

`mapping_shards.py` is a mechanical context-bounding tool, not a classifier. `shard-tasks` partitions one complete, non-truncated workset in original order and writes a manifest that pins the full task artifact, taxonomy, scope, coverage, every task, and every slice. Each lower-cost Codex contributor fills only its attributed decision template. `merge-decisions` rejects missing shards, duplicate tasks, stale pins, incomplete coverage, or out-of-slice work; it restores original order, records contributor artifact hashes, and runs the normal complete mapping validator under a coordinator identity.

After the complete mapping validation and review template exist, `shard-review` partitions the exact per-task review scaffolds. Each scaffold pins both the mapping coordinator and the lower-cost contributor who authored that task. Every slice reviewer must differ from both; `merge-review` requires a coordinator independent of all mapping authors and all review contributors, rejects stale targets or incomplete review coverage, retains per-task contributor identity and shard provenance, and computes the overall status from the contributed semantic verdicts. The ordinary `validate_mapping_review.py` rechecks the same per-task independence and remains the final gate over the complete merged review. Shard manifests and partials remain local and are never submitted in place of the four complete mapping artifacts.

## Mapping review contract

Every new semantic mapping receives an independent, model-led review before database application. `prepare_mapping_review.py` creates only the mechanically verifiable scaffold: artifact hashes, taxonomy identity, task identity, source-row hashes, local-image hashes, and reviewer separation. A different Codex agent authors the per-task verdicts and reasons in `mapping_review.json`; deterministic code never substitutes its own semantic mapping judgment.

The top-level review targets exact canonical hashes for `mapping_tasks.json`, `mapping_decisions.json`, and `validated_mappings.json`, plus the validation checksum, published taxonomy snapshot, and combined mapping-content hash. Every task review also targets the exact task, decision, normalized mapping, source row, and ordered local-image checksums.

Each task receives exactly one verdict:

- `supported`
- `supported_with_caveat`
- `unsupported`
- `unable_to_determine`

The overall review is the mechanical aggregation of those model-authored judgments: `approved`, `approved_with_caveats`, `rejected`, or `unable_to_determine`. The validator rejects incomplete coverage, duplicate tasks, a reviewer matching the mapping author, mismatched overall status, or any stale content pin. Only `approved` and `approved_with_caveats` can pass the database apply gate. The database operation id binds both mapping-validation and mapping-review-validation checksums, and every audit row records reviewer identity and review lineage.

The installed server stores the four submitted mapping artifacts, the recomputed mapping-review validation, and a transactional submission receipt under the combined operation id. A rebuilt evidence job requested with that operation id copies those provenance artifacts into the URL-only portable package together with a sanitization receipt. `prepare_run.py` automatically detects the complete set at the rebuilt package root. It recomputes mapping and review validation; verifies operation id, actor, accepted database write, taxonomy and retailer/category scope; checks the URL-only/pass sanitization contract; pins every mapping-provenance file hash; and copies all seven artifacts into the report output. `--mapping-provenance-dir` provides an explicit local source only when they are not at the package root; any partial server set blocks preparation.

For this server-accepted path, `--download-receipt` and `--extraction-receipt` are mandatory. Preparation validates the exact v1 receipt schemas, requires both receipts to resolve to the same still-present archive, recomputes its hash and size, binds the extraction output to the supplied package directory, and checks the extraction receipt's complete file-count, byte-count, path, size, and hash ledger against the current package. Files added after extraction are rejected except `local_image_manifest.json` and manifest-pinned ordinary files below `images/local/`. Both exact receipt files are copied into the report output as `local_download_receipt.json` and `local_extraction_receipt.json`; their hashes and normalized lineage are recorded in both `run_intake.json` and `evidence_catalog.json`, and correctness checking repeats these checks. This closes accidental edit-or-substitution gaps between safe extraction and report preparation while keeping local image hydration possible. These checksums establish internal integrity and stale-content detection after the authenticated HTTPS download, but they are not digital signatures. An internally consistent package fabricated by a malicious local actor can imitate them, so `server_accepted` must not be described as cryptographic proof of server authenticity.

For a report generated after this mapping stage, keep `mapping_tasks.json`, `mapping_decisions.json`, `validated_mappings.json`, and `mapping_review.json` together in the report output directory. Production rebuilt packages also keep `mapping_submission_receipt.json`, `mapping_review_validation.json`, and `server_sanitization_receipt.json`. The final checker treats deleted, partial, stale, or invalid provenance as `Unable to determine`, a rejected semantic mapping as `Incorrect`, and an approved mapping with review or skipped-variant caveats as `Correct with caveats` at best. A four-artifact development review without server receipts is explicitly `local_review_only` and cannot receive an unqualified `Correct`. An existing-package report with none of these new-mapping artifacts records the mapping-review basis as `not_applicable`.

## Browser QA contract

Production server-package runs call `prepare_run.py` with both transport receipt paths and `--require-browser-qa`. After `render_report.py` and the independent semantic review, `browser_qa.py` loads the exact `report_draft.html` at desktop and mobile widths. It writes `browser_qa.json` plus local screenshots and checks:

- no horizontal page overflow;
- tables remain within explicit scroll containers;
- every local image exists and renders;
- script, image, and stylesheet assets are local and safe;
- product links use allowed web schemes;
- required report elements are present;
- the browser reports no page or console errors.

The QA artifact pins both the draft-HTML hash and render-manifest hash. It is a mechanical browser check, not a substitute for the independent agent's semantic and readability review. Missing, blocked, stale, invalid, or failed browser QA is material whenever the run intake requires it. Any draft edit invalidates both semantic review and browser QA.

## Correctness mechanics

`check_report.py` recomputes or verifies:

- evidence-catalog hash, package fingerprint, every declared source-file hash, every available catalog-source hash, and every claim-ledger source hash;
- package-integrity status and hash;
- report-model, claim-ledger, draft-HTML, table, and selected-image hashes;
- exact claim selector cardinality and evidence binding;
- preserved winning/emerging bundle thresholds;
- one-to-one claim and section parity in HTML;
- visible disclosure of every active warning;
- absence of external script/image assets;
- mapping-review artifact completeness, exact content pins, independent identity, and per-task coverage when the run includes new mapping provenance;
- independent-review identity, target hashes, dimension coverage, and claim coverage;
- required browser-QA schema, exact draft/render hashes, viewport coverage, and findings.

Every non-pass claim, review dimension, report-level finding, and reviewed image is materialized as a coded semantic finding. `Correct with caveats`, `Incorrect`, and `Unable to determine` banners therefore carry the relevant visible, durable rationale.

The final HTML embeds the direct verdict banner without changing the reviewed report body. Any model or body edit changes a hash and requires a new semantic review.

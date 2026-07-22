---
name: brand-fit
description: Use when a user wants Clara to compare a completed checked Retailer Signals report with a brand's current presence at that retailer and the brand's owned catalogue, then author and independently check a private local HTML Brand Fit report.
---

# Brand Fit

Use this workflow only downstream of a completed Retailer Signals run. Brand Fit compares the already-computed retailer signals with two distinct brand evidence scopes:

- the brand's current presence at that retailer, read from the current server database snapshot;
- the brand's mapped owned catalogue, read from the central server database.

Do not call a product a fit merely because one attribute matches. Codex agents decide signal importance, gap meaning, candidate relevance, and narrative through the user's existing ChatGPT plan. Deterministic code owns source rows, exact bundle matches, hashes, rendering, and correctness mechanics. Helper scripts make no separate model API call.

## Boundary

- The central server keeps structured scraped records, the central category taxonomy, accepted mappings, current retailer-presence rows, owned-catalogue rows, and image URLs.
- The checked Retailer Signals report, image bytes, Brand Fit model, semantic review, browser QA, and final HTML stay private and local.
- The source report is never uploaded. The authenticated create request sends only its SHA-256, exact verdict (`Correct` or `Correct with caveats`), and the actor-owned source evidence job id derived from that run's hash-pinned `local_download_receipt.json`.
- The retailer-presence evidence is a `current_database_snapshot`, not a claim that the retailer website was freshly scraped. Disclose the package `read_at` timestamp.
- Treat ranked reference candidates as leads for Codex evaluation, not automatic listing, launch, or assortment recommendations.

The files named as local remain on the user's machine, but their contents may
enter model context when Codex reads them for interpretation or review.

## Preconditions

The source Retailer Signals directory must contain an intact:

- `report.html`;
- `correctness_verdict.json` with `correct` or `correct_with_caveats`;
- `final_artifacts.json` with `final_ready` and the current report hash;
- `local_download_receipt.json` pinned by `evidence_catalog.json` transport lineage.

If any precondition is missing or stale, stop. Do not accept a manually supplied job id or a manually typed report checksum as a substitute.

## Codex-Native Run UX

Before helper scripts or write-heavy work, resolve only material choices that change the run: the completed Retailer Signals directory, brand name, brand-owned source retailer, category aliases when required, private local workspace, report audience, and any explicit emphasis. Do not offer new frameworks, fit definitions, taxonomies, report formats, or cohort definitions unless the evidence requires a user decision.

Use these visible artifacts in chat:

1. Start with a checklist covering source-report validation, authenticated Brand Fit job, checksum download and safe extraction, mapping-state/product-snapshot verification, local image hydration, report preparation, Codex authoring, independent semantic review, desktop/mobile browser QA, correctness, and delivery.
2. Show a Run Intake table with source Retailer Signals run, retailer, category, brand, brand-owned source, database snapshot posture, local workspace/output directory, image posture, and report audience.
3. Show a compact **Decision Table** only for unresolved category aliases, missing/stale source evidence, ambiguous brand source, incomplete image evidence, unsupported server access, or a material report-angle choice. Resolve inferable details yourself.
4. Before a long or write-heavy step, show an execution checkpoint with the command, inputs, private output folder, and expected artifacts. Ask for continuation only when the step is external, destructive, approval-sensitive, or still depends on a material unresolved decision.
5. End with an **Artifact Card** listing local paths, purpose, the exact direct correctness verdict, independent-review state, unresolved items, and next action. `codex_run_review.md` is the durable local card.

Default output policy: produce the richest natural private local package—transport receipts, pinned server evidence, accepted mapping-state and product-data snapshots, local image manifest, evidence catalog, scope metrics, report model, claim ledger, HTML draft, independent semantic review, desktop/mobile browser QA, final `report.html`, direct correctness verdict, `codex_run_review.md`, and `final_artifacts.json`. These are not choices to propose. HTML is the production report format. Never edit plugin source or generated ZIPs during a user run, and never place generated ZIPs or run outputs in the plugin repository.

## Dependency Check

Before helper scripts, run `python scripts/check_dependencies.py` from the plugin working directory. It reports missing declared dependencies and never installs packages at runtime.

## Installed flow

1. Use the existing private Mparanza session file. Never put authentication material in the run directory.
2. Create the Brand Fit job. The client derives the source evidence job, report hash, and source verdict from the completed local run:

```bash
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies create-brand-fit \
  --retailer-run <retailer-signals-report-dir> \
  --brand-source-retailer <brand-owned-source> \
  --brand-name <brand-name> \
  --output <run>/server/brand-fit-job.json
```

Use repeatable `--owned-category-key` or `--retailer-category-key` only when the existing category aliases require them. Omit them otherwise.

3. Poll, checksum-download, and safely extract the ready job:

```bash
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies poll-brand-fit <job-id> --output <run>/server/brand-fit-status.json
python scripts/server_bridge_client.py --session-file <private-auth-dir>/mparanza-session.cookies download-brand-fit <job-id> --output <run>/server/brand-fit.zip --receipt <run>/server/brand-fit-download.json
python scripts/server_bridge_client.py extract-evidence --archive <run>/server/brand-fit.zip --output <run>/brand-fit-package --receipt <run>/server/brand-fit-extraction.json
```

4. Download supported product images to that local package. Retailer anchors and owned-catalogue products are scope-separated so a shared product id cannot silently merge their image evidence:

```bash
python scripts/hydrate_images.py <run>/brand-fit-package
```

5. Prepare the local report run. Preparation requires verified transport receipts, an exact `pack_manifest.json`, `package_integrity: pass`, URL-only server sanitization, pinned accepted `mapping_state_snapshot.json` and product-data snapshot scopes, a current-database retailer-presence disclosure, and exact agreement with the checked source-report hash and coherently derived verdict:

```bash
python scripts/prepare_brand_fit_run.py <run>/brand-fit-package \
  --retailer-run <retailer-signals-report-dir> \
  --output-dir <run>/report \
  --author-agent-id <codex-author-id> \
  --download-receipt <run>/server/brand-fit-download.json \
  --extraction-receipt <run>/server/brand-fit-extraction.json
```

6. Have a Codex agent author `report_model.json` using `authoring_contract.json`:

- preserve the six required section roles and order;
- bind each deterministic claim to an exact CSV row with a selector that matches once;
- display evidence values only through `{{ref_id.field}}` tokens;
- support semantic claims only with already-bound deterministic claims;
- distinguish current retailer presence, the wider owned catalogue, and candidate products;
- acknowledge and visibly explain every active package warning;
- select only products whose exact source rows support the rationale.

7. Render the draft:

```bash
python scripts/render_brand_fit_report.py <run>/report
```

Rendering hash-binds the claim ledger, report model, source report, selected product rows, and local images. It also writes an exact `semantic_review.json` template.

8. Delegate `semantic_review.json` to a different Codex agent. The reviewer must cover every claim, every selected image (including explicit unavailable-image entries), and all required dimensions. The reviewer must not be the report author.

9. Run desktop/mobile browser QA, then correctness:

```bash
python scripts/browser_qa.py <run>/report
python scripts/check_brand_fit_report.py <run>/report
```

## Correctness answer

Always answer “Is this Brand Fit report correct?” with exactly one of:

- `Correct`
- `Correct with caveats`
- `Incorrect`
- `Unable to determine`

Tampered evidence, claim ledgers, source-report bindings, local images, or HTML parity make the report `Incorrect`. A failed semantic or browser finding also makes it `Incorrect`. Missing, stale, incomplete, or non-independent semantic review and missing/blocked required browser QA make it `Unable to determine`. Active disclosed package warnings, an approved semantic caveat, or a source Retailer Signals report that is itself `Correct with caveats` make the result at best `Correct with caveats`.

## Expected local outputs

- copied, hash-bound Brand Fit evidence, exact pack manifest, accepted mapping-state snapshot, product-data snapshot, and checked Retailer Signals report;
- copied transport and sanitization receipts;
- `report_model.json`, `claim_ledger.json`, and `render_manifest.json`;
- selected hash-bound local images under `assets/products/`;
- `report_draft.html`, `semantic_review.json`, and `browser_qa.json`;
- `correctness_verdict.json`, `report.html`, `codex_run_review.md`, and `final_artifacts.json`.

Never upload these report artifacts or image bytes to the server.

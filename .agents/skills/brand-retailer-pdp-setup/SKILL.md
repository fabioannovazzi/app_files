---
name: brand-retailer-pdp-setup
description: Set up a brand-owned PDP source for retailer/category comparison packages. Use when the user asks to find or choose a brand for a retailer category, check whether the brand website has matching products, discover brand-site filters, scrape brand PDPs, materialize filter attributes, map remaining PDP attributes, verify overlap/counts, or build brand-vs-retailer Brand Fit packages such as brand / Saks cashmere or sneakers and brand / Ulta blush or bronzer.
---

# Brand Retailer PDP Setup

Use this workflow for the end-to-end repeatable setup of a brand source retailer that will be compared against an existing retailer/category benchmark.

## Ground Rules

- Run from `<repo-root>` with `source .venv/bin/activate`.
- Use PDP Postgres only. Do not use or introduce a SQLite fallback. If `PDP_DATABASE_URL` or the SSH tunnel is unavailable, fix that before running discovery, scrape, materialization, mapping, or package generation.
- Keep the scope explicit: one brand-source retailer, one comparison retailer, and one or more normalized category keys.
- Persist intermediate results. Even filtered/debug runs should write listing observations, filter observations, links, PDP rows, materialized attributes, logs, and package outputs.
- Preserve product identity from the discovered URL. If a brand site canonicalizes or redirects color-specific PDPs to a default PDP, keep the requested URL parent id and rewrite variants consistently.
- For a brand scraping pipeline, do not run `scripts/brand_web_search_attribute_fill.py` after the official brand PDP/API scrape. The scraped PDP evidence, brand-site filters, deterministic mapping, and `export_pdp_attributes.py --run-vlm` are the source of truth. Report remaining gaps instead of filling them from web search unless the user explicitly asks for a separate web-search enrichment pass.

## Workflow

1. Verify the retailer/category benchmark exists.
   - Check `config/pdp_profiles/{retailer}_{category}.json`.
   - Check `data/pdp/reports/packages/launch/{category}/{retailer}` before package generation.
   - Query Postgres counts for retailer parents, brand-at-retailer parents, and existing category coverage.

2. Choose or validate a brand.
   - Prefer brands with visible inventory in the target retailer/category and an official brand-site category page that can be scoped to the same category.
   - When comparing candidate brands, count retailer presence first, then inspect the official site for matching PDP discoverability and filters.
   - Explain listing-count ambiguity. Brand site totals may mean SKUs, colorways, sizes, or availability rows rather than unique PDP parents.

3. Discover the brand site.
   - Inspect the official category URL, filters, HTML data blobs, sitemap/API endpoints, and pagination/load-more behavior.
   - Record product-level filters only. Materialize color, size, badge/newness, fit, material, silhouette, price bands, or other category-relevant attributes when present. Ignore store availability unless the user explicitly asks for it.
   - Define one deterministic source of truth for discovered PDP links and filter memberships.

4. Add or reuse repo support.
   - Catalog helper: `modules/pdp/{brand}_catalog.py`.
   - Filter discovery: `modules/pdp/{brand}_filter_discovery.py`.
   - PDP adapter: `modules/pdp/adapters/{brand}.py`.
   - PDP profile: `config/pdp_profiles/{brand}_{category}.json`.
   - Discovery script: `scripts/run_{brand}_discovery.py`.
   - Filter materialization script: `scripts/materialize_{brand}_filter_attributes.py`.
   - Register the adapter in `modules/pdp/service.py`, `modules/pdp/__init__.py`, `scripts/cdp_fetch_pdp.py`, and any reconciliation script that imports adapters.
   - Add focused tests for catalog parsing, filter discovery, and adapter parsing.

5. Run discovery.

```bash
source .venv/bin/activate
python scripts/run_{brand}_discovery.py
```

Expected outputs include `data/pdp/discovery_runs/{brand}/...`, persisted `retailer_listing_observations`, persisted `retailer_filter_surfaces`, persisted `retailer_filter_observations`, and `data/pdp/links.json` entries for `{brand}.{category}`.

6. Scrape PDPs.

```bash
source .venv/bin/activate
python scripts/run_pdp_parser.py --retailer {brand} --categories {category} --overwrite
```

Use `scripts/cdp_fetch_pdp.py` instead when the site requires browser/CDP rendering. After scraping, verify active parent and variant counts match the corrected discovery scope.

7. Materialize brand-site filters.

```bash
source .venv/bin/activate
python scripts/materialize_{brand}_filter_attributes.py
```

This should write deterministic `retailer_filter` attribute rows into `pdp_attribute_values`. Verify parent count, filter surfaces, observations, and attribute row counts.

8. Build deterministic/text-LLM/VLM attributes in the PDP database.

```bash
source .venv/bin/activate
PYTHONPATH=$PWD python scripts/export_pdp_attributes.py \
  --retailer {brand} \
  --category {category} \
  --run-vlm
```

The export script persists mapped attributes and the package-facing attribute cache in the PDP database. Brand Fit package generation reads catalog attributes from the database; do not add local file-cache requirements. VLM/image fill belongs here, not in the brand web-search command.

9. Skip brand-site web search fill for brand scraping pipelines.

Do not run `scripts/brand_web_search_attribute_fill.py` when the official brand site has already been discovered and scraped. If mapped attributes are still missing after step 8, inspect the scraped PDP/filter evidence and mapping rules, then report the remaining gap. Treat web-search enrichment as a separate, user-requested follow-up, not part of this workflow.

10. Build the Brand Fit package when mapping is ready.

```bash
source .venv/bin/activate
PYTHONPATH=$PWD python scripts/build_brand_retailer_reference_package.py \
  --brand-source-retailer {brand} \
  --brand-name "{Brand Name}" \
  --retailer {retailer} \
  --category {category}
```

Use repeated `--category` flags for multiple categories. If the live retailer brand URL is wrong or unavailable, correct the brand URL logic when possible; otherwise use `--skip-retailer-live-check` only when the package inputs are otherwise validated.

## Verification Checklist

- Postgres connection works through the tunnel before any runtime step.
- Discovery link count equals the intended unique parent PDP count.
- Site filters are captured and product-level filter memberships are inspectable.
- PDP scrape has zero parser failures or documented expected skips.
- Active brand parent count and variant count match the corrected scrape.
- No stale generated rows remain from earlier buggy parses.
- `export_pdp_attributes.py --run-vlm` is scoped to the new brand/category and writes package-facing cache files.
- `brand_web_search_attribute_fill.py` was not run for the brand scraping pipeline. If the user explicitly requested web-search enrichment, document that it was a separate follow-up and rerun the scoped export if it wrote new values.
- The Brand Fit package is created under `data/pdp/reports/packages/brand_fit/{category}/{retailer}/{brand}` with a successful summary row.

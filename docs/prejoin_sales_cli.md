PDP attribute mapping and sales joins
=====================================

Environment
- Use the project virtualenv interpreter:
  - `./.venv/bin/python`
- Run commands from repo root with `PYTHONPATH=$PWD`.

Recommended CLIs
- Brand-site web-search attribute fill:
  - `PYTHONPATH=$PWD ./.venv/bin/python scripts/brand_web_search_attribute_fill.py`
- Image/VLM attribute fill is normally run by:
  - `PYTHONPATH=$PWD ./.venv/bin/python scripts/export_pdp_attributes.py --run-vlm`
- Dataset join output (run per dataset):
  - `PYTHONPATH=$PWD ./.venv/bin/python scripts/prejoin_sales.py --dataset <dataset>`

There is intentionally no script that runs both attribute fill and sales join.
`brand_web_search_attribute_fill.py` runs only the brand-site web-search fill.
`prejoin_sales.py` only loads sales CSVs and writes joined outputs from the
already-mapped cache.

Purpose
- Attribute fill persists deterministic/LLM, VLM, and brand-site web-search attributes to the PDP database.
- Sales join loads a selected sales CSV dataset and joins it with persisted PDP attributes so the API can serve sales data without live joins.
- Sales join handles per-retailer join keys, fallback matching, and precomputes price bands and Pareto.

Pipeline boundary
- `prejoin_sales.py` serves the sales-analysis pipeline only. It is not part of the current retailer-signals -> brand-fit -> product-hypothesis report pipeline.
- `prejoin_sales.py` expects already-normalized PDP/category/attribute data as input. Cross-retailer category and attribute normalization belongs upstream in the attribute export/mapping pipeline, not in the sales join.
- The sales join should match sales rows to catalog rows, preferably on SKU keys. Any category checks inside this flow are legacy defensive join compatibility, not the source of truth for category normalization.
- Brand-fit packages should read PDP attribute caches, shared mapped attribute outputs, retailer signal bundles, and report package inputs directly. They should not use sales-join matching logic as evidence for brand fit.
- Brand Fit packages require a completed retailer-signal package and its matching retailer-signal brief. Raw generated signal tables are not enough; see `brand_fit_packages.md`.
- Legacy attribute-analysis pages may still load outputs produced around the sales-prejoin flow. Treat that as legacy coupling, not the source of truth for report generation.
- When diagnosing Kiko brand-fit quality, inspect the attribute export/mapping outputs and package inputs. Do not use `prejoin_sales.py` as an authority unless the task is specifically about sales-dataset joins.

Inputs
- Sales files:
  - Default dataset: `data/pdp/sales_data/csv_files/*.csv`
  - Named dataset: `data/pdp/sales_data/datasets/<dataset>/csv_files/*.csv`
  - The CLI concatenates and normalizes headers; required normalized columns are `month, merchant, category, brand, sku, product_description, sales, units`; `merchant` must be non-empty.
- Attribute cache: persisted PDP database attribute values/cache entries.
- Join key config (optional): `config/sales_join_keys.json` (or `.yaml`).
- Category taxonomy prerequisite:
  - Before running attribute export or shared mapping for a new retailer/category, create the category JSON in `config/attribute_taxonomy/categories/` and add it to `config/attribute_taxonomy/manifest.json`.
  - Seed the taxonomy from retailer filter families/values first. Use PDP evidence to refine those leaves, cover missing retailer-filter values, and add dimensions that are absent from the retailer taxonomy.
  - When both sources exist for a product, retailer filter values take precedence. PDP-derived mapped attributes only backfill missing retailer-filter values or populate dimensions that the retailer filters do not define.

Join behavior
- Per retailer (merchant):
  - Primary join: sales SKU → catalog `variant_id` (configurable per retailer).
  - Fallback: normalized brand + product name (canonical) for remaining unmatched rows.
  - Optional parent fallback if configured.
  - Price bands: computed per retailer slice from catalog prices.
  - Pareto: computed per retailer slice on joined sales.
- Duplicate attribute columns that normalize to the same key (e.g., `free from` vs `free_from`) are coalesced during attribute export; the prejoin keeps only the deduped canonical columns.
- Manifest now includes unique counts (sales SKUs/canonicals, catalog variants/parents, matched/unmatched variants/parents), recency buckets for sales-only unmatched, and paths to unmatched audit exports when produced.

Parent attribute fill behavior
- During pre-join, we use the parent attribute cache to fill missing sales-side attributes.
- A missing value is filled only when all non-missing values for the same attribute resolve to a single value across retailers.
- Ambiguous cases (multiple distinct non-missing values across retailers) are left unchanged.
- Repeated no-value suppression: vision/web steps stop re-querying an attribute after 2 consecutive no-value runs for the same product key + attribute in that step.

Example (A/B/C cases)
- Case A: Retailer A = "Organic", Retailer B = "Organic", Retailer C = missing → fill C with "Organic".
- Case B: Retailer A = "Organic", Retailer B = "Natural", Retailer C = missing → leave C missing (ambiguous).
- Case C: Retailer A = missing, Retailer B = missing, Retailer C = missing → leave C missing (no signal).

Outputs
- Dataset-specific join outputs:
  - `data/pdp/sales_data/joined_datasets/<dataset>/full_sales.parquet`
  - `data/pdp/sales_data/joined_datasets/<dataset>/joined.parquet`
  - `data/pdp/sales_data/joined_datasets/<dataset>/joined_manifest.json`
- Optional dataset metadata in input folder:
  - `data/pdp/sales_data/datasets/<dataset>/metadata.json` (or root for default)
  - Example: `{"industry": "Cosmetics in Italy", "currency": "EUR"}`

Runtime consumption
- `modules/pdp/sales_join.load_sales_data` prefers `joined.parquet` and skips live joins when present.
- `modules/pdp/sales_join.load_full_sales_data` prefers `full_sales.parquet` for “full dataset” charts; both functions fall back to legacy/retailer CSVs if the Parquet outputs are missing.

Typical workflow
0) For any new retailer/category, publish the category taxonomy JSON first:
   - add `config/attribute_taxonomy/categories/<category>.json`
   - register it in `config/attribute_taxonomy/manifest.json`
   - seed it from retailer filters, then refine with PDP evidence
1) Put dataset CSV files in one folder:
   - default dataset: `data/pdp/sales_data/csv_files/`
   - named dataset: `data/pdp/sales_data/datasets/<dataset>/csv_files/`
2) Optional quality boost: run brand-site web-search fill:
   - `PYTHONPATH=$PWD ./.venv/bin/python scripts/brand_web_search_attribute_fill.py`
   - If you skip this step, join still runs using the base attribute cache.
3) Build joined outputs for one dataset:
   - `PYTHONPATH=$PWD ./.venv/bin/python scripts/prejoin_sales.py --dataset kiko`
   - (or omit `--dataset` to use `PDP_SALES_DATASET`/default)
4) Restart the API (optionally with `PDP_SALES_DATASET=<dataset>`) to load the chosen joined outputs.

Notes
- If a retailer is missing from the catalog cache, manifest will show catalog_rows=0 and joined_rows=0.
- If matches are low, check `joined_manifest.json` to adjust join keys or normalize brand/product text upstream.

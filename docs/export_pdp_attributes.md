Persist PDP Attributes
======================

Script: `python scripts/export_pdp_attributes.py`

Purpose
- Persist deterministic PDP attributes from parsed PDP data into the configured PDP database.

Prerequisite taxonomy setup
- Before exporting a new retailer/category, create the category JSON under `config/attribute_taxonomy/categories/` and register it in `config/attribute_taxonomy/manifest.json`.
- Build that taxonomy from retailer filter families/values first, then use PDP evidence to validate the leaves, fill gaps, and propose extra dimensions that the retailer filters do not expose.
- Runtime precedence is: retailer filter taxonomy first; mapped PDP attributes are used only when the retailer filter has no value for a given product or when the dimension does not exist in the retailer filter taxonomy.
- Runtime attribute frames retain the winning database source in `<attribute>_effective_source` (for example `codex`, `retailer_filter`, or `deterministic_explicit`). Evidence-pack construction carries that provenance into `product_filter_matrix.csv` and overwrites it with `retailer_filter` when the package's filter-primary layer wins. This makes it mechanically possible to distinguish a Codex mapping that can change a rebuilt report from a lower-priority Codex row that cannot.

What it does
- Reads parsed PDP data from the shared PDP store.
- Normalizes/cleans text, dedupes columns that normalize to the same key (e.g., `free from`/`free_from`), and writes attribute values, stage values, audit rows, and serialized attribute-cache blobs to the PDP database.
- Supports LLM/deterministic modes via config.

Key options
- `--retailer RET` (repeatable): limit export to specific retailer(s).
- `--category CAT` (repeatable): limit to categories.
- `--run-vlm`: after DB persistence, run scoped image/VLM attribute mapping without brand-site web-search mapping.
- The PDP store is configured through `PDP_DATABASE_URL` in `.secrets/secrets.toml`.
- Logging: `EXPORT_LOG_LEVEL` env var controls verbosity; writes to `logs/export_pdp_attributes.log`.

Usage
```bash
PYTHONPATH=$PWD python scripts/export_pdp_attributes.py --retailer ulta
```

Outputs
- PDP database tables/cache entries. This command does not write CSV or Parquet attribute export files.

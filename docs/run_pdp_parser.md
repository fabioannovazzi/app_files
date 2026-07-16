Run PDP Parser
==============

Script: `python scripts/run_pdp_parser.py`

Purpose
- Parse product detail pages (PDPs) for supported retailers, persisting parents/variants to the shared PDP store and the attribute cache.

What it does
- Discovers PDP URLs (or uses provided URLs), fetches PDP HTML (retailer-specific fetchers), parses into parent/variant schemas, writes to the shared PDP store and evidence storage, and logs metrics.
- Supports profiles per retailer/category and optional image download.

Key options (subset)
- `--profile NAME`: specific profile to run (e.g., `ulta_lipstick`).
- `--urls URL [URL…]` or `--urls-file FILE`: explicit URLs to parse.
- `--retailer RET`: retailer identifier; can auto-discover categories.
- `--categories CAT [CAT…]`: category slugs/labels for discovery.
- The PDP store is configured through `PDP_DATABASE_URL` in `.secrets/secrets.toml`.
- `--batch-size N`, `--max-urls N`, `--skip-existing`, `--download-images`, etc. (see `--help` for full list).

Usage
```bash
PYTHONPATH=$PWD python scripts/run_pdp_parser.py --retailer ulta --categories blush lipstick
```

Outputs
- Updates the shared PDP store and associated caches/evidence; prints a summary of parsed/failed/skipped counts.

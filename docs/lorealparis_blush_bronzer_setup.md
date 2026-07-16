# L'Oreal Paris Blush And Bronzer PDP Setup

This setup adds L'Oreal Paris USA as retailer key `lorealparis` for the same PDP
and attribute workflow used for Kiko.

## Scope

- Category pages:
  - `https://www.lorealparisusa.com/makeup/face/blush`
  - `https://www.lorealparisusa.com/makeup/face/bronzer`
- PDP profiles:
  - `lorealparis_blush`
  - `lorealparis_bronzer`
- Product tag links on L'Oreal Paris PDPs are materialized as
  `retailer_filter` rows when they map cleanly to the local blush/bronzer
  taxonomy.

## Commands

Run from the activated repo environment:

```bash
cd ~/Documents/GitHub/app_files
source .venv/bin/activate
```

1. Discover the L'Oreal Paris blush and bronzer PDP family links:

```bash
python scripts/run_retailer_listing_discovery_cdp.py \
  --retailer lorealparis \
  --categories blush bronzer \
  --sort-modes default \
  --max-pages 1 \
  --remote-url http://127.0.0.1:9222
```

2. Scrape and parse the discovered PDPs:

```bash
python scripts/cdp_fetch_pdp.py \
  --retailer lorealparis \
  --categories blush bronzer \
  --task-source latest-listing \
  --listing-sort-modes default \
  --remote-url http://127.0.0.1:9222
```

3. Materialize L'Oreal Paris PDP tag/filter attributes:

```bash
python scripts/materialize_lorealparis_filter_attributes.py \
  --categories blush bronzer
```

4. Run the existing attribute export and mapping flow scoped to L'Oreal Paris:

```bash
python scripts/export_pdp_attributes.py \
  --retailer lorealparis \
  --category blush \
  --category bronzer

python scripts/brand_web_search_attribute_fill.py \
  --retailer lorealparis \
  --category blush \
  --category bronzer
```

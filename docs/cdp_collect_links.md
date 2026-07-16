CDP Collect Links
=================

Script: `python scripts/cdp_collect_links.py`

Purpose
- Collect PDP links from category/PLP pages using a running Chrome via CDP/Playwright.

What it does
- Connects to an existing Chrome (`--remote-url`, default `http://localhost:9222`) and scrolls/paginates category pages to extract PDP links.
- Can operate from retailer profiles (auto-discover category URLs) or a provided category URL.
- When profiles provide multiple `category_urls`, processes all seed URLs for that category.
- Supports auto-pagination, scrolling, and link caps; writes collected links to JSON.
- Auto-pagination uses retailer-specific query params (`currentPage` for Sephora, `page` for Amazon).
- For Amazon, applies category-aware title filtering on search-result cards to keep links relevant to the active category.
- For Amazon page 1, includes a quality gate (retry + minimum link threshold) before accepting a snapshot.
- If the attached Chrome context closes unexpectedly, attempts a CDP reconnect and continues.

Key options (subset)
- `--remote-url`: Chrome DevTools endpoint.
- `--retailer`: Retailer name to pull category URLs from profiles (unless `--category-url` is given).
- `--categories`: Optional category keys to limit profile discovery.
- `--category-url`: Explicit category/PLP URL to open (requires `--category-name`).
- Paging/scrolling: `--page-start/--page-end`, `--auto-paginate`, `--scroll-steps`, `--wait-ms`, `--timeout-ms`, `--max-pages`, `--delay-seconds`, `--min-new-per-page`, `--max-links`.
- Amazon stability: `--amazon-min-first-page-links`, `--amazon-first-page-attempts`.
- Category reset: `--reset-category-links` to clear existing links for the selected categories before recollecting.
- Tab reuse: `--reuse-open-tab`, `--no-navigation`.
- Output is saved to `data/pdp/links.json`.

Usage
```bash
# Using a running Chrome on port 9222, for a specific category URL
python scripts/cdp_collect_links.py --remote-url http://localhost:9222 \
  --category-url "https://example.com/category" \
  --category-name "lipstick" \
  --auto-paginate
```
Or, using profiles:
```bash
python scripts/cdp_collect_links.py --remote-url http://localhost:9222 \
  --retailer ulta --categories lipstick blush --auto-paginate
```

To rebuild a category cleanly after filter changes:
```bash
python scripts/cdp_collect_links.py --remote-url http://localhost:9222 \
  --retailer amazon --categories blush --auto-paginate --reset-category-links
```

Notes
- Requires Chrome started with `--remote-debugging-port=9222` and Playwright installed.
- Uses retailer profiles for discovery if `--retailer` is provided.***

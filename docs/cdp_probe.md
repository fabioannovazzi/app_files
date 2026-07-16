CDP Probe
=========

Script: `python scripts/cdp_probe.py`

Purpose
- Quick probe tool to test PDP fetching via a visible Chrome CDP session. Collects a few PDP links from a category page and saves HTML snapshots.

What it does
- Connects to a running Chrome (`--remote-url`), opens a category/PLP URL, scrolls, collects PDP links with a configurable selector, then fetches up to `--pdp-limit` PDP pages and saves their HTML to `data/pdp/cdp_probe/` (or `--output-dir`).
- If the attached Chrome context closes unexpectedly, attempts a CDP reconnect and retries once.

Key options
- `--remote-url`: Chrome DevTools endpoint (default `http://localhost:9222`).
- `--category-url` (required): Category/PLP URL to open.
- `--selector`: CSS selector for PDP links (defaults to a broad set).
- `--scroll-steps`: How many scroll passes before collecting links (default 8).
- `--pdp-limit`: Max PDPs to fetch (default 3).
- `--output-dir`: Where to write HTML snapshots (default `data/pdp/cdp_probe`).
- `--timeout-ms`: Playwright navigation timeout (default 45000 ms).
- `--reuse-open-tab`, `--no-navigation`: Operate on an existing tab without navigating.

Usage
```bash
python scripts/cdp_probe.py --remote-url http://localhost:9222 \
  --category-url "https://example.com/category" --pdp-limit 3
```

Notes
- Requires Chrome started with `--remote-debugging-port=9222` and Playwright installed.
- Writes PDP HTML files for inspection/diagnostics.***

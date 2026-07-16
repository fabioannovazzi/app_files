Chewy Listing Discovery
=======================

Scope
-----
- Retailer: `chewy`
- Category: `wet_cat_food`
- Category URL: `https://www.chewy.com/b/wet-food-389`
- Required sort surfaces: `newest`, `best_selling`
- Required filter families: `lifestage`, `food texture`, `flavor`, `special diet`, `health feature`, `package count`, `packaging type`

Use `wet_cat_food` for runs and artifacts.

What Happened
-------------
Chewy does not currently behave like Saks in a fresh CDP Chrome profile.

The normal Saks-style command is intended to run one discovery job that captures:
- both sort surfaces;
- listing observations;
- filter surfaces;
- filter memberships;
- `data/pdp/links.json` updates;
- run artifacts under `data/pdp/discovery_runs/cdp/chewy/<run_id>/`.

For Chewy, the browser-backed discovery command can connect to Chrome and can attempt navigation, but Chewy often returns a blank page before any product grid is available. The captured HTML is a Kasada/KPSDK challenge shell, not a product listing.

Observed signatures:
- Browser stays visually white.
- Failure bundle HTML contains `window.KPSDK`, `KP_UIDz`, or `ips.js`.
- Direct HTML requests return HTTP `429` and the same KPSDK shell.
- No product links or filter DOM exist in the captured document.

This means selector changes do not solve the failure. There is no listing DOM to parse.

What Worked
-----------
Manual URL entry sometimes worked for loading a product grid:

```text
https://www.chewy.com/b/wet-food-389
```

When the user manually pasted the URL into the visible Chrome window and waited for products to render, the scraper could read the already-loaded tab. That path proved that the Chewy link extraction and canonicalization logic can work once the product DOM exists.

What Did Not Work
-----------------
These paths did not reliably produce a Chewy product DOM:
- Fresh CDP Chrome profile plus automatic Playwright navigation.
- Fresh CDP Chrome profile plus address-bar-style CDP navigation.
- Direct `curl`/HTML fetch.
- Treating the page as a selector or scroll timing issue.

Why This Differs From Saks
--------------------------
Saks discovery can be run as one CDP-driven command because the attached browser can navigate to each surface and render the PLP.

Chewy distinguishes between a human-loaded page and automation/CDP-driven navigation in this environment. The discovery pipeline expects to navigate between surfaces (`newest`, `best_selling`, filters) itself. Chewy blocks that automatic navigation before the PLP renders.

Current Command Shape
---------------------
Chewy now carries the noisy settings as retailer defaults. The normal command is:

```powershell
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food
```

`--remote-url` already defaults to `http://localhost:9222`.

For `--retailer chewy`, the runner applies these defaults:
- sort modes: strategy defaults, currently `newest` and `best_selling`;
- filter families: `lifestage`, `food texture`, `flavor`, `special diet`, `health feature`, `package count`, `packaging type`;
- `--max-pages 100`;
- `--filter-max-pages 100`;
- `--delay-seconds 1`;
- `--wait-ms 3000`;
- `--max-idle-scrolls 2`;
- normal CDP/browser navigation, with Chewy page advancement done through visible pagination controls;
- `--manual-navigation-crawl-filter-memberships`;
- `--manual-navigation-auto-paste-wait-seconds 20`;
- `--manual-navigation-auto-paste-attempts 5`.

The CDP Chrome window must stay open, visible, and usable while the run is active because Chewy navigation uses Windows clipboard/keyboard automation for the URL transitions.

Sort And Filter Mechanics
-------------------------
Chewy sort is controlled through the visible `Sort By` widget, not by `?sort=...` URLs.

For category ranking surfaces the runner now:
- loads the category URL without a `sort` query parameter;
- sets the Chewy `Sort By` widget to `Newest` or `Bestselling`;
- verifies the widget state before scraping. This supports both the wide desktop
  native select and the narrower responsive radio-drawer layout;
- captures page 1;
- paginates by clicking Chewy's visible `Next Page` control, preserving the browser's
  widget state before every capture.

For filter discovery the runner also uses Chewy's visible `Next Page` control. This
matters because the old first-page-only filter crawl produced partial memberships and
then inflated `links.json` with only the first page of each filter value.

If the widget remains on `Relevance`, or if Chrome is still on a stale `?sort=...`
or wrong `?page=...` URL, the run stops and leaves the checkpoint in place. Restart
Chrome if needed and resume with `--resume`; do not keep a run that scraped
`Relevance` as though it were a ranked sort.

At startup, the run logs `Chewy sort guard active (widget_click_pagination_v4)`. If that
line is missing, the process is running old code and the run should be stopped.
Checkpoints created before this guard are rejected on resume because they may
contain category rows scraped under `Relevance`.

If the run logs `Chewy manual sort widget mode is active`, the operator must set the
widget manually and the scraper will only verify it. That mode is no longer the
default; use it only when debugging the automatic sort setter.

For filter discovery the runner reads Chewy facet metadata from the loaded DOM:
- `data-facet-category`
- `data-facet-group-id`
- `data-facet-id`

This is necessary because many visible filter values have no usable `href`, including package-count values. The extractor synthesizes stable Chewy facet URLs from those IDs, for example:

```text
https://www.chewy.com/f/6-count-or-less-wet-cat-food_c389_f194v19633414
```

Working Windows Setup
---------------------
When Chewy works in normal Chrome but a fresh CDP Chrome goes white, use a cloned Chrome profile instead of a brand-new one.

1) Close Chrome completely
```powershell
taskkill /IM chrome.exe /F
```

2) Clone the normal Chrome user-data directory
```powershell
robocopy "$env:LOCALAPPDATA\Google\Chrome\User Data" "C:\temp\chrome-cdp-chewy-clone" /MIR /R:1 /W:1
```

3) Start Chrome from the cloned directory with CDP enabled
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\temp\chrome-cdp-chewy-clone" `
  --profile-directory="Default"
```

4) In that Chrome window, open `https://www.chewy.com` manually and confirm it renders normally.

5) Verify that CDP is reachable
```powershell
Invoke-WebRequest http://127.0.0.1:9222/json/version
```

6) Run discovery
```powershell
cd C:\path\to\app_files
$env:PYTHONPATH = (Get-Location).Path
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food
```

Notes:
- Keep the seeded Chewy tab open while the run is active.
- If the tab goes white before the grid renders, the run is blocked before discovery can collect anything.

Resume After Browser Failure
----------------------------
The runner writes a checkpoint during the run:

```text
data/pdp/discovery_runs/cdp/chewy/<run_id>/resume_checkpoint.json
```

If Chrome goes white or the run stops, close/restart the CDP Chrome window, confirm `https://www.chewy.com` renders normally again, then run:

```powershell
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food `
  --resume
```

`--resume` picks the latest Chewy run directory under `data/pdp/discovery_runs/cdp/chewy/` that contains `resume_checkpoint.json`.

If you need to resume a specific run instead of the latest checkpoint, use:

```powershell
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food `
  --resume-run-dir data\pdp\discovery_runs\cdp\chewy\<run_id>
```

Resume skips completed sort/filter surfaces. If the browser fails halfway through a surface, that one surface is rerun; completed surfaces are not rerun.

Correct Operational Interpretation
----------------------------------
If the Chewy tab is white, the run is blocked before discovery starts. The scraper cannot recover by scrolling, changing selectors, or increasing page limits.

If the product grid is visible in Chrome before capture, the scraper can collect PDP links from that loaded DOM.

Operational Flow
----------------
Use the Chewy default command above. It keeps one invocation of `run_retailer_listing_discovery_cdp.py`, auto-loads each category/page/filter URL in the visible Chrome window, sets the Chewy sort widget for ranked category surfaces, captures the loaded tab without CDP navigation, and writes one normal discovery output directory plus one normal `links.json` update.

This is different from running separate discovery commands and combining outputs. The desired behavior is still one discovery run, with address-bar loading used only as the navigation mechanism for Chewy.

Optional email notification:

```powershell
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food `
  --manual-navigation-notify
```

`--manual-navigation-notify` uses the existing PDP run notification configuration; if email credentials are not configured, the run logs a warning and continues.

To disable Chewy auto-paste and try normal CDP navigation anyway:

```powershell
python scripts\run_retailer_listing_discovery_cdp.py `
  --retailer chewy `
  --categories wet_cat_food `
  --no-manual-navigation-auto-paste
```

This is expected to fail on blocked Chewy profiles, but the override is available for debugging.

Diagnostics
-----------
Chewy KPSDK failures should be classified as `kasada_kpsdk_challenge` in CDP failure bundles. A failure bundle usually contains:
- `diagnosis.json`
- `page.html`
- `page.png`

Look under:

```text
data/pdp/discovery_runs/cdp/chewy/<run_id>/failure_bundles/
```

If `page.html` contains `window.KPSDK`, `KP_UIDz`, or `ips.js`, the captured page is the challenge shell and does not contain scrapeable listing content.

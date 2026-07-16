CDP Fetch PDP
=============

Script: `python scripts/cdp_fetch_pdp.py`

Purpose
- Fetch PDP pages via an attached Chrome (CDP/Playwright) and parse them using existing retailer profiles/adapters.

What it does
- Connects to a running Chrome (`--remote-url`, default `http://localhost:9222`), loads PDP URLs (from `links.json` or a single URL), captures HTML, parses with `PDPParser` and retailer adapters (Sephora, Ulta, Amazon, Chewy, Kiko), and writes results to the PDP store/evidence storage. Can optionally download variant images.
- If the attached Chrome context closes unexpectedly, attempts a CDP reconnect and retries once.

Key options (subset)
- `--remote-url`: Chrome DevTools endpoint.
- `--retailer` (required): retailer name (sephora, ulta, amazon, chewy, kiko).
- `--url`: Single PDP URL (test mode).
- `--categories`: Category slugs to include (profile names without retailer_ prefix). Defaults to all profiles for the retailer.
- `--links-path`: JSON of links (retailer -> category -> URLs) for batch mode (default `data/pdp/links.json`).
- `--max-per-run`: Cap number of PDPs to fetch (0 = no cap).
- `--wait-ms`, `--timeout-ms`: delays/timeouts for navigation.
- `--rescrape-existing`: force re-scrape for URLs already present in storage.
- `--download-images`: (if present in script; check `--help`) download variant images.

Usage
```bash
python scripts/cdp_fetch_pdp.py --remote-url http://localhost:9222 \
  --retailer ulta --categories lipstick --max-per-run 20
```

Notes
- Requires Chrome started with `--remote-debugging-port=9222` and Playwright installed.
- Uses existing retailer profiles/adapters; when `PDP_DATABASE_URL` is configured, rows are read from and written to Postgres by default.
- Amazon runs skip URLs whose ASIN is already present in the PDP store by default. Use `--rescrape-existing` to disable that resume behavior.
- Chewy PDPs return a KPSDK/Kasada 429 shell to plain HTTP, so use this CDP runner rather than the static requests parser unless you already have browser-cleared cookies.
- For `--retailer chewy`, the fetcher now mirrors discovery: it defaults to address-bar auto-paste navigation in the visible Chrome window and verifies the requested PDP URL via CDP before capture. This avoids the white-page behavior that plain CDP `goto(...)` often triggers on Chewy.
- Use Chewy category key `wet_cat_food` for wet cat food.
- When the Chewy run is forced onto plain CDP navigation (`--no-manual-navigation-auto-paste`, including non-Windows runs), the fetcher now uses a Chewy-specific `domcontentloaded` wait with a shorter default `--timeout-ms 20000` instead of waiting for full `networkidle`. Chewy often never goes truly idle, so this fallback is much faster than the generic path.
- For `--retailer chewy`, the runner now also uses slower default pacing: `--request-pause-seconds 15`, plus an automatic batch cooldown every 30 saved PDPs for 180 seconds. This is meant to reduce mid-run `429` blocks without manual babysitting.
- For `--retailer chewy`, do not start from a fresh blank/untrusted profile and expect the runner to establish trust by itself. Open `chewy.com` manually in the same attached Chrome session/profile first, confirm it renders normally there, then let the runner reuse that live Chewy tab for PDP navigation.
- If a Chewy PDP still resolves to a white/blank shell (`blank_html_shell`) or a Kasada shell (`kasada_challenge`) after the built-in retries, the capture step raises a fatal invalid-page error for that URL, but the outer Chewy batch loop now records the PDP as a failure, skips it, and continues with the remaining queue. In other words: a bad Chewy PDP no longer has to kill the whole run.
- During a long Chewy run, the visible browser can remain on a white page for the current PDP while the runner retries, reconnects CDP, or decides to skip that URL. That is normal as long as the scraper log is still advancing. Treat "white browser + no new log activity beyond the expected 15-second pacing / 3-minute batch cooldown" as the real stuck signal.
- The Chewy auto-paste path requires a visible Chrome window and Windows Python because it uses UI Automation / `SendKeys` against the Chrome address bar.
- A wet cat food smoke run can use:
```bash
PYTHONPATH=$PWD python scripts/cdp_fetch_pdp.py \
  --remote-url "http://127.0.0.1:9222" \
  --retailer chewy \
  --categories wet_cat_food \
  --max-per-run 5 \
  --wait-ms 10000 \
  --timeout-ms 60000 \
  --request-pause-seconds 8
```

Chewy Windows Trusted-Profile Runbook
-------------------------------------

Use this exact flow when Chewy works in your normal Chrome profile but a fresh CDP profile goes white.

Why:
- Chrome no longer exposes CDP on the default live Chrome data directory.
- A fresh CDP profile usually does not carry enough Chewy trust/session state.
- The practical workaround is to clone the working Chrome profile into a separate directory, then attach CDP to that clone.

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

6) Run a one-URL or one-item smoke test
```powershell
cd C:\path\to\app_files
$env:PYTHONPATH = (Get-Location).Path
python scripts\cdp_fetch_pdp.py --retailer chewy --categories wet_cat_food --max-per-run 1 --rescrape-existing
```

Notes:
- If the run logs `Skipping ... already present in the PDP store`, add `--rescrape-existing` for the smoke test.
- Keep the seeded Chewy tab open while the run is active.
- If `Invoke-WebRequest http://127.0.0.1:9222/json/version` fails, the scraper cannot attach to Chrome yet.
- You can override the Chewy pacing if needed, for example:
```powershell
python scripts\cdp_fetch_pdp.py --retailer chewy --categories wet_cat_food `
  --request-pause-seconds 15 `
  --batch-pause-every 30 `
  --batch-pause-seconds 180
```

Server runbook (no GUI session)
-------------------------------

Use this when the server has no desktop (`tty`) and you want a persistent virtual display.

1) Install Google Chrome once
```bash
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get update
sudo apt-get install -y ./google-chrome-stable_current_amd64.deb
```

2) Start virtual display + Google Chrome CDP once
```bash
mkdir -p logs

CHROME_BIN="$(command -v google-chrome || command -v google-chrome-stable)"

nohup /usr/bin/Xvfb :99 -screen 0 1920x1080x24 \
  > logs/xvfb.log 2>&1 < /dev/null &

DISPLAY=:99 nohup "$CHROME_BIN" \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-pdp \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --no-sandbox \
  > logs/chrome_cdp.log 2>&1 < /dev/null &
```

3) Verify CDP is reachable
```bash
curl -s http://127.0.0.1:9222/json/version
```

4) Run a category fetch
```bash
PYTHONPATH=$PWD python scripts/cdp_fetch_pdp.py \
  --remote-url "http://127.0.0.1:9222" \
  --retailer amazon \
  --categories lipstick \
  --wait-ms 8000 \
  --timeout-ms 60000
```

Tomorrow / next category
------------------------

You do not need to restart everything if CDP is still up.

1) Check CDP first
```bash
curl -s http://127.0.0.1:9222/json/version
```

2) If CDP is down, restart `Xvfb` + Google Chrome with the commands above.

3) Launch the next category
```bash
PYTHONPATH=$PWD python scripts/cdp_fetch_pdp.py \
  --remote-url "http://127.0.0.1:9222" \
  --retailer amazon \
  --categories concealer \
  --wait-ms 8000 \
  --timeout-ms 60000
```

Notes
- `--categories` accepts one or more category slugs separated by spaces, for example `--categories lipstick concealer`.
- To keep a long run after disconnect: run with `nohup ... &` or inside `screen`/`tmux`.

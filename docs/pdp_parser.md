# PDP Parser Overview

This guide explains what the Ulta lipstick parser does, how the profile/adapter
pieces fit together, and which entry points developers can use to run it from
the CLI or the legacy UI (deprecated/optional).

## Responsibilities

- Discover Ulta PDP URLs (category pagination, optional sitemap/search hooks).
- Fetch PDP HTML with polite rate limits and capture headers/timestamps.
- Extract JSON-LD, Apollo state, and DOM fallbacks to build evidence blobs.
- Parse retailer-native identifiers, parent metadata, and variant records using
  JSON-path instructions defined in the profile file.
- Apply light-touch normalization (trim, collapse spacing, strip trailing shade
  tokens) while preserving raw values.
- Validate required fields (brand/title, numeric prices, minimum variant count)
  and surface QA flags for downstream review.
- Persist structured parents/variants plus raw HTML/JSON evidence artefacts.
- Emit summary counters (parsed, failed, warnings/errors) to help triage gaps.

The parser never invents IDs, bypasses anti-bot measures, or joins to external
taxonomies. Cross-retailer matching, chemistry enrichment, and shade-color
derivation are handled downstream.

## Architecture

```
config/pdp_profiles/ulta_lipstick.json   # Profile-driven field paths & heuristics
modules/pdp/profile_loader.py            # Typed loader + validation helpers
modules/pdp/engine.py                    # Generic fetch -> parse -> validate pipeline
modules/pdp/adapters/ulta.py             # Thin Ulta-specific overrides/fallbacks
modules/pdp/storage.py                   # Evidence persistence (HTML/JSON)
modules/pdp/store adapter                # PDP store adapter for normalized rows
scripts/run_pdp_parser.py                # CLI helper for developers
tests/modules/pdp/                       # Targeted unit + fixture-based tests
```

The generic engine reads profile instructions to extract values with JSON paths.
Retailer adapters stay lean - Ulta's implementation adds DOM fallbacks, GraphQL
normalisation, and parent/variant fix-ups when the primary blobs shift.

## Profiles and Adapters

- **Profile (`config/pdp_profiles/ulta_lipstick.json`)**: Defines ID extraction,
  variant paths, normalization toggles, and validation thresholds.
- **Adapter (`modules/pdp/adapters/ulta.py`)**: Supplies URL regex helpers,
  extra blob sources, and retailer-specific tweaks (kit detection, GraphQL
  enrichment, variant dedupe).
- **Adapter (`modules/pdp/adapters/sephora.py`)**: Handles Nuxt payloads and
  merges JSON-LD data for Sephora PDPs.
- **Adapter (`modules/pdp/adapters/kiko.py`)**: Extracts Next.js state for KIKO
  Milano PDPs, normalising variants sourced from the `__NEXT_DATA__` script.
  Profiles currently ship for concealer, highlighter, bronzer, palette, mascara,
  eyeshadow, eyeliner, eyebrow, lip gloss, lipstick, blush, and foundation.

To add new retailers, copy the JSON profile template and implement a minimal
adapter that mirrors Ulta's structure.

## CLI Usage

Use the bundled helper to parse URLs outside the legacy UI:

```bash
python scripts/run_pdp_parser.py \
  --retailer ulta \
  --categories lipstick foundation
```

Key flags:

- `--retailer` / `--categories` - auto-discover PDPs by retailer/profile (defaults to every Ulta profile when categories are omitted).
- `--profile` / `--urls` - fall back to explicit profile + URL lists.
- `--urls-file path/to/urls.txt` - read URLs from a newline-delimited file.
- `--max-pages 20` - cap PLP pagination during discovery.
- `--output-dir data/pdp/my_run` - change the export directory.
- `--overwrite` - reuse stable filenames and replace PDP store rows.
- `--no-evidence` - skip persisting HTML/JSON evidence blobs.
- `--reviews-only` – refresh review metadata only (updates parent `extras`, skips CSV/Parquet exports and image downloads). The CLI still reparses all supplied URLs even without `--overwrite` so review snippets stay current.
- `--locale fr-fr` - substitute `{locale}` placeholders in profile URLs (default: en-us).

Every run writes:

- Normalized parents/variants to the PDP store. With `PDP_DATABASE_URL` configured, this is Postgres by default.
- CSV **and** Parquet exports under `data/pdp/cli/<profile>/`.
- Hero/swatch images saved to `data/pdp/cli/<profile>/images` (or `images-<timestamp>` when not overwriting).
- A `summary*.json` file with validation warnings, errors, and failed URLs.
- A final PDP store summary that reports starting totals, per-profile additions, and the ending totals so you can confirm every category actually persisted rows.

### Review outputs

- Reviews, positive/negative highlights, and provider metadata live in the `extras` JSON column of the `parent_products` table in the PDP store.
- When you run the parser without `--reviews-only`, the exported parents CSV/Parquet files under `data/pdp/cli/<profile>/` include the same JSON in their `extras` column.
- `--reviews-only` skips rewriting those CSV/Parquet exports and image folders, so the refresh is limited to updating the PDP store. Downstream consumers should read reviews from the database.

The UI tab used for analyst runs has been retired; the CLI is now the
supported interface for PDP parsing (UI is deprecated/optional).

### Handling geo-blocked retailers (Sephora)

Sephora’s CDN (Akamai) serves different domains by geography.  When the
requests originate from an EU data centre the `.com` PDPs and PLP discovery
usually return **HTTP 403** with a message like “You don’t have permission to
access www.sephora.de”.  The parser is working; the request is simply being
rerouted before we can parse it.

Options:

1. **Run from an allowed network** – e.g. your local laptop if it already opens
   `https://www.sephora.com` without the “wrong country” page.
2. **Route the CLI through a US proxy/VPN.**  The fetcher now honours the
   following environment variables (checked in this order):
   - `PDP_<RETAILER>_PROXY` – use for both HTTP/HTTPS (e.g. `PDP_SEPHORA_PROXY`)
   - `PDP_<RETAILER>_HTTP_PROXY`, `PDP_<RETAILER>_HTTPS_PROXY`
   - Global fallbacks: `PDP_ALL_PROXY`, `PDP_HTTP_PROXY`, `PDP_HTTPS_PROXY`

   Set one of these to a SOCKS5 or HTTP proxy URL (`socks5://user:pass@host:port`
   or `http://user:pass@host:port`) before running the parser:

   ```bash
   export PDP_SEPHORA_PROXY="socks5://user:pass@us-proxy.example:1080"
   PYTHONPATH=$PWD python scripts/run_pdp_parser.py \
       --retailer sephora --categories bronzer --overwrite
   ```

   Simplest paid option: rent a small US-based VPS (or subscribe to a commercial
   proxy) and expose an authenticated SOCKS/HTTP proxy from it.  Remove the env
   var (`unset PDP_SEPHORA_PROXY`) to fall back to the machine’s native network.

3. **As a diagnosis aid** the CLI now surfaces the first ~400 chars of any 403
   body.  If you see “Access Denied” referencing `sephora.de`, it confirms the
   request still exited from an EU IP.

> **Note:** older Python builds without TLS SNI support emit
> `urllib3.util.ssl_.SNIMissingWarning`. The parser can still run, but upgrading
> Python/OpenSSL (or installing `pip install requests[security]`) is recommended
> so Sephora serves the correct certificate chain.

## Testing

Unit tests cover:

- Profile loading/validation (`tests/modules/pdp/test_profile_loader.py`)
- JSON path helpers (`tests/modules/pdp/test_json_path.py`)
- Normalisation toggles (`tests/modules/pdp/test_normalization.py`)
- Engine fixtures:
  - `tests/modules/pdp/test_engine.py` (Ulta + Sephora captured HTML snapshots)
  - `tests/modules/pdp/test_kiko_parser.py` (KIKO Milano snapshot parsed via the
    new adapter)
- DataFrame/CSV helpers (`tests/modules/pdp/test_service.py`)

Regenerate fixtures when Ulta's markup shifts, then adjust profile paths or
adapter fallbacks to restore passing tests. Keep coverage above 80% via
`pytest --cov=src --cov-report=term-missing`.

Kiko Filter Discovery
=====================

Preferred script: `python scripts/run_retailer_listing_discovery_cdp.py --retailer kiko`

Lower-level script: `python scripts/run_kiko_filter_discovery.py`

Purpose
- Capture Kiko category filters from the embedded Algolia state on Kiko PLPs.
- Persist semantic retailer-filter evidence for use as first-choice Kiko attributes.
- Refreshing the PDP attribute cache applies the latest captured evidence to Kiko parent rows.

Captured semantic filters
- `finishEffect` -> `finish`
- `coverage` -> `coverage`
- `waterproof` -> `water resistance` when the value is `YES`
- `spf` -> `spf` when a concrete SPF value is present

Ignored filters
- `averageRating`
- `prices.*`
- `multicolor`

Usage
```bash
PYTHONPATH=$PWD python scripts/run_retailer_listing_discovery_cdp.py --retailer kiko --categories foundation lip_gloss lipstick
PYTHONPATH=$PWD python scripts/run_retailer_listing_discovery_cdp.py --retailer kiko
```

The generic retailer listing discovery command is the normal path. For Kiko, it:
- expands `{locale}` profile URLs with `--locale` (default `en-us`);
- captures the rendered PLP through CDP like other retailers;
- extracts Kiko semantic filters from the embedded Algolia PLP state;
- queries Algolia for filter memberships because Kiko filters are not URL-backed;
- writes latest Kiko filter evidence for attribute-cache refresh.

Standalone fallback
```bash
PYTHONPATH=$PWD python scripts/run_kiko_filter_discovery.py --categories foundation lip_gloss lipstick
PYTHONPATH=$PWD python scripts/run_kiko_filter_discovery.py
```

Outputs
- Generic run artifact: `data/pdp/discovery_runs/cdp/kiko/<timestamp>/`
- Standalone run artifact: `data/pdp/discovery_runs/kiko_filters/<timestamp>/`
- Latest evidence: `data/pdp/retailer_filter_evidence/kiko/filter_observations.parquet`
- Latest surfaces: `data/pdp/retailer_filter_evidence/kiko/filter_surfaces.parquet`

Cache application
- `modules.pdp.attribute_cache_refresh.refresh_pdp_attribute_cache_from_postfill`
  reads the latest evidence and overlays it during Kiko cache refresh.
- Overridden values keep the previous mapped value in `our_<attribute>`.
- Kiko filter values are written to `kiko_filter_<attribute>`.
- `<attribute>_authority_source` is set to `kiko_filter`.

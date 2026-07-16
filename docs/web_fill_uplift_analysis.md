Web Fill Uplift Analysis
========================

Purpose
-------
Legacy note: the normal PDP attribute pipeline now persists web/VLM audit rows
to the PDP database instead of writing `attribute_web_fill_audit.csv`.

Quantify how much the brand-site web-search LLM step improves attribute coverage by measuring:
- how many attribute cells were missing before the web step,
- how many were filled by accepted web answers,
- how many remained missing after that step.

This is the direct KPI for "is web-search worth it?".

Inputs
------
- Legacy flat-file audit: `data/pdp/attribute_mapping/attribute_web_fill_audit.csv`.
- Current runs do not produce this file by default.

CLI
---
```bash
PYTHONPATH=$PWD python scripts/analyze_web_fill_uplift.py --top 40
```

Optional args:
- `--audit-csv <path>`: alternate audit input path.
- `--out-csv <path>`: output summary CSV path.
- `--top <N>`: print top `N` rows by `filled_count`.

Output
------
- Summary CSV:
  - `data/pdp/attribute_mapping/attribute_web_fill_uplift_summary.csv`
- Summary columns:
  - `scope`: `parent` or `variant`
  - `category_key`
  - `attribute_id`
  - `before_missing_count`
  - `filled_count`
  - `after_missing_count`
  - `fill_rate`
  - `fill_rate_pct`

Metric Definitions
------------------
- `before_missing_count`
  - Count of requested attribute cells in web prompts.
  - Parent scope: from `requested_parent_attributes`.
  - Variant scope: from `requested_variant_attributes`.
- `filled_count`
  - Requested cells that were actually filled by web and accepted by pipeline rules.
  - Parent scope: from `filled_parent_attributes`.
  - Variant scope: from `filled_variant_attributes`.
- `after_missing_count = before_missing_count - filled_count`
- `fill_rate_pct = filled_count / before_missing_count * 100`

Interpretation
--------------
- This KPI measures uplift on web-attempted missing cells only.
- It does not include cells never requested by web.
- It does not measure downstream sales impact directly; it measures coverage gain.

Example (server run)
--------------------
- `before_missing`: `34055`
- `filled`: `4490`
- `after_missing`: `29565`
- `overall fill rate`: `13.18%`

Scope split:
- `parent`: `2921 / 14274` (`20.46%`)
- `variant`: `1569 / 19781` (`7.93%`)

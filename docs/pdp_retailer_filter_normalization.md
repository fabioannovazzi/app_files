# PDP Retailer Filter Normalization

Use this step after retailer listing discovery has captured filter observations and
before running PDP attribute mapping or review-theme processing.

Retailer filters are raw evidence. The pipeline preserves them in
`retailer_filter_observations`, then materializes a normalized view into
`pdp_attribute_values` with `source='retailer_filter'`.
When a retailer filter is not semantically compatible with the category
taxonomy, the normalization step should skip it in `pdp_attribute_values` and
leave it only in raw observations.

## Why This Step Exists

Retailers often expose the same concept with different names:

- Amazon may say `life stage`; the wet-cat-food taxonomy uses `lifestage`.
- Amazon and Chewy may both express `packaging type`, but with different value
  casing or plurals.
- Some retailer filters are not taxonomy attributes. For example, an Amazon
  nutrient claim may need to map into `special_diet`, while raw observations
  should remain unchanged for auditability.

Before running `scripts/export_pdp_attributes.py`, normalize the materialized
filter attributes so downstream mapping sees canonical taxonomy IDs and stable
value tokens.

## Command

```bash
source .venv/bin/activate
python scripts/normalize_retailer_filter_attributes.py \
  --retailer amazon \
  --category wet_cat_food
```

By default the command replaces only existing `source='retailer_filter'` rows
for the requested retailer/category scope. It does not delete raw
`retailer_filter_observations`.

Use `--append-only` only for diagnostics where stale display-label rows should
be preserved temporarily.

The command also logs taxonomy gaps after materialization. A gap means the
filter family/value was normalized, but the resulting value is still not an
allowed node for that category. Treat those warnings as a taxonomy/governance
review queue before relying on the filter layer for mapping coverage.

## Recommended Sequence

1. Run listing/filter discovery.
2. Run `scripts/normalize_retailer_filter_attributes.py` for the
   retailer/category.
3. Review any taxonomy-gap warnings from the normalization command.
4. Spot-check `pdp_attribute_values` for canonical taxonomy IDs such as
   `food_texture`, `lifestage`, `special_diet`, `package_count`, and
   `packaging_type`.
5. Run `scripts/export_pdp_attributes.py` for deterministic and optional VLM
   attribute mapping.
6. Run `scripts/build_pdp_review_themes.py` after PDP reviews are present.

## Interpretation

The normalized filter layer is high-confidence but incomplete. A missing
retailer-filter value means "not observed on a filter surface", not "false".
The PDP attribute mapper remains responsible for broader coverage from PDP
text, images, and web evidence.

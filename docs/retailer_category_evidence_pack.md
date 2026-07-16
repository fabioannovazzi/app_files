Retailer Category Evidence Pack
===============================

This document defines the main cohort semantics used by
`scripts/build_retailer_category_evidence_pack.py`.

Top-seller cohort
-----------------

`top_seller` means the product appears in Pareto bucket `A`, derived from the
retailer's top-seller, best-seller, or equivalent popularity sort when that
sort surface is observed.

The top-seller threshold is based on the full discovered category universe, not
only the number of products captured on the ranked top-seller surface:

```text
observed_top_seller_limit =
  min(top_seller_captured_ranked_products, ceil(listing_products * 0.20))
```

Where:

- `listing_products` is the full product universe for the retailer/category
  package.
- `top_seller_captured_ranked_products` is the count of distinct products
  observed on the top-seller ranked surface.
- `0.20` is the fixed top-seller cohort share.

Example: if a category has 578 products and discovery captured 96 products on
the top-seller surface, the theoretical 20% universe cutoff is
`ceil(578 * 0.20) = 116`, but the observed top-seller limit is
`min(96, 116) = 96`.

If a future discovery captures 576 ranked top-seller products for the same
578-product universe, the observed top-seller limit becomes
`min(576, 116) = 116`.

This avoids defining "top 20%" as 20% of a short captured ranked window. The
short ranked window caps what can be observed; it does not become the
denominator.

Sale-pressure cohort
--------------------

`sale_pressure` means the product appears in a sale-first, promotion-first, or
equivalent ranked sort surface when the retailer exposes one and discovery
captures it.

This is a promotion-exposure proxy only. Presence in the sale-pressure files
means the product was observed in that ranked sale/promotional window. Absence
does not prove that the product was not discounted, because discovery may only
capture part of the ranked window and some retailers do not expose a comparable
sale-first sort.

Package metadata
----------------

`package_integrity.json` records the deterministic source-to-package audit for
the generated package. It checks product identity/cohort table consistency and
recomputes top-seller, innovation, and sale-pressure signal rows from the final
`product_filter_matrix.csv` inputs. If this audit fails, repair the package
before using generated report text validation.

`summary.json` mirrors the package integrity status and records the fields
needed to audit these definitions:

- `listing_products`
- `package_integrity`
- `package_integrity_failures`
- `package_integrity_warnings`
- `top_seller_threshold_share`
- `top_seller_captured_ranked_products`
- `top_seller_universe_cutoff`
- `top_seller_observed_cohort_limit`
- `top_seller_cutoff_formula`
- `top_seller_capture_capped_by_observed_window`
- `sale_pressure_available`
- `sale_pressure_sort_mode`
- `sale_pressure_capture_scope`
- `sale_pressure_absence_interpretation`

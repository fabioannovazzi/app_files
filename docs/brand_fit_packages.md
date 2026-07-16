Brand Fit Packages
==================

Purpose
-------

Brand Fit packages sit between Retailer Signals and Product Hypotheses.

The pipeline is:

1. Retailer Signals: analyze one retailer/category shelf, such as `blush ulta`.
2. Brand Fit: compare that retailer/category signal with one brand catalog, such
   as KIKO blush.
3. Product Hypotheses: use the Brand Fit evidence to draft product routes.

Required inputs
---------------

A Brand Fit package must have both a retailer signal source and brand catalog
data:

- A completed retailer-signal package for the same retailer/category.
- The corresponding retailer-signal brief markdown, copied into the package as
  `source_innovation_brief.md`.
- Mapped brand catalog data for the brand/source retailer in the PDP database.
- At least one brand catalog product after applying the requested category or
  owned-category aliases.

The brief is not optional analytical context. It is the category interpretation
layer that explains what the raw signal tables mean, which signals are robust,
which signals are fragile, and which apparent matches should not be over-read.

Raw tables alone are not sufficient. Do not generate or use a Brand Fit package
from `signal_bundles.csv`, PDP rows, or computed bundle tables if the source
retailer-signal brief does not exist.

Brand data is also not optional. If the PDP database has no mapped brand catalog
rows, or if the category filter leaves no brand products, the builder fails
before writing a Brand Fit package.

Package integrity
-----------------

A Brand Fit package must validate its own source-to-package consistency before
any generated report can be trusted. Report validation checks whether final
report text matches the package; it does not prove that the package tables are
complete or correctly wired.

The builder writes `package_integrity.json` and mirrors its status in
`summary.json`. The audit checks that current-retailer anchor attributes
preserve mapped source evidence, that anchor bundle matches recompute from the
final anchor rows, and that `retailer_brand_anchor_signal_fit.csv` is consistent
with `brand_at_retailer_bundle_matches.csv`.

If package integrity fails, repair the package inputs or builder logic before
sending the package to Pro or validating report text.

Rank-weighted visibility metrics
--------------------------------

Brand Fit consumes the `rank_weighted_*` columns already attached to
`top_seller_pairs.csv`, `top_seller_triples.csv`, `innovation_pairs.csv`, and
`innovation_triples.csv` by the Retailer Signals package. It does not read
`web_shelf_selected_shelves.csv` or `web_shelf_robustness_summary.csv` directly;
those files are audit inputs for the upstream retailer/category package only.

These metrics should not create a separate signal family. Gross visibility says
how much rank-weighted shelf mass a bundle carries before overlap removal.
Incremental visibility says how much additional ranked shelf mass it explains
after earlier selected bundles have claimed their products. Neither metric
should be described as sell-out demand, sales, or shopper path attribution.

Review availability
-------------------

Review validation is retailer-dependent evidence, not a mandatory package
input. Some retailers or categories do not expose ratings, review counts, or
review text in the scraped PDP/category evidence. Saks Fifth Avenue cashmere
sweaters and low-top sneakers are examples where current pages do not expose
usable reviews.

When review files such as `bundle_review_validation.csv` or
`top_seller_review_validation.csv` are empty, treat this as "review evidence not
available" rather than a package failure or negative consumer signal. Reports
may still use shelf position, filters, PDP copy, images, price, and brand spread
as evidence, but they must explicitly say that consumer-review validation is not
available.

Non-example: eye categories
---------------------------

If the Retailer Signals page has no eye-category report, then there is no valid
Brand Fit source for:

- `eyeshadow`
- `eyebrow`
- `mascara`
- `eyeliner`

Even if PDP discovery data exists or a script can compute bundle tables, those
categories must be excluded until a proper retailer-signal report and brief have
been produced.

Builder behavior
----------------

`scripts/build_brand_retailer_reference_package.py` enforces this boundary. It
fails when the source retailer-signal brief is missing, when mapped brand parent
data is missing, or when the selected category has no brand catalog products.

Example:

```bash
PYTHONPATH=$PWD ./.venv/bin/python scripts/build_brand_retailer_reference_package.py \
  --brand-source-retailer kiko \
  --brand-name "KIKO Milano" \
  --retailer ulta \
  --category blush
```

For this to be valid, the matching source files must exist, including:

- `data/pdp/reports/packages/launch/blush/ulta/`
- `data/pdp/reports/briefs/launch/blush/ulta.md`

If the brief is missing, create the Retailer Signals report first. Do not bypass
the check by pointing the builder at raw computed package tables.

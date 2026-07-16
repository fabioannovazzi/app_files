# Ulta Discovery V2

Status: Draft (as of 2026-04-19).

## 1. Purpose

This document defines the next Ulta discovery design.

The goal is not to make the crawler more elegant. The goal is to make it more
useful.

The new design is coverage-first. It treats Ulta listing surfaces as data:
category listings, sort order, and selected filter memberships. PDP scraping
remains incremental and mostly unchanged.

## 2. Why Change

The current Ulta discovery approach is too profile-first and too brittle for the
next set of questions we want to answer.

The new requirements are:

1. capture all products in the tracked Ulta categories
2. identify `new` versus `old` without using sales data
3. compare our attribute mapping against Ulta's own classification
4. measure how often Ulta assigns multiple values in the same attribute family
5. focus on coverage, not commercial mapping

Recent debugging showed three concrete issues in the current state:

1. a real pagination bug in
   [discovery.py](../../modules/pdp/discovery.py)
   caused some later Ulta pages to be skipped
2. some live products fall into categories that are outside the current tracked
   profile set
3. local Ulta data is stale, so coverage gaps are a mix of logic gaps and age

The pagination issue is already fixed and covered by
[test_discovery.py](../../tests/modules/pdp/test_discovery.py).

## 3. Objectives In Order

### 3.1 Coverage

Capture all products in the tracked Ulta categories.

Today the tracked Ulta profile set is:

1. `blush`
2. `bronzer`
3. `bb_cc_creams`
4. `color_correct`
5. `concealer`
6. `contour`
7. `eyebrow`
8. `eyeliner`
9. `eyeshadow`
10. `face_primer`
11. `foundation`
12. `highlighter`
13. `lip_gloss`
14. `lip_oil`
15. `lipstick`
16. `mascara`
17. `setting_spray_powder`
18. `tinted_moisturizer`

`makeup_remover` remains out of scope even though Ulta exposes it from the face
surface because it is operationally a skincare cleansing bucket, not a face
makeup category.

If this set is narrowed later, the discovery design does not change.

Extra Kiko categories that are outside this tracked set today, such as lip balm,
lip liner, lip scrub, and lip stain, are not discovery failures in V2 unless we
explicitly decide to expand scope.

### 3.2 New Versus Old

Infer a retailer-native freshness signal without using the sales dataset.

### 3.3 Attribute Audit

Use Ulta listing/filter evidence to compare our mapping against Ulta while
keeping the current one-value BI logic for now.

### 3.4 Double Matching

Measure how common multi-value membership is inside the same Ulta filter family.

This is especially important because one-value BI may be acceptable for some
families and too lossy for others.

### 3.5 Explicit Non-Goal

Commercial mapping is out of scope.

We do not care about `Only at Ulta`, `online only`, price bands, special
offers, or similar merchandising labels.

## 4. Design Principles

### 4.1 Separate Listing Discovery From PDP Scraping

Listing discovery and PDP scraping are different jobs.

Listing discovery should run broadly and frequently.

PDP scraping should remain incremental:

1. if a discovered product is already in our first scrape, do not fetch the PDP
   again by default
2. record fresh listing observations anyway
3. fetch PDPs only for unseen products unless an explicit refresh mode is
   requested later

### 4.2 Coverage First

Filters are evidence. They are not the primary discovery mechanism.

The primary discovery mechanism should be the tracked category listings.

### 4.3 Ulta Evidence First, Our Taxonomy Second

The discovery layer should record what Ulta exposed, not what we think Ulta
meant.

Normalization and comparison to our taxonomy should happen later.

### 4.4 No Manual Labeling Workflow

The first version should be deterministic and simple.

We already know enough from a few category pages to identify which filter
families are useful and which ones should be ignored.

## 5. Discovery Surfaces

### 5.1 Primary Surfaces

For each tracked category:

1. crawl the base category listing
2. crawl all listing pages
3. crawl at least two sort modes:
   1. `default`
   2. `new_arrivals`

These surfaces give us:

1. product coverage
2. category context
3. page position
4. default-sort prominence
5. `new_arrivals` ordering

### 5.2 Secondary Surfaces

Selected attribute filter states should also be observed, but only for
attribute-like families.

Examples:

1. `finish=high+shine`
2. `form=liquid`
3. `coverage=full`

These surfaces are not for timing. They are for retailer-side classification
evidence.

### 5.3 Brand Pages

Brand pages such as `https://www.ulta.com/brand/kiko-milano` are useful for
targeted audits, but they should not be the primary discovery backbone for the
whole catalog.

They are best treated as brand-specific evidence layers.

### 5.4 Sitemap

Yes, sitemap should be used, but only as a secondary signal.

Useful sitemap sources:

1. `https://www.ulta.com/sitemap/p.xml`
2. `https://www.ulta.com/l/category_filter_sitemap.xml`
3. `https://www.ulta.com/l/brand_filter_sitemap.xml`

Sitemap is good for:

1. URL discovery
2. completeness backstop
3. filter URL enumeration
4. `lastmod` when available

Sitemap is not good for:

1. product rank
2. page position
3. launch timing
4. default-sort prominence
5. `new_arrivals` order

So the rule is:

1. category listings are primary
2. sitemap is a backstop and enumerator

## 6. Attribute-Like Filter Families

We do not need a global ontology up front.

We do need a practical initial allowlist of Ulta filter families that are worth
capturing as retailer-side evidence.

Initial families to keep when present:

1. `finish`
2. `form`
3. `coverage`
4. `color lips`
5. `color eyes`
6. `benefit`
7. `mascara type`
8. `waterproof`
9. `SPF`
10. `skin type`

Initial families to ignore:

1. `brand`
2. `category`
3. `price`
4. `special offer`
5. `shopping preference`
6. `page`
7. `sku`
8. `ref_src`

`preference` should not be treated as a core taxonomy family in V1. It is a
claims-like surface and can be saved separately later if needed.

## 7. Data To Persist

The discovery redesign needs persistent observation tables.

This is required for verification and for the `new` versus `old` logic.

### 7.1 Listing Observations

Proposed table: `ulta_listing_observations`

Suggested fields:

1. `crawl_ts`
2. `category_key`
3. `source_surface`
4. `sort_mode`
5. `page`
6. `position`
7. `pdp_url`
8. `parent_product_id`
9. `product_name`
10. `brand`

### 7.2 Filter Observations

Proposed table: `ulta_filter_observations`

Suggested fields:

1. `crawl_ts`
2. `category_key`
3. `filter_family`
4. `filter_value`
5. `pdp_url`
6. `parent_product_id`
7. `source_surface`

### 7.3 Optional Sitemap Observations

Proposed table: `ulta_sitemap_observations`

Suggested fields:

1. `crawl_ts`
2. `sitemap_source`
3. `url`
4. `lastmod`
5. `url_type`

This is optional in V1 but useful if we want explicit sitemap gap analysis.

## 8. New Versus Old: Empirical Heuristic

We should not invent a fake launch date.

What we can do is assign an empirical freshness status from listing history.

These labels are inferred, not verified. We should name them plainly and avoid
pretending we have stronger proof than we do.

### 8.1 Base Rule

1. `old`: product was seen in any prior crawl
2. `first_seen_now`: product was not seen in any prior crawl

### 8.2 Newness Rule From `new_arrivals`

The first useful rule is the one already proposed:

If a first-seen product appears in `new_arrivals` and there are no previously
known products ranked before it in that listing, treat it as genuinely new.

If a first-seen product appears in `new_arrivals` but previously known products
already sit ahead of it, treat it as likely missed before.

Operationally:

1. `new`
   1. product is `first_seen_now`
   2. product appears in `new_arrivals`
   3. every product ranked ahead of it in that category listing was also first
      seen in the current crawl
2. `missed_before`
   1. product is `first_seen_now`
   2. product appears in `new_arrivals`
   3. at least one previously known product ranks ahead of it
3. `unclear_first_seen`
   1. product is `first_seen_now`
   2. product was not observed in `new_arrivals`

### 8.3 Role Of Default Sort

Default sort is not a freshness signal.

It is still important because it tells us commercial prominence.

This is useful later to separate:

1. new and already prominent
2. new but not yet prominent
3. old and established

## 9. Attribute Audit Against Ulta

Once listing and filter observations exist, we can compare three things:

1. Ulta filter membership
2. Ulta PDP content
3. our mapped value

For now we keep the one-value BI logic in our own mapping.

The purpose of the Ulta audit is not to replace our taxonomy. It is to
understand why we differ.

The main causes we expect are:

1. our taxonomy is too narrow for Ulta's shopper taxonomy
2. our PDP interpretation is wrong
3. our one-value parent representation is too lossy
4. Ulta's classification is broader or inconsistent
5. the product is variant-heterogeneous and the disagreement is not resolvable
   at parent level

## 10. Double Matching

Double matching should be measured directly.

For each `category_key` and `filter_family`, compute the share of products that
appear in more than one `filter_value`.

This gives a factual answer to where one-value BI is acceptable and where it is
too lossy.

The output should include:

1. total products observed in the family
2. products with exactly one value
3. products with more than one value
4. percentage with more than one value

## 11. Proposed Crawl Flow

### 11.1 Discovery Run

1. iterate tracked Ulta categories
2. crawl `default` listings across all pages
3. crawl `new_arrivals` listings across all pages
4. optionally crawl selected attribute filter states
5. persist listing and filter observations
6. use sitemap as a completeness backstop

### 11.2 PDP Fetch

1. compare discovered products against the existing local catalog
2. fetch PDPs only for unseen products
3. skip PDP refetch for already-known products by default
4. update observation history for both new and existing products

## 12. Immediate Implementation Sequence

### Phase 1

Make listing discovery complete and persistent.

1. keep the fixed Ulta pagination behavior
2. add support for `new_arrivals`
3. persist listing observations
4. persist selected filter observations

### Phase 2

Add the empirical freshness logic.

1. compute `first_seen`
2. compute `new` versus `missed_before`
3. expose run-level summaries

### Phase 3

Add Ulta attribute audit outputs.

1. compare our mapped values to Ulta filter memberships
2. keep one-value BI logic for now
3. measure double matching by category and family

### Phase 4

Use sitemap for completeness reporting.

1. compare sitemap URLs to listing-discovered URLs
2. flag products that exist in sitemap but not in tracked listing observations

## 13. Open Questions

These do not block V1:

1. whether `preference` should later become a claims surface
2. whether brand pages should be captured systematically for a small audit brand
   set
3. whether to add an explicit PDP refresh mode by age or by status

## 14. Recommendation

Proceed with a discovery-first implementation.

Do not redesign PDP scraping yet.

The first version should deliver:

1. better catalog coverage
2. persistent listing history
3. retailer-native `new` versus `old`
4. attribute audit evidence against Ulta
5. measured double matching

That is enough to decide whether the broader Ulta discovery redesign is working.

# Ulta Discovery V2 Checklist

Status: Draft implementation checklist (as of 2026-04-19).

Companion spec:
[ulta-discovery-v2.md](../../docs/specs/ulta-discovery-v2.md)

## 1. Scope

This checklist is for Ulta only.

Sephora discovery stays unchanged for now.

Reason:

1. Ulta is the retailer where we want to improve coverage, derive empirical
   `new` versus `old`, and compare our mapping against retailer-side filters
2. changing Sephora at the same time would mix two different problems and make
   validation much harder

## 2. Success Criteria

The first usable version should let us:

1. crawl the tracked Ulta categories completely enough to close obvious catalog
   gaps
2. persist listing observations across runs
3. identify `first_seen_now`, `new`, and `missed_before`
4. compare our mapped parent values against Ulta filter memberships
5. measure double matching by category and filter family

## 3. Phase 1: Complete Listing Discovery

### 3.1 Keep And Validate Current Pagination Fix

1. keep the Ulta pagination fix already added in
   [discovery.py](../../modules/pdp/discovery.py)
2. keep the regression coverage in
   [test_discovery.py](../../tests/modules/pdp/test_discovery.py)
3. add one end-to-end smoke check for a category known to require page 2 or
   later, such as Ulta lip oil

### 3.2 Add `new_arrivals` Support

1. update Ulta listing discovery so each tracked category can be crawled in:
   1. default sort
   2. `new_arrivals`
2. persist sort mode on every observed listing row
3. ensure page traversal works under both sorts

### 3.3 Define The Tracked Ulta Category Set Explicitly

1. freeze the current tracked category set for V1
2. include the current face-only additions `bb_cc_creams` and
   `tinted_moisturizer`
3. keep `makeup_remover` out of scope because it is a skincare bucket
4. treat products outside this set as out of scope, not discovery failures
5. do not add extra Kiko-only categories unless we decide to expand scope

### 3.4 Persist Listing Observations

Create or extend a persistent store for `ulta_listing_observations` with:

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

### 3.5 Keep PDP Scraping Incremental

1. if a discovered Ulta PDP already exists locally, do not re-fetch its PDP by
   default
2. always persist fresh listing observations anyway
3. only fetch PDPs for unseen products

## 4. Phase 2: Capture Retailer Filter Evidence

### 4.1 Keep Only Attribute-Like Families

Start with this allowlist when present:

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

Ignore:

1. `brand`
2. `category`
3. `price`
4. `special offer`
5. `shopping preference`
6. `page`
7. `sku`
8. `ref_src`

Leave `preference` out of V1 core mapping.

### 4.2 Persist Filter Observations

Create or extend a persistent store for `ulta_filter_observations` with:

1. `crawl_ts`
2. `category_key`
3. `filter_family`
4. `filter_value`
5. `pdp_url`
6. `parent_product_id`
7. `source_surface`

### 4.3 Decide Discovery Breadth

V1 recommendation:

1. discover products from base category listings under `default` and
   `new_arrivals`
2. capture filter observations only for selected families
3. do not make filter pages the primary discovery backbone

## 5. Phase 3: Add Empirical Newness

### 5.1 Base Status

For every discovered product:

1. `old` if seen in any prior crawl
2. `first_seen_now` if not seen before

### 5.2 Newness Classification

Implement:

1. `new`
   1. first seen in the current crawl
   2. observed in `new_arrivals`
   3. all products ahead of it in the same `new_arrivals` listing are also first
      seen in the current crawl
2. `missed_before`
   1. first seen in the current crawl
   2. observed in `new_arrivals`
   3. at least one product ahead of it was already known
3. `unclear_first_seen`
   1. first seen in the current crawl
   2. not observed in `new_arrivals`

### 5.3 Run Summary

Each Ulta run should report:

1. total products observed
2. newly observed products
3. `new`
4. `missed_before`
5. already known products

## 6. Phase 4: Add Attribute Audit Outputs

### 6.1 Compare Our Mapping To Ulta

For auditable products, compare:

1. our mapped parent-level value
2. Ulta filter memberships
3. Ulta PDP evidence when needed

Keep the current one-value BI logic for our mapping in this phase.

### 6.2 Classify Mismatch Causes

Mismatch causes should be measurable, not anecdotal.

Target buckets:

1. our interpretation is wrong
2. our one-value parent representation is too lossy
3. our taxonomy is too narrow or misaligned
4. Ulta is broader or inconsistent
5. not auditable from listing/filter evidence alone

### 6.3 Measure Double Matching

For each `category_key` and `filter_family`, compute:

1. products with exactly one filter value
2. products with more than one filter value
3. percentage with more than one filter value

## 7. Phase 5: Add Sitemap Backstop

### 7.1 Use Sitemap As A Coverage Check

Use:

1. `https://www.ulta.com/sitemap/p.xml`
2. `https://www.ulta.com/l/category_filter_sitemap.xml`
3. `https://www.ulta.com/l/brand_filter_sitemap.xml`

### 7.2 What Sitemap Should Do

1. help enumerate valid product and filter URLs
2. highlight URLs that exist on Ulta but are missing from tracked listing
   observations
3. support completeness reporting

### 7.3 What Sitemap Should Not Do

1. define `new`
2. replace listing rank
3. replace `new_arrivals`
4. replace default-sort prominence

## 8. Tests

At minimum, add or keep tests for:

1. Ulta pagination beyond page 1
2. Ulta sort handling for `default` and `new_arrivals`
3. listing observation persistence
4. incremental PDP fetch behavior for already-known versus unseen products
5. newness classification from prior observations plus current `new_arrivals`
   rank
6. double-matching computation

## 9. Deferred For Later

These are intentionally out of scope for V1:

1. Sephora discovery redesign
2. global multi-retailer harmonization of discovery logic
3. replacing one-value BI with a multi-value model
4. systematic use of brand pages for every brand
5. LLM-based interpretation of filter families
6. scheduled PDP refresh rules by age

## 10. Recommended Build Order

Build in this order:

1. persistent listing observations under `default` and `new_arrivals`
2. delta PDP fetch from discovered products
3. filter observation capture for selected attribute-like families
4. empirical `new` versus `old`
5. mismatch and double-matching reporting
6. sitemap completeness reporting

## 11. Definition Of Done For V1

V1 is done when we can run one Ulta crawl and produce:

1. a persistent observed-product table with listing history
2. a delta set of unseen PDPs to fetch
3. a retailer-native `new` versus `old` classification
4. a filter-membership evidence table
5. a category-by-family double-matching summary
6. a first audit report for one brand such as Kiko

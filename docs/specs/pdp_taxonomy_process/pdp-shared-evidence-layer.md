# PDP Shared Evidence Layer

Status: Draft V1 evidence-layer assessment (as of 2026-03-13).

## 1. Purpose
This document defines the shared evidence and indexing layer needed to support:
1. taxonomy candidate generation
2. deterministic-policy candidate generation
3. proposal evidence views
4. candidate ranking and hard gating

It is intentionally practical.

The goal is:
1. identify what data already exists
2. identify what can be derived with limited work
3. identify what is still missing for V1
4. avoid designing candidate generation against data the system does not actually have

## 2. Role In The Overall Design
The shared evidence layer sits below:
1. taxonomy proposals
2. deterministic-policy proposals
3. mapping inconsistency candidates

It is not itself a review UI and not itself a publishable business artifact.

Its purpose is to provide stable, queryable evidence for:
1. candidate generation
2. candidate aggregation
3. candidate ranking
4. proposal detail pages

Companion documents:
1. [pdp-taxonomy-and-deterministic-process-brief.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process-brief.md)
2. [pdp-taxonomy-and-deterministic-process.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process.md)
3. [pdp-taxonomy-and-deterministic-operational-workflow.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-operational-workflow.md)

## 3. Required Evidence Domains
The full shared evidence layer needs at least these domains:
1. taxonomy index
2. product record index
3. source text segment index
4. stage assignment index
5. assignment evidence index
6. product identity index
7. impact index
8. precision and agreement metrics

Not all of these must exist in final form before V1 starts.

## 4. Available Now
These are already present in a usable form.

### 4.1 Taxonomy index
Purpose:
1. canonical lookup of category, attribute, value, hierarchy, and synonyms

Core fields:
1. `category_id`
2. `attribute_id`
3. `value_id`
4. `value_label`
5. `term_text`
6. `term_kind`
   1. `label`
   2. `synonym`
7. `parent_value_id`
8. `depth`

Current source:
1. [taxonomy manifest](../../../config/attribute_taxonomy/manifest.json)

Assessment:
1. this is already the semantic source of truth
2. enough exists now for taxonomy-local candidate generation

### 4.2 Product record index
Purpose:
1. provide product-level rows for examples, product counts, and later candidate evidence

Core fields:
1. `retailer`
2. `row_type`
3. `parent_product_id`
4. `variant_id`
5. `category_key`
6. `brand`
7. `product_name`
8. `pdp_url`
9. `hero_image_url`
10. `variant_name`
11. `variant_description`
12. `pdp_text`

Current sources:
1. review tables loaded in [attribute_review_logic.py](../../../modules/pdp/attribute_review_logic.py)
2. example record flows in [api.py](../../../modules/pdp/api.py)
3. existing evidence display in [coverage.jsx](../../../src/review-react/coverage.jsx)

Assessment:
1. enough exists for example-backed review
2. enough exists for product-count-based ranking in V1

### 4.3 Stage assignment index
Purpose:
1. know what each stage assigned to each product for each attribute

Core fields:
1. `retailer`
2. `row_type`
3. `parent_product_id`
4. `variant_id`
5. `attribute_id`
6. `stage`
   1. `deterministic_explicit`
   2. `deterministic`
   3. `llm`
   4. final overlay when applicable
7. `value`
8. `oov_candidate`
9. `updated_at`

Current sources:
1. stage tables defined in PDP store adapter
2. stage table loading in [attribute_review_logic.py](../../../modules/pdp/attribute_review_logic.py)
3. overlay logic in [api.py](../../../modules/pdp/api.py)

Assessment:
1. enough exists now
2. this is strong enough for V1 deterministic-policy candidates and assignment disagreement analysis

### 4.4 Precision and agreement metrics
Purpose:
1. support deterministic ranking and diagnostics

Core fields:
1. `category_key`
2. `attribute_id`
3. explicit positive count
4. deterministic match on explicit
5. LLM match on explicit
6. precision proxies

Current sources:
1. [explicit_precision_metrics.py](../../../modules/add_attributes/explicit_precision_metrics.py)
2. persistence in PDP store adapter

Assessment:
1. already usable as supporting evidence
2. not a blocker for V1

## 5. Derivable Now
These are not yet clean first-class artifacts, but can be derived from existing data without redesigning the whole pipeline.

### 5.1 Assignment evidence index
Purpose:
1. explain why a product got a value

Core fields:
1. product key
2. `attribute_id`
3. `source`
4. `decision_rule`
5. `value`
6. `evidence`
7. `support_runs`
8. `total_runs`
9. `agreement_rate`
10. `certainty_class`
11. `supporting_steps`

Current sources:
1. `pdp_attribute_audit` and helpers in PDP store adapter
2. stage fallback rows
3. resolution ledger and consensus handling in [api.py](../../../modules/pdp/api.py)
4. web/vision fill audit CSV fallback in [api.py](../../../modules/pdp/api.py)

Assessment:
1. the evidence exists
2. it is currently fragmented across audit rows, stage rows, consensus, and CSV fallbacks
3. V1 can derive a unified evidence view from these sources

### 5.2 Impact index
Purpose:
1. rank candidates by affected products
2. later support sales-weighted ranking

Core fields:
1. `category_key`
2. `attribute_id`
3. `value`
4. `product_count`
5. optional `sales_weight`

Current sources:
1. review tables
2. stage tables
3. sales joins for later phases

Assessment:
1. product-count impact is derivable now
2. sales-weighted impact can wait

### 5.3 Coverage evidence view
Purpose:
1. provide a temporary manual evidence surface before the full proposal system exists

Current sources:
1. taxonomy values and synonyms shown in [coverage.jsx](../../../src/review-react/coverage.jsx)
2. deterministic scan shown in [coverage.jsx](../../../src/review-react/coverage.jsx)
3. example records and attached audit shown in [coverage.jsx](../../../src/review-react/coverage.jsx)

Assessment:
1. this is not the final workflow
2. but it is already usable as an evidence surface for early manual review

## 6. Missing For V1
These are the two main gaps if V1 is expected to support full candidate generation rather than only manual and taxonomy-local review.

### 6.1 Source text segment index
Purpose:
1. store source-aware PDP text segments
2. support source-aware candidate generation
3. support recurring unmapped phrase detection
4. support deterministic-expression candidates

Required fields:
1. `retailer`
2. `parent_product_id`
3. `variant_id`
4. `row_type`
5. `source_channel`
6. `segment_id`
7. `segment_text`
8. `normalized_text`

Current status:
1. raw material exists in parsed PDP data and extras
2. no clean normalized segment table or cache exists yet
3. the current coverage UI uses a naive client-side text scan instead

Assessment:
1. this is the main missing index for V1 candidate generation
2. without it, phrase-based candidates remain weak or manual

### 6.2 Product identity index suitable for candidate generation
Purpose:
1. group the same product across retailers
2. support cross-retailer inconsistency candidates
3. support stronger attribute-structure signals

Required fields:
1. `canonical_id`
2. `retailer`
3. `parent_product_id`
4. `variant_id` if needed
5. `category_key`
6. identity confidence

Current status:
1. `canonical_id` exists in parts of the pipeline
2. `canonical_products` storage exists
3. product-family aggregation exists
4. there is not yet a clean review-ready identity layer with confidence and grouping semantics for candidate generation

Assessment:
1. the pieces exist
2. the final index does not
3. this is the second important missing piece

## 7. Phase 2
These are useful but should not block V1.

### 7.1 Sales-weighted impact
Use later for ranking by business importance.

### 7.2 Richer cross-retailer inconsistency scoring
Use later for better automatic clustering and stronger investigation candidates.

### 7.3 Historical trend evidence
Use later to show whether a phrase or inconsistency is growing, shrinking, or stable.

### 7.4 Rich candidate-quality metrics
Confidence models beyond simple thresholds should wait until the basic queue is operational.

## 8. Practical V1 Scope Based On Existing Data
Given the current repo state, V1 should start with candidate types that are already supported well by existing evidence.

### 8.1 Start with
1. taxonomy-local candidates from taxonomy only:
   1. same-term collision
   2. composite value
2. deterministic-policy candidates using stage assignments and audit evidence:
   1. disable bare label
   2. block bad source
   3. add negative pattern when evidence is strong
3. user-created taxonomy proposals
4. manual attribute-structure review supported by the existing coverage evidence surface

### 8.2 Do not start V1 with
1. recurring unmapped phrase candidates as a major automatic stream
2. cross-retailer inconsistency candidates as a major automatic stream

Those depend too much on the missing source segment and product identity indexes.

## 9. Recommended Build Order
To make the evidence layer operational without overbuilding, use this order:

### 9.1 First
1. `taxonomy_terms`
2. `stage_assignments`
3. `assignment_evidence`

### 9.2 Second
4. `pdp_source_segments`

### 9.3 Third
5. `product_identity_groups`

This order matches the real dependencies of candidate generation.

## 10. Immediate Next Step
The next design step should be:
1. define the exact `pdp_source_segments` contract
2. map it onto the current parsed PDP data
3. decide whether it should be materialized in Postgres, cache parquet, or both

That companion is now here:
1. [pdp-source-segments.md](../../../docs/specs/pdp_taxonomy_process/pdp-source-segments.md)

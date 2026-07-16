# PDP Source Segments

Status: Draft V1 source-segment contract (as of 2026-03-13).

## 1. Purpose
This document defines the `pdp_source_segments` contract.

This is the missing evidence structure needed for:
1. source-aware deterministic-policy candidates
2. recurring unmapped phrase candidates
3. source-aware taxonomy review evidence
4. separating deterministic input from LLM input

The goal is simple:
1. stop relying on one flattened PDP blob
2. preserve source boundaries
3. expose trusted and noisy PDP fields explicitly

Companion documents:
1. [pdp-taxonomy-and-deterministic-process-brief.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process-brief.md)
2. [pdp-taxonomy-and-deterministic-operational-workflow.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-operational-workflow.md)
3. [pdp-shared-evidence-layer.md](../../../docs/specs/pdp_taxonomy_process/pdp-shared-evidence-layer.md)

## 2. Problem
The current PDP pipeline still has a flattening step:
1. `_collect_pdp_text_segments(...)` walks `extras` recursively in [pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)
2. `_flatten_description(...)` joins all text into one string in [pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)

That is useful as a fallback text dump, but it is not suitable as the main evidence model for deterministic behavior.

Why:
1. source provenance is lost
2. deterministic and LLM consume text that is too similar
3. noisy sources cannot be blocked cleanly
4. phrase-based candidate generation becomes weak and noisy

## 3. Scope
`pdp_source_segments` is not the same as:
1. raw `extras` JSON
2. full rendered PDP text
3. the existing flattened `description`

It is a normalized, source-aware segmentation layer derived from parsed PDP data.

## 4. Record Shape
Each segment record should contain:

1. `retailer`
2. `row_type`
   1. `parent`
   2. `variant`
3. `parent_product_id`
4. `variant_id`
   1. empty for parent rows
5. `category_key`
6. `source_channel`
7. `segment_id`
8. `segment_order`
9. `source_path`
10. `segment_text`
11. `normalized_text`

Optional metadata:
12. `label`
13. `subtype`
14. `lang`
15. `captured_at`

## 5. Field Semantics

### 5.1 `source_channel`
The stable business-facing source class.

Examples:
1. `title`
2. `summary`
3. `features`
4. `description_markdown`
5. `description_short`
6. `description_long`
7. `variant_name`
8. `variant_description`
9. `ingredients`
10. `usage`
11. `restrictions`
12. `reviews`

### 5.2 `source_path`
The exact path back to the parsed source object.

Examples:
1. `summary`
2. `details.description_markdown`
3. `details.features[2]`
4. `summary_cards[1].description`
5. `reviews[0].comment`

This field is for debugging and traceability.

### 5.3 `segment_id`
A stable per-record identifier for the segment.

Example pattern:
1. `title`
2. `details.features[0]`
3. `summary_cards[2].value`

### 5.4 `segment_order`
Preserve original reading order within the record.

This matters for:
1. example display
2. future prompt shaping
3. deterministic context windows if needed later

### 5.5 `normalized_text`
Lowercased, trimmed normalization for matching and indexing.

V1 normalization should be simple:
1. trim whitespace
2. collapse internal whitespace
3. lowercase

Do not do aggressive stemming or fuzzy normalization in V1.

## 6. Channel Vocabulary: V1
Use these channels only.

### 6.1 Parent channels
1. `title`
2. `summary`
3. `features`
4. `description_markdown`
5. `description_short`
6. `description_long`
7. `ingredients`
8. `usage`
9. `restrictions`
10. `reviews`

### 6.2 Variant channels
1. `variant_name`
2. `variant_description`

### 6.3 Optional derived channel for UI only
1. `highlights`

This may be useful for display, but should resolve to one of the canonical business channels when used for deterministic logic.

## 7. Segment Granularity Rules
This is important.

The system should not store one segment per whole `extras` blob.

V1 granularity:

1. single string field
   1. one segment

2. list of strings
   1. one segment per item

3. list of objects with textual subfields
   1. one segment per meaningful textual subfield

4. review list
   1. one segment per review text block if reviews are indexed

Examples:
1. each feature bullet = one segment
2. each highlight entry = one segment
3. each review comment = one segment
4. summary = one segment

This keeps evidence precise.

## 8. Current Parsed PDP Mapping
This section maps the segment contract to fields already parsed today.

### 8.1 Common parent fields already present
Across the retailer adapters, the current parsed parent payload already tends to expose:
1. `summary`
2. `details.description_markdown`
3. `details.usage`
4. `details.ingredients`
5. `details.features`
6. review summaries and/or `reviews`

### 8.2 Sephora mapping
Current parsed fields in [sephora.py](../../../modules/pdp/adapters/sephora.py):
1. `parent.title_*` -> `title`
2. `extras.summary` -> `summary`
3. `extras.details.description_markdown` -> `description_markdown`
4. `extras.details.usage` -> `usage`
5. `extras.details.ingredients` -> `ingredients`
6. `extras.details.features` -> `features`
7. `extras.reviews_positive` and `extras.reviews_negative` -> review-summary material
8. `extras.reviews` -> `reviews`

### 8.3 Ulta mapping
Current parsed fields in [ulta.py](../../../modules/pdp/adapters/ulta.py):
1. `parent.title_*` -> `title`
2. `extras.summary` -> `summary`
3. `extras.details.description_markdown` -> `description_markdown`
4. `extras.details.usage` -> `usage`
5. `extras.details.ingredients` -> `ingredients`
6. `extras.details.restrictions` -> `restrictions`
7. `extras.details.features` -> `features`
8. `extras.highlights` -> likely `features` or UI-level highlight segments
9. `extras.summary_cards` -> likely `summary` or feature-adjacent evidence depending on card shape
10. `extras.reviews_positive` and `extras.reviews_negative` -> review-summary material
11. raw review payload via attached reviews -> `reviews`

### 8.4 Amazon mapping
Current parsed fields in [amazon.py](../../../modules/pdp/adapters/amazon.py):
1. `parent.title_*` -> `title`
2. `extras.summary` -> `summary`
3. `extras.details.description_markdown` -> `description_markdown`
4. `extras.details.usage` -> `usage`
5. `extras.details.ingredients` -> `ingredients`
6. `extras.details.features` -> `features`

### 8.5 Variant mapping
Variant-level evidence currently exists in several forms:
1. `variant.shade_name_*`
2. `variant.size_text_raw`
3. `variant_description` or equivalent downstream context summaries

For V1:
1. normalize shade/variant display text into `variant_name`
2. keep any actual variant-specific descriptive copy in `variant_description`

## 9. Mapping Rules From Current Parsed Data
These rules should be fixed in V1.

### 9.1 Title
Source:
1. parent title
2. variant display/shade text for variants

Mapping:
1. parent title -> `title`
2. variant display label -> `variant_name`

### 9.2 Summary
Source:
1. `extras.summary`
2. short summary cards only when clearly summary-like

Mapping:
1. `extras.summary` -> `summary`

Do not merge this automatically with long description.

### 9.3 Features
Source:
1. `details.features`
2. normalized highlights where appropriate

Mapping:
1. each feature bullet or highlight item -> one `features` segment

### 9.4 Description
Source:
1. `details.description_markdown`
2. any short/long description fields if present separately in future

Mapping:
1. main body copy -> `description_markdown`
2. if future split exists:
   1. short -> `description_short`
   2. long -> `description_long`

### 9.5 Ingredients
Source:
1. `details.ingredients`

Mapping:
1. one segment if string
2. multiple if later parsed into bullets or lines

### 9.6 Usage
Source:
1. `details.usage`

Mapping:
1. one segment if string
2. multiple if later parsed into bullets

### 9.7 Restrictions
Source:
1. `details.restrictions`

Mapping:
1. one segment if string

### 9.8 Reviews
Source:
1. `extras.reviews`
2. `reviews_positive`
3. `reviews_negative`

Mapping:
1. each raw review comment -> one `reviews` segment
2. positive/negative summaries -> optional `reviews` segments tagged as summary type

Important:
1. index them for evidence if useful
2. deterministic should normally block this source

## 10. Trusted vs Noisy Sources
This is the main reason the contract exists.

### 10.1 Usually trusted for deterministic
1. `title`
2. `summary`
3. `features`
4. `description_markdown`
5. `description_short`
6. `variant_name`
7. `variant_description`

### 10.2 Usually blocked for deterministic
1. `reviews`
2. `ingredients`
3. `usage`
4. `restrictions`

These can still be indexed and shown in evidence.
They are just not default deterministic sources.

## 11. Relationship To Current Flattening
The current recursive collector in [pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py) is still useful as:
1. a fallback flattened text view
2. a debugging dump
3. a broad LLM context input if needed

But it should no longer be the primary representation for:
1. deterministic matching
2. phrase mining
3. candidate generation

That is the key change.

## 12. Storage Options
For V1, either of these is acceptable:

### 12.1 Postgres first
Pros:
1. easy joins with stage tables and existing audit data
2. good for incremental queries

Cons:
1. more schema work

### 12.2 Cache parquet first
Pros:
1. easier to build from current parsing/export flows
2. good fit with existing postfill caches

Cons:
1. joins with stage evidence may be less direct

### 12.3 Recommendation
For V1:
1. materialize where the current PDP export pipeline can write it most easily
2. but keep the logical contract stable regardless of storage

The contract matters more than the first storage choice.

## 13. Minimum V1 Output
To be useful for candidate generation, `pdp_source_segments` V1 must support:
1. retrieving all segments for one product
2. retrieving all segments for one `(category, attribute)` review slice
3. filtering by `source_channel`
4. counting phrase occurrences by source channel
5. showing snippets with product context

If those five use cases work, the V1 segment layer is good enough.

## 14. What This Enables Immediately
Once this exists, the system can support:
1. recurring unmapped phrase candidates from trusted sources
2. add-deterministic-expression candidates with source-aware evidence
3. block-bad-source candidates backed by actual source-channel counts
4. better evidence pages for taxonomy proposals

## 15. Immediate Next Step
The next design step should be:
1. map `pdp_source_segments` onto the current parsed parent/variant payload shape in one concrete extraction table
2. decide initial storage:
   1. Postgres
   2. cache parquet
   3. or both
3. define the minimum write point in the pipeline where segments are materialized

## 16. Concrete Extraction Table
This section freezes the first practical extraction table against the payloads already produced by the current retailer adapters.

The table is intentionally narrow:
1. only current parsed fields
2. no inferred fields
3. no LLM-generated text
4. no post-hoc flattening

### 16.1 Parent rows

| Parsed source | Channel | Segment rule | `source_path` pattern | Notes |
| --- | --- | --- | --- | --- |
| `title_raw` from `parent_products` | `title` | one segment | `title_raw` | not part of `extras`; must be included explicitly |
| `extras.summary` | `summary` | one segment | `summary` | primary short PDP summary |
| `extras.details.description_markdown` | `description_markdown` | one segment | `details.description_markdown` | main body copy |
| `extras.details.features[]` | `features` | one segment per item | `details.features[i]` | strongest short-form marketing evidence |
| `extras.highlights[]` | `features` | one segment per item | `highlights[i]` | preserve `label` and `description` in the segment text |
| `extras.summary_cards[].items[]` | `features` | one segment per item | `summary_cards[i].items[j]` | V1 treats cards as feature-like evidence |
| `extras.details.ingredients` | `ingredients` | one segment | `details.ingredients` | blocked by default for deterministic |
| `extras.details.usage` | `usage` | one segment | `details.usage` | blocked by default for deterministic |
| `extras.details.restrictions` | `restrictions` | one segment | `details.restrictions` | blocked by default for deterministic |
| `extras.reviews[]` comment/headline | `reviews` | one segment per review text block | `reviews[i].comment` or `reviews[i].headline` | indexed for evidence only |
| `extras.reviews_positive` | `reviews` | one segment per textual subfield | `reviews_positive.headline`, `reviews_positive.comment` | tagged as summary subtype |
| `extras.reviews_negative` | `reviews` | one segment per textual subfield | `reviews_negative.headline`, `reviews_negative.comment` | tagged as summary subtype |

### 16.2 Variant rows

| Parsed source | Channel | Segment rule | `source_path` pattern | Notes |
| --- | --- | --- | --- | --- |
| `shade_name_raw` / normalized variant display text | `variant_name` | one segment | `shade_name_raw` | first-choice variant display text |
| `size_text_raw` when it carries visible variant naming value | `variant_name` | optional extra segment | `size_text_raw` | only if it is real display text, not pure measurement noise |
| `variant.extras.*` text fields | `variant_description` | one segment per mapped field/item | payload path in variant `extras` | same extraction rules as parent, but all mapped into variant-level descriptive evidence |

### 16.3 Segment text composition rules
For fields that are structured objects rather than plain strings:

1. `highlights[i]`
   1. if both `label` and `description` exist, segment text is:
      1. `"{label}: {description}"`
   2. if only one exists, use that value

2. `summary_cards[i].items[j]`
   1. segment text is the cleaned item text
   2. if the parent card has a title, store it in `label` metadata
   3. do not prepend the card title into the text in V1 unless needed for readability

3. `reviews_*`
   1. keep headline and comment as separate segments if both exist
   2. preserve summary-vs-raw-review distinction in `subtype`

### 16.4 Current retailer-specific notes
These are concrete rules for the current adapters.

1. Sephora
   1. `shortDescription` maps to `summary`
   2. `benefits` maps to `details.features`
   3. `reviews_positive`, `reviews_negative`, and raw `reviews` are all review material and stay in `reviews`

2. Ulta
   1. `highlights` should map to `features`, not a standalone deterministic channel
   2. `summary_cards[].items[]` should also map to `features`
   3. `summary_cards` card title should stay as metadata, not become a separate value-bearing channel

3. Amazon
   1. `summary` and `description_markdown` may contain similar text
   2. keep both when both exist; do not deduplicate at extraction time

## 17. Initial Storage Decision
V1 should use cache parquet first.

Reason:
1. the export pipeline already writes per-retailer attribute cache parquet slices
2. adding a `segments` slice there is a smaller change than introducing a new Postgres schema first
3. candidate generation can still join segment data to stage/audit evidence via product keys in Polars
4. the segment layer is primarily analytical/evidence-oriented in V1, not a transactional store

### 17.1 Recommended V1 storage shape
Under the existing attribute cache directory, write one additional per-retailer parquet slice:
1. `segments.parquet`

Minimum columns:
1. `retailer`
2. `row_type`
3. `parent_product_id`
4. `variant_id`
5. `category_key`
6. `source_channel`
7. `segment_id`
8. `segment_order`
9. `source_path`
10. `segment_text`
11. `normalized_text`
12. optional `label`
13. optional `subtype`

### 17.2 Deferred storage
Postgres mirroring can be added later if:
1. candidate generation needs lower-latency repeated joins
2. evidence pages need lightweight server-side filtered retrieval
3. the parquet-only approach becomes operationally awkward

But Postgres should not be the first design move for V1.

## 18. Minimum Write Point In The Pipeline
The minimum write point should be in `modules/add_attributes/pdp_attribute_export.py`, at the point where parent and variant rows are loaded from Postgres and `extras` is still structured.

Concretely:
1. parent path:
   1. inside `_load_parent_products(...)`, immediately after `extras_raw` is parsed
   2. before `_flatten_description(extras)` is called

2. variant path:
   1. inside `_load_variants(...)`, immediately after `extras_raw` is parsed
   2. before `variant_segments` are collapsed into `variant_description`

Why this is the right interception point:
1. adapters have already normalized retailer payloads into a common parsed shape
2. `extras` is still available as structured data
3. this is the last point before the pipeline destroys source boundaries by flattening
4. it avoids pushing source-segment logic into each retailer adapter

## 19. V1 Materialization Rule
The V1 rule should be:

1. parse parent and variant rows as today
2. extract structured `pdp_source_segments` rows alongside current parent/variant outputs
3. continue writing the existing flattened `description` and `variant_description` for backward compatibility and debugging
4. persist `segments.parquet` in the same cache slice set as the other attribute-cache artifacts

This keeps the first implementation narrow:
1. no runtime rewrite yet
2. no immediate Postgres schema migration
3. one new evidence artifact with stable semantics

## 20. Immediate Follow-On Design Step
Once this is accepted, the next design step should be:
1. define the normalization helper and exact segment-building rules
2. define how candidate generation reads `segments.parquet`
3. define the first phrase-mining queries that use it

## 21. Segment-Building Algorithm: V1
This section freezes the extraction algorithm so the first implementation is deterministic and reviewable.

The algorithm should take:
1. base product metadata
2. structured parent or variant payload
3. a fixed extraction mapping

And emit:
1. zero or more normalized source-segment rows

The algorithm should not:
1. infer missing fields
2. deduplicate semantically similar segments
3. merge channels
4. rewrite text beyond simple normalization

## 22. Normalization Helper
V1 should use one shared normalization helper for `normalized_text`.

Normalization steps:
1. convert to string
2. trim leading and trailing whitespace
3. replace internal runs of whitespace with a single space
4. lowercase

Example:
1. raw: `\"  Soft   Matte  Finish\\n\"`
2. normalized: `\"soft matte finish\"`

V1 should not do:
1. stemming
2. lemmatization
3. punctuation stripping beyond whitespace cleanup
4. fuzzy normalization
5. synonym expansion

Reason:
1. the segment layer is evidence, not interpretation

## 23. Text Admissibility Rules
A candidate segment should be emitted only if:
1. the extracted value is textual after coercion
2. the trimmed text is non-empty

A candidate segment should be skipped if:
1. the value is null
2. the value is empty after trimming
3. the value is a non-text scalar with no clear textual representation

V1 should not emit segments for:
1. ratings
2. review counts
3. prices
4. purely numeric metadata
5. URLs

## 24. Segment Construction Rules
The algorithm should treat field shapes differently.

### 24.1 String field
1. emit one segment
2. `segment_text` is the cleaned string
3. `source_path` is the field path

### 24.2 List of strings
1. emit one segment per non-empty item
2. preserve source order
3. path shape:
   1. `field[i]`

### 24.3 Object with textual subfields
1. emit one segment per meaningful textual subfield unless a field-specific composition rule exists
2. preserve object traversal order where possible

### 24.4 List of objects
1. emit one or more segments per object according to the field-specific mapping
2. preserve outer list order first, then inner field order

## 25. Field-Specific Composition Rules
These rules override the generic object handling when the payload shape is known.

### 25.1 `highlights[i]`
If the object has:
1. `label`
2. `description`

Then:
1. if both exist, emit one segment with:
   1. `segment_text = \"{label}: {description}\"`
2. if only one exists, emit one segment with that text
3. `label` metadata should store the original `label` when available
4. `source_path = highlights[i]`

### 25.2 `summary_cards[i].items[j]`
If the item resolves to text:
1. emit one segment per item
2. `segment_text` is the cleaned item text only
3. if the parent card has a title, store it in `label`
4. `source_path = summary_cards[i].items[j]`

### 25.3 Reviews
For raw reviews:
1. if `headline` exists, emit a `reviews` segment for it
2. if `comment` exists, emit a separate `reviews` segment for it
3. `subtype` should distinguish:
   1. `raw_headline`
   2. `raw_comment`

For `reviews_positive` / `reviews_negative`:
1. emit one segment per textual subfield
2. `subtype` should distinguish:
   1. `positive_headline`
   2. `positive_comment`
   3. `negative_headline`
   4. `negative_comment`

## 26. Segment Ordering
`segment_order` must be stable and deterministic within one record.

Rule:
1. assign order in extraction order
2. extraction order follows the fixed channel order below
3. within one channel, preserve source order from the parsed payload

Recommended channel extraction order:
1. `title`
2. `summary`
3. `features`
4. `description_markdown`
5. `description_short`
6. `description_long`
7. `variant_name`
8. `variant_description`
9. `ingredients`
10. `usage`
11. `restrictions`
12. `reviews`

This order is not a ranking of trust.
It is only the stable serialization order for the segment store.

## 27. Segment Id Rule
`segment_id` must be deterministic for one record.

V1 rule:
1. use `source_path` as the primary segment identifier
2. if two segments would otherwise have the same `source_path`, append a deterministic suffix:
   1. `#1`
   2. `#2`

Examples:
1. `title_raw`
2. `details.features[0]`
3. `reviews[2].comment`
4. `reviews_positive.comment`

This is sufficient for V1 because the segment layer is evidence-oriented, not a mutable editorial store.

## 28. Parent And Variant Record Rules
Each segment row must carry product identity from the row it came from.

### 28.1 Parent rows
Required:
1. `row_type = parent`
2. `variant_id = \"\"`
3. parent identifiers and category fields copied from the parent record

### 28.2 Variant rows
Required:
1. `row_type = variant`
2. both `parent_product_id` and `variant_id`
3. category fields copied from the joined parent context

Important:
1. variant rows should emit `variant_name` even if no variant descriptive extras exist
2. variant extras-derived text should map to `variant_description`, not to parent channels

## 29. Failure Handling
The extractor should be conservative.

If one field cannot be parsed cleanly:
1. skip only that field
2. continue extracting other fields
3. do not fail the whole product row

If one object shape is unexpected:
1. fall back to generic string extraction only where safe
2. otherwise skip it

This keeps the segment layer robust against retailer payload drift.

## 30. V1 Implementation Contract
The first implementation should therefore have:
1. one shared normalization helper
2. one shared segment builder
3. one fixed channel order
4. one fixed set of field-specific composition rules
5. no retailer-specific extraction logic outside the existing parsed field mapping

That is the minimum contract needed to keep `pdp_source_segments` consistent across retailers and over time.

## 31. Reading `segments.parquet`
The first consumer of `pdp_source_segments` is candidate generation.

V1 should read `segments.parquet` as an evidence table, not as a runtime serving table.

The expected read pattern is:
1. load one or more per-retailer `segments.parquet` slices
2. filter by:
   1. `category_key`
   2. `row_type`
   3. `source_channel`
3. join to:
   1. product record index for titles, URLs, and images
   2. stage assignment index for current outcomes
   3. assignment evidence index when stage-level explanation is needed
4. aggregate into candidate clusters

The segment table should therefore be treated as:
1. phrase evidence
2. snippet source
3. source-channel distribution evidence

It should not be treated as:
1. a replacement for taxonomy
2. a replacement for stage assignments
3. a final runtime input contract by itself

## 32. Common Query Inputs
The first candidate queries all need the same minimal inputs:

1. `segments.parquet`
2. taxonomy term index
3. current stage assignments
4. product metadata for snippet display

V1 should assume these joins are keyed by:
1. `retailer`
2. `parent_product_id`
3. `variant_id`
4. `row_type`

Where `variant_id` is empty for parent rows.

## 33. Recurring Unmapped Phrase Query
Purpose:
1. find repeated phrases in trusted sources that are not covered by taxonomy labels or synonyms

### 33.1 Input filter
Use only segments where:
1. `source_channel` is in the trusted set
   1. `title`
   2. `summary`
   3. `features`
   4. `description_markdown`
   5. `description_short`
   6. `variant_name`
   7. `variant_description`
2. `category_key` is not empty
3. `normalized_text` is non-empty

### 33.2 Phrase extraction
V1 should stay simple.

Use candidate phrase units such as:
1. whole short segments
2. exact bullet text
3. exact short noun/adjective phrase spans only if they are already available from a deterministic extractor

Do not start with:
1. arbitrary n-grams over full long descriptions
2. fuzzy phrase mining
3. embedding-based phrase clustering

### 33.3 Coverage check
For each candidate phrase:
1. compare against taxonomy labels and synonyms in the same category/likely attribute slice
2. drop anything already covered
3. drop generic stop-list terms

### 33.4 Aggregation
Aggregate by:
1. `category_key`
2. likely `attribute_id`
3. `normalized_phrase`

Compute:
1. distinct product count
2. retailer count
3. source-channel distribution
4. sample snippets

### 33.5 Output
Emit only aggregated candidates, not raw phrases.

This query feeds:
1. `recurring_unmapped_phrase` taxonomy candidates

## 34. Add-Deterministic-Expression Query
Purpose:
1. find repeated phrases in trusted sources that strongly and consistently indicate one existing taxonomy value

### 34.1 Input filter
Use only segments where:
1. `source_channel` is in the trusted deterministic set
2. the row has a current final value for the target attribute
3. the target value is a valid taxonomy leaf

### 34.2 Join requirement
Join segments to:
1. final stage assignments
2. optional explicit/deterministic/LLM breakdown when available

### 34.3 Aggregation key
Aggregate by:
1. `category_key`
2. `attribute_id`
3. `value_id`
4. `normalized_phrase`

### 34.4 Metrics
Compute:
1. distinct product count
2. retailer count
3. source-channel distribution
4. agreement rate with the final assigned value
5. competing-value count for the same phrase
6. sample snippets

### 34.5 Output
Only surface phrases that meet the gating rules defined in the operational workflow.

This query feeds:
1. `add_deterministic_expression` candidates

## 35. Block-Bad-Source Query
Purpose:
1. detect attributes where one source channel is responsible for a disproportionate share of bad deterministic evidence

### 35.1 Input filter
Use only:
1. segments from attributes already enabled for deterministic
2. products where deterministic participated in the assignment path

### 35.2 Join requirement
Join segments to:
1. deterministic-stage assignments
2. final outcomes
3. assignment evidence when available

### 35.3 Aggregation key
Aggregate by:
1. `category_key`
2. `attribute_id`
3. `source_channel`

### 35.4 Metrics
Compute:
1. number of deterministic-supported matches by source
2. number of wrong or unstable outcomes by source
3. share of attribute-level false positives attributable to that source
4. representative bad snippets

### 35.5 Output
Only surface channels that cross the `block_bad_source` gating threshold.

This query feeds:
1. `block_bad_source` deterministic-policy candidates

## 36. Snippet Construction Rules
Candidate generation should not display whole long segments blindly.

V1 snippet rule:
1. keep the original `segment_text`
2. show the full segment when it is short
3. truncate only when the segment is long
4. preserve the matched phrase inside the visible excerpt
5. always display:
   1. `source_channel`
   2. product title
   3. retailer

The snippet layer should remain a display concern.
The underlying evidence should still point back to:
1. `segment_id`
2. `source_path`

## 37. Query Output Shape
All phrase-mining queries should emit an intermediate aggregated table before candidate creation.

Minimum columns:
1. `candidate_domain`
2. `candidate_type`
3. `category_key`
4. `attribute_id`
5. optional `value_id`
6. `phrase`
7. `support_product_count`
8. `support_retailer_count`
9. `source_channel_counts`
10. `sample_segment_refs`
11. optional quality metrics

This table is still internal.
The surfaced candidate queue should be generated only after:
1. hard gating
2. deduplication
3. ranking

## 38. V1 Query Scope
To keep the first implementation narrow, V1 should support only:
1. recurring unmapped phrase queries on trusted channels
2. add-deterministic-expression queries on trusted channels
3. block-bad-source queries for enabled deterministic attributes

It should not yet support:
1. cross-retailer phrase-level inconsistency mining
2. semantic clustering of phrases
3. historical trend analysis
4. retailer-specific custom phrase models

## 39. Relationship To The Coverage Page
The current coverage page remains a temporary evidence surface.

Once `segments.parquet` exists:
1. coverage can eventually show source-aware segments instead of one flattened text scan
2. candidate detail pages can reuse the same snippet references

But V1 candidate generation should not depend on a UI rewrite.

## 40. Immediate Next Step
Once this section is accepted, the next design step should be:
1. define the first internal aggregated candidate tables that sit between raw segment queries and surfaced proposals
2. map those tables onto the candidate gating rules already defined in the operational workflow

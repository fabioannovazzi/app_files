# PDP Taxonomy And Deterministic Operational Workflow

Status: Draft operational companion (as of 2026-03-12).

## 1. Purpose
This document captures the operational parts of the design:
1. the deterministic-policy artifact contract
2. the publish and validation contract
3. taxonomy and deterministic candidate generation
4. proposal evidence requirements
5. review workflows
6. hard gating rules for what is surfaced to the user

This is the companion to:
1. [pdp-taxonomy-and-deterministic-process-brief.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process-brief.md)
2. [pdp-taxonomy-and-deterministic-process.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process.md)
3. [pdp-shared-evidence-layer.md](../../../docs/specs/pdp_taxonomy_process/pdp-shared-evidence-layer.md)
4. [pdp-source-segments.md](../../../docs/specs/pdp_taxonomy_process/pdp-source-segments.md)

## 2. Deterministic Policy Artifact: V1
The deterministic-policy artifact is a separate published file, for example:
1. `deterministic_policy.json`

It answers one question:
1. for a given taxonomy value, what text evidence is allowed to lock that value before the LLM stage?

### 2.1 Core design decisions
1. taxonomy synonyms are never consumed implicitly by deterministic
2. `allowed_synonyms` does not exist
3. deterministic-safe phrases live only in the deterministic policy artifact
4. the artifact is sparse:
   1. missing attribute means deterministic is disabled for that attribute
   2. missing value means no custom deterministic behavior for that value
5. deterministic is opt-in
6. source boundaries must be preserved

### 2.2 Minimal shape
Top level:
1. `version`
2. `taxonomy_version`
3. `source_channels_version`
4. `categories`

Attribute block:
1. `allowed_sources`
2. `blocked_sources`
3. `conflict_resolution`
4. `values`

Value block:
1. `allow_label`
2. `deterministic_expressions`
3. `required_context_any`
4. `negative_patterns`

### 2.3 Semantics
1. if an attribute is absent from the file, deterministic does not run for that attribute
2. if a value is absent, that value has no custom deterministic behavior
3. bare labels are usable only when `allow_label=true`
4. taxonomy synonyms never lock by themselves
5. deterministic uses only:
   1. the bare label when explicitly allowed
   2. `deterministic_expressions`
   3. source restrictions
   4. context requirements
   5. negative patterns
6. if multiple values match for one attribute, output `N/A`

### 2.4 What is deliberately not in the file
1. taxonomy labels
2. taxonomy synonyms
3. hierarchy
4. workflow status
5. product examples
6. merge/split metadata

## 3. Source Channels: V1
Use a fixed vocabulary:
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

Expected V1 deterministic stance:
1. usually allowed:
   1. `title`
   2. `summary`
   3. `features`
   4. `description_markdown`
   5. `description_short`
   6. `variant_name`
   7. `variant_description`
2. usually blocked:
   1. `reviews`
   2. `ingredients`
   3. `usage`
   4. `restrictions`

## 4. Publish And Validation Contract
The three published artifacts must validate together:
1. `attribute_taxonomy.json`
2. `deterministic_policy.json`
3. explicit/certain rules

### 4.1 Hard validation rules
1. every deterministic reference must point to an existing taxonomy leaf
2. every explicit-rule target must point to an existing taxonomy leaf
3. parent nodes cannot be targeted by deterministic policy
4. reserved values such as `unknown` and `other` cannot be targeted
5. `allowed_sources` and `blocked_sources` must use only approved source channels
6. `allowed_sources` and `blocked_sources` must not overlap
7. deterministic value entries that do nothing are invalid

### 4.2 Taxonomy change propagation
1. add value:
   1. deterministic policy unchanged
   2. explicit rules unchanged
2. remove value:
   1. dangling deterministic references block publish
   2. dangling explicit-rule references block publish
3. rename value with same id:
   1. deterministic policy remains valid
   2. explicit rules remain valid
4. rename value with new id:
   1. publish blocks until deterministic and explicit references are remapped
5. merge values:
   1. deterministic entries on source values are reviewed, not auto-transferred
   2. explicit rules on source values are reviewed, not auto-transferred
6. split value:
   1. deterministic entries on the old value are reviewed, not auto-copied
   2. explicit rules on the old value are reviewed, not auto-copied

### 4.3 Warning-only rules
These should surface as warnings, not automatic blockers:
1. taxonomy synonym text overlaps with a deterministic expression
2. taxonomy synonym text overlaps with an explicit phrase
3. duplicate deterministic expressions across multiple values in the same attribute
4. enabled deterministic attributes with very sparse value coverage

## 5. Candidate Classes
The system needs three classes of candidate:

### 5.1 Taxonomy-local candidates
These are direct taxonomy suggestions, such as:
1. same-term collision in one attribute
2. composite value
3. recurring unmapped phrase
4. user-created taxonomy proposal

### 5.2 Mapping inconsistency candidates
These do not automatically imply a taxonomy fix.
They indicate something unstable or contradictory, such as:
1. cross-retailer assignment inconsistency
2. attribute structure review

These may route into:
1. taxonomy proposal
2. deterministic-policy proposal
3. dismissal
4. retailer-data issue
5. product-matching issue

### 5.3 Deterministic-policy candidates
These suggest changes to deterministic behavior, such as:
1. add deterministic expression
2. disable bare label
3. block bad source
4. add negative pattern

## 6. First Taxonomy Candidate Generators
V1 starts with these:

### 6.1 Same-term collision in one attribute
Purpose:
1. detect the same normalized term under multiple values in the same `(category, attribute)`

Likely actions:
1. keep as is
2. remove synonym
3. move synonym
4. merge values
5. rename value

### 6.2 Composite value candidate
Purpose:
1. detect values that appear to bundle multiple concepts

Likely actions:
1. keep as is
2. split value
3. rename value
4. merge into an existing broader value

### 6.3 Recurring unmapped phrase candidate
Purpose:
1. detect frequent trusted-source phrases not covered by taxonomy labels or synonyms

Likely actions:
1. add synonym
2. add new value
3. ignore as noise
4. reroute to deterministic policy instead of taxonomy

### 6.4 User-created proposal
Purpose:
1. allow direct human proposals without waiting for system detection

Examples:
1. merge values
2. split value
3. move synonym
4. rename value

## 7. Mapping Inconsistency Candidates

### 7.1 Attribute structure review
Purpose:
1. surface attributes whose value set is likely wrong, unstable, or too fine-grained for reliable use

Core question:
1. is the attribute structure correct as is?
2. should some sibling values merge?
3. should a broader parent be introduced?
4. should some values move elsewhere?

This candidate is usually:
1. user-created
2. or spawned from repeated mapping inconsistency signals

### 7.2 Cross-retailer assignment inconsistency
Purpose:
1. surface cases where the same product receives different values for the same attribute across retailers

Important:
1. this does not automatically mean the taxonomy is wrong
2. it may point to:
   1. taxonomy problems
   2. deterministic/LLM instability
   3. retailer-specific wording
   4. product-matching problems

This is an investigation candidate, not an automatic taxonomy change.

## 8. Proposal Evidence Contract
Every candidate must show a common evidence block.

### 8.1 Common evidence
1. category
2. attribute
3. candidate type
4. reason surfaced
5. affected values
6. sibling values
7. product impact
8. current taxonomy context:
   1. labels
   2. synonyms

### 8.2 Candidate-specific additions
1. same-term collision:
   1. term
   2. all occurrences of the term
   3. whether each occurrence is a label or synonym
2. composite value:
   1. current label
   2. current synonyms
   3. detected components
   4. whether component values already exist
3. recurring unmapped phrase:
   1. phrase
   2. frequency
   3. product count
   4. source channels
   5. sample snippets
4. cross-retailer inconsistency:
   1. matched product group
   2. identity confidence
   3. retailer-specific assigned values
   4. assignment source per retailer
5. attribute structure review:
   1. full sibling list
   2. synonyms for each sibling
   3. representative products per suspicious sibling
   4. phrase evidence driving assignments

### 8.3 Snippet rule
Phrase-based and inconsistency candidates must include short, source-aware snippets.
Each snippet should show:
1. source channel
2. product title or id
3. short text excerpt

## 9. Taxonomy Proposal Workflow
Proposal lifecycle:
1. `open`
2. `approved`
3. `rejected`
4. `applied`

### 9.1 Queue
The queue should show:
1. proposal type
2. category
3. attribute
4. short reason
5. impact
6. confidence
7. status

### 9.2 Detail page
The detail page should show:
1. header
2. why surfaced
3. current taxonomy context
4. evidence
5. proposed resolution
6. actions

### 9.3 Action sets by proposal type
1. same-term collision:
   1. keep
   2. remove synonym
   3. move synonym
   4. merge values
   5. rename value
2. composite value:
   1. keep
   2. split value
   3. rename value
   4. merge into broader value
3. recurring unmapped phrase:
   1. ignore
   2. add synonym
   3. add value
   4. reroute to deterministic policy
4. attribute structure review:
   1. keep as is
   2. merge selected siblings
   3. introduce parent structure
   4. remove value from attribute
   5. move concept elsewhere
5. cross-retailer inconsistency:
   1. keep as valid difference
   2. open attribute structure review
   3. open taxonomy proposal
   4. open deterministic-policy proposal
   5. mark as product-matching issue
   6. mark as retailer-data issue

### 9.4 Approval model
Separate:
1. approve
2. approve with modification
3. reject
4. apply to draft taxonomy

Approval is the decision.
Apply writes the change to draft.
Publish makes the consistent artifact set active.

## 10. Deterministic-Policy Candidate Workflow
Candidate lifecycle matches taxonomy proposals:
1. `open`
2. `approved`
3. `rejected`
4. `applied`

### 10.1 V1 deterministic-policy candidate types
1. add deterministic expression
2. disable bare label
3. block bad source
4. add negative pattern

### 10.2 Required evidence by type
1. add deterministic expression:
   1. target value
   2. proposed expression
   3. snippets
   4. source channels
   5. product count
2. disable bare label:
   1. target value
   2. confusing bare-label snippets
   3. conflicting values or wrong outcomes
3. block bad source:
   1. source channel
   2. bad-match examples
   3. count of bad matches
4. add negative pattern:
   1. triggering expression
   2. proposed negative pattern
   3. repeated false-positive snippets

### 10.3 Actions
1. approve
2. approve with modification
3. reject
4. apply to draft deterministic policy

### 10.4 Boundary rule
The deterministic-policy workflow never decides taxonomy semantics.
If the evidence points to a semantic problem, reroute to taxonomy.

## 11. Candidate Gating And Aggregation
Candidate generation must be mostly automatic, heavily filtered, and aggregated.

The user must never be asked to inspect raw evidence one event at a time.

### 11.1 Three-stage funnel
1. raw evidence
2. aggregated cluster
3. surfaced candidate

Only stage 3 is visible to the user.

### 11.2 Common hard rules
1. no single raw event is shown directly
2. every visible candidate is an aggregate, not one snippet or one product
3. every visible candidate must have:
   1. one stable key
   2. one clear question
   3. one allowed action set
   4. one evidence package
4. user-created proposals bypass support thresholds, but not structural validation
5. anything below threshold stays hidden as watchlist evidence

### 11.3 Aggregation keys
1. same-term collision:
   1. `category_id + attribute_id + normalized_term`
2. composite value:
   1. `category_id + attribute_id + value_id`
3. recurring unmapped phrase:
   1. `category_id + likely_attribute_id + normalized_phrase`
4. cross-retailer inconsistency:
   1. `category_id + attribute_id + conflicting_value_set`
5. attribute structure review:
   1. `category_id + attribute_id`
6. add deterministic expression:
   1. `category_id + attribute_id + value_id + normalized_expression`
7. disable bare label:
   1. `category_id + attribute_id + value_id`
8. block bad source:
   1. `category_id + attribute_id + source_channel`
9. add negative pattern:
   1. `category_id + attribute_id + value_id + expression + negative_pattern`

### 11.4 V1 hard gates
1. same-term collision:
   1. surface immediately when the same normalized term appears under at least 2 distinct values in the same attribute
2. composite value:
   1. surface only when the label contains a strong separator and the split is linguistically obvious or supported by siblings
3. recurring unmapped phrase:
   1. surface only when it appears in trusted sources
   2. is not already covered by taxonomy labels or synonyms
   3. appears in at least 8 distinct products and 2 retailers, or 15 distinct products in 1 retailer
   4. has at least 3 usable snippets
4. cross-retailer inconsistency:
   1. surface only when product identity confidence is high
   2. the inconsistency repeats for at least 3 product groups
5. attribute structure review:
   1. surface only when user-created or when at least 2 strong signals exist for the same attribute
6. add deterministic expression:
   1. surface only when the phrase appears in trusted sources
   2. maps to one value in at least 8 products
   3. later-stage outcome agrees in at least 90 percent of cases
   4. at least 3 good snippets exist
7. disable bare label:
   1. surface only when bare-label use causes at least 5 wrong or unstable assignments
8. block bad source:
   1. surface only when one source accounts for at least 70 percent of false positives and at least 10 false-positive cases exist
9. add negative pattern:
   1. surface only when the same bad pattern repeats in at least 4 products

### 11.5 Queue size control
1. cap open system-suggested candidates per attribute
2. merge duplicates into one cluster
3. keep weak signals hidden

## 12. Ranking
After a candidate clears the hard gate, sort it by:
1. user-created before system-suggested
2. candidate-type priority
3. confidence
4. affected product count
5. decision ease

Recommended taxonomy candidate order:
1. same-term collision
2. composite value
3. user-created proposal
4. recurring unmapped phrase
5. attribute structure review

## 13. Shared Evidence Layer
All candidate generation depends on one shared evidence layer.

At minimum it should contain:
1. taxonomy index:
   1. categories
   2. attributes
   3. values
   4. synonyms
2. observed PDP phrase index:
   1. phrase
   2. source channel
   3. product ids
   4. category
   5. frequency
3. current mapping outcomes:
   1. explicit result
   2. deterministic result
   3. LLM result
   4. unresolved or `N/A`
4. business impact:
   1. product count
   2. optional sales weight later
5. product identity groups for cross-retailer comparison

This evidence layer is the backbone of the candidate system.

## 14. Recommended Next Step
The next concrete design step is:
1. define the shared evidence/index layer in more detail
2. decide which existing data sources can already populate it
3. identify what is missing for V1 candidate generation

That companion is now here:
1. [pdp-shared-evidence-layer.md](../../../docs/specs/pdp_taxonomy_process/pdp-shared-evidence-layer.md)

## 15. Internal Aggregated Candidate Tables
Between raw evidence and the surfaced proposal queue, the system should materialize internal aggregated candidate tables.

These tables are not user-facing.
They are the contract between:
1. evidence extraction and query logic
2. candidate gating
3. surfaced review queues

They solve a real problem:
1. raw evidence is too noisy
2. surfaced candidates are too opinionated to create directly from raw events
3. the system needs one intermediate aggregated layer that is explainable and testable

## 16. Purpose Of The Internal Tables
The internal candidate tables should do four things:
1. aggregate repeated raw observations under a stable key
2. compute support metrics and evidence summaries
3. feed hard gating and ranking
4. preserve references back to sample evidence rows

The surfaced queue should never be built directly from raw snippets or one-off assignment events.

## 17. Common Shape
Every internal aggregated candidate table should have a common structural contract.

Minimum common fields:
1. `candidate_domain`
   1. `taxonomy`
   2. `mapping_inconsistency`
   3. `deterministic_policy`
2. `candidate_type`
3. `candidate_key`
4. `category_key`
5. optional `attribute_id`
6. optional `value_id`
7. `support_product_count`
8. `support_retailer_count`
9. `confidence_level`
10. `decision_ease`
11. `sample_refs`
12. `evidence_summary`
13. `created_from_run_id` or equivalent batch identifier

Optional fields:
1. `conflicting_value_ids`
2. `source_channel_counts`
3. `agreement_rate`
4. `false_positive_rate`
5. `term`
6. `phrase`
7. `likely_target_value_id`
8. `identity_confidence`

## 18. Sample References
`sample_refs` must not inline full evidence payloads.

Instead they should hold stable references to:
1. product ids
2. segment ids
3. audit row ids
4. review example keys

This is important because:
1. the aggregated table is for gating and ranking
2. the detail page can resolve references into full examples later

V1 can store `sample_refs` as a small JSON list of stable ids.

## 19. Taxonomy Aggregated Tables
V1 should use separate internal tables per taxonomy candidate type.

### 19.1 Same-term collision table
One row per:
1. `category_id + attribute_id + normalized_term`

Required fields:
1. `term`
2. `affected_value_ids`
3. `occurrence_roles`
   1. label
   2. synonym
4. `sibling_value_count`
5. `sample_refs`

This table is built from taxonomy only.

### 19.2 Composite value table
One row per:
1. `category_id + attribute_id + value_id`

Required fields:
1. `value_label`
2. `current_synonyms`
3. `detected_components`
4. `existing_component_value_ids`
5. `sample_refs` if product evidence exists

This table can be generated from taxonomy alone, with optional product evidence enrichment later.

### 19.3 Recurring unmapped phrase table
One row per:
1. `category_id + likely_attribute_id + normalized_phrase`

Required fields:
1. `phrase`
2. `support_product_count`
3. `support_retailer_count`
4. `source_channel_counts`
5. `sample_refs`
6. `nearest_existing_value_ids`

This table is built from `pdp_source_segments` plus taxonomy coverage checks.

### 19.4 User-created taxonomy proposal table
One row per user-created proposal.

Required fields:
1. `proposal_type`
2. `proposed_action`
3. `affected_value_ids`
4. `user_rationale`
5. `sample_refs` if any

This table is the exception: it is not mined from evidence first, but it should still share the same common structural contract where possible.

## 20. Mapping Inconsistency Aggregated Tables
These tables capture strong signs of instability without yet deciding whether the fix belongs in taxonomy or deterministic policy.

### 20.1 Cross-retailer assignment inconsistency table
One row per:
1. `category_id + attribute_id + conflicting_value_set`

Required fields:
1. `conflicting_value_ids`
2. `support_product_count`
3. `support_retailer_count`
4. `identity_confidence`
5. `assignment_source_counts`
   1. explicit
   2. deterministic
   3. llm
6. `sample_refs`

This table is built from:
1. product identity groups
2. stage assignments
3. product metadata

### 20.2 Attribute structure review table
One row per:
1. `category_id + attribute_id`

Required fields:
1. `trigger_types`
2. `suspicious_value_ids`
3. `support_product_count`
4. `signal_count`
5. `sample_refs`
6. `reason_summary`

This table is usually built by combining:
1. repeated inconsistency rows
2. heavy sibling overlap evidence
3. user-created structure reviews

## 21. Deterministic-Policy Aggregated Tables
These tables propose changes to deterministic behavior, not taxonomy semantics.

### 21.1 Add deterministic expression table
One row per:
1. `category_id + attribute_id + value_id + normalized_expression`

Required fields:
1. `phrase`
2. `support_product_count`
3. `support_retailer_count`
4. `source_channel_counts`
5. `agreement_rate`
6. `competing_value_count`
7. `sample_refs`

### 21.2 Disable bare label table
One row per:
1. `category_id + attribute_id + value_id`

Required fields:
1. `label_text`
2. `wrong_or_unstable_count`
3. `error_rate`
4. `conflicting_value_ids`
5. `sample_refs`

### 21.3 Block bad source table
One row per:
1. `category_id + attribute_id + source_channel`

Required fields:
1. `source_channel`
2. `false_positive_count`
3. `false_positive_share`
4. `good_match_count`
5. `sample_refs`

### 21.4 Add negative pattern table
One row per:
1. `category_id + attribute_id + value_id + expression + negative_pattern`

Required fields:
1. `expression`
2. `negative_pattern`
3. `false_positive_count`
4. `rare_in_correct_matches`
5. `sample_refs`

## 22. Table Construction Order
The internal tables should be built in this order:
1. raw evidence extraction
2. normalized phrase/assignment grouping
3. internal aggregated candidate tables
4. hard gating
5. ranking
6. surfaced candidate queue

This ordering is important.
Hard gating must run on aggregated tables, not on raw events.

## 23. Relationship To Hard Gating
The aggregated candidate tables are the direct input to the gating rules in section 11.

Example:
1. the recurring unmapped phrase table provides:
   1. `support_product_count`
   2. `support_retailer_count`
   3. `sample_refs`
   4. `source_channel_counts`
2. the gating layer then decides whether that row becomes a surfaced candidate

So:
1. aggregation computes the evidence
2. gating decides visibility

Those are separate steps.

## 24. Relationship To The Surfaced Queue
The surfaced queue should not duplicate the whole aggregated table.

Instead:
1. surfaced queue rows should reference one aggregated table row
2. queue presentation should add:
   1. priority
   2. status
   3. origin
   4. reviewer fields

This separation matters because:
1. one aggregated candidate may exist without being surfaced yet
2. one surfaced candidate should always be traceable back to one aggregated evidence row

## 25. V1 Materialization Strategy
For V1, these internal tables do not need a permanent database schema.

Acceptable first implementations:
1. derived Polars tables in memory during candidate-generation runs
2. cached parquet outputs per candidate class

Do not force a database schema too early.

The important thing is to stabilize:
1. row shape
2. keys
3. metrics
4. evidence references

## 26. Minimum V1 Set
V1 should materialize only the tables needed for the first supported candidate classes:
1. same-term collision
2. composite value
3. recurring unmapped phrase
4. user-created taxonomy proposal
5. add deterministic expression
6. block bad source
7. disable bare label

Cross-retailer inconsistency and attribute structure review can remain:
1. partially manual
2. or phase 2 for fully systematic aggregation

## 27. Recommended Next Step
The next concrete design step is:
1. define the first V1 candidate-generation run outputs
2. decide which of the internal aggregated tables should be cached to parquet
3. define the minimal surfaced queue contract that references these aggregated rows

## 28. Minimal Surfaced Queue Contract
The surfaced queue is the first user-facing layer.

Its purpose is narrow:
1. show only candidates that cleared hard gating
2. give the reviewer a stable work queue
3. keep one visible work item linked to one aggregated evidence row

The queue is not:
1. raw evidence
2. the full aggregated-candidate store
3. the taxonomy itself
4. the deterministic policy itself

## 29. Queue Row Shape
Each surfaced queue row should have this minimum shape.

Identity:
1. `queue_item_id`
2. `candidate_domain`
3. `candidate_type`
4. `candidate_key`
5. `aggregated_row_ref`

Context:
6. `category_key`
7. optional `attribute_id`
8. optional `value_id`
9. `title`
10. `short_reason`

Workflow:
11. `origin`
   1. `system_suggested`
   2. `user_created`
13. `status`
   1. `open`
   2. `approved`
   3. `rejected`
   4. `applied`
14. `priority_score`
15. `confidence_level`
16. `decision_ease`

Impact:
17. `support_product_count`
18. optional `support_retailer_count`

Timing:
19. `created_at`
20. `updated_at`

Review metadata:
21. optional `reviewer`
22. optional `decision_reason`

## 30. Queue Item Title Rule
The queue title should be concrete and action-oriented.

Examples:
1. `Same term collision in finish: satin`
2. `Composite value in color family: red and pink`
3. `Recurring unmapped phrase in primer form: serum-like`
4. `Block bad source for primer form: reviews`
5. `Disable bare label for finish: natural`

Avoid abstract titles such as:
1. `taxonomy review`
2. `governance update`
3. `candidate 183`

## 31. One Queue Row To One Aggregated Row
This should be a hard rule.

One surfaced queue row must reference exactly one aggregated candidate row.

Why:
1. traceability stays simple
2. gating and ranking are explainable
3. detail pages can load evidence directly from one source row
4. queue state does not get mixed with evidence computation

If multiple aggregated rows need to be reviewed together, they should become:
1. one higher-level aggregated row first
2. then one surfaced queue item

Do not make the queue layer solve aggregation problems.

## 32. Queue Status Semantics
Queue status should be workflow state only.

### 32.1 `open`
1. surfaced and awaiting review

### 32.2 `approved`
1. decision made
2. not yet applied to draft artifact

### 32.3 `rejected`
1. explicitly dismissed
2. should not reappear immediately unless new evidence materially changes the candidate

### 32.4 `applied`
1. decision has been written to the draft taxonomy or draft deterministic policy

These are enough for V1.

## 33. Origin Semantics
`origin` is required because user-created and system-suggested items behave differently in ranking and trust.

Allowed values:
1. `user_created`
2. `system_suggested`

Rule:
1. user-created proposals bypass support thresholds
2. they still must pass structural validation before apply

## 34. Priority And Ordering
The queue should not calculate priority by itself.

Instead:
1. priority is assigned from the gating and ranking layer
2. the queue stores the resulting `priority_score`
3. default display order is:
   1. open items first
   2. higher priority first
   3. newest update first as a final tiebreak

This keeps ranking logic out of the UI layer.

## 35. Queue Filters
V1 queue filters should stay simple.

Recommended filters:
1. `status`
2. `candidate_domain`
3. `candidate_type`
4. `category_key`
5. optional `attribute_id`
6. `origin`

Do not start with deep analytics filters.

## 36. Queue Detail Link
Every queue row must open a detail page that resolves:
1. aggregated evidence
2. sample refs
3. current taxonomy context
4. current deterministic-policy context when applicable
5. allowed actions

So the queue row itself stays light.

## 37. Reappearance Rule
Rejected or applied queue items should not simply respawn on the next run from the same unchanged aggregated row.

V1 rule:
1. if the same `candidate_key` and evidence signature reappear unchanged, suppress automatic resurfacing
2. if evidence materially changes, allow resurfacing

This is necessary to avoid endless queue churn.

## 38. Queue Storage
For V1, queue storage can be lighter than full artifact storage.

Acceptable V1 choices:
1. a small Postgres table
2. a cached parquet plus workflow overlay table

The important part is not the storage engine.
The important part is preserving:
1. queue identity
2. workflow state
3. reference to aggregated evidence

## 39. Relationship To Draft Artifacts
The queue does not edit published artifacts directly.

It only supports:
1. review
2. decision
3. apply to draft artifact

So the lifecycle is:
1. aggregated candidate
2. surfaced queue item
3. reviewer decision
4. draft change
5. publish after validation

This keeps the queue operational and the artifacts canonical.

## 40. V1 Minimal Queue Scope
The first surfaced queue only needs to support the initial candidate classes:
1. same-term collision
2. composite value
3. recurring unmapped phrase
4. user-created taxonomy proposal
5. add deterministic expression
6. disable bare label
7. block bad source

That is enough for the first real workflow.

## 41. Control Check
At this point the design is in control if these statements are true:
1. every user-visible queue item maps to one aggregated evidence row
2. every aggregated row maps back to raw evidence references
3. queue workflow state is separate from evidence computation
4. draft changes are separate from published artifacts
5. publish still validates across taxonomy, deterministic policy, and explicit rules

That is the minimum coherence test.

## 42. Recommended Next Step
The next concrete design step is:
1. define the first V1 candidate-generation run outputs
2. decide which intermediate tables are cached
3. decide where queue workflow state is persisted

## 43. First V1 Candidate-Generation Run Outputs
The first candidate-generation run should produce one immutable output set per run.

This run output set is the boundary between:
1. evidence computation
2. candidate gating and ranking
3. queue seeding

V1 should not write candidate outputs directly into the mutable review queue without first materializing the run result.

## 44. Run Identity And Manifest
Each candidate-generation run should have:
1. `run_id`
2. `created_at`
3. `taxonomy_version`
4. `deterministic_policy_version`
5. `explicit_rules_version`
6. evidence-layer versions when relevant
   1. stage snapshot identifier
   2. source-segment snapshot identifier if used
7. scope
   1. retailer filter if any
   2. category filter if any
   3. attribute filter if any

V1 should write one small manifest file for every run.

Recommended format:
1. `run_manifest.json`

Purpose:
1. make every candidate row traceable to a specific evidence snapshot
2. support debugging and reruns
3. stop queue state from being confused with evidence-generation state

## 45. Candidate Run Cache Root
Candidate-generation outputs should live in a dedicated cache root, not inside the existing attribute-cache slices.

Reason:
1. attribute cache stores product/stage evidence
2. candidate-run cache stores review-oriented aggregates and surfaced candidates
3. mixing them would make cache semantics unclear

Recommended V1 shape:
1. one candidate-run root under the Postgres-derived cache area
2. one subdirectory per `run_id`

Example shape:
1. `.../candidate_runs/<run_id>/run_manifest.json`
2. `.../candidate_runs/<run_id>/aggregated/*.parquet`
3. `.../candidate_runs/<run_id>/surfaced/surfaced_candidates.parquet`

The exact filesystem path can be chosen later.
The important design rule is: separate root, one directory per run.

## 46. Aggregated Tables To Cache In V1
These internal aggregated tables should be cached to parquet in V1 because:
1. they are deterministic outputs of one evidence snapshot
2. they are useful for debugging and replay
3. they may be expensive enough to recompute repeatedly

### 46.1 Always cache
1. `taxonomy_same_term_collision.parquet`
2. `taxonomy_composite_value.parquet`
3. `deterministic_disable_bare_label.parquet`
4. `deterministic_block_bad_source.parquet`

### 46.2 Cache when source segments are available
1. `taxonomy_recurring_unmapped_phrase.parquet`
2. `deterministic_add_expression.parquet`
3. `deterministic_add_negative_pattern.parquet`

### 46.3 Do not require in V1
1. `cross_retailer_assignment_inconsistency.parquet`
2. `attribute_structure_review_signals.parquet`

Those can remain manual or phase 2 until the product-identity layer is stronger.

## 47. Surfaced Candidate Run Output
After aggregation, hard gating, deduplication, and ranking, the run should emit one surfaced candidate table.

Recommended file:
1. `surfaced_candidates.parquet`

This file should contain only system-generated candidates that are eligible to enter the queue.

It should include:
1. `candidate_domain`
2. `candidate_type`
3. `candidate_key`
4. `aggregated_row_ref`
5. `category_key`
6. optional `attribute_id`
7. optional `value_id`
8. `title`
9. `short_reason`
10. `priority_score`
11. `confidence_level`
12. `decision_ease`
13. `support_product_count`
14. optional `support_retailer_count`
15. `evidence_signature`
16. `run_id`

This file is immutable once written.

## 48. What Should Stay Derived In Memory
Not every intermediate result needs its own persisted file.

V1 can keep these steps in memory during the run:
1. raw evidence joins
2. phrase normalization helpers
3. pre-aggregation temporary tables
4. final ranking sort before writing `surfaced_candidates.parquet`

Only the run outputs that are useful for review/debugging should be cached.

## 49. User-Created Proposals
User-created proposals are different from system-generated run outputs.

They should not wait for a candidate-generation run.

V1 rule:
1. user-created proposals go directly into queue workflow storage
2. they still reference taxonomy context
3. they still go through validation before apply

So there are two entry paths into the review system:
1. system-generated surfaced candidates from a run
2. direct user-created proposals

## 50. Queue Workflow State Persistence
Queue workflow state should be persisted in Postgres in V1.

Reason:
1. queue state is mutable
2. statuses change over time
3. reviewers add decisions and reasons
4. resurfacing suppression must survive across runs

Parquet is a good fit for immutable run outputs.
Postgres is a better fit for mutable workflow state.

## 51. Minimal Queue State Store
V1 only needs a small mutable store.

At minimum it must preserve:
1. `queue_item_id`
2. `candidate_key`
3. `candidate_type`
4. `candidate_domain`
5. `aggregated_row_ref`
6. `run_id`
7. `evidence_signature`
8. `origin`
9. `status`
10. `priority_score`
11. `reviewer`
12. `decision_reason`
13. `created_at`
14. `updated_at`

This is enough to support:
1. open queue views
2. decisions
3. apply state
4. reappearance suppression

## 52. Reappearance And Upsert Rule
System-generated surfaced candidates should be upserted into queue storage using:
1. `candidate_key`
2. `candidate_type`
3. `candidate_domain`

And compared using:
1. `evidence_signature`

V1 rule:
1. if the same candidate reappears with the same evidence signature and was already rejected or applied, do not resurface it
2. if the evidence signature changes materially, allow resurfacing
3. if the candidate is already open, update freshness metadata instead of creating a duplicate

This is the practical mechanism behind the earlier reappearance rule.

## 53. Recommended First V1 Run Contract
The first V1 run should therefore write:

Immutable outputs:
1. `run_manifest.json`
2. cached aggregated parquet tables for supported candidate classes
3. `surfaced_candidates.parquet`

Mutable workflow store:
4. Postgres queue state for:
   1. system-generated surfaced candidates after upsert
   2. user-created proposals

That is the minimum complete loop.

## 54. Why This Is Enough
This is enough because it cleanly separates:
1. evidence computation
2. review workflow state
3. published business artifacts

That avoids the main failure mode we already saw:
1. workflow concepts leaking into canonical artifacts
2. or UI state leaking into evidence-generation logic

## 55. Recommended Next Step
The next concrete design step is:
1. define the first V1 candidate-generation run outputs field-by-field
2. decide the exact cached parquet file names and minimal schemas
3. define the minimal Postgres queue-state schema

## 56. Physical Schema Strategy For V1
V1 should keep the physical schemas flatter than the logical model.

Recommended rule:
1. scalar fields stay as scalar parquet/Postgres columns
2. nested lists, maps, and sample-reference bundles are stored as JSON strings in V1

Reason:
1. easier schema stability across runs
2. easier debugging from CLI tools
3. easier Postgres interoperability
4. avoids overcommitting to nested parquet structures too early

So V1 should prefer:
1. `*_json` UTF-8 columns for nested payloads

Examples:
1. `sample_refs_json`
2. `source_channel_counts_json`
3. `affected_value_ids_json`
4. `conflicting_value_ids_json`
5. `evidence_summary_json`

## 57. `run_manifest.json` Schema
Each run directory should contain one manifest with this minimum shape.

Required fields:
1. `run_id`
2. `created_at`
3. `taxonomy_version`
4. `deterministic_policy_version`
5. `explicit_rules_version`
6. `stage_snapshot_id`
7. optional `source_segments_snapshot_id`
8. `scope`
   1. `retailers`
   2. `categories`
   3. `attributes`
9. `generated_files`
10. `generator_version`

This file is JSON because:
1. it is small
2. it is read by humans and tooling
3. it does not benefit from parquet

## 58. Aggregated Candidate Parquet Common Schema
Every cached aggregated parquet file should include this common column set.

Required columns:
1. `candidate_domain` `Utf8`
2. `candidate_type` `Utf8`
3. `candidate_key` `Utf8`
4. `category_key` `Utf8`
5. `attribute_id` `Utf8`
6. `value_id` `Utf8`
7. `support_product_count` `Int64`
8. `support_retailer_count` `Int64`
9. `confidence_level` `Utf8`
10. `decision_ease` `Utf8`
11. `sample_refs_json` `Utf8`
12. `evidence_summary_json` `Utf8`
13. `created_from_run_id` `Utf8`

Optional common columns:
14. `priority_score` `Float64`
15. `term` `Utf8`
16. `phrase` `Utf8`
17. `source_channel_counts_json` `Utf8`
18. `agreement_rate` `Float64`
19. `false_positive_rate` `Float64`
20. `affected_value_ids_json` `Utf8`
21. `conflicting_value_ids_json` `Utf8`
22. `identity_confidence` `Float64`

Rule:
1. if a field does not apply to a candidate class, write null

## 59. Exact Aggregated File Set For First V1
The first V1 run should write these parquet files when the corresponding candidate class is enabled.

Always expected:
1. `aggregated/taxonomy_same_term_collision.parquet`
2. `aggregated/taxonomy_composite_value.parquet`
3. `aggregated/deterministic_disable_bare_label.parquet`
4. `aggregated/deterministic_block_bad_source.parquet`

Conditional on `pdp_source_segments` availability:
5. `aggregated/taxonomy_recurring_unmapped_phrase.parquet`
6. `aggregated/deterministic_add_expression.parquet`
7. `aggregated/deterministic_add_negative_pattern.parquet`

These file names should be treated as the first stable V1 names.

## 60. Candidate-Class-Specific Columns
Each aggregated file should add a small number of class-specific columns on top of the common schema.

### 60.1 `taxonomy_same_term_collision.parquet`
Additional columns:
1. `term` `Utf8`
2. `occurrence_roles_json` `Utf8`
3. `sibling_value_count` `Int64`

### 60.2 `taxonomy_composite_value.parquet`
Additional columns:
1. `value_label` `Utf8`
2. `current_synonyms_json` `Utf8`
3. `detected_components_json` `Utf8`
4. `existing_component_value_ids_json` `Utf8`

### 60.3 `taxonomy_recurring_unmapped_phrase.parquet`
Additional columns:
1. `phrase` `Utf8`
2. `nearest_existing_value_ids_json` `Utf8`

### 60.4 `deterministic_add_expression.parquet`
Additional columns:
1. `phrase` `Utf8`
2. `competing_value_count` `Int64`

### 60.5 `deterministic_disable_bare_label.parquet`
Additional columns:
1. `label_text` `Utf8`
2. `wrong_or_unstable_count` `Int64`
3. `error_rate` `Float64`

### 60.6 `deterministic_block_bad_source.parquet`
Additional columns:
1. `source_channel` `Utf8`
2. `false_positive_count` `Int64`
3. `false_positive_share` `Float64`
4. `good_match_count` `Int64`

### 60.7 `deterministic_add_negative_pattern.parquet`
Additional columns:
1. `expression` `Utf8`
2. `negative_pattern` `Utf8`
3. `false_positive_count` `Int64`
4. `rare_in_correct_matches` `Boolean`

## 61. `surfaced_candidates.parquet` Schema
This file is the immutable handoff from one run into queue upsert logic.

Required columns:
1. `candidate_domain` `Utf8`
2. `candidate_type` `Utf8`
3. `candidate_key` `Utf8`
4. `aggregated_row_ref` `Utf8`
5. `category_key` `Utf8`
6. `attribute_id` `Utf8`
7. `value_id` `Utf8`
8. `title` `Utf8`
9. `short_reason` `Utf8`
10. `priority_score` `Float64`
11. `confidence_level` `Utf8`
12. `decision_ease` `Utf8`
13. `support_product_count` `Int64`
14. `support_retailer_count` `Int64`
15. `evidence_signature` `Utf8`
16. `run_id` `Utf8`
17. `origin` `Utf8`

Rule:
1. for V1 system-generated surfaced candidates, `origin` is always `system_suggested`
2. user-created proposals do not belong in this parquet file

## 62. `aggregated_row_ref` Rule
`aggregated_row_ref` should be deterministic and file-based.

V1 format:
1. `<relative parquet path>#<candidate_key>`

Example:
1. `aggregated/deterministic_block_bad_source.parquet#face_primer|form|reviews`

This is enough to:
1. resolve the source aggregated row
2. keep queue upsert logic simple
3. avoid introducing a second row-id system

## 63. Postgres Queue-State Schema
V1 should use one small queue table.

Recommended table:
1. `review_queue_items`

Required columns:
1. `queue_item_id` `TEXT PRIMARY KEY`
2. `candidate_domain` `TEXT NOT NULL`
3. `candidate_type` `TEXT NOT NULL`
4. `candidate_key` `TEXT NOT NULL`
5. `aggregated_row_ref` `TEXT`
6. `run_id` `TEXT`
7. `evidence_signature` `TEXT`
8. `origin` `TEXT NOT NULL`
9. `status` `TEXT NOT NULL`
10. `category_key` `TEXT`
11. `attribute_id` `TEXT`
12. `value_id` `TEXT`
13. `title` `TEXT NOT NULL`
14. `short_reason` `TEXT`
15. `priority_score` `REAL`
16. `confidence_level` `TEXT`
17. `decision_ease` `TEXT`
18. `support_product_count` `INTEGER`
19. `support_retailer_count` `INTEGER`
20. `reviewer` `TEXT`
21. `decision_reason` `TEXT`
22. `created_at` `TEXT NOT NULL`
23. `updated_at` `TEXT NOT NULL`

V1 nullable rule:
1. `aggregated_row_ref`, `run_id`, and `evidence_signature` may be null for user-created proposals

## 64. Queue Indexes
V1 should add only the indexes needed for queue performance and duplicate suppression.

Recommended indexes:
1. unique index on:
   1. `candidate_domain`
   2. `candidate_type`
   3. `candidate_key`
2. non-unique index on:
   1. `status`
   2. `priority_score`
3. non-unique index on:
   1. `category_key`
   2. `attribute_id`

That is enough for the first queue views.

## 65. Optional Decision History Table
V1 does not require a separate history table.

If later needed, add:
1. `review_queue_events`

But do not make it mandatory for first implementation.

The single queue table is enough for:
1. current state
2. duplicate suppression
3. review progress

## 66. Queue Upsert Behavior
When loading `surfaced_candidates.parquet` into queue state:

1. if `(candidate_domain, candidate_type, candidate_key)` does not exist:
   1. insert a new `open` queue row

2. if it exists and `status = open`:
   1. update freshness fields
   2. update `run_id`
   3. update `evidence_signature`
   4. update metrics like priority and support counts

3. if it exists and `status in (rejected, applied)`:
   1. compare `evidence_signature`
   2. if unchanged, suppress resurfacing
   3. if changed materially, reopen by setting:
      1. `status = open`
      2. refreshed metadata

This makes the suppression rule operational.

## 67. Minimal V1 Completeness Test
V1 is physically specified enough to implement when these are all true:
1. every run writes a manifest
2. every supported candidate class has a stable parquet schema
3. every surfaced candidate row can resolve back to one aggregated row
4. queue state can persist reviewer decisions separately from run outputs
5. user-created proposals can exist without a run

That is the implementation-readiness checkpoint.

## 68. Recommended Next Step
The next concrete design step is:
1. write the implementation sequence for V1
2. decide the order of coding tasks
3. define the first narrow deliverable that reaches a usable review workflow

## 69. V1 Implementation Principles
The implementation sequence should follow three strict principles.

### 69.1 Build the review loop before the mutation loop
First prove that:
1. the system can generate useful candidates
2. the queue is understandable
3. the evidence is sufficient for decisions

Only then expand into:
1. draft-apply logic
2. publish workflows
3. cross-artifact mutation flows

Reason:
1. the earlier failure mode was building edit machinery before proving the review object was correct

### 69.2 Start with the evidence we already have
The first deliverable should avoid dependencies on:
1. the missing source-segment index
2. the missing strong product-identity layer

So V1 should start from:
1. taxonomy-only candidate generation
2. user-created proposals
3. existing stage/audit evidence only where already strong

### 69.3 Keep artifact mutation out of phase 1
The first deliverable should not rewrite taxonomy or deterministic policy automatically.

It should support:
1. candidate generation
2. review
3. decision persistence

That is enough to validate the workflow.

## 70. First Narrow Deliverable
The first narrow deliverable should be:

1. candidate-generation run outputs for taxonomy-local candidates
2. queue-state persistence
3. a minimal review queue UI
4. user-created proposal entry
5. approve/reject persistence

It should explicitly not include:
1. apply-to-draft artifact mutation
2. publish
3. source-segment mining
4. cross-retailer inconsistency automation
5. deterministic-policy mutation

### 70.1 Why this is the right first deliverable
Because it proves the hardest product question first:
1. are we surfacing the right review objects?

Without that proof, building mutation and publish flows is premature.

## 71. Phase 1 Scope
Phase 1 should implement only this slice.

### 71.1 Candidate classes included
1. `same_term_same_attribute_collision`
2. `composite_value_candidate`
3. `user_created` taxonomy proposals

### 71.2 Candidate classes excluded
1. recurring unmapped phrase
2. add deterministic expression
3. block bad source
4. disable bare label
5. cross-retailer inconsistency
6. attribute structure review automation

User-created structure reviews can still exist manually, but not as a systematic auto-generated stream.

### 71.3 Deliverables
1. run manifest writing
2. cached parquet for:
   1. `taxonomy_same_term_collision.parquet`
   2. `taxonomy_composite_value.parquet`
3. `surfaced_candidates.parquet`
4. Postgres queue table
5. queue API
6. minimal queue UI
7. user-created proposal creation flow

## 72. Phase 1 Coding Order
The first coding phase should follow this order.

### 72.1 Storage scaffolding
1. candidate-run cache root
2. `run_manifest.json`
3. queue Postgres table and indexes

### 72.2 Taxonomy candidate generators
1. same-term collision generator
2. composite value generator

These are the cleanest and lowest-risk generators because they depend on taxonomy only.

### 72.3 Aggregation and surfaced queue output
1. build aggregated parquet outputs
2. apply hard gating
3. rank
4. write `surfaced_candidates.parquet`

### 72.4 Queue upsert
1. load surfaced candidates into Postgres queue state
2. apply duplicate suppression and reappearance rules

### 72.5 Minimal review UI
1. queue list
2. candidate detail page
3. approve/reject actions
4. user-created proposal form

## 73. Phase 1 UI Scope
The first UI should stay narrow.

Required screens:
1. queue list
2. queue detail
3. create user proposal

Required actions:
1. approve
2. reject
3. add decision reason
4. create proposal

Not in phase 1:
1. generic taxonomy browser
2. direct taxonomy editor
3. publish controls
4. draft artifact editing

## 74. Phase 1 Success Criteria
Phase 1 is successful if all are true:
1. the system can generate taxonomy-local candidates from the current taxonomy
2. queue rows are understandable without reading raw JSON
3. reviewers can approve/reject candidates
4. user-created proposals persist correctly
5. duplicate suppression works across reruns

If any of these fail, do not expand scope yet.

## 75. Phase 2 Scope
Only after phase 1 is working should phase 2 begin.

Phase 2 should add:
1. apply-to-draft taxonomy changes for the supported taxonomy proposal types
2. validation preview against downstream artifacts
3. more complete proposal detail actions

### 75.1 Initial safe apply-to-draft set
The first draft-mutation implementation should stay narrow.

Supported user-created proposal types:
1. `add_synonym`
2. `remove_synonym`
3. `move_synonym`
4. `rename_value`
5. `add_value`

Rules:
1. `rename_value` keeps the same `value_id`; only the label changes
2. `move_synonym` requires exactly one target value in the same attribute
3. `add_value` in V1 creates a new root-level leaf under the selected attribute using the normalized `new_label` as `value_id`
4. `add_value` is blocked for hierarchical attributes in V1
5. reserved leaves such as `unknown` and `other` cannot be edited
6. draft apply requires the queue item to be `approved` first
7. the draft view must show semantic diff items against the published taxonomy
8. the draft must be resettable without affecting the published taxonomy
9. draft preview should be available directly from the current draft state and include explicit-rule impact summary
10. draft publish must reuse the same explicit-rule invalidation gate as direct taxonomy publish
11. successful draft publish must clear the current draft after persisting the published taxonomy and version history
12. user-created merge and split proposals may be previewable before they are applicable to the draft; the preview must show semantic diff and explicit-rule impact
13. `split_value` preview may use a mix of existing target values and new target labels; new targets created this way exist only in the preview draft until a later supported apply path exists

Not yet supported in the first draft-mutation slice:
1. `merge_values`
2. `split_value`
3. attribute structure changes

Reason:
1. synonym edits and same-id renames do not create dangling taxonomy references
2. merge/split/add require downstream reference remediation and should come later

Still not yet:
1. source-segment mining
2. deterministic-policy queue automation

## 76. Phase 3 Scope
Phase 3 should add deterministic-policy review using existing strong evidence.

Candidate classes:
1. `disable_bare_label`
2. `block_bad_source`

Reason:
1. these can be supported from stage assignments and audit evidence before the full source-segment layer is complete

Deliverables:
1. deterministic aggregated parquet outputs
2. surfaced deterministic candidates
3. queue handling for deterministic-policy domain
4. approve/reject workflow for deterministic-policy candidates
5. deterministic-policy draft publish path with validation and versioning
6. safe draft apply for a narrow deterministic candidate set
7. no free-form deterministic-policy mutation yet

Phase-3 foundation may begin with:
1. read-only deterministic-policy artifact endpoints
2. bootstrap output for selected taxonomy attributes
3. validation against taxonomy ids and source-channel vocabulary
4. deterministic-policy draft storage, preview, reset, and publish without mutation
5. a first queue page for the deterministic-policy domain
6. approve/reject queue actions
7. safe apply-to-draft only for:
   - `disable_bare_label`
   - `block_bad_source`
8. preview-before-apply for the same narrow deterministic candidate set

## 77. Phase 4 Scope
Phase 4 should add the source-segment layer and phrase-based candidates.

Deliverables:
1. `pdp_source_segments` extraction
2. `segments.parquet`
3. recurring unmapped phrase candidates
4. add deterministic expression candidates
5. add negative pattern candidates
6. preview/apply-to-draft for `add_deterministic_expression`

This is the first phase that depends on the source-segment contract.

## 78. Phase 5 Scope
Phase 5 should add the product-identity layer and mapping inconsistency automation.

Deliverables:
1. product identity groups
2. cross-retailer inconsistency candidates
3. stronger attribute structure review signals

This is intentionally late because it has the weakest current evidence base.

## 79. What Not To Build Early
Do not build these before phase 1 proves the workflow:
1. full taxonomy editing console
2. complex governance status systems
3. automatic merge/split application
4. cross-retailer candidate automation
5. phrase mining over flattened PDP blobs

These are exactly the kinds of scope expansion that previously derailed the work.

## 80. Recommended First Coding Deliverable
If one concrete deliverable must be chosen, it should be:

1. taxonomy-local candidate run
2. surfaced queue
3. approve/reject workflow
4. user-created proposal entry

That is the first deliverable I would actually ship for review.

## 81. Implementation Readiness Check
The design is ready to move into implementation planning if these are all true:
1. the first deliverable is narrow and explicit
2. each later phase depends on one new evidence capability only
3. mutation and publish are not mixed into candidate discovery
4. the queue is the first user-facing object, not the taxonomy tree

This is now true.

# PDP Taxonomy Governance Spec

Status: Draft proposal (as of 2026-03-11).

## 1. Objective
Define a governed lifecycle for taxonomy leaves so PDP classification does not assume that every current value in `attribute_taxonomy.json` is semantically correct.

This spec comes before:
1. explicit/certain rules
2. deterministic trusted policy
3. LLM value selection

Those later stages must operate only on the governed canonical target set.

## 2. Problem Statement
The current taxonomy validator enforces structure and normalization, but it does not express whether a leaf is:
1. canonical and approved
2. still under review
3. deprecated
4. replaced by another leaf

That is a real issue for PDP mapping because taxonomy shape is not always stable.

Example:
1. `foundation.form` includes broad forms such as `liquid`
2. `face_primer.form` currently includes narrower forms such as `lotion` and `oil`
3. that may be correct, or it may be a granularity error

If `oil` under `face_primer.form` is later deemed non-canonical, deterministic rules should not lock to it in the meantime.

## 3. Core Principles
1. Taxonomy presence is not proof of correctness.
2. The operational target set is the set of active canonical leaves, not every stored leaf.
3. Explicit/certain rules may target only active canonical leaves.
4. Deterministic trusted may lock only active canonical leaves.
5. LLM prompts and allowed outputs must use only active canonical leaves.
6. Draft, `needs_review`, and deprecated leaves may exist in the taxonomy for governance purposes, but runtime classification must not emit them.

## 4. Scope
In scope:
1. value-level lifecycle fields
2. canonical replacement and merge behavior
3. taxonomy review UI and publish flow
4. runtime contract for explicit, deterministic trusted, and LLM stages

Out of scope:
1. deciding the correct ontology for every attribute in this document
2. full historical backfill strategy for already-persisted outputs
3. retailer-specific category mapping rules

## 5. Proposed Leaf Governance Model
Add optional governance fields to taxonomy leaves.

Example:

```json
{
  "id": "oil",
  "label": "oil",
  "synonyms": [
    "beauty oil",
    "dry oil",
    "primer oil"
  ],
  "status": "needs_review",
  "governance_action": "merge",
  "successor_leaf_ids": ["liquid"],
  "governance_reason": "Possible over-specific subtype of liquid for face primer."
}
```

## 6. Governance Fields
Leaf-level governance fields:
1. `status`
2. `governance_action`
3. `successor_leaf_ids`
4. `governance_reason`

### 6.1 `status`
Allowed values:
1. `active`
2. `draft`
3. `needs_review`
4. `deprecated`

Meaning:
1. `active`: canonical runtime target; may be emitted by classifiers
2. `draft`: proposed taxonomy leaf; visible in UI, not emitted at runtime
3. `needs_review`: existing leaf with unresolved ontology concerns; not emitted at runtime
4. `deprecated`: retired leaf; not emitted at runtime; usually points at a replacement

### 6.2 `governance_action`
Allowed values:
1. `merge`
2. `split`

Meaning:
1. `merge`: one non-active leaf is retired into one surviving canonical leaf
2. `split`: one non-active leaf is retired into multiple successor leaves

### 6.3 `successor_leaf_ids`
Type:
1. optional list of strings

Meaning:
1. sibling leaf ids in the same `(category, attribute)` namespace
2. for `merge`, exactly one successor is required
3. for `split`, at least two successors are required
4. a `split` is valid only when the attribute supports `selection=multi`

### 6.4 `governance_reason`
Type:
1. optional string

Meaning:
1. short human-readable explanation for the governance state
2. intended for UI and audit visibility

## 7. Runtime Contract
### 7.1 Taxonomy loading
Runtime classification must derive an active target set per `(category, attribute)`:
1. include only leaves with `status=active`
2. exclude `draft`
3. exclude `needs_review`
4. exclude `deprecated`

Reserved leaves:
1. `unknown`
2. `other`

These remain active by definition and cannot be deprecated.

### 7.2 Explicit/Certain stage
Rules:
1. explicit rules may target only active leaves
2. a rule referencing `draft`, `needs_review`, or deprecated leaf is invalid
3. publish and validation must fail if such a rule exists

### 7.3 Deterministic trusted stage
Rules:
1. deterministic policy applies only to active leaves
2. deterministic aliases on non-active leaves may exist in draft config, but runtime must ignore them
3. non-active leaves must never lock deterministically

### 7.4 LLM stage
Rules:
1. the allowed output set must include only active leaves
2. prompt examples and post-processing must not return non-active leaves
3. if historical prompts or cached outputs mention deprecated leaves, post-processing should remap only when an approved replacement exists

## 8. Governance Actions
The UI and API should support these actions:
1. create leaf as `draft`
2. activate draft leaf
3. mark active leaf as `needs_review`
4. deprecate leaf
5. merge leaf into another leaf
6. split one legacy leaf into multiple successor leaves
7. restore deprecated leaf to `active`
8. edit `governance_reason`

Important distinction:
1. adding a leaf is not the same as activating it
2. keeping a leaf in the file is not the same as allowing runtime emission

## 9. Validation Rules
The taxonomy validator should enforce:
1. `status` must be one of the allowed enums
2. `governance_action` must be one of the allowed enums when present
3. `successor_leaf_ids` must refer to other leaves in the same attribute
4. `successor_leaf_ids` must not point to self
5. every successor target must exist
6. `merge` requires exactly one successor
7. `split` requires at least two successors
8. `split` is valid only for `selection=multi`
9. `unknown` and `other` cannot be `draft`, `needs_review`, or `deprecated`
10. parent nodes with `children` must not carry leaf governance fields

## 10. UI Model
The review experience should have three adjacent tabs:
1. `Taxonomy`
2. `Certain Rules`
3. `Deterministic Policy`

Tab responsibilities:
1. `Taxonomy`: govern the canonical target set
2. `Certain Rules`: govern exact certainty signals for active leaves
3. `Deterministic Policy`: govern trusted deterministic locking for active leaves

This order matters.

The correct workflow is:
1. decide whether the leaf is canonical
2. decide which exact phrases are certain enough
3. decide whether broader deterministic locking is safe

## 11. Taxonomy Tab Requirements
The `Taxonomy` tab should support:
1. category and attribute selection
2. leaf table with `status`, `governance_action`, `successor_leaf_ids`, and `governance_reason`
3. add new draft leaf
4. change lifecycle state
5. merge, split, or deprecate leaf
6. preview runtime impact before publish
7. validate and publish
8. versions and audit

Preview should show:
1. leaves newly entering the active target set
2. leaves leaving the active target set
3. explicit rules that would become invalid
4. deterministic policies that would become inactive
5. rows likely affected by the change

Current implementation status:
1. explicit-rule invalidation preview is implemented
2. deterministic-policy invalidation preview is not yet implemented
3. preview returns newly invalid explicit rules relative to the currently published taxonomy

Publish safeguards:
1. taxonomy publish must be blocked when the draft would newly invalidate active explicit rules
2. the publish API may proceed only when the caller explicitly acknowledges that impact
3. the preview response should be reusable as the publish-blocking explanation payload

Minimum preview payload:
1. explicit rules config path
2. total rules and active rules
3. currently invalid rules
4. draft-invalid rules
5. newly invalid rules
6. newly invalid active rules
7. per-rule impacts with:
   `rule_id`, `category_key`, `attribute_id`, `value_key`, `reason`, `taxonomy_status`, `signal_status`

## 12. Example: `face_primer.form`
Current state may represent an ontology problem, not a matching problem.

Possible review outcomes:
1. keep `oil` and `lotion` as active distinct leaves
2. mark `oil` and `lotion` as `needs_review` while data is studied
3. introduce `liquid` as the canonical leaf and merge `oil` and `lotion` into it
4. restructure the attribute to hierarchical `liquid -> oil/lotion/serum`

This document does not choose the right ontology.

It does require that while the ontology is unsettled:
1. suspect leaves must not be treated as safe runtime targets
2. deterministic stages must not lock values against unstable leaves

## 13. Relationship To Existing Queue-Based Review
The current taxonomy review queue is useful for proposing candidate new values.

It is not sufficient for ontology governance because it does not support:
1. marking an existing leaf as suspect
2. deprecating a leaf
3. merging one leaf into another
4. previewing classifier impact from value retirement

The new taxonomy governance flow should coexist with the candidate queue, not replace it.

## 14. Implementation Notes
Current code gaps:
1. `modules/add_attributes/taxonomy_schema.py` has no leaf lifecycle fields
2. `modules/add_attributes/attribute_taxonomy.py` only supports attribute-level activity, not leaf-level governance
3. explicit and deterministic docs currently assume taxonomy leaf presence is enough

Implementation order:
1. extend taxonomy schema with leaf governance fields
2. build active-leaf filtering in taxonomy loading
3. update explicit validation to require active target leaves
4. update deterministic trusted runtime to ignore non-active leaves
5. add taxonomy governance UI and publish flow

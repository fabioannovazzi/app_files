# PDP Deterministic Trusted Policy Schema

Status: Draft proposal (as of 2026-03-11).

## 1. Objective
Define a source-aware, taxonomy-governed policy layer for the second deterministic stage in PDP attribute mapping.

This stage runs after the explicit/certain phase and before the LLM phase.

This spec depends on the taxonomy-governance model in:
1. [pdp-taxonomy-governance.md](../../../docs/specs/pdp_taxonomy_governance/pdp-taxonomy-governance.md)

The goal is not to replace the explicit phase. The goal is to make deterministic trusted locking safe enough that it can keep its current pipeline role:
1. explicit/certain stage resolves only approved high-certainty phrases
2. deterministic trusted stage resolves only active canonical values covered by reviewed policy
3. LLM resolves only remaining unresolved attributes

## 2. Relationship To The Explicit/Certain Phase
The explicit/certain phase and deterministic trusted phase are adjacent but different governance layers.

Explicit/certain phase:
1. configuration lives in `config/pdp_explicit_declaration_rules.json`
2. match unit is a reviewed phrase or regex certainty signal
3. behavior is deny-by-default and precision-first

Deterministic trusted phase:
1. configuration lives in `attribute_taxonomy.json`
2. match unit is a taxonomy value plus its deterministic policy
3. behavior is opt-in and source-aware

Core rule:
1. explicit/certain governs exact high-certainty wording
2. deterministic trusted governs whether an active canonical value may lock from non-explicit deterministic evidence

## 3. Why A Separate Policy Layer Is Needed
Plain `synonyms` are not sufficient for deterministic locking.

Reason:
1. `synonyms` describe meaning
2. deterministic locking needs reviewed evidence rules

Example:
1. `finish=matte` may be safe with `matte finish`
2. `form=oil` is not safe as a bare token, even if `oil` is semantically related to the value

Therefore:
1. taxonomy keeps semantic `synonyms`
2. deterministic trusted uses separate `deterministic_aliases`

## 4. Placement In The Existing Taxonomy Shape
Current taxonomy shape is:
1. category
2. attribute
3. node or child leaf

The deterministic policy extension must follow that shape.

This policy layer is in addition to leaf governance fields defined by taxonomy governance.

Attribute-level additions:
1. `deterministic_policy`

Leaf-level additions:
1. `deterministic_aliases`
2. `deterministic_policy_override`

Parent nodes with `children` remain structure-only and must not carry leaf deterministic policy fields.

## 5. Proposed Data Model
### 5.1 Attribute-level policy
Example:

```json
{
  "id": "finish",
  "label": "finish",
  "hierarchical": false,
  "levels": 1,
  "selection": "single",
  "scope": "product",
  "kind": "performance",
  "deterministic_policy": {
    "mode": "trusted",
    "allow_bare_label": false,
    "safe_sources": [
      "title",
      "summary",
      "features",
      "description_short",
      "description_long",
      "description_markdown",
      "variant_name"
    ],
    "blocked_sources": [
      "ingredients",
      "reviews",
      "usage",
      "restrictions"
    ],
    "required_context_any": [],
    "negative_patterns": [],
    "conflict_behavior": "na"
  }
}
```

### 5.2 Leaf-level policy
Example:

```json
{
  "id": "matte",
  "label": "Matte",
  "synonyms": ["matte look"],
  "deterministic_aliases": [
    "matte finish",
    "soft matte",
    "velvet matte"
  ],
  "deterministic_policy_override": {
    "allow_bare_label": true
  }
}
```

Example for a risky value:

```json
{
  "id": "oil",
  "label": "Oil",
  "synonyms": [],
  "deterministic_aliases": [
    "lip oil",
    "body oil",
    "primer oil",
    "cleansing oil"
  ],
  "deterministic_policy_override": {
    "mode": "phrase_only",
    "allow_bare_label": false,
    "safe_sources": [
      "title",
      "summary",
      "features",
      "variant_name"
    ],
    "blocked_sources": [
      "ingredients",
      "reviews",
      "usage",
      "restrictions",
      "description_long"
    ],
    "negative_patterns": [
      "seed oil",
      "contains oil",
      "oil complex"
    ]
  }
}
```

## 6. Policy Fields
Shared object shape for both `deterministic_policy` and `deterministic_policy_override`:

1. `mode`
2. `allow_bare_label`
3. `safe_sources`
4. `blocked_sources`
5. `required_context_any`
6. `negative_patterns`
7. `conflict_behavior`

### 6.1 `mode`
Allowed values:
1. `off`
2. `explicit_only`
3. `phrase_only`
4. `trusted`

Meaning:
1. `off`: deterministic trusted never assigns this value
2. `explicit_only`: only the explicit/certain phase may lock this value
3. `phrase_only`: only reviewed `deterministic_aliases` may match
4. `trusted`: reviewed `deterministic_aliases` may match, and bare-label matching may also be allowed if explicitly enabled

### 6.2 `allow_bare_label`
Type:
1. boolean

Meaning:
1. controls whether the leaf label itself may match directly
2. this should default to `false` for risky or overloaded values

### 6.3 `safe_sources`
Type:
1. list of source-channel ids

Meaning:
1. deterministic trusted may use only these channels when they are present

### 6.4 `blocked_sources`
Type:
1. list of source-channel ids

Meaning:
1. matches from these channels are always ignored

### 6.5 `required_context_any`
Type:
1. list of normalized context tokens

Meaning:
1. at least one listed context token must be present near the candidate match
2. this is intended for overloaded values that need local semantic anchoring

### 6.6 `negative_patterns`
Type:
1. list of normalized strings

Meaning:
1. if a local false-positive pattern matches, the candidate match is rejected

### 6.7 `conflict_behavior`
Allowed values:
1. `na`

Meaning:
1. if multiple values for the same attribute survive deterministic trusted matching, the result is `N/A`

## 7. Effective Policy Resolution
For one `(category, attribute, value)`:
1. verify that the leaf is `status=active`
2. start from attribute `deterministic_policy`
3. merge in leaf `deterministic_policy_override`
4. use leaf `deterministic_aliases` as the reviewed phrase set
5. if no effective policy exists after inheritance, deterministic trusted must not lock the value

Default interpretation:
1. no policy does not mean manual product review
2. no policy means deterministic trusted skips the value
3. unresolved rows continue to the LLM phase

## 8. Runtime Contract
For each candidate value during deterministic trusted classification:
1. build effective policy
2. if the leaf is not active, skip
3. if `mode=off`, skip
4. if `mode=explicit_only`, skip
5. collect candidate evidence only from allowed source channels
6. reject candidate evidence from blocked source channels
7. apply `negative_patterns`
8. if `mode=phrase_only`, allow only `deterministic_aliases`
9. if `mode=trusted`, allow `deterministic_aliases`, and allow bare label only when `allow_bare_label=true`
10. if more than one value survives for the same attribute, return `N/A`
11. only unresolved attributes continue to the LLM phase

## 9. Validation Rules
The taxonomy validator must enforce the following:
1. `deterministic_policy` is allowed only on attributes
2. `deterministic_aliases` is allowed only on leaf nodes
3. `deterministic_policy_override` is allowed only on leaf nodes
4. parent nodes with `children` must not carry `deterministic_aliases`
5. parent nodes with `children` must not carry `deterministic_policy_override`
6. `unknown` and `other` leaves must not carry deterministic aliases or overrides
7. `safe_sources` and `blocked_sources` must use only approved source-channel ids
8. `safe_sources` and `blocked_sources` must not overlap
9. `mode=phrase_only` requires `allow_bare_label=false`

Runtime rule in addition to validation:
1. deterministic trusted must ignore non-active leaves even if they carry deterministic draft config
10. `mode=phrase_only` requires non-empty `deterministic_aliases`
11. `negative_patterns` must be non-empty strings after normalization
12. `deterministic_aliases` must be normalized, deduplicated, and lowercased using the same token normalization discipline used for `synonyms`

## 10. Pydantic Model Extension
The following model additions are expected in `modules/add_attributes/taxonomy_schema.py`.

Example shape:

```python
from typing import Literal

DeterministicMode = Literal["off", "explicit_only", "phrase_only", "trusted"]
ConflictBehavior = Literal["na"]
SourceChannel = Literal[
    "title",
    "summary",
    "features",
    "description_short",
    "description_long",
    "description_markdown",
    "variant_name",
    "variant_description",
    "ingredients",
    "usage",
    "restrictions",
    "reviews",
]


class DeterministicPolicy(BaseModel):
    mode: DeterministicMode | None = None
    allow_bare_label: bool | None = None
    safe_sources: list[SourceChannel] | None = None
    blocked_sources: list[SourceChannel] | None = None
    required_context_any: list[str] | None = None
    negative_patterns: list[str] | None = None
    conflict_behavior: ConflictBehavior | None = None
```

Then:
1. add `deterministic_policy: DeterministicPolicy | None = None` to `Attribute`
2. add `deterministic_aliases: list[str] | None = None` to `Node`
3. add `deterministic_policy_override: DeterministicPolicy | None = None` to `Node`

## 11. Canonicalization Requirements
`canonicalize_branch(...)` currently rebuilds taxonomy branches from a fixed set of known keys.

Therefore implementation must also:
1. preserve attribute `deterministic_policy`
2. preserve leaf `deterministic_aliases`
3. preserve leaf `deterministic_policy_override`
4. normalize `deterministic_aliases` using the same synonym token normalization rules
5. strip leaf deterministic fields from parent nodes during canonicalization

## 12. Why This Is Consistent With The Explicit/Certain Phase
The explicit/certain phase and deterministic trusted phase should feel like one review system with two adjacent tabs:
1. `Certain Rules` tab manages approved certainty phrases and regex rules
2. `Deterministic Policy` tab manages attribute defaults, deterministic aliases, and risky-value overrides

This is consistent because both phases are:
1. source-aware
2. review-before-publish
3. versioned
4. previewable before release

## 13. MVP Rollout Rule
Recommended initial rollout:
1. introduce the schema and validator support first
2. keep a strict default: no effective policy means no deterministic trusted lock
3. seed only a small number of safe attributes first, for example `finish`
4. move hard-coded risky-token exceptions, such as the current `oil` safeguard, into taxonomy policy

## 14. Non-Goals
This schema does not introduce:
1. manual per-product adjudication
2. a requirement that all values be policy-authored before the pipeline can run
3. any replacement of the explicit/certain phase
4. any replacement of the LLM phase

Unconfigured values simply bypass deterministic trusted and continue to the LLM phase.

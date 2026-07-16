# PDP Source Channels Spec

Status: Draft proposal (as of 2026-03-11).

## 1. Objective
Define a stable source-channel vocabulary for PDP text used by:
1. explicit/certain deterministic classification
2. deterministic trusted classification
3. LLM classification

The source-channel model exists to prevent a single flattened PDP text blob from being reused for all phases.

## 2. Problem Statement
The current PDP export path flattens most scraped text into:
1. parent `description`
2. variant `variant_description`

This loses provenance too early.

That creates three problems:
1. explicit/certain rules cannot fully exploit path-specific logic
2. deterministic trusted cannot safely block noisy channels like reviews or ingredients
3. LLM receives the same blob shape that deterministic used, which reduces phase separation

## 3. Principles
1. extraction must preserve source provenance until after deterministic classification
2. explicit/certain and deterministic trusted must operate on structured channels, not a merged blob
3. the LLM may receive a separately curated merged prompt view
4. source names must be stable and versioned because they become taxonomy policy keys

## 4. Source-Channel Vocabulary
The canonical channel ids are:
1. `title`
2. `summary`
3. `features`
4. `description_short`
5. `description_long`
6. `description_markdown`
7. `variant_name`
8. `variant_description`
9. `ingredients`
10. `usage`
11. `restrictions`
12. `reviews`

## 5. Channel Definitions
### 5.1 `title`
Meaning:
1. main product title
2. parent title or merged brand plus product display title when used for matching

Typical precision:
1. high

### 5.2 `summary`
Meaning:
1. short marketing summary
2. one or two sentence overview copy

Typical precision:
1. medium to high

### 5.3 `features`
Meaning:
1. feature bullets
2. highlight bullets
3. key benefit bullet lists

Typical precision:
1. high

### 5.4 `description_short`
Meaning:
1. short body description
2. compact narrative description presented as short PDP copy

Typical precision:
1. medium

### 5.5 `description_long`
Meaning:
1. long-form narrative description
2. richer body copy that may contain more marketing language and weaker phrasing

Typical precision:
1. medium to low for deterministic trusted

### 5.6 `description_markdown`
Meaning:
1. cleaned rich-text body description from retailer payloads
2. formatted description sections preserved as normalized text

Typical precision:
1. medium

### 5.7 `variant_name`
Meaning:
1. shade name
2. variant display name
3. size or variant label when it is part of the commercial variant identity

Typical precision:
1. high for variant-sensitive attributes

### 5.8 `variant_description`
Meaning:
1. variant-specific marketing copy
2. variant-specific PDP text not already represented by `variant_name`

Typical precision:
1. medium

### 5.9 `ingredients`
Meaning:
1. ingredient deck only
2. INCI or ingredient composition list

Typical precision:
1. low for general deterministic locking

### 5.10 `usage`
Meaning:
1. how-to-use
2. application instructions

Typical precision:
1. low to medium depending on attribute family

### 5.11 `restrictions`
Meaning:
1. warnings
2. restrictions
3. regulatory or safety disclaimers not intended as product marketing claims

Typical precision:
1. low for general deterministic locking

### 5.12 `reviews`
Meaning:
1. user review text
2. review-derived summary text
3. positive or negative review summaries

Typical precision:
1. low for deterministic locking

## 6. Structured Extraction Contract
The extraction layer should produce a structured payload rather than a single concatenated blob.

Parent example:

```json
{
  "title": "Acceptance Speech Shimmering Hydrating Lip Gloss",
  "summary": "Hydrating shimmer gloss with glass-like shine.",
  "features": [
    "Glass-like shine",
    "Comfortable wear"
  ],
  "description_markdown": "A hydrating gloss with shimmer payoff.",
  "description_short": "",
  "description_long": "",
  "ingredients": "Polybutene, jojoba oil, ...",
  "usage": "Apply directly to lips.",
  "restrictions": "",
  "reviews": [
    "Feels matte after two hours for me."
  ]
}
```

Variant example:

```json
{
  "variant_name": "Trophy (clear with warm gold shimmer)",
  "variant_description": "Warm gold shimmer variant."
}
```

## 7. Flattened Views By Pipeline Phase
Each phase may still receive a flattened text view, but it must be derived from the structured channels according to phase-specific rules.

### 7.1 Explicit/Certain phase
Input form:
1. source-preserving segments
2. each segment carries both channel id and text

Reason:
1. explicit rules may use path-aware constraints such as `required_path_tokens`

### 7.2 Deterministic trusted phase
Input form:
1. source-preserving segments
2. no single merged blob as the primary match surface

Reason:
1. value policy needs `safe_sources` and `blocked_sources`
2. risky channels such as `reviews` and `ingredients` must be suppressible

### 7.3 LLM phase
Input form:
1. curated merged prompt text
2. optionally accompanied by structured channel metadata

Reason:
1. the LLM can benefit from broader context
2. that broader context should not automatically be reused as deterministic evidence

## 8. Default Channel Policy By Phase
### 8.1 Explicit/Certain
Default treatment:
1. all source-preserving channels are visible
2. rule-level filters decide where a phrase is allowed

### 8.2 Deterministic trusted
Recommended defaults:
1. preferred: `title`, `summary`, `features`, `description_markdown`, `description_short`, `variant_name`
2. more restricted: `description_long`, `variant_description`
3. blocked by default for most attributes: `ingredients`, `reviews`, `usage`, `restrictions`

### 8.3 LLM
Recommended defaults:
1. may use all curated channels except channels explicitly deemed too noisy or operationally irrelevant
2. final prompt shaping should be independent from deterministic trusted policy

## 9. Current-Implementation Gap
The current PDP export code still collapses early into broad description strings.

That means the source-channel model is not fully available yet.

Implementation must replace early flattening with channel-preserving extraction before:
1. explicit/certain classification
2. deterministic trusted classification

The LLM prompt builder may still create its own merged context later.

## 10. Guidance For Initial Mapping From Existing Retailer Payloads
Examples of likely mappings:

1. retailer title field -> `title`
2. short summary copy -> `summary`
3. feature bullet arrays -> `features`
4. cleaned HTML rich description -> `description_markdown`
5. short description string -> `description_short`
6. long description string -> `description_long`
7. ingredient deck -> `ingredients`
8. how-to-use text -> `usage`
9. warnings and restrictions -> `restrictions`
10. review arrays and review summaries -> `reviews`
11. shade name and commercial variant label -> `variant_name`
12. variant-level descriptive copy -> `variant_description`

## 11. Non-Goals
This vocabulary does not require:
1. every retailer adapter to populate every channel
2. identical retail payload shapes
3. immediate removal of all legacy flat text fields

It does require:
1. a stable normalized channel id set
2. source preservation until deterministic classification completes

## 12. Documentation Dependency
This source-channel vocabulary is a prerequisite for:
1. deterministic trusted taxonomy policy
2. deterministic trusted UI controls for source allow/block lists
3. preview tooling that explains why a deterministic trusted match did or did not fire

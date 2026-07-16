# PDP Deterministic Policy UI Spec

Status: Draft proposal (as of 2026-03-11).

## 1. Objective
Define a review UI for deterministic trusted policy that is consistent with the existing explicit/certain review workflow.

This UI must also remain consistent with taxonomy governance, because deterministic trusted is meaningful only for active canonical leaves.

The UI must support:
1. editing attribute-level deterministic defaults
2. editing leaf-level deterministic aliases
3. editing leaf-level deterministic overrides
4. previewing impact before publish
5. validating and versioning changes

## 2. Consistency With The Explicit/Certain Phase
This UI is not a separate product. It is the companion governance surface for the explicit/certain phase.

The explicit/certain phase already has:
1. a review page
2. validation
3. publish
4. version history
5. audit

Deterministic trusted should use the same review philosophy:
1. review-before-publish
2. validation-before-publish
3. versioned release
4. audit log
5. preview of impact

Recommended navigation model:
1. one review area
2. three adjacent tabs

Tabs:
1. `Taxonomy`
2. `Certain Rules`
3. `Deterministic Policy`

Ordering rule:
1. taxonomy decides which leaves are active canonical targets
2. certain rules target active canonical leaves
3. deterministic policy governs trusted locking for active canonical leaves

## 3. Information Architecture
### 3.1 Top-level layout
The review page should have:
1. page header and shared navigation
2. left-side filter rail or top filter bar
3. main editor panel
4. preview panel
5. validation and publish panel
6. audit and version history panel

### 3.2 Shared filters
The following filters should be shared with the explicit/certain tab:
1. category
2. attribute
3. value
4. search token

## 4. Primary UI Objects
### 4.1 Taxonomy governance editor
Editable fields:
1. `status`
2. `governance_action`
3. `successor_leaf_ids`
3. `governance_reason`

Purpose:
1. control whether a leaf is an active runtime target
2. support deprecation and merge workflows
3. prevent certain rules and deterministic policy from targeting unstable leaves

Preferred interaction model:
1. operators should act through business actions, not raw schema fields
2. primary actions:
   `Keep active`, `Needs review`, `Merge into...`, `Split into...`, `Mark draft`
3. the UI may still persist `status`, `governance_action`, and `successor_leaf_ids`, but those are implementation details
4. `Split into...` must be disabled for `selection=single` attributes

### 4.2 Active-target banner
When a selected leaf is not active, show a blocking banner in the `Certain Rules` and `Deterministic Policy` tabs.

Behavior:
1. show current leaf status
2. show replacement leaf when configured
3. prevent publish of rules or deterministic policy that would target a non-active leaf

### 4.3 Attribute default policy editor
Editable fields:
1. `mode`
2. `allow_bare_label`
3. `safe_sources`
4. `blocked_sources`
5. `required_context_any`
6. `negative_patterns`
7. `conflict_behavior`

Purpose:
1. define the baseline deterministic trusted behavior for all active leaves under the attribute

### 4.4 Leaf editor
Editable fields:
1. `label`
2. `synonyms` as read-only or lightly editable semantic data
3. `deterministic_aliases`
4. `deterministic_policy_override`

Purpose:
1. define risky-value or special-case behavior without copying the full attribute policy to every leaf

### 4.5 Preview panel
The preview panel is mandatory.

It should show:
1. products that would newly lock after the draft change
2. products that would stop locking after the draft change
3. products that remain unchanged
4. source channel of the matched evidence
5. exact alias or bare-label evidence used
6. blocked matches that were intentionally suppressed
7. conflict cases that resolve to `N/A`

For the taxonomy tab specifically, the first mandatory preview is classifier safety:
1. explicit rules that would become newly invalid under the draft taxonomy
2. newly invalid active explicit rules count
3. the exact impacted rule ids and target values
4. the reason for invalidation, such as `inactive_canonical_value`

Publish behavior:
1. if preview shows newly invalid active explicit rules, `Publish` must stay blocked until the reviewer acknowledges that impact
2. if publish is attempted without acknowledgement, the API must return the same impact payload so the UI can render it directly
3. deterministic-policy impact preview can be added later, but it should follow the same pattern

## 5. Recommended Screen Model
### 5.1 Entry screen
Default state:
1. category selector
2. attribute list
3. selected attribute summary
4. taxonomy status summary
5. current published policy summary
6. draft editor

### 5.2 Attribute drill-in
For one selected attribute, show:
1. attribute metadata
2. active-target summary
3. default deterministic policy
4. leaf grid
5. preview summary tiles

### 5.3 Leaf drill-in
For one selected leaf, show:
1. label and taxonomy path
2. lifecycle status
3. current effective policy
4. inherited fields versus overridden fields
5. deterministic aliases
6. sample matches and sample blocked cases

## 6. Draft Versus Published Model
The UI must clearly separate:
1. published configuration
2. editable draft configuration

Recommended behavior:
1. open page with the currently published deterministic policy draft source
2. allow in-browser editing
3. validate draft without publishing
4. preview draft impact without publishing
5. publish only after validation succeeds

The same published-versus-draft separation should apply to taxonomy governance state.

## 7. Preview Requirements
Preview is the most important safety feature for deterministic trusted.

### 7.1 Required preview outputs
For each draft change:
1. count of newly deterministic-locked rows
2. count of rows no longer locked
3. count of rows now resolving to conflict and therefore `N/A`
4. count of blocked-source matches suppressed by the draft
5. top changed values by category and attribute

For taxonomy changes, also show:
1. leaves entering the active target set
2. leaves leaving the active target set
3. explicit rules invalidated by the draft
4. deterministic policies rendered inactive by the draft

### 7.2 Row-level preview data
For row-level examples, show:
1. retailer
2. parent product id
3. variant id if applicable
4. matched channel
5. matched snippet
6. matched value
7. whether the match came from alias or bare label
8. whether the row would newly lock or stop locking

### 7.3 Comparison mode
Preview should compare:
1. current published effective policy
2. current draft effective policy

This is more useful than previewing draft behavior in isolation.

## 8. Validation Requirements
The UI should surface validation errors before publish.

Validation should include:
1. schema validation
2. enum validation
3. source overlap validation
4. forbidden parent-node deterministic fields
5. reserved-leaf protection
6. `phrase_only` with missing aliases
7. illegal bare-label settings
8. non-active leaf target protection for certain rules and deterministic policy
9. replacement-leaf validation for taxonomy changes

Validation UX:
1. show blocking errors in a dedicated panel
2. show non-blocking warnings separately
3. allow publish only when there are no blocking errors

## 9. Publish Workflow
### 9.1 Publish inputs
The publish action should capture:
1. actor
2. publish note
3. config version
4. generated timestamp

### 9.2 Publish outputs
On publish, store:
1. published version
2. published timestamp
3. actor
4. note
5. diff summary
6. serialized config snapshot

### 9.3 Diff summary
Minimum diff summary fields:
1. previous version
2. current version
3. attributes changed
4. leaves changed
5. aliases added or removed
6. policy overrides added, removed, or updated
7. taxonomy lifecycle changes

## 10. Audit Requirements
The deterministic trusted UI should have an audit panel similar to the explicit/certain workflow.

Audit entries should include:
1. timestamp
2. actor
3. action
4. category
5. attribute
6. leaf when applicable
7. change summary

Example actions:
1. `leaf_status_updated`
2. `leaf_replacement_updated`
3. `taxonomy_config_published`
4. `attribute_policy_updated`
5. `leaf_alias_added`
6. `leaf_alias_removed`
7. `leaf_override_updated`
8. `config_published`

## 11. Version History Requirements
The version history panel should show:
1. version
2. published timestamp
3. actor
4. note
5. changed attribute count
6. changed leaf count
7. changed lifecycle count

Optional future enhancement:
1. rollback or re-publish from a prior version

## 12. API Shape
Recommended sibling API surface to the existing explicit rules API:
1. `GET /review/taxonomy/config`
2. `POST /review/taxonomy/config/validate`
3. `POST /review/taxonomy/config/publish`
4. `GET /review/taxonomy/audit`
5. `POST /review/taxonomy/preview/attribute`
6. `GET /review/deterministic-policy/config`
7. `POST /review/deterministic-policy/config/validate`
8. `POST /review/deterministic-policy/config/publish`
9. `GET /review/deterministic-policy/audit`
10. `POST /review/deterministic-policy/preview/attribute`
11. `POST /review/deterministic-policy/preview/value`

Reason:
1. taxonomy governance must be publishable and auditable in the same review surface
2. deterministic trusted deserves the same governance pattern as explicit/certain
3. keeping sibling APIs avoids overloading the explicit-rule endpoints with multiple config models

## 13. UI Consistency Rules
To stay consistent with the explicit/certain phase:
1. reuse the same page shell and navigation style
2. reuse filter behavior where possible
3. reuse validation and publish interaction patterns
4. reuse version-history and audit presentation patterns
5. keep terminology stable across tabs

Stable terminology:
1. `Taxonomy`
2. `Certain Rules`
3. `Deterministic Policy`
4. `Validate`
5. `Preview`
6. `Publish`
7. `Versions`
8. `Audit`

## 14. Important UX Distinctions
The UI must clearly distinguish:
1. semantic `synonyms`
2. reviewed `deterministic_aliases`

Why:
1. `synonyms` express meaning
2. `deterministic_aliases` express phrases trusted enough to lock before the LLM phase

The editor should not present these two concepts as interchangeable.

## 15. MVP UX Scope
In scope for MVP:
1. attribute policy editor
2. leaf aliases editor
3. leaf override editor
4. preview diff against current publish
5. validation
6. publish
7. audit and version history

Out of scope for MVP:
1. per-product manual adjudication
2. inline taxonomy restructuring
3. advanced rollback workflow
4. automated recommendation of deterministic aliases

## 16. Why This Is Compatible With Scale
This UI is designed for governing reusable rules, not for reviewing thousands of products one by one.

Human work happens at:
1. attribute level
2. leaf value level
3. publish level

The pipeline still classifies product rows automatically.

# PDP Taxonomy And Deterministic Process Design

Status: Draft reset proposal (as of 2026-03-12).

## 1. Objective
Define one coherent process for:
1. maintaining the existing PDP taxonomy
2. proposing and applying taxonomy changes
3. generating and maintaining deterministic matching behavior
4. keeping taxonomy, deterministic policy, and explicit/certain rules consistent

This document is intentionally practical.

It is not a generic governance framework.
It is a process design for getting taxonomy and deterministic mapping into a state that can be improved step by step without drifting.

## 2. Problem To Solve
The current problem is not only deterministic precision.

The system must answer two connected questions:
1. what are the correct canonical taxonomy values?
2. how may those values be matched deterministically?

If the taxonomy is wrong, deterministic can become more precise at producing the wrong answer.
If deterministic behavior is unmanaged, a correct taxonomy still produces unstable locking before the LLM stage.

So the process must cover both together.

## 3. Existing Facts
1. There is already a large taxonomy JSON file.
2. That taxonomy file is the current semantic source of truth.
3. Deterministic mapping runs before the LLM pass and can lock values.
4. The explicit/certain stage already exists as a separate rule layer.
5. The user must not be expected to review 1000 leaves one by one.

## 4. Core Principles
1. Design the whole process coherently before implementing more pieces.
2. Keep the published taxonomy file clean and canonical.
3. Do not store workflow status concepts such as `needs_review` inside the published taxonomy.
4. Workflow objects belong in a separate proposal system, not in the taxonomy file.
5. Synonyms are first-class and must be managed explicitly.
6. Deterministic behavior is conceptually tied to taxonomy, but should live in a separate artifact.
7. The human unit of work is a taxonomy change proposal, not a leaf.
8. System-suggested proposals and user-created proposals should use the same review model.
9. The UI should help decide concrete changes, not display abstract counters.
10. Publish-time validation must prevent taxonomy, deterministic policy, and explicit rules from drifting apart.

## 5. Canonical Artifacts
The system should have four published artifacts.

### 5.1 Published taxonomy
Purpose:
1. define the canonical semantic structure
2. define categories, attributes, values, hierarchy, and synonyms

This is the existing taxonomy JSON file.

The published taxonomy should contain only approved canonical state.
It should not contain review workflow metadata.

### 5.2 Taxonomy proposal queue
Purpose:
1. hold suggested and user-created taxonomy changes before they are applied
2. store evidence, rationale, and review outcome

This is a separate artifact from the published taxonomy.

### 5.3 Published deterministic policy
Purpose:
1. define how taxonomy values may match in deterministic classification
2. define attribute-level defaults
3. define value-level overrides where needed

This should be a separate artifact from the taxonomy file.

### 5.4 Published explicit/certain rules
Purpose:
1. define reviewed exact phrases or regexes for the explicit/certain stage

This remains separate.

## 6. What Belongs In Each Artifact
### 6.1 Published taxonomy contains
1. category ids and labels
2. attribute ids and labels
3. value ids and labels
4. hierarchy
5. synonyms
6. structural taxonomy decisions such as merge, split, rename, add, remove once approved and applied

### 6.2 Published taxonomy does not contain
1. workflow statuses such as `draft`, `needs_review`, `deprecated`
2. proposal review history
3. deterministic matching gates
4. UI-only counters or bookkeeping metadata

### 6.3 Deterministic policy contains
1. attribute-level deterministic defaults
2. optional value-level overrides
3. safe deterministic expressions
4. source restrictions
5. bare-token restrictions

### 6.4 Proposal queue contains
1. proposed taxonomy changes
2. proposal type
3. evidence
4. rationale
5. review state
6. impact preview

## 7. Stable Identity Model
Consistency depends on stable ids.

The process should treat:
1. category id
2. attribute id
3. value id

as the stable references across:
1. taxonomy
2. deterministic policy
3. explicit/certain rules
4. proposal queue

Labels and synonyms may change.
Ids should change only when the semantic object truly changes.

## 8. Taxonomy Proposal Model
The core workflow object is a taxonomy proposal.

It is not a leaf.
It is not an issue ticket in the narrow sense.
It is a proposed change to the taxonomy.

### 8.1 Proposal sources
1. system-suggested
2. user-created

### 8.2 Minimal proposal states
1. `open`
2. `approved`
3. `rejected`
4. `applied`

No extra lifecycle complexity is needed at first.

### 8.3 Proposal types
1. `merge_values`
2. `split_value`
3. `rename_value`
4. `add_value`
5. `remove_value`
6. `move_value`
7. `add_synonym`
8. `remove_synonym`
9. `move_synonym`
10. `change_attribute_structure`
11. `change_attribute_cardinality`

These are the real operations that matter.

## 9. Taxonomy Operations
### 9.1 Value-level operations
1. add leaf
2. merge leaf into another leaf
3. split one leaf into multiple leaves
4. rename leaf
5. remove leaf
6. move leaf under a different parent when hierarchy changes

### 9.2 Synonym-level operations
1. add synonym
2. remove synonym
3. move synonym from one value to another

This is essential.
Many taxonomy problems are actually synonym problems rather than value problems.

### 9.3 Attribute-level operations
1. change flat vs hierarchical structure
2. change parent/child layout
3. change single vs multi-select

Some value fixes are impossible without attribute-level changes.

## 10. Proposal Evidence
Every proposal must carry enough context for a decision.

At minimum:
1. category
2. attribute
3. affected value(s)
4. parent path if hierarchical
5. labels
6. synonyms
7. sibling values
8. reason the proposal exists
9. product/example evidence when available
10. estimated impact

The system should not ask the user to decide anything without showing what the value means.

## 11. How Proposals Are Created
There are two creation paths.

### 11.1 User-created proposals
Examples:
1. split `Red and Pink` into `Red` and `Pink`
2. merge `oil` and `lotion` into `liquid`
3. move a synonym from one value to another

These do not require the system to have detected a problem first.

### 11.2 System-suggested proposals
These are generated from signals such as:
1. same term mapped to multiple values within the same attribute
2. overlapping synonym sets
3. mixed granularity among sibling values
4. composite-looking labels
5. low-usage or zero-usage values
6. high mapping confusion around the same values
7. repeated disagreement between deterministic and LLM outputs

The reviewer should work through ranked proposals, not the full taxonomy.

## 12. Proposal Queue Design
The UI should center on a queue of proposals, not on raw leaf browsing.

### 12.1 Queue behavior
1. show ranked suggested proposals
2. allow direct creation of a new proposal
3. filter by category, attribute, proposal type, and impact
4. let the user open one proposal and decide it

### 12.2 Queue item contents
Each queue item should show:
1. type of proposal
2. affected taxonomy location
3. short reason
4. impact estimate
5. whether it is user-created or system-suggested

### 12.3 Proposal detail page
The detail page should show:
1. current taxonomy state
2. proposed taxonomy state
3. labels and synonyms
4. sibling context
5. examples and usage
6. downstream impacts
7. action controls

This is the real review experience.

## 13. Deterministic Policy Artifact
The deterministic policy must be designed together with taxonomy, but stored separately.

### 13.1 Why it is separate
1. taxonomy expresses semantics
2. deterministic policy expresses matching behavior
3. mixing them in one large file makes review and maintenance harder

### 13.2 What it contains
1. attribute-level deterministic defaults
2. optional value-level overrides
3. source allow/block rules
4. safe deterministic expressions
5. ambiguous-token restrictions

### 13.3 What it references
It references taxonomy ids:
1. category id
2. attribute id
3. value id

## 14. How The Deterministic Policy Is Created
This must be operational, not theoretical.

### 14.1 Bootstrap
The first deterministic policy artifact should be created from the published taxonomy ids.

Initial bootstrap rule:
1. create entries at the attribute level
2. start with defaults only
3. do not require custom leaf-level configuration for every value
4. add value-level overrides only for exceptional or risky values

This keeps the artifact manageable.

### 14.2 Authoring model
Humans do not hand-write 1000 leaf policies.

The normal pattern is:
1. attribute-level default policy
2. small number of value-level overrides

### 14.3 Maintenance after taxonomy changes
When a taxonomy proposal is approved and applied:
1. deterministic policy must be revalidated
2. affected references must be shown
3. merge, split, rename, add, and remove must all have defined handling

Examples:
1. merge: source value overrides may be dropped or manually reassigned to the target
2. split: source value overrides must not be copied blindly; reviewer decides how they map to the new values
3. rename: if id stays stable, policy reference survives unchanged

## 15. Relationship To Explicit/Certain Rules
Explicit/certain rules remain a separate artifact.

They depend on taxonomy in the same way deterministic policy does:
1. rule targets must reference existing taxonomy values
2. taxonomy changes must trigger validation of affected rules

The important distinction is:
1. taxonomy defines what values exist
2. explicit rules define exact high-certainty phrases
3. deterministic policy defines broader deterministic behavior

## 16. Publish And Validation Workflow
The system should publish only consistent sets of artifacts.

### 16.1 Before taxonomy apply
Validate:
1. taxonomy structure after the proposed change
2. synonym consistency
3. hierarchy/cardinality rules
4. deterministic policy references that would break
5. explicit/certain rules that would break

### 16.2 After taxonomy apply
1. update published taxonomy
2. update deterministic policy references where safe
3. require human resolution where not safe
4. validate explicit/certain rules
5. publish the new consistent set

### 16.3 Runtime rule
Runtime should use only published artifacts, not draft proposals.

## 17. Operational Companion
The operational companion for:
1. deterministic-policy artifact details
2. candidate generation
3. evidence contract
4. review workflows
5. hard gating rules

is here:
1. [pdp-taxonomy-and-deterministic-operational-workflow.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-operational-workflow.md)

## 17. Runtime Mapping Pipeline
The intended runtime order is:
1. published taxonomy defines the valid target set
2. explicit/certain rules run first
3. deterministic matching runs second using published deterministic policy
4. LLM handles unresolved cases

The design of deterministic policy and source-channel handling must remain aligned with this order.

## 18. Minimum Viable UI
The first useful UI should support only what is needed to operate the process.

### 18.1 Required
1. proposal queue
2. create proposal
3. proposal detail with labels and synonyms
4. impact preview
5. approve/reject/apply

### 18.2 Explicitly not required
1. generic lifecycle dashboards
2. abstract counters such as total active leaves
3. leaf-by-leaf review of the full taxonomy
4. generic governance language

## 19. Phased Implementation
The design should be implemented in phases, but the design itself should be complete.

### Phase 1
1. finalize the object model
2. keep the published taxonomy file clean
3. define proposal types and evidence requirements
4. define deterministic policy artifact shape
5. define cross-artifact validation rules

### Phase 2
1. build a minimal proposal queue
2. support user-created proposals first
3. support proposal apply to the taxonomy file
4. add deterministic-policy validation against taxonomy

### Phase 3
1. add system-suggested proposals
2. add richer impact previews
3. add deterministic-policy editing and migration support

## 20. Rejected Design Choices
The following are explicitly rejected for this process:
1. reviewing the taxonomy by browsing all leaves
2. storing workflow statuses inside the published taxonomy
3. a generic taxonomy governance console as the primary workflow
4. asking the user to edit a leaf without showing its synonyms and semantic context
5. requiring manual per-value deterministic configuration for the whole taxonomy

## 21. Practical Test For Whether The Design Is Working
The process is working if:
1. a user can create a proposal like “split `Red and Pink` into `Red` and `Pink`”
2. a user can create a proposal like “merge `oil` and `lotion` into `liquid`”
3. the proposal shows enough context to decide it
4. applying the proposal updates taxonomy consistently
5. deterministic policy and explicit rules are validated against the change
6. no one has to browse 1000 leaves to find the next useful task

## 22. Immediate Next Step
Before any more code or UI work:
1. review this process design
2. tighten the core objects if needed
3. agree the minimum proposal types and evidence fields
4. only then inspect the existing taxonomy file against the agreed design

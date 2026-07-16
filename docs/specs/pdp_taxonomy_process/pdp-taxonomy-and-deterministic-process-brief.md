# PDP Taxonomy And Deterministic Process Brief

Status: Draft reset brief (as of 2026-03-12).

## 1. Goal
Build one consistent process for:
1. keeping the taxonomy correct
2. keeping deterministic matching aligned with the taxonomy
3. allowing step-by-step implementation without drifting

## 2. Core Decision
The system needs three different published artifacts:
1. the existing taxonomy file
2. a separate deterministic policy artifact
3. explicit/certain rules

And one workflow artifact:
1. a taxonomy proposal queue

## 3. Existing Taxonomy File
The existing taxonomy file remains the canonical semantic source of truth.

It should contain only:
1. categories
2. attributes
3. values
4. hierarchy
5. synonyms
6. approved structural changes once applied

It should not contain:
1. review workflow statuses
2. temporary notes
3. deterministic matching gates
4. UI bookkeeping counters

## 4. Deterministic Policy Artifact
Deterministic behavior should be stored separately from the taxonomy file.

Reason:
1. taxonomy describes meaning
2. deterministic policy describes matching behavior

The deterministic policy should contain:
1. attribute-level defaults
2. optional value-level overrides
3. safe deterministic expressions
4. source allow/block rules
5. ambiguity restrictions

It should reference taxonomy ids:
1. category id
2. attribute id
3. value id

## 5. Unit Of Work
The user should not review 1000 leaves one by one.

The unit of work is a taxonomy proposal.

Proposal sources:
1. user-created
2. system-suggested

Minimal proposal states:
1. `open`
2. `approved`
3. `rejected`
4. `applied`

## 6. Proposal Types
The process must support at least:
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

## 7. Synonyms Are First-Class
Synonym management is not a minor detail.

Many taxonomy problems are actually synonym problems, not value problems.

So the process must support:
1. adding synonyms
2. removing synonyms
3. moving a synonym from one value to another

## 8. Evidence Required For A Decision
No proposal should be decided without context.

At minimum, each proposal must show:
1. category
2. attribute
3. affected value(s)
4. labels
5. synonyms
6. sibling values
7. parent path if relevant
8. reason for the proposal
9. product/example evidence when available
10. expected impact

## 9. How Proposals Enter The System
### 9.1 User-created examples
1. split `Red and Pink` into `Red` and `Pink`
2. merge `oil` and `lotion` into `liquid`
3. move a synonym from one value to another

### 9.2 System-suggested examples
1. same term appears under multiple values in the same attribute
2. overlapping synonym sets
3. mixed granularity in sibling values
4. composite-looking labels
5. low-usage values
6. repeated mapping confusion

## 10. UI Principle
The UI should be a proposal workflow, not a generic taxonomy console.

The minimum useful UI is:
1. proposal queue
2. create proposal
3. proposal detail page
4. impact preview
5. approve / reject / apply

The UI should not be:
1. a leaf browser over the whole taxonomy
2. a dashboard of abstract counters
3. a page that edits leaves without showing synonyms

## 11. How Deterministic Policy Is Created
The deterministic policy must have an operational bootstrap path.

Initial rule:
1. start from the published taxonomy ids
2. create attribute-level defaults first
3. do not require per-value rules for the whole taxonomy
4. add value-level overrides only where needed

This keeps the first implementation manageable.

## 12. Cross-Artifact Consistency
Taxonomy, deterministic policy, and explicit rules must validate together.

When a taxonomy proposal is applied:
1. taxonomy is updated
2. deterministic policy references are revalidated
3. explicit-rule targets are revalidated
4. broken references must be resolved before publish

Runtime should use only published artifacts, never draft proposals.

## 13. Runtime Order
1. taxonomy defines valid values
2. explicit/certain rules run first
3. deterministic matching runs second
4. LLM handles unresolved cases

## 14. Immediate Next Step
Before more code or UI work:
1. review this brief
2. agree the core artifacts
3. agree the proposal types
4. agree the minimum evidence required
5. then inspect the current taxonomy file against the agreed design

## 15. Companion Document
Longer version:
1. [pdp-taxonomy-and-deterministic-process.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-process.md)

Operational companion:
1. [pdp-taxonomy-and-deterministic-operational-workflow.md](../../../docs/specs/pdp_taxonomy_process/pdp-taxonomy-and-deterministic-operational-workflow.md)

Shared evidence layer:
1. [pdp-shared-evidence-layer.md](../../../docs/specs/pdp_taxonomy_process/pdp-shared-evidence-layer.md)

# PDP Explicit Declaration - Execution Checklist v1

Status: Implementation snapshot (as of 2026-03-05)  
Spec: [pdp-explicit-declaration-classifier.md](../../../docs/specs/pdp_explicit_declaration_classifier/pdp-explicit-declaration-classifier.md)

## Status Legend
1. `[x]` completed and verified.
2. `[ ]` pending.

## Verified Test Snapshot (2026-03-05)
1. Command executed:
   - `pytest -q tests/modules/add_attributes/test_explicit_declaration_classifier.py tests/modules/add_attributes/test_pdp_attribute_export.py tests/modules/add_attributes/test_explicit_precision_metrics.py tests/modules/add_attributes/test_explicit_candidate_mining.py`
2. Result:
   - Run the current suite to obtain an up-to-date count.

## Non-Negotiable Design Gates (Release Blockers)
- [x] G1 `Deny by default`: without explicit approved signal, result is `N/A`.
- [x] G2 `Fail-fast validation`: schema/taxonomy/duplicate-id/regex/conflict checks block execution on error.
- [x] G3 `No weak activation`: broad ambiguous idioms cannot be activated without reviewer justification.
- [x] G4 `Conflict and negation safety`: conflicting or negated claims resolve to `N/A`.
- [x] G5 `Evidence required`: every positive explicit decision persists `rule_id` and snippet evidence.
- [x] G6 `Human publish gate`: `draft -> reviewed -> active`; auto-publish disabled.
- [x] G7 `Activation quality threshold`: minimum reviewed sample size and precision threshold enforced (defaults `30` samples and `0.98` precision).
- [x] G8 `Versioning and rollback`: published rulesets are versioned and reversible by re-publishing a stored version.
- [x] G9 `Attribute lock semantics`: explicit matched attributes are skipped by deterministic/LLM; explicit conflicts are skipped by deterministic and remain eligible for LLM.
- [x] G10 `Immediate explicit promotion`: explicit-resolved attributes bypass downstream multi-step promotion.

Release rule:
1. Feature is releasable when `G1..G10` are all checked.

## M1 Engine + Pipeline Integration (Completed)
Files:
1. [config/pdp_explicit_declaration_rules.json](../../../config/pdp_explicit_declaration_rules.json)
2. [config/pdp_explicit_declaration_rules.schema.json](../../../config/pdp_explicit_declaration_rules.schema.json)
3. [modules/add_attributes/explicit_declaration_classifier.py](../../../modules/add_attributes/explicit_declaration_classifier.py)
4. [modules/add_attributes/pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)
5. [tests/modules/add_attributes/test_explicit_declaration_classifier.py](../../../tests/modules/add_attributes/test_explicit_declaration_classifier.py)
6. [tests/modules/add_attributes/test_pdp_attribute_export.py](../../../tests/modules/add_attributes/test_pdp_attribute_export.py)

Checklist:
- [x] Implement explicit rules loader and validator.
- [x] Enforce taxonomy-safe rule/value checks.
- [x] Implement phrase/regex certainty matching with conflict => `N/A`.
- [x] Integrate explicit stage before deterministic stage.
- [x] Add fill-only merge preserving explicit non-placeholder values.
- [x] Add targeted unit/integration tests.

## M1b Attribute Lock + Immediate Promotion Semantics (Completed)
Files:
1. [modules/add_attributes/pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)
2. [tests/modules/add_attributes/test_pdp_attribute_export.py](../../../tests/modules/add_attributes/test_pdp_attribute_export.py)

Checklist:
- [x] Build per-row unresolved-attribute sets after explicit stage.
- [x] Exclude explicit-resolved attributes from deterministic query payloads.
- [x] Exclude explicit+deterministic-resolved attributes from LLM query payloads.
- [x] Mark explicit-resolved attributes as immediately accepted (no multi-step promotion).
- [x] Add regression tests proving deterministic is not called for explicit locks/conflicts.

Gate M1b:
- [x] `pytest -q tests/modules/add_attributes/test_pdp_attribute_export.py -k "explicit_locks or explicit_conflicts"`

## M2 Persist Explicit Stage + Audit Evidence (Completed)
Files:
1. [modules/add_attributes/pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)
2. PDP store adapter
3. [tests/modules/add_attributes/test_pdp_attribute_export.py](../../../tests/modules/add_attributes/test_pdp_attribute_export.py)

Checklist:
- [x] Add stage source `deterministic_explicit` to stage table mapping.
- [x] Persist explicit stage values separately from deterministic stage values.
- [x] Write explicit audit records with `decision_rule=explicit_declaration_match`.
- [x] Include evidence JSON (`rule_id`, snippet/segment where available).
- [x] Persist conflict/no-match decision rules (`explicit_declaration_conflict`, `explicit_declaration_no_match`).
- [x] Add regression tests for stage persistence and audit payloads.

Gate M2:
- [x] `pytest -q tests/modules/add_attributes/test_pdp_attribute_export.py`

## M3 Precision Proxy Metrics on Explicit Subset (Completed)
Files:
1. [modules/add_attributes/pdp_attribute_export.py](../../../modules/add_attributes/pdp_attribute_export.py)
2. [modules/add_attributes/explicit_precision_metrics.py](../../../modules/add_attributes/explicit_precision_metrics.py)
3. PDP store adapter
4. [tests/modules/add_attributes/test_explicit_precision_metrics.py](../../../tests/modules/add_attributes/test_explicit_precision_metrics.py)

Checklist:
- [x] Compute run-level counts (`explicit_positive_count`, deterministic/llm matches-on-explicit).
- [x] Persist metric rows per `(run_id, category, attribute)`.
- [x] Add deterministic and llm precision proxy fields.
- [x] Add tests for metric correctness and denominator edge cases.

Gate M3:
- [x] `pytest -q tests/modules/add_attributes/test_explicit_precision_metrics.py`

## M4 Candidate Mining CLI for Rule Authoring (Completed)
Files:
1. [scripts/mine_explicit_declaration_candidates.py](../../../scripts/mine_explicit_declaration_candidates.py)
2. [modules/add_attributes/explicit_candidate_mining.py](../../../modules/add_attributes/explicit_candidate_mining.py)
3. PDP store adapter
4. [tests/modules/add_attributes/test_explicit_candidate_mining.py](../../../tests/modules/add_attributes/test_explicit_candidate_mining.py)

Checklist:
- [x] Create deterministic candidate extraction from PDP corpus text.
- [x] Save candidate queue with snippets, counts, and conflict indicators.
- [x] Add status flow (`pending`, `approved`, `rejected`).
- [x] Ensure no candidate is auto-published.
- [x] Add tests for mining output shape and filtering quality.

Gate M4:
- [x] `pytest -q tests/modules/add_attributes/test_explicit_candidate_mining.py`

## M5 FastAPI Review Endpoints (Completed)
Files:
1. [modules/pdp/api.py](../../../modules/pdp/api.py)
2. [modules/pdp/explicit_rules_api.py](../../../modules/pdp/explicit_rules_api.py)
3. PDP store adapter

Checklist:
- [x] `GET /review/explicit-rules/candidates`
- [x] `POST /review/explicit-rules/candidates/{id}/approve`
- [x] `POST /review/explicit-rules/candidates/{id}/reject`
- [x] `GET /review/explicit-rules/config`
- [x] `POST /review/explicit-rules/config/validate`
- [x] `POST /review/explicit-rules/config/publish`
- [x] `GET /review/explicit-rules/audit`
- [x] Block publish when activation quality threshold is not met.
- [x] Require reviewer justification field when activating broad ambiguous patterns.

Gate M5:
- [ ] Add focused endpoint coverage before release; no dedicated endpoint test
  file is currently tracked.

## M6 React Review Surface (Completed, No Component Tests Yet)
Files:
1. [src/review-react/index.jsx](../../../src/review-react/index.jsx)
2. [src/review-react/coverage.jsx](../../../src/review-react/coverage.jsx)
3. [src/review-react/explicit-rules.jsx](../../../src/review-react/explicit-rules.jsx)
4. [templates/review_explicit_rules_react.html](../../../templates/review_explicit_rules_react.html)

Checklist:
- [x] Add candidate filters and cards.
- [x] Add snippet viewer for candidate evidence.
- [x] Add approve/reject actions with reviewer metadata.
- [x] Add config validation/publish/reload panel.
- [x] Add audit and precision proxy blocks.
- [x] Align UI naming to `Explicit attributes`.

Gate M6:
- [x] Manual QA iterations completed on `/review/explicit-rules/page`.
- [ ] Automated UI/component tests.

## M7 Seed Rulebook + Operational Runbook (In Progress)
Files:
1. [config/pdp_explicit_declaration_rules.json](../../../config/pdp_explicit_declaration_rules.json)
2. [docs/specs/pdp_explicit_declaration_classifier/pdp-explicit-declaration-classifier.md](../../../docs/specs/pdp_explicit_declaration_classifier/pdp-explicit-declaration-classifier.md)
3. [docs/specs/pdp_explicit_declaration_classifier/pdp-explicit-declaration-execution-checklist-v1.md](../../../docs/specs/pdp_explicit_declaration_classifier/pdp-explicit-declaration-execution-checklist-v1.md)

Checklist:
- [ ] Seed first category/attribute rules from approved candidates.
- [ ] Capture baseline precision proxy after first publish.
- [ ] Document cadence/ownership for weekly rule maintenance.
- [ ] Add explicit rollback procedure note for operators.

## Operator Quickstart (Empty Rules Config)
1. Mine candidates:
   - `python scripts/mine_explicit_declaration_candidates.py --log-level INFO --min-sample-count 3`
2. Review candidates at `/review/explicit-rules/page` (label: `Explicit attributes`).
3. Approve/reject candidates and publish config.
4. Run export pipeline:
   - `python scripts/export_pdp_attributes.py --retailer ulta --category blush`
5. Validate stage outputs in Postgres (`deterministic_explicit` source + explicit audit rows).

## Global Quality Gates
- [ ] `pytest -q` (full suite)
- [ ] `pytest --cov=src --cov-report=term-missing`
- [ ] `make check`

## Remaining Work
1. M7 operational seeding and governance.
2. Optional automated UI/component tests for explicit review page.

# PDP Explicit Declaration Stage Spec

Status: Implemented baseline (as of 2026-03-05).

## 1. Objective
Implement a new first-stage deterministic classifier that runs before the current deterministic logic in `export_pdp_attributes`.

The stage must behave like a strict human reader:
1. Return an attribute value only when the PDP explicitly states that value using an approved certainty signal.
2. If explicit certainty is not present, return `N/A`.
3. If explicit signals indicate conflicting values, return `N/A`.

This stage is intentionally precision-first and low-recall.

## 2. Why This Stage Exists
1. The current deterministic classifier is useful but not fully reliable as a precision reference.
2. The new explicit stage creates a high-confidence subset of labels.
3. That subset can be used as a benchmark sample to estimate precision of downstream stages.
4. This is not full ground truth, but it is better than having no benchmark.

## 3. Scope
In scope:
1. New explicit stage integrated before current deterministic stage.
2. Certainty rules loaded from JSON config files (no hard-coded idioms in code).
3. Rule validation and fast-fail behavior for formally invalid config.
4. Candidate mining workflow for building rules.
5. Human review workflow (FastAPI + React) to approve/reject candidates.
6. Metrics based on explicit-stage positives for precision estimation.

Out of scope:
1. Replacing existing deterministic stage.
2. Replacing LLM stage.
3. Estimating full-system recall from this stage.

## 4. Core Principles
1. Explicit-only extraction: no inference from weak words.
2. Config-driven rules: certainty idioms live in JSON, never in code constants.
3. Taxonomy-safe outputs: only active canonical taxonomy leaf values can be returned.
4. Fail loudly on invalid config.
5. Human-in-the-loop rule approval.

## 5. Definitions
1. Certainty signal: a phrase/regex approved as strong evidence for one `(category, attribute, value)`.
2. Explicit match: PDP text contains a certainty signal and passes exclusions.
3. Placeholder: `N/A` or equivalent "not stated" value.
4. Formal invalid rule: structurally/taxonomically/technically invalid at load time.
5. Empirically invalid rule: formally valid but poor precision in sampled PDP evidence.
6. Locked attribute: an attribute resolved with a valid value by an upstream stage and excluded from downstream querying.
7. Promotion workflow: the existing downstream multi-step promotion logic used for non-explicit stages.

## 6. Pipeline Behavior
Current order:
1. Deterministic stage.
2. Optional LLM fill.

Target order:
1. Explicit declaration stage (new).
2. Existing deterministic stage (unchanged algorithm).
3. Optional LLM stage.

Merge rule between explicit and existing deterministic:
1. Explicit non-placeholder values are preserved.
2. Existing deterministic may fill only explicit placeholders.
3. Existing deterministic must not overwrite explicit non-placeholder values.

Execution contract (mandatory):
1. Explicit stage is called in `export_pdp_attributes.py` / `compute_pdp_attributes` on every run (full or filtered).
2. If explicit stage returns a valid canonical value for `(row, attribute)`, that attribute becomes `locked_by=explicit`.
3. Attributes locked by explicit are not queried by deterministic stage.
4. Deterministic stage processes only unresolved attributes; its valid results become downstream locks.
5. LLM stage processes only attributes still unresolved after deterministic stage.
6. Explicit-locked values are immediately promoted/accepted and bypass the downstream multi-step promotion workflow.
7. `N/A` from explicit with decision `no_match` does not lock; those attributes remain eligible for deterministic and LLM.
8. `N/A` from explicit with decision `conflict` locks the attribute for deterministic (to prevent overwrite) but remains eligible for LLM.

## 7. Decision Contract
For each row and each configured attribute:
1. Zero matched values => `N/A`.
2. Exactly one matched value => that canonical value.
3. Two or more matched values => `N/A` (conflict).

Examples:
1. Text contains `matte` only => no decision unless that exact rule exists and is approved.
2. Text contains `matte finish` and rule `"matte finish" -> finish=matte` is active => `matte`.
3. Text contains both `matte finish` and `satin finish` for same attribute => `N/A`.

## 8. Config Architecture
Primary file:
1. `config/pdp_explicit_declaration_rules.json`

Schema file:
1. `config/pdp_explicit_declaration_rules.schema.json`

Sparse-config policy:
1. Missing category => no explicit classification for that category.
2. Missing attribute under category => no explicit classification for that attribute.
3. Missing value rules => `N/A` for this stage.

No hard-coded certainty phrases in Python modules.

## 9. Config Data Model
Top-level keys:
1. `version` (string)
2. `updated_at` (ISO timestamp)
3. `categories` (object)
4. `metadata` (object)

Structure:
1. `categories.<category_key>.attributes.<attribute_key>.values.<canonical_value>.certainty_signals[]`

Signal object fields:
1. `rule_id` (required, unique)
2. `type` (`phrase` or `regex`)
3. `pattern` (required)
4. `status` (`active` or `inactive`, default active)
5. `case_sensitive` (optional bool)
6. `word_boundary` (optional bool, phrase default true)
7. `exclude_patterns` (optional list)
8. `required_path_tokens` (optional list)
9. `priority` (optional int; audit ordering only)
10. `notes` (optional string)

Example:
```json
{
  "version": "2026-03-04",
  "updated_at": "2026-03-04T10:00:00Z",
  "categories": {
    "foundation": {
      "attributes": {
        "finish": {
          "values": {
            "matte": {
              "certainty_signals": [
                {
                  "rule_id": "foundation.finish.matte.001",
                  "type": "phrase",
                  "pattern": "matte finish",
                  "status": "active",
                  "exclude_patterns": ["not a matte finish"],
                  "notes": "High-precision declarative phrase"
                }
              ]
            }
          }
        }
      }
    }
  },
  "metadata": {
    "owner": "pdp-data-team"
  }
}
```

## 10. Rule Validity Model
### 10.1 Formal validity (machine-checked)
A rule/config is invalid if any of the following hold:
1. JSON invalid or schema violation.
2. Missing required top-level keys.
3. Unknown category key (not in taxonomy).
4. Unknown attribute key for category.
5. Unknown canonical value for category/attribute.
6. Duplicate `rule_id`.
7. Empty pattern.
8. Invalid `type` or `status` enum.
9. Regex compile failure.
10. Conflicting identical normalized patterns mapped to different values in same `(category, attribute)`.
11. Target canonical value exists in taxonomy but is not `active`.

Formal invalidity handling:
1. Fail fast before classification.
2. Emit actionable error message with path and rule id.

### 10.2 Empirical validity (human-checked)
Machine checks cannot prove semantic correctness of all rules. Example: `matte` may be too broad even if syntactically valid.

Empirical validity controls:
1. Candidate approval requires human review of snippets.
2. Reviewer can reject with reason (`too broad`, `ambiguous`, `negated`, etc.).
3. Approved rules are promoted to `active`; rejected candidates remain in history.
4. Runtime monitoring tracks conflict and disagreement rates.

## 11. Matching Semantics
Input text sources:
1. Parent: PDP description text assembled by existing extraction.
2. Variant: variant description plus existing variant context text.

Normalization:
1. Trim and whitespace-collapse.
2. Case-fold unless `case_sensitive=true`.
3. Phrase rules use escaped matching; regex rules compile as provided.

Filters:
1. `required_path_tokens`: rule only applies if segment path/token context matches.
2. `exclude_patterns`: if any exclusion matches, signal is rejected.

Conflict handling:
1. Multiple value hits for same attribute on same row => `N/A`.
2. When conflict occurs, deterministic is skipped for that `(row, attribute)` and LLM can still resolve downstream.

## 12. Output Contract
Per classification row:
1. Key columns (parent or variant keys).
2. Classified attribute columns.

Value contract:
1. Canonical taxonomy value or `N/A` only.

Optional evidence payload (for audit persistence):
1. `rule_id`
2. `attribute_id`
3. `matched_value`
4. `segment`
5. `snippet`
6. `decision` (`matched`, `conflict`, or `no_match`)

## 13. Persistence Requirements
1. Keep existing persistence behavior intact.
2. Persist explicit-stage results with source `deterministic_explicit`.
3. Persist deterministic stage results with source `deterministic`.
4. Persist LLM stage results with source `llm`.
5. Do not disable writes in filtered/debug runs.

If evidence storage is available in audit tables, include explicit evidence fields.

## 14. Precision Estimation Strategy
Use explicit-stage positives as a high-confidence benchmark sample.

For each run/category/attribute:
1. `explicit_positive_count`
2. `deterministic_match_on_explicit`
3. `llm_match_on_explicit`
4. `deterministic_precision_proxy = deterministic_match_on_explicit / explicit_positive_count`
5. `llm_precision_proxy = llm_match_on_explicit / explicit_positive_count`

Interpretation rule:
1. These are precision estimates on explicit subset only.
2. They are not full-system precision/recall guarantees.

## 15. Building the Config (Candidate Pipeline)
### 15.1 Candidate mining script
Proposed CLI:
1. `scripts/mine_explicit_declaration_candidates.py`

Candidate sources:
1. Frequent n-grams near known attribute/value labels in PDP text.
2. Existing deterministic and LLM outputs as weak proposal seeds.
3. Contradiction checks against neighboring phrases.

Output candidate record fields:
1. `candidate_id`
2. `category_key`
3. `attribute_key`
4. `proposed_value`
5. `pattern`
6. `pattern_type`
7. `sample_count`
8. `sample_snippets[]`
9. `estimated_conflict_rate`
10. `status` (`pending` by default)

No auto-publish.

### 15.2 Human review and publish flow
1. Mine candidates to a queue.
2. Reviewer opens queue UI, inspects snippets, approves/rejects.
3. Approved candidates become draft rules.
4. Draft config runs validator and preview classifier.
5. Reviewer publishes new config version.

## 16. FastAPI Contract (Review)
Suggested endpoints:
1. `GET /review/explicit-rules/candidates`
2. `POST /review/explicit-rules/candidates/{candidate_id}/approve`
3. `POST /review/explicit-rules/candidates/{candidate_id}/reject`
4. `GET /review/explicit-rules/config`
5. `POST /review/explicit-rules/config/validate`
6. `POST /review/explicit-rules/config/publish`
7. `GET /review/explicit-rules/audit`

Route naming note:
1. Backend route keeps `/review/explicit-rules/*`; navigation label shown to users is `Explicit attributes`.

Minimal request/response expectations:
1. Approve includes optional edited pattern and reviewer note.
2. Reject includes mandatory rejection reason.
3. Validate returns `valid: bool`, `errors[]`, `warnings[]`.
4. Publish returns config `version`, `updated_at`, and diff summary.

## 17. React Review Surface
Location:
1. `src/review-react/` (new page/component)

Must support:
1. Candidate list with category/attribute/value filters.
2. Snippet preview with matched text highlighting.
3. Approve/reject actions with reviewer notes.
4. Config JSON editor with validate/publish/reload actions.
5. Validation error panel.
6. Audit + precision proxy visibility.

Design constraint:
1. Human reviewer must be able to reject broad ambiguous phrases quickly.

## 18. Testing Plan
Unit tests:
1. Schema and taxonomy validation failures.
2. Duplicate/conflicting rule detection.
3. Phrase matching, regex matching, exclusions.
4. No explicit evidence -> `N/A`.
5. Conflicting evidence -> `N/A`.

Integration tests:
1. Explicit stage executes before existing deterministic stage.
2. Existing deterministic fills placeholders only.
3. Existing deterministic does not overwrite explicit values.
4. Sparse config behavior (missing category/attribute) yields no explicit output.

API/UI tests:
1. Candidate listing and decision endpoints.
2. Validate and publish flow.
3. End-to-end approval creates active rule and affects next run.

## 19. Non-Negotiable Design Safety Gates
All gates below are blockers. If any gate fails, the module is not acceptable.

1. `Deny by default`: no explicit approved signal means `N/A`.
2. `Fail-fast formal validation`: schema, taxonomy keys/values, duplicate `rule_id`, regex compile, and conflict signatures must fail before classification.
3. `No weak rule activation`: broad ambiguous idioms (for example single-token patterns) cannot be activated without explicit reviewer justification.
4. `Conflict and negation safety`: conflicting value signals or negated declarations must resolve to `N/A`.
5. `Evidence required`: every positive explicit decision must store auditable evidence including `rule_id` and matched text snippet.
6. `Human publish gate`: rules must move through `draft -> reviewed -> active`; auto-publish is forbidden.
7. `Quality gate before activation`: each new/edited rule requires minimum reviewed sample size and minimum precision threshold before activation. Initial defaults: `min_reviewed_samples=30`, `min_precision=0.98`.
8. `Versioning and rollback`: each published ruleset must have immutable version metadata and a defined rollback path.
9. `Attribute lock semantics`: explicit matched attributes must be skipped by deterministic and LLM; explicit conflicts must be skipped by deterministic and may continue to LLM.
10. `Immediate explicit promotion`: explicit-resolved attributes bypass the downstream multi-step promotion flow.

## 20. Acceptance Criteria
1. New explicit stage is wired before current deterministic stage.
2. Stage returns value only on explicit certainty signal.
3. Absent, negated, or conflicting signals return `N/A`.
4. Rules are config-driven (no hard-coded idioms in code).
5. Formal invalid rules fail fast with actionable errors.
6. Sparse config is supported.
7. Explicit-stage positives persist evidence with `source=deterministic_explicit`.
8. Human review workflow exists (FastAPI + React) with no auto-publish.
9. Rule activation enforces minimum reviewed sample size and minimum precision threshold.
10. Precision proxy report from explicit subset is produced per run.
11. Rulesets are versioned and rollback-capable.
12. Explicit matched attributes are excluded from deterministic and LLM query payloads.
13. Explicit conflict attributes are excluded from deterministic query payloads and remain eligible for LLM.
14. Explicit-resolved attributes are immediately accepted without downstream multi-step promotion.

## 21. Rollout Phases
1. Phase 1: Engine + config loader/validator + pipeline ordering + tests.
2. Phase 2: Persistence source separation + evidence capture + metrics.
3. Phase 3: Candidate mining CLI.
4. Phase 4: FastAPI review endpoints.
5. Phase 5: React review page and publish workflow.
6. Phase 6: Gradual category-by-category rule expansion.

## 22. Known Limits
1. This approach does not maximize recall by design.
2. Semantic correctness of phrases cannot be fully machine-proven.
3. Human review quality directly impacts resulting precision.

## 23. Day-0 Operations (No Rules Yet)
1. Mine candidates from existing PDP text:
   - `python scripts/mine_explicit_declaration_candidates.py --log-level INFO --min-sample-count 3`
2. Open `/review/explicit-rules/page` (label: `Explicit attributes`) and review `pending` candidates.
3. Approve precise candidates, set `reviewed_samples` and `precision_estimate`, then publish config.
4. Run export so the explicit stage is applied in production flow:
   - `python scripts/export_pdp_attributes.py --retailer ulta --category blush`
5. Verify persisted outputs in Postgres:
   - Stage table source `deterministic_explicit`
   - Audit `decision_rule` values including `explicit_declaration_match`, `explicit_declaration_conflict`, `explicit_declaration_no_match`
6. Interpretation reminder:
   - If two approved rules for the same attribute both match one PDP (for example `buildable coverage` and `full coverage`), explicit output is `N/A`; deterministic is skipped; LLM can resolve later.

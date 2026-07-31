# Validate Answer Workflow Reference

This reference expands the core workflow in `SKILL.md`. Load it when a run needs detailed review categories, source-support wording, or packaging interpretation.

## Claim Selection

Review material claims rather than every sentence. Prioritize:

- conclusions and recommendations;
- legal, tax, compliance, or eligibility positions;
- numeric claims, percentages, dates, thresholds, and deadlines;
- causal claims and risk statements;
- claims used as premises for later conclusions.

Skip purely introductory, stylistic, or duplicated statements unless they carry a material conclusion.

Claim selection is itself a semantic review step. Read the full answer and
record reviewed sections, omitted sections, limitations, and whether the scope
is `all_material_claims`, `selected_material_claims`, or `limited`. Mechanical
sentence extraction is only navigation help.

## Answer-Contract Conformance

Before claim-by-claim review, assess separately whether the answer addresses the
question, uses the contracted document type, suits the intended audience, and
follows the evidence-display requirement. A source-supported answer can still
fail because it answers the wrong question or produces the wrong artifact.

## Semantic Support Statuses

Use these support statuses in `claims_review.json`:

- `supported`: the cited source directly supports the same fact or conclusion.
- `partially_supported`: the source supports part of the claim or supports a narrower conclusion.
- `not_supported`: the source does not support the claim.
- `contradicted`: the source conflicts with the claim.
- `uncertain`: support cannot be determined because sources are unavailable, gated, too short, or ambiguous.

## Review Dimensions

For each reviewed claim, separate:

- source access: URL/file reachable and captured;
- source identity: model-led assessment that the captured item is the authority
  actually cited, including version, jurisdiction, and period;
- exact passage presence: mechanical observation made only within the
  specifically cited source snapshot;
- semantic support: model-led assessment that the source actually entails,
  narrows, qualifies, or contradicts the claim;
- reasoning: model-led assessment that the conclusion follows from supported
  premises and identification of missing premises;
- professional judgment: explicit factors and alternative interpretations;
- issue treatment and final claim disposition.

Exact or fuzzy text matching is not semantic support. For example, "this is a
terrier" can support "this is a dog" without literal overlap, while "this is
not a dog", "this will be a dog", and "this was a dog" have different
negation or temporal meaning despite strong lexical overlap.

## Validation Boundary

Keep four dimensions explicit:

- mechanically observed: document or source access, identifiers, exact quote
  presence in the available text, and JSON/schema shape;
- model-led source identity and semantic support: authority identity, claim
  meaning, entailment, contradiction, scope, qualification, time, and modality;
- model-led reasoning: whether the conclusion follows from supported premises
  and whether intermediate premises are missing;
- judgment-dependent: legal applicability, materiality, competing
  interpretations, strategy, reasonableness, and uncertain professional
  outcomes.

Deterministic observations may collect evidence but must not decide semantic
support. A passing deterministic audit means the review record is complete
enough to inspect; it does not certify legal correctness.

## Issue Types And Treatments

Use one or more issue types for each claim:

- `source_unavailable` → obtain the source or mark evidence blocked;
- `source_not_identified` → identify the cited authority;
- `wrong_source`, `wrong_source_version`, or
  `wrong_jurisdiction_or_period` → replace the source and reassess support;
- `missing_source_support` → add support, remove the claim, or state
  uncertainty;
- `partial_or_overbroad_support` → narrow the claim;
- `source_contradiction` → correct or remove the claim;
- `qualification_or_scope_distortion` → restore the source's qualification;
- `temporal_or_modality_distortion` → correct tense, timing, certainty, or
  modality;
- `reasoning_gap` → supply the missing premise when supported, otherwise
  narrow, caveat, or remove the conclusion;
- `judgment_dependent` → state uncertainty and require professional review;
- `answer_contract_failure` → revise the answer to the contracted question,
  document type, audience, or evidence display.

Use `none` alone when no issue was identified. Record one of these treatment
actions for every issue: `obtain_source`, `identify_source`, `replace_source`,
`add_support`, `narrow_claim`, `correct_claim`, `restore_qualification`,
`correct_time_or_modality`, `add_reasoning`, `state_uncertainty`,
`remove_claim`, `professional_review`, or `revise_answer_contract`. Treatment
status is `proposed`, `applied`, `blocked`, or
`professional_review_required`; `none` uses `none` / `not_needed`.

## Output Guidance

The validation package is not a new substantive answer. It is a review record.
State assumptions and source limits clearly. Preserve the user's document
structure when writing a corrected Markdown document. A proposed fix in the
review record is not a corrected answer: the answer must be regenerated
semantically and packaged again.

## Deterministic Audit Interpretation

`validation_audit.json` is a guardrail, not a legal conclusion. Its
`record_integrity_status` says whether required review fields and treatments
were recorded. Its `delivery_readiness` aggregates those explicit statuses; it
does not infer legal correctness. Exact passage absence is reported with the
capture scope and never overrides semantic support.

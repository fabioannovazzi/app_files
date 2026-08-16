# Advisory contract v1.0

The canonical cross-workflow artifact is named `advisory_contract.json` and
uses `schema_version: "1.0"`. The machine-readable schema is
`../../../contracts/advisory_contract.v1.schema.json` from this reference.

All semantic contents are authored by Clara from explicit source context or
user-confirmed choices. Deterministic code validates only the declared shape;
it does not infer the decision, scope, evidence standard, analysis method, or
professional-judgement boundary.

## Stable fields

- `decision`: the decision, question, or action the deliverable must support.
- `purpose`: why the deliverable exists and what it must accomplish.
- `audience`: roles or readers whose needs govern the deliverable.
- `deliverable_type`: the intended professional artifact, not merely its file
  extension.
- `output_language`: one of `it`, `en`, `fr`, `de`, or `es`.
- `scope_included` and `scope_excluded`: explicit substantive boundaries.
- `available_inputs`: selected files, data, interviews, prior work, or other
  evidence available to the engagement.
- `evidence_requirements`: what must support material claims, calculations, and
  recommendations.
- `analysis_plan`: the model-led analytical steps expected before delivery.
- `assumptions`: assumptions currently permitted by the contract.
- `unresolved_questions`: questions that remain open and may affect readiness.
- `success_criteria`: observable criteria for a useful and responsible result.
- `selected_clara_workflow`: the fully-qualified Clara workflow producing or
  owning the deliverable.
- `validation_profile.review_dimensions`: the ten required advisory-review
  dimensions. The complete fixed set is shown below.
- `validation_profile.format_checks`: existing Clara checks that are required,
  conditional, or not required for this artifact. This is the composition
  boundary; the validator must consume their artifacts rather than duplicate
  their mechanics.
- `validation_scope`: whether review covers all material content, selected
  material content, or a limited scope, with explicit inclusions, exclusions,
  and limitations.
- `correction_policy`: whether correction is allowed, always with
  `mode: "separate_artifact"` and `preserve_original: true`.
- `professional_judgement_policy`: who owns professional judgement, the
  model's bounded role, and whether approval is required before delivery.

The contract states whether approval is required; it never records approval by
itself. The downstream advisory validation review records explicit
`professional_judgement` and `correction` approval states, approver identity,
and evidence references. Deterministic packaging may verify that a required
state is `approved`, but Clara must not infer that state.

The required review dimensions are:

```json
[
  "contract_conformance",
  "factual_source_support",
  "calculations_data_provenance",
  "reasoning_assumptions",
  "contradictions_missing_evidence",
  "recommendation_evidence_decision_fit",
  "professional_judgement_boundaries",
  "correction_needs",
  "residual_uncertainty",
  "delivery_readiness"
]
```

## Example

```json
{
  "schema_version": "1.0",
  "decision": "Whether to proceed with the proposed channel expansion and under which conditions.",
  "purpose": "Give the steering group a source-backed recommendation and the evidence needed for its decision.",
  "audience": ["Steering group", "Engagement partner"],
  "deliverable_type": "advisory memo",
  "output_language": "en",
  "scope_included": ["Commercial evidence", "Implementation conditions"],
  "scope_excluded": ["Legal and tax advice"],
  "available_inputs": ["draft_memo.docx", "market_evidence.pdf", "analysis.xlsx"],
  "evidence_requirements": ["Every material factual claim identifies its source", "Recommendation conditions trace to available evidence"],
  "analysis_plan": ["Review source support", "Reperform relevant calculations", "Challenge assumptions and recommendation fit"],
  "assumptions": ["The supplied sales extract is complete through 30 June"],
  "unresolved_questions": ["Implementation owner is not yet confirmed"],
  "success_criteria": ["Decision and conditions are explicit", "Residual uncertainty is visible"],
  "selected_clara_workflow": "clara:clara",
  "validation_profile": {
    "review_dimensions": [
      "contract_conformance",
      "factual_source_support",
      "calculations_data_provenance",
      "reasoning_assumptions",
      "contradictions_missing_evidence",
      "recommendation_evidence_decision_fit",
      "professional_judgement_boundaries",
      "correction_needs",
      "residual_uncertainty",
      "delivery_readiness"
    ],
    "format_checks": [
      {
        "workflow": "clara:reporting-engine",
        "requirement": "required",
        "reason": "The recommendation relies on spreadsheet calculations.",
        "artifact_refs": ["reporting-engine/render_manifest.json"]
      }
    ]
  },
  "validation_scope": {
    "coverage": "all_material_content",
    "included_sections": ["Entire deliverable"],
    "excluded_sections": [],
    "limitations": []
  },
  "correction_policy": {
    "mode": "separate_artifact",
    "preserve_original": true,
    "allowed": true,
    "approval_required_before_delivery": true
  },
  "professional_judgement_policy": {
    "owner": "Engagement partner",
    "model_role": "Identify issues and draft evidence-bounded corrections for review",
    "approval_required_before_delivery": true
  }
}
```

## External documents without a contract

Clara may create `advisory_contract.json` from explicit context already supplied
by the user. If a consequential scope, evidence requirement, correction policy,
or judgement owner is not explicit, Clara shows the proposed contract and asks
the user to confirm that point before validation. Missing context is recorded in
`unresolved_questions`; it is never filled with silent assumptions.

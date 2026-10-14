> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Durable position and counter-opinion

Use the prepared, started `deep-research-validator` run and its unchanged
`client_engagement_path`. `<run>` below is its exact output directory. Resolve
the validator module as `modules/deep-research-validator` within the installed
invoking product root or `../deep-research-validator` in source. Run validator commands
through the product's managed launcher with `--module deep-research-validator`.

1. Package the reviewed original with the existing validator in `<run>/position`.
   Keep `document_inventory.json`, `source_inventory.json`, source captures,
   `answer_contract.json`, `claims_review.json`, and `validated_document.md`
   there. The original answer contract must contain
   `"adversarial_policy": "required"`. Preserve unresolved validation outcomes;
   they never determine whether the opposing examination runs. A malformed
   review record must be repaired before binding it. The reviewed Markdown must
   be the same text as `claims_review.json`'s `validated_document`.
2. From the invoking product root, run the normal dependency check, then prepare:

```bash
python scripts/check_dependencies.py --module deep-research-validator
python scripts/managed_python_runtime.py --module deep-research-validator run scripts/adversarial_opinion.py prepare --client-engagement <client_engagement_path> --output-dir <run>
```

This writes `adversarial_brief.json`, freezes the current original package's
exact file hashes, writes a derived `adversarial/answer_contract.json`, and
marks the journey pending. The counter-contract preserves jurisdiction,
language and evidence policies while changing document type, purpose and
audience for the opposing working document. It removes the recursive adversarial
policy. Do not modify that generated contract.

3. Perform the model-led exercise from the skill. Save its complete draft as
   `<run>/adversarial/answer.md`. Inspect it and its cited/supplied sources,
   review all material claims, and package it using the existing validator in
   `<run>/adversarial`. Use the generated counter-contract. Keep captured
   sources within that phase directory and exact source IDs. Produce DOCX for
   each opinion when available. Apply any collected review decisions before
   final packaging; a later edit invalidates the final delivery binding.
4. Write `<run>/adversarial_assessment.json`. The model authors the substance;
   code validates only structure, bindings and explicit state consistency:

```json
{
  "schema_version": "1.0",
  "language": "it",
  "brief_sha256": "SHA-256 of the exact adversarial_brief.json bytes",
  "outcome": "credible_counterposition",
  "rationale": "Evidence-bound explanation of the examination outcome.",
  "search_record": [
    {"question": "Material issue examined", "search_or_source": "Actual query or source examined", "finding": "What this examination established and its limits", "source_refs": ["source-001"]}
  ],
  "comparison": {
    "original_conclusion": "Precise original position with references to the reviewed opinion.",
    "opposing_conclusion": "Precise opposing conclusion, or the bounded negative/limited result.",
    "decisive_issues": ["Where the positions diverge, with source references."],
    "evidence_gaps": [],
    "professional_choices": ["Decision that remains with the professional."],
    "original_position_effect": "unchanged",
    "effect_analysis": "Why the original stays unchanged or requires further work."
  },
  "comparison_review": {"status": "reviewed", "analysis": "How the comparison was checked against both reviewed documents and sources."}
}
```

`language` is `it`, `en`, `fr`, `de`, or `es`, matching the working language.
Each search entry records actual work; `source_refs` may be empty for an
unsuccessful or inaccessible search. Other references must resolve to the
opposing source inventory. Outcomes are `credible_counterposition`,
`no_substantial_counterposition`, and `evidence_limited`. The original-position
effect is `unchanged`, `professional_review_required`, or `revision_required`.
The comparison review is `reviewed` or `revision_required`. A negative outcome
still needs a reviewed, reasoned document and search record.

5. Package and verify from the invoking product root:

```bash
python scripts/managed_python_runtime.py --module deep-research-validator run scripts/adversarial_opinion.py package --client-engagement <client_engagement_path> --output-dir <run> --docx
python scripts/managed_python_runtime.py --module deep-research-validator run scripts/adversarial_opinion.py verify --client-engagement <client_engagement_path> --output-dir <run>
```

Use `--docx` when DOCX tooling is available and visually inspect final DOCX
files under the invoking product's normal delivery rules. Deliver `opinion_package.md`,
`opinion_comparison.md` and its DOCX, both phase documents, and
`opinion_delivery.json`. The phase folders retain sources and reviews. The
helper recomputes both validation audits, retains their separate outcomes,
and records overall `complete`, `professional_review_required`,
`evidence_limited`, `revision_required`, or `blocked`. These describe recorded
work and unresolved issues; `complete` is not legal correctness or professional
approval. A professional-review or evidence-limited package can be delivered
with those limits explicit.

If the original changes, run preparation again and reassess the opposing case
and comparison. If the opposing document or comparison changes, revalidate the
changed material and repackage. Never update hashes to disguise an unreviewed
revision. Finally create the model-data reports, declare every physical artifact
through Studio Archive, review that declaration, and complete the run. Verify
the opinion package again immediately before delivery or when reopening it.

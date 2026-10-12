# Shared question-to-reviewed-answer journey

Vera and Lucia use this same method. The invoking wrapper identifies the
product root and its professional and runtime rules; retain them throughout.
From that root, read `skills/legal-tax-answer-planner/SKILL.md` completely before
preparation and `skills/legal-tax-answer-review/SKILL.md` completely before
review. These wrappers resolve the canonical stage implementations. They do
not create a second implementation of this journey.

Read `adversarial-scope.md` before finalizing the answer contract. Informational
research ends after validation; an opinion on a concrete position or an explicit
opposing-opinion request includes the opposing examination, subject to the
user's instruction to omit it. Validation findings do not determine this scope.
For a supplied position, establish or recover its question, material facts and
contract, then review it before the opposing examination. Do not regenerate a
supplied position merely to force a research-mode choice.

This journey handles questions, analysis and source-backed professional drafts.
It does not replace dedicated filing, signature, statutory form, submission or
other operational controls. Apply the invoking product's no-matching-workflow
rule when the required dedicated workflow is unavailable. Keep language,
governing law, forum, relevant dates and source hierarchy separate. Do not infer
jurisdiction from the language of the conversation.

1. Route the question internally through `prompt-optimizer`. Complete only the
   material intake, jurisdiction confirmation, source curation, answer
   contract, generation instructions, model-led prompt-to-question and prompt-
   to-contract conformance review, and deterministic record/shape validation.
   The inspection layer does not decide whether angle or jurisdiction
   confirmation is needed; ask only when semantic review finds a consequential
   ambiguity.
2. Write `answer_contract.json` before generation. For `quesito-legale-fiscale`,
   follow `adversarial-scope.md` and record `adversarial_policy` (`required` or
   `not_required`) with `adversarial_rationale` in the original contract.
   Respect explicit user instructions. Do not infer this policy from tax/legal
   keywords, document labels, the research mode or the validation outcome.
   Keep generation route separate from document type. New research uses
   `generation_route: codex_direct`; supplied-answer review uses
   `external_document`. Older imported route labels remain provenance only.
   Infer the document type from the request, including short letters and memos.
   Follow `research-choice.md`: both products use one bundled research method,
   without a normal/deep selector or external research-plugin dependency.
3. For new research, read and execute `<product-root>/skills/deep-research/SKILL.md` using the
   accepted optimizer package. It resolves the canonical shared research
   method and opens the existing validation run early. Investigate material
   issues, validate provisional source support and reasoning, seek opposing
   evidence, track findings and respond with targeted research or corrections.
   Persist the issue register and research cycles. Use substantive stopping
   criteria; counts, token savings and repeated model agreement are insufficient.
   For a supplied answer, review it first; use the same research loop for
   material evidence gaps without regenerating the supplied position merely
   to run research. Retain its external-document provenance.
4. Continuous checking never replaces final examination of the complete draft.
   Final validation, the opposing examination and comparison can reopen the
   same research loop. Correct the actual answer, revalidate changed and
   dependent claims, and refresh final reviews against its exact revision.
5. When a generated or external answer is available, route it through
   `deep-research-validator` with the same `answer_contract.json`. Reuse the
   running validation context if the product-owned research stage already
   prepared it; do not create a second validation run. The validator
   applies to short letters and other professional documents as well as
   research reports. Only when `adversarial_policy` is `required`, package the
   original in `position/` beneath the validation run and keep that run open for
   the adversarial stage. Otherwise use the ordinary validator packaging
   without an adversarial package. Keep the run open for research-record
   verification and the invoking journey's remaining writes.
6. Keep the validation dimensions explicit and separate:
   - mechanical observations: document/source access, exact identifier
     resolution, exact passage presence in the specifically cited source
     snapshot, and record shape;
   - model-led source identity and semantic support: whether the captured item
     is the authority actually cited and whether it entails, narrows, qualifies,
     or contradicts the claim;
   - model-led reasoning: whether the conclusion follows from supported premises
     and which intermediate premises are missing;
   - professional judgment: legal applicability, materiality, competing
     interpretations, strategy, and uncertain outcomes.
   Mechanical observations must never decide semantic support. A structurally
   passing audit does not certify legal correctness.
7. Review answer-contract conformance and whether all material claims were
   selected, independently from the individual claim assessments. Treat source,
   support, qualification, time/modality, reasoning, and judgment issues with
   their issue-specific actions rather than a single pass/fail label.
8. Correct support or reasoning defects when the evidence permits. Mark
   judgment-dependent conclusions for professional review rather than
   presenting them as validated facts. Preserve the corrected document,
   validation record and unresolved issues for the next stage. Recording a proposed fix is not correction: regenerate the
   answer semantically and rerun packaging before it can be delivery-ready.
   The packaging layer may reject mechanically contradictory review states—for
   example a contradicted claim retained with no issue treatment, a rejected
   claim marked ready, or a completed correction paired with a no-defect
   outcome—but it must never assign the semantic support or reasoning status.

9. For `quesito-legale-fiscale` with `adversarial_policy: required`, read and
   follow `<product-root>/skills/adversarial-opinion/SKILL.md`
   before delivery, independently of the original validation outcome. Use the
   current model; model diversity is not required. Develop and review a
   substantive opposing case, or a reasoned no-substantial-case/evidence-limited
   result, and compare both positions for the professional. Keep this work
   within the same validation run. Verify the combined `opinion_delivery.json`
   with the documented helper before delivering the original, opposing result,
   comparison and separate reviews. When local tooling is unavailable, perform
   the substantive exercise in chat and state the missing durable evidence.
   With `not_required`, prepare the reviewed answer, sources and limits;
   do not invoke the adversarial helper
   or require `opinion_delivery.json`. Report only the stages actually run.

10. For research performed here, bind and verify `research_review.json` using
    the shared research skill's `research_record.py` instructions after the
    final substantive reviews. Do not finalize an actionable open issue or
    substitute an interrupted run for a completed investigation. The helper
    enforces artifact hashes and declared record consistency, never legal
    correctness. Preserve evidence limits and professional-review items.
    Only after these checks and all contracted final reviews, declare the
    artifacts and complete the same validation run under its review rules,
    then deliver the reviewed package. Supplied-answer review without research
    does not require a fabricated research record.

`quesito-legale-fiscale` does not create a third Studio Archive workstream or a
new external data route. The preparation stage remains governed by the
`prompt-optimizer` workstream record, and the answer-review stage remains
governed by the `deep-research-validator` workstream record, including the
adversarial research, opposing review and final comparison.

At delivery, show only the stages actually performed, using the invoking
product's namespace: `quesito-legale-fiscale -> prompt-optimizer ->
deep-research-validator`. Insert `deep-research` between preparation and
validation only when the product-owned research skill ran, and append
`adversarial-opinion` only when it ran.
Keep the product's reporting and feedback rules. With no local tools, follow
its chat fallback, retain both opinions when required, and disclose which
research or durable records could not be produced.

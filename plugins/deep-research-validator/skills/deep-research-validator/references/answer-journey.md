# Shared question-to-reviewed-answer journey

Vera and Lucia use this same method. The invoking wrapper identifies the
product root and its professional and runtime rules; retain them throughout.
From that root, read `skills/prompt-optimizer/SKILL.md` completely before
preparation and `skills/deep-research-validator/SKILL.md` completely before
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
   Keep generation route separate from document type:
   - `generation_route` is `codex_direct`, `deep_research_plugin`,
     `chatgpt_deep_research`, or `external_document`;
   - `document_type` is the requested answer artifact, such as a research
     report, legal memo, one-page letter, response letter, checklist, or
     counsel brief.
   Infer the document type from the request. For `quesito-legale-fiscale`,
   follow `research-choice.md`: after preparing
   the question, offer the available OpenAI Deep Research plugin or ordinary
   research before finalizing the route. Reuse an explicit choice for
   this answer; otherwise wait for it before generation.
3. Use `deep_research_plugin` when the user selects the installed OpenAI
   `deep-research` skill. Read and follow that skill in the current host with
   the prepared brief, answer contract and selected sources, then resume
   validation. Use `codex_direct` for the ordinary route. Both routes retain
   the generated answer, source record and the same answer contract.
4. Use `chatgpt_deep_research` for a separately chosen native ChatGPT Deep
   Research handoff. This is distinct from the installed plugin route.
   Present one concise handoff containing:
   - the complete text of `optimized_prompt.md`, or a direct local link;
   - the complete contents of `source_domains_comma.txt`;
   - the `answer_contract.json` document type and output requirements;
   - a model-led recommendation to restrict research to the listed sites or
     prioritize them while allowing broader web research.
5. Choose the site policy from the confirmed framework, objective, source
   posture, and issue—not from keywords or a deterministic classifier. Ask the
   user only when competing policies would materially change the professional
   result and the confirmed posture does not resolve the choice.
6. Keep the separate ChatGPT handoff explicit. The assistant cannot claim to start,
   monitor, interrupt, or retrieve a native run unless a callable host tool
   expressly provides that capability. End with one instruction to return the
   completed answer in the same conversation as Markdown, text, HTML, readable
   PDF, or DOCX. Do not ask the user to restate confirmed context.
7. When a generated or external answer is available, route it through
   `deep-research-validator` with the same `answer_contract.json`. The validator
   applies to short letters and other professional documents as well as
   research reports. Only when `adversarial_policy` is `required`, package the
   original in `position/` beneath the validation run and keep that run open for
   the adversarial stage. Otherwise use the ordinary validator packaging and
   finish the reviewed-answer journey without an adversarial package.
8. Keep the validation dimensions explicit and separate:
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
9. Review answer-contract conformance and whether all material claims were
   selected, independently from the individual claim assessments. Treat source,
   support, qualification, time/modality, reasoning, and judgment issues with
   their issue-specific actions rather than a single pass/fail label.
10. Correct support or reasoning defects when the evidence permits. Mark
   judgment-dependent conclusions for professional review rather than
   presenting them as validated facts. Preserve the corrected document,
   validation record and unresolved issues for the next stage. Recording a proposed fix is not correction: regenerate the
   answer semantically and rerun packaging before it can be delivery-ready.
   The packaging layer may reject mechanically contradictory review states—for
   example a contradicted claim retained with no issue treatment, a rejected
   claim marked ready, or a completed correction paired with a no-defect
   outcome—but it must never assign the semantic support or reasoning status.

11. For `quesito-legale-fiscale` with `adversarial_policy: required`, read and
   follow `<product-root>/skills/adversarial-opinion/SKILL.md`
   before delivery, independently of the original validation outcome. Use the
   current model; model diversity is not required. Develop and review a
   substantive opposing case, or a reasoned no-substantial-case/evidence-limited
   result, and compare both positions for the professional. Keep this work
   within the same validation run. Verify the combined `opinion_delivery.json`
   with the documented helper before delivering the original, opposing result,
   comparison and separate reviews. When local tooling is unavailable, perform
   the substantive exercise in chat and state the missing durable evidence.
   With `not_required`, deliver the reviewed answer, sources and limits and
   complete the ordinary validation run; do not invoke the adversarial helper
   or require `opinion_delivery.json`. Report only the stages actually run.

If a selected Deep Research route is unavailable or fails, state the actual
limitation and obtain the user's alternative route choice. Do not silently
substitute ordinary research or move case material to another account. Follow
the availability handling in `research-choice.md`.

`quesito-legale-fiscale` does not create a third Studio Archive workstream or a
new external data route. The preparation stage remains governed by the
`prompt-optimizer` workstream record, and the answer-review stage remains
governed by the `deep-research-validator` workstream record, including the
adversarial research, opposing review and final comparison.

At delivery, show only the stages actually performed, using the invoking
product's namespace: `quesito-legale-fiscale -> prompt-optimizer ->
deep-research-validator`, appending `adversarial-opinion` only when it ran.
Keep the product's reporting and feedback rules. With no local tools, follow
its chat fallback, retain both opinions when required, and disclose which
research or durable records could not be produced.

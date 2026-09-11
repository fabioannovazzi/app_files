---
name: adversarial-opinion
description: Develop and review the strongest evidence-bound opposing case when Vera is asked for an opinion on a concrete legal, tax, or compliance position or explicitly for an opposing opinion. Do not activate for informational research alone; when selected, run independently of the original validation outcome and compare both positions.
---

# Adversarial Opinion

Run this distinct fourth stage after preparation, drafting, and validation in
`vera:quesito-legale-fiscale` only when its original answer contract records
`adversarial_policy: required`. Read and follow
`../quesito-legale-fiscale/references/adversarial-scope.md` before activating it.
It is routine for an opinion on a concrete position, even when that opinion is
well supported; informational research alone does not activate it. Validation asks whether that opinion is supported; this stage
develops the strongest credible case for an incompatible conclusion. Use the
current model and selected runtime. A different model, separate agent, special
mode, or additional user confirmation is not a prerequisite.

For a supplied position, first use the legal-question journey to establish its
facts, scope and answer contract and review it. Respect a user's explicit
instruction to omit the stage; do not change `not_required` merely because
research has produced conclusions. Do not apply this stage to other
Vera workflows merely because their output mentions law or tax.

## Develop the opposing case

1. Read the complete reviewed position, original facts and question, answer
   contract, source evidence and validation limits. State precisely which
   conclusion is challenged. Preserve the original question, jurisdiction,
   relevant dates and evidence posture. Clearly separate established facts,
   disputed facts and hypothetical facts; never invent a factual premise.
2. Choose the opponent's plausible perspective from the case, such as the
   counterparty or authority, when that perspective matters. Ask only if a
   consequential ambiguity remains. Seek competing authorities, exceptions,
   materially different readings of the same authorities or facts, and
   challenges to the original framing. Research beyond the original citations
   when needed within the authorized source boundary. Record the searches or
   sources actually examined and their findings.
3. Develop the strongest substantiated opposing conclusion as a coherent
   opinion, with the reasoning needed to get there. A list of defects, a
   rhetorical objection, or a negation of the original conclusion is not a
   counter-opinion. Identify the decisive premises, strongest evidence, and
   qualifications. Do not invent authorities, exaggerate weak objections, force
   symmetry, or assign unsupported probabilities of success.
4. Record one model-led outcome: `credible_counterposition`,
   `no_substantial_counterposition`, or `evidence_limited`. The second outcome
   requires a reasoned account of what was examined and why no substantial
   opposing case was found within that scope. It does not prove that no such
   case exists. Inaccessible decisive sources or missing facts remain explicit
   evidence limits, not proof of absence. Do not choose an outcome from the
   original validation result or from a fixed number of objections or searches.
5. Review the opposing opinion or reasoned negative result using
   `vera:deep-research-validator`: source identity and support, reasoning,
   qualifications, coverage and professional judgment. Correct supported
   defects. This is validation of the fourth-stage output, not a recursive
   request for another adversarial opinion. Preserve both review records.

Match the working document's detail to the outcome. Develop a credible opposing
case as far as its reasoning and sources require. When none is established,
write a concise reasoned account of the scope, work performed and result; do
not pad it into a full counter-opinion. When evidence is limiting, identify the
decisive missing source or fact, the question it leaves unresolved and the next
useful check. These shorter results still retain the search and review records.

## Compare and deliver

Write a concise comparison containing the original conclusion, opposing
conclusion, decisive differences, evidence that could change the assessment,
and choices requiring professional judgment. Review that comparison against
both opinions and the underlying sources. Keep substantive statements traceable
to the reviewed documents; research and validate any new material claim.

The original may remain unchanged despite a credible opposing case. If the
exercise exposes a defect requiring correction, identify it explicitly,
correct and revalidate the original when supported, then refresh the opposing
exercise against that exact version. Do not silently merge the opinions or
present a preferred legal strategy as an established fact. If missing evidence
or professional judgment prevents closure, preserve the partial package and
state what remains rather than looping or manufacturing a resolution.

Deliver the reviewed original, the reviewed opposing opinion or reasoned
negative/limited result, their source and validation records, and the comparison.
A client letter retains its requested form; the opposing opinion and comparison
are separate working documents for the professional. Final legal choices and
approval remain with the professional.

## Durable execution

When local run tooling is available, read
`references/durable-opinion.md` completely. Keep the two opinions in `position/`
and `adversarial/` under the **same** Studio Archive `deep-research-validator`
run. The planning run remains separate in that engagement. Do not finalize the
validation run after the original opinion alone. The helper's `prepare`,
`package`, and `verify` commands bind the exact position and both review records;
they do not generate or evaluate legal arguments.

When local tools are unavailable, complete the same substantive exercise in
chat with the available research capabilities. Show both positions, sources,
comparison and limits; state that no durable run or hash verification occurred.
If current-source research is unavailable, keep the result evidence-limited.

Include the original review, adversarial research/drafting, opposing review and
comparison as distinct model-visible phases in Vera's model-data report. They
can expose complete opinions, material case facts and selected source text to
the selected model runtime. The stage does not require a new provider account.

At delivery, include `vera:adversarial-opinion` in workflow provenance only when
this exercise actually ran. Follow Vera's existing feedback and reporting rules.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

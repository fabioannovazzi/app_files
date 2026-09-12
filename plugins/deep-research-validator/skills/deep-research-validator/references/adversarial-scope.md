# Decide whether the assignment needs an opposing opinion

Read the user's requested result and confirmed context before finalizing the
answer contract. This is a model-led intent decision, not a keyword classifier.
The subject being legal or fiscal, the presence of client facts, the word
"parere", a research report's conclusions, or the choice of Deep Research does
not by itself request an opinion on a concrete position.

Record `adversarial_policy` as `required` or `not_required` and a short
`adversarial_rationale` in the original `answer_contract.json`. The rationale
identifies the requested work; it does not predict whether an opposing case
will succeed. Keep this decision in the prompt-to-contract semantic review.

- **Informational research — `not_required`:** explain or summarize a rule,
  new measure, eligibility requirements, exclusions, deadlines, sources or
  unresolved interpretations. For example: "Informami sul nuovo credito
  d'imposta: come funziona, a chi spetta e quali spese copre?" Complete
  preparation, research and validation. Relevant exceptions, contrary
  authorities and uncertainties remain part of that research and review.
  Do not invent a client position, opponent or counter-opinion merely to add
  a fourth stage.
- **Opinion on a concrete position — `required`:** the assignment asks the assistant
  to formulate, assess, support or challenge a case-specific legal or fiscal
  conclusion, interpretation or argument. For example: "Con questi fatti,
  redigi un parere motivato sulla spettanza del credito a questo investimento."
  Include the opposing examination after original validation, even if that
  validation finds no defect. An actual dispute, known objection, different
  model or additional confirmation is not required.
- **Explicit user instruction controls:** a request for an opposing opinion
  makes the policy `required`; a request to omit it makes it `not_required`.
  Preserve such a choice when resuming the same assignment. Do not make it a
  permanent preference for other matters.

When no concrete position is requested, use the informational path. Ask only
if an unresolved ambiguity prevents determining the requested professional
result; do not add a routine question about the counter-opinion. A casual
"dammi un parere sul nuovo credito: spiegami come funziona" can be informational,
while a request to substantiate a client's entitlement can be an opinion without
using the word "parere". Interpret the full request in any conversation language.
If the user later changes the assignment, update the contract and review the
new scope before drafting. Ordinary research findings do not silently expand
the assignment into a counter-opinion.

## Finish the selected path

With `not_required`, package and deliver the answer through the ordinary
`deep-research-validator` workflow, retain its sources and unresolved questions,
and complete that validation run. Do not invoke the adversarial helper, create
`position/` or `adversarial/` phase folders, require `opinion_delivery.json`, or
claim that an opposing examination ran. Absence of the stage is not a finding
of `no_substantial_counterposition`: no separate examination was performed.

With `required`, package the reviewed original in `position/`, keep the same
validation run open, and follow `../../adversarial-opinion/SKILL.md`. Deliver the
original, reviewed opposing result and comparison with the combined delivery
verification. In hosts without local tools, apply the same scope and delivery
decision in chat and disclose the missing durable artifacts.

Research mode and adversarial scope are independent. After either ordinary
research or the installed Deep Research plugin, always validate the answer;
then follow the recorded adversarial policy.

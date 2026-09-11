---
name: quesito-legale-fiscale
description: Use when Vera receives a substantive legal, tax, or compliance question, analysis request, or source-backed professional drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for returns, declarations, filings, or forms whose correctness requires a dedicated operational workflow.
---

# Risposta A Quesiti Legali E Fiscali

This is Vera's user-facing specialist workflow for an ordinary substantive
legal, tax, or compliance question. Select it automatically from the user's
question. Do not require the user to invoke, choose, or understand the internal
planning and validation skills.

Follow the `Question To Validated Answer Journey` in `../vera/SKILL.md`. Treat
this skill as the matching specialist workflow for that journey, then:

1. Read `../prompt-optimizer/SKILL.md` completely and follow it before drafting
   or research. It prepares the answer contract, source posture, generation
   route, and generation instructions. Read `references/adversarial-scope.md`
   and follow it to record the model-led `adversarial_policy` and rationale:
   informational research uses `not_required`; an opinion on a concrete
   position uses `required`, subject to the user's explicit instruction.
2. Follow `../prompt-optimizer/references/research-choice.md`: after preparing
   the question, offer the available OpenAI Deep Research plugin for research
   and drafting, or Vera's usual research. Wait for the choice unless it is
   already explicit for this answer. Execute the selected route with the same
   brief and answer contract, then continue to validation. Keep a separately
   chosen ChatGPT-window handoff distinct from the installed plugin.
3. Read `../deep-research-validator/SKILL.md` completely and follow it before
   delivering a generated or supplied answer. Reuse the same answer contract,
   correct supported defects, and keep professional-judgment items explicit.
   With `not_required`, finish the ordinary validation workflow and deliver
   the reviewed answer with sources and limits. With `required` and local
   tooling, package the original in `position/` and keep the validation run open.
4. Only with `adversarial_policy: required`, read
   `../adversarial-opinion/SKILL.md` completely and follow it regardless
   of the original validation outcome. Develop and review the strongest
   substantiated opposing case with the current model; a reasoned negative or
   evidence-limited result is valid. Preserve both opinions and compare them.
5. Deliver the reviewed or corrected answer, its sources and validation limits.
   When the opposing examination was required, include its reviewed result and
   comparison and verify `opinion_delivery.json` through the adversarial helper
   before durable delivery. Informational research can finish after validation
   without an opposing document or combined opinion package. Do not stop after prompt preparation when direct generation is
   available, and do not describe a structurally complete record as proof of
   legal or tax correctness.

Planning and answer review retain separate Studio Archive
runs in the same client engagement when local Vera run capabilities are
available. Original validation and the adversarial stage share the latter run.
This orchestration skill does not create a third client workstream,
duplicate their artifacts, or introduce a new external data route. In ChatGPT
or another surface without local run tooling, continue with the useful in-chat
version required by the Vera runtime contract and state which durable artifacts
were not created.

Do not use this workflow to imitate an unsupported operational return,
declaration, filing, statutory form, signature, payment, or submission. Select
the dedicated Vera workflow when one exists; otherwise use Vera's no-matching-
specialist-workflow outcome.

Before substantive delivery, disclose the stages actually performed:

```text
Vera workflow: vera:quesito-legale-fiscale -> vera:prompt-optimizer -> vera:deep-research-validator
```

Append `-> vera:adversarial-opinion` only when the opposing examination ran.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

---
name: quesito-legale-fiscale
description: Use when Lucia receives a substantive legal, tax-law, or compliance question, analysis request, or source-backed legal drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for filings, signatures, submissions, or operational forms that require a dedicated workflow or the lawyer's direct action.
---

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../lucia/SKILL.md`.

# Risposta A Quesiti Legali E Fiscali

This is Lucia's user-facing specialist workflow for an ordinary substantive
legal, tax-law, or compliance question. Select it automatically from the
lawyer's request. Do not require the user to invoke, choose, or understand the
internal planning and validation skills.

Keep output language, governing law, jurisdiction, forum, and source hierarchy
as separate choices. Lucia normally delivers in Italian, but the applicable
law and qualified sources follow the matter rather than the output language.

1. Read `../prompt-optimizer/SKILL.md` completely and follow it before drafting
   or research. It prepares the answer contract, source posture, generation
   route, and generation instructions.
2. Generate the contracted answer directly when the current runtime can meet
   the required standard, or prepare the explicit ChatGPT Deep Research handoff
   when native Deep Research is materially needed.
3. Read `../deep-research-validator/SKILL.md` completely and follow it before
   delivering a generated or supplied answer. Reuse the same answer contract,
   correct supported defects, and keep professional-judgment items explicit.
4. Deliver the reviewed or corrected answer, its sources, unresolved issues,
   and validation limits as one result. Do not stop after prompt preparation
   when direct generation is available, and do not describe a structurally
   complete record as proof of legal correctness.

The two underlying skills remain separate stages with separate Studio Archive
runs in the same client engagement when local Lucia run capabilities are
available. This orchestration skill does not create a third client workstream,
duplicate their artifacts, or introduce a new external data route. In ChatGPT
or another surface without local run tooling, continue with the useful in-chat
version required by the Lucia runtime contract and state which durable
artifacts were not created.

Do not use this workflow to imitate a filing, signature, submission, statutory
form, portal action, client communication, or other operational act. Select a
dedicated Lucia workflow when one exists; otherwise use Lucia's no-matching-
specialist-workflow outcome. Governing-law conclusions, competing
interpretations, legal strategy, professional judgment, and the final version
to use remain with the lawyer.

Before substantive delivery, disclose:

```text
Lucia workflow: lucia:quesito-legale-fiscale -> lucia:prompt-optimizer -> lucia:deep-research-validator
```

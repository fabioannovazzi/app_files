---
name: quesito-professionale
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
   route, and generation instructions.
2. Generate the contracted answer directly when the current runtime can meet
   the required standard, or prepare the explicit ChatGPT Deep Research handoff
   when native Deep Research is materially needed.
3. Read `../deep-research-validator/SKILL.md` completely and follow it before
   delivering a generated or supplied answer. Reuse the same answer contract,
   correct supported defects, and keep professional-judgment items explicit.
4. Deliver the reviewed or corrected answer, its sources and validation limits
   as one result. Do not stop after prompt preparation when direct generation is
   available, and do not describe a structurally complete record as proof of
   legal or tax correctness.

The two underlying skills remain separate stages with separate Studio Archive
runs in the same client engagement when local Vera run capabilities are
available. This orchestration skill does not create a third client workstream,
duplicate their artifacts, or introduce a new external data route. In ChatGPT
or another surface without local run tooling, continue with the useful in-chat
version required by the Vera runtime contract and state which durable artifacts
were not created.

Do not use this workflow to imitate an unsupported operational return,
declaration, filing, statutory form, signature, payment, or submission. Select
the dedicated Vera workflow when one exists; otherwise use Vera's no-matching-
specialist-workflow outcome.

Before substantive delivery, disclose:

```text
Vera workflow: vera:quesito-professionale -> vera:prompt-optimizer -> vera:deep-research-validator
```

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

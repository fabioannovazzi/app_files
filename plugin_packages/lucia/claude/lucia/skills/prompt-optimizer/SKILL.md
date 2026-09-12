---
name: prompt-optimizer
description: Use automatically when Lucia must turn a lawyer's legal question into a verifiable answer contract, source plan, and generation instructions. This is the exact Prompt Optimizer implementation shared with Vera, not general prompt polishing.
---

# Imposta la risposta

Resolve `../../modules/prompt-optimizer` from this skill directory when it
exists; otherwise resolve `../../../prompt-optimizer` in the repository. Read
that module's `skills/prompt-optimizer/SKILL.md` completely and follow it.
Treat the resolved module root as the plugin working directory for every
command. Do not paraphrase, shorten, fork, or replace the component workflow.

Lucia's public experience and deliverables are in Italian. Preserve the
component's rule that language and jurisdiction are separate, and let it inspect
other-language sources whenever the legal framework requires them.

For the complete `quesito-legale-fiscale` journey, resolve the shared validator
module at `../../modules/deep-research-validator` from this skill directory, or
`../../../deep-research-validator` in repository source. Read its
`skills/deep-research-validator/references/research-choice.md` and follow it
after preparing the question and before finalizing the generation route and
semantic review. Reuse a choice already made for this answer. This does not
turn a preparation-only request into a full research assignment.

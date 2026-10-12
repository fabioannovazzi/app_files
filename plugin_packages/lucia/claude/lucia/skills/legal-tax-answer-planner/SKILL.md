---
name: legal-tax-answer-planner
description: Use automatically when Lucia must turn a lawyer's legal question into a verifiable answer contract, source plan, and generation instructions. This is the exact Legal/Tax Answer Planner implementation shared with Vera, not general prompt polishing.
---

# Imposta la risposta

Resolve `../../modules/prompt-optimizer` from this skill directory when it
exists; otherwise resolve `../../../prompt-optimizer` in the repository. Read
that module's `skills/legal-tax-answer-planner/SKILL.md` completely and follow it.
Treat the resolved module root as the plugin working directory for every
command. Do not paraphrase, shorten, fork, or replace the component workflow.

Lucia's public experience and deliverables are in Italian. Preserve the
component's rule that language and jurisdiction are separate, and let it inspect
other-language sources whenever the legal framework requires them.

For the complete `quesito-legale-fiscale` journey, resolve the shared validator
module at `../../modules/deep-research-validator` from this skill directory, or
`../../../deep-research-validator` in repository source. Read its
`skills/legal-tax-answer-review/references/research-choice.md` before finalizing
the contract. New research always uses `generation_route: codex_direct` and
`../deep-research/SKILL.md`, which resolves the one method shared by both
products. Do not offer a normal/deep choice or an external research-plugin route.
Preparation-only and supplied-answer review requests retain their scope.

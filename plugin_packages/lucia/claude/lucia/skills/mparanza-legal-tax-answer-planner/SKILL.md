---
name: mparanza-legal-tax-answer-planner
description: Use automatically when Lucia must turn a lawyer's legal question into a verifiable answer contract, source plan, and generation instructions. This is the exact Legal/Tax Answer Planner implementation shared with Vera, not general prompt polishing.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/mparanza-lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/mparanza-lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Imposta la risposta

Resolve `../../modules/prompt-optimizer` from this skill directory when it
exists; otherwise resolve `../../../prompt-optimizer` in the repository. Read
that module's `skills/mparanza-legal-tax-answer-planner/SKILL.md` completely and follow it.
Treat the resolved module root as the plugin working directory for every
command. Do not paraphrase, shorten, fork, or replace the component workflow.

Lucia's public experience and deliverables are in Italian. Preserve the
component's rule that language and jurisdiction are separate, and let it inspect
other-language sources whenever the legal framework requires them.

For the complete `quesito-legale-fiscale` journey, resolve the shared validator
module at `../../modules/deep-research-validator` from this skill directory, or
`../../../deep-research-validator` in repository source. Read its
`skills/mparanza-legal-tax-answer-review/references/research-choice.md` before finalizing
the contract. New research always uses `generation_route: codex_direct` and
`../mparanza-deep-research/SKILL.md`, which resolves the one method shared by both
products. Do not offer a normal/deep choice or an external research-plugin route.
Preparation-only and supplied-answer review requests retain their scope.

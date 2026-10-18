---
name: quesito-legale-fiscale
description: Use when Lucia receives a substantive legal, tax-law, or compliance question, analysis request, or source-backed legal drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for filings, signatures, submissions, or operational forms that require a dedicated workflow or the lawyer's direct action.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


<!-- LUCIA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../lucia/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- LUCIA_OPENAI_ONBOARDING_END -->

# Risposta a quesiti legali e fiscali

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../lucia/SKILL.md`.

This is Lucia's user-facing journey from a substantive legal, tax or
compliance question to a reviewed answer. Select it automatically for the
requested complete answer; the user need not choose internal stages.

Resolve `../../modules/deep-research-validator` from this skill directory when
it exists; otherwise resolve `../../../deep-research-validator` in repository
source. Read that module's
`skills/legal-tax-answer-review/references/answer-journey.md` completely and
follow it. Research resolves that same module's `skills/deep-research/SKILL.md`.
The invoking product root is two levels above this skill directory.
Use this product's `../legal-tax-answer-planner/SKILL.md`,
`../legal-tax-answer-review/SKILL.md` and, only when required,
`../adversarial-opinion/SKILL.md`. Do not fork or summarize the shared method.

Every new research assignment uses `../deep-research/SKILL.md`, which resolves
one shared method with repeated investigation, continuous validation and
adversarial challenge using the current host model and tools. Retain
`generation_route: codex_direct`; do not offer a normal/deep selector or depend
on an external research plugin. Final validation and, when required, the
reviewed opposing opinion can reopen targeted research in the same run.
Informational research completes after final validation. A concrete opinion or
an explicit opposing-opinion request includes the final opposing examination
unless the user asks to omit it. Early challenges do not replace that stage.

Lucia normally delivers in Italian, unless the user requests another language.
Keep governing law, jurisdiction, forum and source hierarchy separate from
output language. Final interpretations, strategy, signatures, filings, client
communications and professional approval remain with the lawyer.

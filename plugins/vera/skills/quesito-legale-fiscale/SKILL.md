---
name: quesito-legale-fiscale
description: Use when Vera receives a substantive legal, tax, or compliance question, analysis request, or source-backed professional drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for returns, declarations, filings, or forms whose correctness requires a dedicated operational workflow.
---

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Before substantive work in desktop Codex or local ChatGPT Work, follow the
mandatory one-off local onboarding gate in `../vera/references/local-onboarding.md`.
Load the same local professional profile on every session. A verified paired
lesson worker follows only its active lesson handoff; never recursively onboard
it. Tutorial runs and their feedback stay local. Current user requests take
precedence over saved preferences. This gate does not apply to Claude Cowork.
<!-- VERA_OPENAI_ONBOARDING_END -->
# Risposta a quesiti legali e fiscali

This is Vera's user-facing journey from a substantive legal, tax or
compliance question to a reviewed answer. Select it automatically for the
requested complete answer; the user need not choose internal stages.

Resolve `../../modules/deep-research-validator` from this skill directory when
it exists; otherwise resolve `../../../deep-research-validator` in repository
source. Read that module's
`skills/deep-research-validator/references/answer-journey.md` completely and
follow it. The invoking product root is two levels above this skill directory.
Use this product's `../prompt-optimizer/SKILL.md`,
`../deep-research-validator/SKILL.md` and, only when required,
`../adversarial-opinion/SKILL.md`. Do not fork or summarize the shared method.

Informational research completes after validation. A concrete opinion or an
explicit opposing-opinion request includes the opposing examination unless the
user asks to omit it. The same shared method makes the Deep Research choice
independently and preserves professional review and the no-local-tools fallback.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

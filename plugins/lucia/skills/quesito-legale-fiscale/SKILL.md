---
name: quesito-legale-fiscale
description: Use when Lucia receives a substantive legal, tax-law, or compliance question, analysis request, or source-backed legal drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for filings, signatures, submissions, or operational forms that require a dedicated workflow or the lawyer's direct action.
---

# Risposta a quesiti legali e fiscali

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../lucia/SKILL.md`.

This is Lucia's user-facing journey from a substantive legal, tax or
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

Lucia normally delivers in Italian, unless the user requests another language.
Keep governing law, jurisdiction, forum and source hierarchy separate from
output language. Final interpretations, strategy, signatures, filings, client
communications and professional approval remain with the lawyer.

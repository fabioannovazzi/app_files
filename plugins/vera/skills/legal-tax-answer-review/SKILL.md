---
name: legal-tax-answer-review
description: Use automatically before Vera delivers any generated or supplied legal, tax, or compliance answer—including a research report, memo, or one-page letter—against its answer contract and available sources, with source support, reasoning, and professional judgment separated. Do not use this skill to imply operational completeness for a return, declaration, filing, or form that lacks a dedicated workflow.
---

<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../vera/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- VERA_OPENAI_ONBOARDING_END -->

## Legal/tax model preference

Read `../vera/references/legal-tax-model-policy.md`. Prefer the most capable
available host model; this is advice, never a gate. Continue with the active
model when it differs, is unknown or changes, including in a new chat or any
authorized delegation. Record available provenance without requiring a switch,
confirmation, plugin UI or model API credentials.

# Validate Answer

For subscription evidence, read `../vera/references/research-subscriptions.md`.
Review the actual retained passages and their recorded access/retention limits;
use genuine captures with `--no-fetch` when an authenticated source cannot be
publicly fetched. A saved connection or access-check result is never claim support.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/deep-research-validator` from this skill directory when
it exists; otherwise resolve `../../../deep-research-validator` in the
repository. Read that module's `skills/legal-tax-answer-review/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands.

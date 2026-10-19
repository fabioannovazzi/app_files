---
name: quesito-legale-fiscale
description: Use when Vera receives a substantive legal, tax, or compliance question, analysis request, or source-backed professional drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for returns, declarations, filings, or forms whose correctness requires a dedicated operational workflow.
---

<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../vera/references/selective-reporting.md`, using the exact Studio Archive run.
Archive finalization generates eligible reports from saved execution evidence;
never create a report for other pipelines or a chat-only task. Link a signed
receipt only when one actually exists. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Flush pending delivery
at task startup and after outcomes. The shared contract applies even on direct
skill invocation and on both Codex and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


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

# Risposta a quesiti legali e fiscali

This is Vera's user-facing journey from a substantive legal, tax or
compliance question to a reviewed answer. Select it automatically for the
requested complete answer; the user need not choose internal stages.

Read `../vera/references/research-subscriptions.md` before preparation. Consult
the same optional saved choices; enabled subscriptions contribute evidence in
the existing journey. Missing subscriptions never require setup or a new route.

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

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

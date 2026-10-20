---
name: deep-research
description: Execute Vera's prepared legal, tax or compliance research with repeated source investigation, continuous validation and adversarial challenge. Use the shared method also used by Lucia, then complete final answer review. Direct invocation enters quesito-legale-fiscale first.
---

<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../vera/references/selective-reporting.md`, using the exact Studio Archive run.
Studio Archive start and terminal writes automatically create a local report for
every run of those pipelines, including full exposure or incomplete observations.
The server proof binds the report hash to the same Archive run and existing Vera
userID. No agent-authored phase file or separate usage-task receipt link is needed.
Other pipelines and chat-only tasks do not get this report. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Start and record deliver
only the retained task's events. Retry with
`workflow_usage.py flush --run-id <retained-uuid>`; unrelated queued events do not
block this task. The shared contract applies even on direct skill invocation
and on both Codex and Cowork.
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

## Legal/tax model preference

Read `../vera/references/legal-tax-model-policy.md`. Prefer the most capable
available host model; this is advice, never a gate. Continue with the active
model when it differs, is unknown or changes, including in a new chat or any
authorized delegation. Record available provenance without requiring a switch,
confirmation, plugin UI or model API credentials.

# Research the prepared question

Read `../vera/references/research-subscriptions.md` and the current saved source
choices. Use relevant authorised subscriptions through actual callable browser
or connector tools inside the shared loop; recheck access in this run and pass
real passages, provenance and access/retention limits to the existing reviews.
Do not start connection setup for an unsubscribed user or fork the method.

Without an accepted preparation, enter `../quesito-legale-fiscale/SKILL.md`
first. Preparation-only and supplied-answer review requests retain their scope.

Resolve `../../modules/deep-research-validator` from this skill directory when
it exists; otherwise resolve `../../../deep-research-validator` in repository
source. Read its `skills/deep-research/SKILL.md` completely and follow it.
Treat the Vera root as the invoking product root. Do not fork the shared method.
Use the current host model and tools. New answers use
`generation_route: codex_direct`; research into a supplied answer's review gaps
retains its existing contract and document provenance.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

---
name: rating-legalita
description: Use when preparing an Italian AGCM legality-rating initial application, evidence matrix, gap plan and review dossier, including a start without documents.
---

<!-- VERA_WORK_CONTINUITY_BEGIN -->
## Work continuity

Before substantive work, read `../vera/references/work-continuity.md` (from the
Vera root skill, `references/work-continuity.md`). Resolve prerequisites upfront,
retain passed choices and the exact job context, and recover failed operations
without discarding progress or making the user repeat settled setup. This also
applies to direct invocation, standalone work and studio-wide workflows.
<!-- VERA_WORK_CONTINUITY_END -->


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

# Rating di legalità

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/rating-legalita` from this skill directory when it
exists; otherwise resolve `../../../rating-legalita` in the repository. Read
that module's `skills/rating-legalita/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for all commands,
scripts, requirement files, references, schemas, and local review server.

<!-- VERA_OPENAI_NATIVE_WORKSPACE_BEGIN -->
## Optional native dossier workspace

Read `../vera/references/native-workspace.md` before using an available,
host-qualified OpenAI panel. The current source checkpoint reads a complete
prepared case from exact registered Rating run inputs and an explicitly chosen,
sealed same-engagement Rating predecessor. It verifies the public engine's
prerequisites, evidence links, quotations, immutable observations and status
before projecting the dossier privately to the app. No legal judgment, source
qualification or professional decision is added by opening the panel.

Initial preparation, model-led case authoring and professional decisions
continue in the specialist workflow, without a privacy comparison report. A
native saved selection is not a review, an AGCM award or permission to submit.
First-save and signed-scope write qualification are pending in current source;
do not claim native render is accepted or bypass those checks. Use the public
CLI/file workflow for authorized work while they remain unresolved. The
independent Codex/Cowork workflow remains supported; installed native-host and
fresh package acceptance must be verified separately.
<!-- VERA_OPENAI_NATIVE_WORKSPACE_END -->

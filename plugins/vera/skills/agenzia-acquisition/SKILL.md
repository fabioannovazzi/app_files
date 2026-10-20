---
name: agenzia-acquisition
description: Acquire Agenzia delle Entrate invoices, corrispettivi and quarterly bolli for selected delegated clients; resume verified originals, review exceptions and prepare an explicitly reviewed F24 working paper through Vera's single local worker and optional native panel.
---

# Acquisizione Agenzia delle Entrate

Resolve `../../modules/browser-automation` from this skill directory when it
exists; otherwise resolve `../../../browser-automation` in the source repository.
Read that module's `skills/agenzia-acquisition/SKILL.md` completely and follow it.
Treat its root as the working directory for the ordinary acquisition commands.

This is the sole Agenzia acquisition route. The optional `agenzia_workspace_open`
MCP Apps thread panel and ordinary commands operate on the same worker and saved
files. Do not select a generic teaching capability or reconstruct another runner.
Keep authentication in the operator's visible local Chrome window. Preserve
ordinary command/file delivery where native UI is unavailable.

Follow the current Vera shared Python runtime and model-data report contracts in
`../vera/references/`. After substantive ordinary use, follow the Plugin
Improvement Feedback section in `../vera/SKILL.md`; user-requested tutorials use
the existing local course flow and do not send CRs or delivery stamps.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

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

## Archive reporting boundary

Every plan client must have its exact Archive client and engagement binding.
Starting acquisition creates and starts one Archive run per client before
the worker runs. Its selected client plan is the initial receipted input. The
worker saves client-specific evidence into those runs without closing them
before model review. Each acquired original is measured automatically against its
verified acquisition record. Use the Archive read tool for subsequent inspection;
Vera records its returned data before sending it. After review, declare professional outputs,
finalize and complete the same Archive run. No report-input file is required.
Use `archive-runs.json` to resolve the exact runs, never the worker UUID as a
report run identity. Do not create a second report in the acquisition folder.

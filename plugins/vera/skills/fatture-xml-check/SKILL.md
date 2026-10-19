---
name: fatture-xml-check
description: "Use when checking Italian FatturaPA XML files in a customer folder, summarizing invoice metadata, and identifying malformed XML, date issues, or duplicate candidates."
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

# Fatture XML Check

Before inspecting XML sources, prepare and start the exact Studio Archive run
with workflow_id `fatture-xml-check`. Pass its context to the file-preparation
engine. Do not reuse a `client-file-preparation` or New Client run for this
separate check; those broader processes are outside selective reporting.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/client-file-preparation` from this skill directory when it exists;
otherwise resolve `../../../client-file-preparation` in the repository. Read that
module's `skills/fatture-xml-check/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.


## Optional maintained Codex review panel

Read `../vera/references/native-workspace.md` before opening the panel.

Open the maintained Studio Archive workspace on Codex and choose the exact client-file-preparation run. **Fatture XML · corpi** pages every retained invoice body as read-only metadata. **Anomalie XML e duplicati** pages the complete anomaly queue and compares all members of a formal duplicate candidate group side by side, including multiple bodies in one file. Record an explicit decision only on canonical review items. A candidate is not proof of a duplicate; no invoice is deleted or booked. Discussion exposes only the exact selected saved record after the user requests it.

The ordinary connected-file workflow remains available when the native panel is unavailable.

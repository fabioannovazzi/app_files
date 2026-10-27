---
name: journal-sampling
description: Use to extract a reproducible campione di scritture from a giornale contabile in reviewed CSV/XLSX, including supported print layouts and reviewed registration-style text PDFs. Qualifies the population, normalizes monetary rows and returns the sample, diagnostics and selection trail. For checking an already qualified sample against fatture XML/PDF use vouching; this step does not verify supporting documents.
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

# Journal Sampling

For an already prepared sample, use `vera_workspace_open` when callable and the
exact Studio Archive run has a trusted operator binding. Read
`../vera/references/native-workspace.md` before the handoff. The panel reviews the
maintained sample and decisions; discussion retrieves only the exact selected item
from its replay-verified model context. It preserves population qualification,
normalization, selection lineage and unresolved professional gates. Initial
population review and sample preparation remain in the specialist workflow.
Without native tools or a trusted binding, continue the persistent specialist
route, including in Cowork. Reviewing a sample does not verify its documents.

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In local Codex, use a prepared and started customer-folder run bound to one
exact immutable journal receipt. Finalize every output with purpose and
audience. The normalized population, diagnostics, and exact sample are separate
upstream artifacts. Start Vouching through
`start_check_entries_from_sample`; Studio Archive resolves those internal
artifacts and Vouching checks only the sample rows.

First follow `../vera/references/execution-recovery.md` for component
`journal-sampling`. Use its verified execution root for the handoff below;
never ask the professional to run a terminal command.

Resolve `../../modules/journal-sampling` from this skill directory when it
exists; otherwise resolve `../../../journal-sampling` in the repository. Read
that module's `skills/journal-sampling/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for all commands.


For a text-PDF journal, follow the module's `registration_pdf` intake: inspect
bounded coordinate evidence, review the source-bound physical layout, qualify
every completed registration, then normalize and sample. Dates in registration
headers and postings continued across pages are supported by that adapter.
Readable text alone does not qualify amounts or posting boundaries. Retain
incomplete-population diagnostics and readable partial entries. Use the recovery
adapter contract for unfamiliar structure; never claim qualification from text
extraction alone.

For recoverable ruled/PCL journal layouts, use the component's maintained
`references/pdf-recovery.md` inspection–trial–freeze loop before closing an
unsupported-layout result. Review targeted evidence and revise a recipe or write
a run-local source-reference adapter using ordinary host tools. Retain attempts
and readable entries, require independent checks and full-source replay plus the
ordinary source-mapping receipt, and report technical issues and recoveries
through the incident pipeline. Keep population operations blocked until complete
qualification. Installed code and validators are not changed by local recovery.

For reviewed recipes and run-local PDF adapters, use `write_studio_run_artifact`
with this run's exact client, engagement and run IDs. Send the full text, wait
for success, and pass the returned path to the specialist helper. Use a new
filename for a revision. Do not save these prerequisites through the chat shell.

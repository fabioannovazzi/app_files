---
name: open-item-reconciliation
description: Use to verify a supplied elenco partite aperte clienti o fornitori at a cut-off against mastrini, journal, bank statements, payments, factoring, advances or compensation. Produces closed, partly closed and still-open items, residuals and exceptions. For direct estratto conto versus prima nota matching use journal-bank-reconciliation.
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

# Riconciliazione partite

For normal CSV/XLSX work, use the maintained import-to-delivery operation in
`../../modules/studio-archive/scripts/reconcile_open_items.py` (repository:
`../../../studio-archive/scripts/reconcile_open_items.py`). Inspect the selected
sources and write one request using the component's
`references/simple-reconciliation.md`. Invoke it through `vera_execute` with
component `studio-archive`, script `scripts/reconcile_open_items.py`, and
`arguments=["--request", "<absolute request path>"]`. Reuse the request to reopen
its saved result; do not assemble the import/start/produce/finalize sequence or
repeat calculation after success. Only unresolved material choices require a
question. The agent supplies mappings; technical reviewer labels are generated.

Read `accounting_status`, `report_ready` and the returned artifacts. Exact,
unique, source-verified matches complete automatically. Deliver those files
directly; the browser is optional. For `review_required`, deliver the draft and
its unresolved items, then use the existing review tools for the remaining
decisions. After review/regeneration, call the same operation with
`--finish-run <run_id>`. Never invent human approval. A data-usage warning is
reported alongside the result; it does not negate a verified reconciliation or
justify rerunning it. Preserve the warning and the saved data-usage report.

For a prepared and started run with exact registered source receipts, the
optional native workspace also offers initial preparation. It preserves private
unfinished scope and per-source choices without restoring confirmation. The
reviewer declares every source's role, maintained adapter, perimeter, money and
date conventions and the evidence policies; filenames do not authorize those
choices. Originals up to 4 MiB can be consulted privately in the panel; larger
documents remain in the registered Archive folder. After renewed explicit
review, the panel calls the unchanged raw producer in `outputs/reconciliation/`
and replays assurance, retaining its complete outputs and failed gates. It then
hands back to the existing review. No source qualification, professional
approval or Archive completion is inferred from a draft or successful call.
Interrupted intents or existing partial outputs require specialist recovery
without automatic repetition. Read `../vera/references/native-workspace.md`
before this handoff. These source-qualified controls still require installed
native-host and representative professional acceptance; use the ordinary
persistent specialist route when the panel is unavailable, including in Cowork.

For an already prepared review, use `vera_workspace_open` when callable and the
exact Studio Archive run has a trusted operator binding. Read
`../vera/references/native-workspace.md` before the handoff. The panel uses the
maintained Python review service; discussion retrieves only the selected case
through the existing public model projection. Assured Apply requires the exact
predecessor checkpoint retained independently of mutable run outputs. After Apply, `vera_workspace_open_items_regenerate` can rebuild a raw-input
package that retains its original report settings and uses its package-owned
default cache. It re-extracts the same registered sources, uses only the applied
professional review and performs fresh successor assurance replay inside the
maintained whole-tree transaction. Title and narrative are preserved. Missing
settings, normalized-only packages or custom cache locations keep the specialist
route; never infer settings or read a checkpoint from the candidate tree.
Regeneration does not complete the Archive run or waive remaining checks. Initial
intake, mapping and source qualification retain their existing gates. Without
native tools or a trusted binding, continue persistent specialist work, including
in Cowork. Keep the output/disclosure boundary below unchanged.

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

First follow `../vera/references/execution-recovery.md` for component
`open-item-reconciliation`. Use its verified execution root for the handoff below;
never ask the professional to run a terminal command.

Resolve `../../modules/open-item-reconciliation` from this skill directory when it
exists; otherwise resolve `../../../open-item-reconciliation` in the repository.
Read that module's `skills/open-item-reconciliation/SKILL.md` completely and follow
it. Treat the resolved module root as the plugin working directory for scripts,
requirements, assets, review servers, and outputs.

For a new Vera run, pass `--output-subdirectory reconciliation` to the native
`raw_input_runner.py` command. Keep that same option on regeneration. The native
assured package is then in the bound run's `outputs/reconciliation/`; use that
directory for its review server and assurance validation. Write the required
local model-data disclosure in the owning `outputs/` directory, outside the
exact native assurance boundary. Declare both the nested package and disclosure
when finalizing the Studio Archive run. Never add the disclosure to an already
sealed native assurance directory or alter its receipt to make extra files pass.

---
name: journal-bank-reconciliation
description: Use to reconcile estratti conto bancari with prima nota, giornale contabile or mastrini from reviewed CSV/XLSX or consistently labelled text-PDF tables. Produces matched movements, unmatched rows, residuals and reviewable workpapers. For checking a supplied elenco partite aperte at a cut-off use open-item-reconciliation. OCR-only bank statements are unsupported.
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

# Journal-Bank Reconciliation

Before inspecting supplied bank/journal files or creating any client, engagement
or run, follow "Check supplied files before starting client work" in
`../vera/SKILL.md`: call `check_studio_import_sources` for both sets of files on
the Archive import host. If any input is unavailable, explain the access problem
and folder-connection option immediately, before creating anything. After a late
import failure, report and reuse the existing client and engagement IDs.

When the user chooses the native review panel, use `vera_workspace_open` when
callable and the exact Studio Archive run is authorised through the owned archive
or a trusted operator binding. The panel is optional: ordinary chat preparation
uses the persistent specialist route below, with recorded agent review of routine
source mappings. Do not require panel confirmation to prepare or deliver drafts.
Read `../vera/references/native-workspace.md` before the handoff. The panel opens
the maintained review service; explanations use only its selected-case projection
with exact identifiers omitted by default. Retain the source-bound mapping,
material-value replay, residual review and unsupported-PDF gates below. A running
run without outputs also offers native initial inspection: the user explicitly
assigns the exact imported bank/journal inputs and optional single sample, reviews
every proposed file mapping and the documented currency/entity and relationship
policy, then executes the maintained reconciliation after source qualification.
Only explicit selected-source discussion sends a bounded producer preview of at
most 20 rows to the model. Exact source copies and each inspection/review remain
inside this run; decisions use the maintained public receipt builders. Results
open in the existing review adapter and do not complete or approve the run.
Unsupported layouts remain blocked. Interrupted uncertain execution preserves
artifacts and requires specialist recovery; the panel never silently reruns it.
Unsent source roles/languages and raw mapping/policy fields can be retained in a
local actor/tenant/run draft outside official outputs. Recovery is explicit and
requires the unchanged preparation revision; stale drafts cannot be applied to
new sources. A draft is neither a reviewed receipt nor authorization to execute.
The professional confirmation is never recovered. Exact draft checkpoints reject
concurrent replacement; a denied save or teardown must not claim persistence.
Initial imports, artifact handoffs, the separate residual worker, finalization
and recovery remain specialist-led. Without native tools
or a trusted binding, continue the existing persistent specialist route, including
in Cowork; native availability never substitutes for professional review.

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

First follow `../vera/references/execution-recovery.md` for component
`journal-bank-reconciliation`. Use its verified execution root for the handoff
below; never ask the professional to run a terminal command.

For this Archive run, discover `read_studio_run_artifact` and use its exact
client, engagement and run IDs to read source previews and generated artifacts
into model context. This includes inspection JSON, audits, review notes and
worker receipts. Shell commands that print those files are outside the report's
measurement boundary. The component's `run-all` returns the retained worker
receipt paths after archiving; use those paths for the subsequent recorded read.

Resolve `../../modules/journal-bank-reconciliation` from this skill directory
when it exists; otherwise resolve `../../../journal-bank-reconciliation` in the
repository. Read that module's `skills/journal-bank-reconciliation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands.

The base bounded source contract is `journal_bank.tabular.v6`: ambiguous
day/month text requires a source-bound `day_first` or `month_first` receipt.
The additive `journal_bank.tabular.v7` contract requires an exact current
mapping receipt for Italian textual-month dates (`date_locale: it`) or reviewed
blank-date/no-reference summary labels; it never silently upgrades v6 sources.
Before reporting native values, require the module's fresh
`material_value_ledger.json` replay and review the unclassified exact
`relationship_residuals.csv`; do not infer a residual disposition.

The module may admit a journal text PDF through its reviewed registration
adapter, including dates in registration headers and cross-page postings.
Read the module’s Registration-style journal PDF instructions and use its
bounded coordinate evidence, layout/mapping receipts and closure checks.
Bank PDFs require their own table mapping or the bank source-reference recovery
adapter described in the module's `references/pdf-recovery.md`.

The module may otherwise admit a text PDF only when inspection recovers a consistent,
labelled physical table and the professional approves a source-bound mapping
of date, incoming/outgoing or signed amount, sign convention, and every
excluded monetary column such as running balance. If either source is generic,
inconsistent, or OCR-only PDF text, follow the module's unsupported PDF hard
stop for population-dependent operations. Use ordinary host inspection and the
source-reference adapter recovery contract to solve unfamiliar reading issues.
Preserve readable partial entries and explicit unresolved issues. Preserve
`vera:journal-bank-reconciliation` as the workflow provenance, report zero
emitted movements and no reconciliation deliverable, request a labelled text
PDF table or reviewed CSV/XLSX export, and stop dependent work.

For unfamiliar journal or bank statement layouts, use the component's maintained
`references/pdf-recovery.md` inspection–trial–freeze loop before closing an
unsupported-layout result. Review targeted evidence and revise a recipe or write
a run-local source-reference adapter using ordinary host tools. Retain attempts
and readable entries, require independent accounting/source checks and fresh
replay plus the ordinary source-mapping receipt, and report technical issues and
recoveries through the incident pipeline. Resume the original reconciliation;
extraction success is not task completion. Installed validators remain unchanged.
Select `--pdf-side bank` for bank recovery (journal is the default), and
`--pdf-source` for one PDF inside a bound source folder. Bank layouts live under
`bank.files[filename].pdf_bank_layout`, with separate per-source histories.
The bank checker verifies original monetary tokens, printed balances or movement
totals, and source coverage. Review document scope and column semantics through
the normal mapping receipt; an individual payment confirmation is not a complete
bank statement. Retain readable bank entries when those checks cannot pass.

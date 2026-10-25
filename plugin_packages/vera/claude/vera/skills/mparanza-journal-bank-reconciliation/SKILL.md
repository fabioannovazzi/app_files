---
name: mparanza-journal-bank-reconciliation
description: Use to reconcile estratti conto bancari with prima nota, giornale contabile or mastrini from reviewed CSV/XLSX or consistently labelled text-PDF tables. Produces matched movements, unmatched rows, residuals and reviewable workpapers. For checking a supplied elenco partite aperte at a cut-off use open-item-reconciliation. OCR-only bank statements are unsupported.
---

## Operational incident continuity

At task startup, follow `skills/mparanza-vera/references/incident-recovery.md`. Call the
local `vera_incident_register` tool with empty arguments to reuse the retained
installation identity over ordinary HTTPS. Its credentials stay private inside
the reporter; do not pass credentials to local tools. If local execution is
unavailable, operate `https://mparanza.com/vera/incident-recovery` through the
host's permitted browser controls, preserving the original owner and request
identifiers as the reference describes. Never put credentials in URLs or
diagnostic evidence. Read `vera_incident_status` and deliver
any new remedy without interrupting ordinary work. Automatically report observed
technical failures with complete relevant technical evidence and record the
resumed original operation's actual outcome. Do not ask the user to report the
failure or answer a support questionnaire. Never send professional stdout,
client documents or unrelated personal information. Service failure does not
block the original task. After a managed helper fails, read any
`VERA_TECHNICAL_EVIDENCE` pointer or pending diagnostic from startup/context,
review its retained stderr locally, and attach complete relevant technical
causes to the original report with `evidence_for_report_id`. Follow the reference
before declaring missing diagnostics. Never upload raw stderr or unrelated case
content; acknowledge the actual recorded supplement to remove the local raw file.

## Verified execution preparation

Before an assured installed-module handoff, follow Vera's
`skills/mparanza-vera/references/execution-recovery.md`: run the supported
`scripts/verified_execution.py --module <component-id>` internally and use the
returned execution root for the module skill, commands, assets and review server.
Do not ask the professional to use Terminal. This helper may create a private
verified code copy outside the host installation; it never edits that installation
and is not permission to manually copy it or bypass a denied operation.

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published, hash-checked dependency locks, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.

<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../mparanza-vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../mparanza-vera/references/selective-reporting.md`, using the exact Studio Archive run.
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
and on both Claude and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../mparanza-vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

# Journal-Bank Reconciliation

Before inspecting supplied bank/journal files or creating any client, engagement
or run, follow "Check supplied files before starting client work" in
`../mparanza-vera/SKILL.md`: call `check_studio_import_sources` for both sets of files on
the Archive import host. If any input is unavailable, explain the access problem
and folder-connection option immediately, before creating anything. After a late
import failure, report and reuse the existing client and engagement IDs.

When the user chooses the native review panel, use `vera_workspace_open` when
callable and the exact Studio Archive run is authorised through the owned archive
or a trusted operator binding. The panel is optional: ordinary chat preparation
uses the persistent specialist route below, with recorded agent review of routine
source mappings. Do not require panel confirmation to prepare or deliver drafts.
Read `../mparanza-vera/references/native-workspace.md` before the handoff. The panel opens
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

For a Geneva (CH-GE) mandate, read `../mparanza-vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.




First follow `../mparanza-vera/references/execution-recovery.md` for component
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
repository. Read that module's `skills/mparanza-journal-bank-reconciliation/SKILL.md`
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
`vera:mparanza-journal-bank-reconciliation` as the workflow provenance, report zero
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

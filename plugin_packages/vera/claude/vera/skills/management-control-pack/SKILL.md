---
name: management-control-pack
description: Prepara il controllo di gestione da export contabili oppure analizza costi e margini per commessa, prodotto o cliente, con Direct, Direct Evoluto, Full o ABC e scenari decisionali riveduti. Include P&L, budget/forecast, aging e cassa quando pertinenti. Per i soli scostamenti usa variance-analysis.
---

## Cowork execution contract

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
environment per OS host with the published shared requirements, outside client
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

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

# Management Control Pack



Resolve `../../modules/management-control-pack` from this skill directory when
it exists; otherwise resolve `../../../management-control-pack` in the
repository. Read that module's `skills/management-control-pack/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for dependency checks and helper commands.

For budget monitoring and a client report through Sites, use the resolved module's budget/forecast and Sites delivery instructions. This is distinct from preparing a business plan.

For a focused costing question, follow that module's `references/costing.md`.
Keep the same workflow identity and archive run, select only relevant methods,
and preserve the normal calculation, commentary and disclosure receipts.

## Optional native workspace

When the current host exposes the maintained workspace tools and the user
chooses the panel, follow `../vera/references/native-workspace.md`. The panel
can select exact registered sources and a complete already reviewed recipe or
costing case, retain incomplete choices privately and calculate through the
unchanged producers after a separate confirmation. Reporting and costing remain
distinct; focused costing does not require a general ledger.

For interpretation, explicitly read `vera_workspace_management_commentary_context`
for the exact calculation. It returns the ordinary bounded calculated context,
verified receipts, template and optional expressly selected whole commentary.
It excludes raw originals, the full pack and unsent named readback by default.
Use the actual metric identifiers in the returned records; the reporting and
costing producers retain their existing record shapes. Prepare the complete
normal commentary, distinguishing observations, hypotheses, questions and limits.
Do not infer causation or professional approval. Stage it through
`vera_workspace_management_commentary_stage` only when the current public
calculation permits finalization. Larger complete commentary stays on the
maintained file path; do not truncate it to fit the panel.

The panel separately captures the professional's complete declared decision,
name, actual timezone-aware time and basis. Signed confirmation conserves the
literal comment and readback in the same run. Acceptance uses unchanged
`finalize_pack.py` for all three normal draft report outputs. Rejection or a
request for changes retains the comment and decision without finalizing a report.
Calculation files remain immutable. Record only actual model reads in the normal
run report; app reads and chat-request text do not prove model exposure.

The optional source-preparation prototype retains a literal question,
reporting/costing path, selected original receipt IDs and optional prior case.
A renewed source mandate permits `vera_workspace_management_author_context`
to name only expressly granted original/prior-case paths and hashes, public
method/intake references and an optional explicitly chosen complete proposal
path. Read authorized originals with maintained readers; inspection samples
are not the population. Record actual model exposure separately.

Stage `proposal={case:whole_ordinary_payload,note:open_items}` through
`vera_workspace_management_author_stage`. New reporting mapping_review must
remain exactly `{status:"not_reviewed",reviewer:"",reviewed_at:""}`; never
manufacture human attribution. Preserve prior case/reviews separately. Costing
keeps the whole ordinary payload, exact client/engagement and selected-source
evidence hashes, without a ledger requirement or mechanically chosen semantic
roles, classifications or methods. Larger whole work stays on the file path.

Named complete-case readback, new-run registration, calculation and commentary
review are separate. Current source registration and closure audit have missing
archive_root/digest/load_binding capability wiring. The verified three-line review proposal
remains unapplied pending the repository operating-rule exception; do not claim
this native lifecycle qualified until the repair is applied and retested.
Preserve the complete specialist file path while integration remains incomplete.

Open the normal HTML through `preview_report.py` as described by the component;
interactive panel opening is pending. Preserve earlier versions, full workbook,
HTML and receipts. Signing, delivery and Archive completion remain separate.
Missing native tools do not block file work.

---
name: esg-reporting-assurance
description: Organize one ESG engagement's evidence, versions and professional decisions in Studio Archive; export partial foundation drafts, without claiming complete ESG reporting or assurance.
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

# Fascicolo ESG

Onboarding is optional and must never block ordinary professional work.


Resolve `../../modules/esg-reporting-assurance` from this skill directory in
installed Vera, or `../../../esg-reporting-assurance` in repository source.
Read that module's `skills/esg-reporting-assurance/SKILL.md` completely.
Use the module root as the plugin working directory for helper commands.
Use the existing Studio Archive client, engagement and exact selected input IDs.
The current delivery is the evidence/decision foundation only. Do not present
full reporting, ESRS, taxonomy or assurance as implemented.

## Optional native evidence/version consultation

When this host exposes `vera_workspace_open`, explicitly select the owned ESG
run and open its ESG page. `vera_workspace_esg_setup` lists all retained versions
in thirty-row pages, newest first. `vera_workspace_esg_read` privately shows one
complete chosen object, exact dependencies and the public current/stale status.
`vera_workspace_esg_outputs` privately opens the actual conserved Markdown/JSON
of a partial draft; it does not regenerate, approve or publish it.

Only a requested discussion calls `vera_workspace_esg_context` with the exact
work_ref, source_ref and current revision. It returns the complete selected
version and recursive exact dependency records, including stale historical
observations, declared reviewer names/reasons and draft text. It refuses content
over 64 KiB without truncation. Original input files are not automatically read
and actual model reads remain to be recorded in the ordinary run report.

## Optional native authoring under qualification

The new native authoring routes are source work under qualification. A macOS
temporary-preview path refusal is awaiting an explicit repository exception;
do not report their public mutation acceptance as passed in production source.
Actual installed-host/model acceptance also remains pending. The maintained
ordinary commands above remain available in Claude/Cowork.

When these tools are available, the human uses vera_workspace_esg_author_setup
and private draft saving to choose a literal question, one public operation and
exact registered original IDs. A predecessor is optional and must be explicitly
selected from another ESG run in the same engagement; never infer the latest.
Renewed signed confirmation issues author_request. No service, jurisdiction,
reporting period or framework is silently selected.

Only after that mandate, use vera_workspace_esg_author_context with the exact
work_ref, grant_ref and current revision. Read the full specialist skill and
public schema at the returned paths, the selected original paths and hashes,
and any explicitly granted current/predecessor state or selected proposal.
Record actual reads separately; returned paths do not establish a model read.
Unsent human decision drafts are excluded from this route.

The model may call vera_workspace_esg_author_stage for the granted operation
only: start_case, bind_evidence, register_source or build_deliverables. Supply
the complete public request body in proposal, omitting idempotency_key,
expected_state_sha256 and previous_context; the adapter fixes those from the
mandate. Use a fresh stage idempotency_key. Staging privately previews through
the unchanged public producer against temporary outputs. Do not execute the
public writer on the official run to bypass review.

The human privately reads the entire proposal and producer preview, then
separately confirms author_publish for that exact proposal. The intended
conservation retains the ordinary full request, public state/object or partial
draft, and native receipt. Closed or obsolete mandates cannot authorize context,
staging or publication; they remain privately consultable and cancellable.
Cancellation preserves proposals and history. Unfinished conservation intents
block further writes and Archive closure.

Professional decisions use the distinct app-only decision_setup,
decision_draft_save, decision_preview and decision_commit tools. The human
supplies the actual declared professional, date, decision type, outcome, reason
and exact current dependency versions. Incomplete drafts remain private; neither
name, date, outcome nor confirmation is restored as professional approval.
The public producer binds the eventual decision to the case and selected exact
dependencies. Declared identity is not an authenticated signature; the record
does not assert general ESG compliance or assurance, send or complete a run.

Full ESG reporting and assurance remain unimplemented. No optional native UI
capability is required by the portable ordinary file-based route.

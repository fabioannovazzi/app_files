---
name: open-item-reconciliation
description: Use to verify a supplied elenco partite aperte clienti o fornitori at a cut-off against mastrini, journal, bank statements, payments, factoring, advances or compensation. Produces closed, partly closed and still-open items, residuals and exceptions. For direct estratto conto versus prima nota matching use journal-bank-reconciliation.
---

## Verified execution preparation

Before an assured installed-module handoff, follow Vera's
`skills/vera/references/execution-recovery.md`: run the supported
`scripts/verified_execution.py --module <component-id>` internally and use the
returned execution root for the module skill, commands, assets and review server.
Do not ask the professional to use Terminal. This helper may create a private
verified code copy outside the host installation; it never edits that installation
and is not permission to manually copy it or bypass a denied operation.

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

# Riconciliazione partite

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

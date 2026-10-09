---
name: financial-analysis
description: Use to analyse historical accounting or compare bilanci through source-linked financial schedules, reconciliations, ratios and supported financial due-diligence calculations. For preparing the new bilancio civilistico OIC, nota integrativa or XBRL use bilancio-oic; for a forward-looking business plan use business-planning.
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

# Financial Analysis



Resolve `../../modules/financial-analysis` from this skill directory when it
exists; otherwise resolve `../../../financial-analysis` in the repository.
Read that module's `skills/financial-analysis/SKILL.md` completely and follow
it. Treat the resolved module root as the plugin working directory for all
commands.

For annual historical OIC statements, follow that module's
`references/annual-statements.md` and `run_annual_statements.py` file route.
It produces Word and editable Excel from explicit cell mappings and preserves
source discrepancies. The eight-pack accounting/FDD route does not implement
this annual recipe and must not intercept or block it.

## Native reviewed-case execution and prepared inspection

When `financial_author_setup`, `financial_author_request` and
`financial_author_context` are callable, the optional panel requests a new case
or correction over explicitly chosen registered originals, a named recipe, a
literal professional question and optionally one exact retained predecessor.
Unsent intake fields persist privately with generation CAS and no restored
confirmation. Separate confirmed authorization creates the source mandate.
Read its exact current context and the complete public method; read only those
selected originals through maintained runtime file readers, declaring unread
pages or unsupported material rather than inferring coverage from an inventory.
No provider call is made by the local service. Actual chat/model acceptance is
separate from source or protocol tests.

Propose a complete accounting case using the unchanged public contract shape,
or a pending FDD constructor using `pending_constructor` returned by the context.
That constructor has `schema_version=vera.native.fdd_case_proposal.v1` and the
exact fields `case_id`, `scope_id`, `entity_refs`, `pack_id`, `currency`, `unit`,
`reporting_period`, `package`, `datasets`, `relationships`, `crosswalks`,
`request_id`, `decisions`, `inputs` and `limitations`. Each proposed decision
has only `decision_ref` and its literal `basis`; do not add a reviewer, approval
or fictional review date. Use full source-bound public contracts and the fixed
public FDD input structures. Existing public reviewed bundles may also be
staged, but embedded review claims never authorize native calculation.

`financial_author_stage` receives the exact mandate/current revision,
`proposal={case:complete_case_or_constructor,source_bindings:exact_slot_to_input_id,
note:literal_limits_and_questions}` and an idempotency key. Bind every public
declared source slot to one mandate-selected original. The adapter conserves
immutable proposals and source copies, along with maintained contract/source
checks. These do not parse every source table, run reconciliation, assess
meaning or approve the case. Invalid contracts remain visible and cannot be
adopted as valid. A pending FDD constructor remains explicitly unreviewed.
Read historical proposals by exact `case_ref`; never choose a latest proposal.
Semantic corrections are new complete model proposals or an explicitly selected
predecessor under a new mandate, not edits to a conserved case or result.

The panel separately captures reviewer, exact review date and review basis.
Those unsent fields use candidate-bound generation CAS and are excluded from
model context. Renewed confirmation conserves a new reviewed version; the
proposal and original inputs remain intact. For FDD the unchanged public
`build_fdd_case` receives actual recorded review metadata and proposed decisions,
then the complete bundle is checked again. Public review metadata is tied to
the native actor reference and the named review receipt. No model claim becomes
an approval automatically. Only that separately reviewed version becomes
eligible for the normal public recipe, with its exact reviewed source bindings.
Execution still needs separate confirmation and retains `report_ready=false`,
`source_tie_out=not_assessed` and no approval of financial conclusions.
Open mandates must be reviewed or explicitly cancelled before shared Archive
closure. Cancellation retains evidence and refuses new source context or model
writes. Interrupted conservation requires recovery; never adopt partial success.

When the dedicated `vera_workspace_financial_setup`, `financial_case` and
`financial_execute` tools are callable, reopen the registered running run,
choose one of the eight public recipes and an imported reviewed JSON case, and
explicitly bind every case-declared source ID to one exact registered input.
The panel retains incomplete choices as a private owner-scoped draft; restoring
it does not restore execution confirmation. After renewed confirmation, the
adapter copies the exact case and source bytes under a new immutable calculation
version and invokes the unchanged public pack dispatcher. All ordinary outputs
and receipts are retained. Interrupted execution blocks further writes and
Archive closure until its uncertain outcome is reviewed through the maintained
workflow. Never guess source matches, edit the reviewed contract, or treat
execution as professional approval or completion of the run.

When `vera_workspace_open` is callable, the native workspace can reopen an exact
saved `financial-analysis` run from the maintained Studio Archive. It inspects
one registered prepared pack and its exact producer-declared artifacts. Dedicated
`financial_view` and `financial_explain` tools require an exact retained native
calculation version rather than selecting the latest version. Tables
and JSON members use explicit bounded pages; a child reference requires a new
selection, and discussion reads only that exact artifact/member/page and revision.
Raw sources are excluded from this native prepared inspection. Named source
questions use the module's maintained purpose-recorded evidence-request route;
do not substitute a broad source read. When `financial_source_setup`,
`financial_source_grant` and `financial_source_context` are callable, choose
one exact calculation and one sealed source ID, record the specific professional
question and optionally annotate references. Those annotations do not filter the
file. The separate renewed confirmation authorizes that complete named source
only, invoking unchanged public `model_use.authorize_evidence` on a verified copy
and preserving the immutable original calculation. The public request receipt
and full copied tree are retained. Unsent question drafts remain private,
recoverable and protected by generation CAS; a saved or restored draft does not
authorize source access or restore confirmation.

The source-context tool returns the exact recorded question, one authorized
source path and the selected UTF-8 text page when readable. Text pages may split
records and do not imply complete source inspection; inspect other pages or use
the selected runtime's file reader for that one authorized file when needed.
Binary files are not converted or OCRed by this panel. No other source is
authorized by the request. Interpret the evidence with the full maintained
method, preserving unknowns and actual provenance. Request recording and UI
readback do not prove that a model read the source or approved the conclusion.
Interrupted authorization blocks additional writes and shared Archive closure.

The native inspector checks current case/source/output receipts and the declared
recipe implementation. These checksum checks do not independently repeat the
calculation, assess source tie-out, establish completeness, or approve the
professional conclusion. `report_ready=false` and the existing FDD
`source_tie_out=not_assessed` boundaries remain in force. Changes to meaning, classifications, crosswalks, adjustments or other reviewed
contracts use a new complete proposal and separately reviewed case version,
followed by the normal registered calculation and audit.
Do not interpret a native read or chat handoff as such an update.

Building or changing the reviewed case uses the maintained specialist method,
with its dedicated optional authoring panel when callable. Named original-source requests use the same public route through the
dedicated optional panel or its existing file-based CLI. The shared Archive closure requires its
separate reviewed declarations and actual model-data disclosure; calculation
does not perform it. If the dedicated native tools are absent,
continue the same skill, managed Python and durable Studio Archive files,
including in Cowork. Source mechanisms do not establish installed-host acceptance.

---
name: variance-analysis
description: Use to explain scostamenti Actual versus Budget, Forecast or prior-period accounting results by account, cost centre or available dimensions. Produces reconciled value or supported price-volume-mix variances, charts and reviewable workpapers. For an integrated pack with aging, cash and customer margins use management-control-pack.
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

# Vera Variance Analysis

Route an accountant's management-variance request to the existing Variance
Analysis engine. Resolve the module at
`../../modules/variance-analysis` in an installed Vera package or
`../../../variance-analysis` in this repository. Read that module's
`skills/variance-analysis/SKILL.md` completely and follow it, with the Vera
controls below taking precedence where the host differs. Treat the resolved
module root as the plugin working directory for scripts and dependency checks.



## Host boundary

In Claude, this is a client-bound Vera workflow. Before reading case data,
follow `../vera/SKILL.md` and Studio Archive's client-first sequence using
workflow ID `variance-analysis`: select the exact client and engagement, import
the selected sources as immutable receipts, prepare and start one run, pass the
absolute `client_engagement_path` unchanged as `--client-engagement`, and write
only below its exact `output_dir`. Finalize every physical output as a run
artifact, review it, and complete the run; record failure or cancellation for
an incomplete run. Return only that exact output location.

In Cowork, use only the files and folders the user explicitly connected. The
portable Studio Archive lifecycle is unavailable there, so do not claim that a
Cowork result is a Studio Archive run.

## Accounting intake and review gates

When the optional shared native workspace exposes
`vera_workspace_variance_setup`, open the exact running Archive work there.
Select the registered original and the already prepared comparison recipe,
review currency and output language, inspect the complete declared comparison
and controls, then separately confirm calculation. The panel conserves
incomplete and empty choices without restoring confirmation. It calls the
ordinary rich public runner and preserves its complete output population,
accounting readiness and draft-report status. Read result tables and structured
contexts before chart previews; `vera_workspace_variance_explain` exposes only
the explicitly selected exact CSV/JSON/Markdown page, never the original table
by default. The public widget's fifty-driver preview is not the full result.

When `vera_workspace_variance_author_setup` is available, initial preparation
and comparison correction can start from a private literal question, explicitly
selected original and supporting receipts, optional registered prior recipe,
currency and language. Renewed confirmation conserves the mandate and calls
the public inspector; its suggested mappings are candidates, not semantic
decisions. `vera_workspace_variance_author_context` exposes only this mandate's
authorized source paths/hashes, inspection/skill references and explicitly
selected complete proposal. Read the authorized originals through maintained
readers and report what was actually read. Do not infer a model read from a
copied chat request or panel call.

The host model prepares the complete public recipe and limitations with the
professional. `vera_workspace_variance_author_stage` checks the actual source
columns and public recipe shape without calculation or export. Preserve a
selected prior recipe and its raw reviews; both new professional-review and
root-cause-review slots must remain pending without invented attribution or an
approved alternative. A separate private full-proposal readback records the
literal decision, declared name, actual timezone-aware time and basis. Renewed
signed confirmation imports the comparison and readback into a fresh
same-engagement Archive run with the selected sources. Calculation requires
its own choices and confirmation in that successor. Unsent readback drafts
remain private. Open mandates require conservation or explicit cancellation
before closure; interrupted or altered preparation requires recovery.

When `vera_workspace_variance_review_setup` is available, the panel can record
literal accounting-control decisions and decisions over one explicitly chosen
retained alternative. Read the complete public controls and chosen residual
sequence before deciding. The private draft preserves incomplete decision,
declared reviewer, actual timezone-aware review time and basis without renewing
confirmation. An accepted decision requires the unchanged public accounting
controls to pass; blocked or partial controls cannot be overridden. Signed
renewed confirmation imports immutable comparison and decision receipts into a
fresh same-engagement run, retaining predecessor inputs and outputs. The panel
preselects the exact newly registered comparison only in an empty successor
draft; calculation still requires a separate confirmation. The public runner
alone determines the regenerated report's status. The declared name is not
authenticated, and the panel does not author final interpretation, sign,
deliver or complete the run. Interrupted conservation requires recovery and
blocks repeats and closure. Explicit `vera_workspace_variance_review_explain`
exposes only the selected complete public controls/alternative as untrusted
evidence, omitting private unsent decision fields and the original table.

Model-written final interpretation uses the complete maintained workflow below.
Do not ask the professional to edit JSON. If tools are absent or a complete page exceeds the view limit,
continue with the maintained files and chat. An uncertain or altered native
generation requires specialist recovery before repetition or Archive closure;
do not adopt or overwrite it. Native calculation and reading alone do not
approve a report, complete a run, or prove an installed-host acceptance.

Before calculation, establish from the sources or ask only for unresolved
material choices:

- entity and consolidation perimeter;
- comparison basis: Actual vs Budget, Actual vs Forecast, or current vs prior
  period, including exact periods and fiscal calendar;
- reporting currency and any FX treatment;
- debit/credit and favorable/adverse sign convention;
- amount measure and the account, cost-center, department, entity, product,
  customer, channel, or other reporting dimensions to retain;
- whether units, discounts, and COGS are authoritative enough for the requested
  decomposition;
- the professional's materiality threshold or ranking convention, if one is to
  be applied.

The packaged Vera inspection CLI rejects execution without
`--client-engagement`; the run CLI rejects execution without both
`--client-engagement` and an explicit `--currency`. Never inherit the module's
standalone EUR default. Use amount-only analysis when reliable units are
absent. Run price-volume-mix only when the units basis is present and reviewed.
Do not manufacture volumes, prices, account classifications, cost centers,
causes, favorable/adverse labels, or materiality.

Tie the baseline and comparison totals back to the supplied P&L, trial balance,
management accounts, or approved source totals before interpreting drivers.
The engine's component bridge must reconcile mechanically to total variance.
If either source tie-out or bridge closure cannot be established, mark the
result partial or blocked and do not claim accounting correctness.

Exact arithmetic, period membership after reviewed mappings, component
closure, file identities, and output paths are deterministic controls. The
professional or model-led review owns accounting meaning, semantic causes,
classification, materiality, and management commentary. Keep those judgments
explicitly separate from calculated facts.

## Execution

Run dependency checks from the resolved module, then inspect and review the
suggested recipe before the full run:

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py <bound-input> --output-dir <run-output>/inspection --client-engagement <context.json>
python scripts/run_variance.py <bound-input> --output-dir <run-output>/variance --recipe <reviewed-recipe> --currency <ISO-code> --client-engagement <context.json>
```

Use the complete applicable plot suite from the module: standard waterfall,
component ladder when supported, fixed-dimension bridge, exploded parent/child
bridge, and root-cause bridge with its sweep and drilldowns. Do not add a plot
whose data contract is unavailable. Interpret structured contexts and CSV/JSON
results before chart pixels, and visually inspect every generated chart for
labels, sign direction, clipping, legibility, and reconciliation.

Read `model_use_manifest.json` before opening mapped results and contexts. Use
the complete source only through the module's exact-filter drilldown when a
specific professional question remains unresolved; the deterministic engine
still calculates every selected row.

Validate `review_payload.json` once with the module MCP tools. For a managed
run, include the current absolute `client_engagement` context in that initial
call so persistence resolves the portable `run_root_relative` output
reference. When validation returns a hash-bound local `persistence_token`, use
it for render, save, and apply instead of resending the full review payload.
Save reviewer decisions, apply them, and use `final_artifacts.json` as the
reviewed handoff.

The deterministic report is a visible professional-review draft until
`accounting_review` records an established perimeter, passing source tie-outs,
an established favorable/adverse convention, materiality treatment, named
professional approval, and a reviewed root-cause alternative with rationale.
Only then may its audit status become `approved_for_client_use`.

The final accountant-facing note, written after that review, must state the
comparison and perimeter, source tie-out status, total variance, largest
calculated drivers, reviewed favorable/adverse convention, unresolved data or
judgment items, and links to the tables and variance plots. Narrative causes
must be attributed to supplied evidence or clearly labeled as hypotheses
requiring professional confirmation.

When `vera_workspace_variance_narrative_setup` is available, the optional
panel can retain the three ordinary complete Markdown notes beside the sealed
calculation in the same authoritative run. Explicit
`vera_workspace_variance_narrative_context` returns the verified normal
model-use file references and generated chart references in pages of thirty.
Read the complete manifest and numerical artifacts before chart pixels through
the maintained readers, and record only actual model reads in the normal run
model-data report. References, panel navigation and copied chat requests do not
prove reads. An explicitly selected whole note proposal can be discussed;
private unfinished named readback fields remain omitted.

The host model authors `codex_business_analysis.md`,
`codex_root_cause_sweep_analysis.md` and `run_review.md` in full. Stage all
three literal texts together with `vera_workspace_variance_narrative_stage`.
Interpretation, alternative comparison, residual explanations, evidence-linked
causes or labelled hypotheses, limitations and final-note suitability remain
model/professional judgments. The service checks only shape, exact identities,
file hashes, concurrency and conservation. Complete notes exceeding the stated
96,000-byte serialized payload bound require the maintained file/chat route;
never truncate them to fit the panel.

Select one complete proposal explicitly in the panel, save a literal named
readback with actual timezone-aware time and basis, then renew confirmation.
`vera_workspace_variance_narrative_commit` conserves all three unchanged notes
and `narrative_receipt.json` in a separate versioned folder of the same run.
Rejected notes and requests for correction preserve the complete texts too.
This does not change the accounting report gate, recalculate, authenticate a
reviewer, establish actual model reads, sign, deliver or complete the run.
Draft/blocked comparisons may have diagnostic notes; their accounting status
stays unchanged. A final accountant-facing note requires the public accounting
and root-cause review gates described below. Pending proposals block Archive
closure until an explicit named readback; interrupted conservation requires
specialist recovery. The current source refuses note reopening after Archive completion because
the preceding calculation draft is still bound to the earlier running status.
Completed-run consultation is unqualified and requires a production fix; do
not claim complete native acceptance. The
ordinary independent Cowork file route and its normal outputs remain available.

## Financial report presentation

For comparable monetary results, show the baseline and comparison values together
with both absolute variance in the reporting currency and percentage variance.
Use the existing workflow's reporting charts and structured tables, with units,
periods, aligned numbers, explicit totals and source-supported interpretation.
Do not finish a substantive report with only a compact chat table when normal
artifacts are supported. Use the existing generated report and chart artifacts;
do not invent a custom renderer or manufacture a baseline or monthly breakdown.
Keep zero/negative-base percentages explicitly unavailable where misleading,
retain amount differences, and establish favorable/adverse meaning by account.
A user-requested quick answer or reduced output remains valid.

---
name: variance-analysis
description: Use to explain scostamenti Actual versus Budget, Forecast or prior-period accounting results by account, cost centre or available dimensions. Produces reconciled value or supported price-volume-mix variances, charts and reviewable workpapers. For an integrated pack with aging, cash and customer margins use management-control-pack.
---

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

# Vera Variance Analysis

Route an accountant's management-variance request to the existing Variance
Analysis engine. Resolve the module at
`../../modules/variance-analysis` in an installed Vera package or
`../../../variance-analysis` in this repository. Read that module's
`skills/variance-analysis/SKILL.md` completely and follow it, with the Vera
controls below taking precedence where the host differs. Treat the resolved
module root as the plugin working directory for scripts and dependency checks.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

## Host boundary

In Codex, this is a client-bound Vera workflow. Before reading case data,
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
`codex_root_cause_sweep_analysis.md` and `codex_run_review.md` in full. Stage all
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

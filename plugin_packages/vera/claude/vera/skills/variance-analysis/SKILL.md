---
name: variance-analysis
description: Use when Vera must compare Actual, Budget, Forecast, or prior-period accounting performance, calculate controlled value or price-volume-mix variances, and produce reviewable variance plots and workpapers.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

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

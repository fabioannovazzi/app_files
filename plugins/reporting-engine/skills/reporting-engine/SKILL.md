---
name: reporting-engine
description: Use when Clara needs chart capability manifest evidence, dataset profiling, mechanical chart compatibility checks, or reporting contract inspection before chart/report selection.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling `output/reporting-engine-<run>`
folder next to the user-provided input folder.

# Reporting Engine

Reporting Engine is Clara's non-semantic reporting contract component. It
packages the reviewed source-only chart-selection manifest, role registry,
family selector playbooks, Clara adapter registry, and a unified rendering
entrypoint. Dataset profiles, compatibility audits, and render proofs are
generated only for the current user run outside the repository.

Use this component to answer mechanical questions:

- what chart capabilities exist;
- what roles a chart needs;
- which `reporting-engine.*` adapter owns the chart contract;
- which legacy plugin source is only provenance for that adapter;
- how to render a chosen capability through the adapter boundary;
- what dataset columns are candidate periods, metrics, dimensions, or
  identifiers;
- whether a dataset is mechanically compatible with a chart.

Material choices for this component are limited to the dataset path, output
folder, chart family or capability filter, and whether optional render-library
requirements should be checked. They are not choices to propose as a substitute
for evidence. Inspect the actual inputs first; ask only those unresolved choices in chat. Do not introduce chart, metric, or dimension choices unless the facts cue them.

Do not use this component to claim semantic business validity. It does not know
whether an analysis makes sense for the dataset, whether the user question is
important, or which chart is finally best without a semantic layer or explicit
user direction.

Local data and deterministic-script ownership are part of this workflow.
Deterministic scripts own manifest loading, dataset profiling, role-candidate
extraction, package contract inspection, and mechanical compatibility evidence.
Codex owns interpretation of that evidence and must keep semantic conclusions
separate from the mechanical result.

Explicit approval is reserved for external, destructive, approval-sensitive, or
material steps such as network access, deployment, package release, deleting
files, overwriting user data, or changing the canonical manifest. Local
read-only inspection, profiling into a user-chosen output folder, and contract
summaries can proceed without an approval checkpoint.

Before running helper scripts:

```bash
python scripts/check_dependencies.py
```

This checks the component `requirements.txt`; use `--include-optional` only
when validating render-library requirements.

Useful commands:

```bash
python scripts/reporting_contract.py
python scripts/reporting_adapters.py
python scripts/reporting_adapters.py --capability period_comparison.trend --plan
python scripts/reporting_contract.py --capability period_comparison.trend
python scripts/profile_dataset.py <dataset.csv> --output <run>/dataset_profile.json
python scripts/render_capability.py period_comparison.trend <dataset.csv> --output-dir <run>/render --role-bindings-json '{"period_axis":"Date","comparison_metric":"Sales"}' --artifact-mode data_only
```

Current boundary:

- the source-only manifest is packaged as product contract evidence;
- every manifest capability resolves to a Clara-owned reporting-engine adapter;
- `scripts/render_capability.py` is the stable render entrypoint for a chosen
  capability;
- old chart-family plugin names are provenance, not the caller-facing boundary;
- the chart-family components are embedded in Clara and called through the
  unified render entrypoint;
- the profiler creates runtime dataset-side role candidates;
- Clara may use the evidence to narrow chart choices;
- full report orchestration and semantic validity are intentionally not
  implemented here yet.

## Codex-Native Run UX

For any reporting-engine run, keep a short checklist in chat or in the run
folder. The checklist should cover: inspect the manifest contract, profile the
dataset when one is provided, compare required chart roles with role candidates,
write a Run Intake table, write a Decision Table, and create an Artifact Card.

Default output policy: write user artifacts outside this repository. Catalog
changes, generated ZIPs, and package checks are allowed inside the repo only
when the task is explicitly plugin packaging or release.

The Decision Table should show facts and evidence, not choices to propose. For
example: chart capability, required roles, matched dataset columns, missing
roles, ambiguous roles, invocation contract status, and render-proof status.

Use an execution checkpoint before claiming a chart family is ready: the
manifest must load, the dataset profile must exist when relevant, mechanical
compatibility must be shown, and any missing role must be visible. If a run
creates persistent artifacts, include a `codex_run_review.md` file that links
the manifest, dataset profile, compatibility table, and any final JSON outputs.

## Plugin Improvement Feedback

At the end of every completed or blocked run, briefly identify concrete
improvements that would make this component more useful, such as missing render
adapter coverage, weak role profiling, stale manifest evidence, missing dataset
fixture type, or ambiguous capability wording.

Keep the improvement note local to chat or run artifacts.

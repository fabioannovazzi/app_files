---
name: reporting-engine
description: Use when Clara needs chart capability evidence, dataset profiling, a source-backed dataset semantic layer, mechanical compatibility checks, or reporting contract inspection before chart/report selection.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling `output/reporting-engine-<run>`
folder next to the user-provided input folder.

# Reporting Engine

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Reporting Engine is Clara's reporting contract component. It packages the
reviewed chart-selection manifest, gallery artifact metadata, role registry,
family selector playbooks, Clara adapter registry, stable dataset semantic
contract, and a unified rendering entrypoint. Reviewed semantic layers for user
data are persistent project objects outside the repository. Dataset profiles,
snapshot attachments, compatibility audits, and render proofs are per-run
artifacts outside the repository.

The canonical component root is `../../modules/reporting-engine` relative to
this skill directory in both the editable Clara source and installed Clara
package. Run component helpers with that directory as the working directory.
There is no standalone Reporting Engine plugin or fallback source tree.

Use this component to answer mechanical questions:

- what chart capabilities exist;
- what roles a chart needs;
- which `reporting-engine.*` adapter owns the chart contract;
- which legacy plugin source is only provenance for that adapter;
- how to render a chosen capability through the adapter boundary;
- how to prove the exact input, effective request/recipe, and output bytes for
  that render;
- what dataset columns are candidate periods, metrics, dimensions, or
  identifiers;
- whether a dataset is mechanically compatible with a chart;
- how to create, review, and validate a dataset-specific semantic layer that
  defines metric meaning, aggregation, dimensions, periods, and valid analyses.

Material choices for this component are limited to the dataset path, output
folder, chart family or capability filter, and whether optional render-library
requirements should be checked. They are not choices to propose as a substitute
for evidence. Inspect the actual inputs first; ask only those unresolved choices in chat. Do not introduce chart, metric, or dimension choices unless the facts cue them.

Do not treat the generated scaffold or deterministic validator as semantic
judgment. The scaffold marks every concept `unknown`. Codex or a human must
inspect source evidence and author or review business meaning and analysis
validity. Create semantics once for a stable caller-, connector-, or
project-assigned dataset contract id. On later uploads, reuse that semantic
version through snapshot compatibility; never regenerate semantics merely
because values, rows, members, or date bounds changed. A `contract_valid`
result proves coherent wiring only; it does not
prove the semantic claims are true or choose the final chart.

Local data and deterministic-script ownership are part of this workflow.
Deterministic scripts own manifest loading, dataset profiling, role-candidate
extraction, semantic document scaffolding, reference and role-binding checks,
package contract inspection, and mechanical compatibility evidence. Codex owns
source-backed semantic authoring and interpretation and must keep those
judgments separate from deterministic validation.

Explicit approval is reserved for external, destructive, approval-sensitive, or
material steps such as network access, deployment, package release, deleting
files, overwriting user data, or changing the canonical manifest. Local
read-only inspection, profiling into a user-chosen output folder, and contract
summaries can proceed without an approval checkpoint.

Before running component helper scripts, run this from the Clara plugin root:

```bash
python scripts/check_dependencies.py --module reporting-engine
```

This delegates to the component `requirements.txt`; add `--include-optional`
only when validating render-library requirements. Run the remaining commands
below from `modules/reporting-engine`.

For semantic-layer creation or review, read
`references/semantic_layer.md` before authoring the dataset-specific JSON.

Useful commands:

```bash
python scripts/reporting_contract.py
python scripts/reporting_adapters.py
python scripts/reporting_adapters.py --capability period_comparison.trend --plan
python scripts/reporting_contract.py --capability period_comparison.trend
python scripts/profile_dataset.py <dataset.csv> --output <run>/dataset_profile.json
python scripts/semantic_layer.py init --profile <run>/dataset_profile.json --output <run>/semantic_layer.json
python scripts/semantic_layer.py context --profile <run>/dataset_profile.json --layer <run>/semantic_layer.json --output <run>/semantic_authoring_context.json
python scripts/semantic_layer.py validate --profile <run>/dataset_profile.json --layer <run>/semantic_layer.json --output <run>/semantic_validation.json
python scripts/semantic_layer.py attach --profile <run>/new_snapshot_profile.json --layer <run>/semantic_layer.json --output <run>/snapshot_attachment.json
python scripts/check_compatibility.py <run>/dataset_profile.json --output <run>/compatibility.json
python scripts/render_capability.py period_comparison.trend <dataset.csv> --output-dir <run>/render --role-bindings-json '{"period_axis":"Date","comparison_metric":"Sales"}' --artifact-mode data_only
python scripts/mechanical_acceptance.py --suite --output-dir <empty-run-dir> --execute --artifact-mode data_and_render
```

Current boundary:

- the manifest and gallery artifact metadata are packaged as product contract
  evidence;
- every manifest capability resolves to a Clara-owned reporting-engine adapter;
- `scripts/render_capability.py` is the stable render entrypoint for a chosen
  capability;
- each `render_manifest.json` uses schema `0.2` and records SHA-256 plus byte
  counts for the input and every current-run output, a canonical request
  digest, effective-recipe evidence, and an output-set digest; every invocation
  renders inside a fresh isolated directory so a pre-existing artifact never
  counts as current-run by mere presence;
- old chart-family plugin names are provenance, not the caller-facing boundary;
- the chart-family components are embedded in Clara and called through the
  unified render entrypoint;
- the profiler creates runtime dataset-side role candidates;
- `catalog/semantic_layer.schema.json` defines a persisted stable dataset
  semantic contract with explicit identity and semantic version;
- `scripts/semantic_layer.py` creates an unreviewed scaffold, packages all 48
  manifest analysis types for model-led review, validates evidence and
  canonical-role bindings, attaches mechanically compatible snapshots, and
  resolves reusable period rules into snapshot-specific bounds;
- equal schemas never establish logical dataset identity; the caller, source
  connector, or project configuration must supply the stable contract id;
- changed values, rows, members, and date bounds do not invalidate semantics;
  missing or role-incompatible bound fields disable affected analyses;
- reviewed analysis policies use manifest task and selection-emphasis ids as
  join keys but do not contain or choose a final chart id;
- `contract_valid` and `semantic_readiness` are separate: a mechanically valid
  draft remains `draft_unreviewed`;
- unlisted manifest analysis emphases remain `unknown`; a reviewed semantic
  layer is ready only within its declared scope and does not need one policy per
  chart;
- compatibility evidence distinguishes required roles from optional roles,
  reports candidate and ambiguous columns for both, and only rejects missing
  required roles;
- period-filter charts require a bounded scope or an explicit all-data request,
  while period-axis charts may intentionally use the available range;
- comparison charts require distinct current and baseline periods;
- the root-cause exploded bridge binds a generated alternative driver sequence
  and then one or more one-based drilldown rows; neither choice is hidden in the
  renderer;
- the packaged mechanical acceptance suite currently executes and render-proves
  all 48 capabilities against synthetic fixtures;
- the packaged semantic fixture proves nine valid analysis policies bind
  complete manifest role sets and one unsupported statement analysis remains
  explicitly invalid;
- Clara may use the evidence to narrow chart choices;
- automatic chart selection and full report orchestration are intentionally not
  implemented here.

When a rendered data artifact feeds an HTML deck, seal that CSV or JSON into
the HTML Deck `clara.evidence_bundle.v1` contract and bind the prepared series
or cell. Never copy values from the render manifest into prose or a plot spec.
The current renderer still accepts one input file (except the attribute-package
boundary). Multi-source due-diligence work must first use reviewed semantic and
relationship decisions to materialize deterministic evidence tables; the
renderer must not infer cross-source joins.

## Codex-Native Run UX

For any reporting-engine run, keep a short checklist in chat or in the run
folder. The checklist should cover: inspect the manifest contract, profile the
dataset when one is provided, create or load the dataset semantic layer, validate
its evidence and role bindings, compare required chart roles with role candidates,
write a Run Intake table, write a Decision Table, and create an Artifact Card.

Default output policy: write user artifacts outside this repository. Catalog
changes, generated ZIPs, and package checks are allowed inside the repo only
when the task is explicitly plugin packaging or release.

The Decision Table should show facts and evidence, not choices to propose. For
example: chart capability, required roles, matched dataset columns, missing
roles, ambiguous roles, invocation contract status, and render-proof status.

Use an execution checkpoint before claiming a chart family is ready: the
manifest must load, the dataset profile must exist when relevant, the semantic
layer must be reviewed for any semantic claim, mechanical compatibility must be
shown, and any missing role must be visible. If a run creates persistent
artifacts, include a `codex_run_review.md` file that links the manifest, dataset
profile, semantic layer, semantic validation, compatibility table, and any final
JSON outputs.

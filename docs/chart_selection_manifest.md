# Chart Selection Manifest Approach

Status: draft current approach. The manifest, dataset profile, and first
dataset-specific semantic-layer contract are implemented; automatic selection
is not.

This document describes how the chart selection manifest is intended to work.
It is not a claim that automatic chart selection is solved. It is the current
contract for separating chart-side knowledge from dataset-side facts and future
semantic judgment.

## Goal

The manifest is a selector-facing chart capability contract. Its purpose is to
help a future caller answer three questions:

1. Which chart capabilities could answer this analytical question?
2. What roles must the dataset provide for those capabilities?
3. Which chart-side roles must later be mapped to concrete plugin parameters?

The manifest is not just an artifact inventory. PNG and HTML examples are
evidence for capabilities, but the selector should reason over capability
records, not over filenames or visual gallery labels.

## Current Layers

The approach has four separate layers.

1. Chart selection manifest

   Plot-side only. It describes what each chart capability can do, when it is
   useful, when it should be rejected, which metric and dimension roles it
   needs, what period semantics it supports, and which rendering variants are
   only variants versus true capability choices.

2. Dataset profile

   Dataset-side only. It describes the columns available at runtime: types,
   candidate metrics, candidate dimensions, period columns, cardinality,
   explicit period parseability, grain-like signals, missingness, role
   candidates, and rejected/accepted mechanical evidence. It does not decide
   that an analysis makes business sense.

3. Analysis-validity layer

   Implemented as the dataset-specific semantic-layer contract at
   `plugins/reporting-engine/catalog/semantic_layer.schema.json` with workflow
   support in `plugins/reporting-engine/scripts/semantic_layer.py`. It records
   source-backed metric definitions, aggregation, dimensions, periods, explicit
   scopes, and valid/conditional/invalid analysis policies. A model or human
   authors the semantics; deterministic code scaffolds and validates wiring.

4. Selector or future caller

   Not implemented as a production component. The future caller should join the
   user question, dataset profile, analysis-validity layer, and chart manifest.
   The manifest alone cannot make the final semantic choice.

## Manifest Objects

The packaged manifest lives at
`plugins/reporting-engine/catalog/selection_manifest.json`. Rebuild outputs are
written to `runs/chart_selection_manifest_rebuild/selection_manifest.json` by
`scripts/build_chart_selection_manifest.py`.

Top-level objects:

- `analysis_tasks`: broad analytical families, such as period movement,
  composition, distribution, metric relationship, set overlap, and variance.
  A task can have multiple valid chart treatments.
- `capabilities`: the primary selector contract. Each key is a capability ID
  such as `period_comparison.trend`, `mix.multitier_bar`, or
  `variance.exploded_variance_bridge`.
- `artifacts`: gallery examples and sidecar references. These prove that a
  capability has concrete rendered evidence, but they are not the selector's
  main decision object.
- `role_registry`: canonical mechanical role vocabulary. It lists chart roles,
  profile roles, parameter evidence patterns, and where each role is used.
- `coverage_gaps`: alignment between generated capabilities and gallery
  evidence.
- `selector_audit`: mechanical checks for duplicate signatures, unresolved
  ambiguity, and pairwise overlap.
- `semantic_probes`: small sanity probes that check whether known question
  patterns map to the expected task family.
- `validation_issues`: structural errors found while building the manifest.

## Capability Contract

Each capability record should be read as "this chart can answer this kind of
question when these roles are available."

Important fields:

- `capability_id`: stable chart capability identifier.
- `analysis_task_ids`: broad task families this chart can participate in.
- `selection_emphasis`: the specific reason to choose this chart within a task.
  This is the main tie-breaker between charts that answer similar broad
  questions.
- `visual_grammar`: chart grammar, such as line time series, stacked column,
  bridge, dot gap, table, or scatter.
- `period_semantics`: whether period is an axis, comparison pair, filter,
  scenario, or not applicable.
- `period_scope_contract`: whether the renderer needs an explicit bounded
  analysis period, may use the full available period axis, or must receive an
  explicit all-data request. This prevents a chart from treating a date column
  as if it were also the selected analysis period.
- `metric_requirements`: metric role requirements, including source metric
  count and accepted metric classes.
- `dimension_roles`: dimension roles needed by the chart.
- `dimension_contract`: additional dimensional constraints, such as parent and
  child roles for drilldowns.
- `axis_roles`: how metric, dimension, and period roles map to the visual axes.
- `best_when`: prose guidance for the positive case.
- `avoid_when`: prose guidance for rejection.
- `primary_decision_cue`: structured short statement of the main selector cue.
- `requires_question_focus`: structured focus tokens the question should imply.
- `reject_decision_cues`: structured cues that should push the selector away.
- `forbidden_question_focus`: focus tokens that should not select this chart.
- `competing_capability_ids`: valid alternatives that may answer neighboring
  questions or the same broad task with a different emphasis.
- `selection_contract`: generated selector-facing summary of required roles and
  competing choices.
- `selection_examples`: positive, negative, and ambiguous question examples.
- `normalized_invocation_contract`: generated role-to-parameter proof for the
  capability, including required role contracts, variant role contracts, plugin
  sources, output forms, missing roles, and artifact-level invocation contracts.

The intended selector behavior is not "find one chart for one broad question."
For many IBCS/reporting tasks, multiple charts can answer the same question but
emphasize different details. The manifest must expose the differences so the
future caller can pick a defensible treatment, or keep several candidates when
the question is broad.

## Period Scope

Period handling has two separate mechanical questions:

1. Which dataset column provides period information?
2. Which period scope should the chart render?

For period-axis charts, an unscoped render can be valid because the visible time
range is the chart. A bounded question should still pass scope controls such as
`options.selected_periods`, `options.period_window`, or rolling/fiscal period
options.

For period-filter charts, a period column alone is not enough. The caller must
pass either an explicit bounded analysis period or an explicit all-data request.
Otherwise the renderer can include every available record, which may be valid
only if the caller deliberately asked for that.

## Artifacts And Rendering Variants

Artifacts are examples, not capabilities. The same capability can have multiple
examples.

Every artifact has a `rendering_variant` block:

- `output_form`: image, table, or other output form.
- `layout_variant`: single, small multiples, table, nested drilldown, or
  panelled.
- `encoding_variant`: base, overlay, table, or other encoding distinction.
- `selector_level`: whether the item is a base capability, a true capability
  choice, or only a rendering variant choice.
- `variant_changes_capability_selection`: whether the variant changes chart
  selection rather than only rendering.
- `adds_parameter_roles`: extra roles required by the variant, such as
  `panel_dimension` or `related_marker_metric`.
- `variant_selection_cues`: when this variant is preferred.

Examples:

- Ordinary small multiples are rendering variants when they show the same
  capability with an added panel dimension.
- `set_overlap.upset_small_multiples` is a capability choice because the
  question itself asks how intersections differ across panels.
- `mix.column_overlay` and `mix.stacked_bar_overlay` are capability choices
  because the overlay adds a secondary marker metric to the analytical task.
- Like-for-like charts are not rendering variants. They answer a different
  population question and must remain separate capabilities.

## Intended Selector Flow

A future caller should use the manifest roughly like this:

1. Interpret the question into candidate task families and focus tokens.
2. Read the dataset profile to identify available period, metric, and dimension
   candidates.
3. Filter capabilities whose required roles cannot be satisfied mechanically.
4. Apply the reviewed analysis-validity layer to remove invalid analyses and
   bind approved analysis roles for this dataset.
5. Rank remaining capabilities by `selection_emphasis`, structured decision
   cues, `best_when`, `avoid_when`, and competing capability differences.
6. Map selected semantic roles to concrete dataset columns and plugin
   parameters.
7. Render the chart and compare the output against the capability's stated
   purpose and available gallery evidence.

The manifest supports steps 3, part of 5, and the chart-side part of step 6. The
dataset profiler supports step 2. The semantic-layer contract supports the
persisted evidence, validity, and role bindings needed for step 4, but does not
author those judgments automatically. Step 6 is audited through normalized
invocation contracts and executed through the single
`scripts/render_capability.py` adapter boundary.

## Current Evidence Checks

Generated checks currently include:

- manifest structural validation;
- capability coverage versus gallery evidence;
- pairwise ambiguity audit across capabilities;
- structured decision cue coverage;
- rendering variant classification;
- role registry coverage;
- normalized invocation contract coverage;
- plugin parameter contract audit;
- optional-role candidate, ambiguity, and rejection evidence without treating
  an unavailable optional role as a compatibility failure;
- selection example quality audit;
- per-family selector playbooks;
- per-family selector review;
- dataset profile compatibility audits;
- period-scope preflight in compatibility audits, so period-filter charts can be
  mechanically compatible while still requiring a bounded period or explicit
  all-data request before render;
- question plus PNG review pages;
- stress tests that combine question, manifest, profile compatibility, and PNG
  evidence;
- render/proof matrix that consolidates invocation contract status, dataset
  compatibility, period-scope status, stress-test status, PNG evidence, and
  remaining fixture gaps;
- packaged synthetic mechanical acceptance that profiles datasets, checks every
  capability, binds its roles, executes its component, and validates expected
  rendered artifacts.

The current assessment is written to
`runs/chart_selection_manifest_rebuild/assessment.md`.

As of the latest rebuilt assessment, the manifest reports:

- 48 capabilities;
- 73 artifacts;
- 0 generated-manifest capabilities without gallery examples;
- 0 gallery capabilities without generated manifest records;
- 0 unresolved pairwise ambiguity pairs;
- complete structured decision cue fields for all capabilities;
- 0 used chart roles without parameter-mapping registry entries;
- 48 normalized invocation contracts with `parameter_contract_ready` status.

The plugin parameter contract audit is written to
`runs/chart_selection_manifest_rebuild/plugin_parameter_contract_audit.md`. As
of the latest audit, all 48 capabilities have role-to-parameter evidence and no
missing artifact evidence. The audit also writes normalized invocation
contracts and the shared role registry to JSON.

The durable acceptance evidence is packaged at
`plugins/reporting-engine/catalog/mechanical_acceptance_summary.json`. The
current summary is bound to the manifest digest and records all 48 capabilities
as `component_executed` with `rendered` output proof. Of those records, 43 are
mechanically compatible directly from profiled dataset roles and 5 use an
explicit recipe or packaged-table contract to satisfy roles that cannot come
from an ordinary tabular profile. This is capability-level proof; the 73
artifacts include optional and alternate variants that are not all requested by
one acceptance run.

The render/proof matrix remains a useful development report at
`runs/chart_selection_manifest_rebuild/chart_render_proof_matrix.md`, but the
packaged acceptance summary is the stable release evidence.

The dataset profiles are written to
`runs/chart_selection_manifest_rebuild/dataset_profiles/`. Schema `0.4`
includes period parseability and ordered period values, metric classes and
derived metric candidates, dimension cardinality and missingness, canonical
role candidates with confidence and reason, and exact pairwise dimension
relationships. A bijective label alias is distinguished from a parent-child or
cross-classifying pair so a multidimensional chart cannot satisfy its contract
with two names for the same grouping.

The dataset compatibility audits are written to
`runs/chart_selection_manifest_rebuild/*_dataset_profile_chart_compatibility.md`.
They include `mechanical_role_matches`, `unmatched_required_roles`,
`ambiguous_required_roles`, optional-role matches and ambiguity, and
`rejected_column_evidence` for every checked capability. Rejected-column
evidence is mechanical only: for example, a metric can be rejected because its
metric class is not accepted by the chart role, or a dimension can be rejected
because it does not match a required schema/profile role.

The standalone pairwise ambiguity audit is written to
`runs/chart_selection_manifest_rebuild/pairwise_ambiguity_audit.md`. As of the
latest audit, it finds 7 high-overlap signature groups and 22 high-overlap
pairs; all 22 pairs are resolved with explicit competitor links, ambiguous
example links, negative example links, and no errors or warnings.

`variance.root_cause_exploded_bridge` has a deliberately two-stage structural
contract. First the variance component generates alternative mixed-dimension
driver sequences. The caller binds one alternative through
`options.root_cause_bridge_alternative_result`; it then binds one or more
one-based detail rows through `options.root_cause_bridge_drilldown_rows`. The
manifest and render proof derive the expected drilldown artifact from those
bindings; the renderer does not silently choose an alternative or row.

The selection example quality audit is written to
`runs/chart_selection_manifest_rebuild/selection_example_quality_audit.md`. As
of the latest audit, all 48 capabilities pass with no example-quality errors or
warnings.

The per-family selector playbooks are written to
`runs/chart_selection_manifest_rebuild/family_selector_playbooks/`. As of the
latest generation, there are 9 family files plus an index, covering all 48
capabilities and exposing each family's decision cues, role requirements,
positive examples, ambiguous examples, close competitors, and high-overlap pair
evidence.

The family selector review is written to
`runs/chart_selection_manifest_rebuild/family_selector_review.md`. As of the
latest review, all 9 families are reviewed against positive-question
specificity, close competitors, required/forbidden focus separation, dataset
roles, and PNG/question evidence; the review reports 0 example errors, 0
example warnings, 0 parameter-contract gaps, and 0 asymmetric competitor links.
The crowded families `period_comparison`, `mix`, `variance`, and `distribution`
also include a per-capability manual focus review covering the question,
decision cue, required roles, invocation status, stress status, and render-proof
status.

These checks do not prove semantic correctness. They only prove that the
manifest is internally aligned enough to be used as a chart-side contract.

## What The Manifest Can And Cannot Decide

The manifest can say:

- this chart is a line/time-series treatment;
- this chart compares two periods;
- this chart needs one dimension and optionally a panel dimension;
- this chart is for parent-child variance drilldown;
- this chart should be rejected when the question asks for exact values rather
  than shape;
- this chart has examples and role metadata.

The manifest cannot say by itself:

- whether a specific metric is the right business metric for the question;
- whether two dimensions are semantically related enough to compare;
- whether a dataset's available columns support a meaningful, not just
  mechanical, analysis;
- whether the final report story should choose one valid treatment over another
  without additional context.

Those decisions belong to the reviewed dataset semantic layer plus the caller.
The profile contributes mechanical evidence but cannot make those decisions.

## Remaining Boundary

There is no known base-capability render gap in the current mechanical
acceptance suite. Remaining manifest-side maintenance is to keep fixtures and
the digest-bound summary current when a capability contract changes, and to add
variant-level execution cases where an optional rendering mode has enough risk
to justify separate proof.

The semantic layer remains a separate dataset-specific project object. Its
contract and workflow are documented in
`plugins/reporting-engine/references/semantic_layer.md`. A `contract_valid`
result proves profile, evidence, period-scope, manifest-intent, and role-binding
coherence; it does not prove semantic truth.

## Useful Commands

Rebuild the manifest and assessment:

```bash
source .venv/bin/activate
python scripts/build_chart_selection_manifest.py
```

Run the main manifest-side checks:

```bash
python scripts/audit_chart_artifact_manifest_alignment.py
python scripts/audit_chart_selection_pairwise_ambiguity.py
python scripts/audit_chart_plugin_parameter_contract.py
python scripts/audit_chart_selection_examples.py
python scripts/build_chart_selection_family_playbooks.py
python scripts/build_chart_selection_family_review.py
python scripts/build_chart_selection_setup_audit.py
python scripts/build_chart_selection_stress_test.py
python scripts/build_chart_question_png_review.py
```

Run the packaged end-to-end mechanical acceptance suite:

```bash
python plugins/reporting-engine/scripts/mechanical_acceptance.py \
  --suite \
  --output-dir /tmp/reporting-engine-acceptance \
  --execute \
  --artifact-mode data_and_render
```

Create and validate a dataset-specific semantic layer:

```bash
python plugins/reporting-engine/scripts/profile_dataset.py <dataset.csv> \
  --output <run>/dataset_profile.json
python plugins/reporting-engine/scripts/semantic_layer.py init \
  --profile <run>/dataset_profile.json \
  --output <run>/semantic_layer.json
python plugins/reporting-engine/scripts/semantic_layer.py context \
  --profile <run>/dataset_profile.json \
  --layer <run>/semantic_layer.json \
  --output <run>/semantic_authoring_context.json
python plugins/reporting-engine/scripts/semantic_layer.py validate \
  --profile <run>/dataset_profile.json \
  --layer <run>/semantic_layer.json \
  --output <run>/semantic_validation.json
```

Run focused tests:

```bash
python -m pytest -q \
  tests/scripts/test_build_chart_selection_family_playbooks.py \
  tests/scripts/test_build_chart_selection_family_review.py \
  tests/scripts/test_audit_chart_selection_pairwise_ambiguity.py \
  tests/scripts/test_build_chart_selection_manifest.py \
  tests/scripts/test_build_png_examples_gallery.py \
  tests/scripts/test_static_png_gallery.py \
  tests/scripts/test_validate_png_gallery_manifest.py \
  tests/plugins/test_reporting_engine_semantic_layer.py
```

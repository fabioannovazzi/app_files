# Chart Selection Manifest Approach

Status: draft current approach, expected to change as the selector and semantic
layer are built.

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

   Not implemented yet. This is the future dataset-specific semantic layer. It
   should say which analyses make sense for a dataset and why. For example, it
   should distinguish a mechanically plottable relationship from a meaningful
   business question.

4. Selector or future caller

   Not implemented as a production component. The future caller should join the
   user question, dataset profile, analysis-validity layer, and chart manifest.
   The manifest alone cannot make the final semantic choice.

## Manifest Objects

The generated manifest lives at
`runs/chart_selection_manifest_rebuild/selection_manifest.json` and is produced
by `scripts/build_chart_selection_manifest.py`.

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
4. Apply the future analysis-validity layer to remove semantically invalid
   analyses for this dataset.
5. Rank remaining capabilities by `selection_emphasis`, structured decision
   cues, `best_when`, `avoid_when`, and competing capability differences.
6. Map selected semantic roles to concrete dataset columns and plugin
   parameters.
7. Render the chart and compare the output against the capability's stated
   purpose and available gallery evidence.

The manifest currently supports steps 2, 3, part of 5, and a mechanical check
for step 6. Step 4 is explicitly outside the manifest until the semantic layer
exists. Step 6 is now audited through recipe, catalog, and artifact-contract
evidence, but the plugins still do not expose one normalized invocation schema.

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
- selection example quality audit;
- per-family selector playbooks;
- per-family selector review;
- dataset profile compatibility audits;
- question plus PNG review pages;
- stress tests that combine question, manifest, profile compatibility, and PNG
  evidence;
- render/proof matrix that consolidates invocation contract status, dataset
  compatibility, stress-test status, PNG evidence, and remaining fixture gaps.

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

The render/proof matrix is written to
`runs/chart_selection_manifest_rebuild/chart_render_proof_matrix.md`. As of the
latest matrix, the 48 capabilities are classified as 32 dataset-rendered PNG
proofs, 10 gallery-PNG-plus-parameter proofs, 2 correct dataset rejections, and
4 semantic/package gaps.

The dataset profiles are written to
`runs/chart_selection_manifest_rebuild/dataset_profiles/`. As of schema `0.2`,
period candidates include explicit `period_parseability` with parser type,
sample count, parse-success count, parse-success ratio, parsed min/max, and
inferred grain.

The dataset compatibility audits are written to
`runs/chart_selection_manifest_rebuild/*_dataset_profile_chart_compatibility.md`.
They now include `mechanical_role_matches`, `unmatched_required_roles`,
`ambiguous_required_roles`, and `rejected_column_evidence` for every checked
capability. Rejected-column evidence is mechanical only: for example, a metric
can be rejected because its metric class is not accepted by the chart role, or a
dimension can be rejected because it does not match a required schema/profile
role.

The standalone pairwise ambiguity audit is written to
`runs/chart_selection_manifest_rebuild/pairwise_ambiguity_audit.md`. As of the
latest audit, it finds 8 high-overlap signature groups and 21 high-overlap
pairs; all 21 pairs are resolved with explicit competitor links, ambiguous
example links, negative example links, and no errors or warnings.

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

Those decisions belong to the dataset profile plus the future analysis-validity
layer plus the caller.

## Known Gaps

The next manifest-side gaps are:

- hardening the generated invocation contracts into a stable plugin API schema
  if/when plugins expose one shared callable surface;
- continuing to convert gallery-PNG-plus-parameter proofs into dataset-rendered
  question PNG proofs where a suitable fixture exists. After the current pass,
  10 capabilities still need additional non-semantic render fixtures;
- keeping generated audit outputs linked from stable docs rather than making
  users discover them in `runs/`.

The semantic layer is deliberately left out of this document except for its
boundary, because it is a separate project object and has not been rebuilt yet.

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

Run focused tests:

```bash
python -m pytest -q \
  tests/scripts/test_build_chart_selection_family_playbooks.py \
  tests/scripts/test_build_chart_selection_family_review.py \
  tests/scripts/test_audit_chart_selection_pairwise_ambiguity.py \
  tests/scripts/test_build_chart_selection_manifest.py \
  tests/scripts/test_build_png_examples_gallery.py \
  tests/scripts/test_static_png_gallery.py \
  tests/scripts/test_validate_png_gallery_manifest.py
```

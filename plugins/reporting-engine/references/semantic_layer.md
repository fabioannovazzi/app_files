# Dataset Semantic Layer

Reporting Engine separates four contracts:

1. The chart manifest says what each chart can do and which canonical roles it
   requires.
2. The dataset profile says which columns mechanically look like metrics,
   dimensions, identifiers, and periods.
3. The dataset semantic layer says what those fields mean, how they may be
   aggregated, which analysis families are valid, and why.
4. A future selector may join a question to those three contracts. Selection is
   not implemented by this semantic-layer workflow.

The canonical JSON Schema is `catalog/semantic_layer.schema.json`. The runtime
workflow is `scripts/semantic_layer.py`. User-data semantic layers and their
authoring contexts are run artifacts and must be saved outside the plugin and
repository.

## What The Layer Contains

- A location-independent fingerprint of the exact dataset profile it was
  reviewed against.
- Source inventory and claim-level evidence, including confidence and conflict
  status.
- Reviewed metric definitions, metric classes, aggregation rules, units,
  directionality, period grains, and dimension restrictions.
- Reviewed dimensions, entity meaning, valid uses, and hierarchy.
- Reviewed period columns and explicit single, comparison, rolling, or
  all-available scopes.
- Analysis policies that mark a reusable question family as `valid`,
  `conditional`, `invalid`, or `unknown` for the dataset.
- Canonical manifest `analysis_task_ids`, `selection_emphases`, and role
  bindings for each reviewed analysis policy.
- Open questions and review status.

The semantic layer does not contain a selected chart id. A policy may refer to
manifest selection emphases so the validator can prove that its reviewed
concepts bind the roles needed by one or more matching capabilities. The
manifest still owns chart differences and tie-breakers.

## Workflow

Profile the dataset first:

```bash
python scripts/profile_dataset.py <dataset.csv> \
  --output <run>/dataset_profile.json
```

Create a scaffold:

```bash
python scripts/semantic_layer.py init \
  --profile <run>/dataset_profile.json \
  --output <run>/semantic_layer.json
```

Every generated concept has `status: unknown`. Profiler metric classes and
aggregation guesses appear only under `profile_observation`; they are not
semantic assertions.

Build the model-facing authoring context:

```bash
python scripts/semantic_layer.py context \
  --profile <run>/dataset_profile.json \
  --layer <run>/semantic_layer.json \
  --output <run>/semantic_authoring_context.json
```

The context includes the full mechanical profile, the draft semantic layer,
and all manifest analysis types with their required caller-bound roles. Codex
or another reviewing model must inspect the dataset and authoritative business
sources, then edit the semantic layer. It must preserve conflicts and unknowns
rather than guessing.

Validate the reviewed document:

```bash
python scripts/semantic_layer.py validate \
  --profile <run>/dataset_profile.json \
  --layer <run>/semantic_layer.json \
  --output <run>/semantic_validation.json
```

`contract_valid` means only that identifiers, evidence, columns, periods,
manifest intents, and role bindings are coherent. It does not prove that a
metric definition or business judgment is true. `semantic_readiness` remains
`draft_unreviewed` until the layer is reviewed and contains usable analysis
policies. A reviewed result is `ready_as_scoped_semantic_input`; every manifest
selection emphasis without an explicit reviewed policy remains `unknown`.

## Simple Example

Suppose the profile finds `Sales`, `MarginRate`, `Brand`, and `Date`.
Mechanically, several charts can accept those columns. The semantic layer can
add the facts that:

- `Sales` is additive USD value;
- `MarginRate` is non-additive and must use a sales-weighted mean;
- `Brand` is a valid reporting entity;
- `Date` is a calendar-month key;
- January-February 2026 versus January-February 2025 is the reviewed comparison
  scope.

It can then approve a Brand sales-versus-margin relationship with bindings for
`x_metric`, `y_metric`, and `point_dimension`, and require one aggregated point
per Brand. The validator can prove that the policy is wired to the manifest's
relationship-analysis contract. It cannot prove that the relationship is an
important business question, and it does not choose scatter rather than bubble
unless the reviewed question family and required roles distinguish them.

## Packaged Proof

The synthetic example under `fixtures/semantic_layer/` contains:

- `retail_monthly.csv`: invented monthly retail observations;
- `retail_monthly_source_notes.md`: canonical source definitions;
- `retail_monthly.semantic.json`: a human-reviewed semantic layer.

The example defines four metrics, four dimensions, one calendar, three explicit
period scopes, nine valid analysis policies, and one invalid statement-analysis
policy. It exists to test the contract and carries no customer or real-business
semantics. `catalog/semantic_acceptance_summary.json` binds the validation to
the exact packaged manifest, schema, dataset, source notes, and semantic-layer
digests. Rebuild it with the `semantic_layer.py acceptance` subcommand whenever
one of those inputs changes.

## Design Boundary

Deterministic code is appropriate here for fingerprints, JSON structure,
reference integrity, column existence, date bounds, manifest ids, role kinds,
and required-role completeness. It is not appropriate for deciding what Sales
means, whether MarginRate should be weighted, whether two dimensions make
business sense together, or whether an analysis is useful. Those are
source-backed model or human judgments.

The source-inventory, evidence, coverage, conflict, and open-question
conventions were informed by the current OpenAI Data Analytics
[`create-data-context`](https://github.com/openai/role-specific-plugins/tree/main/plugins/data-analytics/skills/create-data-context)
design. Reporting Engine adds an independent machine-readable
dataset/profile/manifest binding because the OpenAI reference does not define
this chart-analysis validity contract.

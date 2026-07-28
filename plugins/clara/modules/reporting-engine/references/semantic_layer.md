# Dataset Semantic Layer

Reporting Engine separates five contracts:

1. The chart manifest says what each chart can do and which canonical roles it
   requires.
2. A stable dataset contract identifies one logical data asset across uploads.
3. The semantic layer says what that asset's fields mean, how they may be
   aggregated, which reusable period rules apply, and which analyses are valid.
4. Each uploaded snapshot gets a mechanical profile and compatibility record.
5. A future selector may join a question to those contracts. Selection is not
   implemented by this workflow.

The canonical JSON Schema is `catalog/semantic_layer.schema.json`. The runtime
workflow is `scripts/semantic_layer.py`. A reviewed user-data semantic layer is
persistent project data; snapshot profiles, attachments, and authoring contexts
are per-run artifacts. All must be saved outside the plugin and repository.

## What The Layer Contains

- A caller-, connector-, or project-assigned `dataset_contract_id` and explicit
  semantic version.
- The first reviewed snapshot fingerprint as provenance, not as a reuse key.
- Source inventory and claim-level evidence, including confidence and conflict
  status.
- Explicit Sales, Discount, and COGS role mappings. Each role is recorded as
  `mapped`, `absent`, `ambiguous`, or `unknown`, with rationale and
  source-backed evidence when reviewed.
- Reviewed metric definitions, metric classes, aggregation rules, units,
  directionality, period grains, and dimension restrictions.
- Reviewed dimensions, entity meaning, valid uses, and hierarchy.
- Reviewed period columns and reusable rules such as all available, current
  YTD, trailing periods, or current YTD versus prior YTD.
- Analysis policies that mark a reusable question family as `valid`,
  `conditional`, `invalid`, or `unknown` for the dataset.
- Canonical manifest `analysis_task_ids`, `selection_emphases`, and role
  bindings for each reviewed analysis policy.
- Open questions and review status.

The semantic layer does not contain current row counts, values, members,
available date bounds, concrete run windows, or a selected chart id. A policy may refer to
manifest selection emphases so the validator can prove that its reviewed
concepts bind the roles needed by one or more matching capabilities. The
manifest still owns chart differences and tie-breakers.

## Workflow

On the first CSV, XLSX, or Parquet upload, assign a stable dataset contract id
and run intake. The same id must be supplied on later uploads:

```bash
python scripts/dataset_intake.py <dataset.csv> \
  --dataset-contract-id retail_monthly \
  --output-dir <run>
```

That one command writes `dataset_profile.json`, `semantic_layer.draft.json`,
`semantic_authoring_context.json`, and `dataset_intake.json` in the new run
directory. Every generated concept has `status: unknown`; Sales, Discount, and
COGS also begin with `state: unknown`. Profiler metric classes, aggregation
guesses, and column names appear only as observations and candidates. They are
not semantic assertions and never select a canonical business role
automatically.

The context includes the full mechanical profile, the draft semantic layer,
the three canonical business-role review instructions, and all manifest
analysis types with their required caller-bound roles. Codex or another
reviewing model must inspect the dataset and authoritative business sources,
then author the semantic layer on the user's behalf. Do not ask the user to edit
JSON. Preserve conflicts and unknowns rather than guessing; ask one focused
business question only when the available evidence cannot resolve a material
ambiguity.

For each canonical role, record:

- `mapped` when one reviewed metric is the role;
- `absent` when authoritative evidence establishes that the dataset has no
  separate measure for the role;
- `ambiguous` when one or more plausible reviewed metrics remain but no choice
  is supported;
- `unknown` when review has not established any of the other states.

For example, a `DiscountRate` field must not be silently treated as a separate
discount amount, and a unit-cost field must not be silently treated as total
COGS. Likewise, a file containing both gross and net revenue requires source
evidence or a visible ambiguity; the profiler does not choose from the header
text.

Save the reviewed semantic layer as persistent project data outside the plugin
and repository. The run directory keeps only the draft and per-snapshot
artifacts.

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

For every later upload, run intake with the same stable id and reviewed semantic
layer:

```bash
python scripts/dataset_intake.py <new-snapshot.parquet> \
  --dataset-contract-id retail_monthly \
  --semantic-layer <project-data>/retail_monthly.semantic.json \
  --output-dir <run>
```

The intake receipt reports whether the mapping was reused, review is still
required, or the snapshot was rejected. It never overwrites the persistent
semantic layer or silently initializes a replacement.

`compatible` reuses the layer unchanged. `compatible_with_extensions` also
reuses it but leaves new columns unclassified. `partially_compatible` reuses
known semantics while disabling analyses whose bound concepts are unavailable.
`incompatible` rejects the attachment. Changed values, rows, date bounds, and
dimension members do not by themselves change semantic compatibility.

Logical identity is an explicit trust boundary. Equal schemas do not prove that
two anonymous files are the same data asset. A generic upload with no stable id
may be suggested as a candidate match, but this workflow will not attach it by
schema similarity alone. Dataset intake is a local Clara/Codex command, not a
FastAPI route.

## Simple Example

Suppose the profile finds `Sales`, `MarginRate`, `Brand`, and `Date`.
Mechanically, several charts can accept those columns. The reviewed semantic
layer can add the facts that:

- `Sales` is additive USD value and is the canonical Sales role;
- the dataset contains no separate Discount or COGS measure;
- `MarginRate` is non-additive and must use a sales-weighted mean;
- `Brand` is a valid reporting entity;
- `Date` is a calendar-month key;
- current calendar YTD versus aligned prior YTD is a reviewed reusable rule.

If a later snapshot extends through March 2026, the resolver produces January-
March 2026 versus January-March 2025 without changing the semantic layer. It can
also approve a Brand sales-versus-margin relationship with bindings for
`x_metric`, `y_metric`, and `point_dimension`, and require one aggregated point
per Brand. The validator can prove that the policy is wired to the manifest's
relationship-analysis contract. It cannot prove that the relationship is an
important business question, and it does not choose scatter rather than bubble
unless the reviewed question family and required roles distinguish them.

## Packaged Proof

The synthetic example under `fixtures/semantic_layer/` contains:

- `retail_monthly.csv`: invented monthly retail observations;
- `retail_monthly_refresh.csv`: changed values, new months, and a new member;
- `retail_monthly_extension.csv`: a compatible snapshot with one new column;
- `retail_monthly_incompatible.csv`: a snapshot missing all bound metrics;
- `retail_monthly.snapshot_cases.json`: expected reuse outcomes;
- `retail_monthly_source_notes.md`: canonical source definitions;
- `retail_monthly.semantic.json`: a human-reviewed semantic layer.

The example defines four metrics, explicitly maps Sales, records Discount and
COGS as absent, defines four dimensions, one calendar, three reusable period
rules, nine valid analysis policies, and one invalid statement-analysis policy.
It exists to test the contract and carries no customer or real-business
semantics. `catalog/semantic_acceptance_summary.json` binds the validation to
the exact packaged manifest, schema, snapshots, source notes, and semantic-layer
digests. It proves that changed values, months, and members reuse version 1; a
new column is an extension; and missing bound metrics are incompatible. Rebuild
it with the `semantic_layer.py acceptance` subcommand whenever an input changes.

## Design Boundary

Deterministic code is appropriate here for snapshot fingerprints, explicit
dataset-id equality, JSON structure, reference integrity, column existence,
period-rule arithmetic, manifest ids, role kinds, and required-role
completeness. These checks are mechanically verifiable and reproducible. It is
not appropriate for deciding which field is Sales, Discount, or COGS; whether
a role is absent or ambiguous; what Sales means; whether MarginRate should be
weighted; whether two dimensions make business sense together; or whether an
analysis is useful. Those are source-backed model or human judgments.

The source-inventory, evidence, coverage, conflict, and open-question
conventions were informed by the current OpenAI Data Analytics
[`create-data-context`](https://github.com/openai/role-specific-plugins/tree/main/plugins/data-analytics/skills/create-data-context)
design. Reporting Engine adds an independent machine-readable
dataset/profile/manifest binding because the OpenAI reference does not define
this chart-analysis validity contract.

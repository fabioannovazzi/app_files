# Clara Reporting Engine Component

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/clara/modules/reporting-engine) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Reporting Engine is Clara's packaged reporting contract.

It owns:

- the reviewed chart-selection manifest;
- chart role registry and invocation contract evidence;
- Clara adapter registry for every chart family;
- the stable dataset-contract semantic schema, scaffold, authoring context,
  snapshot compatibility, period-rule resolver, and deterministic validator;
- local scripts for reading the contract, profiling user datasets, and rendering one
  chosen capability through the adapter boundary.

The current catalog contains 48 capabilities and 73 documented artifacts. A
packaged synthetic acceptance suite profiles its datasets, checks compatibility,
binds roles to exact recipe parameters, executes every capability, and verifies
the expected rendered output. The durable summary at
`catalog/mechanical_acceptance_summary.json` currently records 48 of 48
capabilities as `component_executed` with rendered proof and binds that evidence
to the exact manifest SHA-256 digest. This proves the base capability contracts;
it does not claim that every optional rendering variant is rendered in the same
run.

The packaged semantic proof under `fixtures/semantic_layer/` binds a synthetic
retail data asset to canonical source notes. It defines four metrics, four
dimensions, one calendar, three reusable period rules, nine valid analysis
policies, and one explicit rejection. Every valid policy binds a complete
manifest role set. Its recurring snapshots prove that changed values, months,
and members reuse the same semantic version; a new column is classified as an
extension; and missing bound metrics reject the snapshot.
`catalog/semantic_acceptance_summary.json` binds that proof to exact manifest,
schema, snapshot, source-note, and semantic-layer digests.

The packaged catalog is source-only. Reviewed semantic layers for user data are
persistent project objects outside the repository. Generated snapshot profiles,
authoring contexts, attachments, compatibility audits, render proofs, and report
artifacts belong in run storage, not in plugin source or the release ZIP.

Reporting Engine owns the semantic-layer contract, not semantic truth. A model
or human must inspect source evidence and author or review metric meaning,
aggregation, valid dimensions, reusable period rules, and analysis validity.
`scripts/semantic_layer.py` deterministically checks that the resulting document
is internally coherent, checks explicit dataset identity and snapshot
compatibility, and resolves concrete period bounds from each snapshot. It does
not decide whether business judgments are true, infer dataset identity from
schema similarity, or orchestrate a report. A future selector should join: user
question, snapshot profile, reviewed semantic layer, and chart manifest.

The old chart-family plugin names are now provenance, not the caller-facing
boundary. Clara embeds those family components and callers should resolve chart
capabilities through the `reporting-engine.*` adapter ids in
`catalog/adapter_registry.json`.

Use `scripts/render_capability.py` as the stable Clara-owned rendering
entrypoint. It accepts a manifest capability id, dataset path, optional recipe,
role bindings, and output directory; it writes a generated recipe when needed,
calls the embedded family component, and records `render_manifest.json`.
The render manifest schema is `0.2`: it binds the run to exact input bytes (or
a directory inventory), a canonical request digest, the effective recipe, and
SHA-256 plus byte counts for every current-run output. Filename proof still
checks that the requested capability rendered, while byte evidence makes the
result suitable for sealing into the HTML Deck evidence contract. A pre-existing
artifact never counts as current-run by mere presence: each invocation renders
inside a fresh isolated directory and publishes only that directory's files.

To start a semantic layer for a profiled dataset:

```bash
python scripts/semantic_layer.py init \
  --profile /tmp/reporting-run/dataset_profile.json \
  --dataset-contract-id retail_monthly \
  --output /tmp/reporting-run/semantic_layer.json
python scripts/semantic_layer.py context \
  --profile /tmp/reporting-run/dataset_profile.json \
  --layer /tmp/reporting-run/semantic_layer.json \
  --output /tmp/reporting-run/semantic_authoring_context.json
python scripts/semantic_layer.py validate \
  --profile /tmp/reporting-run/dataset_profile.json \
  --layer /tmp/reporting-run/semantic_layer.json \
  --output /tmp/reporting-run/semantic_validation.json
python scripts/semantic_layer.py attach \
  --profile /tmp/reporting-run/new_snapshot_profile.json \
  --layer /tmp/reporting-run/semantic_layer.json \
  --output /tmp/reporting-run/snapshot_attachment.json
```

See `references/semantic_layer.md` for the contract and review boundary.

To reproduce the complete mechanical acceptance pass from the component root,
write outputs to an empty directory outside the component:

```bash
python scripts/mechanical_acceptance.py \
  --suite \
  --output-dir /tmp/reporting-engine-acceptance \
  --execute \
  --artifact-mode data_and_render
```

# Reporting Engine

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/reporting-engine) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Reporting Engine is Clara's packaged reporting contract.

It owns:

- the reviewed chart-selection manifest;
- chart role registry and invocation contract evidence;
- Clara adapter registry for every chart family;
- the dataset-specific semantic-layer schema, scaffold, authoring context, and
  deterministic contract validator;
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
retail profile to canonical source notes. It defines four metrics, four
dimensions, one calendar, three explicit period scopes, nine valid analysis
policies, and one explicit rejection. Every valid policy binds a complete
manifest role set. `catalog/semantic_acceptance_summary.json` binds that proof
to exact manifest, schema, dataset, source-note, and semantic-layer digests.

The packaged catalog is source-only. Generated dataset profiles, semantic
layers for user data, authoring contexts, compatibility audits, render proofs,
and report artifacts belong in ignored run directories, not in the plugin
source or release ZIP.

Reporting Engine owns the semantic-layer contract, not semantic truth. A model
or human must inspect source evidence and author or review metric meaning,
aggregation, valid dimensions, period scopes, and analysis validity.
`scripts/semantic_layer.py` deterministically checks that the resulting document
is internally coherent and correctly bound to the supplied dataset profile and
manifest. It does not decide whether those business judgments are true, and it
is not an orchestrator. A future selector should join: user question, dataset
profile, reviewed semantic layer, and chart manifest.

The old chart-family plugin names are now provenance, not the caller-facing
boundary. Clara embeds those family components and callers should resolve chart
capabilities through the `reporting-engine.*` adapter ids in
`catalog/adapter_registry.json`.

Use `scripts/render_capability.py` as the stable Clara-owned rendering
entrypoint. It accepts a manifest capability id, dataset path, optional recipe,
role bindings, and output directory; it writes a generated recipe when needed,
calls the embedded family component, and records `render_manifest.json`.

To start a semantic layer for a profiled dataset:

```bash
python scripts/semantic_layer.py init \
  --profile /tmp/reporting-run/dataset_profile.json \
  --output /tmp/reporting-run/semantic_layer.json
python scripts/semantic_layer.py context \
  --profile /tmp/reporting-run/dataset_profile.json \
  --layer /tmp/reporting-run/semantic_layer.json \
  --output /tmp/reporting-run/semantic_authoring_context.json
python scripts/semantic_layer.py validate \
  --profile /tmp/reporting-run/dataset_profile.json \
  --layer /tmp/reporting-run/semantic_layer.json \
  --output /tmp/reporting-run/semantic_validation.json
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

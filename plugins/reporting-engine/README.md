# Reporting Engine

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/reporting-engine) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Reporting Engine is Clara's packaged non-semantic reporting contract.

It owns:

- the reviewed chart-selection manifest;
- chart role registry and invocation contract evidence;
- Clara adapter registry for every chart family;
- local scripts for reading the contract, profiling user datasets, and rendering one
  chosen capability through the adapter boundary.

The packaged catalog is source-only. Generated dataset profiles, compatibility
audits, render proofs, and report artifacts belong in ignored run directories,
not in the plugin source or release ZIP.

It does not own semantic business validity and it is not yet an orchestrator.
The future selector should join: user question, dataset profile, semantic layer,
and this chart manifest.

The old chart-family plugin names are now provenance, not the caller-facing
boundary. Clara embeds those family components and callers should resolve chart
capabilities through the `reporting-engine.*` adapter ids in
`catalog/adapter_registry.json`.

Use `scripts/render_capability.py` as the stable Clara-owned rendering
entrypoint. It accepts a manifest capability id, dataset path, optional recipe,
role bindings, and output directory; it writes a generated recipe when needed,
calls the embedded family component, and records `render_manifest.json`.
